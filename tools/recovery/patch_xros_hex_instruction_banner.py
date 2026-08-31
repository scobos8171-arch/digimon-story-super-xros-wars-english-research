#!/usr/bin/env python3
"""Localize the hard-coded command-ring instruction banner safely."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))

from rom_research.nds_code_compression import compress_blz, decompress_blz  # noqa: E402


BANNER_OFFSET = 0x10BEE4  # ARM9 RAM 0x0210BEE4
ARM9_COMPRESSED_END_OFFSET = 0xB9C
JAPANESE_BANNER = (
    "じゅうじボタンで　こうもくをえらび　Ａボタンをおして　けっていしてください。"
).encode("cp932")
# Keep the original two-byte Shift-JIS character path.  Full-width English
# uses the game's native NFTR and avoids changing the shared character walker.
# It fits inside the original 114-byte slot and scrolls normally.
ENGLISH_BANNER_TEXT = "Ｄ－ＰＡＤ：ＳＥＬＥＣＴ　　Ａ：ＣＯＮＦＩＲＭ"
ENGLISH_BANNER = ENGLISH_BANNER_TEXT.encode("cp932")


def crc16(data: bytes | bytearray) -> int:
    value = 0xFFFF
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xA001 if value & 1 else 0)
    return value & 0xFFFF


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    original = args.source.read_bytes()
    rom = bytearray(original)
    arm9_rom_offset = struct.unpack_from("<I", rom, 0x20)[0]
    arm9_stored_size = struct.unpack_from("<I", rom, 0x2C)[0]
    arm9 = bytearray(decompress_blz(bytes(rom[arm9_rom_offset:arm9_rom_offset + arm9_stored_size])))
    actual_banner = bytes(arm9[BANNER_OFFSET:BANNER_OFFSET + len(JAPANESE_BANNER)])
    if actual_banner != JAPANESE_BANNER:
        raise ValueError("Unexpected command-ring banner signature")

    arm9[BANNER_OFFSET:BANNER_OFFSET + len(JAPANESE_BANNER)] = (
        ENGLISH_BANNER + b"\0" * (len(JAPANESE_BANNER) - len(ENGLISH_BANNER))
    )
    # ARM9 BLZ is not interchangeable with overlay BLZ: Nintendo's loader
    # expects the first 0x4000 bytes to remain verbatim.  Compressing from
    # offset zero produces a stream that our round-trip decoder accepts but
    # that the hardware/emulator cannot boot safely.
    arm9_ram_address = struct.unpack_from("<I", rom, 0x28)[0]
    rebuilt = b""
    for _ in range(8):
        rebuilt = compress_blz(bytes(arm9), arm9=True)
        compressed_end = arm9_ram_address + len(rebuilt)
        if struct.unpack_from("<I", arm9, ARM9_COMPRESSED_END_OFFSET)[0] == compressed_end:
            break
        struct.pack_into("<I", arm9, ARM9_COMPRESSED_END_OFFSET, compressed_end)
    else:
        raise AssertionError("ARM9 compressed-end pointer did not converge")
    if len(rebuilt) > arm9_stored_size:
        raise ValueError(f"Rebuilt ARM9 grew by {len(rebuilt) - arm9_stored_size} bytes")
    rom[arm9_rom_offset:arm9_rom_offset + len(rebuilt)] = rebuilt
    rom[arm9_rom_offset + len(rebuilt):arm9_rom_offset + arm9_stored_size] = (
        b"\xFF" * (arm9_stored_size - len(rebuilt))
    )
    struct.pack_into("<I", rom, 0x2C, len(rebuilt))
    struct.pack_into("<H", rom, 0x15E, crc16(rom[:0x15E]))

    verified = decompress_blz(bytes(rom[arm9_rom_offset:arm9_rom_offset + len(rebuilt)]))
    if rebuilt[:0x4000] != arm9[:0x4000]:
        raise AssertionError("ARM9 uncompressed prefix was not preserved")
    if not verified[BANNER_OFFSET:BANNER_OFFSET + len(ENGLISH_BANNER)] == ENGLISH_BANNER:
        raise AssertionError("Banner patch failed verification")
    changed = [index for index, (before, after) in enumerate(zip(decompress_blz(
        original[arm9_rom_offset:arm9_rom_offset + arm9_stored_size]
    ), verified)) if before != after]
    allowed = set(range(BANNER_OFFSET, BANNER_OFFSET + len(JAPANESE_BANNER)))
    allowed.update(range(ARM9_COMPRESSED_END_OFFSET, ARM9_COMPRESSED_END_OFFSET + 4))
    if not changed or not set(changed).issubset(allowed):
        raise AssertionError("ARM9 changes escaped the dedicated banner slot")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps({
        "source_rom": str(args.source.resolve()),
        "output_rom": str(args.output.resolve()),
        "source_sha256": hashlib.sha256(original).hexdigest(),
        "output_sha256": hashlib.sha256(rom).hexdigest(),
        "arm9": {
            "code_instructions_changed": False,
            "instruction_banner": {"ram": "0x0210BEE4", "english": ENGLISH_BANNER_TEXT},
            "changed_decompressed_byte_count": len(changed),
            "compressed_end_pointer_offset": "0xB9C",
            "compressed_end_address": f"0x{arm9_ram_address + len(rebuilt):08X}",
            "stored_size_before": arm9_stored_size,
            "stored_size_after": len(rebuilt),
        },
    }, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
