#!/usr/bin/env python3
"""Build a reversible v58-derived Xros hex menu with caption glyphs removed.

The live capture shows the seven Japanese captions as 13 small Engine-B OBJ
overlays.  Their bright glyph/shadow palette indices are 5, 6 and 7; the
green icons use 12--15.  This patch clears only indices 5--7 in tiles reached
by those overlays, then mirrors entry 198 into the fixed runtime archive.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))
sys.path.insert(0, str(ROOT / "tools" / "recovery"))

from analyze_xros_hex_capture import decode_oam_sub  # noqa: E402
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.nitrofs_patch import replace_nitrofs_files  # noqa: E402
from rom_research.xros_pak import (  # noqa: E402
    PAK_ENTRY_SIZE, PAK_HEADER_SIZE, UNCOMPRESSED_FLAG, XrosPak, build_xros_pak,
    compress_xros_lz, find_nitro_file, read_nitro_file,
)

ARCHIVE = "SPR_NCGR.PAK"
ENTRY = 198
TILE_BYTES = 32
CAPTION_FRAGMENTS = (12, 13, 16, 19, 20, 23, 24, 27, 28, 31, 32, 35, 36)
GLYPH_PALETTE_INDICES = {5, 6, 7}
PHYSICAL_ARCHIVE_OFFSET = 0x0136C600
PHYSICAL_ARCHIVE_SIZE = 14872324


def digest(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def tile_indices(sprite: dict[str, int]) -> list[int]:
    return [sprite["tile"] + row * 32 + column for row in range(sprite["h"] // 8) for column in range(sprite["w"] // 8)]


def read_archive(rom: Path) -> tuple[bytes, object]:
    with rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        item = find_nitro_file(files, ARCHIVE)
        return read_nitro_file(handle, item), item


def clear_indices(raw: bytearray, tile: int) -> int:
    start = 0x30 + tile * TILE_BYTES
    changed = 0
    for offset in range(start, start + TILE_BYTES):
        value = raw[offset]
        left, right = value & 0x0F, value >> 4
        new_left = 0 if left in GLYPH_PALETTE_INDICES else left
        new_right = 0 if right in GLYPH_PALETTE_INDICES else right
        new_value = new_left | (new_right << 4)
        if new_value != value:
            raw[offset] = new_value
            changed += (left != new_left) + (right != new_right)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Known-working v58 ROM")
    parser.add_argument("capture", type=Path, help="Provenance capture directory")
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    source_archive, _nitro_item = read_archive(args.source)
    pak = XrosPak.from_bytes(source_archive)
    entries = [pak.unpacked_data(index) for index in range(len(pak.entries))]
    original = entries[ENTRY]
    source_tiles = [original[offset:offset + TILE_BYTES] for offset in range(0x30, len(original), TILE_BYTES)]
    by_hash: dict[str, list[int]] = defaultdict(list)
    for index, tile in enumerate(source_tiles):
        by_hash[digest(tile)].append(index)

    obj = (args.capture / "obj_sub_06600000.bin").read_bytes()
    sprites = {item["index"]: item for item in decode_oam_sub(args.capture / "oam_sub.bin")}
    replacement = bytearray(original)
    rows: list[dict[str, object]] = []
    changed_tiles: set[int] = set()
    changed_pixels = 0
    for oam in CAPTION_FRAGMENTS:
        sprite = sprites[oam]
        for runtime_tile in tile_indices(sprite):
            data = obj[runtime_tile * TILE_BYTES:(runtime_tile + 1) * TILE_BYTES]
            matches = by_hash.get(digest(data), [])
            # Equal source duplicates have identical pixels.  Updating each
            # keeps both the normal and fixed-address archive copies coherent.
            tile_changes = 0
            for source_tile in matches:
                tile_changes += clear_indices(replacement, source_tile)
                if tile_changes:
                    changed_tiles.add(source_tile)
            changed_pixels += tile_changes
            rows.append({"oam": oam, "runtime_tile": runtime_tile, "source_matches": ",".join(map(str, matches)), "cleared_palette_pixels": tile_changes})

    entries[ENTRY] = bytes(replacement)
    staged_archive = build_xros_pak(entries)
    staged = replace_nitrofs_files(args.source.read_bytes(), {ARCHIVE: staged_archive})
    staged_pak = XrosPak.from_bytes(staged_archive)

    # Xros sometimes reads its original fixed physical archive.  Mirror the
    # modified entry into that archive, without changing archive offsets.
    physical_raw = bytes(staged[PHYSICAL_ARCHIVE_OFFSET:PHYSICAL_ARCHIVE_OFFSET + PHYSICAL_ARCHIVE_SIZE])
    physical = XrosPak.from_bytes(physical_raw)
    slot = physical.entries[ENTRY]
    packed = compress_xros_lz(entries[ENTRY])
    if len(packed) > slot.stored_size:
        raise ValueError(f"Entry {ENTRY} needs {len(packed)} bytes; fixed slot holds {slot.stored_size}")
    physical_out = bytearray(physical_raw)
    physical_out[slot.offset:slot.offset + len(packed)] = packed
    physical_out[slot.offset + len(packed):slot.offset + slot.stored_size] = b"\0" * (slot.stored_size - len(packed))
    struct.pack_into("<IIII", physical_out, PAK_HEADER_SIZE + ENTRY * PAK_ENTRY_SIZE, slot.offset, len(entries[ENTRY]), len(packed), slot.flags & ~UNCOMPRESSED_FLAG)
    staged[PHYSICAL_ARCHIVE_OFFSET:PHYSICAL_ARCHIVE_OFFSET + PHYSICAL_ARCHIVE_SIZE] = physical_out

    nitro_final, _ = read_archive_from_data(staged)
    if XrosPak.from_bytes(nitro_final).unpacked_data(ENTRY) != entries[ENTRY]:
        raise AssertionError("NitroFS entry verification failed")
    if XrosPak.from_bytes(physical_out).unpacked_data(ENTRY) != entries[ENTRY]:
        raise AssertionError("Fixed runtime entry verification failed")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(staged)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    with (args.manifest.parent / "caption_overlay_tile_map.tsv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader(); writer.writerows(rows)
    report = {
        "source": str(args.source.resolve()), "output": str(args.output.resolve()),
        "method": "icon-only: clear palette indices 5,6,7 from live-caption overlay tiles",
        "caption_oam": list(CAPTION_FRAGMENTS), "graphics_entry": ENTRY,
        "changed_source_tiles": sorted(changed_tiles), "changed_source_tile_count": len(changed_tiles),
        "cleared_palette_pixels": changed_pixels, "runtime_archive_offset": f"0x{PHYSICAL_ARCHIVE_OFFSET:08X}",
        "runtime_slot_stored_bytes": slot.stored_size, "patched_stored_bytes": len(packed),
        "sha256": hashlib.sha256(staged).hexdigest(),
        "verification": "Entry 198 decompresses identically from NitroFS and fixed runtime archive.",
    }
    args.manifest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def read_archive_from_data(data: bytes | bytearray) -> tuple[bytes, object]:
    class Reader:
        def __init__(self, blob: bytes | bytearray): self.blob, self.pos = blob, 0
        def seek(self, pos: int): self.pos = pos; return pos
        def read(self, size: int = -1):
            if size < 0: size = len(self.blob) - self.pos
            out = bytes(self.blob[self.pos:self.pos + size]); self.pos += len(out); return out
        def __enter__(self): return self
        def __exit__(self, *_): return None
    with Reader(data) as handle:
        files = read_nitrofs(handle, read_header(handle))
        item = find_nitro_file(files, ARCHIVE)
        return read_nitro_file(handle, item), item


if __name__ == "__main__":
    raise SystemExit(main())
