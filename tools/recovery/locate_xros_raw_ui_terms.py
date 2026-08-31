"""Map exact Japanese Xros UI strings to the ROM resource that contains them.

This is deliberately read-only.  The six hex-menu labels are rendered at
runtime, so editing a PNG plate cannot affect them.  This helper searches the
complete ROM for their Shift-JIS byte sequences and records the owning NitroFS
file (or executable region) for each occurrence.  It provides the evidence
needed before any safe text-table patch is attempted.
"""

from __future__ import annotations

import argparse
import csv
import struct
import sys
from bisect import bisect_right
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))

from rom_research.nds_inventory import read_header, read_nitrofs


TARGETS = {
    "ステータス": "STATUS",
    "わざ": "MOVES",
    "そうび": "EQUIPMENT",
    "たいれつ": "FORMATION",
    "もちもの": "ITEMS",
    "マップ": "MAP",
    "じょうほう": "INFO",
    "もどる": "BACK",
    "バトルほうしゅう": "BATTLE RESULTS",
    "つぎへ": "NEXT",
}


def executable_regions(rom: bytes, header: dict[str, int | str]) -> list[tuple[int, int, str]]:
    regions: list[tuple[int, int, str]] = []
    arm9_offset = int(header["arm9_offset"])
    arm9_size = int(header["arm9_size"])
    if arm9_offset and arm9_size:
        regions.append((arm9_offset, arm9_offset + arm9_size, "<ARM9 executable>"))
    # Overlay table records are 0x20 bytes; fields 24/28 point to ROM data.
    off = int(header["arm9_overlay_offset"])
    size = int(header["arm9_overlay_size"])
    for index in range(0, size, 0x20):
        row = rom[off + index:off + index + 0x20]
        if len(row) < 0x20:
            break
        overlay_id, _ram, _ram_size, _bss, _sin, _sout, file_id, _reserved = struct.unpack("<8I", row)
        # The overlay binary itself has a normal NitroFS file id and will be
        # found there. Keep an explicit label only for malformed tables.
        if file_id == 0xFFFFFFFF:
            continue
    return regions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("output_tsv", type=Path)
    args = parser.parse_args()

    rom = args.rom.read_bytes()
    with args.rom.open("rb") as handle:
        header = read_header(handle)
        files = read_nitrofs(handle, header)

    regions = [(item.offset, item.offset + item.size, item.path.replace("\\", "/")) for item in files]
    regions.extend(executable_regions(rom, header))
    regions.sort(key=lambda row: row[0])
    starts = [row[0] for row in regions]

    def owner(address: int) -> tuple[str, int]:
        pos = bisect_right(starts, address) - 1
        if pos >= 0:
            begin, end, name = regions[pos]
            if begin <= address < end:
                return name, address - begin
        return "<outside NitroFS>", address

    rows: list[tuple[str, str, str, str, str, str, str]] = []
    for japanese, english in TARGETS.items():
        needle = japanese.encode("shift_jis")
        cursor = 0
        while True:
            found = rom.find(needle, cursor)
            if found < 0:
                break
            resource, relative = owner(found)
            before = rom[found - 1:found].hex().upper() if found else ""
            after_offset = found + len(needle)
            after = rom[after_offset:after_offset + 1].hex().upper()
            rows.append((japanese, english, f"0x{found:08X}", resource, f"0x{relative:X}", before, after))
            cursor = found + 1

    args.output_tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_tsv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(("japanese", "english", "rom_offset", "resource", "resource_offset", "byte_before", "byte_after"))
        writer.writerows(rows)
    print(f"Mapped {len(rows)} raw UI-string occurrences across {len(files)} NitroFS files")
    print(args.output_tsv.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
