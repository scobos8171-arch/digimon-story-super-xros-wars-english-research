"""Render the real animation states used by the Xros hex command menu.

This is intentionally resource-level: it follows NANR state -> NCER cell ->
NCGR tiles, rather than guessing from message text or a cell contact sheet.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from rom_importer.archives import XrosPak
from rom_importer.nitro import parse_nanr, parse_ncer, parse_ncgr, parse_nclr, render_cell_canvas
from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.xros_pak import find_nitro_file, read_nitro_file

ARCHIVES = ("SPR_NCGR.PAK", "SPR_NCLR.PAK", "SPR_NCER.PAK", "SPR_NANR.PAK")


def crop(image: Image.Image) -> Image.Image:
    box = image.getbbox()
    return image.crop(box) if box else image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    with args.rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        raw = {
            name: XrosPak(read_nitro_file(handle, find_nitro_file(files, name))).unpack(198)
            for name in ARCHIVES
        }
    ncgr = parse_ncgr(raw["SPR_NCGR.PAK"])
    palette = parse_nclr(raw["SPR_NCLR.PAK"])
    cells = parse_ncer(raw["SPR_NCER.PAK"])
    sequences = parse_nanr(raw["SPR_NANR.PAK"])
    args.out.mkdir(parents=True, exist_ok=True)
    lines = ["# Actual hex-menu states from sprite resource 198", ""]
    for index, sequence in enumerate(sequences):
        cell_index = sequence.frames[0].cell_index
        image = crop(render_cell_canvas(ncgr, palette, cells[cell_index]))
        name = f"state_{index:02d}_cell_{cell_index:02d}.png"
        image.save(args.out / name)
        lines.append(f"{index}\tcell {cell_index}\t{image.width}x{image.height}\t{name}")
    (args.out / "STATE_MAP.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
