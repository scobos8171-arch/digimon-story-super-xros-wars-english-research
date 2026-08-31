"""v97: gold labels white text + black outline (not dark-on-gold)."""
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
from patch_v93_simple_ui import GOLD, GOLD124, fill_keep_alpha  # noqa: E402
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.nitrofs_patch import replace_nitrofs_files  # noqa: E402
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file  # noqa: E402

SRC = ROOT / "outputs" / "Xros Evolution Complete US v96 FORMATION LABELS" / "Game" / "Digimon Story Xros Evolution - COMPLETE US v96 FORMATION LABELS.nds"
OUT = ROOT / "outputs" / "Xros Evolution Complete US v97 GOLD WHITE TEXT"


def paint_gold(src: Image.Image, text: str) -> Image.Image:
    out = fill_keep_alpha(src, (236, 140, 28))
    w, h = out.size
    well = (2, 2, w - 2, h - 2)
    size = (max(1, well[2] - well[0]), max(1, well[3] - well[1]))
    mask = make_ds_5x7_mask(text, size)
    black = Image.new("RGBA", size, (0, 0, 0, 255))
    white = Image.new("RGBA", size, (255, 255, 255, 255))
    # 4-connected black outline
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1)):
        out.paste(black, (well[0] + dx, well[1] + dy), mask)
    out.paste(white, (well[0], well[1]), mask)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    qa = OUT / "QA"
    qa.mkdir(exist_ok=True)
    with SRC.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        gfx_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, GRAPHICS_PATH)))
        pal_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cel_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))
    gfx = [gfx_pak.unpacked_data(i) for i in range(len(gfx_pak.entries))]

    def native(entry, cell):
        return render_full_cell(
            parse_ncgr(gfx[entry]),
            parse_nclr(pal_pak.unpacked_data(entry)),
            parse_ncer(cel_pak.unpacked_data(entry))[cell],
        )

    for entry, labels in ((221, GOLD), (124, GOLD124)):
        cells = parse_ncer(cel_pak.unpacked_data(entry))
        pal = parse_nclr(pal_pak.unpacked_data(entry))
        full = [native(entry, i) for i in range(len(cells))]
        for cell, text in labels.items():
            img = paint_gold(full[cell], text)
            full[cell] = img
            img.save(qa / f"e{entry:04d}_c{cell:02d}.png")
        gfx[entry] = encode_selected_cells(gfx[entry], cells, full, pal, set(labels))

    patched = replace_nitrofs_files(SRC.read_bytes(), {GRAPHICS_PATH: build_xros_pak(gfx)})
    assert arm9_slice(SRC.read_bytes()) == arm9_slice(bytes(patched))
    rom = OUT / "Game" / "Digimon Story Xros Evolution - COMPLETE US v97 GOLD WHITE TEXT.nds"
    rom.parent.mkdir(parents=True, exist_ok=True)
    rom.write_bytes(patched)
    Path(r"C:\Users\YOUR_NAME\Downloads\Digimon Story Xros Evolution - COMPLETE US v97 GOLD WHITE TEXT.nds").write_bytes(patched)
    print("wrote", rom)


if __name__ == "__main__":
    main()
