# DigiPak Xros Graphics Workflow

## What is installed

- Upstream source: `tools/third_party/DigiPak`
- Bundled upstream executable: `tools/bin/DigiPak/DigiPak/DigiPAK.exe`
- Safe wrapper: `tools/recovery/digipak_probe.py`

The wrapper is intentionally **unpack only**. It copies an input `.PAK` into
`work/digipak_validation/` before starting DigiPak and never calls `-p` or
`-pm`. Do not use upstream generic packing for ROM replacement yet: it does
not preserve the source compression flags/layout reliably enough for a safe
Xros patch workflow.

## Verified Xros Evolution US v3 archive families

| Archive family | Record count | Role |
| --- | ---: | --- |
| `MAP_NCGR.PAK` | 190 | map tiles |
| `MAP_NCLR.PAK` | 91 | map palettes |
| `MAP_NSCR.PAK` | 240 | map screens/layouts |
| `SPR_NCGR.PAK` | 2,647 | sprite/UI tiles |
| `SPR_NCLR.PAK` | 2,647 | sprite/UI palettes |
| `SPR_NCER.PAK` | 2,647 | sprite/UI cell layouts |
| `SPR_NANR.PAK` | 2,647 | sprite/UI animations |
| `BG_NCGR.PAK` | 315 | background tiles |
| `BG_NCLR.PAK` | 233 | background palettes |
| `BG_NSCR.PAK` | 324 | background layouts |

All record totals were verified by read-only exports on 2026-08-17. The
manifests and exported copies live under:

`work/digipak_validation/xros_evolution_us_v3/`

## Safe next step for the untranslated command ring

1. Render the ordinal-matched `SPR_NCGR` + `SPR_NCLR` + `SPR_NCER` records.
2. Visually identify the record IDs for each command ring label/button.
3. Patch a **copy** of only those records while preserving tile dimensions,
   palette indices, cell data, and animation data.
4. Rebuild a test ROM using a format-aware repacker, then launch an emulator
   smoke test that opens every changed button. No production ROM is changed
   until that test passes.

This is the missing bridge between hand-edited PNGs and the game: a PNG is
not enough on its own; the correct NCGR tile record, NCLR palette, and NCER
cell record must all be mapped and preserved.
