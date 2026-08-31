#!/usr/bin/env python3
"""Render likely text-bearing Xros sprite cells for localization review.

This is a read-only audit helper.  It filters the sprite archive down to
short/wide cells (the shape used by labels, buttons, and banners), then writes
numbered contact sheets plus a JSON manifest.  The ROM is never modified.
"""

from __future__ import annotations

import argparse
import json
import math
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
    parser.add_argument("--minimum-width", type=int, default=32)
    parser.add_argument("--maximum-height", type=int, default=64)
    parser.add_argument("--minimum-aspect", type=float, default=1.4)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--rows", type=int, default=24)
    parser.add_argument("--cell-width", type=int, default=240)
    parser.add_argument("--cell-height", type=int, default=90)
    args = parser.parse_args()

    sprites = XrosSpriteSet.from_rom(args.rom)
    candidates: list[dict[str, object]] = []
    for entry in range(sprites.entry_count):
        try:
            cells = parse_ncer(sprites.raw_entry("cells", entry))
        except Exception:
            continue
        for cell in range(len(cells)):
            try:
                image = sprites.render(entry, cell)
            except Exception:
                continue
            width, height = image.size
            if (
                width >= args.minimum_width
                and height <= args.maximum_height
                and width / max(1, height) >= args.minimum_aspect
            ):
                candidates.append(
                    {
                        "entry": entry,
                        "cell": cell,
                        "width": width,
                        "height": height,
                        "image": image,
                    }
                )

    args.output.mkdir(parents=True, exist_ok=True)
    per_page = args.columns * args.rows
    pages = math.ceil(len(candidates) / per_page)
    manifest: list[dict[str, int]] = []
    for page in range(pages):
        subset = candidates[page * per_page : (page + 1) * per_page]
        sheet = Image.new(
            "RGBA",
            (args.columns * args.cell_width, args.rows * args.cell_height),
            (18, 26, 40, 255),
        )
        draw = ImageDraw.Draw(sheet)
        for offset, item in enumerate(subset):
            x = (offset % args.columns) * args.cell_width
            y = (offset // args.columns) * args.cell_height
            image = item["image"].copy()
            image.thumbnail(
                (args.cell_width - 8, args.cell_height - 26), Image.Resampling.NEAREST
            )
            sheet.alpha_composite(
                image,
                (x + (args.cell_width - image.width) // 2, y + 22),
            )
            draw.text(
                (x + 3, y + 3),
                f"{item['entry']}:{item['cell']}  {item['width']}x{item['height']}",
                fill="white",
            )
            manifest.append(
                {
                    "entry": int(item["entry"]),
                    "cell": int(item["cell"]),
                    "width": int(item["width"]),
                    "height": int(item["height"]),
                    "page": page,
                    "slot": offset,
                }
            )
        sheet.save(args.output / f"text_candidates_{page:02d}.png")

    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"Rendered {len(candidates)} candidate cells across {pages} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
