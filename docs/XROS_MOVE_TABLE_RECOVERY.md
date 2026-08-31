# Super Xros Wars Move Table Recovery

## Verified table layout

ARM9 function `0x0203D6EC` is a bounds-checked record accessor. It returns:

`0x020FC204 + move_id * 0x2C`

for IDs `0..0x4FB`, establishing **1,276 records of 44 bytes each**. ARM9
initialization function `0x0203DA88` patches record offset `+0x1C` from an index
into a linked effect list whose entries are 14 bytes and begin at `0x020E092C`.

Overlay-0 resolver `0x021F5BFC` consumes these records and writes a 52-byte
action-result structure. Verified/probable stages are:

1. `0x021F4BDC`: hit/accuracy resolution.
2. `0x021F516C`: base damage calculation.
3. `0x021F55D4`: critical check; `0x021F5718` applies the critical multiplier.
4. `0x021F747C`: resolves the active move element from an effect descriptor.
5. `0x021F6B50`: checks either of two target resistance fields; damage is divided
   by four through `0x021F573C`, clamped to at least 1.
6. `0x021F6B94`: checks either of two target weakness fields; damage is doubled
   through `0x021F5734`, clamped to at least 1.
7. A target condition can halve damage through `0x021F574C`.
8. A final global multiplier and minimum-one clamp are applied.

The two packed descriptors at offsets `+0x0C` and `+0x10` expose:

- bits `0..6`: effect opcode;
- bits `7..13`: magnitude/chance field;
- bits `14..15`: target flags;
- bits `16..31`: power or effect parameter.

Offsets `+0x14`, `+0x16`, `+0x18`, and `+0x1A` are separate 16-bit fields, not
additional packed descriptors. These meanings are based on direct accessor
behavior. Specific opcode names and several header fields remain pending and are
intentionally not guessed.

The localized move-name block begins at MESPAK00 string index **3191** and contains
exactly 1,276 names, matching the record count. Its preceding parallel block begins
at 1915; the two starts differ by exactly 1,276. Verified joins include:

- move 0: Heavy Speaker;
- move 199: fire punch;
- move 217: Petit Fire RV;
- move 232: Petit Devine RV (source localization spelling).

## Runtime fixtures

- Spadamon Fire Punch: 31 damage; adjacent evidence supports 8 SP.
- Shoutmon Petit Fire RV: 26 damage, 8 SP.
- Starmon Petite Divine RV: 26 damage, 8 SP.
- Ballistamon signature move versus Minotarumon: Resist, 2 damage, 8 SP.

The resisted Ballistamon fixture matches the resolver's quarter-damage branch and
minimum-one clamp. The visible `Resist` label appears to be transient result state,
not persistent combatant status offset `+0xF1`.

## Extractor

Run:

```powershell
py tools\nds_decompiler\xros_move_table.py `
  work\decomp\xros_evolution_us_v3\binaries\arm9_0x02000000.bin `
  work\extracted\xros_evolution_us_v3\moves.json `
  --message-pak work\decomp\xros_evolution_us_v3\nitrofs\MSG\MESPAK00.PAK
```

The resulting JSON contains every record and clearly labels uncertain fields.
The next recovery step is to join IDs to localized names and decode the 14-byte
linked effect entries and effect opcodes.
