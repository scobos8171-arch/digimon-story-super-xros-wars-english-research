"""Export corrected Xros button artwork as standalone indexed PNG assets.

This tool never opens or writes a ROM. It works exclusively from previously
rendered PNG cells and the artist's manual PNG assets.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "recovery"))

from build_xros_custom_ui_rom import make_compact_3x5_mask, make_hex_4x7_mask  # noqa: E402


RESULT_LABELS = [
    "BACK", "CONFIRM", "SWITCH", "BACK", "CONFIRM", "SWITCH",
    "GAINED EXP", "FOUND ITEMS", "NEXT", "FINISH", "TO STATUS",
    "WORLD MAP", "FIELD GUIDE",
]
BATTLE_LABELS = [
    "BACK", "BATTLE START", "BACK", "BATTLE START", "BACK", "BATTLE START",
    "ALL TACTICS", "ALL TACTICS", "ALL TACTICS", "BACK", "BACK", "BACK",
]
ENTRY110_LABELS = ["BACK", "CONFIRM", "NEXT", "FINISH", "FINISH"]
ENTRY147_LABELS = {1: "CONFIRM", 2: "BACK", 3: "BACK"}


def indexed_copy(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    colours: OrderedDict[tuple[int, int, int, int], int] = OrderedDict()
    colours[(0, 0, 0, 0)] = 0
    for pixel in rgba.getdata():
        key = pixel if pixel[3] else (0, 0, 0, 0)
        if key not in colours:
            colours[key] = len(colours)
    if len(colours) > 16:
        raise ValueError(f"Asset uses {len(colours)} colours; expected at most 16")
    palette = [0] * 768
    for colour, index in colours.items():
        palette[index * 3:index * 3 + 3] = list(colour[:3])
    output = Image.new("P", rgba.size, 0)
    output.putpalette(palette)
    pixels = output.load()
    source = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            value = source[x, y]
            pixels[x, y] = colours[value if value[3] else (0, 0, 0, 0)]
    output.info["transparency"] = 0
    return output


def reconstruct_label_well(source: Image.Image, label: str) -> Image.Image:
    """Remove Japanese glyphs from one already-cropped native button cell."""
    result = source.convert("RGBA").copy()
    width, height = result.size
    left, right = (19, width - 2)
    top, bottom = (3, height - 3)
    pixels = result.load()
    for y in range(top, bottom):
        # The controller emblem ends before x=19. The pixel immediately after
        # it is a clean sample of the button's intentional horizontal band.
        sample_x = min(width - 3, 18)
        fill = pixels[sample_x, y]
        if not fill[3]:
            row = [pixels[x, y] for x in range(left, right) if pixels[x, y][3]]
            fill = row[0] if row else (0, 0, 0, 0)
        for x in range(left, right):
            if pixels[x, y][3]:
                pixels[x, y] = fill

    opaque = [pixel for pixel in result.getdata() if pixel[3]]
    dark = min(opaque, key=lambda colour: sum(colour[:3]))
    light = max(opaque, key=lambda colour: sum(colour[:3]))
    text_box = (left, 4, right, height - 3)
    box_size = (text_box[2] - text_box[0], text_box[3] - text_box[1])
    if len(label) >= 9:
        mask_local = make_compact_3x5_mask(label, box_size, scale=1, scale_x=1, scale_y=1)
    else:
        mask_local = make_hex_4x7_mask(label, box_size)
    mask = Image.new("1", result.size, 0)
    mask.paste(mask_local, text_box[:2])
    shadow = Image.new("1", result.size, 0)
    shadow.paste(mask_local, (text_box[0] + 1, text_box[1] + 1))
    result.paste(dark, (0, 0), shadow)
    result.paste(light, (0, 0), mask)
    return result


def save_asset(image: Image.Image, path: Path) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    indexed = indexed_copy(image)
    indexed.save(path, transparency=0)
    return {"file": str(path.resolve()), "size": list(indexed.size), "mode": indexed.mode}


def proof_sheet(items: list[tuple[str, Path]], output: Path, columns: int = 3) -> None:
    slot_w, slot_h, scale = 360, 130, 6
    rows = (len(items) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * slot_w, rows * slot_h), (18, 26, 40, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (label, path) in enumerate(items):
        x, y = (index % columns) * slot_w, (index // columns) * slot_h
        draw.text((x + 8, y + 8), label, fill="white")
        image = Image.open(path).convert("RGBA")
        factor = min(scale, max(1, (slot_w - 20) // image.width), max(1, (slot_h - 42) // image.height))
        enlarged = image.resize((image.width * factor, image.height * factor), Image.Resampling.NEAREST)
        sheet.alpha_composite(enlarged, (x + (slot_w - enlarged.width) // 2, y + 34 + (slot_h - 34 - enlarged.height) // 2))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def export(v105: Path, clean: Path, v114: Path, manual: Path, output: Path) -> dict[str, object]:
    records: list[dict[str, object]] = []
    proof_groups: dict[str, list[tuple[str, Path]]] = {"small": [], "results": [], "battle": []}

    def copy_render(group: str, root: Path, entry: str, cell: int, name: str, label: str):
        source = root / f"entry_{entry}" / f"cell_{cell:02d}.png"
        destination = output / group / name
        records.append(save_asset(Image.open(source), destination))
        proof_groups[group].append((label, destination))

    for cell, label in enumerate(ENTRY110_LABELS):
        copy_render("small", v105, "0110", cell, f"entry110_cell{cell:02d}_{label.lower().replace(' ', '_')}.png", f"110:{cell} {label}")
    for cell, label in ENTRY147_LABELS.items():
        copy_render("small", v105, "0147", cell, f"entry147_cell{cell:02d}_{label.lower()}.png", f"147:{cell} {label}")

    source194 = clean / "entry_0194" / "cell_00.png"
    fixed194 = reconstruct_label_well(Image.open(source194), "BACK")
    path194 = output / "small" / "entry194_cell00_back.png"
    records.append(save_asset(fixed194, path194))
    proof_groups["small"].append(("194:0 BACK", path194))

    for entry, filename, label in (
        (196, "tiny_hex_back_entry196.png", "196:8 Hex BACK"),
        (198, "tiny_hex_back_entry198.png", "198:8 Tiny BACK"),
    ):
        destination = output / "small" / f"entry{entry}_cell08_back.png"
        records.append(save_asset(Image.open(manual / filename), destination))
        proof_groups["small"].append((label, destination))

    for cell, label in enumerate(RESULT_LABELS):
        source = clean / "entry_2218" / f"cell_{cell:02d}.png"
        fixed = reconstruct_label_well(Image.open(source), label)
        destination = output / "results" / f"entry2218_cell{cell:02d}_{label.lower().replace(' ', '_')}.png"
        records.append(save_asset(fixed, destination))
        proof_groups["results"].append((f"2218:{cell} {label}", destination))

    for cell, label in enumerate(BATTLE_LABELS):
        copy_render("battle", v114, "1987", cell, f"entry1987_cell{cell:02d}_{label.lower().replace(' ', '_')}.png", f"1987:{cell} {label}")

    proof_sheet(proof_groups["small"], output / "proof" / "01_small_buttons.png")
    proof_sheet(proof_groups["results"], output / "proof" / "02_result_buttons.png")
    proof_sheet(proof_groups["battle"], output / "proof" / "03_battle_buttons.png")
    report = {"rom_modified": False, "asset_count": len(records), "assets": records}
    (output / "asset_manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("v105_rendered", type=Path)
    parser.add_argument("clean_rendered", type=Path)
    parser.add_argument("v114_rendered", type=Path)
    parser.add_argument("manual", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(export(**vars(args)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
