#!/usr/bin/env python3
"""Map live Xros hex-menu OBJ tiles back to exact NCGR source tile indices.

This is deliberately read-only.  It turns a DeSmuME provenance capture into
an auditable label-to-source map before any ROM is modified.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))
sys.path.insert(0, str(ROOT / "tools" / "recovery"))

from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, read_nitro_file  # noqa: E402
from analyze_xros_hex_capture import decode_oam_sub, render_obj_sprite  # noqa: E402


TILE_BYTES = 32


def digest(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def read_ncgr_entry(rom: Path, archive: str, entry_id: int) -> bytes:
    with rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        nitro = next(item for item in files if item.path.upper().endswith(archive.upper()))
        pak = XrosPak.from_bytes(read_nitro_file(handle, nitro))
        entry = next(item for item in pak.entries if item.index == entry_id)
        return pak.unpacked_data(entry)


def sprite_tile_indices(sprite: dict[str, int]) -> list[int]:
    """Return 4bpp tile indices for DS 2D OBJ mapping, in display order."""
    result = []
    for row in range(sprite["h"] // 8):
        for col in range(sprite["w"] // 8):
            result.append(sprite["tile"] + row * 32 + col)
    return result


def is_label_fragment(sprite: dict[str, int]) -> bool:
    # Seven menu captions are composed from one 32x16 and, when needed, one
    # 16x16 OBJ.  Their tops sit at y=65/67/128/129/131 in the live capture.
    return sprite["h"] == 16 and sprite["w"] in (16, 32) and 62 <= sprite["y"] <= 147


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--entry", type=int, default=198)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    ncgr = read_ncgr_entry(args.rom, "SPR_NCGR.PAK", args.entry)
    if ncgr[:4] != b"RGCN" or len(ncgr) < 0x30:
        raise ValueError("Selected entry is not the expected NCGR layout")
    source_tiles = [ncgr[i : i + TILE_BYTES] for i in range(0x30, len(ncgr), TILE_BYTES)]
    source_by_digest: dict[str, list[int]] = defaultdict(list)
    for index, tile in enumerate(source_tiles):
        if len(tile) == TILE_BYTES:
            source_by_digest[digest(tile)].append(index)

    obj = (args.capture / "obj_sub_06600000.bin").read_bytes()
    palette = (args.capture / "palette_ram.bin").read_bytes()
    sprites = decode_oam_sub(args.capture / "oam_sub.bin")
    fragments = [sprite for sprite in sprites if is_label_fragment(sprite)]

    rows: list[dict[str, object]] = []
    preview = args.out / "runtime_fragments"
    preview.mkdir(exist_ok=True)
    for sprite in fragments:
        image = render_obj_sprite(obj, palette, sprite, palette_base=0x600)
        image.save(preview / f"oam{sprite['index']:03d}_x{sprite['x']}_y{sprite['y']}.png")
        for position, runtime_index in enumerate(sprite_tile_indices(sprite)):
            start = runtime_index * TILE_BYTES
            tile = obj[start : start + TILE_BYTES]
            matches = source_by_digest.get(digest(tile), []) if len(tile) == TILE_BYTES else []
            rows.append(
                {
                    "oam": sprite["index"],
                    "x": sprite["x"],
                    "y": sprite["y"],
                    "width": sprite["w"],
                    "height": sprite["h"],
                    "palette": sprite["pal"],
                    "fragment_tile_position": position,
                    "runtime_tile": runtime_index,
                    "source_entry": args.entry,
                    "source_tile_matches": ",".join(map(str, matches)),
                    "unique_source_tile": matches[0] if len(matches) == 1 else "",
                    "match_count": len(matches),
                    "sha1": digest(tile) if len(tile) == TILE_BYTES else "",
                }
            )

    table = args.out / "hex_runtime_to_entry198_tiles.tsv"
    with table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["oam"], delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    matched = sum(1 for row in rows if int(row["match_count"]) > 0)
    unique = sum(1 for row in rows if int(row["match_count"]) == 1)
    report = args.out / "README.txt"
    report.write_text(
        "Xros hex-menu runtime-to-ROM tile map\n"
        f"ROM: {args.rom}\nCapture: {args.capture}\n"
        f"SPR_NCGR.PAK entry: {args.entry}\n"
        f"Label-fragment OAM sprites: {len(fragments)}\n"
        f"Tile positions: {len(rows)}; matched: {matched}; unique: {unique}\n\n"
        "No ROM was modified. Runtime fragment PNGs and the TSV are evidence for the safe patcher.\n",
        encoding="utf-8",
    )
    print(report.read_text(encoding="utf-8"))
    print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
