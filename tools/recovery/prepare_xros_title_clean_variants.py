#!/usr/bin/env python3
"""Build clean, non-fringing native-DS variants of the X-Blue title logo."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "work" / "DigimonNDSRomEditor-master"
sys.path.insert(0, str(RESEARCH))
sys.path.insert(0, str(ROOT / "tools" / "recovery"))

from build_xros_custom_ui_rom import render_full_cell  # noqa: E402
from rom_research.sprite_retarget import _cell_bounds, _screen_x, _screen_y  # noqa: E402
from rom_research.xros_sprite import XrosSpriteSet, parse_ncer, parse_ncgr, parse_nclr  # noqa: E402


SOURCE = Path(
    r"C:\Users\YOUR_NAME\Documents\Codex\2026-08-29"
    r"\c-users-scobo-downloads-xros-title\outputs\digimon-story-x-blue-redesign.png"
)
ROM = Path(
    r"C:\Users\YOUR_NAME\Downloads\DIGIMO STORY X BLUE"
    r"\Digimon Story Xros Evolution - COMPLETE US v121 USER REMAINING EN.nds"
)
OUT = ROOT / "work" / "xros_title_clean_variants"


def nearest(color: tuple[int, int, int], palette) -> tuple[int, int, int, int]:
    return min(
        palette[1:],
        key=lambda candidate: sum((color[i] - candidate[i]) ** 2 for i in range(3)),
    )


def premultiplied_resize(image: Image.Image, size: tuple[int, int], resample) -> Image.Image:
    # Pillow's RGBa mode stores premultiplied color. Resizing in that mode stops
    # RGB values hidden in transparent pixels from contaminating edge pixels.
    return image.convert("RGBa").resize(size, resample).convert("RGBA")


def coverage_mask(target_size, cell) -> Image.Image:
    cell_left, cell_top, _right, _bottom = _cell_bounds(cell)
    coverage = Image.new("1", target_size, 0)
    px = coverage.load()
    for oam in cell.oams:
        left = _screen_x(oam) - cell_left
        top = _screen_y(oam) - cell_top
        width, height = oam.dimensions
        for y in range(max(0, top), min(target_size[1], top + height)):
            for x in range(max(0, left), min(target_size[0], left + width)):
                px[x, y] = 1
    return coverage


def convert_variant(
    logo: Image.Image,
    target_size: tuple[int, int],
    palette,
    resample,
    alpha_cutoff: int,
    neutral_cutoff: int,
) -> Image.Image:
    size = (206, 65)
    if resample == Image.Resampling.NEAREST:
        resized = logo.resize(size, resample)
    else:
        resized = premultiplied_resize(logo, size, resample)

    native = Image.new("RGBA", target_size, (0, 0, 0, 0))
    src = resized.load()
    dst = native.load()
    cache: dict[tuple[int, int, int], tuple[int, int, int, int]] = {}
    neutral_dark = (24, 24, 24, 255)
    for y in range(resized.height):
        for x in range(resized.width):
            r, g, b, a = src[x, y]
            if a < alpha_cutoff:
                continue
            # The source outline is intended to read as black. At DS size,
            # preserving its subtle warm antialias creates a red/brown halo.
            # Snap all genuinely dark outline samples to a native neutral.
            lum = (54 * r + 183 * g + 19 * b) // 256
            if lum < neutral_cutoff:
                mapped = neutral_dark
            else:
                key = (r, g, b)
                mapped = cache.get(key)
                if mapped is None:
                    mapped = nearest(key, palette)
                    cache[key] = mapped
            dst[1 + x, 48 + y] = (*mapped[:3], 255)
    return native


def main() -> None:
    sprite_set = XrosSpriteSet.from_rom(ROM)
    graphics = parse_ncgr(sprite_set.raw_entry("graphics", 34))
    palette = parse_nclr(sprite_set.raw_entry("palette", 34))
    cells = parse_ncer(sprite_set.raw_entry("cells", 34))
    target = render_full_cell(graphics, palette, cells[0])
    coverage = coverage_mask(target.size, cells[0])

    source = Image.open(SOURCE).convert("RGBA")
    visible = source.getchannel("A").point(lambda v: 255 if v >= 96 else 0)
    bbox = visible.getbbox()
    if not bbox:
        raise ValueError("Source has no visible pixels")
    logo = source.crop(bbox)

    configs = [
        ("A_premult_lanczos", Image.Resampling.LANCZOS, 176, 82),
        ("B_premult_box", Image.Resampling.BOX, 160, 82),
        ("C_nearest", Image.Resampling.NEAREST, 128, 82),
        ("D_premult_lanczos_hard", Image.Resampling.LANCZOS, 208, 96),
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    variants = []
    for name, resample, alpha_cutoff, neutral_cutoff in configs:
        image = convert_variant(logo, target.size, palette, resample, alpha_cutoff, neutral_cutoff)
        for y in range(target.height):
            for x in range(target.width):
                if image.getpixel((x, y))[3] and not coverage.getpixel((x, y)):
                    raise AssertionError(f"{name}: pixel outside OAM coverage at {x},{y}")
        image.save(OUT / f"{name}.png")
        variants.append((name, image))

    scale = 5
    label_height = 22
    sheet = Image.new(
        "RGB",
        (target.width * scale, len(variants) * (target.height * scale + label_height)),
        (18, 24, 34),
    )
    draw = ImageDraw.Draw(sheet)
    y = 0
    for name, image in variants:
        draw.text((4, y + 3), name, fill=(255, 255, 255))
        y += label_height
        checker = Image.new("RGBA", image.size, (10, 10, 10, 255))
        checker.alpha_composite(image)
        sheet.paste(checker.convert("RGB").resize((target.width * scale, target.height * scale), Image.Resampling.NEAREST), (0, y))
        y += target.height * scale
    sheet.save(OUT / "clean_variants_contact_sheet.png")
    print(OUT / "clean_variants_contact_sheet.png")


if __name__ == "__main__":
    main()
