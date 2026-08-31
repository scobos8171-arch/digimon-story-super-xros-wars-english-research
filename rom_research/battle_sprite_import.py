"""Port one Xros Wars battle sprite into a reserved Dawn/Dusk sprite slot.

This is the visual half of roster expansion.  It imports graphics, palette,
cell layout and animation, updates the two Dawn/Dusk size maps, and can bind
the new sprite to a placeholder Digimon record cloned from a chosen template.
It does not yet add a new name string or evolution links.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from digimon_core import constants, loaders
from digimon_core.rom import detectVersion
from rom_research.dusk_pak import DuskPak
from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.nitrofs_patch import replace_nitrofs_files
from rom_research.xros_pak import XrosPak, find_nitro_file, read_nitro_file
from rom_research.xros_sprite import SPRITE_ARCHIVES, parse_ncer, parse_ncgr
from rom_research.sprite_retarget import retarget_sprite_components


DUSK_BATTLE_ARCHIVE = "dat/BTCHR.PAK"
DUSK_BATTLE_SIZE_MAP = "dat/btchr/btchrsize.bin"
DUSK_CHARACTER_SIZE_MAP = "dat/btchr/chrsize.bin"
BATTLE_GROUP_SIZE = 5
PLAYABLE_BATTLE_MAX_SIZE = (48, 48)
BOSS_BATTLE_MAX_SIZE = (120, 120)
STOCK_UI_SPRITE_COUNT = 1627
DUSK_UI_ARCHIVES = {
    "graphics": "dat/SPR_CHR.PAK",
    "palette": "dat/SPR_PAL.PAK",
    "cells": "dat/SPR_CEL.PAK",
    "animation": "dat/SPR_ANM.PAK",
}


def _load_nitro_file(rom_path: Path, requested: str) -> bytes:
    with rom_path.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        return read_nitro_file(handle, find_nitro_file(files, requested))


def _load_xros_components(rom_path: Path, donor_entry: int) -> dict[str, bytes]:
    with rom_path.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        archives = {
            kind: XrosPak.from_bytes(
                read_nitro_file(handle, find_nitro_file(files, archive_name))
            )
            for kind, archive_name in SPRITE_ARCHIVES.items()
        }
    counts = {len(archive.entries) for archive in archives.values()}
    if len(counts) != 1:
        raise ValueError("Xros sprite archive counts do not match")
    entry_count = next(iter(counts))
    if not 0 <= donor_entry < entry_count:
        raise IndexError(f"Donor entry must be between 0 and {entry_count - 1}")
    components = {
        kind: archive.unpacked_data(donor_entry)
        for kind, archive in archives.items()
    }
    expected = {
        "graphics": b"RGCN",
        "palette": b"RLCN",
        "cells": b"RECN",
        "animation": b"RNAN",
    }
    for kind, magic in expected.items():
        if not components[kind].startswith(magic):
            raise ValueError(f"Donor {kind} entry is not a {magic.decode()} file")
    return components


def _sprite_group_components(
    archive: DuskPak,
    sprite_id: int,
) -> dict[str, bytes]:
    group = sprite_id * BATTLE_GROUP_SIZE
    return {
        kind: archive.unpacked_data(group + component_index)
        for component_index, kind in enumerate(SPRITE_ARCHIVES, start=1)
    }


def _append_ui_sprite_bindings(
    dusk_rom: Path,
    plans: tuple[tuple[dict[str, bytes], int, int], ...],
) -> tuple[dict[str, bytes], tuple[int, ...]]:
    """Install portraits/map sprites into existing, engine-addressable slots.

    ``upperscreen_sprites`` stores two additional 16-bit coordinated SPR
    archive IDs: the low word is the larger portrait and the high word is the
    field sprite. The old importer copied all three IDs from a gameplay
    template, which is why Shoutmon showed Agumon's art in the screenshots.

    Dusk's ARM9 runtime only addresses the original coordinated SPR entry
    range. Appending valid PAK entries makes them render offline but produces
    blank circles or wrapped template art in-game. Each plan therefore
    supplies a verified existing portrait/field binding that may be replaced.

    ``unknown_0x4`` is not portrait art: stock entries point to shared
    status/effect resources. It remains cloned from the gameplay template.
    """

    archives = {
        kind: DuskPak.from_bytes(_load_nitro_file(dusk_rom, path))
        for kind, path in DUSK_UI_ARCHIVES.items()
    }
    counts = {len(archive.entries) for archive in archives.values()}
    if len(counts) != 1:
        raise ValueError(f"Dusk UI sprite archive counts do not match: {counts}")
    entry_count = next(iter(counts))
    replacements: dict[str, dict[int, bytes]] = {
        kind: {} for kind in DUSK_UI_ARCHIVES
    }
    bindings: list[int] = []

    def template_components(index: int) -> dict[str, bytes]:
        return {
            kind: archives[kind].unpacked_data(index)
            for kind in DUSK_UI_ARCHIVES
        }

    used_targets: set[int] = set()
    for donor, template_binding, target_binding in plans:
        portrait_template = template_binding & 0xFFFF
        field_template = template_binding >> 16
        portrait_index = target_binding & 0xFFFF
        field_index = target_binding >> 16
        if max(
            portrait_template,
            field_template,
            portrait_index,
            field_index,
        ) >= entry_count:
            raise ValueError("Template upper-screen sprite ID is out of range")
        if {portrait_index, field_index} & used_targets:
            raise ValueError("UI sprite replacement slots must be unique")
        used_targets.update((portrait_index, field_index))
        portrait = retarget_sprite_components(
            donor,
            template_components(portrait_template),
            margin=1,
            repeat_first_frame=True,
        )
        field = retarget_sprite_components(
            donor,
            template_components(field_template),
            margin=1,
            repeat_first_frame=True,
        )
        for kind in DUSK_UI_ARCHIVES:
            replacements[kind][portrait_index] = portrait[kind]
            replacements[kind][field_index] = field[kind]
        bindings.append((field_index << 16) | portrait_index)

    rebuilt = {
        path: archives[kind].rebuild(
            replacements[kind],
        )
        for kind, path in DUSK_UI_ARCHIVES.items()
    }
    return rebuilt, tuple(bindings)


def _patch_model_binding(
    rom_data: bytearray,
    *,
    digimon_id: int,
    target_sprite: int,
    template_id: int,
) -> None:
    version = detectVersion(rom_data)
    if version not in {"DUSK_US", "DAWN_US"}:
        raise ValueError("The target must be a supported US Dawn/Dusk ROM")
    base = loaders.loadBaseDigimonInfo(version, rom_data)
    sprites = loaders.loadSpriteMapTable(version, rom_data)
    battle_strings = loaders.loadBattleStringTable(version, rom_data)
    if digimon_id not in base or template_id not in base:
        raise IndexError("Digimon or template ID does not have a base-data slot")
    if max(digimon_id, template_id) >= len(sprites):
        raise IndexError("Digimon or template ID does not have a sprite-map slot")

    cloned = bytearray(base[template_id].getByteArray())
    cloned[0:2] = digimon_id.to_bytes(2, "little")
    target_record = base[digimon_id]
    rom_data[target_record.offset:target_record.offset + len(cloned)] = cloned

    target_map = sprites[digimon_id]
    source_map = sprites[template_id]
    target_map.unknown_0x4 = source_map.unknown_0x4
    target_map.main_sprite = target_sprite
    target_map.upperscreen_sprites = source_map.upperscreen_sprites
    target_map.writeToRom(rom_data)

    # Temporary display-string binding. The dedicated name-expansion pass
    # will replace this alias with the imported monster's English name.
    battle_strings[digimon_id].value = battle_strings[template_id].value
    battle_strings[digimon_id].writeToRom(rom_data)


def import_battle_sprite(
    dusk_rom: Path,
    xros_rom: Path,
    donor_entry: int,
    target_sprite: int,
    output_rom: Path,
    *,
    digimon_id: int | None = None,
    template_id: int | None = None,
    ui_binding: int | None = None,
    allow_replace: bool = False,
) -> dict[str, int]:
    target_data = bytearray(dusk_rom.read_bytes())
    version = detectVersion(target_data, str(dusk_rom))
    sprite_map = loaders.loadSpriteMapTable(version, target_data)
    users = [index for index, entry in enumerate(sprite_map) if entry.main_sprite == target_sprite]
    is_own_reserved_binding = (
        digimon_id is not None and set(users) == {digimon_id}
    )
    if users and not allow_replace and not is_own_reserved_binding:
        raise ValueError(
            f"Dusk battle-sprite slot {target_sprite} is already used by "
            f"Digimon IDs {users[:12]}; pass --allow-replace to overwrite it"
        )
    if (digimon_id is None) != (template_id is None):
        raise ValueError("--digimon-id and --template-id must be used together")
    if digimon_id is not None and ui_binding is None:
        raise ValueError("Playable imports require an existing UI sprite binding")

    raw_donor = _load_xros_components(xros_rom, donor_entry)
    target_archive = DuskPak.from_bytes(
        _load_nitro_file(dusk_rom, DUSK_BATTLE_ARCHIVE)
    )
    group_start = target_sprite * BATTLE_GROUP_SIZE
    if group_start + 4 >= len(target_archive.entries):
        raise IndexError(
            f"Target sprite must be between 0 and "
            f"{len(target_archive.entries) // BATTLE_GROUP_SIZE - 1}"
        )

    # Playable imports must inherit the normal-sized placement/animation-role
    # metadata of their Dusk gameplay template. Reserved/fixed-enemy slots can
    # contain dummy or boss-specific metadata that makes an otherwise valid
    # imported sprite render off-screen or not animate correctly. Boss reskins
    # intentionally keep their existing encounter metadata.
    template_sprite = (
        sprite_map[template_id].main_sprite
        if template_id is not None
        else target_sprite
    )
    template_components = _sprite_group_components(target_archive, template_sprite)
    donor = retarget_sprite_components(
        raw_donor,
        template_components,
        maximum_size=(
            PLAYABLE_BATTLE_MAX_SIZE
            if digimon_id is not None
            else BOSS_BATTLE_MAX_SIZE
        ),
        repeat_first_frame=digimon_id is None,
    )
    replacements = {
        group_start + component_index: donor[kind]
        for component_index, kind in enumerate(SPRITE_ARCHIVES, start=1)
    }
    if template_id is not None:
        template_metadata_index = template_sprite * BATTLE_GROUP_SIZE
        if template_metadata_index >= len(target_archive.entries):
            raise ValueError(
                f"Template sprite {template_sprite} has no battle metadata"
            )
        replacements[group_start] = target_archive.unpacked_data(
            template_metadata_index
        )
    rebuilt_archive = target_archive.rebuild(replacements)

    size_map = bytearray(_load_nitro_file(dusk_rom, DUSK_BATTLE_SIZE_MAP))
    if len(size_map) % 4 or target_sprite >= len(size_map) // 4:
        raise ValueError("Dusk battle-size map does not cover the target slot")
    component_total = sum(len(donor[k]) for k in SPRITE_ARCHIVES)
    struct.pack_into("<I", size_map, target_sprite * 4, component_total)

    character_map = bytearray(
        _load_nitro_file(dusk_rom, DUSK_CHARACTER_SIZE_MAP)
    )
    old_character_value = struct.unpack_from("<I", character_map, target_sprite * 4)[0]
    ncgr = parse_ncgr(donor["graphics"])
    cell_count = len(parse_ncer(donor["cells"]))
    tiles_per_cell = len(ncgr.tiles) // max(1, cell_count)
    mapped_id = digimon_id if digimon_id is not None else old_character_value & 0xFFFF
    struct.pack_into(
        "<I",
        character_map,
        target_sprite * 4,
        (tiles_per_cell << 16) | (mapped_id & 0xFFFF),
    )

    if digimon_id is not None and template_id is not None:
        _patch_model_binding(
            target_data,
            digimon_id=digimon_id,
            target_sprite=target_sprite,
            template_id=template_id,
        )
        ui_replacements, bindings = _append_ui_sprite_bindings(
            dusk_rom,
            (
                (
                    raw_donor,
                    sprite_map[template_id].upperscreen_sprites,
                    ui_binding,
                ),
            ),
        )
        patched_sprite_map = loaders.loadSpriteMapTable(version, target_data)
        patched_sprite_map[digimon_id].upperscreen_sprites = bindings[0]
        patched_sprite_map[digimon_id].writeToRom(target_data)
        status_sprite_id = patched_sprite_map[digimon_id].unknown_0x4
    else:
        ui_replacements = {}
        status_sprite_id = -1

    patched = replace_nitrofs_files(
        target_data,
        {
            DUSK_BATTLE_ARCHIVE: rebuilt_archive,
            DUSK_BATTLE_SIZE_MAP: bytes(size_map),
            DUSK_CHARACTER_SIZE_MAP: bytes(character_map),
            **ui_replacements,
        },
    )
    output_rom.parent.mkdir(parents=True, exist_ok=True)
    output_rom.write_bytes(patched)
    return {
        "donor_entry": donor_entry,
        "target_sprite": target_sprite,
        "digimon_id": -1 if digimon_id is None else digimon_id,
        "component_bytes": component_total,
        "tiles_per_cell": tiles_per_cell,
        "ui_portrait_sprite": (
            -1 if not ui_replacements else bindings[0] & 0xFFFF
        ),
        "ui_field_sprite": (
            -1 if not ui_replacements else bindings[0] >> 16
        ),
        "ui_status_sprite": status_sprite_id,
        "output_bytes": len(patched),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dusk_rom", type=Path)
    parser.add_argument("xros_rom", type=Path)
    parser.add_argument("donor_entry", type=int)
    parser.add_argument("target_sprite", type=int)
    parser.add_argument("output_rom", type=Path)
    parser.add_argument("--digimon-id", type=lambda value: int(value, 0))
    parser.add_argument("--template-id", type=lambda value: int(value, 0))
    parser.add_argument("--ui-portrait-slot", type=lambda value: int(value, 0))
    parser.add_argument("--ui-field-slot", type=lambda value: int(value, 0))
    parser.add_argument("--allow-replace", action="store_true")
    args = parser.parse_args()
    ui_binding = (
        (args.ui_field_slot << 16) | args.ui_portrait_slot
        if args.ui_portrait_slot is not None and args.ui_field_slot is not None
        else None
    )
    result = import_battle_sprite(
        args.dusk_rom,
        args.xros_rom,
        args.donor_entry,
        args.target_sprite,
        args.output_rom,
        digimon_id=args.digimon_id,
        template_id=args.template_id,
        ui_binding=ui_binding,
        allow_replace=args.allow_replace,
    )
    print(
        f"Imported Blue entry {result['donor_entry']} into Dusk battle slot "
        f"{result['target_sprite']} -> {args.output_rom}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
