#!/usr/bin/env python3
"""Rank Xros PAK graphics by exact tiles currently resident in DS VRAM.

The game copies already-rendered 4bpp tiles into a background VRAM bank.  This
tool compares those exact 32-byte tiles against decompressed NCGR members in a
ROM, allowing a live UI screen to identify its actual archive/member instead
of relying on an assumed filename or an old contact sheet.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))

from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, identify_entry, read_nitro_file  # noqa: E402


TILE_SIZE = 32  # Nintendo DS 4bpp 8x8 tile.


def tiles(data: bytes) -> set[bytes]:
    return {
        hashlib.sha1(data[offset : offset + TILE_SIZE]).digest()
        for offset in range(0, len(data) - TILE_SIZE + 1, TILE_SIZE)
        if any(data[offset : offset + TILE_SIZE])
    }


def ncgr_tiles(data: bytes) -> set[bytes]:
    """Return raw DS character tiles, excluding the Nitro NCGR header.

    The first 0x30 bytes of an NCGR are container metadata, not 4bpp tile
    pixels.  Comparing a VRAM bank with the whole file shifts every candidate
    by 16 bytes and produces weak, misleading matches.  VRAM stores the raw
    character data exactly as it starts at offset 0x30 in these Xros NCGRs.
    """
    if len(data) < 0x30:
        return set()
    return tiles(data[0x30:])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("vram", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--top", type=int, default=100)
    parser.add_argument("--offset", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--length", type=lambda value: int(value, 0), default=None)
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="ARCHIVE:ENTRY",
        help="Remove tiles supplied by a known archive member before ranking; repeatable",
    )
    args = parser.parse_args()

    vram = args.vram.read_bytes()
    end = len(vram) if args.length is None else min(len(vram), args.offset + args.length)
    if args.offset < 0 or args.offset >= end:
        raise ValueError("Selected VRAM range is empty")
    resident = tiles(vram[args.offset:end])
    rows: list[dict[str, object]] = []
    with args.rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        excluded: set[bytes] = set()
        requested_exclusions: list[tuple[str, int]] = []
        for specification in args.exclude:
            archive, separator, entry_text = specification.rpartition(":")
            if not separator or not archive:
                raise ValueError(f"Invalid exclusion {specification!r}; expected ARCHIVE:ENTRY")
            requested_exclusions.append((archive.upper(), int(entry_text, 0)))
        if requested_exclusions:
            for nitro in files:
                archive_name = nitro.path.upper()
                wanted = {entry for archive, entry in requested_exclusions if archive_name.endswith(archive)}
                if not wanted:
                    continue
                pak = XrosPak.from_bytes(read_nitro_file(handle, nitro))
                by_index = {entry.index: entry for entry in pak.entries}
                for entry_index in wanted:
                    if entry_index not in by_index:
                        raise ValueError(f"Missing exclusion {nitro.path}:{entry_index}")
                    excluded |= ncgr_tiles(pak.unpacked_data(by_index[entry_index]))
            resident -= excluded
        for nitro in files:
            if not nitro.path.upper().endswith(".PAK"):
                continue
            try:
                pak = XrosPak.from_bytes(read_nitro_file(handle, nitro))
            except Exception:
                continue
            for entry in pak.entries:
                try:
                    payload = pak.unpacked_data(entry)
                except Exception:
                    continue
                if identify_entry(payload) != "NCGR":
                    continue
                candidate_tiles = ncgr_tiles(payload)
                overlap = len(resident & candidate_tiles)
                if overlap:
                    rows.append(
                        {
                            "matches": overlap,
                            "resident_coverage_pct": round(100 * overlap / max(1, len(resident)), 3),
                            "entry_coverage_pct": round(100 * overlap / max(1, len(candidate_tiles)), 3),
                            "nitrofs_path": nitro.path,
                            "nitrofs_offset": f"0x{nitro.offset:08X}",
                            "entry": entry.index,
                            "entry_size": len(payload),
                        }
                    )
    rows.sort(key=lambda row: (int(row["matches"]), float(row["entry_coverage_pct"])), reverse=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["matches", "resident_coverage_pct", "entry_coverage_pct", "nitrofs_path", "nitrofs_offset", "entry", "entry_size"]
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows[: args.top])
    print(
        f"VRAM range 0x{args.offset:X}-0x{end:X}; resident tiles after exclusions: "
        f"{len(resident)} (removed {len(excluded)} known tiles); matching NCGR members: "
        f"{len(rows)}; wrote {args.out}"
    )
    for row in rows[:10]:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
