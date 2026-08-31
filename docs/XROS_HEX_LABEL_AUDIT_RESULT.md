# Super Xros Blue command-ring label audit

Generated: 2026-08-25

## Status

The six labels have **not** been patched into a ROM yet. The safe source-level patch is blocked until the runtime setter that writes the ring label text is identified. This is intentional: the visible red hex plates are an object shell, while their labels are rendered at runtime. Replacing the plate PNGs cannot replace those strings and can also break the resource layout.

## Verified label set

| Japanese | Planned English |
|---|---|
| ステータス | Status |
| めいれい | Orders |
| そうび | Equipment |
| たいれつ | Formation |
| もちもの | Items |
| マップ | Map |
| じょうほう | Field Guide |

## Evidence collected

- The hex constructor at `0x020C68C0` creates the red command-ring shells and blank cells. It does not contain the six strings.
- The live shell is `SPR_NCGR.PAK`, entry 198. Its cells are plate graphics; the labels are not baked into those cells.
- Message/archive and glyph candidates were catalogued separately. An archive hit only proves that a word exists somewhere in the ROM; it does not prove that it feeds the ring.
- The current runtime captures contain several menu strings, but the six target labels were not found as raw Shift-JIS/CP932 text in the captured ring RAM. This means the label path is likely a message-ID/object lookup or a different owner/update path.
- The audit resolves the relevant constructor, slot builder, text-object constructor/init, palette helper, sprite object calls, and the surrounding ARM9 literal pool without modifying the ROM.

## Why prior swaps did not work

The previous swaps targeted image cells. The ring labels are separate runtime text objects, so the game continued to draw Japanese text. Some replacement images also changed dimensions/palette/resource indexing, which explains clipped text, oversized `BACK`, and black-screen failures.

## Next step for a safe patch

Run the corrected bounded runtime trace while opening the hex ring once. The
earlier Lua scripts requested register aliases named `pc`, `lr`, and `sp`,
but DeSmuME 0.9.13 exposes those values as `r15`, `r14`, and `r13`. This
caused the crucial caller and stack fields to be recorded as `--------`.

The corrected trace records real return addresses for the observed font/text
paths (`0x02039C30`, `0x02039CB0`, `0x0203892C`, `0x0205AA40`, and
`0x0203B8A4`) during the constructor window. Address `0x0203808C` is now
classified as a position update path, while `0x0204C1E4` and `0x0204D03C`
are slot/navigation management rather than proven caption setters.

Once the ring-specific caller is identified, disassemble it in the proven
decompressed ARM9, identify the seven source records, and make one small
icon-only or English-caption patch followed by a cold-boot test.

## Generated artifacts

- `tools/recovery/_tmp_hex_sprite_or_font.py` — read-only ARM9/archive source audit.
- `tools/recovery/report_xros_ring_label_candidates.py` — read-only evidence report.
- `work/decomp/xros_hex_source_report.json` — detailed source/archive report.
- `work/decomp/xros_ring_label_candidates.json` — per-label evidence and patch gate.
- `work/decomp/xros_ring_label_candidates.tsv` — compact table for review.

The report deliberately marks `safe_to_patch_now=false` for every label until the runtime source is proven.
