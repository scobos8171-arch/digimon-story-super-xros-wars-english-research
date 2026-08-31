# Xros command-ring localization: corrected Phase A

## Immediate goal

Identify the code and source records that supply the seven Japanese captions on
the red command ring. Do not modify the ROM until that provenance is proven.

## Confirmed facts

- SPR_NCGR.PAK entry 198 is the live red hex shell/icon resource.
- The Japanese captions are a separate runtime layer; replacing entry 196 or
  entry 198 artwork does not replace them.
- Address 0x020C68C0 constructs the command ring and its seven slots.
- Addresses 0x0204C1E4 and 0x0204D03C manage slot/navigation geometry. They are
  not proven caption setters and are no longer primary trace targets.
- Earlier execution traces reached the constructor and font/text paths, but the
  scripts requested nonexistent pc, lr, and sp register aliases. This lost the
  return address needed to identify each caller.
- This DeSmuME build exposes the registers as r15, r14, and r13.

## Phase A gates

1. Corrected runtime trace: capture real r14 caller addresses and pointer data
   during one ring opening.
2. Static follow-up: disassemble those callers in the proven decompressed ARM9
   image at work/decomp/xros_v52_runtime_proven/binaries/arm9_0x02000000.bin.
3. Source proof: identify the seven message IDs, glyph arrays, or pointers.
4. Small test patch: either suppress only those seven caption submissions
   (icon-only fallback) or replace their records with short English labels.
5. Cold-boot verification: test the ring plus adjacent menus before applying
   the same mechanism to remaining Japanese UI.

## Tooling decision

A broad MCP server is postponed. Codex already has local file/process tooling,
and an MCP wrapper would not add CPU state that the emulator does not expose.
The available DeSmuME source includes a GDB stub, so a Dev+ build is the fallback
if the corrected Lua execution hooks still cannot identify the caption owner.

