from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any


UI_PREFIXES = (
    "b_dwaku",
    "bt_",
    "mshp",
    "sp_",
    "t_menubg",
)


def _link(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def _copy_json(source: Path, target: Path) -> Any:
    data = json.loads(source.read_text(encoding="utf-8"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return data


def build(extracted: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    catalog: dict[str, Any] = {
        "purpose": "Private cartridge-extracted map-builder reference kit",
        "native_dimensions_preserved": True,
        "maps": [],
        "battle_stages": [],
        "ui": [],
        "character_sheets": [],
        "digimon_field_sheets": [],
        "digimon_battle_sheets": [],
        "audio_samples": [],
        "music_tracks": [],
    }

    environments = extracted / "environments"
    for game_dir in sorted(path for path in environments.glob("*") if path.is_dir()):
        manifest_path = game_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        game = game_dir.name
        for record in manifest.get("backgrounds", []):
            relative = record.get("path")
            if not relative:
                continue
            source = game_dir / relative
            if not source.is_file():
                continue
            source_stem = Path(str(record.get("source", ""))).name.casefold()
            kind = str(record.get("kind", "background"))
            if kind in {"field_map", "packed_field_map"}:
                target = output / "maps" / game / Path(relative).name
                group = "maps"
                extras = ("walkable_mask",)
            elif kind.startswith("battle_stage"):
                selected = record.get("composite") or record.get("screen") or relative
                source = game_dir / selected
                target = output / "battle_stages" / game / Path(selected).name
                group = "battle_stages"
                extras = ()
            elif source_stem.startswith(UI_PREFIXES):
                target = output / "battle_ui" / game / Path(relative).name
                group = "ui"
                extras = ()
            else:
                continue
            _link(source, target)
            entry = {
                "game": game,
                "source": record.get("source"),
                "file": target.relative_to(output).as_posix(),
                "width": record.get("width"),
                "height": record.get("height"),
                "kind": kind,
            }
            catalog[group].append(entry)
            for extra in extras:
                extra_relative = record.get(extra)
                if extra_relative and (game_dir / extra_relative).is_file():
                    extra_target = target.with_name(Path(extra_relative).name)
                    _link(game_dir / extra_relative, extra_target)
                    entry[extra] = extra_target.relative_to(output).as_posix()

    characters = extracted / "characters"
    for folder in sorted(path for path in characters.glob("*") if path.is_dir()):
        metadata_path = folder / "metadata.json"
        if not metadata_path.is_file():
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        target_dir = output / "npc_tamer_field_candidates" / folder.name
        for path in folder.iterdir():
            if path.is_file() and path.suffix.casefold() in {".png", ".json"}:
                _link(path, target_dir / path.name)
        catalog["character_sheets"].append(
            {
                "folder": target_dir.relative_to(output).as_posix(),
                "source_game": metadata.get("source_game"),
                "native_frame_size": metadata.get("frame_size"),
                "candidate_only": True,
            }
        )

    roster_path = extracted / "roster.json"
    redirects_path = extracted / "canonical_redirects.json"
    redirect_document = (
        json.loads(redirects_path.read_text(encoding="utf-8"))
        if redirects_path.is_file()
        else {}
    )
    redirects = redirect_document.get("redirects", redirect_document)
    if roster_path.is_file():
        roster = json.loads(roster_path.read_text(encoding="utf-8"))
        mechanics_path = extracted / "mechanics.json"
        playable_ids = (
            set(json.loads(mechanics_path.read_text(encoding="utf-8")).get("species", {}))
            if mechanics_path.is_file()
            else {str(item.get("canonical_id")) for item in roster}
        )
        for item in roster:
            canonical_id = int(item.get("canonical_id", 0))
            if str(canonical_id) in redirects or str(canonical_id) not in playable_ids:
                continue
            source_dir = extracted / str(item.get("folder", ""))
            metadata_path = source_dir / "metadata.json"
            if not metadata_path.is_file():
                continue
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            safe_folder = source_dir.name
            battle_target = output / "digimon_battle" / safe_folder
            field_target = output / "digimon_field" / safe_folder
            for name, animation in metadata.get("animations", {}).items():
                relative = animation.get("file")
                source = source_dir / str(relative or "")
                if not source.is_file():
                    continue
                target_root = field_target if name.startswith("walk_") else battle_target
                target = target_root / source.name
                _link(source, target)
                record = {
                    "canonical_id": canonical_id,
                    "display_name": item.get("display_name"),
                    "animation": name,
                    "file": target.relative_to(output).as_posix(),
                    "native_frame_size": animation.get("frame_size"),
                    "frame_count": animation.get("frame_count"),
                    "timing_ms": animation.get("timing_ms"),
                    "source_game": item.get("source_game"),
                }
                if name.startswith("walk_"):
                    catalog["digimon_field_sheets"].append(record)
                else:
                    catalog["digimon_battle_sheets"].append(record)
            walk = metadata.get("walk") or {}
            for direction, animation in walk.get("directions", {}).items():
                relative = animation.get("file")
                source = source_dir / str(relative or "")
                if not source.is_file():
                    continue
                target = field_target / source.name
                _link(source, target)
                catalog["digimon_field_sheets"].append(
                    {
                        "canonical_id": canonical_id,
                        "display_name": item.get("display_name"),
                        "animation": f"walk_{direction}",
                        "file": target.relative_to(output).as_posix(),
                        "native_frame_size": animation.get("frame_size"),
                        "frame_count": animation.get("frame_count"),
                        "timing_ms": animation.get("timing_ms"),
                        "source_game": item.get("source_game"),
                    }
                )
            if field_target.is_dir():
                _link(metadata_path, field_target / "metadata.json")
            if battle_target.is_dir():
                _link(metadata_path, battle_target / "metadata.json")

    audio_root = extracted / "audio"
    for catalog_path in sorted(audio_root.glob("*/catalog.json")):
        game = catalog_path.parent.name
        audio_catalog = _copy_json(
            catalog_path, output / "audio" / game / "catalog.json"
        )
        for sample in audio_catalog.get("samples", []):
            relative = sample.get("path")
            source = catalog_path.parent / str(relative or "")
            if not source.is_file():
                continue
            target = output / "audio" / game / str(relative)
            _link(source, target)
            catalog["audio_samples"].append(
                {
                    "game": game,
                    "file": target.relative_to(output).as_posix(),
                    "sample_rate": sample.get("sample_rate"),
                    "duration_ms": sample.get("duration_ms"),
                    "looped": sample.get("looped"),
                }
            )
        for source in sorted((catalog_path.parent / "music").glob("*.wav")):
            target = output / "audio" / game / "music" / source.name
            _link(source, target)
            catalog["music_tracks"].append(
                {"game": game, "file": target.relative_to(output).as_posix()}
            )

    (output / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "README.txt").write_text(
        """DIGITAL CROSSROADS - PRIVATE MAP BUILDER REFERENCE KIT

All files in this folder were reconstructed locally from the owner's cartridge dumps.
Keep this folder private. It is deliberately stored under work/ and is not a source asset.

maps/                         Complete map images plus cartridge walkability masks.
battle_stages/                Battle-stage composites at their native dimensions.
battle_ui/                    Original Dusk battle/menu panels, including gauge artwork.
npc_tamer_field_candidates/   Four-direction candidate sheets; identities need QA.
digimon_field/                Canonically deduplicated Digimon walk sheets when available.
digimon_battle/               Canonically deduplicated battle animation sheets.
audio/                        Decoded cartridge samples and sequence/sample catalog.

Read catalog.json before editing. Preserve pixel dimensions, nearest-neighbor pixels,
alpha, and frame order. Never rescale an individual field object independently to make
it look bigger; compose maps at the source game's native scale.
""",
        encoding="utf-8",
    )
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a clean private reference kit")
    parser.add_argument("--extracted", type=Path, default=Path("work/extracted"))
    parser.add_argument("--output", type=Path, default=Path("work/map_builder_kit"))
    args = parser.parse_args()
    catalog = build(args.extracted.resolve(), args.output.resolve())
    print(json.dumps({key: len(value) for key, value in catalog.items() if isinstance(value, list)}, indent=2))
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
