"""Complete the remaining small Xros UI button families without plate overlays.

The selected localization ROM is the output base.  Clean Japanese cells donate
only their untouched native frames; their glyph wells are reconstructed one
scanline at a time and then lettered with the same compact 4x7 face used by the
working English hex menu.  User-supplied native pixel art is imported only when
its dimensions exactly match the live cell.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))
sys.path.insert(0, str(ROOT / "tools" / "recovery"))

from build_xros_custom_ui_rom import (  # noqa: E402
    CELLS_PATH,
    GRAPHICS_PATH,
    PALETTE_PATH,
    arm9_slice,
    edit_canvas,
    encode_selected_cells,
    render_full_cell,
)
from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.nitrofs_patch import replace_nitrofs_files  # noqa: E402
from rom_research.xros_pak import XrosPak, build_xros_pak, find_nitro_file, read_nitro_file  # noqa: E402
from rom_research.xros_sprite import parse_ncer, parse_ncgr, parse_nclr  # noqa: E402


LABELS: dict[int, dict[int, str]] = {
    194: {0: "BACK"},
    2218: {
        0: "BACK",
        1: "CONFIRM",
        2: "SWITCH",
        3: "BACK",
        4: "CONFIRM",
        5: "SWITCH",
        6: "GAINED EXP",
        7: "FOUND ITEMS",
        8: "NEXT",
        9: "FINISH",
        10: "TO STATUS",
        11: "WORLD MAP",
        12: "FIELD GUIDE",
    },
}


def load_archives(rom: Path):
    with rom.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        graphics = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, GRAPHICS_PATH)))
        palettes = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cells = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))
    return graphics, palettes, cells


def row_mode_blank(source: Image.Image, left: int, right: int) -> Image.Image:
    """Erase baked glyphs while preserving each frame's native row gradient."""
    result = source.copy().convert("RGBA")
    # These NCERs compose a short 18px control inside a 32px wrapped OBJ
    # canvas.  Authored rows land five pixels higher after encoding, so the
    # original glyph well actually occupies raw rows 10..22.
    top, bottom = (10, 23) if result.height >= 32 else (4, result.height - 2)
    right = min(right, result.width - 2)
    for y in range(top, bottom):
        row = [result.getpixel((x, y)) for x in range(left, right)]
        opaque = [color for color in row if color[3] and max(color[:3]) - min(color[:3]) > 8]
        candidates = opaque or [color for color in row if color[3]]
        if not candidates:
            continue
        # Native background colors occupy more pixels than either the white
        # face or dark shadow of the Japanese glyphs on every interior row.
        fill = Counter(candidates).most_common(1)[0][0]
        for x in range(left, right):
            if result.getpixel((x, y))[3]:
                result.putpixel((x, y), fill)
    return result


def fit_native(image: Image.Image, target: Image.Image) -> Image.Image:
    """Center native art without resampling and retain the live OAM alpha."""
    if image.width > target.width or image.height > target.height:
        raise ValueError(f"Native asset {image.size} exceeds live canvas {target.size}")
    result = target.copy()
    x = (target.width - image.width) // 2
    y = (target.height - image.height) // 2
    result.alpha_composite(image.convert("RGBA"), (x, y))
    result.putalpha(target.getchannel("A"))
    return result


def text_spec(entry: int, text: str, width: int, height: int) -> dict[str, object]:
    left = 18 if width <= 65 else 20
    right = width - 2
    seam_safe = entry == 2218
    return {
        "text": text,
        "mode": "frame",
        "font_style": "compact_3x5" if seam_safe else "hex_4x7",
        "font_scale": 1,
        # These controls use a pale centre band.  Solid dark lettering is the
        # native relationship; white lettering would disappear into it and
        # leave only a fragmented shadow visible.
        "text_tone": "dark",
        "shadow": False,
        "outline": False,
        "text_rect": (left, 6, right, 16) if seam_safe else (
            (left, 9, right, 21) if height >= 32 else (left, 4, right, 16)
        ),
    }


def build(source: Path, clean: Path, manual_dir: Path, output: Path, manifest: Path) -> dict[str, object]:
    source_data = source.read_bytes()
    source_graphics, source_palettes, source_cells = load_archives(source)
    clean_graphics, clean_palettes, clean_cells = load_archives(clean)
    graphics_entries = [source_graphics.unpacked_data(i) for i in range(len(source_graphics.entries))]
    applied: list[dict[str, object]] = []

    for entry, labels in LABELS.items():
        graphics = parse_ncgr(graphics_entries[entry])
        palette = parse_nclr(source_palettes.unpacked_data(entry))
        cells = parse_ncer(source_cells.unpacked_data(entry))
        canvases = [render_full_cell(graphics, palette, cell) for cell in cells]

        donor_graphics = parse_ncgr(clean_graphics.unpacked_data(entry))
        donor_palette = parse_nclr(clean_palettes.unpacked_data(entry))
        donor_cells = parse_ncer(clean_cells.unpacked_data(entry))
        selected: set[int] = set()

        for cell, text in labels.items():
            donor = render_full_cell(donor_graphics, donor_palette, donor_cells[cell])
            target = canvases[cell]
            if donor.size != target.size:
                raise ValueError(f"Entry {entry} cell {cell}: donor {donor.size} != target {target.size}")
            blank = row_mode_blank(donor, 18 if target.width <= 65 else 20, target.width - 2)
            canvases[cell] = edit_canvas(
                blank, text_spec(entry, text, target.width, target.height), palette, None
            )
            selected.add(cell)
            applied.append({"entry": entry, "cell": cell, "text": text, "method": "clean-frame"})

        graphics_entries[entry] = encode_selected_cells(
            graphics_entries[entry], cells, canvases, palette, selected
        )

    # The manual 62x20 hex Back button is already final native pixel art.
    entry, cell = 196, 8
    graphics = parse_ncgr(graphics_entries[entry])
    palette = parse_nclr(source_palettes.unpacked_data(entry))
    cells = parse_ncer(source_cells.unpacked_data(entry))
    canvases = [render_full_cell(graphics, palette, value) for value in cells]
    manual = Image.open(manual_dir / "tiny_hex_back_entry196.png").convert("RGBA")
    canvases[cell] = fit_native(manual, canvases[cell])
    graphics_entries[entry] = encode_selected_cells(
        graphics_entries[entry], cells, canvases, palette, {cell}
    )
    applied.append({"entry": entry, "cell": cell, "text": "BACK", "method": "manual-native-62x20"})

    patched = replace_nitrofs_files(source_data, {GRAPHICS_PATH: build_xros_pak(graphics_entries)})
    if arm9_slice(source_data) != arm9_slice(patched):
        raise AssertionError("ARM9 changed during small-button completion")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patched)
    report = {
        "source": str(source.resolve()),
        "clean_donor": str(clean.resolve()),
        "output": str(output.resolve()),
        "source_sha256": hashlib.sha256(source_data).hexdigest(),
        "output_sha256": hashlib.sha256(patched).hexdigest(),
        "arm9_unchanged": True,
        "patched_archives": [GRAPHICS_PATH],
        "applied": applied,
        "preserved": [
            "entry 147: existing clean CONFIRM/BACK states",
            "entry 198 cell 8: existing clean tiny B BACK state",
            "entry 1987: centered battle-button work from source build",
        ],
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("clean", type=Path)
    parser.add_argument("manual_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(**vars(args)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
