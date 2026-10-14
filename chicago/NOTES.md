# Chicago → Driver 1 port

Driver 2's Chicago replaces Los Angeles
in Driver 1 (USA v1.1, SLUS-00842). Decisions (user, 2026-10-09): replace a D1
city first, 5th city later; milestone 1 = Take a Ride with traffic + cops; D2
music and car models; opening bridges fixed down; no on-foot; D1 look/feel.

## Status (2026-10-10, late)

Drivable in Take a Ride; textured city, collision, area streaming, restart.
Stage B (roads → traffic/cops) not started. Open issues: see the end.

## Workflow

| what | where |
|---|---|
| inputs (from the user's discs, not shipped) | `work/d1_*.lev`, `work/d2_CHICAGO.LEV` (+ night, .DEN, .LCF) |
| converter | `python convert.py` → `work/chicago_d1.lev` (~2.5 min) |
| package | `python build_package.py --install --chicago work/chicago_d1.lev` (writes mods/preloaded; --install required since 13.10., test copies use CHI_PKG_DIR via dt.prepare; without --chicago the chicago-la feature is dropped!; test-bigmiami removed 13.10., R18) |
| EXE patches | `python exe_patches.py disc/SLUS_008.42.orig --apply disc/SLUS_008.42`, then psxrecomp `generate --bios D:/recomps/games/SCPH1001.BIN`, then `rebuild` |
| test build | `build-test` (CHI_TEST_BUILD=build-test for dt/lab) when the user's dev client is running |
| user's dev client | `build-dev` (desktop shortcut "Driver (dev client)"); the user plays this, with dev mode, snapshots (F9 / L3+R3), hang dumps, debug server :4370. Never write test packages or state into it; rebuild only when it is not running. |
| frozen release | `build-release` (Quiver launches it); updated only when the user declares a release |
| tests | `devtools/dt.py` (snaps, live, spots, soak, addspot, dis) on copies in `<app>/devtest/`; issue spots in `devtools/spots.json`; results `devtest/_out/` |
| user spot play | `Driver (spot).bat` / `devtools/spotplay.py C4|spotname`: windowed copy `devtest/play_<spot>` of build-dev (same exe + installed level, user's input settings, own memcards, port 4377) starting Take a Ride at the spot; menus driven automatically |
| playable copy (laptop) | `python driver_personal/publish_playable.py`: build-dev → `<OneDrive Desktop>/Driver Chicago (playable)` (Play Driver.bat, Play at spot.bat + spots.txt, fixpaths.ps1 rewrites BIOS/disc/memcard paths per PC; dev/ syncs back). Republish after each build-dev update |
| lab | `devtools/lab.py run` (continuous, 6 slots, ports 4400+): job queue `lab.py add capture|soak SPOT experiment=.. env={..} pokes={..}`, converter variants cached as `work/var_*.lev`, idle soaks, regression captures on a new build-dev exe; events in `devtest/_lab/events.log`; **health alert**: 3 failures of one kind in a row or >50% of the last 15 min → `LAB ALERT` line in WORKLOG.md + idle rotation paused (resumes after 3 passes or a new exe); a game that exits (crash, PC=0) is reported as `GAME EXITED PC=.. ra=.. stack ..` (`dt.exit_info`, from run.log + psx_cps_exit_trace.json) instead of ConnectionRefused |
| quiet runner | `devtools/run.py -- CMD` (full log in `devtest/_out/logs/`, capped output) for converter/package/soak/export runs |
| independent LEV check | `devtools/levcheck.py LEV [--world] [--vs OTHER]` → DriverLevelTool parse + texture/OBJ export + counts (2026-10-11: converted 195,243 objects / 847,769 faces / 34 pages; D2 original 220,664 / 1,158,100; LA 63,927 / 323,781) |
| drive test | `devtools/drivetest.py NAME D2X D2Z DIRX DIRZ [--secs N] [--lev LEV] [--port P]`: holds a direction on a test copy and samples the car's height, damage and upside-down counter (lifts, drops, wrecks; the soak/capture jobs don't see those). The car spawns facing north (west at some street spots), its 90° turns are unreliable: test north-bound or straight. Car y is UP (street ≈ 164 at the centre, trench floor 1352 → -1188) |
| restart loop | `devtools/restartloop.py NAME SPOT [--lev LEV] [--port P] [--loops N] [--dir DX,DZ]`: drives straight (into the water at beach_n), waits for Game Over, presses Play Again, then checks alive / kernel / model table / city per loop (C26 reproduction: hangs after a restart at beach_n, pc 0 epc 0x8002D260, with and without the plugin selector) |
| OpenDriver2Tools | binaries `D:/recomps/refs/OpenDriver2Tools-bin/` (DriverLevelTool: D1/D2 viewer with D1 road overlay, OBJ/TGA/overmap export; DriverImageTool: D1 PSX sky unpack, D2 SKYn.RAW; DriverSoundTool: D2 MUSIC.BIN→XM, BLK→WAV); source `D:/recomps/refs/OpenDriver2Tools/` (`regions_d1.cpp`, `d2_types.h`: D1 ROADS 16 B, JUNCTIONS 44 B, ROADBOUNDS 20 B, road-map cell = height s16 \| type 10 bits \| angle 2 bits, roadm = road index per cell) |
| reference source | `D:/recomps/refs/REDRIVER2` (Driver 2 decompiled to C; same engine family), psx-spx for hardware |
| Claude Code | `D:/recomps/CLAUDE.md` (rules, read order), skills `/chi-status /chi-build /chi-spot /chi-levcheck /chi-wrapup`, subagents `chi-investigator` (game runs) / `lev-analyst` (offline), guard hook `D:/recomps/.claude/hooks/guard.py`; `driver_personal/` is a git repo (work/ ignored) |

Converter switches: `CHI_START=x,z` (D2 coords, start position), `CHI_EXPERIMENT`
(`no_coll[=ids]`, `clear_sf6`, `pvs_full`, `no_subremap`, `no_near`, `tile_nocull`,
`no_area_tex`, `no_trench`), `CHI_AREA_TEX` (default 220), `CHI_BIG_TILE` (3000), `CHI_SHRINK`
(3), `CHI_PER_AREA` (1), `CHI_SHARED`, `CHI_RAMP_STEP` (0: a street bridging a trench drops in;
N: stepped ramp), `CHI_WALLTOP` (1: ground on a trench wall follows the trench),
`CHI_MEDIAN_SNAP` (40: a cell that little above a neighbour takes the neighbour's level;
median kerbs in the trench, 1329 beside lanes at 1352, user 02:12).

Menu paths for QA (2026-10-12): Driving Games = from title triangle, right ×4, cross (carousel:
Undercover, Car Chase, Training, Cheats, Driving Games, Take A Ride, Options, High Scores); city list
starts at Miami 1 (Miami 1/2, SF 1/2, LA 1/2 = Chicago slot, NY 1/2). CITY 0x80096834 reads 0 in
Driving Games (not usable there). The timed modes (Pursuit, Getaway, Trail Blazer, Survival, Dirt Track)
end in Game Over within seconds under the dt input harness, but work when the user plays them
(R7): harness artifact, not a bug. Cross Town Checkpoint drives under the harness.

Level slots (EXP, 2026-10-12): disc /DRIVER/LEVELS/ has CREDITS, FLAT, FRISCO, IVIEW, LA, MIAMI, NEWYORK, TRAIN .LEV.
The exe's level path table at RAM 0x80086EC0 (8 pointers to 'LEVELS\*.LEV' strings at 0x80010054..0x800100D8):
0 MIAMI, 1 FRISCO, 2 IVIEW, 3 LA, 4 FLAT, 5 NEWYORK, 6 TRAIN, 7 CREDITS (= the credits city "Newtown"). CITY 0x80096834
holds this index (Take a Ride: Miami 0, SF 1, LA 3, NY 5). Name table 0x8008B328 (8 words); an unknown 0/0x7FFFFFFF
block at 0x80086E60..0x80086EBF. Forcing CITY=7 into Take a Ride crashes in the load (DISPATCH FATAL misaligned target):
a per-city table there is shorter than 8. File offset in SLUS = RAM - 0x80010000 + 0x800.
CITY users (EXP r2): accessed via lui 0x0009 + 0x6834; 78 sites. 8-case switches on CITY (sltiu 8 + jump table):
8004ED88 (tbl 0x800108A8), 80050C8C (0x80010990), 800525BC (0x80010A00), 80052624 (0x80010A20); a 6-case switch at 80052CF8
(tbl 0x80010C18, CITY 6/7 take the default). 18 table-indexed reads (lui bases 0x000A/0x0003/0x000B/0x000C/0x0045/0x0008;
the level table is read at 8006C2FC). CITY is set at 80068A00 (front-end struct 4(t0)), 8006ECC4, 8006EF4C/8006F078 (2080(gp)).
The CITY=7 crash: $ra 0x80077AC8 after jal 0x8007F544 (trampoline), target not from a switch table.
Take a Ride recipe (EXP 13.10.): triangle, right x5, cross, N downs, cross, ~3 s, cross on the Day/Night screen (Day default,
down = Night). The Take a Ride city list has 4 rows: Miami (0 downs, CITY 0), SF (1, CITY 1), LA/Chicago (2, CITY 3), NY (3, CITY 5);
"Miami 1/2" = that Day/Night choice. Day/Night flag candidates 0x801D2DB8 / 0x801D2DC0 (0 day, 1 night; recheck in Chicago).
Per-city RAM data (not changed by Day/Night): 0x800A531C (best table candidate), 0x800A0018, 0x800A0E20, 0x800BD97E, 0x800C0014;
0x8009B23C = the live player block. Details: research_day_music.md.
Day/Night flag = 0x801D2DC0 (set by menu code pc 0x801C2C04; 0x801D2DB8 is a per-frame mirror). Chicago in the LA slot shows NO
Day/Night screen (loads straight in) because original LA has none either (D1: LA is NIGHT-only, user 13.10.; checked with chicago-la OFF). 0x800A531C is filled at load (exe-static 32-B entries from 0x800A6E8C + per-object 32-B records),
its writers don't read CITY → no CITY-indexed exe table needed there; a new city's LEV supplies the records.
**Chicago slot + Day/Night (Infrastructure 13.10.):** row confirm callbacks (FRONTEND) set the Take a Ride mission
0x80096808: Miami 0x78, SF 0x7A, LA 0x7C, NY 0x7D; Miami/SF/NY's then open the Day/Night submenu 0x801C4AE4 (row table
0x801CE0FC, cursor 0x801D2DC0), whose confirm 0x801C4A7C adds the choice to the mission (+0 day, +1 night). MISSION.BLK
(LBA 63177) entry = mission - 0x20 (0x7C -> entry 0x5C: `a 2 2d 1 22 3 ... 13 x z`). Script switch at 0x8006897C (opcode-0x13,
jump table 0x800110D8): opcode 0x1F = night (sets 0x80096850 = 1; Miami/SF/NY night scripts differ only by it), 0x22 = CITY.
Chicago row = LA's highlight callbacks + Miami's confirm; the plugin maps CITY 3 with mission 0x78/0x79/0x7D back to 0x7C,
keeps day/night, points level entry 3 at the day or night LEV (sidecar chicago_slot.bin: 8 day words, LA start, Chicago start,
8 night words) and writes 0x80096850 right after the script parse. Night LEV: `CHI_D2_LEV=work/d2_CHICAGO_night.lev python
convert.py OUT` (same settings; day reconvert == full11 byte-exact); package `--slot --night LEV` (or CHI_NIGHT).

## Formats (both games: LUMPDESC container, `levfile.py`, byte-exact round trip)

- Sections: LOADTIME (lump 35 + sub-lumps), permanent tpages, INMEMORY (36),
  spooled (2048-byte blocks). D1 sub-lump lists: count first, no end marker.
- Roads: D1 ROADMAP 7 / ROADS 8 / JUNCTIONS 9 / ROADSURF 10 / BOUNDS 16, 17;
  D2 STRAIGHTS2 40 / CURVES2 41 / JUNCTIONS2_NEW 43. Shared: TEXTURENAMES 5,
  TEXTUREINFO 34, MODELNAMES 12, PALLET 25, MAP 2, MOCAP 22, CAR_MODELS 28,
  MODELS 1, SPOOLINFO 26, SUBDIVISION 20, OVERLAYMAP 24, CHAIR 33, LOD 21.
- Cells: D1 CELL_OBJECT 16 bytes, plain lists; D2 PACKED 8 bytes, typed
  sub-lists (0x4000 = event marker, e.g. bridges), end bit 0x8000.
- MODEL header identical (36 bytes). D2 bounding sphere = horizontal footprint
  only. Shape flags (REDRIVER2 mdl.h): 0x80 water, 0x400 tile, 0x2000 road,
  0x4000 sprite, 0x4 low barrier (D2 only), 0x10 no-collide.
- D1 surface: tile road map (1500-unit cells, height/type/angle per cell);
  D2: 1024-unit cells with planes/BSP and multi-level (bridges, Lower Wacker).

## Driver 1 engine facts (addresses)

| what | address / value |
|---|---|
| map lump | 0x8002DFEC: cell size must be 3000; regions < 351 |
| LOADTIME buffer | fixed 0x800D8600 (keep loadtime ≤ D1 size) |
| model table | 2048 entries at 0x9F000000 (was 800 at 0x800A0E20; 88 patches) |
| cell object buffer | 0x9F002000, 512 KB (InitCellData 0x80039748) |
| world renderer | 0x800307FC; group table at MODEL+0x1C (`d1models.py`); trap `j self` 0x80030B00 |
| ground tiles | list built in object loop (0x8002D0E0: 128 stack + 512 at *0x8009715C); drawn by 0x800270D4/0x80027240; LOD bands < 2000 near (0x800287A4), < 7000 (0x80097148) mid (0x80027098), < 9000 (0x80097144) far (0x80026FF0); per-poly routine bits at +0x24/+0x28; SUBDIVISION via +0x2C (ptr 0x8009714C) |
| sprites (trees) | 0x8002C6DC, fixed polys at +0 / +0x14 |
| object cull | 0x8002C5F0 (3D, bounding sphere as margin) |
| primitive buffers | 2 × 0x1E000 at 0xD8600 / 0xF6600 (B is followed by the road map tables 0x117220); OTs 0xD0200 / 0xD4400; current 0x80097530 (+0 ptr, +8 start). Per frame: tiles, then all objects in one batch (0x8002D664 → 0x80030ED0), then cars, skid marks (0x8002A084), HUD/minimap (0x80054F84) ≈ 0x5A00 |
| road map lookup | 0x8001EF00: 120 × 120 ring of 4 region tables (ptrs 0x8009D8F4), row parity flipped by *0x80097374 & 1; decoder 0x800354D8 |
| PVS | decoder 0x8003A2A0, counter must hit exactly 0; `pvs.py` |
| areas | switch 0x80033F9C (from 0x80039FE8), load 0x80033B10, model fix-up 0x80033E54 (ids at *0x800972D0), flag 0x800969E8, current 0x800972C0, region 0x8009732C |
| spool queue | 0x800A7BA4 (16-byte entries); reader 0x80034C74; reset 0x800337D4; indices 0x800969EC/F0, write 0x800972B0, sectors left 0x800971F8 |
| VRAM | 16 page slots at x 512–1023 (2 rows); slot→page 0x800BE4F8; CLUT row base per slot 0x800BE1BC+2 (8 rows/slot); area pages load slot 14 → 5 |
| misc | player pos 0x8009B0BC; VSync counter 0x80095250; kernel tables at RAM 0..0xC94 |
| player car | struct 0x8009B0A4 (D2 CAR_DATA-like): +4 matrix (m[1][1] at +0xC), +0x18 pos, +0x24 fposition (<<4), +0x30 quaternion (4096), +0x40 lin vel, +0x4C ang vel, +0xF8 heading, +0x114 damage zones (6 × int, clamp 0xFFF), +0x17C total damage (u16; max at 0x80096E7C; damage routine 0x8003FB98 adds to both; Invincibility path 0x80025AC0 zeroes both each frame = repair). Upside-down rule 0x80023428: m[1][1] < 100 counts game frames at 0x80096920, 181 → damage = max+100 = wrecked. Dev flip: driver_personal.c |

## Road network for traffic (`d1roads.py`, `CHI_ROADS=1`, Infrastructure 13.10.)
- Port of EXP's build_full.py merge v2 (ANYL MAXROADS=420 MINDEG2): D2 straights merged by direction, longest <= 420
  roads (421 resets the game), D2 junctions/curves with >= 2 kept roads = D1 junctions. Roads >= 50% in water (outside the
  converted land; the converter's first road-map pass gives the water cells) are left out: 378 roads / 235 junctions.
- **Lane rule (Miami, verified offline):** a road cell's roadh rot bits (>> 30) = its lane's travel direction: dir-0 (z) roads
  0 on the low-x side / 2 on the high-x side, dir-1 (x) roads 1 low-z / 3 high-z (cell frame of d1roads). The AI's mode
  (+0x30) and the per-road per-mode counts (0x8009E744 rows) follow it; all-rot-0 cells = no traffic. Road cells are forced
  to that rot and their ROADSURF planes stored pre-rotated (`roadsurf_lump(force=)`). Roads are 2-3 cells wide (D2 width
  NumLanes x 1024 x 1.32, at least one cell per direction); D1 NumLanes = cells across, LaneDirs bit k = high-side cell.
- **Junction exit slots (Miami/NY):** slot 0 = road on the -z side (ends there), 1 = +x (starts), 2 = +z (starts), 3 = -x
  (ends); ROADS ConnectIdx[0] = junction at the low end, [1] = high end; entry fromJunc = the road's other-end junction
  (-1 dead end); empty slot (-1, -1, 0, 0). The AI picks its mode as the exit slot it leaves by (EXP: 0x800175EC).
- Heights/water/flags of a roads build are identical to the same build without roads (checked vs full11).
- **Frame (fixed 13.10. 14:xx):** ROADS/JUNCTIONS/ROADBOUNDS use the game's road-map cell (col, row) = floor((x + W*750 + 750)
  / 1500), floor((H*750 - z + 750) / 1500) from the top = convert.py's grid. The spool regions count bottom-up: grid row r
  lives in region rz_n - 1 - r // 60 at row r % 60 (EXP's build_full stored roadm in region r // 60: mirrored, a third of
  the road cells on water; it also rounded instead of floor).
- **Junction cells (Miami, 234/234):** a box of cells valued 0x4000 | junction id, as wide as the crossing roads (2x2..3x3);
  JUNCTIONS (x, z) = the box's low corner; roads start next to it, aligned. 0x80021820 returns 1 only on such a cell, and
  traffic state 2 -> 3 (0x80017F58) needs that plus record +3 (set at 0x80013FB8.. when the car is < 650 from the junction
  (+0x18), the light phase 0x800970D8 & 3 matches its direction and the turn checks pass). 0x8000 = no road.
- Junction record (Miami): type 1 with 3-4 exits (0 at corners), pad byte 0x22.. (runtime bits; 0x800138A0 reads it), entry
  flags 4 with 3-4 exits else 0, extraFlags 0, lights timer/NS/WE 0 (runtime).
- **JUNCBOUNDS (lump 17, Miami 234/234, NY 258/258):** two int32 per junction = its box centre in world units from the
  map centre: ((x + w/2 - W/2) * 1500, (z + h/2 - H/2) * 1500). (build_full's 4 x s16 fit was wrong.) ROADBOUNDS: cells,
  x1 = x - W/2, y1 = z - H/2, x2/y2 inclusive, dir byte.
- **Road cell bits (Miami: 15467 road + 1247 junction cells, all):** roadh bits 26-29 = 0 and bit 0 set (low bits 1);
  other cells 0xF / bit 2 (low bits 4). Our road cells now follow it (water/bridge cells keep the water value).

## Traffic lights in Driver 1 (offline, Infrastructure 13.10.)
- One global cycle: NS state gp+0x8E4 (0x80097054), WE gp+0x8E0 (0x80097050), timer gp+0x8E8. Init 0x80021BEC (NS 1, WE 3,
  300 frames), update 0x80021C10 every frame (from 0x8002340C): 1->2->3->4->1, 300 frames in 1/3, 100 in 2/4. JUNCTIONS'
  lightsTimer/NS/WE are unused. Type-1 junctions apply it: AI 0x80013F48, player red-light check 0x8001AE14.
- 0x800970D8 is a frame counter (rand 0x8004FFF0 reads it); the AI gate's `& 3 == +0x24` is time slicing.
- Glows: 0x80052C10 per object -> per-city table [0x8008AE3C + CITY*4] {kind, model id, name ptr, flag}, ids resolved by
  model NAME at load (0x80052A78, model flag |= 4). CITY 3 (LA, also Chicago): TLIGHT00 k0, TLIGHT01 k1, SLIGHT00 k2,
  SLIGHT01 k3 (flag 1), SLIGHT02 k4. 0x80052CDC draws glow sprites (0x8004343C, colour per state) at per-kind offsets;
  object yang ~0/2048 -> NS state, else WE. Chicago models: TLIGHT01 1179, TLIGHT02 1182 (no kind), SLIGHT01 1174.

## Light glows, car texture pages, Chicago day/night, split cells (Infrastructure 13.10., build b8)
- Glows draw on objects in the 11-entry list 0x800A663C (models with shape flag 0x0004, set at load for the named
  light models). D2 models carried 0x0004 for other reasons (21): cleared in the converter. TLIGHT01 turned a quarter
  (faces -z like LA's; objects yang+16), TLIGHT02 renamed TLIGHT00 (kind 0). Plugin: Chicago glow offsets in CITY 3's
  code (0x800530E4.., helper 0x80053764: x a2-720, y -957/-876/-795, z -100; lamp 560/-1640) while Chicago is loaded.
- **Car texture setup (0x8003BDC8, store 0x8003C218)** writes a CLUT word per car polygon to 0x800BEA04 + 600*(page-5)
  + 20*tex: car textures must sit on pages >= 5 (LA: 5/6). Ours on pages 0-2 overwrote the texture page COUNT table
  0x800BE2F8, so every by-name sprite (0x80052240: FLARE1, LIGHTREF, SMOKE, ...) on a page >= 1 got a garbage record
  (dark squares). texrepack.renumber_permanent swaps the permanent pages to 5.. (keep_carpages = old).
- Chicago by day (plugin s_day_words): CITY==3 compares at 0x800298D8 (fog/sky colours), 0x8003A6B4 (ambient 0x282828),
  0x8003B19C, 0x8003C974, 0x80047030 (sun flare), 0x8004B248 (headlights always), 0x800437E0 (halo) -> 0x7F. Night: LA's
  night (CITY 3) on D2's night LEV, Driver 1 night flag 0x80096850 not set (no double dimming).
  **C39 (13.10.):** level init 0x8002360C also compares CITY with s1 = 3 (set at 0x80023720, so immediate scans miss
  it): 0x8002379C (calls the light halo / trail setup 0x800430B8) and 0x80023CD8 (lights flag 0x800970E8 = 1 -> player
  lamps via 0x8003B064 -> 0x80046234). Chicago day turns both into `b` (s_day_words); 0x800970E8 / 0x80097448 /
  0x80096AA4 then match Miami day. Other s1 compares in that function are not CITY (return values, gp+0x92C = 3).
- **Split cells** (user rule R12: only what is visible may be drivable): a land cell beside a level step >= 300 is
  sampled 4x4 (top D2 level per point); if own level and the neighbour's separate along the axis, the cell gets two
  side-by-side planes (own part / neighbour part, surface info 2: the engine picks by position, the plugin stays out).
  1468 cells in b8 (underbridge ramp's east quarter = the elevated road; c20_p2n deck edge inside the cut's cell).
  keep_fullcells = old. BEACH_GROW default 0 (R12 beach_n).

## City selector, D1 extras, minimap, sky, night water (Infrastructure 13.10., build b11)
- **D1 extras** (pages menu): Newtown/Interview/Training run LA's Take a Ride 0x7C with the script interpreter's CITY
  opcode 0x800689F8 (`lw v0,4(t0)` 0x8D020004) switched to `addiu v0,zero,CITY` while that mission loads; start moved
  like Chicago's (s_level_start). No timer/Game Over (QA-3: Newtown 300 s, Interview 120 s). CHI_EXTRA_LA=0 = their own
  missions (Credits 0x7F / 0xAE / 0xAA, Game Over ~40 s). **FLAT (CITY 4): dropped (user R20)**: a bare dev level
  (no car set, no by-name engine models SKY01-04/wheels/hubcap/ped heads, unreadable model-names lump); crashes at level
  start with any script. Row removed from the selector; fun fact in driver_personal/FINDINGS.md (F1).
- **Sidecar chicago_slot.bin** (27 words): entry 8, LA start 2, Chicago start 2, night entry 8 (0 = none), minimap frame
  6 (0 = LA's overlay), flags (1 = Chicago skies). The plugin also reads the old 12/20-word form.
- **Minimap (C12):** convert default CHI_POLISH_MAP=1; build_package detects a non-LA OVERLAYMAP and stores
  polish_map.params; the plugin writes them into the CITY 3 entry 0x8008B0C8 while Chicago is chosen (in the menu, before
  the level init reads it; 0x80096D2C/30 then follow by themselves), LA's saved values otherwise.
- **Sky (C10):** package ships SKY.BIN = D1's 13 skies byte-identical + Chicago day 13 / night 14 / rain 15 (polish_sky),
  relocated after the night LEV, DRIVER/DATA/SKY.BIN directory record patched (build_package.iso_record; CHI_SKY=0 off).
  Plugin: CITY 3's immediates 0x8004EDE0 (2) / 0x8004EDEC, 0x8004EE00 (rain 3) -> 13|14 / 15 while Chicago is chosen.
- **Night water:** Miami's SEA palette x0.17 (rounded) in the night conversion (texrepack.NIGHT_WATER, CHI_NIGHT_WATER):
  measured Miami Night sea = 0.161-0.181 of Chicago night's per channel, no tint (Chicago night has night flag 0).
- C7: polish_tex default CHI_POLISH_TEX=filter.
- **Car set by city/time (R19, b12):** convert.car_set(): CAR_SETS[(D2 city, day|night)] -> D1 level (CHI_CARS overrides:
  la/miami/sf/ny); Chicago day = Miami, night = LA. The car set gives the car models (28), palettes (25), special (car)
  pages and the car models' other textures (texrepack source "K"); wheels/peds/engine textures stay the base city's
  (LA). Palette entries for pedestrian textures (ARM1, CHEST1, ...) map by name onto the base city's copy. C42 (D2's
  own cars) can plug in as another car set.
- **C40 defaults (b13, user verdict 13.10.):** d1models CHI_POLISH_SUBDIV default "light" (= 0,1000000: every 0x20/0x40
  flagged polygon at the light fixed subdivision level 0x60; "none" warped buildings and was removed); polish_pvs
  CHI_POLISH_PVS default d2 (Driver 2's PVS masks in D1's window) with **32768 bytes per barrel** (C44: LA's larger
  barrel sizes shift the level heap up 57 KB -> full-screen palette/VRAM corruption at fps_drop_2; CHI_POLISH_PVS_BUF=la
  = old sizes, don't use). Check: SPOOLINFO pvs/barrel must stay 32768 x 4.
- **FPS stats for test tools (13.10.):** driver_personal_fps_tick() (driver_personal.c; called by the dev-mode vblank and
  by driver.chicago's model-table vblank, first caller owns it) writes the overlay's own numbers to mod memory
  **0x9F082310** (with the Chicago slot on; allocated on the first frame, logged as "FPS stats at"): +0 magic 0x31535046
  ("FPS1"), +4 FPS, +8 EMU % (once a second, as on the overlay), +12 frames drawn since boot, +16 VBlanks since boot,
  +20 one-second updates. Read with dt: struct.unpack("<6I", d.ram(0x9F082310, 24)); check the magic first.
- **Stall ring STL1 (C45, 13.10.)** right after it at **0x9F082330** (same allocation, 0x130 bytes in all): +0 magic
  0x314C5453 ("STL1"), +4 stalls so far (in game only: >= 6 VBlanks between two game frames, i.e. the draw buffer
  0x80097530 did not swap; only once a region is known, so boot and level loads don't count), +8 longest gap (VBlanks), +12 stalls recorded (ring slot = (n - 1) % 8), +16 ring of 8 x 32 B:
  gap (VBlanks), player x, z (when the next frame came), area before / after (0x800972C0), region before / after
  (0x8009732C), flags (1 = area loading flag 0x800969E8 set during the gap, 2 = spool sectors left 0x800971F8 > 0 during
  the gap, 4 = loading/spool already active when the gap began). Read: struct.unpack("<4I", d.ram(0x9F082330, 16)) and
  struct.unpack("<64I", d.ram(0x9F082340, 256)).

## Converter (`convert.py` + modules)

1. World scale ×1.32, centred (`worldscale.py`): 540 × 570 cells, 18 × 19 regions.
2. Models (`d1models.py`): generated polygon groups/planes; 20/21 → 10/11;
   tiles and sprites kept as is; bounding spheres fitted to vertices; LA's
   engine models appended (BOEING hidden).
3. Visibility (`pvs.py`): per-cell view radius 5–9 by polygon budget.
4. Areas: every region gets 2 switch entries (border: neighbour + own; inner:
   own twice, axes in a checkerboard); the switch rule is simulated cell by
   cell (`loadable_areas`) and each area's set covers every region it can be
   loaded in; areas split above 220 textures (21 areas, 1.65 per region).
6. Road map (`road_levels`, cached pkl → `road_values`): D2 surface per 1500
   cell, one level (D1: first shape polygon wins, 0x8001F274; the test is 2D
   only, height = plane − cell height, plus a hardcoded SF box at 0x8001F34C):
   nearest street level, except (`trench_rule`, switch `no_trench`): a sunken
   level (y ≥ 300 down, trench freeways at 1352) wins over the street above it,
   so a street bridging a trench gets a stepped ramp down into it and up again
   (`CHI_RAMP_STEP` 200: 6 cells of 193 per side along its own road cells,
   kerbs beside the ramp follow it; 0 = plain drop at the bridge edge), and ground
   cells on top of a trench wall take the trench height (`CHI_WALLTOP`; the
   car's centre crosses the cell border before the wall box stops it). Cells
   with a raised deck as well and sea-fixed river-bank cells keep the old rule.
   ROADSURF (`surface_planes` / `roadsurf_lump`, switch `no_surf`): every cell
   whose own or 4-neighbour levels lie ≥ 300 apart gets a surface with one
   full-cell polygon per level (the cell's own level first, then lowest first: the
   engine takes the first while the plugin idles; d relative to the written height,
   quantised to 64) and sloped cells (`cell_slopes`) a tilted own plane; surface
   ids are plain model ids < 900 (the type field doubles as the model whose flags
   say water/grass), info = 1 marks them for the plugin selection, ≤ 320 surfaces
   (43 KB). With `no_surf`, raised decks that continue over streets are flattened
   to the street as before (else the car falls off the deck end; C17).
   Water = model 683 at y 300 (LA: 1544, flag bit 2 clear).
7. Water (`sea_kinds`, `water_cells`, `water_heights`, `far_water_*`): D2 has
   no water surface; D2's overhead map (`d2overlay.py`, LUMP 24, RNC2 tiles,
   +48 px window offset, lake = palette 12, river = 1) classifies connected
   no-surface areas: water / inside (enclosed → plain ground) / void (outside the
   city, drowns as a boundary). Water tiles: LA's tile with real corner vertices
   (LA's has none: far tiles, shape 0x20 via 0x800274B8, read 4 corners from +0x10,
   so stretched tiles shrank to 1500 squares), one per 3000 cell (4 per cell
   overflowed the tile list cap 640 → far gaps); bridge gaps closed (CLOSE 4);
   texture = Miami's SEA, renamed "SEA" (the engine's GetTextureInfo("SEA") at
   0x8004219C gives the near-water page/palette; LA has none → pink water).
   Height: river y 300, lake just under the lowest shore within 12000 (beaches
   sit up to ~2000 below the streets). Beyond the 9000-unit tile range: far
   water planes (model 1214 appended, 6000 units, 2 x 2 quads, only over open
   lake one cell from land; switch no_farwater). Known limit: the narrow river
   beyond 9000 stays thin (planes there would come under the camera).

## Engine patches (`exe_patches.py`, 294 words)

model table (88), cell buffer (4), object guard (16: the batched map-object
draw 0x80030ED0 stops at OBJ_LIMIT 0x16800 per frame), render trap
→ skip model (2), area switch waits while loading (3), spool guard: reset
clears reader/indices/loading flag + empty-entry stop + drained totals (45) + the 4 sector
readers end at a total <= 0 instead of == 0 (4, 2026-10-12: a total gone negative
after a teleport during a load chained into stale queue slots = PC 0 / dispatch
0xB0; the plugin's selection now idles only while the signed total is > 0),
tile guard: tiles (drawn before objects) stop at 0x12000 + tile list cap 640 (26), area switch rewrite
0x8003401C (64: threshold always 13 = 5-cell hysteresis band; Chicago only: a
region whose 2 entries don't name the loaded area, or with none loaded (-1),
loads its own = 2nd entry),
road map RLE decoder rewrite 0x800354D8 (30: bad runs fill the rest, always
ends; old one looped forever on stale buffers after Play Again).
Sea level (11, C35, 2026-10-12): for a water cell whose model is "sea" (flags 0x80)
the ground query 0x8001EEB4 ignores the cell height: ground = wave table value
around y 0 (LA's harbour level) minus a sink term, so cars floated ~1000 above
Chicago's water (drawn 1084 down). 0x8001F0C8..F0FC now add an offset from mod
memory 0x9F082100 (driver_chicago.c: -1084 in Chicago, 0 elsewhere): the redundant
`lui v0,9` and the table-base `addiu` folded into the loads' offsets, the load-delay
nop loads the address. Verified: the car sinks at the drawn water, Game Over.
Model table late use (1, C36): 0x8004B5A4 `lui t7,0xA` (moved to 0x9F00) is the delay
slot of a branch to 0x8004B7A0, whose `addiu t7,t7,0xE20` (0x20C later, missed by the
48-byte lui/use window) still added the old offset: entry index + 904, so model
indices >= 1144 (far water 1214, shore walls 1215) read past the table -> AdEL at
0x8004B7CC -> BIOS handler loop (user freeze 21:11). Now +0. A scan for other
old-table offsets after a lui 0xA found only false positives.
Caves: dead overflow block 0x80051440.., cellsize error block 0x8002E1A0 (both
full); `asm()` in exe_patches.py assembles rewritten routines.
Height-aware road surface selection (C16/C17) is **not an exe patch**: it is done by
`driver_chicago.c` (`surface_select_vblank`): every vblank, for the 3 × 3 cells
around the player (road-map cell via the lookup's own ring addressing: header
0x8009E714, tables 0x8009D8F4, parity 0x80097374; surface pointers 0x8009D904),
a marked surface (SURFACEINFO.info = 1, written by the converter) gets the plane
the car stands on moved to slot 0. Rule since 2026-10-12 (Driver 2's sdGetCell,
user): planes from the top down, the wheel (player y − 160) stays on a plane until
it is below that plane's switch height = Driver 2's own per-level threshold
((256 + thr) × SCALE below, `level_switches`, carried in the SIPOLY pad relative to
the cell height; pad 0 = older level = none) or the midpoint to the next lower
plane, never below that midpoint, at least 64 under the plane; hysteresis 24; the
car's own cell is selected last (shared surfaces). The old rule (highest plane up
to 100 above the wheel) lifted cars 70–90 onto close planes (c20_p2n). Only
the 4 plane words + the nverts/switch word are swapped: a torn read during the engine's loop costs tens of
units, never the other level); the unchanged engine loop then takes it as its first
2D hit. info = 0 (the original cities) is never touched. Limits: player car only;
with traffic/cops (Stage B) each car needs its own selection (or the engine loop);
replays replay the player car, so they follow. Tried and ruled out: a cave in the
exe (no 72 spare words; the "unreferenced" function 0x8006C078 is reached via
0x8006C964 from 0x80025190 → C22 crash: the loop ran in a foreign frame and
returned to address 1) and a cave in mod memory 0x9F082000 (`j` cannot leave the
0x8xxxxxxx segment and the recomp fail-fasts on dispatch outside its image).
build_package.py checks that disc/SLUS_008.42 carries every current patch word
(no hard-coded count); a stale disc exe = "run --apply, generate, rebuild".

## Runtime changes (`driver_personal/runtime_patches/`, originals in `orig/`)

Disc overlays past the image end (iso_reader, mod_runtime), save states keep
mod memory (memory, boot_state), CD DMA into mod memory (dma), write guard
(debug_server), L3+R3 snapshot helper (main.cpp), watchdog underflow fix
(starvation_ring). Plugin `driver_chicago.c`: model table + cell buffer
allocation, empty model (1 culled group, 1 zero polygon), area-switch guard,
size-0 placeholder redirect, ROADSURF plane selection (C16/C17), C33 area-switch
entry hook: psxrecomp function-entry plugin on 0x80033B10 (the switch's texture
page queue), enabled by `game.toml [recompiler] mod_function_entry_funcs =
["0x80033B10"]` (re-apply after updates; `generate` emits the call). Chicago
(city 3) only.

## C47 / C38 shared patch change (14.10., default list 297 -> 307)
- **Exe patches are not visible in RAM:** they live in the generated native code; RAM keeps the original exe image. A
  plugin can't detect them by reading RAM. Code words a plugin writes into RAM make that page "dirty" and it then runs in
  the slow interpreter (C47: the RAM day switches cost +13-15 % host time in dense Chicago).
- **look CITY (exe_patches.look_city_patches):** 8 CITY loads (0x80023634, 0x80023794, 0x80023CD0, 0x8003A6B0, 0x8003C970,
  0x800437DC, 0x8004702C, 0x8004B250) read LOOK_CITY 0x8009789C (gp+0x112C) and 0x800298D8 reads C3 0x80097898
  (gp+0x1128) instead of `li 3` (that site tests CITY < 4 afterwards). The plugin keeps LOOK_CITY = CITY / 0x7F (Chicago by
  day) and C3 = 3 / 0x7F; s_day_words are no longer written. **0x8003B1A4 stays original**: redirected, Chicago by day
  called 0x80079AF0(0x1F800308) (stack to the scratchpad) and the draw crashed at level start (PC 0; bisection).
- **C38:** decoder error path 0x80035670 -> empty region (static); **root fix:** the spool reset tail (0x80051454..5C, run
  at level start and restart) empties the queue (write index, stream sectors 0xA88) and ends in 0x80032DEC's
  end-of-queue path: CdReadyCallback(0) + CdControl(CdlPause). Before, a restart left the drive streaming the old read
  and the new level's reads met a stuck CD interrupt (spool-done wait 0x80033AF8 forever; dump 103933).

## C50 Play Again in the D1 extras (14.10.)
- Newtown / Interview / Training run LA's Take a Ride script (0x7C, CITY opcode switched). The script buffer is a heap
  block (0x80068360: *0x80097098, 0xC00 bytes); in those levels a region read (CD DMA, pc 0x8008160C) lands on it, and
  Play Again parses it again (loader 0x800686C0 re-reads MISSION.BLK, parser 0x80068928(a0 start, a1 end); main loop
  ptr/end at 0x800C6F04 + 0x2B8/0x2B4): the parser sat on a size-0 "opcode" (game frame 1, car y 4524).
- Fix: function-entry hook on 0x80068928 (game.toml mod_function_entry_funcs = 0x80033B10, 0x80068928): for an extra
  level the script moves to 0x800A0D00..0x800A0E20 (static, unused, C48 survey), a0/a1, gp+0x101C and the struct
  fields point there, and the start opcode (0x13) is moved to the level's start before the parse (the re-read script
  names LA's start). Host-only (M8: allocate that buffer statically in guest code). Verified: Newtown 3/3, Interview 2/2,
  Training 2/2, Chicago 2/2 restarts.

## C37 diagonal surfaces (14.10., CHI_DIAG=1, opt-in)
- Where the axis split (split_cells) finds no clean cut between a cell's own level and a neighbour's, `diagonal_cut`
  tries straight cuts in 15-degree steps (axis angles excluded), takes the widest O/N gap, puts the line on a 250 grid
  (else 50), clips the cell square to the neighbour's side and fans it into 1-3 triangles; the surface is
  [neighbour triangles..., own level FULL box] (first match wins, 0x8001F164 / 0x8001F5B0 test nverts 3 with
  0x80024370: inside = every edge cross >= 0 in the poly frame, i.e. clockwise winding). Neighbour offset in 100 steps.
  Surface info stays 2 (not all FULL), so the plugin's plane selection never touches these. Cells with "X" samples
  (stacked, unclear) keep the old result. Chicago day: 165 cells, 230 triangles, no surface dropped (ids fit).
- Debug: `CHI_DIAG_LIST=1|all` (cells with D1/D2 coords), `CHI_DIAG_CELL=col,row` (samples, cut, triangles).
- Test 14.10. (var_c37_diag_day.lev, build-test): a spawn exactly at cell (487,152) flipped the car: its front wheel
  stood in the cell's new 400-high wedge (D2's embankment), i.e. the cut is where D2 has it; a run from (486,152) east
  and south crossed the diagonal cells (487/488, 152/153) smoothly (no fall-through, no stall). The route's one
  pop-up (+870) was at (485,154/155), an old whole-cell step; b15 on the same route pops up as well (+680) and got stuck.
  Steps stay steps (D1 surfaces have no walls): a diagonal only moves the step line onto D2's visible edge.
- M8 budget: ROADSURF (lump 10, in memory) 49,900 -> 66,120 B (+16 KB, b15 vs C37); on PS1 within budget or capped by triangle count.

## tricatch.py (C45 corr4 artefact catcher, 14.10.)
- `python devtools/tricatch.py PORT OUT LEVEL --start=D2X,D2Z --legs="1,0,35" [--runs N] [--thresh 0.018]`: drives Chicago by day
  (dt.launch copy), after each area switch screenshots for 3 s; a dark sky band (> thresh) saves hit_N.png + GP0 captures of 6 frames
  (out/runR/gpu: per primitive pc/ra, src = packet address, OT). Routes vary with traffic: use several runs; check hits by eye.

## C17 / C28 height trace (14.10., FAN r13/r14 positions, road map read from RAM: scratchpad cellprobe.py)
- deckfall night_2 "under the world" at D2 (41206,229758): every cell within 6 km is lake water (683, 1080): the car drove
  off the lakeshore and drowned (authentic). floating r13 (y -936): the trench there (4 cells at 1352, edge cells 242) is
  intact; the sink was water depth; not repeated in r14.
- **C28 cause:** shorewall D2 (-179728,558771): between the street (0) and the lake (1080) runs a strip of plain ground at
  1176, i.e. D2's shore bank under the water surface; a car that gets in sits under the water line without drowning
  (stuck, y -997). Fix `CHI_BANK_WATER=1` (road_values): cells whose levels all lie in [WATER_Y+40, RAIL_FLOOR-100) become
  water, flood-filled from water cells through such cells only (trench 1352 stays). Chicago day: 125 cells, at most 3 from
  the water. Test level work/var_c28_bank_day.lev (b15 + switch): the strip reads 683/1080 in game.
- deck lift (day_1 / night_1, y 1091-1370 at D2 (-5334,257052) / (-3007,258017)): the cells there carry both planes (deck
  242: deck + street; ramps 56/69: street + raised 1096-1240 with D2 switch heights 676/845). The selector was not idle
  (no spool in 24 s of driving), so the "idle during spools" theory is out; open: a 0.1-s height trace of FAN's route.

## C17 causes (14.10., FAN r15 deckfall trace + r16 hs_drop, road map from RAM)
- **Drowning vs ground:** FindSurfaceD2 0x8001EEB4 gives each WHEEL sea ground (wave + sea offset 0x9F082100 = -1084,
  minus (100 - *0x800970DC)/2 while sinking) when its cell's model has flag 0x80 (only the water model 683) and y < 0xDC.
  The drowning check FUN_0003A698 looks at the car CENTRE (FUN_000217C8 at car +0xC8): sea + y <= 0xDB -> countdown
  0x80097004 (25) -> timer 0x800970DC (100, decremented in 0x8002360C) -> < 0: Game Over; else both reset. A car
  straddling a street / water edge sinks on its water wheels while its centre is a street cell: no drowning, stuck
  ~1000 below the street (hs_drop: a 1-cell street between a 968 strip and the lake; deckfall end -1004).
- **Lift:** the elevated Lake Shore Drive over the shore water is rasterised into lone deck cells (one plane, +1352)
  touching only at corners; a car entering one from the street is snapped up 1352; along it, it drops through the gaps.
- Other lakeshore pits: ground strips at 968 (above the water) and 1176 (under it, C28 CHI_BANK_WATER).
- Options sent to Strategy: (a) engine: drown when a wheel is on sea ground (PS1-native, done: DROWN_EDGE), (b) solid
  shore walls (user, R22), (c) lone deck cells -> water: withdrawn (they are D2's drivable deck, see C53 / C17 patches).

## C53 / C17 engine patches (14.10., shared list 378)
- **COSMETICS:** LoadCosmetics 0x80052620 reads CARSET 0x800978A0 (was CITY); its jump table 0x80010A20 is a base table
  [0, 8, 0x10, 0x18, 0x482, 0x20, 0, 0x28] (lw a0 + j 0x80052684 instead of jr); entry 4 -> rows at 0x800A16A0 (old
  model-table area behind the C42 damage tables), written by the plugin from assets/cosmetics_day/night.bin (build_package:
  work/var_polish_cosmetics_chicago_<t>.bin or CHI_COSMETICS_<T>) for car set 4. Chicago day with Miami's cars now gets
  Miami's rows (C53). Runtime block 0x8009AF04 (4 x 100 B: player row, rows 5-7).
- **DROWN_EDGE (C17 a):** see "C17 causes"; cave 0x8005265C..80 (the freed case blocks; default block at 0x80052654),
  entered from 0x8003ADC8; FindSurfaceD2's sea-wheel byte 0x800970F8 is sticky (clear at 0x8001F158 removed), the cave
  clears it; DROWN_RANGE 0x800978A8 (gp+0x1138) = 620 in Chicago (plugin), 0 elsewhere.
- **Test packages need the patch env:** the package manifest carries every exe patch as `main_exe` patches that the runtime
  applies to the RAM image (from the original disc); generated code comes from the build. An isolated root test therefore
  needs the opt-in env (e.g. CHI_COSMETICS=1) when the package is built, or RAM data/code words stay original.
- Converter (opt-in): CHI_BANK_WATER=1 (C28). D2 fact: type 0x4080 = curved road plane (REDRIVER2 dr2roads.c); in the
  grid it is the elevated Lake Shore Drive deck at -1352 (ABOVE the street; d2surface's raw height has the other sign).
  The deck-only cells over the water are that drivable deck (not slivers): a CHI_LONE_DECK switch that made them water
  was withdrawn the same day. **Deck fix (CHI_DECK_FIX, default since b16):** after the water-edge rule (which flipped
  filled gaps back), corner gaps of deck-only cells get the deck level (16 cells), and deck-only cells with water in the
  3 x 3 get their land neighbours' levels as lower planes (224 cells; 2476 inland deck-only cells untouched), so a street
  car is kept low (falls under the deck, drowns at the water) instead of being snapped up 1352. CHI_BANK_WATER default
  since b16 (FAN r18: drowns at c28_bank / c28_bank_w, b15 stuck).
  b16b (FAN r19): the lowered deck cells' deck plane carries its own switch 300 under the deck (world["deck_switch"] ->
  SIPOLY pad, e.g. 2020 = deck 1352 up over a 968 cell): with only the deck and a 968 strip plane the midpoint switch lay
  ~190 above the street and a street car with a bounce took the deck (snap 164 -> 1460). Rise from the 968 strip back to
  the street (-698 -> 203): no guard planes from wet neighbours (hs_lift_6_9 rule), so a strip car climbs the street
  cell's edge = the unwalled-step behaviour; the cure is solid shore walls (R22), not more guards.
  **SEL1 debug record** (14.10., for FAN's snap hunt): 0x9F082440 (stats block +0x130, after STL1), every VBlank: "SEL1",
  VBlanks, player cell word, selector y, idle | d2rule<<16 | stacked<<17, best | best height<<16, top switch, slot-0 d.

## M8 study: cell object buffer in main RAM? (14.10., Infrastructure; offline + live reads, no build change)
- D1 sizing (InitCellData 0x80039748 + level loader 0x800346C8): heap gets the model spool buffer (SPOOLINFO, >= 64 KB),
  4 slot buffers (the PVS sizes), cell pointers (window 30^2 x 8 = 7 KB), cell objects ((sum of the 4 slot object maxima
  0x800AB050 + straddlers 0x80097350) x 16 B) and cell data (sum of the 4 slot cell-data maxima x 4 B).
- Chicago b16b live: slot object maxima 2560/3328/2944/3584 = 12416 + 360 straddlers -> **204 KB** (the 512 KB mod buffer is
  2.5x oversized); cell data 17408 words = 68 KB; heap end WITHOUT the objects 0x1DE5B8. LA (computed from its LEV with the
  same formula): objects 9728 (+ its straddlers) ~ 156 KB, heap end ~0x1E15xx -> LA leaves ~123 KB below 2 MB.
- So Chicago needs ~200 KB more than LA in main RAM; with the objects on the heap it would end ~0x210438 (66 KB past 2 MB
  before any stack). Chicago vs LA in main RAM: in-memory models +84 KB, ROADSURF +55 KB, road lumps +15 KB, other lumps
  +18 KB, objects +43 KB, cell data +18 KB, PVS buffers -57 KB.
- Where the objects are: maxima come from ~15 dense downtown regions (up to 3553 objects; LA's densest 2688). 40 % of all
  objects are D2's flat ground tiles (ROAD1 39k, PATH1 19k, BIGGRASS, BIGPATH, MEDIAN1; pitch 1352) in 1-wide strips:
  merging pairs saves 7 % city-wide but only 3-10 % in the densest regions; 2x2 blocks ~0. Exact duplicates: 101.
  SHOREWALL (converter-added) 243 objects in the densest region.
- Levers (estimates): tile strip merging (Nx1) ~-10-15 KB **(NOT lossless: D1 draws tiles beyond 2000 units from one 3x3
  subdivision UV grid per model, a merged strip stretches the texture at mid/far range; Polish; skip without exact UVs)**; shore-wall runs as longer models ~-5-10 KB; in-memory
  models to area spooling (Polish's area/page work) ~-40-80 KB; ROADSURF coarser merging ~-10-20 KB (height risk);
  real stack need (LA's 123 KB slack is likely mostly unused) to be measured. Sum ~70-125 KB: borderline.

## Host-only parts (Milestone 8: real PS1 hardware; user 13.10.) — each with a possible PS1 path
New engine features need a PS1-native path (guest MIPS in the exe, data within 2 MB RAM / 1 MB VRAM / CD).
| host-only today | where | possible PS1 path |
|---|---|---|
| mod memory 0x9F000000.. (Expansion 1: model table 2048 x 4, cell object buffer 512 KB, sea level / Chicago flag, menu block, FPS1/STL1) | exe_patches NEW_BASE, driver_chicago.c alloc_fixed | fit into main RAM: model table in a freed exe/heap area, cell buffer sized to the level (spool-limited), small blocks in a code cave; FPS1/STL1 are dev-only (drop) |
| model slots past 800 (2048) | exe_patches model table (88 words) | converter keeps a level <= 800 models (dedupe / merge), or the table in main RAM (above) |
| plugin logic (driver_chicago.c: Chicago slot / level table entry 3 swap, start move, menu pages + rows, Day/Night remap, CITY-opcode switch for the D1 extras, glow / day / sky / minimap code-word switches, sea level flag, ROADSURF plane selection, area-switch guard, C33 entry hook) | vblank / function-entry plugins | guest code in a code cave of the exe (or the FRONTEND overlay for menu work), driven by the same data (level table rows, per-city tables extended to a 9th city index instead of switching CITY 3 words) |
| runtime changes (disc overlays past the image end, CD DMA into mod memory, save states with mod memory, write guard, watchdog fix) | runtime_patches/chicago-runtime.diff | DMA/overlays disappear with a real disc image; save states / guards are dev-only |
| files relocated past the disc end (chicago.lev, chicago_night.lev, SKY.BIN with Chicago skies), directory-record patches, FRONTEND.BIN patches | build_package disc_user overlays + patches | build a new ISO / BIN: files in the file system (LEVELS/CHICAGO.LEV etc.), FRONTEND patched in place |
| plugin-only measurement (FPS1 / STL1 blocks, dev mode, overlay) | driver_personal.c | dev-only, not needed on hardware |
| converter output limits checked only on the host (texture page budget, spool buffers, PVS barrels 32768) | convert.py / texrepack / polish_pvs | already PS1 limits (keep them): VRAM slots, spool buffer sizes, heap layout (C44) |

## Resolved (cause → fix)

- C25 kernel zeroed + freeze at the north map edge → the engine loads a 2 × 2
  window of regions and, in the top region row, asks for the row above the map.
  LA's SPOOLINFO has a ring of empty regions (265 of 324 entries 0xFFFF); Chicago
  filled all 342 of the engine's 350-entry table, so above-map indices ≥ 350
  (column 8 on) read past the table into the spool records → garbage offset →
  CD read into address 0. Fix: an empty ring: `CHI_WORLD=480x630` (16 × 21
  regions = 336; `worldscale.py`; D1 coordinates unchanged, only the grid).
  Verified 2026-10-11 15:1x on build-test (retail BIOS): alive, kernel intact,
  all-spot captures clean. Not the default yet (resume: soaks, flip, combined run).
  Side findings: build-test had no `bios.cfg` → its copies ran OpenBIOS; and
  `dt.kernel_ok` reads "kernel BAD" from the menu on under OpenBIOS (false
  positive). A 5-parallel `dt.py spots` run can spawn with area 0 (loading race)
  and then report wrong models: rerun sequentially before believing it.
- C16 car lifted onto the bridge when driving under it (sunken freeway) → D2
  trenches lie 1352 below street level (y 1352 down); where a street bridges them
  the cell has levels 0 and 1352 and "nearest street level" chose the bridge, so
  the car was snapped up 1264 and wrecked (drivetest baseline). Fix: `trench_rule`
  (lower level wins + wall-top cells, 2026-10-11): 619 sunken cells, 113 under a
  bridging road (8 crossings: trench cols 429-434 at rows 552-554, 716-718, 826-830;
  cols 661-664 at 734-735, 770-772, 826-830, 876-877; E-W trench rows 506-510 at
  cols 405-408), ~2900 wall-top cells. Driving under the bridges works (user,
  02:09). The street over the bridge (and every other two-level cell: decks over
  streets, wall tops, lanes beside ramps) → ROADSURF planes (`surface_planes`:
  every level of the cell and its 4 neighbours ≥ 300 apart, lowest first, info = 1,
  ~14.5k cells, 320 surfaces) + `driver_chicago.c` moving the plane nearest the
  player's height first each vblank (see Engine patches). Verified 2026-10-11 13:10
  on build-test: under and over the bridge at full speed, soaks clean.
- Crashes in some streets → stale models: Driver 1 only switches areas in
  border regions → switch entries everywhere + visibility-based area sets.
- Frozen picture (music on) → placeholder (size-0) models drawn while loading →
  redirect to the empty model.
- Picture freeze + music stop, kernel overwritten → empty model had 0 polygons,
  tile loop decrements first → 1 zero polygon.
- C33 freeze at an area switch (hang 193318, 9 → 1): I_MASK and timer-1 mode both
  0x071A → vblank masked, VSync waits forever (heartbeat: raise count runs, deliver
  stops). The kernel TCB (0x0E200) keeps the last exception's registers: vertex loop
  0x80030A44, count 0x4F8D, GTE stores past the scratchpad into the I/O area = a
  model read from texel data. The switch queues the new area's texture pages staged
  at spool buffer + 0xA000 (block 20, `ori a1,0xa000` 0x80033B2C, request queue
  0x800A7BA4: 7 × 17 blocks type 1, then models type 3); the old area's models
  (area 9: 36 blocks) sit there and the first sector lands ~13 ms after the
  request, often before the vblank hook's redirect → function-entry hook at
  0x80033B10 redirects the spool entries before any request (see Runtime changes).
  12 Chicago areas have > 20 model blocks (LA too, max 49).
- Play Again crash / scrambled textures → spool reset left the CD reader
  running → reset fixes (+ loading flag, else deadlock).
- Wrong models (DIESEL street, fragments) → second area switch during a load →
  switch waits for the load.
- Invisible buildings / holes / noise → page loader writes npal/4+1 CLUT rows;
  32 palettes zeroed the next slot's first 4 → max 31.
- Fatal "GP0 unknown command" → primitive buffer overflow by ground tiles →
  tile guard; tile list unbounded → cap 640.
- Curves/junctions black → DETAIL_* LOD textures missing from areas → LOD
  targets inherit areas. Trees as black quads → sprites kept as is.
- Distance tile textures wrong → SUBDIVISION UVs remapped. Tall objects
  vanishing → bounding spheres fitted. LA plane in a street → hidden.

## Open issues

- **Teleport-only fatals (C34 family, parked 2026-10-12):** teleporting the car into a new
  area while loads are in flight gives varying fatals (kernel at 0x0..0x200 overwritten →
  dispatch 0xB0; a smashed $ra 0x4E709A99, halt EPC 0x80079CA0), consistent with a spool
  read streaming to a stale queue slot's destination. Natural spawns/drives: none seen.
  Possible guard for later: the plugin, while no read is in flight, clears spool queue
  entries (0x800A7BA4, 16 B) whose destination lies outside the known spool buffers
  (the exe's chain end 0x80034CF8.. has no spare words for a bounds check).
- **Missing ground** at some spots (park: a band directly under/around the car,
  i.e. the near tile range 0x800287A4; freeway: all ground under the overpass).
  Gaps now show the clear colour (driver_chicago.c clears both DRAWENVs to dark
  water blue while a level runs; D1 never clears the frame). Not water (nearest
  river object 43k away), not flag 0x20 single-quad path, not PVS (pvs_full),
  tiles are listed (draw stamps) and all objects are in memory. Ruled out: tile LOD thresholds, SUBDIVISION data and
  UVs, sprite shadows, big-tile cell listing (CHI_BIG_TILE 1500), near-range
  NCLIP (tile_nocull), palettes/transparency, primitive limits, palettes of the band's primitives.
  Park details: the hole is where single-polygon grass tiles (#76, 0x0421 /
  flags2 0x4000, 1378 wide, y -22) have their centre within 2000 of the camera
  (near range). Their SUBDIVISION grids match their polygons. Unlike Driver 1's
  own single-polygon tiles (vertex pointer = polygon block, size 2120 / sphere
  1060), they carry real vertex arrays. fn tracing (fn_filter/fn_entry_dump)
  records only part of the calls; GPU dump "pc" = running code, not the emitter.
- Far water as separate squares → shrinking corner-less tiles + tile list cap →
  real corner vertices, one tile per cell, far planes (2026-10-11).
- Pink water near a sinking car → missing "SEA" texture → renamed (2026-10-11).
- Water inside building blocks / smear beside bridges → D2 "no surface" read
  as sea → D2 overhead map classification, water y 300 (2026-10-11).
- Black/missing buildings at some starts → start inside the 5-cell band kept
  area -1 → own-area rule also for -1 (area switch rewrite).
- Fixed 2026-10-10: cars falling through streets = primitive overflow into the
  road map tables (peak 0x235A4 > 0x1E000), now object guard + lower tile cap.
  Verify drowning (car driving into the river) again with intact road tables.
- Rare stall (1/19 soaks, overpass_s near the south edge): CPU stuck in the BIOS
  file-read device call 0xBFC128A8 in exception context, CD IRQ pending
  (starvation watchdog). Before it: libcd 0x80079B1C/0x80079CAC.
- Overpasses stretch close to the camera (no near-plane clipping in D1).
- Texture downscaling in dense areas (~600 halvings now; near-aware).
- Sky box seams (LA sky over Chicago); loading bar stops halfway (sized for LA).
- Minimap still LA; damaged wheel textures; LA with engine patches but without
  chicago-la hangs while loading (0x80035524, older).
- Stage B (roads/traffic/cops), D2 cars and music, 5th city.
- Two-level cells (C16/C17), remaining limits of the plugin selection: it follows
  the player only; traffic and cops (Stage B) will need per-car selection or a
  real engine loop (no spare exe words; see Engine patches). Data-only history:
  plain drop (`CHI_RAMP_STEP=0`, the user's car fell through the deck and
  flipped), stepped ramps (200: car inside the geometry over 6 cells, "worse"),
  a blocked crossing (barrier objects, not built). C17 ramps now get sloped
  ROADSURF planes (`cell_slopes`: D2 heights 300 off the centre, per-axis planar
  test) and decks are no longer flattened; smoothness at `rampsink` and the
  launch at the top of the trench exit ramps (full speed: the car jumps and may
  land on its roof, drive test 03:06) are for the user's test.
- Trench ends: the col 661-664 freeway runs into river tunnels (rows 733 and
  787 read sea, the surface has no planes in D2 tunnels) and under a street at
  row 878 (reads grass): the car is lifted/wrecked at those portals (C20).
  `trench_ends` (2026-10-12): covered stretches <= TUNNEL_GAP filled at trench
  depth; street gaps <= BRIDGE_GAP (2) between trench cells at the same depth =
  bridge (D2 samples only the bridge; the trench runs under, the street stays a
  plane); remaining dead ends rise over END_RAMP cells, only where the trench is
  <= END_RAMP wide across the end (without it 1898 of 2932 ramp cells were side
  ramps along beaches and wide sunken areas) and no trench cell at that depth
  lies within 3 cells ahead (+-2 beside the end's width): a bend is no end
  (wallstop1: a false ramp in the curving trench flipped the car); 346 ramp
  cells remain, the C20 freeway ends included; holes beside the trench filled at
  depth except void cells (drowning boundary). A ramp cell keeps its own street
  plane even inside the widened sep. Review 2026-10-12 (user /code-review): #2
  was wrong (inside cells have no D2 level, so there is no street to lose).
- C17 decks/ramps: ramps climb in 135–300 steps (one height per cell; smooth
  slopes need ROADSURF shapes), and the deck flattening drops the car halfway up
  (Live test, spot `rampsink`). Mirror of C16: a deck over a street can keep its
  height only if the street car is lifted, or drop the deck car at each crossing.

## Plan

B. Roads: rasterise D2 surface onto the D1 road map + ROADSURF; rebuild
   ROADS/JUNCTIONS/BOUNDS from STRAIGHTS2/CURVES2/JUNCTIONS2. Counts (2026-10-11):
   D2 Chicago 838 straights + 151 curves + 252 junctions vs D1 max NY 410 roads /
   258 junctions (Miami 365/234, SF 358/223, LA 259/167). D1 roads are straight with
   2 connections → curves become straight chains joined by 2-way junctions; chicago_d1.lev
   currently ships empty ROADS/JUNCTIONS/BOUNDS/ROADSURF (4 bytes each). To do first:
   find the D1 exe's road/junction array limits (consumers: civ spawn via road-map
   roadIndex, cop pursuit via BOUNDS), merge collinear straights, then validate the lumps
   offline in DriverLevelTool's viewer (D1 road overlay) before any game run.
D. D2 car models (+ D1 EXE cosmetics). E. D2 music → D1 MUSIC.BIN. F. 5th city.

## Polish items (Polish, 13.10.): minimap, sky, texture downscaling
- **Minimap (C12, `polish_map.py`, CHI_POLISH_MAP=1):** D1 overlay lump 24 = u16 tile offsets at +0 (max 160 tiles),
  8 bytes at +320 (kept), CLUT at +0x148, RNC2 tiles (32x32 4-bit) from +0x168. Per-city exe table 0x8008B080 + CITY*24:
  x_off, y_off, width, height, toptile (byte +0x10; tiles >= it filled with byte +0x11), scale. Pixel: column =
  x_off + z/scale, row = y_off + x/scale (0x800563CC; D1 maps are D2's turned a quarter). Width/height also copied to
  0x80096D2C/30 at level init (0x800541E8). LA: 324, 175, 192, 416, 78, 2812. Chicago (D2 map 3/4, turned, 16x9 tiles):
  253, 142, 512, 288, 144 | 9<<8, 3775 -- verified by poking (devtest/_out/1013-193042-polish-v2map). **Plugin to do:**
  write the CITY 3 entry (0x8008B0C8, 6 words) while Chicago is loaded, before 0x800541E8 runs (else also 0x80096D2C/30);
  restore LA's for LA. polish_map has its own RNC2 packer (round-trip checked against d2overlay.rnc2).
- **Sky (C10, `polish_sky.py`):** not level data. D1 sky = DRIVER/DATA/SKY.BIN (LBA 208, 228988 bytes; copy in
  work/d1_SKY.BIN): 13 x 48-byte tables (12 image offsets), file size, then 12 BMPs per sky (64x42 4-bit, 1464 bytes
  padded) = a 256x126 panorama 4 across x 3 down; dome v 0..126, horizon ~v 105. Sky number gp+0xD7C (0x800974EC)
  set at 0x8004ED84.. by CITY (jump table 0x800108A8): credits 1, LA 2 (rain flags 0x80096AA8/9 -> 3), Miami 4,
  NY 7, SF 10 (+1 night 0x80096850, +2 rain, only for CITY 0/1/5); loader reads 0x34 bytes at number*0x30 then the
  images (0x8004EED4..). PCSKY in the LEV is not what is drawn (changing it showed nothing). D2 SKY0.RAW (work/d2_SKY0.RAW,
  from the D2 disc DRIVER2/DATA) = same layout at 2x (512x252, 5 x 64 KB: day, night, rain, dawn, dusk); D2 rows 0..167
  are one continuous image down to the skyline base -> squeezed to v 0..105, flat ground colour below.
  `python polish_sky.py work/d1_SKY.BIN work/var_polish_sky_1.BIN` = D1's 13 skies + Chicago day 13, night 14, rain 15.
  Verified in game with a test-only in-place overlay (LA's sky 2 replaced: work/var_polish_sky_test_la2day.BIN at
  disc_user offset 425984): Chicago skyline + clouds by day (devtest/_out/1013-193402-polish-skytest). **Plugin/package
  to do:** ship var_polish_sky_1.BIN as a relocated SKY.BIN (new LBA + directory extent, like chicago.lev) and set
  0x800974EC to 13 (day) / 14 (night) / 15 (rain) after 0x8004EE20 when Chicago is loaded.
- **Texture downscaling (C7, `polish_tex.py`, CHI_POLISH_TEX):** pixel-bound, not palette-bound (areas need up to 16.2
  pages of 4-bit pixels for 10 free; one region alone needs 169 textures, so CHI_AREA_TEX < ~170 fails); UV crop saves
  0.5 %. `filter` = box-filtered halving (pair -> palette colour nearest the average), -10 % colour error at the same
  budget; `cost` = loss-ordered choice (-15 % error, but halves thin textures such as LINES 96 -> 12): not recommended.
- **C31 facade flicker:** the flicker buildings are plain boxes (no decal polygons; D2 Chicago has 38 decal-like polys
  in all); D1 per-object renderer (0x800307FC): groups before the first "sorted" group (bit 31) go into one per-model
  list at OT (z/2 + 0x1000) (LA uses that for ground-level polys), sorted groups per polygon at OT z; polygon flags
  0x20/0x40 pick near subdivision handlers (< 6000 / 9000 units, 0x80030B08).
- C1 (Polish 13.10.): two more ruled out at park (black strip ahead of the car, nothing drawn there): the LOD swap
  table (all swaps off: same strip) and the quick tile path for odd rotations (shape flag 0x20 cleared on the 43 tile
  models placed at non-quarter-turn angles: same strip). Note: Chicago places 9662 quick-path tiles (single-polygon,
  shape 0x20) at non-quarter-turn yang; LA has 17690 such tiles, all at quarter turns.
- Smashables (C24, Polish 13.10.): one global table at exe 0x8008AE90, 20-byte entries {name ptr (kuseg 0x0001xxxx),
  debris kind (10 box, 11 cone, 12 barrel/phone/parking, 13 other), param (0 / 0xFA0 / -6500 / -3300), param (0x320..0x1000),
  0}: CONE, BOX, CONE1, CONE2, BIN, BARRIER, BARREL, TABLE, CHAIR, UMBRELLA, UMBRELLA1, PHONE, PHONE1, SIGN00, NEWS,
  PARKING, FENCE (+ _TASTIC), CONE_TASTIC1..4, TRAININGCONES1..3. Chicago models missing from it: BARREL1/2, BARRIER1,
  BOX2/3, SIGN01..06 (_TASTIC).
- West map edge (Polish 13.10.): D2 has no bounds code; beyond its last surface cells sdGetCell returns sea_plane
  (deep water, type 9), so the car would sink in Driver 2 too. Our void ring = water/drowning matches D2; no change.
- Sky rows (C46, Polish 13.10.): Driver 1's sky renderer ignores the sky models' UVs. The loader (0x8004EF44..)
  uploads each of the 12 BMPs (bottom-up rows read from the end) with its own CLUT (CLUT ids 0x800BDD20 + 2*i) and
  builds a per-piece UV record table at 0x800BDE40 + 8*i; the dome draws band b of every quadrant from image row b
  and column polygon c from piece c (verified with a colour-coded test sky: top band = row 0, middle = row 1, bottom
  band (8..-6 degrees, horizon ~57 % down) = row 2; all four quadrants show the same 4 pieces). So the arrangement
  can only be set in SKY.BIN; D2's "row 2 for dome models 1/3" needs a plugin/exe change of the per-quadrant
  piece choice. polish_sky.py: CHI_POLISH_SKY=mirror puts D2's flipped rows (half brightness, D2's reflection
  rows y3/y4) below the horizon; CHI_POLISH_SKY_TOP=N starts the panorama at D2 row N (42 = less vertical squeeze,
  larger skyline). Both are read by build_package (polish_sky.sky_bmps) when the package is built.
- Minimap follow-up (C12, Polish 14.10.): (1) the exe's x/y offsets name the minimap WINDOW's corner; the car sits
  48 px in from it (as D2's overmap.c +48): polish_map.params now subtracts 48 from both (without it the minimap
  showed the area ~50 px away: Gold Coast/lake instead of the L downtown at l_down_e). (2) the overlay lump must be
  4-byte aligned (a 2-aligned 12530-byte lump hung the level load on the loading screen); tiles are now 4-aligned.
  (3) CHI_POLISH_MAP_F=1.5: 448 x 256 (14 x 8 tiles, scale 4247, offsets 177/78) for D1's 448 px width limit;
  verified in game at l_down_e (downtown grid, the L and the river around the car).
- C45 shared pages (Polish 14.10.): CHI_POLISH_SHAREDPAGES=1 (polish_pages.py) packs texture groups needed by exactly
  the same 2+ areas into whole "stable" pages first (one index per content, identical bytes in every listing area,
  at most CHI_POLISH_SHAREDPAGES_CAP=2 per area; caps 4/6 do not fit the texture budget); the rest stays per-area
  content. Stable indices go to <lev>.stable.json; only those may be skipped when resident. With CHI_POLISH_AREAS=2:
  street-weighted sectors per switch 175 -> 154 with skipping (b13: 169 at 5255 crossings; areas2+sp: 154 at 2628),
  downscaled textures 834 (b13 604). Level work/var_polish_c45_sp1_day.lev loads and renders (l_down_e run 14.10.).

## C42 Driver 2 cars, data prototype (Polish, 14.10.)
- `polish_cars.py`, switch **CHI_POLISH_D2CARS=1** (convert.car_set() returns "d2", cars = the D2 level). The slot map
  is D1 slot <- D2 slot: 0 (cop) <- 3, 1 <- 0, 2 <- 1, 5..8 (player pairs) <- 8, 9, 10, 12. Override with
  CHI_POLISH_D2CARS_MAP. Lump 28 has the same container in both games (13 x {clean, damage, low}). The damage entry
  is header + vertices only in both games, so it can be copied as is.
  - Lump 25: D2 entries {palette, texnum, tpage, clut_no} + a CLUT, or a reference to an earlier CLUT (REDRIVER2
    cars.c ProcessPalletLump). D1 entries are {palette, texnum, tpage} + a CLUT, with no terminator.
  - D2 palette 4 (a fifth colour) is dropped, because D1 has 4 colours.
  - The base city's pedestrian palettes (ARM1, JEANS1, ...) are appended.
  - D2 special pages are put in D1 pair order (minor page first); pages 68/69 are unused.
- **D1 car damage = u shift on the same page** (from the data layout):
  - Traffic and cop: the twin is at u+128, same v (BCK1->BCK1DAM, COP3->COP3DAM).
  - Player cars: u+64 per stage (xxDM0..DM3).
  - D2 uses u+128 for traffic and specials (FWING11->FWING12, SIDE1SPE 64->192); its lights have stages at +64.
- **Bug in all builds before CARPAGES:** texrepack packs traffic and cop textures one by one, which loses the
  +128 twins. Damaged traffic cars then show neighbour textures (b-level check: COP3->COP6, BCK1->PEDHEAD3).
  - Fix: **CHI_POLISH_CARPAGES=1** (also on with D2CARS). It keeps the traffic and cop pages whole as permanent
    pages (polish_cars.fixed_pages: pages with >= 4 used textures; D2 50/58/65, LA 5/6, Miami 3/4).
  - Cost: per-area budget minus the number of whole pages. Miami set: +1 permanent page, 672 -> 749 downscaled
    (Loop facades / landmarks): rejected by Strategy.
  - **CHI_POLISH_CARPAGES=2 (twin pages, default with D2CARS):** polish_cars.attach_twins gives every traffic or
    cop texture with a +128 twin a `twin` Item. texrepack.pack_group("perm") then calls polish_cars.pack_twins:
    the pairs go first into twin pages (clean at x < 128, twin at x+128); the other permanent textures are placed
    first-fit into the free space of those pages; the rest are packed as usual. Car items get low texture numbers
    (`carfirst`, because the car CLUT table holds 30 per page).
  - Twin-page results: Miami set: 16 pairs, 4 permanent pages, 672 downscaled, the identical list, so no cost
    (var_polish_c49_twin_1_day). D2 cars: 27 pairs, 5 permanent pages, 749 downscaled (the D2 car textures are
    larger: twin area 2.12 half-pages vs Miami 1.46).
- Player cars from D2 specials cannot get D1's +64/stage layout: their textures are up to 192 wide.
  - Needed: an engine change gated to Chicago (damage shift +128, 1 stage, for player slots), or D2 civilian
    bodies in the player slots.
- Engine items (Infrastructure): 9 D2 models vs 7 D1 slots; per-slot exe tables (wheel positions/size,
  collision box, handling, damage zones); the cop has no police textures in D2 Chicago (D2 cop = civ model 3 +
  lightbar from the engine).
- **C45 round 2: ping-pong-free switch entries (Polish 14.10.)**
  - Switches: CHI_POLISH_PINGPONG=1, also on with CHI_POLISH_CORRIDOR=2.
  - Cause of the flapping: the exe rule is positional. An entry fires anywhere in its band, and a region whose
    entries don't name the loaded area loads its own area right at entry.
  - So two regions across one edge whose fires disagree switch on every crossing of that edge:
    - border regions that point at each other (169/185 in b14: 16 -> 3 -> 16 on each crossing);
    - lateral border regions that point at different areas (corr3 185/186: 6 <-> 7).
  - Fix: `polish_areas.fix_pingpong` picks each region's two entries from the usual patterns plus the
    neighbours' targets, so no edge ping-pongs. It uses single-region and pair moves, and weights edges by street
    crossings.
  - What is left is structural: corners where 3 areas meet, since a region has only 2 entries.
  - Checks (scratchpad flapcheck.py: global, with reachable loaded states; routesim.py: 300 random street drives
    x 2000 cells):

    | level | ping-pong edges | street edges with ping-pong | switches | back-and-forth (within 6 cells) |
    |---|---|---|---|---|
    | b14 | 210 | 113 | 13008 | 650 |
    | corr3 | 230 | 120 | 13497 | 489 |
    | corr4 (AREAS=2 + CORRIDOR=2) | 93 | 39 | 5575 | 109 |

  - corr4 has 15 areas and 607 downscaled textures.
- **C42 "cop bonnet noise" resolved (14.10.):** no cop was in those shots. The car array (0x8009B0A4, stride
  0x18C, damage per zone at +0x114) held only the player. The "cop with lightbar" is the D2 fire engine's own cab
  (LITESPEC lightbar) seen from the chase camera after spins.
  - The red/white noise is the player-slot damage shift (+64 per stage) on D2 special textures.
  - The D2 civ/cop CLUTs on the permanent pages have no red variants, and the twins share CLUTs.
- **Car damage engine facts:** see research_d2_cars.md "Engine spec". D1 0x8003E6A0 is D2's DentCar. Zone tables
  are reached through per-city pointers; UV shift +128 (AI cars) or +64 per stage (player).
  - D2 DEN data converts 1:1 (polish_cars.write_damage_blob).
  - (Corrected: one damage table set for all cities, DTL.BIN at 0x801F8BC0; Miami cars dent correctly. C51 closed.)
- **C23 wallstop1 flip (Polish 14.10.):** not the 12.10. bend rule. That rule only acts on trench-end ramps, and
  ramps are off since R10 (`keep_trenchramps`).
  - Cause: split cells (R12, b8 13.10.). At the trench curve, D2 has a grass lip at street level over the trench floor
    (stacked: the floor runs on under it, ~1000 wide, e.g. (421,955)/(421,956)). `split_cells` classified the lip's
    samples by their top level as the neighbour's (street) part. A car in the trench hugging the east side then got
    the street plane under its wheels: lifted 1352 at speed, flipped, wrecked.
  - Fix: **CHI_POLISH_SPLITSTACK=1**. A sample whose stack contains the cell's own level is never the neighbour's
    part, so such cells are not split; 8 cells change (1468 -> 1460 splits).
  - Repro (pt.py hook, full throttle north from wallstop1, var_polish_c23_1_day): no lift (y stays -1188), no flip.
    With a right-steer sequence the car follows the curve to (-98920,-469091).
  - Trade-off: a street car on the lip falls into the trench up to ~750 units early. The alternative, a stacked
    height-rule cell, needs full-cell planes, which would let a street car float over the trench part of that cell.
  - Remaining C23 behaviour: hitting a plane-step wall (a trench edge without D2 collision boxes) at a shallow angle
    still drops the speed hard (800k -> 45k, bounces) instead of sliding.
  - Smooth sliding would need invisible collision rails along trench edges: generated collision-only models, boxes
    on a chained polyline with flush joints; box yang is in 64ths, so directions are 5.6 deg steps. Proposed, not built.
- **C52 check (Polish 14.10.): the trench edge where the car bounces has D2 boxes, and we keep them.**
  - The bounce points (D1 (-88320,-489585), (-88966,-486370), (-89591,-483966)) sit on a curved chain of concrete
    barriers BARRIER25OA3/OB3 (D2 object yang 61-63, one box each: 32/95 x 1024 x 1304). They are present in
    var_polish_c23_1_day with their boxes, at trench depth.
  - D1's box collision (0x8004B30C..: type-0 boxes) rotates the box centre by the object yang (matrix table
    0x800A6E8C, 64 steps). The box angle = object yang + box yang, both in 64ths. So joints are as in D2.
  - Shallow hits along the chain stop hard (800k -> 45k per joint) because of D1's collision response, not data:
    authentic D1 behaviour; no rails built (Strategy's rule).
  - Side note: convert.turn_model adds 64*q to the box yang, but the units are 64ths. It should add q (only
    TLIGHT01 is turned today).
- **C46 follow-up (Polish 14.10.):** engine proposal for D2's exact sky dome order in research_sky.md.
  - D1's dome loop takes per-polygon piece bytes from 0x8008AA8C[base + i] (bases 0/12/24/36).
  - UV records are at 0x800BDE40 + 8*piece, CLUT ids at 0x800BDD20 + 2*piece.
  - D2 uses BASE1..4 (20 polygons) with 28 pieces (cap, rows 0/1/2, flipped variants) via HorizonTextures/HorizonLookup.
  - Chicago-gated plan: D2 dome models; D2's 40-byte table written into 0x8008AA8C; bases 0/20/0/20; a 28-entry
    UV/CLUT table in mod memory.
- **C42 step 1, mixed car set (Polish 14.10.):** `CHI_POLISH_D2CARS=mixed` (`polish_carmix.py`).
  - Lump 28: slots 0-2 = D2 models (map 0<-3, 1<-0, 2<-1), slots 5-8 = the car set's player cars (Miami by day,
    LA by night) with their special pages.
  - D2 traffic/cop textures enter texrepack as source "D" from the Chicago LEV (no night darkening), with their
    +128 damage twins (attach_twins on "D").
  - Palettes: D2's civ entries remapped from "D", plus the base pedestrian ones.
  - `<lev>.dmg.bin`: civ vertex rows (900 B) + civ polygon rows (1260 B), slots 0-2, from work/d2_CHICAGO.DEN.
  - Cost vs b15: +1 permanent page (4 -> 5); 672 -> 749 downscaled textures, the same 30 new + 44 further building
    textures as for whole car pages (C49 list).
  - var_polish_c42_mix1_day.lev: loads, drives, no fatal error; Miami player car intact. No traffic was in view in
    the sanity run.
  - **mix2** (`CHI_POLISH_CARMIX_HALF=1`): the 38 D2 car textures (and their twins alike) are halved once
    (64x32 -> 32x32, BON 64x64 -> 32x64), so the set fits Miami's budget: 4 permanent pages. The city's downscaled
    list is identical to b15 (359 entries, 672 halvings). Original vs halved: findings/c42_mix2_cartextures.png.
    var_polish_c42_mix2_day.lev (+ .dmg.bin). **mix3 = mix2 built with CHI_ROADS=1** (b-builds set it; mix1/mix2 lacked the road lumps, so no AI cars spawned): 22-23 live cars, D2 Chicago police car in traffic (findings/c42_mix3_d2_cop_traffic.png).

## Chicago music (milestone 2, Polish 14.10.; polish_music.py)
- **How D1 picks the song:**
  - Music init 0x8004D208(song) reads 12 bytes of SOUND\MUSIC.BIN at song*8 ({xm, bank, next}), loads the XM
    and the bank, and uploads the bank (0x8004E214). It is called at 0x80022B5C with *0x800977A0 (unless CITY 4).
  - *0x800977A0 = (mission + 3) & 7, written by the mission loader at 0x800687A8..B8. Take a Ride: Miami 0x78
    -> 3, SF 0x7A -> 5, LA 0x7C -> 7, NY 0x7D -> 0. Chicago runs LA's mission 0x7C, so today it plays LA's song 7.
- **MUSIC.BIN** has the same container in both games ({xm, bank} x 8 + end, then XM + VAG bank per song). D2
  Chicago = songs 2 and 6. Bank sizes fit D1's range (D2 song 2: 80660 B, D1 max 86756 B).
- **Verified in game** (test-only in-place overlay `work/var_polish_music_test_inplace.BIN`: song 7 = D2 song 2,
  same file size, at disc_user 16122*2048):
  - Chicago day: song word 7. SPU RAM holds D2 song 2's bank (20/20 chunks) and none of D1 song 7's.
  - Voices 16-23 (music) play from the D2 bank (spu_voices).
  - Control without the overlay: D1 song 7 bank. Miami: song 3, D1 song 3 bank.
  - Audio: findings/music_d2_chicago_song2_in_d1.wav vs findings/music_d1_la_song7_control.wav.
- **Data:** `work/var_polish_music_chicago.BIN` = D1 songs 0-7 byte-identical (offsets +16) + 8 = D2 song 2 +
  9 = D2 song 6 (1085288 B). Ship it relocated like SKY.BIN: overlay + DRIVER/SOUND/MUSIC.BIN directory record
  (LBA 16122).
- **Shipped (Infrastructure 14.10.):** exe_patches MUSIC_SELECT (default, list 351): 0x800687A8..B4 = lw v1, 0x217C(gp)
  (MUSIC_XOR 0x800988EC: no xrefs, zero in dumps); addiu v0, s0, 3; andi 7; xor v0, v1; the original sw. W = 0 keeps every
  city's song (the dropped sign extension does not touch the low 3 bits). The plugin (mission_parse_entry, entry hook
  0x80068928 just before) writes W = (8 day / 9 night) ^ ((s0 + 3) & 7) when Chicago is active and the package ships
  music (sidecar flags bit 1), else 0. build_package: CHI_POLISH_MUSIC=1 copies work/var_polish_music_chicago.BIN to
  assets/music.bin after sky.bin + DRIVER/SOUND/MUSIC.BIN record patch. Verified (SPU RAM bank chunks 20/20): Chicago day
  song 8, night song 9; without music song 7 + D1 bank. A root's game.toml needs the 0x80068928 entry hook (else no
  C50 / music: _root_np and build-test lacked it until 14.10.).
- **Song select (engine, Chicago-gated, M8-friendly):** replace the store at 0x800687B4/B8 (`andi v0,v0,7;
  sw v0,0x1030(gp)`) with a stub that stores 8 (day) / 9 (night) while Chicago is active (plugin flag
  0x9F082104), otherwise (mission+3)&7. Other cities read songs 0-7 from the same file unchanged.
- **D1 car cosmetics / wheel table (Ghidra pass 2, Polish 14.10.; for C42 wheels):**
  - car_cosmetics = 0x8009AF04: 4 runtime entries of 100 B (25 words). Entry 0 = the player car, entries 1-3 = the
    AI models. DrawCarWheels 0x8003B208 indexes it by model.
  - Layout as D2's CAR_COSMETICS up to the wheels: 8 SVECTORs (headLight, frontInd, backInd, brakeLight, revLight,
    policeLight, exhaust, smoke) at +0x00..+0x3F, then wheelDisp[4] at +0x40..+0x5F (x = +-0x19 - disp.vx,
    y = -(suspension + 0x32) - disp.vy, z = -disp.vz). Wheel size is a constant 0x65 in DrawCarWheels (D2 has a
    per-model wheelSize).
  - Filled per level by LoadCosmetics 0x80052620 from the exe table 0x800853D8 (8 entries x 100 B per CITY;
    bases 0 Miami / 8 SF / 0x10 Interview / 0x18 LA+Chicago / 0x20 NY / 0x28 Newtown):
    - entry 0 = base + player car choice (0x8009683C);
    - entries 1-3 = base + 5, 6, 7.
    Then 0x8001BA14 adjusts the wheel points.
  - For D2 cars in Chicago: provide city 3's AI rows (and player rows) from D2's cosmetics, Chicago-gated (LA shares
    base 0x18).
- **C17-relevant (Ghidra pass 2):**
  - GlobalTimeStep 0x8001BAC0 -> StepCars 0x8001D648 -> StepOneCar 0x8001D6E4: per wheel, FindSurfaceD2-role
    0x8001EEB4 (pos -> ground point + normal from the 1500-unit road map ring, normal (0,0x1000,0) off the map).
  - Then CheckCarToCarCollisions 0x8001FAFC, RebuildCarMatrix 0x8001B380, CheckScenaryCollisions 0x8004AD94 (box test
    inlined).
  - MapHeight 0x8001F5B0 has the same road-map math.
- **C42 cosmetics rows (Polish 14.10.; polish_cosmetics.py, CHI_POLISH_COSMETICS):**
  - work/var_polish_cosmetics_chicago_day.bin / _night.bin hold 8 x 100 B, to replace the exe table rows at
    0x800853D8 + 0x18*100 while Chicago is loaded:
    - rows 0-4 = the time of day's D1 car set (day Miami base 0, night LA);
    - rows 5-7 = D2 cop (model 3), civ 0, civ 1 converted.
  - Conversion: lights 1:1 (D2 order = D1 order, 'fire' dropped). Wheels: vx +-8, vz same, vy + wheelSize - 64,
    from D2 x = +-17 - vx, y = -wheelSize - vy - susComp + 14 vs D1 x = +-25 - vx, y = -(susp + 50) - vy.
  - Wheel size: D1 draws the tread at a fixed radius 0x65 = 101 (D2's sizeScale = wheelSize*1.4142). D2 cop 53 -> 75,
    civ 0 49 -> 69, civ 1 52 -> 74, so D1 draws them 35-46% too big. That needs a per-model radius in DrawCarWheels
    (0x8003B208, the two `* 0x65 >> 0xc` sites) plus the wheel models' tread vertices.
  - Side find: today Chicago by day draws Miami's player cars with LA's rows (city 3 base 0x18); the day file fixes
    that too.
  - StepOneCar reads the same rows, so the D2 rows also change the ride height: check in game.
