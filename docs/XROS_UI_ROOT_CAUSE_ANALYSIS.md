# Xros UI localization: root-cause analysis (2026-08-17)

## Bottom line

The Japanese command-ring labels were **not** failing because the user's
English PNG edits were poor. They were failing because the patch pipeline had
not proven which runtime resource produced the visible pixels. It wrote to an
archive that is demonstrably not the resource used by the visible screen.

No further UI replacement should be applied until the v2 runtime capture has
been analyzed.

## Facts established from the current evidence

1. `SPR_NCGR.PAK` entry 196 is already English in the v46 test ROM, in both
   known physical/NitroFS copies. Its rendered cells contain `STATUS`,
   `SKILLS`, `EQUIP`, `PARTY`, `ITEMS`, `MAP`, `INFO`, and `BACK`.
2. The real game screenshot is still Japanese. Therefore entry 196 is not the
   active source for the command-ring button labels on that screen.
3. The earlier runtime probe read only `0x06200000..0x0621FFFF`, assuming it
   was sub-screen background VRAM. Exact tile matching found
   `BG_NCGR.PAK` entry 265 with 100% candidate coverage.
4. Rendering entry 265 as raw tiles shows the rocky battle arena, not the
   command ring. Therefore the probe did not capture the relevant graphics
   bank. Its archive conclusion was invalid for command-ring localization.
5. A prior claim that `BG_NCGR.PAK` entry 163 was the instruction banner is
   also not sufficient evidence. Its raw tiles contain unrelated Japanese
   copyright/title artwork. It must not be patched as the ring banner.

## What was going wrong

| Failure | Effect seen in game | Correct response |
| --- | --- | --- |
| Wrong archive family (`SPR_NCGR` entry 196) | Hand-edited red buttons never appeared | Identify live tile bank first |
| Wrong VRAM address assumption | A convincing but irrelevant 100% match to battle scenery | Capture all BG/OBJ windows and VRAM mapping registers |
| Mixing text, tile graphics, and font data | Some strings change while buttons do not | Classify each screen element before editing |
| Unsafe font/name substitutions | White placeholder glyphs, `Shoji`, black screens | Freeze font edits; patch only decoded message records with length/encoding checks |
| Testing against multiple builds/states | Results looked contradictory | Pin every test to one ROM hash and cold boot without an older save state |

## Correct recovery procedure

1. Cold-boot the pinned v46 diagnostic ROM.
2. Leave the Japanese hex command menu open.
3. Run `xros_ui_provenance_capture_v2.lua`. It is read-only and captures all
   mapped BG windows, both OBJ windows, palettes, OAM, and VRAMCNT registers.
4. Match every captured 4bpp tile against all NCGR records, per address
   window—not against a guessed PAK.
5. Decode the selected screen's NSCR tilemap and NCLR palette. Confirm the
   reconstructed PNG matches the screenshot, including the Japanese labels.
6. Only then map each manual PNG cell onto the exact tile coordinates, keeping
   the NCGR dimensions, palette indices, NSCR, NCER/NANR (if applicable),
   compressed size, and archive directory intact.
7. Test on a cold boot with the Skills option selected. The Skills transition
   must open correctly before the patch can be promoted.

## Why the black screen is separate

The Skills black screen follows an unsafe transition-related patch, not merely
a visual mismatch. It is probably a malformed message/font/resource table or
an affected loader path. The safe response is to isolate it against the clean
ROM and then perform a one-change binary search. It should not be debugged by
adding more translated tiles to the same build.
