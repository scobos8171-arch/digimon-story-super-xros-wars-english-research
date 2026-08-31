#!/usr/bin/env python3
"""Localize the frozen battle-menu image used by the menu tutorial."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "work" / "DigimonNDSRomEditor-master"),
    str(ROOT / "tools" / "recovery"),
    str(ROOT / "tools" / "rom_importer"),
]

from build_xros_custom_ui_rom import arm9_slice, make_ds_5x7_mask  # noqa: E402
from nitro import parse_ncgr, parse_nclr, parse_nscr, render_screen  # noqa: E402
from render_xros_state_bg_layers import render as render_live_bg  # noqa: E402
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.nitrofs_patch import replace_nitrofs_files  # noqa: E402
from rom_research.xros_pak import (  # noqa: E402
    XrosPak,
    build_xros_pak,
    find_nitro_file,
    read_nitro_file,
)


GRAPHICS_PATH = "data/BG_NCGR.PAK"
PALETTE_PATH = "data/BG_NCLR.PAK"
SCREEN_PATH = "data/BG_NSCR.PAK"
TUTORIAL_GRAPHICS_ENTRY = 87
TUTORIAL_SCREEN_ENTRY = 84
LIVE_PALETTE_ENTRY = 62
# The tutorial loader copies entry 87's tiles 657+ over VRAM characters 662+.
# Keeping the rebuilt frozen image entirely inside that tutorial-only tail
# prevents any changes to the ordinary battle UI loaded from entry 78.
SOURCE_TILE_BASE = 657
VRAM_TILE_BASE = 662


def clear_text(image: Image.Image, box: tuple[int, int, int, int]) -> None:
    """Replace baked glyphs with each scanline's dominant plaque color."""
    left, top, right, bottom = box
    pixels = image.load()
    for y in range(top, bottom):
        colors = Counter(pixels[x, y] for x in range(left, right))
        # The base plate is the most frequent opaque color on each scanline.
        fill = max(
            (item for item in colors.items() if item[0][3]),
            key=lambda item: item[1],
        )[0]
        for x in range(left, right):
            pixels[x, y] = fill


def draw_compact(
    image: Image.Image,
    text: str,
    box: tuple[int, int, int, int],
    *,
    scale_y: int = 1,
) -> None:
    left, top, right, bottom = box
    text = text.upper()
    mask = make_ds_5x7_mask(text, (right - left, bottom - top))
    mask_pixels = mask.load()
    pixels = image.load()
    # Use native colors already present in every label bank.
    white = (255, 255, 255, 255)
    shadow = (24, 24, 32, 255)
    points: list[tuple[int, int]] = []
    for y in range(bottom - top):
        for x in range(right - left):
            if mask_pixels[x, y]:
                points.append((left + x, top + y))
    for x, y in points:
        if left <= x + 1 < right and top <= y + 1 < bottom:
            pixels[x + 1, y + 1] = shadow
    for x, y in points:
        if left <= x < right and top <= y < bottom:
            pixels[x, y] = white


LABELS = (
    ((25, 1, 82, 14), "DIGIMON"),
    ((101, 1, 160, 14), "DIGIMON"),
    ((191, 1, 256, 14), "DIGIMON"),
    ((4, 43, 77, 61), "ALL TACTICS"),
    ((180, 43, 255, 61), "BATTLE START"),
    ((96, 80, 163, 96), "ACTIVE TACTIC"),
    ((30, 96, 163, 118), "BURNING STAR C"),
    ((174, 96, 256, 118), "DRILL BUSTER"),
    ((36, 171, 150, 188), "BANDAGE"),
)


def nearest_index(color: tuple[int, int, int, int], palette, bank: int) -> int:
    if color[3] < 128:
        return 0
    start = bank * 16
    candidates = range(start, min(start + 16, len(palette)))
    return min(
        candidates,
        key=lambda i: sum((palette[i][channel] - color[channel]) ** 2 for channel in range(3)),
    ) - start


def encode(graphics: bytes, screen: bytes, palette, image: Image.Image, live_map: bytes) -> tuple[bytes, bytes, int]:
    ncgr = parse_ncgr(graphics)
    nscr = parse_nscr(screen)
    columns = nscr.width // 8
    rows = nscr.height // 8
    if image.size != (nscr.width, nscr.height) or ncgr.bpp != 4:
        raise ValueError("unexpected tutorial background format")
    out_graphics = bytearray(graphics)
    out_screen = bytearray(screen)
    pixels = image.load()
    changed_positions: set[int] = set()
    for left, top, right, bottom in (box for box, _ in LABELS):
        for tile_y in range(top // 8, (bottom + 7) // 8):
            for tile_x in range(left // 8, (right + 7) // 8):
                if 0 <= tile_x < columns and 0 <= tile_y < rows:
                    changed_positions.add(tile_y * columns + tile_x)
    used_by_untouched = {
        int.from_bytes(live_map[p * 2:p * 2 + 2], "little") & 0x3FF
        for p in range(columns * rows)
        if p not in changed_positions
    }
    candidate_tiles = [
        tile for tile in range(VRAM_TILE_BASE, 1024)
        if tile not in used_by_untouched and tile - 5 < len(ncgr.tiles)
    ]
    patterns: list[bytes] = []
    pattern_indexes: dict[bytes, int] = {}
    map_values = [
        int.from_bytes(live_map[p * 2:p * 2 + 2], "little")
        for p in range(columns * rows)
    ]
    for position in sorted(changed_positions):
        tile_x, tile_y = position % columns, position // columns
        original = int.from_bytes(live_map[position * 2:position * 2 + 2], "little")
        bank = (original >> 12) & 15
        unpacked = bytearray(64)
        for y in range(8):
            for x in range(8):
                unpacked[y * 8 + x] = nearest_index(
                    pixels[tile_x * 8 + x, tile_y * 8 + y], palette, bank
                )
        packed = bytearray(32)
        for index, value in enumerate(unpacked):
            packed[index // 2] |= value << (4 * (index & 1))
        packed_bytes = bytes(packed)
        pattern = pattern_indexes.get(packed_bytes)
        if pattern is None:
            pattern = len(patterns)
            pattern_indexes[packed_bytes] = pattern
            patterns.append(packed_bytes)
        if pattern >= len(candidate_tiles):
            raise ValueError(
                f"edited labels need {len(patterns)} tiles; only {len(candidate_tiles)} safe slots"
            )
        map_values[position] = candidate_tiles[pattern] | (bank << 12)
    for pattern, packed in enumerate(patterns):
        source_tile = candidate_tiles[pattern] - 5
        offset = 0x30 + source_tile * 32
        out_graphics[offset:offset + 32] = packed
    for position, value in enumerate(map_values):
        offset = 0x24 + position * 2
        out_screen[offset:offset + 2] = value.to_bytes(2, "little")
    return bytes(out_graphics), bytes(out_screen), len(patterns)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("state", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("qa_dir", type=Path)
    args = parser.parse_args()
    source = args.source.read_bytes()
    with args.source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        gfx_raw = read_nitro_file(handle, find_nitro_file(files, GRAPHICS_PATH))
        pal_raw = read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH))
        scr_raw = read_nitro_file(handle, find_nitro_file(files, SCREEN_PATH))
    gfx_pak, pal_pak, scr_pak = map(XrosPak.from_bytes, (gfx_raw, pal_raw, scr_raw))
    graphics = [gfx_pak.unpacked_data(i) for i in range(len(gfx_pak.entries))]
    screens = [scr_pak.unpacked_data(i) for i in range(len(scr_pak.entries))]
    palette = parse_nclr(pal_pak.unpacked_data(LIVE_PALETTE_ENTRY))
    regs = (args.state / "9reg.bin").read_bytes()
    lcd = (args.state / "lcdm.bin").read_bytes()
    vmem = (args.state / "vmem.bin").read_bytes()
    cnt = int.from_bytes(regs[0x1008:0x100A], "little")
    hofs = int.from_bytes(regs[0x1010:0x1012], "little") & 0x1FF
    vofs = int.from_bytes(regs[0x1012:0x1014], "little") & 0x1FF
    before = render_live_bg(lcd[0x40000:0x60000], vmem[0x400:0x600], cnt, hofs, vofs)
    after = before.copy()
    for box, text in LABELS:
        clear_text(after, box)
        draw_compact(after, text, box)
    live_map = lcd[0x40000:0x40600]
    graphics[TUTORIAL_GRAPHICS_ENTRY], screens[TUTORIAL_SCREEN_ENTRY], tile_count = encode(
        graphics[TUTORIAL_GRAPHICS_ENTRY], screens[TUTORIAL_SCREEN_ENTRY], palette, after, live_map
    )
    new_gfx = build_xros_pak(graphics)
    new_scr = build_xros_pak(screens)
    patched = replace_nitrofs_files(source, {GRAPHICS_PATH: new_gfx, SCREEN_PATH: new_scr})
    if arm9_slice(source) != arm9_slice(patched):
        raise AssertionError("ARM9 changed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.qa_dir.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    # The rebuilt map references the runtime destination indices; render a QA
    # preview from the desired composed image rather than the source archive's
    # intentionally shifted tile tail.
    decoded = after
    for name, image in (("before", before), ("after", decoded)):
        image.save(args.qa_dir / f"{name}.png")
        image.resize((1024, 768), Image.Resampling.NEAREST).save(args.qa_dir / f"{name}_4x.png")
    unchanged_gfx = [i for i in range(len(graphics)) if i != TUTORIAL_GRAPHICS_ENTRY and gfx_pak.unpacked_data(i) != graphics[i]]
    unchanged_scr = [i for i in range(len(screens)) if i != TUTORIAL_SCREEN_ENTRY and scr_pak.unpacked_data(i) != screens[i]]
    manifest = {
        "source": str(args.source.resolve()),
        "output": str(args.output.resolve()),
        "source_sha256": sha(source),
        "output_sha256": sha(patched),
        "changed_archives": [GRAPHICS_PATH, SCREEN_PATH],
        "changed_entries": {GRAPHICS_PATH: [TUTORIAL_GRAPHICS_ENTRY], SCREEN_PATH: [TUTORIAL_SCREEN_ENTRY]},
        "tutorial_tile_patterns": tile_count,
        "other_graphics_entries_changed": unchanged_gfx,
        "other_screen_entries_changed": unchanged_scr,
        "palette_archive_unchanged": True,
        "sprite_archives_unchanged": True,
        "arm9_unchanged": True,
        "labels": [text for _, text in LABELS],
    }
    (args.qa_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
