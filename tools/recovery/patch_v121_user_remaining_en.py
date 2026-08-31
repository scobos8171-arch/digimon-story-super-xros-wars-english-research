"""v121: inject user-painted remaining English sprites onto v120.

Source folder: C:\\Users\\YOUR_NAME\\Downloads\\Xros remaining sprites EN
In-place uncompressed SPR members. ARM9 / NCER / NCLR unchanged.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
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
    / "Xros Evolution Complete US v120 LE DONORS"
    / "Game"
    / "Digimon Story Xros Evolution - COMPLETE US v120 LE DONORS.nds"
)
OUT = ROOT / "outputs" / "Xros Evolution Complete US v121 USER REMAINING EN"
DOWNLOADS = Path(r"C:\Users\YOUR_NAME\Downloads\Digimon Story Xros Evolution - COMPLETE US v121 USER REMAINING EN.nds")
ASSETS = Path(r"C:\Users\YOUR_NAME\Downloads\Xros remaining sprites EN")
NAME_RE = re.compile(r"cell_(\d+)_(\d+)x(\d+)\.png$", re.I)
ENTRY_RE = re.compile(r"entry_(\d+)$", re.I)
FORBIDDEN = {(198, cell) for cell in range(1, 8)} | {(196, cell) for cell in range(1, 8)}
SAMPLE_QA = {(42, 0), (42, 2), (125, 0), (131, 0), (2002, 0), (2002, 1), (104, 0), (2433, 1), (2024, 0), (220, 0)}


def discover() -> dict[tuple[int, int], Path]:
    found: dict[tuple[int, int], Path] = {}
    for path in ASSETS.rglob("cell_*.png"):
        folder = path.parent.name
        entry_match = ENTRY_RE.match(folder)
        cell_match = NAME_RE.match(path.name)
        if not entry_match or not cell_match:
            continue
        key = (int(entry_match.group(1)), int(cell_match.group(1)))
        if key in FORBIDDEN:
            raise ValueError(f"refusing hex runtime cell {key}")
        found[key] = path
    if not found:
        raise ValueError(f"no cell PNGs under {ASSETS}")
    return found


def place(artist: Image.Image, native: Image.Image) -> Image.Image:
    artist = artist.convert("RGBA")
    if artist.size == native.size:
        return artist
    fitted = Image.new("RGBA", native.size, (0, 0, 0, 0))
    if artist.width <= native.width and artist.height <= native.height:
        x = (native.width - artist.width) // 2
        y = (native.height - artist.height) // 2
        fitted.alpha_composite(artist, (x, y))
        return fitted
    bbox = native.getbbox()
    if bbox is None:
        raise ValueError(f"native empty {native.size} vs artist {artist.size}")
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    piece = artist
    ab = artist.getbbox()
    if ab is not None:
        piece = artist.crop(ab)
    if piece.size != (tw, th):
        piece = piece.resize((tw, th), Image.Resampling.NEAREST)
    fitted.paste(piece, (bbox[0], bbox[1]), piece)
    return fitted


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
    assets = discover()
    grouped: dict[int, dict[int, Path]] = defaultdict(dict)
    for (entry, cell), path in assets.items():
        grouped[entry][cell] = path
    rom = bytearray(SRC.read_bytes())
    gfx_item, gfx, pal, cel = load_paks(SRC)
    pak = bytearray(gfx.data)
    with SRC.open("rb") as handle:
        hdr = read_header(handle)
    arm9 = bytes(rom[int(hdr["arm9_offset"]) : int(hdr["arm9_offset"]) + int(hdr["arm9_size"])])
    applied = 0
    for entry, replacements in sorted(grouped.items()):
        slot = gfx.entries[entry]
        if not slot.is_uncompressed:
            raise ValueError(f"entry {entry} is compressed")
        raw = gfx.unpacked_data(entry)
        nclr = parse_nclr(pal.unpacked_data(entry))
        cells = parse_ncer(cel.unpacked_data(entry))
        canvases = [render_full_cell(parse_ncgr(raw), nclr, cells[i]) for i in range(len(cells))]
        selected = set()
        for cell, path in sorted(replacements.items()):
            if cell >= len(cells):
                raise ValueError(f"{entry} has no cell {cell}")
            artist = Image.open(path)
            canvases[cell] = place(artist, canvases[cell])
            selected.add(cell)
            applied += 1
            if (entry, cell) in SAMPLE_QA:
                canvases[cell].save(qa / f"e{entry:04d}_c{cell:02d}.png")
        encoded = encode_selected_cells(raw, cells, canvases, nclr, selected)
        if len(encoded) != slot.stored_size:
            raise ValueError(f"{entry} encoded {len(encoded)} != {slot.stored_size}")
        pak[slot.offset : slot.offset + slot.stored_size] = encoded
        print(f"entry {entry:4d} cells {sorted(selected)}")
    if bytes(pak) == gfx.data:
        raise ValueError("SPR unchanged")
    rom[gfx_item.offset : gfx_item.offset + gfx_item.size] = pak
    if arm9 != bytes(rom[int(hdr["arm9_offset"]) : int(hdr["arm9_offset"]) + int(hdr["arm9_size"])]):
        raise AssertionError("ARM9 changed")
    dest = OUT / "Game" / "Digimon Story Xros Evolution - COMPLETE US v121 USER REMAINING EN.nds"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(rom)
    DOWNLOADS.write_bytes(rom)
    print("applied", applied, "entries", len(grouped))
    print("wrote", dest)
    print("wrote", DOWNLOADS)


if __name__ == "__main__":
    main()
