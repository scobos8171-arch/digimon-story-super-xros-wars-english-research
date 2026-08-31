#!/usr/bin/env python3
"""Build a compact evidence report for the six Xros command-ring labels.

This is deliberately non-destructive.  It does not edit a ROM or any image.
It answers three separate questions for each label:

* Is the Japanese term present in a decoded message archive?
* Is a matching glyph sequence present in a graphics/font resource?
* Has the live runtime capture proved that this is the label currently drawn
  by the command ring?

Keeping these evidence classes separate prevents another incorrect PNG swap.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "work" / "ui_forensics"
DECOMP = ROOT / "work" / "decomp"

TERMS = {
    "status": ("ステータス", "Status"),
    "orders": ("めいれい", "Orders"),
    "equipment": ("そうび", "Equipment"),
    "formation": ("たいれつ", "Formation"),
    "items": ("もちもの", "Items"),
    "map": ("マップ", "Map"),
    "info": ("じょうほう", "Field Guide"),
}


def rows(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def compact(rows_, limit=40):
    seen = set()
    out = []
    for row in rows_:
        key = tuple(row.get(k, "") for k in ("term", "japanese", "container", "member", "offset", "font_entry"))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def main() -> int:
    clean = rows(UI / "hex_glyph_sequences_clean_font.tsv")
    all_fonts = rows(UI / "xros_ui_glyph_sequences_all_fonts.tsv")
    runtime = rows(UI / "hex_ui_text_sources_v56.tsv")
    scan_lines = (UI / "command_ring_text_scan.txt").read_text(encoding="utf-8", errors="replace") if (UI / "command_ring_text_scan.txt").exists() else ""
    source_report = DECOMP / "xros_hex_source_report.json"
    report_json = json.loads(source_report.read_text(encoding="utf-8")) if source_report.exists() else {}
    message_hits = report_json.get("message_hits", [])

    wanted = set(TERMS)
    result = {
        "generated_by": str(Path(__file__).resolve()),
        "rom_patch_status": "not attempted (source identification only)",
        "notes": [
            "A message/archive hit proves that the word exists somewhere in the ROM; it does not prove that it feeds the ring.",
            "A glyph hit proves a raster/font sequence exists; it may belong to a map, tutorial, or another menu.",
            "A runtime-code hit is stronger, but the six labels were not found as raw Shift-JIS in the captured ring RAM.",
        ],
        "labels": {},
    }

    for key, (jp, en) in TERMS.items():
        glyph = [r for r in clean + all_fonts if r.get("term") in {key, "items_inventory" if key == "items" else key} or r.get("japanese") == jp]
        msg = [r for r in message_hits if r.get("term") == key or r.get("japanese") == jp]
        run = [r for r in runtime if r.get("term") == key or r.get("japanese") == jp]
        scan = jp in scan_lines
        result["labels"][key] = {
            "japanese": jp,
            "english": en,
            "message_archive_hits": len(msg),
            "message_examples": compact(msg),
            "glyph_resource_hits": len(glyph),
            "glyph_examples": compact(glyph),
            "runtime_source_hits": len(run),
            "runtime_source_examples": compact(run),
            "raw_runtime_scan_found": scan,
            "live_ring_label_proven": False,
            "safe_to_patch_now": False,
        }

    # Useful high-level counts for triage.
    result["summary"] = {
        "message_hits_total": len(message_hits),
        "clean_glyph_rows": len(clean),
        "all_font_glyph_rows": len(all_fonts),
        "runtime_source_rows": len(runtime),
        "runtime_scan_has_not_found_lines": scan_lines.count("not found in standard encodings"),
    }
    out = DECOMP / "xros_ring_label_candidates.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    tsv = DECOMP / "xros_ring_label_candidates.tsv"
    with tsv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["term", "japanese", "english", "message_hits", "glyph_hits", "runtime_hits", "raw_runtime_scan_found", "live_ring_label_proven", "safe_to_patch_now"])
        for key, item in result["labels"].items():
            writer.writerow([key, item["japanese"], item["english"], item["message_archive_hits"], item["glyph_resource_hits"], item["runtime_source_hits"], item["raw_runtime_scan_found"], item["live_ring_label_proven"], item["safe_to_patch_now"]])

    print(f"Wrote {out}")
    print(f"Wrote {tsv}")
    for key, item in result["labels"].items():
        print(f"{key:10} msg={item['message_archive_hits']:4} glyph={item['glyph_resource_hits']:4} runtime={item['runtime_source_hits']:3} raw={item['raw_runtime_scan_found']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
