"""Build the playable Digimon World Dusk: Xros Rift campaign patch.

The campaign preserves Dusk's event scripts and progression flags while
changing the layer those scripts present:

* two starter packs use the Xros roster and two use custom stock teams;
* Dorulumon and Sparrowmon join the playable Shoutmon X2 pilot roster;
* three Dusk story bosses use Bagra Army sprites and one uses a corrupted
  Shoutmon X2 clone, all without adding unsupported battle slots;
* key locations and dialogue tell a coherent Xros Rift crossover story;
* random encounters occur about 60% less often;
* the base scan/data setting is tripled from 15 to 45.

This is a compatibility campaign, not a transplant of Blue's incompatible
map/event engine. Existing Dusk maps and event triggers remain the stable
playability foundation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from digimon_core import constants, loaders
from digimon_core.rom import detectVersion
from rom_research.battle_sprite_import import (
    BATTLE_GROUP_SIZE,
    BOSS_BATTLE_MAX_SIZE,
    DUSK_BATTLE_ARCHIVE,
    PLAYABLE_BATTLE_MAX_SIZE,
    _load_nitro_file,
    _load_xros_components,
    _sprite_group_components,
    import_battle_sprite,
)
from rom_research.dusk_pak import DuskPak
from rom_research.hybrid_xros import (
    BALLISTAMON_ID,
    SHOUTMON_ID,
    SHOUTMON_X2_ID,
    install_shoutmon_x2_pilot,
    verify_shoutmon_x2_pilot,
)
from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.nitrofs_patch import _crc16
from rom_research.xros_pak import find_nitro_file, read_nitro_file
from rom_research.xros_sprite import (
    DuskSpriteSet,
    SPRITE_ARCHIVES,
    parse_ncer,
    parse_ncgr,
    parse_nclr,
    render_cell_rgba,
)
from rom_research.sprite_retarget import retarget_sprite_components


DORULUMON_ID = 0x09F
SPARROWMON_ID = 0x117
GUILMON_ID = 0x064
PATAMON_ID = 0x068
TERRIERMON_ID = 0x077
RENAMON_ID = 0x079
CORONAMON_ID = 0x09C
LUNAMON_ID = 0x09D

DORULUMON_TEMPLATE_ID = 0x065
SPARROWMON_TEMPLATE_ID = 0x07C

SCAN_RATE = 45
ENCOUNTER_RATE_NUMERATOR = 5
ENCOUNTER_RATE_DENOMINATOR = 2


def _validate_sprite_components(
    label: str,
    components: dict[str, bytes],
) -> dict[str, int]:
    """Validate and software-render every frame of one battle sprite."""

    graphics = parse_ncgr(components["graphics"])
    palette = parse_nclr(components["palette"])
    cells = parse_ncer(components["cells"])
    if not graphics.tiles or not palette or not cells:
        raise AssertionError(f"{label} has an empty graphics resource")

    animation = components["animation"]
    if len(animation) < 16 or animation[:4] != b"RNAN":
        raise AssertionError(f"{label} has an invalid NANR animation")
    declared_animation_size = struct.unpack_from("<I", animation, 8)[0]
    if declared_animation_size != len(animation):
        raise AssertionError(
            f"{label} NANR declares {declared_animation_size} bytes, "
            f"but contains {len(animation)}"
        )

    rendered_frames = 0
    opaque_pixels = 0
    for cell_index, cell in enumerate(cells):
        for oam_index, oam in enumerate(cell.oams):
            width, height = oam.dimensions
            address_scale = 4 if oam.colors == 16 else 2
            partition_scale = 32 if oam.colors == 16 else 64
            first_tile = (
                oam.character * address_scale
                + cell.partition_offset // partition_scale
            )
            tile_count = width * height // 64
            if first_tile + tile_count > len(graphics.tiles):
                raise AssertionError(
                    f"{label} cell {cell_index} OAM {oam_index} references "
                    "tiles outside its NCGR"
                )
        rendered = render_cell_rgba(graphics, palette, cell)
        frame_pixels = sum(rendered.pixels[3::4]) // 255
        if frame_pixels:
            rendered_frames += 1
            opaque_pixels += frame_pixels
        if rendered.width > 256 or rendered.height > 192:
            raise AssertionError(
                f"{label} frame {cell_index} is {rendered.width}x"
                f"{rendered.height}, outside a Nintendo DS screen"
            )
    if rendered_frames != len(cells):
        raise AssertionError(
            f"{label} rendered only {rendered_frames} of {len(cells)} frames"
        )
    return {
        "tiles": len(graphics.tiles),
        "palette_colors": len(palette),
        "frames": rendered_frames,
        "opaque_pixels": opaque_pixels,
    }


def _verify_roster_and_progression(
    rom_data: bytearray,
    version: str,
) -> dict[str, int]:
    """Check every parsed combatant, move link, encounter, and evolution."""

    base = loaders.loadBaseDigimonInfo(version, rom_data)
    enemies = loaders.loadEnemyDigimonInfo(version, rom_data)
    moves = loaders.loadMoveData(version, rom_data)
    standards = loaders.loadStandardDigivolutions(version, rom_data)
    armor = loaders.loadArmorDigivolutions(version, rom_data)
    dna, _dna_conditions = loaders.loadDnaDigivolutions(version, rom_data)
    starters = loaders.loadStarters(version, rom_data)
    encounter_areas = loaders.loadWildEncounterAreas(version, rom_data)
    encounter_rewards = loaders.loadEncounterRewardData(version, rom_data)

    def check_move(owner: str, move_id: int) -> None:
        if move_id != 0xFFFF and not 0 <= move_id < len(moves):
            raise AssertionError(f"{owner} references invalid move {move_id}")

    for index, move in enumerate(moves):
        if move.id != index:
            raise AssertionError(f"Move slot {index} stores ID {move.id}")
        if not 1 <= move.num_hits <= 4:
            raise AssertionError(f"Move {index} has invalid hit count {move.num_hits}")

    for digimon_id, record in base.items():
        if record.id != digimon_id:
            raise AssertionError(f"Base slot {digimon_id} stores ID {record.id}")
        if not 1 <= record.hp <= 9999 or not 1 <= record.mp <= 9999:
            raise AssertionError(f"Base Digimon {digimon_id} has invalid HP/MP")
        for field in ("attack", "defense", "spirit", "speed", "evasion"):
            if not 0 <= getattr(record, field) <= 999:
                raise AssertionError(
                    f"Base Digimon {digimon_id} has invalid {field}"
                )
        if not 1 <= record.aptitude <= 99:
            raise AssertionError(f"Base Digimon {digimon_id} has invalid aptitude")
        if not 0 <= record.exp_curve <= 2:
            raise AssertionError(f"Base Digimon {digimon_id} has invalid EXP curve")
        for move_id in (record.move_signature, *record.getRegularMoves()):
            check_move(f"Base Digimon {digimon_id}", move_id)

    for enemy_id, record in enemies.items():
        if record.id != enemy_id:
            raise AssertionError(f"Enemy slot {enemy_id} stores ID {record.id}")
        if not 0 <= record.level <= 99 or record.hp <= 0 or record.mp <= 0:
            raise AssertionError(f"Enemy {enemy_id} has invalid level or HP/MP")
        for move_id in (
            record.move_signature,
            record.move_1,
            record.move_2,
            record.move_3,
            record.move_4,
        ):
            check_move(f"Enemy {enemy_id}", move_id)

    valid_condition_ids = set(range(0x17))

    def check_target(owner: str, target: int) -> None:
        if target != 0xFFFFFFFF and target not in base:
            raise AssertionError(f"{owner} references invalid Digimon {target}")

    def check_condition(owner: str, condition_id: int, value: int) -> None:
        if condition_id not in valid_condition_ids:
            raise AssertionError(
                f"{owner} uses invalid condition 0x{condition_id:X}"
            )
        if condition_id in {0x15, 0x16} and value not in base:
            raise AssertionError(
                f"{owner} requires invalid Digimon ID {value}"
            )

    for digimon_id, record in standards.items():
        targets = (
            record.degen_evo_id,
            record.evolution_1_id,
            record.evolution_2_id,
            record.evolution_3_id,
        )
        for target in targets:
            check_target(f"Standard progression {digimon_id}", target)
        groups = ("degen", "evo_1", "evo_2", "evo_3")
        for group in groups:
            for condition_index in (1, 2, 3):
                check_condition(
                    f"Standard progression {digimon_id}",
                    getattr(record, f"{group}_condition_id_{condition_index}"),
                    getattr(record, f"{group}_condition_value_{condition_index}"),
                )

    for index, record in enumerate(armor):
        check_target(f"Armor progression {index}", record.digimon_id)
        check_target(f"Armor progression {index}", record.evolution_id)
        for condition_index in (1, 2, 3):
            check_condition(
                f"Armor progression {index}",
                getattr(record, f"condition_id_{condition_index}"),
                getattr(record, f"condition_value_{condition_index}"),
            )
        check_condition(
            f"Armor degeneration {index}",
            record.degen_condition_id,
            record.degen_condition_value,
        )

    for index, record in enumerate(dna):
        for target in (
            record.digimon_1_id,
            record.digimon_2_id,
            record.dna_evolution_id,
        ):
            check_target(f"DNA progression {index}", target)
        for condition_index in (1, 2, 3):
            check_condition(
                f"DNA progression {index}",
                getattr(record, f"condition_id_{condition_index}"),
                getattr(record, f"condition_value_{condition_index}"),
            )

    for index, starter in enumerate(starters):
        if starter.digimon_id not in base:
            raise AssertionError(f"Starter {index} references an invalid Digimon")
        if not 1 <= starter.level <= base[starter.digimon_id].aptitude:
            raise AssertionError(
                f"Starter {index} level exceeds its legal aptitude"
            )

    encounter_count = 0
    for area_index, area in enumerate(encounter_areas):
        if area.num_encounters != len(area.encounters):
            raise AssertionError(
                f"Encounter area {area_index} count does not match its records"
            )
        for encounter in area.encounters:
            if encounter.digimon_id not in enemies:
                raise AssertionError(
                    f"Encounter area {area_index} references missing enemy "
                    f"{encounter.digimon_id}"
                )
            if encounter.reward_slot >= len(encounter_rewards):
                raise AssertionError(
                    f"Encounter area {area_index} has invalid reward slot "
                    f"{encounter.reward_slot}"
                )
            encounter_count += 1

    return {
        "base_digimon_records": len(base),
        "enemy_combat_records": len(enemies),
        "move_damage_records": len(moves),
        "standard_progression_records": len(standards),
        "armor_progression_records": len(armor),
        "dna_progression_records": len(dna),
        "wild_encounter_records": encounter_count,
        "encounter_reward_records": len(encounter_rewards),
    }


def _verify_vanilla_engine_data_unchanged(
    output_data: bytearray,
    source_data: bytearray,
    version: str,
) -> dict[str, int | str]:
    """Prove damage/EXP systems and unrelated progression stayed vanilla."""

    output_moves = loaders.loadMoveData(version, output_data)
    source_moves = loaders.loadMoveData(version, source_data)
    if [entry.getByteArray() for entry in output_moves] != [
        entry.getByteArray() for entry in source_moves
    ]:
        raise AssertionError("Move damage/effect data changed unexpectedly")

    output_enemies = loaders.loadEnemyDigimonInfo(version, output_data)
    source_enemies = loaders.loadEnemyDigimonInfo(version, source_data)
    if output_enemies.keys() != source_enemies.keys() or any(
        output_enemies[key].getByteArray() != source_enemies[key].getByteArray()
        for key in output_enemies
    ):
        raise AssertionError("Enemy stats, AI, damage moves, or EXP rewards changed")

    output_rewards = loaders.loadEncounterRewardData(version, output_data)
    source_rewards = loaders.loadEncounterRewardData(version, source_data)
    if [entry.getByteArray() for entry in output_rewards] != [
        entry.getByteArray() for entry in source_rewards
    ]:
        raise AssertionError("Encounter reward tables changed unexpectedly")

    if loaders.loadLvlupTypeTable(version, output_data) != loaders.loadLvlupTypeTable(
        version, source_data
    ):
        raise AssertionError("Level-up growth table changed unexpectedly")

    output_areas = loaders.loadWildEncounterAreas(version, output_data)
    source_areas = loaders.loadWildEncounterAreas(version, source_data)
    if len(output_areas) != len(source_areas):
        raise AssertionError("Wild encounter area count changed")
    for output_area, source_area in zip(output_areas, source_areas):
        # Only the two step-distance thresholds at bytes 2..5 may differ.
        if (
            output_area.getByteArray()[:2] != source_area.getByteArray()[:2]
            or output_area.getByteArray()[6:] != source_area.getByteArray()[6:]
        ):
            raise AssertionError("Wild encounter composition changed unexpectedly")

    changed_species = {
        SHOUTMON_ID,
        BALLISTAMON_ID,
        SHOUTMON_X2_ID,
        DORULUMON_ID,
        SPARROWMON_ID,
    }
    output_base = loaders.loadBaseDigimonInfo(version, output_data)
    source_base = loaders.loadBaseDigimonInfo(version, source_data)
    for digimon_id in output_base.keys() - changed_species:
        if output_base[digimon_id].getByteArray() != source_base[
            digimon_id
        ].getByteArray():
            raise AssertionError(
                f"Unrelated base Digimon {digimon_id} changed unexpectedly"
            )

    changed_progressions = {
        BALLISTAMON_ID,
        SHOUTMON_X2_ID,
        DORULUMON_ID,
        SPARROWMON_ID,
    }
    output_standards = loaders.loadStandardDigivolutions(version, output_data)
    source_standards = loaders.loadStandardDigivolutions(version, source_data)
    for digimon_id in output_standards.keys() - changed_progressions:
        if output_standards[digimon_id].getByteArray() != source_standards[
            digimon_id
        ].getByteArray():
            raise AssertionError(
                f"Unrelated standard progression {digimon_id} changed"
            )

    output_armor = loaders.loadArmorDigivolutions(version, output_data)
    source_armor = loaders.loadArmorDigivolutions(version, source_data)
    if [entry.getByteArray() for entry in output_armor] != [
        entry.getByteArray() for entry in source_armor
    ]:
        raise AssertionError("Armor progression changed unexpectedly")
    output_dna, _ = loaders.loadDnaDigivolutions(version, output_data)
    source_dna, _ = loaders.loadDnaDigivolutions(version, source_data)
    if [entry.getByteArray() for entry in output_dna] != [
        entry.getByteArray() for entry in source_dna
    ]:
        raise AssertionError("DNA progression changed unexpectedly")

    return {
        "move_damage_table": "byte-identical to Dusk",
        "enemy_stats_ai_exp": "byte-identical to Dusk",
        "level_growth_table": "byte-identical to Dusk",
        "encounter_rewards": "byte-identical to Dusk",
        "unrelated_base_records_verified": len(output_base) - len(changed_species),
        "unrelated_progressions_verified": (
            len(output_standards) - len(changed_progressions)
        ),
    }


@dataclass(frozen=True)
class SpriteImport:
    name: str
    donor_entry: int
    target_sprite: int
    digimon_id: int | None = None
    template_id: int | None = None
    ui_binding: int | None = None
    compact_name: str = ""
    replaces: str = ""


PLAYER_IMPORTS = (
    SpriteImport(
        "Dorulumon",
        donor_entry=1262,
        target_sprite=413,
        digimon_id=DORULUMON_ID,
        template_id=DORULUMON_TEMPLATE_ID,
        ui_binding=(1059 << 16) | 1528,
        compact_name="Dorulumon",
    ),
    SpriteImport(
        "Sparrowmon",
        donor_entry=1263,
        target_sprite=414,
        digimon_id=SPARROWMON_ID,
        template_id=SPARROWMON_TEMPLATE_ID,
        ui_binding=(1060 << 16) | 1529,
        compact_name="Sparrowmn",
    ),
)

# Slot 408 is used by playable Shoutmon X2 and the former SkullBaluchimon
# story encounter, which is renamed as a corrupted X2 clone. The remaining
# three imports retain Dusk's boss choreography.
BOSS_IMPORTS = (
    SpriteImport(
        "Lilithmon",
        donor_entry=1296,
        target_sprite=410,
        compact_name="Lilithmon",
        replaces="Mercurimon",
    ),
    SpriteImport(
        "Tactimon",
        donor_entry=1294,
        target_sprite=411,
        compact_name="Tactmon",
        replaces="Gaiomon",
    ),
    SpriteImport(
        "DarkKnightmon",
        donor_entry=1275,
        target_sprite=412,
        compact_name="D.Knightmon",
        replaces="GranDracmon",
    ),
)

BOSS_ENEMY_IDS = {
    0x209: "X2 Clone",
    0x20F: "Lilithmon",
    0x212: "Tactmon",
    0x215: "D.Knightmon",
}

STARTER_PACKS = (
    (SHOUTMON_ID, BALLISTAMON_ID, DORULUMON_ID),
    (SHOUTMON_ID, DORULUMON_ID, SPARROWMON_ID),
    (GUILMON_ID, RENAMON_ID, PATAMON_ID),
    (LUNAMON_ID, CORONAMON_ID, TERRIERMON_ID),
)

LOCATION_REPLACEMENTS = {
    "Limit Valley": "Xros Valley",
    "Thriller Ruins": "Bagra Ruins",
    "Chaos Brain": "Xros Core",
    "Shadow Abyss": "Bagra Abyss",
}

DIALOGUE_REPLACEMENTS = {
    "SkullBaluchimon": "X2 Clone",
    "Mercurimon": "Lilithmon",
    "Gaiomon": "Tactmon",
    "GranDracmon": "D.Knightmon",
    "Grandracmon": "D.Knightmon",
    **LOCATION_REPLACEMENTS,
}

# Indexes are records in the Dusk half of MSG.PAK. The event flow remains
# untouched; only text within each record's original fixed byte budget changes.
STORY_DIALOGUE = {
    5508: (
        "A rift created the new[BR][RED]DigiArea[RED]:"
        "[BR][RED]Xros Valley[RED]."
    ),
    5509: (
        "A foreign Digimon signal[BR]is coming from[BR]"
        "[RED]Xros Valley[RED].[BR]We should investigate."
    ),
    5510: (
        "Sukekiyo, Kakumi,[BR]investigate the rift.[BR]"
        "Find any Digimon[BR]stranded inside."
    ),
    5513: (
        "I've been waiting for[BR]you, [PLAYER_NAME].[BR]"
        "Go to [RED]Xros Valley[RED].[BR]Find the signal's source[BR]"
        "and bring any survivors[BR]back to Night Crow."
    ),
    5567: (
        "Well done, [PLAYER_NAME].[BR]We are studying the[BR]"
        "[RED]Xros Code[RED] you recovered."
    ),
    5568: (
        "A dark Shoutmon X2![BR]"
        "A Bagra copy!"
    ),
    5569: (
        "Chief Julia,[BR]we decoded it![BR]"
        "The [RED]Xros Code[RED] is a[BR]foreign boost program.[BR]"
        "The virus uses it[BR]to open more rifts."
    ),
    5571: (
        "It is a worm carrying[BR]foreign Xros Code.[BR]"
        "A fragment restored[BR][RED]Dark E Area[RED],"
        "[BR]but the rift is[BR]still growing."
    ),
    5682: (
        "X2 Clone helped[BR]Lilithmon create[BR]"
        "[RED]M-D Word[RED].[BR]Both carry [RED]Xros Code[RED].[BR]"
        "The Bagra Army is[BR]inside our server."
    ),
    5710: (
        "Enough! Lilithmon![BR]X2 Clone! Attack![BR]"
        "kid. Tactmon and I[BR]will finish the Rift!"
    ),
    6127: (
        "Our Bagra plan has[BR]reached its final stage.[BR]"
        "[PLAYER_NAME], if you want[BR]to seal the Xros Rift,[BR]"
        "follow us into[BR][RED]Xros Core[RED].[BR]Grimmon is waiting..."
    ),
    6129: (
        "They will fuse Grimmon[BR]and the ChronoCore..."
        "[BR]We must stop them!"
    ),
    6139: (
        "The Bagra Army gathered[BR]digi-entelecheia and[BR]"
        "Xros Code from every[BR]battle. Grimmon will[BR]"
        "absorb the ChronoCore[BR]and join both worlds!"
    ),
    6140: (
        "The Xros Code answers![BR]My body is overflowing![BR]"
        "The ChronoCore and I[BR]are finally one!"
    ),
    6141: (
        "[PLAYER_NAME], you made it...[BR]This world rejected us,[BR]"
        "but the Xros Rift gave[BR]us perfect power.[BR]"
        "[RED]ChaosGrimmon[RED] now carries[BR]Chrono Data and Xros Code.[BR]"
        "No Digimon in either[BR]world can stop us!"
    ),
    6159: (
        "The plan...ends here.[BR]Grimmon could not contain[BR]"
        "Chrono Data and Xros Code.[BR]The rift is collapsing..."
        "[BR]The Bagra Army has lost."
    ),
    12914: "Choose a Xros team.",
    12929: (
        "Xros team:[BR]Shoutmon, Ballistamon,[BR]"
        "Dorulumon. Recommended."
    ),
    12930: (
        "Fast Xros team:[BR]Shoutmon, Dorulumon,[BR]and Sparrowmon."
    ),
    12931: (
        "Classic team:[BR]Guilmon, Renamon,[BR]and Patamon."
    ),
    12932: (
        "Moon and Sun team:[BR]Lunamon, Coronamon,[BR]and Terriermon."
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _set_fixed_string(record: Any, text: str, rom_data: bytearray) -> None:
    original = record.text
    record.text = text
    if not record.fits():
        record.text = original
        raise ValueError(
            f"Replacement for {record.region_id} index/offset "
            f"0x{record.offset:X} exceeds its {record.original_byte_length}-byte budget"
        )
    record.writeToRom(rom_data)


def _patch_names_and_text(
    rom_data: bytearray,
    version: str,
) -> dict[str, Any]:
    regions = loaders.loadAllStringRegions(version, rom_data)
    short_names = regions["arm9_digiegg_enemy_names"]
    battle_strings = loaders.loadBattleStringTable(version, rom_data)
    battle_table_start = constants.STRING_BATTLE_TABLE_OFFSET[version][0]

    player_names = {
        DORULUMON_ID: "Dorulumon",
        SPARROWMON_ID: "Sparrowmn",
    }
    for digimon_id, name in player_names.items():
        record = short_names[digimon_id]
        _set_fixed_string(record, name, rom_data)
        battle_strings[digimon_id].value = record.offset - battle_table_start
        battle_strings[digimon_id].writeToRom(rom_data)

    for enemy_id, name in BOSS_ENEMY_IDS.items():
        _set_fixed_string(short_names[enemy_id], name, rom_data)

    location_records = regions["arm9_locations_farmboards"]
    location_changes = 0
    for record in location_records:
        replacement = LOCATION_REPLACEMENTS.get(record.text)
        if replacement is None:
            continue
        _set_fixed_string(record, replacement, rom_data)
        location_changes += 1

    msg_records = regions["msgpak_all"]
    global_changes = 0
    for record in msg_records:
        replacement = record.text
        for old, new in DIALOGUE_REPLACEMENTS.items():
            replacement = replacement.replace(old, new)
        if replacement == record.text:
            continue
        _set_fixed_string(record, replacement, rom_data)
        global_changes += 1

    for index, text in STORY_DIALOGUE.items():
        if index >= len(msg_records):
            raise IndexError(f"MSG.PAK dialogue index {index} is missing")
        _set_fixed_string(msg_records[index], text, rom_data)

    return {
        "player_short_names": player_names,
        "boss_short_names": BOSS_ENEMY_IDS,
        "location_records_changed": location_changes,
        "global_dialogue_records_changed": global_changes,
        "story_dialogue_records_changed": len(STORY_DIALOGUE),
    }


def _patch_gameplay(rom_data: bytearray, version: str) -> dict[str, Any]:
    base = loaders.loadBaseDigimonInfo(version, rom_data)
    starters = loaders.loadStarters(version, rom_data)
    standards = loaders.loadStandardDigivolutions(version, rom_data)

    # Let the two extra player species use sensible native Dusk progression
    # instead of the reserved slots' dummy evolution records.
    for target_id, template_id in (
        (DORULUMON_ID, DORULUMON_TEMPLATE_ID),
        (SPARROWMON_ID, SPARROWMON_TEMPLATE_ID),
    ):
        target = standards[target_id]
        source = standards[template_id]
        rom_data[target.offset:target.offset + target.SIZE] = source.getByteArray()

    for pack_index, team in enumerate(STARTER_PACKS):
        for slot_index, digimon_id in enumerate(team):
            starter = starters[pack_index * 3 + slot_index]
            starter.digimon_id = digimon_id
            starter.level = min(20, base[digimon_id].aptitude)
            starter.writeToRom(rom_data)

    encounter_changes = []
    for area_index, area in enumerate(loaders.loadWildEncounterAreas(version, rom_data)):
        old_lower, old_upper = area.rate_lower, area.rate_upper
        area.rate_lower = min(
            0xFFFF,
            (old_lower * ENCOUNTER_RATE_NUMERATOR) // ENCOUNTER_RATE_DENOMINATOR,
        )
        area.rate_upper = min(
            0xFFFF,
            (old_upper * ENCOUNTER_RATE_NUMERATOR) // ENCOUNTER_RATE_DENOMINATOR,
        )
        area.writeToRom(rom_data)
        encounter_changes.append(
            {
                "area": area_index,
                "from": [old_lower, old_upper],
                "to": [area.rate_lower, area.rate_upper],
            }
        )

    scan_offset = constants.BASE_SCAN_RATE_OFFSET[version]
    old_scan = rom_data[scan_offset]
    rom_data[scan_offset] = SCAN_RATE

    return {
        "starter_packs": [list(team) for team in STARTER_PACKS],
        "encounter_areas_changed": len(encounter_changes),
        "encounter_rate_multiplier": 2.5,
        "encounter_frequency_target": 0.4,
        "scan_rate_from": old_scan,
        "scan_rate_to": SCAN_RATE,
        "native_evolution_records_cloned": 2,
    }


def _run_sprite_imports(
    pilot_rom: Path,
    xros_rom: Path,
    output_rom: Path,
    stage_roms: tuple[Path, ...],
) -> list[dict[str, Any]]:
    current = pilot_rom
    results: list[dict[str, Any]] = []
    for index, item in enumerate((*PLAYER_IMPORTS, *BOSS_IMPORTS)):
        next_rom = stage_roms[index]
        result = import_battle_sprite(
            current,
            xros_rom,
            item.donor_entry,
            item.target_sprite,
            next_rom,
            digimon_id=item.digimon_id,
            template_id=item.template_id,
            ui_binding=item.ui_binding,
            allow_replace=True,
        )
        results.append({**asdict(item), **result})
        current = next_rom
    shutil.copyfile(current, output_rom)
    return results


def install_xros_campaign(
    dusk_rom: Path,
    xros_rom: Path,
    output_rom: Path,
    *,
    write_manifest: bool = True,
) -> dict[str, Any]:
    dusk_rom = Path(dusk_rom)
    xros_rom = Path(xros_rom)
    output_rom = Path(output_rom)
    if output_rom.resolve() in {dusk_rom.resolve(), xros_rom.resolve()}:
        raise ValueError("Output ROM must be different from both source ROMs")
    if detectVersion(bytearray(dusk_rom.read_bytes()), str(dusk_rom)) != "DUSK_US":
        raise ValueError("Target must be Digimon World: Dusk (USA)")

    dusk_before = _sha256(dusk_rom)
    xros_before = _sha256(xros_rom)
    output_rom.parent.mkdir(parents=True, exist_ok=True)

    # Keep exact, short-lived intermediate files beside the output. Python's
    # TemporaryDirectory applies a private Windows ACL that managed desktop
    # sandboxes cannot reopen, while ordinary files inherit the workspace ACL.
    pilot_rom = output_rom.with_name(output_rom.name + ".stage-pilot.tmp")
    stage_roms = tuple(
        output_rom.with_name(output_rom.name + f".stage-sprite-{index}.tmp")
        for index in range(len(PLAYER_IMPORTS) + len(BOSS_IMPORTS))
    )
    try:
        install_shoutmon_x2_pilot(
            dusk_rom,
            xros_rom,
            pilot_rom,
            starter_pack=0,
            write_manifest=False,
        )
        sprite_results = _run_sprite_imports(
            pilot_rom,
            xros_rom,
            output_rom,
            stage_roms,
        )
    finally:
        for stage_path in (pilot_rom, *stage_roms):
            stage_path.unlink(missing_ok=True)

    rom_data = bytearray(output_rom.read_bytes())
    version = detectVersion(rom_data, str(output_rom))
    text_result = _patch_names_and_text(rom_data, version)
    gameplay_result = _patch_gameplay(rom_data, version)
    output_rom.write_bytes(rom_data)

    if _sha256(dusk_rom) != dusk_before or _sha256(xros_rom) != xros_before:
        raise AssertionError("A source ROM changed during the campaign build")

    verification = verify_xros_campaign(
        output_rom,
        xros_rom,
        dusk_rom=dusk_rom,
    )
    output_hash = _sha256(output_rom)
    manifest = {
        "format": "digimon_nds_xros_campaign_v4",
        "preset": "dusk_xros_rift_campaign_v4_runtime_safe_sprites",
        "output_rom": output_rom.name,
        "output_sha256": output_hash,
        "source_sha256": {
            "dusk": dusk_before,
            "super_xros_wars_blue": xros_before,
        },
        "compatibility_design": (
            "Dusk event scripts and map geometry are preserved; Xros Wars "
            "sprites, names, dialogue, teams, and balance settings create the crossover."
        ),
        "sprite_compatibility": (
            "Xros pixels are retargeted into Dusk-native battle cell and "
            "animation envelopes inside the original 415-slot runtime limit; "
            "dedicated portrait/map art replaces verified existing SPR slots."
        ),
        "sprite_imports": sprite_results,
        "text": text_result,
        "gameplay": gameplay_result,
        "verification": verification,
        "compact_rom_labels": {
            "Sparrowmon": "Sparrowmn",
            "Tactimon": "Tactmon",
            "DarkKnightmon": "D.Knightmon",
        },
    }
    manifest_path = output_rom.with_name(output_rom.name + ".xros-campaign.json")
    if write_manifest:
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return {
        "output_rom": str(output_rom),
        "manifest": str(manifest_path) if write_manifest else "",
        "sha256": output_hash,
        "verified": True,
        **verification,
    }


def verify_xros_campaign(
    output_rom: Path,
    xros_rom: Path,
    *,
    dusk_rom: Path | None = None,
) -> dict[str, Any]:
    output_rom = Path(output_rom)
    xros_rom = Path(xros_rom)
    rom_data = bytearray(output_rom.read_bytes())
    version = detectVersion(rom_data, str(output_rom))
    if version != "DUSK_US":
        raise AssertionError(f"Campaign ROM identifies as {version}, not DUSK_US")
    if struct.unpack_from("<H", rom_data, 0x15E)[0] != _crc16(rom_data[:0x15E]):
        raise AssertionError("Campaign ROM header CRC is invalid")

    # Retain all of the original playable Shoutmon X2 recipe guarantees.
    pilot = verify_shoutmon_x2_pilot(output_rom, xros_rom, starter_pack=0)

    base = loaders.loadBaseDigimonInfo(version, rom_data)
    sprites = loaders.loadSpriteMapTable(version, rom_data)
    starters = loaders.loadStarters(version, rom_data)
    standards = loaders.loadStandardDigivolutions(version, rom_data)
    regions = loaders.loadAllStringRegions(version, rom_data)
    roster_and_progression = _verify_roster_and_progression(rom_data, version)
    vanilla_integrity: dict[str, int | str] = {}
    if dusk_rom is not None:
        source_data = bytearray(Path(dusk_rom).read_bytes())
        if detectVersion(source_data, str(dusk_rom)) != version:
            raise AssertionError("Vanilla comparison ROM is not Dusk (USA)")
        vanilla_integrity = _verify_vanilla_engine_data_unchanged(
            rom_data,
            source_data,
            version,
        )

    for item in PLAYER_IMPORTS:
        assert item.digimon_id is not None
        if base[item.digimon_id].hp == 9999:
            raise AssertionError(f"{item.name} still has dummy base data")
        if sprites[item.digimon_id].main_sprite != item.target_sprite:
            raise AssertionError(f"{item.name} sprite binding is incorrect")

    if (
        standards[DORULUMON_ID].getByteArray()
        != standards[DORULUMON_TEMPLATE_ID].getByteArray()
    ):
        raise AssertionError("Dorulumon's native evolution progression was not cloned")
    if (
        standards[SPARROWMON_ID].getByteArray()
        != standards[SPARROWMON_TEMPLATE_ID].getByteArray()
    ):
        raise AssertionError("Sparrowmon's native evolution progression was not cloned")

    actual_starters = [
        tuple(starters[index * 3 + slot].digimon_id for slot in range(3))
        for index in range(4)
    ]
    if tuple(actual_starters) != STARTER_PACKS:
        raise AssertionError("Xros starter packs do not match the campaign plan")

    encounter_areas = loaders.loadWildEncounterAreas(version, rom_data)
    expected_rate_pairs = {
        (250, 1000),
        (250, 1250),
        (250, 2500),
        (500, 1750),
    }
    for area in encounter_areas:
        if area.rate_lower <= 0 or area.rate_upper <= 0:
            raise AssertionError("An encounter area has an invalid zero rate")
        if (area.rate_lower, area.rate_upper) not in expected_rate_pairs:
            raise AssertionError(
                "An encounter area does not use the 2.5x step-distance setting"
            )
    if rom_data[constants.BASE_SCAN_RATE_OFFSET[version]] != SCAN_RATE:
        raise AssertionError("The 3x base scan/data setting is missing")

    short_names = regions["arm9_digiegg_enemy_names"]
    expected_names = {
        DORULUMON_ID: "Dorulumon",
        SPARROWMON_ID: "Sparrowmn",
        **BOSS_ENEMY_IDS,
    }
    for entry_id, name in expected_names.items():
        if short_names[entry_id].text.lstrip() != name:
            raise AssertionError(f"Short name for 0x{entry_id:03X} is not {name}")

    # Shorter fixed-slot strings are padded with zero glyphs after [END].
    # The game's original pointer starts at the intended text, while a full
    # sequential reparse can attach that harmless padding to the next record.
    location_texts = {
        record.text.lstrip() for record in regions["arm9_locations_farmboards"]
    }
    if not set(LOCATION_REPLACEMENTS.values()).issubset(location_texts):
        raise AssertionError("One or more Xros campaign location names are missing")
    msg_records = regions["msgpak_all"]
    msg_texts = {record.text.lstrip() for record in msg_records}
    for index, text in STORY_DIALOGUE.items():
        if text not in msg_texts:
            raise AssertionError(f"Story dialogue record {index} does not match")

    with output_rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        archive = DuskPak.from_bytes(
            read_nitro_file(handle, find_nitro_file(files, DUSK_BATTLE_ARCHIVE))
        )
    source_archive = None
    if dusk_rom is not None:
        source_archive = DuskPak.from_bytes(
            _load_nitro_file(Path(dusk_rom), DUSK_BATTLE_ARCHIVE)
        )
    verified_components = 0
    imported_sprite_frames = pilot["battle_frames_rendered"]
    imported_opaque_pixels = pilot["battle_opaque_pixels"]
    imported_ui_sprites = pilot["ui_sprites_rendered"]
    upper_sprites = DuskSpriteSet.from_rom(output_rom)
    for item in (*PLAYER_IMPORTS, *BOSS_IMPORTS):
        raw_donor = _load_xros_components(xros_rom, item.donor_entry)
        group = item.target_sprite * BATTLE_GROUP_SIZE
        template_sprite = (
            sprites[item.template_id].main_sprite
            if item.template_id is not None
            else item.target_sprite
        )
        stored = {
            kind: archive.unpacked_data(group + component_index)
            for component_index, kind in enumerate(SPRITE_ARCHIVES, start=1)
        }
        donor = (
            retarget_sprite_components(
                raw_donor,
                _sprite_group_components(archive, template_sprite),
                maximum_size=PLAYABLE_BATTLE_MAX_SIZE,
            )
            if item.template_id is not None
            else (
                retarget_sprite_components(
                    raw_donor,
                    _sprite_group_components(source_archive, template_sprite),
                    maximum_size=BOSS_BATTLE_MAX_SIZE,
                    repeat_first_frame=True,
                )
                if source_archive is not None
                else stored
            )
        )
        if item.template_id is None and stored == raw_donor:
            raise AssertionError(f"{item.name} still uses raw Xros cell geometry")
        for component_index, kind in enumerate(SPRITE_ARCHIVES, start=1):
            if archive.unpacked_data(group + component_index) != donor[kind]:
                raise AssertionError(
                    f"{item.name} {kind} is not retargeted to its Dusk template"
                )
            verified_components += 1
        visual = _validate_sprite_components(item.name, donor)
        imported_sprite_frames += visual["frames"]
        imported_opaque_pixels += visual["opaque_pixels"]
        if item.template_id is not None:
            if archive.unpacked_data(group) != archive.unpacked_data(
                template_sprite * BATTLE_GROUP_SIZE
            ):
                raise AssertionError(
                    f"{item.name} does not use its Dusk template metadata"
                )
            packed_upper = sprites[item.digimon_id].upperscreen_sprites
            if packed_upper == sprites[item.template_id].upperscreen_sprites:
                raise AssertionError(f"{item.name} still uses template UI sprites")
            if packed_upper != item.ui_binding:
                raise AssertionError(
                    f"{item.name} does not use its runtime-safe existing UI slots"
                )
            status_icon = sprites[item.digimon_id].unknown_0x4
            if status_icon != sprites[item.template_id].unknown_0x4:
                raise AssertionError(
                    f"{item.name} does not preserve its Dusk status/effect binding"
                )
            for sprite_index in (
                packed_upper & 0xFFFF,
                packed_upper >> 16,
            ):
                rendered = upper_sprites.render_rgba(sprite_index)
                if sum(rendered.pixels[3::4]) == 0:
                    raise AssertionError(f"{item.name} has a blank UI/map sprite")
                imported_ui_sprites += 1

    # The two new all-stock packs must display real, nonblank Dusk sprites in
    # battle, in portrait/UI contexts, and as the smaller map-mode sprites.
    stock_starter_ids = (
        GUILMON_ID,
        RENAMON_ID,
        PATAMON_ID,
        LUNAMON_ID,
        CORONAMON_ID,
        TERRIERMON_ID,
    )
    stock_sprite_frames = 0
    stock_opaque_pixels = 0
    upper_sprite_resources = 0
    for digimon_id in stock_starter_ids:
        main_sprite = sprites[digimon_id].main_sprite
        group = main_sprite * BATTLE_GROUP_SIZE
        components = {
            kind: archive.unpacked_data(group + component_index)
            for component_index, kind in enumerate(SPRITE_ARCHIVES, start=1)
        }
        visual = _validate_sprite_components(
            constants.DIGIMON_ID_TO_STR[digimon_id],
            components,
        )
        stock_sprite_frames += visual["frames"]
        stock_opaque_pixels += visual["opaque_pixels"]
        packed_upper = sprites[digimon_id].upperscreen_sprites
        for sprite_index in (packed_upper & 0xFFFF, packed_upper >> 16):
            rendered = upper_sprites.render_rgba(sprite_index)
            if sum(rendered.pixels[3::4]) == 0:
                raise AssertionError(
                    f"Starter 0x{digimon_id:03X} has a blank UI/map sprite"
                )
            upper_sprite_resources += 1

    return {
        "rom_version": version,
        "header_crc": "ok",
        "battle_sprite_count": pilot["battle_sprite_count"],
        "xros_components_verified": verified_components + pilot["blue_components_verified"],
        "playable_xros_species": 5,
        "bagra_boss_reskins": len(BOSS_IMPORTS),
        "starter_packs_verified": 4,
        "encounter_areas_verified": len(encounter_areas),
        "encounter_frequency_target": "40% of vanilla",
        "base_scan_data": "3x vanilla",
        "story_dialogue_records_verified": len(STORY_DIALOGUE),
        "locations_verified": len(LOCATION_REPLACEMENTS),
        "shoutmon_x2_recipe": "ok",
        "imported_battle_frames_rendered": imported_sprite_frames,
        "imported_battle_opaque_pixels": imported_opaque_pixels,
        "imported_ui_map_sprites_rendered": imported_ui_sprites,
        "stock_starter_frames_rendered": stock_sprite_frames,
        "stock_starter_opaque_pixels": stock_opaque_pixels,
        "stock_starter_ui_map_sprites_rendered": upper_sprite_resources,
        "roster_and_progression": roster_and_progression,
        "vanilla_engine_integrity": vanilla_integrity,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dusk_rom", type=Path)
    parser.add_argument("xros_rom", type=Path)
    parser.add_argument("output_rom", type=Path)
    parser.add_argument("--no-manifest", action="store_true")
    args = parser.parse_args()
    result = install_xros_campaign(
        args.dusk_rom,
        args.xros_rom,
        args.output_rom,
        write_manifest=not args.no_manifest,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
