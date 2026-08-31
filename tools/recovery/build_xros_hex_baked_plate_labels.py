#!/usr/bin/env python3
"""Bake English into private red-plate tiles while keeping caption OAMs disabled.

v68 proved that the caption OAM objects must stay disabled.  Each command hex
otherwise uses the same 64x64 red plate (character 15).  This tool copies that
plate into seven unused NCGR areas, draws a compact English label on each, and
retargets only the existing *plate* OAM character numbers.  Caption OAMs are
not enabled or edited.
"""

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
PLATE_SOURCE = 15
# Disjoint 64x64 OBJ 2D mapping blocks: base..base+7 and base+32..base+39.
PLATE_COPIES = (128, 136, 144, 152, 192, 200, 208)
LABELS = ("STATUS", "SKILLS", "EQUIP", "FORMATION", "ITEMS", "MAP", "INFO")
FONT = {
    "A": ("010", "101", "111", "101", "101"), "E": ("111", "100", "110", "100", "111"),
    "F": ("111", "100", "110", "100", "100"), "I": ("111", "010", "010", "010", "111"),
    "K": ("101", "110", "100", "110", "101"), "L": ("100", "100", "100", "100", "111"),
    "M": ("10001", "11011", "10101", "10001", "10001"), "N": ("101", "111", "111", "111", "101"),
    "O": ("010", "101", "101", "101", "010"), "P": ("110", "101", "110", "100", "100"),
    "Q": ("010", "101", "101", "011", "001"), "R": ("110", "101", "110", "101", "101"),
    "S": ("011", "100", "010", "001", "110"), "T": ("11111", "00100", "00100", "00100", "00100"),
    "U": ("101", "101", "101", "101", "111"),
}


def compress_optimal(data: bytes) -> bytes:
    """Optimal 4KiB LZ encoding for this small fixed-slot NCER member.

    The stock encoder is intentionally greedy.  Here, flag-byte boundaries
    matter: a locally longer match can cost an extra flag byte later.  This
    dynamic program minimizes the complete encoded length over literals and
    3..18-byte matches, with the same format as ``compress_xros_lz``.
    """
    source = bytes(data)
    n = len(source)
    chains: dict[bytes, list[int]] = {}
    matches: list[dict[int, int]] = [{} for _ in range(n)]
    for pos in range(n):
        if pos + 3 <= n:
            key = source[pos:pos + 3]
            for candidate in reversed(chains.get(key, ())):
                if candidate < pos - 0x1000:
                    break
                maximum = min(18, n - pos)
                length = 3
                while length < maximum:
                    expected = source[candidate + (length % (pos - candidate))]
                    if source[pos + length] != expected:
                        break
                    length += 1
                for choice in range(3, length + 1):
                    matches[pos].setdefault(choice, candidate)
            chains.setdefault(key, []).append(pos)
    # dp[position][token_mod_8] -> byte count after position.
    dp = [[10**9] * 8 for _ in range(n + 1)]
    choice: list[list[tuple[int, int] | None]] = [[None] * 8 for _ in range(n)]
    for mod in range(8):
        dp[n][mod] = 0
    for pos in range(n - 1, -1, -1):
        for mod in range(8):
            flag_cost = 1 if mod == 0 else 0
            next_mod = (mod + 1) & 7
            best = flag_cost + 1 + dp[pos + 1][next_mod]
            selected: tuple[int, int] = (1, -1)
            for length, start in matches[pos].items():
                cost = flag_cost + 2 + dp[pos + length][next_mod]
                if cost < best:
                    best, selected = cost, (length, start)
            dp[pos][mod] = best
            choice[pos][mod] = selected
    tokens: list[tuple[int, int]] = []
    pos = mod = 0
    while pos < n:
        selected = choice[pos][mod]
        if selected is None:
            raise AssertionError("optimal encoder lost its reconstruction")
        length, start = selected
        tokens.append(selected)
        pos += length; mod = (mod + 1) & 7
    output = bytearray(b"\0\0\0\0")
    for group_start in range(0, len(tokens), 8):
        flags_at = len(output); flags = 0; output.append(0)
        for bit, (length, start) in enumerate(tokens[group_start:group_start + 8]):
            if length == 1:
                flags |= 1 << bit
                source_pos = sum(item[0] for item in tokens[:group_start + bit])
                output.append(source[source_pos])
            else:
                encoded = (start & 0xFFF) - 0x12
                output.append(encoded & 0xFF)
                output.append(((encoded >> 8) & 0xF) << 4 | (length - 3))
        output[flags_at] = flags
    struct.pack_into("<I", output, 0, len(output))
    return bytes(output)


def write_pixel(raw: bytearray, base: int, x: int, y: int, value: int) -> None:
    tile = base + (y // 8) * 32 + (x // 8)
    off = 0x30 + tile * TILE_BYTES + (y % 8) * 4 + (x % 8) // 2
    old = raw[off]
    raw[off] = (old & 0xF0) | value if x % 2 == 0 else (old & 0x0F) | (value << 4)


def copy_plate(raw: bytearray, destination: int) -> None:
    for row in range(8):
        for col in range(8):
            source_tile = PLATE_SOURCE + row * 32 + col
            target_tile = destination + row * 32 + col
            src = 0x30 + source_tile * TILE_BYTES
            dst = 0x30 + target_tile * TILE_BYTES
            raw[dst:dst + TILE_BYTES] = raw[src:src + TILE_BYTES]


def draw_label(raw: bytearray, base: int, text: str) -> None:
    width = sum(len(FONT[c][0]) + 1 for c in text) - 1
    x = (64 - width) // 2
    y = 30
    for char in text:
        for gy, row in enumerate(FONT[char]):
            for gx, pixel in enumerate(row):
                if pixel == "1":
                    # native dark-red depth and cream face in the existing OBJ palette
                    write_pixel(raw, base, x + gx + 1, y + gy + 1, 3)
                    write_pixel(raw, base, x + gx, y + gy, 7)
        x += len(FONT[char][0]) + 1


def replace_entry(archive: bytes, entry: bytes, *, optimal: bool = False, keep_slot_size: bool = False) -> bytes:
    pak = XrosPak.from_bytes(archive)
    slot = pak.entries[ENTRY]
    packed = compress_optimal(entry) if optimal else compress_xros_lz(entry)
    # This entry has intentional alignment slack before entry 199.  Use only
    # that adjacent zero-filled gap; do not move any archive member.
    next_offset = pak.entries[ENTRY + 1].offset
    capacity = next_offset - slot.offset
    if len(packed) > capacity:
        raise ValueError(f"Entry {ENTRY} needs {len(packed)} bytes; safe gap holds {capacity}")
    result = bytearray(archive)
    result[slot.offset:slot.offset + len(packed)] = packed
    stored_size = slot.stored_size if keep_slot_size else len(packed)
    if stored_size < len(packed):
        raise ValueError("Requested fixed slot is smaller than compressed data")
    result[slot.offset + len(packed):next_offset] = b"\0" * (next_offset - (slot.offset + len(packed)))
    # Keep v68's exact NCER member boundary. The decoder stops after the
    # declared uncompressed size, so zero padding after a complete LZ stream
    # is harmless while preserving the runtime's expected layout.
    struct.pack_into("<IIII", result, 0x10 + ENTRY * 0x10, slot.offset, len(entry), stored_size, slot.flags & ~0x80000000)
    if XrosPak.from_bytes(bytes(result)).unpacked_data(ENTRY) != entry:
        raise AssertionError("PAK round-trip failed")
    return bytes(result)


def retarget_plates(ncer: bytes) -> bytes:
    _section, cells, extended, _unknown, _mapping, _part = struct.unpack_from("<IHHIII", ncer, 0x14)
    record_size = 0x10 if extended == 1 else 8
    oam_start = 0x30 + record_size * cells
    result = bytearray(ncer)
    for cell, new_base in zip(range(1, 8), PLATE_COPIES):
        record = 0x30 + cell * record_size
        oam_count, _readonly, relative = struct.unpack_from("<HHI", ncer, record)
        # The final OAM is the existing 64x64 red plate. Leave every other OAM,
        # particularly hidden captions, exactly untouched.
        offset = oam_start + relative + (oam_count - 1) * 6 + 4
        old = struct.unpack_from("<H", ncer, offset)[0]
        if (old & 0x3FF) != PLATE_SOURCE:
            raise ValueError(f"Cell {cell} final OAM is not the expected shared plate")
        struct.pack_into("<H", result, offset, (old & ~0x3FF) | new_base)
    # v68 permanently disables the caption OAMs via attr0 object mode.  In
    # disabled mode the DS ignores attr1/attr2 entirely.  Zero those dead
    # fields so this NCER still fits v68's fixed 530-byte compressed slot.
    caption_oams = {1: (1, 2), 2: (1,), 3: (1, 2), 4: (1, 2), 5: (1, 2), 6: (1, 2), 7: (1, 2)}
    for cell, indexes in caption_oams.items():
        record = 0x30 + cell * record_size
        _count, _readonly, relative = struct.unpack_from("<HHI", ncer, record)
        for index in indexes:
            offset = oam_start + relative + index * 6
            attr0 = struct.unpack_from("<H", result, offset)[0]
            if (attr0 & 0x0300) != 0x0200:
                raise ValueError(f"Cell {cell} caption OAM {index} is not disabled in the v68 source")
            struct.pack_into("<HH", result, offset + 2, 0, 0)
    return bytes(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path); parser.add_argument("output", type=Path); parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    rom = bytearray(args.source.read_bytes())
    with args.source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        ncgr_item = find_nitro_file(files, "SPR_NCGR.PAK")
        ncer_item = find_nitro_file(files, "SPR_NCER.PAK")
        ncgr_archive = read_nitro_file(handle, ncgr_item)
        ncer_archive = read_nitro_file(handle, ncer_item)
    ncgr_pak = XrosPak.from_bytes(ncgr_archive)
    ncgr = bytearray(ncgr_pak.unpacked_data(ENTRY))
    for base, label in zip(PLATE_COPIES, LABELS):
        copy_plate(ncgr, base); draw_label(ncgr, base, label)
    ncer_pak = XrosPak.from_bytes(ncer_archive)
    ncer = retarget_plates(ncer_pak.unpacked_data(ENTRY))
    rom[ncgr_item.offset:ncgr_item.offset + ncgr_item.size] = replace_entry(ncgr_archive, bytes(ncgr))
    rom[ncer_item.offset:ncer_item.offset + ncer_item.size] = replace_entry(ncer_archive, ncer, optimal=True, keep_slot_size=True)
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_bytes(rom)
    report = {"source": str(args.source.resolve()), "output": str(args.output.resolve()), "labels": LABELS,
              "method": "private plate copies; hidden caption OAMs unchanged", "sha256": hashlib.sha256(rom).hexdigest()}
    args.manifest.parent.mkdir(parents=True, exist_ok=True); args.manifest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
