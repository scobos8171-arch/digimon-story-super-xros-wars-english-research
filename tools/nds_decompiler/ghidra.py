from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


def find_analyze_headless(requested: Path | None = None) -> Path:
    candidates: list[Path] = []
    if requested:
        requested = Path(requested)
        candidates.extend([requested, requested / "support" / "analyzeHeadless.bat"])
    if os.environ.get("GHIDRA_HOME"):
        candidates.append(Path(os.environ["GHIDRA_HOME"]) / "support" / "analyzeHeadless.bat")
    downloads = Path.home() / "Downloads"
    candidates.extend(downloads.glob("ghidra_*_PUBLIC/support/analyzeHeadless.bat"))
    candidates.extend(Path("C:/ghidra").glob("ghidra_*_PUBLIC/support/analyzeHeadless.bat"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "Ghidra analyzeHeadless.bat was not found. Install Ghidra, pass --ghidra, or set GHIDRA_HOME."
    )


def analyze_manifest(
    manifest_path: Path,
    *,
    ghidra: Path | None = None,
    programs: set[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    manifest_path = Path(manifest_path).resolve()
    root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    analyze_headless = find_analyze_headless(ghidra)
    script_path = Path(__file__).with_name("ghidra_scripts").resolve()
    project_dir = root / "ghidra_project"
    export_root = root / "pseudocode"
    project_dir.mkdir(parents=True, exist_ok=True)
    export_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    selected = [
        program
        for program in manifest["analysis_programs"]
        if not programs or program["name"] in programs
    ]
    if programs:
        missing = programs - {program["name"] for program in selected}
        if missing:
            raise ValueError("Unknown analysis program(s): " + ", ".join(sorted(missing)))
    for program in selected:
        binary = root / program["file"]
        export_dir = export_root / program["name"]
        export_dir.mkdir(parents=True, exist_ok=True)
        if not force and (export_dir / "pseudocode.c").is_file() and (export_dir / "functions.tsv").is_file():
            results.append({"program": program["name"], "returncode": 0, "skipped": True})
            continue
        command = [
            str(analyze_headless),
            str(project_dir),
            "NintendoDS",
            "-import",
            str(binary),
            "-overwrite",
            "-processor",
            program["language"],
            "-loader",
            "BinaryLoader",
            "-loader-baseAddr",
            f"0x{program['base_address']:08X}",
            "-scriptPath",
            str(script_path),
            "-preScript",
            "MarkNdsEntryPoints.java",
            f"0x{program['entry_address']:08X}",
            f"0x{program['static_init_start']:08X}",
            f"0x{program['static_init_end']:08X}",
            "-postScript",
            "ExportPseudocode.java",
            str(export_dir),
        ]
        completed = subprocess.run(command, text=True, capture_output=True)
        log = export_dir / "ghidra.log"
        log.write_text((completed.stdout or "") + (completed.stderr or ""), encoding="utf-8")
        result = {"program": program["name"], "returncode": completed.returncode, "skipped": False, "log": str(log)}
        results.append(result)
        if completed.returncode:
            raise RuntimeError(f"Ghidra failed for {program['name']}; see {log}")
    summary = {"ghidra": str(analyze_headless), "programs": results}
    (root / "ghidra_analysis.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
