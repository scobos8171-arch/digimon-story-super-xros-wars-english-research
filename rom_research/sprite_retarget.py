"""Retarget imported sprite art into a Dawn/Dusk-compatible sprite envelope.

Super Xros Wars and Dawn/Dusk both store Nitro NCGR/NCLR/NCER/NANR resources,
but their battle sprites do not use the same cell bounds or animation layout.
Copying all four donor files verbatim therefore produces oversized sprites in
battle and overlapping pieces on the starter screen.

This module keeps the donor's visible pixels while rebuilding them inside an
existing Dawn/Dusk template:

* donor frames are nearest-neighbour scaled to the template cell bounds;
* the template NCER and NANR are retained verbatim;
* graphics are re-tiled using the template OAM character addresses;
* a DS BGR555 palette is rebuilt for the template bit depth.

The result uses only formats and layouts already accepted by the Dusk engine.
No runtime scaling, high-resolution overlay, or new battle logic is involved.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from rom_research.xros_sprite import (
    Cell,
    Oam,
    RenderedRgba,
    parse_ncer,
    parse_ncgr,
    parse_nclr,
    render_cell_rgba,
)


RGBA = tuple[int, int, int, int]


def _screen_x(oam: Oam) -> int:
    return (oam.x + 0x100) % 0x200


def _screen_y(oam: Oam) -> int:
    return (oam.y + 0x80) % 0x100


def _cell_bounds(cell: Cell) -> tuple[int, int, int, int]:
    if not cell.oams:
        return (0, 0, 1, 1)
    left = min(_screen_x(oam) for oam in cell.oams)
    top = min(_screen_y(oam) for oam in cell.oams)
    right = max(_screen_x(oam) + oam.dimensions[0] for oam in cell.oams)
    bottom = max(_screen_y(oam) + oam.dimensions[1] for oam in cell.oams)
    return left, top, right, bottom


def _rgba_pixels(image: RenderedRgba) -> tuple[RGBA, ...]:
    return tuple(
        tuple(image.pixels[index:index + 4])  # type: ignore[misc]
        for index in range(0, len(image.pixels), 4)
    )


def _fit_frame(
    source: RenderedRgba,
    width: int,
    height: int,
    *,
    margin: int,
    maximum_size: tuple[int, int] | None,
    maximum_scale: float,
    horizontal_offset: int,
    vertical_alignment: str,
) -> tuple[RGBA, ...]:
    """Scale one cropped donor frame into a transparent template canvas."""

    canvas: list[RGBA] = [(0, 0, 0, 0)] * (width * height)
    usable_width = max(1, width - margin * 2)
    usable_height = max(1, height - margin * 2)
    if maximum_size is not None:
        usable_width = min(usable_width, maximum_size[0])
        usable_height = min(usable_height, maximum_size[1])
    if maximum_scale <= 0:
        raise ValueError("maximum_scale must be positive")
    scale = min(
        usable_width / source.width,
        usable_height / source.height,
        maximum_scale,
    )
    output_width = max(1, round(source.width * scale))
    output_height = max(1, round(source.height * scale))
    offset_x = (width - output_width) // 2 + horizontal_offset
    offset_x = max(0, min(width - output_width, offset_x))
    if vertical_alignment == "top":
        offset_y = margin
    elif vertical_alignment == "center":
        offset_y = (height - output_height) // 2
    elif vertical_alignment == "bottom":
        # Normal battle sprites read better when their feet share the template
        # baseline. Starter-screen imports can opt into top alignment because
        # Dusk places their lower half behind the selection-card backgrounds.
        offset_y = height - margin - output_height
    else:
        raise ValueError(
            "vertical_alignment must be 'top', 'center', or 'bottom'"
        )
    source_pixels = _rgba_pixels(source)
    for y in range(output_height):
        source_y = min(source.height - 1, y * source.height // output_height)
        for x in range(output_width):
            source_x = min(source.width - 1, x * source.width // output_width)
            color = source_pixels[source_y * source.width + source_x]
            if color[3]:
                canvas[(offset_y + y) * width + offset_x + x] = color
    return tuple(canvas)


def _choose_palette(
    canvases: Iterable[tuple[RGBA, ...]],
    maximum_opaque_colors: int,
) -> tuple[RGBA, ...]:
    counts: Counter[RGBA] = Counter()
    for canvas in canvases:
        counts.update(color for color in canvas if color[3])
    selected = [
        color
        for color, _count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:maximum_opaque_colors]
    ]
    return ((0, 0, 0, 0), *selected)


def _nearest_palette_index(color: RGBA, palette: tuple[RGBA, ...]) -> int:
    if not color[3]:
        return 0
    try:
        return palette.index(color)
    except ValueError:
        pass
    return min(
        range(1, len(palette)),
        key=lambda index: (
            (color[0] - palette[index][0]) ** 2
            + (color[1] - palette[index][1]) ** 2
            + (color[2] - palette[index][2]) ** 2
        ),
    )


def _encode_tiles(
    template_graphics: bytes,
    template_cells: tuple[Cell, ...],
    canvases: tuple[tuple[RGBA, ...], ...],
    palette: tuple[RGBA, ...],
) -> bytes:
    graphics = parse_ncgr(template_graphics)
    bytes_per_tile = 0x20 if graphics.bpp == 4 else 0x40
    tiles_per_character = graphics.mapping_unit_bytes // bytes_per_tile
    tile_pixels = [bytearray(64) for _ in graphics.tiles]
    for cell, canvas in zip(template_cells, canvases):
        left, top, right, bottom = _cell_bounds(cell)
        canvas_width = right - left
        canvas_height = bottom - top
        for oam in cell.oams:
            width, height = oam.dimensions
            base_tile = (
                oam.character * tiles_per_character
                + cell.partition_offset // bytes_per_tile
            )
            flip_x = not oam.affine and bool(oam.affine_flags & 0x08)
            flip_y = not oam.affine and bool(oam.affine_flags & 0x10)
            for tile_y in range(0, height, 8):
                for tile_x in range(0, width, 8):
                    tile_index = base_tile + (tile_y // 8) * (width // 8) + tile_x // 8
                    if tile_index >= len(tile_pixels):
                        raise ValueError("Template OAM references tiles outside its NCGR")
                    tile = tile_pixels[tile_index]
                    for pixel_y in range(8):
                        for pixel_x in range(8):
                            local_x = tile_x + pixel_x
                            local_y = tile_y + pixel_y
                            display_x = width - 1 - local_x if flip_x else local_x
                            display_y = height - 1 - local_y if flip_y else local_y
                            canvas_x = _screen_x(oam) - left + display_x
                            canvas_y = _screen_y(oam) - top + display_y
                            color = (
                                canvas[canvas_y * canvas_width + canvas_x]
                                if 0 <= canvas_x < canvas_width
                                and 0 <= canvas_y < canvas_height
                                else (0, 0, 0, 0)
                            )
                            tile[pixel_y * 8 + pixel_x] = _nearest_palette_index(
                                color,
                                palette,
                            )

    output = bytearray(template_graphics)
    cursor = 0x30
    if graphics.bpp == 8:
        for tile in tile_pixels:
            output[cursor:cursor + 0x40] = tile
            cursor += 0x40
    else:
        for tile in tile_pixels:
            packed = bytearray(bytes_per_tile)
            for index in range(0, 64, 2):
                packed[index // 2] = tile[index] | (tile[index + 1] << 4)
            output[cursor:cursor + bytes_per_tile] = packed
            cursor += bytes_per_tile
    return bytes(output)


def _encode_palette(template_palette: bytes, palette: tuple[RGBA, ...]) -> bytes:
    output = bytearray(template_palette)
    capacity = max(0, (len(output) - 0x28) // 2)
    if len(palette) > capacity:
        raise ValueError("Template NCLR cannot hold the rebuilt palette")
    for index in range(capacity):
        color = palette[index] if index < len(palette) else (0, 0, 0, 0)
        red = color[0] * 31 // 255
        green = color[1] * 31 // 255
        blue = color[2] * 31 // 255
        value = red | (green << 5) | (blue << 10)
        output[0x28 + index * 2:0x2A + index * 2] = value.to_bytes(2, "little")
    return bytes(output)


def retarget_sprite_components(
    donor: dict[str, bytes],
    template: dict[str, bytes],
    *,
    margin: int = 2,
    maximum_size: tuple[int, int] | None = None,
    maximum_scale: float = 1.0,
    horizontal_offset: int = 0,
    repeat_first_frame: bool = False,
    vertical_alignment: str = "bottom",
) -> dict[str, bytes]:
    """Return donor art rebuilt with a Dusk template's cell/animation layout."""

    donor_graphics = parse_ncgr(donor["graphics"])
    donor_palette = parse_nclr(donor["palette"])
    donor_cells = parse_ncer(donor["cells"])
    template_graphics = parse_ncgr(template["graphics"])
    template_cells = parse_ncer(template["cells"])
    if not donor_cells or not template_cells:
        raise ValueError("Donor and template sprites must contain at least one cell")

    donor_frames = tuple(
        render_cell_rgba(donor_graphics, donor_palette, cell)
        for cell in donor_cells
    )
    canvases: list[tuple[RGBA, ...]] = []
    for index, template_cell in enumerate(template_cells):
        left, top, right, bottom = _cell_bounds(template_cell)
        donor_frame_index = 0 if repeat_first_frame else min(
            index,
            len(donor_frames) - 1,
        )
        canvases.append(
            _fit_frame(
                donor_frames[donor_frame_index],
                max(1, right - left),
                max(1, bottom - top),
                margin=margin,
                maximum_size=maximum_size,
                maximum_scale=maximum_scale,
                horizontal_offset=horizontal_offset,
                vertical_alignment=vertical_alignment,
            )
        )
    maximum_colors = 15 if template_graphics.bpp == 4 else 255
    palette = _choose_palette(canvases, maximum_colors)
    if len(palette) == 1:
        raise ValueError("Donor sprite renders fully transparent")
    return {
        "graphics": _encode_tiles(
            template["graphics"],
            template_cells,
            tuple(canvases),
            palette,
        ),
        "palette": _encode_palette(template["palette"], palette),
        "cells": template["cells"],
        "animation": template["animation"],
    }
