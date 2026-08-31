"""Inject original English donors into Xros UI sprite entries safely.

Only selected cells in SPR_NCGR.PAK are edited.  Palette, cell, animation,
ARM9, overlays, messages, and every other NitroFS file remain unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


REPO_ROOT = Path(__file__).resolve().parents[2]
ROM_RESEARCH = REPO_ROOT / "work" / "DigimonNDSRomEditor-master"
if str(ROM_RESEARCH) not in sys.path:
    sys.path.insert(0, str(ROM_RESEARCH))

from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.nitrofs_patch import replace_nitrofs_files  # noqa: E402
from rom_research.sprite_retarget import (  # noqa: E402
    _cell_bounds,
    _nearest_palette_index,
    _screen_x,
    _screen_y,
)
from rom_research.xros_pak import (  # noqa: E402
    XrosPak,
    build_xros_pak,
    find_nitro_file,
    read_nitro_file,
)
from rom_research.xros_sprite import parse_ncer, parse_ncgr, parse_nclr  # noqa: E402
from rom_research.xros_english_fonts import read_font_entries  # noqa: E402
from rom_research.xros_compact_english_font import (  # noqa: E402
    character_map,
    decode_cell,
    glyph_format,
    glyph_layout,
)


GRAPHICS_PATH = "SPR_NCGR.PAK"
PALETTE_PATH = "SPR_NCLR.PAK"
CELLS_PATH = "SPR_NCER.PAK"

# mode "text" means the cell is a transparent text-only object.  "frame"
# retains the source UI frame and clears only the supplied text rectangle.
SPECS: dict[int, dict[int, dict[str, object]]] = {
    35: {0: {"text": "DEMO", "mode": "text"}},
    42: {
        0: {"text": "CANCEL", "mode": "frame", "clear": (7, 4, 61, 23), "text_rect": (7, 2, 61, 23)},
        1: {"text": "CANCEL", "mode": "frame", "clear": (7, 4, 61, 23), "text_rect": (7, 2, 61, 23)},
        2: {"text": "FINISH", "mode": "frame", "clear": (7, 4, 61, 23), "text_rect": (7, 2, 61, 23)},
        3: {"text": "FINISH", "mode": "frame", "clear": (7, 4, 61, 23), "text_rect": (7, 2, 61, 23)},
        4: {"text": "RETRY", "mode": "frame", "clear": (7, 4, 61, 23), "text_rect": (7, 2, 61, 23)},
        5: {"text": "RETRY", "mode": "frame", "clear": (7, 4, 61, 23), "text_rect": (7, 2, 61, 23)},
        6: {"text": "CONFIRM", "mode": "frame", "clear": (7, 4, 61, 23), "text_rect": (7, 2, 61, 23)},
        7: {"text": "CONFIRM", "mode": "frame", "clear": (7, 4, 61, 23), "text_rect": (7, 2, 61, 23)},
        8: {"text": "AUTO", "mode": "frame", "clear": (7, 4, 61, 23), "text_rect": (7, 2, 61, 23)},
        9: {"text": "AUTO", "mode": "frame", "clear": (7, 4, 61, 23), "text_rect": (7, 2, 61, 23)},
    },
    47: {
        0: {"text": "WORLD MAP", "mode": "text"},
        1: {"text": "DESTINATION MAP", "mode": "text"},
    },
    86: {0: {"text": "CAMERA", "mode": "frame", "clear": (25, 8, 119, 25)}},
    110: {
        0: {"text": "BACK", "mode": "frame", "clear": (18, 4, 54, 18), "fill_strategy": "row_gradient", "row_reference_x": 8, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (18, 6, 54, 16)},
        1: {"text": "CONFIRM", "mode": "frame", "clear": (18, 4, 54, 18), "fill_strategy": "row_gradient", "row_reference_x": 8, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (18, 6, 54, 16)},
        2: {"text": "NEXT", "mode": "frame", "clear": (18, 4, 54, 18), "fill_strategy": "row_gradient", "row_reference_x": 8, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (18, 6, 54, 16)},
        3: {"text": "FINISH", "mode": "frame", "clear": (18, 4, 54, 18), "fill_strategy": "row_gradient", "row_reference_x": 8, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (18, 6, 54, 16)},
        4: {"text": "FINISH", "mode": "frame", "clear": (18, 4, 54, 18), "fill_strategy": "row_gradient", "row_reference_x": 8, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (18, 6, 54, 16)},
    },
    125: {0: {"text": "SWITCH", "mode": "frame", "clear": (13, 1, 63, 17), "text_rect": (13, 0, 63, 18)}},
    126: {0: {"text": "STATUS", "mode": "frame", "clear": (13, 1, 63, 17), "text_rect": (13, 0, 63, 18)}},
    127: {6: {"text": "DIGIXROS!", "mode": "text"}},
    131: {
        0: {"text": "JOGRESS UP", "mode": "frame", "clear": (14, 8, 94, 25)},
        1: {"text": "JOGRESS UP", "mode": "frame", "clear": (14, 8, 94, 25)},
    },
    132: {
        0: {"text": "SELECT SKILL", "mode": "frame", "clear": (14, 8, 94, 25)},
        1: {"text": "SELECT SKILL", "mode": "frame", "clear": (14, 8, 94, 25)},
    },
    138: {
        0: {"text": "CONGRATS!", "mode": "text"},
        1: {"text": "CONGRATS!", "mode": "text"},
        2: {"text": "CONGRATS!", "mode": "text"},
    },
    141: {0: {"text": "WORK REPORT", "mode": "text"}},
    142: {0: {"text": "EXPEDITION REPORT", "mode": "text"}},
    143: {0: {"text": "LEVEL-UP REPORT", "mode": "text"}},
    147: {
        # These three blue controls were supplied as blank, native-frame
        # canvases.  Restore the complete text well row-by-row first, then
        # use the same unscaled 4x7 face as the English hex labels.
        1: {"text": "CONFIRM", "mode": "frame", "clear": (15, 1, 58, 17), "fill_strategy": "row_gradient", "row_reference_x": 14, "font_style": "hex_4x7", "shadow": True, "outline": False, "text_rect": (15, 4, 58, 14)},
        2: {"text": "BACK", "mode": "frame", "clear": (15, 1, 52, 17), "fill_strategy": "row_gradient", "row_reference_x": 14, "font_style": "hex_4x7", "shadow": True, "outline": False, "text_rect": (15, 4, 52, 14)},
        3: {"text": "BACK", "mode": "frame", "clear": (15, 1, 52, 17), "fill_strategy": "row_gradient", "row_reference_x": 14, "font_style": "hex_4x7", "shadow": True, "outline": False, "text_rect": (15, 4, 52, 14)},
    },
    149: {
        1: {"text": "PREPARING", "mode": "text"},
        2: {"text": "PREPARING", "mode": "text"},
        3: {"text": "PREPARING", "mode": "text"},
        4: {"text": "PREPARING", "mode": "text"},
    },
    194: {0: {"text": "BACK", "mode": "frame", "clear": (13, 1, 51, 17), "text_rect": (13, 0, 51, 18)}},
    196: {
        # Entry 198 contains the game's own clean versions of these seven red
        # command frames.  Use them as donors instead of painting over the
        # Japanese glyphs; this retains every bevel/highlight/diagonal pixel.
        1: {"text": "STATUS", "mode": "frame", "base_entry": 198, "base_cell": 1, "font_style": "compact_3x5", "font_scale": 1, "outline": False, "text_rect": (2, 32, 62, 45)},
        2: {"text": "SKILLS", "mode": "frame", "base_entry": 198, "base_cell": 2, "font_style": "compact_3x5", "font_scale": 1, "outline": False, "text_rect": (2, 32, 62, 45)},
        3: {"text": "EQUIP", "mode": "frame", "base_entry": 198, "base_cell": 3, "font_style": "compact_3x5", "font_scale": 1, "outline": False, "text_rect": (2, 32, 62, 45)},
        4: {"text": "PARTY", "mode": "frame", "base_entry": 198, "base_cell": 4, "font_style": "compact_3x5", "font_scale": 1, "outline": False, "text_rect": (2, 32, 62, 45)},
        5: {"text": "ITEMS", "mode": "frame", "base_entry": 198, "base_cell": 5, "font_style": "compact_3x5", "font_scale": 1, "outline": False, "text_rect": (2, 32, 62, 45)},
        6: {"text": "MAP", "mode": "frame", "base_entry": 198, "base_cell": 6, "font_style": "compact_3x5", "font_scale": 1, "outline": False, "text_rect": (2, 32, 62, 45)},
        7: {"text": "INFO", "mode": "frame", "base_entry": 198, "base_cell": 7, "font_style": "compact_3x5", "font_scale": 1, "outline": False, "text_rect": (2, 32, 62, 45)},
        # BACK has no text-free donor.  Remove only its bright glyph pixels
        # inside the label well while leaving the frame and B icon untouched.
        8: {"text": "BACK", "mode": "frame", "clear": (14, 2, 60, 18), "fill_strategy": "non_light", "font_style": "compact_3x5", "font_scale": 2, "text_rect": (14, 0, 60, 20)},
    },
    198: {
        # Full-RAM/OBJ-VRAM capture of the live Xros Loader menu proved that
        # the game loads entry 198, not the visually identical entry 196.
        # Cells 1-7 reuse one shared tile region. Their Japanese labels are
        # drawn later by the runtime font layer, so painting those cells would
        # make every button show the final label. Only cell 8 is independent
        # baked artwork and is safe to patch here.
        8: {"text": "BACK", "mode": "frame", "clear": (0, 0, 52, 18), "fill_strategy": "solid_rectangle", "icon": "B", "icon_side": "left", "font_style": "ds_5x7", "text_rect": (0, 0, 52, 18), "plate_width": 44, "plate_height": 14, "plate_corner": 1},
    },
    213: {0: {"text": "SWITCH", "mode": "frame", "clear": (13, 1, 63, 17), "text_rect": (13, 0, 63, 18)}},
    220: {0: {"text": "REMOVE", "mode": "frame", "clear": (13, 1, 51, 17), "text_rect": (13, 0, 51, 18)}},
    227: {
        0: {"text": "DEFEATED!", "mode": "text"},
        1: {"text": "JOINED YOU!", "mode": "text"},
    },
    1950: {0: {"text": "SMART DOWN!", "mode": "text"}},
    1964: {0: {"text": "SMART UP!", "mode": "text"}},
    1971: {
        # This archive is also loaded from a fixed physical cartridge slot.
        # Use the compact bitmap face: it stays crisp at native DS size and
        # compresses below the original entry allocation (unlike NFTR glyphs
        # with per-pixel outlines, which overflowed the slot by 182 bytes).
        21: {"text": "ORDERS", "mode": "frame", "clear": (13, 5, 56, 17), "fill_strategy": "alpha_row_gradient", "row_reference_x": 57, "text_rect": (9, 5, 59, 17), "font_style": "compact_3x5", "font_scale_x": 1, "font_scale_y": 2, "outline": False},
        22: {"text": "ORDERS", "mode": "frame", "clear": (13, 5, 60, 17), "fill_strategy": "alpha_row_gradient", "row_reference_x": 61, "text_rect": (9, 5, 63, 17), "font_style": "compact_3x5", "font_scale_x": 1, "font_scale_y": 2, "outline": False},
        23: {"text": "SPECIAL", "mode": "frame", "clear": (13, 5, 56, 17), "fill_strategy": "alpha_row_gradient", "row_reference_x": 57, "text_rect": (9, 5, 59, 17), "font_style": "compact_3x5", "font_scale_x": 1, "font_scale_y": 2, "outline": False},
        24: {"text": "SPECIAL", "mode": "frame", "clear": (13, 5, 60, 17), "fill_strategy": "alpha_row_gradient", "row_reference_x": 61, "text_rect": (9, 5, 63, 17), "font_style": "compact_3x5", "font_scale_x": 1, "font_scale_y": 2, "outline": False},
        25: {"text": "DIGIXROS", "mode": "frame", "clear": (13, 5, 56, 17), "fill_strategy": "alpha_row_gradient", "row_reference_x": 57, "text_rect": (9, 5, 59, 17), "font_style": "compact_3x5", "font_scale_x": 1, "font_scale_y": 2, "outline": False},
        26: {"text": "DIGIXROS", "mode": "frame", "clear": (13, 5, 60, 17), "fill_strategy": "alpha_row_gradient", "row_reference_x": 61, "text_rect": (9, 5, 63, 17), "font_style": "compact_3x5", "font_scale_x": 1, "font_scale_y": 2, "outline": False},
        27: {"text": "ITEMS", "mode": "frame", "clear": (13, 5, 56, 17), "fill_strategy": "alpha_row_gradient", "row_reference_x": 57, "text_rect": (9, 5, 59, 17), "font_style": "compact_3x5", "font_scale_x": 1, "font_scale_y": 2, "outline": False},
        28: {"text": "ITEMS", "mode": "frame", "clear": (13, 5, 60, 17), "fill_strategy": "alpha_row_gradient", "row_reference_x": 61, "text_rect": (9, 5, 63, 17), "font_style": "compact_3x5", "font_scale_x": 1, "font_scale_y": 2, "outline": False},
        29: {"text": "TACTICS", "mode": "frame", "clear": (13, 5, 56, 17), "fill_strategy": "alpha_row_gradient", "row_reference_x": 57, "text_rect": (9, 5, 59, 17), "font_style": "compact_3x5", "font_scale_x": 1, "font_scale_y": 2, "outline": False},
        30: {"text": "TACTICS", "mode": "frame", "clear": (13, 5, 60, 17), "fill_strategy": "alpha_row_gradient", "row_reference_x": 61, "text_rect": (9, 5, 63, 17), "font_style": "compact_3x5", "font_scale_x": 1, "font_scale_y": 2, "outline": False},
        31: {"text": "FORMATION", "mode": "frame", "clear": (13, 5, 56, 17), "fill_strategy": "alpha_row_gradient", "row_reference_x": 57, "text_rect": (9, 5, 59, 17), "font_style": "compact_3x5", "font_scale_x": 1, "font_scale_y": 2, "outline": False},
        32: {"text": "FORMATION", "mode": "frame", "clear": (13, 5, 60, 17), "fill_strategy": "alpha_row_gradient", "row_reference_x": 61, "text_rect": (9, 5, 63, 17), "font_style": "compact_3x5", "font_scale_x": 1, "font_scale_y": 2, "outline": False},
        33: {"text": "WAIT", "mode": "frame", "clear": (13, 5, 56, 17), "fill_strategy": "alpha_row_gradient", "row_reference_x": 57, "text_rect": (9, 5, 59, 17), "font_style": "compact_3x5", "font_scale_x": 1, "font_scale_y": 2, "outline": False},
        34: {"text": "WAIT", "mode": "frame", "clear": (13, 5, 60, 17), "fill_strategy": "alpha_row_gradient", "row_reference_x": 61, "text_rect": (9, 5, 63, 17), "font_style": "compact_3x5", "font_scale_x": 1, "font_scale_y": 2, "outline": False},
    },
    1987: {
        # Preserve the native blue frames and controller icons.  Only erase
        # the old glyph well row-by-row, then draw one consistent compact
        # face.  Rebuilding the whole plate caused the white boxes and color
        # bleed seen in earlier test builds.
        0: {"text": "BACK", "mode": "frame", "clear": (3, 4, 66, 24), "fill_strategy": "row_gradient", "row_reference_x": 5, "font_style": "hex_4x7", "shadow": True, "outline": False, "text_rect": (3, 8, 66, 20)},
        1: {"text": "BATTLE START", "mode": "frame", "clear": (22, 4, 88, 24), "fill_strategy": "row_gradient", "row_reference_x": 88, "font_style": "hex_4x7", "shadow": True, "outline": False, "text_rect": (22, 8, 88, 20)},
        2: {"text": "BACK", "mode": "frame", "clear": (3, 4, 66, 24), "fill_strategy": "row_gradient", "row_reference_x": 5, "font_style": "hex_4x7", "shadow": True, "outline": False, "text_rect": (3, 8, 66, 20)},
        3: {"text": "BATTLE START", "mode": "frame", "clear": (22, 4, 88, 24), "fill_strategy": "row_gradient", "row_reference_x": 88, "font_style": "hex_4x7", "shadow": True, "outline": False, "text_rect": (22, 8, 88, 20)},
        4: {"text": "BACK", "mode": "frame", "clear": (3, 4, 66, 24), "fill_strategy": "row_gradient", "row_reference_x": 5, "font_style": "hex_4x7", "shadow": True, "outline": False, "text_rect": (3, 8, 66, 20)},
        5: {"text": "BATTLE START", "mode": "frame", "clear": (22, 4, 88, 24), "fill_strategy": "row_gradient", "row_reference_x": 88, "font_style": "hex_4x7", "shadow": True, "outline": False, "text_rect": (22, 8, 88, 20)},
        6: {"text": "ALL TACTICS", "mode": "frame", "clear": (4, 4, 67, 24), "fill_strategy": "row_gradient", "row_reference_x": 68, "font_style": "hex_4x7", "shadow": True, "outline": False, "text_rect": (4, 8, 67, 20)},
        7: {"text": "ALL TACTICS", "mode": "frame", "clear": (4, 4, 67, 24), "fill_strategy": "row_gradient", "row_reference_x": 68, "font_style": "hex_4x7", "shadow": True, "outline": False, "text_rect": (4, 8, 67, 20)},
        8: {"text": "ALL TACTICS", "mode": "frame", "clear": (4, 4, 67, 24), "fill_strategy": "row_gradient", "row_reference_x": 68, "font_style": "hex_4x7", "shadow": True, "outline": False, "text_rect": (4, 8, 67, 20)},
        9: {"text": "BACK", "mode": "frame", "clear": (0, 4, 51, 24), "fill_strategy": "row_gradient", "row_reference_x": 52, "font_style": "hex_4x7", "shadow": True, "outline": False, "text_rect": (0, 8, 51, 20)},
        10: {"text": "BACK", "mode": "frame", "clear": (0, 4, 51, 24), "fill_strategy": "row_gradient", "row_reference_x": 52, "font_style": "hex_4x7", "shadow": True, "outline": False, "text_rect": (0, 8, 51, 20)},
        11: {"text": "BACK", "mode": "frame", "clear": (0, 4, 51, 24), "fill_strategy": "row_gradient", "row_reference_x": 52, "font_style": "hex_4x7", "shadow": True, "outline": False, "text_rect": (0, 8, 51, 20)},
    },
    2002: {
        0: {"text": "NEXT", "mode": "frame", "clear": (13, 1, 57, 17), "text_rect": (13, 0, 57, 18)},
        1: {"text": "FINISH", "mode": "frame", "clear": (13, 1, 57, 17), "text_rect": (13, 0, 57, 18)},
        2: {"text": "SKIP", "mode": "frame", "clear": (13, 1, 57, 17), "text_rect": (13, 0, 57, 18)},
    },
    2018: {0: {"text": "SWIFT UP!", "mode": "text"}},
    2020: {0: {"text": "POWER DOWN!", "mode": "text"}},
    2021: {0: {"text": "SMART DOWN!", "mode": "text"}},
    2022: {0: {"text": "SWIFT DOWN!", "mode": "text"}},
    2023: {0: {"text": "DEFENSE DOWN!", "mode": "text"}},
    2024: {0: {"text": "PARALYSIS", "mode": "frame", "clear": (12, 0, 47, 27), "text_rect": (12, 0, 47, 28)}},
    2025: {0: {"text": "SLEEP", "mode": "frame", "clear": (12, 0, 47, 27), "text_rect": (12, 0, 47, 28)}},
    2026: {0: {"text": "CONFUSION", "mode": "frame", "clear": (12, 0, 47, 31), "text_rect": (12, 0, 47, 32)}},
    2027: {0: {"text": "DARKNESS", "mode": "frame", "clear": (12, 0, 47, 31), "text_rect": (12, 0, 47, 32)}},
    2034: {0: {"text": "CURE PARALYSIS", "mode": "text"}},
    2035: {0: {"text": "CURE SLEEP", "mode": "text"}},
    2036: {0: {"text": "CURE CONFUSION", "mode": "text"}},
    2037: {0: {"text": "CURE DARKNESS", "mode": "text"}},
    2043: {0: {"text": "ENERGETIC", "mode": "text"}},
    2044: {0: {"text": "SPOILED", "mode": "text"}},
    2045: {0: {"text": "WILD", "mode": "text"}},
    2046: {0: {"text": "COOL", "mode": "text"}},
    2047: {0: {"text": "SELFISH", "mode": "text"}},
    2048: {0: {"text": "GENTLE", "mode": "text"}},
    2049: {0: {"text": "ROBOT", "mode": "text"}},
    2050: {0: {"text": "FUNKY", "mode": "text"}},
    2060: {0: {"text": "PARALYSIS", "mode": "frame", "clear": (14, 0, 61, 38), "text_rect": (14, 0, 61, 39)}},
    2061: {0: {"text": "SLEEP", "mode": "frame", "clear": (14, 0, 61, 34), "text_rect": (14, 0, 61, 35)}},
    2067: {0: {"text": "CHAOS", "mode": "frame", "clear": (14, 0, 59, 33), "text_rect": (14, 0, 59, 34)}},
    2070: {0: {"text": "CURE PARALYSIS", "mode": "text"}},
    2071: {0: {"text": "CURE SLEEP", "mode": "text"}},
    2072: {0: {"text": "CURE CONFUSION", "mode": "text"}},
    2073: {0: {"text": "CURE DARKNESS", "mode": "text"}},
    2235: {
        0: {"text": "LIVE EVENT REPORT", "mode": "text"},
        1: {"text": "WORK REPORT", "mode": "text"},
        2: {"text": "EXPEDITION REPORT", "mode": "text"},
        3: {"text": "GROWTH REPORT", "mode": "text"},
    },
    2242: {
        0: {"text": "QUEST REWARDS", "mode": "text"},
        1: {"text": "BATTLE CONDITIONS", "mode": "text"},
    },
    2244: {
        0: {"text": "QUEST RATE", "mode": "frame", "clear": (3, 1, 101, 31), "fill_strategy": "row_gradient", "row_reference_x": 104, "font_style": "compact_3x5", "font_scale": 2, "text_rect": (3, 6, 101, 26)},
    },
    2249: {
        0: {"text": "YES", "mode": "frame", "clear": (3, 4, 55, 20), "fill_strategy": "row_gradient", "row_reference_x": 70, "font_style": "compact_3x5", "font_scale": 2, "text_rect": (3, 4, 55, 20)},
        1: {"text": "YES", "mode": "frame", "clear": (3, 4, 55, 20), "fill_strategy": "row_gradient", "row_reference_x": 70, "font_style": "compact_3x5", "font_scale": 2, "text_rect": (3, 4, 55, 20)},
        2: {"text": "NO", "mode": "frame", "clear": (3, 4, 55, 20), "fill_strategy": "row_gradient", "row_reference_x": 70, "font_style": "compact_3x5", "font_scale": 2, "text_rect": (3, 4, 55, 20)},
        3: {"text": "NO", "mode": "frame", "clear": (3, 4, 55, 20), "fill_strategy": "row_gradient", "row_reference_x": 70, "font_style": "compact_3x5", "font_scale": 2, "text_rect": (3, 4, 55, 20)},
    },
    # DigiBit Bank: retain the original pink title band and blue button art.
    # The source labels are baked into the NCGR cells, so each text well is
    # reconstructed row-by-row from a clean part of that same original cell.
    2250: {
        0: {"text": "DIGIBIT BANK", "mode": "frame", "clear": (0, 0, 144, 19), "fill_strategy": "row_gradient", "row_reference_x": 5, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (0, 4, 144, 15)},
        1: {"text": "WITHDRAW", "mode": "frame", "clear": (4, 2, 98, 23), "fill_strategy": "row_gradient", "row_reference_x": 5, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (4, 8, 98, 17)},
        2: {"text": "DEPOSIT", "mode": "frame", "clear": (4, 2, 98, 23), "fill_strategy": "row_gradient", "row_reference_x": 5, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (4, 8, 98, 17)},
        3: {"text": "EXIT ATM", "mode": "frame", "clear": (4, 2, 98, 23), "fill_strategy": "row_gradient", "row_reference_x": 5, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (4, 8, 98, 17)},
    },
}


# Additional Japanese text embedded directly in NCGR sprites.  These entries
# were confirmed from a complete contact-sheet audit of the source ROM.  The
# edits preserve the original cell dimensions, OAM layout, palettes, and UI
# frames; only pixels inside the text areas are replaced.
SPECS.update(
    {
        8: {
            cell: {"text": "LOST EVOLUTION", "mode": "text"}
            for cell in (1, 3, 4, 5)
        },
        36: {
            0: {
                "text": "BLUE FLARE",
                "mode": "frame",
                "clear": (34, 2, 159, 28),
                "text_rect": (34, 1, 159, 29),
            },
            1: {
                "text": "TWILIGHT",
                "mode": "frame",
                "clear": (34, 2, 158, 29),
                "text_rect": (34, 1, 158, 30),
            },
        },
        38: {
            0: {
                "text": "START ADVENTURE",
                "mode": "frame",
                "clear": (3, 1, 159, 17),
                "text_rect": (3, 0, 159, 18),
            },
            1: {
                "mode": "frame",
                "labels": [
                    {"text": "CONTINUE", "clear": (3, 0, 159, 17), "text_rect": (3, 0, 159, 18)},
                    {"text": "START OVER", "clear": (3, 17, 159, 34), "text_rect": (3, 17, 159, 35)},
                    {"text": "RELOAD CHALLENGE", "clear": (3, 34, 159, 51), "text_rect": (3, 34, 159, 52)},
                ],
            },
            2: {
                "mode": "frame",
                "labels": [
                    {"text": "CONTINUE", "clear": (3, 0, 159, 17), "text_rect": (3, 0, 159, 18)},
                    {"text": "START OVER", "clear": (3, 17, 159, 34), "text_rect": (3, 17, 159, 35)},
                    {"text": "RELOAD CHALLENGE", "clear": (3, 34, 159, 51), "text_rect": (3, 34, 159, 52)},
                ],
            },
            3: {
                "mode": "frame",
                "labels": [
                    {"text": "CONTINUE", "clear": (3, 0, 159, 17), "text_rect": (3, 0, 159, 18)},
                    {"text": "START OVER", "clear": (3, 17, 159, 34), "text_rect": (3, 17, 159, 35)},
                    {"text": "RELOAD CHALLENGE", "clear": (3, 34, 159, 51), "text_rect": (3, 34, 159, 52)},
                ],
            },
            4: {
                "text": "CONTINUE",
                "mode": "frame",
                "clear": (3, 1, 159, 17),
                "text_rect": (3, 0, 159, 18),
            },
        },
        39: {
            0: {
                "mode": "text",
                "labels": [
                    {"text": "ORIGINAL: AKIYOSHI HONGO", "text_rect": (0, 0, 182, 12)},
                    {"text": "(C)2011 TOEI / TV ASAHI / NBGI", "text_rect": (0, 12, 182, 24)},
                ],
            }
        },
        40: {
            0: {
                "mode": "text",
                "labels": [
                    {"text": "ORIGINAL: AKIYOSHI HONGO", "text_rect": (0, 0, 182, 12)},
                    {"text": "(C)2011 TOEI / TV ASAHI / NBGI", "text_rect": (0, 12, 182, 24)},
                ],
            }
        },
        84: {
            0: {
                "text": "TRAINING",
                "mode": "frame",
                "clear": (0, 8, 50, 37),
                "text_rect": (0, 6, 50, 39),
            },
            2: {
                "text": "WORK",
                "mode": "frame",
                "clear": (0, 8, 51, 37),
                "text_rect": (0, 6, 51, 39),
            },
        },
        104: {0: {"text": "DIGIFARM", "mode": "text"}},
        124: {
            **{
                cell: {"text": "DIGIXROS", "mode": "frame", "clear": (3, 1, 77, 15), "text_rect": (3, 0, 77, 16)}
                for cell in (16, 20, 21, 22)
            },
            **{
                cell: {"text": "JOGRESS UP", "mode": "frame", "clear": (3, 1, 77, 15), "text_rect": (3, 0, 77, 16)}
                for cell in (17, 23, 24, 25)
            },
            **{
                cell: {"text": "MELODY EVOLVE", "mode": "frame", "clear": (3, 1, 77, 15), "text_rect": (3, 0, 77, 16)}
                for cell in (18, 26, 27, 28)
            },
            **{
                cell: {"text": "DIGIMON LIST", "mode": "frame", "clear": (3, 1, 76, 15), "text_rect": (3, 0, 76, 16)}
                for cell in (19, 29, 30, 31)
            },
        },
        128: {
            cell: {
                "text": "DIGIXROS",
                "mode": "frame",
                "clear": (13, 1, 82, 17),
                "text_rect": (13, 0, 82, 18),
            }
            for cell in range(13, 20)
        },
        140: {0: {"text": "LIVE EVENT REPORT", "mode": "text"}},
        221: {
            **{
                cell: {"text": "PLAYER INFO", "mode": "frame", "clear": (0, 0, 80, 16), "fill_strategy": "solid_rectangle", "font_style": "ds_5x7", "text_rect": (2, 3, 78, 14), "plate_corner": 1}
                for cell in (16, 20, 21, 22)
            },
            **{
                cell: {"text": "QUEST INFO", "mode": "frame", "clear": (0, 0, 80, 16), "fill_strategy": "solid_rectangle", "font_style": "ds_5x7", "text_rect": (2, 3, 78, 14), "plate_corner": 1}
                for cell in (17, 23, 24, 25)
            },
            **{
                cell: {"text": "PARTY DIGIMON", "mode": "frame", "clear": (0, 0, 80, 16), "fill_strategy": "solid_rectangle", "font_style": "ds_5x7", "text_rect": (2, 3, 78, 14), "plate_corner": 1}
                for cell in (18, 26, 27, 28)
            },
            **{
                cell: {"text": "FIELD GUIDE", "mode": "frame", "clear": (0, 0, 80, 16), "fill_strategy": "solid_rectangle", "font_style": "ds_5x7", "text_rect": (2, 3, 78, 14), "plate_corner": 1}
                for cell in (19, 29, 30, 31)
            },
        },
        2028: {0: {"text": "HP DRAIN", "mode": "text"}},
        2029: {0: {"text": "MP DRAIN", "mode": "text"}},
        2030: {0: {"text": "CURSE", "mode": "text"}},
        2031: {0: {"text": "CURSE", "mode": "text"}},
        2032: {0: {"text": "SHUFFLE", "mode": "text"}},
        2068: {0: {"text": "SHUFFLE", "mode": "text"}},
        2218: {
            0: {"text": "BACK", "mode": "frame", "clear": (20, 4, 50, 17), "fill_strategy": "row_gradient", "row_reference_x": 8, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (20, 6, 50, 16)},
            1: {"text": "CONFIRM", "mode": "frame", "clear": (20, 4, 63, 17), "fill_strategy": "row_gradient", "row_reference_x": 8, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (20, 6, 63, 16)},
            2: {"text": "SWITCH", "mode": "frame", "clear": (20, 4, 56, 17), "fill_strategy": "row_gradient", "row_reference_x": 8, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (20, 6, 56, 16)},
            3: {"text": "BACK", "mode": "frame", "clear": (20, 4, 50, 17), "fill_strategy": "row_gradient", "row_reference_x": 8, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (20, 6, 50, 16)},
            4: {"text": "CONFIRM", "mode": "frame", "clear": (20, 4, 63, 17), "fill_strategy": "row_gradient", "row_reference_x": 8, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (20, 6, 63, 16)},
            5: {"text": "SWITCH", "mode": "frame", "clear": (20, 4, 56, 17), "fill_strategy": "row_gradient", "row_reference_x": 8, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (20, 6, 56, 16)},
            6: {"text": "GAINED EXP", "mode": "frame", "clear": (20, 4, 86, 17), "fill_strategy": "row_gradient", "row_reference_x": 8, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (20, 6, 86, 16)},
            7: {"text": "FOUND ITEMS", "mode": "frame", "clear": (20, 4, 102, 17), "fill_strategy": "row_gradient", "row_reference_x": 8, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (20, 6, 102, 16)},
            8: {"text": "NEXT", "mode": "frame", "clear": (20, 4, 50, 17), "fill_strategy": "row_gradient", "row_reference_x": 8, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (20, 6, 50, 16)},
            9: {"text": "FINISH", "mode": "frame", "clear": (20, 4, 50, 17), "fill_strategy": "row_gradient", "row_reference_x": 8, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (20, 6, 50, 16)},
            10: {"text": "TO STATUS", "mode": "frame", "clear": (20, 4, 60, 17), "fill_strategy": "row_gradient", "row_reference_x": 8, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (20, 6, 60, 16)},
            11: {"text": "WORLD MAP", "mode": "frame", "clear": (20, 4, 60, 17), "fill_strategy": "row_gradient", "row_reference_x": 8, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (20, 6, 60, 16)},
            12: {"text": "DIGIMON LIST", "mode": "frame", "clear": (20, 4, 74, 17), "fill_strategy": "row_gradient", "row_reference_x": 8, "font_style": "compact_3x5", "font_scale": 1, "text_rect": (20, 6, 74, 16)},
        },
        2231: {
            14: {"text": "CLOSE", "mode": "frame", "clear": (18, 1, 51, 17), "text_rect": (18, 0, 51, 18)},
            16: {"text": "CONFIRM", "mode": "frame", "clear": (18, 1, 52, 17), "text_rect": (18, 0, 52, 18)},
        },
    }
)


MOVE_BANNER_OCR = REPO_ROOT / "work" / "ocr" / "xros_move_banners_manga.json"

# These labels were legible enough to verify directly from the rendered
# source artwork.  They override weak OCR/cache matches.
MOVE_BANNER_OVERRIDES = {
    2433: "GIGA DESTROYER LEGACY",
    2434: "TOP GUN",
    2435: "STARLIGHT EXPLOSION",
    2437: "FORBIDDEN TEMPTATION",
    2438: "CROSS BLADE",
    2440: "EXTREME JIHAD",
    2441: "NORTHERN CROSS BOMBER",
    2444: "TERRA FORCE",
    2446: "BLITZ HAMMER",
    2447: "GIGA BLASTER",
    2449: "METAL WOLF CLAW",
}


def add_move_banner_specs() -> None:
    """Replace all Japanese move-banner artwork with safe English labels.

    A cache-backed label is accepted only when local OCR confidence is at
    least 0.80.  Anything less certain receives a stable neutral identifier,
    which is preferable to attaching the wrong named move to an animation.
    Both animation-state cells contain the same label and are patched.
    """
    recovered: dict[int, dict[str, object]] = {}
    if MOVE_BANNER_OCR.exists():
        recovered = {
            int(item["entry"]): item
            for item in json.loads(MOVE_BANNER_OCR.read_text(encoding="utf-8"))
        }
    for entry in range(2433, 2647):
        item = recovered.get(entry, {})
        confidence = float(item.get("confidence", 0.0))
        english = str(item.get("english", "")).strip()
        if entry in MOVE_BANNER_OVERRIDES:
            label = MOVE_BANNER_OVERRIDES[entry]
            source = "visually_verified"
        elif confidence >= 0.80 and english:
            label = english
            source = "ocr_translation_cache"
        else:
            label = f"SPECIAL MOVE {entry - 2432:03d}"
            source = "safe_identifier"
        label = " ".join(label.upper().split())
        SPECS[entry] = {
            cell: {"text": label, "mode": "text", "label_source": source}
            for cell in (1, 2)
        }


add_move_banner_specs()

# The original command-ring captions use dark ink on a pale beveled label.
# Keep that palette relationship for every normal/highlighted state.
for _spec in SPECS.get(1971, {}).values():
    _spec["text_tone"] = "dark"
    # Entry 1971 must remain inside its original 7,467-byte compressed slot.
    # A true native 3x5 face is both readable at DS scale and compresses like
    # the source glyph tiles; vertically doubled letters overflow that slot.
    _spec["font_scale_x"] = 1
    _spec["font_scale_y"] = 1
    # This NCER composes the 68x22 label from wrapped OBJ pieces.  Its tile
    # encoder lands edited rows five pixels higher than canvas coordinates.
    # Author the replacement five rows lower so the final ROM render sits in
    # the original caption well and fully covers the Japanese glyphs.
    _clear = tuple(_spec["clear"])
    _text = tuple(_spec["text_rect"])
    _spec["clear"] = (_clear[0], 10, _clear[2], 22)
    # Keep one native pixel of breathing room below the caption in the
    # composed runtime label.  Authoring at y=9..21 lands at y=4..16 after
    # the NCER wrap, instead of touching the lower bevel at y=17.
    _spec["text_rect"] = (_text[0], 9, _text[2], 21)

# Compact framed buttons reserve their left edge for a controller/icon glyph.
# Their original Japanese labels occupy nearly the complete remaining height,
# so clear that full interior rather than leaving lower glyph fragments.
for _entry in (
    36, 38, 42, 110, 125, 126, 131, 132, 147, 194, 198, 213, 220,
    1971, 1987, 2002, 2231, 2249,
):
    for _spec in SPECS.get(_entry, {}).values():
        if _spec.get("mode") == "frame" and "clear" in _spec:
            # Entry 1971's command-ring labels are tiny shaped OBJ cells.
            # Expanding their clear rectangle destroys transparent corners
            # and creates the large opaque plate seen in game.
            if _entry not in (
                42, 110, 125, 126, 128, 147, 194, 1971, 1987, 2002, 213, 220,
            ):
                _spec["full_label_height"] = True


def load_font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        Path("C:/Windows/Fonts/consolab.ttf"),
        Path("C:/Windows/Fonts/lucon.ttf"),
        Path("C:/Windows/Fonts/consola.ttf"),
    ):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


class NftrPixelFont:
    # Bank 7 is the bold, all-caps English UI face from Lost Evolution.  It
    # remains readable at DS resolution and matches the existing Xros labels.
    def __init__(self, rom: Path, bank: int = 7):
        self.data = read_font_entries(rom)[bank]
        self.mapping = character_map(self.data)
        self.cells, self.cell_size, self.widths, self.first, self.last = glyph_layout(self.data)
        self.cell_width, self.cell_height, self.bpp = glyph_format(self.data)

    def render(self, text: str) -> Image.Image:
        glyphs: list[tuple[Image.Image, int]] = []
        for character in text:
            if character == " ":
                glyphs.append((Image.new("1", (1, self.cell_height), 0), 4))
                continue
            glyph = self.mapping.get(ord(character), self.mapping.get(ord("?")))
            if glyph is None or not self.first <= glyph <= self.last:
                continue
            offset = self.cells + glyph * self.cell_size
            cell = decode_cell(
                self.data[offset:offset + self.cell_size],
                self.cell_width,
                self.cell_height,
                self.bpp,
            )
            width_offset = self.widths + 3 * (glyph - self.first)
            left, glyph_width, advance = self.data[width_offset:width_offset + 3]
            # decode_cell returns black ink on white.  Convert it into a 1-bit mask.
            mask = cell.point(lambda value: 1 if value < 128 else 0, mode="1")
            glyphs.append((mask, max(1, advance, left + glyph_width)))
        total_width = max(1, sum(advance for _mask, advance in glyphs))
        output = Image.new("1", (total_width, self.cell_height), 0)
        cursor = 0
        for mask, advance in glyphs:
            output.paste(mask, (cursor, 0), mask)
            cursor += advance
        return output


def make_mask(
    text: str,
    size: tuple[int, int],
    pixel_font: NftrPixelFont | None = None,
) -> Image.Image:
    width, height = size
    if pixel_font is not None:
        rendered = pixel_font.render(text)
        maximum_width = max(1, width - 8)
        maximum_height = max(1, height - 4)
        scale = min(1.0, maximum_width / rendered.width, maximum_height / rendered.height)
        if scale < 1.0:
            rendered = rendered.resize(
                (max(1, round(rendered.width * scale)), max(1, round(rendered.height * scale))),
                Image.Resampling.NEAREST,
            )
        mask = Image.new("1", size, 0)
        mask.paste(rendered, ((width - rendered.width) // 2, (height - rendered.height) // 2))
        return mask
    for font_size in range(max(5, height - 4), 4, -1):
        font = load_font(font_size)
        mask = Image.new("1", size, 0)
        draw = ImageDraw.Draw(mask)
        box = draw.textbbox((0, 0), text, font=font)
        text_width = box[2] - box[0]
        text_height = box[3] - box[1]
        if text_width <= max(1, width - 8) and text_height <= max(1, height - 4):
            draw.text(
                ((width - text_width) // 2 - box[0], (height - text_height) // 2 - box[1]),
                text,
                font=font,
                fill=1,
            )
            return mask
    mask = Image.new("1", size, 0)
    ImageDraw.Draw(mask).text((2, 2), text, font=ImageFont.load_default(), fill=1)
    return mask


# A deliberately small hand-pixelled alphabet for the 60-pixel command
# buttons.  Scaling these 3x5 forms by exactly 2 keeps every edge on the DS
# pixel grid; there is no anti-aliasing or resampling blur.
COMPACT_3X5 = {
    "A": ("010", "101", "111", "101", "101"),
    "B": ("110", "101", "110", "101", "110"),
    "C": ("011", "100", "100", "100", "011"),
    "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"),
    "F": ("111", "100", "110", "100", "100"),
    "G": ("011", "100", "101", "101", "011"),
    "H": ("101", "101", "111", "101", "101"),
    "I": ("111", "010", "010", "010", "111"),
    "K": ("101", "101", "110", "101", "101"),
    "L": ("100", "100", "100", "100", "111"),
    "M": ("101", "111", "111", "101", "101"),
    "N": ("101", "111", "111", "111", "101"),
    "O": ("010", "101", "101", "101", "010"),
    "P": ("110", "101", "110", "100", "100"),
    "Q": ("010", "101", "101", "111", "011"),
    "R": ("110", "101", "110", "101", "101"),
    "S": ("011", "100", "010", "001", "110"),
    "T": ("111", "010", "010", "010", "010"),
    "U": ("101", "101", "101", "101", "111"),
    "V": ("101", "101", "101", "101", "010"),
    "W": ("101", "101", "111", "111", "101"),
    "X": ("101", "101", "010", "101", "101"),
    "Y": ("101", "101", "010", "010", "010"),
    "Z": ("111", "001", "010", "100", "111"),
    " ": ("000", "000", "000", "000", "000"),
}

# The same narrow 4x7 face used by the successful English hex captions.
# It has variable-width letters and therefore fits the native battle-button
# text wells without stretching or using a proportional system font.
HEX_4X7 = {
    "A": ("0110", "1001", "1001", "1111", "1001", "1001", "1001"),
    "B": ("1110", "1001", "1001", "1110", "1001", "1001", "1110"),
    "C": ("0111", "1000", "1000", "1000", "1000", "1000", "0111"),
    "E": ("1111", "1000", "1000", "1110", "1000", "1000", "1111"),
    "H": ("1001", "1001", "1001", "1111", "1001", "1001", "1001"),
    "I": ("111", "010", "010", "010", "010", "010", "111"),
    "K": ("1001", "1010", "1100", "1000", "1100", "1010", "1001"),
    "L": ("1000", "1000", "1000", "1000", "1000", "1000", "1111"),
    "R": ("1110", "1001", "1001", "1110", "1010", "1001", "1001"),
    "S": ("0111", "1000", "1000", "0110", "0001", "0001", "1110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    " ": ("0", "0", "0", "0", "0", "0", "0"),
}


def make_hex_4x7_mask(text: str, size: tuple[int, int]) -> Image.Image:
    """Return a centered mask using the native hex-caption 4x7 glyphs."""
    text = text.upper()
    glyphs = [HEX_4X7.get(character, HEX_4X7[" "]) for character in text]
    width = sum(len(glyph[0]) for glyph in glyphs) + max(0, len(glyphs) - 1)
    mask = Image.new("1", size, 0)
    x = max(0, (size[0] - width) // 2)
    y = max(0, (size[1] - 7) // 2)
    pixels = mask.load()
    for glyph in glyphs:
        for gy, row in enumerate(glyph):
            for gx, value in enumerate(row):
                if value == "1" and x + gx < size[0] and y + gy < size[1]:
                    pixels[x + gx, y + gy] = 1
        x += len(glyph[0]) + 1
    return mask


# Native-looking DS UI face: 5x7 with a 1px outline.  This matches the
# original Japanese labels better than doubled 3x5 blocks.
DS_5X7 = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01110"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("111", "010", "010", "010", "010", "010", "111"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    " ": ("00", "00", "00", "00", "00", "00", "00"),
}
DS_5X7_CONDENSED = {
    "A": ("0110", "1001", "1001", "1111", "1001", "1001", "1001"),
    "B": ("1110", "1001", "1001", "1110", "1001", "1001", "1110"),
    "C": ("0111", "1000", "1000", "1000", "1000", "1000", "0111"),
    "D": ("1110", "1001", "1001", "1001", "1001", "1001", "1110"),
    "E": ("1111", "1000", "1000", "1110", "1000", "1000", "1111"),
    "G": ("0110", "1001", "1000", "1011", "1001", "1001", "0110"),
    "I": ("111", "010", "010", "010", "010", "010", "111"),
    "L": ("1000", "1000", "1000", "1000", "1000", "1000", "1111"),
    "M": ("1001", "1111", "1111", "1001", "1001", "1001", "1001"),
    "N": ("1001", "1101", "1101", "1011", "1011", "1001", "1001"),
    "O": ("0110", "1001", "1001", "1001", "1001", "1001", "0110"),
    "P": ("1110", "1001", "1001", "1110", "1000", "1000", "1000"),
    "R": ("1110", "1001", "1001", "1110", "1010", "1001", "1001"),
    "T": ("1111", "0100", "0100", "0100", "0100", "0100", "0100"),
    "Y": ("1001", "1001", "0110", "0110", "0100", "0100", "0100"),
}


def _trim_glyph(rows: tuple[str, ...]) -> list[str]:
    used = [x for x in range(len(rows[0])) if any(row[x] == "1" for row in rows)]
    if not used:
        return list(rows)
    return [row[min(used) : max(used) + 1] for row in rows]


def _ds_5x7_width(text: str, condensed: bool) -> int:
    width = 0
    for index, character in enumerate(text.upper()):
        font = DS_5X7_CONDENSED if condensed and character in DS_5X7_CONDENSED else DS_5X7
        glyph = _trim_glyph(font.get(character, DS_5X7[" "]))
        width += len(glyph[0])
        if index:
            width += 1
    return width


def _mix_rgba(color: tuple[int, int, int, int], target: tuple[int, int, int], amount: float) -> tuple[int, int, int, int]:
    return (
        max(0, min(255, int(color[0] + (target[0] - color[0]) * amount))),
        max(0, min(255, int(color[1] + (target[1] - color[1]) * amount))),
        max(0, min(255, int(color[2] + (target[2] - color[2]) * amount))),
        255,
    )


def _snap_rgba(color: tuple[int, int, int, int], palette) -> tuple[int, int, int, int]:
    snapped = palette[_nearest_palette_index(color, tuple(palette))]
    if snapped[3] == 0:
        return (color[0], color[1], color[2], 255)
    return snapped


def _plate_box(width: int, height: int, spec: dict[str, object]) -> tuple[int, int, int, int]:
    if "plate_width" in spec:
        plate_width = int(spec["plate_width"])
    else:
        plate_width = max(16, int(round(width * float(spec.get("plate_width_scale", 1.0)))))
    if "plate_height" in spec:
        plate_height = int(spec["plate_height"])
    else:
        plate_height = height
    plate_width = min(width, max(12, plate_width))
    plate_height = min(height, max(8, plate_height))
    left = (width - plate_width) // 2
    top = (height - plate_height) // 2
    return left, top, left + plate_width, top + plate_height


def _draw_gloss_plate(
    image: Image.Image,
    box: tuple[int, int, int, int],
    fill: tuple[int, int, int, int],
    border: tuple[int, int, int, int],
    palette,
    corner: int,
) -> None:
    left, top, right, bottom = box
    pixels = image.load()
    fill = _snap_rgba(fill, palette)
    border = _snap_rgba(border, palette)
    highlight = _snap_rgba(_mix_rgba(fill, (255, 255, 255), 0.45), palette)
    sheen = _snap_rgba(_mix_rgba(fill, (255, 255, 255), 0.22), palette)
    shade = _snap_rgba(_mix_rgba(fill, (0, 0, 0), 0.18), palette)
    deep = _snap_rgba(_mix_rgba(fill, (0, 0, 0), 0.36), palette)
    plate_height = bottom - top
    for y in range(top, bottom):
        for x in range(left, right):
            dx = min(x - left, right - 1 - x)
            dy = min(y - top, bottom - 1 - y)
            if corner and dx + dy < corner:
                continue
            if dx == 0 or dy == 0 or (corner and dx + dy == corner):
                pixels[x, y] = border
            elif y == top + 1:
                pixels[x, y] = highlight
            elif y == top + 2 and plate_height >= 14:
                pixels[x, y] = sheen
            elif y >= bottom - 2:
                pixels[x, y] = deep
            elif y >= bottom - 3 and plate_height >= 14:
                pixels[x, y] = shade
            else:
                pixels[x, y] = fill


# Hard 12x12 / 16x16 face-button circles.  O outline, H highlight, F fill, S shade.
CIRCLE_12 = (
    "....OOOO....",
    "..OOHHHFOO..",
    ".OHHHHFFFFO.",
    ".OHHHFFFFFO.",
    "OHHHFFFFFFFO",
    "OHHFFFFFFFSO",
    "OHFFFFFFFSSO",
    "OFFFFFFFSSSO",
    ".OFFFFFSSSO.",
    ".OFFFFSSSSO.",
    "..OOFSSSOO..",
    "....OOOO....",
)
CIRCLE_16 = (
    ".....OOOOOO.....",
    "...OOHHHHFFOO...",
    "..OHHHHHFFFFFO..",
    ".OHHHHHFFFFFFFO.",
    ".OHHHHFFFFFFFFO.",
    "OHHHHFFFFFFFFFFO",
    "OHHHFFFFFFFFFFFO",
    "OHHFFFFFFFFFFFSO",
    "OHFFFFFFFFFFFSSO",
    "OFFFFFFFFFFFSSSO",
    "OFFFFFFFFFFSSSSO",
    ".OFFFFFFFFSSSSO.",
    ".OFFFFFFFSSSSSO.",
    "..OFFFFFSSSSSO..",
    "...OOFFSSSSOO...",
    ".....OOOOOO.....",
)


def _draw_simple_icon(
    image: Image.Image,
    letter: str,
    side: str,
    border: tuple[int, int, int, int],
    bounds: tuple[int, int, int, int] | None = None,
    palette=None,
) -> None:
    box_left, box_top, box_right, box_bottom = bounds or (0, 0, image.width, image.height)
    plate_height = box_bottom - box_top
    mask = CIRCLE_16 if plate_height >= 20 else CIRCLE_12
    size = len(mask)
    top = box_top + (plate_height - size) // 2
    left = box_left + 2 if side == "left" else box_right - size - 2
    raw = {
        "B": ((72, 168, 232, 255), (32, 88, 168, 255), (168, 220, 255, 255)),
        "X": ((216, 56, 64, 255), (152, 24, 32, 255), (255, 168, 176, 255)),
        "Y": ((56, 184, 80, 255), (24, 112, 40, 255), (168, 236, 176, 255)),
        "A": ((72, 168, 232, 255), (32, 88, 168, 255), (168, 220, 255, 255)),
    }.get(letter, ((72, 168, 232, 255), (32, 88, 168, 255), (168, 220, 255, 255)))
    if palette is not None:
        fill = _snap_rgba(raw[0], palette)
        shade = _snap_rgba(raw[1], palette)
        light = _snap_rgba(raw[2], palette)
        outline = _snap_rgba(border, palette)
        ink = _snap_rgba((255, 255, 255, 255), palette)
        ink_edge = _snap_rgba((24, 24, 24, 255), palette)
    else:
        fill, shade, light = raw
        outline, ink, ink_edge = border, (255, 255, 255, 255), (24, 24, 24, 255)
    pixels = image.load()
    roles = {"O": outline, "H": light, "F": fill, "S": shade}
    inside: set[tuple[int, int]] = set()
    for row, pattern in enumerate(mask):
        for column, code in enumerate(pattern):
            if code == ".":
                continue
            x, y = left + column, top + row
            if 0 <= x < image.width and 0 <= y < image.height:
                pixels[x, y] = roles[code]
                if code != "O":
                    inside.add((x, y))
    glyph_box = (7, 7) if size >= 16 else (5, 5)
    glyph = (
        make_ds_5x7_mask(letter, glyph_box)
        if size >= 16
        else make_compact_3x5_mask(letter, glyph_box, scale=1)
    )
    gx = left + (size - glyph_box[0]) // 2
    gy = top + (size - glyph_box[1]) // 2
    marks = glyph.load()
    letter_px: set[tuple[int, int]] = set()
    for row in range(glyph_box[1]):
        for column in range(glyph_box[0]):
            if marks[column, row]:
                letter_px.add((gx + column, gy + row))
    for x, y in letter_px:
        for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = x + ox, y + oy
            if (nx, ny) in inside and (nx, ny) not in letter_px:
                pixels[nx, ny] = ink_edge
    for x, y in letter_px:
        if 0 <= x < image.width and 0 <= y < image.height:
            pixels[x, y] = ink


def make_ds_5x7_mask(text: str, size: tuple[int, int]) -> Image.Image:
    text = text.upper()
    condensed = _ds_5x7_width(text, False) + 2 > size[0]
    output = Image.new("1", size, 0)
    pixels = output.load()
    total = _ds_5x7_width(text, condensed)
    cursor = max(0, (size[0] - total) // 2)
    top = max(0, (size[1] - 7) // 2)
    for character in text:
        font = DS_5X7_CONDENSED if condensed and character in DS_5X7_CONDENSED else DS_5X7
        glyph = _trim_glyph(font.get(character, DS_5X7[" "]))
        for row, pattern in enumerate(glyph):
            for column, bit in enumerate(pattern):
                x, y = cursor + column, top + row
                if bit == "1" and 0 <= x < size[0] and 0 <= y < size[1]:
                    pixels[x, y] = 1
        cursor += len(glyph[0]) + 1
    return output


def make_compact_3x5_mask(
    text: str,
    size: tuple[int, int],
    scale: int = 2,
    scale_x: int | None = None,
    scale_y: int | None = None,
) -> Image.Image:
    text = text.upper()
    scale_x = max(1, scale if scale_x is None else scale_x)
    scale_y = max(1, scale if scale_y is None else scale_y)
    glyph_width = 3 * scale_x
    gap = scale_x
    total_width = max(1, len(text) * glyph_width + max(0, len(text) - 1) * gap)
    total_height = 5 * scale_y
    output = Image.new("1", size, 0)
    start_x = max(0, (size[0] - total_width) // 2)
    start_y = max(0, (size[1] - total_height) // 2)
    draw = ImageDraw.Draw(output)
    cursor = start_x
    for character in text:
        rows = COMPACT_3X5.get(character, COMPACT_3X5[" "])
        for row, pattern in enumerate(rows):
            for column, bit in enumerate(pattern):
                if bit == "1":
                    left = cursor + column * scale_x
                    top = start_y + row * scale_y
                    draw.rectangle((left, top, left + scale_x - 1, top + scale_y - 1), fill=1)
        cursor += glyph_width + gap
    return output


def render_full_cell(graphics, palette, cell) -> Image.Image:
    left, top, right, bottom = _cell_bounds(cell)
    width = max(1, right - left)
    height = max(1, bottom - top)
    output = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = output.load()
    bytes_per_tile = 0x20 if graphics.bpp == 4 else 0x40
    tiles_per_character = graphics.mapping_unit_bytes // bytes_per_tile
    for oam in cell.oams:
        oam_width, oam_height = oam.dimensions
        tile_index = oam.character * tiles_per_character + cell.partition_offset // bytes_per_tile
        flip_x = not oam.affine and bool(oam.affine_flags & 0x08)
        flip_y = not oam.affine and bool(oam.affine_flags & 0x10)
        for tile_y in range(0, oam_height, 8):
            for tile_x in range(0, oam_width, 8):
                if tile_index >= len(graphics.tiles):
                    tile_index += 1
                    continue
                tile = graphics.tiles[tile_index]
                bank_offset = oam.palette * 16 if graphics.bpp == 4 and len(palette) > 16 else 0
                for py in range(8):
                    for px in range(8):
                        index = tile[py * 8 + px]
                        if not index:
                            continue
                        local_x = tile_x + px
                        local_y = tile_y + py
                        display_x = oam_width - 1 - local_x if flip_x else local_x
                        display_y = oam_height - 1 - local_y if flip_y else local_y
                        x = _screen_x(oam) - left + display_x
                        y = _screen_y(oam) - top + display_y
                        palette_index = bank_offset + index
                        if 0 <= x < width and 0 <= y < height and palette_index < len(palette):
                            pixels[x, y] = palette[palette_index]
                tile_index += 1
    return output


def dominant_fill(
    image: Image.Image,
    rectangle: tuple[int, int, int, int],
    strategy: str = "default",
):
    colors = Counter(
        pixel
        for pixel in image.crop(rectangle).getdata()
        if pixel[3] and (strategy != "non_light" or sum(pixel[:3]) < 620)
    )
    return colors.most_common(1)[0][0] if colors else (0, 0, 0, 0)


def edit_canvas(
    source: Image.Image,
    spec: dict[str, object],
    palette,
    pixel_font: NftrPixelFont | None,
) -> Image.Image:
    mode = str(spec["mode"])
    result = source.copy() if mode == "frame" else Image.new("RGBA", source.size, (0, 0, 0, 0))
    opaque = [color for color in palette if color[3]]
    dark = min(opaque, key=lambda color: sum(color[:3])) if opaque else (0, 0, 0, 255)
    light = max(opaque, key=lambda color: sum(color[:3])) if opaque else (255, 255, 255, 255)

    labels = spec.get("labels")
    if labels is None:
        labels = [spec]
    # A multi-line label shares one source-language text region.  Clear that
    # well once before drawing any English line; clearing it per line would
    # erase the first line while placing the second.
    pending_clear: dict[str, object] | None = None
    plate_box: tuple[int, int, int, int] | None = None
    if mode == "frame" and "clear" in spec:
        pending_clear = spec
    for raw_label in labels:
        label = dict(raw_label)
        clear_source: dict[str, object] | None = None
        if pending_clear is not None:
            clear_source = pending_clear
            pending_clear = None
        elif mode == "frame" and "clear" in label:
            clear_source = label
        if clear_source is not None:
            rectangle = tuple(int(value) for value in clear_source["clear"])
            strategy = str(clear_source.get("fill_strategy", spec.get("fill_strategy", "default")))
            if strategy == "glyphs":
                # Preserve a shaded/outlined frame by removing only the
                # bright Japanese glyph cores and their one-pixel dark edge.
                # Unlike a rectangular fill, this leaves every bevel,
                # highlight, icon, and non-text background pixel intact.
                fill = dominant_fill(result, rectangle, "non_light")
                glyphs = Image.new("1", result.size, 0)
                glyph_pixels = glyphs.load()
                source_pixels = result.load()
                left, top, right, bottom = rectangle
                for y in range(max(0, top), min(result.height, bottom)):
                    for x in range(max(0, left), min(result.width, right)):
                        red, green, blue, alpha = source_pixels[x, y]
                        if alpha and min(red, green, blue) >= 170 and max(red, green, blue) - min(red, green, blue) <= 75:
                            glyph_pixels[x, y] = 1
                glyphs = glyphs.filter(ImageFilter.MaxFilter(3))
                result.paste(fill, (0, 0), glyphs)
                rectangle = None
            elif strategy == "row_gradient":
                # These buttons have a deliberate vertical colour ramp.  A
                # flat fill makes the new label look pasted on, so take one
                # verified background pixel from each source row and extend
                # it only through the old text well.  The caller picks a
                # reference column outside icons, borders, and glyphs.
                left, top, right, bottom = rectangle
                reference_x = int(clear_source["row_reference_x"])
                pixels = result.load()
                for y in range(max(0, top), min(result.height, bottom)):
                    fill = pixels[max(0, min(result.width - 1, reference_x)), y]
                    for x in range(max(0, left), min(result.width, right)):
                        pixels[x, y] = fill
                rectangle = None
            elif strategy == "alpha_row_gradient":
                # Repaint only pixels that were already opaque.  This is for
                # small shaped OBJ labels: transparent corners and arrow
                # cut-outs must remain transparent or the game displays a
                # conspicuous rectangular plate around the command name.
                left, top, right, bottom = rectangle
                reference_x = int(clear_source["row_reference_x"])
                pixels = result.load()
                for y in range(max(0, top), min(result.height, bottom)):
                    fill = pixels[max(0, min(result.width - 1, reference_x)), y]
                    for x in range(max(0, left), min(result.width, right)):
                        if pixels[x, y][3]:
                            pixels[x, y] = fill
                rectangle = None
            elif strategy == "panel_row_gradient":
                # Result buttons have a white centre panel over a coloured
                # lower band.  Copying a pixel from the outer frame makes a
                # fake solid box, so sample the clean far-right part of the
                # centre panel for the upper rows and retain the source band
                # colour below it.
                left, top, right, bottom = rectangle
                reference_x = int(clear_source["row_reference_x"])
                pixels = result.load()
                for y in range(max(0, top), min(result.height, bottom)):
                    if y < 18:
                        fill = pixels[max(0, min(result.width - 1, reference_x)), y]
                    else:
                        fill = pixels[max(0, min(result.width - 1, 8)), y]
                    for x in range(max(0, left), min(result.width, right)):
                        pixels[x, y] = fill
                rectangle = None
            elif strategy == "glyph_erase_gradient":
                # Preserve a coloured result-button face while replacing its
                # Japanese label.  The face is made of horizontal colour
                # bands; the original glyphs are neutral white/grey/black.
                # For each row, recover the dominant *coloured* face pixel,
                # then replace only neutral glyph pixels inside the text well.
                # This deliberately never paints a rectangular white plate.
                left, top, right, bottom = rectangle
                pixels = result.load()
                for y in range(max(0, top), min(result.height, bottom)):
                    row_colours = Counter()
                    for x in range(max(0, left), min(result.width, right)):
                        red, green, blue, alpha = pixels[x, y]
                        if alpha and max(red, green, blue) - min(red, green, blue) >= 24:
                            row_colours[(red, green, blue, alpha)] += 1
                    if not row_colours:
                        continue
                    fill = row_colours.most_common(1)[0][0]
                    for x in range(max(0, left), min(result.width, right)):
                        red, green, blue, alpha = pixels[x, y]
                        if alpha and max(red, green, blue) - min(red, green, blue) <= 52:
                            pixels[x, y] = fill
                rectangle = None
            elif strategy == "orange_button":
                # The service-menu buttons repeat the same orange/black
                # stripe at every width.  Recreate its row band from a clean
                # far-left sample, then keep the beveled endcaps outside the
                # clear rectangle intact.  It is deliberately separate from
                # blue `row_gradient`: this panel has a dark centre stripe.
                left, top, right, bottom = rectangle
                pixels = result.load()
                for y in range(max(0, top), min(result.height, bottom)):
                    fill = pixels[6, y]
                    for x in range(max(0, left), min(result.width, right)):
                        pixels[x, y] = fill
                rectangle = None
            elif strategy == "solid_rectangle":
                # Same native canvas and 4bpp palette.  The visible plate is
                # inset so it reads thinner, with a 1px gloss band snapped to
                # indexed colours.  Transparent margins stay index 0.
                sample = source.load()
                blues, oranges, darks = Counter(), Counter(), Counter()
                for y in range(source.height):
                    for x in range(source.width):
                        red, green, blue, alpha = sample[x, y]
                        if alpha < 200:
                            continue
                        if red < 40 and green < 40 and blue < 40:
                            darks[(red, green, blue, 255)] += 1
                        elif min(red, green, blue) > 210:
                            continue
                        elif blue > red + 20:
                            blues[(red, green, blue, 255)] += 1
                        elif red > blue + 20:
                            oranges[(red, green, blue, 255)] += 1
                face = blues if sum(blues.values()) >= sum(oranges.values()) else oranges
                fill = face.most_common(1)[0][0] if face else (48, 96, 216, 255)
                border = darks.most_common(1)[0][0] if darks else (16, 16, 16, 255)
                result = Image.new("RGBA", source.size, (0, 0, 0, 0))
                plate_box = _plate_box(result.width, result.height, spec)
                _draw_gloss_plate(
                    result,
                    plate_box,
                    fill,
                    border,
                    palette,
                    int(spec.get("plate_corner", 2)),
                )
                icon = str(spec.get("icon") or label.get("icon") or "")
                if icon:
                    _draw_simple_icon(
                        result,
                        icon.upper()[0],
                        str(spec.get("icon_side") or label.get("icon_side") or "right"),
                        border,
                        plate_box,
                        palette,
                    )
                rectangle = None
            # Sample the compact, known-good interior before expanding the
            # erase area. Sampling the full-height rectangle can make the
            # existing white glyphs outnumber the real button fill.
            if rectangle is not None:
                fill = dominant_fill(result, rectangle, strategy)
            if rectangle is not None and spec.get("full_label_height"):
                rectangle = (
                    rectangle[0],
                    1,
                    min(rectangle[2], result.width - 2),
                    max(1, result.height - 2),
                )
            if rectangle is not None:
                ImageDraw.Draw(result).rectangle(rectangle, fill=fill)
        text_rectangle = tuple(
            int(value)
            for value in label.get(
                "text_rect",
                spec.get("text_rect", (0, 0, result.width, result.height)),
            )
        )
        text_left, text_top, text_right, text_bottom = text_rectangle
        if plate_box is not None:
            text_left, text_top, text_right, text_bottom = plate_box
            text_left += 2
            text_top += 1
            text_right -= 2
            text_bottom -= 1
        if spec.get("full_label_height"):
            text_top, text_bottom = 0, result.height
        icon = str(spec.get("icon") or label.get("icon") or "")
        if icon:
            plate_height = (plate_box[3] - plate_box[1]) if plate_box else result.height
            icon_size = 16 if plate_height >= 24 else (10 if plate_height >= 16 else 8)
            side = str(spec.get("icon_side") or label.get("icon_side") or "right")
            origin_left = plate_box[0] if plate_box else 0
            origin_right = plate_box[2] if plate_box else result.width
            if side == "left":
                text_left = max(text_left, origin_left + icon_size + 4)
            else:
                text_right = min(text_right, origin_right - icon_size - 4)
            if plate_box is None:
                text_top = 2
                text_bottom = result.height - 2
        text_size = (max(1, text_right - text_left), max(1, text_bottom - text_top))
        style = str(label.get("font_style", spec.get("font_style", "")))
        if style == "compact_3x5":
            local_mask = make_compact_3x5_mask(
                str(label["text"]),
                text_size,
                int(label.get("font_scale", spec.get("font_scale", 2))),
                int(label.get("font_scale_x", spec.get("font_scale_x", label.get("font_scale", spec.get("font_scale", 2))))),
                int(label.get("font_scale_y", spec.get("font_scale_y", label.get("font_scale", spec.get("font_scale", 2))))),
            )
        elif style == "ds_5x7":
            local_mask = make_ds_5x7_mask(str(label["text"]), text_size)
        elif style == "hex_4x7":
            local_mask = make_hex_4x7_mask(str(label["text"]), text_size)
        else:
            local_mask = make_mask(str(label["text"]), text_size, pixel_font)
        mask = Image.new("1", result.size, 0)
        mask.paste(local_mask, (text_left, text_top))
        tone = str(label.get("text_tone", spec.get("text_tone", "light")))
        if tone == "dark":
            text_color = dark
            outline_color = light
        else:
            text_color = light
            outline_color = dark
        if bool(label.get("shadow", spec.get("shadow", False))):
            shadow = Image.new("1", result.size, 0)
            shadow.paste(local_mask, (text_left + 1, text_top + 1))
            result.paste(outline_color, (0, 0), shadow)
        if bool(label.get("outline", spec.get("outline", True))):
            # 4-connected outline only.  MaxFilter(3) added diagonal blobs
            # that read as smear on these tiny DS labels.
            outline = Image.new("1", result.size, 0)
            src, dst = mask.load(), outline.load()
            width, height = result.size
            for y in range(height):
                for x in range(width):
                    if not src[x, y]:
                        continue
                    dst[x, y] = 1
                    for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        nx, ny = x + ox, y + oy
                        if 0 <= nx < width and 0 <= ny < height:
                            dst[nx, ny] = 1
            result.paste(outline_color, (0, 0), outline)
        result.paste(text_color, (0, 0), mask)
    return result


def encode_selected_cells(template_graphics: bytes, cells, canvases, palette, selected) -> bytes:
    graphics = parse_ncgr(template_graphics)
    tile_pixels = [bytearray(tile) for tile in graphics.tiles]
    bytes_per_tile = 0x20 if graphics.bpp == 4 else 0x40
    tiles_per_character = graphics.mapping_unit_bytes // bytes_per_tile
    for cell_index in selected:
        cell = cells[cell_index]
        canvas = canvases[cell_index]
        left, top, right, bottom = _cell_bounds(cell)
        width = max(1, right - left)
        for oam in cell.oams:
            oam_width, oam_height = oam.dimensions
            base_tile = oam.character * tiles_per_character + cell.partition_offset // bytes_per_tile
            if graphics.bpp == 4 and len(palette) > 16:
                bank_start = oam.palette * 16
                oam_palette = tuple(palette[bank_start:bank_start + 16])
            else:
                oam_palette = tuple(palette)
            flip_x = not oam.affine and bool(oam.affine_flags & 0x08)
            flip_y = not oam.affine and bool(oam.affine_flags & 0x10)
            for tile_y in range(0, oam_height, 8):
                for tile_x in range(0, oam_width, 8):
                    tile_index = base_tile + (tile_y // 8) * (oam_width // 8) + tile_x // 8
                    if tile_index >= len(tile_pixels):
                        raise ValueError("Template OAM references tiles outside its NCGR")
                    tile = tile_pixels[tile_index]
                    for py in range(8):
                        for px in range(8):
                            local_x = tile_x + px
                            local_y = tile_y + py
                            display_x = oam_width - 1 - local_x if flip_x else local_x
                            display_y = oam_height - 1 - local_y if flip_y else local_y
                            x = _screen_x(oam) - left + display_x
                            y = _screen_y(oam) - top + display_y
                            color = canvas.getpixel((x, y)) if 0 <= x < canvas.width and 0 <= y < canvas.height else (0, 0, 0, 0)
                            # Four-bit sprites store a palette-bank-local
                            # nibble, not an index into the complete NCLR.
                            tile[py * 8 + px] = _nearest_palette_index(color, oam_palette)
    output = bytearray(template_graphics)
    cursor = 0x30
    if graphics.bpp == 8:
        for tile in tile_pixels:
            output[cursor:cursor + 0x40] = tile
            cursor += 0x40
    else:
        for tile in tile_pixels:
            packed = bytearray(0x20)
            for index in range(0, 64, 2):
                packed[index // 2] = tile[index] | (tile[index + 1] << 4)
            output[cursor:cursor + 0x20] = packed
            cursor += 0x20
    return bytes(output)


def arm9_slice(data: bytes) -> bytes:
    class Reader:
        def __init__(self, raw): self.raw, self.pos = raw, 0
        def seek(self, pos): self.pos = pos; return pos
        def read(self, size=-1):
            if size < 0: size = len(self.raw) - self.pos
            value = self.raw[self.pos:self.pos + size]; self.pos += len(value); return value
    header = read_header(Reader(data))
    start = int(header["arm9_offset"])
    return data[start:start + int(header["arm9_size"])]


def build(
    source: Path,
    output: Path,
    manifest: Path,
    preview: Path,
    font_rom: Path | None = None,
    only: set[tuple[int, int]] | None = None,
) -> dict[str, object]:
    source_data = source.read_bytes()
    with source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        graphics_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, GRAPHICS_PATH)))
        palette_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, PALETTE_PATH)))
        cells_pak = XrosPak.from_bytes(read_nitro_file(handle, find_nitro_file(files, CELLS_PATH)))
    graphics_entries = [graphics_pak.unpacked_data(index) for index in range(len(graphics_pak.entries))]
    previews: list[tuple[int, int, Image.Image]] = []
    changes: list[dict[str, object]] = []
    pixel_font = NftrPixelFont(font_rom) if font_rom else None
    donor_cache: dict[tuple[int, int], Image.Image] = {}

    def donor_canvas(entry: int, cell: int, target_size: tuple[int, int]) -> Image.Image:
        key = (entry, cell)
        if key not in donor_cache:
            donor_graphics = parse_ncgr(graphics_entries[entry])
            donor_palette = parse_nclr(palette_pak.unpacked_data(entry))
            donor_cells = parse_ncer(cells_pak.unpacked_data(entry))
            donor_cache[key] = render_full_cell(
                donor_graphics,
                donor_palette,
                donor_cells[cell],
            )
        donor = donor_cache[key]
        if donor.size == target_size:
            return donor.copy()
        # Cell bounds can differ by a transparent pixel or two even when the
        # underlying frame is identical. Centre the donor without scaling.
        fitted = Image.new("RGBA", target_size, (0, 0, 0, 0))
        fitted.alpha_composite(
            donor,
            ((target_size[0] - donor.width) // 2, (target_size[1] - donor.height) // 2),
        )
        return fitted

    for entry_id, available_specs in SPECS.items():
        cell_specs = {
            cell_id: spec
            for cell_id, spec in available_specs.items()
            if only is None or (entry_id, cell_id) in only
        }
        if not cell_specs:
            continue
        graphics = parse_ncgr(graphics_entries[entry_id])
        palette = parse_nclr(palette_pak.unpacked_data(entry_id))
        cells = parse_ncer(cells_pak.unpacked_data(entry_id))
        canvases = [render_full_cell(graphics, palette, cell) for cell in cells]
        for cell_id, spec in cell_specs.items():
            source_canvas = canvases[cell_id]
            if "base_entry" in spec:
                source_canvas = donor_canvas(
                    int(spec["base_entry"]),
                    int(spec.get("base_cell", cell_id)),
                    source_canvas.size,
                )
            canvases[cell_id] = edit_canvas(source_canvas, spec, palette, pixel_font)
            previews.append((entry_id, cell_id, canvases[cell_id]))
            change_text = spec.get("text")
            if change_text is None:
                change_text = [str(label["text"]) for label in spec.get("labels", [])]
            changes.append({"entry": entry_id, "cell": cell_id, "text": change_text})
        graphics_entries[entry_id] = encode_selected_cells(
            graphics_entries[entry_id], cells, canvases, palette, set(cell_specs)
        )
    replacement = build_xros_pak(graphics_entries)
    patched = replace_nitrofs_files(source_data, {GRAPHICS_PATH: replacement})
    if arm9_slice(source_data) != arm9_slice(patched):
        raise AssertionError("ARM9 changed during data-only UI patch")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patched)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "source_rom": str(source.resolve()),
        "output_rom": str(output.resolve()),
        "source_sha256": hashlib.sha256(source_data).hexdigest(),
        "output_sha256": hashlib.sha256(patched).hexdigest(),
        "changed_archives": [GRAPHICS_PATH],
        "arm9_unchanged": True,
        "font_donor_rom": str(font_rom.resolve()) if font_rom else None,
        "changes": changes,
    }
    manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    columns, cell_width, cell_height = 3, 260, 80
    rows = (len(previews) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * cell_width, rows * cell_height), (20, 30, 42, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (entry, cell, image) in enumerate(previews):
        x, y = (index % columns) * cell_width, (index // columns) * cell_height
        draw.text((x + 3, y + 3), f"{entry}:{cell}", fill="white")
        sheet.alpha_composite(image, (x + 3, y + 22))
    preview.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(preview)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("preview", type=Path)
    parser.add_argument(
        "--font-rom",
        type=Path,
        help="Use an English NFTR from this legally owned ROM as the pixel-letter donor.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="ENTRY:CELL",
        help="Patch only this entry/cell pair; repeat to build a small review batch.",
    )
    args = parser.parse_args()
    selected: set[tuple[int, int]] | None = None
    if args.only:
        selected = set()
        for raw in args.only:
            entry_text, separator, cell_text = raw.partition(":")
            if not separator:
                parser.error(f"invalid --only value {raw!r}; expected ENTRY:CELL")
            selected.add((int(entry_text), int(cell_text)))
    result = build(
        args.source,
        args.output,
        args.manifest,
        args.preview,
        args.font_rom,
        selected,
    )
    print(json.dumps({key: value for key, value in result.items() if key != "changes"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
