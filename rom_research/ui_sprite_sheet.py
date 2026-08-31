"""Render coordinated Dusk UI-sprite archive entries for visual auditing."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw

from rom_research.battle_sprite_import import DUSK_UI_ARCHIVES, _load_nitro_file
from rom_research.dusk_pak import DuskPak
from rom_research.xros_sprite import (
    parse_ncer,
    parse_ncgr,
    parse_nclr,
    render_cell_rgba,
)


def render_sheet(
    rom_path: Path,
    output_path: Path,
    indices: tuple[int, ...],
) -> None:
    archives = {
        kind: DuskPak.from_bytes(_load_nitro_file(rom_path, archive_path))
        for kind, archive_path in DUSK_UI_ARCHIVES.items()
    }
    rows: list[tuple[int, int, Image.Image]] = []
    for sprite_index in indices:
        graphics = parse_ncgr(archives["graphics"].unpacked_data(sprite_index))
        palette = parse_nclr(archives["palette"].unpacked_data(sprite_index))
        cells = parse_ncer(archives["cells"].unpacked_data(sprite_index))
        for cell_index, cell in enumerate(cells):
            rendered = render_cell_rgba(graphics, palette, cell)
            rows.append(
                (
                    sprite_index,
                    cell_index,
                    Image.frombytes(
                        "RGBA",
                        (rendered.width, rendered.height),
                        rendered.pixels,
                    ),
                )
            )

    cell_width = 112
    cell_height = 112
    columns = min(6, max(1, len(rows)))
    sheet = Image.new(
        "RGBA",
        (columns * cell_width, math.ceil(len(rows) / columns) * cell_height),
        "#18202b",
    )
    draw = ImageDraw.Draw(sheet)
    for position, (sprite_index, cell_index, sprite) in enumerate(rows):
        x = position % columns * cell_width
        y = position // columns * cell_height
        sprite.thumbnail((cell_width - 8, cell_height - 24), Image.Resampling.NEAREST)
        sheet.alpha_composite(
            sprite,
            (
                x + (cell_width - sprite.width) // 2,
                y + 20 + (cell_height - 20 - sprite.height) // 2,
            ),
        )
        draw.text(
            (x + 4, y + 4),
            f"#{sprite_index} cell {cell_index}",
            fill="#f2f5f8",
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("indices", nargs="+", type=int)
    args = parser.parse_args()
    render_sheet(args.rom, args.output, tuple(args.indices))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
