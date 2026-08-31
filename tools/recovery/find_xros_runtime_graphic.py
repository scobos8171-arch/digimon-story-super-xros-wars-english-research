#!/usr/bin/env python3
"""Find the exact rendered-graphic source in an Xros ROM by NCGR payload.

This is deliberately independent of filename assumptions.  It takes a clean
ROM graphic entry (for example the Japanese command-ring entry) and compares
its decompressed NCGR bytes against every parseable PAK member in a target
build.  A match identifies the actual resource family which can then be
patched and verified before any localization batch is attempted.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))

from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, find_nitro_file, read_nitro_file  # noqa: E402


def raw_archive(path: Path, name: str) -> bytes:
    with path.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        return read_nitro_file(handle, find_nitro_file(files, name))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("clean_rom", type=Path)
    parser.add_argument("target_rom", type=Path)
    parser.add_argument("--archive", default="SPR_NCGR.PAK")
    parser.add_argument("--entry", type=int, default=196)
    parser.add_argument("--scope", choices=("graphics", "all"), default="all")
    args = parser.parse_args()

    clean_entry = XrosPak.from_bytes(raw_archive(args.clean_rom, args.archive)).unpacked_data(
        args.entry
    )
    fingerprint = hashlib.sha256(clean_entry).hexdigest()
    matches: list[dict[str, object]] = []
    scanned_archives = 0
    scanned_entries = 0
    with args.target_rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        wanted = [item for item in files if item.path.upper().endswith(".PAK")]
        if args.scope == "graphics":
            wanted = [item for item in wanted if item.path.upper().endswith("SPR_NCGR.PAK")]
        for item in wanted:
            try:
                pak = XrosPak.from_bytes(read_nitro_file(handle, item))
            except Exception:
                continue
            scanned_archives += 1
            for index in range(len(pak.entries)):
                try:
                    candidate = pak.unpacked_data(index)
                except Exception:
                    continue
                scanned_entries += 1
                if hashlib.sha256(candidate).hexdigest() == fingerprint:
                    matches.append(
                        {
                            "nitrofs_path": item.path,
                            "nitrofs_offset": f"0x{item.offset:08X}",
                            "entry": index,
                            "entry_unpacked_size": len(candidate),
                        }
                    )
    print(
        {
            "source": {"archive": args.archive, "entry": args.entry, "sha256": fingerprint},
            "scope": args.scope,
            "scanned_archives": scanned_archives,
            "scanned_entries": scanned_entries,
            "matches": matches,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
