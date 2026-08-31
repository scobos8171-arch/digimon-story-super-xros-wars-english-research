"""v118: battle-ring captions — capital ORDERS, one shared plate gray.

Starts from v117 (DigiXros wording). Only SPR 1971 cells 21-34. ARM9 untouched.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))
sys.path.insert(0, str(ROOT / "tools" / "recovery"))
from build_xros_custom_ui_rom import (  # noqa: E402
    CELLS_PATH,
    COMPACT_3X5,
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

JP = ROOT / "work" / "roms" / "xros_blue.nds"
SRC = (
    ROOT
    / "outputs"
    / "Xros Evolution Complete US v117 DIGIXROS WORDING"
    / "Game"
    / "Digimon Story Xros Evolution - COMPLETE US v117 DIGIXROS WORDING.nds"
)
OUT = ROOT / "outputs" / "Xros Evolution Complete US v118 RING CAPTIONS GRAY"
DOWNLOADS = Path(r"C:\Users\YOUR_NAME\Downloads\Digimon Story Xros Evolution - COMPLETE US v118 RING CAPTIONS GRAY.nds")
ENTRY = 1971
FACE = (230, 246, 246, 255)
INK = (24, 32, 48, 255)
LABELS = {
    21: "ORDERS",
    22: "ORDERS",
    23: "SPECIAL",
    24: "SPECIAL",
    25: "DIGIXROS",
    26: "DIGIXROS",
    27: "ITEMS",
    28: "ITEMS",
    29: "TACTICS",
    30: "TACTICS",
    31: "FORMATION",
    32: "FORMATION",
    33: "WAIT",
    34: "WAIT",
}
# Square capital O so ORDERS does not read as oRDERS.
RING_3X5 = dict(COMPACT_3X5)
RING_3X5["O"] = ("111", "101", "101", "101", "111")


def load_paks(path: Path):
    with path.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        item = find_nitro_file(files, GRAPHICS_PATH)
        gfx = XrosPak.from_bytes(read_nitro_file(handle, item))
        pal = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cel = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))
    return item, gfx, pal, cel


def is_arrow(r: int, g: int, b: int, a: int) -> bool:
    return a > 200 and r > 170 and g > 130 and b < 130 and r + g > b * 3


def is_outline(r: int, g: int, b: int, a: int) -> bool:
    return a > 200 and max(r, g, b) < 90


def well_box(canvas: Image.Image, highlighted: bool) -> tuple[int, int, int, int]:
    origin = canvas.getbbox()
    if origin is None:
        raise ValueError("empty caption")
    ox, oy = origin[0], origin[1]
    right = 60 if highlighted else 56
    return ox + 13, oy + 5, ox + right, oy + 17


def fill_well(canvas: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    out = canvas.copy()
    pixels = out.load()
    left, top, right, bottom = box
    for y in range(max(0, top), min(out.height, bottom)):
        for x in range(max(0, left), min(out.width, right)):
            r, g, b, a = pixels[x, y]
            if a < 200 or is_arrow(r, g, b, a) or is_outline(r, g, b, a):
                continue
            pixels[x, y] = FACE
    return out


def make_ring_mask(text: str, size: tuple[int, int]) -> Image.Image:
    text = text.upper()
    glyph_width, gap, scale = 3, 1, 1
    total = max(1, len(text) * glyph_width + max(0, len(text) - 1) * gap)
    output = Image.new("1", size, 0)
    draw = ImageDraw.Draw(output)
    cursor = max(0, (size[0] - total) // 2)
    start_y = max(0, (size[1] - 5) // 2)
    for character in text:
        rows = RING_3X5.get(character, RING_3X5[" "])
        for row, pattern in enumerate(rows):
            for column, bit in enumerate(pattern):
                if bit == "1":
                    x = cursor + column * scale
                    y = start_y + row * scale
                    draw.point((x, y), fill=1)
        cursor += glyph_width + gap
    return output


def draw_label(canvas: Image.Image, box: tuple[int, int, int, int], text: str) -> Image.Image:
    out = canvas.copy()
    well = (box[2] - box[0], box[3] - box[1])
    mask = make_ring_mask(text, well)
    placed = Image.new("1", out.size, 0)
    placed.paste(mask, (box[0], box[1]))
    out.paste(INK, (0, 0), placed)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    qa = OUT / "QA"
    qa.mkdir(exist_ok=True)
    rom = bytearray(SRC.read_bytes())
    with SRC.open("rb") as handle:
        hdr = read_header(handle)
    arm9 = bytes(rom[int(hdr["arm9_offset"]) : int(hdr["arm9_offset"]) + int(hdr["arm9_size"])])
    jp_item, jp_gfx, jp_pal, jp_cel = load_paks(JP)
    us_item, us_gfx, us_pal, us_cel = load_paks(SRC)
    del jp_item
    slot = us_gfx.entries[ENTRY]
    if not slot.is_uncompressed:
        raise ValueError("1971 compressed")
    nclr = parse_nclr(us_pal.unpacked_data(ENTRY))
    cells = parse_ncer(us_cel.unpacked_data(ENTRY))
    jp_nclr = parse_nclr(jp_pal.unpacked_data(ENTRY))
    jp_cells = parse_ncer(jp_cel.unpacked_data(ENTRY))
    jp_ncgr = parse_ncgr(jp_gfx.unpacked_data(ENTRY))
    us_bytes = us_gfx.unpacked_data(ENTRY)
    canvases = [render_full_cell(parse_ncgr(us_bytes), nclr, cells[i]) for i in range(len(cells))]
    selected = set()
    for cell, text in LABELS.items():
        donor = render_full_cell(jp_ncgr, jp_nclr, jp_cells[cell])
        highlighted = cell % 2 == 0
        box = well_box(donor, highlighted)
        painted = draw_label(fill_well(donor, box), box, text)
        donor.save(qa / f"jp_{cell:02d}.png")
        painted.save(qa / f"en_{cell:02d}.png")
        canvases[cell] = painted
        selected.add(cell)
        print(cell, text, box)
    encoded = encode_selected_cells(us_bytes, cells, canvases, nclr, selected)
    if len(encoded) != slot.stored_size:
        raise ValueError(f"size {len(encoded)} != {slot.stored_size}")
    pak = bytearray(us_gfx.data)
    pak[slot.offset : slot.offset + slot.stored_size] = encoded
    rom[us_item.offset : us_item.offset + us_item.size] = pak
    if arm9 != bytes(rom[int(hdr["arm9_offset"]) : int(hdr["arm9_offset"]) + int(hdr["arm9_size"])]):
        raise AssertionError("ARM9 changed")
    patched = parse_ncgr(encoded)
    for cell in selected:
        render_full_cell(patched, nclr, cells[cell]).save(qa / f"rom_{cell:02d}.png")
    dest = OUT / "Game" / "Digimon Story Xros Evolution - COMPLETE US v118 RING CAPTIONS GRAY.nds"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(rom)
    DOWNLOADS.write_bytes(rom)
    print("wrote", dest)
    print("wrote", DOWNLOADS)


if __name__ == "__main__":
    main()
