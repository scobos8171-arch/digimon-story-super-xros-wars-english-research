#!/usr/bin/env python3
"""Paint native-size English directly into the seven Xros hex caption OAMs."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))

from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, compress_xros_lz, find_nitro_file, read_nitro_file  # noqa: E402

ENTRY = 198
TILE_BYTES = 32
RUNTIME_GRAPHICS_SHADOW_OFFSET = 0x0136C600
RUNTIME_GRAPHICS_SHADOW_SIZE = 14872324
FONT = {
    "A": ("0110", "1001", "1001", "1111", "1001", "1001", "1001"),
    "E": ("1111", "1000", "1000", "1110", "1000", "1000", "1111"),
    "F": ("1111", "1000", "1000", "1110", "1000", "1000", "1000"),
    "I": ("111", "010", "010", "010", "010", "010", "111"),
    "K": ("1001", "1010", "1100", "1000", "1100", "1010", "1001"),
    "L": ("1000", "1000", "1000", "1000", "1000", "1000", "1111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("1001", "1101", "1101", "1011", "1011", "1001", "1001"),
    "O": ("0110", "1001", "1001", "1001", "1001", "1001", "0110"),
    "P": ("1110", "1001", "1001", "1110", "1000", "1000", "1000"),
    "Q": ("0110", "1001", "1001", "1001", "1011", "1010", "0101"),
    "R": ("1110", "1001", "1001", "1110", "1010", "1001", "1001"),
    "S": ("0111", "1000", "1000", "0110", "0001", "0001", "1110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("1001", "1001", "1001", "1001", "1001", "1001", "0110"),
}
# Caption OAM segments from the live command-ring capture.  The 48-pixel
# captions are *not* one contiguous tile block: the 32px and 16px OAMs use
# independently addressed columns in 2D OBJ mapping.  Earlier builds treated
# them as contiguous and consequently painted unrelated tile rows.
LABELS = (
    (((12, 32), (14, 16)), "STATUS"),
    (((35, 32),), "SKILLS"),
    (((41, 32), (43, 16)), "EQUIP"),
    (((48, 32), (50, 16)), "FORMATION"),
    (((55, 32), (57, 16)), "ITEMS"),
    (((62, 32), (64, 16)), "MAP"),
    (((69, 32), (71, 16)), "INFO"),
)


def write_pixel(raw: bytearray, segments: tuple[tuple[int, int], ...], x: int, y: int, value: int) -> None:
    """Write to a logical caption canvas backed by the live OBJ mapping.

    The sub engine uses 1D OBJ mapping with a 128-byte character boundary.
    Consequently attr2's character name is multiplied by four to obtain the
    physical 4bpp tile index.  Tiles inside each object are then contiguous.
    """
    offset_x = x
    for base, width in segments:
        if offset_x < width:
            tile = base * 4 + (y // 8) * (width // 8) + (offset_x // 8)
            break
        offset_x -= width
    else:
        raise ValueError(f"caption x={x} is outside its OAM segments")
    offset = 0x30 + tile * TILE_BYTES + (y % 8) * 4 + (x % 8) // 2
    previous = raw[offset]
    raw[offset] = (previous & 0xF0) | value if x % 2 == 0 else (previous & 0x0F) | (value << 4)


def clear_overlay(raw: bytearray, segments: tuple[tuple[int, int], ...]) -> None:
    width = sum(width for _base, width in segments)
    for y in range(16):
        for x in range(width): write_pixel(raw, segments, x, y, 0)


def text_width(text: str) -> int:
    return sum(len(FONT[letter][0]) for letter in text) + len(text) - 1


def draw_label(raw: bytearray, segments: tuple[tuple[int, int], ...], text: str) -> None:
    width = sum(width for _base, width in segments)
    clear_overlay(raw, segments)
    total = text_width(text)
    x = (width - total) // 2
    y = 4
    for letter in text:
        glyph = FONT[letter]
        # One-pixel dark red shadow, then a light cream/white face. Palette
        # indices are native to the existing hex OBJ palette.
        for gy, row in enumerate(glyph):
            for gx, pixel in enumerate(row):
                if pixel == "1":
                    if x + gx + 1 < width and y + gy + 1 < 16: write_pixel(raw, segments, x + gx + 1, y + gy + 1, 3)
                    write_pixel(raw, segments, x + gx, y + gy, 7)
        x += len(glyph[0]) + 1


def patch_member(pak_raw: bytes, entry: bytes) -> tuple[bytes, int, int]:
    pak = XrosPak.from_bytes(pak_raw)
    slot = pak.entries[ENTRY]
    packed = compress_xros_lz(entry)
    if len(packed) > slot.stored_size: raise ValueError(f"entry {ENTRY} exceeds fixed slot")
    archive = bytearray(pak_raw)
    archive[slot.offset:slot.offset + len(packed)] = packed
    archive[slot.offset + len(packed):slot.offset + slot.stored_size] = b"\0" * (slot.stored_size - len(packed))
    struct.pack_into("<IIII", archive, 0x10 + ENTRY * 0x10, slot.offset, len(entry), len(packed), slot.flags & ~0x80000000)
    if XrosPak.from_bytes(bytes(archive)).unpacked_data(ENTRY) != entry: raise AssertionError("PAK round-trip failed")
    return bytes(archive), slot.stored_size, len(packed)


def patch_archive(rom: bytearray, files, archive_name: str) -> tuple[int, int, int, int]:
    item = find_nitro_file(files, archive_name)
    pak_raw = bytes(rom[item.offset:item.offset + item.size])
    pak = XrosPak.from_bytes(pak_raw)
    entry = bytearray(pak.unpacked_data(ENTRY))
    for segments, text in LABELS: draw_label(entry, segments, text)
    rebuilt, before, after = patch_member(pak_raw, bytes(entry))
    rom[item.offset:item.offset + item.size] = rebuilt
    # This loader also retains an original fixed-address copy of SPR_NCGR.
    # Patch its same entry in-place so runtime and NitroFS agree.
    shadow_raw = bytes(rom[RUNTIME_GRAPHICS_SHADOW_OFFSET:RUNTIME_GRAPHICS_SHADOW_OFFSET + RUNTIME_GRAPHICS_SHADOW_SIZE])
    shadow, shadow_before, shadow_after = patch_member(shadow_raw, bytes(entry))
    rom[RUNTIME_GRAPHICS_SHADOW_OFFSET:RUNTIME_GRAPHICS_SHADOW_OFFSET + RUNTIME_GRAPHICS_SHADOW_SIZE] = shadow
    return before, after, shadow_before, shadow_after


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path); parser.add_argument("output", type=Path); parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    rom = bytearray(args.source.read_bytes())
    with args.source.open("rb") as handle: files = read_nitrofs(handle, read_header(handle))
    before, after, shadow_before, shadow_after = patch_archive(rom, files, "SPR_NCGR.PAK")
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_bytes(rom)
    report = {"source": str(args.source.resolve()), "output": str(args.output.resolve()), "entry": ENTRY, "labels": [text for _segments, text in LABELS], "method": "replace caption overlay pixels with compact English OBJ text", "nitrofs_stored_bytes_before": before, "nitrofs_stored_bytes_after": after, "shadow_stored_bytes_before": shadow_before, "shadow_stored_bytes_after": shadow_after, "sha256": hashlib.sha256(rom).hexdigest(), "verification": "Entry 198 round-trips through both NitroFS and fixed runtime graphics archive slots."}
    args.manifest.parent.mkdir(parents=True, exist_ok=True); args.manifest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__": main()
