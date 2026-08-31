"""Inventory a Nintendo DS ROM's NitroFS files without extracting game data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


@dataclass(frozen=True)
class NitroFile:
    file_id: int
    path: str
    offset: int
    size: int


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def read_header(handle: BinaryIO) -> dict[str, int | str]:
    handle.seek(0)
    header = handle.read(0x200)
    if len(header) != 0x200:
        raise ValueError("File is too small to be a Nintendo DS ROM")
    return {
        "title": header[0:12].rstrip(b"\0").decode("ascii", errors="replace"),
        "game_code": header[12:16].decode("ascii", errors="replace"),
        "maker_code": header[16:18].decode("ascii", errors="replace"),
        "arm9_offset": _u32(header, 0x20),
        "arm9_size": _u32(header, 0x2C),
        "fnt_offset": _u32(header, 0x40),
        "fnt_size": _u32(header, 0x44),
        "fat_offset": _u32(header, 0x48),
        "fat_size": _u32(header, 0x4C),
        "arm9_overlay_offset": _u32(header, 0x50),
        "arm9_overlay_size": _u32(header, 0x54),
        "arm7_overlay_offset": _u32(header, 0x58),
        "arm7_overlay_size": _u32(header, 0x5C),
    }


def read_nitrofs(handle: BinaryIO, header: dict[str, int | str]) -> list[NitroFile]:
    fnt_offset = int(header["fnt_offset"])
    fnt_size = int(header["fnt_size"])
    fat_offset = int(header["fat_offset"])
    fat_size = int(header["fat_size"])
    if not fnt_offset or not fnt_size or fat_size % 8:
        raise ValueError("ROM has an invalid or missing NitroFS table")

    handle.seek(fnt_offset)
    fnt = handle.read(fnt_size)
    handle.seek(fat_offset)
    fat = handle.read(fat_size)
    file_count = len(fat) // 8

    root_subtable = _u32(fnt, 0)
    root_first_file = _u16(fnt, 4)
    directory_count = _u16(fnt, 6)
    if root_subtable >= len(fnt) or directory_count == 0:
        raise ValueError("Malformed NitroFS filename table")

    directories: dict[int, tuple[int, int]] = {}
    for index in range(directory_count):
        entry = index * 8
        if entry + 8 > len(fnt):
            raise ValueError("Directory table extends past the filename table")
        directory_id = 0xF000 + index
        directories[directory_id] = (_u32(fnt, entry), _u16(fnt, entry + 4))
    directories[0xF000] = (root_subtable, root_first_file)

    names_by_id: dict[int, str] = {}

    def walk(directory_id: int, prefix: str) -> None:
        try:
            cursor, next_file_id = directories[directory_id]
        except KeyError as exc:
            raise ValueError(f"Unknown NitroFS directory id 0x{directory_id:04X}") from exc
        while cursor < len(fnt):
            length = fnt[cursor]
            cursor += 1
            if length == 0:
                return
            is_directory = bool(length & 0x80)
            name_length = length & 0x7F
            raw_name = fnt[cursor:cursor + name_length]
            cursor += name_length
            name = raw_name.decode("ascii", errors="replace")
            path = f"{prefix}/{name}" if prefix else name
            if is_directory:
                child_id = _u16(fnt, cursor)
                cursor += 2
                walk(child_id, path)
            else:
                names_by_id[next_file_id] = path
                next_file_id += 1
        raise ValueError("Unterminated NitroFS directory subtable")

    walk(0xF000, "")
    files: list[NitroFile] = []
    for file_id in range(file_count):
        start, end = struct.unpack_from("<II", fat, file_id * 8)
        if end < start:
            raise ValueError(f"File {file_id} has an invalid FAT range")
        files.append(
            NitroFile(
                file_id=file_id,
                path=names_by_id.get(file_id, f"<unnamed:{file_id}>"),
                offset=start,
                size=end - start,
            )
        )
    return files


def _identify_magic(data: bytes) -> str:
    signatures = {
        b"NARC": "NARC archive",
        b"RGCN": "NCGR graphics",
        b"RLCN": "NCLR palette",
        b"RECN": "NCER cells",
        b"RNAN": "NANR animation",
        b"SDAT": "Nintendo SDAT audio",
        b"BMD0": "Nintendo DS 3D model",
        b"BTX0": "Nintendo DS texture",
        b"PK\x03\x04": "ZIP archive",
    }
    for signature, label in signatures.items():
        if data.startswith(signature):
            return label
    if data[:1] == b"\x10" and len(data) >= 4:
        return "Nintendo LZ10"
    if data[:1] == b"\x11" and len(data) >= 4:
        return "Nintendo LZ11"
    if data[:1] == b"\x24" and len(data) >= 4:
        return "Nintendo Huffman"
    if data[:1] == b"\x30" and len(data) >= 4:
        return "Nintendo RLE"
    return ""


def write_inventory(rom_path: Path, output_path: Path) -> tuple[dict, list[NitroFile]]:
    with rom_path.open("rb") as handle:
        header = read_header(handle)
        files = read_nitrofs(handle, header)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(
                [
                    "file_id",
                    "path",
                    "rom_offset",
                    "size",
                    "detected_format",
                    "first_16_bytes",
                    "sha1",
                ]
            )
            for item in files:
                handle.seek(item.offset)
                first = handle.read(min(item.size, 16))
                handle.seek(item.offset)
                digest = hashlib.sha1()
                remaining = item.size
                while remaining:
                    chunk = handle.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    digest.update(chunk)
                    remaining -= len(chunk)
                writer.writerow(
                    [
                        item.file_id,
                        item.path,
                        f"0x{item.offset:08X}",
                        item.size,
                        _identify_magic(first),
                        first.hex(" ").upper(),
                        digest.hexdigest(),
                    ]
                )
    return header, files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    header, files = write_inventory(args.rom, args.output)
    print(
        f"{header['title']} ({header['game_code']}): "
        f"{len(files)} NitroFS files -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
