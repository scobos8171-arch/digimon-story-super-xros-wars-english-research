"""v105: hex-menu BACK (entry 198 cell 8) from the original 52x18 plate.

Leaves hex label tiles (cells 1-7) in the same NCGR. ARM9 unchanged.
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
    render_full_cell, make_ds_5x7_mask,
)
from patch_v103_original_plates import inpaint_letters, draw_english  # noqa: E402
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, find_nitro_file, read_nitro_file  # noqa: E402

JP = ROOT / "work" / "roms" / "xros_blue.nds"
SRC = ROOT / "outputs" / "Xros Evolution Complete US v104 USER BLANKS" / "Game" / "Digimon Story Xros Evolution - COMPLETE US v104 USER BLANKS.nds"
OUT = ROOT / "outputs" / "Xros Evolution Complete US v105 HEX BACK"


def load(path: Path):
    with path.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        item = find_nitro_file(files, GRAPHICS_PATH)
        gfx = XrosPak.from_bytes(read_nitro_file(handle, item))
        pal = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cel = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))
    return item, gfx, pal, cel


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    qa = OUT / "QA"
    qa.mkdir(exist_ok=True)
    rom = bytearray(SRC.read_bytes())
    _, jp_gfx, jp_pal, jp_cel = load(JP)
    us_item, us_gfx, us_pal, us_cel = load(SRC)
    with SRC.open("rb") as handle:
        hdr = read_header(handle)
    arm9 = bytes(rom[int(hdr["arm9_offset"]): int(hdr["arm9_offset"]) + int(hdr["arm9_size"])])

    jp_ncgr = parse_ncgr(jp_gfx.unpacked_data(198))
    jp_nclr = parse_nclr(jp_pal.unpacked_data(198))
    cells = parse_ncer(jp_cel.unpacked_data(198))
    original = render_full_cell(jp_ncgr, jp_nclr, cells[8])
    original.save(qa / "jp_08.png")
    cleaned = inpaint_letters(original, "left")
    cleaned.save(qa / "inpaint_08.png")
    painted = draw_english(cleaned, "BACK", "left")
    painted.save(qa / "en_08.png")
    print("jp", original.size, original.getbbox(), "painted", painted.size, painted.getbbox())

    us_ncgr_bytes = us_gfx.unpacked_data(198)
    us_nclr = parse_nclr(us_pal.unpacked_data(198))
    us_cells = parse_ncer(us_cel.unpacked_data(198))
    canvases = [render_full_cell(parse_ncgr(us_ncgr_bytes), us_nclr, us_cells[i]) for i in range(len(us_cells))]
    canvases[8] = painted
    encoded = encode_selected_cells(us_ncgr_bytes, us_cells, canvases, us_nclr, {8})
    slot = us_gfx.entries[198]
    print("encoded", len(encoded), "slot", slot.stored_size, "uncomp", slot.is_uncompressed)
    if len(encoded) != slot.stored_size:
        raise ValueError("size mismatch")
    pak = bytearray(us_gfx.data)
    pak[slot.offset:slot.offset + slot.stored_size] = encoded
    rom[us_item.offset:us_item.offset + us_item.size] = pak
    if arm9 != bytes(rom[int(hdr["arm9_offset"]): int(hdr["arm9_offset"]) + int(hdr["arm9_size"])]):
        raise AssertionError("ARM9 changed")
    dest = OUT / "Game" / "Digimon Story Xros Evolution - COMPLETE US v105 HEX BACK.nds"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(rom)
    Path(r"C:\Users\YOUR_NAME\Downloads\Digimon Story Xros Evolution - COMPLETE US v105 HEX BACK.nds").write_bytes(rom)
    print("wrote", dest)


if __name__ == "__main__":
    main()
