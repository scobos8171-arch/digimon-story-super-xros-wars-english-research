#!/usr/bin/env python3
"""Patch the user-authored X-Blue title with its own native DS palette."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "work" / "DigimonNDSRomEditor-master"
sys.path.insert(0, str(RESEARCH))
sys.path.insert(0, str(ROOT / "tools" / "recovery"))

from build_xros_custom_ui_rom import (  # noqa: E402
    CELLS_PATH,
    GRAPHICS_PATH,
    PALETTE_PATH,
    XrosPak,
    arm9_slice,
    build_xros_pak,
    encode_selected_cells,
    find_nitro_file,
    parse_ncer,
    parse_ncgr,
    read_header,
    read_nitro_file,
    read_nitrofs,
    render_full_cell,
    replace_nitrofs_files,
)
from rom_research.sprite_retarget import _cell_bounds, _screen_x, _screen_y  # noqa: E402


ENTRY = 34


def bgr555(color: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(max(0, min(31, round(channel * 31 / 255))) for channel in color)


def expanded(color5: tuple[int, int, int]) -> tuple[int, int, int, int]:
    return tuple(channel * 255 // 31 for channel in color5) + (255,)


def encode_nclr(template: bytes, palette5: list[tuple[int, int, int]]) -> bytes:
    output = bytearray(template)
    capacity = max(0, (len(output) - 0x28) // 2)
    if len(palette5) > capacity:
        raise ValueError(f"Palette has {len(palette5)} colors but NCLR capacity is {capacity}")
    for index in range(capacity):
        r, g, b = palette5[index] if index < len(palette5) else (0, 0, 0)
        value = r | (g << 5) | (b << 10)
        output[0x28 + index * 2:0x2A + index * 2] = value.to_bytes(2, "little")
    return bytes(output)


def coverage_mask(size: tuple[int, int], cell) -> Image.Image:
    left, top, _right, _bottom = _cell_bounds(cell)
    result = Image.new("1", size, 0)
    pixels = result.load()
    for oam in cell.oams:
        x0 = _screen_x(oam) - left
        y0 = _screen_y(oam) - top
        width, height = oam.dimensions
        for y in range(max(0, y0), min(size[1], y0 + height)):
            for x in range(max(0, x0), min(size[0], x0 + width)):
                pixels[x, y] = 1
    return result


def make_palette(art: Image.Image) -> tuple[list[tuple[int, int, int]], tuple[tuple[int, int, int, int], ...]]:
    opaque = [pixel[:3] for pixel in art.getdata() if pixel[3] >= 128]
    if not opaque:
        raise ValueError("Logo has no opaque pixels")
    samples = Image.new("RGB", (len(opaque), 1))
    samples.putdata(opaque)
    quantized = samples.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    raw = quantized.getpalette() or []
    count = max(quantized.getdata()) + 1
    candidate5 = [bgr555(tuple(raw[i * 3:i * 3 + 3])) for i in range(count)]

    # Index zero is transparent. Preserve the quantizer order while removing
    # colors that collapse to the same 15-bit DS value.
    palette5: list[tuple[int, int, int]] = [(0, 0, 0)]
    seen = {(0, 0, 0)}
    for color in candidate5:
        if color not in seen:
            seen.add(color)
            palette5.append(color)
    runtime = tuple((0, 0, 0, 0) if i == 0 else expanded(color) for i, color in enumerate(palette5))
    return palette5, runtime


def nearest_index(color: tuple[int, int, int], palette) -> int:
    return min(
        range(1, len(palette)),
        key=lambda i: sum((color[channel] - palette[i][channel]) ** 2 for channel in range(3)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_rom", type=Path)
    parser.add_argument("logo", type=Path)
    parser.add_argument("output_rom", type=Path)
    parser.add_argument("qa_dir", type=Path)
    args = parser.parse_args()

    source_data = args.source_rom.read_bytes()
    with args.source_rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        graphics_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, GRAPHICS_PATH)))
        palette_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cells_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))

    graphics_entries = [graphics_pak.unpacked_data(i) for i in range(len(graphics_pak.entries))]
    palette_entries = [palette_pak.unpacked_data(i) for i in range(len(palette_pak.entries))]
    cells = parse_ncer(cells_pak.unpacked_data(ENTRY))
    if len(cells) != 1:
        raise ValueError(f"Expected one title cell, found {len(cells)}")
    graphics = parse_ncgr(graphics_entries[ENTRY])
    target = render_full_cell(graphics, ((0, 0, 0, 0),) * 256, cells[0])

    supplied = Image.open(args.logo).convert("RGBA")
    bbox = supplied.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("Supplied logo is empty")
    art = supplied.crop(bbox)
    if art.width > 206 or art.height > 65:
        raise ValueError(f"Visible art {art.size} exceeds safe title region 206x65; no scaling is allowed")

    palette5, runtime_palette = make_palette(art)
    canvas = Image.new("RGBA", target.size, (0, 0, 0, 0))
    src = art.load()
    dst = canvas.load()
    cache: dict[tuple[int, int, int], int] = {}
    # The supplied artwork is cropped to its visible pixels above. Centre it
    # inside the full-width title band instead of assuming a 206px-wide mark.
    # This keeps narrower, correctly-proportioned logos visually balanced.
    left = (target.width - art.width) // 2
    top = 48
    for y in range(art.height):
        for x in range(art.width):
            r, g, b, a = src[x, y]
            if a < 128:
                continue
            key = (r, g, b)
            index = cache.get(key)
            if index is None:
                index = nearest_index(key, runtime_palette)
                cache[key] = index
            dst[left + x, top + y] = runtime_palette[index]

    coverage = coverage_mask(target.size, cells[0])
    for y in range(canvas.height):
        for x in range(canvas.width):
            if canvas.getpixel((x, y))[3] and not coverage.getpixel((x, y)):
                raise AssertionError(f"Logo pixel outside OAM coverage at {x},{y}")

    graphics_entries[ENTRY] = encode_selected_cells(
        graphics_entries[ENTRY], cells, [canvas], runtime_palette, {0}
    )
    palette_entries[ENTRY] = encode_nclr(palette_entries[ENTRY], palette5)
    patched = replace_nitrofs_files(
        source_data,
        {
            GRAPHICS_PATH: build_xros_pak(graphics_entries),
            PALETTE_PATH: build_xros_pak(palette_entries),
        },
    )
    if arm9_slice(source_data) != arm9_slice(patched):
        raise AssertionError("ARM9 changed")
    args.output_rom.parent.mkdir(parents=True, exist_ok=True)
    args.output_rom.write_bytes(patched)

    args.qa_dir.mkdir(parents=True, exist_ok=True)
    canvas.save(args.qa_dir / "prepared_custom_palette.png")
    black = Image.new("RGBA", canvas.size, (0, 0, 0, 255))
    black.alpha_composite(canvas)
    black.resize((canvas.width * 8, canvas.height * 8), Image.Resampling.NEAREST).save(
        args.qa_dir / "prepared_custom_palette_8x_black.png"
    )
    result = {
        "source_rom": str(args.source_rom.resolve()),
        "logo": str(args.logo.resolve()),
        "output_rom": str(args.output_rom.resolve()),
        "source_sha256": hashlib.sha256(source_data).hexdigest(),
        "output_sha256": hashlib.sha256(patched).hexdigest(),
        "visible_art_size": list(art.size),
        "resized": False,
        "palette_colors_including_transparency": len(palette5),
        "changed_archives": [GRAPHICS_PATH, PALETTE_PATH],
        "arm9_unchanged": True,
    }
    (args.qa_dir / "build_manifest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
