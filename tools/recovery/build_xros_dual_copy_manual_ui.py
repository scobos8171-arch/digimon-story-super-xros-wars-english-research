"""Build a UI-localized Xros ROM with both graphic archive copies synchronized.

Xros loads some UI sprites through NitroFS and some through the original
physical SPR_NCGR.PAK location.  A normal NitroFS rebuild can therefore be
perfectly valid yet invisible in-game.  This wrapper first applies the
artist's native PNG cells using the existing safe cell encoder, then mirrors
each changed entry into the original compressed archive without changing any
of its entry offsets.
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
sys.path[:0] = [str(ROOT / "tools" / "recovery"), str(EDITOR)]

from patch_xros_manual_ui_cells import build, discover_cells  # noqa: E402
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


def _archive(rom: Path) -> tuple[int, bytes]:
    with rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        item = find_nitro_file(files, ARCHIVE)
        return item.offset, read_nitro_file(handle, item)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Known-good source ROM")
    parser.add_argument("output", type=Path)
    parser.add_argument("manual_root", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--preview", type=Path, required=True)
    parser.add_argument(
        "--physical-offset", type=lambda value: int(value, 0),
        help="Original cartridge SPR_NCGR.PAK offset (for a relocated NitroFS source)",
    )
    parser.add_argument(
        "--physical-size", type=lambda value: int(value, 0),
        help="Original cartridge SPR_NCGR.PAK byte size; required with --physical-offset",
    )
    args = parser.parse_args()

    selected = sorted({entry for entry, _cell in discover_cells(args.manual_root)})
    scratch = ROOT / "work" / "dual_copy_ui_scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    staged = scratch / "encoded_nitrofs_only.nds"
    stage_manifest = scratch / "encoded_nitrofs_only.json"
    stage_preview = scratch / "encoded_nitrofs_only.png"
    build(args.source, staged, args.manual_root, stage_manifest, stage_preview)

    nitrofs_source_offset, source_bytes = _archive(args.source)
    if (args.physical_offset is None) != (args.physical_size is None):
        raise ValueError("--physical-offset and --physical-size must be supplied together")
    if args.physical_offset is None:
        source_offset = nitrofs_source_offset
    else:
        source_offset = args.physical_offset
        data = args.source.read_bytes()
        source_bytes = data[source_offset:source_offset + args.physical_size]
        if len(source_bytes) != args.physical_size:
            raise ValueError("Original physical archive extends beyond source ROM")
    _staged_offset, staged_bytes = _archive(staged)
    physical = XrosPak.from_bytes(source_bytes)
    patched = XrosPak.from_bytes(staged_bytes)
    result = bytearray(staged.read_bytes())
    mirrored: list[dict[str, int]] = []

    for index in selected:
        source_entry = physical.entries[index]
        unpacked = patched.unpacked_data(index)
        packed = compress_xros_lz(unpacked)
        if len(packed) > source_entry.stored_size:
            raise ValueError(
                f"Entry {index} cannot be mirrored safely: compressed {len(packed)} "
                f"> original slot {source_entry.stored_size}"
            )
        start = source_offset + source_entry.offset
        end = start + source_entry.stored_size
        result[start:start + len(packed)] = packed
        result[start + len(packed):end] = b"\0" * (source_entry.stored_size - len(packed))
        struct.pack_into(
            "<IIII", result, source_offset + PAK_HEADER_SIZE + index * PAK_ENTRY_SIZE,
            source_entry.offset, len(unpacked), len(packed), source_entry.flags & ~UNCOMPRESSED_FLAG,
        )
        mirrored.append({"entry": index, "stored_bytes": len(packed), "slot_bytes": source_entry.stored_size})

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result)
    output_offset, output_bytes = _archive(args.output)
    output_fat = XrosPak.from_bytes(output_bytes)
    output_physical = XrosPak.from_bytes(result[source_offset:source_offset + len(source_bytes)])
    for index in selected:
        expected = patched.unpacked_data(index)
        if output_fat.unpacked_data(index) != expected:
            raise AssertionError(f"NitroFS copy mismatch for entry {index}")
        if output_physical.unpacked_data(index) != expected:
            raise AssertionError(f"Physical copy mismatch for entry {index}")

    report = {
        "source": str(args.source.resolve()),
        "output": str(args.output.resolve()),
        "selected_entries": selected,
        "selected_count": len(selected),
        "physical_archive_offset": f"0x{source_offset:08X}",
        "nitrofs_source_archive_offset": f"0x{nitrofs_source_offset:08X}",
        "nitrofs_archive_offset": f"0x{output_offset:08X}",
        "mirrored": mirrored,
        "verification": "Each selected entry decompresses identically from both archive copies.",
        "sha256": hashlib.sha256(result).hexdigest(),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.preview.parent.mkdir(parents=True, exist_ok=True)
    args.preview.write_bytes(stage_preview.read_bytes())
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
