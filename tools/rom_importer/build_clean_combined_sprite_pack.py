#!/usr/bin/env python
"""Build a clean-ROM-only, deduplicated Digimon sprite reference pack.

The importer output is already tied to SHA-256 identified clean cartridge
dumps. This exporter never reads edited ROMs or generated artwork. It groups
species canonically by name, retains pixel-distinct battle variants, and
records every clean source that contributed the same artwork.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

from PIL import Image


ALLOWED_SOURCES = {"dusk", "lost_evolution", "xros_blue", "xros_red"}
SOURCE_LABELS = {
    "dusk": "Digimon World Dusk (USA)",
    "lost_evolution": "Digimon Story Lost Evolution (Japan)",
    "xros_blue": "Digimon Story Super Xros Wars Blue (Japan)",
    "xros_red": "Digimon Story Super Xros Wars Red (Japan)",
}
COPY_FILES = (
    "battle_all_cells.png",
    "battle_idle.png",
    "battle_attack_01.png",
    "battle_hit.png",
    "battle_defeat.png",
    "walk_down.png",
    "walk_left.png",
    "walk_up.png",
    "walk_right.png",
    "portrait.png",
    "full_body.png",
)


def safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]', "_", value).strip(" .")
    return value or "Unknown Digimon"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_if_present(source: Path, target: Path, filename: str) -> bool:
    path = source / filename
    if not path.is_file():
        return False
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target / filename)
    return True


def make_native_walk_sheet(source: Path, destination: Path) -> bool:
    """Write the nine frames actually stored by Dusk: Down, Left, Up."""
    paths = [source / f"walk_{direction}.png" for direction in ("down", "left", "up")]
    if not all(path.is_file() for path in paths):
        return False
    images = [Image.open(path).convert("RGBA") for path in paths]
    try:
        width = max(image.width for image in images)
        height = sum(image.height for image in images)
        sheet = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        y = 0
        for image in images:
            sheet.alpha_composite(image, ((width - image.width) // 2, y))
            y += image.height
        destination.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(destination)
    finally:
        for image in images:
            image.close()
    return True


def locate_artwork(species_dir: Path, metadata: dict, battle_hash: str) -> Path | None:
    primary_hashes = {
        str(item.get("battle_hash", ""))
        for item in metadata.get("source_variants", [])
        if not item.get("asset_path")
    }
    if battle_hash in primary_hashes and (species_dir / "battle_all_cells.png").is_file():
        return species_dir
    for item in metadata.get("source_variants", []):
        if item.get("battle_hash") != battle_hash or not item.get("asset_path"):
            continue
        candidate = species_dir / str(item["asset_path"])
        if (candidate / "battle_all_cells.png").is_file():
            return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extracted", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    extracted = args.extracted.resolve()
    output = args.output.resolve()
    roster = json.loads((extracted / "roster.json").read_text(encoding="utf-8"))
    import_report = json.loads((extracted / "import_report.json").read_text(encoding="utf-8"))
    clean_roms = {
        entry["profile"]: {
            "filename": entry["filename"],
            "game_code": entry["game_code"],
            "title": entry["title"],
            "sha256": entry["sha256"],
            "source_species": entry["source_species"],
        }
        for entry in import_report["roms"]
        if entry["profile"] in ALLOWED_SOURCES
    }
    if set(clean_roms) != ALLOWED_SOURCES:
        raise SystemExit(f"missing clean source profiles: {sorted(ALLOWED_SOURCES - set(clean_roms))}")

    output.mkdir(parents=True, exist_ok=True)
    complete_root = output / "01 Complete Digimon Packs"
    battle_root = output / "02 Battle Sheets"
    walk_root = output / "03 Native Field Walk Sheets - 9 Stored Frames"
    icon_root = output / "04 Battle and Menu Icons"
    field_root = output / "05 Field and Card Sprites"
    variant_root = output / "06 Pixel-Distinct Source Variants"
    for folder in (complete_root, battle_root, walk_root, icon_root, field_root, variant_root):
        folder.mkdir(parents=True, exist_ok=True)

    index_rows: list[dict] = []
    source_rows: list[dict] = []
    hashes: dict[str, list[str]] = defaultdict(list)
    explicit_xros_agumon: dict | None = None
    missing_artwork: list[dict] = []

    for position, roster_item in enumerate(roster, 1):
        species_dir = extracted / str(roster_item["folder"])
        metadata = json.loads((species_dir / "metadata.json").read_text(encoding="utf-8"))
        canonical_id = int(metadata["canonical_id"])
        display_name = str(metadata["display_name"])
        prefix = f"{canonical_id:03d} - {safe_name(display_name)}"
        species_output = complete_root / prefix
        species_output.mkdir(parents=True, exist_ok=True)

        copied = [filename for filename in COPY_FILES if copy_if_present(species_dir, species_output, filename)]
        (species_output / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if (species_dir / "battle_all_cells.png").is_file():
            shutil.copy2(species_dir / "battle_all_cells.png", battle_root / f"{prefix} - battle sheet.png")
        if make_native_walk_sheet(species_dir, walk_root / f"{prefix} - native walking sheet.png"):
            native_walk_frames = 9
        else:
            native_walk_frames = 0
        if (species_dir / "portrait.png").is_file():
            shutil.copy2(species_dir / "portrait.png", icon_root / f"{prefix} - battle menu icon.png")
        if (species_dir / "full_body.png").is_file():
            shutil.copy2(species_dir / "full_body.png", field_root / f"{prefix} - field card sprite.png")

        variants_by_hash: dict[str, list[dict]] = defaultdict(list)
        for source in metadata.get("source_variants", []):
            if source.get("source_game") in ALLOWED_SOURCES and source.get("battle_hash"):
                variants_by_hash[str(source["battle_hash"])].append(source)

        primary_hash = next(
            (str(item["battle_hash"]) for item in metadata.get("source_variants", [])
             if item.get("source_game") == metadata.get("source_game") and item.get("battle_hash")),
            "",
        )
        variant_records = []
        for variant_number, (battle_hash, sources) in enumerate(variants_by_hash.items(), 1):
            artwork = locate_artwork(species_dir, metadata, battle_hash)
            source_games = sorted({str(item["source_game"]) for item in sources})
            is_primary = battle_hash == primary_hash
            variant = {
                "variant_number": variant_number,
                "battle_hash": battle_hash,
                "is_primary_artwork": is_primary,
                "source_games": source_games,
                "sources": sources,
                "artwork_available": artwork is not None,
            }
            variant_records.append(variant)
            if artwork is None:
                missing_artwork.append({"canonical_id": canonical_id, "name": display_name, **variant})
            elif not is_primary:
                label = " + ".join(SOURCE_LABELS[name] for name in source_games)
                target = variant_root / prefix / f"Variant {variant_number:02d} - {safe_name(label)}"
                copy_if_present(artwork, target, "battle_all_cells.png")
                (target / "source.json").write_text(json.dumps(variant, ensure_ascii=False, indent=2), encoding="utf-8")

            for source in sources:
                row = {
                    "canonical_id": canonical_id,
                    "display_name": display_name,
                    "source_game": source["source_game"],
                    "source_label": SOURCE_LABELS[source["source_game"]],
                    "source_internal_id": source.get("internal_id"),
                    "source_name": source.get("source_name", ""),
                    "battle_hash": battle_hash,
                    "shared_variant_sources": ";".join(source_games),
                    "pixel_distinct_from_primary": not is_primary,
                    "artwork_available": artwork is not None,
                }
                source_rows.append(row)
                if display_name.casefold() == "agumon" and source["source_game"] == "xros_blue":
                    explicit_xros_agumon = row

        entry = {
            "canonical_id": canonical_id,
            "display_name": display_name,
            "primary_source": metadata.get("source_game"),
            "source_games": sorted({item["source_game"] for item in source_rows if item["canonical_id"] == canonical_id}),
            "battle_ready": bool(metadata.get("animations")),
            "has_walk_animation": bool(metadata.get("has_walk_animation")),
            "native_stored_walk_frames": native_walk_frames,
            "right_direction": "mirrored_from_left" if native_walk_frames else "unavailable",
            "files": copied,
            "pixel_distinct_battle_variants": len(variants_by_hash),
            "variants": variant_records,
        }
        (species_output / "pack-entry.json").write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
        index_rows.append({key: value for key, value in entry.items() if key not in {"files", "variants"}})
        if (species_dir / "battle_all_cells.png").is_file():
            hashes[sha256(species_dir / "battle_all_cells.png")].append(prefix)
        if position % 100 == 0:
            print(f"Exported {position}/{len(roster)} canonical Digimon", flush=True)

    if explicit_xros_agumon is None:
        raise SystemExit("Xros Blue Agumon was not found; refusing to publish an incomplete pack")
    agumon_marker = output / "XROS BLUE AGUMON - VERIFIED.json"
    agumon_marker.write_text(json.dumps(explicit_xros_agumon, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_csv(path: Path, rows: list[dict]) -> None:
        if not rows:
            return
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    write_csv(output / "sprite-index.csv", index_rows)
    write_csv(output / "source-provenance-index.csv", source_rows)
    duplicate_hashes = {key: value for key, value in hashes.items() if len(value) > 1}
    manifest = {
        "format": "clean-ds-digimon-sprite-collection-v51",
        "policy": {
            "clean_rom_only": True,
            "excluded": ["edited ROMs", "fan-made Digimon", "generated PixelForge art", "mod-derived assets"],
            "dedupe": "one canonical species folder; pixel-distinct source artwork retained as variants; Xros Red/Blue identical slots share one variant",
            "field_walk": "9 native frames: Down x3, Left x3, Up x3; Right is mirrored from Left at runtime",
        },
        "clean_rom_sources": clean_roms,
        "canonical_species": len(index_rows),
        "source_records": len(source_rows),
        "with_native_walk": sum(1 for item in index_rows if item["has_walk_animation"]),
        "total_battle_art_sets": sum(int(item["pixel_distinct_battle_variants"]) for item in index_rows),
        "alternate_pixel_distinct_variant_sets": sum(max(0, int(item["pixel_distinct_battle_variants"]) - 1) for item in index_rows),
        "unresolved_variant_artwork": len(missing_artwork),
        "xros_blue_agumon": explicit_xros_agumon,
        "unexpected_cross_name_identical_primary_sheets": duplicate_hashes,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "QA - missing variant artwork.json").write_text(json.dumps(missing_artwork, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "README.txt").write_text(
        "ALL DIGIMON SPRITE ASSETS - CLEAN COMBINED v51\n\n"
        "Sources: clean Digimon World Dusk (USA), Lost Evolution (Japan), and Super Xros Wars Red/Blue (Japan) cartridge dumps.\n"
        "No edited-ROM, custom Digimon, PixelForge-generated, or other mod assets are included.\n\n"
        "Canonical species are deduplicated by identity. Pixel-distinct source art is retained under 06 Pixel-Distinct Source Variants.\n"
        "Xros Red and Blue copies of identical artwork are represented once and both sources are recorded in metadata.\n"
        "Xros Blue Agumon is explicitly verified by XROS BLUE AGUMON - VERIFIED.json.\n\n"
        "FIELD WALK FORMAT: the DS stores 9 frames: Down x3, Left x3, Up x3. Right is a horizontal mirror of Left.\n"
        "Each complete pack includes walk_right.png for convenience, but metadata marks it as derived.\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(output),
        "canonical_species": len(index_rows),
        "source_records": len(source_rows),
        "xros_blue_agumon": explicit_xros_agumon,
        "missing_variant_artwork": len(missing_artwork),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
