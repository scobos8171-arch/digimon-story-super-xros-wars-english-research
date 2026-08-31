# Xros Blue Command Menu Runtime Findings

## Scope

This note tracks the command/party menu still visible in Japanese in the
`v51 V46 BASE ALL FINISHED UI` build. It deliberately separates observed
runtime behavior from assumptions based only on ROM archive contents.

## Verified runtime symptoms

- Seven red command buttons remain Japanese.
- The horizontal instruction banner remains Japanese.
- The currency/possession label displays `Shoji`.
- The short party name displays `Ballista` rather than `Ballistamon`.

## Verified source mapping

### Instruction banner

The earlier claim that this banner was `BG_NCGR.PAK` entry 163 was disproved
by rendering that member: it is unrelated title/copyright artwork. The banner
is rendered text and must be traced through the runtime text layer.

### `Shoji`

The ASCII text `Shoji` exists in NitroFS file `MSG/MESPAK01.PAK` at file offset
`0xD7BC` (ROM offset `0x00BF79BC`). It is live message/data text, not baked into
the command-button artwork.

### Command buttons — resolved source mismatch

The complete V2 capture proves that the lower-screen OBJ bank uses
`SPR_NCGR.PAK` entry **198**, not entry 196:

- 229 distinct live OBJ tiles match entry 198;
- this is 100% of entry 198's nonblank NCGR tiles;
- it covers 77.104% of all distinct nonblank live OBJ tiles;
- after subtracting entry 198, the remaining 68 live tiles do not match any
  NCGR member in the ROM.

Rendering entry 198 shows the red button frames and the Japanese B/Back button,
but the seven red buttons are intentionally blank. Therefore their Japanese
labels are generated at runtime from the text/font layer. Entry 196 is a
different UI resource, so every previous entry-196 artwork patch was writing
valid pixels to an inactive member. Save-state caching and a shadow archive
are no longer the leading explanation.

The remaining 68 unmatched OBJ tiles are consistent with runtime-generated
glyph tiles. The completed V3 capture adds all 4 MiB of ARM9 RAM so their
encoded source strings and renderer can be traced.

## Runtime evidence

The V2 capture is stored under `outputs/Xros UI Runtime Probe Test v2/` and
contains complete mapped BG/OBJ banks, palettes, OAM, and VRAMCNT registers.
It established the correct graphic member. The V3 capture is stored under
`outputs/Xros UI Runtime Probe Test v3/` and includes complete main RAM.
Standard Shift-JIS scanning found the active overlay-0 strings:

- `アイテム` at `0x0221A254`;
- `さくせん` at `0x0221A31E`, `0x0221A33C`, `0x0221A35C`, and `0x0221A37C`;
- `もどる` at `0x0221AA34`, `0x0221AA94`, and `0x0221AAB4`;
- `わざ` at `0x0221A7AC`, `0x0221A7BC`, `0x0221A7CC`, and `0x0221A84C`.

`ステータス`, `めいれい`, `たいれつ`, `もちもの`, `マップ`, `じょうほう`,
`デジクロス`, `バトルけっか`, and `つぎへ` are absent from the full capture
in Shift-JIS, CP932, and UTF-16LE. They therefore use another source or
encoding and must not be patched by blind Shift-JIS replacement.

A paired runtime package now captures the circular command ring and Battle
Results separately. Comparing those snapshots will:

1. find the live encoded label table or its copied working buffer;
2. identify pointers/references from the active overlay;
3. separate runtime text from the one baked B/Back cell;
4. support a minimal text-layer patch plus an entry-198 B/Back patch.

## Localization targets

- `めいれい` -> `Orders`
- `デジクロス` -> `DigiXros`
- `たいれつ` -> `Formation`
- `アイテム` -> `Items`
- `さくせん` -> `Tactics`
- `もどる` -> `Back`
- `バトルけっか` -> `Battle Results`
- `つぎへ` -> `Next`
- `Smartness` -> `Wisdom`
- `Swiftness` -> `Speed`
- `Mamori` -> `Defense`
- `Yujo` -> `Bond`

## Safety rule

No further release build should be labelled UI-complete until a cold-boot
runtime capture proves every target screen changed and the sword/skills path
still opens without a black screen.
