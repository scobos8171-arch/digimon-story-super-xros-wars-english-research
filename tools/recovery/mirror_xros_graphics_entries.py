"""Mirror selected SPR_NCGR.PAK entries into Xros's physical archive copy.

Some Xros UI loaders address the cartridge's original SPR_NCGR.PAK location
instead of following the NitroFS FAT after a rebuilt archive is relocated.  A
normal data-only patch can therefore verify perfectly while remaining
invisible in game.  This tool takes a source ROM, a staged ROM whose NitroFS
copy is already patched, and mirrors only explicitly selected entries into the
source ROM's original fixed-size archive slots.
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
    UNCOMPRESSED_FLAG,
    XrosPak,
    compress_xros_lz,
    find_nitro_file,
    read_nitro_file,
)


ARCHIVE = "SPR_NCGR.PAK"


def nitro_archive(path: Path) -> tuple[int, bytes]:
    with path.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        item = find_nitro_file(files, ARCHIVE)
        return item.offset, read_nitro_file(handle, item)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Known-good ROM before the staged patch")
    parser.add_argument("staged", type=Path, help="ROM with the desired NitroFS entries")
    parser.add_argument("output", type=Path)
    parser.add_argument("--entry", action="append", required=True, type=int)
    parser.add_argument("--physical-offset", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--physical-size", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()

    entries = sorted(set(args.entry))
    source_data = args.source.read_bytes()
    staged_data = args.staged.read_bytes()
    source_physical_bytes = source_data[
        args.physical_offset : args.physical_offset + args.physical_size
    ]
    if len(source_physical_bytes) != args.physical_size:
        raise ValueError("Physical archive extends beyond source ROM")

    source_physical = XrosPak.from_bytes(source_physical_bytes)
    _staged_offset, staged_nitro_bytes = nitro_archive(args.staged)
    staged_nitro = XrosPak.from_bytes(staged_nitro_bytes)
    output = bytearray(staged_data)
    mirrored: list[dict[str, int]] = []

    for index in entries:
        source_entry = source_physical.entries[index]
        desired = staged_nitro.unpacked_data(index)
        packed = compress_xros_lz(desired)
        if len(packed) > source_entry.stored_size:
            raise ValueError(
                f"Entry {index}: compressed patch {len(packed)} exceeds the "
                f"original physical slot {source_entry.stored_size}"
            )
        start = args.physical_offset + source_entry.offset
        end = start + source_entry.stored_size
        output[start : start + len(packed)] = packed
        output[start + len(packed) : end] = b"\0" * (source_entry.stored_size - len(packed))
        struct.pack_into(
            "<IIII",
            output,
            args.physical_offset + PAK_HEADER_SIZE + index * PAK_ENTRY_SIZE,
            source_entry.offset,
            len(desired),
            len(packed),
            source_entry.flags & ~UNCOMPRESSED_FLAG,
        )
        mirrored.append(
            {
                "entry": index,
                "stored_bytes": len(packed),
                "slot_bytes": source_entry.stored_size,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)

    output_nitro_offset, output_nitro_bytes = nitro_archive(args.output)
    output_nitro = XrosPak.from_bytes(output_nitro_bytes)
    output_physical = XrosPak.from_bytes(
        bytes(output[args.physical_offset : args.physical_offset + args.physical_size])
    )
    for index in entries:
        expected = staged_nitro.unpacked_data(index)
        if output_nitro.unpacked_data(index) != expected:
            raise AssertionError(f"NitroFS copy mismatch for entry {index}")
        if output_physical.unpacked_data(index) != expected:
            raise AssertionError(f"Physical copy mismatch for entry {index}")

    report = {
        "source": str(args.source.resolve()),
        "staged": str(args.staged.resolve()),
        "output": str(args.output.resolve()),
        "entries": entries,
        "physical_archive_offset": f"0x{args.physical_offset:08X}",
        "physical_archive_size": args.physical_size,
        "nitrofs_archive_offset": f"0x{output_nitro_offset:08X}",
        "mirrored": mirrored,
        "verification": "Selected entries decompress identically from both archive copies.",
        "sha256": hashlib.sha256(output).hexdigest(),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
