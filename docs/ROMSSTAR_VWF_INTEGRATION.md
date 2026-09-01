# Romsstar ASM VWF integration

Upstream source: [Romsstar/XrosWars_ASM](https://github.com/Romsstar/XrosWars_ASM),
pinned here as the `third_party/Romsstar_XrosWars_ASM` Git submodule at commit
`1e6f173953aeac7443ae3e06a38746c3b63c8c47`.

The upstream `xroswars.asm` is an **armips** script for the Blue ARM9. It
switches a fixed-width rendering path to variable-width behavior, adjusts the
associated flag checks/default width, and replaces a small table/routine. The
upstream comments credit the original Lost Evolution routine to SydMontague and
the Xros Wars adaptation to Romsstar.

## Important status

This is an **optional experimental text-rendering layer**, not part of the
verified v145/v147 graphics build. Do not apply it to an already working build
without testing every dynamic text screen. The offsets are specific to Xros
Wars Blue's decompressed ARM9.

## Setup

```powershell
git submodule update --init --recursive
```

Install `armips` separately and make it available on `PATH`. The upstream
script expects a file named `arm9.bin` beside `xroswars.asm` and opens it at
runtime address `0x02000000`.

## Safe private-ROM workflow

1. Start with a private clean/v145-compatible Blue ROM. Do not add it to Git.
2. Extract the ARM9 using the NDS header's ARM9 offset/size.
3. BLZ-decompress it using `rom_research.nds_code_compression.decompress_blz`.
4. Copy the decompressed bytes to a temporary private folder as `arm9.bin`, and
   copy the pinned `xroswars.asm` beside it.
5. Run `armips xroswars.asm` from that temporary folder.
6. BLZ-recompress the patched ARM9 with
   `compress_blz(decompressed, arm9=True)`. Do **not** use an overlay compressor.
7. Update the ARM9 compressed-end pointer at decompressed offset `0xB9C` until
   compression converges, update header ARM9 size at `0x2C`, and recalculate
   header CRC16 at `0x15E`.
8. Confirm the decompressed output round-trips byte-for-byte, boot from a cold
   start, and test menus, story dialogue, battle text, scrolling banners, and
   save/load before promoting a build.

The existing ARM9 rebuild logic in
[`rom_research/xros_message_buffers.py`](../rom_research/xros_message_buffers.py)
is the reference for steps 6–7.

## Blue v145 baseline guard

Before applying the assembler script, verify these expected **decompressed**
ARM9 bytes. A mismatch means stop: the patch may target the wrong executable.

| RAM address | Expected original bytes |
| --- | --- |
| `0x02006404` | `02 09 11 E3` |
| `0x0203A020` | `02 09 10 E3` |
| `0x0203B410` | `02 C9 A0 E3` |
| `0x02032340` | `20 01 9F E5` |
| `0x020DDC23` | `08` |
| `0x020DDC2B` | `0C` |
| `0x020DDC33` | `10` |
| `0x020DDC3B` | `08` |
| `0x02045034` | `38 40 2D E9 1F DE 4D E2` |

These guards were read from the private v145 baseline ARM9; they are evidence
for safe targeting, not a claim that the VWF behavior is fully verified.
