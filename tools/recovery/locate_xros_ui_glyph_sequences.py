#!/usr/bin/env python3
"""Search Xros resources and RAM for direct NFTR glyph-index sequences.

Some menu labels are absent as Shift-JIS even while visibly rendered.  One
plausible representation is a table of font glyph indices.  This read-only
probe derives the indices from the ROM's own NFTR and searches decompressed
code, NitroFS/PAK members, and supplied RAM captures in common byte layouts.
"""

from __future__ import annotations

import argparse
import csv
import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EDITOR = ROOT / "work" / "DigimonNDSRomEditor-master"
NFTR_TOOLS = ROOT / "work" / "reference" / "DSLEChsLocalization" / "scripts"
sys.path[:0] = [str(EDITOR), str(NFTR_TOOLS)]

from nftr import NFTR  # noqa: E402
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, find_nitro_file, read_nitro_file  # noqa: E402


TERMS = {
    "status": "ステータス",
    "skills": "わざ",
    "equip": "そうび",
    "formation": "たいれつ",
    "items_inventory": "もちもの",
    "items": "アイテム",
    "map": "マップ",
    "info": "じょうほう",
    "back": "もどる",
    "orders": "めいれい",
    "digixros": "デジクロス",
    "battle_results": "バトルけっか",
    "battle_rewards": "バトルほうしゅう",
    "next": "つぎへ",
    "tactics": "さくせん",
    "wisdom": "かしこさ",
    "speed": "すばやさ",
    "defense": "まもり",
    "bond": "ゆうじょう",
}


def all_offsets(data: bytes, needle: bytes):
    cursor = 0
    while needle:
        cursor = data.find(needle, cursor)
        if cursor < 0:
            return
        yield cursor
        cursor += 1


def font_index_maps(rom: Path) -> list[tuple[int, dict[int, int]]]:
    with rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        raw = read_nitro_file(handle, find_nitro_file(files, "FONT_NFTR.PAK"))
    pak = XrosPak.from_bytes(raw)
    mappings: list[tuple[int, dict[int, int]]] = []
    for entry in pak.entries:
        font = NFTR(pak.unpacked_data(entry))
        mapping: dict[int, int] = {}
        for cmap in font.cmaps:
            mapping.update(cmap.index_map)
        mappings.append((entry.index, mapping))
    return mappings


def character_code(character: str) -> int:
    encoded = character.encode("shift_jis")
    return int.from_bytes(encoded, "big")


def patterns(font_entry: int, mapping: dict[int, int]):
    for term, text in TERMS.items():
        try:
            indices = [mapping[character_code(ch)] for ch in text]
        except KeyError:
            continue
        if all(0 <= value <= 0xFF for value in indices):
            yield term, text, font_entry, "glyph_u8", bytes(indices), indices
        yield term, text, font_entry, "glyph_u16le", b"".join(struct.pack("<H", value) for value in indices), indices
        yield term, text, font_entry, "glyph_u16be", b"".join(struct.pack(">H", value) for value in indices), indices


def source_blobs(rom: Path, code_dir: Path | None, captures: list[Path]):
    if code_dir and code_dir.exists():
        for path in sorted(code_dir.rglob("*.bin")):
            yield "decompressed_code", str(path), path.read_bytes()
    for capture in captures:
        if capture.is_file():
            yield "runtime_capture", str(capture), capture.read_bytes()
        elif capture.exists():
            for path in sorted(capture.rglob("*.bin")):
                yield "runtime_capture", str(path), path.read_bytes()
    with rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        for item in files:
            handle.seek(item.offset)
            data = handle.read(item.size)
            yield "nitrofs", item.path, data
            if len(data) < 8 or data[4:8] != b"2.01":
                continue
            try:
                pak = XrosPak.from_bytes(data)
            except ValueError:
                continue
            for entry in pak.entries:
                try:
                    unpacked = pak.unpacked_data(entry)
                except ValueError:
                    continue
                yield "xros_pak", f"{item.path}::entry_{entry.index:04d}", unpacked


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--code-dir", type=Path)
    parser.add_argument("--capture", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    wanted = [
        pattern
        for font_entry, mapping in font_index_maps(args.rom)
        for pattern in patterns(font_entry, mapping)
    ]
    rows: list[tuple[str, str, int, str, str, str, str, str]] = []
    for container, member, data in source_blobs(args.rom, args.code_dir, args.capture):
        for term, text, font_entry, layout, needle, indices in wanted:
            for offset in all_offsets(data, needle):
                rows.append(
                    (
                        term,
                        text,
                        font_entry,
                        layout,
                        " ".join(f"{value:04X}" for value in indices),
                        container,
                        member,
                        f"0x{offset:X}",
                    )
                )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(("term", "japanese", "font_entry", "layout", "glyph_indices", "container", "member", "offset"))
        writer.writerows(sorted(rows))
    print(f"Wrote {len(rows)} hits to {args.out}")
    counts = {key: 0 for key in TERMS}
    for row in rows:
        counts[row[0]] += 1
    for key, count in counts.items():
        print(f"{key}\t{count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
