#!/usr/bin/env python3
"""Safely replace Xros Blue's baked Japanese battle-results header.

The screen title is not a message-table string: it is part of BG_NCGR.PAK
entry 307, loaded into main-engine BG2.  This tool proves that mapping against
a captured battle-results state, changes the title pixels only, and preserves
every map/palette/layout/value tile on the screen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "work" / "DigimonNDSRomEditor-master"), str(ROOT / "tools" / "recovery")]

from build_xros_custom_ui_rom import arm9_slice, make_compact_3x5_mask  # noqa: E402
from render_xros_state_bg_layers import render  # noqa: E402
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.nitrofs_patch import replace_nitrofs_files  # noqa: E402
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file  # noqa: E402


GRAPHICS_PATH = "BG_NCGR.PAK"
GRAPHICS_ENTRY = 307
CHAR_BASE = 0x8000
SCREEN_BASE = 0x1000
TITLE_CELLS = (6, 1, 21, 4)  # x0, y0, exclusive x1/y1
TEXT_BOX = (48, 12, 168, 28)
TITLE = "BATTLE RESULTS"


def rgba_from_bgr555(value: int) -> tuple[int, int, int, int]:
    return ((value & 31) * 255 // 31, ((value >> 5) & 31) * 255 // 31, ((value >> 10) & 31) * 255 // 31, 255)


def row_fill(image: Image.Image, box: tuple[int, int, int, int]) -> None:
    """Erase only glyph pixels using the existing blue plaque gradient."""
    left, top, right, bottom = box
    pixels = image.load()
    for y in range(top, bottom):
        colors = Counter(pixels[x, y] for x in range(left, right))
        fill = max((pair for pair in colors.items() if pair[0][3]), key=lambda pair: pair[1])[0]
        for x in range(left, right):
            pixels[x, y] = fill


def draw_title(image: Image.Image, box: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = box
    mask = make_compact_3x5_mask(TITLE, (right - left, bottom - top), scale=2)
    mask_pixels, pixels = mask.load(), image.load()
    # Native-style dark drop shadow followed by the same icy-white headline ink.
    for y in range(mask.height):
        for x in range(mask.width):
            if mask_pixels[x, y] and left + x + 1 < right and top + y + 1 < bottom:
                pixels[left + x + 1, top + y + 1] = (24, 40, 96, 255)
    for y in range(mask.height):
        for x in range(mask.width):
            if mask_pixels[x, y]:
                pixels[left + x, top + y] = (232, 248, 255, 255)


def nearest_palette_index(color: tuple[int, int, int, int], palette: list[tuple[int, int, int, int]], bank: int) -> int:
    if color[3] < 128:
        return 0
    start = bank * 16
    return min(range(16), key=lambda index: sum((palette[start + index][channel] - color[channel]) ** 2 for channel in range(3)))


def tile_id(live_vram: bytes, x: int, y: int) -> tuple[int, int]:
    value = struct.unpack_from("<H", live_vram, SCREEN_BASE + (y * 32 + x) * 2)[0]
    return value & 0x3FF, value >> 12


def patch_entry(entry: bytes, state: Path, qa_dir: Path, art: Path | None = None) -> tuple[bytes, list[int]]:
    regs = (state / "9reg.bin").read_bytes()
    lcd = (state / "lcdm.bin").read_bytes()
    vmem = (state / "vmem.bin").read_bytes()
    cnt = struct.unpack_from("<H", regs, 8 + 2 * 2)[0]
    if ((cnt >> 2) & 3) * 0x4000 != CHAR_BASE or ((cnt >> 8) & 31) * 0x800 != SCREEN_BASE:
        raise ValueError("captured state is not the expected battle-results main BG2 layout")
    live_vram, live_palette = lcd[:0x20000], vmem[:0x200]
    before = render(live_vram, live_palette, cnt, 0, 0)
    after = before.copy()
    if art is None:
        row_fill(after, TEXT_BOX)
        draw_title(after, TEXT_BOX)
    else:
        user_art = Image.open(art).convert("RGBA")
        if user_art.size != (168, 32):
            raise ValueError(f"header art must be 168x32, got {user_art.size}")
        after.alpha_composite(user_art, (24, 0))
    palette = [rgba_from_bgr555(struct.unpack_from("<H", live_palette, index * 2)[0]) for index in range(256)]
    out = bytearray(entry)
    changed: list[int] = []
    x0, y0, x1, y1 = TITLE_CELLS
    for tile_y in range(y0, y1):
        for tile_x in range(x0, x1):
            runtime_tile, bank = tile_id(live_vram, tile_x, tile_y)
            # Entry 307's NCGR tile payload starts at 0x10.  The captured
            # loader copies that payload directly to VRAM tile 0, so this is
            # deliberately not the common 0x50 offset used by other NCGRs.
            source_offset = 0x10 + runtime_tile * 32
            runtime_offset = CHAR_BASE + runtime_tile * 32
            if entry[source_offset:source_offset + 32] != live_vram[runtime_offset:runtime_offset + 32]:
                raise ValueError(f"entry 307 tile {runtime_tile:#x} does not match the live state")
            packed = bytearray(32)
            for py in range(8):
                for px in range(8):
                    index = nearest_palette_index(after.getpixel((tile_x * 8 + px, tile_y * 8 + py)), palette, bank)
                    packed[py * 4 + px // 2] |= index << (4 * (px & 1))
            if out[source_offset:source_offset + 32] != packed:
                out[source_offset:source_offset + 32] = packed
                changed.append(runtime_tile)
    qa_dir.mkdir(parents=True, exist_ok=True)
    before.save(qa_dir / "battle_results_header_before.png")
    after.save(qa_dir / "battle_results_header_after.png")
    after.crop((24, 0, 192, 40)).resize((1008, 240), Image.Resampling.NEAREST).save(qa_dir / "battle_results_header_after_6x.png")
    return bytes(out), sorted(set(changed))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("state", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("qa_dir", type=Path)
    parser.add_argument("--art", type=Path, help="168x32 transparent PNG exported from the user's Aseprite header")
    args = parser.parse_args()
    source = args.source.read_bytes()
    with args.source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        raw = read_nitro_file(handle, find_nitro_file(files, GRAPHICS_PATH))
    pak = XrosPak.from_bytes(raw)
    entries = [pak.unpacked_data(index) for index in range(len(pak.entries))]
    original_entry = entries[GRAPHICS_ENTRY]
    entries[GRAPHICS_ENTRY], changed_tiles = patch_entry(original_entry, args.state, args.qa_dir, args.art)
    patched = replace_nitrofs_files(source, {GRAPHICS_PATH: build_xros_pak(entries)})
    if arm9_slice(source) != arm9_slice(patched):
        raise AssertionError("ARM9 changed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    manifest = {
        "source": str(args.source.resolve()), "output": str(args.output.resolve()),
        "source_sha256": hashlib.sha256(source).hexdigest(), "output_sha256": hashlib.sha256(patched).hexdigest(),
        "changed_archive": GRAPHICS_PATH, "changed_entry": GRAPHICS_ENTRY,
        "changed_runtime_tiles": changed_tiles, "title": TITLE, "art": str(args.art.resolve()) if args.art else None,
        "preserved": ["BG_NSCR map", "BG_NCLR palette", "all other BG_NCGR entries", "ARM9", "battle EXP/BIT/item values"],
    }
    (args.qa_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
