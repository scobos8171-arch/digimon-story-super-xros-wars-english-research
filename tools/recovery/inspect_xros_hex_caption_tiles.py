#!/usr/bin/env python3
"""Render the exact entry-198 tiles used by the live hex-menu captions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))

from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, read_nitro_file  # noqa: E402
from rom_research.xros_sprite import parse_ncgr, parse_nclr  # noqa: E402

TILE_GROUPS = (
    (12, 13, 14, 15, 44, 45, 46, 47),
    (35, 36, 37, 38, 67, 68, 69, 70),
    (41, 42, 43, 44, 73, 74, 75, 76),
    (48, 49, 50, 51, 80, 81, 82, 83),
    (55, 56, 57, 58, 87, 88, 89, 90),
    (62, 63, 64, 65, 94, 95, 96, 97),
    (69, 70, 71, 72, 101, 102, 103, 104),
)


def archive_entry(rom: Path, name: str, index: int) -> bytes:
    with rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        item = next(file for file in files if file.path.upper().endswith(name))
        return XrosPak.from_bytes(read_nitro_file(handle, item)).unpacked_data(index)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--runtime-palette", type=Path, help="palette_ram.bin from the live capture")
    args = parser.parse_args()
    graphics = parse_ncgr(archive_entry(args.rom, "SPR_NCGR.PAK", 198))
    palette = parse_nclr(archive_entry(args.rom, "SPR_NCLR.PAK", 198))
    if args.runtime_palette:
        raw = args.runtime_palette.read_bytes()
        # Engine-B OBJ palette 0 starts at 0x600 in DeSmuME palette RAM.
        palette = []
        for index in range(16):
            value = int.from_bytes(raw[0x600 + index * 2 : 0x602 + index * 2], "little")
            palette.append(((value & 31) * 8, ((value >> 5) & 31) * 8, ((value >> 10) & 31) * 8, 0 if index == 0 else 255))
    scale = 5
    sheet = Image.new("RGBA", (4 * 8 * scale + 150, len(TILE_GROUPS) * 16 * scale), (20, 25, 35, 255))
    draw = ImageDraw.Draw(sheet)
    for group_index, indices in enumerate(TILE_GROUPS):
        for position, tile_index in enumerate(indices):
            column = position % 4
            row = position // 4
            tile = graphics.tiles[tile_index]
            image = Image.new("RGBA", (8, 8))
            image.putdata([palette[value] for value in tile])
            sheet.alpha_composite(image.resize((8 * scale, 8 * scale), Image.Resampling.NEAREST), (column * 8 * scale, (group_index * 16 + row * 8) * scale))
            draw.text((4 * 8 * scale + 5, (group_index * 16 + row * 8) * scale), str(indices[row * 4:(row + 1) * 4]), fill="white")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out)


if __name__ == "__main__":
    main()
