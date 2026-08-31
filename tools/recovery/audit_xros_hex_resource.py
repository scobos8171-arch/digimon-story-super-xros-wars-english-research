"""Render and compare the Super Xros Wars hex-menu sprite resource.

This is intentionally read-only. It extracts one requested sprite resource
from each supplied ROM, renders every NCER cell with its original
NCGR/NCLR data, and writes hashes plus contact sheets.  The output answers a
single question before any new patch is attempted: which cells actually carry
the Japanese command-ring text in each ROM build?
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw


REPO_ROOT = Path(__file__).resolve().parents[2]
EDITOR_ROOT = REPO_ROOT / "work" / "DigimonNDSRomEditor-master"
if str(EDITOR_ROOT) not in sys.path:
    sys.path.insert(0, str(EDITOR_ROOT))

from rom_research.xros_sprite import XrosSpriteSet  # noqa: E402


DEFAULT_ENTRY_ID = 198  # 0xC6, the hex-button shell resource.


def parse_rom_argument(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("ROM must be LABEL=full\\path\\to\\file.nds")
    label, raw_path = value.split("=", 1)
    path = Path(raw_path).expanduser().resolve()
    if not label.strip() or not path.is_file():
        raise argparse.ArgumentTypeError(f"ROM is missing or invalid: {value}")
    return label.strip(), path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def paste_cell(sheet: Image.Image, image: Image.Image, x: int, y: int, title: str) -> None:
    draw = ImageDraw.Draw(sheet)
    if image.width > 0 and image.height > 0:
        rendered = image.resize((image.width * 3, image.height * 3), Image.Resampling.NEAREST)
        sheet.alpha_composite(rendered, (x + 8, y + 20))
    draw.text((x + 8, y + 4), title, fill=(255, 255, 255, 255))


def audit_rom(label: str, path: Path, output_root: Path, entry_id: int) -> dict[str, object]:
    sprite_set = XrosSpriteSet.from_rom(path)
    raw_graphics = sprite_set.raw_entry("graphics", entry_id)
    raw_palette = sprite_set.raw_entry("palette", entry_id)
    raw_cells = sprite_set.raw_entry("cells", entry_id)

    # Render first, so malformed resources fail visibly rather than yielding a
    # misleading empty report.
    from rom_research.xros_sprite import parse_ncer

    cells = parse_ncer(raw_cells)
    rendered = [sprite_set.render(entry_id, index) for index in range(len(cells))]
    cell_meta: list[dict[str, object]] = []
    for index, image in enumerate(rendered):
        rgba = image.tobytes()
        cell_meta.append(
            {
                "cell": index,
                "size": [image.width, image.height],
                "rgba_sha256": digest(rgba),
                "opaque_pixels": sum(1 for pixel in image.getdata() if pixel[3]),
            }
        )

    column_width, row_height = 240, 220
    columns = 3
    rows = max(1, (len(rendered) + columns - 1) // columns)
    sheet = Image.new("RGBA", (columns * column_width, rows * row_height), (15, 26, 42, 255))
    for index, image in enumerate(rendered):
        x = (index % columns) * column_width
        y = (index // columns) * row_height
        paste_cell(sheet, image, x, y, f"entry {entry_id} / cell {index} / {image.width}x{image.height}")

    label_dir = output_root / label
    label_dir.mkdir(parents=True, exist_ok=True)
    sheet.save(label_dir / f"entry_{entry_id:04d}_all_cells.png")
    for index, image in enumerate(rendered):
        image.save(label_dir / f"cell_{index:02d}_original.png")

    return {
        "label": label,
        "rom": str(path),
        "rom_sha256": digest(path.read_bytes()),
        "entry": entry_id,
        "archives": {
            "SPR_NCGR.PAK": {"unpacked_size": len(raw_graphics), "sha256": digest(raw_graphics)},
            "SPR_NCLR.PAK": {"unpacked_size": len(raw_palette), "sha256": digest(raw_palette)},
            "SPR_NCER.PAK": {"unpacked_size": len(raw_cells), "sha256": digest(raw_cells)},
        },
        "cells": cell_meta,
        "contact_sheet": str((label_dir / "entry_0198_all_cells.png").resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", action="append", required=True, type=parse_rom_argument)
    parser.add_argument(
        "--entry-id",
        type=lambda value: int(value, 0),
        default=DEFAULT_ENTRY_ID,
        help="Sprite PAK entry to audit (decimal or 0x-prefixed hexadecimal).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "work" / "qa" / "xros_hex_resource_audit",
    )
    args = parser.parse_args()
    output_root = args.out.resolve()
    report = {"purpose": "read-only Xros sprite resource audit", "entry": args.entry_id, "results": []}
    for label, path in args.rom:
        report["results"].append(audit_rom(label, path, output_root, args.entry_id))
    (output_root / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(output_root / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
