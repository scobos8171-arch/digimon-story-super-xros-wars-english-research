from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import Any


EDITOR_URL = "https://github.com/joaomlsantos/DigimonNDSRomEditor"


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.name.lower()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes | bytearray):
        return value.hex()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "__dict__"):
        return {
            key: _json_value(item)
            for key, item in vars(value).items()
            if not key.startswith("_") and key != "offset"
        }
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _upstream_commit(editor_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(editor_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or None
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def _load_editor(editor_root: Path) -> tuple[Any, Any, Any]:
    root = editor_root.resolve()
    if not (root / "digimon_core" / "loaders.py").is_file():
        raise FileNotFoundError(
            f"DigimonNDSRomEditor core not found under {root}; clone {EDITOR_URL}"
        )
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    try:
        rom = importlib.import_module("digimon_core.rom")
        loaders = importlib.import_module("digimon_core.loaders")
        constants = importlib.import_module("digimon_core.constants")
    except ImportError as exc:
        raise RuntimeError(f"Unable to import DigimonNDSRomEditor core: {exc}") from exc
    return rom, loaders, constants


def _named_records(records: Any, names: Any, *, key_name: str = "id") -> list[dict[str, Any]]:
    iterable = records.values() if isinstance(records, dict) else records
    result: list[dict[str, Any]] = []
    for index, record in enumerate(iterable):
        item = _json_value(record)
        record_id = int(item.get(key_name, index))
        if isinstance(names, dict):
            name = names.get(record_id)
        else:
            name = names[record_id] if 0 <= record_id < len(names) else None
        item["display_name"] = name or f"unknown_{record_id}"
        result.append(item)
    return result


def _existing_crosscheck(output_root: Path, species: list[dict[str, Any]], moves: list[dict[str, Any]]) -> dict[str, Any]:
    mechanics_path = output_root / "mechanics.json"
    result: dict[str, Any] = {
        "mechanics_present": mechanics_path.is_file(),
        "species_compared": 0,
        "species_exact_base_stats": 0,
        "moves_compared": 0,
        "moves_exact_core_fields": 0,
        "mismatches": [],
    }
    if not mechanics_path.is_file():
        return result
    mechanics = json.loads(mechanics_path.read_text(encoding="utf-8"))
    current_species = mechanics.get("species", {})
    current_moves = mechanics.get("skills", {})
    for editor_item in species:
        if not editor_item.get("playable_record"):
            continue
        source_id = str(editor_item["id"])
        candidates = [item for item in current_species.values() if str(item.get("source_internal_id")) == source_id]
        if not candidates:
            continue
        result["species_compared"] += 1
        expected = candidates[0].get("base_stats", {})
        actual = {key: editor_item.get(key) for key in ("hp", "mp", "attack", "defense", "spirit", "speed", "aptitude")}
        if all(expected.get(key) == value for key, value in actual.items()):
            result["species_exact_base_stats"] += 1
        elif len(result["mismatches"]) < 25:
            result["mismatches"].append({"kind": "species", "id": source_id, "editor": actual, "native": expected})
    for editor_item in moves:
        source_id = str(editor_item["id"])
        native = current_moves.get(f"dusk:{source_id}")
        if not native:
            continue
        result["moves_compared"] += 1
        pairs = (("mp_cost", "mp_cost"), ("primary_value", "power"), ("num_hits", "hits"))
        if all(editor_item.get(left) == native.get(right) for left, right in pairs):
            result["moves_exact_core_fields"] += 1
        elif len(result["mismatches"]) < 25:
            result["mismatches"].append({"kind": "move", "id": source_id})
    result["ok"] = not result["mismatches"]
    return result


def export_editor_data(
    rom_path: Path,
    editor_root: Path,
    output_root: Path,
    *,
    include_strings: bool = False,
) -> dict[str, Any]:
    """Export GPL-tool results without vendoring GPL source or copyrighted ROM data."""
    rom_module, loaders, constants = _load_editor(editor_root)
    source = rom_module.RomFile(str(rom_path.resolve()))
    version = source.version
    data = source.rom_data
    target = output_root / "editor_verified"
    target.mkdir(parents=True, exist_ok=True)

    species = _named_records(
        loaders.loadBaseDigimonInfo(version, data), constants.DIGIMON_ID_TO_STR
    )
    for item in species:
        stage = loaders.getDigimonStage(int(item["id"])).lower().replace("-", "_")
        item["stage"] = stage or "reserved_or_non_roster"
        item["playable_record"] = bool(stage)
    moves = _named_records(loaders.loadMoveData(version, data), constants.MOVE_ARRAY_STR)
    equipment = _named_records(
        loaders.loadEquipment(version, data), constants.ITEM_ID_TO_STR
    )
    consumables = _named_records(
        loaders.loadConsumables(version, data), constants.ITEM_ID_TO_STR
    )

    standard = []
    for source_id, record in loaders.loadStandardDigivolutions(version, data).items():
        routes = loaders.loadDigivolutionInformation(data, record.offset)
        for target_id, conditions in routes.items():
            standard.append(
                {
                    "source_id": source_id,
                    "source_name": constants.DIGIMON_ID_TO_STR.get(source_id, f"unknown_{source_id}"),
                    "target_id": target_id,
                    "target_name": constants.DIGIMON_ID_TO_STR.get(target_id, f"unknown_{target_id}"),
                    "conditions": [
                        {
                            "id": condition_id,
                            "name": constants.DIGIVOLUTION_CONDITIONS.get(condition_id, f"condition_{condition_id}"),
                            "value": value,
                        }
                        for condition_id, value in conditions
                    ],
                }
            )
    armor = [_json_value(item) for item in loaders.loadArmorDigivolutions(version, data)]
    dna, dna_conditions = loaders.loadDnaDigivolutions(version, data)
    dna_records = []
    for item in dna:
        record = _json_value(item)
        ids = [item.digimon_1_id, item.digimon_2_id, item.dna_evolution_id]
        if all(value in constants.DIGIMON_ID_TO_STR for value in ids):
            record["conditions"] = _json_value(dna_conditions.get(item.dna_evolution_id, []))
            record["digimon_1_name"] = constants.DIGIMON_ID_TO_STR[item.digimon_1_id]
            record["digimon_2_name"] = constants.DIGIMON_ID_TO_STR[item.digimon_2_id]
            record["result_name"] = constants.DIGIMON_ID_TO_STR[item.dna_evolution_id]
            dna_records.append(record)

    encounters = []
    for area in loaders.loadWildEncounterAreas(version, data):
        item = _json_value(area)
        item["location"] = loaders.getCurrentLocation(area.offset, version)
        encounters.append(item)

    exports = {
        "species.json": species,
        "moves.json": moves,
        "evolutions.json": {"standard": standard, "armor": armor, "dna": dna_records},
        "encounters.json": encounters,
        "world_map.json": [_json_value(item) for item in loaders.loadHabitatsWorldmap(version, data)],
        "items.json": {"equipment": equipment, "consumables": consumables},
        "quests.json": [_json_value(item) for item in loaders.loadQuestData(version, data)],
        "starters.json": [_json_value(item) for item in loaders.loadStarters(version, data)],
    }
    if include_strings:
        exports["strings.json"] = _json_value(loaders.loadAllStringRegions(version, data))
    for filename, value in exports.items():
        _write_json(target / filename, value)

    crosscheck = _existing_crosscheck(output_root, species, moves)
    _write_json(target / "crosscheck.json", crosscheck)
    counts = {
        "species": len(species),
        "playable_species_records": sum(bool(item["playable_record"]) for item in species),
        "moves": len(moves),
        "standard_evolutions": len(standard),
        "armor_evolutions": len(armor),
        "dna_evolutions": len(dna_records),
        "encounter_areas": len(encounters),
        "world_map_entries": len(exports["world_map.json"]),
        "equipment": len(equipment),
        "consumables": len(consumables),
        "quests": len(exports["quests.json"]),
        "starters": len(exports["starters.json"]),
    }
    manifest = {
        "schema_version": 1,
        "source_game": version,
        "source_rom": rom_path.name,
        "source_rom_sha256": hashlib.sha256(bytes(data)).hexdigest(),
        "provenance": "DigimonNDSRomEditor verified decode",
        "upstream": {"url": EDITOR_URL, "commit": _upstream_commit(editor_root)},
        "counts": counts,
        "contains_strings": include_strings,
        "crosscheck_ok": crosscheck.get("ok"),
    }
    _write_json(target / "manifest.json", manifest)
    return {**manifest, "output": str(target.resolve())}
