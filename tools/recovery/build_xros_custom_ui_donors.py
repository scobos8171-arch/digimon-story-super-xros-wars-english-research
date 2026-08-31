"""Build original English PNG donors for Xros-only Japanese UI sprites.

The files produced by this script are review assets, not a ROM patch.  Every
PNG keeps the rendered dimensions and palette of its source Xros cell.  Text
is drawn without antialiasing so the donor can later be encoded back into the
original NCGR/NCER envelope without introducing unsupported colours.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


REPO_ROOT = Path(__file__).resolve().parents[2]
ROM_RESEARCH = REPO_ROOT / "work" / "DigimonNDSRomEditor-master"
if str(ROM_RESEARCH) not in sys.path:
    sys.path.insert(0, str(ROM_RESEARCH))

from rom_research.xros_sprite import XrosSpriteSet, parse_ncer  # noqa: E402


TRANSLATIONS: dict[int, dict[int, str]] = {
    86: {0: "CAMERA"},
    127: {6: "DIGIXROS!"},
    131: {0: "JOGRESS UP", 1: "JOGRESS UP"},
    132: {0: "SELECT SKILL", 1: "SELECT SKILL"},
    141: {0: "WORK REPORT"},
    142: {0: "EXPEDITION REPORT"},
    143: {0: "LEVEL-UP REPORT"},
    2235: {
        0: "LIVE EVENT REPORT",
        1: "LIVE EVENT REPORT",
        2: "LIVE EVENT REPORT",
        3: "LIVE EVENT REPORT",
    },
    2242: {0: "QUEST REWARDS", 1: "QUEST REWARDS"},
    2244: {0: "QUEST COMPLETION"},
    2250: {
        0: "DIGIBIT BANK",
        1: "WITHDRAW",
        2: "DEPOSIT",
        3: "EXIT ATM",
    },
}


def load_font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        Path("C:/Windows/Fonts/consolab.ttf"),
        Path("C:/Windows/Fonts/lucon.ttf"),
        Path("C:/Windows/Fonts/consola.ttf"),
    ):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def opaque_palette(image: Image.Image) -> list[tuple[int, int, int, int]]:
    counts = Counter(pixel for pixel in image.convert("RGBA").getdata() if pixel[3])
    return [color for color, _count in counts.most_common()]


def nearest(color: tuple[int, int, int, int], palette: list[tuple[int, int, int, int]]):
    if not palette:
        return color
    return min(
        palette,
        key=lambda item: sum((item[channel] - color[channel]) ** 2 for channel in range(3)),
    )


def text_mask(text: str, size: tuple[int, int]) -> Image.Image:
    width, height = size
    for font_size in range(max(5, height), 4, -1):
        font = load_font(font_size)
        probe = Image.new("1", size, 0)
        draw = ImageDraw.Draw(probe)
        box = draw.textbbox((0, 0), text, font=font, stroke_width=0)
        text_width = box[2] - box[0]
        text_height = box[3] - box[1]
        if text_width <= max(1, width - 8) and text_height <= max(1, height - 4):
            x = (width - text_width) // 2 - box[0]
            y = (height - text_height) // 2 - box[1]
            draw.text((x, y), text, font=font, fill=1)
            return probe
    probe = Image.new("1", size, 0)
    ImageDraw.Draw(probe).text((1, 1), text, font=ImageFont.load_default(), fill=1)
    return probe


def donor_image(source: Image.Image, text: str) -> Image.Image:
    """Return a transparent, DS-palette-safe English text donor."""

    source = source.convert("RGBA")
    palette = opaque_palette(source)
    # Most fixed labels are separate OBJ text sprites.  Keeping the donor
    # transparent avoids baking menu frames into the replacement.
    result = Image.new("RGBA", source.size, (0, 0, 0, 0))
    mask = text_mask(text, source.size)
    outline = mask.filter(ImageFilter.MaxFilter(3))
    shadow = nearest((20, 20, 20, 255), palette)
    foreground = nearest((255, 255, 255, 255), palette)
    result.paste(shadow, (0, 0), outline)
    result.paste(foreground, (0, 0), mask)
    return result


def build(rom: Path, output: Path) -> dict[str, object]:
    sprites = XrosSpriteSet.from_rom(rom)
    output.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    for entry_id, cells_to_translate in TRANSLATIONS.items():
        cells = parse_ncer(sprites.raw_entry("cells", entry_id))
        entry_dir = output / f"entry_{entry_id:04d}"
        entry_dir.mkdir(parents=True, exist_ok=True)
        for cell_id, text in cells_to_translate.items():
            if cell_id >= len(cells):
                raise IndexError(f"Entry {entry_id} has no cell {cell_id}")
            source = sprites.render(entry_id, cell_id)
            donor = donor_image(source, text)
            source_path = entry_dir / f"cell_{cell_id:02d}_source.png"
            donor_path = entry_dir / f"cell_{cell_id:02d}_english.png"
            source.save(source_path)
            donor.save(donor_path)
            entries.append(
                {
                    "entry": entry_id,
                    "cell": cell_id,
                    "text": text,
                    "width": source.width,
                    "height": source.height,
                    "source": str(source_path.resolve()),
                    "donor": str(donor_path.resolve()),
                }
            )
    manifest = {
        "source_rom": str(rom.resolve()),
        "format": "RGBA PNG; transparent; nearest-colour source palette; no antialiasing",
        "entries": entries,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = build(args.rom, args.output)
    print(f"Built {len(result['entries'])} English donor cells in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
