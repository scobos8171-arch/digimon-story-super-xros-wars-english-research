#!/usr/bin/env python3
"""Render the live Xros hex-menu OBJ tiles as a labeled contact sheet.

This is an analysis-only utility.  It reads a DeSmuME VRAM capture and writes
PNG previews; it never writes a ROM, save, emulator memory, or source asset.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def read_palette(path: Path, palette_index: int) -> list[tuple[int, int, int, int]]:
    data = path.read_bytes()
    # Bottom-screen OBJ palettes begin at 0x600 in the complete DS palette RAM.
    offset = 0x600 + palette_index * 32
    colors: list[tuple[int, int, int, int]] = []
    for i in range(16):
        value = int.from_bytes(data[offset + i * 2 : offset + i * 2 + 2], "little")
        colors.append(((value & 31) * 8, ((value >> 5) & 31) * 8, ((value >> 10) & 31) * 8, 0 if i == 0 else 255))
    return colors


def render_tile(data: bytes, tile_index: int, colors: list[tuple[int, int, int, int]]) -> Image.Image:
    image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    pixels = image.load()
    chunk = data[tile_index * 32 : tile_index * 32 + 32]
    for y in range(8):
        for x_pair in range(4):
            byte = chunk[y * 4 + x_pair]
            pixels[x_pair * 2, y] = colors[byte & 0x0F]
            pixels[x_pair * 2 + 1, y] = colors[byte >> 4]
    return image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--obj", type=Path, required=True)
    parser.add_argument("--palette", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--first", type=int, default=8)
    parser.add_argument("--last", type=int, default=71)
    parser.add_argument("--palette-index", type=int, default=0)
    parser.add_argument("--scale", type=int, default=5)
    args = parser.parse_args()

    raw = args.obj.read_bytes()
    colors = read_palette(args.palette, args.palette_index)
    cols = 16
    count = args.last - args.first + 1
    rows = (count + cols - 1) // cols
    cell_w = 8 * args.scale + 18
    cell_h = 8 * args.scale + 18
    sheet = Image.new("RGBA", (cols * cell_w, rows * cell_h), (18, 29, 45, 255))
    draw = ImageDraw.Draw(sheet)
    for offset, tile_index in enumerate(range(args.first, args.last + 1)):
        x = (offset % cols) * cell_w
        y = (offset // cols) * cell_h
        tile = render_tile(raw, tile_index, colors).resize((8 * args.scale, 8 * args.scale), Image.Resampling.NEAREST)
        sheet.alpha_composite(tile, (x + 4, y + 12))
        draw.text((x + 2, y), str(tile_index), fill=(220, 235, 255, 255))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
