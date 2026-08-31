"""Auto-skip Xros Wars anime movies through the native completion path."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from rom_research.nds_code_compression import compress_blz, decompress_blz
from rom_research.nds_inventory import read_header


# State 10 normally waits for player input before taking the native movie-skip
# branch. Force that branch on its first update, after initialization and fades.
MOVIE_SKIP_WAIT_OFFSET = 0x7D0C0
EXPECTED_MOVIE_SKIP_WAIT = bytes.fromhex("48 00 96 e5")
AUTO_SKIP_BRANCH = bytes.fromhex(
    "a9 fd ff eb"
)  # bl 0x7C76C: raise the native movie-complete event
ARM9_COMPRESSED_END_OFFSET = 0xB9C


def _crc16(data: bytes | bytearray) -> int:
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc & 0xFFFF


def build_movie_skip_rom(
    source_rom: Path,
    output_rom: Path,
    manifest_path: Path,
) -> dict[str, object]:
    rom = bytearray(source_rom.read_bytes())
    with source_rom.open("rb") as handle:
        header = read_header(handle)
    arm9_offset = int(header["arm9_offset"])
    arm9_size = int(header["arm9_size"])
    compressed = bytes(rom[arm9_offset:arm9_offset + arm9_size])
    decompressed = bytearray(decompress_blz(compressed))
    actual = bytes(
        decompressed[
            MOVIE_SKIP_WAIT_OFFSET:
            MOVIE_SKIP_WAIT_OFFSET + len(AUTO_SKIP_BRANCH)
        ]
    )
    if actual != EXPECTED_MOVIE_SKIP_WAIT:
        raise ValueError(
            f"Movie-skip-wait signature changed: expected "
            f"{EXPECTED_MOVIE_SKIP_WAIT.hex(' ')}, got {actual.hex(' ')}"
        )
    decompressed[
        MOVIE_SKIP_WAIT_OFFSET:
        MOVIE_SKIP_WAIT_OFFSET + len(AUTO_SKIP_BRANCH)
    ] = AUTO_SKIP_BRANCH
    # Nintendo's ARM9 module parameters embed the absolute end address of the
    # compressed image. Since changing even one instruction can alter the BLZ
    # size, update that pointer and recompress until the size is stable.
    arm9_ram_address = struct.unpack_from("<I", rom, 0x28)[0]
    rebuilt_arm9 = b""
    for _ in range(8):
        rebuilt_arm9 = compress_blz(bytes(decompressed), arm9=True)
        compressed_end = arm9_ram_address + len(rebuilt_arm9)
        if (
            struct.unpack_from(
                "<I", decompressed, ARM9_COMPRESSED_END_OFFSET
            )[0]
            == compressed_end
        ):
            break
        struct.pack_into(
            "<I",
            decompressed,
            ARM9_COMPRESSED_END_OFFSET,
            compressed_end,
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
    rom[
        arm9_offset + len(rebuilt_arm9):arm9_offset + arm9_size
    ] = b"\xFF" * (arm9_size - len(rebuilt_arm9))
    struct.pack_into("<I", rom, 0x2C, len(rebuilt_arm9))
    struct.pack_into("<H", rom, 0x15E, _crc16(rom[:0x15E]))

    output_rom.parent.mkdir(parents=True, exist_ok=True)
    output_rom.write_bytes(rom)

    # Read back from the completed ROM and validate the exact runtime patch.
    with output_rom.open("rb") as handle:
        output_header = read_header(handle)
        handle.seek(int(output_header["arm9_offset"]))
        verified = decompress_blz(handle.read(int(output_header["arm9_size"])))
    if (
        verified[
            MOVIE_SKIP_WAIT_OFFSET:
            MOVIE_SKIP_WAIT_OFFSET + len(AUTO_SKIP_BRANCH)
        ]
        != AUTO_SKIP_BRANCH
    ):
        raise AssertionError("Movie skip was not present after ROM write")

    manifest: dict[str, object] = {
        "source_rom": str(source_rom),
        "output_rom": str(output_rom),
        "source_sha256": hashlib.sha256(source_rom.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(rom).hexdigest(),
        "arm9_original_compressed_size": arm9_size,
        "arm9_new_compressed_size": len(rebuilt_arm9),
        "arm9_compressed_end_address": (
            f"0x{arm9_ram_address + len(rebuilt_arm9):08X}"
        ),
        "decompressed_patch_offset": f"0x{MOVIE_SKIP_WAIT_OFFSET:X}",
        "original_instructions": EXPECTED_MOVIE_SKIP_WAIT.hex(" "),
        "replacement_instructions": AUTO_SKIP_BRANCH.hex(" "),
        "behavior": (
            "Movie playback initializes normally, then state 10 raises the same "
            "completion callback used by the native movie player. The unmodified "
            "state machine performs cleanup and enters state 11; pixel-engine "
            "scenes and movie assets remain intact."
        ),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_rom", type=Path)
    parser.add_argument("output_rom", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    result = build_movie_skip_rom(args.source_rom, args.output_rom, args.manifest)
    print(
        f"Built {args.output_rom}; ARM9 {result['arm9_original_compressed_size']} "
        f"-> {result['arm9_new_compressed_size']} bytes; "
        f"SHA-256 {result['output_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
