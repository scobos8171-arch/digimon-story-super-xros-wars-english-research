#!/usr/bin/env python3
"""Patch manually edited, native-size Xros UI PNG cells into a ROM safely."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "recovery"))
from build_xros_custom_ui_rom import (  # noqa: E402
    GRAPHICS_PATH,
    arm9_slice,
    encode_selected_cells,
    parse_ncer,
    parse_ncgr,
    parse_nclr,
    read_header,
    read_nitro_file,
    read_nitrofs,
    render_full_cell,
    replace_nitrofs_files,
    XrosPak,
    build_xros_pak,
    find_nitro_file,
)


def load_exact(path: Path, size: tuple[int, int]) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    if image.size != size:
        raise ValueError(f"{path.name} is {image.size}; expected exactly {size}. No scaling was performed.")
    return image


def restore_to_storage_canvas(path: Path, storage_canvas: Image.Image) -> Image.Image:
    """Place an exported visible cell back into its untouched padded OAM canvas."""
    image = Image.open(path).convert("RGBA")
    if image.size == storage_canvas.size:
        return image
    visible = storage_canvas.getbbox()
    if visible is None:
        raise ValueError(f"{path.name} has no matching source bounds")
    visible_size = (visible[2] - visible[0], visible[3] - visible[1])
    if image.size != visible_size:
        raise ValueError(
            f"{path.name} is {image.size}; expected native visible size {visible_size} "
            f"or full storage size {storage_canvas.size}. No scaling was performed."
        )
    restored = Image.new("RGBA", storage_canvas.size, (0, 0, 0, 0))
    restored.alpha_composite(image, (visible[0], visible[1]))
    return restored


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("preview", type=Path)
    parser.add_argument("--title-menu", required=True, type=Path, help="Entry 38 cell 1: 162x50 PNG")
    parser.add_argument("--status-pill", required=True, type=Path, help="Entry 126 cell 0: 64x18 PNG")
    args = parser.parse_args()

    source_data = args.source.read_bytes()
    with args.source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        graphics_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, GRAPHICS_PATH)))
        palette_path = "data/SPR_NCLR.PAK"
        cells_path = "data/SPR_NCER.PAK"
        palette_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, palette_path)))
        cells_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, cells_path)))

    entries = [graphics_pak.unpacked_data(index) for index in range(len(graphics_pak.entries))]
    edits = {38: {1: args.title_menu}, 126: {0: args.status_pill}}
    previews: list[tuple[int, int, Image.Image]] = []
    for entry, replacements in edits.items():
        cells = parse_ncer(cells_pak.unpacked_data(entry))
        palette = parse_nclr(palette_pak.unpacked_data(entry))
        canvases = [render_full_cell(parse_ncgr(entries[entry]), palette, cell) for cell in cells]
        for cell, path in replacements.items():
            canvases[cell] = restore_to_storage_canvas(path, canvases[cell])
            previews.append((entry, cell, canvases[cell]))
        entries[entry] = encode_selected_cells(entries[entry], cells, canvases, palette, set(replacements))

    patched = replace_nitrofs_files(source_data, {GRAPHICS_PATH: build_xros_pak(entries)})
    if arm9_slice(source_data) != arm9_slice(patched):
        raise AssertionError("ARM9 changed during graphics-only patch")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps({
        "source_rom": str(args.source.resolve()),
        "output_rom": str(args.output.resolve()),
        "source_sha256": hashlib.sha256(source_data).hexdigest(),
        "output_sha256": hashlib.sha256(patched).hexdigest(),
        "changed_archives": [GRAPHICS_PATH],
        "arm9_unchanged": True,
        "manual_assets": {"38:1": str(args.title_menu.resolve()), "126:0": str(args.status_pill.resolve())},
    }, indent=2), encoding="utf-8")
    sheet = Image.new("RGBA", (200, 120), (24, 31, 44, 255))
    draw = ImageDraw.Draw(sheet)
    y = 8
    for entry, cell, image in previews:
        draw.text((8, y), f"{entry}:{cell}  {image.width}x{image.height}", fill="white")
        y += 18
        sheet.alpha_composite(image, (8, y))
        y += image.height + 10
    args.preview.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.preview)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
