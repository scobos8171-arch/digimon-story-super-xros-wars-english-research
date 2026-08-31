#!/usr/bin/env python3
"""Map the seven actual 32x32 Xros hex-caption OAM objects to entry-198 tiles."""

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

from analyze_xros_hex_capture import decode_oam_sub, render_obj_sprite  # noqa: E402
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, read_nitro_file  # noqa: E402

CAPTION_OAM = (11, 15, 18, 22, 26, 30, 34)
TILE_BYTES = 32


def sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def source_tiles(rom: Path) -> list[bytes]:
    with rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        file = next(item for item in files if item.path.upper().endswith("SPR_NCGR.PAK"))
        entry = XrosPak.from_bytes(read_nitro_file(handle, file)).unpacked_data(198)
    return [entry[offset : offset + TILE_BYTES] for offset in range(0x30, len(entry), TILE_BYTES)]


def indices(sprite: dict[str, int]) -> list[int]:
    return [sprite["tile"] + row * 32 + column for row in range(sprite["h"] // 8) for column in range(sprite["w"] // 8)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("capture", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    source = source_tiles(args.rom)
    lookup: dict[str, list[int]] = defaultdict(list)
    for tile_index, tile in enumerate(source):
        lookup[sha1(tile)].append(tile_index)
    obj = (args.capture / "obj_sub_06600000.bin").read_bytes()
    palette = (args.capture / "palette_ram.bin").read_bytes()
    sprites = {item["index"]: item for item in decode_oam_sub(args.capture / "oam_sub.bin")}
    rows: list[dict[str, object]] = []
    for oam in CAPTION_OAM:
        sprite = sprites[oam]
        render_obj_sprite(obj, palette, sprite, palette_base=0x600).resize((128, 128)).save(args.out / f"oam{oam:03d}.png")
        for position, runtime_index in enumerate(indices(sprite)):
            tile = obj[runtime_index * TILE_BYTES : (runtime_index + 1) * TILE_BYTES]
            matches = lookup.get(sha1(tile), [])
            rows.append({"oam": oam, "position": position, "runtime_tile": runtime_index, "source_matches": ",".join(map(str, matches)), "unique_source": matches[0] if len(matches) == 1 else "", "match_count": len(matches)})
    with (args.out / "caption_oam_tiles.tsv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader(); writer.writerows(rows)


if __name__ == "__main__":
    main()
