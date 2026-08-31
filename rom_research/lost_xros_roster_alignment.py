"""Align Lost Evolution and Xros Wars roster IDs using rendered battle sprites."""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

from rom_research.roster_name_map import Message, read_messages
from rom_research.xros_sprite import XrosSpriteSet


LOST_NAME_FIRST = 119
LOST_NAME_LAST = 440
LOST_SPRITE_FIRST = 1061
XROS_NAME_FIRST = 651
XROS_NAME_LAST = 1048
XROS_SPRITE_FIRST = 908


def _image_key(sprite_set: XrosSpriteSet, entry: int) -> bytes:
    image = sprite_set.render(entry)
    bounds = image.getbbox()
    if bounds:
        image = image.crop(bounds)
    digest = hashlib.sha256()
    digest.update(image.width.to_bytes(2, "little"))
    digest.update(image.height.to_bytes(2, "little"))
    digest.update(image.tobytes())
    return digest.digest()


def _table(
    messages: list[Message],
    first: int,
    last: int,
) -> dict[int, str]:
    return {
        message.string_index: message.text
        for message in messages
        if message.archive == "MSG/MESPAK00.PAK"
        and message.pak_entry == 0
        and first <= message.string_index <= last
    }


def align_rosters(
    lost_rom: Path,
    xros_rom: Path,
    lost_japanese_csv: Path,
    lost_english_csv: Path,
    xros_japanese_csv: Path,
    output_csv: Path,
) -> dict[str, int]:
    lost_japanese = _table(
        read_messages(lost_japanese_csv), LOST_NAME_FIRST, LOST_NAME_LAST
    )
    lost_english = _table(
        read_messages(lost_english_csv), LOST_NAME_FIRST, LOST_NAME_LAST
    )
    xros_japanese = _table(
        read_messages(xros_japanese_csv), XROS_NAME_FIRST, XROS_NAME_LAST
    )
    lost_sprites = XrosSpriteSet.from_rom(lost_rom)
    xros_sprites = XrosSpriteSet.from_rom(xros_rom)

    lost_by_image: dict[bytes, list[int]] = {}
    for lost_name_index in range(LOST_NAME_FIRST, LOST_NAME_LAST + 1):
        sprite_entry = LOST_SPRITE_FIRST + lost_name_index - LOST_NAME_FIRST
        lost_by_image.setdefault(_image_key(lost_sprites, sprite_entry), []).append(
            lost_name_index
        )

    rows: list[dict[str, str | int]] = []
    exact = 0
    for xros_name_index in range(XROS_NAME_FIRST, XROS_NAME_LAST + 1):
        xros_sprite_entry = XROS_SPRITE_FIRST + xros_name_index - XROS_NAME_FIRST
        matches = lost_by_image.get(_image_key(xros_sprites, xros_sprite_entry), [])
        if len(matches) == 1:
            lost_name_index = matches[0]
            exact += 1
            status = "pixel_exact"
            lost_jp = lost_japanese.get(lost_name_index, "")
            lost_en = lost_english.get(lost_name_index, "")
            lost_sprite_entry: str | int = (
                LOST_SPRITE_FIRST + lost_name_index - LOST_NAME_FIRST
            )
        else:
            status = "xros_only_or_changed"
            lost_name_index = ""
            lost_jp = ""
            lost_en = ""
            lost_sprite_entry = ""
        rows.append(
            {
                "xros_roster_id": xros_name_index - XROS_NAME_FIRST,
                "xros_name_index": xros_name_index,
                "xros_sprite_entry": xros_sprite_entry,
                "xros_japanese": xros_japanese.get(xros_name_index, ""),
                "lost_roster_id": (
                    lost_name_index - LOST_NAME_FIRST
                    if isinstance(lost_name_index, int)
                    else ""
                ),
                "lost_name_index": lost_name_index,
                "lost_sprite_entry": lost_sprite_entry,
                "lost_japanese": lost_jp,
                "lost_english": lost_en,
                "status": status,
            }
        )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return {
        "xros_species": len(rows),
        "lost_species": len(lost_japanese),
        "pixel_exact": exact,
        "xros_only_or_changed": len(rows) - exact,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lost_rom", type=Path)
    parser.add_argument("xros_rom", type=Path)
    parser.add_argument("lost_japanese_csv", type=Path)
    parser.add_argument("lost_english_csv", type=Path)
    parser.add_argument("xros_japanese_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    args = parser.parse_args()
    result = align_rosters(
        args.lost_rom,
        args.xros_rom,
        args.lost_japanese_csv,
        args.lost_english_csv,
        args.xros_japanese_csv,
        args.output_csv,
    )
    print(
        f"Aligned {result['pixel_exact']} pixel-exact species across "
        f"{result['xros_species']} Xros and {result['lost_species']} Lost entries; "
        f"{result['xros_only_or_changed']} Xros entries require review"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
