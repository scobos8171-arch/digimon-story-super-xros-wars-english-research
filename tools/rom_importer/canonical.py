from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import get_close_matches
from pathlib import Path

from .profiles import canonical_display_name, normalize_name


API = "https://digi-api.com/api/v1"
ELEMENTS = {
    "thunder": "electricity",
    "electric": "electricity",
    "neutral": "null",
    "none": "null",
}

LEVEL_TO_STAGE = {
    "baby i": "in_training",
    "baby ii": "in_training",
    "in-training i": "in_training",
    "in-training ii": "in_training",
    "child": "rookie",
    "rookie": "rookie",
    "adult": "champion",
    "champion": "champion",
    "perfect": "ultimate",
    "ultimate": "mega",
    "mega": "mega",
    "armor": "armor",
    "hybrid": "hybrid",
}


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "DigitalCrossroads-private-importer/1.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold().replace("grey", "gray"))


def enrich(output: Path, workers: int = 12) -> dict:
    roster_path = output / "roster.json"
    mechanics_path = output / "mechanics.json"
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    mechanics = json.loads(mechanics_path.read_text(encoding="utf-8"))
    listing = _get_json(f"{API}/digimon?pageSize=2000").get("content", [])
    by_name: dict[str, list[dict]] = {}
    for item in listing:
        by_name.setdefault(_key(item.get("name", "")), []).append(item)

    matches: dict[int, dict] = {}
    for item in roster:
        candidates = by_name.get(_key(item.get("display_name", "")), [])
        if len(candidates) == 1:
            matches[int(item["canonical_id"])] = candidates[0]

    cache_dir = output.parent / "cache" / "digi_api"
    cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch(pair: tuple[int, dict]) -> tuple[int, dict | None]:
        canonical_id, item = pair
        cache_path = cache_dir / f"{item['id']}.json"
        try:
            if cache_path.exists():
                return canonical_id, json.loads(cache_path.read_text(encoding="utf-8"))
            detail = _get_json(item["href"])
            cache_path.write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")
            return canonical_id, detail
        except Exception:
            return canonical_id, None

    details: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch, pair) for pair in matches.items()]
        for future in as_completed(futures):
            canonical_id, detail = future.result()
            if detail:
                details[canonical_id] = detail

    for key, skill in mechanics.get("skills", {}).items():
        element = str(skill.get("element", "null")).casefold()
        skill["canonical_element"] = ELEMENTS.get(element, element)
        skill["sp_cost"] = int(skill.get("mp_cost", 0))

    covered = 0
    review = []
    for item in roster:
        canonical_id = int(item["canonical_id"])
        species = mechanics.get("species", {}).get(str(canonical_id), {})
        if not species:
            continue
        detail = details.get(canonical_id)
        if detail:
            attributes = [str(value.get("attribute", "Unknown")) for value in detail.get("attributes", [])]
            levels = [str(value.get("level", "Unknown")) for value in detail.get("levels", [])]
            canonical_skills = [
                {
                    "name": value.get("translation") or value.get("skill", ""),
                    "original_name": value.get("skill", ""),
                    "description": value.get("description", ""),
                }
                for value in detail.get("skills", [])
            ]
            species["canonical_attributes"] = attributes or ["Unknown"]
            species["canonical_attribute"] = (attributes[0] if attributes else "Unknown").casefold()
            species["canonical_levels"] = levels or ["Unknown"]
            canonical_stage = next(
                (LEVEL_TO_STAGE[value.casefold()] for value in levels if value.casefold() in LEVEL_TO_STAGE),
                "xros" if any("xros" in value.casefold() for value in levels) else "unknown",
            )
            species["canonical_stage"] = canonical_stage
            if species.get("provenance") == "compatibility_estimate" and canonical_stage != "unknown":
                species["stage"] = canonical_stage
                species["stage_provenance"] = "canonical_reference"
            species["canonical_reference_skills"] = canonical_skills
            species["canonical_reference_source"] = f"{API}/digimon/{detail.get('id')}"
            covered += 1
        else:
            stage = str(species.get("stage", "unknown"))
            fallback = "variable" if stage == "hybrid" else "free" if stage in {"armor", "xros"} else "unknown"
            species["canonical_attributes"] = [fallback.capitalize()]
            species["canonical_attribute"] = fallback
            species["canonical_levels"] = ["Unknown"]
            species["canonical_stage"] = "unknown"
            species["canonical_reference_skills"] = []
            species["canonical_reference_source"] = "unmatched"
            key = _key(item.get("display_name", ""))
            suggestions = get_close_matches(key, list(by_name), n=3, cutoff=0.62)
            review.append(
                {
                    "canonical_id": canonical_id,
                    "display_name": item.get("display_name", ""),
                    "source_game": item.get("primary_source", ""),
                    "suggestions_only": [by_name[value][0].get("name", "") for value in suggestions],
                    "status": "needs_manual_identity_review",
                }
            )

        # Dusk stores eight elemental affinities per species. The strongest
        # affinity is the safest deterministic element for the new matchup UI;
        # ties and missing tables remain Null rather than being guessed.
        resistances = species.get("resistances", {})
        if isinstance(resistances, dict) and resistances:
            maximum = max(int(value) for value in resistances.values())
            strongest = [name for name, value in resistances.items() if int(value) == maximum]
            element = strongest[0] if len(strongest) == 1 else "null"
            species["canonical_element"] = ELEMENTS.get(element.casefold(), element.casefold())
        else:
            species["canonical_element"] = "null"

    mechanics["canonical_reference"] = {
        "source": "DAPI (official and fan-reference aggregation, mainly Wikimon)",
        "url": "https://digi-api.com/",
        "matched_species": covered,
        "total_species": len(mechanics.get("species", {})),
        "manual_review_species": len(review),
        "policy": "ROM learnsets remain authoritative; reference skills are validation candidates only.",
    }
    groups: dict[str, list[dict]] = {}
    for item in roster:
        if str(item.get("canonical_id")) in mechanics.get("species", {}):
            groups.setdefault(normalize_name(item.get("display_name", "")), []).append(item)
    redirects: dict[str, int] = {}
    duplicate_groups = []
    for normalized, members in groups.items():
        if not normalized or len(members) < 2:
            continue
        members.sort(
            key=lambda item: (
                mechanics["species"][str(item["canonical_id"])].get("provenance") == "rom_verified",
                item.get("source_game") == "dusk",
                -int(item["canonical_id"]),
            ),
            reverse=True,
        )
        primary = members[0]
        primary_id = int(primary["canonical_id"])
        primary["display_name"] = canonical_display_name(primary["display_name"])
        mechanics["species"][str(primary_id)]["display_name"] = primary["display_name"]
        duplicates = []
        for duplicate in members[1:]:
            duplicate_id = int(duplicate["canonical_id"])
            redirects[str(duplicate_id)] = primary_id
            duplicates.append({"canonical_id": duplicate_id, "display_name": duplicate["display_name"]})
        duplicate_groups.append(
            {"primary_id": primary_id, "display_name": primary["display_name"], "redirected": duplicates}
        )
    (output / "canonical_redirects.json").write_text(
        json.dumps({"redirects": redirects, "groups": duplicate_groups}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    mechanics["canonical_reference"]["redirected_aliases"] = len(redirects)
    review_path = output.parent / "qa_reports" / "canonical_attribute_review.json"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    roster_path.write_text(json.dumps(roster, ensure_ascii=False, indent=2), encoding="utf-8")
    mechanics_path.write_text(json.dumps(mechanics, ensure_ascii=False, indent=2), encoding="utf-8")
    return mechanics["canonical_reference"]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path, nargs="?", default=Path("work/extracted"))
    args = parser.parse_args()
    print(json.dumps(enrich(args.output), indent=2))
