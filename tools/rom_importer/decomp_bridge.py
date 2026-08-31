from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


DS_DECOMP_URL = "https://github.com/AetiasHax/ds-decomp"


def extract_decomp_project(rom_path: Path, dsd_path: Path, output: Path) -> dict[str, Any]:
    executable = dsd_path.resolve()
    if not executable.is_file():
        raise FileNotFoundError(f"ds-decomp executable not found: {executable}")
    rom = rom_path.resolve()
    if not rom.is_file():
        raise FileNotFoundError(rom)
    output.mkdir(parents=True, exist_ok=True)
    command = [
        str(executable),
        "rom",
        "extract",
        "--rom",
        str(rom),
        "--output-path",
        str(output.resolve()),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "ds-decomp extraction failed:\n" + (completed.stderr or completed.stdout)
        )
    version = subprocess.run(
        [str(executable), "--version"], capture_output=True, text=True
    )
    files = [path for path in output.rglob("*") if path.is_file()]
    manifest = {
        "schema_version": 1,
        "source_rom": rom.name,
        "source_rom_sha256": hashlib.sha256(rom.read_bytes()).hexdigest(),
        "tool": "ds-decomp",
        "tool_version": (version.stdout or version.stderr).strip(),
        "upstream": DS_DECOMP_URL,
        "purpose": "ARM9, overlay, event, and asset format research for the native Godot implementation",
        "native_runtime": False,
        "file_count": len(files),
        "arm9_overlay_count": len(list((output / "arm9_overlays").glob("*"))) if (output / "arm9_overlays").is_dir() else 0,
    }
    (output / "decomp_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return {**manifest, "output": str(output.resolve())}
