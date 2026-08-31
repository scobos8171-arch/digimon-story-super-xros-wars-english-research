#!/usr/bin/env python3
"""Render DS text-background layers directly from an extracted DeSmuME state."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from PIL import Image


def color(raw: bytes, index: int) -> tuple[int, int, int, int]:
    value = struct.unpack_from("<H", raw, index * 2)[0]
    return (
        (value & 31) * 255 // 31,
        ((value >> 5) & 31) * 255 // 31,
        ((value >> 10) & 31) * 255 // 31,
        255,
    )


def render(vram: bytes, palette: bytes, cnt: int, hofs: int, vofs: int) -> Image.Image:
    bpp8 = bool(cnt & 0x80)
    char_base = ((cnt >> 2) & 3) * 0x4000
    screen_base = ((cnt >> 8) & 31) * 0x800
    size = (cnt >> 14) & 3
    width = 512 if size in (1, 3) else 256
    height = 512 if size in (2, 3) else 256
    image = Image.new("RGBA", (256, 192))
    pixels = image.load()
    for sy in range(192):
        wy = (sy + vofs) % height
        for sx in range(256):
            wx = (sx + hofs) % width
            block_x, block_y = wx // 256, wy // 256
            blocks_per_row = width // 256
            block = block_y * blocks_per_row + block_x
            map_offset = screen_base + block * 0x800 + ((wy & 255) // 8 * 32 + (wx & 255) // 8) * 2
            raw = struct.unpack_from("<H", vram, map_offset)[0]
            tile, flip_x, flip_y, bank = raw & 0x3FF, bool(raw & 0x400), bool(raw & 0x800), raw >> 12
            px, py = wx & 7, wy & 7
            if flip_x:
                px = 7 - px
            if flip_y:
                py = 7 - py
            if bpp8:
                index = vram[char_base + tile * 64 + py * 8 + px]
            else:
                value = vram[char_base + tile * 32 + py * 4 + px // 2]
                index = (value >> (4 * (px & 1))) & 15
                index += bank * 16
            rgba = color(palette, index)
            if index & (255 if bpp8 else 15) == 0:
                rgba = (*rgba[:3], 0)
            pixels[sx, sy] = rgba
    return image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("state", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    regs = (args.state / "9reg.bin").read_bytes()
    lcd = (args.state / "lcdm.bin").read_bytes()
    pal = (args.state / "vmem.bin").read_bytes()
    args.output.mkdir(parents=True, exist_ok=True)
    engines = {
        "main": (lcd[0x00000:0x20000], pal[0x000:0x200], 0),
        "sub": (lcd[0x40000:0x60000], pal[0x400:0x600], 0x1000),
    }
    for name, (vram, palette, base) in engines.items():
        for bg in range(4):
            cnt = struct.unpack_from("<H", regs, base + 8 + bg * 2)[0]
            hofs = struct.unpack_from("<H", regs, base + 0x10 + bg * 4)[0] & 0x1FF
            vofs = struct.unpack_from("<H", regs, base + 0x12 + bg * 4)[0] & 0x1FF
            try:
                image = render(vram, palette, cnt, hofs, vofs)
                image.save(args.output / f"{name}_bg{bg}.png")
            except (IndexError, struct.error) as exc:
                print(f"{name} BG{bg}: {exc}")


if __name__ == "__main__":
    main()
