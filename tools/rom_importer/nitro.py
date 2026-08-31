from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


RGBA = tuple[int, int, int, int]


@dataclass(frozen=True)
class Ncgr:
    bpp: int
    width_tiles: int
    height_tiles: int
    mapping_unit_bytes: int
    tiles: tuple[bytes, ...]


@dataclass(frozen=True)
class Oam:
    x: int
    y: int
    affine: bool
    flags: int
    colors: int
    shape: int
    size: int
    character: int
    palette: int

    @property
    def dimensions(self) -> tuple[int, int]:
        dimensions = {
            (0, 0): (8, 8),
            (0, 1): (16, 16),
            (0, 2): (32, 32),
            (0, 3): (64, 64),
            (1, 0): (16, 8),
            (1, 1): (32, 8),
            (1, 2): (32, 16),
            (1, 3): (64, 32),
            (2, 0): (8, 16),
            (2, 1): (8, 32),
            (2, 2): (16, 32),
            (2, 3): (32, 64),
        }
        try:
            return dimensions[(self.shape, self.size)]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported OAM shape/size {self.shape}/{self.size}"
            ) from exc


@dataclass(frozen=True)
class Cell:
    oams: tuple[Oam, ...]
    partition_offset: int = 0


@dataclass(frozen=True)
class AnimationFrame:
    cell_index: int
    duration_ticks: int


@dataclass(frozen=True)
class AnimationSequence:
    label: str
    mode: int
    frames: tuple[AnimationFrame, ...]


@dataclass(frozen=True)
class Nscr:
    width: int
    height: int
    color_mode: int
    entries: tuple[int, ...]


def parse_ncgr(data: bytes) -> Ncgr:
    if data[:4] not in {b"RGCN", b"RBCN"} or len(data) < 0x30:
        raise ValueError("Data is not a supported NCGR/NCBR file")
    (
        _section_size,
        height,
        width,
        bit_depth,
        mapping,
        _mode,
        tile_data_size,
        _data_offset,
    ) = struct.unpack_from("<IHHIIIII", data, 0x14)
    bpp = 4 if bit_depth == 3 else 8 if bit_depth == 4 else 0
    if not bpp:
        raise ValueError(f"Unsupported NCGR bit-depth code {bit_depth}")
    bytes_per_tile = 0x20 if bpp == 4 else 0x40
    available = min(tile_data_size, max(0, len(data) - 0x30)) // bytes_per_tile
    declared = width * height
    tile_count = declared if declared and declared <= available else available
    tiles: list[bytes] = []
    for index in range(tile_count):
        raw = data[
            0x30 + index * bytes_per_tile : 0x30 + (index + 1) * bytes_per_tile
        ]
        if bpp == 4:
            pixels = bytearray(64)
            for byte_index, value in enumerate(raw):
                pixels[byte_index * 2] = value & 0x0F
                pixels[byte_index * 2 + 1] = value >> 4
            tiles.append(bytes(pixels))
        else:
            tiles.append(raw)
    return Ncgr(
        bpp=bpp,
        width_tiles=width if width not in {0, 0xFFFF} else 0,
        height_tiles=height if height not in {0, 0xFFFF} else 0,
        mapping_unit_bytes=32 << ((mapping >> 20) & 0x3),
        tiles=tuple(tiles),
    )


def parse_nclr(data: bytes) -> tuple[RGBA, ...]:
    if data[:4] not in {b"RLCN", b"RPCN"} or len(data) < 0x28:
        raise ValueError("Data is not an NCLR/NCPR palette")
    extension_size, _bpp, _unknown, _unknown2, palette_size = struct.unpack_from(
        "<IHHII", data, 0x14
    )
    if palette_size == 0 or palette_size > extension_size:
        palette_size = max(0, extension_size - 0x18)
    palette_size = min(palette_size, max(0, len(data) - 0x28))
    colors: list[RGBA] = []
    for offset in range(0x28, 0x28 + palette_size, 2):
        value = struct.unpack_from("<H", data, offset)[0]
        colors.append(
            (
                (value & 0x1F) * 255 // 31,
                ((value >> 5) & 0x1F) * 255 // 31,
                ((value >> 10) & 0x1F) * 255 // 31,
                255,
            )
        )
    if colors:
        colors[0] = (*colors[0][:3], 0)
    return tuple(colors)


def parse_ncer(data: bytes) -> tuple[Cell, ...]:
    if data[:4] != b"RECN" or len(data) < 0x30:
        raise ValueError("Data is not an NCER cell bank")
    (
        _section_size,
        cell_count,
        extended,
        _unknown,
        _mapping,
        partition_data_offset,
    ) = struct.unpack_from("<IHHIII", data, 0x14)
    record_size = 0x10 if extended == 1 else 8
    oam_start = 0x30 + record_size * cell_count
    cells: list[Cell] = []
    for cell_index in range(cell_count):
        record = 0x30 + record_size * cell_index
        oam_count, _readonly, relative = struct.unpack_from("<HHI", data, record)
        oams: list[Oam] = []
        for oam_index in range(oam_count):
            cursor = oam_start + relative + oam_index * 6
            if cursor + 6 > len(data):
                raise ValueError("NCER OAM data is truncated")
            a0, a1, a2 = struct.unpack_from("<HHH", data, cursor)
            oams.append(
                Oam(
                    x=a1 & 0x1FF,
                    y=a0 & 0xFF,
                    affine=bool(a0 & 0x100),
                    flags=(a1 >> 9) & 0x1F,
                    colors=256 if a0 & 0x2000 else 16,
                    shape=(a0 >> 14) & 3,
                    size=(a1 >> 14) & 3,
                    character=a2 & 0x3FF,
                    palette=(a2 >> 12) & 0xF,
                )
            )
        cells.append(Cell(tuple(oams)))

    if partition_data_offset:
        cursor = 0x18 + partition_data_offset
        if cursor + 8 <= len(data):
            _maximum, first_offset = struct.unpack_from("<II", data, cursor)
            cursor += first_offset
            for index, cell in enumerate(cells):
                if cursor + 8 > len(data):
                    break
                partition_offset, _partition_size = struct.unpack_from(
                    "<II", data, cursor
                )
                cells[index] = Cell(cell.oams, partition_offset)
                cursor += 8
    return tuple(cells)


def _parse_labels(data: bytes, offset: int, count: int) -> tuple[str, ...]:
    if offset < 0 or offset + 8 > len(data) or data[offset : offset + 4] != b"LBAL":
        return tuple(f"sequence_{index:02d}" for index in range(count))
    section_size = struct.unpack_from("<I", data, offset + 4)[0]
    if section_size < 8 + count * 4 or offset + section_size > len(data):
        return tuple(f"sequence_{index:02d}" for index in range(count))
    string_base = offset + 8 + count * 4
    labels: list[str] = []
    for index in range(count):
        relative = struct.unpack_from("<I", data, offset + 8 + index * 4)[0]
        start = string_base + relative
        end = data.find(b"\0", start, offset + section_size)
        if end < 0:
            labels.append(f"sequence_{index:02d}")
        else:
            labels.append(data[start:end].decode("ascii", errors="replace"))
    return tuple(labels)


def parse_nanr(data: bytes) -> tuple[AnimationSequence, ...]:
    if data[:4] != b"RNAN" or len(data) < 0x30 or data[0x10:0x14] != b"KNBA":
        raise ValueError("Data is not a NANR animation bank")
    section_size, sequence_count, _total_frames, sequence_offset, refs_offset, frames_offset = struct.unpack_from(
        "<IHHIII", data, 0x14
    )
    labels = _parse_labels(data, 0x10 + section_size, sequence_count)
    sequences: list[AnimationSequence] = []
    for sequence_index in range(sequence_count):
        cursor = 0x18 + sequence_offset + sequence_index * 0x10
        if cursor + 0x10 > len(data):
            raise ValueError("NANR sequence table is truncated")
        frame_count, _first_frame, frame_type, _sequence_type, mode, frame_address = struct.unpack_from(
            "<HHHHII", data, cursor
        )
        frames: list[AnimationFrame] = []
        for frame_index in range(frame_count):
            ref = 0x18 + refs_offset + frame_address + frame_index * 8
            if ref + 8 > len(data):
                raise ValueError("NANR frame reference is truncated")
            data_offset, duration, _marker = struct.unpack_from("<IHH", data, ref)
            frame_data = 0x18 + frames_offset + data_offset
            if frame_data + 2 > len(data):
                raise ValueError("NANR frame data is truncated")
            cell_index = struct.unpack_from("<H", data, frame_data)[0]
            if frame_type not in {0, 1, 2}:
                raise ValueError(f"Unsupported NANR frame type {frame_type}")
            frames.append(AnimationFrame(cell_index, duration))
        sequences.append(AnimationSequence(labels[sequence_index], mode, tuple(frames)))
    return tuple(sequences)


def parse_nscr(data: bytes) -> Nscr:
    if data[:4] != b"RCSN" or len(data) < 0x24:
        raise ValueError("Data is not an NSCR tile map")
    _section_size, width, height, color_mode, map_size = struct.unpack_from(
        "<IHHII", data, 0x14
    )
    map_size = min(map_size, max(0, len(data) - 0x24))
    entries = tuple(
        struct.unpack_from("<H", data, 0x24 + offset)[0]
        for offset in range(0, map_size - (map_size % 2), 2)
    )
    return Nscr(width, height, color_mode, entries)


def _tile_pixel(
    tile: bytes,
    palette: tuple[RGBA, ...],
    index: int,
    bank: int,
    bpp: int,
) -> RGBA:
    color_index = tile[index]
    if color_index == 0:
        return (0, 0, 0, 0)
    palette_index = color_index + (bank * 16 if bpp == 4 else 0)
    return palette[palette_index] if palette_index < len(palette) else (255, 0, 255, 255)


def render_cell_canvas(ncgr: Ncgr, palette: tuple[RGBA, ...], cell: Cell) -> Image.Image:
    """Render on the DS coordinate canvas so animation frames retain their origin."""
    canvas = Image.new("RGBA", (512, 256), (0, 0, 0, 0))
    pixels = canvas.load()
    bytes_per_tile = 0x20 if ncgr.bpp == 4 else 0x40
    tiles_per_character = max(1, ncgr.mapping_unit_bytes // bytes_per_tile)
    for oam in cell.oams:
        width, height = oam.dimensions
        x_origin = (oam.x + 0x100) % 0x200
        y_origin = (oam.y + 0x80) % 0x100
        tile_index = oam.character * tiles_per_character + cell.partition_offset // bytes_per_tile
        flip_x = not oam.affine and bool(oam.flags & 0x08)
        flip_y = not oam.affine and bool(oam.flags & 0x10)
        for tile_y in range(0, height, 8):
            for tile_x in range(0, width, 8):
                if tile_index < len(ncgr.tiles):
                    tile = ncgr.tiles[tile_index]
                    for pixel_y in range(8):
                        for pixel_x in range(8):
                            color = _tile_pixel(
                                tile,
                                palette,
                                pixel_y * 8 + pixel_x,
                                oam.palette,
                                ncgr.bpp,
                            )
                            if color[3] == 0:
                                continue
                            local_x = tile_x + pixel_x
                            local_y = tile_y + pixel_y
                            if flip_x:
                                local_x = width - 1 - local_x
                            if flip_y:
                                local_y = height - 1 - local_y
                            x = x_origin + local_x
                            y = y_origin + local_y
                            if 0 <= x < canvas.width and 0 <= y < canvas.height:
                                pixels[x, y] = color
                tile_index += 1
    return canvas


def render_cell(ncgr: Ncgr, palette: tuple[RGBA, ...], cell: Cell) -> Image.Image:
    canvas = render_cell_canvas(ncgr, palette, cell)
    bounds = canvas.getbbox()
    return canvas.crop(bounds) if bounds else Image.new("RGBA", (1, 1), (0, 0, 0, 0))


def render_tileset(
    ncgr: Ncgr,
    palette: tuple[RGBA, ...],
    *,
    columns: int | None = None,
) -> Image.Image:
    if not ncgr.tiles:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    columns = columns or ncgr.width_tiles
    if not columns:
        columns = max(1, int(math.ceil(math.sqrt(len(ncgr.tiles)))))
    rows = math.ceil(len(ncgr.tiles) / columns)
    image = Image.new("RGBA", (columns * 8, rows * 8), (0, 0, 0, 0))
    pixels = image.load()
    for tile_index, tile in enumerate(ncgr.tiles):
        tile_x = (tile_index % columns) * 8
        tile_y = (tile_index // columns) * 8
        for y in range(8):
            for x in range(8):
                pixels[tile_x + x, tile_y + y] = _tile_pixel(
                    tile, palette, y * 8 + x, 0, ncgr.bpp
                )
    return image


def render_palette_preview(
    palette: tuple[RGBA, ...], *, swatch_size: int = 16, columns: int = 16
) -> Image.Image:
    """Render an NCLR palette as a simple swatch grid for inspection."""
    if not palette:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    columns = max(1, columns)
    rows = math.ceil(len(palette) / columns)
    image = Image.new(
        "RGBA", (columns * swatch_size, rows * swatch_size), (0, 0, 0, 0)
    )
    for index, color in enumerate(palette):
        x = (index % columns) * swatch_size
        y = (index // columns) * swatch_size
        block = Image.new("RGBA", (swatch_size, swatch_size), color)
        image.alpha_composite(block, (x, y))
    return image


def render_screen(ncgr: Ncgr, palette: tuple[RGBA, ...], nscr: Nscr) -> Image.Image:
    if nscr.width <= 0 or nscr.height <= 0:
        raise ValueError("NSCR has invalid dimensions")
    columns = nscr.width // 8
    rows = nscr.height // 8
    image = Image.new("RGBA", (nscr.width, nscr.height), (0, 0, 0, 0))
    pixels = image.load()
    for position, raw in enumerate(nscr.entries[: columns * rows]):
        tile_index = raw & 0x3FF
        if tile_index >= len(ncgr.tiles):
            continue
        flip_x = bool(raw & 0x400)
        flip_y = bool(raw & 0x800)
        bank = (raw >> 12) & 0xF
        tile = ncgr.tiles[tile_index]
        base_x = (position % columns) * 8
        base_y = (position // columns) * 8
        for y in range(8):
            for x in range(8):
                source_x = 7 - x if flip_x else x
                source_y = 7 - y if flip_y else y
                pixels[base_x + x, base_y + y] = _tile_pixel(
                    tile,
                    palette,
                    source_y * 8 + source_x,
                    bank,
                    ncgr.bpp,
                )
    return image


def save_palette_preview(palette: tuple[RGBA, ...], output: Path) -> None:
    columns = 16
    rows = max(1, math.ceil(len(palette) / columns))
    image = Image.new("RGBA", (columns * 16, rows * 16), (0, 0, 0, 0))
    for index, color in enumerate(palette):
        x = (index % columns) * 16
        y = (index // columns) * 16
        block = Image.new("RGBA", (16, 16), color)
        image.alpha_composite(block, (x, y))
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
