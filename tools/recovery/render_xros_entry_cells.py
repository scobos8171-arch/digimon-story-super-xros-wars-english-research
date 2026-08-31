#!/usr/bin/env python3
"""Render every cell from selected Xros sprite entries for close review."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
EDITOR = ROOT / "work" / "DigimonNDSRomEditor-master"
sys.path.insert(0, str(EDITOR))

from rom_research.xros_sprite import XrosSpriteSet, parse_ncer  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("entries", nargs="+", type=int)
    parser.add_argument("--scale", type=int, default=4)
    args = parser.parse_args()

    sprites = XrosSpriteSet.from_rom(args.rom)
    args.output.mkdir(parents=True, exist_ok=True)
    for entry in args.entries:
        cells = parse_ncer(sprites.raw_entry("cells", entry))
        rendered = [sprites.render(entry, cell) for cell in range(len(cells))]
        entry_dir = args.output / f"entry_{entry:04d}"
        entry_dir.mkdir(parents=True, exist_ok=True)
        for cell, image in enumerate(rendered):
            image.save(entry_dir / f"cell_{cell:02d}.png")
        cell_width = max(image.width for image in rendered) * args.scale + 24
        cell_height = max(image.height for image in rendered) * args.scale + 30
        sheet = Image.new(
            "RGBA",
            (cell_width * len(rendered), cell_height),
            (18, 26, 40, 255),
        )
        draw = ImageDraw.Draw(sheet)
        for cell, image in enumerate(rendered):
            scaled = image.resize(
                (image.width * args.scale, image.height * args.scale),
                Image.Resampling.NEAREST,
            )
            x = cell * cell_width + (cell_width - scaled.width) // 2
            y = 24 + (cell_height - 24 - scaled.height) // 2
            sheet.alpha_composite(scaled, (x, y))
            draw.text((cell * cell_width + 4, 4), f"{entry}:{cell} {image.width}x{image.height}", fill="white")
        sheet.save(args.output / f"{entry:04d}_all_cells.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
