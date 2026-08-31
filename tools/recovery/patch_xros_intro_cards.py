#!/usr/bin/env python3
"""Install native English lower-screen intro cards into Xros background entries."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image


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
from nitro import parse_ncgr, parse_nclr, parse_nscr, render_screen  # noqa: E402


GRAPHICS_PATH = "data/BG_NCGR.PAK"
PALETTE_PATH = "data/BG_NCLR.PAK"
SCREEN_PATH = "data/BG_NSCR.PAK"
ENTRIES = tuple(range(33, 42))

# These lower-screen story cards are displayed with the game's already-loaded
# shared title palette.  BG_NCLR entries with the same archive indices are
# unrelated assets; overwriting them corrupts the screen behind the cards.
# Runtime calibration shows bank 1 has the complete live card palette:
# black, neutral grays, saturated red, and a near-white fill.
TEXT_PALETTE_BANK = 1
QA_SHARED_PALETTE_ENTRY = 175
TRANSPARENT = 0
WHITE = 15
MID_GRAY = 11
BLACK = 1
RED = 10


def ds_color(color: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(max(0, min(31, round(component * 31 / 255))) for component in color)


def expand_color(color: tuple[int, int, int]) -> tuple[int, int, int, int]:
    return tuple(component * 255 // 31 for component in color) + (255,)


def native_index(red: int, green: int, blue: int, alpha: int) -> int:
    """Map the antialiased source art onto the intro palette's native ink."""
    if alpha < 128:
        return TRANSPARENT
    # Highlight words in the source are red.  Keep every red shade in the
    # original card's single vivid red rather than leaking blue/purple edges.
    brightness = (red + green + blue) // 3
    if red > green * 1.35 and red > blue * 1.35 and red > 96:
        # The source's red lettering has a dark-red outline.  That outline
        # must remain black in the native palette, otherwise it becomes a
        # solid red blob on hardware.
        # Source red ink has three native shades: a near-black outer edge,
        # a dark-red inner edge (around R=143), and a bright-red fill
        # (around R=231).  The live card palette only needs the latter red;
        # map both darker layers to black for a crisp readable outline.
        return RED if red >= 180 else BLACK
    if brightness >= 210:
        return WHITE
    if brightness >= 70:
        return MID_GRAY
    return BLACK


def encode_screen(graphics: bytes, screen: bytes, image: Image.Image) -> tuple[bytes, bytes]:
    ncgr = parse_ncgr(graphics)
    nscr = parse_nscr(screen)
    if image.size != (nscr.width, nscr.height):
        raise ValueError(f"art is {image.size}; expected {nscr.width}x{nscr.height}")
    if ncgr.bpp != 4:
        raise ValueError("intro background is expected to be 4bpp")
    tile_capacity = len(ncgr.tiles)
    patterns: list[bytes] = []
    indexes: dict[bytes, int] = {}
    map_entries: list[int] = []
    pixels = image.load()
    for tile_y in range(nscr.height // 8):
        for tile_x in range(nscr.width // 8):
            tile = bytearray(64)
            for y in range(8):
                for x in range(8):
                    red, green, blue, alpha = pixels[tile_x * 8 + x, tile_y * 8 + y]
                    if alpha < 128:
                        continue
                    tile[y * 8 + x] = native_index(red, green, blue, alpha)
            pattern = bytes(tile)
            tile_index = indexes.get(pattern)
            if tile_index is None:
                tile_index = len(patterns)
                indexes[pattern] = tile_index
                patterns.append(pattern)
            # All English ink uses the calibrated live bank.  It is the only
            # one that contains both the white fill and the native red accent.
            map_entries.append(tile_index | TEXT_PALETTE_BANK << 12)
    if len(patterns) > tile_capacity:
        raise ValueError(f"card needs {len(patterns)} unique tiles; entry only holds {tile_capacity}")
    out_graphics = bytearray(graphics)
    for tile_index in range(tile_capacity):
        pixels64 = patterns[tile_index] if tile_index < len(patterns) else bytes(64)
        packed = bytearray(32)
        for index, value in enumerate(pixels64):
            packed[index // 2] |= value << (4 * (index & 1))
        offset = 0x30 + tile_index * 32
        out_graphics[offset:offset + 32] = packed
    out_screen = bytearray(screen)
    for index, tile_index in enumerate(map_entries):
        out_screen[0x24 + index * 2:0x26 + index * 2] = tile_index.to_bytes(2, "little")
    return bytes(out_graphics), bytes(out_screen)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("cards_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("qa_dir", type=Path)
    args = parser.parse_args()
    source_data = args.source.read_bytes()
    with args.source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        gfx_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, GRAPHICS_PATH)))
        pal_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        scr_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, SCREEN_PATH)))
    graphics = [gfx_pak.unpacked_data(i) for i in range(len(gfx_pak.entries))]
    screens = [scr_pak.unpacked_data(i) for i in range(len(scr_pak.entries))]
    args.qa_dir.mkdir(parents=True, exist_ok=True)
    qa: dict[int, Image.Image] = {}
    tile_counts: dict[int, int] = {}
    for entry in ENTRIES:
        art_path = args.cards_dir / f"entry_{entry:04d}_intro_EN_256x192.png"
        art = Image.open(art_path).convert("RGBA")
        graphics[entry], screens[entry] = encode_screen(graphics[entry], screens[entry], art)
        decoded = render_screen(
            parse_ncgr(graphics[entry]),
            parse_nclr(pal_pak.unpacked_data(QA_SHARED_PALETTE_ENTRY)),
            parse_nscr(screens[entry]),
        )
        qa[entry] = decoded
        tile_counts[entry] = len({
            tuple(decoded.getpixel((x + local_x, y + local_y)) for local_y in range(8) for local_x in range(8))
            for x in range(0, 256, 8)
            for y in range(0, 192, 8)
        })
    patched = replace_nitrofs_files(source_data, {
        GRAPHICS_PATH: build_xros_pak(graphics),
        SCREEN_PATH: build_xros_pak(screens),
    })
    if arm9_slice(source_data) != arm9_slice(patched):
        raise AssertionError("ARM9 changed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    for entry, image in qa.items():
        image.save(args.qa_dir / f"entry_{entry:04d}_decoded.png")
        image.resize((1024, 768), Image.Resampling.NEAREST).save(args.qa_dir / f"entry_{entry:04d}_decoded_4x.png")
    (args.qa_dir / "manifest.json").write_text(json.dumps({
        "source_rom": str(args.source.resolve()),
        "output_rom": str(args.output.resolve()),
        "source_sha256": hashlib.sha256(source_data).hexdigest(),
        "output_sha256": hashlib.sha256(patched).hexdigest(),
        "entries": list(ENTRIES),
        "tile_patterns": tile_counts,
        "changed_archives": [GRAPHICS_PATH, SCREEN_PATH],
        "shared_intro_palette_preserved": True,
        "arm9_unchanged": True,
    }, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
