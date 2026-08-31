"""Export native Blue/Red menu logos for hand localization."""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BLUE_SRC = ROOT / "outputs" / "_title_probe_blue"
RED_SRC = ROOT / "outputs" / "_title_probe_red"
OUT = ROOT / "outputs" / "Xros Blue Red menu logos to paint"
DOWNLOADS = Path(r"C:\Users\YOUR_NAME\Downloads\Xros Blue Red menu logos to paint")

# (folder, filename, relpath under probe, note)
FILES = [
    ("01_title_logo", "BLUE_title_logo_entry_0034_cell_00_206x142.png", "entry_0034/cell_00.png"),
    ("01_title_logo", "RED_title_logo_entry_0034_cell_00_206x142.png", "entry_0034/cell_00.png"),
    ("02_army_logos", "BLUE_FLARE_entry_0036_cell_00_161x30.png", "entry_0036/cell_00.png"),
    ("02_army_logos", "TWILIGHT_RED_entry_0036_cell_01_160x31.png", "entry_0036/cell_01.png"),
    ("02_army_logos", "VS_lines_entry_0036_cell_02_252x71.png", "entry_0036/cell_02.png"),
    ("02_army_logos", "VS_both_armies_entry_0036_cell_03_252x71.png", "entry_0036/cell_03.png"),
    ("03_title_menu", "BEGIN_ADVENTURE_entry_0038_cell_00_162x18.png", "entry_0038/cell_00.png"),
    ("03_title_menu", "CONTINUE_NEWGAME_RELOAD_entry_0038_cell_01_162x50.png", "entry_0038/cell_01.png"),
    ("03_title_menu", "CONTINUE_NEWGAME_RELOAD_entry_0038_cell_02_162x50.png", "entry_0038/cell_02.png"),
    ("03_title_menu", "CONTINUE_NEWGAME_RELOAD_entry_0038_cell_03_162x50.png", "entry_0038/cell_03.png"),
    ("03_title_menu", "CONTINUE_entry_0038_cell_04_162x18.png", "entry_0038/cell_04.png"),
    ("03_title_menu", "copyright_red_strip_entry_0039_cell_00_246x32.png", "entry_0039/cell_00.png"),
    ("03_title_menu", "copyright_blue_strip_entry_0040_cell_00_246x32.png", "entry_0040/cell_00.png"),
    ("03_title_menu", "DEMO_entry_0035_cell_00_56x22.png", "entry_0035/cell_00.png"),
]


def copy_cell(probe: Path, rel: str, dest: Path) -> Image.Image:
    src = probe / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(src).convert("RGBA")
    image.save(dest)
    return image


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    for folder, name, rel in FILES:
        probe = RED_SRC if name.startswith("RED_") else BLUE_SRC
        image = copy_cell(probe, rel, OUT / folder / name)
        preview = image.resize((image.width * 4, image.height * 4), Image.Resampling.NEAREST)
        preview.save(OUT / folder / name.replace(".png", "_4x.png"))
        print(name, image.size)

    readme = """XROS BLUE / RED MENU LOGOS TO PAINT
=====================================
Native 1x PNGs from clean Japanese Blue (TBFJ) and Red (TLTJ) cartridges.

RULES
- Edit the native PNG, not the _4x preview.
- Keep the exact width x height in the filename.
- Keep transparency. Hard pixels only. No blur or resize.
- Keep the X mark, army emblems, metallic shading, and BLUE/RED badge.
- Replace Japanese lettering only.

TITLE LOGO (entry 34, 206x142)
Japanese: デジモンストーリー 超クロスウォーズ ブルー
English:
  DIGIMON STORY
  SUPER XROS WARS
  BLUE
Red's SPR member 34 is the same graphic as Blue in these dumps (both say ブルー).
Paint a RED variant if you want a Red-version title.

ARMY LOGOS (entry 36) — these are the Blue vs Red (Twilight) menu logos
cell 00 ブルーフレア = BLUE FLARE
cell 01 トワイライト = TWILIGHT
cell 02 = VS divider lines only
cell 03 = both logos + divider

TITLE MENU (entry 38)
cell 00 / 04 ぼうけんを はじめる = BEGIN ADVENTURE
cell 01-03:
  つづきから はじめる = CONTINUE
  はじめから やりなおす = NEW GAME
  リロードチャレンジ = RELOAD CHALLENGE
Keep yellow = selected, cyan = unselected.

COPYRIGHT (39 red strip, 40 blue strip)
Keep names/year:
  (c) Akiyoshi Hongo, Toei Animation, TV Asahi, Dentsu
  (c) 2011 NBGI

Return the same filenames.
"""
    (OUT / "README.txt").write_text(readme, encoding="utf-8")
    if DOWNLOADS.exists():
        shutil.rmtree(DOWNLOADS)
    shutil.copytree(OUT, DOWNLOADS)
    print("wrote", DOWNLOADS)


if __name__ == "__main__":
    main()
