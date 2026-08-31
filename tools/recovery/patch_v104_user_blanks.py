"""v104: user blanks + English in the well + nearest resize to native.

Do not flatten or inpaint the plate. ARM9 unchanged (v102 base).
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
from paint_blank_ui_buttons import _is_button_pixel  # noqa: E402
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, find_nitro_file, read_nitro_file  # noqa: E402

JP = ROOT / "work" / "roms" / "xros_blue.nds"
SRC = ROOT / "outputs" / "Xros Evolution Complete US v102 INPLACE CLEAN BUTTONS" / "Game" / "Digimon Story Xros Evolution - COMPLETE US v102 INPLACE CLEAN BUTTONS.nds"
OUT = ROOT / "outputs" / "Xros Evolution Complete US v104 USER BLANKS"
BLANKS = Path(r"C:\Users\YOUR_NAME\Downloads\Buttons with no letters we need to localize")

LABELS_1987 = {
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
}
LABELS_147 = {
    1: ("CONFIRM", "left"),
    2: ("BACK", "left"),
    3: ("BACK", "left"),
}


def extract_slots(sheet: Image.Image, count: int) -> list[Image.Image]:
    sheet = sheet.convert("RGBA")
    cell_w = sheet.width // count
    has_alpha = sheet.getchannel("A").getextrema()[0] == 0
    top = 0 if has_alpha else 24
    slots = []
    for i in range(count):
        crop = sheet.crop((i * cell_w, top, (i + 1) * cell_w, sheet.height))
        px = crop.load()
        bbox = None
        for y in range(crop.height):
            for x in range(crop.width):
                r, g, b, a = px[x, y]
                if not _is_button_pixel(r, g, b, a):
                    continue
                if bbox is None:
                    bbox = [x, y, x + 1, y + 1]
                else:
                    bbox[0] = min(bbox[0], x)
                    bbox[1] = min(bbox[1], y)
                    bbox[2] = max(bbox[2], x + 1)
                    bbox[3] = max(bbox[3], y + 1)
        if bbox is None:
            slots.append(Image.new("RGBA", (1, 1), (0, 0, 0, 0)))
            continue
        piece = crop.crop(tuple(bbox)).convert("RGBA")
        # Punch studio/black background to real transparency.
        p = piece.load()
        for y in range(piece.height):
            for x in range(piece.width):
                r, g, b, a = p[x, y]
                if r + g + b < 50:
                    p[x, y] = (0, 0, 0, 0)
        slots.append(piece)
    return slots


def draw_centered(plate: Image.Image, text: str, icon_side: str) -> Image.Image:
    out = plate.copy()
    w, h = out.size
    if icon_side == "left":
        well = (17, 3, w - 2, h - 2)
    else:
        well = (3, 3, w - 18, h - 2)
    size = (max(1, well[2] - well[0]), max(1, well[3] - well[1]))
    mask = make_ds_5x7_mask(text, size)
    white = Image.new("RGBA", size, (255, 255, 255, 255))
    edge = Image.new("RGBA", size, (20, 32, 64, 255))
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        out.paste(edge, (well[0] + dx, well[1] + dy), mask)
    out.paste(white, (well[0], well[1]), mask)
    return out


def place_on_canvas(canvas: Image.Image, plate: Image.Image) -> Image.Image:
    out = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    bbox = canvas.getbbox() or (0, 0, plate.width, plate.height)
    x0, y0, x1, y1 = bbox
    target = (x1 - x0, y1 - y0)
    fitted = plate if plate.size == target else plate.resize(target, Image.Resampling.NEAREST)
    out.paste(fitted, (x0, y0), fitted)
    return out


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
    rom = bytearray(SRC.read_bytes())
    jp_item, jp_gfx, jp_pal, jp_cel = load_paks(JP)
    us_item, us_gfx, us_pal, us_cel = load_paks(SRC)
    pak = bytearray(us_gfx.data)
    with SRC.open("rb") as handle:
        hdr = read_header(handle)
    arm9 = bytes(rom[int(hdr["arm9_offset"]): int(hdr["arm9_offset"]) + int(hdr["arm9_size"])])

    jobs = [
        (1987, LABELS_1987, BLANKS / "original_entry1987_reference_sheet.png", 12),
        (147, LABELS_147, BLANKS / "original_entry147_reference_sheet.png", 4),
    ]
    for entry, labels, sheet_path, count in jobs:
        ncgr = parse_ncgr(jp_gfx.unpacked_data(entry))
        nclr = parse_nclr(jp_pal.unpacked_data(entry))
        cells = parse_ncer(jp_cel.unpacked_data(entry))
        canvases = [render_full_cell(ncgr, nclr, cells[i]) for i in range(len(cells))]
        plates = extract_slots(Image.open(sheet_path), count)
        for cell, (text, side) in labels.items():
            native_bb = canvases[cell].getbbox()
            nw, nh = native_bb[2] - native_bb[0], native_bb[3] - native_bb[1]
            plate = plates[cell].resize((nw, nh), Image.Resampling.NEAREST)
            lettered = draw_centered(plate, text, side)
            canvases[cell] = place_on_canvas(canvases[cell], lettered)
            canvases[cell].save(qa / f"e{entry:04d}_c{cell:02d}.png")
            print(entry, cell, "sheet", plates[cell].size, "native", (nw, nh), text)
        painted = encode_selected_cells(jp_gfx.unpacked_data(entry), cells, canvases, nclr, set(labels))
        slot = us_gfx.entries[entry]
        if len(painted) != slot.stored_size:
            raise ValueError(f"{entry} {len(painted)} != {slot.stored_size}")
        pak[slot.offset:slot.offset + slot.stored_size] = painted

    rom[us_item.offset:us_item.offset + us_item.size] = pak
    if arm9 != bytes(rom[int(hdr["arm9_offset"]): int(hdr["arm9_offset"]) + int(hdr["arm9_size"])]):
        raise AssertionError("ARM9 changed")
    dest = OUT / "Game" / "Digimon Story Xros Evolution - COMPLETE US v104 USER BLANKS.nds"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(rom)
    Path(r"C:\Users\YOUR_NAME\Downloads\Digimon Story Xros Evolution - COMPLETE US v104 USER BLANKS.nds").write_bytes(rom)
    print("wrote", dest)


if __name__ == "__main__":
    main()
