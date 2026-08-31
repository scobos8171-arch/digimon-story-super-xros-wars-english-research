#!/usr/bin/env python3
"""Analyze a field-hex DeSmuME dump for the six runtime hex labels."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

TERMS = {
    "status": "ステータス",
    "equip": "そうび",
    "formation": "たいれつ",
    "items": "もちもの",
    "map": "マップ",
    "info": "じょうほう",
    "skills": "わざ",
    "banner": "じゅうじボタン",
    "shoji": "しょじきん",
    "back": "もどる",
}

OAM_SIZES = {
    (0, 0): (8, 8),
    (0, 1): (16, 16),
    (0, 2): (32, 32),
    (0, 3): (64, 64),
    (1, 0): (16, 8),
    (1, 1): (32, 8),
    (1, 2): (32, 16),
    (1, 3): (64, 32),
    (2, 0): (8, 16),
    (2, 1): (8, 32),
    (2, 2): (16, 32),
    (2, 3): (32, 64),
}

BLOBS = (
    ("main_ram", "main_ram_02000000.bin", 0x02000000),
    ("itcm", "itcm_01FF8000.bin", 0x01FF8000),
    ("dtcm_27e", "dtcm_027E0000.bin", 0x027E0000),
    ("dtcm_27c", "dtcm_027C0000.bin", 0x027C0000),
    ("overlay0", "overlay0_021F3D20.bin", 0x021F3D20),
    ("overlay2", "overlay2_0221BF80.bin", 0x0221BF80),
    ("arm9_ui", "arm9_ui_0210A000.bin", 0x0210A000),
    ("txeu", "txeu_0226C000.bin", 0x0226C000),
)


def find_all(data: bytes, needle: bytes, limit: int = 8) -> list[int]:
    hits: list[int] = []
    start = 0
    while needle:
        i = data.find(needle, start)
        if i < 0:
            return hits
        hits.append(i)
        start = i + 1
        if len(hits) >= limit:
            return hits
    return hits


def sjis_u16le(text: str) -> bytes:
    raw = text.encode("cp932")
    out = bytearray()
    i = 0
    while i < len(raw):
        b = raw[i]
        if (0x81 <= b <= 0x9F) or (0xE0 <= b <= 0xFC):
            out += int.from_bytes(raw[i : i + 2], "big").to_bytes(2, "little")
            i += 2
        else:
            out += bytes((b, 0))
            i += 1
    return bytes(out)


def decode_oam_sub(path: Path) -> list[dict[str, int]]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    sprites = []
    for index in range(min(128, len(raw) // 8)):
        a0 = int.from_bytes(raw[index * 8 : index * 8 + 2], "little")
        a1 = int.from_bytes(raw[index * 8 + 2 : index * 8 + 4], "little")
        a2 = int.from_bytes(raw[index * 8 + 4 : index * 8 + 6], "little")
        hide = (a0 >> 8) & 3
        if hide == 2:
            continue
        shape = (a0 >> 14) & 3
        size = (a1 >> 14) & 3
        width, height = OAM_SIZES.get((shape, size), (8, 8))
        y = a0 & 0xFF
        x = a1 & 0x1FF
        if y == 192 and x == 0:
            continue
        sprites.append(
            {
                "index": index,
                "x": x,
                "y": y,
                "w": width,
                "h": height,
                "tile": a2 & 0x3FF,
                "pal": (a2 >> 12) & 0xF,
                "shape": shape,
                "size": size,
            }
        )
    return sprites


def render_obj_sprite(
    obj: bytes,
    palette: bytes,
    sprite: dict[str, int],
    *,
    palette_base: int,
) -> Image.Image:
    image = Image.new("RGBA", (sprite["w"], sprite["h"]), (0, 0, 0, 0))
    pixels = image.load()
    # DS palette RAM: Engine A OBJ starts at 0x200 and Engine B (the bottom
    # screen here) OBJ starts at 0x600.  The old hard-coded 0x200 produced
    # misleading contact sheets for the lower-screen runtime glyphs.
    pal_off = palette_base + sprite["pal"] * 32
    colors = []
    for i in range(16):
        value = int.from_bytes(palette[pal_off + i * 2 : pal_off + i * 2 + 2], "little")
        r = (value & 31) * 8
        g = ((value >> 5) & 31) * 8
        b = ((value >> 10) & 31) * 8
        colors.append((r, g, b, 0 if i == 0 else 255))
    tile = sprite["tile"]
    tiles_x = sprite["w"] // 8
    for ty in range(0, sprite["h"], 8):
        for tx in range(0, sprite["w"], 8):
            # The Xros lower screen is using DS 2D OBJ tile mapping.  In
            # that layout, every sprite row advances by 32 8x8 tiles rather
            # than by the sprite's own width.  The prior 1D assumption made
            # every repeated blank-plate OAM entry look like the Status
            # label, which obscured the true per-label tile ranges.
            offset = (tile + (ty // 8) * 32 + tx // 8) * 32
            chunk = obj[offset : offset + 32]
            if len(chunk) < 32:
                continue
            for py in range(8):
                for px in range(4):
                    byte = chunk[py * 4 + px]
                    left, right = byte & 0xF, byte >> 4
                    x = tx + px * 2
                    y = ty + py
                    if 0 <= x < sprite["w"]:
                        pixels[x, y] = colors[left]
                    if 0 <= x + 1 < sprite["w"]:
                        pixels[x + 1, y] = colors[right]
    return image


def u32(data: bytes, addr: int, base: int) -> int:
    off = addr - base
    if off < 0 or off + 4 > len(data):
        return 0
    return int.from_bytes(data[off : off + 4], "little")


def analyze(dump: Path) -> str:
    lines: list[str] = [f"dump: {dump}", ""]
    blobs: list[tuple[str, bytes, int]] = []
    for name, filename, base in BLOBS:
        path = dump / filename
        if path.exists() and path.stat().st_size:
            blobs.append((name, path.read_bytes(), base))
            lines.append(f"have {name} {path.stat().st_size} bytes base=0x{base:08X}")
        else:
            lines.append(f"MISSING {filename}")
    lines.append("")

    ram = next((data for name, data, base in blobs if name == "main_ram"), b"")
    if ram:
        blobs.append(("main_ram_alias", ram, 0x02000000))

    lines.append("=== encoding search ===")
    found_any = False
    for name, data, base in blobs:
        if name == "main_ram_alias":
            continue
        for term, text in TERMS.items():
            variants = [
                ("cp932", text.encode("cp932")),
                ("utf16le", text.encode("utf-16le")),
                ("sjis_u16le", sjis_u16le(text)),
            ]
            for enc, needle in variants:
                hits = find_all(data, needle)
                if hits:
                    found_any = True
                    addrs = ", ".join(f"0x{base + off:08X}" for off in hits)
                    lines.append(f"  {name} {term}/{enc}: {addrs}")
    if not found_any:
        lines.append("  no hex-ring words in dumped regions (cp932/utf16le/sjis-u16le)")
    lines.append("")

    if ram:
        banner = "じゅうじボタンで".encode("cp932")
        hits = find_all(ram, banner, 10)
        lines.append("=== banner copies ===")
        for off in hits:
            chunk = ram[off : off + 80].split(b"\0")[0]
            lines.append(f"  0x{0x02000000 + off:08X} {chunk.decode('cp932', errors='replace')!r}")
        lines.append("")
        lines.append("=== known constructor pointers ===")
        for addr in (0x020C6C04, 0x020C6C08, 0x021F3CEC, 0x02117348, 0x0210BEE4, 0x02113098):
            lines.append(f"  0x{addr:08X} = 0x{u32(ram, addr, 0x02000000):08X}")
        lines.append("")

    sprites = decode_oam_sub(dump / "oam_sub.bin")
    lines.append(f"=== sub OAM live sprites: {len(sprites)} ===")
    for sprite in sprites:
        lines.append(
            f"  oam{sprite['index']:03d} x={sprite['x']:3d} y={sprite['y']:3d} "
            f"{sprite['w']}x{sprite['h']} tile={sprite['tile']} pal={sprite['pal']}"
        )
    obj = dump / "obj_sub_06600000.bin"
    pal = dump / "palette_ram.bin"
    if sprites and obj.exists() and pal.exists():
        out_dir = dump / "label_tiles"
        out_dir.mkdir(exist_ok=True)
        obj_bytes = obj.read_bytes()
        pal_bytes = pal.read_bytes()
        for sprite in sprites:
            if sprite["y"] in (0, 192) and sprite["h"] <= 16 and sprite["w"] >= 32:
                continue
            image = render_obj_sprite(
                obj_bytes,
                pal_bytes,
                sprite,
                palette_base=0x600,
            )
            image.save(out_dir / f"oam{sprite['index']:03d}_{sprite['x']}x{sprite['y']}.png")
        # A composited lower-screen OBJ layer is the quickest way to verify
        # which tiles actually belong to the labels versus the reusable red
        # button plate.  OAM order is sufficient for this diagnostic capture.
        screen = Image.new("RGBA", (256, 192), (0, 0, 0, 0))
        for sprite in sprites:
            image = render_obj_sprite(
                obj_bytes,
                pal_bytes,
                sprite,
                palette_base=0x600,
            )
            screen.alpha_composite(image, (sprite["x"], sprite["y"]))
        screen.save(dump / "sub_obj_composite.png")
        lines.append(f"wrote OBJ composite to {dump / 'sub_obj_composite.png'}")
        lines.append(f"wrote label tiles to {out_dir}")
    lines.append("")
    lines.append("If lua_hex_scan.tsv exists, it is the in-emulator encoding scan of ITCM/DTCM/overlays.")
    return "\n".join(lines) + "\n"


def latest_dump(root: Path) -> Path:
    dumps = [path for path in root.iterdir() if path.is_dir() and path.name[0].isdigit()]
    if not dumps:
        raise SystemExit(f"No dump folders in {root}")
    return max(dumps, key=lambda path: path.name)


def main() -> int:
    # Windows PowerShell commonly uses cp1252.  The reports deliberately
    # contain Japanese search strings, so force UTF-8 instead of crashing
    # after the useful files have already been written.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("dump", type=Path, nargs="?")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(
            r"C:\Users\YOUR_NAME\Documents\Codex\2026-07-24\c-users-scobo-downloads-download-digimon"
            r"\outputs\Xros Evolution Complete US v64 HEX CAPTURE\DATA TO SEND TO DEV"
        ),
    )
    args = parser.parse_args()
    dump = args.dump if args.dump else latest_dump(args.root)
    report = analyze(dump)
    out = dump / "HEX_CAPTURE_REPORT.txt"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
