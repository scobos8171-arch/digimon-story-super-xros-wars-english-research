"""Resize Xros Wars' ARM9 message work buffers for expanded translations.

The retail executable contains a six-entry table with the largest decompressed
member expected in MESPAK00 through MESPAK05.  Rebuilt English archives are
larger than those Japanese maxima.  Leaving the retail values in place causes
message data to overwrite adjacent memory (blank speaker headers and eventual
runtime crashes are two observed symptoms).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from rom_research.nds_code_compression import compress_blz, decompress_blz
from rom_research.nds_inventory import read_header
from rom_research.nds_inventory import read_nitrofs
from rom_research.xros_pak import XrosPak


MESSAGE_ARCHIVES = tuple(f"MSG/MESPAK0{index}.PAK" for index in range(6))
ARM9_MESSAGE_MAXIMA_OFFSET = 0xDDD5C
RETAIL_MAXIMA = (0x17B0C, 0x66D4, 0xA2AC, 0x61D0, 0x0FFC, 0x21EC)
ARM9_COMPRESSED_END_OFFSET = 0xB9C


def _crc16(data: bytes | bytearray) -> int:
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc & 0xFFFF


def _message_maxima(rom_path: Path) -> tuple[int, ...]:
    with rom_path.open("rb") as handle:
        header = read_header(handle)
        files = {item.path: item for item in read_nitrofs(handle, header)}
        maxima: list[int] = []
        for name in MESSAGE_ARCHIVES:
            item = files.get(name)
            if item is None:
                raise KeyError(f"Missing NitroFS file {name}")
            handle.seek(item.offset)
            archive = XrosPak.from_bytes(handle.read(item.size))
            maxima.append(max(entry.uncompressed_size for entry in archive.entries))
    return tuple(maxima)


def build_message_buffer_rom(
    source_rom: Path,
    output_rom: Path,
    manifest_path: Path,
) -> dict[str, object]:
    source_rom = Path(source_rom)
    output_rom = Path(output_rom)
    rom = bytearray(source_rom.read_bytes())
    with source_rom.open("rb") as handle:
        header = read_header(handle)

    arm9_offset = int(header["arm9_offset"])
    arm9_size = int(header["arm9_size"])
    arm9_ram_address = struct.unpack_from("<I", rom, 0x28)[0]
    decompressed = bytearray(
        decompress_blz(bytes(rom[arm9_offset:arm9_offset + arm9_size]))
    )
    actual = struct.unpack_from("<6I", decompressed, ARM9_MESSAGE_MAXIMA_OFFSET)
    if actual != RETAIL_MAXIMA:
        raise ValueError(
            "ARM9 message-maxima signature changed: expected "
            f"{tuple(hex(value) for value in RETAIL_MAXIMA)}, got "
            f"{tuple(hex(value) for value in actual)}"
        )

    archive_maxima = _message_maxima(source_rom)
    patched_maxima = tuple(
        max(retail, actual_size)
        for retail, actual_size in zip(RETAIL_MAXIMA, archive_maxima)
    )
    struct.pack_into(
        "<6I", decompressed, ARM9_MESSAGE_MAXIMA_OFFSET, *patched_maxima
    )

    rebuilt_arm9 = b""
    for _ in range(8):
        rebuilt_arm9 = compress_blz(bytes(decompressed), arm9=True)
        compressed_end = arm9_ram_address + len(rebuilt_arm9)
        if struct.unpack_from("<I", decompressed, ARM9_COMPRESSED_END_OFFSET)[0] == compressed_end:
            break
        struct.pack_into(
            "<I", decompressed, ARM9_COMPRESSED_END_OFFSET, compressed_end
        )
    else:
        raise AssertionError("ARM9 compressed-end pointer did not converge")

    if decompress_blz(rebuilt_arm9) != bytes(decompressed):
        raise AssertionError("Recompressed ARM9 failed round-trip validation")
    if len(rebuilt_arm9) > arm9_size:
        raise ValueError(
            f"Rebuilt ARM9 grew by {len(rebuilt_arm9) - arm9_size} bytes"
        )

    rom[arm9_offset:arm9_offset + len(rebuilt_arm9)] = rebuilt_arm9
    rom[arm9_offset + len(rebuilt_arm9):arm9_offset + arm9_size] = (
        b"\xFF" * (arm9_size - len(rebuilt_arm9))
    )
    struct.pack_into("<I", rom, 0x2C, len(rebuilt_arm9))
    struct.pack_into("<H", rom, 0x15E, _crc16(rom[:0x15E]))

    output_rom.parent.mkdir(parents=True, exist_ok=True)
    output_rom.write_bytes(rom)

    with output_rom.open("rb") as handle:
        output_header = read_header(handle)
        handle.seek(int(output_header["arm9_offset"]))
        verified = decompress_blz(handle.read(int(output_header["arm9_size"])))
    verified_maxima = struct.unpack_from(
        "<6I", verified, ARM9_MESSAGE_MAXIMA_OFFSET
    )
    if verified_maxima != patched_maxima:
        raise AssertionError("Message-buffer table failed ROM write verification")

    manifest: dict[str, object] = {
        "source_rom": str(source_rom.resolve()),
        "output_rom": str(output_rom.resolve()),
        "source_sha256": hashlib.sha256(source_rom.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(rom).hexdigest(),
        "arm9_original_compressed_size": arm9_size,
        "arm9_new_compressed_size": len(rebuilt_arm9),
        "decompressed_table_offset": f"0x{ARM9_MESSAGE_MAXIMA_OFFSET:X}",
        "retail_maxima": [f"0x{value:X}" for value in RETAIL_MAXIMA],
        "archive_maxima": [f"0x{value:X}" for value in archive_maxima],
        "patched_maxima": [f"0x{value:X}" for value in patched_maxima],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_rom", type=Path)
    parser.add_argument("output_rom", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    result = build_message_buffer_rom(
        args.source_rom, args.output_rom, args.manifest
    )
    print(
        f"Built {args.output_rom}; maxima {result['patched_maxima']}; "
        f"SHA-256 {result['output_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
