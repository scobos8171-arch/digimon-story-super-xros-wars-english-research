#!/usr/bin/env python3
"""Recover Xros battle-banner names with local Manga OCR.

The ROM stores these move names as outlined Japanese sprite artwork, not as
normal message strings.  This read-only helper renders one copy of each
banner, OCRs it locally, and compares the result with the translation cache.
It deliberately records confidence instead of silently accepting weak fuzzy
matches; the UI patcher can then use exact/cache-backed names and fall back to
neutral English identifiers for unresolved artwork.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

from PIL import Image
from manga_ocr import MangaOcr


ROOT = Path(__file__).resolve().parents[2]
EDITOR = ROOT / "work" / "DigimonNDSRomEditor-master"
sys.path.insert(0, str(EDITOR))

from rom_research.xros_sprite import XrosSpriteSet  # noqa: E402


JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


def normalize(value: str) -> str:
    value = value.replace("\n", "").replace(" ", "")
    return re.sub(r"[^\u3040-\u30ff\u3400-\u9fffA-Za-z0-9]+", "", value)


def best_translation(ocr: str, translations: dict[str, str]) -> tuple[str, str, float]:
    needle = normalize(ocr)
    candidates = [(key, normalize(key)) for key in translations if JAPANESE.search(key)]
    exact = next((key for key, cleaned in candidates if cleaned == needle), None)
    if exact is not None:
        return exact, str(translations[exact]), 1.0
    best_key = ""
    best_score = 0.0
    for key, cleaned in candidates:
        if not cleaned or not needle:
            continue
        score = difflib.SequenceMatcher(None, needle, cleaned).ratio()
        if score > best_score:
            best_key, best_score = key, score
    return best_key, str(translations.get(best_key, "")), best_score


def banner_image(sprites: XrosSpriteSet, entry: int) -> Image.Image:
    # Battle banner entries contain an empty cell followed by two copies of
    # the same label for separate animation states.  OCR only cell 1.
    image = sprites.render(entry, 1).convert("RGBA")
    bounds = image.getchannel("A").getbbox()
    if not bounds:
        return Image.new("RGB", (1, 1), "white")
    image = image.crop(bounds)
    background = Image.new("RGB", image.size, "white")
    background.paste(image.convert("RGB"), mask=image.getchannel("A"))
    return background.resize(
        (background.width * 4, background.height * 4),
        Image.Resampling.NEAREST,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("translation_cache", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--first", type=int, default=2433)
    parser.add_argument("--last", type=int, default=2646)
    args = parser.parse_args()

    translations = json.loads(args.translation_cache.read_text(encoding="utf-8"))
    sprites = XrosSpriteSet.from_rom(args.rom)
    ocr = MangaOcr(force_cpu=True)
    results: list[dict[str, object]] = []
    for entry in range(args.first, args.last + 1):
        raw = ocr(banner_image(sprites, entry))
        key, english, score = best_translation(raw, translations)
        results.append(
            {
                "entry": entry,
                "ocr": raw,
                "matched_japanese": key,
                "english": english,
                "confidence": round(score, 4),
            }
        )
        if (entry - args.first + 1) % 20 == 0:
            print(f"OCR progress: {entry - args.first + 1}/{args.last - args.first + 1}", flush=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    confident = sum(float(item["confidence"]) >= 0.80 for item in results)
    print(f"Cache-matched {confident}/{len(results)} banners at confidence >= 0.80")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
