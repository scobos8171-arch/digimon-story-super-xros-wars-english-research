"""Build a reviewable library of native Xros Blue nine-frame field sprites.

This intentionally keeps identity confidence separate from asset validity.  A
sprite may be a perfectly valid native walk sheet even when the historical
``internal id + 266`` name proposal is wrong in the late Xros block.

Outputs are written below ``outputs/Xros Native Field Sprite Recovery Pack``:

* ``all_native_nine_frame`` preserves every nine-frame Xros candidate.
* ``verified_named`` contains prior visual approvals, explicit human
  confirmations, and byte-exact normalized-frame matches to clean Lost
  Evolution resources.
* ``review_pages`` provides labeled contact sheets for fast visual auditing.
* ``special_comparisons`` includes useful cross-game variants such as
  Minervamon.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.rom_importer.extractor import load_context
from tools.rom_importer.sprites import compose_sheet, normalized_frame_hash


ROOT = Path(r"C:\Users\YOUR_NAME\Documents\Codex\2026-07-24\c-users-scobo-downloads-download-digimon")
CHARACTERS = ROOT / "work" / "extracted" / "characters"
ROSTER = ROOT / "work" / "extracted" / "roster.json"
REVIEW = ROOT / "work" / "qa_reports" / "field_walk_visual_review.json"
OUTPUT = ROOT / "outputs" / "Xros Native Field Sprite Recovery Pack"
XROS_ROM = ROOT / "work" / "roms" / "xros_blue.nds"
LOST_ROM = ROOT / "work" / "roms" / "lost_evolution.nds"

# These are direct visual identifications by the project owner.  They override
# formula-derived labels but do not renumber or destroy the original resource.
HUMAN_OVERRIDES = {
    657: {
        "canonical_id": 635,
        "display_name": "Tactimon",
        "confidence": "human_confirmed_from_all_nine_frames",
        "notes": "Owner visually confirmed Xros field entry 657 as Tactimon.",
    },
}


def read_json(path: Path, default):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def key_name(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return value or "unnamed"


def walk_records(metadata: dict) -> dict:
    walk = metadata.get("walk")
    return walk if isinstance(walk, dict) else {}


def is_nine_frame_walk(metadata: dict) -> bool:
    walk = walk_records(metadata)
    return all(
        isinstance(walk.get(direction), dict)
        and int(walk[direction].get("frame_count", 0)) == 3
        and walk[direction].get("file")
        for direction in ("up", "down", "left", "right")
    )


def copy_walk(source: Path, target: Path, metadata: dict, extra: dict) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for direction, record in walk_records(metadata).items():
        if not isinstance(record, dict):
            continue
        filename = str(record.get("file", ""))
        source_file = source / filename
        if filename and source_file.is_file():
            shutil.copy2(source_file, target / filename)
    output_metadata = {**metadata, **extra}
    (target / "metadata.json").write_text(
        json.dumps(output_metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def export_native_walk(target: Path, frames: tuple[Image.Image, ...], extra: dict) -> dict:
    """Write one native Xros nine-cell resource without cross-game deduping."""
    target.mkdir(parents=True, exist_ok=True)
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
        sheet.save(target / filename)
        walk[direction] = {
            "file": filename,
            "frame_size": list(frame_size),
            "frame_count": 3,
            "timing_ms": [160, 160, 160],
        }
    metadata = {
        "role": "native_xros_field_resource",
        "source_game": "xros_blue_clean_rom",
        "walk": walk,
        **extra,
    }
    (target / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return metadata


def preview_frame(folder: Path, metadata: dict) -> Image.Image:
    down = walk_records(metadata).get("down", {})
    path = folder / str(down.get("file", ""))
    if not path.is_file():
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    sheet = Image.open(path).convert("RGBA")
    size = down.get("frame_size", [sheet.width // 3, sheet.height])
    width = max(1, int(size[0]))
    height = max(1, int(size[1]))
    return sheet.crop((width, 0, min(sheet.width, width * 2), min(sheet.height, height)))


def contained(canvas: Image.Image, image: Image.Image, box: tuple[int, int, int, int]) -> None:
    bounds = image.getbbox()
    if not bounds:
        return
    image = image.crop(bounds)
    left, top, right, bottom = box
    scale = min((right - left) / image.width, (bottom - top) / image.height, 4.0)
    image = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.Resampling.NEAREST,
    )
    x = left + (right - left - image.width) // 2
    y = bottom - image.height
    canvas.alpha_composite(image, (x, y))


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    all_root = OUTPUT / "all_native_nine_frame"
    verified_root = OUTPUT / "verified_named"
    review_root = OUTPUT / "review_pages"
    comparisons = OUTPUT / "special_comparisons"
    for folder in (all_root, verified_root, review_root, comparisons):
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)

    roster = read_json(ROSTER, [])
    id_to_roster: dict[int, list[dict]] = {}
    for row in roster:
        for source_id in row.get("source_ids", {}).get("xros_blue", []):
            if isinstance(source_id, int):
                id_to_roster.setdefault(source_id, []).append(row)

    review = read_json(REVIEW, {})
    decisions_by_asset = {
        str(row.get("candidate_asset_id")): row
        for row in review.get("decisions", [])
        if isinstance(row, dict) and row.get("candidate_asset_id")
    }

    if not XROS_ROM.is_file():
        raise FileNotFoundError(f"Clean Xros Blue ROM not found: {XROS_ROM}")
    context = load_context(XROS_ROM)
    battle_start = min(species.battle_entry for species in context.species)

    # Lost Evolution shares a large amount of field art with Xros.  Exact
    # nine-frame hashes let us restore identities that the old exporter threw
    # away as duplicates, without relying on the fragile late-Xros offset.
    lost_hash_names: dict[str, list[dict]] = {}
    if LOST_ROM.is_file():
        lost = load_context(LOST_ROM)
        lost_battle_start = min(species.battle_entry for species in lost.species)
        lost_id_to_roster: dict[int, list[dict]] = {}
        for row in roster:
            for source_id in row.get("source_ids", {}).get("lost_evolution", []):
                if isinstance(source_id, int):
                    lost_id_to_roster.setdefault(source_id, []).append(row)
        for lost_entry in range(min(lost_battle_start, lost.coordinated.count)):
            lost_internal_id = lost_entry - 474
            names = lost_id_to_roster.get(lost_internal_id, [])
            if not names:
                continue
            try:
                lost_frames = lost.coordinated.resource(lost_entry).rendered_cells()
            except Exception:
                continue
            if len(lost_frames) != 9 or max(max(frame.size) for frame in lost_frames) > 96:
                continue
            lost_hash_names.setdefault(normalized_frame_hash(lost_frames), []).extend(names)

    rows: list[dict] = []
    for entry in range(min(battle_start, context.coordinated.count)):
        try:
            frames = context.coordinated.resource(entry).rendered_cells()
        except Exception:
            continue
        if len(frames) != 9 or max(max(frame.size) for frame in frames) > 96:
            continue

        asset_id = f"xros_blue_spr_{entry:04d}"
        inferred_id = entry - 266
        predictions = id_to_roster.get(inferred_id, [])
        prediction_names = [str(row.get("display_name", "")) for row in predictions]
        decision = decisions_by_asset.get(asset_id)
        override = HUMAN_OVERRIDES.get(entry)
        exact_lost_matches = lost_hash_names.get(normalized_frame_hash(frames), [])
        exact_unique = {
            int(row.get("canonical_id")): row
            for row in exact_lost_matches
            if row.get("canonical_id") is not None
        }

        if override:
            display_name = str(override["display_name"])
            canonical_id = int(override["canonical_id"])
            status = "human_confirmed"
            confidence = str(override["confidence"])
            notes = str(override["notes"])
        elif decision and decision.get("decision") == "accepted_visual_match":
            display_name = str(decision.get("display_name") or f"entry {entry}")
            canonical_id = int(decision.get("canonical_id"))
            status = "visual_verified"
            confidence = "prior_side_by_side_visual_approval"
            notes = str(decision.get("notes", ""))
        elif len(exact_unique) == 1:
            matched = next(iter(exact_unique.values()))
            display_name = str(matched.get("display_name") or f"entry {entry}")
            canonical_id = int(matched.get("canonical_id"))
            status = "exact_cross_game_match"
            confidence = "all_nine_native_frames_identical_to_lost_evolution"
            notes = "Identity restored from an exact nine-frame clean-ROM match to Lost Evolution."
        elif decision and decision.get("decision") == "rejected_visual_mismatch":
            display_name = f"Unidentified entry {entry}"
            canonical_id = None
            status = "valid_sprite_rejected_name_mapping"
            confidence = "native_asset_identity_unknown"
            notes = (
                f"Rejected prior prediction: {decision.get('display_name')}. "
                f"{decision.get('notes', '')}"
            ).strip()
        elif prediction_names:
            display_name = prediction_names[0]
            canonical_id = int(predictions[0].get("canonical_id"))
            status = "formula_predicted_unverified"
            confidence = "xros_internal_id_plus_266_prediction"
            notes = "Preserved for review; name has not been visually approved."
        else:
            display_name = f"Unidentified entry {entry}"
            canonical_id = None
            status = "unidentified_native_sprite"
            confidence = "native_asset_identity_unknown"
            notes = "Nine-frame native sprite outside the currently named roster mapping."

        slug = key_name(display_name)
        target_name = f"{entry:04d}_{slug}"
        provenance = {
            "asset_id": asset_id,
            "source_game": "xros_blue_clean_rom",
            "source_entry": entry,
            "inferred_internal_id": inferred_id if prediction_names else None,
            "formula_prediction_names": prediction_names,
            "resolved_display_name": display_name,
            "resolved_canonical_id": canonical_id,
            "identity_status": status,
            "identity_confidence": confidence,
            "identity_notes": notes,
            "native_frame_count": 9,
            "preserved_even_if_identity_unknown": True,
        }
        target = all_root / target_name
        metadata = export_native_walk(target, frames, provenance)
        if status in {"human_confirmed", "visual_verified", "exact_cross_game_match"}:
            copy_walk(target, verified_root / target_name, metadata, provenance)

        rows.append({
            **provenance,
            "source_folder": target.relative_to(ROOT).as_posix(),
            "pack_folder": target.relative_to(ROOT).as_posix(),
        })

    # Authentic Minervamon from Dusk, plus the Xros formula candidate.  Keeping
    # both makes it possible to choose the native look appropriate to a target.
    minerva = ROOT / "work" / "extracted" / "digimon" / "434_minervamon"
    minerva_meta = read_json(minerva / "metadata.json", {})
    if minerva_meta.get("has_walk_animation"):
        target = comparisons / "minervamon_dusk_verified"
        target.mkdir(parents=True, exist_ok=True)
        for name in ("walk_up.png", "walk_down.png", "walk_left.png", "walk_right.png", "battle_idle.png"):
            if (minerva / name).is_file():
                shutil.copy2(minerva / name, target / name)
        (target / "metadata.json").write_text(
            json.dumps({
                "display_name": "Minervamon",
                "source_game": "dusk_clean_rom",
                "identity_status": "rom_linked_verified",
                "walk_entry": 544,
                "frame_count": 9,
                "notes": "Authentic Dusk walk and idle; not generated.",
            }, indent=2) + "\n",
            encoding="utf-8",
        )

    xros_minerva = all_root / "0571_minervamon"
    if xros_minerva.is_dir():
        shutil.copytree(xros_minerva, comparisons / "minervamon_xros_entry_0571_candidate")

    # Contact sheets: include the main species-shaped field range and preserve
    # the sparse nine-frame resources in the manifest for separate review.
    main_rows = [row for row in rows if 266 <= int(row["source_entry"]) <= 667]
    font = ImageFont.load_default()
    per_page = 24
    for page_start in range(0, len(main_rows), per_page):
        page_rows = main_rows[page_start : page_start + per_page]
        canvas = Image.new("RGBA", (1200, 720), (12, 23, 39, 255))
        draw = ImageDraw.Draw(canvas)
        for slot, row in enumerate(page_rows):
            column, line = slot % 6, slot // 6
            x, y = column * 200, line * 180
            draw.rounded_rectangle(
                (x + 4, y + 4, x + 196, y + 176),
                8,
                fill=(25, 49, 76, 255),
                outline=(71, 126, 166, 255),
                width=2,
            )
            source = ROOT / str(row["source_folder"])
            metadata = read_json(source / "metadata.json", {})
            contained(canvas, preview_frame(source, metadata), (x + 12, y + 42, x + 188, y + 142))
            title = f"{int(row['source_entry']):04d} {row['resolved_display_name']}"
            draw.text((x + 10, y + 12), title[:31], fill=(242, 247, 255, 255), font=font)
            draw.text((x + 10, y + 150), str(row["identity_status"])[:31], fill=(113, 215, 255, 255), font=font)
        page_number = page_start // per_page + 1
        canvas.convert("RGB").save(review_root / f"page_{page_number:02d}.png")

    manifest = {
        "source": "clean Digimon Story Super Xros Wars Blue ROM extraction",
        "total_native_nine_frame_resources": len(rows),
        "main_range_266_667_count": len(main_rows),
        "verified_named_count": sum(row["identity_status"] in {"human_confirmed", "visual_verified", "exact_cross_game_match"} for row in rows),
        "human_overrides": HUMAN_OVERRIDES,
        "warning": "Formula predictions are not equivalent to identity proof, especially in late Xros entries.",
        "mervamon": "No authentic clean Dusk, Lost Evolution, or Xros Blue species/field asset is present; custom art is required.",
        "records": rows,
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with (OUTPUT / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "source_entry", "asset_id", "resolved_display_name", "resolved_canonical_id",
            "identity_status", "identity_confidence", "inferred_internal_id",
            "formula_prediction_names", "identity_notes", "source_folder", "pack_folder",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            output_row = dict(row)
            output_row["formula_prediction_names"] = " | ".join(row["formula_prediction_names"])
            writer.writerow(output_row)

    readme = f"""# Xros Native Field Sprite Recovery Pack

This pack preserves **{len(rows)}** native nine-frame field resources from the clean
Xros Blue extraction. **{len(main_rows)}** occur in the principal 266-667 field range.

- `verified_named/` contains prior side-by-side visual approvals, owner-confirmed
  Tactimon entry 657, and exact clean-ROM matches to Lost Evolution. These
  cross-game matches recover identities without relying on filename order.
- `all_native_nine_frame/` retains every valid sheet, including unidentified assets.
- `review_pages/` is the fastest way to identify more late Xros sprites.
- `special_comparisons/` contains authentic Dusk Minervamon and its Xros candidate.

Identity is deliberately not invented. Rejected formula names remain preserved as
unidentified native sprites. Mervamon has no authentic clean-ROM asset in the source
games and therefore is not fabricated in this pack.

`promotion_report.json` records the verified batch copied into the normalized
asset library. Existing working walk sheets are never overwritten.
"""
    (OUTPUT / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps({key: manifest[key] for key in (
        "total_native_nine_frame_resources", "main_range_266_667_count", "verified_named_count", "mervamon"
    )}, indent=2))
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
