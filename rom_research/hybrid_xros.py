"""Install a playable Shoutmon X2 hybrid pilot into Digimon World: Dusk.

The patch deliberately uses mechanics the stock Dusk engine already executes:

* Shoutmon, Ballistamon, and Shoutmon X2 occupy reserved player-species IDs.
* Their Blue artwork is retargeted into three existing BTCHR.PAK slots that
  the fixed-size Dusk battle runtime can address safely.
* Ballistamon's signature technique is a high-cost Dusk move used as the
  temporary Buddy Blaster/DigiXros proxy.
* Ballistamon can permanently evolve to Shoutmon X2 only while Shoutmon is in
  the party, using Dusk's native ``DIGIMON ID IN PARTY`` condition.
* A selected starter pack is updated so both component Digimon are obtainable.

This is a compatibility implementation, not an ARM9 battle-engine rewrite.
The emitted JSON manifest records the generalized recipe and its fidelity so a
future dedicated Xros Loader command can consume the same roster mapping.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from digimon_core import constants, loaders
from digimon_core.rom import detectVersion
from rom_research.battle_sprite_import import (
    BATTLE_GROUP_SIZE,
    DUSK_BATTLE_ARCHIVE,
    DUSK_BATTLE_SIZE_MAP,
    DUSK_CHARACTER_SIZE_MAP,
    DUSK_UI_ARCHIVES,
    PLAYABLE_BATTLE_MAX_SIZE,
    STOCK_UI_SPRITE_COUNT,
    _append_ui_sprite_bindings,
    _load_nitro_file,
    _load_xros_components,
    _patch_model_binding,
    _sprite_group_components,
)
from rom_research.dusk_pak import DuskPak
from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.nitrofs_patch import _crc16, replace_nitrofs_files
from rom_research.xros_pak import find_nitro_file, read_nitro_file
from rom_research.xros_sprite import (
    SPRITE_ARCHIVES,
    parse_ncer,
    parse_ncgr,
    parse_nclr,
    render_cell_rgba,
)
from rom_research.sprite_retarget import retarget_sprite_components


EMPTY_ID = 0xFFFFFFFF
RESERVED_SPRITE_SLOT = 401
STOCK_BATTLE_SPRITE_COUNT = 415
BALLISTAMON_SPRITE_SLOT = 406
SHOUTMON_X2_SPRITE_SLOT = 408

# Existing coordinated SPR slots formerly used only by unobtainable enemy
# records. Dusk's runtime does not safely address appended UI entries.
SHOUTMON_UI_BINDING = (1054 << 16) | 1523
BALLISTAMON_UI_BINDING = (1058 << 16) | 1527
SHOUTMON_X2_UI_BINDING = (1056 << 16) | 1525

SHOUTMON_ID = 0x09E
BALLISTAMON_ID = 0x0BA
SHOUTMON_X2_ID = 0x116

# Visually verified battle entries in Blue's coordinated SPR_* archives.
# The nearby entries are DigiXros forms, so an off-by-five mapping can still
# parse correctly while displaying the wrong Digimon.
SHOUTMON_BLUE_ENTRY = 1260
BALLISTAMON_BLUE_ENTRY = 1261
SHOUTMON_X2_BLUE_ENTRY = 1266

SHOUTMON_TEMPLATE_ID = 0x062       # Agumon
BALLISTAMON_TEMPLATE_ID = 0x0A8    # Mekanorimon
SHOUTMON_X2_TEMPLATE_ID = 0x121    # MetalGreymon

DEFAULT_BUDDY_BLASTER_PROXY = 325  # Giga Blaster

# Reserved name records are ten encoded characters wide (20 bytes including
# the terminator), so the two longer names need compact in-ROM labels.
RESERVED_SHORT_NAMES = {
    "Lunamon": "Shoutmon",
    "Raremon": "Ballista",
    "Lekismon": "Shout X2",
}


@dataclass(frozen=True)
class PilotSpecies:
    name: str
    digimon_id: int
    donor_entry: int
    template_id: int
    sprite_slot: int


@dataclass(frozen=True)
class HybridRecipe:
    name: str
    initiator_id: int
    component_ids: tuple[int, ...]
    result_id: int
    temporary_move_id: int
    permanent_level: int
    temporary_mode: str = "signature_move_proxy"
    permanent_mode: str = "standard_evolution_party_condition"
    temporary_partner_check: bool = False
    permanent_partner_check: bool = True


def _species_plan(existing_sprite_count: int) -> tuple[PilotSpecies, ...]:
    if existing_sprite_count < STOCK_BATTLE_SPRITE_COUNT:
        raise ValueError(
            f"Dusk BTCHR.PAK has only {existing_sprite_count} sprite groups; "
            f"expected at least {STOCK_BATTLE_SPRITE_COUNT}"
        )

    return (
        PilotSpecies(
            "Shoutmon",
            SHOUTMON_ID,
            SHOUTMON_BLUE_ENTRY,
            SHOUTMON_TEMPLATE_ID,
            RESERVED_SPRITE_SLOT,
        ),
        PilotSpecies(
            "Ballistamon",
            BALLISTAMON_ID,
            BALLISTAMON_BLUE_ENTRY,
            BALLISTAMON_TEMPLATE_ID,
            BALLISTAMON_SPRITE_SLOT,
        ),
        PilotSpecies(
            "Shoutmon X2",
            SHOUTMON_X2_ID,
            SHOUTMON_X2_BLUE_ENTRY,
            SHOUTMON_X2_TEMPLATE_ID,
            SHOUTMON_X2_SPRITE_SLOT,
        ),
    )


def _u32_at(data: bytes | bytearray, index: int) -> int:
    return struct.unpack_from("<I", data, index * 4)[0]


def _set_u32(data: bytearray, index: int, value: int) -> None:
    offset = index * 4
    if offset == len(data):
        data.extend(struct.pack("<I", value))
    elif offset + 4 <= len(data):
        struct.pack_into("<I", data, offset, value)
    else:
        raise ValueError("Parallel sprite-size map has a partial trailing entry")


def _tiles_per_cell(components: dict[str, bytes]) -> int:
    graphics = parse_ncgr(components["graphics"])
    cell_count = len(parse_ncer(components["cells"]))
    return len(graphics.tiles) // max(1, cell_count)


def _install_sprite_groups(
    dusk_rom: Path,
    xros_rom: Path,
    target_data: bytearray,
) -> tuple[
    bytes,
    bytes,
    bytes,
    dict[str, bytes],
    tuple[PilotSpecies, ...],
    dict[int, dict[str, bytes]],
]:
    target_archive = DuskPak.from_bytes(
        _load_nitro_file(dusk_rom, DUSK_BATTLE_ARCHIVE)
    )
    if len(target_archive.entries) % BATTLE_GROUP_SIZE:
        raise ValueError("Dusk BTCHR.PAK entry count is not divisible by five")
    existing_count = len(target_archive.entries) // BATTLE_GROUP_SIZE
    species = _species_plan(existing_count)

    sprite_map = loaders.loadSpriteMapTable(detectVersion(target_data), target_data)
    battle_strings = loaders.loadBattleStringTable(
        detectVersion(target_data), target_data
    )
    original_name_links = {
        item.digimon_id: (
            battle_strings[item.digimon_id].offset,
            battle_strings[item.digimon_id].value,
        )
        for item in species
    }
    for item in species:
        if item.sprite_slot >= existing_count:
            continue
        users = [
            index
            for index, entry in enumerate(sprite_map)
            if entry.main_sprite == item.sprite_slot
        ]
        displaced_users = {
            BALLISTAMON_SPRITE_SLOT: {0x205},  # stock "????" enemy
            SHOUTMON_X2_SPRITE_SLOT: {0x209},  # X2 Clone story boss
        }
        allowed = {item.digimon_id, *displaced_users.get(item.sprite_slot, set())}
        if set(users) - allowed:
            raise ValueError(
                f"Battle sprite slot {item.sprite_slot} is used by IDs "
                f"{sorted(set(users) - allowed)[:12]}"
            )

    raw_donors = {
        item.digimon_id: _load_xros_components(xros_rom, item.donor_entry)
        for item in species
    }
    donors: dict[int, dict[str, bytes]] = {}
    replacements: dict[int, bytes] = {}
    appended: list[tuple[bytes, bool]] = []

    next_append_slot = existing_count
    for item in species:
        template_sprite = sprite_map[item.template_id].main_sprite
        metadata_index = template_sprite * BATTLE_GROUP_SIZE
        if metadata_index >= len(target_archive.entries):
            raise ValueError(
                f"{item.name} template sprite {template_sprite} has no metadata"
            )
        metadata = target_archive.unpacked_data(metadata_index)
        metadata_compressed = target_archive.entries[metadata_index].compressed
        donor = retarget_sprite_components(
            raw_donors[item.digimon_id],
            _sprite_group_components(target_archive, template_sprite),
            maximum_size=PLAYABLE_BATTLE_MAX_SIZE,
        )
        donors[item.digimon_id] = donor
        if item.sprite_slot < existing_count:
            base = item.sprite_slot * BATTLE_GROUP_SIZE
            # Battle metadata contains frame placement and animation-role
            # values. The old reserved slot has a shorter dummy record, so it
            # cannot safely drive a real imported sprite.
            replacements[base] = metadata
            for component_index, kind in enumerate(SPRITE_ARCHIVES, start=1):
                replacements[base + component_index] = donor[kind]
            continue
        if item.sprite_slot != next_append_slot:
            raise ValueError(
                f"New battle sprite slots must be sequential; expected "
                f"{next_append_slot}, got {item.sprite_slot}"
            )
        appended.append((metadata, metadata_compressed))
        for kind in SPRITE_ARCHIVES:
            appended.append((donor[kind], True))
        next_append_slot += 1

    rebuilt_archive = target_archive.rebuild(
        replacements,
        appended_entries=tuple(appended),
    )

    size_map = bytearray(_load_nitro_file(dusk_rom, DUSK_BATTLE_SIZE_MAP))
    character_map = bytearray(_load_nitro_file(dusk_rom, DUSK_CHARACTER_SIZE_MAP))
    if len(size_map) != existing_count * 4 or len(character_map) != existing_count * 4:
        raise ValueError("Dusk battle sprite maps do not match BTCHR.PAK")

    for item in species:
        donor = donors[item.digimon_id]
        component_total = sum(len(donor[kind]) for kind in SPRITE_ARCHIVES)
        _set_u32(size_map, item.sprite_slot, component_total)
        character_value = (
            (_tiles_per_cell(donor) << 16) | (item.digimon_id & 0xFFFF)
        )
        _set_u32(character_map, item.sprite_slot, character_value)

        _patch_model_binding(
            target_data,
            digimon_id=item.digimon_id,
            target_sprite=item.sprite_slot,
            template_id=item.template_id,
        )

    ui_target_bindings = {
        SHOUTMON_ID: SHOUTMON_UI_BINDING,
        BALLISTAMON_ID: BALLISTAMON_UI_BINDING,
        SHOUTMON_X2_ID: SHOUTMON_X2_UI_BINDING,
    }
    ui_replacements, upper_bindings = _append_ui_sprite_bindings(
        dusk_rom,
        tuple(
            (
                raw_donors[item.digimon_id],
                sprite_map[item.template_id].upperscreen_sprites,
                ui_target_bindings[item.digimon_id],
            )
            for item in species
        ),
    )
    patched_sprite_map = loaders.loadSpriteMapTable(
        detectVersion(target_data),
        target_data,
    )
    for item, binding in zip(species, upper_bindings):
        patched_sprite_map[item.digimon_id].upperscreen_sprites = binding
        patched_sprite_map[item.digimon_id].writeToRom(target_data)

    # The generic single-sprite importer aliases a template name. The hybrid
    # pilot instead keeps each reserved slot's original link, then replaces its
    # stock "Undecided" short-name record below.
    for offset, value in original_name_links.values():
        target_data[offset:offset + 4] = value.to_bytes(4, "little")

    return (
        rebuilt_archive,
        bytes(size_map),
        bytes(character_map),
        ui_replacements,
        species,
        donors,
    )


def _install_reserved_short_names(rom_data: bytearray, version: str) -> int:
    """Replace the three contextual ``Undecided`` labels in a fixed budget."""

    regions = loaders.loadAllStringRegions(version, rom_data)
    records = regions.get("arm9_digiegg_enemy_names", [])
    replacements = 0
    seen: set[str] = set()
    for index, record in enumerate(records[:-1]):
        replacement = RESERVED_SHORT_NAMES.get(record.text)
        if replacement is None:
            continue
        candidate = records[index + 1]
        if candidate.text != "Undecided":
            continue
        candidate.text = replacement
        if not candidate.fits():
            raise ValueError(
                f"Reserved short name {replacement!r} does not fit its ROM slot"
            )
        candidate.writeToRom(rom_data)
        replacements += 1
        seen.add(record.text)
    missing = set(RESERVED_SHORT_NAMES) - seen
    if missing:
        raise ValueError(
            f"Could not find reserved name slots after: {sorted(missing)}"
        )
    return replacements


def _set_evolution_group(
    record: Any,
    slot: int,
    target_id: int,
    conditions: tuple[tuple[int, int], tuple[int, int], tuple[int, int]],
) -> None:
    setattr(record, f"evolution_{slot}_id", target_id)
    for condition_slot, (condition_id, value) in enumerate(conditions, start=1):
        setattr(record, f"evo_{slot}_condition_id_{condition_slot}", condition_id)
        setattr(record, f"evo_{slot}_condition_value_{condition_slot}", value)


def _install_gameplay_records(
    rom_data: bytearray,
    *,
    starter_pack: int,
    fusion_level: int,
    buddy_move_id: int,
) -> None:
    version = detectVersion(rom_data)
    if version != "DUSK_US":
        raise ValueError("The hybrid pilot currently targets Digimon World: Dusk (USA)")
    if not 0 <= buddy_move_id < len(loaders.loadMoveData(version, rom_data)):
        raise IndexError(f"Buddy Blaster proxy move {buddy_move_id} is out of range")
    if not 1 <= fusion_level <= 99:
        raise ValueError("Fusion level must be between 1 and 99")
    if not 0 <= starter_pack < 4:
        raise ValueError("Starter pack must be between 0 and 3")

    _install_reserved_short_names(rom_data, version)
    base = loaders.loadBaseDigimonInfo(version, rom_data)
    standards = loaders.loadStandardDigivolutions(version, rom_data)

    # Temporary DigiXros compatibility layer. Blue gives Buddy Blaster to
    # Ballistamon as the initiator; Dusk executes the selected native move as
    # its signature technique.
    ballistamon = base[BALLISTAMON_ID]
    ballistamon.move_signature = buddy_move_id
    ballistamon.writeToRom(rom_data)

    # Permanent DigiFusion compatibility layer. The target slot is otherwise
    # unused in the stock Ballistamon placeholder record.
    source = standards[BALLISTAMON_ID]
    free_slot = next(
        (
            slot
            for slot in (1, 2, 3)
            if getattr(source, f"evolution_{slot}_id") == EMPTY_ID
        ),
        None,
    )
    if free_slot is None:
        # Idempotent reinstall may find the recipe already present.
        free_slot = next(
            (
                slot
                for slot in (1, 2, 3)
                if getattr(source, f"evolution_{slot}_id") == SHOUTMON_X2_ID
            ),
            None,
        )
    if free_slot is None:
        raise ValueError("Ballistamon has no free evolution slot")
    _set_evolution_group(
        source,
        free_slot,
        SHOUTMON_X2_ID,
        (
            (0x01, fusion_level),       # LEVEL
            (0x15, SHOUTMON_ID),        # DIGIMON ID IN PARTY
            (0x00, 0),
        ),
    )
    source.writeToRom(rom_data)

    result = standards[SHOUTMON_X2_ID]
    result.degen_evo_id = BALLISTAMON_ID
    result.degen_condition_id_1 = 0x01
    result.degen_condition_value_1 = 1
    result.degen_condition_id_2 = 0
    result.degen_condition_value_2 = 0
    result.degen_condition_id_3 = 0
    result.degen_condition_value_3 = 0
    result.writeToRom(rom_data)

    # Make the recipe testable from a new game without save editing. Preserve
    # slot three of the selected pack, replacing only its first two members.
    starters = loaders.loadStarters(version, rom_data)
    first = starter_pack * 3
    for starter, digimon_id in zip(
        starters[first:first + 2],
        (SHOUTMON_ID, BALLISTAMON_ID),
    ):
        starter.digimon_id = digimon_id
        starter.level = min(20, base[digimon_id].aptitude)
        starter.writeToRom(rom_data)


def _manifest(
    species: tuple[PilotSpecies, ...],
    recipe: HybridRecipe,
    *,
    starter_pack: int,
    output_rom: Path,
    output_sha256: str,
) -> dict[str, Any]:
    return {
        "format": "digimon_nds_hybrid_xros_v1",
        "preset": "shoutmon_x2_playable_pilot",
        "output_rom": output_rom.name,
        "output_sha256": output_sha256,
        "species": [asdict(item) for item in species],
        "recipe": {
            **asdict(recipe),
            "component_ids": list(recipe.component_ids),
        },
        "starter_pack": starter_pack + 1,
        "name_fidelity": {
            "editor_labels": "English hybrid names",
            "rom_short_labels": {
                "Shoutmon": "Shoutmon",
                "Ballistamon": "Ballista",
                "Shoutmon X2": "Shout X2",
            },
            "full_name_contexts": (
                "Some full-name screens can remain blank until the packed "
                "name table is relocated"
            ),
        },
        "mechanic_fidelity": {
            "temporary_digixros": (
                "Playable signature-move proxy; stock Dusk does not enforce "
                "the partner check during battle"
            ),
            "permanent_digifusion": (
                "Native Dusk evolution with level and required-party-Digimon checks"
            ),
        },
    }


def install_shoutmon_x2_pilot(
    dusk_rom: Path,
    xros_rom: Path,
    output_rom: Path,
    *,
    starter_pack: int = 0,
    fusion_level: int = 20,
    buddy_move_id: int = DEFAULT_BUDDY_BLASTER_PROXY,
    write_manifest: bool = True,
) -> dict[str, Any]:
    """Build and verify a playable hybrid ROM without modifying either input."""

    dusk_rom = Path(dusk_rom)
    xros_rom = Path(xros_rom)
    output_rom = Path(output_rom)
    if output_rom.resolve() in {dusk_rom.resolve(), xros_rom.resolve()}:
        raise ValueError("Output ROM must be different from both source ROMs")

    target_data = bytearray(dusk_rom.read_bytes())
    if detectVersion(target_data, str(dusk_rom)) != "DUSK_US":
        raise ValueError("Target must be Digimon World: Dusk (USA)")

    (
        archive,
        size_map,
        character_map,
        ui_replacements,
        species,
        _donors,
    ) = _install_sprite_groups(
        dusk_rom,
        xros_rom,
        target_data,
    )
    _install_gameplay_records(
        target_data,
        starter_pack=starter_pack,
        fusion_level=fusion_level,
        buddy_move_id=buddy_move_id,
    )

    patched = replace_nitrofs_files(
        target_data,
        {
            DUSK_BATTLE_ARCHIVE: archive,
            DUSK_BATTLE_SIZE_MAP: size_map,
            DUSK_CHARACTER_SIZE_MAP: character_map,
            **ui_replacements,
        },
    )
    output_rom.parent.mkdir(parents=True, exist_ok=True)
    output_rom.write_bytes(patched)

    recipe = HybridRecipe(
        name="Buddy Blaster / Shoutmon X2",
        initiator_id=BALLISTAMON_ID,
        component_ids=(SHOUTMON_ID,),
        result_id=SHOUTMON_X2_ID,
        temporary_move_id=buddy_move_id,
        permanent_level=fusion_level,
    )
    verification = verify_shoutmon_x2_pilot(
        output_rom,
        xros_rom,
        starter_pack=starter_pack,
        fusion_level=fusion_level,
        buddy_move_id=buddy_move_id,
    )
    output_sha256 = hashlib.sha256(output_rom.read_bytes()).hexdigest()
    manifest = _manifest(
        species,
        recipe,
        starter_pack=starter_pack,
        output_rom=output_rom,
        output_sha256=output_sha256,
    )
    manifest["verification"] = verification
    manifest_path = output_rom.with_name(output_rom.name + ".xros.json")
    if write_manifest:
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return {
        "output_rom": str(output_rom),
        "manifest": str(manifest_path) if write_manifest else "",
        "sha256": output_sha256,
        "species_count": len(species),
        "battle_sprite_count": verification["battle_sprite_count"],
        "starter_pack": starter_pack + 1,
        "fusion_level": fusion_level,
        "buddy_move_id": buddy_move_id,
        "verified": True,
    }


def verify_shoutmon_x2_pilot(
    output_rom: Path,
    xros_rom: Path,
    *,
    starter_pack: int = 0,
    fusion_level: int = 20,
    buddy_move_id: int = DEFAULT_BUDDY_BLASTER_PROXY,
) -> dict[str, Any]:
    output_rom = Path(output_rom)
    xros_rom = Path(xros_rom)
    output_data = bytearray(output_rom.read_bytes())
    version = detectVersion(output_data, str(output_rom))
    if version != "DUSK_US":
        raise AssertionError(f"Patched ROM identifies as {version}, not DUSK_US")
    if struct.unpack_from("<H", output_data, 0x15E)[0] != _crc16(output_data[:0x15E]):
        raise AssertionError("Patched ROM header CRC is invalid")

    base = loaders.loadBaseDigimonInfo(version, output_data)
    standards = loaders.loadStandardDigivolutions(version, output_data)
    sprites = loaders.loadSpriteMapTable(version, output_data)
    starters = loaders.loadStarters(version, output_data)
    string_regions = loaders.loadAllStringRegions(version, output_data)

    for digimon_id in (SHOUTMON_ID, BALLISTAMON_ID, SHOUTMON_X2_ID):
        if base[digimon_id].hp == 9999:
            raise AssertionError(f"Reserved ID 0x{digimon_id:03X} still has dummy stats")
    if base[BALLISTAMON_ID].move_signature != buddy_move_id:
        raise AssertionError("Ballistamon does not have the DigiXros proxy move")

    ballistamon_evolutions = [
        (
            slot,
            getattr(standards[BALLISTAMON_ID], f"evolution_{slot}_id"),
        )
        for slot in (1, 2, 3)
    ]
    fusion_slot = next(
        (slot for slot, target in ballistamon_evolutions if target == SHOUTMON_X2_ID),
        None,
    )
    if fusion_slot is None:
        raise AssertionError("Ballistamon -> Shoutmon X2 recipe is missing")
    source = standards[BALLISTAMON_ID]
    conditions = {
        (
            getattr(source, f"evo_{fusion_slot}_condition_id_{index}"),
            getattr(source, f"evo_{fusion_slot}_condition_value_{index}"),
        )
        for index in (1, 2, 3)
    }
    if (0x01, fusion_level) not in conditions:
        raise AssertionError("Fusion level condition is missing")
    if (0x15, SHOUTMON_ID) not in conditions:
        raise AssertionError("Shoutmon-in-party condition is missing")
    if standards[SHOUTMON_X2_ID].degen_evo_id != BALLISTAMON_ID:
        raise AssertionError("Shoutmon X2 degeneration link is missing")

    first = starter_pack * 3
    if [starters[first].digimon_id, starters[first + 1].digimon_id] != [
        SHOUTMON_ID,
        BALLISTAMON_ID,
    ]:
        raise AssertionError("Selected starter pack does not contain the Xros pair")

    short_name_records = string_regions.get("arm9_digiegg_enemy_names", [])
    short_names = {record.text for record in short_name_records}
    expected_short_names = set(RESERVED_SHORT_NAMES.values())
    if not expected_short_names.issubset(short_names):
        raise AssertionError("Reserved English short-name records are missing")

    with output_rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        archive = DuskPak.from_bytes(
            read_nitro_file(handle, find_nitro_file(files, DUSK_BATTLE_ARCHIVE))
        )
        size_map = read_nitro_file(
            handle, find_nitro_file(files, DUSK_BATTLE_SIZE_MAP)
        )
        character_map = read_nitro_file(
            handle, find_nitro_file(files, DUSK_CHARACTER_SIZE_MAP)
        )
        ui_archives = {
            kind: DuskPak.from_bytes(
                read_nitro_file(handle, find_nitro_file(files, path))
            )
            for kind, path in DUSK_UI_ARCHIVES.items()
        }
    sprite_count = len(archive.entries) // BATTLE_GROUP_SIZE
    if sprite_count != STOCK_BATTLE_SPRITE_COUNT:
        raise AssertionError(
            "BTCHR.PAK was expanded beyond Dusk's runtime-safe 415 slots"
        )
    for kind, ui_archive in ui_archives.items():
        if len(ui_archive.entries) != STOCK_UI_SPRITE_COUNT:
            raise AssertionError(
                f"{kind} UI archive was expanded beyond Dusk's runtime-safe "
                f"{STOCK_UI_SPRITE_COUNT} entries"
            )
    species = _species_plan(sprite_count)
    if len(size_map) != sprite_count * 4 or len(character_map) != sprite_count * 4:
        raise AssertionError("Expanded sprite size maps do not match BTCHR.PAK")

    rendered_frames = 0
    rendered_opaque_pixels = 0
    ui_sprites_rendered = 0
    for item in species:
        if sprites[item.digimon_id].main_sprite != item.sprite_slot:
            raise AssertionError(f"{item.name} sprite-map binding is incorrect")
        raw_donor = _load_xros_components(xros_rom, item.donor_entry)
        group = item.sprite_slot * BATTLE_GROUP_SIZE
        template_sprite = sprites[item.template_id].main_sprite
        donor = retarget_sprite_components(
            raw_donor,
            _sprite_group_components(archive, template_sprite),
            maximum_size=PLAYABLE_BATTLE_MAX_SIZE,
        )
        for component_index, kind in enumerate(SPRITE_ARCHIVES, start=1):
            if archive.unpacked_data(group + component_index) != donor[kind]:
                raise AssertionError(
                    f"{item.name} {kind} is not retargeted to its Dusk template"
                )
        template_metadata = archive.unpacked_data(
            template_sprite * BATTLE_GROUP_SIZE
        )
        if archive.unpacked_data(group) != template_metadata:
            raise AssertionError(
                f"{item.name} battle metadata does not match its Dusk template"
            )
        expected_size = sum(len(donor[kind]) for kind in SPRITE_ARCHIVES)
        if _u32_at(size_map, item.sprite_slot) != expected_size:
            raise AssertionError(f"{item.name} size-map entry is incorrect")
        if _u32_at(character_map, item.sprite_slot) & 0xFFFF != item.digimon_id:
            raise AssertionError(f"{item.name} character-map ID is incorrect")
        graphics = parse_ncgr(donor["graphics"])
        palette = parse_nclr(donor["palette"])
        cells = parse_ncer(donor["cells"])
        for cell_index, cell in enumerate(cells):
            rendered = render_cell_rgba(graphics, palette, cell)
            opaque_pixels = sum(rendered.pixels[3::4]) // 255
            if not opaque_pixels:
                raise AssertionError(
                    f"{item.name} battle frame {cell_index} renders blank"
                )
            if rendered.width > 256 or rendered.height > 192:
                raise AssertionError(
                    f"{item.name} battle frame {cell_index} exceeds 256x192"
                )
            rendered_frames += 1
            rendered_opaque_pixels += opaque_pixels

        upper = sprites[item.digimon_id].upperscreen_sprites
        status_icon = sprites[item.digimon_id].unknown_0x4
        upper_ids = (upper & 0xFFFF, upper >> 16)
        template_upper = sprites[item.template_id].upperscreen_sprites
        if upper == template_upper:
            raise AssertionError(f"{item.name} still uses its template UI sprites")
        expected_upper = {
            SHOUTMON_ID: SHOUTMON_UI_BINDING,
            BALLISTAMON_ID: BALLISTAMON_UI_BINDING,
            SHOUTMON_X2_ID: SHOUTMON_X2_UI_BINDING,
        }[item.digimon_id]
        if upper != expected_upper:
            raise AssertionError(
                f"{item.name} does not use its runtime-safe existing UI slots"
            )
        if status_icon != sprites[item.template_id].unknown_0x4:
            raise AssertionError(
                f"{item.name} does not preserve its Dusk status/effect binding"
            )
        for upper_id in upper_ids:
            if upper_id >= len(ui_archives["graphics"].entries):
                raise AssertionError(f"{item.name} UI sprite is out of range")
            graphics = parse_ncgr(ui_archives["graphics"].unpacked_data(upper_id))
            palette = parse_nclr(ui_archives["palette"].unpacked_data(upper_id))
            cells = parse_ncer(ui_archives["cells"].unpacked_data(upper_id))
            rendered = render_cell_rgba(graphics, palette, cells[0])
            if not sum(rendered.pixels[3::4]):
                raise AssertionError(f"{item.name} UI sprite renders blank")
            ui_sprites_rendered += 1

    return {
        "rom_version": version,
        "header_crc": "ok",
        "battle_sprite_count": sprite_count,
        "blue_components_verified": len(species) * 4,
        "base_records_verified": len(species),
        "short_names_verified": len(expected_short_names),
        "temporary_proxy_move": buddy_move_id,
        "permanent_recipe": "ok",
        "starter_pack": starter_pack + 1,
        "battle_frames_rendered": rendered_frames,
        "battle_opaque_pixels": rendered_opaque_pixels,
        "ui_sprites_rendered": ui_sprites_rendered,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dusk_rom", type=Path)
    parser.add_argument("xros_rom", type=Path)
    parser.add_argument("output_rom", type=Path)
    parser.add_argument("--starter-pack", type=int, default=1, choices=range(1, 5))
    parser.add_argument("--fusion-level", type=int, default=20)
    parser.add_argument(
        "--buddy-move",
        type=lambda value: int(value, 0),
        default=DEFAULT_BUDDY_BLASTER_PROXY,
    )
    parser.add_argument("--no-manifest", action="store_true")
    args = parser.parse_args()
    result = install_shoutmon_x2_pilot(
        args.dusk_rom,
        args.xros_rom,
        args.output_rom,
        starter_pack=args.starter_pack - 1,
        fusion_level=args.fusion_level,
        buddy_move_id=args.buddy_move,
        write_manifest=not args.no_manifest,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
