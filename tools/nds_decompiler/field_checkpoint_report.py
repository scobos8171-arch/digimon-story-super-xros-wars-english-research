#!/usr/bin/env python3
"""Extract field checkpoints and summarize consecutive main-RAM differences."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from state_memory import parse_memory_blocks, unpack_state
from memory_diff import changed_runs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest_path = args.capture_dir / "checkpoints.tsv"
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        checkpoints = list(csv.DictReader(handle, delimiter="\t"))

    extracted = args.capture_dir / "extracted"
    extracted.mkdir(parents=True, exist_ok=True)
    usable = []
    for entry in checkpoints:
        state = Path(entry["state"])
        if not state.exists():
            continue
        blocks = parse_memory_blocks(unpack_state(state))
        ram = blocks.get("WRAM")
        if ram is None:
            continue
        destination = extracted / (state.stem + "_wram.bin")
        destination.write_bytes(ram)
        usable.append((entry, ram, destination))

    comparisons = []
    hot_addresses: Counter[str] = Counter()
    for (before, left, left_path), (after, right, right_path) in zip(usable, usable[1:]):
        runs = changed_runs(left, right)
        for run in runs:
            hot_addresses[run["address"]] += 1
        comparisons.append({
            "before": before,
            "after": after,
            "before_ram": str(left_path),
            "after_ram": str(right_path),
            "changed_byte_runs": len(runs),
            "runs": runs,
        })

    result = {
        "checkpoint_count": len(usable),
        "comparison_count": len(comparisons),
        "frequently_changing_addresses": hot_addresses.most_common(100),
        "comparisons": comparisons,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}: {len(usable)} checkpoints, {len(comparisons)} comparisons")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

