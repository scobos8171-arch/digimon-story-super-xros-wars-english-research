#!/usr/bin/env python3
"""Inventory every valid Xros 2.01 PAK embedded in a ROM image.

NitroFS paths only show the current file table.  Rebuilt Xros ROMs may retain
older, fixed-offset PAK copies that the executable still opens directly.  This
scanner reports those physical copies so a localization patch can target the
archive the game actually uses.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))

from rom_research.xros_pak import XrosPak  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--min-entries", type=int, default=1)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    data = args.rom.read_bytes()
    hits: list[dict[str, object]] = []
    cursor = 0
    while True:
        signature = data.find(b"2.01", cursor)
        if signature < 0:
            break
        cursor = signature + 1
        base = signature - 4
        if base < 0:
            continue
        try:
            pak = XrosPak.from_bytes(data[base:])
        except Exception:
            continue
        if len(pak.entries) < args.min_entries:
            continue
        end = max(entry.offset + entry.stored_size for entry in pak.entries)
        hits.append(
            {
                "offset": f"0x{base:08X}",
                "size": end,
                "entries": len(pak.entries),
                "entry_196": (
                    {
                        "offset": f"0x{pak.entries[196].offset:08X}",
                        "stored_size": pak.entries[196].stored_size,
                        "uncompressed_size": pak.entries[196].uncompressed_size,
                    }
                    if len(pak.entries) > 196
                    else None
                ),
            }
        )
    report = {"rom": str(args.rom), "pak_copies": hits}
    rendered = json.dumps(report, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
