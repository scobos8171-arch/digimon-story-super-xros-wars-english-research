#!/usr/bin/env python3
"""Fast visual audit of the low-numbered Xros UI sprite entries.

Produces separate sheets for entries which are unchanged from the clean JP ROM
and entries already altered by the current localization build.  This avoids
claiming that every unchanged sprite is untranslated while still making the
actual likely omissions reviewable at a glance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))

from rom_research.xros_sprite import XrosSpriteSet, parse_ncer  # noqa: E402


def is_label_like(width: int, height: int) -> bool:
    return width >= 24 and height <= 72 and width / max(height, 1) >= 1.25


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clean_jp", type=Path)
    parser.add_argument("localized", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--first-entry", type=int, default=0)
    parser.add_argument("--last-entry", type=int, default=230)
    args = parser.parse_args()

    clean = XrosSpriteSet.from_rom(args.clean_jp)
    localized = XrosSpriteSet.from_rom(args.localized)
    groups: dict[str, list[dict]] = {"unchanged": [], "changed": []}
    first = max(0, args.first_entry)
    last = min(args.last_entry, clean.entry_count - 1, localized.entry_count - 1)
    for entry in range(first, last + 1):
        changed = clean.raw_entry("graphics", entry) != localized.raw_entry("graphics", entry)
        try:
            cells = parse_ncer(localized.raw_entry("cells", entry))
        except Exception:
            continue
        for cell in range(len(cells)):
            try:
                image = localized.render(entry, cell)
            except Exception:
                continue
            if not is_label_like(*image.size):
                continue
            groups["changed" if changed else "unchanged"].append(
                {"entry": entry, "cell": cell, "size": list(image.size), "image": image}
            )

    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {}
    columns, rows, slot_w, slot_h = 4, 12, 240, 100
    for name, records in groups.items():
        records.sort(key=lambda r: (r["entry"], r["cell"]))
        manifest[name] = [{k: v for k, v in record.items() if k != "image"} for record in records]
        per_page = columns * rows
        for page in range(math.ceil(len(records) / per_page)):
            image = Image.new("RGBA", (columns * slot_w, rows * slot_h), (19, 27, 40, 255))
            draw = ImageDraw.Draw(image)
            for index, record in enumerate(records[page * per_page:(page + 1) * per_page]):
                x = index % columns * slot_w
                y = index // columns * slot_h
                sprite = record["image"].copy()
                sprite.thumbnail((slot_w - 10, slot_h - 26), Image.Resampling.NEAREST)
                image.alpha_composite(sprite, (x + (slot_w - sprite.width) // 2, y + 23))
                draw.text((x + 4, y + 4), f"{record['entry']}:{record['cell']} {record['size'][0]}x{record['size'][1]}", fill="white")
            image.save(args.output / f"low_ui_{name}_{page:02d}.png")
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({name: len(records) for name, records in groups.items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
