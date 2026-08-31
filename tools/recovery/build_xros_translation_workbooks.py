from __future__ import annotations

import csv
import shutil
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw


PACK = Path(r"C:\Users\YOUR_NAME\pixelforge\xros_ui_localization_pack")
QUEUE = PACK / "localization_queue.csv"
OUT = PACK / "06_ASEPRITE_TRANSLATION_BATCHES"


def main() -> None:
    rows = list(csv.DictReader(QUEUE.open(encoding="utf-8-sig")))
    grouped: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["entry"])].append(row)

    OUT.mkdir(parents=True, exist_ok=True)
    sheets = OUT / "00_CONTACT_SHEETS"
    sheets.mkdir(exist_ok=True)

    for entry, entry_rows in sorted(grouped.items()):
        usable = [r for r in entry_rows if int(r["width"]) > 1 and int(r["height"]) > 1]
        if not usable:
            continue
        batch = OUT / f"entry_{entry:04d}"
        batch.mkdir(exist_ok=True)
        images: list[tuple[dict[str, str], Path, Image.Image]] = []
        for row in usable:
            source = Path(row["source_png"])
            if not source.is_absolute():
                source = PACK / source
            if not source.exists():
                continue
            target = batch / source.name
            shutil.copy2(source, target)
            images.append((row, target, Image.open(target).convert("RGBA")))

        scale = 6
        card_w = 360
        cards = []
        for row, _, im in images:
            preview = im.resize((im.width * scale, im.height * scale), Image.Resampling.NEAREST)
            cards.append((row, preview))
        total_h = sum(max(p.height + 42, 90) for _, p in cards) + 20
        sheet = Image.new("RGB", (card_w, total_h), "#20242c")
        draw = ImageDraw.Draw(sheet)
        y = 10
        for row, preview in cards:
            draw.text((10, y), f"entry {entry} / cell {row['cell']} / {row['width']}x{row['height']}", fill="white")
            y += 22
            sheet.paste(preview, (10, y), preview)
            y += max(preview.height + 20, 68)
        sheet.save(sheets / f"entry_{entry:04d}_contact.png")

        note = batch / "TRANSLATION_NOTES.txt"
        lines = [
            f"SUPER XROS WARS BLUE UI — ENTRY {entry}",
            "",
            "Edit only the copied PNG files in this folder.",
            "Keep the exact canvas size, indexed palette, transparency, and border pixels.",
            "Do not resize, anti-alias, blur, or add colors unless the final injection validator approves them.",
            "",
            "LOCALIZATION:",
        ]
        for row, target, _ in images:
            lines.append(f"- cell {int(row['cell']):02d} | {row['width']}x{row['height']} | {target.name} | TRANSLATION: REVIEW CONTACT SHEET")
        note.write_text("\n".join(lines) + "\n", encoding="utf-8")

    (OUT / "README_FIRST.txt").write_text(
        "SUPER XROS WARS BLUE — REMAINING JAPANESE UI WORK\n\n"
        "Each entry folder contains safe copies of extracted cells and a translation note.\n"
        "00_CONTACT_SHEETS contains 6x nearest-neighbor previews for reading tiny text.\n"
        "The title screen is tracked separately because it is layered full-screen artwork.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
