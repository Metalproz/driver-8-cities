# Driver 2's exact sky dome order in Driver 1 (C46 follow-up, engine proposal; Polish 14.10.)

For later, only if the user wants it after the "sky d2" probe. Today's data-only sky (polish_sky.py) squeezes
D2's rows into D1's 3 bands. Exe addresses are from the original exe (`dt.py dis --orig`).

## Driver 1 today (3 bands)
- Dome = models 0..3: LA's SKY01A..SKY04A, 12 polygons each (3 bands x 4 pieces).
- The dome loop at 0x800500FC..0x800501D0 calls 0x8004F7C8(model, base) for each model:
  - model 0 (0x80050124, `move a1,zero`): base 0
  - model 1 (0x8005015C, `addiu a1,zero,0xc`): base 12
  - model 2 (0x80050194, `0x18`): base 24
  - model 3 (0x800501CC, `0x24`): base 36
- Per polygon i, 0x8004F9F8..0x8004FA10 reads a piece number from the byte table **0x8008AA8C**`[base + i]`
  (48 bytes) and calls 0x8004F34C. That routine takes:
  - UVs from the record **0x800BDE40 + 8*piece** (u0v0 u1v1 u2v2 u3v3, read at 0x8004F6E4..0x8004F744);
  - the CLUT from **0x800BDD20 + 2*piece** (0x8004F748..0x8004F75C);
  - the tpage from gp+0xD88.
- Model UVs are ignored. The sky loader (0x8004EF44..; table writes at 0x8004F030 CLUT and 0x8004F0D8 UV) fills
  12 pieces = 3 image rows x 4 columns from SKY.BIN.

## Driver 2 (REDRIVER2 sky.c)
- Dome = BASE1..BASE4 (Chicago models 0..3), **20 polygons each**.
- `LoadSky` builds 28 pieces = 7 groups x 4 columns:
  - g0: single colour, the row-0 top pixel (the cap);
  - g1: row 0; g2: row 1; g3: row 1 flipped; g4: row 0 flipped; g5: row 2; g6: row 2 flipped.
  - Flipped = v0/v1 and v2/v3 swapped (v + 83 <-> v).
- `PlotHorizonMDL`: piece = `HorizonTextures[HorizonLookup[level][k] + i]`.
  - Chicago: model 0 and model 2 use offset 0, models 3 and 1 use offset 20.
  - `HorizonTextures` = {0..19, 0..7, 20..27, 16..19} (40 bytes).
  - Models 0/2 get cap, row 0, row 1, row 1f, row 0f. Models 1/3 get cap, row 0, row 2, row 2f, row 0f.

## Proposed change (Chicago-gated, plugin + a few exe words)
1. **Converter:** for Chicago put D2's BASE1..4 (20 polygons) into model slots 0..3 instead of LA's SKY01A..04A.
   Their textures don't matter (UVs are ignored).
2. **Piece table:** D2's 40-byte HorizonTextures fits D1's 48-byte table at 0x8008AA8C. The plugin writes it while
   Chicago is loaded and restores LA's 48 bytes otherwise.
3. **Bases:** model 0 = 0, model 1 = 20, model 2 = 0, model 3 = 20. Patch the immediates at 0x80050128 (stays 0),
   0x80050160 (0xc -> 20), 0x80050198 (0x18 -> 0), 0x800501D0 (0x24 -> 20), Chicago-gated (or plugin-written
   words while Chicago is loaded).
4. **28 pieces instead of 12:** move the UV records (28 x 8 B) and CLUT ids (28 x 2 B) to mod memory.
   - Patch the plot routine's two bases (`lui/addiu` at 0x8004F6E4/E8 and 0x8004F748/4C).
   - After each sky load the plugin builds piece 4g + c from D1 piece 4r + c (r = 0, 1, 1, 0, 2, 2 for g1..g6):
     same CLUT, v swapped for g3/g4/g6. g0 = all four UVs at row 0's (u0, v0).
   - Simpler alternative: let the loader write 28 entries.
5. **SKY.BIN:** ship D2's three rows 1:1 (half resolution, 64x42 per piece) instead of the squeezed panorama.
   This is a new polish_sky mode (e.g. CHI_POLISH_SKY=d2rows); the D2 rows need no squeeze.

Cost: 4 immediates + 4 base loads + a 40-byte table write + a post-load fill (about 30 lines of plugin), all
Chicago-only. Other cities keep LA's/their own 12-piece dome unchanged.
