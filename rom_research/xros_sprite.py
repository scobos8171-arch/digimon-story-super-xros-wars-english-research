"""Render Xros Wars sprite-archive entries for visual import selection."""

from __future__ import annotations

import argparse
import math
import struct
from dataclasses import dataclass
from pathlib import Path

from rom_research.nds_inventory import read_header, read_nitrofs
from rom_research.dusk_pak import DuskPak
from rom_research.xros_pak import (
    XrosPak,
    find_nitro_file,
    read_nitro_file,
)


SPRITE_ARCHIVES = {
    "graphics": "SPR_NCGR.PAK",
    "palette": "SPR_NCLR.PAK",
    "cells": "SPR_NCER.PAK",
    "animation": "SPR_NANR.PAK",
}

DUSK_SPRITE_ARCHIVES = {
    "graphics": "dat/SPR_CHR.PAK",
    "palette": "dat/SPR_PAL.PAK",
    "cells": "dat/SPR_CEL.PAK",
    "animation": "dat/SPR_ANM.PAK",
}

OAM_DIMENSIONS = {
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


@dataclass(frozen=True)
class Ncgr:
    bpp: int
    mapping_unit_bytes: int
    tiles: tuple[bytes, ...]


@dataclass(frozen=True)
class Oam:
    x: int
    y: int
    affine: bool
    affine_flags: int
    colors: int
    shape: int
    size: int
    character: int
    palette: int

    @property
    def dimensions(self) -> tuple[int, int]:
        try:
            return OAM_DIMENSIONS[(self.shape, self.size)]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported OAM shape/size {self.shape}/{self.size}"
            ) from exc


@dataclass(frozen=True)
class Cell:
    oams: tuple[Oam, ...]
    partition_offset: int = 0


@dataclass(frozen=True)
class RenderedRgba:
    width: int
    height: int
    pixels: bytes


class XrosSpriteSet:
    """Four coordinated PAK files whose entry IDs describe one sprite."""

    def __init__(self, archives: dict[str, XrosPak]):
        missing = set(SPRITE_ARCHIVES) - archives.keys()
        if missing:
            raise ValueError(f"Missing sprite archives: {', '.join(sorted(missing))}")
        counts = {name: len(archive.entries) for name, archive in archives.items()}
        if len(set(counts.values())) != 1:
            raise ValueError(f"Sprite archive entry counts do not match: {counts}")
        self.archives = archives
        self.entry_count = next(iter(counts.values()))

    @classmethod
    def from_rom(cls, rom_path: Path) -> "XrosSpriteSet":
        with rom_path.open("rb") as handle:
            files = read_nitrofs(handle, read_header(handle))
            archives = {
                kind: XrosPak.from_bytes(
                    read_nitro_file(handle, find_nitro_file(files, archive_name))
                )
                for kind, archive_name in SPRITE_ARCHIVES.items()
            }
        return cls(archives)

    def raw_entry(self, kind: str, index: int) -> bytes:
        return self.archives[kind].unpacked_data(index)

    def render(self, index: int, cell_index: int = 0) -> Image.Image:
        from PIL import Image

        rendered = self.render_rgba(index, cell_index)
        return Image.frombytes(
            "RGBA",
            (rendered.width, rendered.height),
            rendered.pixels,
        )

    def render_rgba(self, index: int, cell_index: int = 0) -> RenderedRgba:
        if not 0 <= index < self.entry_count:
            raise IndexError(f"Sprite index {index} is out of range")
        ncgr = parse_ncgr(self.raw_entry("graphics", index))
        palette = parse_nclr(self.raw_entry("palette", index))
        cells = parse_ncer(self.raw_entry("cells", index))
        if not cells:
            return RenderedRgba(1, 1, b"\0\0\0\0")
        if not 0 <= cell_index < len(cells):
            raise IndexError(
                f"Cell {cell_index} is out of range for sprite {index} "
                f"({len(cells)} cells)"
            )
        return render_cell_rgba(ncgr, palette, cells[cell_index])


class DuskSpriteSet(XrosSpriteSet):
    """Dawn/Dusk sprite entries exposed through the shared renderer."""

    @classmethod
    def from_rom(cls, rom_path: Path) -> "DuskSpriteSet":
        with rom_path.open("rb") as handle:
            files = read_nitrofs(handle, read_header(handle))
            archives = {
                kind: DuskPak.from_bytes(
                    read_nitro_file(handle, find_nitro_file(files, archive_name))
                )
                for kind, archive_name in DUSK_SPRITE_ARCHIVES.items()
            }
        return cls(archives)  # type: ignore[arg-type]


def parse_ncgr(data: bytes) -> Ncgr:
    if data[:4] != b"RGCN" or len(data) < 0x30:
        raise ValueError("Entry is not an NCGR file")
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
        raise ValueError(f"Unsupported NCGR bit depth field {bit_depth}")
    # Nitro 1D OBJ mapping uses 32/64/128/256-byte character-number units.
    # Dusk's normal player sprites use 128 bytes, while large boss slots use
    # 256 bytes. The mapping header selects the correct OAM tile stride.
    mapping_unit_bytes = 32 << ((mapping >> 20) & 0x3)
    bytes_per_tile = 0x20 if bpp == 4 else 0x40
    declared_tiles = height * width
    available_tiles = min(tile_data_size, max(0, len(data) - 0x30)) // bytes_per_tile
    tile_count = (
        declared_tiles
        if declared_tiles and declared_tiles <= available_tiles
        else available_tiles
    )
    tile_data = data[0x30:0x30 + tile_count * bytes_per_tile]
    tiles: list[bytes] = []
    for tile_index in range(tile_count):
        raw = tile_data[
            tile_index * bytes_per_tile:(tile_index + 1) * bytes_per_tile
        ]
        if bpp == 4:
            pixels = bytearray(64)
            for byte_index, value in enumerate(raw):
                pixels[byte_index * 2] = value & 0x0F
                pixels[byte_index * 2 + 1] = value >> 4
            tiles.append(bytes(pixels))
        else:
            tiles.append(raw)
    return Ncgr(bpp, mapping_unit_bytes, tuple(tiles))


def parse_nclr(data: bytes) -> tuple[tuple[int, int, int, int], ...]:
    if data[:4] not in {b"RLCN", b"RPCN"} or len(data) < 0x28:
        raise ValueError("Entry is not an NCLR file")
    extension_size, _bpp, _unknown, _unknown2, palette_size = struct.unpack_from(
        "<IHHII", data, 0x14
    )
    if palette_size == 0 or palette_size > extension_size:
        palette_size = max(0, extension_size - 0x18)
    palette_size = min(palette_size, max(0, len(data) - 0x28))
    colors: list[tuple[int, int, int, int]] = []
    for offset in range(0x28, 0x28 + palette_size, 2):
        value = struct.unpack_from("<H", data, offset)[0]
        red = (value & 0x1F) * 255 // 31
        green = ((value >> 5) & 0x1F) * 255 // 31
        blue = ((value >> 10) & 0x1F) * 255 // 31
        colors.append((red, green, blue, 255))
    if colors:
        colors[0] = (*colors[0][:3], 0)
    return tuple(colors)


def parse_ncer(data: bytes) -> tuple[Cell, ...]:
    if data[:4] != b"RECN" or len(data) < 0x30:
        raise ValueError("Entry is not an NCER file")
    (
        _cell_section_size,
        cell_count,
        extended,
        _unknown,
        _mapping,
        partition_data_offset,
    ) = struct.unpack_from("<IHHIII", data, 0x14)
    cell_record_size = 0x10 if extended == 1 else 8
    oam_start = 0x30 + cell_record_size * cell_count
    cells: list[Cell] = []
    for cell_index in range(cell_count):
        record = 0x30 + cell_record_size * cell_index
        oam_count, _read_only, relative_oam = struct.unpack_from("<HHI", data, record)
        oams: list[Oam] = []
        for oam_index in range(oam_count):
            oam_offset = oam_start + relative_oam + oam_index * 6
            if oam_offset + 6 > len(data):
                raise ValueError("NCER OAM data extends past the file")
            a0, a1, a2 = struct.unpack_from("<HHH", data, oam_offset)
            oams.append(
                Oam(
                    x=a1 & 0x1FF,
                    y=a0 & 0xFF,
                    affine=bool(a0 & 0x100),
                    affine_flags=(a1 >> 9) & 0x1F,
                    colors=256 if a0 & 0x2000 else 16,
                    shape=(a0 >> 14) & 3,
                    size=(a1 >> 14) & 3,
                    character=a2 & 0x3FF,
                    palette=(a2 >> 12) & 0xF,
                )
            )
        cells.append(Cell(tuple(oams)))

    if partition_data_offset:
        position = 0x18 + partition_data_offset
        if position + 8 <= len(data):
            _maximum_size, first_data_offset = struct.unpack_from("<II", data, position)
            position += first_data_offset
            for index, cell in enumerate(cells):
                if position + 8 > len(data):
                    break
                partition_offset, _partition_size = struct.unpack_from(
                    "<II", data, position
                )
                cells[index] = Cell(cell.oams, partition_offset)
                position += 8
    return tuple(cells)


def render_cell(
    ncgr: Ncgr,
    palette: tuple[tuple[int, int, int, int], ...],
    cell: Cell,
) -> Image.Image:
    from PIL import Image

    rendered = render_cell_rgba(ncgr, palette, cell)
    return Image.frombytes(
        "RGBA",
        (rendered.width, rendered.height),
        rendered.pixels,
    )


def render_cell_rgba(
    ncgr: Ncgr,
    palette: tuple[tuple[int, int, int, int], ...],
    cell: Cell,
) -> RenderedRgba:
    canvas_width = 512
    canvas_height = 256
    canvas = bytearray(canvas_width * canvas_height * 4)
    for oam in cell.oams:
        width, height = oam.dimensions
        x_offset = (oam.x + 0x100) % 0x200
        y_offset = (oam.y + 0x80) % 0x100

        bytes_per_tile = 0x20 if ncgr.bpp == 4 else 0x40
        tiles_per_character = ncgr.mapping_unit_bytes // bytes_per_tile
        tile_index = (
            oam.character * tiles_per_character
            + cell.partition_offset // bytes_per_tile
        )
        oam_pixels = bytearray(width * height * 4)
        for tile_y in range(0, height, 8):
            for tile_x in range(0, width, 8):
                if tile_index < len(ncgr.tiles):
                    bank_offset = (
                        oam.palette * 16
                        if ncgr.bpp == 4 and len(palette) > 16
                        else 0
                    )
                    for pixel_y in range(8):
                        for pixel_x in range(8):
                            color_index = ncgr.tiles[tile_index][pixel_y * 8 + pixel_x]
                            if color_index == 0:
                                continue
                            palette_index = bank_offset + color_index
                            color = (
                                palette[palette_index]
                                if palette_index < len(palette)
                                else (255, 0, 255, 255)
                            )
                            destination = (
                                (tile_y + pixel_y) * width + tile_x + pixel_x
                            ) * 4
                            oam_pixels[destination:destination + 4] = bytes(color)
                tile_index += 1

        flip_x = not oam.affine and bool(oam.affine_flags & 0x08)
        flip_y = not oam.affine and bool(oam.affine_flags & 0x10)
        for source_y in range(height):
            for source_x in range(width):
                source = (source_y * width + source_x) * 4
                alpha = oam_pixels[source + 3]
                if alpha == 0:
                    continue
                destination_x = x_offset + (width - 1 - source_x if flip_x else source_x)
                destination_y = y_offset + (height - 1 - source_y if flip_y else source_y)
                if not (
                    0 <= destination_x < canvas_width
                    and 0 <= destination_y < canvas_height
                ):
                    continue
                destination = (
                    destination_y * canvas_width + destination_x
                ) * 4
                canvas[destination:destination + 4] = oam_pixels[source:source + 4]

    left = canvas_width
    top = canvas_height
    right = -1
    bottom = -1
    for y in range(canvas_height):
        row_start = y * canvas_width * 4
        for x in range(canvas_width):
            if canvas[row_start + x * 4 + 3]:
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)
    if right < left or bottom < top:
        return RenderedRgba(1, 1, b"\0\0\0\0")

    width = right - left + 1
    height = bottom - top + 1
    cropped = bytearray(width * height * 4)
    for y in range(height):
        source = ((top + y) * canvas_width + left) * 4
        destination = y * width * 4
        cropped[destination:destination + width * 4] = canvas[
            source:source + width * 4
        ]
    return RenderedRgba(width, height, bytes(cropped))


def make_contact_sheet(
    sprite_set: XrosSpriteSet,
    start: int,
    count: int,
    output_path: Path,
    columns: int = 16,
    cell_size: int = 96,
) -> None:
    from PIL import Image, ImageDraw

    stop = min(sprite_set.entry_count, start + count)
    if start < 0 or start >= stop:
        raise ValueError("The requested sprite range is empty")
    rows = math.ceil((stop - start) / columns)
    sheet = Image.new("RGBA", (columns * cell_size, rows * cell_size), "#18202b")
    draw = ImageDraw.Draw(sheet)
    for position, index in enumerate(range(start, stop)):
        column = position % columns
        row = position // columns
        x = column * cell_size
        y = row * cell_size
        try:
            sprite = sprite_set.render(index)
            maximum = cell_size - 10
            sprite.thumbnail((maximum, maximum), Image.Resampling.NEAREST)
            image_x = x + (cell_size - sprite.width) // 2
            image_y = y + 9 + (cell_size - 9 - sprite.height) // 2
            sheet.alpha_composite(sprite, (image_x, image_y))
        except (ValueError, IndexError) as exc:
            draw.text((x + 4, y + 22), "render\nerror", fill="#ff6b6b")
            draw.text((x + 4, y + cell_size - 12), str(exc)[:12], fill="#ff6b6b")
        draw.text((x + 3, y + 2), f"{index:04d}", fill="#f2f5f8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(output_path, quality=92)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=256)
    parser.add_argument("--columns", type=int, default=16)
    parser.add_argument("--cell-size", type=int, default=96)
    parser.add_argument(
        "--game",
        choices=("xros", "dusk"),
        default="xros",
        help="archive layout to read (default: xros)",
    )
    args = parser.parse_args()
    sprite_set = (
        XrosSpriteSet.from_rom(args.rom)
        if args.game == "xros"
        else DuskSpriteSet.from_rom(args.rom)
    )
    make_contact_sheet(
        sprite_set,
        args.start,
        args.count,
        args.output,
        args.columns,
        args.cell_size,
    )
    print(
        f"Rendered sprites {args.start}.."
        f"{min(sprite_set.entry_count, args.start + args.count) - 1} "
        f"to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
