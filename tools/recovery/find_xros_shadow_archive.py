#!/usr/bin/env python3
"""Locate copies of a Xros graphics PAK inside a rebuilt ROM.

Xros builds can retain an original graphics archive at a fixed physical ROM
offset while NitroFS points at a relocated replacement.  Editing only the
NitroFS copy then appears to succeed but has no on-screen effect.  This tool
uses a clean cartridge's archive entry as a fingerprint and reports every
valid PAK copy in a target ROM.
"""

from __future__ import annotations

import argparse
import io
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EDITOR_ROOT = ROOT / "work" / "DigimonNDSRomEditor-master"
sys.path.insert(0, str(EDITOR_ROOT))

from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import (  # noqa: E402
    XrosPak,
    find_nitro_file,
    read_nitro_file,
)


def archive_from_nitrofs(rom_path: Path, archive_name: str):
    data = rom_path.read_bytes()
    handle = io.BytesIO(data)
    files = read_nitrofs(handle, read_header(handle))
    item = find_nitro_file(files, archive_name)
    return data, item, read_nitro_file(io.BytesIO(data), item)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("clean_rom", type=Path)
    parser.add_argument("target_rom", type=Path)
    parser.add_argument("--archive", default="SPR_NCGR.PAK")
    parser.add_argument("--entry", type=int, default=196)
    parser.add_argument("--probe-bytes", type=int, default=64)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    target_data, target_nitro, target_blob = archive_from_nitrofs(
        args.target_rom, args.archive
    )
    _, clean_nitro, clean_blob = archive_from_nitrofs(args.clean_rom, args.archive)
    clean_pak = XrosPak.from_bytes(clean_blob)
    target_pak = XrosPak.from_bytes(target_blob)
    entry = clean_pak.entries[args.entry]
    probe_size = min(args.probe_bytes, entry.stored_size)
    if probe_size < 16:
        raise SystemExit("Selected entry is too small to fingerprint safely.")
    probe = clean_blob[entry.offset : entry.offset + probe_size]

    candidates = []
    start = 0
    while True:
        found = target_data.find(probe, start)
        if found < 0:
            break
        base = found - entry.offset
        start = found + 1
        if base < 0 or base + len(clean_blob) > len(target_data):
            continue
        try:
            candidate_blob = target_data[base : base + len(clean_blob)]
            candidate = XrosPak.from_bytes(candidate_blob)
            candidate_entry = candidate.entries[args.entry]
            candidates.append(
                {
                    "physical_offset": f"0x{base:08X}",
                    "physical_size": len(clean_blob),
                    "entry_offset": f"0x{candidate_entry.offset:08X}",
                    "entry_stored_size": candidate_entry.stored_size,
                    "entry_stored_sha256": sha(
                        candidate_blob[
                            candidate_entry.offset : candidate_entry.offset
                            + candidate_entry.stored_size
                        ]
                    ),
                    "is_nitrofs_copy": base == target_nitro.offset,
                }
            )
        except Exception:
            continue

    report = {
        "archive": args.archive,
        "entry": args.entry,
        "clean_nitrofs_offset": f"0x{clean_nitro.offset:08X}",
        "clean_nitrofs_size": len(clean_blob),
        "target_nitrofs_offset": f"0x{target_nitro.offset:08X}",
        "target_nitrofs_size": len(target_blob),
        "target_nitrofs_entry_stored_sha256": sha(
            target_blob[
                target_pak.entries[args.entry].offset : target_pak.entries[args.entry].offset
                + target_pak.entries[args.entry].stored_size
            ]
        ),
        "candidate_copies": candidates,
    }
    rendered = json.dumps(report, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
