#!/usr/bin/env python3
"""Inject one native-size transparent SKIP button into Xros entry 2002 cell 2."""

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
    CELLS_PATH,
    GRAPHICS_PATH,
    PALETTE_PATH,
    XrosPak,
    arm9_slice,
    build_xros_pak,
    encode_selected_cells,
    find_nitro_file,
    parse_ncer,
    parse_ncgr,
    parse_nclr,
    read_header,
    read_nitro_file,
    read_nitrofs,
    render_full_cell,
    replace_nitrofs_files,
)


ENTRY = 2002
CELL = 2


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("skip_png", type=Path)
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
    original_graphics = parse_ncgr(entries[ENTRY])
    canvases = [render_full_cell(original_graphics, palette, cell) for cell in cells]
    before = canvases[CELL]
    replacement = Image.open(args.skip_png).convert("RGBA")
    visible = before.getbbox()
    if visible is None:
        raise ValueError("original SKIP cell has no visible bounds")
    visible_size = (visible[2] - visible[0], visible[3] - visible[1])
    if replacement.size not in {before.size, visible_size}:
        raise ValueError(
            f"SKIP is {replacement.size}; expected {visible_size} visible or {before.size} padded; "
            "no scaling performed"
        )
    if replacement.getchannel("A").getextrema()[0] != 0:
        raise ValueError("SKIP PNG has no transparent pixels")
    if replacement.size == before.size:
        storage_replacement = replacement
    else:
        storage_replacement = Image.new("RGBA", before.size, (0, 0, 0, 0))
        storage_replacement.alpha_composite(replacement, (visible[0], visible[1]))
    canvases[CELL] = storage_replacement
    entries[ENTRY] = encode_selected_cells(entries[ENTRY], cells, canvases, palette, {CELL})
    patched = replace_nitrofs_files(source, {GRAPHICS_PATH: build_xros_pak(entries)})
    if arm9_slice(source) != arm9_slice(patched):
        raise AssertionError("ARM9 changed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.qa_dir.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    after = render_full_cell(parse_ncgr(entries[ENTRY]), palette, cells[CELL])
    before.save(args.qa_dir / "before_skip.png")
    replacement.save(args.qa_dir / "artist_skip.png")
    after.save(args.qa_dir / "rom_decoded_skip.png")
    decoded_visible = after.crop(visible)
    decoded_visible.save(args.qa_dir / "rom_decoded_skip_visible.png")
    if list(decoded_visible.getdata()) != list(replacement.getdata()):
        raise AssertionError("ROM-decoded SKIP differs from supplied PNG")
    changed = [
        i for i in range(len(entries))
        if gfx_pak.unpacked_data(i) != entries[i]
    ]
    manifest = {
        "source": str(args.source.resolve()),
        "output": str(args.output.resolve()),
        "artist_png": str(args.skip_png.resolve()),
        "source_sha256": sha(source),
        "output_sha256": sha(patched),
        "changed_archives": [GRAPHICS_PATH],
        "changed_sprite_entries": changed,
        "changed_cell": f"{ENTRY}:{CELL}",
        "arm9_unchanged": True,
        "rom_decode_matches_artist_png": True,
    }
    (args.qa_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
