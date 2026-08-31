from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageOps

from .nds import NdsRom
from .profiles import (
    SpeciesRecord,
    canonical_display_name,
    detect_profile,
    normalize_name,
    safe_slug,
    species_for_rom,
)
from .sprites import (
    CoordinatedSprites,
    DuskBattleSprites,
    DuskMapSprites,
    SpriteResource,
    compose_sheet,
    normalized_frame_hash,
    save_resource_components,
)


DEFAULT_TICK_RATE = 60
DEFAULT_WALK_MS = 150


@dataclass
class RomContext:
    rom: NdsRom
    profile: str
    species: tuple[SpeciesRecord, ...]
    battle: DuskBattleSprites | CoordinatedSprites
    coordinated: CoordinatedSprites
    map_sprites: DuskMapSprites | None


@dataclass
class AnalyzedSource:
    context_index: int
    species_index: int
    battle_hash: str
    opaque_pixels: int
    cell_count: int
    sequence_labels: list[str]
    error: str = ""


class DisjointSet:
    def __init__(self, count: int):
        self.parent = list(range(count))
        self.rank = [0] * count

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        left, right = self.find(left), self.find(right)
        if left == right:
            return
        if self.rank[left] < self.rank[right]:
            left, right = right, left
        self.parent[right] = left
        if self.rank[left] == self.rank[right]:
            self.rank[left] += 1


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rom_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resource(context: RomContext, species: SpeciesRecord) -> SpriteResource:
    return context.battle.resource(species.battle_entry)


def load_context(path: Path) -> RomContext:
    rom = NdsRom(path)
    profile = detect_profile(rom)
    coordinated = (
        CoordinatedSprites.dusk(rom) if profile == "dusk" else CoordinatedSprites.xros(rom)
    )
    return RomContext(
        rom=rom,
        profile=profile,
        species=species_for_rom(rom),
        battle=DuskBattleSprites(rom) if profile == "dusk" else coordinated,
        coordinated=coordinated,
        map_sprites=DuskMapSprites(rom) if profile == "dusk" else None,
    )


def analyze_contexts(contexts: list[RomContext]) -> list[AnalyzedSource]:
    analyses: list[AnalyzedSource] = []
    total = sum(len(context.species) for context in contexts)
    completed = 0
    cache: dict[tuple[int, int], tuple[str, int, int, list[str], str]] = {}
    for context_index, context in enumerate(contexts):
        for species_index, species in enumerate(context.species):
            cache_key = (context_index, species.battle_entry)
            cached = cache.get(cache_key)
            if cached is None:
                try:
                    resource = _resource(context, species)
                    frames = resource.rendered_cells()
                    battle_hash = normalized_frame_hash(frames)
                    opaque = sum(
                        sum(1 for alpha in frame.getchannel("A").getdata() if alpha)
                        for frame in frames
                    )
                    labels = [sequence.label for sequence in resource.sequences()]
                    cached = (battle_hash, opaque, len(frames), labels, "")
                except Exception as exc:  # one corrupt/unsupported entry must not stop the roster
                    cached = ("", 0, 0, [], f"{type(exc).__name__}: {exc}")
                cache[cache_key] = cached
            analyses.append(
                AnalyzedSource(
                    context_index=context_index,
                    species_index=species_index,
                    battle_hash=cached[0],
                    opaque_pixels=cached[1],
                    cell_count=cached[2],
                    sequence_labels=list(cached[3]),
                    error=cached[4],
                )
            )
            completed += 1
            if completed % 100 == 0 or completed == total:
                print(f"Analyzed {completed}/{total} source roster entries")
    return analyses


def build_groups(
    contexts: list[RomContext],
    analyses: list[AnalyzedSource],
) -> list[list[int]]:
    dsu = DisjointSet(len(analyses))
    by_name: dict[str, int] = {}
    xros_version_slot: dict[int, int] = {}
    for index, analysis in enumerate(analyses):
        species = contexts[analysis.context_index].species[analysis.species_index]
        normalized = normalize_name(species.display_name)
        is_placeholder = not normalized or set(species.display_name) <= {"?", "？", " ", "-"}
        if not is_placeholder:
            previous = by_name.setdefault(normalized, index)
            dsu.union(index, previous)
        # Red and Blue share the same 398-slot roster layout. Pairing the same
        # internal slot is reliable when one version has Japanese names and
        # the other has localized full-width Latin names. Do not globally
        # merge on rendered hashes: DS archives also reuse or alias artwork
        # for placeholders, transformations and visually related forms.
        if species.source_game in {"xros_red", "xros_blue"}:
            previous = xros_version_slot.setdefault(species.internal_id, index)
            dsu.union(index, previous)

    groups: dict[int, list[int]] = {}
    for index in range(len(analyses)):
        groups.setdefault(dsu.find(index), []).append(index)
    return sorted(groups.values(), key=lambda group: min(group))


def _name_score(species: SpeciesRecord) -> tuple[int, int, int]:
    name = species.display_name
    ascii_letters = sum(character.isascii() and character.isalpha() for character in name)
    replacement_penalty = name.count("?") + name.count("？") + name.count("�")
    source_score = {
        "dusk": 40,
        "lost_evolution": 35,
        "xros_blue": 30,
        "xros_red": 20,
    }.get(species.source_game, 0)
    return (ascii_letters - replacement_penalty * 10, source_score, -len(name))


def _asset_score(
    context: RomContext,
    species: SpeciesRecord,
    analysis: AnalyzedSource,
) -> tuple[int, int, int]:
    walk = int(
        context.map_sprites is not None
        and species.walk_entry is not None
        and 0 <= species.walk_entry < context.map_sprites.count
    )
    source_score = {
        "dusk": 40,
        "lost_evolution": 30,
        "xros_blue": 25,
        "xros_red": 20,
    }.get(species.source_game, 0)
    return (walk, source_score, analysis.opaque_pixels)


def _sequence_role(label: str, index: int) -> str:
    lowered = label.casefold()
    if any(token in lowered for token in ("wait", "idle")):
        return "idle"
    if any(token in lowered for token in ("atck", "attack", "atk")):
        return "attack"
    if any(token in lowered for token in ("dmge", "damage", "dmg", "hit")):
        return "hit"
    if any(token in lowered for token in ("dead", "defeat", "down", "ko")):
        return "defeat"
    return ("idle", "attack", "hit", "defeat")[min(index, 3)]


def _frames_for_sequence(
    cells: tuple[Image.Image, ...],
    sequence,
) -> tuple[list[Image.Image], list[int]]:
    frames: list[Image.Image] = []
    timing: list[int] = []
    for frame in sequence.frames:
        if 0 <= frame.cell_index < len(cells):
            frames.append(cells[frame.cell_index])
            timing.append(max(1, round(frame.duration_ticks * 1000 / DEFAULT_TICK_RATE)))
    return frames, timing


def export_battle(
    resource: SpriteResource,
    output: Path,
    *,
    raw_components: bool,
) -> dict:
    cells = resource.rendered_cells()
    all_sheet, frame_size = compose_sheet(cells)
    all_sheet.save(output / "battle_all_cells.png")
    sequences = resource.sequences()
    animations: dict[str, dict] = {}
    attack_number = 0
    role_frames: dict[str, tuple[list[Image.Image], list[int], str]] = {}
    for index, sequence in enumerate(sequences):
        role = _sequence_role(sequence.label, index)
        frames, timing = _frames_for_sequence(cells, sequence)
        if role == "idle":
            # Very short NANR ticks are readable on original hardware with its
            # presentation cadence, but look like flicker at modern refresh rates.
            timing = [max(100, value) for value in timing]
        if not frames:
            continue
        if role == "attack":
            attack_number += 1
            key = f"attack_{attack_number:02d}"
        else:
            key = role
        role_frames[key] = (frames, timing, sequence.label)

    if not role_frames and cells:
        idle_count = min(3, len(cells))
        role_frames["idle"] = (list(cells[:idle_count]), [150] * idle_count, "cell_fallback")
        if len(cells) > idle_count:
            role_frames["attack_01"] = ([cells[idle_count]], [180], "cell_fallback")
        if len(cells) > idle_count + 1:
            role_frames["hit"] = ([cells[-1]], [180], "cell_fallback")

    for key, (frames, timing, label) in role_frames.items():
        filename = f"battle_{key}.png"
        sheet, size = compose_sheet(frames)
        sheet.save(output / filename)
        animations[key] = {
            "file": filename,
            "frame_size": list(size),
            "frame_count": len(frames),
            "timing_ms": timing,
            "source_sequence": label,
            "derived": label == "cell_fallback",
        }

    if "idle" not in animations and cells:
        sheet, size = compose_sheet([cells[0]])
        sheet.save(output / "battle_idle.png")
        animations["idle"] = {
            "file": "battle_idle.png",
            "frame_size": list(size),
            "frame_count": 1,
            "timing_ms": [180],
            "source_sequence": "first_cell",
            "derived": True,
        }
    if not any(key.startswith("attack") for key in animations) and cells:
        # A small set of late-roster banks contains only a representative
        # pose and relies on engine effects/movement for its attack. Preserve
        # that behavior with an explicit derived animation contract.
        attack_pose = cells[1] if len(cells) > 1 else cells[0]
        sheet, size = compose_sheet([attack_pose])
        sheet.save(output / "battle_attack_01.png")
        animations["attack_01"] = {
            "file": "battle_attack_01.png",
            "frame_size": list(size),
            "frame_count": 1,
            "timing_ms": [180],
            "source_sequence": "representative_pose_with_engine_effect",
            "derived": True,
        }
    if "hit" not in animations and cells:
        sheet, size = compose_sheet([cells[-1]])
        sheet.save(output / "battle_hit.png")
        animations["hit"] = {
            "file": "battle_hit.png",
            "frame_size": list(size),
            "frame_count": 1,
            "timing_ms": [180],
            "source_sequence": "last_cell",
            "derived": True,
        }
    if "defeat" not in animations and cells:
        # The DS games normally fade/remove the damage pose rather than store
        # a distinct KO drawing. Keep that behavior explicit for the engine.
        source = role_frames.get("hit", ([cells[-1]], [180], "last_cell"))[0][-1]
        sheet, size = compose_sheet([source])
        sheet.save(output / "battle_defeat.png")
        animations["defeat"] = {
            "file": "battle_defeat.png",
            "frame_size": list(size),
            "frame_count": 1,
            "timing_ms": [250],
            "source_sequence": "hit_pose_then_engine_fade",
            "derived": True,
        }

    if raw_components:
        save_resource_components(resource, output / "raw")
    return {
        "frame_size": list(frame_size),
        "frame_count": len(cells),
        "animations": animations,
        "palette_reference": _sha256(resource.palette),
        "animation_labels": [sequence.label for sequence in sequences],
    }


def export_walk(
    map_sprites: DuskMapSprites,
    entry: int,
    output: Path,
    *,
    raw_components: bool,
) -> dict | None:
    try:
        frames = map_sprites.frames(entry)
    except Exception:
        return None
    if len(frames) < 9:
        return None
    if len(frames) >= 15:
        # Dusk MCHR banks contain 25 poses. The initial extractor incorrectly
        # used 6:9 as the forward walk; those are intermediary/idle poses.
        # The cartridge's four directional walk triplets are 0:3, 3:6,
        # 9:12 and 12:15.
        directions = {
            "up": list(frames[0:3]),
            "left": list(frames[3:6]),
            "down": list(frames[9:12]),
            "right": list(frames[12:15]),
        }
    else:
        directions = {
            "up": list(frames[0:3]),
            "left": list(frames[3:6]),
            "down": list(frames[6:9]),
        }
        directions["right"] = [ImageOps.mirror(frame) for frame in directions["left"]]
    metadata: dict[str, dict] = {}
    for direction, direction_frames in directions.items():
        filename = f"walk_{direction}.png"
        sheet, frame_size = compose_sheet(direction_frames)
        sheet.save(output / filename)
        metadata[direction] = {
            "file": filename,
            "frame_size": list(frame_size),
            "frame_count": len(direction_frames),
            "timing_ms": [DEFAULT_WALK_MS] * len(direction_frames),
            "mirrored_from": "left" if direction == "right" and len(frames) < 15 else None,
        }
    if raw_components:
        raw_dir = output / "raw" / "walk"
        raw_dir.mkdir(parents=True, exist_ok=True)
        for name, data in map_sprites.raw_components(entry).items():
            (raw_dir / f"{name}.bin").write_bytes(data)
    return {"entry": entry, "directions": metadata}


def _copy_or_export_optional_sprite(
    context: RomContext,
    entry: int | None,
    filename: str,
    output: Path,
) -> dict | None:
    if entry is None or not 0 <= entry < context.coordinated.count:
        return None
    try:
        resource = context.coordinated.resource(entry)
        frames = resource.rendered_cells()
        sheet, frame_size = compose_sheet(frames)
        sheet.save(output / filename)
        return {
            "entry": entry,
            "file": filename,
            "frame_size": list(frame_size),
            "frame_count": len(frames),
        }
    except Exception:
        return None


def export_canonical_roster(
    contexts: list[RomContext],
    analyses: list[AnalyzedSource],
    groups: list[list[int]],
    output: Path,
    *,
    raw_components: bool,
) -> list[dict]:
    digimon_root = output / "digimon"
    digimon_root.mkdir(parents=True, exist_ok=True)
    roster: list[dict] = []
    for canonical_id, group in enumerate(groups, 1):
        members = []
        for analysis_index in group:
            analysis = analyses[analysis_index]
            context = contexts[analysis.context_index]
            species = context.species[analysis.species_index]
            members.append((analysis_index, analysis, context, species))
        display_species = max((member[3] for member in members), key=_name_score)
        display_name = canonical_display_name(display_species.display_name)
        preferred = max(
            members,
            key=lambda member: _asset_score(member[2], member[3], member[1]),
        )
        _, preferred_analysis, preferred_context, preferred_species = preferred
        slug = safe_slug(display_name, f"digimon_{canonical_id:03d}")
        folder = digimon_root / f"{canonical_id:03d}_{slug}"
        folder.mkdir(parents=True, exist_ok=True)
        notes: list[str] = []
        try:
            resource = _resource(preferred_context, preferred_species)
            battle_metadata = export_battle(
                resource,
                folder,
                raw_components=raw_components,
            )
        except Exception as exc:
            battle_metadata = {
                "frame_size": [1, 1],
                "frame_count": 0,
                "animations": {},
                "palette_reference": "",
                "animation_labels": [],
            }
            notes.append(f"Preferred battle resource failed: {type(exc).__name__}: {exc}")

        walk_metadata = None
        walk_source = next(
            (
                member
                for member in sorted(
                    members,
                    key=lambda item: _asset_score(item[2], item[3], item[1]),
                    reverse=True,
                )
                if member[2].map_sprites is not None
                and member[3].walk_entry is not None
            ),
            None,
        )
        if walk_source is not None:
            _, _, walk_context, walk_species = walk_source
            walk_metadata = export_walk(
                walk_context.map_sprites,
                walk_species.walk_entry,
                folder,
                raw_components=raw_components,
            )
        if walk_metadata is None:
            notes.append("No verified field-walking mapping in the selected source ROMs.")

        portrait = _copy_or_export_optional_sprite(
            preferred_context,
            preferred_species.portrait_entry,
            "portrait.png",
            folder,
        )
        full_body = _copy_or_export_optional_sprite(
            preferred_context,
            preferred_species.full_body_entry,
            "full_body.png",
            folder,
        )

        unique_variant_hashes: set[str] = {preferred_analysis.battle_hash}
        variants: list[dict] = []
        for _, analysis, context, species in members:
            variant = {
                "source_game": species.source_game,
                "source_rom": context.rom.path.name,
                "internal_id": species.internal_id,
                "source_name": species.display_name,
                "battle_entry": species.battle_entry,
                "battle_hash": analysis.battle_hash,
                "walk_entry": species.walk_entry,
                "portrait_entry": species.portrait_entry,
                "full_body_entry": species.full_body_entry,
                "analysis_error": analysis.error,
            }
            if (
                analysis.battle_hash
                and analysis.battle_hash not in unique_variant_hashes
                and not analysis.error
            ):
                variant_dir = (
                    folder
                    / "variants"
                    / f"{species.source_game}_{species.internal_id:04d}"
                )
                variant_dir.mkdir(parents=True, exist_ok=True)
                try:
                    variant_resource = _resource(context, species)
                    variant_cells = variant_resource.rendered_cells()
                    variant_sheet, _ = compose_sheet(variant_cells)
                    variant_sheet.save(variant_dir / "battle_all_cells.png")
                    if raw_components:
                        save_resource_components(variant_resource, variant_dir / "raw")
                    variant["asset_path"] = str(variant_dir.relative_to(folder)).replace("\\", "/")
                    unique_variant_hashes.add(analysis.battle_hash)
                except Exception as exc:
                    variant["export_error"] = f"{type(exc).__name__}: {exc}"
            variants.append(variant)

        source_ids = {
            source: sorted(
                {member[3].internal_id for member in members if member[3].source_game == source}
            )
            for source in sorted({member[3].source_game for member in members})
        }
        first_animation = battle_metadata["animations"].get("idle", {})
        metadata = {
            "canonical_id": canonical_id,
            "internal_id": preferred_species.internal_id,
            "display_name": display_name,
            "source_game": preferred_species.source_game,
            "source_ids": source_ids,
            "source_variants": variants,
            "frame_size": battle_metadata["frame_size"],
            "frame_count": battle_metadata["frame_count"],
            "timing_ms_per_frame": first_animation.get("timing_ms", []),
            "animations": battle_metadata["animations"],
            "has_walk_animation": walk_metadata is not None,
            "walk": walk_metadata,
            "portrait": portrait,
            "full_body": full_body,
            "palette_reference": battle_metadata["palette_reference"],
            "battle_animation_labels": battle_metadata["animation_labels"],
            "notes": notes,
        }
        (folder / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        roster.append(
            {
                "canonical_id": canonical_id,
                "display_name": display_name,
                "folder": str(folder.relative_to(output)).replace("\\", "/"),
                "source_game": preferred_species.source_game,
                "source_ids": source_ids,
                "has_walk_animation": walk_metadata is not None,
                "battle_ready": bool(battle_metadata["animations"]),
            }
        )
        if canonical_id % 50 == 0 or canonical_id == len(groups):
            print(f"Exported {canonical_id}/{len(groups)} canonical Digimon")
    return roster


def export_character_candidates(
    contexts: list[RomContext],
    output: Path,
) -> dict:
    root = output / "characters"
    root.mkdir(parents=True, exist_ok=True)
    exported = 0
    seen_hashes: set[str] = set()
    referenced_dusk_walk = {
        species.walk_entry
        for context in contexts
        if context.profile == "dusk"
        for species in context.species
        if species.walk_entry is not None
    }
    for context in contexts:
        if context.map_sprites is not None:
            for entry in range(context.map_sprites.count):
                if entry in referenced_dusk_walk:
                    continue
                try:
                    frames = context.map_sprites.frames(entry)
                except Exception:
                    continue
                if len(frames) < 9:
                    continue
                key = normalized_frame_hash(frames[:9])
                if key in seen_hashes:
                    continue
                seen_hashes.add(key)
                folder = root / f"dusk_mchr_{entry:04d}"
                folder.mkdir(parents=True, exist_ok=True)
                walk = export_walk(context.map_sprites, entry, folder, raw_components=False)
                if walk is None:
                    shutil.rmtree(folder)
                    continue
                metadata = {
                    "role": "npc_or_tamer_candidate",
                    "source_game": context.profile,
                    "entry": entry,
                    "walk": walk,
                    "notes": "Unreferenced Dusk MCHR entry; assign a semantic name in overrides.json.",
                }
                (folder / "metadata.json").write_text(
                    json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
                )
                exported += 1

        if context.profile in {"lost_evolution", "xros_red", "xros_blue"}:
            # Character/field entries precede the contiguous battle roster.
            battle_start = min(species.battle_entry for species in context.species)
            for entry in range(min(battle_start, context.coordinated.count)):
                try:
                    resource = context.coordinated.resource(entry)
                    frames = resource.rendered_cells()
                except Exception:
                    continue
                if len(frames) != 9 or max(max(frame.size) for frame in frames) > 96:
                    continue
                key = normalized_frame_hash(frames)
                if key in seen_hashes:
                    continue
                seen_hashes.add(key)
                folder = root / f"{context.profile}_spr_{entry:04d}"
                folder.mkdir(parents=True, exist_ok=True)
                directions = {
                    "up": list(frames[0:3]),
                    "left": list(frames[3:6]),
                    "down": list(frames[6:9]),
                }
                directions["right"] = [ImageOps.mirror(frame) for frame in directions["left"]]
                walk = {}
                for direction, direction_frames in directions.items():
                    filename = f"walk_{direction}.png"
                    sheet, frame_size = compose_sheet(direction_frames)
                    sheet.save(folder / filename)
                    walk[direction] = {
                        "file": filename,
                        "frame_size": list(frame_size),
                        "frame_count": 3,
                        "timing_ms": [DEFAULT_WALK_MS] * 3,
                    }
                (folder / "metadata.json").write_text(
                    json.dumps(
                        {
                            "role": "npc_tamer_or_field_candidate",
                            "source_game": context.profile,
                            "entry": entry,
                            "walk": walk,
                            "notes": "Nine-cell directional candidate; assign a semantic name in overrides.json.",
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                exported += 1
    return {"exported_character_candidates": exported, "unique_hashes": len(seen_hashes)}


def safe_clean_output(output: Path) -> None:
    output = output.resolve()
    if output.name.casefold() != "extracted" or output.parent.name.casefold() != "work":
        raise ValueError(
            "Refusing to clean an output that is not exactly a work/extracted directory"
        )
    if output.exists():
        shutil.rmtree(output)


def extract_batch(
    rom_paths: list[Path],
    output: Path,
    *,
    clean: bool = False,
    raw_components: bool = False,
    characters: bool = False,
) -> dict:
    if clean:
        safe_clean_output(output)
    output.mkdir(parents=True, exist_ok=True)
    contexts: list[RomContext] = []
    failures: list[dict] = []
    seen_profiles: dict[str, int] = {}
    for path in rom_paths:
        try:
            context = load_context(path)
            # Prefer a later path for the same game profile; this lets a user
            # provide a localized Blue ROM instead of the original Japanese one.
            if context.profile in seen_profiles:
                existing = seen_profiles[context.profile]
                contexts[existing] = context
            else:
                seen_profiles[context.profile] = len(contexts)
                contexts.append(context)
            print(
                f"Loaded {context.profile}: {len(context.species)} species from {path.name}"
            )
        except Exception as exc:
            failures.append({"rom": str(path), "error": f"{type(exc).__name__}: {exc}"})
    if not contexts:
        raise RuntimeError("No supported ROMs could be loaded")

    analyses = analyze_contexts(contexts)
    groups = build_groups(contexts, analyses)
    roster = export_canonical_roster(
        contexts,
        analyses,
        groups,
        output,
        raw_components=raw_components,
    )
    character_report = (
        export_character_candidates(contexts, output)
        if characters
        else {"exported_character_candidates": 0, "unique_hashes": 0}
    )
    (output / "roster.json").write_text(
        json.dumps(roster, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = {
        "schema_version": 1,
        "roms": [
            {
                "profile": context.profile,
                "filename": context.rom.path.name,
                "game_code": context.rom.header.game_code,
                "title": context.rom.header.title,
                "sha256": _rom_sha256(context.rom.path),
                "source_species": len(context.species),
            }
            for context in contexts
        ],
        "source_species_total": len(analyses),
        "canonical_species_total": len(roster),
        "deduplicated_entries": len(analyses) - len(roster),
        "battle_ready": sum(item["battle_ready"] for item in roster),
        "with_walk_animation": sum(item["has_walk_animation"] for item in roster),
        "character_candidates": character_report,
        "rom_load_failures": failures,
    }
    (output / "import_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def extract_proof(rom_path: Path, name: str, output: Path) -> dict:
    context = load_context(rom_path)
    requested = normalize_name(name)
    matches = [
        species for species in context.species if normalize_name(species.display_name) == requested
    ]
    if not matches:
        raise ValueError(f"{name!r} was not found in {context.profile}")
    species = matches[0]
    output.mkdir(parents=True, exist_ok=True)
    resource = _resource(context, species)
    battle = export_battle(resource, output, raw_components=True)
    walk = None
    if context.map_sprites is not None and species.walk_entry is not None:
        walk = export_walk(
            context.map_sprites,
            species.walk_entry,
            output,
            raw_components=True,
        )
    metadata = {
        **species.to_dict(),
        **battle,
        "has_walk_animation": walk is not None,
        "walk": walk,
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


def verify_extraction(output: Path) -> dict:
    roster_path = output / "roster.json"
    if not roster_path.is_file():
        raise FileNotFoundError(f"Missing {roster_path}")
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    redirects_path = output / "canonical_redirects.json"
    redirect_document = (
        json.loads(redirects_path.read_text(encoding="utf-8"))
        if redirects_path.is_file()
        else {}
    )
    redirects = redirect_document.get("redirects", redirect_document)
    errors: list[str] = []
    names: set[str] = set()
    ids: set[int] = set()
    battle_ready = walk_ready = 0
    for item in roster:
        canonical_id = item["canonical_id"]
        if canonical_id in ids:
            errors.append(f"Duplicate canonical ID {canonical_id}")
        ids.add(canonical_id)
        # Redirected source slots remain in the extraction audit so their files
        # can be inspected, but are hidden from the playable roster.
        if str(canonical_id) not in redirects:
            normalized = normalize_name(item["display_name"])
            if normalized and normalized in names:
                errors.append(f"Duplicate canonical name {item['display_name']}")
            names.add(normalized)
        folder = output / item["folder"]
        metadata_path = folder / "metadata.json"
        if not metadata_path.is_file():
            errors.append(f"Missing metadata for {canonical_id}")
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        animations = metadata.get("animations", {})
        required = {"idle", "hit", "defeat"}
        for animation_name in sorted(required - set(animations)):
            errors.append(
                f"Missing {animation_name} animation for canonical ID {canonical_id}"
            )
        if not any(name.startswith("attack") for name in animations):
            errors.append(f"Missing attack animation for canonical ID {canonical_id}")
        for animation in animations.values():
            if not (folder / animation["file"]).is_file():
                errors.append(
                    f"Missing {animation['file']} for canonical ID {canonical_id}"
                )
        if item.get("battle_ready"):
            battle_ready += 1
        if item.get("has_walk_animation"):
            walk_ready += 1
    mechanics_path = output / "mechanics.json"
    mechanics_species = verified_mechanics = estimated_mechanics = 0
    playable_battle_ready = playable_walk_ready = 0
    if not mechanics_path.is_file():
        errors.append("Missing mechanics.json; run the mechanics command after batch")
    else:
        mechanics = json.loads(mechanics_path.read_text(encoding="utf-8"))
        species_data = mechanics.get("species", {})
        skill_data = mechanics.get("skills", {})
        mechanics_species = len(species_data)
        playable_ids = set(map(int, species_data))
        playable_battle_ready = sum(
            bool(item.get("battle_ready"))
            for item in roster
            if int(item["canonical_id"]) in playable_ids
        )
        playable_walk_ready = sum(
            bool(item.get("has_walk_animation"))
            for item in roster
            if int(item["canonical_id"]) in playable_ids
        )
        roster_ids = {int(item["canonical_id"]) for item in roster}
        unknown_mechanics_ids = set(map(int, species_data)) - roster_ids
        if unknown_mechanics_ids:
            errors.append(
                "Mechanics references unknown canonical IDs: "
                + ", ".join(map(str, sorted(unknown_mechanics_ids)))
            )
        for item in roster:
            canonical_id = item["canonical_id"]
            record = species_data.get(str(canonical_id))
            if not isinstance(record, dict):
                # Blank and question-mark slots are retained in the raw asset
                # audit but are deliberately excluded from the playable roster.
                continue
            provenance = record.get("provenance")
            if provenance == "rom_verified":
                verified_mechanics += 1
            elif provenance == "compatibility_estimate":
                estimated_mechanics += 1
            else:
                errors.append(
                    f"Invalid mechanics provenance for canonical ID {canonical_id}: {provenance}"
                )
            base_stats = record.get("base_stats", {})
            for stat in ("hp", "mp", "attack", "defense", "spirit", "speed"):
                if not isinstance(base_stats.get(stat), (int, float)) or base_stats[stat] <= 0:
                    errors.append(f"Invalid {stat} for canonical ID {canonical_id}")
            for learned in record.get("learnset", []):
                skill_id = learned.get("skill_id")
                if skill_id not in skill_data:
                    errors.append(
                        f"Missing skill {skill_id!r} for canonical ID {canonical_id}"
                    )
    return {
        "source_asset_slots": len(roster),
        "canonical_species": mechanics_species,
        "battle_ready": playable_battle_ready,
        "walk_ready": playable_walk_ready,
        "source_slot_battle_ready": battle_ready,
        "source_slot_walk_ready": walk_ready,
        "mechanics_species": mechanics_species,
        "rom_verified_mechanics": verified_mechanics,
        "estimated_mechanics": estimated_mechanics,
        "errors": errors,
        "ok": not errors,
    }
