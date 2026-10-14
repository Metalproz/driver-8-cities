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
