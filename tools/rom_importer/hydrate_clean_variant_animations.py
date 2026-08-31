#!/usr/bin/env python
"""Add full animation exports to pixel-distinct clean-ROM variants."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .extractor import export_battle, load_context


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--rom-dir", type=Path, required=True)
    args = parser.parse_args()
    pack = args.pack.resolve()
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    expected = manifest["clean_rom_sources"]
    contexts = {}
    species = {}
    for profile in ("dusk", "lost_evolution", "xros_blue", "xros_red"):
        rom = args.rom_dir / f"{profile}.nds"
        if file_hash(rom) != expected[profile]["sha256"]:
            raise SystemExit(f"clean ROM hash mismatch: {rom}")
        context = load_context(rom)
        contexts[profile] = context
        species[profile] = {item.internal_id: item for item in context.species}

    hydrated = 0
    for source_json in (pack / "06 Pixel-Distinct Source Variants").rglob("source.json"):
        record = json.loads(source_json.read_text(encoding="utf-8"))
        source = next(
            (item for item in record["sources"] if item["source_game"] in contexts),
            None,
        )
        if source is None:
            continue
        profile = source["source_game"]
        item = species[profile].get(int(source["internal_id"]))
        if item is None:
            raise SystemExit(f"source record not found: {profile} #{source['internal_id']}")
        metadata = export_battle(contexts[profile].battle.resource(item.battle_entry), source_json.parent, raw_components=False)
        (source_json.parent / "animation-metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        hydrated += 1
        if hydrated % 25 == 0:
            print(f"Hydrated {hydrated} variant animation packs", flush=True)
    print(json.dumps({"hydrated_variant_animation_packs": hydrated}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
