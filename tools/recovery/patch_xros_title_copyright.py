#!/usr/bin/env python3
"""Install the English title copyright strip into both Xros title variants."""

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
    replace_nitrofs_files,
)


ENTRIES = (39, 40)


def ds_color(color: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(max(0, min(31, round(component * 31 / 255))) for component in color)


def expand_color(color: tuple[int, int, int]) -> tuple[int, int, int, int]:
    return tuple(component * 255 // 31 for component in color) + (255,)


def make_palette(art: Image.Image) -> tuple[list[tuple[int, int, int]], tuple[tuple[int, int, int, int], ...]]:
    # The artwork deliberately has just four colors. Keep them in a stable
    # palette order with index 0 reserved for transparency.
    palette5: list[tuple[int, int, int]] = [(0, 0, 0)]
    seen = {(0, 0, 0)}
    for red, green, blue, alpha in art.getdata():
        if alpha < 128:
            continue
        color = ds_color((red, green, blue))
        if color not in seen:
            seen.add(color)
            palette5.append(color)
    runtime = tuple((0, 0, 0, 0) if index == 0 else expand_color(color)
                    for index, color in enumerate(palette5))
    return palette5, runtime


def encode_nclr(template: bytes, palette: list[tuple[int, int, int]]) -> bytes:
    result = bytearray(template)
    capacity = (len(result) - 0x28) // 2
    if len(palette) > capacity:
        raise ValueError(f"palette needs {len(palette)} colors, capacity is {capacity}")
    for index in range(capacity):
        red, green, blue = palette[index] if index < len(palette) else (0, 0, 0)
        result[0x28 + index * 2:0x2A + index * 2] = (red | green << 5 | blue << 10).to_bytes(2, "little")
    return bytes(result)


def nearest_index(color: tuple[int, int, int], palette: tuple[tuple[int, int, int, int], ...]) -> int:
    return min(range(1, len(palette)), key=lambda index: sum(
        (color[channel] - palette[index][channel]) ** 2 for channel in range(3)
    ))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("art", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("qa_dir", type=Path)
    args = parser.parse_args()

    art = Image.open(args.art).convert("RGBA")
    if art.size != (246, 32):
        raise ValueError(f"{args.art.name} must be 246x32; got {art.size}")
    palette5, runtime_palette = make_palette(art)
    if len(palette5) > 256:
        raise ValueError("copyright palette exceeds DS palette capacity")

    source_data = args.source.read_bytes()
    with args.source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        graphics_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, GRAPHICS_PATH)))
        palette_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cells_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))

    graphics = [graphics_pak.unpacked_data(index) for index in range(len(graphics_pak.entries))]
    palettes = [palette_pak.unpacked_data(index) for index in range(len(palette_pak.entries))]
    qa_images: dict[int, Image.Image] = {}
    for entry in ENTRIES:
        cells = parse_ncer(cells_pak.unpacked_data(entry))
        if len(cells) != 1:
            raise ValueError(f"entry {entry} expected one cell, got {len(cells)}")
        native = Image.new("RGBA", (256, 32), (0, 0, 0, 0))
        # These native exports are 246px wide inside a 256px storage canvas.
        native.alpha_composite(art, (5, 0))
        encoded = Image.new("RGBA", native.size, (0, 0, 0, 0))
        cache: dict[tuple[int, int, int], int] = {}
        for y in range(native.height):
            for x in range(native.width):
                red, green, blue, alpha = native.getpixel((x, y))
                if alpha < 128:
                    continue
                key = (red, green, blue)
                index = cache.get(key)
                if index is None:
                    index = nearest_index(key, runtime_palette)
                    cache[key] = index
                encoded.putpixel((x, y), runtime_palette[index])
        graphics[entry] = encode_selected_cells(graphics[entry], cells, [encoded], runtime_palette, {0})
        palettes[entry] = encode_nclr(palettes[entry], palette5)
        qa_images[entry] = encoded

    patched = replace_nitrofs_files(source_data, {
        GRAPHICS_PATH: build_xros_pak(graphics),
        PALETTE_PATH: build_xros_pak(palettes),
    })
    if arm9_slice(source_data) != arm9_slice(patched):
        raise AssertionError("ARM9 changed")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    args.qa_dir.mkdir(parents=True, exist_ok=True)
    for entry, image in qa_images.items():
        image.save(args.qa_dir / f"entry_{entry:04d}_copyright_runtime.png")
        image.resize((1024, 128), Image.Resampling.NEAREST).save(
            args.qa_dir / f"entry_{entry:04d}_copyright_runtime_4x.png"
        )
    (args.qa_dir / "manifest.json").write_text(json.dumps({
        "source_rom": str(args.source.resolve()),
        "output_rom": str(args.output.resolve()),
        "source_sha256": hashlib.sha256(source_data).hexdigest(),
        "output_sha256": hashlib.sha256(patched).hexdigest(),
        "art": str(args.art.resolve()),
        "entries": list(ENTRIES),
        "palette_colors_including_transparency": len(palette5),
        "changed_archives": [GRAPHICS_PATH, PALETTE_PATH],
        "arm9_unchanged": True,
    }, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
