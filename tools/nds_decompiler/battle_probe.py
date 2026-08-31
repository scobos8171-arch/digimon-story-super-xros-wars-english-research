#!/usr/bin/env python3
"""Rank live HP/SP memory candidates from two DeSmuME battle save states."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.nds_decompiler.state_memory import overlay_matches, parse_memory_blocks, unpack_state


MAIN_RAM_BASE = 0x02000000


def value_transitions(
    before: bytes,
    after: bytes,
    *,
    old_value: int | None = None,
    new_value: int | None = None,
    direction: str = "decrease",
    widths: tuple[int, ...] = (2, 4),
    limit: int = 250,
) -> list[dict[str, object]]:
    """Return ranked little-endian scalar transitions in main RAM.

    Known on-screen values produce a narrow, high-confidence result. Without
    known values, conservative bounds keep the report useful for HP/SP-like
    counters rather than returning every animation and timer change.
    """
    if len(before) != len(after):
        raise ValueError("memory dumps must have equal lengths")
    results: list[dict[str, object]] = []
    for width in widths:
        if width not in (1, 2, 4):
            raise ValueError("supported widths are 1, 2, and 4 bytes")
        for offset in range(0, len(before) - width + 1):
            left = int.from_bytes(before[offset : offset + width], "little")
            right = int.from_bytes(after[offset : offset + width], "little")
            if left == right:
                continue
            if old_value is not None and left != old_value:
                continue
            if new_value is not None and right != new_value:
                continue
            if old_value is None and new_value is None:
                if max(left, right) > 65535:
                    continue
                delta = right - left
                if direction == "decrease" and not (-10000 <= delta < 0):
                    continue
                if direction == "increase" and not (0 < delta <= 10000):
                    continue
                if direction == "any" and abs(delta) > 10000:
                    continue
            score = 0
            score += 100 if old_value is not None else 0
            score += 100 if new_value is not None else 0
            score += 12 if width == 2 else 5 if width == 4 else 0
            score += 5 if offset % width == 0 else 0
            score += 3 if 0 <= left <= 9999 and 0 <= right <= 9999 else 0
            results.append(
                {
                    "address": f"0x{MAIN_RAM_BASE + offset:08x}",
                    "offset": f"0x{offset:06x}",
                    "width": width,
                    "before": left,
                    "after": right,
                    "delta": right - left,
                    "score": score,
                    "context_before": before[max(0, offset - 8) : offset + width + 8].hex(),
                    "context_after": after[max(0, offset - 8) : offset + width + 8].hex(),
                }
            )
    results.sort(key=lambda row: (-int(row["score"]), int(str(row["offset"]), 16), int(row["width"])))
    return results[:limit]


def _wram_from_state(path: Path) -> bytes:
    blocks = parse_memory_blocks(unpack_state(path))
    if "WRAM" not in blocks:
        raise ValueError(f"WRAM block was not found in {path}")
    return blocks["WRAM"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path, help="state saved at the battle command menu")
    parser.add_argument("after", type=Path, help="state saved after HP/SP values settle")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overlays", type=Path)
    parser.add_argument("--hp-before", type=int)
    parser.add_argument("--hp-after", type=int)
    parser.add_argument("--sp-before", type=int)
    parser.add_argument("--sp-after", type=int)
    parser.add_argument("--limit", type=int, default=250)
    args = parser.parse_args()

    before = _wram_from_state(args.before)
    after = _wram_from_state(args.after)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "before_wram.bin").write_bytes(before)
    (args.output / "after_wram.bin").write_bytes(after)

    report: dict[str, object] = {
        "before_state": str(args.before),
        "after_state": str(args.after),
        "active_overlays_before": [row for row in overlay_matches(before, args.overlays) if row["loaded_match"]],
        "active_overlays_after": [row for row in overlay_matches(after, args.overlays) if row["loaded_match"]],
        "known_values": {
            "hp_before": args.hp_before,
            "hp_after": args.hp_after,
            "sp_before": args.sp_before,
            "sp_after": args.sp_after,
        },
    }
    report["hp_candidates"] = value_transitions(
        before,
        after,
        old_value=args.hp_before,
        new_value=args.hp_after,
        direction="decrease",
        limit=args.limit,
    )
    report["sp_candidates"] = value_transitions(
        before,
        after,
        old_value=args.sp_before,
        new_value=args.sp_after,
        direction="decrease",
        limit=args.limit,
    )
    if args.hp_before is None and args.hp_after is None:
        report["generic_decreases"] = value_transitions(before, after, direction="decrease", limit=args.limit)

    destination = args.output / "battle_probe.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {destination}")
    print(f"HP candidates: {len(report['hp_candidates'])}")
    print(f"SP candidates: {len(report['sp_candidates'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
