"""v94: leftover BACK/CONFIRM sprites from the user's screenshot folder."""
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
    render_full_cell, arm9_slice,
)
from patch_v93_simple_ui import center_text, erase_glyphs  # noqa: E402
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.nitrofs_patch import replace_nitrofs_files  # noqa: E402
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file  # noqa: E402

SOURCE = ROOT / "outputs" / "Xros Evolution Complete US v94 SCREENSHOT UI TEXT" / "Game" / "Digimon Story Xros Evolution - COMPLETE US v94 SCREENSHOT UI TEXT.nds"
# written by cleanup first; this script paints sprites on that ROM
OUT = SOURCE

BUTTONS = {
    110: {0: "BACK", 1: "CONFIRM", 2: "NEXT", 3: "FINISH", 4: "FINISH"},
    194: {0: "BACK"},
    2218: {0: "BACK", 1: "CONFIRM", 2: "SWITCH", 3: "BACK", 4: "CONFIRM", 5: "SWITCH"},
}


def main() -> None:
    source = SOURCE.read_bytes()
    with SOURCE.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        gfx_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, GRAPHICS_PATH)))
        pal_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cel_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))
    gfx = [gfx_pak.unpacked_data(i) for i in range(len(gfx_pak.entries))]

    def native(entry, cell):
        return render_full_cell(parse_ncgr(gfx[entry]), parse_nclr(pal_pak.unpacked_data(entry)), parse_ncer(cel_pak.unpacked_data(entry))[cell])

    qa = SOURCE.parent.parent / "QA"
    qa.mkdir(parents=True, exist_ok=True)
    for entry, labels in BUTTONS.items():
        cells = parse_ncer(cel_pak.unpacked_data(entry))
        pal = parse_nclr(pal_pak.unpacked_data(entry))
        full = [native(entry, i) for i in range(len(cells))]
        for cell, text in labels.items():
            src = full[cell]
            well = (16, 2, src.width - 2, src.height - 2)
            img = center_text(erase_glyphs(src, well), text, (255, 255, 255), "ds", well)
            full[cell] = img
            img.save(qa / f"e{entry:04d}_c{cell:02d}.png")
        gfx[entry] = encode_selected_cells(gfx[entry], cells, full, pal, set(labels))
    patched = replace_nitrofs_files(source, {GRAPHICS_PATH: build_xros_pak(gfx)})
    assert arm9_slice(source) == arm9_slice(bytes(patched))
    SOURCE.write_bytes(patched)
    Path(r"C:\Users\YOUR_NAME\Downloads\Digimon Story Xros Evolution - COMPLETE US v94 SCREENSHOT UI.nds").write_bytes(patched)
    print("sprites patched", SOURCE)


if __name__ == "__main__":
    main()
