from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Any


def gpu_status() -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=True,
        )
        return {"available": True, "devices": [line.strip() for line in completed.stdout.splitlines() if line.strip()]}
    except (OSError, subprocess.CalledProcessError):
        return {"available": False, "devices": []}


def annotate_with_ollama(pseudocode: Path, output: Path, *, model: str) -> dict[str, Any]:
    source = Path(pseudocode).read_text(encoding="utf-8", errors="replace")
    prompt = (
        "You are assisting a clean-room Nintendo DS reverse-engineering project. "
        "Analyze this Ghidra C-like pseudocode. Propose a concise function name, parameter/return types, "
        "likely subsystem, confidence from 0 to 1, and evidence. Do not claim certainty. Return JSON only.\n\n"
        + source[:24000]
    )
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json"}).encode()
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        envelope = json.loads(response.read().decode("utf-8"))
    result = json.loads(envelope["response"])
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
