"""v102: clean buttons on v98. ARM9 untouched. SPR members overwritten in place."""
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
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, find_nitro_file, read_nitro_file  # noqa: E402

JP = ROOT / "work" / "roms" / "xros_blue.nds"
SRC = ROOT / "outputs" / "Xros Evolution Complete US v98 SPECIES FAMILY NAMES" / "Game" / "Digimon Story Xros Evolution - COMPLETE US v98 SPECIES FAMILY NAMES.nds"
OUT = ROOT / "outputs" / "Xros Evolution Complete US v102 INPLACE CLEAN BUTTONS"

# icon_side: which edge keeps the controller icon
SPECS = {
    1987: {
        0: ("BACK", "right"),
        1: ("BATTLE START", "left"),
        2: ("BACK", "right"),
        3: ("BATTLE START", "left"),
        4: ("BACK", "right"),
        5: ("BATTLE START", "left"),
        6: ("ALL TACTICS", "right"),
        7: ("ALL TACTICS", "right"),
        8: ("ALL TACTICS", "right"),
        9: ("BACK", "right"),
        10: ("BACK", "right"),
        11: ("BACK", "right"),
    },
    147: {
        1: ("CONFIRM", "left"),
        2: ("BACK", "left"),
        3: ("BACK", "left"),
    },
    110: {
        0: ("BACK", "left"),
        1: ("CONFIRM", "left"),
        2: ("NEXT", "left"),
        3: ("DONE", "left"),
        4: ("DONE", "left"),
    },
    194: {0: ("BACK", "left")},
    2218: {
        0: ("BACK", "left"),
        1: ("CONFIRM", "left"),
        2: ("SWITCH", "left"),
        3: ("BACK", "left"),
        4: ("CONFIRM", "left"),
        5: ("SWITCH", "left"),
    },
}


def paint(cell: Image.Image, text: str, icon_side: str) -> Image.Image:
    out = cell.copy()
    px = out.load()
    w, h = out.size
    if icon_side == "left":
        x0, x1 = 18, w - 3
    else:
        x0, x1 = 5, w - 20
    y0, y1 = 4, h - 4
    for y in range(max(0, y0), min(h, y1)):
        sample = None
        probe = x0 if icon_side == "right" else min(w - 4, x1 - 1)
        for sx in (probe, probe + 1 if probe + 1 < w else probe):
            r, g, b, a = px[max(0, min(w - 1, sx)), y]
            if a > 200 and max(r, g, b) < 220:
                sample = (r, g, b)
                break
        if sample is None:
            sample = (40, 110, 220)
        for x in range(max(0, x0), min(w, x1)):
            r, g, b, a = px[x, y]
            if a > 0:
                px[x, y] = (*sample, a)
    size = (max(1, min(w, x1) - max(0, x0)), max(1, min(h, y1) - max(0, y0)))
    mask = make_ds_5x7_mask(text, size)
    ink = Image.new("RGBA", size, (255, 255, 255, 255))
    sh = Image.new("RGBA", size, (12, 28, 72, 255))
    out.paste(sh, (max(0, x0) + 1, max(0, y0) + 1), mask)
    out.paste(ink, (max(0, x0), max(0, y0)), mask)
    return out


def load_paks(path: Path):
    with path.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        gfx_item = find_nitro_file(files, GRAPHICS_PATH)
        gfx = XrosPak.from_bytes(read_nitro_file(handle, gfx_item))
        pal = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cel = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))
    return files, gfx_item, gfx, pal, cel


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    qa = OUT / "QA"
    qa.mkdir(exist_ok=True)
    rom = bytearray(SRC.read_bytes())
    jp_files, _, jp_gfx, jp_pal, jp_cel = load_paks(JP)
    us_files, gfx_item, us_gfx, us_pal, us_cel = load_paks(SRC)
    pak = bytearray(us_gfx.data)

    # ARM9 must stay identical to v98.
    with SRC.open("rb") as handle:
        from rom_research.nds_inventory import read_header as rh
        hdr = rh(handle)
        arm9 = bytes(rom[int(hdr["arm9_offset"]): int(hdr["arm9_offset"]) + int(hdr["arm9_size"])])

    for entry, labels in SPECS.items():
        jp_ncgr = parse_ncgr(jp_gfx.unpacked_data(entry))
        jp_nclr = parse_nclr(jp_pal.unpacked_data(entry))
        cells = parse_ncer(jp_cel.unpacked_data(entry))
        canvases = [render_full_cell(jp_ncgr, jp_nclr, cells[i]) for i in range(len(cells))]
        for cell, (text, side) in labels.items():
            canvases[cell] = paint(canvases[cell], text, side)
            canvases[cell].save(qa / f"e{entry:04d}_c{cell:02d}.png")
        painted = encode_selected_cells(
            jp_gfx.unpacked_data(entry), cells, canvases, jp_nclr, set(labels)
        )
        slot = us_gfx.entries[entry]
        if len(painted) != slot.stored_size:
            raise ValueError(f"entry {entry} painted {len(painted)} != slot {slot.stored_size}")
        if not slot.is_uncompressed:
            raise ValueError(f"entry {entry} is compressed; refusing in-place write")
        pak[slot.offset:slot.offset + slot.stored_size] = painted
        print(f"entry {entry} in-place {len(painted)} bytes")

    rom[gfx_item.offset:gfx_item.offset + gfx_item.size] = pak
    with SRC.open("rb") as handle:
        hdr = rh(handle)
        arm9_after = bytes(rom[int(hdr["arm9_offset"]): int(hdr["arm9_offset"]) + int(hdr["arm9_size"])])
    if arm9 != arm9_after:
        raise AssertionError("ARM9 changed")
    dest = OUT / "Game" / "Digimon Story Xros Evolution - COMPLETE US v102 INPLACE CLEAN BUTTONS.nds"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(rom)
    Path(r"C:\Users\YOUR_NAME\Downloads\Digimon Story Xros Evolution - COMPLETE US v102 INPLACE CLEAN BUTTONS.nds").write_bytes(rom)
    print("wrote", dest, "bytes", len(rom), "arm9 unchanged")


if __name__ == "__main__":
    main()
