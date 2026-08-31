# DS Digimon Story ARM Decompressor Integration

The project uses the Nintendo DS backwards-LZ decoder in
`tools/rom_importer/nds.py` through the extraction pipeline in
`tools/nds_decompiler/pipeline.py`.

## Upstream validation

The implementation was checked byte-for-byte against both fixtures supplied
with `acemon33/DSDigimonStoryARMDecompressor`:

- Lost Evolution `arm9.bin` -> `arm9_decrypt_with_main.bin`: PASS
- Lost Evolution `overlay9_0.bin` -> `overlay9_0_dec.bin`: PASS

The upstream TGUI, SFML, and tinyfiledialogs dependencies implement its GUI;
they are not required by the decompression algorithm.

## Xros result

`DXWBLUEFLARE` v52 extraction:

- ARM9: 696,396 stored bytes -> 1,145,912 decoded bytes
- Six ARM9 overlays detected
- All six overlays BLZ-decompressed successfully

Manifest: `work/decomp/xros_v52_runtime_proven/manifest.json`

## Dusk result

`DS2_USA_DUSK` extraction:

- ARM9 and all 18 overlays are already stored uncompressed
- They are still exported through the same normalized analysis pipeline

Manifest: `work/decomp/dusk_clean_usa/manifest.json`

## Commands

```powershell
python -m tools.nds_decompiler.cli extract GAME.nds --output work/decomp/GAME --no-nitrofs
python tools/nds_decompiler/blz_tool.py arm9.bin arm9.dec.bin --arm9
```
