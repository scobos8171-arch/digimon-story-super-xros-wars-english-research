"""Small, auditable NitroFS replacement helpers for ROM research tools."""

from __future__ import annotations

import struct
import math
from pathlib import Path

from rom_research.nds_inventory import NitroFile, read_header, read_nitrofs
from rom_research.xros_pak import find_nitro_file


def replace_nitrofs_files(
    rom_data: bytes | bytearray,
    replacements: dict[str, bytes],
    *,
    alignment: int = 0x200,
    allow_expand: bool = True,
) -> bytearray:
    """Relocate replacement files into unused ROM tail space and update FAT.

    Existing file bodies are left intact; only new copies and their FAT
    ranges are written.  Keeping the old bytes makes the operation easier to
    audit and avoids shifting any other ROM section.
    """

    if alignment <= 0 or alignment & (alignment - 1):
        raise ValueError("alignment must be a positive power of two")
    output = bytearray(rom_data)
    with _ByteArrayReader(output) as handle:
        header = read_header(handle)
        files = read_nitrofs(handle, header)

    resolved: list[tuple[NitroFile, bytes]] = [
        (find_nitro_file(files, name), data)
        for name, data in replacements.items()
    ]
    tail_start = max(item.offset + item.size for item in files)
    cursor = (tail_start + alignment - 1) & ~(alignment - 1)
    fat_offset = int(header["fat_offset"])

    for item, replacement in resolved:
        # Same-size and smaller metadata files can safely stay in place.
        # Larger archives are copied to the tail so no neighbouring file moves.
        if len(replacement) <= item.size:
            start = item.offset
        else:
            start = (cursor + alignment - 1) & ~(alignment - 1)
        end = start + len(replacement)
        if end > len(output):
            if not allow_expand:
                raise ValueError(
                    f"Replacement files need {end - len(output):,} more bytes than "
                    "the ROM's unused tail provides"
                )
            output.extend(b"\xFF" * (end - len(output)))
        output[start:end] = replacement
        struct.pack_into("<II", output, fat_offset + item.file_id * 8, start, end)
        cursor = max(cursor, end)

    used_size = max(
        struct.unpack_from("<I", output, 0x80)[0],
        max(
            struct.unpack_from("<II", output, fat_offset + item.file_id * 8)[1]
            for item in files
        ),
    )
    struct.pack_into("<I", output, 0x80, used_size)
    capacity = max(0, math.ceil(math.log2(max(1, len(output)) / 0x20000)))
    output[0x14] = capacity
    struct.pack_into("<H", output, 0x15E, _crc16(output[:0x15E]))
    return output


def write_patched_rom(
    source_path: Path,
    output_path: Path,
    replacements: dict[str, bytes],
) -> None:
    patched = replace_nitrofs_files(source_path.read_bytes(), replacements)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(patched)


class _ByteArrayReader:
    """Minimal seek/read context wrapper accepted by the inventory parser."""

    def __init__(self, data: bytes | bytearray):
        self.data = data
        self.position = 0

    def __enter__(self) -> "_ByteArrayReader":
        return self

    def __exit__(self, *_args) -> None:
        return None

    def seek(self, position: int) -> int:
        self.position = position
        return position

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.data) - self.position
        result = bytes(self.data[self.position:self.position + size])
        self.position += len(result)
        return result


def _crc16(data: bytes | bytearray) -> int:
    """Nintendo header CRC-16 (initial 0xFFFF, reflected polynomial 0xA001)."""

    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc & 0xFFFF
