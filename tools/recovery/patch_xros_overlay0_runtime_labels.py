"""Build a minimal, auditable Xros UI proof ROM from the live-overlay capture.

This intentionally patches *only* two labels proven by the DeSmuME runtime
probe to live in ARM9 overlay 0.  It is not a broad graphics replacement:
that is exactly why it is safe to use as the first validation build.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDITOR_ROOT = ROOT / "work" / "DigimonNDSRomEditor-master"
if str(EDITOR_ROOT) not in sys.path:
    sys.path.insert(0, str(EDITOR_ROOT))

from rom_research.nds_code_compression import compress_blz, decompress_blz
from rom_research.nds_inventory import read_header, read_nitrofs


OVERLAY_ID = 0
EXPECTED_RAM_ADDRESS = 0x021F3D20

# Exact, capture-proven text locations in overlay 0.  Each replacement is
# padded to the original Shift-JIS slot length.
PATCHES = (
    # Standalone battle-command strings from the overlay-0 pointer table
    # at +0x26570.  Do not patch さくせん: it only appears inside longer
    # sentences such as ガードさくせん.
    (0x26500, "たいき".encode("cp932"), b"WAIT\0\0"),
    (0x26508, "ガード".encode("cp932"), b"GUARD\0"),
    (0x2651C, "がったい".encode("cp932"), b"DIGIXROS"),
    (0x26528, "ひっさつ".encode("cp932"), b"SPECIAL\0"),
    (0x26534, "アイテム".encode("cp932"), b"ITEMS\0\0\0"),
    (0x26540, "とんずら".encode("cp932"), b"FLEE\0\0\0\0"),
    (0x2654C, "かくとう".encode("cp932"), b"FIGHT\0\0\0"),
    (0x26558, "せつやく".encode("cp932"), b"CONSERVE"),
    (0x26564, "フルパワ".encode("cp932"), b"FULLPWR\0"),
    # Skill-row prefixes inside overlay 0.  These are わざ１-４ labels, not
    # the field hex ring, but they are the same runtime font path.
    (0x26A8C, "わざ".encode("cp932"), b"MOVE"),
    (0x26A9C, "わざ".encode("cp932"), b"MOVE"),
    (0x26AAC, "わざ".encode("cp932"), b"MOVE"),
    (0x26B2C, "わざ".encode("cp932"), b"MOVE"),
    (0x26D14, "もどる".encode("cp932"), b"BACK\0\0\0\0\0\0\0\0"),
    (0x26D74, "もどる".encode("cp932"), b"BACK\0\0\0\0\0\0\0\0"),
    (0x26D94, "もどる".encode("cp932"), b"BACK\0\0\0\0\0\0\0\0"),
)


def crc16(data: bytes | bytearray) -> int:
    value = 0xFFFF
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xA001 if value & 1 else 0)
    return value & 0xFFFF


def find_overlay(rom: bytes, header: dict[str, int | str]) -> tuple[int, int, int, int]:
    table = int(header["arm9_overlay_offset"])
    size = int(header["arm9_overlay_size"])
    for cursor in range(table, table + size, 0x20):
        overlay_id, ram_address, ram_size, _bss, _si0, _si1, file_id, flags = struct.unpack_from(
            "<8I", rom, cursor
        )
        if overlay_id == OVERLAY_ID:
            if ram_address != EXPECTED_RAM_ADDRESS:
                raise ValueError(f"Overlay 0 RAM address changed: 0x{ram_address:08X}")
            return cursor, file_id, ram_size, flags
    raise ValueError("ARM9 overlay 0 was not found")


def build(source: Path, output: Path, manifest_path: Path) -> dict[str, object]:
    source = Path(source)
    raw = source.read_bytes()
    rom = bytearray(raw)
    with source.open("rb") as handle:
        header = read_header(handle)
        files = {item.file_id: item for item in read_nitrofs(handle, header)}
    table_offset, file_id, expected_ram_size, old_flags = find_overlay(rom, header)
    item = files[file_id]
    stored = bytes(rom[item.offset:item.offset + item.size])
    decoded = bytearray(decompress_blz(stored))
    if len(decoded) != expected_ram_size:
        raise ValueError("Overlay 0 decompressed size does not match overlay table")

    changes: list[dict[str, str]] = []
    for offset, expected, replacement in PATCHES:
        actual = bytes(decoded[offset:offset + len(expected)])
        if actual != expected:
            raise ValueError(
                f"Signature at overlay+0x{offset:X} changed: expected {expected.hex()}, got {actual.hex()}"
            )
        decoded[offset:offset + len(replacement)] = replacement
        changes.append({"overlay_offset": f"0x{offset:X}", "replacement": replacement.rstrip(b"\0").decode("ascii")})

    rebuilt = compress_blz(bytes(decoded))
    if decompress_blz(rebuilt) != bytes(decoded):
        raise AssertionError("Overlay compression round-trip failed")

    # Put the replacement at the ROM tail and point the FAT + overlay table to
    # it.  This does not overwrite any existing game file and is reversible.
    alignment = 0x200
    start = (len(rom) + alignment - 1) & ~(alignment - 1)
    end = start + len(rebuilt)
    rom.extend(b"\xFF" * (end - len(rom)))
    rom[start:end] = rebuilt
    fat = int(header["fat_offset"])
    struct.pack_into("<II", rom, fat + file_id * 8, start, end)
    new_flags = (old_flags & 0xFF000000) | len(rebuilt)
    struct.pack_into("<I", rom, table_offset + 0x1C, new_flags)
    struct.pack_into("<I", rom, 0x80, max(struct.unpack_from("<I", rom, 0x80)[0], end))
    struct.pack_into("<H", rom, 0x15E, crc16(rom[:0x15E]))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rom)

    # Independent re-open validation; never report success based on RAM only.
    with output.open("rb") as handle:
        output_header = read_header(handle)
        output_files = {entry.file_id: entry for entry in read_nitrofs(handle, output_header)}
        output_item = output_files[file_id]
        handle.seek(output_item.offset)
        verified = decompress_blz(handle.read(output_item.size))
    if verified != bytes(decoded):
        raise AssertionError("Written overlay does not match the verified rebuilt overlay")
    for offset, _expected, replacement in PATCHES:
        if verified[offset:offset + len(replacement)] != replacement:
            raise AssertionError(f"Patch failed verification at 0x{offset:X}")

    manifest = {
        "source_rom": str(source.resolve()),
        "output_rom": str(output.resolve()),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "output_sha256": hashlib.sha256(rom).hexdigest(),
        "overlay_id": OVERLAY_ID,
        "overlay_ram_address": f"0x{EXPECTED_RAM_ADDRESS:08X}",
        "overlay_file_id": file_id,
        "original_stored_size": item.size,
        "rebuilt_stored_size": len(rebuilt),
        "changes": changes,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    result = build(args.source, args.output, args.manifest)
    print(f"Built {result['output_rom']} with {len(result['changes'])} verified runtime-label patches")
