#!/usr/bin/env python3
"""Render a searchable contact sheet of Xros UI sprite entries.

This is a review tool only: it never writes to a ROM.  Use its entry IDs as
the evidence for a subsequent conservative, data-only UI patch.
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
from rom_research.xros_sprite import XrosSpriteSet  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--first", type=int, default=1800)
    parser.add_argument("--last", type=int, default=2300)
    parser.add_argument("--columns", type=int, default=8)
    parser.add_argument("--cell-width", type=int, default=160)
    parser.add_argument("--cell-height", type=int, default=120)
    args = parser.parse_args()

    sprites = XrosSpriteSet.from_rom(args.rom)
    first = max(0, args.first)
    last = min(sprites.entry_count - 1, args.last)
    width, height = args.cell_width, args.cell_height
    rows = math.ceil((last - first + 1) / args.columns)
    sheet = Image.new("RGB", (args.columns * width, rows * height), "#121a28")
    draw = ImageDraw.Draw(sheet)
    manifest: list[dict[str, object]] = []
    for offset, index in enumerate(range(first, last + 1)):
        x, y = offset % args.columns * width, offset // args.columns * height
        try:
            image = sprites.render(index)
            full_size = image.size
            image.thumbnail((width - 8, height - 28), Image.Resampling.NEAREST)
            sheet.paste(image, (x + (width - image.width) // 2, y + 22), image)
            manifest.append({"index": index, "rendered": True, "size": full_size})
        except Exception as exc:  # individual malformed entries are evidence too
            draw.text((x + 4, y + 26), "unrenderable", fill="#ff8b8b")
            manifest.append({"index": index, "rendered": False, "error": str(exc)})
        draw.text((x + 4, y + 4), f"#{index}", fill="#ffffff")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output)
    args.output.with_suffix(".json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Rendered {first}-{last}: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
