"""Build a compact offline recovery status report from generated artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--tests-passed", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    output = root / "work/decomp/xros_evolution_us_v3/recovery_status"
    recipes_path = root / "work/extracted/xros_evolution_us_v3/digixros_recipes.json"
    gpu_path = root / "work/decomp/xros_evolution_us_v3/gpu_formula_search_report.json"
    moves_path = root / "work/extracted/xros_evolution_us_v3/moves.json"
    runtime_root = root / "work/decomp/runtime_states"

    recipes = json.loads(recipes_path.read_text(encoding="utf-8")) if recipes_path.exists() else {}
    gpu = json.loads(gpu_path.read_text(encoding="utf-8")) if gpu_path.exists() else {}
    moves = json.loads(moves_path.read_text(encoding="utf-8")) if moves_path.exists() else {}
    state_manifests = sorted(runtime_root.glob("*/manifest.json")) if runtime_root.exists() else []
    component_rows = [component for recipe in recipes.get("recipes", []) for component in recipe.get("components", [])]

    status = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "tests_passed": args.tests_passed,
        "moves_decoded": len(moves.get("records", [])),
        "linked_requirements_decoded": len(recipes.get("recipes", [])),
        "requirement_components_total": len(component_rows),
        "requirement_components_named": sum(row.get("display_name") is not None for row in component_rows),
        "runtime_states_extracted": len(state_manifests),
        "gpu": {
            "device": gpu.get("device"),
            "gpu_name": gpu.get("gpu_name"),
            "candidates_tested": gpu.get("candidates_tested"),
            "exact_fit_found": gpu.get("exact_fit_found"),
            "best_absolute_error": (gpu.get("best") or {}).get("absolute_error"),
        },
        "verified_anchors": [
            "combatant record base 0x0221AFD4, stride 0x1A0",
            "current HP +0xE4; current SP +0xEA; level +0xEF",
            "battle float stats +0x60, +0x78, +0xA8",
            "move table 0x020FC204, 1276 records x 44 bytes",
            "linked requirement table 0x020E092C, 14-byte records",
            "Shoutmon X2 command ID 1205 requires zero-based species 356 and 357",
        ],
        "next_high_value_targets": [
            "exact helper semantics and rounding order in base damage",
            "critical and Guard modifier order",
            "status/targeting opcode catalog",
            "DigiXros result lookup and SP distribution",
            "turn order and AI",
            "XP, rewards, encounters, evolution, and event VM",
        ],
        "artifacts": {},
    }
    for label, path in {
        "moves": moves_path,
        "battle_static_spec": root / "work/extracted/xros_evolution_us_v3/battle_static_spec.json",
        "digixros_requirements": recipes_path,
        "gpu_formula_report": gpu_path,
        "battle_recovery_notes": root / "docs/BATTLE_OVERLAY_RECOVERY.md",
    }.items():
        if path.exists():
            status["artifacts"][label] = {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Offline Recovery Status",
        "",
        f"Generated: `{status['generated_utc']}`",
        "",
        f"- Regression tests: **{'PASS' if status['tests_passed'] else 'FAIL/NOT RUN'}**",
        f"- Moves decoded: **{status['moves_decoded']}**",
        f"- Linked requirements decoded: **{status['linked_requirements_decoded']}**",
        f"- Named components: **{status['requirement_components_named']}/{status['requirement_components_total']}**",
        f"- Runtime states extracted: **{status['runtime_states_extracted']}**",
        f"- GPU: **{status['gpu']['gpu_name'] or 'CPU fallback'}**",
        f"- Formula candidates tested: **{status['gpu']['candidates_tested'] or 0}**",
        f"- Exact fit in current hypothesis family: **{status['gpu']['exact_fit_found']}**",
        "",
        "## Next high-value targets",
        "",
        *[f"- {item}" for item in status["next_high_value_targets"]],
        "",
        "The current GPU family is a falsification tool, not an automatically accepted formula.",
    ]
    output.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output.with_suffix(".md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
