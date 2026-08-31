"""Patch the hex-menu scrolling banner and FUNDS in ARM9.

These two Shift-JIS slots live in decompressed ARM9 at 0x10BEE4 and 0x113098.
They are the ticker between the two screens and the party 'Shoji' label.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work" / "DigimonNDSRomEditor-master"))
from rom_research.nds_code_compression import compress_blz, decompress_blz  # noqa: E402
from rom_research.nds_inventory import read_header  # noqa: E402

SRC = ROOT / "outputs" / "Xros Evolution Complete US v98 SPECIES FAMILY NAMES" / "Game" / "Digimon Story Xros Evolution - COMPLETE US v98 SPECIES FAMILY NAMES.nds"
OUT = ROOT / "outputs" / "Xros Evolution Complete US v99 HEX BANNER FUNDS"

BANNER_OFF = 0x10BEE4
BANNER_EN = b"SELECT WITH THE D-PAD. PRESS A TO CONFIRM."
FUNDS_OFF = 0x113098
FUNDS_EN = b"FUNDS"


def crc16(data: bytes | bytearray) -> int:
    value = 0xFFFF
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xA001 if value & 1 else 0)
    return value & 0xFFFF


def slot_len(blob: bytes, offset: int) -> int:
    end = blob.find(b"\0", offset)
    if end < 0:
        raise ValueError("unterminated ARM9 string")
    return end - offset


def main() -> None:
    rom = bytearray(SRC.read_bytes())
    with SRC.open("rb") as handle:
        header = read_header(handle)
    arm9_off = int(header["arm9_offset"])
    arm9_size = int(header["arm9_size"])
    compressed = bytes(rom[arm9_off:arm9_off + arm9_size])
    dec = bytearray(decompress_blz(compressed))
    b_len = slot_len(dec, BANNER_OFF)
    f_len = slot_len(dec, FUNDS_OFF)
    print("banner slot", b_len, "jp", dec[BANNER_OFF:BANNER_OFF + b_len].decode("cp932"))
    print("funds slot", f_len, "jp", dec[FUNDS_OFF:FUNDS_OFF + f_len].decode("cp932"))
    if len(BANNER_EN) > b_len:
        raise ValueError("banner English longer than JP slot")
    if len(FUNDS_EN) > f_len:
        raise ValueError("funds English longer than JP slot")
    dec[BANNER_OFF:BANNER_OFF + b_len] = BANNER_EN + b"\0" * (b_len - len(BANNER_EN))
    dec[FUNDS_OFF:FUNDS_OFF + f_len] = FUNDS_EN + b"\0" * (f_len - len(FUNDS_EN))
    packed = compress_blz(bytes(dec), arm9=True)
    print("old arm9", arm9_size, "new", len(packed))
    if len(packed) > arm9_size:
        raise ValueError(f"compressed ARM9 grew {len(packed)} > {arm9_size}")
    rom[arm9_off:arm9_off + len(packed)] = packed
    rom[arm9_off + len(packed):arm9_off + arm9_size] = b"\xFF" * (arm9_size - len(packed))
    struct.pack_into("<I", rom, 0x2C, len(packed))
    struct.pack_into("<H", rom, 0x15E, crc16(rom[:0x15E]))
    # verify
    check = decompress_blz(bytes(rom[arm9_off:arm9_off + len(packed)]))
    got_b = check[BANNER_OFF:].split(b"\0", 1)[0]
    got_f = check[FUNDS_OFF:].split(b"\0", 1)[0]
    print("verify banner", got_b)
    print("verify funds", got_f)
    if got_b != BANNER_EN or got_f != FUNDS_EN:
        raise AssertionError("ARM9 string verify failed")
    dest = OUT / "Game" / "Digimon Story Xros Evolution - COMPLETE US v99 HEX BANNER FUNDS.nds"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(rom)
    Path(r"C:\Users\YOUR_NAME\Downloads\Digimon Story Xros Evolution - COMPLETE US v99 HEX BANNER FUNDS.nds").write_bytes(rom)
    print("wrote", dest, "bytes", len(rom))


if __name__ == "__main__":
    main()
