"""v95: rebuild corrupted BACK/CONFIRM pills from clean v93 cells.

v94 only erased bright pixels, so dark kana stayed under BACK. Wipe the
whole text well, keep icon + ROM alpha, then draw the word.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))
sys.path.insert(0, str(ROOT / "tools" / "recovery"))
from build_xros_custom_ui_rom import (  # noqa: E402
    GRAPHICS_PATH, PALETTE_PATH, CELLS_PATH,
    encode_selected_cells, parse_ncgr, parse_nclr, parse_ncer,
    render_full_cell, arm9_slice, make_ds_5x7_mask,
)
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.nitrofs_patch import replace_nitrofs_files  # noqa: E402
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file  # noqa: E402

V93 = ROOT / "outputs" / "Xros Evolution Complete US v93 SIMPLE GOLD AND NATIVE BUTTONS" / "Game" / "Digimon Story Xros Evolution - COMPLETE US v93 SIMPLE GOLD AND NATIVE BUTTONS.nds"
V94 = ROOT / "outputs" / "Xros Evolution Complete US v94 SCREENSHOT UI TEXT" / "Game" / "Digimon Story Xros Evolution - COMPLETE US v94 SCREENSHOT UI TEXT.nds"
OUT = ROOT / "outputs" / "Xros Evolution Complete US v95 CLEAN BACK BUTTONS"

# Use clean Japanese v93 artwork as the plate, not the corrupted v94 cells.
LABELS = {
    110: {0: "BACK", 1: "CONFIRM", 2: "NEXT", 3: "DONE", 4: "DONE"},
    194: {0: "BACK"},
    2218: {0: "BACK", 1: "CONFIRM", 2: "SWITCH", 3: "BACK", 4: "CONFIRM", 5: "SWITCH"},
}


def wipe_well(cell: Image.Image, well: tuple[int, int, int, int]) -> Image.Image:
    out = cell.copy()
    px = out.load()
    x0, y0, x1, y1 = well
    samples = []
    for y in range(y0, y1):
        r, g, b, a = px[x0, y]
        if a > 200:
            samples.append((r, g, b))
    fill = samples[len(samples) // 2] if samples else (48, 120, 220)
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b, a = px[x, y]
            if a > 0:
                px[x, y] = (*fill, a)
    return out


def draw_word(cell: Image.Image, text: str, well: tuple[int, int, int, int]) -> Image.Image:
    out = wipe_well(cell, well)
    size = (max(1, well[2] - well[0]), max(1, well[3] - well[1]))
    mask = make_ds_5x7_mask(text, size)
    ink = Image.new("RGBA", size, (255, 255, 255, 255))
    sh = Image.new("RGBA", size, (16, 32, 80, 255))
    out.paste(sh, (well[0] + 1, well[1] + 1), mask)
    out.paste(ink, (well[0], well[1]), mask)
    return out


def load_paks(path: Path):
    with path.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        gfx = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, GRAPHICS_PATH)))
        pal = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cel = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))
    return gfx, pal, cel


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    qa = OUT / "QA"
    qa.mkdir(parents=True, exist_ok=True)
    src_gfx, src_pal, src_cel = load_paks(V93)
    dst_gfx, dst_pal, dst_cel = load_paks(V94)
    gfx_out = [dst_gfx.unpacked_data(i) for i in range(len(dst_gfx.entries))]

    for entry, labels in LABELS.items():
        cells = parse_ncer(src_cel.unpacked_data(entry))
        pal = parse_nclr(src_pal.unpacked_data(entry))
        ng = parse_ncgr(src_gfx.unpacked_data(entry))
        full = [render_full_cell(ng, pal, cells[i]) for i in range(len(cells))]
        for cell, text in labels.items():
            src = full[cell]
            well = (17, 2, src.width - 2, src.height - 2)
            img = draw_word(src, text, well)
            full[cell] = img
            img.save(qa / f"e{entry:04d}_c{cell:02d}.png")
        gfx_out[entry] = encode_selected_cells(src_gfx.unpacked_data(entry), cells, full, pal, set(labels))

    patched = replace_nitrofs_files(V94.read_bytes(), {GRAPHICS_PATH: build_xros_pak(gfx_out)})
    assert arm9_slice(V94.read_bytes()) == arm9_slice(bytes(patched))
    rom = OUT / "Game" / "Digimon Story Xros Evolution - COMPLETE US v95 CLEAN BACK BUTTONS.nds"
    rom.parent.mkdir(parents=True, exist_ok=True)
    rom.write_bytes(patched)
    Path(r"C:\Users\YOUR_NAME\Downloads\Digimon Story Xros Evolution - COMPLETE US v95 CLEAN BACK BUTTONS.nds").write_bytes(patched)
    print("wrote", rom)


if __name__ == "__main__":
    main()
