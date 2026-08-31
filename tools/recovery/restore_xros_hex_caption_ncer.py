#!/usr/bin/env python3
"""Restore entry 198's original command-hex OAM layout from a known-good ROM.

Used only to undo v68's deliberately hidden caption OAM descriptors.  The
source remains v68; this replaces just SPR_NCER.PAK entry 198 with its v58
version, leaving all other v68 bytes unmodified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))

from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, compress_xros_lz, find_nitro_file, read_nitro_file  # noqa: E402

ARCHIVE = "SPR_NCER.PAK"
ENTRY = 198


def archive_and_entry(path: Path) -> tuple[object, bytes, bytes]:
    with path.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        item = find_nitro_file(files, ARCHIVE)
        archive = read_nitro_file(handle, item)
    pak = XrosPak.from_bytes(archive)
    return item, archive, pak.unpacked_data(ENTRY)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="v68 icon-only ROM")
    parser.add_argument("donor", type=Path, help="v58 LIVE HEX MENU FIX ROM")
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    source = bytearray(args.source.read_bytes())
    source_item, source_archive, _source_entry = archive_and_entry(args.source)
    _donor_item, _donor_archive, donor_entry = archive_and_entry(args.donor)
    if donor_entry[:4] != b"RECN":
        raise ValueError("Donor entry 198 is not NCER")
    pak = XrosPak.from_bytes(source_archive)
    slot = pak.entries[ENTRY]
    packed = compress_xros_lz(donor_entry)
    if len(packed) > slot.stored_size:
        raise ValueError("Restored NCER cannot fit its original archive slot")
    rebuilt = bytearray(source_archive)
    rebuilt[slot.offset:slot.offset + len(packed)] = packed
    rebuilt[slot.offset + len(packed):slot.offset + slot.stored_size] = b"\0" * (slot.stored_size - len(packed))
    struct.pack_into("<IIII", rebuilt, 0x10 + ENTRY * 0x10, slot.offset, len(donor_entry), len(packed), slot.flags & ~0x80000000)
    if XrosPak.from_bytes(bytes(rebuilt)).unpacked_data(ENTRY) != donor_entry:
        raise AssertionError("Restored NCER failed round-trip verification")
    source[source_item.offset:source_item.offset + source_item.size] = rebuilt
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(source)
    report = {
        "source": str(args.source.resolve()), "donor": str(args.donor.resolve()),
        "output": str(args.output.resolve()), "archive": ARCHIVE, "entry": ENTRY,
        "method": "restore original v58 caption OAM descriptors into v68 only",
        "sha256": hashlib.sha256(source).hexdigest(),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
