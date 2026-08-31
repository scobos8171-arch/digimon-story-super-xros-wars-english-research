"""Extract Super Xros Wars' linked DigiXros recipe table from ARM9.

The game stores zero-based species IDs in 14-byte recipe records. Move records
whose low type byte is 1 reference those recipes through their +0x1C field.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


ARM9_BASE = 0x02000000
RECIPE_TABLE_ADDRESS = 0x020E092C
RECIPE_RECORD_SIZE = 14


def load_species_names(digimon_root: Path) -> dict[int, dict]:
    """Return Xros' zero-based species ID -> canonical metadata summary."""
    result: dict[int, dict] = {}
    for metadata_path in sorted(digimon_root.glob("*/metadata.json")):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source_ids = metadata.get("source_ids", {})
        ids = source_ids.get("xros_blue", []) or source_ids.get("xros_red", [])
        for one_based_id in ids:
            zero_based_id = int(one_based_id) - 1
            result.setdefault(
                zero_based_id,
                {
                    "zero_based_id": zero_based_id,
                    "source_internal_id": int(one_based_id),
                    "canonical_id": metadata.get("canonical_id"),
                    "display_name": metadata.get("display_name"),
                },
            )
    return result


def species_ref(species_id: int, names: dict[int, dict]) -> dict:
    ref = names.get(species_id)
    if ref:
        return dict(ref)
    return {
        "zero_based_id": species_id,
        "source_internal_id": species_id + 1,
        "canonical_id": None,
        "display_name": None,
    }


def extract(arm9_path: Path, moves_path: Path, digimon_root: Path) -> dict:
    arm9 = arm9_path.read_bytes()
    moves_doc = json.loads(moves_path.read_text(encoding="utf-8"))
    names = load_species_names(digimon_root)
    table_offset = RECIPE_TABLE_ADDRESS - ARM9_BASE
    recipes = []

    for move in moves_doc["records"]:
        if (int(move["field_0x00_u16"]) & 0xFF) != 1:
            continue
        index = int(move["linked_effect_index_i32"])
        if index < 0:
            continue
        offset = table_offset + index * RECIPE_RECORD_SIZE
        if offset < 0 or offset + RECIPE_RECORD_SIZE > len(arm9):
            continue
        values = struct.unpack_from("<7h", arm9, offset)
        field_0x00_i16, component_count, *component_slots = values
        if not 0 <= component_count <= len(component_slots):
            continue
        component_ids = component_slots[:component_count]
        recipes.append(
            {
                "move_record_id": move["id"],
                "move_display_name": move.get("display_name"),
                "move_record_address": move.get("record_address"),
                "recipe_index": index,
                "recipe_address": f"0x{RECIPE_TABLE_ADDRESS + index * RECIPE_RECORD_SIZE:08X}",
                "field_0x00_i16": field_0x00_i16,
                "component_count": component_count,
                "components": [species_ref(value, names) for value in component_ids],
                "raw_i16": list(values),
                "verified_result": (
                    {"display_name": "Shoutmon X2", "provenance": "successful runtime fixture"}
                    if component_ids == [356, 357]
                    else None
                ),
                "provenance": "ARM9 linked requirement table; consumed by FUN_0209CFE0",
            }
        )

    return {
        "schema": "xros_digixros_recipe_table_v1",
        "source_arm9": str(arm9_path),
        "source_moves": str(moves_path),
        "recipe_table_address": f"0x{RECIPE_TABLE_ADDRESS:08X}",
        "recipe_record_size": RECIPE_RECORD_SIZE,
        "species_id_convention": "component IDs are zero-based in ARM9; source_internal_id is one-based",
        "field_0x00_status": "unknown; it is not a species ID and is intentionally not labeled as the result",
        "recipe_count": len(recipes),
        "recipes": recipes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm9", type=Path)
    parser.add_argument("moves", type=Path)
    parser.add_argument("digimon_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    document = extract(args.arm9, args.moves, args.digimon_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {document['recipe_count']} recipes to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
