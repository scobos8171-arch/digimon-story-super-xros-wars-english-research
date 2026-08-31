#!/usr/bin/env python3
"""Render a raw Xros BG_NCGR record as an indexed tile atlas.

This intentionally does *not* guess a palette or screen layout.  It is a
forensic visualizer: a tile atlas lets us compare the exact graphics record
identified from live VRAM with a screenshot before any ROM bytes are changed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))

from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, find_nitro_file, read_nitro_file  # noqa: E402
from rom_research.xros_sprite import parse_ncgr  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("entry", type=int)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--columns", type=int, default=32)
    parser.add_argument("--scale", type=int, default=2)
    args = parser.parse_args()

    with args.rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        archive = XrosPak.from_bytes(
            read_nitro_file(handle, find_nitro_file(files, "BG_NCGR.PAK"))
        )
        raw = archive.unpacked_data(args.entry)

    ncgr = parse_ncgr(raw)
    if ncgr.bpp != 4:
        raise ValueError(f"Expected 4bpp BG graphics, got {ncgr.bpp}bpp")
    columns = max(1, args.columns)
    rows = (len(ncgr.tiles) + columns - 1) // columns
    atlas = Image.new("RGBA", (columns * 8, rows * 8), (0, 0, 0, 255))
    for index, tile in enumerate(ncgr.tiles):
        tile_image = Image.new("RGBA", (8, 8))
        # This grayscale is deliberate. Tile shapes are the evidence; a wrong
        # NCLR must not make a record appear to match a screenshot.
        tile_image.putdata([(value * 17, value * 17, value * 17, 255) for value in tile])
        atlas.alpha_composite(tile_image, ((index % columns) * 8, (index // columns) * 8))

    rendered = atlas.resize((atlas.width * args.scale, atlas.height * args.scale), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(rendered)
    for column in range(0, columns + 1, 8):
        draw.line((column * 8 * args.scale, 0, column * 8 * args.scale, rendered.height), fill=(255, 0, 255, 160))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    rendered.save(args.out)
    print(f"Rendered BG_NCGR entry {args.entry}: {len(ncgr.tiles)} tiles -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
