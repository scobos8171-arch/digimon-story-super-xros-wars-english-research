"""Create 1:1 native-resolution button sheets for manual pixel editing."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "recovery"))

from build_xros_blank_button_import import SOURCE_CELLS, crop_sheet_cell  # noqa: E402


SMALL_RESULT = [
    *(('0110', cell, label) for cell, label in enumerate(('BACK', 'CONFIRM', 'NEXT', 'FINISH', 'FINISH'))),
    ('0147', 1, 'CONFIRM'), ('0147', 2, 'BACK'), ('0147', 3, 'BACK'),
    ('0194', 0, 'BACK'), ('0196', 8, 'BACK'), ('0198', 8, 'BACK'),
    ('2218', 0, 'BACK'), ('2218', 1, 'CONFIRM'), ('2218', 2, 'SWITCH'),
    ('2218', 3, 'BACK SELECTED'), ('2218', 4, 'CONFIRM SELECTED'),
    ('2218', 5, 'SWITCH SELECTED'), ('2218', 6, 'GAINED EXP'),
    ('2218', 7, 'FOUND ITEMS'), ('2218', 8, 'NEXT'), ('2218', 9, 'FINISH'),
    ('2218', 10, 'TO STATUS'), ('2218', 11, 'WORLD MAP'),
    ('2218', 12, 'FIELD GUIDE'),
]

BATTLE_LABELS = (
    'BACK', 'BATTLE START', 'BACK', 'BATTLE START', 'BACK', 'BATTLE START',
    'ALL TACTICS', 'ALL TACTICS', 'ALL TACTICS', 'BACK', 'BACK', 'BACK',
)


def assemble(items: list[tuple[str, Image.Image]], output: Path, mapping: Path, gap: int = 4) -> None:
    max_height = max(image.height for _, image in items)
    width = gap + sum(image.width + gap for _, image in items)
    height = max_height + gap * 2
    sheet = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    rows = []
    x = gap
    for label, image in items:
        y = gap + (max_height - image.height) // 2
        sheet.alpha_composite(image.convert('RGBA'), (x, y))
        rows.append((label, x, y, image.width, image.height))
        x += image.width + gap
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    with mapping.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, delimiter='\t')
        writer.writerow(('label', 'x', 'y', 'width', 'height'))
        writer.writerows(rows)


def make_preview(sheet_path: Path, mapping_path: Path, output: Path, scale: int = 4) -> None:
    source = Image.open(sheet_path).convert('RGBA')
    enlarged = source.resize((source.width * scale, source.height * scale), Image.Resampling.NEAREST)
    canvas = Image.new('RGBA', (enlarged.width, enlarged.height + 28), (18, 26, 40, 255))
    canvas.alpha_composite(enlarged, (0, 28))
    ImageDraw.Draw(canvas).text((6, 7), f'1:1 source: {sheet_path.name} | mapping: {mapping_path.name}', fill='white')
    canvas.save(output)


def build(clean_rendered: Path, blank_battle_sheet: Path, output: Path) -> None:
    small_items: list[tuple[str, Image.Image]] = []
    for entry, cell, label in SMALL_RESULT:
        source = clean_rendered / f'entry_{entry}' / f'cell_{cell:02d}.png'
        small_items.append((f'{entry}:{cell} {label}', Image.open(source).convert('RGBA')))

    blank_sheet = Image.open(blank_battle_sheet).convert('RGBA')
    battle_items: list[tuple[str, Image.Image]] = []
    for cell, label in enumerate(BATTLE_LABELS):
        image = crop_sheet_cell(blank_sheet, 1987, cell)
        battle_items.append((f'1987:{cell} {label}', image))

    small_sheet = output / 'small_and_result_buttons_NATIVE_1X.png'
    small_map = output / 'small_and_result_buttons_NATIVE_1X.tsv'
    battle_sheet = output / 'battle_buttons_BLANK_NATIVE_1X.png'
    battle_map = output / 'battle_buttons_BLANK_NATIVE_1X.tsv'
    assemble(small_items, small_sheet, small_map)
    assemble(battle_items, battle_sheet, battle_map)
    make_preview(small_sheet, small_map, output / 'PREVIEW_small_and_result_4X.png')
    make_preview(battle_sheet, battle_map, output / 'PREVIEW_battle_blank_4X.png')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('clean_rendered', type=Path)
    parser.add_argument('blank_battle_sheet', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    build(**vars(args))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
