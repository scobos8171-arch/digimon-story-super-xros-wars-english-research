"""Render Dawn/Dusk BTCHR.PAK sprite slots for visual auditing."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw

from rom_research.battle_sprite_import import (
    DUSK_BATTLE_ARCHIVE,
    _load_nitro_file,
    _sprite_group_components,
)
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
    sprite_ids: tuple[int, ...],
) -> None:
    archive = DuskPak.from_bytes(_load_nitro_file(rom_path, DUSK_BATTLE_ARCHIVE))
    rows: list[tuple[int, int, Image.Image]] = []
    for sprite_id in sprite_ids:
        components = _sprite_group_components(archive, sprite_id)
        graphics = parse_ncgr(components["graphics"])
        palette = parse_nclr(components["palette"])
        cells = parse_ncer(components["cells"])
        for cell_index, cell in enumerate(cells):
            rendered = render_cell_rgba(graphics, palette, cell)
            rows.append(
                (
                    sprite_id,
                    cell_index,
                    Image.frombytes(
                        "RGBA",
                        (rendered.width, rendered.height),
                        rendered.pixels,
                    ),
                )
            )

    cell_width = 128
    cell_height = 128
    columns = min(6, max(1, len(rows)))
    sheet = Image.new(
        "RGBA",
        (columns * cell_width, math.ceil(len(rows) / columns) * cell_height),
        "#18202b",
    )
    draw = ImageDraw.Draw(sheet)
    for position, (sprite_id, cell_index, sprite) in enumerate(rows):
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
            f"slot {sprite_id} cell {cell_index}",
            fill="#f2f5f8",
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("sprite_ids", nargs="+", type=int)
    args = parser.parse_args()
    render_sheet(args.rom, args.output, tuple(args.sprite_ids))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
