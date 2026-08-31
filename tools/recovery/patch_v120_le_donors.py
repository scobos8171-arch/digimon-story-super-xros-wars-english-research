"""v120: Lost Evolution English donors onto leftover Xros cells of the same meaning.

Only same-meaning swaps. Aspect-fit the LE opaque plate into the native
Xros cell well. SPR in-place, ARM9 unchanged.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))
sys.path.insert(0, str(ROOT / "tools" / "recovery"))
from build_xros_custom_ui_rom import (  # noqa: E402
    CELLS_PATH,
    GRAPHICS_PATH,
    PALETTE_PATH,
    encode_selected_cells,
    parse_ncer,
    parse_ncgr,
    parse_nclr,
    render_full_cell,
)
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, find_nitro_file, read_nitro_file  # noqa: E402

SRC = (
    ROOT
    / "outputs"
    / "Xros Evolution Complete US v119 BATTLE MENU"
    / "Game"
    / "Digimon Story Xros Evolution - COMPLETE US v119 BATTLE MENU.nds"
)
OUT = ROOT / "outputs" / "Xros Evolution Complete US v120 LE DONORS"
DOWNLOADS = Path(r"C:\Users\YOUR_NAME\Downloads\Digimon Story Xros Evolution - COMPLETE US v120 LE DONORS.nds")
LE = Path(r"C:\Users\YOUR_NAME\Downloads\Lost Evolution English Button Donors - Native")

# (xros_entry, xros_cell, le_png, meaning)
SWAPS = [
    (104, 0, "LE_entry0094_cell00_160x41.png", "DIGIFARM"),
    (2242, 0, "LE_entry0064_cell00_141x24.png", "QUEST REWARDS"),
    (2242, 1, "LE_entry0063_cell00_130x29.png", "CONDITIONS"),
    (2002, 0, "LE_entry0178_cell00_97x19.png", "NEXT"),
]


def load_paks(path: Path):
    with path.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        item = find_nitro_file(files, GRAPHICS_PATH)
        gfx = XrosPak.from_bytes(read_nitro_file(handle, item))
        pal = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cel = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))
    return item, gfx, pal, cel


def aspect_fit(donor: Image.Image, canvas: Image.Image) -> Image.Image:
    out = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    piece = donor.convert("RGBA")
    box = piece.getbbox()
    if box is not None:
        piece = piece.crop(box)
    target = canvas.getbbox() or (0, 0, canvas.width, canvas.height)
    tw, th = target[2] - target[0], target[3] - target[1]
    if tw < 1 or th < 1:
        return out
    scale = min(tw / piece.width, th / piece.height)
    nw = max(1, round(piece.width * scale))
    nh = max(1, round(piece.height * scale))
    fitted = piece.resize((nw, nh), Image.Resampling.NEAREST)
    x = target[0] + (tw - nw) // 2
    y = target[1] + (th - nh) // 2
    out.paste(fitted, (x, y), fitted)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    qa = OUT / "QA"
    qa.mkdir(exist_ok=True)
    rom = bytearray(SRC.read_bytes())
    with SRC.open("rb") as handle:
        hdr = read_header(handle)
    arm9 = bytes(rom[int(hdr["arm9_offset"]) : int(hdr["arm9_offset"]) + int(hdr["arm9_size"])])
    gfx_item, gfx, pal, cel = load_paks(SRC)
    pak = bytearray(gfx.data)
    grouped: dict[int, list[tuple[int, Path, str]]] = {}
    for entry, cell, filename, meaning in SWAPS:
        grouped.setdefault(entry, []).append((cell, LE / filename, meaning))
    for entry, jobs in grouped.items():
        slot = gfx.entries[entry]
        if not slot.is_uncompressed:
            raise ValueError(f"{entry} compressed")
        nclr = parse_nclr(pal.unpacked_data(entry))
        cells = parse_ncer(cel.unpacked_data(entry))
        raw = gfx.unpacked_data(entry)
        canvases = [render_full_cell(parse_ncgr(raw), nclr, cells[i]) for i in range(len(cells))]
        selected = set()
        for cell, path, meaning in jobs:
            donor = Image.open(path)
            before = canvases[cell]
            placed = aspect_fit(donor, before)
            before.save(qa / f"before_e{entry:04d}_c{cell:02d}.png")
            donor.convert("RGBA").save(qa / f"le_e{entry:04d}_c{cell:02d}.png")
            placed.save(qa / f"en_e{entry:04d}_c{cell:02d}.png")
            canvases[cell] = placed
            selected.add(cell)
            print(f"{entry}:{cell:02d} {meaning} native {before.size} bbox {before.getbbox()} <- {path.name} {donor.size}")
        encoded = encode_selected_cells(raw, cells, canvases, nclr, selected)
        if len(encoded) != slot.stored_size:
            raise ValueError(f"{entry} {len(encoded)} != {slot.stored_size}")
        pak[slot.offset : slot.offset + slot.stored_size] = encoded
        patched = parse_ncgr(encoded)
        for cell, _path, _meaning in jobs:
            render_full_cell(patched, nclr, cells[cell]).save(qa / f"rom_e{entry:04d}_c{cell:02d}.png")
    rom[gfx_item.offset : gfx_item.offset + gfx_item.size] = pak
    if arm9 != bytes(rom[int(hdr["arm9_offset"]) : int(hdr["arm9_offset"]) + int(hdr["arm9_size"])]):
        raise AssertionError("ARM9 changed")
    dest = OUT / "Game" / "Digimon Story Xros Evolution - COMPLETE US v120 LE DONORS.nds"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(rom)
    DOWNLOADS.write_bytes(rom)
    print("wrote", dest)
    print("wrote", DOWNLOADS)


if __name__ == "__main__":
    main()
