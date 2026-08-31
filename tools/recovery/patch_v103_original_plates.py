"""v103: put English on original-looking plates.

1987/147 use the user's blank sheets (gradient/icons intact).
110/194/2218 inpaint Japanese glyphs instead of flattening the well.
ARM9 is copied unchanged from v102.
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
from paint_blank_ui_buttons import split_sheet, _is_button_pixel  # noqa: E402
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, find_nitro_file, read_nitro_file  # noqa: E402

JP = ROOT / "work" / "roms" / "xros_blue.nds"
SRC = ROOT / "outputs" / "Xros Evolution Complete US v102 INPLACE CLEAN BUTTONS" / "Game" / "Digimon Story Xros Evolution - COMPLETE US v102 INPLACE CLEAN BUTTONS.nds"
OUT = ROOT / "outputs" / "Xros Evolution Complete US v103 ORIGINAL PLATES"
BLANKS = Path(r"C:\Users\YOUR_NAME\Downloads\Buttons with no letters we need to localize")
SCALE = 6

SPECS_BLANK = {
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
}
SPECS_INPAINT = {
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


def split_exact(path: Path, count: int, sizes: list[tuple[int, int]]) -> list[Image.Image]:
    sheet = Image.open(path).convert("RGBA")
    cell_w = sheet.width // count
    out = []
    for i, (nw, nh) in enumerate(sizes):
        crop = sheet.crop((i * cell_w, 26, (i + 1) * cell_w, sheet.height))
        bbox = None
        px = crop.load()
        for y in range(crop.height):
            for x in range(crop.width):
                if not _is_button_pixel(*px[x, y]):
                    continue
                if bbox is None:
                    bbox = [x, y, x + 1, y + 1]
                else:
                    bbox[0] = min(bbox[0], x)
                    bbox[1] = min(bbox[1], y)
                    bbox[2] = max(bbox[2], x + 1)
                    bbox[3] = max(bbox[3], y + 1)
        if bbox is None:
            out.append(Image.new("RGBA", (nw, nh), (0, 0, 0, 0)))
            continue
        button = crop.crop(tuple(bbox))
        # Native size, nearest-neighbor so the 6x sheet becomes exact DS pixels.
        out.append(button.resize((nw, nh), Image.Resampling.NEAREST))
    return out


def apply_blank(jp_cell: Image.Image, blank: Image.Image) -> Image.Image:
    """Keep JP alpha/layout; copy blank RGB into the visible button."""
    out = jp_cell.copy()
    bbox = jp_cell.getbbox()
    if bbox is None:
        return out
    x0, y0, x1, y1 = bbox
    target = (x1 - x0, y1 - y0)
    plate = blank.convert("RGBA")
    if plate.size != target:
        plate = plate.resize(target, Image.Resampling.NEAREST)
    src = plate.load()
    dst = out.load()
    for y in range(plate.height):
        for x in range(plate.width):
            r, g, b, a = src[x, y]
            jr, jg, jb, ja = dst[x0 + x, y0 + y]
            if ja > 0:
                dst[x0 + x, y0 + y] = (r, g, b, ja)
    return out


def inpaint_letters(cell: Image.Image, icon_side: str) -> Image.Image:
    out = cell.copy()
    px = out.load()
    w, h = out.size
    bbox = cell.getbbox() or (0, 0, w, h)
    if icon_side == "left":
        icon = (bbox[0], bbox[1], bbox[0] + 17, bbox[3])
    else:
        icon = (bbox[2] - 17, bbox[1], bbox[2], bbox[3])
    glyph = [[False] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 200:
                continue
            if icon[0] <= x < icon[2] and icon[1] <= y < icon[3]:
                continue
            if x <= bbox[0] + 2 or x >= bbox[2] - 2 or y <= bbox[1] + 2 or y >= bbox[3] - 2:
                continue
            if r > 180 and g > 180 and b > 180:
                glyph[y][x] = True
            elif r > 160 and abs(r - g) < 40 and b > 140 and (r + g + b) > 430:
                glyph[y][x] = True
    for y in range(h):
        for x in range(w):
            if not glyph[y][x]:
                continue
            left = x - 1
            while left >= 0 and glyph[y][left]:
                left -= 1
            right = x + 1
            while right < w and glyph[y][right]:
                right += 1
            if left >= 0 and right < w and px[left, y][3] > 200 and px[right, y][3] > 200:
                t = (x - left) / max(1, right - left)
                lr, lg, lb, _ = px[left, y]
                rr, rg, rb, _ = px[right, y]
                a = px[x, y][3]
                px[x, y] = (
                    int(lr + (rr - lr) * t),
                    int(lg + (rg - lg) * t),
                    int(lb + (rb - lb) * t),
                    a,
                )
            elif left >= 0 and px[left, y][3] > 200:
                r, g, b, _ = px[left, y]
                px[x, y] = (r, g, b, px[x, y][3])
            elif right < w and px[right, y][3] > 200:
                r, g, b, _ = px[right, y]
                px[x, y] = (r, g, b, px[x, y][3])
    return out


def draw_english(cell: Image.Image, text: str, icon_side: str) -> Image.Image:
    out = cell.copy()
    bbox = cell.getbbox() or (0, 0, cell.width, cell.height)
    if icon_side == "left":
        well = (bbox[0] + 18, bbox[1] + 4, bbox[2] - 3, bbox[3] - 3)
    else:
        well = (bbox[0] + 4, bbox[1] + 4, bbox[2] - 18, bbox[3] - 3)
    size = (max(1, well[2] - well[0]), max(1, well[3] - well[1]))
    mask = make_ds_5x7_mask(text, size)
    white = Image.new("RGBA", size, (255, 255, 255, 255))
    black = Image.new("RGBA", size, (16, 24, 48, 255))
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        out.paste(black, (well[0] + dx, well[1] + dy), mask)
    out.paste(white, (well[0], well[1]), mask)
    return out


def load_paks(path: Path):
    with path.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        gfx_item = find_nitro_file(files, GRAPHICS_PATH)
        gfx = XrosPak.from_bytes(read_nitro_file(handle, gfx_item))
        pal = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cel = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))
    return gfx_item, gfx, pal, cel


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
    arm9_slice = bytes(rom[int(hdr["arm9_offset"]): int(hdr["arm9_offset"]) + int(hdr["arm9_size"])])

    def jp_canvases(entry: int):
        ncgr = parse_ncgr(jp_gfx.unpacked_data(entry))
        nclr = parse_nclr(jp_pal.unpacked_data(entry))
        cells = parse_ncer(jp_cel.unpacked_data(entry))
        return cells, nclr, [render_full_cell(ncgr, nclr, cells[i]) for i in range(len(cells))]

    # 1987 + 147 from artist blanks
    blanks_1987_sizes = []
    cells1987, nclr1987, canv1987 = jp_canvases(1987)
    for im in canv1987:
        bb = im.getbbox() or (0, 0, im.width, im.height)
        blanks_1987_sizes.append((bb[2] - bb[0], bb[3] - bb[1]))
    plates_1987 = split_exact(BLANKS / "original_entry1987_reference_sheet.png", 12, blanks_1987_sizes)
    print("1987 plates", [p.size for p in plates_1987], "native", blanks_1987_sizes)

    cells147, nclr147, canv147 = jp_canvases(147)
    sizes147 = []
    for im in canv147:
        bb = im.getbbox() or (0, 0, im.width, im.height)
        sizes147.append((max(1, bb[2] - bb[0]), max(1, bb[3] - bb[1])))
    plates_147 = split_exact(BLANKS / "original_entry147_reference_sheet.png", 4, sizes147)
    print("147 plates", [p.size for p in plates_147], "native", sizes147)

    jobs = [
        (1987, SPECS_BLANK[1987], canv1987, plates_1987, cells1987, nclr1987, True),
        (147, SPECS_BLANK[147], canv147, plates_147, cells147, nclr147, True),
    ]
    for entry, labels in SPECS_INPAINT.items():
        cells, nclr, canv = jp_canvases(entry)
        jobs.append((entry, labels, canv, None, cells, nclr, False))

    for entry, labels, canvases, plates, cells, nclr, use_blank in jobs:
        for cell, (text, side) in labels.items():
            if use_blank:
                base = apply_blank(canvases[cell], plates[cell])
            else:
                base = inpaint_letters(canvases[cell], side)
            canvases[cell] = draw_english(base, text, side)
            canvases[cell].save(qa / f"e{entry:04d}_c{cell:02d}.png")
        painted = encode_selected_cells(jp_gfx.unpacked_data(entry), cells, canvases, nclr, set(labels))
        slot = us_gfx.entries[entry]
        if len(painted) != slot.stored_size:
            raise ValueError(f"{entry}: {len(painted)} != {slot.stored_size}")
        if not slot.is_uncompressed:
            raise ValueError(f"{entry} compressed")
        pak[slot.offset:slot.offset + slot.stored_size] = painted
        print("wrote entry", entry)

    rom[us_item.offset:us_item.offset + us_item.size] = pak
    arm9_after = bytes(rom[int(hdr["arm9_offset"]): int(hdr["arm9_offset"]) + int(hdr["arm9_size"])])
    if arm9_slice != arm9_after:
        raise AssertionError("ARM9 changed")
    dest = OUT / "Game" / "Digimon Story Xros Evolution - COMPLETE US v103 ORIGINAL PLATES.nds"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(rom)
    Path(r"C:\Users\YOUR_NAME\Downloads\Digimon Story Xros Evolution - COMPLETE US v103 ORIGINAL PLATES.nds").write_bytes(rom)
    print("wrote", dest)


if __name__ == "__main__":
    main()
