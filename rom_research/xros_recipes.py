"""Extract the native Xros Wars DigiFusion recipe table."""

from __future__ import annotations

import argparse
import csv
import struct
from dataclasses import dataclass
from pathlib import Path

from rom_research.nds_code_compression import decompress_blz
from rom_research.nds_inventory import read_header
from rom_research.roster_name_map import read_messages


RECIPE_OFFSET = 0xE27C0
RECIPE_COUNT = 219
RECIPE_SIZE = 32
XROS_FORMAL_NAME_FIRST = 651
STAT_NAMES = {
    0: "unused",
    1: "attack",
    2: "intelligence",
    3: "speed",
    4: "defense",
    6: "befriended_species",
}


@dataclass(frozen=True)
class Requirement:
    kind: int
    value: int


@dataclass(frozen=True)
class XrosRecipe:
    result_id: int
    mode: int
    component_ids: tuple[int, ...]
    minimum_level: int
    requirements: tuple[Requirement, ...]


def extract_arm9(rom_path: Path) -> bytes:
    with rom_path.open("rb") as handle:
        header = read_header(handle)
        handle.seek(int(header["arm9_offset"]))
        return decompress_blz(handle.read(int(header["arm9_size"])))


def parse_recipes(arm9: bytes) -> tuple[XrosRecipe, ...]:
    recipes: list[XrosRecipe] = []
    for index in range(RECIPE_COUNT):
        offset = RECIPE_OFFSET + index * RECIPE_SIZE
        values = struct.unpack_from("<HBB5H9H", arm9, offset)
        stored_result, mode, component_count = values[:3]
        if not 1 <= component_count <= 5:
            raise ValueError(f"Recipe {index} has invalid component count")
        stored_components = values[3:8]
        if any(value == 0xFFFF for value in stored_components[:component_count]):
            raise ValueError(f"Recipe {index} has a missing required component")
        if any(value != 0xFFFF for value in stored_components[component_count:]):
            raise ValueError(f"Recipe {index} has data after its component list")
        tail = values[8:]
        requirements = tuple(
            Requirement(kind=tail[pair + 1], value=tail[pair])
            for pair in (2, 4, 6)
            if tail[pair] != 0xFFFF
        )
        recipes.append(
            XrosRecipe(
                result_id=stored_result + 1,
                mode=mode,
                component_ids=tuple(
                    value + 1 for value in stored_components[:component_count]
                ),
                minimum_level=tail[0],
                requirements=requirements,
            )
        )
    return tuple(recipes)


def _names(messages_csv: Path) -> dict[int, str]:
    return {
        message.string_index - XROS_FORMAL_NAME_FIRST: message.text
        for message in read_messages(messages_csv)
        if message.archive == "MSG/MESPAK00.PAK"
        and message.pak_entry == 0
        and XROS_FORMAL_NAME_FIRST <= message.string_index <= 1048
    }


def export_recipes(
    rom_path: Path,
    messages_csv: Path,
    output_csv: Path,
) -> int:
    names = _names(messages_csv)
    recipes = parse_recipes(extract_arm9(rom_path))
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "recipe_index",
                "result_id",
                "result_name",
                "mode",
                "component_ids",
                "component_names",
                "minimum_level",
                "requirement_1",
                "requirement_2",
                "requirement_3",
            )
        )
        for index, recipe in enumerate(recipes):
            formatted_requirements = [
                (
                    f"befriend {names.get(requirement.value + 1, requirement.value + 1)}"
                    if requirement.kind == 6
                    else f"{STAT_NAMES.get(requirement.kind, requirement.kind)} "
                    f"{requirement.value}"
                )
                for requirement in recipe.requirements
            ]
            writer.writerow(
                (
                    index,
                    recipe.result_id,
                    names.get(recipe.result_id, ""),
                    recipe.mode,
                    " / ".join(map(str, recipe.component_ids)),
                    " / ".join(names.get(value, "") for value in recipe.component_ids),
                    recipe.minimum_level,
                    *(formatted_requirements + [""] * (3 - len(formatted_requirements))),
                )
            )
    return len(recipes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("messages_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    args = parser.parse_args()
    count = export_recipes(args.rom, args.messages_csv, args.output_csv)
    print(f"Exported {count} DigiFusion recipes to {args.output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
