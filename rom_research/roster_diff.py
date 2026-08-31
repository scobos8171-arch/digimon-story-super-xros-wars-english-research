"""Compare rendered Blue and Dusk battle sprites and report donor candidates."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
from pathlib import Path

from PIL import Image, ImageDraw

from digimon_core import constants, loaders
from digimon_core.rom import detectVersion
from rom_research.dusk_pak import DuskPak
from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.xros_pak import find_nitro_file, read_nitro_file
from rom_research.xros_sprite import (
    XrosSpriteSet,
    parse_ncer,
    parse_ncgr,
    parse_nclr,
    render_cell,
)


BLUE_BATTLE_START = 908
BLUE_BATTLE_END = 1306
DUSK_BATTLE_ARCHIVE = "dat/BTCHR.PAK"


def _image_key(image: Image.Image) -> str:
    digest = hashlib.sha256()
    digest.update(image.width.to_bytes(2, "little"))
    digest.update(image.height.to_bytes(2, "little"))
    digest.update(image.tobytes())
    return digest.hexdigest()


def _load_dusk_battle_archive(rom_path: Path) -> DuskPak:
    with rom_path.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        return DuskPak.from_bytes(
            read_nitro_file(
                handle,
                find_nitro_file(files, DUSK_BATTLE_ARCHIVE),
            )
        )


def _render_dusk_sprite(archive: DuskPak, sprite_id: int) -> Image.Image:
    base = sprite_id * 5
    return render_cell(
        parse_ncgr(archive.unpacked_data(base + 1)),
        parse_nclr(archive.unpacked_data(base + 2)),
        parse_ncer(archive.unpacked_data(base + 3))[0],
    )


def _dusk_names(rom_path: Path) -> dict[int, list[str]]:
    rom_data = bytearray(rom_path.read_bytes())
    version = detectVersion(rom_data, str(rom_path))
    sprite_map = loaders.loadSpriteMapTable(version, rom_data)
    names: dict[int, list[str]] = {}
    for digimon_id, entry in enumerate(sprite_map):
        name = constants.DIGIMON_ID_TO_STR.get(digimon_id)
        if name:
            names.setdefault(entry.main_sprite, []).append(name)
    return names


def compare_rosters(
    dusk_rom: Path,
    blue_rom: Path,
    csv_path: Path,
    preview_path: Path,
) -> tuple[int, int]:
    dusk_archive = _load_dusk_battle_archive(dusk_rom)
    dusk_sprite_count = len(dusk_archive.entries) // 5
    names = _dusk_names(dusk_rom)
    exact_by_hash: dict[str, list[int]] = {}
    for sprite_id in range(dusk_sprite_count):
        image = _render_dusk_sprite(dusk_archive, sprite_id)
        exact_by_hash.setdefault(_image_key(image), []).append(sprite_id)

    blue = XrosSpriteSet.from_rom(blue_rom)
    end = min(BLUE_BATTLE_END, blue.entry_count)
    rows: list[dict[str, str | int]] = []
    candidates: list[tuple[int, Image.Image]] = []
    exact_count = 0
    for donor_entry in range(BLUE_BATTLE_START, end):
        image = blue.render(donor_entry)
        matches = exact_by_hash.get(_image_key(image), [])
        if matches:
            exact_count += 1
        else:
            candidates.append((donor_entry, image))
        rows.append(
            {
                "blue_entry": donor_entry,
                "classification": "exact Dusk match" if matches else "donor candidate",
                "dusk_sprite_ids": ", ".join(str(value) for value in matches),
                "dusk_names": " / ".join(
                    name
                    for sprite_id in matches
                    for name in names.get(sprite_id, [])
                ),
                "width": image.width,
                "height": image.height,
                "blue_graphics_bytes": len(blue.raw_entry("graphics", donor_entry)),
                "blue_palette_bytes": len(blue.raw_entry("palette", donor_entry)),
                "blue_cell_bytes": len(blue.raw_entry("cells", donor_entry)),
                "blue_animation_bytes": len(blue.raw_entry("animation", donor_entry)),
            }
        )

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    _write_candidate_sheet(candidates, preview_path)
    return exact_count, len(candidates)


def _write_candidate_sheet(
    candidates: list[tuple[int, Image.Image]],
    output_path: Path,
    *,
    columns: int = 12,
    cell_size: int = 112,
) -> None:
    rows = max(1, math.ceil(len(candidates) / columns))
    sheet = Image.new(
        "RGB",
        (columns * cell_size, rows * cell_size),
        "#18202b",
    )
    draw = ImageDraw.Draw(sheet)
    for position, (entry, original) in enumerate(candidates):
        column = position % columns
        row = position // columns
        x = column * cell_size
        y = row * cell_size
        image = original.copy()
        image.thumbnail((cell_size - 10, cell_size - 22), Image.Resampling.NEAREST)
        image_x = x + (cell_size - image.width) // 2
        image_y = y + 17 + (cell_size - 17 - image.height) // 2
        sheet.paste(image, (image_x, image_y), image)
        draw.text((x + 4, y + 3), str(entry), fill="#f2f5f8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, quality=94)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dusk_rom", type=Path)
    parser.add_argument("blue_rom", type=Path)
    parser.add_argument("csv", type=Path)
    parser.add_argument("preview", type=Path)
    args = parser.parse_args()
    exact, candidates = compare_rosters(
        args.dusk_rom,
        args.blue_rom,
        args.csv,
        args.preview,
    )
    print(
        f"Compared {exact + candidates} Blue battle sprites: "
        f"{exact} exact Dusk matches, {candidates} donor candidates"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
