"""Port Lost Evolution's English character-decoder instruction to Xros."""

from __future__ import annotations

import struct
from pathlib import Path

from rom_research.nds_code_compression import compress_blz, decompress_blz
from rom_research.nds_inventory import read_header


PATCH_OFFSET = 0x39CB0
EXPECTED = bytes.fromhex("b0 10 d4 e1")  # ldrh r1, [r4]
REPLACEMENT = bytes.fromhex("00 10 a0 e3")  # mov r1, #0
COMPRESSED_END_OFFSET = 0xB9C


def crc16(data: bytes | bytearray) -> int:
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc & 0xFFFF


def build(source: Path, output: Path) -> None:
    rom = bytearray(source.read_bytes())
    with source.open("rb") as handle:
        header = read_header(handle)
    offset = int(header["arm9_offset"])
    size = int(header["arm9_size"])
    decompressed = bytearray(decompress_blz(bytes(rom[offset:offset + size])))
    if decompressed[PATCH_OFFSET:PATCH_OFFSET + 4] != EXPECTED:
        raise ValueError("Xros ASCII decoder signature changed")
    decompressed[PATCH_OFFSET:PATCH_OFFSET + 4] = REPLACEMENT

    ram_address = struct.unpack_from("<I", rom, 0x28)[0]
    rebuilt = b""
    for _ in range(8):
        rebuilt = compress_blz(bytes(decompressed), arm9=True)
        end_address = ram_address + len(rebuilt)
        if struct.unpack_from("<I", decompressed, COMPRESSED_END_OFFSET)[0] == end_address:
            break
        struct.pack_into("<I", decompressed, COMPRESSED_END_OFFSET, end_address)
    else:
        raise AssertionError("Compressed-end pointer did not converge")
    if decompress_blz(rebuilt) != bytes(decompressed):
        raise AssertionError("ARM9 compression roundtrip failed")
    if len(rebuilt) > size:
        raise ValueError("Rebuilt ARM9 no longer fits")

    rom[offset:offset + len(rebuilt)] = rebuilt
    rom[offset + len(rebuilt):offset + size] = b"\xFF" * (size - len(rebuilt))
    struct.pack_into("<I", rom, 0x2C, len(rebuilt))
    struct.pack_into("<H", rom, 0x15E, crc16(rom[:0x15E]))
    output.write_bytes(rom)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.source, args.output)
