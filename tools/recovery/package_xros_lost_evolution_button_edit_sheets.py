#!/usr/bin/env python3
"""Package native transparent Xros canvases with applicable LE English donors."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

from PIL import Image


DOWNLOADS = Path(r"C:\Users\YOUR_NAME\Downloads")
XROS = DOWNLOADS / "Xros Native Button Edit Sheets"
LE = DOWNLOADS / "Lost Evolution English Button Donors - Native"
OUT = DOWNLOADS / "Xros Buttons - Native Manual Edit Package"


DONORS = (
    ("READY", "LE_entry0175_cell00_97x19.png"),
    ("SHOW MENU", "LE_entry0176_cell00_97x19.png"),
    ("QUIT", "LE_entry0177_cell00_97x19.png"),
    ("NEXT", "LE_entry0178_cell00_97x19.png"),
    ("VIEW REWARD", "LE_entry0119_cell00_97x19.png"),
    ("DIGIEGG RANKING", "LE_entry0120_cell00_100x19.png"),
)


def make_donor_sheet() -> None:
    items: list[tuple[str, str, Image.Image]] = []
    for label, filename in DONORS:
        source = LE / filename
        if not source.is_file():
            continue
        items.append((label, filename, Image.open(source).convert("RGBA")))

    gutter = 4
    width = sum(image.width for _, _, image in items) + gutter * (len(items) + 1)
    height = max(image.height for _, _, image in items) + gutter * 2
    sheet = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    rows: list[tuple[str, str, int, int, int, int]] = []
    x = gutter
    for label, filename, image in items:
        y = gutter
        sheet.alpha_composite(image, (x, y))
        rows.append((label, filename, x, y, image.width, image.height))
        x += image.width + gutter

    native = OUT / "03_LOST_EVOLUTION_APPLICABLE_DONORS_NATIVE_1X.png"
    sheet.save(native)
    preview = sheet.resize((sheet.width * 4, sheet.height * 4), Image.Resampling.NEAREST)
    preview.save(OUT / "PREVIEW_03_LOST_EVOLUTION_APPLICABLE_DONORS_4X.png")
    with (OUT / "03_LOST_EVOLUTION_APPLICABLE_DONORS_NATIVE_1X.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(("label", "source_file", "x", "y", "width", "height"))
        writer.writerows(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    copies = (
        ("battle_buttons_BLANK_NATIVE_1X.png", "01_XROS_BATTLE_MENU_BLANK_NATIVE_1X.png"),
        ("battle_buttons_BLANK_NATIVE_1X.tsv", "01_XROS_BATTLE_MENU_BLANK_NATIVE_1X.tsv"),
        ("PREVIEW_battle_blank_4X.png", "PREVIEW_01_XROS_BATTLE_MENU_BLANK_4X.png"),
        ("small_and_result_buttons_NATIVE_1X.png", "02_XROS_SMALL_AND_RESULT_ORIGINAL_NATIVE_1X.png"),
        ("small_and_result_buttons_NATIVE_1X.tsv", "02_XROS_SMALL_AND_RESULT_ORIGINAL_NATIVE_1X.tsv"),
        ("PREVIEW_small_and_result_4X.png", "PREVIEW_02_XROS_SMALL_AND_RESULT_ORIGINAL_4X.png"),
    )
    for source_name, destination_name in copies:
        shutil.copy2(XROS / source_name, OUT / destination_name)
    make_donor_sheet()
    (OUT / "README.txt").write_text(
        "All editable sheets are transparent RGBA at native 1x resolution.\n"
        "Do not resize the Xros cells. Use each TSV to crop and return cells exactly.\n"
        "Sheet 01: blank Xros battle-menu plates.\n"
        "Sheet 02: original Xros small/result controls.\n"
        "Sheet 03: applicable Lost Evolution English donor controls.\n"
        "Lost Evolution donors are references, not dimension-compatible direct swaps.\n"
        "The PREVIEW files are nearest-neighbour 4x viewing copies only.\n",
        encoding="utf-8",
    )
    print(OUT)


if __name__ == "__main__":
    main()
