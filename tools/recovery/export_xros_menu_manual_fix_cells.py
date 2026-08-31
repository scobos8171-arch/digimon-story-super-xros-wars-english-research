#!/usr/bin/env python3
"""Export native-size JP and localized UI cells for manual pixel-art repair."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))

from rom_research.xros_sprite import XrosSpriteSet  # noqa: E402


CELLS = ((38, 0), (38, 1), (38, 2), (38, 3), (126, 0))


def label(entry: int, cell: int) -> str:
    return "title_menu" if entry == 38 else "status_pill"


def make_sheet(records: list[tuple[str, Image.Image]], output: Path) -> None:
    margin, gap, title_h = 12, 14, 18
    width = max(image.width for _, image in records)
    height = sum(title_h + image.height for _, image in records) + gap * (len(records) - 1)
    sheet = Image.new("RGBA", (width + margin * 2, height + margin * 2), (24, 31, 44, 255))
    draw = ImageDraw.Draw(sheet)
    y = margin
    for name, image in records:
        draw.text((margin, y), f"{name} — {image.width}x{image.height}", fill=(255, 255, 255, 255))
        y += title_h
        sheet.alpha_composite(image, (margin + (width - image.width) // 2, y))
        y += image.height + gap
    sheet.save(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clean_jp", type=Path)
    parser.add_argument("localized", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    clean = XrosSpriteSet.from_rom(args.clean_jp)
    localized = XrosSpriteSet.from_rom(args.localized)
    args.output.mkdir(parents=True, exist_ok=True)
    jp_records: list[tuple[str, Image.Image]] = []
    current_records: list[tuple[str, Image.Image]] = []
    for entry, cell in CELLS:
        name = f"entry_{entry:04d}_cell_{cell:02d}_{label(entry, cell)}"
        jp = clean.render(entry, cell)
        current = localized.render(entry, cell)
        jp.save(args.output / f"{name}_JP_ORIGINAL_{jp.width}x{jp.height}.png")
        current.save(args.output / f"{name}_CURRENT_DEFECTIVE_{current.width}x{current.height}.png")
        jp_records.append((f"{name} / JP original", jp))
        current_records.append((f"{name} / current defective", current))
    make_sheet(jp_records, args.output / "JP_ORIGINALS_CONTACT_SHEET.png")
    make_sheet(current_records, args.output / "CURRENT_DEFECTIVE_CONTACT_SHEET.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
