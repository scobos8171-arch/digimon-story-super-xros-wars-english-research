"""Export verified/probable battle-formula constants from overlay 0."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


OVERLAY_BASE = 0x021F3D20

# Literal-pool addresses and their use are supported by overlay pseudocode.
FLOAT_CONSTANTS = {
    "mixed_attack_class_1_primary": 0x021F4DC0,
    "mixed_attack_class_1_secondary": 0x021F4DC8,
    "mixed_attack_class_2_primary": 0x021F4DCC,
    "mixed_attack_class_2_secondary": 0x021F4DD0,
    "mixed_defense_class_1_primary": 0x021F4EDC,
    "mixed_defense_class_1_secondary": 0x021F4EE0,
    "mixed_defense_class_2_primary": 0x021F4EE4,
    "mixed_defense_class_2_secondary": 0x021F4EE8,
    "component_power_base": 0x021F50C8,
    "component_level_divisor": 0x021F50D4,
    "target_level_divisor": 0x021F5164,
    "attacker_level_divisor": 0x021F52C4,
    "attacker_level_numerator": 0x021F52C8,
    "attacker_level_subtractor": 0x021F52CC,
    "defender_level_divisor": 0x021F52D0,
    "random_step": 0x021F52D8,
    "random_base": 0x021F52DC,
    "damage_upper_clamp": 0x021F52E0,
}

POINTER_CONSTANTS = {
    "combatant_level_base": 0x021F50CC,
    "combatant_record_base": 0x021F50D0,
    "target_level_base": 0x021F5160,
    "target_secondary_stat_base": 0x021F5168,
    "level_factor_base": 0x021F52C0,
}


def read_u32(blob: bytes, address: int) -> int:
    return struct.unpack_from("<I", blob, address - OVERLAY_BASE)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("overlay", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    blob = args.overlay.read_bytes()
    floats = {
        name: {
            "literal_address": f"0x{address:08X}",
            "raw_u32": f"0x{read_u32(blob, address):08X}",
            "value": struct.unpack("<f", struct.pack("<I", read_u32(blob, address)))[0],
        }
        for name, address in FLOAT_CONSTANTS.items()
    }
    pointers = {
        name: {
            "literal_address": f"0x{address:08X}",
            "value": f"0x{read_u32(blob, address):08X}",
        }
        for name, address in POINTER_CONSTANTS.items()
    }
    document = {
        "schema": "xros_battle_static_spec_v1",
        "source_overlay": str(args.overlay),
        "overlay_base": f"0x{OVERLAY_BASE:08X}",
        "functions": {
            "weighted_attacker_stat": "0x021F4D04",
            "weighted_defender_stat": "0x021F4DD4",
            "attacker_contribution": "0x021F4EEC",
            "defender_contribution": "0x021F50D8",
            "base_damage": "0x021F516C",
            "critical_check": "0x021F55D4",
            "critical_apply": "0x021F5718",
            "resistance_apply": "0x021F573C via 0x021F6B50",
            "weakness_apply": "0x021F5734 via 0x021F6B94",
            "conditional_half": "0x021F574C",
        },
        "combatant_layout": {
            "record_base": "0x0221AFD4",
            "record_stride": "0x1A0",
            "primary_attack_f32": "0x60",
            "primary_defense_f32": "0x78",
            "secondary_stat_f32": "0xA8",
            "current_hp_u16": "0xE4",
            "current_sp_u16": "0xEA",
            "level_u8": "0xEF",
            "persistent_status_u8": "0xF1",
        },
        "float_constants": floats,
        "pointer_constants": pointers,
        "verified_modifier_branches": {
            "resistance": {"operation": "divide", "value": 4, "minimum": 1},
            "weakness": {"operation": "multiply", "value": 2, "minimum": 1},
            "conditional_half": {"operation": "divide", "value": 2},
            "random_factor": {
                "expression_probable": "0.99 + 0.01 * randint(0,4)",
                "range_probable": [0.99, 1.03],
                "evidence": "base-damage RNG call uses bound 3000, modulo-five transform, literals 0.01 and 0.99",
            },
        },
        "unresolved_operations": [
            "exact meanings of float helper functions 0x0201E904/0x0201F358/0x0201F538/0x0201F9EC/0x0201F768",
            "precise conversion and rounding points",
            "critical probability and multiplier semantics",
            "Guard branch connection and order",
        ],
        "confidence": "constants/addresses verified; expression labels remain probable until helper semantics are named",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
