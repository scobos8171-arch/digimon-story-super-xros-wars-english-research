# Xros Evolution Complete US v3 — Party Level 15 AR Code

This code is specific to the localized v3 ROM with SHA-256:

`90432395bc8aaa67fcc3ef58b90d6ee08732107f4c2323c055d28db8a17fdf87`

Runtime evidence comes from `work/battle-captures/level15_before.dst`. The six
field-party records use a `0x80`-byte stride, with the displayed level byte at
record offset `+0x34`:

| Slot | Digimon | Level address | Captured value |
|---:|---|---:|---:|
| 1 | Shoutmon | `0x021F071C` | 9 |
| 2 | Spadamon | `0x021F079C` | 9 |
| 3 | Starmon | `0x021F081C` | 9 |
| 4 | Ballistamon | `0x021F089C` | 8 |
| 5 | Agumon | `0x021F091C` | 6 |
| 6 | Tentomon | `0x021F099C` | 3 |

## One-shot Action Replay code

Press **Select** while the party/status list is loaded:

```text
94000130 FFFB0000
221F071C 0000000F
221F079C 0000000F
221F081C 0000000F
221F089C 0000000F
221F091C 0000000F
221F099C 0000000F
D2000000 00000000
```

The code changes only the six live level bytes. It does not independently
recalculate growth stats or experience. Disable the cheat after activation,
change screens, and verify the levels and DigiXros condition before saving.
Keep the pre-cheat save-state until persistence and stat recalculation have
been confirmed.

If the game rebuilds these records from its save data when the screen changes,
the levels will revert. In that case this code remains useful for identifying
the condition check, but a permanent version must patch the authoritative save
records or the level getter rather than this field-party cache.
