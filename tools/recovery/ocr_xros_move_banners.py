#!/usr/bin/env python3
"""OCR the Japanese move-name sprite bank and match it to the local translation cache.

This helper is read-only.  It renders the move-name cells from SPR_NCGR.PAK,
joins split labels, asks a local Tesseract installation to read the Japanese
text, and fuzzy-matches the result against the translation cache produced by
the message-localization pipeline.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps


ROOT = Path(__file__).resolve().parents[2]
EDITOR = ROOT / "work" / "DigimonNDSRomEditor-master"
sys.path.insert(0, str(EDITOR))

from rom_research.xros_sprite import XrosSpriteSet, parse_ncer  # noqa: E402


JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


def normalize(value: str) -> str:
    value = value.replace("\n", "").replace(" ", "")
    value = value.replace("ｰ", "ー").replace("･", "・")
    return re.sub(r"[^\u3040-\u30ff\u3400-\u9fffA-Za-z0-9]+", "", value)


def joined_entry(sprites: XrosSpriteSet, entry: int) -> Image.Image:
    cells = parse_ncer(sprites.raw_entry("cells", entry))
    rendered = [sprites.render(entry, cell) for cell in range(len(cells))]
    visible: list[Image.Image] = []
    for image in rendered:
        alpha = image.getchannel("A")
        bounds = alpha.getbbox()
        if bounds:
            visible.append(image.crop(bounds))
    if not visible:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    width = sum(image.width for image in visible)
    height = max(image.height for image in visible)
    output = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    x = 0
    for image in visible:
        output.alpha_composite(image, (x, (height - image.height) // 2))
        x += image.width
    return output


def ocr_image(tesseract: Path, tessdata: Path, image: Image.Image) -> str:
    # The title graphics use bright outlined glyphs.  Compositing over black,
    # upscaling without smoothing, and maximizing contrast gives Tesseract a
    # stable baseline without altering the ROM artwork.
    background = Image.new("RGBA", image.size, (0, 0, 0, 255))
    background.alpha_composite(image)
    gray = ImageOps.grayscale(background.convert("RGB"))
    gray = ImageEnhance.Contrast(gray).enhance(2.0)
    gray = gray.resize((gray.width * 8, gray.height * 8), Image.Resampling.NEAREST)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        gray.save(temporary)
        completed = subprocess.run(
            [
                str(tesseract),
                str(temporary),
                "stdout",
                "--tessdata-dir",
                str(tessdata),
                "-l",
                "jpn",
                "--psm",
                "7",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return completed.stdout.strip()
    finally:
        temporary.unlink(missing_ok=True)


def best_translation(ocr: str, translations: dict[str, str]) -> tuple[str, str, float]:
    needle = normalize(ocr)
    candidates = [(key, normalize(key)) for key in translations if JAPANESE.search(key)]
    exact = next((key for key, normalized in candidates if normalized == needle), None)
    if exact is not None:
        return exact, translations[exact], 1.0
    best_key = ""
    best_score = 0.0
    for key, normalized in candidates:
        if not normalized or not needle:
            continue
        score = difflib.SequenceMatcher(None, needle, normalized).ratio()
        if score > best_score:
            best_key, best_score = key, score
    return best_key, translations.get(best_key, ""), best_score


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("translation_cache", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--first", type=int, default=2433)
    parser.add_argument("--last", type=int, default=2646)
    parser.add_argument(
        "--tesseract",
        type=Path,
        default=Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
    )
    parser.add_argument("--tessdata", type=Path, default=ROOT / "work" / "ocr" / "tessdata")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    translations = json.loads(args.translation_cache.read_text(encoding="utf-8"))
    sprites = XrosSpriteSet.from_rom(args.rom)
    images = {entry: joined_entry(sprites, entry) for entry in range(args.first, args.last + 1)}

    def inspect(entry: int) -> dict[str, object]:
        raw = ocr_image(args.tesseract, args.tessdata, images[entry])
        key, english, score = best_translation(raw, translations)
        return {
            "entry": entry,
            "ocr": raw,
            "matched_japanese": key,
            "english": english,
            "confidence": round(score, 4),
        }

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        results = list(executor.map(inspect, range(args.first, args.last + 1)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    confident = sum(float(item["confidence"]) >= 0.8 for item in results)
    print(f"OCR-matched {confident}/{len(results)} move banners at confidence >= 0.80")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
