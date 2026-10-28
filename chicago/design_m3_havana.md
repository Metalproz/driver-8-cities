# Milestone 3 design: city-independent converter + Havana in its own slot (Infrastructure, 23.10., DRAFT for the user)

Goal (user 23.10., agenda A step 3): (1) the converter / package / plugin work for any Driver 2 city, not just Chicago;
(2) Havana gets its OWN reserved slot on the selector's page 2 "Driver 2 cities", next to Chicago; LA, Chicago and the
Driver 1 extras stay as they are. Design only: no shared code or exe changes until the user decides.

## 1. Havana's data (Option A: read from the player's Driver 2 disc 1)

All Havana inputs are on D2 disc 1 (checked in the image): `DRIVER2/LEVELS/HAVANA.LEV` (10.9 MB), `NLEVELS/HAVANA.LEV`
(night), `LEVELS/HAVANA.DEN` (damage zones), `LEVELS/HAVANA.LCF` (car cosmetics), the sky `DATA/SKYn.RAW` of Havana,
`SOUND/MUSIC.BIN` (Havana's songs), `SOUND/VOICES2.BLK` (car banks: REDRIVER2 `car_banks[1]`). `inputs.INPUTS` gets the
same entries as Chicago's (`d2_HAVANA.LEV` ... with size + md5), read through psxiso like today; nothing is shipped.

Havana vs Chicago (D2 headers, measured):

| | Chicago | Havana |
|---|---|---|
| cells | 512 x 768 @ 2048 | 512 x 448 @ 2048 (58 % of Chicago's area) |
| regions with data | 134 of 16 x 24 | 92 of 16 x 14 |
| cell objects / cell data | 181 228 / 333 293 | 103 659 / 172 541 |
| models | 1205 | **1529** (D1 model table 2048: fits) |
| texture pages / areas | 70 / 19 | 52 / 11 |
| model spool buffer | 23 blocks | **63 blocks** (largest area; must fit D1's spool buffer, check first) |

Smaller world, fewer pages and cell objects: the RAM / VRAM budget should be easier than Chicago's. The two risks are the
model count (1529, many small props) and the 63-block area model spool (D1's buffer size is the limit; Chicago needed the
C30 carry path for 23).

## 2. A 6th city slot: what it needs

Facts (NOTES "Level slots", EXP 12.10.): CITY 0x80096834 indexes 8-entry tables: level paths 0x80086EC0 (0 MIAMI, 1 FRISCO,
2 IVIEW, 3 LA, **4 FLAT**, 5 NEWYORK, 6 TRAIN, 7 CREDITS/Newtown), names 0x8008B328, 4 eight-case CITY switches (jump
tables 0x800108A8 sky number, 0x80010990, 0x80010A00, 0x80010A20 cosmetics (now by CARSET)), a 6-case switch 0x80010C18
(6/7 default), minimap 0x8008B080 + CITY x 24, glows 0x8008AE3C + CITY x 4, day haze 0x800298BC, 18 table-indexed reads.
Chicago today = CITY 3 + a plugin flag (shares LA's index, tables written by the plugin while Chicago is chosen).

**Recommended: Havana shares CITY 4 (FLAT's index) like Chicago shares 3 with LA.** The plugin points entry 4 at
Havana only while Havana's row is chosen; with the flag off entry 4 is FLAT.LEV again (nothing replaced). No mission in
MISSION.BLK uses CITY 4 (opcode 0x22 values: 0 Miami 32, 1 SF 32, 2 Interview 2, 3 LA 19, 5 NY 26, 6 Desert 11, 7 Newtown 1).
Las Vegas / Rio share indices the same way (one flag each), so the table extension is never forced. FLAT is a bare dev level that the selector never offers (V_FLAT is not
used, user R20). Every CITY table already has an entry 4, so no table grows and no exe table moves; the plugin fills
entry 4 for Havana the same way it fills entry 3 for Chicago. The alternative, a new index 8, means extending all the
8-entry tables and switches above (exe-wide, ~30 sites, the CITY = 7 crash shows how one short table breaks a load):
several days more for nothing the user sees. Index 4 is "Havana's own slot" in every sense the player notices (own row,
own level, own music / sky / map / cars, LA untouched).

What the slot needs (each item = the existing Chicago mechanism, keyed by city instead of hard-wired to CITY 3):

| item | how (today for Chicago -> Havana) |
|---|---|
| level file | level path entry 4 -> the package's `havana.lev` / `havana_night.lev` (LEVEL_LOC_TABLE entry swap, as entry 3) |
| selector row | page 2 "Driver 2 cities": row "Havana" (virt V_HAVANA, CITY 4), today a grey placeholder |
| Take a Ride flow | LA's Take a Ride script 0x7C with the CITY opcode switched to 4 (the Newtown / Desert path) + start position move |
| day / night | the Day/Night screen like Chicago's row (night = NLEVELS/HAVANA.LEV) |
| start position | per-city start (today CHICAGO_START in build_package) |
| car set | car set 4 + Havana's D2 models (LCF / DEN, car_banks[1]); cop = Havana's D2 cop model |
| cop settings | Take a Ride cops as LA / Chicago (felony from the script); D2 Havana cop model + siren |
| music | 2 more songs in the relocated MUSIC.BIN (Chicago uses slots 8 / 9; Havana 10 / 11, MUSIC_XOR word) |
| sky | Havana's D2 sky (SKYn.RAW) as sky numbers 16 / 17 (Chicago uses 14 / 15) |
| minimap | entry 4 of 0x8008B080 written while Havana is loaded (C12 code, per-city overlay from HAVANA.LEV) |
| specials | Havana's own specials (D2 models 8 / 9 / 10 / 12 of HAVANA.LCF), per-area like Chicago |
| save data | Take a Ride writes no per-city progress (to verify with a Havana save test); career untouched |
| plugin gates | `chicago_active()` (CITY 3 + flag) becomes `d2_city()` = Chicago or Havana (sea level, D2 planes, sky, sounds, specials, CLUT strip ...) |

## 3. What is Chicago-specific today

Converter / package (a per-city profile replaces each item; Chicago's profile = today's values, byte-identical output):
- **Names / inputs:** `d2_CHICAGO.*` in convert.py (DEN, LCF, LEV, night LEV), build_package (asset names `chicago*.lev`,
  `group = "Chicago"`, FRONTEND label "Chicago"), setup_chicago (RECIPE, stamps, file names).
- **World scale / placement:** worldscale.py (SCALE 1.32 chosen for Chicago's 1.27 M north-south span, OFFSET from
  Chicago's object extents, CELLS 480 x 630). Havana keeps 1.32 (cars the same size) with its own offset / grid.
- **Water / height model:** WATER_LEVEL 1084 and the quay / beach / basin rules, trench + rail cuts (RAIL_CUTS seeds,
  bridge gaps), slopes: tuned on Chicago spots. Havana has sea, harbour and docks -> the water model needs a Havana pass.
- **Start, car sets, sounds:** CHICAGO_START_D2, CAR_SETS[("CHICAGO", ...)], D2_CHICAGO_BANK (car_banks[0]).
- **Polish modules:** polish_sky (Chicago's sky), polish_map (Chicago's overlay params), polish_music (songs 2 / 6),
  polish_cosmetics / polish_specials / polish_cars (CHICAGO.LCF / DEN, special areas), polish_laday (LA only, stays).
- **Recipe:** setup_chicago.RECIPE = specdmg2's env; a Havana recipe starts from it.
- **Chicago-only lists (Polish review 23.10.):** polish_cars slot_map (D2 ids / roles: cop 0, civilians 1 / 2 / 3, special
  slot 4, player 12 / 9 / 10 / 8), palette variant counts, AI_SLOTS (Havana: its own MISSIONS.BLK residentModels);
  polish_specials SPECIAL_BY_AREA (Chicago's SpecialByRegion row), SPECIALS 8 / 9 / 10 / 12, DEFAULT 10; polish_tex PROTECT /
  LANDMARK_PREFIX (Chicago texture names); polish_areas AREAS_SHARE 0.8 / corr5 (tuned on Chicago routes); convert.py quay /
  basin rules with Chicago model ids and names (QUAY_RAIL_SRC, QUAY_DROP, SHOREWALL, WATER_TEX, BASIN_MIN / BASIN_Y,
  KEEP_SHORE_TILES, C74 SUBDIV rules); polish_map marks / NUDGE / stored params; polish_moon (SKYMOON from the night LEV:
  check Havana's NLEVELS); polish_sky d2raw placement. Generic already: texrepack's slot-15 short page and the CLUT cap
  (Havana's 52 pages make the CLUT margin the first thing to check).

Engine / plugin (driver_chicago.c, exe_patches.py): CITY 3 hard-wired in `chicago_active()`, the level entry 3 swap, minimap
entry 3, sky numbers 14 / 15, music slots 8 / 9, the specials asset, car tables for car set 4. The exe side (S1 CLUT strip,
S4, C37 planes, C42 car groups, C82 / C87) is already city-independent or gated by per-level words the plugin writes.

## 4. Havana's specials: ferries / boats (REDRIVER2 event.c)

Havana (GameLevel 1) runs D2 events: two **ferries** that carry cars (HavanaFerryData: 2 boats with paths, cars move
with the deck: BoatOffset / OnBoat), a **"mini" lift / platform** (HavanaMiniData), fixed events (havanaFixed[3]) and a
camera hack for the first ferry ride. Driver 1 has no event system.
- **Phase 1 (with the first probe):** ferries as static scenery at their dock positions (drivable deck where the D2 data
  places it), the mini platform fixed; no moving boats.
- **Phase 2 (own decision later):** moving ferries = a small event engine (path, deck surface that moves the cars on it).
  New engine feature with a PS1-native path; estimate 3-5 days alone.
Havana's special CARS (the D2 "special" model slot: e.g. the Havana bus / truck types in HAVANA.LCF models 8-12) reuse
Chicago's specials pipeline unchanged (per-area slot, D2 damage zones C87, special damage 2 rule).

## 5. Plan and first estimate

| step | who | effort |
|---|---|---|
| 0. throwaway Havana dry run with Chicago's profile minus the Chicago-only lists: hits the real risks early (63-block spool, 1529 models, CLUT / VRAM budget) | Infrastructure + Polish | 0.5 day |
| 1a. profile object + Chicago profile: names / inputs / scale / start / recipe | Infrastructure | 1 day |
| 1b. (parallel) the polish_* constants into the profile, each module byte-identical by itself | Polish | 1 day |
| 2. Havana conversion: inputs, scale / grid, first water + height pass, specials, car set | Infrastructure + Polish | 2-3 days to a drivable level |
| 3. 6th slot = CITY 4: level entry swap, selector row, Take a Ride script, start, day/night, plugin `d2_city()` | Infrastructure | 1-1.5 days |
| 4. Havana sky / map / music / cars / sounds (data) | Polish / Design | 1-2 days (parallel to 3) |
| 5. probe "Havana 1" (static ferries), fixes from the user's review | all | 1-2 rounds |
| later: moving ferries (event engine) | Infrastructure | 3-5 days, separate decision |

First drivable Havana probe: about **5-7 working days** (steps 1-4 partly in parallel), then the usual review rounds.
Risks: the 63-block area model spool and 1529 models (fit check first, may need the C30 carry / an area split), the
harbour water model, Havana's height data around the docks.

## 6. Decisions for the user

1. Havana's slot: **CITY 4 (FLAT's unused index; recommended)** or a new index 8 (exe tables grow; several days more,
   no visible difference).
2. Ferries in the first probe: **static (recommended)**, moving ferries as a separate step after the first review.
3. Converter: one per-city profile file per D2 city (recommended), so Las Vegas / Rio follow the same way.
