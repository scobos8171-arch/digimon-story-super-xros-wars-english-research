# Localization status map

This map records the known rendering path for the current English work. It is
the starting point for contributors; `unknown` means investigate before editing.

| Area | Rendering path | Verified target | Status | Contribution route |
| --- | --- | --- | --- | --- |
| Story dialogue | Dynamic message renderer | `MSG/MESPAK*.PAK` + NFTR glyph mapping | In progress | Rebuild message tables; preserve control codes and offsets |
| Moving command instruction | ARM9 dynamic text | RAM `0x0210BEE4`, CP932 | Localized | Use the ARM9-specific BLZ patcher |
| Command menu labels | Mixed: shared frame + runtime text | Runtime writer; entry 198 is shared | Investigated | Do not bake labels into shared cells; trace string source |
| Command buttons | Static sprite cells | `SPR_NCGR.PAK`, entry 1971, cells 21-34 | Localized in v145 | Use native transparent PNGs and the v145 patcher |
| SKIP button | Static sprite cell | `SPR_NCGR.PAK`, entry 2002, cell 2 | Localized in v144/v145 | Use `patch_xros_skip_button_png.py` |
| Taiki first shout | Static OBJ lettering strip | `SPR_NCGR.PAK`, entry 1993 | Localized | Use the dedicated cut-in patcher |
| Taiki DigiXros shout | Static OBJ lettering strip | `SPR_NCGR.PAK`, entry 1993 | Localized | Use the dedicated cut-in patcher |
| Menu tutorial image | Baked background tilemap | `BG_NCGR.PAK:87`, `BG_NSCR.PAK:84` | Localized prototype | Preserve 4bpp tiles, palette, and tutorial-only tile tail |
| Menu tutorial sequence | Baked tutorial frames | Nine editable frame captures | Needs English art review | Edit native-size PNGs; reinsertion workflow is documented |
| Intro cards | Static sprite cells | entries 33-41 | Localized | Keep palette banks and cell geometry unchanged |
| Title/logo | Static graphics | Red/Blue-specific title resources | Partial | Audit Red and Blue independently |

## Definition of done

A screen is not marked done merely because its screenshot looks English.
Contributors must provide the source target, a decoded before/after preview,
the changed-entry list, a cold-boot test, and save/load confirmation.
