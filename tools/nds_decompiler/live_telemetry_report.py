#!/usr/bin/env python3
"""Turn change-only DeSmuME telemetry into a compact, named battle timeline."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def name_map(root: Path) -> dict[int, str]:
    result: dict[int, str] = {}
    for path in root.glob("*/metadata.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        name = data.get("display_name", path.parent.name)
        for variant in data.get("source_variants", []):
            if variant.get("source_game") in {"xros_blue", "xros_red"}:
                try:
                    result[int(variant["internal_id"])] = name
                except (KeyError, TypeError, ValueError):
                    pass
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("telemetry", type=Path)
    parser.add_argument("digimon_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    names = name_map(args.digimon_root)
    rows = []
    with args.telemetry.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if not row.get("species_id"):
                continue
            species = int(row["species_id"])
            row["name"] = names.get(species, f"species_{species}")
            rows.append(row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Live battle timeline", "", f"Captured slot changes: **{len(rows)}**", "",
             "| Frame | Slot | Digimon | Lv | HP | SP | Status | Selected command |",
             "|---:|---:|---|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(
            f"| {row['frame']} | {row['slot']} | {row['name']} | {row['level']} | "
            f"{row['hp']}/{row['max_hp']} | {row['sp']}/{row['max_sp']} | "
            f"{row['status']} | {row['selected_14c']} / {row['selected_150']} |"
        )
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} ({len(rows)} changes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

