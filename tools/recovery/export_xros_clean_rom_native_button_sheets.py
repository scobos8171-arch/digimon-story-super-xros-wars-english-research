#!/usr/bin/env python3
"""Export genuine 1:1 Xros button cells directly from a clean Japanese ROM."""

from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "work" / "DigimonNDSRomEditor-master"
sys.path.insert(0, str(RESEARCH))
sys.path.insert(0, str(ROOT / "tools" / "recovery"))

from build_xros_custom_ui_rom import render_full_cell  # noqa: E402
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, find_nitro_file, read_nitro_file  # noqa: E402
from rom_research.xros_sprite import parse_ncer, parse_ncgr, parse_nclr  # noqa: E402


GRAPHICS = "SPR_NCGR.PAK"
PALETTES = "SPR_NCLR.PAK"
CELLS = "SPR_NCER.PAK"

SMALL_RESULT = (
    *((110, cell, label) for cell, label in enumerate(("BACK", "CONFIRM", "NEXT", "FINISH", "FINISH"))),
    (147, 1, "CONFIRM"),
    (147, 2, "BACK"),
    (147, 3, "BACK"),
    (194, 0, "BACK"),
    (196, 8, "BACK"),
    (198, 8, "BACK"),
    (2218, 0, "BACK"),
    (2218, 1, "CONFIRM"),
    (2218, 2, "SWITCH"),
    (2218, 3, "BACK SELECTED"),
    (2218, 4, "CONFIRM SELECTED"),
    (2218, 5, "SWITCH SELECTED"),
    (2218, 6, "GAINED EXP"),
    (2218, 7, "FOUND ITEMS"),
    (2218, 8, "NEXT"),
    (2218, 9, "FINISH"),
    (2218, 10, "TO STATUS"),
    (2218, 11, "WORLD MAP"),
    (2218, 12, "FIELD GUIDE"),
)

BATTLE = (
    (1987, 0, "BACK"),
    (1987, 1, "BATTLE START"),
    (1987, 2, "BACK"),
    (1987, 3, "BATTLE START"),
    (1987, 4, "BACK"),
    (1987, 5, "BATTLE START"),
    (1987, 6, "ALL TACTICS"),
    (1987, 7, "ALL TACTICS"),
    (1987, 8, "ALL TACTICS"),
    (1987, 9, "BACK"),
    (1987, 10, "BACK"),
    (1987, 11, "BACK"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_archives(rom: Path) -> tuple[XrosPak, XrosPak, XrosPak]:
    with rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        return tuple(
            XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, name)))
            for name in (GRAPHICS, PALETTES, CELLS)
        )  # type: ignore[return-value]


def render_selected(
    archives: tuple[XrosPak, XrosPak, XrosPak],
    selected: tuple[tuple[int, int, str], ...],
) -> list[tuple[int, int, str, Image.Image]]:
    graphics_pak, palette_pak, cell_pak = archives
    parsed: dict[int, tuple[object, object, object]] = {}
    output: list[tuple[int, int, str, Image.Image]] = []
    for entry, cell_index, label in selected:
        if entry not in parsed:
            parsed[entry] = (
                parse_ncgr(graphics_pak.unpacked_data(entry)),
                parse_nclr(palette_pak.unpacked_data(entry)),
                parse_ncer(cell_pak.unpacked_data(entry)),
            )
        graphics, palette, cells = parsed[entry]
        image = render_full_cell(graphics, palette, cells[cell_index])  # type: ignore[index]
        output.append((entry, cell_index, label, image))
    return output


def assemble(
    items: list[tuple[int, int, str, Image.Image]],
    output: Path,
    mapping: Path,
    individual: Path,
    gap: int = 4,
) -> None:
    max_height = max(image.height for *_metadata, image in items)
    width = gap + sum(image.width + gap for *_metadata, image in items)
    sheet = Image.new("RGBA", (width, max_height + gap * 2), (0, 0, 0, 0))
    rows: list[tuple[object, ...]] = []
    individual.mkdir(parents=True, exist_ok=True)
    x = gap
    for entry, cell, label, image in items:
        y = gap + (max_height - image.height) // 2
        sheet.alpha_composite(image, (x, y))
        filename = f"entry{entry:04d}_cell{cell:02d}_{image.width}x{image.height}.png"
        image.save(individual / filename)
        rows.append((entry, cell, label, filename, x, y, image.width, image.height))
        if sheet.crop((x, y, x + image.width, y + image.height)).tobytes() != image.tobytes():
            raise AssertionError(f"Sheet round-trip failed for entry {entry} cell {cell}")
        x += image.width + gap
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    with mapping.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(("entry", "cell", "intended_english", "individual_file", "x", "y", "width", "height"))
        writer.writerows(rows)


def preview(source: Path, output: Path, scale: int = 4) -> None:
    image = Image.open(source).convert("RGBA")
    scaled = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
    canvas = Image.new("RGBA", (scaled.width, scaled.height + 28), (18, 26, 40, 255))
    canvas.alpha_composite(scaled, (0, 28))
    ImageDraw.Draw(canvas).text((6, 7), "PREVIEW ONLY - genuine clean-ROM pixels enlarged 4x", fill="white")
    canvas.save(output)


def main() -> None:
    rom = Path(
        r"C:\Users\YOUR_NAME\Downloads\5612 - Digimon Story - Super Xros Wars Blue (JP)"
        r"\Digimon Story - Super Xros Wars Blue (5612) (JP).nds"
    )
    output = Path(r"C:\Users\YOUR_NAME\Downloads\Xros OG Buttons - Clean ROM Native 1X")
    output.mkdir(parents=True, exist_ok=True)
    archives = load_archives(rom)

    battle = output / "01_BATTLE_MENU_OG_CLEAN_ROM_NATIVE_1X.png"
    small = output / "02_SMALL_AND_RESULT_OG_CLEAN_ROM_NATIVE_1X.png"
    assemble(
        render_selected(archives, BATTLE),
        battle,
        output / "01_BATTLE_MENU_OG_CLEAN_ROM_NATIVE_1X.tsv",
        output / "individual_battle_menu",
    )
    assemble(
        render_selected(archives, SMALL_RESULT),
        small,
        output / "02_SMALL_AND_RESULT_OG_CLEAN_ROM_NATIVE_1X.tsv",
        output / "individual_small_and_result",
    )
    preview(battle, output / "PREVIEW_01_BATTLE_MENU_OG_4X.png")
    preview(small, output / "PREVIEW_02_SMALL_AND_RESULT_OG_4X.png")
    (output / "SOURCE_PROVENANCE.txt").write_text(
        f"Source ROM: {rom}\n"
        f"Source SHA-256: {sha256(rom)}\n"
        "Source archives: SPR_NCGR.PAK + SPR_NCLR.PAK + SPR_NCER.PAK\n"
        "Rendering: exact NCER/OAM bounds at 1x; no scaling, painting, or donor artwork.\n"
        "Editable sheets: transparent RGBA with 4px transparent gutters.\n"
        "PREVIEW files only: nearest-neighbour 4x enlargement.\n",
        encoding="utf-8",
    )
    print(output)


if __name__ == "__main__":
    main()
