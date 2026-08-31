#!/usr/bin/env python3
"""Permanently hide only the seven Xros field-hex caption OAM objects.

Entry 198 of SPR_NCER.PAK defines each command hex as icon + caption overlay
(one or two OAMs) + base plate.  Setting the overlay OAM object mode to
disabled reproduces the verified live Lua icon-only result without touching
the icons, plate pixels, text renderer, ARM9, or save data.
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
# cell 1..7: OAM 0 is icon; OAM 1 (+ OAM 2 where present) are captions;
# final OAM is the underlying 64x64 red plate.
CAPTION_OAMS = {1: (1, 2), 2: (1,), 3: (1, 2), 4: (1, 2), 5: (1, 2), 6: (1, 2), 7: (1, 2)}


def patch_ncer(data: bytes) -> tuple[bytes, list[dict[str, int]]]:
    if data[:4] != b"RECN" or len(data) < 0x30:
        raise ValueError("Entry 198 is not an NCER file")
    _section, cell_count, extended, _unknown, _mapping, _partition = struct.unpack_from("<IHHIII", data, 0x14)
    cell_record_size = 0x10 if extended == 1 else 8
    oam_start = 0x30 + cell_record_size * cell_count
    result = bytearray(data)
    changed: list[dict[str, int]] = []
    for cell_index, oam_indices in CAPTION_OAMS.items():
        record = 0x30 + cell_index * cell_record_size
        oam_count, _read_only, relative = struct.unpack_from("<HHI", data, record)
        for oam_index in oam_indices:
            if oam_index >= oam_count:
                raise ValueError(f"Cell {cell_index} has no OAM {oam_index}")
            offset = oam_start + relative + oam_index * 6
            old = struct.unpack_from("<H", data, offset)[0]
            # attr0 bits 8..9: 10 = disabled/hidden OBJ. Preserve y, shape,
            # colors and every other descriptor property.
            new = (old & ~0x0300) | 0x0200
            struct.pack_into("<H", result, offset, new)
            changed.append({"cell": cell_index, "oam": oam_index, "offset": offset, "old_attr0": old, "new_attr0": new})
    return bytes(result), changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    rom = bytearray(args.source.read_bytes())
    with args.source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        item = find_nitro_file(files, ARCHIVE)
        archive_bytes = read_nitro_file(handle, item)
    pak = XrosPak.from_bytes(archive_bytes)
    slot = pak.entries[ENTRY]
    patched_entry, changed = patch_ncer(pak.unpacked_data(ENTRY))
    packed = compress_xros_lz(patched_entry)
    if len(packed) > slot.stored_size:
        raise ValueError(f"Patched NCER entry needs {len(packed)} bytes; slot holds {slot.stored_size}")
    archive = bytearray(archive_bytes)
    archive[slot.offset:slot.offset + len(packed)] = packed
    archive[slot.offset + len(packed):slot.offset + slot.stored_size] = b"\0" * (slot.stored_size - len(packed))
    struct.pack_into("<IIII", archive, 0x10 + ENTRY * 0x10, slot.offset, len(patched_entry), len(packed), slot.flags & ~0x80000000)
    if XrosPak.from_bytes(bytes(archive)).unpacked_data(ENTRY) != patched_entry:
        raise AssertionError("Recompressed NCER entry failed verification")
    rom[item.offset:item.offset + item.size] = archive
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "source": str(args.source.resolve()), "output": str(args.output.resolve()),
        "archive": ARCHIVE, "entry": ENTRY, "method": "disable caption OAM descriptors only",
        "changed_descriptors": changed, "stored_bytes_before": slot.stored_size,
        "stored_bytes_after": len(packed), "sha256": hashlib.sha256(rom).hexdigest(),
        "verification": "Patched NCER entry round-trips through Xros LZ and remains in its original archive slot.",
    }
    args.manifest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
