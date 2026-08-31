"""v116: recenter battle-ring captions (entry 1971) using Codex's proven 1971 path.

Codex constraints reused as-is:
  - compact 3x5 at 1x1 (vertically doubled glyphs overflow the well)
  - alpha_row_gradient only; do not expand the clear rect
  - author 5px lower so NCER wrap lands in the original caption well
  - dark ink on the pale bevel
  - in-place uncompressed SPR member; ARM9 / NCER / NCLR untouched
  - JP Blue plates as donors so overflowed v115 arrows are restored
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))
sys.path.insert(0, str(ROOT / "tools" / "recovery"))
from build_xros_custom_ui_rom import (  # noqa: E402
    CELLS_PATH,
    GRAPHICS_PATH,
    PALETTE_PATH,
    SPECS,
    edit_canvas,
    encode_selected_cells,
    parse_ncer,
    parse_ncgr,
    parse_nclr,
    render_full_cell,
)
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, find_nitro_file, read_nitro_file  # noqa: E402

JP = ROOT / "work" / "roms" / "xros_blue.nds"
SRC = (
    ROOT
    / "outputs"
    / "Xros Evolution Complete US v115 ARTIST EN BUTTONS"
    / "Game"
    / "Digimon Story Xros Evolution - COMPLETE US v115 ARTIST EN BUTTONS.nds"
)
OUT = ROOT / "outputs" / "Xros Evolution Complete US v116 RING CAPTIONS CENTERED"
DOWNLOADS = Path(
    r"C:\Users\YOUR_NAME\Downloads\Digimon Story Xros Evolution - COMPLETE US v116 RING CAPTIONS CENTERED.nds"
)
ENTRY = 1971


def load_paks(path: Path):
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
    # Module-level SPECS[1971] then adds +5 Y for a tight 68x22 authoring
    # canvas. render_full_cell on this ROM is the padded OAM canvas, so that
    # extra wrap must not be applied here. Keep Codex's 1x1 compact face,
    # dark ink, and alpha_row_gradient; place text in the Japanese well.
    specs = {}
    for cell, spec in SPECS[ENTRY].items():
        local = dict(spec)
        local["font_scale_x"] = 1
        local["font_scale_y"] = 1
        local["font_scale"] = 1
        local["outline"] = False
        local["text_tone"] = "dark"
        local["fill_strategy"] = "alpha_row_gradient"
        # Undo the +5 wrap: original well is y=5..17 on the 68x22 plate.
        clear = tuple(int(v) for v in spec["clear"])
        local["clear"] = (clear[0], 5, clear[2], 17)
        local["text_rect"] = (clear[0], 5, clear[2], 17)
        local["row_reference_x"] = spec["row_reference_x"]
        specs[cell] = local
    rom = bytearray(SRC.read_bytes())
    jp_item, jp_gfx, jp_pal, jp_cel = load_paks(JP)
    us_item, us_gfx, us_pal, us_cel = load_paks(SRC)
    del jp_item
    with SRC.open("rb") as handle:
        hdr = read_header(handle)
    arm9 = bytes(rom[int(hdr["arm9_offset"]) : int(hdr["arm9_offset"]) + int(hdr["arm9_size"])])

    slot = us_gfx.entries[ENTRY]
    if not slot.is_uncompressed:
        raise ValueError("v115 1971 is compressed; in-place overwrite is unsafe")
    nclr = parse_nclr(us_pal.unpacked_data(ENTRY))
    us_cells = parse_ncer(us_cel.unpacked_data(ENTRY))
    jp_nclr = parse_nclr(jp_pal.unpacked_data(ENTRY))
    jp_cells = parse_ncer(jp_cel.unpacked_data(ENTRY))
    jp_ncgr = parse_ncgr(jp_gfx.unpacked_data(ENTRY))
    us_ncgr_bytes = us_gfx.unpacked_data(ENTRY)
    canvases = [render_full_cell(parse_ncgr(us_ncgr_bytes), nclr, us_cells[i]) for i in range(len(us_cells))]
    selected = set()
    for cell, spec in sorted(specs.items()):
        donor = render_full_cell(jp_ncgr, jp_nclr, jp_cells[cell])
        # SPECS are authored on the tight 68x22 composed label. render_full_cell
        # returns the full OAM canvas (76x32 / 80x32) with a transparent origin
        # offset. Shift every rectangle onto that plate so the +5 NCER wrap
        # still lands in the original Japanese well.
        origin = donor.getbbox()
        if origin is None:
            raise ValueError(f"1971:{cell} donor is empty")
        ox, oy = origin[0], origin[1]
        local = dict(spec)
        local["clear"] = (
            ox + int(spec["clear"][0]),
            oy + int(spec["clear"][1]),
            ox + int(spec["clear"][2]),
            oy + int(spec["clear"][3]),
        )
        local["text_rect"] = (
            ox + int(spec["text_rect"][0]),
            oy + int(spec["text_rect"][1]),
            ox + int(spec["text_rect"][2]),
            oy + int(spec["text_rect"][3]),
        )
        painted = edit_canvas(donor, local, nclr, None)
        donor.save(qa / f"jp_{cell:02d}.png")
        painted.save(qa / f"en_{cell:02d}.png")
        canvases[cell] = painted
        selected.add(cell)
        print(cell, spec["text"], "origin", (ox, oy), "clear", local["clear"], "text", local["text_rect"])
    encoded = encode_selected_cells(us_ncgr_bytes, us_cells, canvases, nclr, selected)
    if len(encoded) != slot.stored_size:
        raise ValueError(f"1971 encoded {len(encoded)} != slot {slot.stored_size}")
    pak = bytearray(us_gfx.data)
    pak[slot.offset : slot.offset + slot.stored_size] = encoded
    rom[us_item.offset : us_item.offset + us_item.size] = pak
    if arm9 != bytes(rom[int(hdr["arm9_offset"]) : int(hdr["arm9_offset"]) + int(hdr["arm9_size"])]):
        raise AssertionError("ARM9 changed")
    patched = parse_ncgr(encoded)
    for cell in sorted(selected):
        render_full_cell(patched, nclr, us_cells[cell]).save(qa / f"rom_{cell:02d}.png")
    dest = OUT / "Game" / "Digimon Story Xros Evolution - COMPLETE US v116 RING CAPTIONS CENTERED.nds"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(rom)
    DOWNLOADS.write_bytes(rom)
    print("wrote", dest)
    print("wrote", DOWNLOADS)


if __name__ == "__main__":
    main()
