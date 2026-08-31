from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class NdsHeader:
    title: str
    game_code: str
    maker_code: str
    arm9_offset: int
    arm9_size: int
    fnt_offset: int
    fnt_size: int
    fat_offset: int
    fat_size: int
    arm9_overlay_offset: int
    arm9_overlay_size: int


@dataclass(frozen=True)
class NitroFile:
    file_id: int
    path: str
    offset: int
    size: int


@dataclass(frozen=True)
class Arm9Overlay:
    overlay_id: int
    ram_address: int
    ram_size: int
    bss_size: int
    static_init_start: int
    static_init_end: int
    file_id: int
    compressed_size: int
    flags: int
    data: bytes


def decompress_blz(data: bytes) -> bytes:
    """Decompress the backwards-LZ stream used by Nintendo DS code overlays."""
    if len(data) < 8:
        raise ValueError("BLZ overlay is too short")
    compressed_length = int.from_bytes(data[-8:-5], "little")
    header_length = data[-5]
    extra_length = int.from_bytes(data[-4:], "little")
    if (
        compressed_length <= header_length
        or compressed_length > len(data)
        or header_length < 8
        or header_length > 0x20
    ):
        raise ValueError("Invalid BLZ footer")
    output = bytearray(data)
    compressed_start = len(output) - compressed_length
    source = len(output) - header_length
    destination = len(output) + extra_length
    output.extend(b"\0" * extra_length)
    while source > compressed_start:
        source -= 1
        flags = output[source]
        for _ in range(8):
            if source <= compressed_start or destination <= compressed_start:
                break
            if flags & 0x80:
                source -= 2
                if source < compressed_start:
                    raise ValueError("BLZ back-reference header crosses the prefix")
                code = output[source] | (output[source + 1] << 8)
                length = (code >> 12) + 3
                displacement = (code & 0xFFF) + 3
                for _copy in range(length):
                    destination -= 1
                    reference = destination + displacement
                    if destination < compressed_start or reference >= len(output):
                        raise ValueError("BLZ back-reference is outside the output")
                    output[destination] = output[reference]
            else:
                source -= 1
                destination -= 1
                if source < compressed_start or destination < compressed_start:
                    raise ValueError("BLZ literal crosses the uncompressed prefix")
                output[destination] = output[source]
            flags = (flags << 1) & 0xFF
    if source != compressed_start or destination != compressed_start:
        raise ValueError(
            f"BLZ stream ended at source 0x{source:X}, destination 0x{destination:X}, "
            f"expected 0x{compressed_start:X}"
        )
    return bytes(output)


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


class NdsRom:
    """Read-only Nintendo DS header and NitroFS reader."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._data = self.path.read_bytes()
        self.header = self._parse_header(self._data)
        self.files = self._parse_nitrofs(self._data, self.header)
        self._by_path = {
            item.path.replace("\\", "/").casefold(): item for item in self.files
        }

    @staticmethod
    def _parse_header(data: bytes) -> NdsHeader:
        if len(data) < 0x200:
            raise ValueError("File is too small to be a Nintendo DS ROM")
        return NdsHeader(
            title=data[0:12].rstrip(b"\0").decode("ascii", errors="replace"),
            game_code=data[12:16].decode("ascii", errors="replace"),
            maker_code=data[16:18].decode("ascii", errors="replace"),
            arm9_offset=_u32(data, 0x20),
            arm9_size=_u32(data, 0x2C),
            fnt_offset=_u32(data, 0x40),
            fnt_size=_u32(data, 0x44),
            fat_offset=_u32(data, 0x48),
            fat_size=_u32(data, 0x4C),
            arm9_overlay_offset=_u32(data, 0x50),
            arm9_overlay_size=_u32(data, 0x54),
        )

    @staticmethod
    def _parse_nitrofs(data: bytes, header: NdsHeader) -> tuple[NitroFile, ...]:
        if not header.fnt_offset or not header.fnt_size or header.fat_size % 8:
            raise ValueError("ROM has an invalid or missing NitroFS table")
        fnt = data[header.fnt_offset : header.fnt_offset + header.fnt_size]
        fat = data[header.fat_offset : header.fat_offset + header.fat_size]
        if len(fnt) != header.fnt_size or len(fat) != header.fat_size:
            raise ValueError("NitroFS table extends beyond the ROM")

        root_subtable = _u32(fnt, 0)
        root_first_file = _u16(fnt, 4)
        directory_count = _u16(fnt, 6)
        if not directory_count or root_subtable >= len(fnt):
            raise ValueError("Malformed NitroFS filename table")

        directories: dict[int, tuple[int, int]] = {}
        for index in range(directory_count):
            cursor = index * 8
            if cursor + 8 > len(fnt):
                raise ValueError("NitroFS directory table is truncated")
            directories[0xF000 + index] = (
                _u32(fnt, cursor),
                _u16(fnt, cursor + 4),
            )
        directories[0xF000] = (root_subtable, root_first_file)
        names_by_id: dict[int, str] = {}
        active: set[int] = set()

        def walk(directory_id: int, prefix: str) -> None:
            if directory_id in active:
                raise ValueError("NitroFS directory cycle detected")
            if directory_id not in directories:
                raise ValueError(f"Unknown NitroFS directory 0x{directory_id:04X}")
            active.add(directory_id)
            cursor, next_file_id = directories[directory_id]
            while cursor < len(fnt):
                length = fnt[cursor]
                cursor += 1
                if length == 0:
                    active.remove(directory_id)
                    return
                is_directory = bool(length & 0x80)
                name_length = length & 0x7F
                if cursor + name_length > len(fnt):
                    raise ValueError("NitroFS filename extends beyond the table")
                name = fnt[cursor : cursor + name_length].decode(
                    "ascii", errors="replace"
                )
                cursor += name_length
                path = f"{prefix}/{name}" if prefix else name
                if is_directory:
                    if cursor + 2 > len(fnt):
                        raise ValueError("NitroFS child directory ID is truncated")
                    child_id = _u16(fnt, cursor)
                    cursor += 2
                    walk(child_id, path)
                else:
                    names_by_id[next_file_id] = path
                    next_file_id += 1
            raise ValueError("Unterminated NitroFS directory subtable")

        walk(0xF000, "")
        files: list[NitroFile] = []
        for file_id in range(len(fat) // 8):
            start, end = struct.unpack_from("<II", fat, file_id * 8)
            if end < start or end > len(data):
                raise ValueError(f"Invalid FAT range for file {file_id}")
            files.append(
                NitroFile(
                    file_id=file_id,
                    path=names_by_id.get(file_id, f"unnamed/{file_id:05d}.bin"),
                    offset=start,
                    size=end - start,
                )
            )
        return tuple(files)

    def find(self, requested_path: str) -> NitroFile:
        normalized = requested_path.replace("\\", "/").casefold()
        direct = self._by_path.get(normalized)
        if direct is not None:
            return direct
        basename = PurePosixPath(normalized).name
        matches = [
            item for item in self.files if PurePosixPath(item.path.casefold()).name == basename
        ]
        if not matches:
            raise FileNotFoundError(f"NitroFS file not found: {requested_path}")
        if len(matches) > 1:
            raise ValueError(
                "Ambiguous NitroFS basename: " + ", ".join(item.path for item in matches)
            )
        return matches[0]

    def read(self, item_or_path: NitroFile | str) -> bytes:
        item = self.find(item_or_path) if isinstance(item_or_path, str) else item_or_path
        return self._data[item.offset : item.offset + item.size]

    def read_range(self, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self._data):
            raise ValueError(f"ROM range 0x{offset:X}+0x{size:X} is invalid")
        return self._data[offset : offset + size]

    def arm9_overlays(self) -> tuple[Arm9Overlay, ...]:
        offset = self.header.arm9_overlay_offset
        size = self.header.arm9_overlay_size
        if not size:
            return ()
        if size % 0x20 or offset + size > len(self._data):
            raise ValueError("ARM9 overlay table is malformed")
        files_by_id = {item.file_id: item for item in self.files}
        result: list[Arm9Overlay] = []
        for cursor in range(offset, offset + size, 0x20):
            (
                overlay_id,
                ram_address,
                ram_size,
                bss_size,
                static_init_start,
                static_init_end,
                file_id,
                compressed_flags,
            ) = struct.unpack_from("<8I", self._data, cursor)
            item = files_by_id.get(file_id)
            if item is None:
                raise ValueError(f"ARM9 overlay {overlay_id} references missing file {file_id}")
            stored = self.read(item)
            compressed_size = compressed_flags & 0xFFFFFF
            flags = compressed_flags >> 24
            decoded = decompress_blz(stored) if flags & 1 else stored
            if len(decoded) != ram_size:
                raise ValueError(
                    f"ARM9 overlay {overlay_id} decoded to 0x{len(decoded):X}, "
                    f"expected 0x{ram_size:X}"
                )
            result.append(
                Arm9Overlay(
                    overlay_id,
                    ram_address,
                    ram_size,
                    bss_size,
                    static_init_start,
                    static_init_end,
                    file_id,
                    compressed_size,
                    flags,
                    decoded,
                )
            )
        return tuple(result)

    def extract(self, output: Path, *, prefix: str = "") -> int:
        output = Path(output)
        normalized_prefix = prefix.replace("\\", "/").strip("/").casefold()
        count = 0
        for item in self.files:
            path_key = item.path.casefold()
            if normalized_prefix and not (
                path_key == normalized_prefix or path_key.startswith(normalized_prefix + "/")
            ):
                continue
            relative = PurePosixPath(item.path)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Unsafe NitroFS path: {item.path}")
            target = output.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.read(item))
            count += 1
        return count
