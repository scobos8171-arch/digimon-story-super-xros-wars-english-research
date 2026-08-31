#!/usr/bin/env python3
"""Inject artist-edited command buttons into Xros entry 1971 cells 21-34."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "tools" / "recovery"),
    str(ROOT / "work" / "DigimonNDSRomEditor-master"),
]

from build_xros_custom_ui_rom import (  # noqa: E402
    CELLS_PATH, GRAPHICS_PATH, PALETTE_PATH, XrosPak, arm9_slice,
    build_xros_pak, encode_selected_cells, find_nitro_file, parse_ncer,
    parse_ncgr, parse_nclr, read_header, read_nitro_file, read_nitrofs,
    render_full_cell, replace_nitrofs_files,
)


ENTRY = 1971
FILES = {
    21: "ORDERS_A.png", 22: "ORDERS_B.png",
    23: "SPECIAL_A.png", 24: "SPECIAL_B.png",
    25: "DIGIXROS_A.png", 26: "DIGIXROS_B.png",
    27: "ITEMS_A.png", 28: "ITEMS_B.png",
    29: "TACTICS_A.png", 30: "TACTICS_B.png",
    31: "FORMATION_A.png", 32: "FORMATION_B.png",
    33: "WAIT_A.png", 34: "WAIT_B.png",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def visible_pixels_match(left: Image.Image, right: Image.Image) -> bool:
    """Ignore RGB payload hidden beneath fully transparent pixels."""
    for a, b in zip(left.getdata(), right.getdata()):
        if a[3] != b[3]:
            return False
        if a[3] and a[:3] != b[:3]:
            return False
    return True


def restore_visible(image: Image.Image, storage: Image.Image) -> tuple[Image.Image, tuple[int, int, int, int]]:
    visible = storage.getbbox()
    if visible is None:
        raise ValueError("source cell has no visible pixels")
    visible_size = (visible[2] - visible[0], visible[3] - visible[1])
    if image.size == storage.size:
        return image, (0, 0, storage.width, storage.height)
    if image.size != visible_size:
        raise ValueError(f"PNG is {image.size}; expected {visible_size} or {storage.size}; no scaling")
    restored = Image.new("RGBA", storage.size, (0, 0, 0, 0))
    restored.alpha_composite(image, (visible[0], visible[1]))
    return restored, visible


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("png_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("qa_dir", type=Path)
    args = parser.parse_args()
    source = args.source.read_bytes()
    with args.source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        gfx_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, GRAPHICS_PATH)))
        pal_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cel_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))
    entries = [gfx_pak.unpacked_data(i) for i in range(len(gfx_pak.entries))]
    palette = parse_nclr(pal_pak.unpacked_data(ENTRY))
    cells = parse_ncer(cel_pak.unpacked_data(ENTRY))
    original = parse_ncgr(entries[ENTRY])
    canvases = [render_full_cell(original, palette, cell) for cell in cells]
    bounds: dict[int, tuple[int, int, int, int]] = {}
    artists: dict[int, Image.Image] = {}
    args.qa_dir.mkdir(parents=True, exist_ok=True)
    nonexact_visible_pixels: dict[str, int] = {}
    for cell, filename in FILES.items():
        artist = Image.open(args.png_dir / filename).convert("RGBA")
        if artist.getchannel("A").getextrema()[0] != 0:
            raise ValueError(f"{filename} has no transparent pixels")
        canvases[cell].save(args.qa_dir / f"before_{cell:02d}.png")
        canvases[cell], bounds[cell] = restore_visible(artist, canvases[cell])
        artists[cell] = artist
    entries[ENTRY] = encode_selected_cells(entries[ENTRY], cells, canvases, palette, set(FILES))
    patched = replace_nitrofs_files(source, {GRAPHICS_PATH: build_xros_pak(entries)})
    if arm9_slice(source) != arm9_slice(patched):
        raise AssertionError("ARM9 changed")
    decoded_graphics = parse_ncgr(entries[ENTRY])
    for cell, filename in FILES.items():
        decoded = render_full_cell(decoded_graphics, palette, cells[cell])
        visible = decoded.crop(bounds[cell])
        visible.save(args.qa_dir / f"rom_{cell:02d}_{filename}")
        difference = sum(
            a[3] != b[3] or (a[3] and a[:3] != b[:3])
            for a, b in zip(visible.getdata(), artists[cell].getdata())
        )
        if difference:
            # WAIT A/B share flipped ROM character tiles. The artist's pair
            # cannot both exist byte-for-byte; preserve exact B and record the
            # small, still-readable A hardware normalization.
            if cell != 33:
                raise AssertionError(f"ROM-decoded cell {cell} differs from {filename}")
            nonexact_visible_pixels[filename] = difference
    changed = [i for i in range(len(entries)) if gfx_pak.unpacked_data(i) != entries[i]]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    manifest = {
        "source": str(args.source.resolve()),
        "output": str(args.output.resolve()),
        "source_sha256": sha(source),
        "output_sha256": sha(patched),
        "changed_archives": [GRAPHICS_PATH],
        "changed_sprite_entries": changed,
        "changed_cells": [f"{ENTRY}:{cell}" for cell in FILES],
        "arm9_unchanged": True,
        "rom_decodes_match_artist_pngs_except_shared_wait_a": True,
        "shared_tile_normalization": nonexact_visible_pixels,
    }
    (args.qa_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
