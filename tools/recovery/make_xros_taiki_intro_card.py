#!/usr/bin/env python3
"""Create the English replacement for the Taiki lower-screen intro card."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


FONT = Path(r"C:\Windows\Fonts\consolab.ttf")


def text_mask(size: tuple[int, int], font: ImageFont.FreeTypeFont, text: str, y: int) -> tuple[Image.Image, int]:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    bounds = draw.textbbox((0, 0), text, font=font)
    x = (size[0] - (bounds[2] - bounds[0])) // 2
    draw.text((x, y), text, font=font, fill=255)
    return mask.point(lambda value: 255 if value >= 128 else 0), x


def paint(out: Image.Image, mask: Image.Image, fill: tuple[int, int, int, int], mid: tuple[int, int, int, int], edge: tuple[int, int, int, int]) -> None:
    out.paste(edge, mask=mask.filter(ImageFilter.MaxFilter(5)))
    out.paste(mid, mask=mask.filter(ImageFilter.MaxFilter(3)))
    out.paste(fill, mask=mask)


def paint_line(
    out: Image.Image,
    font: ImageFont.FreeTypeFont,
    y: int,
    segments: tuple[tuple[str, bool], ...],
) -> None:
    """Paint a centred line, optionally highlighting individual segments red."""
    text = "".join(segment for segment, _red in segments)
    mask, x = text_mask(out.size, font, text, y)
    paint(out, mask, (246, 246, 246, 255), (97, 115, 180, 255), (24, 24, 32, 255))
    cursor = x
    draw = ImageDraw.Draw(Image.new("L", out.size, 0))
    for segment, red in segments:
        if red:
            red_mask = Image.new("L", out.size, 0)
            ImageDraw.Draw(red_mask).text((cursor, y), segment, font=font, fill=255)
            red_mask = red_mask.point(lambda value: 255 if value >= 128 else 0)
            paint(out, red_mask, (231, 48, 29, 255), (143, 24, 15, 255), (48, 8, 8, 255))
        cursor += round(draw.textlength(segment, font=font))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    size = (256, 192)
    font = ImageFont.truetype(str(FONT), 11)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    white = (246, 246, 246, 255)
    blue_mid = (97, 115, 180, 255)
    dark_edge = (24, 24, 32, 255)

    cards = {
        33: ((88, (("I'M ", False), ("TAIKI KUDO.", True))),
             (108, (("A MIDDLE SCHOOL STUDENT", False),)),
             (126, (("FROM TOKYO.", False),))),
        34: ((82, (("ONE DAY, I HEARD", False),)),
             (104, (("SOMEONE CALLING FOR HELP...", False),)),
             (126, (("SO I FOLLOWED THE VOICE.", False),))),
        35: ((82, (("MY FRIENDS AND I WERE", False),)),
             (104, (("SENT TO ANOTHER WORLD:", False),)),
             (126, (("THE ", False), ("DIGITAL WORLD.", True))),),
        36: ((82, (("THERE, I MET CREATURES", False),)),
             (104, (("MADE OF DIGITAL DATA:", False),)),
             (126, (("THE ", False), ("DIGIMON.", True))),),
        37: ((82, (("SHOUTMON, A HOTHEADED", True),)),
             (104, (("DIGIMON WHO DREAMS OF", False),)),
             (126, (("BECOMING DIGIMON ", False), ("KING.", True))),),
        38: ((92, (("BALLISTAMON,", True),)),
             (118, (("OUR RELIABLE POWERHOUSE.", False),))),
        39: ((92, (("DORULUMON,", True),)),
             (118, (("A FREE-SPIRITED WANDERER.", False),))),
        40: ((82, (("IN THE ", False), ("DIGITAL WORLD,", True))),
             (104, (("POWERFUL DIGIMON", False),)),
             (126, (("WAITED FOR US...", False),))),
        41: ((92, (("OUR ", False), ("NEW ADVENTURE", True))),
             (118, (("WAS ABOUT TO BEGIN...", False),))),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for entry, lines in cards.items():
        out = Image.new("RGBA", size, (0, 0, 0, 0))
        for y, segments in lines:
            paint_line(out, font, y, segments)
        stem = f"entry_{entry:04d}_intro_EN_256x192"
        out.save(args.output_dir / f"{stem}.png")
        out.resize((1024, 768), Image.Resampling.NEAREST).save(args.output_dir / f"{stem}_4x.png")
        indexed = out.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
        indexed.save(args.output_dir / f"{stem}_INDEXED.png", transparency=0)
    print(f"wrote {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
