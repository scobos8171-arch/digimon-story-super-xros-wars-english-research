#!/usr/bin/env python3
"""Build a one-card runtime palette chart for the Xros intro scene."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))
sys.path.insert(0, str(ROOT / "tools" / "recovery"))
sys.path.insert(0, str(ROOT / "tools" / "rom_importer"))

from build_xros_custom_ui_rom import (  # noqa: E402
    XrosPak,
    arm9_slice,
    build_xros_pak,
    find_nitro_file,
    read_header,
    read_nitro_file,
    read_nitrofs,
    replace_nitrofs_files,
)
from nitro import parse_ncgr, parse_nscr  # noqa: E402


GRAPHICS_PATH = "data/BG_NCGR.PAK"
SCREEN_PATH = "data/BG_NSCR.PAK"
ENTRY = 34


def pack_tile(value: int) -> bytes:
    """A solid 8x8 4bpp tile using a single palette value."""
    return bytes([value | value << 4]) * 32


def make_chart(graphics: bytes, screen: bytes) -> tuple[bytes, bytes]:
    ncgr = parse_ncgr(graphics)
    nscr = parse_nscr(screen)
    if ncgr.bpp != 4 or (nscr.width, nscr.height) != (256, 192):
        raise ValueError("unexpected intro-card format")

    # Tile 0 is transparent.  Values 1–15 fill two 15-cell rows: the top row
    # uses live bank 0 and the lower row uses live bank 1.  Each colour cell is
    # two tiles wide by two tiles high so it remains legible in a screenshot.
    out_gfx = bytearray(graphics)
    for value in range(16):
        offset = 0x30 + value * 32
        out_gfx[offset:offset + 32] = pack_tile(value)
    entries = [0] * (32 * 24)
    for bank, tile_y in ((0, 7), (1, 14)):
        for value in range(1, 16):
            tile_x = 1 + (value - 1) * 2
            for dy in range(2):
                for dx in range(2):
                    entries[(tile_y + dy) * 32 + tile_x + dx] = value | bank << 12
    out_scr = bytearray(screen)
    for index, entry in enumerate(entries):
        out_scr[0x24 + index * 2:0x26 + index * 2] = entry.to_bytes(2, "little")
    return bytes(out_gfx), bytes(out_scr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = args.source.read_bytes()
    with args.source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        gp = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, GRAPHICS_PATH)))
        sp = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, SCREEN_PATH)))
    graphics = [gp.unpacked_data(i) for i in range(len(gp.entries))]
    screens = [sp.unpacked_data(i) for i in range(len(sp.entries))]
    graphics[ENTRY], screens[ENTRY] = make_chart(graphics[ENTRY], screens[ENTRY])
    patched = replace_nitrofs_files(source, {
        GRAPHICS_PATH: build_xros_pak(graphics),
        SCREEN_PATH: build_xros_pak(screens),
    })
    if arm9_slice(source) != arm9_slice(patched):
        raise AssertionError("ARM9 changed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
