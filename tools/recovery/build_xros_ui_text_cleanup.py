"""Apply narrowly-scoped, data-only Xros UI wording and overflow repairs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EDITOR = ROOT / "work" / "DigimonNDSRomEditor-master"
sys.path.insert(0, str(EDITOR))

from rom_research.nds_inventory import read_header, read_nitrofs  # noqa: E402
from rom_research.nitrofs_patch import replace_nitrofs_files  # noqa: E402
from rom_research.story_messages import build_message_table, parse_message_table  # noqa: E402
from rom_research.xros_pak import (  # noqa: E402
    XrosPak,
    build_xros_pak,
    find_nitro_file,
    read_nitro_file,
)


# Coordinates are (MESPAK number, PAK entry, string index). These strings were
# confirmed against the Japanese message dump and screenshots from hardware
# testing. Control parameters (^0, ^1) must remain unchanged.
REPAIRS: dict[tuple[int, int, int], str] = {
    # Canonical stat names used by the status, party, equipment, DigiFarm,
    # and battle-information screens.
    (0, 0, 58): "Wisdom",
    (0, 0, 59): "Speed",
    (0, 0, 60): "Defense",
    (0, 0, 134): "Wisdom",
    (0, 0, 135): "Speed",
    (0, 0, 136): "Defense",
    (0, 0, 137): "Bond",
    (1, 1, 107): "Wisdom",
    (1, 1, 108): "Speed",
    (1, 1, 109): "Defense",
    (1, 1, 111): "Weakness",
    (1, 1, 112): "Status",
    (1, 1, 113): "Special",
    (1, 3, 78): "Speed",
    (1, 3, 108): "Speed",
    (1, 15, 3): "Wisdom",
    (1, 15, 4): "Speed",
    (1, 15, 5): "Defense",
    (1, 15, 51): "Wisdom",
    (1, 15, 52): "Speed",
    (1, 15, 53): "Defense",
    (1, 16, 73): "Wisdom",
    (1, 16, 74): "Speed",
    (1, 16, 75): "Defense",
    (1, 16, 76): "Bond",
    (1, 16, 172): "Wisdom",
    (1, 16, 173): "Speed",
    (1, 16, 174): "Defense",
    (1, 16, 199): "Weakness",
    (1, 17, 1): "Defense",
    (1, 17, 2): "Speed",
    (1, 17, 28): "Wisdom",

    # General Information screen. Keep these deliberately short so the
    # original DS layout does not clip them.
    (1, 16, 23): "Play Time",
    (1, 16, 25): "Friends",
    (1, 16, 26): "DigiFarm Lv",
    (1, 16, 27): "DigiScore",
    (1, 16, 28): "Quests",
    (1, 16, 29): "Field Guide",
    (1, 16, 30): "GENERAL INFO",
    (1, 16, 77): "Funds",

    # Save system.
    (0, 0, 49): "Saving...\nDo not turn off the power.",
    (0, 0, 51): "Save failed.\nTurn off the system, then\nreinsert the Game Card.",
    (1, 17, 30): "Save failed.\nTurn off the system, then\nreinsert the Game Card.",
    (1, 17, 31): "Could not write save data.\nTurn off the system, then\nreinsert the Game Card.",
    (1, 17, 35): "Save your current game?",
    (1, 17, 36): "Yes",
    (1, 17, 37): "No",
    (1, 17, 38): "Saving...\nDo not turn off the power.",
    (1, 17, 41): "Choose with the D-Pad.\nPress A to confirm.",
    (1, 17, 42): "Choose a Digimon to view.",
    (1, 17, 43): "Choose a Digimon to learn a move.",
    (1, 17, 44): "Choose a Digimon to attack.",
    (1, 17, 45): "Not enough MP to use this move!",

    # Shop and Farm Island menus.
    (1, 18, 0): "Buy Equipment",
    (1, 18, 1): "Buy Items",
    (1, 18, 2): "Buy Farm Goods",
    (1, 18, 3): "Close",
    (1, 18, 4): "Sell Equipment",
    (1, 18, 5): "Sell Items",
    (1, 18, 6): "Sell Farm Goods",
    (1, 18, 7): "Held Items",
    (1, 18, 8): "Storage",
    (1, 18, 9): "Held Items",
    (1, 18, 10): "Storage",
    (1, 18, 11): "Buy Farm Goods",
    (1, 18, 12): "Place Terrain Board",
    (1, 18, 13): "Set BGM Board",
    (1, 18, 14): "Storage",
    (1, 18, 15): "Buy ^0?",
    (1, 18, 16): "Price: ^0 Bit",
    (1, 18, 17): "How many ^0?",
    (1, 18, 18): "Total: ^0 Bit",
    (1, 18, 19): "Sell ^0 for\n^1 Bit?",
    (1, 18, 20): "Buy",
    (1, 18, 21): "Cancel",
    (1, 18, 22): "Sell ^0 for\n^1 Bit?",
    (1, 18, 23): "Sell",
    (1, 18, 24): "Cancel",
    (1, 18, 25): "Bought ^1 x ^0.",
    (1, 18, 26): "Sold ^1 x ^0.",
    (1, 18, 27): "Use ^0 to raise it\nto MAX?",
    (1, 18, 28): "Raise ^0 to Lv.^1?",
    (1, 18, 29): "Yes",
    (1, 18, 30): "No",
    (1, 18, 31): "Raised ^0 to MAX!",
    (1, 18, 32): "Raised ^0 to Lv.^1!",
    (1, 18, 33): "Welcome! What can I get you?",
    (1, 18, 34): "Welcome to the Farm Shop!",
    (1, 18, 35): "What would you like to sell?",
    (1, 18, 36): "Choose an item to buy.",
    (1, 18, 37): "Choose an item to sell.",
    (1, 18, 38): "Choose an item to equip.",
    (1, 18, 39): "Choose Farm Goods to buy.",
    (1, 18, 40): "Choose a farm for the Terrain Board.",
    (1, 18, 41): "Choose equipment to buy.",
    (1, 18, 42): "Choose an item to buy.",
    (1, 18, 43): "Choose Farm Goods to buy.",
    (1, 18, 44): "Choose a farm for the Terrain Board.",
    (1, 18, 45): "Choose a Terrain Board.",
    (1, 18, 46): "Choose a farm for the BGM Board.",
    (1, 18, 47): "Choose a BGM Board.",
    (1, 18, 48): "You have no equipment.",
    (1, 18, 49): "You have no items.",
    (1, 18, 50): "You have no Farm Goods.",
    (1, 18, 51): "Not enough Bit!",
    (1, 18, 52): "You cannot carry any more.",
    (1, 18, 53): "Special items cannot be sold.",
    (1, 18, 54): "This Terrain Board is already MAX.",
    (1, 18, 55): "This BGM Board is already MAX.",
    (1, 18, 56): "A Digimon is using this item.",
    (1, 18, 57): "This item is placed on Farm Island.",
    (1, 18, 58): "Not enough Bit!",
    (1, 18, 59): "Item",
    (1, 18, 60): "Price",
    (1, 18, 61): "Stock",
    (1, 18, 63): "Terrain Board",
    (1, 18, 64): "Level",
    (1, 18, 66): "BGM Board",

    # Screenshot leftovers: stats list, Bond, status ailments, location.
    (1, 1, 122): "Bond",
    (1, 3, 80): "Bond",
    (1, 3, 109): "Bond",
    (1, 15, 63): "Bond",
    (1, 17, 5): "Bond",
    (1, 1, 105): "Fusion",
    (1, 16, 49): "Fusion",
    (1, 1, 116): "Confuse",
    (1, 16, 103): "Confuse",
    (1, 16, 177): "Confuse",
    (0, 0, 155): "Confuse",
    (1, 1, 114): "Fine",
    (1, 16, 100): "Fine",
    (1, 16, 97): "Defense",
    (1, 6, 8): "Yonyard 1",
    (1, 6, 9): "Yonyard 2",
    (1, 6, 10): "Yonyard 3",
    (1, 21, 26): "Power\nWisdom\nSpeed\nDefense\nBond",
    (1, 16, 34): "Jogress",

    # Formation/stats panel: leftover romaji next to LV.
    # Daidai = 世代 (stage). Jotai = 状態 (condition). Fine = 元気.
    (1, 16, 43): "Stage",
    (1, 16, 44): "Status",
    (1, 16, 80): "Learned",
    (1, 16, 96): "Power rank",
    (1, 16, 98): "Wisdom rank",
    (1, 16, 99): "Default sort",
    (1, 16, 100): "OK",
    (1, 16, 105): "Seal",
    (1, 1, 114): "OK",
    (0, 0, 115): "OK",

    # Species / family names still stored as romaji.
    (0, 0, 71): "Dark",
    (0, 0, 72): "Fighting",
    (0, 0, 73): "Mythic",
    (0, 0, 74): "Beast",
    (0, 0, 75): "Angel",
    (0, 0, 76): "Devil",
    (0, 0, 78): "Machine",
    (0, 0, 79): "Bird",
    (0, 0, 80): "Insect",
    (0, 0, 81): "Plant",
    (0, 0, 116): "Spoiled",
    (0, 0, 4507): "Insect Song",
    (0, 0, 4508): "Plant Song",
    (0, 0, 4518): "Mythic",
    (0, 0, 4519): "Beast",
    (0, 0, 4520): "Angel",
    (0, 0, 4521): "Devil",
    (0, 0, 4523): "Machine",
    (0, 0, 4524): "Bird",
    (0, 0, 4525): "Insect",
    (0, 0, 4526): "Plant",
    (0, 0, 4527): "Volcano",
    (0, 0, 4529): "Marble",
    (0, 0, 4533): "Prairie",
    (0, 0, 4534): "Forest",
    (1, 16, 194): "Species",
    (1, 17, 3): "Final",
    (1, 17, 9): "Element",
    (1, 1, 100): "Attack",
    (1, 1, 102): "Flee",
}


def _arm9(data: bytes) -> bytes:
    class Reader:
        def __init__(self, value: bytes):
            self.value, self.position = value, 0
        def seek(self, position: int) -> int:
            self.position = position
            return position
        def read(self, size: int = -1) -> bytes:
            if size < 0:
                size = len(self.value) - self.position
            result = self.value[self.position:self.position + size]
            self.position += len(result)
            return result
    reader = Reader(data)
    header = read_header(reader)
    start = int(header["arm9_offset"])
    return data[start:start + int(header["arm9_size"])]


def build(source: Path, output: Path, manifest: Path) -> dict[str, object]:
    replacements: dict[str, bytes] = {}
    applied: list[dict[str, object]] = []
    with source.open("rb") as handle:
        files = read_nitrofs(handle, read_header(handle))
        for archive_number in sorted({key[0] for key in REPAIRS}):
            archive_name = f"MSG/MESPAK{archive_number:02d}.PAK"
            pak = XrosPak.from_bytes(
                read_nitro_file(handle, find_nitro_file(files, archive_name))
            )
            entries = [pak.unpacked_data(i) for i in range(len(pak.entries))]
            for entry_index in sorted({k[1] for k in REPAIRS if k[0] == archive_number}):
                original = entries[entry_index]
                _offsets, strings = parse_message_table(original, encoding="shift_jis")
                patched = list(strings)
                for key, replacement in REPAIRS.items():
                    if key[:2] != (archive_number, entry_index):
                        continue
                    string_index = key[2]
                    if string_index >= len(patched):
                        raise IndexError(f"Missing UI string {key}")
                    before = patched[string_index].decode("shift_jis", errors="replace")
                    after = replacement.encode("ascii")
                    patched[string_index] = after
                    applied.append({"key": key, "before": before, "after": replacement})
                entries[entry_index] = build_message_table(original, patched)
            replacements[archive_name] = build_xros_pak(entries)

    source_data = source.read_bytes()
    patched_rom = replace_nitrofs_files(source_data, replacements)
    if _arm9(source_data) != _arm9(patched_rom):
        raise AssertionError("ARM9 changed during data-only UI cleanup")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patched_rom)
    result: dict[str, object] = {
        "source": str(source.resolve()),
        "output": str(output.resolve()),
        "source_sha256": hashlib.sha256(source_data).hexdigest(),
        "output_sha256": hashlib.sha256(patched_rom).hexdigest(),
        "arm9_unchanged": True,
        "patched_archives": sorted(replacements),
        "applied_count": len(applied),
        "applied": applied,
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    result = build(args.source, args.output, args.manifest)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
