#!/usr/bin/env python3
"""Fit the approved high-resolution X-Blue logo into Xros entry 34 safely."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "work" / "DigimonNDSRomEditor-master"
sys.path.insert(0, str(RESEARCH))
sys.path.insert(0, str(ROOT / "tools" / "recovery"))

from build_xros_custom_ui_rom import render_full_cell  # noqa: E402
from rom_research.sprite_retarget import _cell_bounds, _screen_x, _screen_y  # noqa: E402
from rom_research.xros_sprite import XrosSpriteSet, parse_ncer, parse_ncgr, parse_nclr  # noqa: E402


def nearest(color: tuple[int, int, int], palette) -> tuple[int, int, int, int]:
    # Palette index zero is transparent in the sprite renderer.
    return min(
        palette[1:],
        key=lambda candidate: sum((color[index] - candidate[index]) ** 2 for index in range(3)),
    )


def main() -> None:
    source = Path(
        r"C:\Users\YOUR_NAME\Documents\Codex\2026-08-29"
        r"\c-users-scobo-downloads-xros-title\outputs\digimon-story-x-blue-redesign.png"
    )
    rom = Path(
        r"C:\Users\YOUR_NAME\Downloads\DIGIMO STORY X BLUE"
        r"\Digimon Story Xros Evolution - COMPLETE US v121 USER REMAINING EN.nds"
    )
    output = ROOT / "work" / "xros_title_v122" / "entry_0034" / "cell_00" / "english_completed.png"
    preview = ROOT / "work" / "xros_title_v122" / "title_redesign_native_8x.png"

    sprite_set = XrosSpriteSet.from_rom(rom)
    graphics = parse_ncgr(sprite_set.raw_entry("graphics", 34))
    palette = parse_nclr(sprite_set.raw_entry("palette", 34))
    cells = parse_ncer(sprite_set.raw_entry("cells", 34))
    target = render_full_cell(graphics, palette, cells[0])

    logo = Image.open(source).convert("RGBA")
    # The high-resolution source retains a few nearly invisible antialias
    # remnants far below the actual mark. Use the same opacity threshold that
    # the DS conversion uses when determining the visible crop.
    visible_alpha = logo.getchannel("A").point(lambda value: 255 if value >= 96 else 0)
    bbox = visible_alpha.getbbox()
    if bbox is None:
        raise ValueError("The redesign has no visible pixels")
    logo = logo.crop(bbox)

    # Match the title screen's existing 206-pixel visual width. Height follows
    # from the redesign's own aspect ratio; no stretching is permitted.
    maximum_width = 206
    maximum_height = target.height - 8
    scale = min(maximum_width / logo.width, maximum_height / logo.height)
    size = (max(1, round(logo.width * scale)), max(1, round(logo.height * scale)))
    logo = logo.resize(size, Image.Resampling.LANCZOS)

    native = Image.new("RGBA", target.size, (0, 0, 0, 0))
    # Entry 34 is not a rectangular bitmap. Its top 48 rows begin at x=32,
    # which clipped the redesign's wide D and Y when it was geometrically
    # centred. Starting at y=48 puts the wide top line inside the full-width
    # OAM band. One pixel of left inset keeps its 206px width inside x=0..208.
    left = 1
    top = 48
    source_pixels = logo.load()
    destination = native.load()
    cache: dict[tuple[int, int, int], tuple[int, int, int, int]] = {}
    for y in range(logo.height):
        for x in range(logo.width):
            red, green, blue, alpha = source_pixels[x, y]
            if alpha < 96:
                continue
            key = (red, green, blue)
            mapped = cache.get(key)
            if mapped is None:
                mapped = nearest(key, palette)
                cache[key] = mapped
            destination[left + x, top + y] = (*mapped[:3], 255)

    cell_left, cell_top, _cell_right, _cell_bottom = _cell_bounds(cells[0])
    coverage = Image.new("1", target.size, 0)
    coverage_pixels = coverage.load()
    for oam in cells[0].oams:
        oam_left = _screen_x(oam) - cell_left
        oam_top = _screen_y(oam) - cell_top
        oam_width, oam_height = oam.dimensions
        for y in range(max(0, oam_top), min(target.height, oam_top + oam_height)):
            for x in range(max(0, oam_left), min(target.width, oam_left + oam_width)):
                coverage_pixels[x, y] = 1
    for y in range(target.height):
        for x in range(target.width):
            if native.getpixel((x, y))[3] and not coverage_pixels[x, y]:
                raise AssertionError(f"Visible logo pixel falls outside entry-34 OAM coverage at {x},{y}")

    output.parent.mkdir(parents=True, exist_ok=True)
    native.save(output)
    enlarged = native.resize((native.width * 8, native.height * 8), Image.Resampling.NEAREST)
    enlarged.save(preview)
    print(f"target_canvas={target.size}")
    print(f"logo_native_size={logo.size}")
    print(f"placement=({left},{top})")
    print(f"native={output}")
    print(f"preview={preview}")


if __name__ == "__main__":
    main()
