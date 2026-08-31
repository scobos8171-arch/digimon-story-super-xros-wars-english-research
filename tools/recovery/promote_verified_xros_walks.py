"""Promote proven native Xros walk sheets into canonical Digimon folders."""
from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(r"C:\Users\YOUR_NAME\Documents\Codex\2026-07-24\c-users-scobo-downloads-download-digimon")
PACK = ROOT / "outputs" / "Xros Native Field Sprite Recovery Pack"
MANIFEST = PACK / "manifest.json"
ROSTER = ROOT / "work" / "extracted" / "roster.json"
REPORT = PACK / "promotion_report.json"
VERIFIED = {"human_confirmed", "visual_verified", "exact_cross_game_match"}
PRIORITY = {"human_confirmed": 0, "visual_verified": 1, "exact_cross_game_match": 2}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    manifest = load(MANIFEST)
    roster = load(ROSTER)
    roster_by_id = {int(row["canonical_id"]): row for row in roster}
    choices: dict[int, dict] = {}
    for record in manifest["records"]:
        canonical_id = record.get("resolved_canonical_id")
        status = record.get("identity_status")
        if canonical_id is None or status not in VERIFIED:
            continue
        canonical_id = int(canonical_id)
        current = choices.get(canonical_id)
        rank = (PRIORITY[status], int(record["source_entry"]))
        if current is None or rank < current[0]:
            choices[canonical_id] = (rank, record)

    promoted = []
    skipped_existing = []
    failures = []
    for canonical_id, (_rank, record) in sorted(choices.items()):
        roster_row = roster_by_id.get(canonical_id)
        if roster_row is None:
            failures.append({"canonical_id": canonical_id, "reason": "missing roster row"})
            continue
        target = ROOT / "work" / "extracted" / roster_row["folder"]
        metadata_path = target / "metadata.json"
        metadata = load(metadata_path)
        if metadata.get("has_walk_animation"):
            skipped_existing.append(canonical_id)
            continue
        source = ROOT / record["pack_folder"]
        source_metadata = load(source / "metadata.json")
        walk = source_metadata.get("walk")
        if not isinstance(walk, dict):
            failures.append({"canonical_id": canonical_id, "reason": "source walk metadata missing"})
            continue
        missing = [
            direction for direction in ("up", "down", "left", "right")
            if not (source / f"walk_{direction}.png").is_file()
        ]
        if missing:
            failures.append({"canonical_id": canonical_id, "reason": f"missing files: {missing}"})
            continue
        for direction in ("up", "down", "left", "right"):
            shutil.copy2(source / f"walk_{direction}.png", target / f"walk_{direction}.png")
        metadata["has_walk_animation"] = True
        metadata["walk"] = walk
        metadata["walk_source"] = {
            "source_game": "xros_blue_clean_rom",
            "source_entry": int(record["source_entry"]),
            "identity_status": record["identity_status"],
            "identity_confidence": record["identity_confidence"],
        }
        notes = metadata.setdefault("notes", [])
        note = (
            f"Native Xros Blue field entry {record['source_entry']} promoted by "
            f"{record['identity_status']}; all nine frames preserved."
        )
        if note not in notes:
            notes.append(note)
        save(metadata_path, metadata)
        roster_row["has_walk_animation"] = True
        promoted.append({
            "canonical_id": canonical_id,
            "display_name": roster_row["display_name"],
            "source_entry": int(record["source_entry"]),
            "identity_status": record["identity_status"],
            "folder": roster_row["folder"],
        })

    save(ROSTER, roster)
    report = {
        "promoted_count": len(promoted),
        "skipped_existing_count": len(skipped_existing),
        "failure_count": len(failures),
        "promoted": promoted,
        "skipped_existing_canonical_ids": skipped_existing,
        "failures": failures,
    }
    save(REPORT, report)
    print(json.dumps({key: report[key] for key in (
        "promoted_count", "skipped_existing_count", "failure_count"
    )}, indent=2))


if __name__ == "__main__":
    main()
