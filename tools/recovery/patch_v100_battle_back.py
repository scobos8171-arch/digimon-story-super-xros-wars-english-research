"""v100: only the battle-setup BACK button (entry 1987 cells 0, 2, 4).

Restore the Japanese plate, wipe the whole text well row-by-row, draw BACK.
Leave BATTLE START / ALL TACTICS / small BACKs for later passes.
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
    render_full_cell, arm9_slice, make_hex_4x7_mask,
)
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.nitrofs_patch import replace_nitrofs_files  # noqa: E402
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file  # noqa: E402

JP = ROOT / "work" / "roms" / "xros_blue.nds"
SRC = ROOT / "outputs" / "Xros Evolution Complete US v101 SAFE BANNER BACK" / "Game" / "tmp_graft.nds"
OUT = ROOT / "outputs" / "Xros Evolution Complete US v101 SAFE BANNER BACK"
CELLS = (0, 2, 4)


def paint_back(jp: Image.Image) -> Image.Image:
    out = jp.copy()
    px = out.load()
    w, h = out.size
    # Keep the right-side B icon. Wipe everything left of it.
    icon_left = w - 20
    x0, x1 = 5, icon_left
    y0, y1 = 4, h - 4
    for y in range(y0, y1):
        sample = None
        for sx in (5, 6, 7):
            r, g, b, a = px[sx, y]
            if a > 200 and max(r, g, b) < 210:
                sample = (r, g, b)
                break
        if sample is None:
            sample = (32, 96, 210)
        for x in range(x0, x1):
            r, g, b, a = px[x, y]
            if a > 0:
                px[x, y] = (*sample, a)
    well = (x0, y0, x1, y1)
    size = (x1 - x0, y1 - y0)
    mask = make_hex_4x7_mask("BACK", size)
    ink = Image.new("RGBA", size, (255, 255, 255, 255))
    shadow = Image.new("RGBA", size, (8, 24, 72, 255))
    out.paste(shadow, (x0 + 1, y0 + 1), mask)
    out.paste(ink, (x0, y0), mask)
    return out


def load(path: Path):
    with path.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        gfx = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, GRAPHICS_PATH)))
        pal = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cel = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))
    return gfx, pal, cel


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    qa = OUT / "QA"
    qa.mkdir(exist_ok=True)
    jp_gfx, jp_pal, jp_cel = load(JP)
    us_gfx, us_pal, us_cel = load(SRC)
    jp_ncgr = parse_ncgr(jp_gfx.unpacked_data(1987))
    jp_nclr = parse_nclr(jp_pal.unpacked_data(1987))
    cells = parse_ncer(jp_cel.unpacked_data(1987))
    canvases = [render_full_cell(jp_ncgr, jp_nclr, cells[i]) for i in range(len(cells))]
    for index in CELLS:
        before = canvases[index].copy()
        before.save(qa / f"before_{index:02d}.png")
        canvases[index] = paint_back(canvases[index])
        canvases[index].save(qa / f"after_{index:02d}.png")
        print(index, "jp", before.size, "after", canvases[index].size)

    gfx_out = [us_gfx.unpacked_data(i) for i in range(len(us_gfx.entries))]
    gfx_out[1987] = encode_selected_cells(
        us_gfx.unpacked_data(1987), cells, canvases, jp_nclr, set(CELLS)
    )

    patched = replace_nitrofs_files(SRC.read_bytes(), {GRAPHICS_PATH: build_xros_pak(gfx_out)})
    assert arm9_slice(SRC.read_bytes()) == arm9_slice(bytes(patched))
    rom = OUT / "Game" / "Digimon Story Xros Evolution - COMPLETE US v101 SAFE BANNER BACK.nds"
    rom.parent.mkdir(parents=True, exist_ok=True)
    rom.write_bytes(patched)
    Path(r"C:\Users\YOUR_NAME\Downloads\Digimon Story Xros Evolution - COMPLETE US v101 SAFE BANNER BACK.nds").write_bytes(patched)
    Path(r"C:\Users\YOUR_NAME\Downloads\Digimon Story Xros Evolution - COMPLETE US v98 SPECIES FAMILY NAMES.nds").write_bytes(
        (ROOT / "outputs" / "Xros Evolution Complete US v98 SPECIES FAMILY NAMES" / "Game" / "Digimon Story Xros Evolution - COMPLETE US v98 SPECIES FAMILY NAMES.nds").read_bytes()
    )
    print("wrote", rom)


if __name__ == "__main__":
    main()
