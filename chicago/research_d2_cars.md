# C42: Driver 2 Chicago cars in Driver 1 (EXP offline research, 2026-10-13)

Sources: work/d2_CHICAGO.LEV and work/d1_LA.lev (read only); refs/OpenDriver2Tools/DriverLevelTool/driver_routines (level.h LUMP_CAR_MODELS = 28, d2_types.h carmodelentry_t and MODEL, models.cpp loader); refs/REDRIVER2/src_rebuild/Game/C (cars.c/h, cosmetic.c, handling.c, denting.c); chicago/NOTES.md (car texture pages >= 5).

## Lump 28 layout (loader, models.cpp)
- int modelCount; then 13 entries { int cleanOffset, damOffset, lowOffset } (-1 = none). base = 4 + 13*12 = 160 (the loader's r_ofs). Offsets are relative to base. Each model: int size, then MODEL (shape_flags, flags2, instance_number, tri_verts, zBias, bounding_sphere, num_point_normals, num_vertices, num_polys, vertices ptr, poly_block ptr, ...).
- MAX_CAR_MODELS = 13 (d2_types.h). REDRIVER2 uses MAX_CAR_RESIDENT_MODELS for CAR_MODEL arrays and car_cosmetics[] (cosmetic.c: colBox, wheel size/disp per resident model).

## 1. D2 Chicago (work/d2_CHICAGO.LEV, lump 28 = 123324 B, modelCount 27)
- Slots used: 0,1,2,3,4,8,9,10,12 (9 models; 5,6,7,11 empty). Each has clean, damage and low versions.
- Clean: 112-122 verts, 118-131 polys (slot 0: 120 v / 128 p, 9716 B; slot 9: 112 / 118, 8828 B). Damage version about 1 KB; low version 2.4-4.1 KB.
- Lump 25 (palettes): 15576 B. Lump 22 (motion capture, 12 entries): 240-3840 B each. Textures sit in car pages (see NOTES: pages >= 5 in D1).
- Role per slot (civ / cop / player / special) is NOT in the LEV: it is in the D2 exe (civ_ai.c, cop_ai.c, cars.c), not read here.
- Damage/denting, handling and wheel/collision data: exe-side in D2 (handling.c, denting.c, cosmetic.c car_cosmetics[]). None is in the LEV.

## 2. D1 LA (work/d1_LA.lev, lump 28 = 60264 B, modelCount 18)
- Slots used: 0,1,2,5,6,7,8 (7 models). Clean 4.2-9.7 KB; polys 71-127; damage 0.6-1.0 KB; low detail only in slots 0,1,2,5.
- Slots 0-2 show 0 verts in my parse (their header looks different; treat as approximate).
- Lump 25 (palettes): 2996 B (D2: 15576 B). Motion capture (22): 3 x 1536 B + 1096 B.
- Player car and civilian choice: D1 exe (cosmetics and car tables in the exe, per NOTES "D1 EXE cosmetics"; NOTES gives no exe addresses for them).
- Car texture pages must be >= 5 (NOTES, 0x8003BDC8 / CLUT table 0x800BEA04).

## 3. Differences that matter and the cheapest route
- Format: same lump 28 container and loader; D2 car models use the same MODEL struct. Limit: 13 slots per level (D2 uses 9 here, D1 LA 7).
- Polygons: D2 clean car models (about 120 verts / 128 polys) are the same size as D1's (116-127 verts). Pages and palettes are the bigger constraint (D2 palettes 15.6 KB vs D1 3 KB; car pages >= 5).
- Cheapest route keeping D1 handling and damage: data-only conversion of the D2 car models (lump 28, palettes 25 and their texture pages) into the Chicago level, with a slot map (D2 civ/cop/player to D1 slots) written into D1's car table in the exe. Handling and denting stay D1 (exe). Needs: (a) the slot map (exe data, not read yet), (b) texture pages >= 5, (c) the D1 damage-zone count per model (6 zones in D1 per NOTES, 0x8009B0A4 +0x114).
- Engine work only if D2's per-car handling must differ from D1's exe tables (not in scope).
- Open: the civ/cop/player role per slot, and whether D1's car table maps 1:1 to D2's 9 models.

## Part 2 (partial, offline)
- Role map D2 (REDRIVER2 civ_ai.c, cars.c): civ cars are created with InitCar(..., CONTROL_TYPE_CIV_AI, model) where the model is an index into residentCarModels[] (level slot -> resident slot). SPECIAL_CAR_SLOT marks mission/special cars (limo on mission 33, ambulance on mission 26). externalCopModel (civ_ai.c 3447, 3527) is the cop model. Which of the 9 Chicago slots is civ, cop or player choice is NOT resolved from these sources (needs the residentCarModels table values for Chicago, not read).
- Parse caveat (D1 slots 0-2 with 0 verts): OpenDriver2Tools models.cpp decodes lump 28 with one routine for both games ("TODO: D1 and D2 to have different decoding routines"), and the D1 path has an "older D1 LEV versions" branch. My parse uses the D2 MODEL header; slots 0-2 of D1 LA have a different header layout or a compressed/denting-only entry. Not confirmed.
- D1 role map (player, civ, cop per slot) and the per-city civ table in the exe: not resolved. The AI records at 0x80098950 are road-traffic records (0x50 each, 22 of them), not car model objects; the car slots are at 0x8009B0A4 + 0xDEC*k (8 traffic slots) and the player at 0x8009B0A4. Their model byte offset is not in the notes. Next: a runtime read of the car struct model field (guess the offset from the D2 CAR_DATA ap.model, then confirm on 10 cars in LA and Miami).

## Engine spec: car damage for Driver 2 cars (Polish, 14.10.; offline from the exe + REDRIVER2 denting.c)

### How Driver 1 damages a car
- Driver 1's damage code is Driver 2's DentCar, nearly 1:1. Function 0x8003E6A0, a0 = car index t7:
  0 = the player, others = AI cars.
- Per-car damage per zone (6 zones): `*(0x8009B0A4 + t7*0x18C + 0x114 + zone*4)`. 0x8009B0A4 is the car array,
  stride 0x18C, player = 0. The level is that value >> 10.
- AI car model slot: byte `0x80098950 + (t7-1)*0x50 + 0x10`.
- Zone tables come through 4 pointers, set at 0x8003E5D8..E4 from per-city tables (index = CITY `*0x80096834`):

  | pointer | from table | content |
  |---|---|---|
  | `*0x800973E0` | 0x8008A6DC | civ/cop vertices: rows by D1 slot 0..2 (`s0` = the AI car's model byte), 6 x 50 B, 0xFF-terminated |
  | `*0x800973E4` | 0x8008A6BC | player vertices: rows by car choice `*0x8009683C` (0..3 = slots 5..8) |
  | `*0x800973D0` | 0x8008A71C | civ/cop polygons: 6 x 70 B per row |
  | `*0x800973D4` | 0x8008A6FC | player polygons |

  The layout is exactly Driver 2's CHICAGO.DEN layout (verts 6x50, polys 6x70).
- Vertex denting (0x8003E788..0x8003E930) lerps clean -> damage model vertices (the lump 28 damage entry: the
  same format in both games).
- **UV shift, per polygon** (0x8003E990..0x8003EABC):
  - Each zone polygon gets level += damage >> 10, written into a byte per polygon at
    `0x800B09BC + t7*1024` (cleared first; 0x8003E934 picks the buffer).
  - Clamp, at 0x8003EA1C: `beqz t7` -> player branch.
    - AI cars (0x8003EA24..34): max 1.
    - Player (0x8003EA3C..4C): max 3.
  - Level to u offset, at 0x8003EA88: `beqz t7` -> player branch.
    - AI cars (0x8003EA90..98): `sll 7` = +128.
    - Player (0x8003EA9C..A4): `sll 6` = +64 per stage.
  - Draw (0x8003DF94, at 0x8003E098..E0C0): `u0/u1/u2 += offset[poly]`, the low byte of the three UV halfwords.
    The CLUT stays the clean texture's.

### Driver 2's rule (denting.c DentCar)
- level = clamp(sum of zone damage >> 10, 0, 2).
- offset = ((L^1) ^ ((L^1) | level)) * 64, where L = gHDCarDamageLevels[model][poly] (0 or 1, from the DEN file).
  - L = 0 (body panels): level 1 -> 0, level 2 -> +128.
  - L = 1 (lights, 3 texture stages): +64 / +128.
- D2 textures follow this: body damage twin at u+128; light stages at +64 / +128.

### What breaks with Driver 2 cars today
1. The zone tables are LA's (CITY 3), so the vertex and polygon numbers belong to LA's models. Driver 2 bodies
   dent and shift the wrong polygons.
   - (Correction 14.10., Infrastructure: D1 has ONE damage table set for all cities, DRIVER/DTL.BIN at 0x801F8BC0, and
    all 8 per-city pointer entries are identical. So Miami cars dent correctly in Chicago; C51 was not an issue.
    D2 civilian data goes into entry 4 of the civ tables, from <lev>.dmg.bin -> dmg_civ.bin via build_package.)
2. Player slots shift +64 per stage. D2 special textures (up to 192 wide) have no such layout, so damaged
   player cars show neighbour textures.

### Proposed engine change (Chicago-gated, plugin flag `lui at,0x9F08; lw at,0x2104(at)` as in AREA_SWITCH_CODE)
**A, minimal:**
- The player uses the AI rule in Chicago. Two sites:
  - 0x8003EA1C `beqz t7, 0x8003EA3C`: in Chicago do not branch (cap 1).
  - 0x8003EA88 `beqz t7, 0x8003EA9C`: in Chicago do not branch (`sll 7`).
- Both are `beqz` with a delay slot (0x8003EA20 `sb v0,(v1)`; 0x8003EA8C nop), so use a jump to a stub:
  `if (t7 == 0 && !chicago) goto player-branch`.
- Result: D2 bodies show their +128 twin at level >= 1. Lights jump straight to stage 3 (BACKL13).

**Zone tables:** when Chicago is active (and the car set is "d2"), point the 4 pointers at Chicago tables.
- Patch 0x8003E5C4..E4, or override the stored values right after 0x8003E5E4.
- Data: `polish_cars.write_damage_blob(work/d2_CHICAGO.DEN, OUT)` makes one blob (6.8 KB):

  | table | offset | size |
  |---|---|---|
  | civ_verts | 0 | 900 (3 rows) |
  | player_verts | 900 | 1200 (4 rows) |
  | civ_polys | 2100 | 1260 |
  | player_polys | 3360 | 1680 |
  | civ_levels | 5040 | 768 (3 x 256) |
  | player_levels | 5808 | 1024 (4 x 256) |

  Rows follow the slot map (civ/cop = D1 slots 0, 1, 2 <- D2 3, 0, 1; player choice 0..3 <- D2 8, 9, 10, 12).
- Where the blob lives (plugin RAM, or a spare lump read at level load) is Infrastructure's call.
- Sample: `work/var_polish_c42_4_day.dmg.bin`.
- (No Miami-set mismatch: all cities share one table set; see the correction above.)

**B, D2-exact (optional, after A):**
- Replace the clamp and conversion (0x8003EA1C..0x8003EABC) in Chicago with clamp 2 and
  `offset = ((L^1) ^ ((L^1)|level)) * 64`, L from the *_levels rows (by the same s0 row index).
- Lights then get their 3 stages, and level 1 leaves bodies clean, as in Driver 2.

### Open
- Per-model handling, collision box and wheel tables are separate exe tables (not covered here).
- The 9-vs-7 model question stands.

## C57-C59 causes (EXP, 2026-10-16, offline; no game runs)
### C57 smaller cars: missing model scale in lump 28 (cause found)
- polish_cars.lump28() copies the D2 MODEL bytes unchanged (vertices, bounding_sphere). worldscale.SCALE = 1.32 (D2 -> D1 units) is applied to positions only (to_d1), not to the car models.
- Evidence (MODEL bounding_sphere): D2 Chicago civ slots 0-4: 385-406; D1 LA civ/cop slots 0-2: 515-606; D1 Miami 555-608. Ratio ~0.65-0.76, which is 1/1.32 = 0.76 within noise. So the D2 bodies are authentic size but in D2 units, shown 1.32x too small.
- Fix route: scale the mapped D2 models by 1.32 when writing lump 28 (vertex coordinates and bounding_sphere; the model's own pivot is already at 0). Check the same for the car cosmetics (wheel displacement, light positions) once they are used. Vertex extents were not measured (pointer decode not done).
### C58 cars not rendered close (candidates, not verified)
- Candidates in the lump 28 conversion: (a) bounding_sphere is unscaled (above), so object cull (0x8002C5F0 uses the sphere as margin) and the clean/low choice work on a too-small sphere; (b) D1 LA slots 6-8 (player cars) have no low model (low = -1) while the D2 slots carry low models, so the low path may read a model the exe expects to be absent; (c) slot map 5..8 <- 8, 9, 10, 12 with D2 slots 8 and 10 much larger (bsphere 663-672): the cull sphere and the model size disagree.
- Next (one run): poke the D2 car to 2 m and check the clean model draw; compare the bsphere cull with the scaled sphere.
### C59 civilian traffic uses the cop model (cause found)
- D1 slot 0 is the cop model (LA: COP1..5) and the converter maps D2 civ residentCarModels[3] to D1 slot 0 (polish_cars.py D1_FROM_D2 = {0: 3, ...}) with the reason "Driver 2's cop is a civilian model". Civilian AI cars spawn with their D1 model slot (AI record byte 0x80098950 + (car-1)*0x50 + 0x10, see the damage section), so every civ car in slot 0 is drawn with the cop body.
- Fix route: map D2 civ to D1 slots 1 and 2 (plus 3-4 if D1 has them unused) and keep slot 0 as the D1 cop model (LA COP1..5) unless a D2 police car is found in the Chicago lump (none in the 9 slots).
### Spec: D2 hitboxes, D2 player car, damage on all D2 cars
- D2 CAR_COSMETICS (REDRIVER2 dr2types.h:211): headLight, frontInd, backInd, brakeLight, revLight, policeLight, exhaust, smoke, fire (SVECTOR each), wheelDisp[4], extraInfo, powerRatio, cbYoffset, susCoeff, traction, wheelSize, cPoints[12] (collision points), colBox (collision box), cog (centre of gravity), twistRateX, ... car_cosmetics[] is indexed by resident model (cosmetic.c).
- Hitboxes: D1 uses its own collision/handling per car slot in the exe; D2's colBox and cPoints would need a per-slot table in the exe (guest code, relocated table or patch of the collision routine). Effort: medium-high.
- D2 player car: the player's handling (powerRatio, susCoeff, traction, wheelSize) and cosmetics come from car_cosmetics[] per model; D1 has them per slot in the exe. Needs the same per-slot table replacement plus the choice-to-slot map (D1 slots 5-8 = player cars). Effort: high.
- Damage on all D2 cars: the dent tables (0x800973E0 etc., per slot, from the per-city tables at 0x8008A6DC) must cover every mapped slot; the damaged model (lump 28 'damage' entry) is present for all D2 slots (verified). Damaged textures: the damage texture pages must be in the car pages (>= 5). Effort: medium (data), high if the 6 zones of a D2 car need D1-sized tables.

## C57/C59 verification run (EXP, 2026-10-16, scratchpad converter copy, not the shared files)
- Converted work/var_exp_cars1_day.lev (14.4 MB, 1216 models) with CHI_POLISH_D2CARS=mixed, CHI_POLISH_CARMIX_COPFULL=1, CHI_POLISH_CARS_SCALE=1.32, from a scratchpad copy of chicago/*.py and work/ (shared files untouched).
- Diff (scratchpad only, to be adopted behind CHI_POLISH_D2CARS):
  - polish_cars.py: D1_FROM_D2 = {1: 3, 2: 0, 5: 8, 6: 9, 7: 10, 8: 12} (was {0: 3, 1: 0, 2: 1, ...}): civilians only in slots 1-2.
  - polish_carmix.py: CIV_SLOTS = (1, 2); COP_SLOT = 0 with slot 0 taken from the car set (src "K"); CAR_SCALE = env CHI_POLISH_CARS_SCALE (default 1.32); new scale_model(): bounding_sphere (+8) and vertices (count +12, offset +16, 8 B per SVECTOR) scaled, applied to every D2-sourced model (src "D").
  - Known gap: the mixed damage rows (<lev>.dmg.bin, slots 0-2) are still built from D2 civ rows, so slot 0 (cop) would get a civ damage row. Needs the same change in damage_civ().
- Game run (one, devtest/exp, port 4450, dt.launch, start = l_down_e D2 -101562,106946, standing, 6 shots at 4 s): loaded (Chicago, CITY 3, pos 23662,164,54070), no fatal. No civilian car in view in any of the 6 frames, so C57 (size vs D1), C58 (visibility near/far) and C59 (cop body on civilians) are NOT verified by this run. Sheet: devtest/exp_work/cars1/exp_sheet.png.
- Next: a traffic-dense spot (cellprobe CP_NEAR=1 puts the player next to the nearest live car) for the same level, and the same shot for a D1 baseline (var_roads_b11_day.lev) for the size comparison.

## C57-C59 second run (EXP, 2026-10-16): traffic missing in the mixed build
- Damage rows: damage_tables() already follows the slot map, so the cop row (slot 0) gets the empty row (0xFF), and slots 1-2 get D2 3 and D2 0. No extra change was needed; the earlier "known gap" was wrong.
- Build: work/var_exp_cars2_day.lev (same converter output as cars1; cars1 deleted).
- cellprobe CP_NEAR=1 at l_down_e: baseline (var_roads_b16b_day.lev) found traffic at once (near car at 1442 units, models 2 and 3); the mixed build found NO traffic car (no near lines, spawn.png only).
- Scan (60 s, 5 s steps, same spot): baseline 10-11 active AI cars; mixed build 0 active cars at every sample. So C58 (vanishing) and C59 (cop body) cannot be judged in the mixed build: no civilian spawns. Traffic spawn is blocked by the mixed build (not diagnosed: candidates are the civ slots 1-2 (only 2 models), the cop slot 0 without its pages, or the residentCarModels indices, which the baseline uses as models 2 and 3).
- Size baseline: base near0-5 shots (devtest/exp_work/cars2/build_base) exist; no mixed car to compare.
- Sheet: devtest/exp_work/cars2/side_by_side.png (base near0, near3, near5; mixed spawn).

## Spawn diagnosis and cars3 (EXP, 2026-10-16)
- Cause of zero spawns: the converter run lacked CHI_ROADS=1. NOTES (mix3 entry): mix1/mix2 lacked the road lumps, so no AI cars spawned; the mix4 probe had CHI_ROADS=1. The slot map change was not the cause.
- C59 rule kept: map {1: 3, 2: 0, 5..8: 8, 9, 10, 12} (civilians only in slots 1-2; slot 0 = the car-set cop). No change needed for the rule.
- cars3 = mixed + CHI_ROADS=1 + CHI_POLISH_CARS_SCALE=1.32 + CHI_POLISH_CARMIX_COPFULL=1 (work/var_exp_cars3_day.lev; cars2 deleted).
- cellprobe CP_NEAR=1 at l_down_e: traffic spawns (AI models 2, 3, 2, 2, 9, 3; no model 0 in six samples, so no cop body seen). Baseline: models 2 and 3.
- Size: not measurable from these shots (player-to-car distances 10k-19k units in cellprobe's near frames). Side-by-side: devtest/exp_work/cars3/side_by_side.png.
(see the quay section below)
