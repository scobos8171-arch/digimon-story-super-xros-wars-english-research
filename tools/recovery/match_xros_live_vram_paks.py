#!/usr/bin/env python3
"""Match consecutive live VRAM tiles against every decompressed Xros PAK member."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))

from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, read_nitro_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("vram", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--minimum-run", type=int, default=4)
    args = parser.parse_args()

    live = args.vram.read_bytes()
    live_tiles: dict[bytes, list[int]] = defaultdict(list)
    for offset in range(0, len(live) - 31, 32):
        tile = live[offset:offset + 32]
        if tile != b"\0" * 32 and tile != b"\xff" * 32:
            live_tiles[tile].append(offset)

    rows: list[dict[str, object]] = []
    with args.rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        for item in files:
            raw = read_nitro_file(handle, item)
            if len(raw) < 8 or raw[4:8] != b"2.01":
                continue
            try:
                pak = XrosPak.from_bytes(raw)
            except Exception:
                continue
            for entry in pak.entries:
                try:
                    data = pak.unpacked_data(entry)
                except Exception:
                    continue
                for phase in range(32):
                    source = range(phase, len(data) - 31, 32)
                    offsets = list(source)
                    index = 0
                    while index < len(offsets):
                        start = offsets[index]
                        candidates = live_tiles.get(data[start:start + 32], ())
                        best = 0
                        best_live = 0
                        for live_start in candidates:
                            run = 1
                            while (
                                index + run < len(offsets)
                                and live_start + run * 32 + 32 <= len(live)
                                and data[offsets[index + run]:offsets[index + run] + 32]
                                == live[live_start + run * 32:live_start + run * 32 + 32]
                            ):
                                run += 1
                            if run > best:
                                best, best_live = run, live_start
                        if best >= args.minimum_run:
                            rows.append({
                                "archive": item.path,
                                "entry": entry.index,
                                "source_offset": f"0x{start:X}",
                                "vram_offset": f"0x{best_live:X}",
                                "tiles": best,
                                "bytes": best * 32,
                            })
                            index += best
                        else:
                            index += 1

    rows.sort(key=lambda row: (-int(row["tiles"]), str(row["archive"]), int(row["entry"])))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} runs; best={rows[:20]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
