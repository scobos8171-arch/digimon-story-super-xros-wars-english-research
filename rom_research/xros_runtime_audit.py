"""Audit a localized Xros Wars ROM for gameplay-neutral file changes.

The localization is expected to change only the six message archives and the
font archive.  Any change to ARM executables, overlays, maps, encounters,
battle data, or other NitroFS files is treated as a runtime regression risk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.story_messages import MESSAGE_ARCHIVES, parse_message_table
from rom_research.xros_pak import XrosPak, read_nitro_file


ALLOWED_CHANGED_FILES = frozenset({"FONT_NFTR.PAK", *MESSAGE_ARCHIVES})


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _inventory(path: Path) -> tuple[bytes, dict[str, dict[str, object]]]:
    rom = path.read_bytes()
    with path.open("rb") as handle:
        header = read_header(handle)
        files = read_nitrofs(handle, header)
        inventory = {}
        for item in files:
            handle.seek(item.offset)
            data = handle.read(item.size)
            if len(data) != item.size:
                raise ValueError(f"Short read for {item.path}")
            inventory[item.path.replace("\\", "/")] = {
                "offset": item.offset,
                "size": item.size,
                "sha256": _sha256(data),
                "data": data,
            }
    return rom, inventory


def audit(
    reference: Path,
    candidate: Path,
    allowed_changed_files: frozenset[str] = ALLOWED_CHANGED_FILES,
) -> dict[str, object]:
    reference_rom, reference_files = _inventory(reference)
    candidate_rom, candidate_files = _inventory(candidate)
    if set(reference_files) != set(candidate_files):
        missing = sorted(set(reference_files) - set(candidate_files))
        added = sorted(set(candidate_files) - set(reference_files))
        raise ValueError(f"NitroFS path mismatch; missing={missing}, added={added}")

    changed = sorted(
        name
        for name in reference_files
        if reference_files[name]["sha256"] != candidate_files[name]["sha256"]
    )
    unexpected = sorted(set(changed) - allowed_changed_files)

    ordered = sorted(
        (
            int(record["offset"]),
            int(record["offset"]) + int(record["size"]),
            name,
        )
        for name, record in candidate_files.items()
    )
    bounds_or_overlap = []
    for index, (start, end, name) in enumerate(ordered):
        previous_end = ordered[index - 1][1] if index else 0
        if start < previous_end or end > len(candidate_rom):
            bounds_or_overlap.append(
                {"path": name, "start": start, "end": end, "previous_end": previous_end}
            )

    message_counts = {}
    message_tables = {}
    message_failures = []
    for archive_name in MESSAGE_ARCHIVES:
        archive = XrosPak.from_bytes(candidate_files[archive_name]["data"])
        record_count = 0
        table_count = 0
        for entry_index in range(len(archive.entries)):
            entry = archive.unpacked_data(entry_index)
            try:
                _offsets, strings = parse_message_table(entry, encoding="shift_jis")
            except ValueError:
                continue
            table_count += 1
            for string_index, raw in enumerate(strings):
                record_count += 1
                try:
                    raw.decode("shift_jis", errors="strict")
                except UnicodeDecodeError as exc:
                    message_failures.append(
                        {
                            "archive": archive_name,
                            "entry": entry_index,
                            "string": string_index,
                            "error": str(exc),
                        }
                    )
        message_counts[archive_name] = record_count
        message_tables[archive_name] = table_count

    result = {
        "reference": str(reference),
        "candidate": str(candidate),
        "reference_sha256": _sha256(reference_rom),
        "candidate_sha256": _sha256(candidate_rom),
        "nitrofs_file_count": len(candidate_files),
        "changed_files": changed,
        "allowed_changed_files": sorted(allowed_changed_files),
        "unexpected_changed_files": unexpected,
        "bounds_or_overlap_problems": bounds_or_overlap,
        "message_counts": message_counts,
        "message_table_counts": message_tables,
        "strict_shift_jis_failures": message_failures,
        "runtime_code_identical": reference_rom[0x4000:0x4000 + 0xAA04C]
        == candidate_rom[0x4000:0x4000 + 0xAA04C],
    }
    result["passed"] = not (
        unexpected
        or bounds_or_overlap
        or message_failures
        or not result["runtime_code_identical"]
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--allow-changed-file",
        action="append",
        default=[],
        help="Permit an additional data-only NitroFS file to differ.",
    )
    args = parser.parse_args()
    allowed = frozenset((*ALLOWED_CHANGED_FILES, *args.allow_changed_file))
    result = audit(args.reference, args.candidate, allowed)
    rendered = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
