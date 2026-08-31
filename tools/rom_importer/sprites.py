from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .archives import DuskPak, XrosPak
from .nds import NdsRom
from .nitro import (
    AnimationSequence,
    parse_nanr,
    parse_ncer,
    parse_ncgr,
    parse_nclr,
    render_cell,
    render_cell_canvas,
)


@dataclass(frozen=True)
class SpriteResource:
    graphics: bytes
    palette: bytes
    cells: bytes
    animation: bytes
    metadata: bytes | None = None

    def rendered_cells(self) -> tuple[Image.Image, ...]:
        ncgr = parse_ncgr(self.graphics)
        palette = parse_nclr(self.palette)
        canvases = tuple(
            render_cell_canvas(ncgr, palette, cell) for cell in parse_ncer(self.cells)
        )
        # NCER coordinates share one origin across the entire bank. Cropping each
        # cell independently makes sprites resize and slide between animations.
        bounds = [canvas.getbbox() for canvas in canvases]
        visible = [bound for bound in bounds if bound is not None]
        if not visible:
            return tuple(Image.new("RGBA", (1, 1), (0, 0, 0, 0)) for _ in canvases)
        union = (
            min(bound[0] for bound in visible),
            min(bound[1] for bound in visible),
            max(bound[2] for bound in visible),
            max(bound[3] for bound in visible),
        )
        return tuple(canvas.crop(union) for canvas in canvases)

    def sequences(self) -> tuple[AnimationSequence, ...]:
        try:
            return parse_nanr(self.animation)
        except ValueError:
            return ()


class CoordinatedSprites:
    def __init__(self, archives: dict[str, DuskPak | XrosPak]):
        counts = {len(archive.entries) for archive in archives.values()}
        if len(counts) != 1:
            raise ValueError(f"Coordinated archive counts differ: {sorted(counts)}")
        self.archives = archives
        self.count = next(iter(counts))

    @classmethod
    def dusk(cls, rom: NdsRom) -> "CoordinatedSprites":
        paths = {
            "graphics": "dat/SPR_CHR.PAK",
            "palette": "dat/SPR_PAL.PAK",
            "cells": "dat/SPR_CEL.PAK",
            "animation": "dat/SPR_ANM.PAK",
        }
        return cls({key: DuskPak(rom.read(path)) for key, path in paths.items()})

    @classmethod
    def xros(cls, rom: NdsRom) -> "CoordinatedSprites":
        paths = {
            "graphics": "SPR_NCGR.PAK",
            "palette": "SPR_NCLR.PAK",
            "cells": "SPR_NCER.PAK",
            "animation": "SPR_NANR.PAK",
        }
        return cls({key: XrosPak(rom.read(path)) for key, path in paths.items()})

    def resource(self, index: int) -> SpriteResource:
        return SpriteResource(
            graphics=self.archives["graphics"].unpack(index),
            palette=self.archives["palette"].unpack(index),
            cells=self.archives["cells"].unpack(index),
            animation=self.archives["animation"].unpack(index),
        )


class DuskBattleSprites:
    GROUP_SIZE = 5

    def __init__(self, rom: NdsRom):
        self.archive = DuskPak(rom.read("dat/BTCHR.PAK"))
        self.count = len(self.archive.entries) // self.GROUP_SIZE

    def resource(self, slot: int) -> SpriteResource:
        if not 0 <= slot < self.count:
            raise IndexError(f"Dusk battle slot {slot} is out of range")
        base = slot * self.GROUP_SIZE
        return SpriteResource(
            metadata=self.archive.unpack(base),
            graphics=self.archive.unpack(base + 1),
            palette=self.archive.unpack(base + 2),
            cells=self.archive.unpack(base + 3),
            animation=self.archive.unpack(base + 4),
        )


MCHR_DIMENSIONS = {
    128: (16, 16),
    256: (16, 32),
    512: (32, 32),
    1024: (32, 64),
    2048: (64, 64),
}


class DuskMapSprites:
    """Dusk's compact nine-frame MCHR walking-sprite archives."""

    def __init__(self, rom: NdsRom):
        self.graphics = DuskPak(rom.read("dat/MCHR_CHR.PAK"))
        self.palettes = DuskPak(rom.read("dat/MCHR_PAL.PAK"))
        self.animations = DuskPak(rom.read("dat/MCHR_ANM.PAK"))
        self.hitboxes = DuskPak(rom.read("dat/MCHR_HIT.PAK"))
        self.count = min(
            len(self.graphics.entries),
            len(self.palettes.entries),
            len(self.animations.entries),
            len(self.hitboxes.entries),
        )

    def raw_components(self, index: int) -> dict[str, bytes]:
        return {
            "graphics": self.graphics.unpack(index),
            "palette": self.palettes.unpack(index),
            "animation": self.animations.unpack(index),
            "hitbox": self.hitboxes.unpack(index),
        }

    def frames(self, index: int) -> tuple[Image.Image, ...]:
        raw = self.graphics.unpack(index)
        palette_raw = self.palettes.unpack(index)
        if len(raw) < 8:
            raise ValueError(f"MCHR entry {index} is truncated")
        count = int.from_bytes(raw[0:4], "little")
        frame_size = int.from_bytes(raw[4:8], "little")
        if frame_size not in MCHR_DIMENSIONS:
            raise ValueError(f"MCHR entry {index} has unsupported frame size {frame_size}")
        if 8 + count * frame_size > len(raw):
            raise ValueError(f"MCHR entry {index} frame data is truncated")
        colors = []
        for offset in range(0, min(32, len(palette_raw)), 2):
            value = int.from_bytes(palette_raw[offset : offset + 2], "little")
            colors.append(
                (
                    (value & 31) * 255 // 31,
                    ((value >> 5) & 31) * 255 // 31,
                    ((value >> 10) & 31) * 255 // 31,
                    255,
                )
            )
        if colors:
            colors[0] = (*colors[0][:3], 0)
        width, height = MCHR_DIMENSIONS[frame_size]
        frames: list[Image.Image] = []
        for frame_index in range(count):
            frame_raw = raw[
                8 + frame_index * frame_size : 8 + (frame_index + 1) * frame_size
            ]
            image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            pixels = image.load()
            tile_index = 0
            for tile_y in range(0, height, 8):
                for tile_x in range(0, width, 8):
                    tile = frame_raw[tile_index * 32 : (tile_index + 1) * 32]
                    tile_index += 1
                    for byte_index, value in enumerate(tile):
                        x = (byte_index * 2) % 8
                        y = (byte_index * 2) // 8
                        low, high = value & 15, value >> 4
                        if low and low < len(colors):
                            pixels[tile_x + x, tile_y + y] = colors[low]
                        if high and high < len(colors):
                            pixels[tile_x + x + 1, tile_y + y] = colors[high]
            frames.append(image)
        return tuple(frames)


def normalized_frame_hash(frames: tuple[Image.Image, ...] | list[Image.Image]) -> str:
    digest = hashlib.sha256()
    for image in frames:
        rgba = image.convert("RGBA")
        bounds = rgba.getbbox()
        if bounds:
            rgba = rgba.crop(bounds)
        digest.update(rgba.width.to_bytes(2, "little"))
        digest.update(rgba.height.to_bytes(2, "little"))
        digest.update(rgba.tobytes())
    return digest.hexdigest()


def compose_sheet(
    frames: tuple[Image.Image, ...] | list[Image.Image],
    *,
    columns: int | None = None,
) -> tuple[Image.Image, tuple[int, int]]:
    if not frames:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0)), (1, 1)
    width = max(frame.width for frame in frames)
    height = max(frame.height for frame in frames)
    columns = columns or len(frames)
    rows = (len(frames) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * width, rows * height), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        x = (index % columns) * width + (width - frame.width) // 2
        y = (index // columns) * height + (height - frame.height)
        sheet.alpha_composite(frame, (x, y))
    return sheet, (width, height)


def save_resource_components(resource: SpriteResource, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    if resource.metadata is not None:
        (output / "metadata.bin").write_bytes(resource.metadata)
    (output / "graphics.NCGR").write_bytes(resource.graphics)
    (output / "palette.NCLR").write_bytes(resource.palette)
    (output / "cells.NCER").write_bytes(resource.cells)
    (output / "animation.NANR").write_bytes(resource.animation)
