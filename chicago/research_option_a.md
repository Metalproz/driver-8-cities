# Option A groundwork: read D2 content from the player's discs (EXP, 2026-10-16)

## 1. Reader prototype (scratchpad, not in the shared tree)
- chicago/optiona/d2iso.py (prototype; adopted 16.10. as chicago/psxiso.py, prototype removed) (stdlib only): ISO9660 on MODE2/2352 BIN. Sector data at offset 24: Form 1 = 2048 bytes, Form 2 = 2324 bytes (submode 0x20). Commands: tree, get (--raw = whole 2352-byte sectors for XA/STR), find.
- Images: games/Driver 2 (USA) (Disc 1) (v1.1).bin (647 MB) and (Disc 2) (v1.1).bin (603 MB), cues SLUS_011.61 (Disc 1) and the Disc 2 SLUS.

## 2. Validation (md5 vs the hand-copied work files; all identical on both discs)
| D2 file (disc path) | our copy | size | result |
|---|---|---|---|
| DRIVER2/LEVELS/CHICAGO.LEV | work/d2_CHICAGO.LEV | 10915840 | identical (disc 1 and 2) |
| DRIVER2/NLEVELS/CHICAGO.LEV | work/d2_CHICAGO_night.lev | 10915840 | identical (disc 1 and 2) |
| DRIVER2/LEVELS/CHICAGO.DEN | work/d2_CHICAGO.DEN | 12727 | identical |
| DRIVER2/LEVELS/CHICAGO.LCF | work/d2_CHICAGO.LCF | 3120 | identical |
| DRIVER2/DATA/SKY0.RAW | work/d2_SKY0.RAW | 327680 | identical |
| DRIVER2/SOUND/MUSIC.BIN | (no local copy in the tree) | 777944 | extracted, md5 b153580d82d6091a3b234179873bc1b2 |

## 3. Inventory (sizes in bytes)
- Disc 1 (v1.1): DRIVER2/ with SLUS_011.61, SYSTEM.CNF, FRONTEND.BIN 50406, LEAD.BIN 24272, MCARD.BIN 115336, PATH.BIN 47044; DATA/ (SCRS.BIN 7898, SKY0..3.RAW 327680 each, CARCONT.RAW 393216, CITY.RAW, CITYBACK.RAW, GFX.RAW, FEFONT.BNK, MCTEXT/, CARS/ (CARBACK/CCARS/HCARS/RCARS/VCARS.RAW), CUTS/); FMV/ (0..9: RENDER*.STR/SBN, FMV.EXE 174080); LEVELS/ (CHICAGO, HAVANA, RIO, VEGAS: .LEV 10915840 each, .DEN 12727, .LCF 3120); NLEVELS/ (same 4 cities, night, 10915840 each); MLEVELS/ and MNLEVELS/ (mission variants, 1.7-2.6 MB each); SOUND/ (MUSIC.BIN 777944, VOICES2.BLK 2377156); MAPS/, MISSIONS/, REPLAYS/, TRAILS/, XA/, GFX/.
- Disc 2 (v1.1): same tree (LEVELS/NLEVELS/MLEVELS/MNLEVELS for the same 4 cities; FMV 0..9 with other RENDER numbers; MCARD.BIN; SYSTEM.CNF).
- The two discs are not the same: Disc 1 holds FMV 0,1,9 and the SOUND/ folder; Disc 2 holds FMV 0,1,2,9 with different renders. The Chicago LEVs, DEN, LCF and SKY0 are on both.

## 4. Audit: what the Chicago package and converter use from D2
| file | where | class |
|---|---|---|
| assets/chicago.lev (13.1 MB) | converted from DRIVER2/LEVELS/CHICAGO.LEV (convert.py) | (b) converted by code |
| assets/chicago_night.lev (15.2 MB) | converted from NLEVELS/CHICAGO.LEV | (b) |
| assets/sky.bin (281836) | polish_sky.py: D1 SKY.BIN + D2 DATA/SKY0.RAW (layout identical) | (b), plus optional hand variants |
| music: var_polish_music_chicago.BIN -> MUSIC.BIN | polish_music.chicago_music(d1, d2): D1 MUSIC.BIN + D2 MUSIC.BIN | (b) |
| assets/chicago_preview.bin (14624) | design/previews/out/CHICAGO (Design-made picture) | (c) hand-made, needs a recipe or a Design source |
| assets/chicago_slot.bin (116) | generated sidecar (entry words from the LEV header, LA/Chicago starts) | (b) generated |
| work/d2_CHICAGO.LEV/.DEN/.LCF, work/d2_CHICAGO_night.lev, work/d2_SKY0.RAW | hand copies of the user's disc files | (a) direct D2 files: read from the disc at setup instead |
| work/d2_CHICAGO.DEN (damage tables) | build_package/polish_cars: damage rows | (a) direct (from the D2 DEN) |
| D2 car models and palettes | taken from the D2 LEV lumps 25/28 (polish_cars, polish_carmix) | (b) |
- D1-derived files used as input or shipped instead of read from the player's D1 disc: work/d1_LA.lev, d1_MIAMI.lev, d1_NEWYORK.lev, d1_FRISCO.lev, d1_IVIEW.lev, d1_FLAT.lev (hand copies of the D1 LEVs: read from the D1 disc); the D1 SKY.BIN and MUSIC.BIN are read by the converter from the work tree, not the disc; FRONTEND.BIN and the disc directory records are patched in the disc overlay (build_package, disc_user overlays). Under Option A: the patch recipe must read the player's D1 disc.
- Recipes still needed for class (c): chicago_preview.bin (Design output), any Polish bin (var_polish_sky_*, var_polish_music_*) that is adopted as a default.

## 5. Step plan for Infrastructure (Strategy, 2026-10-16; user: Option A is the NEXT step, priority)
Goal: every D1/D2 input comes from the player's disc images at setup; nothing derived from either game is shipped; Driver 1 stays the only recompiled program. One disc version each: D1 USA v1.1 (SLUS_00842), D2 USA v1.1 disc 1 (SLUS_01161) + disc 2 (SLUS_01318); reference images in D:/recomps/games (.bin + .cue).
1. **Disc registry**: the app learns the D2 discs like it knows the D1 disc (disc.cfg / project-manifest `disc_count`; D2 disc 1+2 entries, checked by volume id/serial + md5 of known files). Missing or wrong disc = clear message.
2. **Shared reader module**: adopt chicago/optiona/d2iso.py (done 16.10.: chicago/psxiso.py; stdlib, MODE2/2352, Form 1/2, tree/get/find) as the one reader for D1 and D2 images. It already reproduces our d2_* copies byte-for-byte.
3. **Input layer**: replace the hard paths with a resolver: convert.py `CHI_D2_LEV` / work/d2_CHICAGO.LEV, NLEVELS/CHICAGO.LEV, CHICAGO.DEN/.LCF, DATA/SKY0.RAW, SOUND/MUSIC.BIN, and the D1 side work/d1_*.lev + the D1 SKY/MUSIC inputs → read from the registered disc images (cache in a setup cache dir, keyed by disc md5). Keep env overrides for experiments. The existing work/d1_*, d2_* files stay untouched (user inputs).
   Hard-coded D2/D1 reads found by Polish (16.10.), all must go through the resolver: polish_sky.py `RAW = work/d2_SKY0.RAW`; build_package.py minimap_params `Overlay("work/d2_CHICAGO.LEV")` (+ polish_map.py __main__); polish_cosmetics.py work/d2_CHICAGO.LCF + .LEV defaults and `EXE = disc/SLUS_008.42.orig`; convert.py mixed car set DEN fallback work/d2_CHICAGO.DEN; texrepack.py `DAY_LEV` (l.242) + open("work/d2_CHICAGO.LEV") (l.802); polish_music.py MUSIC.BIN (command line). Already via CHI_D2_LEV: polish_slopes, polish_areas (cache next to the D2 file → move cache to the setup cache dir), polish_map.lump, polish_carmix/polish_cars. Design asset derived from D2: SKYMOON_24.png (moon sprite) → class (c), needs a recipe from the D2 sprite.
4. **Package build at setup**: one command = read discs → convert day+night → build_package → install into the player's build; deterministic; the cache avoids re-converting on every test. dt.prepare, probes.py and publish_playable.py use the same path.
5. **Ship audit**: nothing from section 4's classes (a)-(c) ships. chicago_preview.bin (class c) gets a recipe or stays out until the user picks the preview picture. FRONTEND/directory patches stay patches against the player's D1 disc.
6. **Check**: one clean build that reads only the disc images (resolver pointed away from work/ by a switch, files untouched) → md5 of the produced chicago.lev / night / sky / music equals today's b16b build with the same switches; one sanity run at a spot; then a probe for the user.
Out of scope: no D2 recompilation, no other regions, the PS1 disc builder (M8) much later.
