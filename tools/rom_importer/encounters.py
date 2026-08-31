from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

from .nds import NdsRom


# Dusk stores one 0x200-byte encounter block per area in the ROM image and
# exposes a compact equivalent as dat/ec/eNNN.bin in NitroFS.  These boundaries
# are location transitions in that ordered block list (two blocks = 0x400).
LOCATION_STARTS = {
    0: "Unknown",
    2: "Login Mountain",
    5: "Sunken Tunnel",
    8: "Chip Forest",
    12: "Resistor Jungle",
    16: "Limit Valley",
    20: "Magnet Mine",
    24: "Loop Swamp",
    26: "Palette Amazon",
    29: "Task Canyon",
    33: "Process Factory",
    37: "Access Glacier",
    41: "Macro Sea",
    44: "Proxy Island",
    48: "Highlight Haven",
    52: "Shadow Abyss",
    56: "Chaos Brain",
    59: "Transfield",
    64: "Thriller Ruins",
    68: "Unknown",
}


def _location_for(index: int) -> str:
    start = max(value for value in LOCATION_STARTS if value <= index)
    return LOCATION_STARTS[start]


def _dusk_to_canonical(roster_path: Path) -> dict[int, int]:
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    result: dict[int, int] = {}
    for item in roster:
        canonical = int(item.get("canonical_id", 0))
        for source_id in item.get("source_ids", {}).get("dusk", []):
            result[int(source_id)] = canonical
    return result


def extract_dusk_encounters(
    rom_path: Path, output: Path, roster_path: Path
) -> dict[str, Any]:
    """Export Dusk's per-area encounter pools without copying ROM resources."""
    rom = NdsRom(rom_path)
    files = {item.path.replace("\\", "/"): item for item in rom.files}
    canonical_ids = _dusk_to_canonical(roster_path)
    areas: list[dict[str, Any]] = []

    for index in range(1000):
        source = f"dat/ec/e{index:03d}.bin"
        if source not in files:
            if index > 0:
                break
            continue
        data = rom.read(files[source])
        if len(data) < 16:
            continue
        count, lower_rate, upper_rate = struct.unpack_from("<HHH", data, 0)
        entries = []
        for entry_index in range(min(count, (len(data) - 16) // 24)):
            record = struct.unpack_from("<12H", data, 16 + entry_index * 24)
            source_id = int(record[0])
            canonical_id = canonical_ids.get(source_id, 0)
            if canonical_id <= 0:
                continue
            entries.append(
                {
                    "source_id": source_id,
                    "canonical_id": canonical_id,
                    "weight": int(record[9]),
                    "level": max(1, int(record[10])),
                    "reward_table_id": int(record[11]),
                }
            )
        areas.append(
            {
                "area_index": index,
                "location": _location_for(index),
                "rate_lower": lower_rate,
                "rate_upper": upper_rate,
                "entries": entries,
            }
        )

    payload = {
        "schema_version": 1,
        "source_game": "dusk",
        "source_rom": rom_path.name,
        "notes": (
            "rate_lower/rate_upper and weighted species groups come from the "
            "cartridge encounter blocks; runtime frequency is separately tunable"
        ),
        "areas": areas,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"areas": len(areas), "output": str(output.resolve())}
