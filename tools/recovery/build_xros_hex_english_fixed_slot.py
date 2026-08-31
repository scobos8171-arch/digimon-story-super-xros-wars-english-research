#!/usr/bin/env python3
"""Safely localize the seven field-hex labels without changing their objects.

This is deliberately narrower than earlier attempts:
  * NCER, NANR, ARM9, overlays and save handling are untouched.
  * It keeps the original stored-size table values for the graphics member.
  * It only replaces the decoded pixels that are uploaded as the hex captions.

The two fixed-location graphics copies used by the v58 base are patched in
place, because that base has an archive-shadow loader for this UI resource.
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
sys.path.insert(0, str(ROOT / "tools" / "recovery"))

from build_xros_hex_english_labels import ENTRY, LABELS, draw_label  # noqa: E402
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import XrosPak, compress_xros_lz, find_nitro_file, read_nitro_file  # noqa: E402

ARCHIVE = "SPR_NCGR.PAK"
SHADOW_OFFSET = 0x0136C600
SHADOW_SIZE = 14872324


def localized_member(pak_bytes: bytes) -> tuple[bytes, dict[str, int]]:
    pak = XrosPak.from_bytes(pak_bytes)
    slot = pak.entries[ENTRY]
    before = pak.unpacked_data(ENTRY)
    after = bytearray(before)
    for segments, text in LABELS:
        draw_label(after, segments, text)
    if slot.is_uncompressed:
        # This is the important case for entry 198 in the v58 base. Writing
        # the raw member directly preserves the original mode and exact
        # stored size, which prevents the menu loader from seeing a different
        # archive layout.
        packed = bytearray(after)
    else:
        packed = bytearray(compress_xros_lz(bytes(after)))
    if len(packed) > slot.stored_size:
        raise ValueError(f"localized entry needs {len(packed)} bytes; fixed slot is {slot.stored_size}")
    output = bytearray(pak_bytes)
    start = slot.offset
    output[start:start + len(packed)] = packed
    # Preserve the original table size, flags and physical layout.
    output[start + len(packed):start + slot.stored_size] = b"\0" * (slot.stored_size - len(packed))
    check = XrosPak.from_bytes(bytes(output))
    if check.unpacked_data(ENTRY) != bytes(after):
        raise AssertionError("fixed-slot graphics member does not round-trip")
    return bytes(output), {
        "original_stored_size": slot.stored_size,
        "localized_payload_size": len(packed),
        "storage": "uncompressed" if slot.is_uncompressed else "compressed",
        "unpacked_size": len(after),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    rom = bytearray(args.source.read_bytes())
    with args.source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        nitro_item = find_nitro_file(files, ARCHIVE)
        nitro_before = read_nitro_file(handle, nitro_item)
    nitro_after, nitro_report = localized_member(nitro_before)
    if len(nitro_after) != nitro_item.size:
        raise AssertionError("NitroFS archive changed size")
    rom[nitro_item.offset:nitro_item.offset + nitro_item.size] = nitro_after

    shadow_before = bytes(rom[SHADOW_OFFSET:SHADOW_OFFSET + SHADOW_SIZE])
    shadow_after, shadow_report = localized_member(shadow_before)
    rom[SHADOW_OFFSET:SHADOW_OFFSET + SHADOW_SIZE] = shadow_after

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    report = {
        "source": str(args.source.resolve()),
        "output": str(args.output.resolve()),
        "archive": ARCHIVE,
        "entry": ENTRY,
        "labels": [text for _segments, text in LABELS],
        "method": "graphics-only, original NCER/NANR and fixed PAK tables retained",
        "nitrofs": nitro_report,
        "fixed_runtime_copy": shadow_report,
        "sha256": hashlib.sha256(rom).hexdigest(),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
