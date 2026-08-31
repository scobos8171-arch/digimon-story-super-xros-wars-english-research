"""Build Xros button sprites from user-supplied blank native-frame sheets.

The sheets are renderer contact sheets at 6x scale.  This tool extracts the
blank frame for each button, fits it to the *live* cell size, applies the live
cell's transparency mask, then draws only the English hex-caption face.  No
old Japanese/English glyph pixels are retained from the source ROM.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))
sys.path.insert(0, str(ROOT / "tools" / "recovery"))

from build_xros_custom_ui_rom import (  # noqa: E402
    GRAPHICS_PATH,
    PALETTE_PATH,
    CELLS_PATH,
    _cell_bounds,
    arm9_slice,
    edit_canvas,
    encode_selected_cells,
    render_full_cell,
)
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.nitrofs_patch import replace_nitrofs_files  # noqa: E402
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file  # noqa: E402
from rom_research.xros_sprite import parse_ncer, parse_ncgr, parse_nclr  # noqa: E402


SCALE = 6
SHEET_BACKGROUND = (18, 26, 40, 255)

# (entry, cell): (source-sheet native width, source-sheet native height, label)
SOURCE_CELLS = {
    (147, 1): (58, 18, "CONFIRM"),
    (147, 2): (52, 18, "BACK"),
    (147, 3): (52, 18, "BACK"),
    (1987, 0): (88, 28, "BACK"),
    (1987, 1): (89, 28, "BATTLE START"),
    (1987, 2): (88, 28, "BACK"),
    (1987, 3): (89, 28, "BATTLE START"),
    (1987, 4): (89, 28, "BACK"),
    (1987, 5): (89, 28, "BATTLE START"),
    (1987, 6): (88, 28, "ALL TACTICS"),
    (1987, 7): (88, 28, "ALL TACTICS"),
    (1987, 8): (89, 28, "ALL TACTICS"),
    (1987, 9): (68, 28, "BACK"),
    (1987, 10): (68, 28, "BACK"),
    (1987, 11): (69, 28, "BACK"),
}

# The selected v105 base already contains clean, native CONFIRM/BACK art for
# entry 147.  Its exported "blank" reference sheet has an opaque white
# editor backing layer, so importing it would damage working button art.
# Entry 1987 is the actual unfinished battle-button family.
APPLY_ENTRIES = (1987,)


def crop_sheet_cell(sheet: Image.Image, entry: int, cell: int) -> Image.Image:
    """Extract one native-sized blank frame from the known 6x contact sheet."""
    widths = [item[0] for (group, _cell), item in SOURCE_CELLS.items() if group == entry]
    heights = [item[1] for (group, _cell), item in SOURCE_CELLS.items() if group == entry]
    width, height, _label = SOURCE_CELLS[(entry, cell)]
    slot_width = max(widths) * SCALE + 24
    slot_height = max(heights) * SCALE + 30
    if sheet.size != (slot_width * (max(key[1] for key in SOURCE_CELLS if key[0] == entry) + 1), slot_height):
        raise ValueError(f"Unexpected entry {entry} sheet dimensions: {sheet.size}")
    x = cell * slot_width + (slot_width - width * SCALE) // 2
    y = 24 + (slot_height - 24 - height * SCALE) // 2
    return sheet.crop((x, y, x + width * SCALE, y + height * SCALE)).resize((width, height), Image.Resampling.NEAREST)


def label_spec(entry: int, cell: int, text: str) -> dict[str, object]:
    if entry == 147:
        # Live v105 cells are two pixels taller than the clean sheet assets.
        # The frames are fitted first, then the label is centred in their live
        # 20px high space.
        left, right = 15, 58 if cell == 1 else 52
        # Put the face in the saturated-blue centre band, below the pale
        # highlight.  This is both more legible and visually matches the
        # finished hex labels.
        return {"text": text, "mode": "frame", "font_style": "hex_4x7", "shadow": True,
                "outline": False, "text_rect": (left, 8, right, 18)}
    if cell in (1, 3, 5):
        rect = (22, 12, 88, 25)
    elif cell in (6, 7, 8):
        rect = (4, 12, 67, 25)
    elif cell in (9, 10, 11):
        rect = (0, 12, 51, 25)
    else:
        rect = (3, 12, 66, 25)
    return {"text": text, "mode": "frame", "font_style": "hex_4x7", "shadow": True,
            "outline": False, "text_rect": rect}


def make_preview(images: list[tuple[int, int, Image.Image]], output: Path) -> None:
    columns, scale = 3, 6
    width, height = 310, 230
    sheet = Image.new("RGBA", (columns * width, ((len(images) + columns - 1) // columns) * height), SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    for index, (entry, cell, image) in enumerate(images):
        x, y = (index % columns) * width, (index // columns) * height
        draw.text((x + 5, y + 5), f"{entry}:{cell}", fill="white")
        scaled = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
        sheet.alpha_composite(scaled, (x + (width - scaled.width) // 2, y + 32))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def build(source: Path, entry147_sheet: Path, entry1987_sheet: Path, output: Path, manifest: Path, preview: Path) -> dict[str, object]:
    sheets = {147: Image.open(entry147_sheet).convert("RGBA"), 1987: Image.open(entry1987_sheet).convert("RGBA")}
    source_data = source.read_bytes()
    with source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        graphics_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, GRAPHICS_PATH)))
        palette_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cells_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))
    graphics_entries = [graphics_pak.unpacked_data(index) for index in range(len(graphics_pak.entries))]
    preview_images: list[tuple[int, int, Image.Image]] = []
    applied: list[dict[str, object]] = []
    for entry in APPLY_ENTRIES:
        graphics = parse_ncgr(graphics_entries[entry])
        palette = parse_nclr(palette_pak.unpacked_data(entry))
        cells = parse_ncer(cells_pak.unpacked_data(entry))
        canvases = [render_full_cell(graphics, palette, value) for value in cells]
        selected: set[int] = set()
        for (group, cell), (_w, _h, text) in SOURCE_CELLS.items():
            if group != entry:
                continue
            blank = crop_sheet_cell(sheets[entry], entry, cell)
            target = canvases[cell]
            # The NCER encoder uses padded OAM canvases (for example 64x32)
            # while the artist's button frame is the actual visible sprite
            # (for example 58x18).  Do not stretch that frame to the OAM
            # canvas; centre it at its native scale before lettering.
            if blank.size != target.size:
                fitted = target.copy()
                fitted.alpha_composite(
                    blank,
                    ((target.width - blank.width) // 2, (target.height - blank.height) // 2),
                )
                blank = fitted
            blank.putalpha(target.getchannel("A"))
            canvases[cell] = edit_canvas(blank, label_spec(entry, cell, text), palette, None)
            preview_images.append((entry, cell, canvases[cell]))
            selected.add(cell)
            applied.append({"entry": entry, "cell": cell, "text": text, "canvas": list(target.size)})
        graphics_entries[entry] = encode_selected_cells(graphics_entries[entry], cells, canvases, palette, selected)
    patched = replace_nitrofs_files(source_data, {GRAPHICS_PATH: build_xros_pak(graphics_entries)})
    if arm9_slice(source_data) != arm9_slice(patched):
        raise AssertionError("ARM9 changed during button import")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patched)
    make_preview(preview_images, preview)
    report = {"source": str(source.resolve()), "output": str(output.resolve()),
              "source_sha256": hashlib.sha256(source_data).hexdigest(),
              "output_sha256": hashlib.sha256(patched).hexdigest(),
              "source_sheets": {"entry147": str(entry147_sheet.resolve()), "entry1987": str(entry1987_sheet.resolve())},
              "arm9_unchanged": True, "patched_archives": [GRAPHICS_PATH], "applied": applied}
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("entry147_sheet", type=Path)
    parser.add_argument("entry1987_sheet", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("preview", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(**vars(args)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
