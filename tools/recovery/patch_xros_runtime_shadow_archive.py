"""Patch Xros' original physical sprite archive as well as its NitroFS copy.

Some UI code reads SPR_NCGR.PAK from the cartridge's original physical
location instead of following NitroFS FAT relocation.  Earlier tools rebuilt
the archive uncompressed at the ROM tail, leaving that original compressed
body untouched.  This tool creates a size-bounded compressed archive for the
original location using selected entries from an already-patched donor ROM.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDITOR = ROOT / "work" / "DigimonNDSRomEditor-master"
sys.path.insert(0, str(EDITOR))

from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.xros_pak import (  # noqa: E402
    PAK_ENTRY_SIZE,
    PAK_HEADER_SIZE,
    PAK_VERSION,
    UNCOMPRESSED_FLAG,
    XrosPak,
    compress_xros_lz,
    find_nitro_file,
)

ARCHIVE = "SPR_NCGR.PAK"


def _read_archive(rom: Path) -> tuple[int, bytes]:
    with rom.open("rb") as handle:
        header = read_header(handle)
        files = read_nitrofs(handle, header)
        item = find_nitro_file(files, ARCHIVE)
        handle.seek(item.offset)
        return item.offset, handle.read(item.size)


def _selected_entries(stage: Path) -> set[int]:
    result: set[int] = set()
    for path in stage.glob("entry_*/*/english_completed.png"):
        result.add(int(path.parent.parent.name.split("_")[1]))
    if not result:
        raise ValueError(f"No staged entries found under {stage}")
    return result


def _build_bounded_archive(clean: XrosPak, donor: XrosPak, selected: set[int]) -> bytes:
    """Patch entries in place without changing any original data offsets.

    Several Xros menu consumers address compressed sprite records by their
    cartridge-era position instead of consistently following the rebuilt
    NitroFS archive.  Repacking the archive therefore leaves a valid table
    but moves the payload away from the address those consumers read.  Keep
    every original offset and replace only payloads that fit their slots.
    """
    output = bytearray(clean.data)
    for index in sorted(selected):
        clean_entry = clean.entries[index]
        unpacked = donor.unpacked_data(index)
        stored = compress_xros_lz(unpacked)
        if len(stored) > clean_entry.stored_size:
            raise ValueError(
                f"Entry {index} needs {len(stored):,} bytes but its original "
                f"fixed slot is only {clean_entry.stored_size:,} bytes"
            )

        start = clean_entry.offset
        end = start + clean_entry.stored_size
        output[start:start + len(stored)] = stored
        output[start + len(stored):end] = b"\0" * (clean_entry.stored_size - len(stored))
        struct.pack_into(
            "<IIII",
            output,
            PAK_HEADER_SIZE + index * PAK_ENTRY_SIZE,
            clean_entry.offset,
            len(unpacked),
            len(stored),
            clean_entry.flags & ~UNCOMPRESSED_FLAG,
        )
    return bytes(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean-rom", required=True, type=Path)
    parser.add_argument("--donor-rom", required=True, type=Path)
    parser.add_argument("--stage", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()

    clean_offset, clean_bytes = _read_archive(args.clean_rom)
    _donor_offset, donor_bytes = _read_archive(args.donor_rom)
    selected = _selected_entries(args.stage)
    runtime_archive = _build_bounded_archive(
        XrosPak.from_bytes(clean_bytes), XrosPak.from_bytes(donor_bytes), selected
    )

    output = bytearray(args.donor_rom.read_bytes())
    if output[clean_offset:clean_offset + len(clean_bytes)] != clean_bytes:
        raise ValueError("Donor no longer contains the untouched original shadow archive")
    output[clean_offset:clean_offset + len(runtime_archive)] = runtime_archive

    check = XrosPak.from_bytes(runtime_archive)
    donor = XrosPak.from_bytes(donor_bytes)
    for index in selected:
        if check.unpacked_data(index) != donor.unpacked_data(index):
            raise AssertionError(f"Runtime entry {index} differs after recompression")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    report = {
        "clean_rom": str(args.clean_rom.resolve()),
        "donor_rom": str(args.donor_rom.resolve()),
        "output": str(args.output.resolve()),
        "archive": ARCHIVE,
        "runtime_physical_offset": f"0x{clean_offset:08X}",
        "runtime_archive_size": len(runtime_archive),
        "selected_entries": sorted(selected),
        "selected_count": len(selected),
        "sha256": hashlib.sha256(output).hexdigest(),
        "verification": "Every selected runtime entry decompresses byte-identically to donor",
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
