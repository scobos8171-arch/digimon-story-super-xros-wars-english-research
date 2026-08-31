from __future__ import annotations

import json
import re
import struct
from pathlib import Path
from typing import Any

from PIL import Image

from .archives import XrosPak, decompress_nintendo_rle
from .nds import NdsRom
from .nitro import Ncgr, Nscr, parse_ncgr, parse_nclr, parse_nscr, render_screen


def _parse_field_char(data: bytes) -> Ncgr:
    declared = struct.unpack_from("<I", data, 0)[0]
    raw = data[4 : 4 + declared]
    tiles = []
    for offset in range(0, len(raw) - 31, 32):
        packed = raw[offset : offset + 32]
        pixels = bytearray(64)
        for index, value in enumerate(packed):
            pixels[index * 2] = value & 0xF
            pixels[index * 2 + 1] = value >> 4
        tiles.append(bytes(pixels))
    return Ncgr(4, 0, 0, 32, tuple(tiles))


def _parse_field_palette(data: bytes) -> tuple[tuple[int, int, int, int], ...]:
    declared = min(struct.unpack_from("<I", data, 0)[0], len(data) - 4)
    colors = []
    for offset in range(4, 4 + declared, 2):
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


def _parse_field_screen(data: bytes) -> Nscr:
    width, height = struct.unpack_from("<HH", data, 0)
    count = min((width // 8) * (height // 8), (len(data) - 4) // 2)
    entries = struct.unpack_from(f"<{count}H", data, 4)
    return Nscr(width, height, 0, tuple(entries))


def extract_backgrounds(rom_path: Path, output: Path) -> dict[str, Any]:
    """Render complete NCGR/NCLR/NSCR background triplets from a local ROM."""
    rom = NdsRom(rom_path)
    paths = {item.path.replace("\\", "/"): item for item in rom.files}
    casefolded = {path.casefold(): path for path in paths}
    output.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []

    for path, item in sorted(paths.items()):
        if not path.casefold().endswith(".ncgr"):
            continue
        stem = path[:-5]
        palette_path = casefolded.get((stem + ".NCLR").casefold())
        screen_path = casefolded.get((stem + ".NSCR").casefold())
        if palette_path is None or screen_path is None:
            continue
        try:
            image = render_screen(
                parse_ncgr(rom.read(item)),
                parse_nclr(rom.read(paths[palette_path])),
                parse_nscr(rom.read(paths[screen_path])),
            )
        except (AssertionError, IndexError, KeyError, ValueError) as exc:
            records.append({"source": stem, "error": str(exc)})
            continue
        relative = Path(path).with_suffix(".png")
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination)
        records.append(
            {
                "source": stem,
                "path": relative.as_posix(),
                "width": image.width,
                "height": image.height,
            }
        )

    # Dusk battle stages use extensionless, RLE-compressed Nitro resources:
    # <id>ac/<id>as/<id>ap for the main layer and <id>bc/<id>bs for its overlay.
    battle_dir = output / "battle_stages"
    palette_files = sorted(
        path for path in paths if path.startswith("dat/btmap/") and path.endswith("ap")
    )
    for palette_path in palette_files:
        filename = Path(palette_path).name
        stage_id = filename[:-2]
        required = {
            suffix: casefolded.get(f"dat/btmap/{stage_id}{suffix}".casefold())
            for suffix in ("ac", "as", "ap")
        }
        if any(value is None for value in required.values()):
            continue
        try:
            palette = parse_nclr(
                decompress_nintendo_rle(rom.read(paths[str(required["ap"])]))
            )
            main = render_screen(
                parse_ncgr(decompress_nintendo_rle(rom.read(paths[str(required["ac"])]))),
                palette,
                parse_nscr(decompress_nintendo_rle(rom.read(paths[str(required["as"])]))),
            )
            battle_dir.mkdir(parents=True, exist_ok=True)
            main_path = battle_dir / f"{stage_id}_main.png"
            main.save(main_path)
            screen = main.crop((0, 0, min(256, main.width), min(192, main.height)))
            screen_path = battle_dir / f"{stage_id}_screen.png"
            screen.save(screen_path)
            record: dict[str, Any] = {
                "source": f"dat/btmap/{stage_id}",
                "path": main_path.relative_to(output).as_posix(),
                "width": main.width,
                "height": main.height,
                "kind": "battle_stage_main",
                "screen": screen_path.relative_to(output).as_posix(),
            }
            overlay_char = casefolded.get(f"dat/btmap/{stage_id}bc".casefold())
            overlay_screen = casefolded.get(f"dat/btmap/{stage_id}bs".casefold())
            if overlay_char is not None and overlay_screen is not None:
                overlay = render_screen(
                    parse_ncgr(decompress_nintendo_rle(rom.read(paths[overlay_char]))),
                    palette,
                    parse_nscr(decompress_nintendo_rle(rom.read(paths[overlay_screen]))),
                )
                overlay_path = battle_dir / f"{stage_id}_overlay.png"
                overlay.save(overlay_path)
                composite = main.copy()
                composite.alpha_composite(overlay)
                composite_path = battle_dir / f"{stage_id}.png"
                composite.save(composite_path)
                record["overlay"] = overlay_path.relative_to(output).as_posix()
                record["composite"] = composite_path.relative_to(output).as_posix()
            records.append(record)
        except (AssertionError, IndexError, KeyError, ValueError) as exc:
            records.append({"source": f"dat/btmap/{stage_id}", "error": str(exc)})

    # Field maps use <id>a.c/.p/.s and optional <id>b.c/.p/.s layers.
    field_dir = output / "field_maps"
    field_palettes = sorted(
        path
        for path in paths
        if re.fullmatch(r"dat/map/[^/]+a\.p", path, flags=re.IGNORECASE)
    )
    for palette_path in field_palettes:
        match = re.fullmatch(r"dat/map/(.+)a\.p", palette_path, flags=re.IGNORECASE)
        if match is None:
            continue
        map_id = match.group(1)
        layer_images = []
        layer_paths: dict[str, str] = {}
        try:
            for layer in ("a", "b"):
                char_path = casefolded.get(f"dat/map/{map_id}{layer}.c".casefold())
                screen_path = casefolded.get(f"dat/map/{map_id}{layer}.s".casefold())
                layer_palette_path = casefolded.get(f"dat/map/{map_id}{layer}.p".casefold())
                if char_path is None or screen_path is None or layer_palette_path is None:
                    continue
                character_data = decompress_nintendo_rle(rom.read(paths[char_path]))
                screen_data = decompress_nintendo_rle(rom.read(paths[screen_path]))
                palette_data = decompress_nintendo_rle(rom.read(paths[layer_palette_path]))
                if len(character_data) <= 8:
                    continue
                layer_image = render_screen(
                    _parse_field_char(character_data),
                    _parse_field_palette(palette_data),
                    _parse_field_screen(screen_data),
                )
                field_dir.mkdir(parents=True, exist_ok=True)
                layer_path = field_dir / f"{map_id}_{layer}.png"
                layer_image.save(layer_path)
                layer_images.append(layer_image)
                layer_paths[layer] = layer_path.relative_to(output).as_posix()
            if not layer_images:
                continue
            composite = layer_images[0].copy()
            for overlay in layer_images[1:]:
                composite.alpha_composite(overlay)
            composite_path = field_dir / f"{map_id}.png"
            composite.save(composite_path)
            record: dict[str, Any] = {
                "source": f"dat/map/{map_id}",
                "path": composite_path.relative_to(output).as_posix(),
                "layers": layer_paths,
                "width": composite.width,
                "height": composite.height,
                "kind": "field_map",
            }

            # Each .0t expands to an eight-byte header followed by a one-bit-per-
            # pixel traversal mask.  Zero bits are floor and one bits are blocked.
            # Keeping this as a PNG lets Godot use the cartridge-authored geometry
            # without bundling any ROM data in the project itself.
            traversal_path = casefolded.get(f"dat/map/{map_id}.0t".casefold())
            if traversal_path is not None:
                traversal = decompress_nintendo_rle(rom.read(paths[traversal_path]))
                if len(traversal) >= 8:
                    mask_width, mask_height = struct.unpack_from("<II", traversal, 0)
                    packed = traversal[8:]
                    if mask_width * mask_height <= len(packed) * 8:
                        mask = Image.new("L", (mask_width, mask_height), 0)
                        pixels = mask.load()
                        for pixel_index in range(mask_width * mask_height):
                            source_byte = packed[pixel_index >> 3]
                            blocked = (source_byte >> (pixel_index & 7)) & 1
                            pixels[pixel_index % mask_width, pixel_index // mask_width] = (
                                0 if blocked else 255
                            )
                        mask_path = field_dir / f"{map_id}_walkable.png"
                        mask.save(mask_path)
                        record["walkable_mask"] = mask_path.relative_to(output).as_posix()
                        record["mask_width"] = mask_width
                        record["mask_height"] = mask_height

            records.append(record)
        except (AssertionError, IndexError, KeyError, ValueError) as exc:
            records.append({"source": f"dat/map/{map_id}", "error": str(exc)})

    # Lost Evolution and Super Xros Wars coordinate their field components by
    # entry number across top-level XrosPak archives. Collision entries begin
    # with width/height and a 16-byte header followed by a one-bit pixel mask.
    packed_names = ("MAP_NCGR.PAK", "MAP_NCLR.PAK", "MAP_NSCR.PAK")
    if all(name in paths for name in packed_names):
        graphics = XrosPak(rom.read(paths["MAP_NCGR.PAK"]))
        palettes = XrosPak(rom.read(paths["MAP_NCLR.PAK"]))
        screens = XrosPak(rom.read(paths["MAP_NSCR.PAK"]))
        collision = (
            XrosPak(rom.read(paths["MAP_COLL.PAK"]))
            if "MAP_COLL.PAK" in paths
            else None
        )
        packed_count = min(
            len(graphics.entries), len(palettes.entries), len(screens.entries)
        )
        for map_index in range(packed_count):
            source = f"packed_map/{map_index:03d}"
            try:
                image = render_screen(
                    parse_ncgr(graphics.unpack(map_index)),
                    parse_nclr(palettes.unpack(map_index)),
                    parse_nscr(screens.unpack(map_index)),
                )
                field_dir.mkdir(parents=True, exist_ok=True)
                image_path = field_dir / f"{map_index}.png"
                image.save(image_path)
                record = {
                    "source": source,
                    "path": image_path.relative_to(output).as_posix(),
                    "width": image.width,
                    "height": image.height,
                    "kind": "packed_field_map",
                }
                if collision is not None and map_index < len(collision.entries):
                    raw = collision.unpack(map_index)
                    if len(raw) >= 16:
                        mask_width, mask_height = struct.unpack_from("<II", raw, 0)
                        packed = raw[16:]
                        if mask_width * mask_height <= len(packed) * 8:
                            mask = Image.new("L", (mask_width, mask_height), 0)
                            pixels = mask.load()
                            for pixel_index in range(mask_width * mask_height):
                                blocked = (
                                    packed[pixel_index >> 3]
                                    >> (pixel_index & 7)
                                ) & 1
                                pixels[
                                    pixel_index % mask_width,
                                    pixel_index // mask_width,
                                ] = 0 if blocked else 255
                            mask_path = field_dir / f"{map_index}_walkable.png"
                            mask.save(mask_path)
                            record["walkable_mask"] = mask_path.relative_to(
                                output
                            ).as_posix()
                records.append(record)
            except (AssertionError, IndexError, KeyError, ValueError) as exc:
                records.append({"source": source, "error": str(exc)})

    manifest = {
        "source_rom": rom_path.name,
        "game_code": rom.header.game_code,
        "rendered": sum("path" in item for item in records),
        "failed": sum("error" in item for item in records),
        "backgrounds": records,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest
