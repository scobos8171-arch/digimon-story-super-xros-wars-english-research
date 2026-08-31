from __future__ import annotations

import json
import statistics
import struct
from pathlib import Path
from typing import Iterable

from .nds import NdsRom
from .profiles import detect_profile, discover_roms, normalize_name, parse_dusk_strings


SCHEMA_VERSION = 1

SPECIES_NAMES = (
    "holy",
    "dark",
    "dragon",
    "beast",
    "bird",
    "machine",
    "aquan",
    "insect_plant",
    "unknown",
)
ELEMENT_NAMES = (
    "light",
    "dark",
    "fire",
    "earth",
    "wind",
    "steel",
    "water",
    "thunder",
)
TYPE_NAMES = (
    "balance",
    "attacker",
    "tank",
    "technical",
    "speed",
    "hp_type",
    "mp_type",
)
XP_CURVE_NAMES = ("early", "normal", "late")
CONDITION_NAMES = {
    0x00: "none",
    0x01: "level",
    0x02: "dragon_exp",
    0x03: "beast_exp",
    0x04: "aquan_exp",
    0x05: "bird_exp",
    0x06: "insect_plant_exp",
    0x07: "machine_exp",
    0x08: "dark_exp",
    0x09: "holy_exp",
    0x0A: "species_exp",
    0x0B: "attack",
    0x0C: "defense",
    0x0D: "speed",
    0x0E: "spirit",
    0x0F: "aptitude",
    0x10: "stress",
    0x11: "stress_alt",
    0x12: "friendship",
    0x13: "friendship_alt",
    0x14: "inventory_item",
    0x15: "party_digimon",
    0x16: "befriended_digimon",
}

# Fixed regions in the North American A6RE cartridge build. The large species
# and evolution tables are discovered from NitroFS instead of hard-coded here.
DUSK_MOVE_DATA = (0x000F9578, 0x000FCE04)
DUSK_MOVE_NAMES = (0x0010E4EC, 0x001116CC)
DUSK_TRAIT_NAMES = (0x000F8648, 0x000F9576)
DUSK_LEVEL_GROWTH = 0x00122458
DUSK_ARMOR_EVOLUTIONS = (0x0024EBC0, 0x0024EE80)
DUSK_DNA_EVOLUTIONS = (0x0024EE80, 0x00258BDC)


def _enum_name(names: tuple[str, ...], value: int, prefix: str) -> str:
    return names[value] if 0 <= value < len(names) else f"{prefix}_{value}"


def dusk_stage(internal_id: int) -> str:
    if 0x41 <= internal_id <= 0x57:
        return "in_training"
    if 0x61 <= internal_id <= 0x9D:
        return "rookie"
    if 0xA8 <= internal_id <= 0x115 and internal_id != 0xBA:
        return "champion"
    if 0x120 <= internal_id <= 0x188:
        return "ultimate"
    if 0x191 <= internal_id <= 0x1F4:
        return "mega"
    return "reserved_or_battle_only"


def _page_pointers(data: bytes, record_size: int) -> tuple[int, ...]:
    if len(data) < 4:
        raise ValueError("NitroFS data page is truncated")
    header_size = struct.unpack_from("<I", data, 0)[0]
    if header_size < 4 or header_size % 4 or header_size > len(data):
        raise ValueError(f"Invalid data-page header size 0x{header_size:X}")
    pointers = struct.unpack_from(f"<{header_size // 4}I", data, 0)
    for pointer in pointers:
        if pointer < header_size or pointer + record_size > len(data):
            raise ValueError(f"Invalid data-page record pointer 0x{pointer:X}")
    return tuple(pointers)


def _numbered_pages(rom: NdsRom, prefix: str) -> Iterable[tuple[int, bytes]]:
    matches: list[tuple[int, bytes]] = []
    normalized = prefix.strip("/") + "/"
    for item in rom.files:
        if not item.path.startswith(normalized):
            continue
        suffix = item.path[len(normalized) :]
        if suffix.isdigit():
            matches.append((int(suffix), rom.read(item)))
    return sorted(matches)


def _parse_dusk_base(rom: NdsRom) -> dict[int, dict]:
    result: dict[int, dict] = {}
    trait_names = parse_dusk_strings(
        rom.read_range(DUSK_TRAIT_NAMES[0], DUSK_TRAIT_NAMES[1] - DUSK_TRAIT_NAMES[0])
    )
    resistance_names = ELEMENT_NAMES
    for page_number, page in _numbered_pages(rom, "dat/dm"):
        for slot, pointer in enumerate(_page_pointers(page, 0x40)):
            raw = page[pointer : pointer + 0x40]
            internal_id = struct.unpack_from("<H", raw, 0)[0]
            expected_id = page_number * 8 + slot
            if internal_id != expected_id:
                raise ValueError(
                    f"Dusk base page {page_number} slot {slot} contains ID "
                    f"{internal_id}, expected {expected_id}"
                )
            level = raw[2]
            species_id = raw[3]
            hp = struct.unpack_from("<H", raw, 4)[0]
            mp, attack, defense, spirit, speed, evasion, aptitude = struct.unpack_from(
                "<7H", raw, 8
            )
            resistance_values = struct.unpack_from("<8H", raw, 0x16)
            trait_ids = list(raw[0x28:0x2C])
            support_trait_id = raw[0x2C]
            digimon_type = raw[0x2D]
            moves = list(struct.unpack_from("<5H", raw, 0x2E))
            exp_curve = struct.unpack_from("<I", raw, 0x3C)[0]
            result[internal_id] = {
                "source_internal_id": internal_id,
                "record_level": level,
                "stage": dusk_stage(internal_id),
                "species_id": species_id,
                "species": _enum_name(SPECIES_NAMES, species_id, "species"),
                "type_id": digimon_type,
                "type": _enum_name(TYPE_NAMES, digimon_type, "type"),
                "base_stats": {
                    "hp": hp,
                    "mp": mp,
                    "attack": attack,
                    "defense": defense,
                    "spirit": spirit,
                    "speed": speed,
                    "evasion": evasion,
                    "aptitude": aptitude,
                },
                "resistances": {
                    name: value for name, value in zip(resistance_names, resistance_values)
                },
                "trait_ids": trait_ids,
                "traits": [
                    trait_names[value] if value < len(trait_names) else f"trait_{value}"
                    for value in trait_ids
                ],
                "support_trait_id": support_trait_id,
                "support_trait": (
                    trait_names[support_trait_id]
                    if support_trait_id < len(trait_names)
                    else f"trait_{support_trait_id}"
                ),
                "signature_move_id": moves[0],
                "regular_move_ids": moves[1:],
                "xp_curve_id": exp_curve,
                "xp_curve": _enum_name(XP_CURVE_NAMES, exp_curve, "curve"),
                "raw_flags": {
                    "unknown_0x38": raw[0x38],
                    "dex_habitat": raw[0x39],
                    "unknown_0x3a": raw[0x3A],
                    "is_scannable": raw[0x3B],
                },
            }
    return result


def _parse_dusk_moves(rom: NdsRom) -> dict[int, dict]:
    start, end = DUSK_MOVE_DATA
    data = rom.read_range(start, end - start)
    if len(data) % 0x1C:
        raise ValueError("Dusk move table is not aligned to 0x1C-byte records")
    names = parse_dusk_strings(
        rom.read_range(DUSK_MOVE_NAMES[0], DUSK_MOVE_NAMES[1] - DUSK_MOVE_NAMES[0])
    )
    count = len(data) // 0x1C
    if len(names) != count:
        raise ValueError(f"Dusk has {count} move records but {len(names)} move names")
    result: dict[int, dict] = {}
    for index in range(count):
        raw = data[index * 0x1C : (index + 1) * 0x1C]
        move_id, mp_cost = struct.unpack_from("<HH", raw, 0)
        if move_id != index:
            raise ValueError(f"Dusk move {index} contains ID {move_id}")
        primary_effect, primary_value, secondary_effect, secondary_raw = struct.unpack_from(
            "<4H", raw, 6
        )
        secondary_value = struct.unpack("<h", struct.pack("<H", secondary_raw))[0]
        result[move_id] = {
            "id": move_id,
            "name": names[index],
            "mp_cost": mp_cost,
            "element_id": raw[4],
            "element": _enum_name(ELEMENT_NAMES, raw[4], "element"),
            "special_identifier": raw[5],
            "primary_effect": primary_effect,
            "power": primary_value,
            "secondary_effect": secondary_effect,
            "secondary_value": secondary_value,
            "is_consumable": struct.unpack_from("<H", raw, 0x10)[0],
            "hits": raw[0x12],
            "range": raw[0x13],
            "range_flags": struct.unpack_from("<H", raw, 0x14)[0],
            "unknown_0x16": struct.unpack_from("<H", raw, 0x16)[0],
            "level_learned": struct.unpack_from("<H", raw, 0x18)[0],
            "source_game": "dusk",
            "provenance": "rom_verified",
        }
    return result


def _condition(condition_id: int, value: int) -> dict:
    return {
        "id": condition_id,
        "kind": CONDITION_NAMES.get(condition_id, f"unknown_{condition_id}"),
        "value": value,
    }


def _conditions(values: tuple[int, ...] | list[int], start: int = 0) -> list[dict]:
    result: list[dict] = []
    for cursor in range(start, start + 6, 2):
        condition_id, value = int(values[cursor]), int(values[cursor + 1])
        if condition_id:
            result.append(_condition(condition_id, value))
    return result


def _parse_dusk_standard_evolutions(rom: NdsRom) -> dict[int, dict]:
    result: dict[int, dict] = {}
    for page_number, page in _numbered_pages(rom, "dat/sk"):
        for slot, pointer in enumerate(_page_pointers(page, 0x70)):
            internal_id = page_number * 8 + slot
            values = struct.unpack_from("<28I", page, pointer)
            targets = values[:4]
            routes: list[dict] = []
            devolution = None
            for target_slot, target_id in enumerate(targets):
                if target_id == 0xFFFFFFFF:
                    continue
                route = {
                    "target_source_id": target_id,
                    "conditions": _conditions(values, 4 + target_slot * 6),
                    "method": "standard",
                }
                if target_slot == 0:
                    route["method"] = "devolution"
                    devolution = route
                else:
                    routes.append(route)
            result[internal_id] = {"evolutions": routes, "devolution": devolution}
    return result


def _parse_dusk_armor_evolutions(rom: NdsRom) -> list[dict]:
    start, end = DUSK_ARMOR_EVOLUTIONS
    result: list[dict] = []
    for offset in range(start, end, 0x2C):
        values = struct.unpack("<11I", rom.read_range(offset, 0x2C))
        result.append(
            {
                "source_id": values[0],
                "item_id": values[1],
                "target_source_id": values[2],
                "conditions": _conditions(values, 3),
                "devolution_conditions": [_condition(values[9], values[10])]
                if values[9]
                else [],
                "method": "armor",
            }
        )
    return result


def _parse_dusk_dna_evolutions(rom: NdsRom) -> list[dict]:
    start, end = DUSK_DNA_EVOLUTIONS
    result: list[dict] = []
    for offset in range(start, end, 0x24):
        values = struct.unpack("<9I", rom.read_range(offset, 0x24))
        result.append(
            {
                "source_ids": [values[0], values[1]],
                "target_source_id": values[2],
                "conditions": _conditions(values, 3),
                "method": "dna",
            }
        )
    return result


def _parse_dusk_growth(rom: NdsRom) -> dict[str, dict]:
    raw = rom.read_range(DUSK_LEVEL_GROWTH, len(TYPE_NAMES) * 12)
    stat_names = ("hp", "mp", "attack", "defense", "spirit", "speed")
    result: dict[str, dict] = {}
    for type_id, type_name in enumerate(TYPE_NAMES):
        values = raw[type_id * 12 : (type_id + 1) * 12]
        result[type_name] = {
            stat: {
                "minimum": values[index * 2],
                "maximum": values[index * 2 + 1],
                "deterministic_average": (
                    values[index * 2] + values[index * 2 + 1]
                )
                / 20.0,
                "scale_divisor": 10,
            }
            for index, stat in enumerate(stat_names)
        }
    return result


def extract_dusk_mechanics(rom: NdsRom) -> dict:
    if detect_profile(rom) != "dusk":
        raise ValueError("Dusk mechanics extraction requires an A6RE ROM")
    base = _parse_dusk_base(rom)
    skills = _parse_dusk_moves(rom)
    standard = _parse_dusk_standard_evolutions(rom)
    for internal_id, routes in standard.items():
        if internal_id in base:
            base[internal_id].update(routes)
    for record in base.values():
        learnset: list[dict] = []
        for role, move_id in [
            ("signature", record["signature_move_id"]),
            *(("learned", move_id) for move_id in record["regular_move_ids"]),
        ]:
            skill = skills.get(move_id)
            if skill is None:
                continue
            learnset.append(
                {
                    "skill_id": f"dusk:{move_id}",
                    "source_move_id": move_id,
                    "role": role,
                    "level": 1 if role == "signature" else skill["level_learned"],
                }
            )
        record["learnset"] = learnset
    return {
        "base": base,
        "skills": {f"dusk:{key}": value for key, value in skills.items()},
        "growth_profiles": _parse_dusk_growth(rom),
        "armor_evolutions": _parse_dusk_armor_evolutions(rom),
        "dna_evolutions": _parse_dusk_dna_evolutions(rom),
    }


def _median_stats_by_stage(base: dict[int, dict]) -> dict[str, dict[str, int]]:
    stat_names = ("hp", "mp", "attack", "defense", "spirit", "speed", "evasion", "aptitude")
    stages: dict[str, list[dict]] = {}
    for record in base.values():
        stage = record["stage"]
        if stage == "reserved_or_battle_only" or record["base_stats"]["hp"] >= 9000:
            continue
        stages.setdefault(stage, []).append(record["base_stats"])
    result: dict[str, dict[str, int]] = {}
    for stage, records in stages.items():
        result[stage] = {
            name: int(round(statistics.median(record[name] for record in records)))
            for name in stat_names
        }
    return result


def _fallback_stage(source_ids: dict) -> str:
    lost = source_ids.get("lost_evolution", [])
    if lost:
        value = int(lost[0])
        if value <= 21:
            return "in_training"
        if value <= 62:
            return "rookie"
        if value <= 131:
            return "champion"
        if value <= 199:
            return "ultimate"
        return "mega"
    xros = source_ids.get("xros_blue", source_ids.get("xros_red", []))
    if xros:
        value = int(xros[0])
        # Super Xros Wars' fusion/special roster does not use a conventional
        # baby-to-Mega level. Keep it in its own stage instead of labelling
        # every Shoutmon combination and army unit as Mega.
        if value >= 352:
            return "xros"
        if value <= 3:
            return "in_training"
        if value <= 49:
            return "rookie"
        if value <= 132:
            return "champion"
        if value <= 232:
            return "ultimate"
        return "mega"
    return "rookie"


def _compatibility_record(item: dict, medians: dict[str, dict[str, int]]) -> dict:
    canonical_id = int(item["canonical_id"])
    stage = _fallback_stage(item.get("source_ids", {}))
    baseline = dict(medians.get(stage, medians["rookie"]))
    # A small deterministic spread prevents every source-only species from
    # being statistically identical while keeping them in a verified Dusk
    # stage envelope. These numbers are deliberately labelled estimates.
    for index, key in enumerate(("hp", "mp", "attack", "defense", "spirit", "speed")):
        spread = ((canonical_id * (index * 4 + 7)) % 11) - 5
        baseline[key] = max(1, int(round(baseline[key] * (100 + spread) / 100.0)))
    type_id = canonical_id % len(TYPE_NAMES)
    species_id = canonical_id % 8
    return {
        "canonical_id": canonical_id,
        "display_name": item.get("display_name", ""),
        "source_game": item.get("source_game", "unknown"),
        "source_internal_id": next(
            iter(item.get("source_ids", {}).get(item.get("source_game", ""), [0])), 0
        ),
        "provenance": "compatibility_estimate",
        "stage": stage,
        "species_id": species_id,
        "species": SPECIES_NAMES[species_id],
        "type_id": type_id,
        "type": TYPE_NAMES[type_id],
        "base_stats": baseline,
        "resistances": {name: 100 for name in ELEMENT_NAMES},
        "xp_curve_id": 1,
        "xp_curve": "normal",
        "learnset": [
            {"skill_id": "compat:strike", "role": "signature", "level": 1},
            {"skill_id": "compat:burst", "role": "learned", "level": 8},
        ],
        "evolutions": [],
        "devolution": None,
        "notes": (
            "Source-only Lost Evolution/Xros species. Stats are a balanced Dusk-stage "
            "compatibility profile, not asserted to be original cartridge values."
        ),
    }


def build_normalized_mechanics(rom_paths: list[Path], asset_root: Path) -> dict:
    roster_path = Path(asset_root) / "roster.json"
    if not roster_path.is_file():
        raise FileNotFoundError(f"Missing extracted roster: {roster_path}")
    asset_slots = json.loads(roster_path.read_text(encoding="utf-8"))
    roster = [
        item
        for item in asset_slots
        if normalize_name(item.get("display_name", ""))
        and not set(item.get("display_name", "")) <= {"?", "？", " ", "-"}
    ]
    dusk_rom = None
    detected: dict[str, str] = {}
    for path in rom_paths:
        rom = NdsRom(path)
        profile = detect_profile(rom)
        detected[profile] = path.name
        if profile == "dusk":
            dusk_rom = rom
    if dusk_rom is None:
        raise ValueError("A Dusk US (A6RE) ROM is required for the verified mechanics pass")

    dusk = extract_dusk_mechanics(dusk_rom)
    source_to_canonical = {
        int(source_id): int(item["canonical_id"])
        for item in roster
        for source_id in item.get("source_ids", {}).get("dusk", [])
    }
    medians = _median_stats_by_stage(dusk["base"])
    species: dict[str, dict] = {}
    verified = estimated = 0
    for item in roster:
        canonical_id = int(item["canonical_id"])
        dusk_ids = item.get("source_ids", {}).get("dusk", [])
        source_record = dusk["base"].get(int(dusk_ids[0])) if dusk_ids else None
        if source_record is None:
            record = _compatibility_record(item, medians)
            estimated += 1
        else:
            record = dict(source_record)
            record.update(
                {
                    "canonical_id": canonical_id,
                    "display_name": item.get("display_name", ""),
                    "source_game": "dusk",
                    "provenance": "rom_verified",
                }
            )
            for route in record.get("evolutions", []):
                route["target_canonical_id"] = source_to_canonical.get(
                    int(route["target_source_id"])
                )
            if record.get("devolution"):
                record["devolution"]["target_canonical_id"] = source_to_canonical.get(
                    int(record["devolution"]["target_source_id"])
                )
            verified += 1
        species[str(canonical_id)] = record

    armor: list[dict] = []
    for route in dusk["armor_evolutions"]:
        normalized = dict(route)
        normalized["canonical_id"] = source_to_canonical.get(route["source_id"])
        normalized["target_canonical_id"] = source_to_canonical.get(
            route["target_source_id"]
        )
        armor.append(normalized)
    dna: list[dict] = []
    for route in dusk["dna_evolutions"]:
        normalized = dict(route)
        normalized["canonical_ids"] = [
            source_to_canonical.get(value) for value in route["source_ids"]
        ]
        normalized["target_canonical_id"] = source_to_canonical.get(
            route["target_source_id"]
        )
        dna.append(normalized)

    skills = dict(dusk["skills"])
    skills.update(
        {
            "compat:strike": {
                "id": "compat:strike",
                "name": "Data Strike",
                "mp_cost": 4,
                "element": "neutral",
                "power": 35,
                "hits": 1,
                "level_learned": 1,
                "source_game": "original_gameplay_layer",
                "provenance": "compatibility_estimate",
            },
            "compat:burst": {
                "id": "compat:burst",
                "name": "Cross Burst",
                "mp_cost": 10,
                "element": "neutral",
                "power": 70,
                "hits": 1,
                "level_learned": 8,
                "source_game": "original_gameplay_layer",
                "provenance": "compatibility_estimate",
            },
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "sources": detected,
        "coverage": {
            "canonical_total": len(roster),
            "source_asset_slots": len(asset_slots),
            "reserved_or_unidentified_slots": len(asset_slots) - len(roster),
            "rom_verified": verified,
            "compatibility_estimate": estimated,
            "dusk_skills": len(dusk["skills"]),
            "standard_evolution_species": sum(
                bool(record.get("evolutions")) for record in dusk["base"].values()
            ),
            "armor_routes": len(armor),
            "dna_routes": len(dna),
        },
        "growth_profiles": dusk["growth_profiles"],
        "xp_model": {
            "source_field": "Dusk base record exp_curve (0 early, 1 normal, 2 late)",
            "runtime_note": (
                "Curve classification is ROM-verified. The standalone Godot level-cost "
                "formula is an original compatibility formula because the DS executable "
                "calculates thresholds in code rather than storing a discovered table."
            ),
        },
        "skills": skills,
        "species": species,
        "armor_evolutions": armor,
        "dna_evolutions": dna,
    }


def extract_mechanics(rom_paths: list[Path], asset_root: Path) -> dict:
    result = build_normalized_mechanics(rom_paths, asset_root)
    output = Path(asset_root) / "mechanics.json"
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"output": str(output.resolve()), **result["coverage"]}


def discover_and_extract_mechanics(rom_dir: Path, asset_root: Path) -> dict:
    paths = list(discover_roms(rom_dir))
    if not paths:
        raise ValueError(f"No .nds files found in {rom_dir}")
    return extract_mechanics(paths, asset_root)
