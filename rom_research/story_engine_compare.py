"""Compare two Digimon Story-era Nintendo DS ROM containers and sprites."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.xros_pak import XrosPak, read_nitro_file
from rom_research.xros_sprite import SPRITE_ARCHIVES


def _load_rom(rom_path: Path) -> tuple[dict[str, int | str], dict[str, bytes]]:
    with rom_path.open("rb") as handle:
        header = read_header(handle)
        files = read_nitrofs(handle, header)
        payloads = {
            item.path.replace("\\", "/").casefold(): read_nitro_file(handle, item)
            for item in files
        }
    return header, payloads


def _pak_counts(payloads: dict[str, bytes]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path, data in payloads.items():
        if not path.endswith(".pak"):
            continue
        try:
            counts[path] = len(XrosPak.from_bytes(data).entries)
        except ValueError:
            continue
    return counts


def _coordinated_sprite_archives(
    payloads: dict[str, bytes],
) -> dict[str, XrosPak]:
    result: dict[str, XrosPak] = {}
    for kind, archive_name in SPRITE_ARCHIVES.items():
        key = archive_name.casefold()
        if key not in payloads:
            raise FileNotFoundError(f"Missing coordinated sprite archive {archive_name}")
        result[kind] = XrosPak.from_bytes(payloads[key])
    counts = {len(archive.entries) for archive in result.values()}
    if len(counts) != 1:
        raise ValueError(f"Coordinated sprite archive counts differ: {counts}")
    return result


def _sprite_signatures(
    archives: dict[str, XrosPak],
) -> tuple[tuple[str, ...], ...]:
    entry_count = len(archives["graphics"].entries)
    signatures: list[tuple[str, ...]] = []
    for index in range(entry_count):
        signatures.append(
            tuple(
                hashlib.sha1(archives[kind].unpacked_data(index)).hexdigest()
                for kind in SPRITE_ARCHIVES
            )
        )
    return tuple(signatures)


def compare(
    donor_rom: Path,
    target_rom: Path,
    output_json: Path,
    output_csv: Path,
) -> dict[str, Any]:
    donor_header, donor_payloads = _load_rom(donor_rom)
    target_header, target_payloads = _load_rom(target_rom)
    donor_paks = _pak_counts(donor_payloads)
    target_paks = _pak_counts(target_payloads)
    donor_sprites = _sprite_signatures(
        _coordinated_sprite_archives(donor_payloads)
    )
    target_sprites = _sprite_signatures(
        _coordinated_sprite_archives(target_payloads)
    )

    target_by_signature: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for index, signature in enumerate(target_sprites):
        target_by_signature[signature].append(index)

    matches: list[tuple[int, tuple[int, ...]]] = []
    donor_only: list[int] = []
    for donor_index, signature in enumerate(donor_sprites):
        target_indices = tuple(target_by_signature.get(signature, ()))
        if target_indices:
            matches.append((donor_index, target_indices))
        else:
            donor_only.append(donor_index)

    shared_paths = sorted(donor_payloads.keys() & target_payloads.keys())
    result: dict[str, Any] = {
        "donor": {
            "path": str(donor_rom),
            "title": donor_header["title"],
            "game_code": donor_header["game_code"],
            "nitro_files": len(donor_payloads),
            "sprite_entries": len(donor_sprites),
        },
        "target": {
            "path": str(target_rom),
            "title": target_header["title"],
            "game_code": target_header["game_code"],
            "nitro_files": len(target_payloads),
            "sprite_entries": len(target_sprites),
        },
        "filesystem": {
            "shared_paths": len(shared_paths),
            "donor_only_paths": sorted(donor_payloads.keys() - target_payloads.keys()),
            "target_only_paths": sorted(target_payloads.keys() - donor_payloads.keys()),
        },
        "pak_entry_counts": {
            path: {
                "donor": donor_paks.get(path),
                "target": target_paks.get(path),
            }
            for path in sorted(donor_paks.keys() | target_paks.keys())
        },
        "sprites": {
            "exact_donor_entries_already_in_target": len(matches),
            "donor_only_entries": len(donor_only),
            "target_duplicate_signature_groups": sum(
                1 for indices in target_by_signature.values() if len(indices) > 1
            ),
        },
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("lost_evolution_entry", "xros_wars_entries"))
        for donor_index, target_indices in matches:
            writer.writerow(
                (donor_index, " ".join(str(index) for index in target_indices))
            )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("donor_rom", type=Path)
    parser.add_argument("target_rom", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("output_csv", type=Path)
    args = parser.parse_args()
    result = compare(
        args.donor_rom,
        args.target_rom,
        args.output_json,
        args.output_csv,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
