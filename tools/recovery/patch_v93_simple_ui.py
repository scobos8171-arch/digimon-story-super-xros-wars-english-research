"""v93: simple gold labels, native-alpha 147/1987 buttons, stats STATUS.

Starts from v88 Canonical (v87 hex + message fixes). NCGR only.
"""
from __future__ import annotations

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
    make_ds_5x7_mask,
    make_hex_4x7_mask,
    encode_selected_cells,
    parse_ncgr,
    parse_nclr,
    parse_ncer,
    render_full_cell,
    arm9_slice,
)
from paint_blank_ui_buttons import split_sheet  # noqa: E402
from patch_xros_manual_ui_cells import palette_distance  # noqa: E402
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.nitrofs_patch import replace_nitrofs_files  # noqa: E402
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file  # noqa: E402

SOURCE = ROOT / "outputs" / "Xros Evolution Complete US v88 CANONICAL UI TEXT" / "Game" / "Digimon Story Xros Evolution - COMPLETE US v88 CANONICAL UI TEXT.nds"
OUT = ROOT / "outputs" / "Xros Evolution Complete US v93 SIMPLE GOLD AND NATIVE BUTTONS"
BUTTONS = Path(r"C:\Users\YOUR_NAME\Downloads\Buttons with no letters we need to localize")

GOLD = {
    16: "PLAYER INFO", 20: "PLAYER INFO", 21: "PLAYER INFO", 22: "PLAYER INFO",
    17: "QUEST INFO", 23: "QUEST INFO", 24: "QUEST INFO", 25: "QUEST INFO",
    18: "PARTY DIGIMON", 26: "PARTY DIGIMON", 27: "PARTY DIGIMON", 28: "PARTY DIGIMON",
    19: "FIELD GUIDE", 29: "FIELD GUIDE", 30: "FIELD GUIDE", 31: "FIELD GUIDE",
}
GOLD124 = {
    16: "DIGIXROS", 20: "DIGIXROS", 21: "DIGIXROS", 22: "DIGIXROS",
    17: "JOGRESS UP", 23: "JOGRESS UP", 24: "JOGRESS UP", 25: "JOGRESS UP",
    18: "MELODY EVOLVE", 26: "MELODY EVOLVE", 27: "MELODY EVOLVE", 28: "MELODY EVOLVE",
    19: "DIGIMON LIST", 29: "DIGIMON LIST", 30: "DIGIMON LIST", 31: "DIGIMON LIST",
}
B1987 = {
    0: "BACK", 1: "BATTLE START", 2: "BACK", 3: "BATTLE START",
    4: "BACK", 5: "BATTLE START", 6: "ALL TACTICS", 7: "ALL TACTICS",
    8: "ALL TACTICS", 9: "BACK", 10: "BACK", 11: "BACK",
}
B147 = {1: "CONFIRM", 2: "BACK", 3: "BACK"}


def fill_keep_alpha(src: Image.Image, rgb: tuple[int, int, int]) -> Image.Image:
    out = src.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a > 0:
                px[x, y] = (*rgb, a)
    return out


def center_text(canvas: Image.Image, text: str, ink: tuple[int, int, int], style: str, well=None) -> Image.Image:
    out = canvas.copy()
    w, h = out.size
    well = well or (1, 1, w - 1, h - 1)
    size = (max(1, well[2] - well[0]), max(1, well[3] - well[1]))
    mask = make_hex_4x7_mask(text, size) if style == "hex" else make_ds_5x7_mask(text, size)
    layer = Image.new("RGBA", size, (*ink, 255))
    shadow = Image.new("RGBA", size, (40, 20, 0, 180) if ink[0] > 200 else (255, 255, 255, 180))
    out.paste(shadow, (well[0] + 1, well[1] + 1), mask)
    out.paste(layer, (well[0], well[1]), mask)
    return out


def keep_rom_alpha(rom_cell: Image.Image, painted: Image.Image) -> Image.Image:
    """Painted RGB, ROM alpha. Same canvas size required."""
    if painted.size != rom_cell.size:
        fitted = Image.new("RGBA", rom_cell.size, (0, 0, 0, 0))
        ox = (rom_cell.width - painted.width) // 2
        oy = (rom_cell.height - painted.height) // 2
        fitted.paste(painted, (max(0, ox), max(0, oy)))
        painted = fitted
    out = painted.copy()
    out.putalpha(rom_cell.getchannel("A"))
    return out


def erase_glyphs(cell: Image.Image, well: tuple[int, int, int, int]) -> Image.Image:
    """Replace bright letter pixels in the well with nearby fill."""
    out = cell.copy()
    px = out.load()
    x0, y0, x1, y1 = well
    fills = []
    for y in range(y0, y1):
        for x in range(x0, min(x0 + 3, x1)):
            r, g, b, a = px[x, y]
            if a > 200 and max(r, g, b) < 200:
                fills.append((r, g, b))
    fill = fills[len(fills) // 2] if fills else (40, 110, 210)
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b, a = px[x, y]
            if a > 0 and (r + g + b) > 420:
                px[x, y] = (*fill, a)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = SOURCE.read_bytes()
    with SOURCE.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        gfx_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, GRAPHICS_PATH)))
        pal_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cel_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))

    gfx_entries = [gfx_pak.unpacked_data(i) for i in range(len(gfx_pak.entries))]
    blanks_147 = split_sheet(BUTTONS / "original_entry147_reference_sheet.png", 4)
    canvases: dict[int, dict[int, Image.Image]] = {}

    def native(entry: int, cell: int) -> Image.Image:
        g = parse_ncgr(gfx_entries[entry])
        p = parse_nclr(pal_pak.unpacked_data(entry))
        c = parse_ncer(cel_pak.unpacked_data(entry))
        return render_full_cell(g, p, c[cell])

    # Gold 221: simple filled bar, keep alpha, centered caps.
    canvases[221] = {}
    for cell, text in GOLD.items():
        src = native(221, cell)
        filled = fill_keep_alpha(src, (236, 140, 28))
        canvases[221][cell] = center_text(filled, text, (40, 16, 0), "ds")

    canvases[124] = {}
    for cell, text in GOLD124.items():
        src = native(124, cell)
        filled = fill_keep_alpha(src, (236, 140, 28))
        canvases[124][cell] = center_text(filled, text, (40, 16, 0), "ds")

    # Stats header 126 still Japanese ステータス.
    src126 = native(126, 0)
    well126 = (18, 2, src126.width - 2, src126.height - 2)
    canvases[126] = {0: center_text(erase_glyphs(src126, well126), "STATUS", (255, 255, 255), "ds", well126)}

    # 147: native alpha + artist blank RGB (exact 58x18 / 52x18).
    canvases[147] = {}
    for cell, text in B147.items():
        rom_cell = native(147, cell)
        blank = blanks_147[cell].convert("RGBA")
        painted = keep_rom_alpha(rom_cell, blank)
        well = (20, 3, painted.width - 2, painted.height - 2)
        canvases[147][cell] = center_text(painted, text, (255, 255, 255), "ds", well)

    # 1987: native canvas, wipe old letters, draw centered in blue mass.
    canvases[1987] = {}
    for cell, text in B1987.items():
        rom_cell = native(1987, cell)
        # Icon on the right for BACK/ALL TACTICS, left for BATTLE START (X).
        if "BATTLE" in text:
            well = (22, 6, rom_cell.width - 4, rom_cell.height - 4)
        else:
            well = (4, 6, rom_cell.width - 20, rom_cell.height - 4)
        wiped = erase_glyphs(rom_cell, well)
        canvases[1987][cell] = center_text(wiped, text, (255, 255, 255), "hex", well)

    # Hex BACK 198:8 — baked 52x30, keep B icon.
    src198 = native(198, 8)
    well198 = (16, 6, src198.width - 2, 24)
    canvases[198] = {8: center_text(erase_glyphs(src198, well198), "BACK", (255, 255, 255), "ds", well198)}

    preview = OUT / "QA"
    preview.mkdir(parents=True, exist_ok=True)
    for entry, cells in canvases.items():
        for cell, img in cells.items():
            img.save(preview / f"e{entry:04d}_c{cell:02d}.png")

    gfx_out = list(gfx_entries)
    for entry, cell_map in canvases.items():
        cells = parse_ncer(cel_pak.unpacked_data(entry))
        pal = parse_nclr(pal_pak.unpacked_data(entry))
        full = [native(entry, i) for i in range(len(cells))]
        for i, img in cell_map.items():
            full[i] = img
        gfx_out[entry] = encode_selected_cells(gfx_entries[entry], cells, full, pal, set(cell_map))

    new_pak = build_xros_pak(gfx_out)
    rom_path = OUT / "Game" / "Digimon Story Xros Evolution - COMPLETE US v93 SIMPLE GOLD AND NATIVE BUTTONS.nds"
    rom_path.parent.mkdir(parents=True, exist_ok=True)
    patched = replace_nitrofs_files(source, {GRAPHICS_PATH: new_pak})
    assert arm9_slice(source) == arm9_slice(bytes(patched))
    rom_path.write_bytes(patched)
    Path(r"C:\Users\YOUR_NAME\Downloads\Digimon Story Xros Evolution - COMPLETE US v93 SIMPLE GOLD AND NATIVE BUTTONS.nds").write_bytes(patched)
    print("wrote", rom_path, "bytes", len(patched))


if __name__ == "__main__":
    main()
