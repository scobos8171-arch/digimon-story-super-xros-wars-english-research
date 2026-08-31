#!/usr/bin/env python3
"""Render red-dominant Xros sprite cells to locate menu/button assets."""

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


def red_fraction(image: Image.Image) -> float:
    opaque = [pixel for pixel in image.getdata() if pixel[3] >= 128]
    if not opaque:
        return 0.0
    red = sum(
        1
        for r, g, b, _a in opaque
        if r >= 105 and r >= g * 1.35 and r >= b * 1.15
    )
    return red / len(opaque)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--minimum-red", type=float, default=0.16)
    parser.add_argument("--minimum-width", type=int, default=32)
    parser.add_argument("--minimum-height", type=int, default=20)
    parser.add_argument("--maximum-width", type=int, default=200)
    parser.add_argument("--maximum-height", type=int, default=110)
    args = parser.parse_args()

    sprites = XrosSpriteSet.from_rom(args.rom)
    matches: list[dict[str, object]] = []
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
            if not (
                args.minimum_width <= width <= args.maximum_width
                and args.minimum_height <= height <= args.maximum_height
            ):
                continue
            fraction = red_fraction(image)
            if fraction >= args.minimum_red:
                matches.append(
                    {
                        "entry": entry,
                        "cell": cell,
                        "width": width,
                        "height": height,
                        "red_fraction": fraction,
                        "image": image,
                    }
                )

    columns, rows_per_page = 5, 20
    cell_width, cell_height = 220, 125
    per_page = columns * rows_per_page
    args.output.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    for page in range(math.ceil(len(matches) / per_page)):
        subset = matches[page * per_page : (page + 1) * per_page]
        sheet = Image.new(
            "RGBA",
            (columns * cell_width, rows_per_page * cell_height),
            (18, 26, 40, 255),
        )
        draw = ImageDraw.Draw(sheet)
        for offset, item in enumerate(subset):
            x = offset % columns * cell_width
            y = offset // columns * cell_height
            image = item["image"].copy()
            image.thumbnail((cell_width - 8, cell_height - 28), Image.Resampling.NEAREST)
            sheet.alpha_composite(image, (x + (cell_width - image.width) // 2, y + 24))
            draw.text(
                (x + 3, y + 3),
                f"{item['entry']}:{item['cell']} {item['width']}x{item['height']} red={item['red_fraction']:.2f}",
                fill="white",
            )
            manifest.append({key: value for key, value in item.items() if key != "image"})
        sheet.save(args.output / f"red_ui_candidates_{page:02d}.png")

    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"Rendered {len(matches)} candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
