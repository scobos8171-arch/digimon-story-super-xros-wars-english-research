"""v115: inject artist EN buttons onto v114 in-place.

Sources:
  C:\\Users\\YOUR_NAME\\Downloads\\individual_small_and_result_en
  C:\\Users\\YOUR_NAME\\Downloads\\individual_battle_menu_en

Each PNG is already native OAM canvas size. Encode only the named cells.
SPR members stay uncompressed and same stored_size. ARM9 / NCER / NCLR
untouched. Hex 198 cells 1-7 are not in the asset set and are not painted.
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
    GRAPHICS_PATH,
    PALETTE_PATH,
    CELLS_PATH,
    encode_selected_cells,
    parse_ncgr,
    parse_nclr,
    parse_ncer,
    render_full_cell,
)
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, find_nitro_file, read_nitro_file  # noqa: E402

SRC = (
    ROOT
    / "outputs"
    / "Xros Evolution Complete US v114 COMPLETE BUTTON PASS"
    / "Game"
    / "Digimon Story Xros Evolution - COMPLETE US v114 COMPLETE BUTTON PASS.nds"
)
OUT = ROOT / "outputs" / "Xros Evolution Complete US v115 ARTIST EN BUTTONS"
ASSET_DIRS = [
    Path(r"C:\Users\YOUR_NAME\Downloads\individual_small_and_result_en"),
    Path(r"C:\Users\YOUR_NAME\Downloads\individual_battle_menu_en"),
]
DOWNLOADS = Path(r"C:\Users\YOUR_NAME\Downloads\Digimon Story Xros Evolution - COMPLETE US v115 ARTIST EN BUTTONS.nds")
NAME_RE = re.compile(r"entry(\d+)_cell(\d+)_\d+x\d+\.png$", re.I)

# Hex menu: never paint cells 1-7 (runtime OBJ labels). Cell 8 BACK is baked.
FORBIDDEN = {(198, cell) for cell in range(1, 8)} | {(196, cell) for cell in range(1, 8)}


def discover() -> dict[tuple[int, int], Path]:
    found: dict[tuple[int, int], Path] = {}
    for folder in ASSET_DIRS:
        for path in sorted(folder.glob("entry*.png")):
            match = NAME_RE.match(path.name)
            if not match:
                continue
            key = (int(match.group(1)), int(match.group(2)))
            if key in FORBIDDEN:
                raise ValueError(f"refusing to paint hex runtime cell {key}: {path}")
            found[key] = path
    if not found:
        raise ValueError("no artist EN button PNGs found")
    return found


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

    for entry, replacements in sorted(grouped.items()):
        slot = gfx.entries[entry]
        if not slot.is_uncompressed:
            raise ValueError(f"entry {entry} is compressed; in-place overwrite is unsafe")
        ncgr_bytes = gfx.unpacked_data(entry)
        nclr = parse_nclr(pal.unpacked_data(entry))
        cells = parse_ncer(cel.unpacked_data(entry))
        canvases = [render_full_cell(parse_ncgr(ncgr_bytes), nclr, cells[i]) for i in range(len(cells))]
        selected: set[int] = set()
        for cell, path in sorted(replacements.items()):
            if cell >= len(cells):
                raise ValueError(f"entry {entry} has no cell {cell}")
            artist = Image.open(path).convert("RGBA")
            native = canvases[cell]
            if artist.size != native.size:
                raise ValueError(
                    f"{path.name}: {artist.size} != native {entry}:{cell} {native.size}"
                )
            before = qa / f"before_e{entry:04d}_c{cell:02d}.png"
            native.save(before)
            artist.save(qa / f"artist_e{entry:04d}_c{cell:02d}.png")
            canvases[cell] = artist
            selected.add(cell)
            print(f"{entry}:{cell:02d} {artist.size} <- {path.name}")
        encoded = encode_selected_cells(ncgr_bytes, cells, canvases, nclr, selected)
        if len(encoded) != slot.stored_size:
            raise ValueError(f"{entry} encoded {len(encoded)} != slot {slot.stored_size}")
        pak[slot.offset : slot.offset + slot.stored_size] = encoded
        patched = parse_ncgr(encoded)
        for cell in sorted(selected):
            roundtrip = render_full_cell(patched, nclr, cells[cell])
            roundtrip.save(qa / f"rom_e{entry:04d}_c{cell:02d}.png")

    if bytes(pak) == gfx.data:
        raise ValueError("SPR_NCGR.PAK unchanged")
    rom[gfx_item.offset : gfx_item.offset + gfx_item.size] = pak
    if arm9 != bytes(rom[int(hdr["arm9_offset"]) : int(hdr["arm9_offset"]) + int(hdr["arm9_size"])]):
        raise AssertionError("ARM9 changed")
    dest = OUT / "Game" / "Digimon Story Xros Evolution - COMPLETE US v115 ARTIST EN BUTTONS.nds"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(rom)
    DOWNLOADS.write_bytes(rom)
    print("wrote", dest)
    print("wrote", DOWNLOADS)
    print("cells", len(assets), "entries", sorted(grouped))


if __name__ == "__main__":
    main()
