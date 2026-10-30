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
| inputs (from the user's discs, not shipped) | Option A (16.10.): read from the registered disc images (`chicago/inputs.py`, disc list `<app>/game.toml [game] discs`, cache `<app>/setup_cache`); the old hand copies `work/d1_*.lev`, `work/d2_CHICAGO.*` only with `CHI_INPUTS=work` |
| converter | `python convert.py` → `work/chicago_d1.lev` (~5 min); one-command setup from the discs: `python setup_chicago.py --build build-test` (day + night + package, cached) |
| package | `python build_package.py --install --chicago work/chicago_d1.lev` (writes mods/preloaded; --install required since 13.10., test copies use CHI_PKG_DIR via dt.prepare; without --chicago the chicago-la feature is dropped!; test-bigmiami removed 13.10., R18) |
| EXE patches | `python exe_patches.py disc/SLUS_008.42.orig --apply disc/SLUS_008.42`, then psxrecomp `generate --bios D:/recomps/games/SCPH1001.BIN`, then `rebuild` |
| test build | `build-test` (CHI_TEST_BUILD=build-test for dt/lab) when the user's dev client is running |
| probe env | probes.json "env" reaches only the converter / package build (publish_playable); the running game never sees it. Runtime switches (plugin getenv, CHI_C88_*) cannot be probed: make the wanted behaviour the default (or package data) before a probe (C90, 24.10.). |
| probe packages | publish_playable.py used to copy mods/packages (incl. driver.personal's manifest) from build-dev, so new features / options from build-test never reached probes. Fixed by Strategy (24.10.): the probe copy overlays the probe build's packages except driver.chicago. After adding a manifest feature, check the probe folder's manifest. |
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

- **C37 engine (Infrastructure 16.10.)**: exe group SLOPE_DIV (exe_patches.py, shared list 384 -> 417): MapHeight
  (0x8001F8A8..E4) and FindSurfaceD2 (0x8001F2B4..F4) divide the plane term by divisor = 4096 + ((b - 4096) & D2_PLANES)
  (gp+0x1110 = 0x80097880; plugin -1 in Chicago, 0 elsewhere): Driver 2's sdHeightOnPlane, exact slopes from unit
  normals; D1 cities bit-identical (div truncates like the original rounding >> 12). Blocks rescheduled in place
  (one load moved into the preceding beq delay slot, HI/LO hazards >= 2 instructions).
- **Surface capacity**: surfaces are cell-local and rotatable (MapHeight: x / z within the cell, 2 rotation bits,
  height relative to the cell word), so cells share a surface when their pieces match. City-wide CHI_POLISH_SLOPES
  gave 3298 distinct surfaces (896 kept, 3612 cells dropped; ROADSURF would be ~650 KB). polish_slopes now quantizes
  (CHI_POLISH_SLOPES_Q = grid, gradient step, offset step): 125/250/375 grids still 2541/2241/1722 distinct; grid
  750 (pieces split only along cell diagonals) fits all 5417 slope cells under the cap with gradient step 64 (1.6 %)
  and offsets of 16: ROADSURF 61.5 -> 120 KB, in-memory section 336 -> 396 KB (host fine; M8 budget note).
  CHI_POLISH_SLOPES_EXACT now defaults to 0 (unit normals; the engine divides).
- Level work/var_c37_slopes3_day.lev / _night.lev = b16b recipe + CHI_POLISH_SLOPES=1 + Q 750,64,16.
- Checks 16.10. (build-test, drive 2.5 s from the spot, 10 ms samples): diag_ramp: the car drives off the bank top
  and descends 1100 units smoothly (|dy| <= 119 per sample, tilt up to 26 deg) into the river (drowns, as in D2);
  diag_embank / east_ramp_s / c28_bank: no fall-through, no fling, tilt and speeds like b16b. FPS fps_drop_2 0.494 /
  0.4915 vs b16b 0.4932 / 0.4912 (unchanged). Miami and Chicago boot. Teleport tests (writing the car position)
  break the physics in both levels: not usable for slope checks.
- **C55 moon gate (Infrastructure 16.10., shared list 417 -> 426)**: the sky-sun test's CITY load at 0x8004702C
  reads SUN_CITY (gp+0x1114 = 0x80097884; look_city_patches owns that word, CHI_MOON_GATE=0 keeps the LOOK_CITY
  load); plugin writes LOOK_CITY elsewhere (D1 cities unchanged), 0x7F Chicago day, 0x7E Chicago night. The glare
  call at 0x80047068 goes to stub 0x80011868 (MDEC string cave; seeds/ghidra_funcs.txt): SUN_CITY == 0x7E -> return,
  else j 0x800493cc. So at night the disc (D2 SKYMOON, CHI_NIGHT_MOON=1) is drawn without the sun glare. PS1-native.
- **C55 follow-up (Infrastructure 16.10., user review of "look": moon too bright, night looked like day)**: Chicago night
  runs with Driver 1's night flag 0x80096850 = 0 (LA's day Take a Ride + the darkened night LEV), so the sky-sun code
  takes its day branch: disc (FUN_000473F0: 24 x 20 FT4 + a rotating additive ray halo of brightness = visibility count),
  full-screen additive glare tile (FUN_000493CC) and an additive lens-flare chain (0x800470C8.., drawn while s1 != 0).
  The scene itself is dark at the same poses (checked); the brightening came from those effects. Now for Chicago
  (SUN_CITY 0x7E night / 0x7F day): stub 0x80011868 skips the glare tile and clears s1 (no flare chain); the disc block
  0x800474A0..0x8004751C is rewritten in place (same 32 words, load-delay nops removed): a3 = 0 (halo adds nothing) and
  the night moon quad is 30 x 26 (CHI_MOON_HW/_HH = 15/13; day sun and Driver 1 keep 24 x 20). CHI_SUN_SPRITE=0 = old
  disc block. Shared list 454 -> 487. Check 16.10.: night heading sweep at the user's 184636 pose shows the bigger moon
  with no halo/glare and a dark scene; day sun sprite only; Miami boots and drives.
- Look levels work/var_look2_day.lev (CHI_ROADS=1 + CHI_POLISH_TEX_HEIGHT=1, C7) / var_look2_night.lev (CHI_D2_LEV=night
  + CHI_NIGHT_MOON=1). Sanity 16.10. (build-test, devtest/c55, port 4465): Chicago day SUN_CITY 0x7F, night 0x7E, moon
  disc with craters visible while turning at the spawn, no glare; Miami SUN_CITY 0 (= CITY), drives; all alive.

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

## S1/S2: CLUT strip + slot 15 short page (Infrastructure 20.10., exe, all cities; default on)
- **VRAM facts (measured)**: slot 15 (x 960..1023, y 256..511) held the level-load CLUT allocator 0x80097550 (from (960, 256),
  4 per row) and the area slot CLUT blocks (64 x 8, table 0x800BE1BC); rows 427..502 are Driver 1's fixed HUD sprite block
  (uploaded as 960, 459, 64 x 53, so rows 503..511 are inside it too; (1008, 511) is a night CLUT), row 426 the loading CLUT
  (0x8003336C), (320, 511) the loading screen's CLUT (0x800508B0). The loading screen draws 320 x 480 interlaced at x 0..319,
  y 0..479 WHILE the level loads (v1 put area CLUTs at y 240..255 x 0..319: the first area's palettes were overwritten).
  Free in play and during the load: y 240..255 x 320..511 (region A) and y 496..511 x 0..511 (region B).
- **CLUT_STRIP (CHI_CLUT_STRIP, default 1)**: allocator starts at (320, 240); rows 240..242 stay the sky CLUTs' own cursor
  (0x800974E0 copy, as rows 256..258 before) + map CLUT; then region A (12 per row), then region B (32 per row); one advance
  routine ADV (cave 0x80010778) replaces the helper 0x800516AC and its inline copies (0x80051758, 0x80051C84). Area slots: one
  512-wide row each at (0, 496 + slot) (table writes 0x800520A0; area loader 0x8003393C: rect 512 x 1, CLUT words x += 64
  per 4 palettes, 0x800339E0). **Capacity**: region A 192 + region B 32 x first area slot. Chicago var_d2cars16 (first 6):
  allocator ends at (352, 501) = 374 of 384; Polish's slot-15 level ends at (208, 497); Miami (first 9) ends (384, 499).
  Overflow would overwrite the first area slot's CLUT row: a converter-side budget is needed (S2 CLUT dedupe is the real fix).
- **SLOT15 (CHI_S1_SLOT15, default 1)**: a permanent page with TEXTUREINFO flags bit 0x80 (converter CHI_POLISH_S1_SLOT15) goes
  through cave SC (0x800106D0, perm loop call 0x80051DF0): slot index 15 (outside the area loops' 0..14), rect (960, 256),
  upload 64 x 170 (rows 256..425; 0x800517B4 reads the rect height), page/slot tables 0x800BE278 / 0x800BE507 / 0x800BE744;
  running page rect, slot counter and overflow flag 0x8009757C unchanged. Driver 1 levels have no 0x80 page.
- **Cave**: 0x800106D0..0x8001084F = sound debug strings ('Error: Can't allocate SFX buffer' .. 'Bank: %d, Sample: ...'),
  unreferenced (no lui/addiu pair, no pointer word); seeds SC 0x800106D0, ADV 0x80010778.
- **MIPS load delays matter in caves**: the recompiled code honours them for some loads: v2 had `lhu s0, 6(s4)` directly
  before `sh s0, 0x16(sp)` -> Miami's first permanent page uploaded with a wrong height (sun glare gone, blue garbage in
  the sky). Never use a loaded register in the next instruction (also needed on real hardware).
- **Verified 20.10.** (devtest/infra, build-test): every texture CLUT (0x80087030, 4096 entries), the car CLUT table
  0x800BE9FC, tpages, page texels, the 12 sky CLUTs and the HUD block identical to the original layout in Miami, SF, LA, NY
  and Chicago; screenshots at the start pose differ only in moving smoke/traffic (Miami 319 px); Polish's
  var_polish_s1_slot15_1_day.lev: page 9 in slot 15 at (960, 256), rows 0..169 = its LEV texels, 10 CLUTs correct, area rows
  correct, HUD intact. Same CLUT upload sizes as before (no FPS / stall change expected).

## S4 design: RAM back into the 2 MB (Infrastructure 20.10., R39 follow-up; design only, nothing built yet)
- **Budget in play** (R38 captures, var_d2cars16 / d1_MIAMI, heap ptr 0x80097098, stack below 0x801F8B00..0x80200000):
  Miami heap end 0x1B24F0 -> ~280 KB free under the stack; Chicago heap end 0x1EA2AC -> **58 KB free**. Chicago heap
  (no cell objects): PVS buffers 4 x 32 KB, model spool 49 x 2 KB, cell ptrs 7 KB, cell data 68 KB, INMEMORY 341 KB
  (MODELS 202, ROADSURF 60, 24: 21, 20: 19, 9: 11).
- **What lives outside the 2 MB (Chicago)**: cell objects 196 KB (D1 formula: 4 barrel maxima 12160 + 360 straddlers x 16 B;
  the 512 KB mod buffer is reservation slack), C30 carry 54-86 KB used (256 KB reserved), car polygon buffer 34 KB, specials
  ~90 KB, rows / car tables / LTAB ~10 KB, model table 1223 entries x 4 = 5 KB (> 800: D1's table at 0x800A0E20 is now
  the c42m six-model tables), D2 surface table 2.2 MB (C37, host; M8 phase 2 = per-region blocks). **Chicago deficit
  without the surface table: ~420 KB needed vs 58 KB free = ~360 KB.** D1 cities: the original layout fits by design.
- **Pool for the cell buffer gains ~nothing**: per-region placement (Crash-style, regions in any 2 x 2 window must not
  overlap) vs D1's fixed barrel partitions, offline over all regions (scratch s4/pool_bound.py): Chicago objects barrel sum
  190 KB / 2x2 lower bound 174 KB / greedy 218 KB; cell data 68 / 56 / 78; PVS 90 / 88 / 142 (Miami 174 / 144 / 144,
  LA 152 / 128 / 168). D1's partitions are already within 10 % of the bound; the object indices in the cell data carry the
  barrel base (d1cells objs_add), so a pool would also need index relocation at load. Not worth it.
- **Real levers (Chicago)**: PVS buffers sized to the real maxima (converter writes 32768 each; actual 24 / 22 / 22 / 22 KB)
  **-38 KB**; carry as "pin the outgoing area": only possible with a second model spool area (98 KB) or a model-level pool
  in the spool buffer (shared corridor models stay, new area's models fill free 2 KB blocks; load path per model) -
  memory-neutral vs the carry's 86 KB peak, saves reloading shared models; in-memory models to area spooling (Polish, S1
  area work) -40..80 KB; car polygon buffer from fitted models -10..20 KB; specials block shared with the carry pool;
  stack reserve to be measured (58 KB zero run under it).
- **Plan proposed**: S4a (all cities, PS1-native, behind CHI_S4): cell objects back on the heap (original D1 code, no mod
  buffer) when heap end + objects + stack reserve fit, else the mod buffer (Chicago until the diet lands); carry in a
  heap-tail pool for D1 cities (Miami: ~106 KB slack after the objects). S4b (Chicago diet, converter): tight PVS, area
  spooling of in-memory models (with Polish). S4c: model-level spool pool replacing the carry. Measure each: free RAM in
  play (Miami + Chicago), STL1 stalls, FPS, area-switch screenshots (C30 / C68 classes).

## S4a (Infrastructure 20.10.): Driver 1 cities fully in the 2 MB (exe + plugin + converter; opt-in CHI_S4)
- **Model table in main RAM (all cities, always)**: NEW_BASE 0x80115600 (2048 entries, 8 KB); the level heap starts 8 KB higher
  (0x800228DC: 0x80115600 -> 0x80117600); cave ZT (0x80010814, called instead of 0x800505E0 at 0x800228F0) clears the table at
  every level start (the frontend used that RAM). C68 stub and the late-use fix 0x8004B7B0 follow NEW_BASE. The plugin keeps
  allocating an (unused) 8 KB block at 0x9F000000 so the other mod blocks keep their addresses (alloc_fixed order).
- **Sea level / Chicago flag** are RAM words 0x80097888 / 0x8009788C (gp+0x1118 / +0x111C, no exe xrefs; were 0x9F082100/04).
- **Cell objects (S4 flag 0x80097890 = gp+0x1120, plugin: env CHI_S4=1 or a file chi_s4.flag next to the exe)**: InitCellData
  (0x800397CC: `move t8, ra; jal S4C; nop; move ra, t8`, it is a leaf) calls cave S4C (0x800107C8): flag set and the heap end
  after objects + cell data below 0x801F8000 -> objects on the heap (Driver 1's own layout); else the mod buffer 0x9F002000.
- **Converter CHI_S4=1**: SPOOLINFO PVS barrel buffers sized like Driver 1 sizes its own levels (LoadRegionData 0x800342D4
  spools roadm to +0, roadh to +0x1000, then the PVS to +0: need = max(roadm, 0x1000 + roadh, pvs) per barrel; reproduces
  Miami / LA / NY / SF exactly). Chicago 4 x 32 KB -> 24/22/22/22 KB (-38 KB). Level work/var_s4a_1_day.lev (cars1 recipe).
- **Measured (build-test, start pose + 18 s drive)** - free RAM between heap end and the stack (deepest stack write in NY
  0x801FAC04 = 21 KB, painted-stack test): S4 on: Miami heap end 0x1E5750 (objects on the heap, 77 KB free), SF 0x1E48F4 (80),
  LA 0x1E6AA0 (72), NY 0x1F704C (objects on the heap, **14 KB gap to the deepest stack**; Driver 1's own NY had 22 KB: the
  model table's 8 KB); S4 off: Miami 0x1B44F0 (151 KB, objects in mod memory). Chicago: off 0x1EC2AC (50 KB, the 8 KB shift),
  S4a level 0x1E2AAC (88 KB); its cell objects (196 KB) stay in mod memory. FPS / STL1 stalls unchanged (same counts).
- **Still host-only for Chicago**: cell objects 196 KB, C30 carry <= 86 KB, car polygon buffer 34 KB, specials ~90 KB, civ rows /
  car tables ~10 KB, D2 surface table 2.2 MB; frontend menu block 0x9F082110 (all cities, Chicago-slot menu); dev FPS1/STL1.
- **Lesson**: hand-encoded MIPS words are a trap (0x0300C021 is `addu t8, t8, zero`, not `move t8, ra`); always asm().
- **Probe 'optimisation 1' hang (21.10.)**: AdEL at 0x8002CF60 on every map = a model-table use the linear site scan missed:
  0x8002CED4 `beqz v0, 0x8002CF48` has the (patched) `lui t7, 0xA` in its delay slot and the far-object block 0x8002CF48 adds
  0xE20 itself (C36 class). Fixed in MODEL_TABLE_LATE (0x8002CF4C). Since the 0x9F000000 table move it had read entry + 904
  for those far objects (wrong / no far models); a branch-following scan (scratch mtscan.py) finds no further site.

## S3 design: compressed area pages + pre-seek (Infrastructure 21.10.; PARKED, user Q39 = A)
- **Parked** because: with S1's dense per-area pages Driver 1's codec gives only 0.82 of raw (-18 %, -7 % with per-area
  padding); no cave space (Ghidra function dump: no dead code, only scattered unreferenced strings); stalls are not
  load-bound (routes6: opt1 = opt2a, ~0.55 s per switch, 4 stalls). Pre-seek only if pauses become noticeable.
- **Today's area page path** (0x80033B10 queue + 0x80033870 callback): per page one request of 17 blocks (0x11, sector =
  area gfx + 17 * k, 0x80033C70 / 0x80033CAC) into the staging window spool buffer + 0xA000 (blocks 20..36); the callback
  uploads the CLUT block (first 2 KB: npal, 63 CLUTs) and then the 32 KB of raw texels in four 8 KB chunks (64 x 64 VRAM px,
  double-buffered halves, chunk counter 0x80097244), so the upload overlaps the CD read.
- **Compressed pages** with Driver 1's own codec (the permanent-page format: npal, CLUTs, texels RLE-packed backwards,
  decoder 0x80035B5C): Chicago area pages 0.68 of raw (texels), i.e. 17 -> ~12 blocks per page; a switch reads 7 pages:
  ~-35 blocks (-70 KB, ~0.23 s at 2x) per switch; opt2a's average switch (textures ~238 KB + models ~112 KB) -> ~-20 %.
  Models stay raw (the codec is texel-specific; a generic LZ decoder would be new code, WipEout-style LZSS 0.64 measured).
- **Engine changes**: (a) per-page block counts and offsets (converter: a 16-byte size row per area next to AreaTPages, or the
  page record's first word); the queue builder reads them instead of 0x11 / +0x11; (b) the callback for a compressed page
  waits for the whole page (no chunk streaming), decodes in place (backwards RLE: compressed texels placed at the end of the
  32 KB window, checked: the format reads forward and writes the page from its last byte backwards, so a pure in-place decode collides
  at the end); either a window of 32 KB + compressed size (staging 49 blocks; Chicago's buffer has 49 / opt2a 88) or a strip
  decoder (new, ~40 words) that writes 64-row strips into an 8 KB ring and uploads each finished strip bottom-up (staging
  unchanged: header + compressed + 8 KB <= 17 blocks). CLUT path unchanged. Decode cost ~ a few
  ms per page (to measure), once per page per switch. PS1-native: ~120-180 words of MIPS in a cave (the S1 cave is full; a
  new cave needs an audit of unreferenced strings / dead debug code).
- **Pre-seek** (Spyro): when the player enters a region whose area differs from the loaded one (the switch trigger 0x80033F9C
  fires in border regions), D1 already queues the load; a pre-seek would issue CdlSeekL to the next area's first sector one
  region earlier. Gain ~ one seek (~100-200 ms on hardware; depends on the runtime's CD timing model). Needs the area of
  neighbouring regions (SPOOLINFO) and a free CD (no pending request).
- **Order**: S3 needs Polish's opt2a layout (area pages per area) as input; (a)+(b) first, pre-seek after measuring STL1 stalls.

## Chicago's menu picture (14.10., Design's CHICAGO preview)
- The picture quad of the Chicago row is LA2's: GP0 packet in FRONTEND RAM (0x801D2D30..): screen (160,194)-(288,422),
  texpage 0x0008 (VRAM x 512, y 0, 4-bit), u 0..127, v 0..227, CLUT 0x447C (VRAM 960,273). The row handler's word at
  0x801CDFC0 (LA 0x00C80148, Miami 0x00B60147) is not the GPU texpage/CLUT itself (not decoded).
- Plugin: preview_vblank (in the menu branch of chicago_slot_vblank) uploads rows 2..229 of the 232-row picture + its CLUT
  over LA2 while the highlighted row is Chicago (GP0 0xA0, sampled VRAM compare via gpu_vram_peek so it uploads once),
  and restores LA2 from a copy taken before the first upload on any other row. Verified: Chicago row shows Chicago;
  "Driver 1 cities", Miami, SF, LA, NY show their own pictures. CHI_PREVIEW=0 keeps LA's picture.
- VRAM in the menu (dump): framebuffers left, FRNT pages right; pages 13-14 at y 256 (x 832..959) are empty (room for
  a real data-path page later).

## Chicago sky/haze words (14.10., Design DAY_GRADE / SKY_SPRITES)
- Night moon: the plugin writes 0x80096C24 (x, y, z halfwords; the sun/flare routine's day vector, also used at night) =
  D2's moon_position (-32000,-11500,-18000) while Chicago night is loaded, D1's (-32000,-11000,-5000) otherwise.
  Verified in game. Host-only (M8: per-city vector or night LEV).
- Day haze: 0x80097138 / 0x80097150 are set by 0x800298BC per CITY (Chicago day: C3 0x7F -> default branch = Miami's
  ef ef ef) and read by 0x800270D4 (called from the map draw 0x8002C8FC -> 0x8002D0F4) into scratchpad POLY_F4 colours.
  Live pokes to red/blue in Chicago day changed nothing visible in a street view (test 14.10.): this word does not drive
  the far fade seen there; the haze is likely the D2 sky band or a depth-cue colour elsewhere. Not implemented.

## Host-only parts (Milestone 8: real PS1 hardware; user 13.10.) — each with a possible PS1 path
New engine features need a PS1-native path (guest MIPS in the exe, data within 2 MB RAM / 1 MB VRAM / CD).
| host-only today | where | possible PS1 path |
|---|---|---|
| (S4 measure 20.10.) Chicago in play: 58 KB free under the stack; mod memory needs ~420 KB (cell objects 196, carry <= 86, car polygons 34, specials ~90, rest ~15) -> deficit ~360 KB without the D2 surface table | see "S4 design" | S4a: D1 cities fully in 2 MB; Chicago needs the data diet (tight PVS -38 KB, in-memory models to area spooling, model-level spool pool) |
| mod memory 0x9F000000.. (Expansion 1: model table 2048 x 4, cell object buffer 512 KB, sea level / Chicago flag, menu block, FPS1/STL1) | exe_patches NEW_BASE, driver_chicago.c alloc_fixed | fit into main RAM: model table in a freed exe/heap area, cell buffer sized to the level (spool-limited), small blocks in a code cave; FPS1/STL1 are dev-only (drop) |
| model slots past 800 (2048) | exe_patches model table (88 words) | converter keeps a level <= 800 models (dedupe / merge), or the table in main RAM (above) |
| plugin logic (driver_chicago.c: Chicago slot / level table entry 3 swap, start move, menu pages + rows, Day/Night remap (Chicago + C63 LA day: entry swap, night flag, sky, song), CITY-opcode switch for the D1 extras, glow / day / sky / minimap code-word switches, sea level flag, ROADSURF plane selection, area-switch guard, C33 entry hook) | vblank / function-entry plugins | guest code in a code cave of the exe (or the FRONTEND overlay for menu work), driven by the same data (level table rows, per-city tables extended to a 9th city index instead of switching CITY 3 words) |
| runtime changes (disc overlays past the image end, CD DMA into mod memory, save states with mod memory, write guard, watchdog fix) | runtime_patches/chicago-runtime.diff | DMA/overlays disappear with a real disc image; save states / guards are dev-only |
| files relocated past the disc end (chicago.lev, chicago_night.lev, SKY.BIN with Chicago skies), directory-record patches, FRONTEND.BIN patches | build_package disc_user overlays + patches | build a new ISO / BIN: files in the file system (LEVELS/CHICAGO.LEV etc.), FRONTEND patched in place |
| plugin-only measurement (FPS1 / STL1 blocks, dev mode, overlay) | driver_personal.c | dev-only, not needed on hardware |
| Chicago menu picture (14.10.): plugin uploads design/previews CHICAGO (4-bit 128x232 + CLUT) over LA2's VRAM slot (512,0)/(960,273) via GP0 0xA0 while the Chicago row is highlighted, restores LA2 otherwise | driver_chicago.c preview_vblank, build_package CHI_PREVIEW | an 8th FRNT.B1 page (relocated file) + TPDATA/FECLUT entries + the Chicago row's own quad texpage/CLUT (FRONTEND overlay loader to decode) |
| setup from the disc images (Option A: psxiso.py, inputs.py, setup_chicago.py; Python on the player's PC) | chicago/ | M8 disc builder reads the same two disc sets and writes a new image instead of overlays |
| converter output limits checked only on the host (texture page budget, spool buffers, PVS barrels 32768) | convert.py / texrepack / polish_pvs | already PS1 limits (keep them): VRAM slots, spool buffer sizes, heap layout (C44) |
| C88 Nightmare / C92 Uncap (25.10.): the 24-slot cop array (47 KB) in mod memory, chaser assignment at spawn (plugin hook FUN_8001B720), cheats menu pages, Uncap CPU overclock + frame-wait skip (runtime) | driver_chicago.c, driver_gameplay.c, psxrecomp runtime | slots in RAM under the stack (Miami 77 / SF 80 / LA 72 KB free fit 24); **New York: only ~8 slots fit (14 KB free)**, so the real-PS1 build caps NY Nightmare at ~8 chasers (no cap on PC); chaser assignment as guest code in the spawn; Uncap has no PS1 equivalent (off = PS1 reference) |
| C94 Extra draw distance (25.10.): 27 x 27 PVS buffer + 4096-entry object list in mod memory, 2 x 0x50000 primitive buffers in the GPU-DMA aperture 0x00F00000, ~2x guest CPU per frame (needs Uncap) | driver_gameplay.c extra-draw, exe c94 words | none at 1.5x (RAM + CPU); the toggle off is the PS1 reference |
| C96 / C101 (25.10.): Nightmare / Hell levels on the 2 x 0x50000 aperture primitive buffers; the _xd level pair + XTMP buffer for Extra draw distance | driver_gameplay.c dp_big_prim_buffers, driver_chicago.c | Nightmare: Driver 1 buffers + its own car budget (near cars low-poly beyond ~11 full models); xd: none (feature host-only) |
| C129 D2 traffic (30.10., Strategy decision): the Driver 2 civ-AI core (REDRIVER2 civ_ai.c road following, chicago/c129) runs host-side in the plugin, hooked at Driver 1's per-car AI (FUN_80013D88), D2 cities only; needs ~50 KB guest RAM as an overlay (12 KB code, 21-29 KB road blob, ~7 KB state) | driver_chicago.c (hook) + chicago/c129 | the identical core built for mipsel (verified against the host path in every C129 test) as a recompiled overlay at a fixed main-RAM window once the RAM diet frees ~50 KB in D2 cities; diet candidate: Driver 1's replay recording buffer (0x801E0000.., up to ~80 KB in play) shrunk in D2 cities |

- **C42 r3 (b) six resident car models** (exe c42m is guest code + fixed RAM): host-only are the car polygon buffer for car
  set 4 (mod memory, 1400 entries = 34 KB; 6 Driver 2 models use ~900 entries = 22 KB, Driver 1's buffer 0x800AB728 holds
  666), the civilian zone rows (3.6 KB) and the DentCar level table (1.5 KB) in mod memory, and the plugin's choices (spawn
  list, PBUF/PCAP). The six-model tables sit in the old model-table area 0x800A0E20.. (free only because the model table
  moved to 0x9F000000, itself host-only). PS1 path: a 22 KB main-RAM buffer (or smaller fitted models) + the rows in RAM.
- **C37 phase 1 surface lookup** (driver_chicago.c d2sf_entry + assets/d2_surface.bin, 2.2 MB in host memory): Milestone 8 phase 2 = the same lookup as guest code in audited dead space (dead-code audit needed) + per-region surface blocks streamed with the region spool (~11-30 KB per Driver 1 region).
## Option A: discs as inputs (Infrastructure 16.10., R25; Milestone 3)
Every Driver 1 / Driver 2 input is read from the player's own disc images; nothing derived ships. One version each:
D1 USA v1.1 (SLUS_008.42), D2 USA v1.1 disc 1 (SLUS_011.61) + disc 2 (SLUS_013.18).
- **Reader** `chicago/psxiso.py` (stdlib; adopted from EXP's d2iso prototype): ISO9660 on MODE2/2352 BIN or CUE, Form 1 user
  data at +24; `tree / get [--raw] / find`. The one reader for both games.
- **Registry = the app's own disc list** (16.10. r2, user: the launcher must name all 3 discs, originals in
  D:/recomps/games, no disc1.bin): `<app>/game.toml [game] discs = [D1, D2 disc 1, D2 disc 2]`, `disc_serials =
  [SLUS-00842, SLUS-01161, SLUS-01318]`, `boot_discs = 1` (written by `python chicago/inputs.py register IMG.cue ...` into
  the root game.toml + build-test + build-wip; never build-dev or the frozen release). An image is identified by its ISO
  volume id (SLUS_00842 / SLUS_01161 / SLUS_01318) + boot exe md5 (D1 eee7d057..., D2 both 22ad9643...); wrong disc /
  version / not MODE2 = clear message. Full-image md5 of the Redump dumps kept in `inputs.PROFILES` (info only).
  D1 fallback: disc.cfg.
- **Runtime patch (main.cpp, `runtime_patches/chicago-runtime.diff` last section)**: `[game] boot_discs = N` (read straight
  from game.toml; 0/absent = upstream) -> only the first N roster discs boot. The launcher's Disc Selection lists all three
  with labels "<image> - game disc" / "<image> - setup input (Driver 2 city data): OK | MISSING | WRONG DISC (needs
  SLUS-01161, found ...) | NOT A PS1 DISC IMAGE"; the same lines + a fix hint go to the log at startup ("Disc Selection N",
  "input disc N"). A launch / persisted selection of an input disc boots disc 1 ("disc N ... is a setup input ...; booting
  disc 1"), clamped right after the settings read (before the mod/package target check) and after the launcher. Save
  states keep their unscoped names (scope only when more than one disc boots). Verified 16.10. (build-test copy, port 4461):
  labels OK, Chicago day + Miami drive, missing/wrong input discs reported, selected=2/3 boots disc 1.
- **Automatic build at game start (r3, 16.10., user: "load content from the Driver 2 discs like from the Driver 1 disc")**:
  `game.toml [game] prelaunch = "python driver_personal/chicago/setup_chicago.py --auto"` (root, build-test, build-wip,
  build-dev). The runtime (main.cpp run_prelaunch, right before the mod commit, never headless or with PSX_NO_PRELAUNCH=1)
  runs `<prelaunch> --build-dir <exe dir> --check` hidden: 0 = the build's package stamp (`setup_stamp.txt`: level keys of
  all chicago/*.py + recipe CHI_ROADS=1 + CHI_POLISH_MUSIC=1 + slot/pages, input md5s, D1 image, patched exe, preview) is
  current -> boot at once (~1 s); 10 = due -> `<prelaunch> --build-dir <exe dir>` in its own console window "Building
  Chicago from your Driver 2 discs" (streams the converter, ~9 min after a code change, seconds when only the package is
  due), installs atomically (pkg.new -> pkg), log setup_cache/logs/auto.log, then the boot continues. Driver 2 disc 1
  missing/wrong: a package without the Chicago row (engine extensions only; D1 cities work, an enabled chicago-slot
  feature that no package declares is ignored), console message + launcher label MISSING. Any failure: message box,
  boot continues. dt.prepare and publish_playable (fixpaths) strip `prelaunch` (test/laptop copies keep their own or
  the PC-built package). Verified 16.10. (build-test copy): run 1 built (511 s) then booted, run 2 booted in 4 s with
  Chicago (song 8); no-D2 check -> package without chicago-slot. dt.py defaults to build-test (spotplay keeps build-dev).
  Player tool form (Python on the player's PC vs a built tool) still open.
- **R27 3-disc probes (16.10.)**: probes.json `"discs": 3` (default for every entry except the six of 16.10. in
  publish_playable.LEGACY_ONE_DISC, which keep the 1-disc copy; `"discs": 1` forces the old form). A 3-disc probe: both
  Driver 2 images (.bin + .cue, original names) copied once into `<probe root>/_disc` (size/time; a fresh copy is
  md5-checked against the Redump dump), the copy's game.toml keeps the roster (3 discs, disc_serials, boot_discs = 1) +
  `require_discs = 3`, prelaunch stripped (Chicago still built on this PC and shipped), PROBE3 fixpaths.ps1 rewrites the
  3 disc paths to `_disc`. Runtime: `[game] require_discs = N` (opt-in, default off) -> message box "Discs required ...
  Disc 3 (<image>): MISSING | WRONG DISC ..." and exit 1 unless the first N roster discs are present and correct.
  Test overrides: CHI_PROBES_FILE, CHI_PROBE_ROOT (publish_playable). Verified offline 16.10. (dummy probe in devtest,
  build-test exe): Chicago (song 8) + Miami with 3 discs; D2 disc 2 removed -> refused with that message.
- **C45 quay round 4 (Infrastructure 16.10.), exe group NEAR_SUB (exe_patches.py, shared list 384 -> 501)**: Driver 2's
  near-only subdivision for D2 cities (gate gp+0x1124 = 0x80097894, bits 1 world / 2 tiles, plugin 3 in Chicago;
  CHI_NEAR_SUB_BITS tests) + piece drop (gp+0x113C = 0x800978AC, plugin 96; CHI_NEAR_PIECE). Textured-quad handler
  table entry -> cave WQ (diagonal >= 64 px pre-filter, then GTE depth of the 4 vertices, any SZ < 600 -> 4x4 handler
  0x80030F60, else an inline copy of the plain handler); tile near band entry depth < 2300 -> cave (near if depth <
  radius + 100); 0x80030C20 drops pieces with avg sz / 2 < 0x20 + NEAR_PIECE. Cave in the libgpu debug strings
  0x80011924..0x80011AD7, seeded (seeds/ghidra_funcs.txt, KSEG0 lines: the old 0x000xxxxx seeds were never loaded).
  - Findings: Polish's loop counter counts legit big near polygons too (player car at OT 7, near walls) and the scripted
    drive is not deterministic (runs differ by 25000 units), so "0/48" is not measurable with it. Glitch sources
    identified: GATE 1204 quads, SHOREWALL 1215 (its object gets near level 0 at the camera, so D1's per-object near
    level cannot gate this), water tile 683 (mid band while its edge reaches the camera). The start-pose wedge
    (SHOREWALL) is gone; residual dark beams still show in some loop frames (source not pinned yet).
  - FPS fps_drop_2 (b16b, 2 runs each): off 0.4900 / 0.4925, on 0.4828 / 0.4839 (-1.3 %; world -0.4, tiles -0.8).
  - Test harness: scratchpad it.py (pt.py clone, port 4463, --exepatch for interpreted test words), hook_loop4.py,
    hook_pick.py (polygons under screen points, triangle test as the GPU draws), hook_fps.py.
- **C45 round 5 (Infrastructure 16.10.): the dark beams were stale screen points, a converter bug.**
  - Deterministic camera test (scratch c45cam.py + camcount.py): plugin test hook CHI_TEST_POSE=<file> (driver_chicago.c
    test_pose_vblank, env-gated, host-only) holds the player car at "x y z angle" every vblank, so the chase camera settles
    on the same view; 5 anchors from the user's quay snapshots (003234/003300/140923/140902/003320) x 8 headings x
    near/far (700 back) = 80 frames, GPU frame decoded. Glitch = textured quad whose two triangles have opposite winding
    (twist, both >= 60 px^2) or a vertex at the GTE clamp with >= 400 px^2 on screen. Camera position RAM 0x8009D768.
  - Cause: Driver 1's world renderer transforms only the first tri_verts (model header byte +6) vertices into the
    screen cache when an object is near (depth - radius < 9000) and shape flag 0x8000 is clear; 0x20/0x40 polygons
    recompute their vertices, but plain ones (flags & 0x60 == 0) read the cache, so a vertex >= tri_verts takes the
    previous object's screen point -> twisted quads = the dark diagonal beams/wedges (SHOREWALL 1215 had 0; traced:
    written by the plain handler with all 4 SZ 3000..9600, i.e. not near-plane at all). Chicago's models all carried 0.
  - Fix (converter, default on, CHI_TRI_VERTS=0 = old): d1models.near_vertex_count sets byte +6 = highest vertex
    index of a plain polygon + 1 (instances take their source's; FARWATER/SHOREWALL too; tiles/sprites untouched).
    Camera test, original engine: 43/80 frames -> 7/80 (twists 0; the rest are thin ground strips with a clamped
    vertex below the car). NEAR_SUB (round 4) did not touch the beams (the quads were far); it stays opt-in.
  - Level work/var_c45_tv2_day/_night.lev (look2 recipe + the fix). Checks 16.10.: FPS fps_drop_2 0.4949 / 0.4950 vs
    look2 0.4947 / 0.4947 (unchanged); l_down_e drive + turn sweep clean; Miami boots and drives (converter-only change).
    Remaining "clamped vertex" polygons in the camera set: thin ground strips (tpage 28) under/beside the car with a
    vertex behind the camera (Driver 1 has no near clipping; same road texture, not visible in the shots; most are
    larger than the GPU's 1023 x 511 limit and dropped) and traffic cars pushed into the held car (car pages). No twisted
    quads (the beams) in any frame.
- **C61 (16.10.)**: Undercover opened the city list = the dev feature "Start at City Select" (driver.personal
  quick-city-select, enabled in build-dev's and even build-release's state): its stub jumped to Take a Ride while the
  game mode 0x800967F4 was 0, which it is again after backing out. Now one-shot per boot (flag 0x80097890) in
  build-test / build-wip's driver.personal manifest; mods/preloaded untouched (agents must not write it).
- **C62 (16.10.)**: LA minimap all red = minimap_vblank copied "LA's entry" from RAM on the first vblank, which during
  boot ran before the exe was loaded (garbage saved, written back forever). LA's exe values are now constants.
- **C64 / C65 (16.10.)**: Interview runs its own mission 0xAE (via_la_for: original setup, flag 0x80096854 = 1,
  traffic, song 1 = New York night); the selector's "Training" row is "Desert" (CITY 6 via LA's Take a Ride) with
  Miami's night song 4 (MUSIC_XOR for mission 0x7C only).
- **Exe from the image**: `d1_SLUS_008.42` (inputs.py, md5 eee7d057...) replaces disc/SLUS_008.42.orig as build_package's
  patch base (work mode still uses .orig). `python setup_chicago.py --check-exe`: exe_patches --apply on it == disc/
  SLUS_008.42 (aad320a4..., 16.10.), so the patched recompiler input is reproducible from the player's image.
- **Resolver** `chicago/inputs.py`: `inputs.path(name)` / `read(name)` with the old work/ names (d1_LA/MIAMI/FRISCO/NEWYORK/
  IVIEW/FLAT.lev, d1_SKY.BIN, d1_MUSIC.BIN, d2_CHICAGO.LEV / _night.lev / .DEN / .LCF, d2_SKY0.RAW, d2_MUSIC.BIN,
  d2_CITY.RAW): extracted once into `<app>/setup_cache/inputs/<d1_usa_v11|d2_usa_v11>/`, each checked against its md5
  (size + md5 table in `inputs.INPUTS`). Mode `CHI_INPUTS`: auto (default: discs when registered, else chicago/work),
  disc, work (the old hand copies; untouched). `CHI_D2_LEV` = day (default) / night / a path; the old spelling
  `work/d2_CHICAGO_night.lev` goes through the resolver too. Converter caches (*.pkl) go to `setup_cache/convert` in disc
  mode (`inputs.cache_dir()`; work mode keeps chicago/work as before). Day/night is decided by `inputs.is_input`, not by
  the path string. `CHI_D2_SKY`, `CHI_MUSIC_BIN`, `CHI_COSMETICS_*` = file overrides for experiments.
- Callers switched: convert.py (D2 LEV, LA base, car-set levels, DEN, caches), texrepack.py (Miami sea, night darkening
  day LEV, __main__), build_package.py (DISC_BIN = registered D1 image, D1 SKY.BIN, minimap D2 overlay + LA lump,
  car-set refs, **music built at package time** = polish_music.chicago_music(D1 MUSIC.BIN, D2 MUSIC.BIN) under
  CHI_POLISH_MUSIC=1, cosmetics generated from the D2 LCF when car set 4 has no override), polish_sky (SKY0.RAW),
  polish_map/polish_cosmetics/texbudget mains, polish_areas/polish_pvs caches. polish_slopes/cars/carmix take
  convert's D2 data already. The D1 exe (`disc/SLUS_008.42.orig`) is the app's own extraction from the D1 disc.
- **One command** `python chicago/setup_chicago.py --build NAME | --pkg DIR [--force] [--levels-only]`: discs only
  (`--inputs work` for comparisons) -> convert day + night (RECIPE `CHI_ROADS=1`; other CHI_* from the environment)
  -> build_package --slot (CHI_SLOT, CHI_MENU_PAGES=1) -> md5 list. Levels cached as `setup_cache/out/chicago_<tod>_<key>.lev`,
  key = md5(chicago/*.py + CHI_* level switches + input md5s): a rerun with nothing changed takes seconds; older
  outputs of the same time of day are pruned. Refuses build-release; build-dev only with `--dev` (user's go).
  dt.prepare / probes.py / publish_playable.py build their packages with build_package, so they read the discs too.
- **Check 16.10.**: (1) today's code from work/ (CHI_ROADS=1) == var_roads_b16b day/night (md5 16dcfd49.../408653b5...);
  (2) setup_chicago from the discs only (fresh setup_cache, caches recomputed): chicago.lev, chicago_night.lev identical,
  sky.bin 5023e0f8... == probe "city selector" (old code), music.bin a2ac6216... == the hand-made
  var_polish_music_chicago.BIN, chicago_slot.bin and manifest identical (only the music bit / music entries differ when
  CHI_POLISH_MUSIC=1); (3) audit hook: the converter opened 0 files under chicago/work, build_package only the level given
  on its command line. Sanity (build-test, port 4461, l_down_e, Chicago day via the city menu): CITY 3, sky 13, song 8,
  drove 28k units, alive, no fatal.
- **Ship audit** (what must never be published; driver_personal/.gitignore): disc images, chicago/work, *.lev/*.bin/
  *.orig/*.wav (before) + *.raw/*.tim/*.4bit/*.clut/*.cue, design/out/, design/previews/out/, setup_cache/ (added
  16.10.). Packages (mods/preloaded, build-*/mods/packages/driver.chicago, probe and playable copies) are built
  locally from the discs and stay local. Open: (a) `chicago_preview.bin` (class c) is Design's picture made from D2's
  sky panorama + a **game screenshot** (design_src/chicago_street.png): no disc recipe possible as is; the package
  takes it only when design/previews/out/CHICAGO.* exists locally (CHI_PREVIEW=0 = LA's picture). (b) findings/*.png
  and design/*.png are game screenshots/renders; 9 findings PNGs are tracked in git.
- **Disc copies (16.10. r2)**: app root game.toml/disc.cfg, build-test (game.toml, settings) and the build-dev config
  (single disc = the original D1 .cue/.bin; its 10-12 exe lacks boot_discs, so its 3-disc roster waits for a build-dev
  rebuild) all use the D:/recomps/games originals. publish_playable/probes copy the ORIGINAL D1 image under its own name
  into `disc/` / `_disc/` (+ the patched SLUS_008.42 + SYSTEM.CNF); fixpaths.ps1 rewrites the copy's game.toml to one disc
  (the D2 discs stay on the PC; the package is prebuilt). Still on <app>/disc/disc1.*: the frozen release build (disc.cfg,
  settings, game.toml), build-ovl, catalog_identity.json + [prepare_disc] (the setup wizard's own copy names),
  devtest/_root_np (hard link of disc1.bin). Old work/*.pkl caches deleted (414 MB); regionsweep reads road_levels from
  inputs.cache_dir().

- **C69 auto-build bound to the exe (Infrastructure 16.10.)**: the pre-launch build hashed the shared code, so a build
  whose exe was older (build-dev, 15:27 run, unfinished, package untouched) would have got a package built for newer
  engine patches. Now `<build>/chicago_exe.json` (written by `setup_chicago.py --mark BUILD`, build-dev only with --dev)
  binds the build's exe md5 to code_key() (converter + package scripts + disc/SLUS_008.42); auto() skips and logs
  ("skipped, package left as is") when the marker is missing, the exe is not the marked one or the code moved on;
  the package stamp also carries the exe md5. Mark a build right after installing a freshly generated exe (build-test
  after each regenerate; build-dev as part of a ship). build-dev has no marker yet: it keeps its 13:12 package.

- **C68 hang in probe "look" (Infrastructure 16.10., root cause EXP research_hang_look.md)**: FUN_0005F0EC (ambient
  objects on non-road cells listed by FUN_000143CC; runs while DAT_000976C8 != 0) ignores FUN_000217C8's result, which
  writes the cell model index only for a non-zero road-map cell word. Chicago has zero cell words inside its own
  960 x 1260 grid (map header DAT_0009E714/18, not an LA constant); the stale stack value indexed the model table out of
  range -> lhu AdEL at 0x8005F350 -> BIOS exception loop. Exe group C68 (list 438 -> 454, default on, CHI_C68=0 off):
  the call goes through stub 0x800118B4 (unused libgpu "$Id: sys.c" text, seeded) that clears local_30[0] first and
  falls back to model 0 for a null table entry. The index is the road map's 10-bit id (converter keeps road-map ids
  < 900), so no 11th bit is needed. Snapshots (driver_personal.c write_regs_json) now add badvaddr and the
  interrupted guest context from the BIOS TCB (0x108 -> PCB -> TCB: +8 r0..r31, +0x88 EPC, +0x94 SR, +0x98 cause) plus
  64 words at the guest sp; validated on the 184920 hang dump (EPC 0x8005F350, cause 0x10, sp 0x1F800330, ra 0x8005F328).
  Sanity 16.10.: Chicago day boots, idles and drives at the hang position; the spawner was not active there (flag 0).

- **C67 affine facade seams (Infrastructure 16.10.)**: exe group C67 (shared list 487 -> 554, CHI_C67=0 off): the light
  quad handler entry (table 0x9C, set at 0x8002D564/68; 0x80030718 = fixed 2 x 2 split for every 0x40/0x60 quad and 0x20
  quads at near level 0x10) -> cave LQ 0x80011924 (libgpu debug strings, seeded; shares NEAR_SUB's cave, the two are
  exclusive). In a Driver 2 city (D2_PLANES != 0) LQ projects the 4 corners (RTPT + RTPS), writes their screen points
  into the cache (v1 + 0x1F0, so the plain handler is right even for vertices >= tri_verts) and applies Driver 2's rule
  (REDRIVER2 draw.c): diff * 4 <= minZ - 350 -> plain 0x8003056C; minZ - C67_FINE < diff * 2 -> 4 x 4 0x80030F60; else
  the original 2 x 2. Driver 1 cities: straight to 0x80030718.
  - FPS fps_drop_2 (2 runs each, tv2 level): base 0.4927 / 0.4948; D2's FINE 150: 0.4918 / 0.4922 (4 x 4 too often);
    no 4 x 4 at all: 0.4967 / 0.4963; **FINE 0 (default): 0.4938 / 0.4946** = baseline. CHI_TRI_VERTS=all (count every
    polygon's vertices) cost 0.4 % and is not needed (the cave writes the cache): default stays "plain".
  - Camera set (80 quay poses): world twists still 0; the few flagged polygons are traffic cars pushed into the held car
    (different frames every run). l_down_e drive + turn: no holes.

- **C70 quay wall faces at/under the car (Infrastructure 16.10., user snapshot 202133)**: not near-plane strips but draw
  order. The faces were the land-side parts of quay walls that hang from street level to the water (999/1000 at the pose,
  traced via the packet writer's a1 -> model table; plus SHOREWALL 1215): Driver 1 sorts every polygon of a 'sorted'
  model by its own average depth, and a wall piece 2400 units away sorted nearer than the big road-tile pieces in front
  of it, so it was drawn over the road. (Tests that did not help: hiding via num_polys - the renderer walks the group
  table; flipping the group plane; an NCLIP back-face cull in LQ - it also culled real railings, kept as opt-in
  CHI_C70_CULL.) Fix, converter, default on (CHI_LOW_WALLS=0 = old): low walls (every placement: top at most 400 above
  the street, bottom at least 850 below; 60 models) get their polygons that lie wholly 50+ below the street into groups
  ahead of the 'sorted' group (d1models.BELOW_Y / plan_groups), so those are drawn at the object's depth, behind the
  road; parapets and railings above the street stay sorted. SHOREWALL's single group is unsorted entirely.
  Checks: user pose clean (faces gone, railing intact), 96-frame camera set clean (left: thin road strips with a clamped
  vertex, traffic cars), FPS fps_drop_2 0.4912 / 0.4916 vs 0.4910 / 0.4916. Levels work/var_c70_lw2_day/_night.lev.

- **C55 correction / C7 / C67 round 2 (Infrastructure 16.10., user review of "look 2")**:
  - C55: by DAY a Driver 2 city keeps Driver 1's sun glare tile, lens flare and ray halo again (SUN_CITY 0x7F takes the
    original path); only at NIGHT (0x7E) the stub skips glare + flare and the disc block zeroes the halo; moon quad 36 x 30
    (CHI_MOON_HW/_HH 18/15). Stub is 8 words again (0x80011868..87).
  - C7 adopted: polish_tex CHI_POLISH_TEX_HEIGHT default 1, CHI_POLISH_TEX_HIGH default 1536.
  - C67 r2: the user's remaining cuts (snapshots look 2 212541..) were on 0x60 facade quads ~110 x 75 px that LQ drew
    plain (small depth spread). LQ now splits a quad whose v1-v3 screen diagonal |dx| + |dy| >= C67_PX (96, GTE SXY0/SXY2
    after the RTPS) even with a small spread (2 x 2, or 4 x 4 by the FINE rule). Cave 105 words, into the GPU-timeout
    text (0x80011A98..AC8; sprintf's digit tables from 0x80011AD8 stay). FPS fps_drop_2 0.4888 / 0.4924 / 0.4884 / 0.4934
    vs 0.4912 / 0.4916 / 0.4910 / 0.4916 (-0.1 %, within the run-to-run spread). Flags-0 quads (1368 of 5070 textured
    quads) still take the plain handler unchanged.

- **C70 round 2 (Infrastructure 16.10., user snapshots "look 3 + quay" 222454..222539)**: the tall dark slab beside the
  balustrade was a SHOREWALL hanging from a raised level (instance at y -1594: the 2000-high wall then stands above the
  street); 120+ such instances city-wide. Polish's CHI_POLISH_SHOREFIX (bank level of the land neighbours instead, else no
  wall) is now the default (CHI_POLISH_SHOREFIX=0 = old). The large dark rectangle over the river is no geometry: only the
  sky dome (OT 0, tp 8) is drawn there, its dark lower band shows where the far bank is not drawn (visibility / C56 sky
  band, not C70). Camera set now 128 poses (+ 222505, 222526 anchors): no wall faces, railings intact; FPS fps_drop_2
  0.4918 avg of 4 vs 0.4924 (noise). Levels work/var_combo2_day/_night.lev. devtest/_c45root deleted.

- **C37 Option B design (Infrastructure 16.10., user's choice): Driver 2's own surface lookup in the engine, D2 cities.**
  - Why: Driver 1's road map has one surface per 1500 cell; the converter approximates D2's per-1024-cell BSP of planes
    with shared, quantised plane lists (cap ~900 ids), and stacked levels get full-cell planes swapped by a host-side
    selector -> floating / clipping beside ramps (slope_float etc.), coarse diagonal banks. slope_ref is right only where
    a single level fits the approximation.
  - Data: per Driver 2 cell (1024 D2 units) the original record: cell entry (one BSP root, or a level list
    [threshold, root] for stacked cells), BSP nodes (angle 11 / dist 12 / offset 8 bits), planes (surf, a, b, c, d).
    The converter re-packs the D2 records that overlap each Driver 1 region (30 x 30 cells of 1500 = 45000 units,
    about 44 x 44 D2 cells) into a new block appended to that region's spool data (after roadm/roadh), with a 44 x 44
    cell index (2 bytes each) + node / plane arrays local to the block. Size estimate from D2's own blocks (16 KB median,
    31 KB max per 65536-unit D2 region): about 7 KB median, 15 KB max per Driver 1 region; 4 resident regions =
    30-60 KB RAM (the road map tables already resident are 4 x 14.4 KB). Measured exactly before building.
  - Streaming: the block rides with Driver 1's existing region spool (same CD read, same ring slot of 4), so no new
    loader; a per-slot pointer (scratch words) is set where the road-map table pointer is set (0x8009D8F4 ring).
  - Lookup (guest code, PS1-native): D1 (x, z) -> D2 (fixed-point scale + offset, worldscale), region slot, cell index,
    BSP walk with the exe's own rcossin table (PsyQ rcos/rsin), plane -> height = -d - (a x + c z) / b (D2
    sdHeightOnPlane; the C37 SLOPE_DIV division), y_D1 = -height x SCALE; normal = (a, b, c) for the car's tilt.
    Stacked cells: D2's sdGetCell rule (the wheel stays on a level until it is below that level's switch height), so
    the host-side selector (driver_chicago.c surface_select_vblank) is no longer needed in D2 cities.
  - Hooks: MapHeight (0x8001F5B0) and FindSurfaceD2 (0x8001EEB4) branch to the cave when CITY is a Driver 2 city
    (D2_PLANES word) and the cell has D2 data; else the original code (water cells, outside, Driver 1 cities).
  - Fallback: no D2 block / cell entry -1 (sea) -> the Driver 1 road map as today (water model, drowning, map edge).
  - Measured 17.10.: D2's region block = 8-byte header + a 64 x 64 cell table (8 KB) + planes / level lists / nodes
    (1.8-23 KB). A Driver 1 region (30 x 3000 = 90000 D1 units = ~67 D2 cells across) re-packed: ~9 KB cell index
    (2 B per D2 cell) + 2-23 KB planes/nodes -> ~11-30 KB per region, 44-120 KB for 4 resident regions (vs the road map
    tables' 4 x 14.4 KB). Compacting the index (only cells with data, or 1 B per cell into a per-region list) roughly
    halves it.
  - Code space is the blocker for the native lookup: ~150-250 words of guest code (cell index, BSP walk with
    rcos/rsin, plane height, normal, level choice by switch height, two hooks). All known caves are used (C45/C67 libgpu
    strings, MDEC strings, C68 $Id text, DROWN_EDGE). A dead-code audit is needed (Ghidra: every function without
    call / jump / pointer references; a first call-only scan lists 171 candidates, most of them reached by j / jalr).
  - Phased plan: phase 1 = the lookup as a host function-entry hook (mod_function_entry_funcs on MapHeight /
    FindSurfaceD2 + a 4-word early-return patch reading a mailbox), all D2 surface data loaded into mod memory from the
    package (2.2 MB, host) -> correct D2 slopes for the user to judge in days; phase 2 = the same lookup as guest code
    in audited dead space + the per-region blocks streamed with the region spool (PS1-native, M8).
  - Code space: the BSP walk + plane evaluation is ~80-120 words; caves needed (to be found; the libgpu/MDEC string caves
    are used). Test: slope_ref unchanged, slope_float / 223147 / 223234 / 223249 no float or clip, diag_ramp /
    diag_embank / a river bank follow the ground, FPS fps_drop_2 unchanged.

- **C70 round 3 (Infrastructure 17.10., user "quay 2": walls no longer broken but disappear, visible only from one
  part)**: round 2 sent EVERY below-street polygon of the 60 low-wall models to object depth, including the faces that
  look at the river: from the water side / bridges those then lost the painter's order against the water tile pieces.
  Now only the UNDERGROUND faces go there: a below-street wall polygon whose visible side (-normal) looks at land (no
  sea_kinds water cell 400 units in front) at most placements (convert.low_wall_models -> d1models.BELOW_Y as a set of
  polygon indices). 15 models keep such faces. Water-facing faces are depth-sorted again. Checks: 128-pose camera set +
  user poses (202133, 222505): no faces over the road, railings intact; FPS 0.4947 / 0.4929 vs 0.4935 / 0.4929. The
  user's exact quay-2 camera (off the chase position) could not be reproduced with the held-car camera.
  Levels work/var_c70r3_day/_night.lev.
- **build_package: frame-less minimap lumps (17.10.)**: levels converted before the C12 default (no stored map frame,
  e.g. var_roads_b16b) were packaged with the new F=1 frame -> tile upload overran, garbage VRAM, void world (Design's
  harness). Such lumps now fall back to the old F 1.5 frame (env overrides).

- **C73 draw distance analysis (Infrastructure 17.10., offline + 1 capture at 222505)**:
  - Reach: objects are drawn from cells within a per-cell view radius of 5..9 cells x 3000 = 15000..27000 D1 units
    (= ~11400..20500 D2 units; D2: 16000-22000), chosen by the converter (pvs.radius_grid) so the polygons in range
    fit the per-frame primitive buffer (0x1E000 B x 0.72 at ~20 B/polygon = ~5500 polygons); the exe's cell loop
    (FUN_0002C8FC) is hard-wired to a 19 x 19 window (radius 9). Areas' model sets come from the same radii.
  - At the bridge view (222505) only 12 polygons sit at OT 0: the sky dome (tpage 8, LA's sky models 0..3); 58 far
    polygons are water / quay walls; no building across the river is drawn. The "dark rectangle" is the dome's lower
    band showing through where no far geometry is, not towers drawn dark.
    Correction (Polish 17.10.): that band showed the city-selector preview picture: the plugin re-uploaded
    chicago_preview.bin over VRAM x 512, y 0..227 (left half of the sky page 8) every vblank in game, because the
    menu mark stays in RAM and the Chicago row stays under the cursor. Fixed in driver_chicago.c preview_vblank
    (uploads / restores only when the highlighted row changes); the 222505 view now shows the d2v3 skyline.
  - No depth cue to tune: Driver 1 keeps the camera position in the GTE far-colour registers (RFC/GFC/BFC; read by
    world_renderer 0x800307FC and cull_objects 0x8002C5F0), so a far colour / fog for Chicago day needs new code.
  - Limits for more reach: the 19 x 19 window constant + cell pointer window (30^2 x 8 B), slot object buffers, the
    primitive buffers (2 x 120 KB, fixed in D1 RAM) and the polygon cost. Options: (a) a far "skyline" set: a few
    boxes per tall building (D2's own LOW_ set has only 10 small models), drawn beyond the radius in a cheap pass
    (~2-6 polygons each, ~100-300 towers -> 0.5-2 K polygons, one extra model area ~30-60 KB); (b) radius by view
    direction (open water / lake views get 10-12 where the cost allows; needs the window constant raised: RAM
    +~7 KB per +2 cells, FPS cost only in those views); (c) cheapest: give the dome's lower band a Driver 2 skyline
    texture (C46 sky) so the gap reads as distant city.

- **C37 phase 1 done (Infrastructure 17.10.): Driver 2's own surface lookup as a host hook.**
  - game.toml mod_function_entry_funcs += MapHeight 0x8001F5B0, FindSurfaceD2 0x8001EEB4 (regenerated); plugin
    driver_chicago.c d2sf_entry: on every call in a Driver 2 city it looks the query point (a0: x, y down, z) up in
    assets/d2_surface.bin (d2surf_asset.py; build_package CHI_D2_SURF=1, ~2.2 MB: D2's region blocks + curves) exactly
    like sdGetCell (level list by the wheel's height, BSP with precomputed rcos/rsin, sdHeightOnPlane, y down) and writes
    that plane (unit normal, d for the exact height at the point, in the cell's rotated (u, v) frame: bit30 swaps,
    bit31 negates) with a full footprint into polygon 0 of the cell's ROADSURF surface; a cell without a surface borrows
    a one-polygon scratch surface (mod memory) unless Driver 2 is flat within 40 of Driver 1's height (street). Driver 1
    water cells (model flags2 0x4000) and Driver 2 sea keep Driver 1. Cached per surface (plane, rotation, height).
    The vblank plane selector is off while it runs.
  - Checks 17.10. (var_slopes2_day = slopes3 recipe + current defaults; car centre vs Driver 2's level x 1.32 + 164):
    slope_ref mean 6 / max 47 (drive), slope_float 6 / 61, 223147 4 / 67, diag_embank 21 (flat offset), quay 3,
    riverbridge 22 (0 / 1 max tilt 4-15 deg). FPS fps_drop_2 0.4939 / 0.4933 vs 0.4907 / 0.4911 (the first version cost
    3-5 %: per-call guest writes; fixed by the cache, the street skip and direct RAM reads).
  - Open for the user's judgment: at the foot of 45-55 deg banks (diag_ramp spawn, c28_bank_w) Driver 1's car physics
    rolls the car over on the exact slope (the earlier approximated planes were gentler). shore_bank (C28 bank stored
    under the water line, converted to water) keeps Driver 1's water by design.
  - Switches: CHI_D2_SURF=1 (package), CHI_D2SF_MAXTILT (contact normal tilt cap, default 30), CHI_D2SF_DEBUG,
    CHI_D2SF_STAGE (profiling), CHI_D2SF_GSIGN (test).

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

## C42 engine step: Driver 2 cars (Infrastructure 17.10.; C57 / C58 / C59)
- **Design (sub-steps):** S1 data (converter, CHI_POLISH_D2CARS=1), S2 damage (exe + plugin), S3 player collision box
  (exe + plugin), S4 checks + level pair. Everything gated by car set 4 / main-RAM words that are 0 in Driver 1 cities.
- **Driver 1 car facts (Ghidra + runtime):**
  - Resident car models: 0 = the player's car (lump slot 5 + choice 0x8009683C), 1..3 = lump slots 0..2 (clean
    0x800A1AB0[k], damage 0x800A1AD0[k], low 0x800A1AE0[k]; loader FUN_000527BC). AI record +0x10 = resident model,
    +0x11 = palette 1..4 (the cop, resident 1, too); car struct +0 = car index, +2 = resident model. Cops (resident 1)
    also cruise in traffic (Driver 1 behaviour).
  - DentCar 0x8003E6A0 rows: AI row = resident model (1..3), player row = choice. The C42 civ blob had rows by slot
    0..2, so every AI car dented with the wrong row and slot 2 read the polygon table ("no dents on Driver 2 cars").
  - **Car buffers (C58 cause):** FUN_0003BDC8 builds the 4 resident models into ONE polygon buffer 0x800AB728 of 666
    entries (cap 0x29A at DAT_000973B0; textured quad = 1 entry, flat quad = 2). Per car: damage UV offsets 150 B (AI,
    0x800AF97A + car * 0x96; player 260 B at 0x800B08B8), 128 deformed vertices (0x800B09BC + car * 0x400). Driver 2
    models are ~250 triangles / up to 131 vertices: with the player + cop the buffer was full at resident 2 (160 of
    248) and resident 3 (lump slot 2) got 0 polygons = invisible traffic cars (wheels only); UV / vertex buffers
    overflowed into the next car (texture noise).
  - Car collision boxes are exe constants: car-car 0x80067C9C half 186 x 90 x 520 (162 x 468 when car+0x12E == 1),
    scenery 0x8003FF0C 169 (138) x 520, broad phase 0x8001FAFC rotated 209 / 585 + 90.
  - Main RAM 0x80097860..0x80097893 is NOT free (non-zero in 17 of 71 RAM dumps; 0x80097870 read 0x4545 in game).
    0x800988C8..0x80098977 is NOT free either: the felony event tables (FUN_00063C60 init, FUN_000650E4 reads event k's
    (counter, threshold) word at 0x800988C8 + 4k; zero in dumps because most thresholds are 0). C42E words therefore
    live at 0x80093380..0x80093390 (a 3144-B zero block of the exe image 0x80093378..0x80093FC0: no xrefs, no pointer
    formation into it, zero in all 71 dumps). Side find: the older words REGION_PENDING 0x800988E0 (C45, opt-in),
    STABLE_END 0x800988E4 and MUSIC_XOR 0x800988EC are felony events 6, 7, 9 (low halves only, thresholds stay 0, so the
    felony rules are unchanged; the level-init clear resets them until the plugin's next write).
- **S1 data** (polish_cars.py, polish_cosmetics.py, convert.py, build_package.py; switch CHI_POLISH_D2CARS=1, opt-in):
  - Slot map {0: 3, 1: 1, 2: 2, 5: 12, 6: 9, 7: 10, 8: 8} (player choice 0 = the default car = D2 12, the fire engine last). Driver 2's lump 25 has colour variants only for models 1
    (page 65) and 2 (page 62); models 0, 3, 4 have one paint, model 3's = the police livery (REDRIVER2: cop =
    residentCarModels[3], palette 0). So slot 0 = D2 3 (the cop) and civilians 1/2 = D2 1/2 (EXP's {1: 3, 2: 0} would
    put the police body on civilians, C59). Cop palette entries 0..3 = the textures' own CLUTs (cop_palettes(); without
    them Driver 1 drew the cop with stray CLUTs).
  - C57: scale_model() x1.32 (CHI_POLISH_CARS_SCALE) on vertices + bounding sphere of clean, damage and low models.
  - C58: fit_model() (CHI_POLISH_CARS_FIT=0 = off): triangle pairs sharing an edge with the same texture, UVs and normals
    -> one quad in ring order (Driver 1's builder swaps v2/v3 into GPU Z order, so the quad draws exactly the two
    original triangles; verified triangle-identical); flat pairs -> F4 split on the shared edge; > 128 vertices: the
    shortest edges welded (D2 3: 2, D2 10: 3, D2 12: 1). Result: polys 132-152, AI <= 149, buffer 604 of 666 (taxi).
    DEN rows remapped to the new vertex / polygon numbers (damage_tables(den, fit_maps)).
  - Sidecars: <lev>.dmg.bin 5040 B (civ verts 900 + polys 1260 by resident 1..3, player verts 1200 + polys 1680 by
    choice), <lev>.cos.bin 800 B (cosmetics rows 0-3 players, 5-7 residents 1-3, x1.32 with D1's own wheel x offset),
    <lev>.box.bin (player colBox x1.32). build_package -> dmg_civ.bin, dmg_player.bin, cosmetics_*.bin, car_boxes.bin.
  - CHI_POLISH_CARMIX_HALF=1 + COPFULL=1 work in this mode too (D2 civilian textures halved, cop full): 4 permanent
    pages, downscaled list 661 = the baseline's (no city texture cost).
- **S2/S3 engine** (exe_patches c42e_patches, shared list 713; C42_TABLES):
  - C42_TABLES entry 4 one row lower (0x800A0CF4 / 0x800A1050): row 1 (cop) lands at the blob start.
  - DentCar clamp / shift: player cap 3 ^ PDMG, shift 6 ^ (PDMG >> 1); PDMG (0x800988D0) = 2 for Driver 2 player cars
    (AI rule: 1 stage, +128 = their damage twins), 0 = Driver 1 (+64 x 3). PDMG = 0x80093380.
  - Player zone rows: the plugin allocates a "car tables" block (mod memory, after the FPS overlay's 0x9F082310) and
    points entry 4 of the player tables (data words 0x8008A6CC / 0x8008A70C) at it: Driver 2 rows, or Driver 1's
    copied from DTL for a car set 4 level with Driver 1 player cars.
  - Player box: car-car (loop body rewritten without load-delay nops) PBX / PBZ (0x80093384 / 88) for car index 0;
    scenery PBS low half (0x8009338C) + PBZ; broad phase margin 90 + PBS high half (the player's extra reach over
    585 / 209; 0 for a car of Driver 1 size). Driver 2 civilians x1.32 are within 8 % of Driver 1's box: unchanged.
    Plugin test switch CHI_C42E_BOX=0. A first version added PBZ to every car's broad margin: -9 % FPS (more narrow
    tests in bunched traffic) -> high-half extra.
- **Checks (devtest d2c, l_down_e, var_d2cars4 pair):** buffer 604/666, all 3 AI models drawn side by side / near /
  4000 / 9000 (blue D2 2 civilian visible beside the player, before: wheels only); cars the size of the player's D2 car;
  cops in D2 police livery, civilians in colour variants; crash: zones on both cars, dented; night OK. FPS standing
  22.1 vs baseline (Miami cars) 22.4 (taxi), 21.6 with the fire engine (its broad margin).
- **Open / limits:** the fire engine (now choice 3) fills the chase camera (camera distance is Driver 1's); specials' wheels drawn at D1's fixed radius 101 (fire engine D2 168); lights jump to their
  +128 stage (variant B = per-polygon D2 levels not built); cPoints (D2 body contact points) not used.
- **Host-only (M8):** the car tables block lives in mod memory and the plugin writes the rows / words; a PS1 version
  keeps the rows in a level lump and sets the words from the car-set data at level load.

## C72 river speckles at riverbridge (Infrastructure 17.10., analysis, not fixed)
- Reproduced (var_c70r3_day, CHI_START riverbridge, heading 0): a thin sloping line of opaque, saturated multi-colour pixels
  (165 px, x 320-503, y 139-144, 111 distinct 15-bit colours) along the far water edge where the quay meets the water;
  present in both frame buffers (drawn every frame), only in that view (headings 1-3 clean).
- GP0 frame (911 prims, no VRAM upload in the frame): every textured prim touching the band was rasterised with its own
  CLUT (35 prims: water p640 c992,285, quay p832/256 c992,368 and c1008,372, balustrade p768/256 c992,363, sky p512):
  none gives saturated colours; texels just outside their UV boxes are not saturated either. The only saturated CLUT is
  the minimap's (c960,256, semi tiles on page 768), whose top tile row lies at y 142-145 but is clipped by the minimap
  draw area (E3/E4 400,160-495,219), and the speckle line slopes with the perspective (the minimap rows do not).
- Owners of the speckle pixels by draw order: long stretched quads of the bridge side (p832/256 c1008,372 uv v238-246,
  vertices y 39..229, the C45 near-clip family) and the minimap rows.
- 111 colours from 4-bit CLUT textures point at blending or a sampler edge case, not one wrong CLUT. Next step: the
  same frame in DuckStation (psxrecomp/tools/gpu_parity.py) to tell emulator from game data, or stop the long
  stretched quads (C45 round 3) and look again.

## C66 garbled bottom strip = car polygons through the camera (Infrastructure 17.10.)
- Found in the 16.10. 'holes' captures (devtest/_out/1016-164840-infra-holes s10/s11): a cop right behind the player,
  inside the chase camera, drawn as huge garbled polygons over the bottom of the screen. Driver 1's car drawers
  (triangles 0x8003DF94, quads 0x8003E244) have no near test: vertices behind the camera are saturated by RTPT.
- Fix (exe_patches c66_patches, PS1-native, gated): the GTE FLAG of the RTPT is read before NCLIP (which clears it); bit 31
  (SZ / divide / SX-SY saturation) & NEARCULL (0x80093390; plugin: 0x80000000 while Chicago is loaded, 0 elsewhere) rejects
  the polygon like a back face. Triangles: cfc2 + NCLIP moved one slot, the mask loaded into a free load-delay slot;
  quads: mask in fp (saved by the prologue), NCLIP / stores shifted one slot, the 4th vertex's RTPS in the branch delay.
- Check: a traffic car moved into the camera (300-1300 behind the player): drawn clean, no strip; FPS standing 22.1 (=);
  Miami: words 0, cars normal.

## C45 corridor layout re-check + C30 model carry (Infrastructure 17.10.)
- **corr4 with today's defaults** (CHI_ROADS=1 + CHI_POLISH_AREAS=2 + CHI_POLISH_CORRIDOR=2 = var_c45corr_day/_night vs the
  same converter without them, var_c45base_day): 6 routes (scratchpad routes6.py: teleport by test pose, settle, 40 s
  heading-holding drive with reverse-on-stuck; l_down_e N/S, park N, blueboxes S, c30 S, flicker2 E):
  - area switches 12 -> 4, STL1 stalls 10 -> 6, mean FPS 24.7 = 24.7, load time per switch ~0.5 s in both;
  - switch screenshots clean (no wrong textures / holes seen);
  - cost now: 15 areas instead of 21, downscaled textures 661 -> 789; 89 textures lose resolution, 306 K texels, many of
    them landmarks (Adler Planetarium, Art Institute, Chinatown, Field Museum, Merchandise Mart, Navy Pier, EL). With
    the C7 height rule the baseline improved; corr4's bigger areas now cost more. -> not made the default: user decision.
- **C30 buildings popping out during an area load:** the user's snapshot (probe_look 20261016-184018, area 12, LOADING):
  708 model-table entries on the empty model and no streamed model left: the area-switch guard (C33) sends every streamed
  model of the outgoing area to the empty model until the load completes (~0.5 s), so all area buildings vanish. Not the
  page swap (old hypothesis). Fix (plugin, host-only): at the switch (entry hook 0x80033B10) the streamed models are
  copied to a carry buffer (mod memory, 256 KB; absolute vertex / polygon / normal / collision pointers relocated) and the
  entries point at the copies; when the load completes the loader's pointers replace the shared ones and the remaining
  copies (outgoing area only) go to the empty model. Log: 115-168 models (54-86 KB) carried per switch, 37-84 replaced by
  the loader. Primitive-buffer use during loads (A/B, same routes): without carry it fell to 30-45 % of the frame before
  the switch (buildings gone), with carry it stays. CHI_C30_CARRY=0 = old behaviour. Carried models draw with the old
  area's pages; with corr4 the corridor regions use pages both areas share. M8: needs a second model buffer in RAM.

## R30 package (Infrastructure 17.10.): quick-city-select off, corr5 default, C37 joins, LA day sky, C30 residue
- **quick-city-select OFF (user rule):** the driver.personal manifest already defaults it off; publish_playable.force_off()
  now disables it in every published state (probe copies + the playable copy). build-dev's own state.toml still has it on:
  switch it off with the next build-dev ship. dt.prepare / cellprobe states never enable it.
- **corr5 = converter default** (user ✅): polish_areas CHI_POLISH_AREAS "2", CHI_POLISH_CORRIDOR "2", CHI_POLISH_AREAS_SHARE 0.8,
  polish_tex CHI_POLISH_TEX_PROTECT "1" (each "0" = off).
- **C37 round 2, joins:** traced at slope_ref (trench floor -> 7 deg ramp -> street, D2 plane 406 between 741 and the
  street): the car's pitch overshot to -944 at the foot (ramp pitch ~-510) and nosed down to +555..+1324 after the crest.
  Driver 2's FindSurfaceD2 / sdHeightOnPlane have no smoothing either (REDRIVER2 dr2roads.c); Driver 1's car reacts harder to
  a crease. The hook now averages a cross of radius R around the query (central-difference gradient; samples > 120 off the
  centre plane's extension are not used, so kerbs / walls / other levels stay sharp), only within 3000 of the player
  (AI cars keep the exact planes). R (D2 units): 0 -> foot -944 / crest -735..555; 256 -> -873 / -692..651; 512 -> -636 /
  -523..445; 768 -> -614 / -535..500. Default CHI_D2SF_SMOOTH=512 (a vertical curve of ~1350 D1 units). FPS 22.6 = 22.6.
- **C37 round 3 (R31, user 'slopes 3': perfect except "a very slight bump while driving UP" slope_ref):** triangle
  kernel (CHI_D2SF_KERNEL=tri, default; box = round 2): the cross at R plus the cross at R/2, per axis weights 1 2 3 2 1
  (height) and the mean of the two central differences (slope), so the curvature of a crease also ramps in. Drive-up runs
  (floor -> 7 deg ramp -> street, 2 each): crest nose dip 447..449 -> 429..435, crest vy step 36.7k..38k -> 31.3k..37.5k (box
  noise ~ the effect: the user judges). CHI_D2_SURF is now the package default (build_package; CHI_D2_SURF=0 = off).
- **C63 LA day far streets (Design 18.10.):** the far-street flat quads take the plane word 0x80097150 and the fog word
  0x80097138 (0x00BBGGRR, set once per level by 0x800298BC, read by 0x800270D4); they held LA's night values in LA day. The
  plugin writes plane (112, 111, 105) / fog (226, 212, 190) while la_day_active() (LA night, D1 untouched). Checked.
- **Capture harness (for Design / QA):** chicago/devtools/capture_city.py OUT laday|lanight|chiday|chinight [--copy design
  --port 4490 --prep]: prepares the copy from build-test with the current levels (d2cars9 + LA day 8), drives the pages
  menu, saves menu / start / drive shots, prints city / night / look / sky / plane / fog words.
- **C63 LA day sky:** build_package.chicago_skybin(la_day) appends Design's design/la_day_sky.py sky (recipe on the player's
  D1 sky 10) as SKY.BIN 16 when CHI_LA_DAY_LEV is packaged (one SKY.BIN with Chicago's 13-15 per CHI_POLISH_SKY), sidecar
  flag 4; the plugin's LA by day takes sky 16 then (CHI_LADAY_SKY overrides). Checked: LA day sky 16, song 2.
- **C30 residue (probe 'loading' 20261017-1901*, not during a load):** reproduced exactly with var_polish_c45_corr5_day at the
  snapshot pose (D1 124928,164,-2407 hdg 3062): the lower half of a far tower is overdrawn by a huge stretched ground quad
  (p896/256 c1008,376, uv 7 x 16 texels, screen y 71..241) that the ordering table sorts in front of the building; as the car
  moves the sort flips, so building parts pop. C45 near / big-quad family (NEAR_SUB subdivision would also fix the order),
  not the area loader.

## C42 round 3 design (Infrastructure 17.10.; user points a-f of R30; D2 = REDRIVER2 src_rebuild, EXP research_d2_cars_r3.md)
**Driver 1 today (facts):** resident car models 0 = player (lump slot 5 + choice), 1 = cop (slot 0), 2-3 = civilians
(slots 1-2); arrays clean 0x800A1AB0[], damage 0x800A1AD0[], low 0x800A1AE0[] (loader FUN_000527BC writes 6 clean entries but
damage[4..5] = low[0..1]: only 4 usable); car polygon groups 4 x 0x3C at 0x800AF5B0 (FUN_0003BBF8 / BDC8) in one 666-entry
buffer; per car: UV offsets 150 B (player 260), 128 deformed vertices. Civilians spawn as model 2 + rand % 2 with palette
1 + rand % 4 (FUN_000154A8 / 16760 / 1638C); pursuers are model 1 unless 0x80096774 ("unmarked cops", 0 in Chicago) or
0x80096770 == 0; plain traffic also carries model-1 patrol cars (D1 behaviour; in the 7 'd2 cars 2' snapshots every model-1
car is a cop or a patrol car, no cop drove a civilian model). AI records 22 (0x80098950, 0x50 each) + player, car array 25.
**Driver 2 (reference):** MAX_CARS 20; PSX 5 resident models: civ list modelRandomList[16] over slots 0-2 + 4, cop = slot 3
(requestCopCar), slot 4 = SPECIAL_CAR_SLOT (spooled per region; specModelValid / allowSpecSpooling; model 8/9/10 with siren via
CarHasSiren); palette 0 for model 0 / >4, else 0-4 random; car_cosmetics per resident model (FixCarCos centres the wheels:
delta.vz = -(wheelDisp[0].vz + wheelDisp[1].vz - 14) / 2; body drawn at where + R * cog, DrawCarObject); wheel radius =
wheelSize * 14142 / 10000 per model (cars.c); colBox / cPoints per model; sound banks per resident model
(MapCarIndexToBank, car_banks[4][9]); DentCar level clamp 2, per-polygon kind L (gHDCarDamageLevels): offset
((L^1) ^ ((L^1)|level)) * 64.
**Plan (steps, each with one sanity run; engine changes gated by car set 4, PS1 path noted):**
1. (d) wheels: per-model wheel radius (cosmetics row tail word, plugin-written) used by DrawCarWheels instead of 0x65 (two
   `* 0x65 >> 12` sites + the tread vertices: scale the wheel draw matrix), FixCarCos centring + D2's cog body offset in the
   converter (polish_cosmetics / polish_cars), checked against the user's reference (Screenshot_59). PS1: static exe code.
2. (f) clean damage textures: D2's per-polygon rule (B) in DentCar with the DEN level rows (remapped by fit_maps), or as a
   data filter (zone polygon lists only with a +128 twin); debris shards (giant black triangles, snapshot 1831) checked
   separately (Setup_Debris uses car texture data).
3. (a) cop look: Chicago = no unmarked cops (0x80096774 stays 0) + D2's rule "cop = police model only" (patrol model-1 cars in
   plain traffic -> civilians, i.e. traffic never spawns model 1 in car set 4); user snapshot wanted if (a) means
   something else.
4. (b) more models at once like D2: residents 0 player, 1 cop, 2-4 civilians, 5 special = 6 (D2 PSX: 5 + player car):
   relocate the three model arrays and the polygon group structs, enlarge the polygon buffer (~1000 entries; mod memory on
   PC, PS1: shrink the low models / share the buffer), spawn list like modelRandomList, DentCar rows 1..5, cosmetics rows
   (LoadCosmetics base table: 8 -> 10 rows for car set 4), palettes per model. Car cap stays D1's (~20 active + player = D2).
5. (c) regional specials: EXP's per-region spawn table; slot 5 swapped at area / region change from the in-memory lump
   (rebuild that slot's car polygons, despawn its cars first), siren for 8/9/10, colBox from the plugin's box table.
6. (e) sounds: per-car engine / horn banks from D2 (D1 sound engine research first: car SFX bank per city).

## C42 round 3, steps 1-2 built (Infrastructure 17.10.)
- **Wheels (d):** convert writes <lev>.whl.bin (D2 wheelSize x 1.32: choices 0-3, AI 1-3; taxi 65, specials 91-119, civ
  65-70 vs D1's 73) -> assets/car_wheels.bin. Plugin entry hook on DrawCarWheels (0x8003B208, game.toml hook list) sets the
  shared wheel models' hub (0-7) and tread (16-23) vertices to +-size and WHEEL_RIM (0x80093394) = rim - 101; exe
  c42w_patches: the four `x * 0x65 >> 12` rim sites multiply by 101 + WHEEL_RIM (lw t9 / mult / mflo). Driver 1 cars: 73 / 101,
  word 0. FixCarCos (D2 handling.c) applied to the wheels (dz = -(w0.z + w1.z - 14) / 2) and D2's cog body offset
  (DrawCarObject: body at where + R * cog) to the body vertices (clean / damage / low; CHI_POLISH_CARS_COG=0 = off).
- **Damage textures (f), D2 rule:** <lev>.lvl.bin = D2 DEN per-polygon kinds (0 body / 1 lights; civ models 48-50 light
  polygons, specials all 0) renumbered by fit_maps -> assets/dmg_levels.bin. exe c42d_patches: DentCar clamp AI 1 + RULEB
  (0x80093398, 0/1), player 3 ^ PDMG (PDMG 1 -> 2); the shift loop calls DCAVE1 (unreferenced "$Id: intr.c" string,
  0x80011BB8) / DCAVE2 ("$Id: bios.c", 0x800123E0): with LTAB (0x8009339C, the plugin's 1 KB table of L^1: row 0 = player
  choice, rows 1-3 = AI models) offset = ((L^1) ^ ((L^1)|level)) << 6, else Driver 1's shift (AI 7, player 6). So Driver 2
  bodies stay clean at level 1 and take their +128 twin at level 2, lights +64 / +128, as in denting.c.
- Lesson: the exe's "zero block" 0x80093378..0x80093FC0 is BSS cleared at boot: fine for plugin words, NOT for code (a cave
  there ran as zeros through the interpreter and crashed). DentCar keeps no ra on the stack: the cave call saves ra in t9.
- Checks: d2cars6 crash run (light damage, bodies clean), Miami drive (words 0, rim 101).

## C42 round 3 (b): six resident car models (Infrastructure 17.10.)
- **Exe group c42m_patches** (exe_patches.py, 314 words; Driver 1 levels leave lump slots 3-4 empty, so their models 4-5
  stay null and nothing changes for them: Miami check = 644 buffer entries, models 1-3, as before):
  - tables moved to the old model-table area (same lui 0x800A as the cosmetics, only low halves change): COS 0x800A0E20
    (6 x 100, 32 sites), STRUCTS 0x800A1078 (6 x 0x3C), DAMG 0x800A11E0 / LOWM 0x800A11F8 (6 words; before 4 + 4 with
    damage[4..5] = low[0..1]), LOWUV 0x800A1210 (6 x 50 + slack, stays zero: Driver 2 low models have 72-108 polygons, the
    draw reads past 50; d2cars6's init cleared 72 bytes from model 3's row into the hubcap data 0x800B6E84).
  - group builder FUN_0003BBF8 rewritten as a loop of 6 (flags as Driver 1: player a2 = 1 + stack 1; palettised a3 = 1 only
    for models 2-3), palette-halves loop of 6, the SF cop offset (city 1) on STRUCTS[1] / DAMG[1].
  - FUN_0003BDC8: buffer base + cap from PCAVE (cave in the unreferenced "Library Programs (c) 1993-1997 Sony" text
    0x800932C8, seeded; ra kept in t9): PBUF / PCAP (0x800933A0 / A4) or Driver 1's 0x800AB728 / 666; the cap sits in $at
    (unused by the builder), the two `slti t2, 0x29a` sites read it. Note: Driver 1's New York with choice 0 needs ~685
    entries and is truncated at 666 (Driver 1 behaviour, kept).
  - low UV init FUN_0003E540: models 1..5, null-safe, <= 50 bytes per row (per-city pointer block 0x8003E588.. stays in
    place: C51 patches 0x8003E5A8). Loader FUN_000527BC clears 6 entries (stale models 4-5 of a previous Chicago load).
  - LoadCosmetics 0x80052684..: 6 rows (entry 0 = base + choice, entries 1..5 = base + 5..9); car set 4 has 10 rows at
    0x800A16A0..0x800A1A88.
  - civilian spawn (5 sites 0x80015E5C, 0x80015E84, 0x800165AC, 0x80016988, 0x800169F0; `2 + r % 2`, r >= 0): model =
    SPAWN[r & 15] (16 bytes at 0x800932B8, same copyright text): Driver 1's {2, 3} x 8; the plugin writes Driver 2's list for
    car set 4 (civ_ai.c modelRandomList: {2,3,2,3, 2,3,2,3, 4,4,4,4, 2,3,4,5}; models 4/5 only while loaded).
  - car draw FUN_0003A698: model & 3 -> & 7 (0x8003A6A8, 0x8003AF14); struct compare 0x8003A574 and the LOWUV / STRUCTS
    sites (lui 0xb -> 0xa).
- **Plugin**: civ zone rows (3 or 5 models) in a mod-memory block, entry 4 of the civ tables (0x8008A6EC / 0x8008A72C) points
  one row before it (the old place 0x800A0E20 holds COS now); PBUF/PCAP (car set 4: 1400-entry buffer); SPAWN; DentCar level
  table 6 rows (dmg_levels.bin 9 x 256: AI 1..5 + choices 0..3); cosmetics 8 or 10 rows; wheels 7 or 9 values.
- **Lesson (mod plan rejected):** the runtime applies the package's main_exe patches to RAM at the exe entry only if EVERY
  expected byte still matches; a vblank write of the plugin into a patched text word before that (SPAWN at 0x800932B8)
  rejected the WHOLE plan: RAM kept the original exe, every patched function failed the text-image check and ran the
  original code in the interpreter (no log line in a killed run). The plugin now writes SPAWN only once PCAVE's first word is
  in RAM. Rule: a plugin must not write a word that a main_exe patch expects before the plan is applied.
- The exe's "zero block" 0x80093310..0x80094378 is intr.c's environment (memclr of 0x41A words at the interrupt
  init; its handler stack top is 0x80094328): the plugin words 0x80093380..A4 sit at the bottom of that 4 KB stack.
- **Converter** (CHI_POLISH_CARS_SIX=1 default with CHI_POLISH_D2CARS=1): lump slots 3 <- D2 3 and 4 <- D2 4 (after the
  R31 cop fix below; D2 PSX: slot 4 = SPECIAL_CAR_SLOT, default model 4, specials per region = step c); damage rows
  5 civ (.dmg.bin 6480 B), level rows 9 (.lvl.bin 2304 B), cosmetics 10 rows (.cos.bin 1000 B, rows 8-9 from row 5's tail),
  wheels 9 (AI 4/5: 65 / 73). Fitted polygons: D2 0 148, D2 4 143 (AI UV buffer 150), entries 903 of 1400.
- **Car CLUT table (found here, also in d2cars6):** the palette loader FUN_00056610 and the builder (palettised models) write
  0x800BE9FC + 600 * (page - 5) + 20 * min(texture, 30): only 2 pages x 30 textures. d2cars6 had civilian + pedestrian
  textures on pages 7/8: 32 palette words + the builder's words landed in 0x800BEEE8..0x800BF228 (skid buffer end pointer
  0x800BEEE8, the area up to the font copy 0x800BF2EC), and those textures drew with whatever CLUT words were there. Now
  (polish_cars.mark_palette_items / pack_twins): palettised textures (civilian models 2-3 + pedestrians) are packed first
  into the first two car pages with the lowest texture numbers; convert.py keeps only palette entries inside the table and
  refuses a level whose palettised polygons fall outside. d2cars7: 0 spills, pedestrians (CHEST1, JEANS1, ARM1) on page 5.
- **Damage twins pixel-only** (CHI_POLISH_TWIN_PIXELS=1): a twin is only drawn through its clean texture (u + 128, same
  texture number and CLUT), so it needs its pixels but no texture entry / CLUT slot (a page holds 32). Without this the
  six-model set needed a 5th permanent page and 342 more city textures were halved.
- **Cop texture size**: d2cars7 uses CHI_POLISH_CARMIX_HALF=1 WITHOUT COPFULL (the cop's textures halved like the other
  cars): 4 permanent pages and 654 downscaled city textures = d2cars6's budget. With COPFULL=1 (cop sharp, as in d2cars6) the
  six models need a 5th permanent page: 996 downscaled city textures (+342).
- Level pair var_d2cars7_day / _night (CHI_POLISH_D2CARS=1 CHI_ROADS=1 CHI_POLISH_CARMIX_HALF=1). Checks: 6 residents,
  traffic models 1-5, crash dents, FPS = d2cars6 (standing 20.2 / 19.9, driving 18.9 / 18.7); Miami unchanged.
- **R31 cop bug (user: "chasing cops are a regular BLUE traffic car, the D2 police car never shows"):** the cops WERE
  resident model 1 (all 7 'd2 cars 2' snapshots: pursuit / patrol = model 1, 0x80096774 unmarked-cops word 0), but model 1
  was built from D2 lump model 3 = a plain light-blue sedan (page 50 has no police marks). Driver 2's own Chicago missions
  (MISSIONS.BLK on disc 1, MS_MISSION.residentModels at +96, 34 of 37 Chicago missions) are {1, 2, 3, 0, special}: the
  COP is lump model 0 (page 58: POLSIGN1, BLUELYN = the white "Chicago Police" livery; REDRIVER2 externalCopModel =
  residentCarModels[3], palette 0). EXP's 'model 3 = police' was wrong. Map now {0: 0 cop, 1: 1, 2: 2, 3: 3, 4: 4, players
  12/9/10/8}; levels var_d2cars8_day/_night (d2cars7 deleted). Checked: the cop draws as the white police car with its roof
  bar, model 4 = the light-blue sedan, model 5 = the van; 0 CLUT spills, 4 permanent pages, 654 halved city textures.
- **Cop lights, code comparison:** body + livery = Driver 2's (model 0, palette 0). The lights differ:
  Driver 1 (FUN_00046000) draws a red/blue sweeping bar at fixed model-space spots x +-(64..112), y -164, z 15 (Driver 1's
  cop roof); Driver 2 Chicago (cosmetic.c AddCopCarLight, GameLevel 0) draws RED-only pulsing lights (count 16) at
  cog + policeLight (measured for model 3 before the fix; model 0 to be measured). Possible fix (small, Chicago-gated,
  PS1-native): FUN_00046000's position / pattern / colour from per-model data.

## R32 fixes after 'd2 cars 3' (Infrastructure 18.10.)
- **Player car glitches (rear window, damaged bonnet / boot = map pieces, "J Coast"):** VRAM watch (scratch vramwatch.py:
  VRAM of the chosen pair vs the level's page texels) showed the first special page wrong from the start in u 128..255,
  v 0..127 = Driver 1's MINIMAP tile cache: FUN_00056278 uploads 4 x 4 map tiles of 32 px to DAT_000975F0 + table
  0x8008B140 (32..56 words, 0..96 rows), and DAT_000975F0 = the VRAM slot of the chosen car's first special page (texture
  loader). Driver 1's own minor pages leave that quadrant free; Driver 2's are full there (BONSPEC5's +128 twin, WINDSPEC,
  SFRWIN ...). Fix (convert.py, CHI_SPECIAL_FLIP=1 default): the minor page of each pair swaps its halves when the lower
  half is unused (TSHADOW in all four: 64, 67, 57, 55); the texture details / remap y move by 128. Audit in convert: no
  player-car texture or its +128 twin may touch that quadrant (else the build fails).
- **Civilians drawn white / half (model 3 = D2 2):** polish_cars.palettes read only N entries of D2's lump 25, N = the
  first word = the number of STORED CLUTs; REDRIVER2 ProcessPalletLump reads until palette == -1. D2 2's BON31, DOOR31,
  BWING31, BOOT31, windows and roof had no entries -> their CLUT table words stayed 0 -> palettes 2-4 drew CLUT 0. Fixed.
- **Colour variety:** Driver 2 has 5 colour variants per civilian texture (+ base); Driver 1 spawned palette 1 + r % 4
  (base + table slots 0-2 = 3 of D2's). exe c42p: the 4 palette sites read PALT[r & 15] (0x800932EC, Driver 1 {1..4});
  the plugin writes 1..5 for car set 4 (base + D2 0..3; slot 3 = palette 5, as Driver 1's own city-5 case).
- **Cop lights (c42l):** Driver 1's FUN_00046000 drew at x +-"p`P@@P`p" (0x8008A8D8), y -164, z 15 (its own cop's roof);
  Driver 2's cop (lump 0) has its roof bar top at y -116, x +-33..66, z 30..63 (fitted model). COPW (0x800933A8,
  plugin): y delta << 16 | z; Chicago (car set 4) y -120, z 46, x table all 50 (a fixed pair like D2's GameLevel 0 rule);
  Driver 1: 0 / 15 / its own table. Colours stay Driver 1's red / blue (D2 Chicago: red only; no room in the block).
- **Sky overwrote the civilian car page (half / garbled civilians, also city textures before the D2 cars):** LoadSky
  (0x8004ED34) uploads the sky panorama to VRAM (512, 0) = slot 0x8 = the FIRST permanent page in load order; Driver 1
  levels list their PCSKY page first (LA page 2, Miami 30; PCSKY 256 x 128 reserves the top half). Our levels listed page
  5 (civilian textures) first. convert.py now loads the PCSKY page first (d2cars9: [7, 5, 6, 8]); no extra VRAM.
- **Runtime VRAM check:** chicago/devtools/vramcheck.py OUT LEVEL [--prep]: drives Chicago and compares VRAM at the tpages
  of the permanent pages 5-8 and the chosen special pair with the level's texels (texels inside textures only). d2cars9:
  pages 5, 6, 8, 14 = 0 mismatches over 120 s of driving; page 7 only in PCSKY (= the sky, intended), page 13 only in
  the swapped-out TSHADOW (= the minimap cache, intended).
- **Memory safety audit:** car CLUT table (convert: entries only inside 2 pages x 30, palettised polygons checked);
  minimap tile cache vs special pages (convert audit, above); damage twins at +128 inside their page (pixels-only twins
  packed by pack_twins); six-model tables in the old model-table area (fixed, below 0x800A1AB0); polygon buffer bounded
  by PCAP (+2 entries headroom); LOWUV clear bounded (50 B). The VRAM watcher (scratch vramwatch.py) is the runtime check.

## C42 round 3 (c) + (e) built (Infrastructure 18.10., user R32: specials option B, sounds option A3)
- **(c) Regional specials** (polish_specials.py, CHI_SPECIALS=1 default with the six-model set; levels var_d2cars10_*):
  - one special per OUR area, like Driver 2's SpecialByRegion[LoadedArea]: the majority of Driver 2's SpecialByRegion
    over the area's regions (convert keeps region_d2area); d2cars10: 8 (fire engine) areas 0, 8, 11, 12, 15; 9 areas 1,
    4, 6, 14; 10 (school bus) areas 2, 3, 5, 7, 9, 10, 13. Model 12 (152 polygons > the 150-polygon AI UV buffer) stays a
    player car only (polish_specials.usable).
  - textures: texrepack.EXTRA_MODELS puts each special's textures (source "C", Driver 2's special pages) into the texture
    sets of its areas (no permanent cost): downscaled city textures 654 -> 843 (+189: the areas now carry ~half a page).
  - lump slot 4 loads Driver 2's default special 10; <lev>.spc.bin -> assets/specials_<day|night>.bin: the 4 specials
    (clean / damage / low, polygons remapped to their area pages), cosmetics row (= the player row of that car), wheel
    size, zone rows, area mask, region table.
  - plugin specials_vblank: when the loaded area's special differs from model 5's and no car uses model 5, the special's
    models go to mod memory (pointers relocated like 0x80052944), clean / damage / low[5], cosmetics row 5, zone rows,
    DentCar level row 5 = 3 (no texture shift: the damage stages are not in the area sets) and the wheel size are set;
    polygon group 5 is built by the plugin (port of FUN_0003BDC8 for a non-player non-palettised model, buffer entries
    1402+) and REBUILT after every area texture load (tpage / CLUT words of the area pages are baked). SPAWN entry 15 =
    model 5 only while the loaded area holds the special's textures; outside, group 5 and the low model are hidden.
  - checked: specials 8 and 10 swap in at area changes, school bus drawn with its own textures (out_spc screenshots).
    CHI_SPC_DEBUG=1: stderr trace. Host-only (M8: Driver 2's CD spool of the special pages / models).
- **(e) Car engine sounds** (build_package car_sfx, assets/car_sfx.bin from the player's D2 disc 1 VOICES2.BLK, new input
  d2_VOICES2.BLK; plugin sfx_vblank): after Chicago's bank 0 load completes (table entry 1 = bank base + 0x3710), Driver 2
  banks 12 / 4 / 13 (engine + idle loops, 66.3 KB, 16 kHz) replace Driver 1's samples 1-2 (71.5 KB): bank 12 engine at
  sample 1's address, its idle at sample 2's address (the player's channels 0 / 1 keep playing), banks 4 / 13 behind it
  as samples 16-19; the table's rate field gives the 16 kHz pitch. The AI engine channels 7 / 8 restart on the sample of
  the car they follow (model 1 / 3 -> bank 4, 4 -> bank 13, else bank 12): voice start address + key-on (spu_write).
  Horns / sirens / other Driver 1 sounds unchanged; the SPU block sizes did not need trimming. Checked: channels switch
  between 0x4720 (bank 12) and 0x74D0 (bank 4) with the car's model. Host-only (M8: a Chicago SFX lump + guest restart).

## C42 round 3 (c) design: regional special vehicles (Infrastructure 18.10., awaiting a texture-budget decision)
- **Driver 2 (REDRIVER2 spool.c):** the special slot (residentCarModels[4]) follows the LOADED AREA:
  SpecialByRegion[Chicago] = {5,1,3,3,2,2,2,3,3,3,3,1,1,1,2,3,2,2,3,0} (per D2 area 0..19), model = value + 7, so Chicago
  spawns 12 (area 0), 8 = fire engine (areas 1, 11-13), 10 (areas 2, 3, 7-10, 15, 18), 9 (areas 4-6, 14, 16, 17).
  CheckSpecialSpool swaps it only when no car uses a special model; it streams the model (clean / damaged / low) and its
  2 texture pages + CLUTs from the CD into a dedicated VRAM slot (specTpages), ~400 frames. Civilians take the special at
  index 14/15 of modelRandomList (1/16 + 1/32 when valid). D2 missions also fix it (residentModels[4]: mostly 10).
- **Driver 1 port:** these four specials are exactly our four player cars (8, 9, 10, 12). Geometry swap: rebuild group
  5 at runtime (it is built last, so the builder can rerun for it from its buffer start), clean / damage / low pointers
  from model bytes kept in memory (the load-time lump area becomes the primitive buffers after load), cosmetics row 9,
  zone / level rows, wheel size: guest cave at the area switch + plugin data. Spawning: SPAWN entry 15 = 5 only while a
  special is loaded (already in place).
- **The cost is VRAM.** A special needs ~2 D2 pages (60-68 K px); halved once + damage stages ~ half a page. Free space
  now: perm pages 5/6 full (twins), 7 full, 8 has ~25 % (16 K px). Options:
  A. one extra permanent page as a "special slot", textures swapped per area (plugin upload; PS1 path = a CD load like
     D2): +1 permanent page = ~342 more halved city textures (measured with the 5-page six-model build).
  B. the special's textures in the AREA texture sets of the areas where it spawns (stable placement): no permanent cost,
     the areas that carry a special lose ~0.5 page (more halving there only).
  C. no extra VRAM: only the player's own chosen car can appear as a regional special (its special pages are loaded),
     i.e. in the areas where D2 spawns that model.
  D. quarter-resolution special textures in the free 16 K px of page 8 (all four would not fit; one at a time + swap).
  Recommendation: B (D2-like per-area specials, cost local to those areas), or C as a cheap first step.

## R33 fixes after 'd2 cars 5' (Infrastructure 18.10.)
- **Colour choice (1):** Driver 2's Chicago civilians have base + 4 stored CLUT variants (palette lump: count word, read until -1;
  pages 1/50/62/63/65 carry 5). c42m's builder flag is now a3 = (model - 2) < 3, so resident models 2-4 are palettised (model 4,
  the van / Driver 2 model 3, had palettes chosen but no CLUT rows: the garbled blue-white car in 151005). Palette per spawn =
  PALT 0x800932EC[r & 15] (c42p, 4 sites 0x80015ED8/0x800165C8/0x800169A4/0x80016A0C), table 1..5 nearly uniform like Driver 2's
  random choice. Converter: palettised textures first, <= 30 per car page (CLUT table 0x800BE9FC is 2 pages x 30 x 20 B); 42 in total.
- **Far LOD colours (2):** the low model (FUN_0002E230, world handlers) takes CLUTs from 0x80087030[page*32+tex] at draw time;
  plugin entry hook lod_entry (game.toml mod_function_entry_funcs 0x8002E230) sets those words for a palettised low model to the
  car's slot (palette of the car being drawn 0x80096990: 1 = base slot +0x10, 2..5 = slots 0..3). Host-only (M8: guest wrapper).
- **Player hole (3):** the full triangle-pair fit merged non-coplanar pairs into quads (bow-tie gap at the left mirror, 150502).
  Player models (buffers 260 polys) now merge only nearly coplanar pairs (FIT_ANGLE / FIT_COS, fitted(..., player=True));
  AI models keep the full fit (150-poly buffers). Damage rows use the matching fit (fits_player).
- **Damage textures (4):** the plugin writes the LTAB rows raw = the final DCAVE values (`s_dmg_lvl & 3`, default 3 = no shift):
  player rows L ^ 1 (Driver 2 special pages kept whole), AI rows 1 (clean, +128 twin at level 2) or 3 where the texture has no
  packed +128 twin (TWINNED registry from attach_twins) - before, such polygons shifted onto unrelated textures. vramcheck on
  var_d2cars11 (150 s, area changes): car pages 5/6/8/14 0 bad texels; page 7 = sky slot 0x8 and page 13 u128+ = minimap cache
  (both expected).
- **Specials (5):** car-car box = Driver 2's colBox x 1.32 per special (asset entry header now 8 ints: model, area mask, sizes x3,
  wheel, box x, box z; 8 = 263 x 891, 9 = 232 x 562, 10 = 228 x 870); plugin writes SPBX/SPBZ 0x800933AC/B0; exe BOXCAVE
  0x80052704 (in c42m's LoadCosmetics dead space, seeded; c42e's box tail jumps there): player -> PBX/PBZ, model 5 -> SPBX/SPBZ,
  0 = Driver 1's box. **Missing bus tiles + pale far-LOD box:** the plugin's polygon size table (spc_build_group, lod_entry) was
  wrong; Driver 1's is at 0x80089F1C: {8,12,16,24,20,20,28,32,8,12,16,16,0,0,0,0,12,12,12,16,20,20,24,24,0...}. Fixed: bus near
  and far textured (spc run on var_d2cars11).
- **Map items (6) -> Polish (data):** sand patch drawn differently (150740) and missing water tiles at the monument (150819).

- **C74 sand patch (Infrastructure 18.10.):** ground tiles in the mid band (0x80027098 -> routine 0x80026C38, writer 0x80026BE8)
  take their UVs from SUBDIVISION via a list of one word PER POLYGON at model +0x2C (s5 += 4; high half = 20-byte record of
  nine (u, v)); remap_subdivision only remapped the first word, so the other records of multi-polygon tiles (66 of 157 tile
  models) kept Driver 2's page coordinates (sand drawn from v 224-255 = an empty region). Now every record is remapped with
  the polygon texture whose original rectangle contains its points (CHI_SUBDIV_ALL=0 = old behaviour); 1658 SUBDIVISION bytes
  change, models unchanged. Captured at 150740: patch polys v 224-255 -> v 0-19, patch gone (findings/c74_sand_before_after.png).

## R34 fixes after 'd2 cars 6' (Infrastructure 18.10.)
- **Special texture slot (item 4, user 25 = A):** option B (special textures in the area sets) lost them at every area
  change while Driver 1 kept reusing the car (2 buses followed the player 300k units into area 14: hidden / garbled
  specials). Now like Driver 2's special-car slot: polish_specials.reserve_slot takes the empty bottom half (256 x 128) of
  a permanent page (page 8 = tpage 0xB in var_d2cars13) + 16 reserved texture entries (CLUT rows allocated by the page
  loader, zero data); slot_layout packs each special's textures there (skyline, halving the largest until they fit: about
  half resolution; page 1 entry 0 stays on its permanent page). Asset "2CPS" (+ slot header page, first entry, x, y, w, h,
  entries, block bytes; per special the block = texels w*h/2 + 16 x 32-byte CLUTs). Plugin spc_slot_upload: on the swap
  (only while no car uses model 5, so the old textures stay until then) texels -> tpage 0x80086F30[page] + slot rect,
  CLUTs -> 0x80087030[page * 32 + entry]; group 5 built once per swap; every 64 vblanks a sampled VRAM check re-uploads if
  lost. Area sets no longer carry special textures (city halved textures back to 654). Host-only (M8: a guest spool of the
  slot block). CHI_SPECIAL_SLOT=0 = R33 area sets.
- **Far special drawn as a pale box (item 2):** the civilian spawn (c42p PALT) gives every car a palette; FUN_0002E230
  switches to the car-palette handler table 0x8008A1BC whenever the drawn car's palette 0x80096990 != 0, which takes CLUTs
  from the car CLUT table (car pages 5-6 only) -> CLUT 0 for the special's polygons (GPU: op 0x34, clut 0). Driver 2 gives
  specials palette 0 (civ_ai.c: residentCarModels > 4); the plugin zeroes the palette byte (car record +0x11) of model-5
  cars every vblank (host-only; M8: the 4 c42p sites skip PALT for model 5).
- **Special box offset (item 1):** Driver 2 centres colBox on the drawn body (initOBox where - R * cog; the body is drawn at
  where + drawCarMat * cog, drawCarMat negates x / z, i.e. the same point). Our body sits at the cog shift (bus +154 along
  z), the box at the car origin -> box 154 too far back. Exe c42m BOXCAVE: box centre (+0x30 / +0x38 of the collision
  record) += column 2 of the car matrix (+0x10 / +0x18) x SPBO (0x800933B4, gp-0x33BC, plugin from the high half of the
  asset's box z word). Offsets: fire engine 7, special 9 22, bus 154, 12 0.
- **Ride height (item 5):** Driver 2 clearance (D2 units) = 14 - wheelDisp.y - cog.y - lowest body vertex (cars.c
  DrawCarWheels): civilians 41-51, van 56, special 9 74, bus 92, fire engine 98. Specials (CHI_RIDE_MODELS 8,9,10,11,12) ride
  CLEARANCE + 1.32 x (their clearance - the civilians' mean) higher: bus +59, fire engine +67, special 9 +35, 12 -14.
- **Damaged-hood hole (item 3):** the player fit merged triangle pairs coplanar in the CLEAN model only; dented, the quad
  bent and Driver 1 culled it by its first triangle. fit_model now also requires coplanarity in the damage model.
- **Palettes (item 6):** Driver 2's lump stores 5 variants (palette 0..4) per palettised texture; retail Driver 2 picks
  Random2 % 5 = base + lump palettes 0..3 (REDRIVER2 [A] enables the 5th). We use base + 4 = retail D2 (all 53 palettised
  textures carry 5 distinct CLUTs in RAM). A 6th needs a wider car CLUT table (exe); not done.

## R35 fixes after 'd2 cars 7' (Infrastructure 18.10.)
- **Fire-truck region ruined VRAM (item 1, HIGH):** the slot upload used GP0 0xA0 (vram_upload) from the vblank hook; when
  the game was itself mid-way through a CPU -> VRAM transfer / command (area texture streaming), the injected words became
  its data (the user's area 8: every world texture green). Now spc_slot_upload writes the runtime VRAM directly
  (gpu_get_vram_ptr + gpu_vram_dirty_mark_rows + gr_vram_transfer_in, like a completed GP0 transfer) without touching the
  GP0 state, bounds-checked (slot inside its tpage, block inside the asset entry, CLUT spots inside VRAM). Test:
  CHI_SPC_CYCLE=N (devtest aid: swap specials every N s even while in use) -> ~290 swaps incl. area loads, no corruption;
  vramcheck: car pages 5/6/14 0 bad texels, page 8 only the slot rows.
- **Buses spawned high / bounced (item 2):** Driver 1's civilian spawn uses the civilians' ride height; the special rested
  ~180 lower in y (its cosmetics wheel y). (a) The D2 clearance extra is now a BODY shift up (polish_cars.cog_shift dy,
  polish_cosmetics.ride_extras), the wheel y keeps the body-depth rule; (b) the plugin adds the wheel-y difference (row 5
  vs model 2's row) to a newly placed model-5 car's y (+ the x16 copy). Measured: model-5 y swing in the first 3 s 1-7
  (civilians 0-20), before 400.
- **Player speed (item 3):** Driver 1's pad handler FUN_0001FF24 sets thrust 7200 (accelerate) / ~-7000 (brake) for the
  player (car + 0xF0); Driver 2 FIXEDH(powerRatio * 4915). Exe C35T: the handler's last block (Miami choice-3 x 19/16) is
  now thrust = (thrust * THRS + 0x800) >> 12 with THRS 0x800933B8 (plugin, car set 4) = D2 powerRatio * 4915 * 1.32 / 7200
  from the player choice's cosmetics tail (+96, unused by Driver 1); Miami's rule kept bit-exact (4864/4096). Chicago
  choices: 0 (D2 12, powerRatio 4500) 4055 = -1 %, 1 (9) 3154, 2 (10, bus) 2402, 3 (8, fire engine) 2703. Assumes
  Driver 1's and Driver 2's drag scale alike (not measured: the walk-teleport harness ends in water / frozen cars).
- **Special touch threw cars away (item 4):** the broad phase (0x8001FAFC) admits a pair only within Driver 1's 209 / 585
  + 90 + PBS high half; the bus box (870 + 154 offset) was only tested once deeply overlapping -> big push-out. The
  plugin adds the loaded special's extra reach (bus 614) to the PBS margin.
- **Sky:** CHI_POLISH_SKY default = d2raw (polish_sky.sky_mode; "old" = the previous default).

## R36 (Infrastructure 20.10.): approved defaults, special box, car sounds + horns, sky seams (C76)
- **Defaults (user approved 'la day 6' / 'map fixes 2'):** convert.py CHI_POLISH_QUAYFILL=4, CHI_POLISH_QUAYCLEAN=1,
  CHI_POLISH_INSIDEWATER=basin (KEEPSHORETILES, BASIN_Y 24 and sky d2raw were defaults already; "0" switches them off).
  setup_chicago builds LA by Day from the disc with polish_laday.py (mode v15 = the frozen design/la_day_v11_cluts.json +
  v14 vegetation / props) into <setup cache>/out/la_day_<key>.lev (key: polish_laday's modules + design/la_day_* +
  CHI_POLISH_LA_DAY* + the D1 input md5s) and passes it as CHI_LA_DAY_LEV (main + --auto, code_key includes it);
  CHI_LA_DAY=0 = none. Check: the setup build is byte-identical to var_polish_la_day_15.lev.
- **Special box (item 1):** the R34 offset had the wrong sign. Driver 1's car models face -z (headlight z -525 in every
  D1 cosmetics row; Driver 2's bus -618), the collision matrix's column 2 is the driving direction, so the body moved by
  +cog z sits BEHIND the origin: the box centre moves by -cog z (polish_specials: bus -154, fire engine -7, 9 -22).
- **C82 bus front collision (23.10., exe c82 + plugin SPTW):** Driver 1's car-car response (GlobalTimeStep 0x8001C9xx..CF0C)
  gives BOTH cars the same impulse and the same yaw kick (impulse x lever x 0x37, t1 set at 0x8001CA10; no mass / inertia per car).
  Driver 2 (handling.c) scales the kick by twistRateY / 2 per model (CHICAGO.LCF: cars 224, models 8 / 10 = 50, 9 = 120, all
  masses 4096) -> in Driver 1 the bus (lever up to 716 front / 1024 rear) spun ~4.5x too hard and its nose swept the player.
  Fix: S1-cave TW 0x80010850 (jal from 0x8001CC44 (car s7) / 0x8001CE9C (car s3), does their 'lw v1, 0x98(sp)'): t1 = SPTW
  (0x800933BC, plugin: 0x37 x twistRateY / 224 -> bus / fire engine 12, special 9 29) for model 5, else 0x37. Also the pair
  pre-check |dx|,|dy|,|dz| < 1201 on car ORIGINS (0x8001C4B4..EC) -> 2000: the bus box reaches 1024 behind its origin, so rear
  hits were tested only after ~330 overlap (Driver 1 boxes never touch beyond 1104 -> no change in D1 cities). Measured
  (bus_hit3, opt2d day, ramming at speed from 4000): before front yaw 9-111 deg with the bus spun round; after 2-5 deg, contact
  at 1232-1304 (= box 716 + player box), bus stays aligned. Switches: CHI_C82=0 (exe), CHI_C82_TW=0 (plugin). PS1: pure exe.
- **Car sounds v2 (items 3 + 4):** Driver 2's MapCarIndexToBank for Chicago (car_banks[0] = {12,4,13,5,16,9,2,15,10},
  model - 1, 0 -> 1, > 6 -> -3): cop 0 -> 4, D2 1 -> 12, D2 2 -> 4 (the Delta 88 shares the cop's), D2 3 -> 13, player car
  D2 12 -> 10, specials 8 -> 16, 9 -> 9, 10 -> 2. car_sfx.bin "CSX2" (build_package.car_sfx_v2, vag.py: ADPCM decode /
  linear resample / encode, 68 dB round trip): engine / idle loops at 11025 Hz (CHI_CAR_SFX_RATE), horns 8 kHz.
  SPU: samples 1-2's 73184 B = the civilian engines / idles (45.7 KB) + their horns (13.5 KB) + reserved player and
  special horns; the music block's tail (0x19000 - song bank, 22.2 KB by day) = the player choice's engine / idle; the
  mission block's tail (0x21800 - Take a Ride's 117 KB = 20.2 KB) = the special's engine / idle, reloaded on a special
  swap. Table slots 1 / 2 player (channels 0 / 1 restarted), 16-23 engines, 24-28 horns; AI channels 7 / 8 follow
  their car's model. Horns: Driver 1 HAS one: R1 -> FUN_0004D740(4, 0, 8): bank 0 sample 8 on channel 4 every 11 frames
  (and in cop mode R1 toggles the siren); the plugin retargets channel 4 to the player car's Driver 2 horn. Civilians
  honk at the player (new, like Driver 2's civ_ai: closing on the player ahead, max one at a time, cooldown) on voice 4
  while the player is not honking. Fix: the bank-0 trigger no longer depends on a remembered address (v1 replaced the
  sounds only on the first level load of a session). Host-only (M8: a Chicago SFX lump + guest placement).
- **C83 engine sound (23.10., vag.py V2, package asset):** measured Chicago vs Miami (spu_voices / spu_events / SPU dump):
  same channel use (0 engine, 1 idle, 2 crash = bank 0 sample 0 from FUN_0003FF0C, 3 skid loop 0x16500 unchanged), the same
  pitch RATIOS (D1's engine pitch = revs/4 - x/128 + 1000 over 4096 x the table rate: 0.23x after gear changes .. 1.97x on
  burnout; Driver 2's = revs/4 + revsvol/64 + 1500: ~0.37x .. 1.6x on the ground), no stray key-ons, all bank 0 samples intact.
  Cause: the R36 11 kHz conversion. Driver 2 encodes a loop's block 0 with the history of the loop's END; vag decoded the
  source from silence (block 0 off by up to 8000), and the resampled loop's last block was padded with up to 27 zeros INSIDE
  the loop -> the player's engine (D2 bank 10) clicked + dropped out (26 samples) once per loop, i.e. more often the higher
  the revs (burnout, braking into reverse at full revs). V2 (CHI_VAG_V2=0 = R36): loops decoded as on their 2nd pass, resampled
  to whole 28-sample blocks, encoded with the loop end's history (fixed point), 63-tap windowed-sinc low-pass before the
  16 -> 11 kHz step (linear interpolation aliased). In game (SPU dump): player engine seam step 7168 (> p99.9 6103) -> 5182
  (< p99.9 6216); every engine / idle loop now below its p99.9; sizes -16 B or equal (SPU budget unchanged). Pitch remap (plugin
  sfx_v2_vblank step 7, CHI_C83_PITCH=0 off; Chicago + D2 cars only, channel 0 while it plays the D2 player engine): arg' =
  (arg - 1000) x 0.71 + 1414 (D2: revs/4 + revsvol/64 + 1500, burnout revs 20160 vs D1 ~28300) applied via the channel's
  rate (+0x44, one frame behind). Measured ratios: idle 0.22 -> 0.33, accel max 1.54 -> 1.31, burnout 1.96 -> 1.56. AI
  engines (0.43-0.58x) already sit in D2's range (revs/4 + 1500). Host-only (M8: the same map in guest code at 0x8004DACC).
- **Sky seams (C76, user: 'cut' lines in the sky that move with the view):** Driver 1's dome draws piece k with u
  64k..64k+63, v 42r..42r+41 (0x800BDE40): texel 63 / row 41 is never sampled, so one panorama column / row was skipped
  at every seam, and each piece was quantised to its own 16 colours (_bmp4) -> colour steps along the seams. polish_sky:
  the panorama is resampled to 253 x 124 and cut with a one-texel overlap (CHI_POLISH_SKY_SEAM=0 = old), each piece's
  palette is chosen from the piece plus a 3-texel ring of its neighbours. Measured on the dome view: vertical seam
  contrast 14.0 -> 7.8 (median 10-12), horizontal 15.6 -> 11.1 (night); day 31.9 -> 22.0 / 47.2 -> 30.4 (source 20). Not
  fixable in data: affine texture warping of the big dome / far wall quads (diagonal kinks; the PC renderer's
  [video] perspective_texturing would remove them). Halved walls: see open question (texture edge / halving).

- **C76 dome split (Infrastructure 20.10., parked):** convert.sky_subdivide (CHI_SKY_SUBDIV=1; rows CHI_SKY_SUBDIV_ROWS, default
  1,2 = 36 quads per quadrant) + exe C76D (sky_dome_patches): FUN_0004F34C wrote the four screen points twice; the redundant
  second block (0x8004F604..F6EC) is now the branch "byte 1 bit 7 -> UVs from polygon bytes 8..15, CLUT of byte1 & 0x7F",
  else the table (Driver 1 domes draw as before; SF checked). Lessons: the copyright-text tail after 0x8009330C is live
  runtime data (a cave there halted), and a cave must be a jal/jr subroutine (no recompiled entry mid-function to jump
  back to). FPS at fps_drop_2 (3 reps): standing 24.6 -> 24.3, driving 26.4 -> 25.4 (noisy). The user approved the
  unsplit sky (probe 33), so the converter default is off; the exe branch stays (inert without marked polygons).

## C42 round 3 (e) research: per-car engine / horn sounds (Infrastructure 18.10.)
- **Driver 1:** level SFX load FUN_0004C29C: SOUND\VOICES.BLK (header 11 offsets = 10 lumps) lump 0 -> SPU bank 0
  (164 KB, 16 samples), lump 1 -> bank 3 (65 KB), lump 2 + k -> bank 4 (k from the mission table 0x8008A96C; 63-131 KB).
  Bank = count, then {offset, size, loop, rate} x n, then VAG data (LoadSoundBank 0x8004E214). The car channels are
  started once per level (FUN_0004C438, FUN_0004D7E4(channel, bank, sample, x, y, z, vol, pitch)): ch 0 sample 1, ch 1
  sample 2, ch 3 sample 3, ch 5-6 sample 4, ch 7-8 sample 1 (+ ch 4 in 2-player); FUN_0004CA5C then only moves them
  (FUN_0004DDA8: position / volume / pitch from revs) to the nearest cars; model 1 = siren. So EVERY car, every city,
  uses the same engine samples: bank 0 sample 1 (engine loop 57.7 KB @22 kHz) and 2 (15.4 KB loop) - no per-car sound.
- **Driver 2:** SOUND\VOICES2.BLK (73 offsets), the same bank format (16 kHz). LoadLevelSFX loads one CAR bank per
  resident model (MapCarIndexToBank: car_banks[city][model - 1, 0 -> 1, > 6 -> -3]); a car bank = 3 samples: engine
  loop, idle loop, horn (8 kHz), 19-31 KB. Engine pitch = revs / 4 + revsvol / 64 + 1500 (gamesnd.c), 3 channels per
  car. Chicago: model 1 -> bank 12, 2 -> 4, 3 -> 13, 4 -> 5, cop 0 -> 4, specials 8 -> 16, 9 -> 9, 10 -> 2, 12 -> 10.
- **Import path:** (1) package: a Chicago-only SFX lump = D2 car banks of the 6 resident models (player choice, cop,
  civ 1/2/3, model 4) appended to bank 0's samples (~150 KB; the converter reads VOICES2.BLK from the player's disc 1,
  Option A), relocated like MUSIC.BIN; (2) exe: FUN_0004C438 / FUN_0004CA5C start the engine / idle channel of a car with
  sample = per-model table (+ restart when a channel moves to a car of another model), horn = sample 3 of the model;
  pitch: D2's rates are 16 kHz vs 22 kHz (scale the pitch word). **SPU RAM is the limit** (512 KB): D1 already holds bank 0
  164 KB + bank 3 65 KB + bank 4 up to 131 KB + the music bank up to 87 KB + reverb: ~150 KB more does not fit; Chicago
  would have to drop D1's engine samples 1-2 (73 KB) and fit the rest elsewhere (e.g. a smaller mission bank 4, or only
  3 D2 banks shared by model like D2's own mapping: cop and model 2 already share bank 4). Needs a budget decision.
- **SPU map (static, InitSound 0x8004D3DC: SpuMalloc of the table 0x8008AA24 at boot; same in every city):** SFX bank 0
  0x28000 (160 KB; D1 lump 0 uses 159.9), bank 1 0x400, music 0x19000 (100 KB; largest song bank 84.7 KB), mission bank 4
  0x21800 (134 KB; largest lump 127.9 KB), bank 3 0x10000 (64 KB; 63.3 used); reverb mode 5 (hall) 43.5 KB, system 4 KB,
  free 5.5 KB. Needs: A = 3 D2 banks 78 KB / 4 banks 96.6 KB vs 71.5 KB freed by D1's engine samples 1-2 + 5.5 free + 21 KB
  from trimming the music / mission blocks to their maxima -> 3 banks fit, 4 need 11 kHz resampling (-31 %); B = 5 banks
  ~127 KB (55 KB more: mission block or resampling); C = one bank 19-30 KB (fits).

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
  - Ride height (fixed 14.10. evening): D1's StepOneCar sets it from wheelDisp.y (D1 cars: -165 -> y 164, bodies ~130
    deep = ~34 clearance). The first rows (vy + wheelSize - 64 = -41) sank the D2 bodies (y ~77). Now wheelDisp.y =
    -(body depth + 34) (CHI_POLISH_COSMETICS_RIDE=body, CHI_POLISH_COSMETICS_CLEAR=34): -118/-122/-114 -> traffic
    y ~121, bodies visible on the road (pt hook near-car shots, mix4). D2 bodies are only 80-88 deep, so y 164 would
    float them ~75 high.
- **C7 street-level first (Polish 14./15.10.; CHI_POLISH_TEX_HEIGHT=1, polish_tex.pick_height):** when the page
  budget forces halving, textures used high up go first.
  - Height = mean model-space -y of the polygons using the texture; high = from 1200 units (CHI_POLISH_TEX_HIGH).
  - Order: high first, then far-only, then the largest.
  - var_polish_c7_height1_day.lev vs b15 (same page budget):
    - street-level losses 283 textures / 1.25 M px -> 173 / 0.76 M px (-39 %);
    - high losses 76 / 0.26 M -> 167 / 0.64 M px;
    - total lost pixels 1.51 M -> 1.40 M (halving steps 672 -> 778, more but smaller).
  - 293 textures change (157 street-level sharper, 6 street-level softer, 130 high softer):
    findings/c7_height_texture_changes.csv.
- **Night moon (CHI_NIGHT_MOON=1, polish_moon.py, night conversion):** the SKYSUN item (24x24, LA's slot that wins the
  by-name lookup) gets Design's SKYMOON_24.png. It is quantised to 15 colours with the semi-transparency bit,
  background index 15 = 0x0000 (as D1's SKYSUN).
  - var_polish_moon1_night.lev; slot preview findings/night_moon_skysun_slot.png (left LA's sun, right the moon).
  - In game the chase camera never showed the high sky at beach_n / lakeview, so the moon itself is not yet seen on
    screen (Infrastructure's moon vector is in build-test).
- **quay_wall (Polish 16.10.; user snapshots 20261015-234734..234751, smooth loading probe):** "huge stretched grey
  planes" at the river quay D1 (-82000,-220500), area 11, region 135.
  - Not corr4-specific: the same objects are in b16b.
  - Candidate 1: D2 model 1115, a concrete quay wall of two 256 x 7152 quads (9440 D1 units long), placed twice at
    y 1014 along the quay. Driver 1 has no near clipping, so a polygon whose corners pass behind the camera is drawn
    stretched across the screen (C2 family). City-wide, 35 polygons in 11 models are longer than 3000 D2 units.
    - Fix: **CHI_POLISH_TESS=1500** (polish_tess.py, hooked at the start of d1models.convert_models). It cuts such
      FT4/GT4 quads into strips of at most 1500 units, interpolating vertices, UVs and normals (1115: 2 -> 14 polys).
  - Candidate 2: SHOREWALL hanging from a raised level. Land cell (425,775) next to the river reads only -1634 (a
    structure top), so the 2000-high quay wall hung from 1594 above the street. City-wide 109 walls had raised tops.
    - Fix: **CHI_POLISH_SHOREFIX=1**: a raised bank (> 300 above the street) takes the median street-near level of
      its land neighbours, else gets no wall. 4671 -> 4616 walls, 0 raised tops.
  - Level: work/var_polish_quay2_day.lev (corr4 recipe + both switches). Spot quay_wall added.
  - Pose replication from the snapshots is unstable (the car flies after poking its state), so the in-game check is
    partial: findings/quay_wall_before_after.png. User probe recommended.
- **C60 chase music (Polish 16.10.):**
  - Driver 1's chase switch is 0x8004CF50 (= D2 FunkUpDaBGMTunez). When copmusic (0x80096C70) == 0 and the felony
    (0x80097708) >= 0x293, it sets copmusic = 1 and calls XM set-position 0x80073020(Song_ID *0x80096C88,
    xm_coptrackpos[*0x80097298]). The table sits at 0x8008AA04 (8 ints: 11,12,11,11,8,11,15,12, read with lhu;
    lui/addiu of the base at 0x8004CF84/88).
  - Chicago's songs 8/9 read past it: entries 8/9 are InitSound's SPU words 0x28000/0x400, so there is no chase
    section.
  - D2 positions: Chicago day (D2 song 2) 7, night (song 6) 8.
  - Test (in-place D2 song 2 in slot 7, data poke table[7] = 7, felony 0x400): copmusic = 1 and the music switches;
    louder and brighter spectrum (findings/music_chase_test_normal/chase.wav).
  - Engine spec: point the base at a 10-entry copy (polish_music.coptrackpos_table(): D1's 8 + 7, 8). It needs no
    gate, since the first 8 entries are identical.
  - **Engine (Infrastructure 16.10., exe group CHASE_TABLE, shared list 426 -> 438)**: lui/addiu at 0x8004CF84/88 ->
    0x8001188C, a 10-int table in the unused MDEC debug strings after the C55 moon stub (no references; ranges
    manifest unchanged, so not decoded as code). CHI_CHASE_TABLE=0 = off. The XM set-position writes the order
    position to song struct (*(0x800C7888 + 4 x Song_ID 0x80096C88)) + 0x1C. Check (build-test, felony poked to
    0x400): Chicago day song 8 -> position 7, night song 9 -> 8, Miami song 3 -> 11 (D1 unchanged); music plays on.
  - **CHI_POLISH_MUSIC default on** in build_package (16.10., user R23; CHI_POLISH_MUSIC=0 = off). Only in the Chicago
    slot package (needs D2 disc 1).
- **C37 D2 surface planes (Polish 16.10., `polish_slopes.py`, CHI_POLISH_SLOPES=1):**
  - D2 stores the surface per 1024 cell as a BSP of cuts at any angle, with one plane (a,b,c,d, unit normal x 16384) per
    leaf; height = -d - (a x + c z) / b (sdHeightOnPlane).
  - D1 already takes any plane on a triangle or box: MapHeight 0x8001F5B0 / FindSurfaceD2 0x8001EEB4 (the only readers
    of surface_ptrs besides the loader 0x80021CA8) compute height = ((px a + pz c) >> 12) - d - cell h. That has NO
    division by b, so a unit normal makes a slope g only g/sqrt(1+g^2) steep (45 deg -> 0.71). D1's own cities are
    unaffected: unit normals, slopes <= 0.2 (FRISCO).
  - StepOneCar uses the returned normal in D2's impulse formula (expects unit length) and the vertical depth for lift.
  - polish_slopes clips each D1 cell against the BSP leaves of the D2 cells it overlaps. It keeps single-level, no-sea
    cells with a sloped piece or a >= 40 step, merges equal planes, and writes triangles plus the largest plane as a
    full box last (first match wins). CHI_POLISH_SLOPES_AT="x,z,r;..." limits the cells.
    CHI_POLISH_SLOPES_EXACT=1 writes a, c = gradient x 4096, b = sqrt(4096^2 - a^2 - c^2) (min 1024).
  - City-wide: 5715 cells qualify (2940 steeper than 0.4, mostly banks; 1489 gentler slopes; 1276 non-axis splits;
    only 10 gentle slopes with both x and z gradients), 0-20 triangles per cell. Every cell needs its own surface id
    (ids < 900, ~438 free), so data-only covers at most a few hundred cells.
  - diag_ramp is the top edge of a 45 deg (E) / 55 deg diagonal (A) bank down into the river (D2 planes
    E: a -11585 b 11585; A: a = c = -9459, b 9459). The old level wrote that cell flat at h 284, so the car stood level
    inside the bank.
    - var_polish_c37_slopes1 (EXACT): the car was flung 1800 units and flipped within 0.5 s. The normal is wrong
      (b clamped), so the impulses go mostly sideways.
    - var_polish_c37_slopes2 (unit normals, 3 cells at diag_ramp): the car rolls backwards down the bank to the water's
      edge, tilting with it (no fall-through), then flips (Game Over). That matches the physics for a 45-55 deg bank;
      the slope is 0.71x steep.
  - **Engine spec:** in MapHeight and FindSurfaceD2, divide by b (D2's formula) instead of >> 12, gated to Chicago
    (CITY 3) or for all cities (D1 changes <= 2 %). Then the data writes D2's unit normals for exact heights and
    normals. Plus more surface ids (or a D2-style per-cell plane lookup) for the 5715 cells.
- **Quay artefact round 2 (Polish 16.10., user snapshots quay fix 0032*):**
  - Cause: my C40 default CHI_POLISH_SUBDIV=light turns every flagged polygon into 0x60. The renderer 0x80030B08 gives
    0x60 polygons the fixed light handler (+0x10) even next to the camera. Only 0x20 polygons get the full near
    subdivision (< 6000 units, +0x20), which LA uses on its big polygons (9984 polys flagged 0x20).
  - So the river quay-wall models 1113/1114 (9462 long, faces from -213 to 1014) and 1115, still 1400-unit strips
    after TESS, were drawn stretched where they run beside or behind the camera. At the user's pose 003300, 7+7+4 of
    their polygons cross the camera plane (scratch nearclip analysis).
  - Fix: CHI_POLISH_SUBDIV_LONG=6000 (d1models.polish_subdiv). Models longer than 6000 keep Driver 2's flags:
    11 models, 230 polygons at 0x20, negligible cost.
  - Level var_polish_quay3_day (quay2 + the switch). Same drive east along the quay from the user's start
    (findings/quay3_subdiv_long_before_after.png): quay2 shows the dark wedge / slanted slab in 4 frames; quay3 shows
    none, one small spike left.
  - Not fixed: water tile 683 (quick-path tile, flags 0, 3060 square at y 1084) also crosses the camera plane there.
    It is a candidate for the translucent slab; quick-path tiles never get the near subdivision.
  - Surface 754's second plane (d -1640, sw 1334) is D2's stacked lower level with its switch height: collision
    only, not drawn.
  - Pose poking from a snapshot (0x8009B000..0x8009B300) ends the game at once (Game Over). The car heading is
    0x8009B19C (4096 = full turn).
- **C46 + C56 sky variant (Polish 16.10., `polish_sky.py` CHI_POLISH_SKY=d2, package-time; work/var_polish_c46_sky3.BIN):**
  - Rows: D2 rows 0..167 uncropped (no TOP=42) squeezed to v 0..105.
  - Haze: the skyline's dark base v 84..104 blends towards HAZE_TOP (216,224,234), 0.15 -> 0.9, by day.
  - Below the horizon: D2's reflection (rows 167 -> 140 flipped, half brightness) in v 105..125. By day it sits under
    the haze gradient (CHI_POLISH_SKY_REFLHAZE = 0.8 gradient share); at night it is plain.
  - Finding: v 105..125 IS visible from street level (bridge: screen rows ~75..115). A plain dark reflection made the
    C56 slab darker (24,32,32) in variant sky2. sky3: (144,152,160) at bridge.
  - Sheet: findings/c46_c56_sky3_sheet.png (bridge before / after, lakeview).
  - The old switches (CHI_POLISH_SKY=mirror, _TOP, _GROUND=grad) are superseded.
- **C12 dot calibration (Polish 16.10.):**
  - CHI_POLISH_MAP_MARKS="x,z;..." (test only, polish_map.marks) paints a 7x7 dark frame at the predicted car pixel.
    Level work/var_polish_c12_marks_day.lev has frames at bridge, lakeview, l_down_e, deckfall_w (south) and
    kernelnorth (north).
  - In game, the dot sat the same offset from the frame at all 5 spots: no scale drift; +1 px in screen y (= map
    column / z), within 1/3 px in screen x.
  - The window shows the map transposed: screen x = map row (x, 1.5 screen px per map px), screen y = map column (z).
  - Fix: CHI_POLISH_MAP_NUDGE="dc,dr" (map px added to the exe offsets, package time via build_package
    minimap_params). "1,0" centres the dot (checked at l_down_e: dot on the frame centre,
    findings/c12_dot_calibrated_l_down_e.png); "-1,0" doubled the error and "0,-1" moved it sideways.
  - Zoom to D2's scale (F=1) still needs the CLUT read moved: exe immediate at 0x80054194 (map + 0x148) -> 0x200
    (polish_map CLUT_AT for 252 tiles). Data-only maximum: F=4/3 (var_polish_c12_map43_day). Native test level:
    var_polish_c12_map1test_day (CLUT copy at 0x148, tiles 164..179 garbage).
- **C12 round 2 (Polish 16.10. 14:0x), probe 'minimap' broken:**
  - Cause: the snapshot's exe entry was (178, 78, 448, 256, 2416, 4247), i.e. F=1.5. The level had the F=4/3 lump
    (512 x 288, 16 tiles across), but build_package recomputed the frame from the environment at package time, where
    CHI_POLISH_MAP_F was unset. The tiles were laid out 14 across (sheared) at the old scale (no zoom).
  - Fix: polish_map appends "PMAP" + the 6 frame words after the tile data; build_package.minimap_params uses the
    stored frame (stored_params). The package always matches the level; NUDGE/F are now level-build switches.
  - D2's zoom = F=1 (672 x 384, 252 tiles). Data-only, at most 164 tiles fit before the CLUT at map + 0x148: a road
    crop still needs 20 x 10 = 200 tiles, so the exe immediate at 0x80054194 (0x148 -> 0x200) is required.
  - Test level var_polish_c12_map1v2_day (F=1 + NUDGE 1,0 + the test CLUT copy at 0x148: tiles 164..179 garbage)
    shows D2's density at l_down_e / purpleshops (findings/c12_r2_zoom_sheet.png). Without TESTCLUT it is the ship
    level once the immediate is patched. D1's minimap rotates with the car like D2's.
- **C12 D2 zoom (Infrastructure 16.10.)**: exe group MAP_CLUT (exe_patches.py, 6 words 0x80054178..8C, shared list
  378 -> 384): the overlay-map loader FUN_80054140 uploads the CLUT from map + 0x148 + MAP_CLUT_EXTRA (gp+0x1134 =
  0x800978A4, no exe xrefs); the heap-pointer update is rewritten gp-relative to make room. D1 lumps all have the CLUT
  at 0x148 (160 tile slots), so the word is 0 for them; the plugin sets it to CLUT_AT - 0x148 from the level's frame
  (tiles = frame word 4 & 0xFF; > 160 -> CLUT_AT = (2 x tiles + 8) word aligned; F=1 Chicago: 252 tiles -> 0x200, extra
  0xB8). Levels work/var_c12_map1_day.lev / var_c12_map1_night.lev (b16b recipe CHI_ROADS=1 + CHI_POLISH_MAP_F=1 +
  CHI_POLISH_MAP_NUDGE=1,0; frame 290, 141, 672, 384, 252 | 9 << 8, 2831 stored in the lump). Verified (build-test, l_down_e):
  EXTRA 0xB8, D2 palette, no garbage tiles, dot on the road; Miami EXTRA 0, its map unchanged.
  Sheet findings/c12_map1_zoom_vs_d2_ref.png (with the user's D2 crops). setup_chicago's level cache key now hashes only
  the modules convert.py imports (modulefinder), so exe/package-only edits no longer reconvert at the next game start.
- **C45 quay round 3 (Polish 16.10. 14:4x): zero glitches needs the engine.**
  - Counter: a scripted loop at the user's pose (D2 -179758,-101534; 48 steps, all 8 heading octants, near and far)
    decodes each frame's GP0 (psxrecomp/tools/psx_gpu_frame.decode_entries) and counts textured non-sky polygons with
    area > 20000 or bbox > 600 x 300. Source matching: captured uv/tpage -> level polygons (scratch uvfind.py).
  - quay3 (SUBDIV_LONG=6000): 30/48 frames. Sources:
    - water tile 683 sub-quads (tile renderer pc 0x8007AFAC / 0x8005152C / 0x80079B2C, polygon flags ignored);
    - SHOREWALL 1215 (1500 x 2000, flags 0, built by convert.shore_wall_model) and FARWATER 1214 (flags 0);
    - small semi-transparent 0x60 polygons.
  - How D2 avoids it (REDRIVER2 draw.c PlotBuildingModelSubdivNxN + tile.c drawMesh): every textured quad near the
    camera is subdivided (2x2 / 4x4 when diff*4 > minZ-350, whatever its flags), and sub-quads with avg OTZ <= 5 or
    nclip <= 0 are dropped. There is no real near clipping. D1 subdivides only polygons flagged 0x20 / 0x40 and its
    tile path never.
  - Data imitation CHI_POLISH_NEARALL=E (d1models: 0x20 on every polygon with an edge >= E, tiles included):
    E=600 -> 13/48 frames, but frames/vblank at fps_drop_2 dropped 0.491 -> 0.447 (-9 %, breaks the C40 rule).
    The water tiles stay (the tile renderer ignores flags). Not for shipping; level deleted.
  - **Engine spec (Infrastructure, gated CITY 3 = Chicago, PS1-native):** in D1's polygon emitters reject a polygon
    when a projected vertex has SZ < NEAR (e.g. 48; or GTE FLAG bit 17 divide overflow) after RTPT/RTPS, as D2 drops
    near sub-quads.
    - Emitters seen in the captures: world handlers 0x8002CD94, 0x8002D2DC (function 0x8002D0F4), 0x80082D04,
      0x80084C58; tile/water 0x8007AFAC, 0x8007AEE0, 0x80079B2C, 0x8005152C.
    - With that, no NEARALL is needed (no FPS cost; a few mfc2 + compares per polygon).
    - Check with the same loop counter (target 0/48).
  - Sheet: findings/c45_quay_r3_loop_sheet.png.
- **C63 LA by Day, feasibility (Polish 16.10.):**
  - D1 has ONE LEV per city for day and night: MIAMI/FRISCO/LA/NEWYORK.LEV have the same lump set, and there is no
    night LEV. So day/night is engine state:
    - night flag 0x80096850;
    - sky number by CITY (jump table 0x800108A8: LA 2 / rain 3; +1 night only for CITY 0/1/5);
    - LOOK_CITY 0x8009789C (Chicago day sets 0x7F);
    - lamp/light sprites and car lights follow the night flag.
  - LA's textures are night-baked. Mean texel luminance: LA 74.6 vs Miami 118.4, SF 111.9, NY 95.8. Dark texels:
    48 % vs 20-32 %. 257 of 551 textures (58 % of the texel area) are > 45 % dark: lit shop windows on black,
    window grids on black facades. Sheet: findings/c63_d1_city_textures.png.
  - A palette recipe cannot make day of them: findings/c63_la_day_palette_preview.png (gamma/saturation lift: still
    night) and _v2.png (black -> concrete, glow -> glass: washed-out grey, detail lost, since the shading lives in
    the darks).
  - Day textures need either a Design repaint of the 257, or a curated swap table onto D1's own day textures
    (NY/SF/Miami facades, same disc = Option A friendly; LA would partly look like NY/SF), or a mix: swap the window
    grids/backgrounds, repaint the landmark shopfronts.
- **C7 round 2 + C67 (Polish 16.10. 19:xx):**
  - D2 storey = 512 units: the mode of the vertex-level spacing of Chicago's 448 tall models is 510-519.
  - polish_tex now has CHI_POLISH_TEX_HIGH_MODE = mean (default) / min (lowest vertex) / share (share of polygons
    wholly above HIGH, CHI_POLISH_TEX_HIGH_SHARE). The choice is per texture: only 16 of 589 textures lie wholly
    above floor 3, and almost every halved texture (324 of 340) is also used at floors 1-3. min/share move the cut
    to ground-floor textures (share 0.75: ground-floor texel loss 0.94 M -> 1.16 M) = worse.
  - Best at the same budget: mean mode with CHI_POLISH_TEX_HIGH=1536 (3 storeys). Texels lost on textures first used
    at floors 2-3: 390 K -> 306 K (-22 %); textures from the ground floor: 941 K -> 996 K (+6 %; mostly tower facades
    tiled from the ground); textures wholly above floor 3: unchanged. Level work/var_polish_c7_high1536_day.lev
    (CHI_ROADS=1, TEX_HEIGHT=1, TEX_HIGH=1536).
  - Truly "ground + 2-3 floors sharp, upper soft" for one tiled facade texture would need a second (halved) copy
    for the upper polygons = more pages, not fewer.
  - C67 diagonal cuts: PS1 affine texture seams between the two triangles of large facade quads (the probe's
    settings.toml has perspective_texturing = false). Not caused by TEX_HEIGHT: the geometry and UVs are the same,
    and halving scales the UVs exactly; blockier texels only make the seam more visible.
  - D2 reduces such seams by subdividing every near quad. Our C40 default puts flagged polygons on D1's light fixed
    level (0x60).
  - CHI_POLISH_SUBDIV_TALL=H (d1models): quads >= H tall get the full near flag 0x20. H=512 cost 4.3 % frames at
    fps_drop_2 (0.495 -> 0.473): breaks the C40 rule, not adopted. Sheet: findings/c67_facade_subdiv_tall_sheet.png,
    user crop findings/c67_user_affine_seam_crop.png.
  - Options: (a) the user turns on perspective_texturing (host-only; removes all affine seams); (b) a PS1-native
    engine change: subdivide only quads whose screen-space depth ratio is large (D2's diff*4 > minZ-350 test) in
    D1's light handler.
- **C70 quay wall "wrong position" (Polish 16.10. 20:4x):**
  - The placement matches D2. DriverLevelTool world OBJ of D2 and of var_c45_tv2_day, top-down at the user's point:
    the same bridge, the balustrade (1114) on the bridge edge, water on both sides. OBJ mapping: D2 X = -ox*4096,
    Z = oz*4096; D1 the same.
  - The converter puts 1114/1115 at exactly 1.32 x D2's offsets (D2 dz -527 -> D1 -696; 1115 at y 1014 = D2 768).
  - There is no object within 1600 units of the car at 202133, yet the user's shot shows concrete wall faces at the
    car. Those are stretched near-camera polygons of the long quay-wall strips (1114/1115, 9462 long, running 696
    south of the car): the C45 near-clip family, not a position error.
  - The fix is the C45 round 3 engine spec (near-Z rejection in the polygon emitters, Chicago-gated). No data change.
  - Sheet: findings/c70_quay_position_sheet.png.
- **C63 LA by Day step 1 (Polish 16.10. 23:4x), route C:**
  - `polish_laday.py` (CHI_POLISH_LA_DAY=1; `python polish_laday.py OUT.lev`, all inputs read from the disc via
    inputs.py) builds the swap table work/polish_la_day_table.json and writes it into LA.LEV:
    - Night textures: LA world textures (not special/car pages, used by models, not ground/sprite/HUD names) with
      > 30 % dark opaque texels, or lit window grids (> 8 warm blobs).
    - Donors: NY/SF/Miami world textures that read as day (mean lum >= 90, < 30 % dark), not ads (saturation
      <= 0.45, name filter). The match uses a 16x16 edge signature, aspect within 2:1, a same-size bonus, max 3 reuses.
      Roads swap only with donor roads.
    - Design list: lit shopfronts / landmarks (few warm blobs, or landmark names), top 24 by use x area:
      findings/c63_la_day_design_list.json.
  - Writing: raw spooled pages are patched in every area copy; resident compressed pages are re-encoded and the
    TEXTUREINFO perm/special sizes updated (Lev.build(keep_layout=False)).
  - Result var_polish_la_day_3.lev: 168 night textures -> 144 swaps + 24 Design. In game in the Chicago slot (day
    look, Chicago day sky as a stopgap) LA reads as day (findings/c63_la_day_sheet.png).
  - A few unsuitable donors remain (a "Computers" sign, a helicopter ad, a poster): add them to AD_WORDS / a
    Design exclusion list.
- **C46/C56 sky d2v2 (Polish 16.10. 23:5x, Design QUEUE 6c):** polish_sky CHI_POLISH_SKY=d2v2 (package time):
  - cap v0..26 = D2 row-0 mean colour; D2 clouds y0..83 -> v26..61; skyline y84..167 -> v61..108 (horizon v108);
    horizontal box 2:1;
  - by day v102..108 blend 25 % toward the skyline base colour (no haze ramp);
  - reflection v108..126 = flipped D2 y167->126 at 0.5, then 35 % toward (176,186,198) day / (38,38,35) night.
  - Versioned work/var_polish_c46_sky4.BIN. Captures day + night at bridge and riverbridge with var_combo2:
    findings/c46_d2v2_sky_sheet.png (with Design's D2 reference).
  - Seen: at street level the skyline band still reads as a big dark block behind the near buildings. The pale
    translucent rectangles above it are Chicago geometry, not the sky. Coloured speckles on the river at
    riverbridge (day and night) are a separate water-texture issue to check.
- **C63 LA day v4 (Polish 16.10. 23:5x):**
  - polish_laday.reviewed_table() adopts Design's review (design/la_day_swap_review.json: 106 keep, 15 replace with
    named donors, 23 LA signs/posters excluded = unchanged) and Design's CLUT-only repaint recipe for the 24
    landmarks/shopfronts (design/la_day_repaint.py recipe(); same pixels, day CLUT).
  - Used automatically when the review file exists (CHI_POLISH_LA_DAY_REVIEW=0 = matcher only).
  - Level work/var_polish_la_day_4.lev: 121 swaps + 24 repaints. Sheet: findings/c63_la_day_4_sheet.png.
  - Some kept LA textures still show lit windows (e.g. DT53, a window grid on Design's sign_keep list, and a few
    facades under the 30 % dark rule): Design's call.
- **Sky d2v3 (Polish 17.10., Design QUEUE 8):**
  - CHI_POLISH_SKY=d2v3 (polish_sky._d2_v2(v3=True)): Lanczos + UnsharpMask(1, 60, 2) for the reductions; cap
    v0..12; clouds v12..61; skyline v61..108; by day v84..108 blend 40 % toward (176,186,198) with floor (110,118,128);
    6c reflection.
  - work/var_polish_c46_sky5.BIN (sky4 deleted). Sheet: findings/c46_d2v3_sky_sheet.png.
  - The dark block at bridge still renders (80,88,88) although the dome's v84..108 is now >= (110,118,128): that block
    is NOT (only) the dome. Next: a GP0 capture there to see which primitive draws it (far geometry / C73?).
- **LA day v5:** Design's recipe now repaints 45 textures (DT53 + 20 more lit ones); var_polish_la_day_5.lev =
  121 swaps + 45 CLUT repaints (findings/c63_la_day_5_sheet.png); _4 deleted.
- **C63 LA by Day, engine part (Infrastructure 17.10.):**
  - Package: `CHI_LA_DAY_LEV=path` (build_package, opt-in) copies the LA day level to assets/la_day.lev at the next
    1000-sector boundary after the last relocated file (LBA 348000 with day+night+sky+music) + an `[[overlay]]`;
    the sidecar grows to 37 words (29-36 = LA day's 8 level-table entry words).
  - Plugin (driver_chicago.c, `s_have_laday` / `s_la_day` / `la_day_active()` = slot on, LA row, CITY 3, mission 0x7C):
    - menu: the LA row's confirm becomes Miami's 0x001C444C (Day/Night screen) on both menus;
    - the Day/Night remap: with the LA row (s_virtual V_LA) 0x78 = day, 0x79/0x7D = night, mission back to 0x7C;
    - level table entry 3 = LA day entry while active (LA's own otherwise; story LA missions != 0x7C stay night);
    - LOOK_CITY / C3 = 0x7F (chday), SUN_CITY follows (D1's day sun + glare);
    - night flag 0x80096850 cleared each vblank (LA's Take a Ride script does not set it: LA's night look is
      LOOK_CITY == 3, e.g. FUN_0002360c `night_flag || LOOK_CITY == 3`; brightness 0x80097128 is 0x80 in both);
    - sky immediates 0x8004EDE0/EC/EE00 = Miami day 4 / rain 6 (CHI_LADAY_SKY=n: 7 NY, 10 SF; rain n+2), present in
      the original SKY.BIN too;
    - music: the mission-parse hook writes MUSIC_XOR = 2 ^ ((mission+3)&7) -> song 2 ("The Briefcase"); the C60 chase
      table gives song 2 its own chase position. The parse also runs from the in-game script (0x80068C6C, s0 is not
      the mission there), so LA day keys on the mission word, not s0.
  - Sanity (devtest c63, var_c70r3 pair + var_polish_la_day_5): LA day = entry3 0x2A7B0800 (LBA 348000), night 0,
    look/sun 0x7F, sky 4, song 2, drives; LA night = LA's own entry 0xCB5800, look 3, sky 2, song 7 (unchanged);
    Chicago day = sky 13, song 8 (unchanged).
  - Open: the Day/Night screen's background is the same picture for every city (as for Chicago); setup_chicago (the
    user's own build) does not build the LA day level yet (needs polish_laday from the disc + CHI_LA_DAY_LEV);
    host-only list: the LA day switch is part of the plugin-logic row.
- **The bridge "dark block" is geometry, not the sky (Polish 17.10.):**
  - With the colour-coded test sky (CHI_POLISH_SKY_TEST=1) the sky shows its test colours around and above, while
    the block stays near black (8,8,8) as tower silhouettes. With the d2v3 sky it reads (80,88,88).
    Sheet: findings/c46_dark_block_is_geometry.png.
  - The GP0 ring at that spot holds ~985 packets per game frame, and the dome / far towers did not show up in the
    decoded composite, so the drawing function could not be attributed this way.
  - So: distant towers drawn dark (far LOD models and/or the distance colour fade), where D2 shows them blue-grey
    and textured.
  - Route: Infrastructure (C73 draw distance / far LOD, plus the depth-cue far colour for Chicago day). Not
    fixable in the sky data.
- **Sky dome lower band / "pale ghost towers" = VRAM conflict (Polish 17.10., river view 222505, d2v3):**
  - The 12 dome polygons (OT 0, tpage 8) read u 0..255 / v 0..125 of page 8 (VRAM x 512..575) with per-piece CLUTs.
  - The VRAM dump shows our D2 sky correctly only in u 128..255 (x 544..575). At x 512..543, y ~15..226 sits the
    city-selector preview picture (a car in a city, rounded frame), uploaded AFTER the sky (it also covers the sky
    rows). So dome pieces 0/1 of every band draw the preview: the pale translucent "towers" up top and the dark
    lower band.
  - My earlier test sky only changed the right half, which is why the block looked like geometry. Infrastructure's
    "LA's dome texture" is this overwritten area.
  - Fix route (Infrastructure, plugin/frontend): upload the selector preview only while the frontend runs, put it
    in a VRAM area the level does not use, or re-upload the sky pieces after it. No data fix: SKY.BIN is already
    right. Sheet: findings/c73_sky_vram_overwritten.png.
- **C45 corr5 (Polish 17.10.): smoother loading without the texture cost.**
  - CHI_POLISH_AREAS_SHARE (area merge limit, x CHI_AREA_TEX, default 1.1) = 0.8 gives 16 areas instead of 15, and
    624 downscaled textures, fewer than the base layout's 661.
  - New CHI_POLISH_TEX_PROTECT=1 (polish_tex.protected / LANDMARK_PREFIX: NAVPIR, ARTINST, MRCHMRT, WRG*, FMNH,
    ADDLER, CHINA*, SDRFLD/MEGFLD, JOHNH, STOLHA, 333NW, CHISTR, SDTL, CABGRN, WICKL, STNICH, EL*, SEARS, ...) keeps
    landmarks last in the halving order.
  - corr5 = CHI_ROADS=1 + AREAS=2 + CORRIDOR=2 + AREAS_SHARE=0.8 + TEX_PROTECT=1: 654 downscaled, 0 landmark
    textures halved (base 88, corr4 117). Generic textures take the difference (+371 K texels beyond base).
  - Routes (scratchpad routes6p.py = Infrastructure's routes6 on copy polish / 4470): corr5 2 switches, 4 stalls,
    25.4 FPS vs corr4 4 / 7 / 24.1 in the same harness. Every route ends in a wreck after 9-22 s in both levels.
  - Levels work/var_polish_c45_corr5_day/_night.lev. Table: findings/c45_corr5_tradeoff.png.
- **C70 quay clean-up (Polish 17.10., user R30):**
  - CHI_POLISH_QUAYCLEAN=1 (convert.shore_walls): our generated SHOREWALL fillers (model 1215, 1500 x 2000, top
    40 below the bank) are dropped within QUAY_R=1600 of Driver 2's own quay-wall lines (1113/1114/1115; 184
    segments from D2's cell objects: origin + model z axis rotated by yang, 7168 D2 units). 257 of 4616 fillers
    dropped city-wide; beach walls elsewhere stay.
  - The water tiles (y 1084) already fill the river below D2's quay walls (which reach 1014).
  - Level work/var_polish_c70_qc1_day.lev (CHI_ROADS=1 + the switch). Sheet next to the user's quay 3 shots:
    findings/c70_quayclean_sheet.png.
- **Sky d2v4 (user R30):** the d2v3 haze blend started at v84 and left a bright step across the towers. d2v4 blends
  the whole skyline section v61..108 (40 % toward (176,186,198), floor (110,118,128)); the reflection below as before.
  work/var_polish_c46_sky6.BIN (sky5 deleted). Sheet: findings/c46_d2v4_sky_sheet.png.
- **C63 LA day v6 (Polish 17.10., user R30 + Design QUEUE 10):**
  - Repaint v2: Design's role-based la_day_repaint.recipe() (45 textures).
  - Coverage pass in reviewed_table(): every other LA world texture still night-painted (opaque texels > 30 % dark or
    mean lum < 70; not swapped / repainted / sign_keep; not cars, wheels, HUD, peds, sky, sea) gets a CLUT-only day
    version: vegetation (VEG_WORDS by name, or a mostly green palette) via Design's veg_clut, the rest via day_clut.
    31 textures: veg GRASS02, TREE, BARRIER; other: far / LOD ground tiles DT2-35A/B and DT3-11B, sand, the airport
    apron, rocks, props (bench, bin, phones, meter, cones, barrel, barriers, billboards, signs). List:
    findings/c63_la_day_6_cover.json.
  - LA day sky: polish_laday.la_day_skybin() = D1's 13 + Chicago 13/14/15 + Design's LA day sky as **index 16**
    (free) -> work/var_polish_la_day_sky1.BIN. Infrastructure: CHI_LADAY_SKY / the plugin should set sky 16 for
    LA day.
  - Level work/var_polish_la_day_6.lev = 121 swaps + 76 repaints. The capture used a test SKY.BIN with the LA sky
    in slot 13 (deleted afterwards). Sheet: findings/c63_la_day_6_sheet.png (trees green, warm LA haze sky, props
    lit by day).
  - Open: some palm fronds still read dark green-blue (Design's veg colours); ROD24 / DT53 were not in the
    captured views.
- **C63 LA day v7 (Polish 17.10.):**
  - Conflict resolved by pixels and users: DT2-35A (96x96) is the PALM sprite (also referenced by the
    DETAIL_ROAD/JUNC tile models), DT2-35B its trunk strip. The far-street texture is **DT3-11B** (asphalt with a
    dashed centre line, on 32 tile models).
  - v7: Design's VEG_RECIPE per name (palm/tree/wall -> veg_clut v2, GRASS02 -> dry grass, SAND/ROCKS01/BARRIER ->
    flat_clut); DT3-11B -> match_clut to the near road's day donor (ROAD2A -> FRISCO ROAD1: luminance quantiles +
    tint, lane markings kept); Design's ROD24/DT53 tweaks via recipe().
  - work/var_polish_la_day_7.lev (_6 deleted). Sheet: findings/c63_la_day_7_sheet.png (palms sunny green, far road
    matches the near road, sand/grass/rocks by day).
  - Seen: black triangle shards around a crash (debris / crash particles still night-dark, likely on a special/car
    page): next coverage item.
- **C63 LA day v8 (Polish 17.10.):**
  - Night-only leftovers that the engine draws by name (not on models, LA page 2/7): DEBRIS (crash shards, dark
    0.55) -> day_clut (ENGINE_DAY in polish_laday).
  - SMOKE stays: it is drawn additive, and a light smoke CLUT became a white blob in the capture. SKID is already
    mid-grey; FLARE1/LIGHT/SUN2 lamp halos follow the engine's night flag.
  - work/var_polish_la_day_8.lev (_7 deleted). Sheet with a crash: findings/c63_la_day_8_sheet.png (the cop crash
    shows no black shards).
- **C70 r2 quay fill (Polish 18.10., user R31):**
  - At the user's pose (D2 -181797,-100505) the circled pieces are D2's lower river walk: model 1000 (a 1204-tall
    face at y 991, left), 1115 (lower wall), boxes 117/119/122 at y 991; plus our SHOREWALL filler.
  - CHI_POLISH_QUAYFILL=1 (convert, boxes around the 3 user poses, or "x,z,r;..."): drops QUAY_DROP = 1000, 1115,
    117, 119, 122 and fillers inside the boxes, and adds water tiles at the river's level (y 1084) on every 1500
    sub-cell not under a water tile whose road-map levels are water or only low (the lower walk): 13 objects
    dropped, 8 water tiles added.
  - Level work/var_polish_c70_qc2_day.lev (+ QUAYCLEAN; qc1 deleted). Sheet: findings/c70_quayfill_sheet.png
    (the left slab is gone).
  - Remaining: the dark band right under the balustrade is the balustrade model 1114's own wall face (one model with
    the railing). Removing it needs a balustrade-only variant of 1114 inside the box (possible, ask the user).
- **C70 r3 quay clean-up qc3 (Polish 18.10.):**
  - CHI_POLISH_QUAYFILL=1 now works on the whole lower river-walk stretch around quay_wall. Sites = D2's lower-walk
    pieces (1000/1115/117/119/122 below the street) within 12000 of quay_wall: 23 sites; everything within 2500 of a
    site is cleaned.
    - lower-walk pieces and our fillers dropped;
    - the balustrade models 1113/1114 swapped for rail-only copies QRAIL1113/QRAIL1114 (convert.rail_only: polygons
      reaching > 60 below the origin collapsed; models 1216 -> 1218);
    - water tiles at y 1084 on uncovered water / low-only sub-cells: 38 objects dropped, 14 water tiles added.
  - Levels work/var_polish_c70_qc3_day/_night.lev (+ QUAYCLEAN; night CHI_D2_LEV=night + CHI_NIGHT_MOON=1); package
    env CHI_POLISH_SKY=d2v5. Sky d2v5 = Design's levels pass (design/sky_d2v5_levels.py) after d2v4, day only:
    work/var_polish_c46_sky7.BIN. Sheet: findings/c70_qc3_sheet.png.
  - Side effect: where the lower walk's wall (1000) closed the gap, the car can now drive off the quay into the river
    (drowns), as in the day capture.
- **C70 qc4 (Polish 18.10.):** removed lower-walk pieces keep their collision. Instead of being dropped, QUAY_DROP
  objects inside the stretch use invisible copies QGHOST1000/1115/117/119/122 (rail_only with every polygon
  collapsed; collision block kept; models 1218 -> 1223). Only our SHOREWALL fillers (no collision) are dropped.
  Levels work/var_polish_c70_qc4_day/_night.lev (qc3 deleted). Check run at the user's pose: the car stays on the
  street (end y 176, not wrecked): findings/c70_qc4_day_check.png.
- **C63 LA day v9 (Polish 18.10., Design R31):**
  - No donors for roads / paths: names in Design's VEG_RECIPE skip the swap. ROAD2A, ROAD01A, NEWROAD3/4, PATHC,
    BCKLANE/2 use asphalt_clut on LA's own pixels, and the far road DT3-11B uses the same asphalt.
  - Every donor CLUT goes through Design's la_grade_clut. VEG_RECIPE v3 (trees, trunk_clut, cone_clut).
  - work/var_polish_la_day_9.lev = 114 swaps + 76 repaints (_8 deleted). Capture along the user's la day 2 spots:
    findings/c63_la_day_9_sheet.png (uniform asphalt, no white intersections).
  - Open: some facades still show lit yellow window grids (textures under the night thresholds or on Design's keep
    list).
- **C63 LA day v10 (Polish 18.10.):** Design's 46 repaints + the stronger la_grade_clut; work/var_polish_la_day_10.lev
  (114 swaps + 77 repaints; _9 deleted). Sheet: findings/c63_la_day_10_sheet.png.
  - Bug check "olive palm trunk": GPU capture at the spawn. The olive pole is RODPOST (page 1, 208,160 16x64, olive
    night CLUT; on Design's sign_keep list), not the palm. The palm model 304 is fronds DT2-35A + trunk DT2-35B
    (poly tex 12 = detail 12, CLUT 12), and its CLUT in the level equals trunk_clut (brown).
  - "Black cones": CONE2 is the only cone texture (model 348 CONE_TASTIC); its level CLUT equals cone_clut (orange),
    and cones render orange in the captures. The dark shapes beside the player car are its wheels.
  - Remaining: one lit window grid on a brick facade (third frame).
- **C70 qc5 + sky d2v6 (Polish 18.10., user R33):**
  - The sloped quay walls are the real ones: 1113/1114 faces and 1115 stay as D2 has them.
  - CHI_POLISH_QUAYFILL=2 makes only the vertical fronts standing before them invisible (1000 and the lower-walk boxes
    117/119/122 -> QGHOST copies, collision kept), with no rail-only swap. The water fill stays.
  - Sky CHI_POLISH_SKY=d2v6 (day only): Design's d2v5 sky rows, skyline band 0.85*(0.8c) + 0.15*(100,104,108): tower
    darks ~ (99,105,111) instead of (137,144,154). Reference towers (user's D2 shots): (124,119,117) / (70,74,67).
    work/var_polish_c46_sky8.BIN (sky7 deleted).
  - Levels work/var_polish_c70_qc5_day/_night.lev (qc4 deleted). Sheet: findings/c70_qc5_sheet.png. In the capture
    drive the car jumped near the gate house; not wrecked.
- **C63 LA day v12 (Polish 18.10., Design QUEUE 15-17):**
  - No donor swaps any more. polish_laday.v12_entries() + write_entries() (default mode CHI_POLISH_LA_DAY_MODE=v12;
    "reviewed" = the old donor pipeline) take Design's night_targets().
    - Textures with > 1 % lit pixels -> la_day_pixels.day_v3 (new 4-bit indices + CLUT written into every page copy);
      the rest -> day_v2_clut (CLUT only).
    - VEG_RECIPE names keep their recipes (veg v4); DEBRIS keeps its day CLUT.
    - 178 entries: 128 pixel, 32 CLUT, 17 recipe, 1 engine.
  - work/var_polish_la_day_12.lev (_11 and design/out/design_laday_test.lev deleted). Capture from the user's la day 3
    start: findings/c63_la_day_12_sheet.png. The LA sky still needs Infrastructure's index-16 hookup for the probe.
- **Map items from "d2 cars 5" (Polish 18.10., partial):**
  - Sand patch (snapshot 150740, D2 45600,-228437): all sand models there (75/107/109-111, texture SAND) and their
    SUBDIVISION records are remapped correctly (no D2 UVs in models or the lump). The GP0 capture shows the darker
    strip as sub-quads drawn with the SAND CLUT but D2's original SAND UV rect (192..255, 224..255), e.g. pc
    0x8002D2DC/0x8002CD94/0x8002CD20, OT 3036/3543, next to correct sub-quads of the same object. The source of
    those UVs is still open: an engine-side tile UV path (Infrastructure trace of 0x8002D2DC's UV source at that
    pose).
  - Monument water (150819, D2 46494,-226366): the hole beside the monument is a no-surface area that sea_kinds
    classifies as "inside" (enclosed -> plain ground). D2 shows its global water level through such holes.
    CHI_POLISH_INSIDEWATER=R (water tiles on inside cells within R 3000-cells of lake/river water) does not reach the
    monument even at R=3 (853 cells city-wide, too many). Needed: a per-hole rule (basin vs building interior, e.g.
    no building object over it).
- **C75 basin water (Polish 18.10.):** CHI_POLISH_INSIDEWATER=basin (convert.exposed_inside_cells).
  - Each enclosed no-surface hole ("inside", 633 holes) is judged from Driver 2's own objects in it and its 1-cell
    ring. It is a basin (gets water tiles) if some object carries a water-edge texture (WATER_TEX: RIVER, BUKFON,
    FOUNT, POOL, WATER) and <= 35 % of the objects are 1000+ high; building blocks are facade-dominated.
  - D2's overhead map has no water colour at Buckingham Fountain (13/9 grey) and the radius rule could not reach it.
  - Result: 11 basins, 134 road cells, including the fountain (16 of its 58 objects are tall centre pieces). Two
    random holes (523,893) and (399,783) stay dry.
  - Level work/var_polish_c75_basin1_day.lev (+ CHI_ROADS, QUAYCLEAN, QUAYFILL=2). Sheet:
    findings/c75_basin_sheet.png (water in the basin from the south).
- **C75 basin check (Polish 18.10.):** D2 top-down renders of the 11 basins (findings/c75_basins_d2_views.png):
  - real (no D2 geometry, so D2's water level shows): Buckingham Fountain (87 cells); the 18-cell channel at D2
    (-14311,13143); 4 x 5-cell channels at x -155852;
  - false: 5 holes of 1-3 cells on the north lakefront (x -183124) lie under building roofs.
  - Rule tightened: BASIN_MIN = 5 road cells, giving 6 basins. Level work/var_polish_c75_basin2_day.lev (basin1
    deleted).
- **R34 (Polish 18.10.): quay / sky / fountain, pair work/var_polish_r34_1_day/_night.lev (package env CHI_POLISH_SKY=d2raw)**
  - Quay: reproduced the user's 3 quay + sky 6 views with the CHI_TEST_POSE hook (pose file "x y z angle", angle =
    RAM 0x8009B19C & 4095). The "see-through" far quay was our QUAYFILL=2: the lower-walk boxes 117/119/122 are the
    quay seen from across the river. CHI_POLISH_QUAYFILL=3 hides only the vertical front 1000 (collision kept); the
    boxes and the sloped walls stay, and the water fill stays.
  - Sky CHI_POLISH_SKY=d2raw (day; night = d2v4): D2's art only placed (cap v0..12 flat D2 top colour, clouds
    y0..83 -> v12..61, skyline y84..167 -> v61..108, reflection flipped at half brightness), Lanczos, no grading.
    work/var_polish_c46_sky9.BIN.
  - Fountain: basin water tiles at BASIN_Y = 24 (CHI_POLISH_BASIN_Y; just under street / sand level -22) instead of
    the river's 1084, for all 6 basins.
  - Sheet: findings/r34_quay_sky_fountain_sheet.png.
- **C63 LA day v13 (Polish 18.10., Design R34 QUEUE 18-20):** v12_entries now uses la_day_pixels.day_v3 (region recipe,
  detail transfer LA_DAY_DETAIL=0.5) on every night target (160), the VEG_RECIPE names their own recipes (17), DEBRIS
  as before. work/var_polish_la_day_13.lev (_12 and design/out/design_laday_test.lev deleted). Sheet:
  findings/c63_la_day_13_sheet.png. Some facades look blotchy/blue-grey (busy window regions): Design's call.
- **R35 (Polish 18.10.):**
  - LA day v15 = v11 buildings + v14 vegetation/props (polish_laday.v15_entries, default mode CHI_POLISH_LA_DAY_MODE=v15):
    the reviewed donor swaps + Design's v11 day CLUTs, frozen in design/la_day_v11_cluts.json (35 CLUTs; the repaint
    code changed since the user approved v11), then v14's entries for VEG_RECIPE / props / debris on top. All 520
    building textures are identical to the user's approved D:/temp/la day 3 la_day.lev. work/var_polish_la_day_15.lev
    (_14 deleted). Sheet: findings/c63_la_day_15_sheet.png.
  - Bridge hole at quay_wall: the converter dropped D2 street-level tiles (PATH1 149) whose road cell the overhead map
    paints as river. CHI_POLISH_KEEPSHORETILES (default 1) keeps tiles that stand on a real D2 surface.
  - Quay city-wide: CHI_POLISH_QUAYFILL=4 = mode 3 for every D2 lower-walk site (4853 sites: front 1000 invisible,
    collision kept; fillers dropped; water tiles on water / low-only cells at the nearest water level).
  - Basins: water continues one cell under the surrounding sand (at BASIN_Y 24, hidden below it), so no gap at the rims.
  - Pair work/var_polish_r35_1_day/_night.lev (r34_1 deleted). Sheet: findings/r35_map_sheet.png (bridge hole
    filled, fountain water continuous, far quay visible).
- **S1 per-area texture packing (Polish 20.10.), result: not the lever we hoped for.**
  - Diagnostic CHI_POLISH_PACKSTAT=1 (texrepack): budget 13 pages per area - 4 permanent = 9 per area. Chicago areas
    need 6.3-15.8 pages of area textures at full resolution (101-175 % of capacity; only area 9 fits).
  - Ideal simulation (every area packs its own set at 92 % fill, halving largest first): 352 textures halved somewhere
    (1297 area-halvings, 64.6 page-area units lost). With +1 page per area: 298; +2: 246; +3: 199. Today: 654 halving
    operations on ~330-345 distinct textures, ~18.4 page-equivalents (~80 page-area units).
  - Of 589 Chicago textures, 274 are used by in-memory models (fixed UVs in every area) and 3 by tiles; only 312 are
    area-only. CHI_POLISH_S1=1 (polish_s1.py + texrepack S1_LOCAL/S1_RESERVE/remap_area + convert per-area model
    remap): the 311 local textures packed per area (73 halved somewhere), but the global pass, squeezed by the page
    reserve, halved its textures harder (574 operations, roads to a quarter). Net: no real improvement.
  - Conclusion: the binding limit is VRAM pages per area, not packing. Gains need more pages per area: S2 (CLUTs to
    rows 496..511 = +1 page), the 2 special (car) pages, D2-style layout (C77), or streaming the in-memory models'
    textures per area. Kept behind the switch (default off); levels deleted.
- **S1 options for the user (Polish 20.10., estimates):** builds with CHI_POLISH_EXTRA_PAGES=k (texrepack budget + k pages per
  area, estimate only) on today's Chicago day: halved textures 654 today -> +1 page 557, +2 472, +6 66 (current packer;
  the ideal per-area packer would reach 280 / 247 / 51). Slot-15 short page (~0.67 page) -> ~590. In-memory models
  visible per area: 45-106 KB (D2 sizes; the in-memory lump is 168 KB): streaming them per area makes all their
  274 textures per-area packable (~350-400 halved, ideal sim 352). Miami: already full (7 permanent + 5-6 area
  pages + 2 special = 15); a repack frees 2.7 pages of exact duplicates but nothing visible changes (no halving in D1).
- **S1 slot-15 short page (Polish 20.10., data side of Infrastructure's CHI_CLUT_STRIP + CHI_S1_SLOT15):** CHI_POLISH_S1_SLOT15=1
  (texrepack): the most-shared Chicago textures (permanent first, then by number of areas) fill a 5th permanent page,
  256 x 170 (rows 170.. stay 0), flags 1|0x80, ≤ 31 CLUTs, not counted in the area slot budget. Today: 10 textures,
  42 K of 43.5 K texels; halved 654 -> 585. Test level work/var_polish_s1_slot15_1_day.lev (page index 9).
- **Q36 B: in-memory models streamed per area + per-area texture packing (Polish 21.10.):**
  - CHI_POLISH_STREAM_INMEM=1 (convert.stream_keep): 319 of 497 in-memory models move into the area spools. Kept
    resident: tiles, LOD targets, sky slots, lights, the water model, unplaced, quay sources, instance sources of kept.
  - Together with CHI_POLISH_S1=1, 540 textures are packed per area (each area's model copies get their own UVs).
  - Halved placements 56 % -> 47.5 %; lost texels 82 -> 64 page-area units (= the ideal-packing simulation).
  - RAM: in-memory lump 202 -> 67 KB, model spool buffer 98 -> 176 KB (net ~-57 KB). Area switch reads +62 KB on
    average (S3 compression).
  - Levels work/var_polish_opt2a_day/_night.lev (+ opt1 recipe). First look OK (findings/opt2a_first_look.png).
  - Engine checks requested from Infrastructure: staging at buffer+0xA000, C30 carry / C33 guard, trailer size.
  - texrepack prints "texture placements (Chicago, per area)" as the comparable metric (the old "downscaled
    textures" count = halving ops of the global pass only).
  - CARPAL_MERGE touches only car-model textures on the car pages (5/6). The bus is a special with its own
    textures/slot: not affected.

## Q42: scripted test runner on the debug server (Infrastructure 23.10.; core built, MCP wrapper next)
- **Built (step 1):** `devtools/runner/` (session.py, report.py, __main__.py, tests/). `cd devtools; python -m runner list |
  run NAME... [--port 4468] [--copy runner] [--build build-test]` -> devtest/_out/runner/<time>-<test>/ (steps.jsonl,
  result.json, report.html, PNG, WAV, game.log). Session: menu(path), pose, drive, hold/press, wait_for, poke32, car(i),
  find_model, screenshot(+baseline diff), audio(secs) -> WAV + metrics (rms, peak, clicks, silences). Verdict fails on a
  failed check, crash or a real '-hang' dump; recovered watchdog snapshots ('-stall', FMV) are only noted. Tests (all PASS
  23.10.): bus_head_on (C82: yaw 4-7 deg, contact 1235-1248), out_of_tape (C81: Out of Tape at +17 s, 2 min on, no hang),
  undercover_interview (C84/C80: timer runs, overlay unpatched, 5 s WAV rms 6.6k, 0 clicks).
- **Watchdog change (driver_personal.c):** a '-hang' snapshot whose game moves again is renamed '-stall' (Undercover's
  intro FMV stops the VSync counter for > 3 s and made a false '-hang' dump every time).
- **MCP wrapper (step 2, 23.10.):** `devtools/runner/mcp_server.py` (stdio JSON-RPC, no extra packages): tools launch,
  stop, status, menu, pose, press, hold, drive, read_ram (<= 256 B), write_word, wait_word, screenshot (+baseline), audio_capture,
  list_tests, run_test; one session at a time (devtest/runner, port 4468), compact JSON, tool prints go to stderr. Checked
  with a stdio client (launch -> Miami -> drive -> screenshot -> 3 s WAV -> stop). Not registered in any MCP config (a
  user / Strategy decision): command `python D:/recomps/Apps/Driver-DriverRecompiled/driver_personal/chicago/devtools/runner/mcp_server.py`.
- Design (as drafted):
Goal: Playwright-style, repeatable game tests instead of one-off scratch scripts; one API for humans, agents (MCP) and
batches. Built on what exists: dt.prepare / dt.launch (copies, ports, BELOW_NORMAL), the TCP debug server (set_input, ram,
shot, spu_*, audio_wav, fntrace / wtrace), the dev-mode watchdog dumps.
- **Package** `devtools/runner/`: `session.py` (one instance: build, level(s), state features, env, port, copy; start / stop
  by PID; collects run.log + dev/dumps), `steps.py` (actions), `expect.py` (assertions), `report.py` (JSON + one HTML page
  per run: steps, timings, screenshots, diffs, WAV links, verdict), `cli.py` (`python -m runner run tests/x.py`).
- **Actions:** `menu(path)` (named navigation: "take_a_ride/chicago/night", "undercover/new_game", "selector/interview";
  the menu sequences copied between scripts today live here once), `spot(name)` (spots.json pose), `press(btn, hold)`,
  `hold(buttons, secs)`, `drive(policy, secs)` (straight / random / route, reverse when stuck), `turbo(on)`.
- **Waits:** `wait_for(pred, timeout)` on RAM words (`ram(addr) == v`, `changes(addr)`), position, city, loading flag, a
  run.log regex, frame / VBlank progress; a failed wait records the last state.
- **Checks:** `screenshot(name)` + `expect_image(name, baseline, mask=, tol=)` (per-pixel / SSIM-like score, masks for HUD and
  traffic), `audio(secs) -> WAV` + metrics (RMS, click detector = max step vs p99.9, silence gaps), `expect_no_hang()` (VBlank
  counter + watchdog dump dir), `expect_ram`, `vram_check` (vramcheck.py as a step).
- **Baselines:** `devtools/runner/baselines/<test>/<name>.png|.json`, replaced only with `--update-baselines` (reviewed).
- **MCP wrapper** (`runner/mcp_server.py`, stdio): launch / stop / menu / spot / press / drive / wait_for / screenshot / compare /
  audio_capture / read_ram / run_test; compact JSON results (paths, scores), never raw dumps (token rule).
- **Rules kept:** one instance per agent port range, kill by PID only, no build-dev / user saves, no unapproved soaks, capped
  output like run.py.
- **First tests (today's scratch scripts):** chicago_night_drive (no hang, FPS), bus_front_ram (C82), engine_loop_click (C83),
  newtown_no_cops (C79), interview_selector (C80 / C85), undercover_new_game (C84), D1 cities + extras load smoke. Effort ~1 day
  for the core + MCP, then tests one by one. Host-only tooling (no PS1 relevance).

## R43 analysis: Newtown cops, Interview timer, special damage room (Polish 23.10., offline)
- **D1 mission script (MISSION.BLK):** index = 124 u32 offsets (entry e = [off(e), off(e+1))); loader segment table 0x8008C1E8
  (key, value) pairs: entry = mission - key + value for the first key >= mission. Opcode sizes: byte table 0x8008BCE4
  (mission_script_step 0x800687D4; specials 0x02 / 0x14 / 0x16 / 0x46 / 0x56 / 0x5E / 0x68). In-game interpreter
  FUN_80068C6C: 0x31 = cops off (0x800976F8 = 0), 0x32 = cops on, 0x26 n = cop cap 0x80097760 (n < 5), 0x18 n = wait n s,
  0x16 = message, 0x01 = end. Cop director FUN_80064A64 does nothing while 0x800976F8 = 0.
  - LA Take a Ride 0x7C (entry 92): `a 2(45,1) 22(3) 37 2(10,22000) 13(x,z) 34(5) 2(52,0) b 32 26(2) 2(45,0)`.
  - Newtown credits 0x7F (entry 95): `... 22(7) ... 2(66,0) 2(57,4097) 26(0) 31 2(52,0) b 2(45,0)` (no cops).
  - Interview 0xAE (entry 118): `... 22(2) 2(39,1) 26(0) 31 13(-10500,-22144) 34(0) 2(66,0) 18(10000) 16("Well done!") 18(2) 1`.
- **C79:** the selector's extras run LA's script → cops on, cap 2 (Newtown, Desert). Fix = plugin rewrite of 0x32/0x26 in
  the MISSION_SAFE copy for V_NEWTOWN (Infrastructure).
- **C80:** IVIEW.BIN overlay (LBA 127, 17120 B, 0x801E0000): timer 0x801E4278 (+2/update, 0x801E0738), red flash from 0xC00,
  time-up branch 0x801E0714, clock draw 0x801E1248 (call 0x801E0424), init 0x801E1008. Fix = overlay patch only for the
  selector's Interview (Infrastructure).
- **C87 (48, 23.10.): Driver 2's damage zones for the special.** D1 DamageCar3D (0x8003FC98) = D2 bcollide.c, but lbody is a
  fixed 0x104 and the nose is measured from the car origin; D2 uses colBox.vz / 2 per model from the body. Cave NOSE in the
  unreferenced 'ready_cb_*' strings (0x800104E0..0x8001052B; ghq xrefs, lui/addiu immediates and pointer words checked),
  jal from 0x8003FD70 ('addu v0, t1, a0' in the delay slot, NOSE does the moved 'mflo t0'): model 5 -> nose' =
  (nose - SPBO) x SPLB >> 12 with SPLB = 260 x 4096 / (SPBZ / 2) (plugin 0x800933C0; CHI_C87=0 exe, CHI_C87_ZONES=0 plugin).
  Runner special_zones: a side hit 500 behind the bus origin -> middle zone 2 = 4095 (Driver 1's rule: rear corner 3).
  Scenery hits (0x8003FF0C, same 0x104 compares at 0x80040800..): NOSES in the S1 cave (jal from 0x800407E8, its 'mflo t2'
  in the delay slot; NOSES does the moved 'sra v1, v0, 12', puts the car (s2) in t9 and jumps to the shared CORE at
  0x800104E8; NOSE (car-car) = 'mflo t0; move t9, t2' + CORE). Runner special_zones (homing approach, contact position
  logged): contact 351 behind the origin -> middle zone (D1 rule: rear); special_damage2 on specdmg2: coherent u+128
  damage textures, player wall hits through NOSES fine.
- **C82 SPTW from data (24.10.):** Polish's <lev>.spt.bin ("SPT1", n, civilian reference twistRateY, n x {model, twist})
  -> build_package asset spctwist_day / night.bin -> plugin SPTW = 0x37 x twist / ref (the old table stays as fallback).
  Chicago = the table (bus SPTW 12 checked in game); Havana 8 / 9: 100, 10: 50, 11: 180, 12: 420 (ref 224).
- **Q45 B +64 withdrawn (23.10.):** Polish found D2's damage offset goes to U (cars.c adds DENTUVS to u0/u1/u2), the copies
  now sit 128 texels right of the clean ones (D2's rule) -> CHI_Q45B_EXE default 0 (old DCAVE2: +128 at level 2 for level
  byte 1); .spd.bin rows unchanged (DMG_OFF reads 128). Levels var_polish_specdmg2_*.
- **C86 (23.10., build-dev regressions 47):** three load-delay hazards in our patches (R3000: the instruction after a load
  sees the OLD register; the recompiler models it): c42w wheel rim `lw t9; addiu t9, t9, 0x65` (stale t9 -> rim 202, tyres
  2x, every city), C37 MapHeight `lw v0, -8(s0); addiu v0, v0, -4096` (divisor from a instead of b in D2 cities -> wrong
  ground heights, the camera jumped), C42B box offset (`lw v0; beq v0` and `lw t2; mult t2`). Rescheduled / nop;
  exe_patches.load_delay_hazards() runs on every CLI use and refuses a patch set with a hazard. Runner: rim 101, Chicago
  camera dy -1001..+301 -> -714..-555, bus_head_on PASS; slopes test identical old vs new exe at diag_ramp / slope_ref
  (car physics uses FindSurfaceD2, hazard-free). **The probe 'special damage' (exe 784915f1) still has the tyre bug:
  don't judge wheels there.** build-dev re-shipped (ff86c7e3) with setup_stamp.txt so prelaunch keeps the opt2d package.
- **Q45 B engine side (23.10.):** exe c42d DCAVE2 (14 words, the cave's limit): after the row offset, a2 = (row == 5 * 256),
  shift = 6 - a2 -> offset = ((L^1) ^ ((L^1)|level)) << 5 for the special: level byte 1 -> +64 at damage level 2, 3 -> none.
  CHI_Q45B_EXE=0 = old cave. Plugin: specdmg_day/night.bin (build_package copies <lev>.spd.bin) -> spd_write_row5 at every
  special swap / rebuild / choice change (CHI_Q45B=0: all 3). Checked: LTAB row 5 == the bus's spd row, wrecked bus textures
  coherent. Lesson: never change an exe_patches default before the shared apply (the package guard breaks every dt.prepare).
- **C85 (23.10., plugin, with C80's selector flag):** IVIEW hit counter 0x801E35B8 is stored at 0x801E0D7C (AC8235B8)
  after the comment + speech; the X marks (0x801E1BCC, call 0x801E1674) and the stop at 4 (0x801E0828) read it -> the
  store becomes 0 (CHI_C85=0 off; Polish's addresses, verified in IVIEW.BIN). Run: 18 comments, counter 0, no X, no end.
- **C84 (23.10., regression from S4a):** Undercover > New Game -> black screen: FAIL-FAST unknown dispatch 0x9F079F08 (ra
  0x80101B94 = FMV player). The model-table vblank treated main RAM 0x80115600.. as the model table outside a level too
  (frontend heap / FMV player memory since S4a) and wrote s_empty_model there. Gate: s_lvl_beat (LVL_BEAT in the in-level
  hooks d2sf / wheels / lod / area queue / mission parse), table work only within 30 vblanks of it. Verified: model-table
  off = OK, build-dev = OK, fix = interview starts (timer runs); Chicago area switch carry still runs. Lesson: anything that
  reads/writes the main-RAM model table must check that a level is running.
- **C79 / C80 done (Infrastructure 23.10., plugin):** C79: mission_parse_entry (after the MISSION_SAFE copy) turns
  '32 26(n<5)' into '31 26(0)' for V_NEWTOWN (CHI_C79=0 off); test: 0x800976F8 / 0x80097760 = 0 / 0 for 32 s. C80:
  chicago_slot_vblank sets s_iv_sel at the selector's 0x7C -> 0xAE switch, clears it on a new frontend session (MENU_MARK
  0 -> 0x0172001A); while set and CITY 2 with the overlay present (0x801E0714 = 0x28621000): 0x801E0738 and 0x801E0424 ->
  0 (CHI_C80=0 off). Runs: timer 0 constant, no stopwatch; CHI_C80=0: timer +0x200 / 3 s, stopwatch, 'You ran out of
  time! Loser...'. Overlay code patched in RAM: the runtime revokes native code compiled from changed RAM (README).
  Host-only (M8: guest code patches the two words after the overlay load).
- **Q32 re-measure:** see the C42 row. Specials' D2 damage twins sit +128 rows below the clean texture (DEN kind 0 → level 2
  offset 128), 35-47 K px per special at full res; the 128-row slot can't hold a +128 twin. Free: page 8 top 8 K px, page 6
  ~3 K px. -1 area page costs halved 56.0 → 71.2 %, lost 82 → 110 units (CHI_POLISH_EXTRA_PAGES=-1 run, opt2d recipe).
- **C85 (selector Interview hits):** hit counter 0x801E35B8, ++ at 0x801E0D7C (after the comment + speech at 0x801E0C50..0x801E0D54);
  X marks 0x801E1BCC (call 0x801E1674); end at 4 = 0x801E0828 bne → state 3; end text 0x801E061C. Patch: 0x801E0D7C → nop.
- **Q45 B (CHI_POLISH_SPECDMG=1, default off; polish_specials._slot_layout_dmg):** [specdmg1 had the copies at v+64 = WRONG axis,
  user saw noise] since specdmg2: D2's damage offset goes to U (cars.c adds DENTUVS to the u bytes of the clut_uv0/tpage_uv1/uv3_uv2
  words); slot clean columns 0-127, D2 twin (u+128 on the D2 page, texels present) at u+DMG_OFF 128 = D2's own body rule; untwinned textures fill the rest. Uniform scale (binary search)
  then per-texture per-axis growth (4 % steps), 3 packing orders; area-filtered downscale with palette re-quantise
  (downscale()). <lev>.spd.bin = "SPD1", n, DMG_OFF, n x {model, 256 B level row: 1 shift / 3 none} (fitted clean polygon order).
  Area kept vs D2 (specdmg2): 8 25.6 %, 9 30.2 %, 10 27.8 %, 12 28.8 % (without damage: 44 / 47 / 39 / 55 %). City + CLUTs unchanged.
  Zone rows (48 a): exactly D2 DEN rows via fit_maps (0 zones differ; fewer entries only from quad merges / merged verts).

## C40 day 1 (Infrastructure 24.10.): dense-spot measurement + cost breakdown + lever plan (no code yet)
- **Method (runner, build-test 769db982 = build-dev + test-pose any city):** tests fps_spots (4 headings x 5 s standing,
  10 s driving; FPS = PHASE 0x800970D8 / VBlanks x 59.94; GP0 packets per game frame from gpu_ring_stats; phase_hot static
  diff = guest hot functions) + miami_dense_scan (Miami's dense views picked by GP0 packets per frame while driving 120 s).
  Chicago spots = level starts (fps_drop_1 / 2, l_down_e / w); Miami = its 3 densest views (pose + wait_world).
- **Numbers (standing avg / driving):** Chicago fps_drop_1 20.9 / 20.5, fps_drop_2 23.2 / 19.8, l_down_e 19.6 / (4.5 crash),
  l_down_w 22.4 / 20.2 -> **21.5 / 20.2**; Miami (8695,419942) 26.6 / 26.7, (40329,422641) 24.3 / 26.7, (40504,417683)
  24.8 / 29.1 -> **25.2 / 27.5**. Gap ~15 % standing, ~27 % driving. Packets per frame are SIMILAR (Chicago 670-2200,
  Miami 1000-2000): at the same packet count Chicago runs slower -> the gap is mostly NOT the map's primitive count.
- **Hot functions, share of guest samples (Chicago / Miami):** GlobalTimeStep 0x8001C214 3.3 / 0.0; FUN_8003E244 (from
  FUN_8003A45C, car draw) 2.9 / 0.3; FUN_8001B380 (per-car matrix in GlobalTimeStep) 2.7 / 0.4; FUN_80067A44 (car-car box
  SAT, from 0x80067838) 2.3 / 0.0; FUN_800305D0 1.7 / 0.3; 0x80011924 (C68 stub, per object) 1.4 / 0.0; FUN_800277D4
  (near tiles, from 0x800287A4) 1.2 / 0.0; FUN_8007B1E8 (20 callers 0x80035C34.. = region / spool unpack, while standing)
  1.2 / 0.0. Same in both: FindSurface 0x8001EEB4 9 / 9, object renderer 0x80030474 2.4 / 3.1, 0x8003DF94 2.4 / 2.4;
  subdivision loop 0x80030C20 1.5 / 5.6 (Miami subdivides MORE). The Chicago-only extras add up to ~16 % = the gap.
- **Ranked levers (expected gain, all Chicago / D2-gated, no visual change unless noted):**
  1. Car-car pre-check per pair (C82 widened it to 2000 for ALL pairs: every traffic pair within 2000 now runs the full
     SAT): window 1201 unless a pair has a big box (special / player PBZ) -> ~3-5 %.
  2. Traffic cost: per-car matrix + physics with 6 resident models / more cars (FUN_8001B380, GlobalTimeStep): measure
     cars-in-play Chicago vs Miami first; D2 traffic density as the reference -> 1-3 %.
  3. D2 car draw: far cars to the low model at D2's distance (D2 models 118-131 polys vs D1's) -> 1-3 %.
  4. Spool work while standing (FUN_8007B1E8 callers): find what re-spools each frame (C30 carry / S4 / area) -> ~1 %.
  5. C68 stub (0x80011924, per object): a cheaper check -> ~1 %.
  6. Near tiles (FUN_800277D4): Chicago's near-tile range -> ~1 %.
  Prep for 1 (offline, 24.10.): two places widen pairs for ALL cars: the broad phase margin (FUN_8001FAFC: 90 + PBS high
  half = player reach + the special's s_spc_reach, added to every car's AABB, R35) and the pre-check window (C82: 2000).
  Per-pair / per-car versions need a model check (car+2 == 5, car == player) = ~11 cave words each; free cave words today:
  ready_cb 3, S1 3, DCAVE1 5, DCAVE2 3 (no contiguous 11). Options: (a) the margin / window computed once per frame by
  the plugin into gp words is NOT enough (per car); (b) free a cave by compacting a patched block (e.g. the C68 stub = lever 5,
  or FUN_8001FAFC's own loop, rescheduled in place like C37); (c) a new dead-string cave (cave_audit + ghq xrefs + immediates).
  7. Only then D2-style map rendering (per-object draw distance by size, D2 tile path): visual risk, gated; the ruled-out
     list stays (lightpvs adopted, subdivision none rejected, tile merge dropped, PVS encoding exhausted, tighter margins = pop-in).

## C88 / C89 cheats (Infrastructure 24.10., build-test 49c8578d / 07c68845; design: design_c88_cheats.md)
- Words (zero block): INFM 0x800933C4, NGHT 0x800933C8, SPD2 0x800933CC, 0x800933D0 = C89's dummy; LOW GRAVITY = Driver 1's
  hidden 0x8009D8E8. All off = Driver 1 unchanged.
- **Low gravity (exe):** 0x8001D7D4 -0xAAA -> -0x1555 (1/2 g when 0x8009D8E8 != 0). Runner cannot hold a car in the air
  (a pose lands within a frame): the feel is the user's check.
- **Super speed (plugin):** SPD2 -> THRS = 2 x (Chicago's D2 value, or Driver 1's 4096 / Miami choice-3 4864): best speed
  12.1 k -> 20.5 k units / s in 8 s. Reverse thrust doubles too. PS1: the menu code writes THRS.
- **Infinite mass (exe):** GlobalTimeStep's mission-rule block 0x8001C9FC..0x8001CA4C rewritten without nops into flag
  arithmetic (a2 / t2 &= mission rule, and with INFM &= car id != 0): the player is never moved by a car-car impulse.
  Needs C82's TW (it sets t1 = 0x37 itself; the old 'addiu t1, zero, 0x37' is gone). Bus rams: player yaw 0 / 0 (/ 105
  one miss) vs 12 / 59 / 7 without. No impulse doubling for the other car (no space; D2-like enough).
- **C89 (exe):** the 3 game-start resets (0x80024838 / 3C / 48) store into the dummy word: Survival (type 0x13 confirmed)
  keeps Invincibility / Immunity (runner survival_cheats PASS). Unconditional: cheats are opt-in anyway.
- **Nightmare: blocked on a design question.** Driver 1 has only 4 cop data slots (0x800C4E38 + n x 0x7A8, FUN_80063B74
  allocates, loops over 4): pursuit needs a slot, so "every car chases" = more slots (~2 KB RAM each + every 4-loop) or
  "4 civilian-model pursuers at all times" (force cop spawns, keep the civilian model, felony on). The host test that only
  set AI state 4 does not chase (17-21 'pursuers', none closing in).
- **Nightmare 58 B estimate (every car chases; no build yet):** cop slots 0x800C4E38 + n x 0x7A8 (1960 B), 4 of them
  (0x800C6CD8 end); AI records 0x80098950 x 0x50 (25), byte +5 = slot + 1. Sized for 4 (ghq + lui/addiu scan, 13 base
  sites): alloc FUN_80063B14 / 80063B74, init 80063C60, clears 80016CE4 / 80064A64 / 8005474C / 800635C0 (to 0x800C6CD8),
  4-loops in 8005474C (3), 800635C0, 800641C0, CheckScenaryCollisions (end constant +0x1960), index use 8001638C. Slot use
  in Miami pursuit (2-3 cops): +0x4..0x3A0 header + route words, +0x758..0x7A8 state; 0x3A0..0x758 stayed zero. Guest
  share of the slot functions < 1 % with 2-3 cops (only 0x80061C68 0.45 % in the cop range). RAM: 20 slots = +31 KB,
  25 = +41 KB; free under the stack (S4): Miami 77, SF 80, LA 72, NY 14 KB, Chicago / Havana already host-only.
- **"cheats 2" build (build-test 56bcef4a, user 62 / 63 B):**
  - Menu layout 2 (plugin cheats_vblank): page 1 = CREDITS .. STILTS, ANTIPODEAN (row 6 as a proxy of 0x8009D8EC), PAGE 2
    (row 7); page 2 = LOW GRAVITY, INFINITE MASS, SUPER SPEED, NIGHTMARE, PAGE 1 (rows 1-5, row 0 + rest hidden, room for
    2 more). True values in the plugin while the screen is up, written back on leaving. Hidden rows = unlock word -3
    (driver_gameplay.c unlock-all now leaves -3 alone). Page rows have no On/Off: runtime patch of the FRONTEND draw
    0x801C765C..88 (psx_mod_write_code_word, checked word by word): skip On/Off when the unlock entry +4 is negative
    (page rows -1; cheat rows forced >= 0, Driver 1's NULL row 6 has -1 there). Row 6 / page rows jump to the no-op.
  - Cop slots (exe c88_slot_patches, CHI_C88_SLOTS=0 off): 24-slot array in plugin memory, address from zero-block words
    SLOT0 / SLOT1 / SLOTM / SLOTE 0x800933D4..E0 (SLOTM = base - 0x4E38: it replaces 'lui 0xc' where the addiu is kept;
    a first build had base - 0xC4E38 there and Driver 1's patrol cops never started a chase: runner cops_d1 vs a build-dev
    copy found it). 14 adjacent 'lui 0xc / addiu' pairs -> 'lw / nop', 2 kept addiu, level clear / minimap / lost-pursuit
    loop ends from SLOTE, seen / init / spot loops 4 -> 24; allocators, FUN_80063AA8 and the drop loop stay on slots 1-4.
    Write trace on the old area: no writes. cops_d1 PASS (Driver 1's cops chase in slots 1-2 as on build-dev).
  - Nightmare (plugin, host; CHI_C88_NIGHTMARE=0 hides it): moving traffic (states 2 / 3) gets slots 5.. set up like
    FUN_80063B74 + FUN_8001548C, state 4; cops on, felony >= 0x293, 'seen' kept; NY at most 8 slots; released when off.
    Newtown needs no police model: the chasers keep their own models and its cop cap 0 keeps the director's cops away.
    Runner nightmare (standing FPS off -> on, pursuers): Miami 28.0 -> 17.7 (21), Chicago 24.9 -> 15.8 (21), NY 24.0 ->
    19.1 (8, cap), Newtown 29.9 -> 20.3 (17); they close in, 20 s drive alive, release PASS. Cost = the pile-up (car-car
    SAT 0x80067A44 4 %, scenery 0x8004AC88 4 %, more cars drawn), not the slot code.
- **"cheats 3" (build-test 8fbaca31, user review of cheats 2):**
  - Chasers did not chase like cops: the pursuit handler 0x80065424 re-plans the route (jal 0x8006466C) only when
    'frame % 4 == slot - 1' (0x80066044..50): never for slots 5... Exe: '(frame & 3) == (slot - 1) & 3' (0x8006602C..4C,
    same for slots 1-4 with frame >= 0). Plugin: chasers get record +8 = 0 (lane-traffic flag; Driver 1's cops 0 at
    spawn, back to 1 on release). Runner nightmare_vs_cop (Miami, one Driver 1 cop vs the chasers in the same chase):
    route active 0.51 vs 0.39 of samples, top speed median cop 625 k vs chasers 1156 k: PASS. Model / palette stay
    civilian (user OK); no other cop-only branch found in the handler (it reads only the car's state words).
  - Cost: the chasers now reach and ram the player: Nightmare standing FPS Miami 28.0 -> 9.4, Chicago 24.9 -> 7.8
    (driving 8.5); guest: car-car SAT 0x80067A44 13 %, pair loop 0x8001C3D4 6 %, route grid 0x80061C68 5 %.
  - Invincibility vs flip wreck (exe 0x80023440..60, CHI_C88_FLIP=0 off): FUN_800230B0 counts frames with the player's
    up vector y (0x8009B0B0) < 100 in 0x80096920 and sets damage = max + 100 after 180; with 0x8009681C != 0 the counter
    is reset instead. Runner flip_wreck: on the roof 10 s with Invincibility, damage 0; without it wrecked (241 frames).
- **Roadmap 65 prep (switches, defaults off; build-test c976365a):** CHI_C88_NM_CAP=n = at most n slots in use, the
  nearest traffic cars first; CHI_C88_NM_REPLAN=n = re-plan every n frames while Nightmare is on (exe mask word RMASK
  0x800933E4 | 3 in the handler, 0 = Driver 1's 4). Chicago standing / driving FPS (off 25): no cap 7.8 / 8.6, replan 16
  7.1 / 7.2 (no gain: the route search is not the cost), cap 12 11.3 / 11.8, cap 12 + replan 16 11.9 / 12.1, cap 8 14.2 /
  16.5. The cost is the pile-up of cars that really reach the player (car-car collisions), so only the cap helps.
- **C92 "Uncap GPU usage" (Infrastructure 24.10., build-test 5286ceda; design chicago/design_c92_uncap.md):**
  - Runtime (psxrecomp, not upstream: own port, the upstream cpu_overclock source is not on this machine): Q16 scale
    g_psx_oc_q16 (+ exact remainder g_psx_oc_rem) on CPU cycle charges before they reach psx_cycle_count:
    psx_advance_cycles (after the batch merge; new psx_advance_cycles_scaled = the old body), the interpreter's
    per-instruction fast path (dirty_ram_interp.c interp_cyc_step) and the load charge (memory.c psx_load_charge_cycles).
    Device catch-up in psx_devices_service_to_now is not scaled, so vblank / timers / CD / SPU / DMA events keep their
    real schedule. 65536 = off: one extra compare per charge. API psx_set_cpu_overclock_percent / psx_mod_set_cpu_overclock
    (mod_plugins.h), clamped 100..400. Backup of the six touched files: scratch c92_backup.
  - driver.personal feature "uncap-gpu" (Mods: "Uncap GPU usage", group Performance, default off), integer option
    cpu_percent 100..400 step 25, default 200; activation plugin driver.uncap-gpu (driver_gameplay.c), next launch.
    Runner: RUNNER_UNCAP=<percent> enables it in a test copy; plugin test aid CHI_TEST_OC=<file> sets the percent live.
  - Measured (off -> 200 %): Chicago fps_drop_2 standing avg 26.2 -> 29.9 (all 4 headings 29.9-30.1), driving 29.0 ->
    29.9; Miami start 27.9 -> 29.9; Nightmare (12 chasers) Miami 10.4 -> 23.7, Chicago 11.6 -> 24.4.
  - Checks: out_of_tape PASS with 200 % (no hang, no stall dump); replay recorded at 200 % and watched as Quick Replay at
    100 % (uncap_replay MODE=on_off): AI positions at the same game frames within 0-450 units, like the 100 / 100
    reference; cops_d1, nightmare_start, feather PASS with it off (default path unchanged).
  - Host-only by nature (an emulator setting); off = the PS1 reference for M8.
- **C92 EMU % (user 67, 25.10.):** host throughput is ~96-101 M guest cycles / s on this PC at any overclock (runner,
  unpaced; runs 16:40-16:53 overlapped the user's probe session). At 200 % the game also spins its frame wait
  (FUN_8002360C 0x80024254: jal VSync(-1) until count - last >= 2) with 2x the cycles per vblank, so the idle part of every
  frame costs host time: Chicago fps_drop_2 EMU 285 % (100) / 201 % (150) / 149 % (200), Miami 258 / 187 / 150; no
  warm-up in a 12 s series from the level start (152, 150, 150 ...). PSX_IDLE_SKIP=1 does not catch this loop (VSync does
  stores + GPUSTAT / timer MMIO): 146 %. Dev mode costs ~12 % (153 -> 172 % at 200 %). Estimate with the wait skipped:
  Chicago ~178 % (work ~1.8 M cycles / frame), Miami ~260 %.
- **C92 frame-wait skip (25.10.):** with Uncap on, VSync(-1) called from the main loop's frame wait (
  VSync 0x80079B00, ra 0x8002425C, count - last < 2) advances guest time to the next IRQ the guest can observe
  (psx_skip_to_next_vblank_if_overclocked: i_stat & i_mask clear, psx_idle_cycles_to_next_observable_event, <= 1.2 M);
  a first version jumped straight to the vblank and skipped CD / timer IRQs in between: crash (DISPATCH FATAL
  misaligned 0x01010101) and the replay tape stopped (out_of_tape). Hook: driver.personal plugin driver.uncap-gpu
  (function-entry plugins need an id that is also registered as activation / vblank, else "trusted plugin is
  unavailable"); game.toml mod_function_entry_funcs + 0x80079B00. EMU headroom at 200 % (idle machine): Chicago 173 ->
  234 %, Miami 174 -> 237 %; uncap_replay (200 % recorded / 100 % replay), out_of_tape, cops_d1, nightmare PASS.
- **C88 Nightmare r3 (user 25.10.):** every traffic car becomes a chaser at its spawn: entry hook on FUN_8001B720 when
  called from the spawn tail (ra 0x80015FAC, a1 = 1); nightmare_take() = the old conversion (slot 5.., state 4,
  record +8 = 0). No cap on PC (CHI_C88_NM_CAP=n optional; NY's PS1 limit in the host-only table). Specials chase too;
  a chasing special is released when another special is pending (the player entered another special's region) so it
  despawns like traffic and the swap can happen; the specials' model-5 scan now covers all 24 AI cars. Siren and
  lights stay off for traffic models (Driver 1 ties both to the police model: AddIndicatorLight model 1 + state 4,
  FUN_8004CA5C siren channel model 1); chasers use Driver 1's pursuit engine sound (revs pitch). Runner
  nightmare_start: 20 chasers within 3 s, 20 of them taken at spawn; nightmare_vs_cop, cops_d1, nightmare_felony PASS.
  Police cars: chasers no longer count in Driver 1's cop count 0x80097764 (set to the cops in slots 1-4 every running
  frame), so the director keeps spawning real cops (nightmare_start: a police car in pursuit). The chasers' revving
  engine is the bank-0 engine loop pitched by the car's revs (FUN_8004CA5C loop 2, cars with the pursuit flag car
  +0x12E, which the pursuit handler also uses for its speed boost 0x80065FBC): the cars' own engine, not police audio;
  the siren (loop 1) needs the police model. build-test f1425073.
- **Felony (user 66):** with Nightmare on, felony is kept at 0x1000 on every running frame (was set once per level);
  runner nightmare_felony (Miami, back to the menu, Chicago) PASS. Note: Driver 1's attract-demo reset also clears
  NGHT (as it clears its own cheats) if the title screen sits until the demo starts.
- **C90 (cheats 3 review, build-test adb53ffb):**
  - Probe env (probes.json "env") is used only for the converter / package build (publish_playable); runtime getenv
    switches never reach a probe. Runtime choices must be defaults (or package data).
  - Nightmare wrote felony / cops-on / 'seen' every vblank, also on the loading screen and in the pause menu: now only
    when the game frame counter 0x800970D8 moved; a new level / restart (counter smaller) sets felony 0x1000.
  - Default cap 12 (CHI_C88_NM_CAP=0 = none), nearest cars first; wrecked cars (damage +0x17C >= 0x4651) are skipped
    (the pursuit handler frees such a cop at once, 0x8006550C: re-assign churn); the loaded regional special (model 5)
    is never a chaser (its body is drawn only inside its texture area: 'bus without body').
  - Chicago chase audio: the car-car crash (bank 0 sample 0, SPU 0x1010, GlobalTimeStep 0x8001C960 -> FUN_8004D7E4)
    keyed ~50 / s by the pile-up, peak-limited; NM-off samples otherwise present. Pause: 0 key-ons, silent (runner).
  - Main-menu strip under the police car: also on build-dev after quitting a level (older, not the cheats work).
- **C91 FEATHER:** INFM word 0x20 = INFINITE MASS, 0x100 = FEATHER. c88 block rewritten (gp-relative mission type,
  mission types 3 / 6 = Driver 1's rule only): feather swaps the two ids (mask = -(word >> 8)) before the same rule,
  so the car meeting the player keeps its motion; tail in S1 FTHR1 (3 words) + the pack-B string tail (4 words; pack
  rewritten: bits 4 LOWG, 5 / 8 from the INFM word, 6 NGHT, 7 SPD2). Unpack 'andi 0x120'. Offline emulation of the
  block: 0 mismatches over mission types x ids x modes. Runner feather: bus dv 0-2687 (off 380-490 k), player dv 0.6-0.9 M
  (off 0.1-0.5 M).
- **Cop slot size (60 B question):** route builder 0x80061F5C (called by the search 0x80063114, heap 0x800C43B4 max 502,
  grid 0x800C039C 64 x 64 x 4 B, cell 1500 units) writes <= 64 nodes x 0x1C at slot +0x58..+0x758 (limits 0x40 / 0x41 at
  0x80062058 / 0x80062118 / 0x80062178); fixed fields +0x0..0x58 and +0x758..0x7A8. Worst case = the full 1960 B; cap 32
  nodes = 1064 B, cap 24 = 840 B (needs the tail offsets moved). 20 / 25 chasers: full 31 / 41 KB, cap 32 17 / 22 KB, cap
  24 13 / 18 KB vs free Miami 77, SF 80, LA 72, NY 14 KB. Police-only chasers need the same slot each (no saving).
- **Probe build 079891a8:** NIGHTMARE row + host test only with CHI_C88_NIGHTMARE=1 (default hidden: page 2 = INFINITE
  MASS / SUPER SPEED). The old host test (AI state 4 without a cop slot) would run the pursuit handler on 'slot -1'
  0x800C4690 = other data: never enable it outside a test.
- **Nightmare slim variant (shared route pool) ruled out:** a cop slot holds its own route: FUN_80063114 (route search
  over the shared 64 x 64 grid 0x800C039C, origin gp 0x80097748 / 4C) builds a linked node list inside the slot (+0x58
  head, nodes in +0x60..0x758, absolute pointers, +0x14 / 18 / 1C indices); the pursuit handler 0x80065424 (state 4 in
  the AI jump table 0x8008539C, slot = 0x800C4690 + 0x7A8 x record byte +5) follows it every frame (calls 8006466C,
  80064C90, 80064DEC, 800660D8). Sharing slots = a new route search on every hand-over, and swaps break the pointers.
  Patrol cops run the spot check FUN_80064360 every 4th frame by slot (FUN_80064FE0). Proposed instead (Strategy):
  road chasers via the junction choice FUN_80016F0C (random pick 'rand % count' at ~0x800175A0 -> exit toward the
  player; record +0x30 dir, +0x2C next road; car i struct 0x8009B230 + i x 0x18C, x +0xC8, z +0xD0) + the 4 real slots
  handed to the nearest chasers.
- **Menu pages (plugin cheats_vblank, build-test 07c68845; CHI_C88_MENU=0 off; runner cheats_menu PASS + sheet):**
  on the Cheats screen (FRONTEND screen id 0x801CDE5C = 6) row 6 (Driver 1's unused "NULL" row, no-op jump 0x801C74D4,
  draw reads 0x8009D8E8) is unlocked and labelled LOW GRAVITY; cross toggles 0x8009D8E8. Right = page 2: row count
  0x800967D8 8 -> 4, row 0 "DRIVER 1 CHEATS" (its jump entry 0x801C0728 -> the no-op meanwhile; cross / Left = back),
  rows 1-3 INFINITE MASS / NIGHTMARE / SUPER SPEED drawn and toggled through Driver 1's words 0x8009681C / 20 / 0x8009D8DC
  as proxies (saved on page entry, swapped back on leave). Leaving the screen restores names, count, jump entry. Ruled
  out: hiding rows by unlock word 0 (no effect on this screen; driver.personal's unlock-all likely keeps -2) and '>' / '<' in labels (not
  in the menu font). Labels live in guest memory from psx_mod_alloc_guest_memory (host-only; M8: strings in FRONTEND's
  free tail + the same table writes from the overlay).
- **Replay header (exe, CHI_C88_REPLAY=0 off):** Driver 1 saves cheats in 0x80097644 bits 0-3 (packer in MCARD.BIN at
  overlay +0x2074, keeps the other bits of the old word; load path 0x80024868 restores). Bits 4-7 = LOWG 0x10, INFM 0x20,
  NGHT 0x40, SPD2 0x80. Pack: 0x80024F1C (called by every game / replay / demo start) jumps to a stub in two dead printf
  strings (primbuf 0x80010954, its reference was overwritten by CAVE; cellsize 0x80010464, block skipped by the 3000
  patch) that writes bits 4-7 from the words (sltu, so any nonzero = on) and returns to 0x80024F24. Unpack: the load
  block 0x80024868..0x80024934 rewritten gp-relative (same stores, same order) + 4 stores (bit values, every reader tests
  != 0). Demo reset 0x80024D0C..48 also zeroes the 4 words. Checks: runner replay_header PASS (bits 0x90 at game start,
  0xB0 with INFM too), survival_cheats PASS; offline emulation of old vs new block (scratch c88_emu.py): 3000 random
  headers, stores identical + the 4 new words, demo reset identical + 4 zeroes. Memcard save / load round trip not
  runner-checked (the MCARD screen shows an empty dialog headless): probe item. Quick Replay does not use the header.
- **High scores (exe, CHI_C88_SCORES=0 off; build-test 93a6fdc8):** FUN_8006C964 (game start) skips the record (flag
  0x80096F00 = 0 at 0x8006CA80) when 0x8009D8DC / E0 / E4 / E8 is set (Driver 1: rear wheel, minis, stilts, low gravity;
  Antipodean, Invincibility, Immunity do not block). 0x8006C9FC..CA34 (4 x lw / nop / bnez) became one OR over those 4 +
  INFM / NGHT / SPD2 and one bne (same target and delay slot; t0..t2 dead there). Runner cheat_scores PASS: Survival
  restart without cheats writes the flag from 0x8006CA74 (= 1), with SUPER SPEED from 0x8006CA80 (= 0).

- **C95 cheats 5 crash = CD sector lost after a rewind (Infrastructure 25.10.; runtime cdrom.c):** the user's probe
  restored a rewind / state (log "reapplied mod plan ... after savestate restore", cycle counter 100 M back at frame
  ~61085; rewind = F8 or Select+R3 (keyboard Right Shift+Y), state menu F7 / Select+R1; settings.toml rewind = true).
  The runtime's post-restore CD boost (cdrom_savestate_boost_vblank, 180 host frames) cut read_delay to <= 4096 at EVERY
  frame: sector 330141 arrived 2738 cycles before a vblank, 330142 followed 4095 after it (6833 later), before the
  guest had read 330141 (INT exposure alone is 5000) -> page 0xF's buffer one sector off -> Driver's texture-page
  loader (FUN_800516E4) read a CLUT count 0x33FDAAAA and wrote CLUT ids over 0x80086F30..0x8008E8DC (incl. libgpu's
  table 0x8008E8D0) -> LoadImage jalr 0x7F216 = DISPATCH FATAL. Fix: the read_delay cap only once at the restore and
  only with no data INT outstanding (cdrom_apply_savestate_delay_caps clamp_read); runtime diff section "C92 / C94 /
  C95". Runner cd_restore (restore + Chicago load x3) PASS. The unpaced runner did not reproduce the per-frame clamp
  (the boost runs per presented host frame). C81 (probe optimisation 2 hang): its dump has cycles ~69 s behind the
  frame count = many rewinds / state loads in that session, so the same cause is plausible (no log kept to prove it).
- **cheats 5 fixes (Infrastructure 25.10., build-test; runner tests in brackets):**
  - C96 popping polygons: world_renderer (0x80030E64) and its subdivided path (0x800315D8) take the OT slot as
    (sum of 4 vertex depths >> 3) & 0x3FFC; past avg depth ~32760 it WRAPPED to a near slot (far buildings drawn over the
    street; Extra draw distance reaches it, D1's corner cells too). Clamped to 0x3FFC (caves 0x80094890 / A8, the add
    after the andi moved into the cave).
  - C96 near cars low-poly with Nightmare: FUN_80014A8C draws cars nearest first and switches to the low model when
    (buffer start + 0x1E000 - pointer - 3000) - remaining cars x 0x800 < 4000 (stops at < 0): it assumed Driver 1's
    buffer size. Now minus the size from XPBN 0x80093428 (0x80014C54 / C5C / EF4). Nightmare / Hell levels are set up
    with the two 0x50000 aperture buffers (dp_big_prim_buffers, shared with Extra draw distance), object / tile limits
    stay Driver 1's; all limit words follow the buffers the level really uses (0x800BDFAC / 0x800BE02C), never the
    requested ones. The 1.5x car LOD is off while Nightmare / Hell is on.
  - C97 Quick Replay ended early / damage in the replay: a replay sets 0x80096899 and Driver 1 then skips the whole
    player block at 0x80025A38 incl. INVINCIBILITY's damage reset -> the replayed car was wrecked (replay over). Replay-
    only cave 0x800948C0 does the reset (same stores) and skips as before (replay_cheats: reaches the recorded end).
  - C98 menu strip / black box: specials_vblank returns while FRONTEND is resident (no slot re-upload in the menu).
  - C99 HELL (page 2 row, word 0x8009342C): pursuers never wreck (0x8006549C: damage reset before Driver 1's 0x4651
    check), drive value car+0xF0 x2 (0x80065FDC) and the rubber-band target speed slot+0x24 x2 as read (0x80065EF8);
    caves 0x80094910... Runner hell: 21 pursuers, max damage < 0x4651; top speed on the Miami causeway +41 % vs
    Nightmare (f0 3x): something else limits AI top speed (tried: pursuit grip pair s4 / fp x 2 at 0x8001E408, no gain, reverted; scaling 0x12E in FUN_8001DFF4 x
    0x2D / 0x37 / 0x44 >> 5). Not in the replay header (memcard replays lose it); the attract demo does not clear it.
  - C99 v3 (Polish's static analysis of the cop driver block 0x80065BD0..0x80066000): with HELL both rubber bands are
    skipped (A 0x80065D0C: within 4000 units target = player speed + 10; B 0x80065E94: blend toward the player's speed),
    the drive value x 2 (x 4 where Driver 1 halves it for car+0x12E == 1), target x 2; caves 0x80094910..0x800949C4
    (labels). Runner hell, causeway, standing player: pursuer |v| p50 777k / p90 967k vs Nightmare 144k / 500k.
  - C102 car shadow: Polish's '3 x 3 grid' was the near ground band (FUN_800287A4). The shadow is ONE PolyFT4 (op 0x2E,
    CARSHAD uv, a static primitive at 0x800A216C + buffer x 1000 + car x 0x28) written by FUN_8002ADEC (called from the
    car draw FUN_8003A698, ra 0x8003AE9C) through the car's 4 corner points car +0x88 / 0x98 / 0xA8 / 0xB8 (world x, y,
    z ints, also the physics' points; quad P0 P1 P3 P2). Exe: 0x8002AE30 -> cave 0x80094708 copies car +0x88..+0xC0 to
    SBUF 0x80093440 and adds SHD[car] (0x80093480 + 16 car: 4 x (dx, dz) i16); the routine reads the copy. Plugin
    shadow_vblank: for the Chicago special (model 5) the offsets stretch its quad along its own axes to the .sps.bin
    half length / width (package spcshadow_day/night.bin); 0 = Driver 1. Runner shadow_bus: bus quad 378 x 1214 ->
    offsets +-340 along, +-31..41 across (target 442 x 1722).
  - C104 (cheats 7 'cars only very close after NY -> Chicago'): with the _xd level the draw decode went into the 27 x 27
    buffer only, so Driver 1's 19 x 19 buffer 0x800A80C4 kept the previous city's PVS; FUN_800398B0 (car visibility for
    the car draw list FUN_80014A8C) reads it -> cars culled by a stale grid. The draw cave now copies the middle 19 x 19
    into 0x800A80C4 after the decode (shared copy loop with the cops' path). Runner city_switch: NY -> Chicago, the
    19 x 19 equals the 27 x 27's middle.
  - C105 Antipodean 'on by itself' (user steps: Invincibility, page 2, Hell, back, Free Ride Miami): screen id 6
    (0x801CDE5C) is any row-list screen; on Take a Ride's city list the plugin took it for the Cheats screen, re-laid
    rows and its proxies moved Hell's value into LOW GRAVITY's word (= page 1's ANTIPODEAN proxy: shown On, low gravity
    in the level). Cheats screen now also needs the menu definition pointer 0x801CDC8C == 0x001C0020 (city list
    0x1C0038, others 0x1C000C / 0x1C0028). Runner anti_check with the user's steps: LOW GRAVITY / ANTIPODEAN stay 0.
  - C106 HELL in the replay header (bit 9): pack A -> cave 0x8009479C ORs it into t1, pack B clears bits 4-9 (mask
    0x3F0); the load block's closing jal 0x80024F1C -> cave 0x800947B4 (HELL = header & 0x200, then the pack); the
    attract-demo reset zeroes HELL (cave 0x80094634 via word 8). replay_header 0x390, replay_cheats with HELL PASS.
  - C107 rewind / state loads with our add-ons (user decision B): hangs after a restore with Nightmare / Hell / Extra
    draw distance = those levels draw into the mod GPU-DMA aperture (big primitive buffers), which save states did not
    carry: RAM / OT came back from the state, the aperture from 'now' -> the GPU chain ran through stale primitives,
    DrawSync never returned (runner rewind_loop: Miami round 0, Chicago round 3). Runtime: BS_SEC_GDMA 0x13 = the used
    aperture (memory.c psx_mod_gpu_dma_snapshot / restore, boot_state.c; runtime diff section C107). Plugin: a restore
    (VBlank counter 0x80095250 going back) re-derives the host caches (area switch tracker, the special's tpage / CLUT
    build, Nightmare's frame gate). rewind_loop (12 x save / drive / load, Invincibility): Chicago + Miami with
    Nightmare, Chicago Extra draw + Hell, NY Extra draw + Uncap: no hang, game frames advance after every restore.
    Seen meanwhile: in long drives Nightmare's pursuers thin out (19 -> 3 in Miami over ~50 s) also WITHOUT any save
    state (open, Nightmare).
  - C108 Nightmare thinning (runner nm_thin, Miami: 21 -> 2 pursuers with the player boxed in): chasers Driver 1 wrecks
    (damage >= 0x4651, the pursuit handler frees them) stayed as traffic next to the player, the 24 AI records stayed
    full, nothing spawned. The plugin now removes such a wreck like Driver 1's despawn FUN_80017C50 (record state and
    lane flag 0, index back on the free stack 0x80099AF0 / count 0x80096FC4) when it is out of view (behind the
    camera: depth through 0x800BBE84 < 0, or > 15000 away) after 2 s, or after 10 s anyway; the spawn hook makes the
    fresh car a chaser. Wrecks stay wrecked (never-wreck = Hell). nm_thin 60 s: Miami 18-22, Chicago median 15-22.
  - Hang seen once in runner nightmare_vs_cop (26.10., Miami, Nightmare, player standing): same signature as the
    cheats 7 user dump (in exception, i_mask 0, the guest in libgpu's GPU-timeout loop 0x800764C4 / VSync inside the
    interrupt handler, no vblank delivered; starvation watchdog exit). Not reproduced in 3 x 240 s (runner hang_hunt
    with PSX_STARVATION_TIMEOUT_US=0 keeps a hung instance for GPU / DMA / IRQ state). The 'huge semi-transparent
    quads' suspect is gone (they were a ring-decode artefact, see popping polygons below); open.
  - Popping polygons, GP0-ring evidence re-checked (Infrastructure 26.10. 23:xx, scratch pop_src.py): two artefacts in
    the ring analysis. (1) The ring's "pc" / "ra" are the CPU's LAST STORE / return address at DMA time (DrawOTag runs
    while the cell walker FUN_8002C8FC already builds the next frame), not the prim's writer: use the entry's "src"
    (prim address). (2) psx_gpu_frame's GpuState starts at draw area 0,0-1023,511 / offset 0,0; a ring frame that
    starts mid game frame (no E3/E4/E5 before the prim) is decoded against that default, so a normal prim that runs
    off the screen bottom counts as 50-100k "visible" px. The tpage 74 semi quads (uv 0x70-0x8F x 0xC0-0xFF) are car
    shadows (FUN_8002ADEC, prims 0x800A216C + 1000 x buffer + 0x28 x car): mostly the player's own, every frame, its
    rear corners off the screen bottom (y clamped 1023): ~4k px really on screen with the real draw area. Also, comparing
    neighbouring RING frames (vblanks) instead of game frames, and keying on uvs (subdivided ground changes them every
    frame), makes everything "blink". With src + real draw area + game-frame neighbours: Miami Extra draw 630 game frames
    and Chicago 463 game frames show no visible big one-frame polygon; GTE-saturated (+-1024) prims exist (near poles,
    tpage 30, 2047 px tall), and the GPU's size limit drops them as on a PS1. So the QA-POP counts (vanilla too) do not
    show the user's pop; a user F9 snapshot at the moment of a pop is needed. Shadow code has no near-plane check (4 corners
    projected, no SZ test): a car beside / behind the camera would give a garbage shadow quad (not seen in these runs).
  - The user's cheats 5 "distortion" snapshots (dev/dumps/probe_cheats_5_20261025-2022*..2033*, screens only: the prims
    were in the GPU-DMA aperture, not in ram.bin): (a) 202203 Chicago: a pavement strip drawn OVER the player's car =
    sort order, the OT slot wrap fixed by C96 in cheats 6; (b) 202242 / 202857: red semi-transparent triangles on the
    bottom screen edge = Driver 1's own pursuer indicator (FUN_80055820 -> FUN_800555F4: for each AI car in pursuit,
    state 4, in a cone behind the player, a 40 x 30 PolyF3 at y 210..240, x = 256 + bearing, brighter when nearer;
    loop over 22 records). With Nightmare every car is a pursuer, so many red triangles pop in and out at the bottom:
    the likely "popping polygons" of cheats 7 (original feature, multiplied). Ring-confirmed (Miami Nightmare, 473
    frames, src in the primitive buffers, words 0x22RRGGBB / y 0xF0 / 0xD2).
  - C113 shadow near-plane guard (exe_patches c113_patches, default off): 0x8002B050 -> cave 0x8008A3C0 (zero padding
    after the 0xFFFF-terminated u16 list at 0x8008A2A0, seeded): the shadow is skipped when a corner SZ < SNEAR
    (zero-block word 0x80093438, gp -0x3338). driver.chicago writes it every vblank from CHI_SHADOW_NEAR (default 128 since 27.10. on Strategy's go; 0 = Driver 1).
    H = 256, so 128 = the GTE divide-overflow bound (a corner at / behind the camera plane). Miami Nightmare with 128:
    player shadow kept (199 of 218 frames vs 204 of 226 off); a car shadow with saturated corners in 204 frames (off run)
    gone; shadow_bus, nightmare_start PASS. PS1-native (exe code + a RAM word).
  - C115 (cheats 9 user: Chicago music much slower after Hell -> a Driver 1 map -> exit -> Chicago): real-time speed, not
    the song (runner music_rate: song 8 and tempo identical; the headless copies always have headroom). Cause: the C111
    adaptive Extra-draw CPU speed carried the previous level's value (Miami Hell chase: up to 400 %) into the next level,
    and an overclock the host cannot hold slows the whole emulation (music = EMU < 100 %, seen before on the laptop).
    driver_gameplay.c: (1) s_xd_pct back to 200 when the game frame counter 0x800970D8 goes back (new level / restart /
    rewind; log "new level: Extra draw CPU N -> 200 %"); (2) host guard overclock_guard(): the overlay's EMU % (once a
    second) < 97 while overclocked -> CPU ceiling = current - 50 (min 100), 10 s at >= 99 % -> +25 (max 400); applies to
    Uncap and Extra draw alike (log "CPU ceiling now"). Desktop: EMU 99.7-100 % before and after (not reproducible here).
  - C116 Mods feature "Developer recording tools" (driver.personal dev-tools, default ON): its activation calls
    psx_mod_request_dev_tools() (TCP debug server, recorders, freeze heartbeat file, GP0 history); Developer Mode no longer
    does. Off: "psxrecomp: developer tools off", no port, heartbeat file untouched, F9 / dump.request -> "snapshot skipped"
    + OSD hint. Test copies keep them via --debug-port. Runtime diff section C116 (heartbeat_thread and gp0_ring_record
    gated on g_psx_dev_tools; main.cpp's dangling else that hid the "off" line).
  - C109 hang mechanism (both dumps, 27.10.): the interrupt handler's stack (libetc ISR stack 0x80093xxx..0x800942A8,
    cpu sp 0x80094268) holds FUN_75FA4 (libgpu queue, run from the GPU-DMA-end callback, I_MASK 0 while it runs) ->
    queued StoreImage FUN_75960 (Driver's day-time sun-flare check FUN_80046E44 reads a VRAM rect into 0x800B722C every
    frame; s2 = 0x000B722C in both dumps) -> its wait for GPUSTAT bit 27 'ready to send VRAM' (ra 0x80075B18) -> libgpu's
    timeout FUN_764C4. Inside the handler VSync does not advance, so only the iteration counter (0x8008EA58, limit
    0xF0000 at 0x80076508) ends the wait: 362k / 450k iterations done when the 4 s starvation watchdog fired. So the
    trigger is a C0 (VRAM -> CPU) command that did not start a read (vram_read_active 0). Not reproduced: hang_hunt
    13 x 240-300 s (rewind every frame included; runner copies have no settings.toml = rewind off by default!). build-wip
    probes (memory.c, C117): CPU GP0 word while a linked-list DMA feeds GP0, and C0000000 arriving while the GP0 parser
    is inside a command (pixel words of LoadImage's CPU remainder loop 0x800758E8 excluded): 0 in 12 min.
  - C109 fix set (build-wip 5eab5fa6, next probe after the cheats 10 review; Strategy go A + B):
    (A) exe_patches c109_patches: 0x80076508 lui v0, 0xF -> 0x1: libgpu's wait helper gives up after 0x10000 iterations
    instead of 0xF0000. Normal play never iterates there (runner gpuwait, Miami + Chicago, Nightmare + Extra draw, 6000
    samples of 0x8008EA58: peak 1). In the hang dumps the loop ran ~70-150k iterations per second, so a stuck GPU now
    costs a stall of about half a second to one second, then libgpu's own 'GPU timeout' (queue cleared, GPU command
    buffer reset) and the game goes on. Every trigger is in the dev log as 'tty: GPU timeout:que=..,stat=..' (guest printf).
    (B) runtime (diff section C117): the end of an OT linked-list DMA is a GP0 command boundary: a chain that ends inside
    a command (unterminated polyline, truncated polygon, VRAM write without its data) resets the parser (log 'C117 OT DMA
    ended inside a GP0 command'), so the next CPU command (StoreImage's C0) cannot be eaten as data. Probes (log once /
    first 20): CPU GP0 word during an OT DMA; C0000000 into a busy parser; a CPU-written C0 that never started a read
    (2000 GPUSTAT polls) + the last 32 GP0/GP1 words. 0 events in the checks so far.
  - Runner copies and rewind (27.10.): dt.prepare now writes build-dev's settings.toml into every copy (its [memcard]
    section removed: it names the user's saves; skip_launcher = true), so tests run like the user's game (rewind ON every
    15 frames, OpenGL settings, spu_hq). Every runner / hang_hunt / probe-check PASS before 27.10. 03:00 ran with the
    runtime defaults = rewind OFF (copies had no settings.toml; RUNNER_SETTINGS silently did nothing).
  - C103 host profile (26.10., desktop, windowed normal game paced at 100 %, runner host_load with DT_WINDOWED=1
    + devtools/hostprof.py = thread sampler with exe symbols from llvm-nm):
    | item | cost (share of one desktop core) |
    |---|---|
    | emulation (recompiled guest code + cycle model + devices), Chicago fps_drop_2 / Miami start | ~0.20-0.28 |
    | same with Extra draw distance (CPU 400 %) | ~0.33-0.40 |
    | pacer busy-wait (RtlQueryPerformanceCounter spin before each present) | ~0.13 |
    | always-on debug instrumentation inside it (debug_server_trace_write_check, fntrace_record, parity / audio trace, starvation ring) | ~0.01-0.02 (5-10 % of the emulation) |
    | dev mode, rewind (depth 50 / 15), supersampling 2, antialiasing, spu_hq: each on vs off | within noise (<= 0.05) |
    | GL driver thread, audio, other threads | idle (waits) |
    Process total ~0.45-0.55 cores (0.70 with Extra draw); frame period 16.68 ms p50 / 16.69 p95 / 16.91 max over
    1200 frames (no hitches, rewind on). Headless headroom (runner host_speed) ~3.4x. The guest is ~2 % interpreted.
    Not seen on the desktop: the 'first ~3 minutes slow'. Likely on the laptop: the probe folder and _disc live in
    OneDrive Desktop (Files On-Demand: a new probe / the disc image are downloaded while the game reads them).
  - C110 host-load fixes (26.10., user pre-approved): (b) frame_pacing.c sleeps with the high-resolution waitable timer
    until ~0.5 ms before the deadline (QPC spin 13 % -> 3 % of the emulation thread; frame period p95 16.70 ms, max
    17.1); (c) the TCP debug server and the per-store / MMIO / block recorders (debug_server_trace_write_check,
    trace_mmio_write, cyc_observe, parity_trace_note_write) run only as developer tools: --debug-port on the command
    line (test copies) or psx_mod_request_dev_tools() from driver.personal dev-mode (F9 snapshots keep working);
    play builds without dev mode print 'developer tools off'; (e) build-wip uses ThinLTO (-flto=thin): headless headroom
    Chicago 343 -> 375 %. Runtime diff section C110.
  - C111 Extra draw distance: adaptive CPU speed 200..400 % instead of a fixed 400 % (the frame-wait hook rates each
    game frame: arrived at its VSync wait before 2 vblanks = slack, else late; late frames in a 30-frame window +50 %,
    120 slack frames in a row -25 %). Note: host time per frame is the extra drawing work itself; the overclock only
    decides whether the frame fits its 30 FPS budget.
  - C100 overclock only while game frames advance (8 vblanks without a game frame: 100 %): menus, loading screens, FMV,
    pause spin at exact timing (menu EMU was below 100 % on the laptop with 400 %). Chase music slowing = EMU < 100 %.
  - C101 native 27 x 27 PVS (Polish's _xd levels): XPVS 0x80093430 = 729 -> the draw decode (0x8002D97C) runs into XB with
    *0x800973A8 = 729, the cops' decode (0x8003A258) into XTMP 0x80093434 and copies the middle 19 x 19 (caves
    0x80094640 / 0x80094684, zero run 0x80094634..0x800947C8 zero in every dump); the C94 cave skips its 19 x 19 copy.
    Package: CHI_XD_LEVELS=1 puts <name>_xd_day/_night.lev after the last relocated file + specials_xd_*.bin (only .lev
    and .spc.bin differ), sidecar words 37-52; the plugin loads them while Extra draw distance owns the C94 words.
  - Not reproduced: Antipodean switching on (0 in all 15 snapshot RAMs, anti_check), the loading-screen sound
    (loading_sound: no key-on between the confirm and the first frame; the user had rewound just before).
- **C94 "Extra draw distance" (Infrastructure 25.10., D1 cities first; design chicago/design_c94_drawdist.md):**
  - Exe (exe_patches c94_all, always applied; Driver 1 behaviour while the words hold Driver 1 values): the cell loop
    FUN_8002C8FC reads its window (XS / XW 19), corner trim (XT 4 / XL 18), radius (XR 9), PVS buffer (XB 0x000A80C4),
    object list (XLIST 0x000A76AC), tile bands (XTB1 / XTB2 7000 / 9000), the guards' limits (XOBJ / XTILE) and the two
    primitive buffers (XPB0 / XPB1 0x000D8600 / 0x000F6600, read at 0x800515BC) from zero-block words 0x800933F0..24
    (gp-relative). Cave 0x800947D0 (zero run, seeded in ghidra_funcs) runs only when XR != 9: plane start values 4
    cells further out, the 19 x 19 PVS copied into the middle of a 27 x 27 buffer (ring = 1: drawn when in the frustum).
  - The zero block is cleared at boot (image data reads 0 at the title): driver.chicago's vblank writes the Driver 1
    values every vblank unless XDD (0x80093408) = 1 (driver.personal's extra-draw owns the words). Code placed in the
    zero block ran interpreted (page diverged under plugin data writes): cave moved + runtime mod_bless after plugin writes.
  - Plugin driver.personal "extra-draw" (driver_gameplay.c): 27 x 27 window (radius 13, trim 6), PVS + 4096-entry list in
    guest mod memory, tile bands 10500 / 13500, limits XOBJ 0x48800 / XTILE 0x28800, two 0x50000 primitive buffers in the
    GPU-DMA aperture (psx_mod_alloc_gpu_dma_memory), car LOD 0x80096A48 x 1.5. CHI_XD_PARTS test aid (1 window, 2 list,
    4 bands, 8 buffers, 16 car LOD, 32 limits; default all).
  - Pitfall (GP0 unknown command 0xFE hang): the buffers must be given in KUSEG form (0x00F00000, like 0x000D8600):
    Driver ORs len << 24 straight into the primitive pointer, a KSEG0 0x80F00000 put bit 31 into the tag's length
    byte (0x89 instead of 0x09) and the GPU walked into vertex data.
  - Runner draw_distance (CITY, POSE, DRIVE; RUNNER_XDRAW=1 on): Miami / Frisco / LA / NY / Chicago alive, no garbage in
    the sheets, far ring drawn (posed Miami causeway: horizon objects only with the feature on; NY start: far buildings
    down the street). GP0 packets per frame: Miami 1219 -> 1637, NY 1573 -> 2444. Sampled primitive high water <= 0x19360
    (NY) even with the feature on (the old 0x1E000 would mostly have held; the bigger buffers are the safety margin).
  - Cost is guest CPU (2x cells through cull_objects): at Uncap 200 % FPS standing Miami 30 -> 28.3, NY start 30 -> 19.8;
    at 400 %: NY 30 FPS with EMU headroom 111 %, Chicago fps_drop_2 30 FPS / 183 % (desktop, unpaced runner copy).
    With the frame-wait skip a higher overclock costs host time only when the frame needs it.
  - Decision A (Strategy 25.10., for probe cheats 5): extra-draw's activation sets the overclock to 400 % (max with
    Uncap's own option; Uncap is implied), Mods text says so. Fallback B (1.25x step, cave parameterised) if the laptop
    cannot hold it. Function-entry plugins are not feature-gated: the wait skip runs whenever the CPU is overclocked.
  - Not done yet: D2 cities' own 27 x 27 PVS / area sets (converter; Chicago today = its 19 x 19 PVS + ring 1), a
    residency guard for far D1 objects (none seen missing / garbled in the five runs).
## C40 levers (Infrastructure 24.10., build-test 21a327c2)
- **Lever 1 done (exe C42E site 0x8001FB70 + plugin):** the broad-phase margin comes from each car's own MATRIX pad (car +
  0x16: 0 in 600 RAM dumps, cleared on car re-init, rewritten every vblank): player / special reach only for those cars
  (R35 had added both to EVERY car -> every traffic pair flagged, C82 window let it through, full SAT). Guest samples:
  GlobalTimeStep pair loop 3.3 -> 0.4 %, SAT FUN_80067A44 2.3 -> 0.5 %, FUN_8001B380 2.7 -> 0.7 %. FPS standing (4 dense
  spots x 4 headings): 20.9 / 23.2 / 19.6 / 22.4 -> 22.6 / 25.8 / 18.4 / 25.4 (avg 21.5 -> 23.1; Miami dense 25.2).
  bus_head_on + special_zones PASS (special reach intact). CHI_C40M=0: old shared margin. PS1-native exe; the per-car
  value is host-written (M8: written by guest code at spawn / special swap).
- **Lever 3 measured, default OFF (plugin CHI_C40_LOD=1):** D2's car LOD distance (5500 -> 7260 vs D1's 10000):
  car draw share 3.6 -> 2.6 % but FPS unchanged at all 4 spots.
- **Lever 2 = no action:** active AI cars Chicago 22 / Miami 21 (state byte +1 of the AI record) = Driver 2's own 14 civil
  + 7 parked: traffic is already at D2's density (never thinner).
- **Corrections to day 1:** 0x80011924 is C67's facade cave (D2's own split rule, a feature), not the C68 stub (lever 5
  re-scoped: no cheap cut); FUN_8007B1E8 is NormalClip (called by the polygon drawers 0x80035C34..0x80039134), not spooling
  (lever 4 = map rendering). The runtime charges guest cycles per instruction and GP0 DMA at 1 cycle / word (no GPU fill
  model): FPS follows guest CPU work; host samples (phase_hot) are only a proxy.
- **Remaining gap (~8 % standing)** is map rendering (tile / object drawers, NormalClip, subdivision) = lever 7 territory
  (D2-style rendering), which needs the user's OK first. Driving FPS at these spots is dominated by crashes (debris
  packets); fps_spots now drives a 12 s heading-hold route along the start heading (fps_drop_2: 26.4 FPS, 1023
  packets / frame, 4.5 k units).

## Audit 23.10. step 2 (Polish): white ground = teleport artefact; C72 = aliased barricades
- **Test-pose teleports over long distances leave the world undrawn** (only sky dome, car, debris; ground white / grey,
  "area load after pose" returns at once). Screenshots / FPS after such a pose are invalid. Start the level AT the spot
  instead: dt.prepare(copy, start=(d2x, d2z)) (runner: patch rs.dt.prepare, scratch audit_start.py), then rotate with a
  same-place pose. Started at riverbridge, quay_wall, flicker2 and driven through: ground fine.
- **C72:** GP0 capture at riverbridge (start, heading 0): the saturated line y 112-114 is owned by 4 PolyFT4 1-2 px tall
  (tpage 960,256 = short page 9, uv 0..33 x 144..162 = entry 7 "BARRCDE", CLUT 288,500); VRAM read in game: CLUT and
  texels identical to the level. The barricade's orange / white / blue stripes minified without mipmaps = the speckle.
- **C40 corrected:** started-at-spot FPS: fps_drop_2 19.1 / 27.8 / 25.6 / 24.4 standing (4 headings), 22.7 driving;
  l_down_e 19.8 / 15.9 / 16.2 standing (then wrecked by traffic); Miami 28.3 / 24.8, LA 22.6 / 20.1 (menu starts).

## M3 step 0 + 1a/1b: Havana dry run, per-city profile (Polish 24.10., user 54 yes / 55 B)
- **cityprofile.py** (new): `CHI_CITY` (default CHICAGO) selects `P`; Chicago's profile = the old constants exactly:
  inputs keys (LEV day / night, DEN, LCF, SKY0.RAW), object-extent centre (-119488, 65984) + grid 480 x 630
  (worldscale), start (9216, 106496) (build_package, polish_areas spawn seed), car sets day miami / night la, water level
  1084, water model slot 683, basin water textures, quay wall texture ("C", 1, 3), quay model lists (rail src, drop, ghosts,
  quay_spot), rail inclines / cuts / floor, hidden engine models, landmark prefixes (polish_tex), D1<-D2 car slot map,
  specials (SpecialByRegion row, models, default), car banks (build_package; Infrastructure agreed).
  Read by inputs.d2_lev / cache_dir, worldscale, convert, texrepack (DAY_LEV, report label), polish_cars / cosmetics /
  specials / map / tex / sky / areas, build_package. Chicago-only features switch off when the profile's list is empty
  (SHORE_WALLS needs wall_texture, QUAY_FILL quay_rail_src, QUAY_CLEAN quay_models).
- **Proof:** `setup_chicago.py --levels-only --force` (RECIPE = specdmg2) gives day + night .lev and all 7 sidecars
  byte-identical to var_polish_specdmg2_day / _night.
- **Fixes found by the dry run:** convert() imported polish_cars only on the D2-cars path (UnboundLocalError on every
  other build); converter caches (surface_grid4, sea_kinds, road_levels, level_switches, sea_fixed) were keyed by code
  only -> `_city_key()` ("" for Chicago, so its keys are unchanged).
- **Havana (HAVANA profile, experimental):** inputs.INPUTS d2_HAVANA.LEV / _night / .DEN / .LCF (disc 1). Centre
  (-11158, -90171) from the D2 object extents x -494387..472071, z -388789..208446 (with Chicago's centre the east 61k units
  were off-grid). `CHI_CITY=HAVANA` + ROADS S4 STREAM_INMEM S1_SLOT15 converts: 22 areas, halved 60.1 % / lost 134 units
  (Chicago 56 % / 82), CLUT 241/384 (LA car set; Chicago's D2 cars add ~124), in-memory 182 KB, model spool buffer ~99 blocks
  (Chicago 88), roads 396 / junctions 272 (Chicago 409 / 266), heights deeper (-3000) and higher (+2500..4500) than
  Chicago's. Open for the Havana pass: start, sky, water level / shore texture / quay lists, landmarks, cars (LCF / DEN /
  slot map / specials, car_banks[1]), minimap params, music slots and sea level (Infrastructure, plugin).
- **Havana pass (Polish 24.10.):** HAVANA profile filled from D2 disc 1 / REDRIVER2: start (-238668, -235595) rot 1025
  (MISSIONS.BLK 52 / 53 = Take a Drive, glaunch.c 50 + level*2 + night), sky SKY1.RAW (sky.c), water 2750 (sea plane -2048;
  harbour quays at -2026..-2050), shore walls with SEAWALLN (page 0 / 16), landmarks (CPTLIO, CATHDR, TEATRO, STADIU, CFUERZ ...),
  slot map as Chicago (missions residentModels {1,2,3,0}), specials 8-12 (SpecialByRegion[1], default 11), car_banks[1],
  minimap overlay (overmap.c [1]: 544 x 352, 187 tiles; d2overlay.CITY + polish_map tiles per city).
  Generic fixes on the way: WALL_DEPTH / BED_DEPTH / WATER_Y relative to the profile's water level; area texture limit +
  `area_single_over_ok` (one Havana region alone sees 225-253 textures); specials that are no player choice get their own
  cos row / wheel (polish_cosmetics.special_row); slot entries per profile (Havana 17); reachability cache keyed by the
  spawn; new sidecar <lev>.spt.bin (twistRateY per special, Infrastructure's C82 SPTW).
  Result var_polish_hav2_day / _night: 27 areas, model spool 110 blocks (220 KB), in-memory 183 KB, halved 50.9 % / lost 126
  units, CLUT 337 / 384 (no palette trim needed), 396 roads / 272 junctions, specials keep 29-41 % of D2 area with damage
  copies. Chicago re-checked byte-identical after all of it (setup_chicago --levels-only, .lev + 7 sidecars).
- **Havana pass (24.10.):** profile HAVANA filled from D2 disc 1 / REDRIVER2: start (-238668, -235595) rot 1025 (MISSIONS.BLK
  Take a Drive 52/53 = 50 + level*2 + night), sky SKY1.RAW (sky.c skyNum 1), water 2750 (D2 sea plane -2048; harbour quays at
  -2026..-2050 -> D1 +2674..2706), wall texture SEAWALLN (page 0 det 16), landmarks (CPTLIO CATHDR TEATRO STADIU CFUERZ ...),
  specials 8-12 (SpecialByRegion[1] + 7, default 11), car_banks[1], overlay (d2overlay.CITY HAVANA = overmap.c [1]: 544 x 352,
  187 tiles -> polish_map 11 x 17, CLUT_AT 384). New profile fields: area_tex_limit, area_single_over_ok (a one-region area
  over the limit is kept: Havana's harbour region sees 225-253 textures; limit 260 instead merged areas into a 266 KB spool),
  special_slot_entries (Havana 17). Water-relative depths: WALL_DEPTH / BED_DEPTH = Chicago value + (water_level - 1084).
  Specials that are no player choice (Havana 11) get their cos row (polish_cosmetics.special_row) and wheel from the LCF.
  Overlay() defaults to the profile city; polish_areas reachability cache key includes the spawn.
  New sidecar <lev>.spt.bin ("SPT1", n, civ ref twistRateY, n x {model, twistRateY} from LCF +230) for the plugin's SPTW.
  Result var_polish_hav2_day/_night: 27 areas, spool 110 blocks (220 KB), halved 50.9 % / lost 126 units, CLUT 337/384,
  in-memory 183 KB, roads 396 / junctions 272, specials kept 29-41 % of D2 area. Chicago re-check after all edits:
  setup_chicago --levels-only byte-identical to specdmg2 (.lev + 7 sidecars).

## M3 step 3: Havana's own slot (Infrastructure 27.10., build-wip; user 54 yes, slot index = Q68 open)
- **CITY 4 (FLAT) costs** found in the exe (FUN_80022818): CITY 4 skips InitMusic, sets the view width 0x800971B4 = 0x400
  (400 elsewhere), skips the player-car placement FUN_800682C0 from the mission start (why FLAT crashed / hung 13.10.);
  plus FLAT's entry 4 in ~10 per-city tables / 4 CITY switches (LoadSky, glows 0x8008AE3C / AE5C, minimap 0x8008B080..
  B094 / B230 / B268, 0x8008ABB8, 0x800148C4, haze 0x800298BC `city < 4`). Option B (Havana in CITY 3 like Chicago, own
  row / level / assets) needs none of it -> asked as Q68; the code below runs Havana in CITY 3 (B) until the answer.
- **Package (build switch):** build_package `CHI_HAVANA_DAY` (+ `CHI_HAVANA_NIGHT`) -> a subprocess `CHI_CITY=HAVANA
  build_package.py --city-assets assets/havana ...` (the converter modules bind the profile at import) writes Havana's
  own set into assets/havana/ (car_boxes, car_sfx with car_banks[1], car_wheels, cosmetics, d2_surface 1.39 MB, dmg_*,
  specials / spctwist / specdmg, preview if Design makes one); the Chicago run adds Havana's skies to SKY.BIN (after
  Chicago 13-15 and LA day 16: Havana 17 day / 18 night / 19 rain), D2 songs 1 / 5 as MUSIC.BIN songs 10 / 11,
  havana.lev / havana_night.lev after the last relocated file (overlays, LBA 367000 / 376000 with today's package) and
  assets/havana/slot.bin (chicago_slot.bin layout, 55 words: + word 53 water y -2750, word 54 start heading 1025;
  flags word bits 8-15 = first sky number). Without the switch the package is byte-identical to before (checked: full
  package diff of the refactored build_package vs the old one, cheats 10 recipe). city_assets() = the per-city part of
  main(), moved unchanged. cityprofile.start_rot (new optional field, Havana 1025; no effect on conversions).
- **Plugin (driver_chicago.c):** one asset set loaded at a time (`city_assets_load(0 Chicago / 1 Havana)`, files via
  apath(): assets/ or assets/havana/), reloaded when the selector's D2 row changes (select_virtual); d2_virtual() =
  V_CHICAGO or V_HAVANA; chicago_active() = d2_city(). Per city from the sidecar: level entries, start (+ heading:
  start_heading_vblank turns the spawned car in place over the first 12 frames: matrix, quaternion, +0xF8), night entry,
  minimap words (CLUT_AT 2 x 187 tiles + 8 = 384), car sets 0x10404, sky base (17), song base (Havana 10 / 11), sea
  level (-2750; Havana skips the switch-pad format check), stable pages. Page 2 row "Havana" (LA's handler, the Day/Night
  confirm) when the package has assets/havana/slot.bin, grey otherwise. C37 surface asset and its saved D1 surface
  records reset per city (d2sf_unload). DROWN_RANGE stays 0 in Havana (the exe band starts at Chicago's -1120: D1 rule
  there until the band start is a word). Traffic-light glow offsets: Chicago's values (Havana's signal models unchecked).
- **Checks (runner, build-wip exe):** havana_drive (new test; menu path take_a_ride/havana[/night]): boots, flag 1, sea
  -2750, start heading 1025 facing along the street, drives 17-27k units, day and night (song 11 by night); Chicago:
  cheats_menu, nightmare_start, replay_header, replay_cheats, cd_restore, rewind_loop (with Havana packaged), city_switch
  (package without Havana). Replay header bits: Havana night 0x4000, Chicago day 0x1000; mirror word 0x56000004 / ..01.
- **PS1 budget (M8):** Havana in CITY 3 adds no guest table (LA's CITY-3 entries + the words the plugin already writes for
  Chicago). Level (Polish hav2): 27 areas, model spool 110 blocks = 220 KB (< 256 KB carry), in-memory 183 KB, models
  1540 / 2048 (2048-entry table at 0x80115600), CLUT 337 / 384, texture halving 50.9 % (per-area VRAM pages as Chicago).
  Host-only additions (M8 list): the per-city asset sets / their reload (as Chicago's assets), the spawn heading write
  (M8: the heading in the mission script or a per-city start table), the variant restore below (the variant itself lives
  in guest RAM: header bits + mirror word).
- **Havana round 2 (27.10., build-wip b7cb0c58, levels Polish hav3 + _xd pair):** package recipe = cheats 10 + `CHI_HAVANA_DAY /
  _NIGHT=work/var_polish_hav3_day / _night.lev` (+ `CHI_XD_LEVELS=1`: havana_xd_day / _night after Havana's levels,
  Havana slot words 37-52, specials_xd in assets/havana/; runner: XPVS 729, its xd entry, drives). Menu picture: Design's
  HAVANA.4bit / .clut (128 x 228) -> assets/havana/preview.bin, shown with its own CLUT when the row is highlighted
  (checked on screen). spcshadow (.sps.bin) now in Havana's set.
  - **C17 band per city (engine):** the cave at 0x8005265C jumps to 0x8008A340 (seeded), which adds BANDW 0x80093624
    instead of the fixed 1120 (Chicago 1120 = unchanged rule, Havana 2786 = 36 under its water; CHI_DROWN_BANDW=0 = old
    cave). DROWN_RANGE 620 in both. Runner havana_water: words BANDW 2786 / DROWN_RANGE 620 / sea -2750 in place, but no
    harbour edge could be driven into water yet (geometry below).
  - **Heights (converter, for Polish):** D2 Havana surfaces (d2surface.levels, y down) cluster at 0 (street, 2836 cells
    of 3000), 2048 (982: the harbour level the profile's quays and the Take a Drive start sit on) and -2500 (55). In
    the game the street cells are at y ~136 (D1, y up), the start (D2 2048) at +2864 and D2 -2500 cells at ~-2609: the
    non-street levels come out with the opposite sign (Chicago's deck rule: D2 -1024 -> D1 +1352). Result: the harbour
    quarter around the start is a plateau ~2700 above the streets instead of a basin ~2700 below, 4400-5400-unit drops
    between quarters (runner: car fell from 1885 to -2561, wrecked), the water (-2750) 5400 under the old town's streets.
  - **Signal glows:** Havana's models are TLIGHT1 / SLIGHT1 / SLIGHT2 / DLIGHT1 (Chicago: TLIGHT00 / 01 / 02, SLIGHT01).
    Driver 1's light code finds LA's kinds by name, so Havana shows no signal glows (nothing wrong drawn). Glows need a
    Havana LIGHT_RENAME / LIGHT_TURN in the converter and Havana's head offsets in the plugin (per-city glow words).
  - **Ferries:** the model list has FERRY / FERRYT1 / NOTFERRY and static boats IABOAT1 / 4 / YY / ZZ; D2 places the two
    ferries through events (event.c HavanaFerryData), not as cell objects, so no ferry shows; static IABOAT props do.
- **Havana hav4 (27.10.):** Polish's reading is right (D2 heights y-up; the "2048" quarter is raised in D2; water 160 ->
  sea constant -160). Data: a flood over D2's surface from the start (512-unit steps, <= 300 height change) reaches the
  main level through intermediate heights; the first descent is a straight ramp along +x at D2 z -258123, x -127564 (h
  2065) .. -113228 (h 283), 64 per 512 units. In the game (havana_ramp, D1 -153655 / -221696 heading +x) the car drops
  2547 between two 0.1-s samples at its top: the converted level has no ramp there. The converted road / height map
  (roadh low 16 bits) holds the raised quarter as a closed island (2801 cells at -2703, no neighbour step <= 1300 to the
  rest; 27 road-to-road steps > 300, e.g. h -415 / -2703 at D1 (-156750, 204750)). Shore cars at y ~ -24 were lifted
  2880 within 6 s at two shores (D1 -267750 / -209250 and -215250): plateau heights next to the harbour. Start y 2840 =
  D2's Take a Drive start h 2048 x 1.32 + the car's ~137: consistent. Drowning band words: 196 / 196 (Havana), 1120 /
  620 (Chicago); chicago_drown: Chicago lake edge drowns on the band build and the old-cave baseline alike.
- **M3 fixes for LA <-> Chicago (<-> Havana) mixups (C118, Strategy go 27.10.; each separately revertible by env):**
  (1) `CHI_VARIANT_REPLAY=0` off: replay header word 0x80097644 bits 12-15 = level variant (0 LA, 1 / 2 Chicago day /
  night, 3 / 4 Havana day / night, 5 LA day); a replay start restores it at the mission parse (before the level loads).
  (2) `CHI_VARIANT_STATE=0` off: mirror word 0x80093620 (zero block, magic 0x56) re-applied by restore_vblank.
  (3) `CHI_VARIANT_LA=0` off: a mission other than Take a Ride (0x7C; the Day/Night confirms 0x78 / 79 / 7D in CITY 3
  excepted) runs LA: the page-2 selector exists only in Take a Ride (Driving Games keep Driver 1's city list, Undercover
  has none), so LA's records are never written from a Chicago / Havana run (Take a Ride keeps no records).

## cheats 5 review (Polish 25.10., analysis): menu strip / black box, bus shadow + tyres, extra-draw holes
- **Menu strip + black box = the specials slot re-uploaded in the frontend.** VRAM diff main menu at boot vs main menu
  after a Chicago Take a Ride (runner, polish copy): the block x 704..767, y 128..255 (page 8 bottom half = R34 specials
  slot) holds the .spc.bin slot block after returning (first 256 B match work/var_polish_specdmg2_day.lev.spc.bin +78016;
  before: frontend data, 7397 non-zero bytes). The main menu's semi-transparent sprite reads VRAM x 704..727, y 0..135
  (screen 152, 226): its rows 128..135 are slot data = the strip; other frontend screens using x 704..767, y 128..255
  show the black box. Cause: specials_vblank (driver_chicago.c) gates on chicago_active() && psx_mod_game_started(),
  both still true in the frontend after quitting (CITY stays 3), so the 64-vblank "slot lost -> re-upload" keeps
  writing the slot over the frontend's VRAM. Fix (plugin): also require "in level" (e.g. FRONTEND overlay not resident:
  MENU_MARK 0x801CE038 != 0x0172001A, or the in-level beat LVL_BEAT recent) for spc_slot_upload and its check. Also
  left over after Chicago (harmless at the main menu, check other screens): x 832..1023, y 256..480 (Chicago pages),
  CLUT rows 480..511 at x 0..192 / 416..512.
- **Bus tyres "too small":** wheel size is Driver 2-faithful (LCF wheelSize 74 x 1.32 = 98, civilians 52 -> 69; same
  tread / hub rule as cars.c DrawCarWheels). The gap above the tyre in the arch (snapshot 202242) matches R34's ride
  height rule: specials' BODY raised by CLEARANCE + 1.32 x (their clearance - civilians' mean) = bus +59, fire engine
  +67, 9 +35 -> the wheel sits ~0.6 radius low in its arch. Fix: place the special's wheels per D2 (wheel centre y = -
  wheelSize - wheelDisp.vy - susCompression + 14, x1.32) and drop the body raise (polish_cosmetics wheel_vy +
  ride_extras for model 5 + the plugin's placement offset).
- **Bus shadow:** Driver 2 sizes it from cPoints[0..3] (handling.c SetShadowPoints; bus x +-163..168, z -645..660 ->
  x1.32: +-221, -851..871). Correction (25.10.): FUN_80040BAC is NOT the body shadow (its quad is one-sided z 450..750,
  behind the car = a rear effect). The shadow in a GPU frame: a 3 x 3 PolyFT4 grid under the car, tpage 0x1E, clut 0x7F83,
  uv 180..191 / 31..59; producer still to find (wtrace on that tpage / clut word). Fix: for model 5 take the corners from per-model words (plugin from the asset; exe gate like SPBX / SPBZ).
- **Extra draw distance holes / bad buildings (D1 + Chicago):** see the C94 row; causes in order of likelihood:
  (1) ground tiles stop at the tile band 13500 (XTB2) while objects reach radius 13 x 3000 = 39000 and the ring is drawn
  without PVS: along open streets the road 13.5k..39k is simply not drawn; plus the tile list cap (128 stack + 512 at
  *0x8009715C, XTILE guard) can drop nearer tiles once more tile objects are in range; (2) far objects whose model is not
  in the loaded area (area sets were built for radius 9) draw with whatever sits in that model slot; (3) far objects
  beyond the OT's z range sort into the last bucket; (4) subdivision thresholds 6000 / 9000 (0x80030B08) unscaled.
  Fill the ring: far ground band to the object radius with the cheap far-tile routine (FUN_80026FF0) + a bigger tile list,
  a residency guard (skip non-resident models), the OT shift for XR 13, subdivision x1.5; for Chicago a converter
  27 x 27 PVS + wider area sets (data, Polish) cuts cost.
- **cheats 6 data side (Polish 25.10.):** CHI_POLISH_SPCRIDE=d2wheel (polish_cosmetics.ride_extras: body raise by D2's
  clearance - wheelSize relation: 8 +15, 9 +11, 10 +28, 12 -13 instead of 67 / 35 / 59 / -15; also the player choices,
  same models); CHI_POLISH_SPCSHADOW=1 -> <lev>.sps.bin ("SPS1", n, n x {model, 4 x (x, z)} = D2 cPoints x 1.32);
  CHI_POLISH_XDRAW=1 (pvs.py) -> the Extra-draw level variant: native 27 x 27 PVS (radius 5..13 by 0x50000 x 0.72; 289552
  cells at 13), area sets from that radius: halved 67.5 % / lost 113 (normal 56 % / 82), spool 98 blocks, CLUT 365/384.
  Levels work/var_polish_cheats6_day/_night (a + b) and _xd_day/_night (a + b + XDRAW). Switches off: setup_chicago
  --levels-only byte-identical to specdmg2 (.lev + 8 sidecars).
- **C99 Hell, D1 pursuit speed path (Polish 25.10., static):** cop driver block 0x80065BD0..0x80066000 (record s0, car s1):
  rubber band A 0x80065D0C..80 (0x80096E60 && rec+0x7A0: target -> player speed 0x8009B1AC + 10 within 4000 units, blend
  above), rubber band B 0x80065E94..E0 (0x80096E68 == 0: blend toward max(player speed - 20, 20)); base target = table
  0x8008BBD8 / 0x8008BBE4 (0x80097710) [difficulty 0x80096870] x felony factor (0x80097740 / [0x800C4C94] + felony x
  [0x800C4C80] >> 12); max thrust ((diff + 8) << 10 [+ (diff + 4) << 10]) x (0x80097700 + felony x [0x800C4C7C] >> 12) >> 12,
  thrust = clamp(err x max / 50); car+0x108 < 0x30 low-speed scale; car+0x12E == 1 -> thrust >> 1 (0x80065FBC). Physics:
  linear drag -12 x v per wheel (StepOneCar), so the rubber bands are the likely cap (+41 %).
- **D1 car shadow (Polish 25.10., offline):** not model data (no D1 car model in LA lump 28 references CARSHAD; car models
  use pages 1/3/4/5/6, 67-72) and not cosmetics (row = 8 lights + 4 wheels + 2 shorts). Texture CARSHAD 32 x 64 in every
  level (LA p7 d3 128,96; Miami p1 d15 112,192; Chicago p6 d28 144,160). Not looked up via GetTextureDetails 0x80052240
  (52 calls); "CARSHAD" bytes at 0x80096958 have no xref. Exe-side; find the writer by primitives using that rect.
- **Havana hav4 (Polish 27.10.):** heights were never sign-flipped: d2surface levels() h is y-up and equals -object y in
  both cities (Chicago h -1024 <-> objects y +1024; Havana h 2048 <-> objects y -2048). Havana's "2048" quarter (9130 land
  cells, roads ROAD1 / PATH1 at object y -2048, the Take a Drive start) is RAISED 2048 above the main level 0 (84002
  cells); h -2048 (923 cells) is low ground at the sea plane. The real error was the water: 2750 (D1, down) from the
  wrong reading; the harbour water sits just under the main level (SEAWALLN quay walls reach 111 below it, the three
  static FERRY cell objects float at y 111) -> water_level 160, BED_DEPTH 776, wall_depth 3200 (raised-quarter cliffs
  ~2860 to the water). Road map D1 heights: raised 7406 cells at -2703, main + water 1198575 at 0..160 (hav3: water cells
  1084730 at 2750, so 2600-5450 drops). Lights: profile light_turn / light_rename: TLIGHT1 (turn 32) -> TLIGHT00, SLIGHT1
  -> SLIGHT01, SLIGHT2 (turn 32) -> SLIGHT02, DLIGHT1 -> SLIGHT00. Ferries: 3 FERRY objects already in D2's cell data
  (y 111), converted as static world objects.
- **Havana hav5 (Polish 27.10.): the ramp and the shore lift were building blocks read as water / at 0.**
  - Cause 1 (sea_kinds): water vs building block is decided by the D2 overhead map's palette; Chicago's (1 river, 12 lake)
    was hard-coded. In Havana 12 (and 10 / 13) are the grey building blocks, the sea is 4 (+ 5 coast shading, 1 sea
    labels). So most enclosed blocks were "water": the raised quarters looked like islands over 'sea' (the ramp at D2 z
    -258123 ran between two water strips: havana_ramp's car, posed at the ramp's edge row, had wheels over D1 water ->
    the 2547 drop), and havana_water's "shores" (D1 -267750 / -209250, -215250) are building blocks inside the Necropolis
    raised quarter (lifted to the quarter's level). The ramp itself was always in the road map (188 per cell).
  - Cause 2: real building blocks ("inside") were written at 0, also inside the raised quarters (2700 drop at every block
    edge; the d2sf hook keeps Driver 1's height where Driver 2 has no surface).
  - Cause 3 (C17 deck fix): raised-quarter / ramp cells beside a block (no surface = "wet") counted as deck-only cells at
    the water and got the street level as an extra plane, which the road map then wrote (choice = level nearest 0).
  - Cause 4 (region write): regions without objects share one "empty" spool block incl. ITS road map (the map edge's: all
    water); Havana's centre regions (7,10) / (8,10) have no objects -> 7200 block cells written as water.
  - Fixes: cityprofile `map_water` (Chicago (1, 12), Havana (1, 4, 5); sea_kinds cache key unchanged for (1, 12)),
    `inside_follow` (Havana: block cells take the nearest street cell's level, multi-source BFS), `raised_ground` (Havana
    (-2703, -2726): not decks for C17) and C17's water test skips "inside" cells when inside_follow; convert: an empty
    region shares the empty block only with an identical road map (generic; Chicago byte-identical, below).
  - Numbers (day; D1 written heights, 4-neighbour steps): road<->block steps > 300: hav4 1861 -> hav5 23; road cells
    beside fake water: 12748 -> 0; raised cells beside water: 1304 -> 0; water tiles 21283 -> 7284, shore walls 7204 ->
    2243. Road<->road steps > 300 (both cells with a D2 surface): 1184 -> 930; hav5's 930 checked against D2 (24 samples
    between the centres, continuity <= 100 per 62 units): 640 cliffs > 1000 and 112 smaller steps where D2 itself has no
    continuous surface (walls / raised platforms), 128 + 1 continuous D2 slopes steeper than 300 per cell (carried by the
    sloped ROADSURF planes / the d2sf exact lookup), 49 stacked deck cells by the water (C17 rule: street written, deck plane kept;
    43 on the D2 1537 diagonal deck at the east shore, 5 on ~800-900 decks in East Havana, 1 at the west tunnel).
  - Ramp profile (row 777, D1 cols 377-392): -2700, -2636, -2444, -2260, -2068, -1884, -1700, -1508, -1324, -1132, -948,
    -756, -572, -388, -196, 4 (max 192 per cell, D2's 64 per 512); rows 772-781 beside it follow the same profile.
  - Real main-level shores for havana_water (road cells, 5 road cells behind, 5 water cells ahead): start D1 (-22500,
    195000) towards +z (Malecon), (367500, -196500) towards +x (harbour), (-213000, 55500) towards -z (west bay).
  - In game (Polish copy devtest/polish, build-wip exe, package CHI_HAVANA_DAY/_NIGHT = hav5): static poses read the converted
    heights within 20 (ramp row 777, raised blocks, start). The ramp drive from its top (+x) follows the D2 slope (2747 -> 134
    over x -152684 .. -132808 = 0.125): havana_ramp's "<= 300 per 0.1 s" failed only because the car does ~1300 units per
    sample; slope-relative check passes. -x / +-z drives from cell 372 stay at 2830-2870 (no fall).
  - TELEPORT ARTEFACT (runner): after a long pose the engine keeps the start region's road map in the target's barrel (RAM
    dump posed at (-22500, 205000) = region (7,12): barrel 1 (0x8011E680, 21600-byte stride from 0x80119220) held region
    (5,8), the raised start quarter) -> cars stand 2700 up on 'water', or at street level over water (x 367k..455k), and
    the area is undrawn (white). A pose into another region and back fixed (7,12) but not (12,8); driving into a region
    always loads it. Water / height tests far from the start need the package start there or a drive-in.
  - Drowning on correctly loaded Havana water (region (13,8), x 461k+): the car rides at y -25 (water 160), countdown
    0x80097004 stays 25, timer 100, also with CHI_D2_SURF=0. Engine side (Infrastructure): neither the centre rule nor the
    C17 band fires at Havana's shallow sea. Malecon / west bay spots hit sea walls (no drive-in there).
  - **hav6 (Polish 27.10.): drowning cause = the water tile's model slot** (Infrastructure found it in RAM: runtime model
    683 in Havana had flags 0x0001 / 0x0000). D2 Havana has its own model 683 (unnamed AREA model, 2 objects at y -2726),
    so the area spool replaced the water tile in the runtime table: no sea flag 0x80 -> no sea branch in FindSurfaceD2,
    no drowning. Profile water_model 683 -> 124 (BUILDING0018: in-memory, never placed, no instance / LOD use). Side
    effect: 25 areas (was 27), spool 218 KB (xd 210), halving 48.4 % (xd 56.5 %), CLUT 335 / 336. In game (own copy,
    build-wip exe): havana_water PASS (harbour (367500, -196500) +x: timer -> -1, Game Over; the 2nd spot only inherited that Game Over); ramp PASS with
    the slope-relative check (havana_ramp's fixed 300-per-sample limit fails at the car's speed: steps 415 on the real
    0.125 ramp). Chicago unaffected (profile only; CHICAGO keeps 683).

## C119: overclock host guard v2 (Infrastructure 27.10., build-wip e1665478; probe "havana 1" user report)
- **Report:** "Uncap GPU usage makes no difference on vs off" (user laptop `Startklar`: Intel GL driver 32.0.101.7076, 144 Hz,
  internal scale 2x, Extra draw ON, Uncap OFF + cpu_percent 300; developer tools were off in that log). The C115 guard logged
  62 % at 300 -> 68 % at 250 -> 76 % at 200 -> 95 % at 150 -> ceiling 100, then 83-95 % each time it re-raised to 125.
- **Causes:** (1) Extra draw implies Uncap (s_xd_pct 200..400 wins over s_uncap_pct), so Uncap on/off cannot differ while
  Extra draw is on (by design, said in the option text). (2) The guard judged single seconds right after the level start
  (spooling), counted menu/loading seconds (forced 100 %, always full speed) toward re-raising -> flapping 100 <-> 125.
- **No regression in 6162815a:** desktop A/B vs cheats 10 2078d295: host_speed headless (Chicago fps_drop_2, uncap 200 +
  Extra draw) 274/274 % vs 275 %; host_load windowed 0.50/0.54 vs 0.50/0.48 cores. Dev tools on/off 274 vs 278 %.
  Extra draw costs ~18 % host time (324 -> 274 % headless). build-dev 6ce7fda1 does not start in a build-test copy (no
  debug server), not compared. The laptop is simply short of host time with Chicago + Extra draw.
- **Lab finding (runner test `oc_guard`: game pinned to one core + a duty-cycle hog, windowed, paced):** with the frame-wait
  skip, lowering the CPU speed saves host time only when the guest drops from 30 to 20 FPS; per-vblank host costs (GL,
  present, SPU) dominate a short host. Old rule at hog 0.65: 100 %, EMU 70 %, 20 FPS; new: 200 %, EMU 67 %, 30 FPS. Where the
  overclock IS the cause (hog 0.3, Uncap 400): probe at 100 % reads 99 % -> cut kept (EMU 95-99 %). No hog: no guard lines.
- **Guard v2 (driver_gameplay.c overclock_guard):** (a) in-level seconds only; (e) 8 s warm-up after a level start / pause;
  trigger = 3-second average < 97 % while overclocked; (b) probe 3 s at 100 %: >= 97 % or a gain >= CHI_OC_GAIN (10) =
  overclock was the cause -> ceiling 100, re-raise +25 after `need` full-speed seconds, (c) `need` doubles per kept cut
  (10..320 s); otherwise host-limited -> ceiling back, hold 60 s; (d) "host is short of full speed" logged once at 100 %.
  CHI_OC_GUARD=1 = the C115 rule. Host-only (PS1 path: no overclock exists there, nothing to port).
- **Open / proposal:** if a short host should keep music speed instead of 30 FPS, the lever is host-side frame skipping
  (present/raster fewer guest frames), a runtime feature; it only helps if GL/present is the laptop's cost (unmeasured).

## Minimap streaming (D2) study (Analyst 27.10., offline; R63)
- **D2's scheme (REDRIVER2 overmap.c):** LUMP_OVERLAYMAP (24) is loaded with the level (main.c 217
  ProcessOverlayLump) and copied whole into RAM (D_MALLOC): u16 offsets of RNC2-packed 32x32 4-bit tiles (512 B raw
  each) at +0, 16-colour CLUT at +512 (uploaded to 960,256 once). Streaming is VRAM-only, never CD: a 4x4 ring of
  tile slots (128x128 4-bit = 32x128 halfwords = 8 KB) inside the "OVERHEAD" texture page; LoadMapTile(slot, x, y)
  RNC-unpacks one tile into the 520-byte MapBuffer and LoadImages it (8x32 halfwords); out-of-range tiles = the
  `dummy` fill byte. InitOverheadMap fills 16 tiles; DrawOverheadMap shifts the 4x4 maptile[][] ring by one
  column/row and reloads 4 tiles when the player's map pixel (x_map/y_map = offset + pos/scale) crosses the middle
  (x_mod/y_mod 16) of a 32-px tile. Full-screen map (DrawFullscreenMap, pause.c PauseMap toggles gShowMap): 320x256,
  1:1, centred on the player and clamped to the map edges, d-pad pans 8 px/frame, optional rotated mode; it draws
  every on-screen tile immediately (LoadMapTile(ntiles & 15) + DrawPrim + DrawSync per tile, off-screen tiles
  clipped), then InitOverheadMap restores the ring when the map closes.
- **Driver 1 is the same code family, and the port already uses it:** loader 0x80054140 memcpys the lump to the heap
  (0x80097098), CLUT at +0x148 (+ MAP_CLUT_EXTRA for D2 frames); LoadMapTile = 0x80056278 (slot table 0x8008B140,
  VRAM base 0x800975F0 = special page u128..255 v0..127, buffer 0x800BE790, RNC 0x80026140); init 0x800541C8;
  ring update in 0x8005474C (4 calls); pixel 0x800563CC. Note 0x80056278 skips the x < width test for CITY 3
  (tiles past the east edge wrap to the next row instead of the fill byte; LA quirk, harmless so far).
- **Numbers** (scratch mapstudy.py): lump bytes / tiles / unique: D1 LA 9012/78/73, Miami 11540/96, Frisco
  12108/156, NY 9936/84; D2 Chicago 21880/252/163, Havana 21960/187/140, Vegas 19988/189/160, Rio 25856/252/158;
  ours chicago.lev 22144/252/163 (frame 290,141,672,384,252|9<<8,2831), havana.lev 22416/187/140 (128,224,352,544,
  187|8<<8,2703). RAM: the whole packed lump stays resident (+13 KB vs LA per D2 city). VRAM: 8 KB ring in every
  case; a whole-map texture would be 129 KB (Chicago/Rio), 94-95 KB (Havana/Vegas). So "adopting D2's streaming"
  saves nothing more: it is already what runs. CD-streaming tiles would save at most ~20 KB RAM per city but costs a
  CD seek per 32-px crossing against the area spooler (C45 family): not recommended.
- **Pause map (why it fails for D2 cities):** the pause menu sets flag 0x800967E8 (write at 0x8006C498; handler
  0x8006C4BC clears it on a key); 0x800543D8 then calls the full map 0x80057AE4 instead of the HUD. 0x80057AE4 draws
  ALL w/32 x h/32 tiles 1:1 on a fixed 512x240 screen (TILE 0,0,512,240), each through slot 0 (0x80056278(0,c,r) +
  GT4 frame + FT4 via 0x80074628 = DrawSync + send), no clipping, layout hard-coded per CITY: 0/5 straight, 1 (Frisco)
  scrolls vertically with the player, 2/3: screen x = 32 row + (512 - h) / 2, y = w - (240 - w) / 2 - 32 col.
  Marker 0x80058278: table offsets + 0x31 only for CITY 0/5; CITY 1 uses constants 0x83/0xCC, CITY 2/3 constants
  0x118 / -0x1C (LA's frame), then 0x8005813C / 0x800585D8 draw it. Simulated (scratch fullmap_sim.py) for the
  CITY 3 branch: LA 192x416 -> y 8..200 (100 % visible); Chicago 672x384 -> y 248..920 = 0 % on screen (blank map);
  Havana 352x544 -> 41 % (bottom cut, edges cut); Vegas 672x288 -> 0 %; Rio 576x416 -> 7 %. The marker is placed
  with LA's constants for every D2 city. Also 252 RNC decodes + 504 DrawPrim/DrawSync per frame (no clip).
- **Proposal (guest code, PS1-native; plugin only writes data words as today):** a D2-frame branch at the top of
  0x80057AE4 (flag word gp-relative like MAP_CLUT_EXTRA, set from the slot sidecar's frame) into a cave routine that
  ports D2's DrawFullscreenMap non-rotated path to Driver 1's frame: player pixel from the table (as 0x800563CC: col =
  x_off + 48 + z/scale, row = y_off + 48 + x/scale), screen x = row - ox, y = (w - col) - oy, origin ox/oy = player
  minus screen centre (256/120) clamped to [0, size - screen] per axis (Havana pans in x and y, the others in y only),
  draw only tiles overlapping 512x240 (<= 17 x 9 = 153, typically 16 x 8) with the existing 0x80056278 + FT4 pair,
  marker at (row - ox, w - col - oy) via 0x8005813C. Optional D2 d-pad pan (+-8 px/frame, pad word 0x8009752C bits
  0x8000/0x2000/0x1000/0x4000) needs 0x8006C4BC to ignore d-pad presses as "close". Slot-agnostic: works for all
  4 D2 cities in CITY 3 or in new slots (Q68), D1 cities keep the old path. Cost: 0 extra RAM/VRAM (code only,
  ~120-150 words); fewer tile decodes per paused frame. No memory to gain from the minimap itself (see above).

## Q68 = 68 B: D2 cities stay virtual in CITY 3; D2 city id decoupled (Infrastructure 27.10., build-wip)
- **Assessment (offline, ghq):** CITY 0x80096834 has 113 refs in 63 functions. A new index (8+) would need 12 CITY-indexed
  tables moved / extended (glows 0x8008AE3C / AE5C, minimap 0x8008B088-B094 / B230 / B268, 0x8008ABB8, 0x800148C4, level paths
  0x80086EC0, DTM_BIN 0x80086F00, names 0x8008B328, runtime 0x800BE0A4 x 0x20), switches 525B8 / 52620 / 52CDC / LoadSky / 508B0
  (default for 8+) and ~60 equality / range checks (==1 SF, ==5 NY, ==2/6 interview / training, <4 haze, 6/7); "cities
  unlocked" 0x800967E0 (max city + 1, memcard) would exceed D1's own lists. Free indices: only 4 (FLAT: InitMusic skip, view
  width 0x400, no player placement at 0x80022818); 7 = credits. User decision 68 B (27.10.): virtual cities in CITY 3.
- **City id (plugin driver_chicago.c):** `D2_SLOT_CITY 3`, `s_d2c[]` = {name, asset dir, slot sidecar, preview, song base,
  variant code, glow column}: 0 Chicago (assets/, songs 8/9, variants 1/2), 1 Havana (havana/, 10/11, 3/4), 2 Las Vegas
  (vegas/, 12/13, 6/7), 3 Rio (rio/, 14/15, 8/9). V_VEGAS 8 / V_RIO 9 virtuals; `d2_city()` = running id or -1;
  cur_variant / apply_variant / select_virtual / glows / sea word key on the id. Replay header bits 12-15: codes 10-15 free.
  Test switch `CHI_D2_ROW_CITY=2|3`: page 2's Havana row loads Las Vegas / Rio (rows wired when the levels land).
- **Package (build_package EXTRA_CITIES):** `CHI_HAVANA_DAY/_NIGHT`, `CHI_VEGAS_DAY/_NIGHT`, `CHI_RIO_DAY/_NIGHT` ->
  assets/<dir>/ (subprocess CHI_CITY=<NAME>), <dir>.lev / _night / _xd_day / _xd_night after the last file, skies appended
  in id order (first sky number in each slot.bin flags bits 8-15), D2 songs at the fixed slots up to the last packaged city
  (cityprofile songs). Without a city's switch nothing of it is written.
- **PS1 path (Milestone 8; host-only today):** the city choice is a host plugin decision (asset set from the package, level
  table entry 3 rewritten, per-city words poked). Guest-side: one guest word (the variant code, already mirrored in
  VARIANT_WORD 0x80093620 and the replay header bits 12-15) read by a small exe routine at the level load that picks the level
  path / CD position (entry 3's 8 words from a per-city table on the disc) and the city's data block (sidecar words: sky base,
  song base, sea level, glows, minimap frame) into guest RAM, instead of the plugin.

## C121: Havana car sounds (Infrastructure 27.10., build-wip 36cf8f4e; user 'havana 1': D2 cities sound like Driver 1)
- **Cause (plugin sfx_v2_vblank, R36):** (1) the CSX2 parse (s_sx_n / s_sx_map / sample offsets) was cached once per session
  and never reset when city_assets_load swapped the asset set: after the boot-time Chicago set, Havana's car_sfx.bin was
  copied with Chicago's offsets out of a freed / reused buffer (garbage or Chicago samples); (2) the civilian banks were
  Chicago's fixed {12, 4, 13} (Havana's car_banks[1]: cop / model 3 -> 11, model 2 -> 10, model 4 -> 7), so none were placed
  and the player slot (copied from slot 20) stayed silent (spu_voices: channel 0 off, channel 1 on a stray address).
- **Fix:** sx_reset() in city_assets_load; civilian banks from the set's map (model 2's bank -> slots 20/21 + horn 25, the
  cop's -> 16/17 + 24, the next other of models 3/4 -> 18/19 + 26; Chicago's map gives the old layout byte for byte).
  Runner `car_sounds` (spu_voices per channel, bank 0 table): Havana player engine / idle now 0x38EF0 / 0x3A760 (music
  tail, D2 bank 4 = choice 0), civilians placed to 0x12ED0; Chicago unchanged (0x3CD60 / 0x3F020, civilians to 0x12E60).
- **Chicago too (user, 'havana 1' desktop session 22:13):** the page-2 cursor passing the Havana row loads Havana's set and
  back (select_virtual on highlight), so even a Chicago-only session swapped s_sfx under a parse made earlier (title demo):
  the log shows the civilian line but no 'R36 player car sound' -> the player kept a civilian / Driver 1 engine. Runner
  car_sounds FIRST=<city> (quit, the other city): old exe 6162815a Chicago -> Havana = channel 1 on a stray address, no player
  sound; Havana -> Chicago on the old exe played Chicago's layout in Havana; ff9dfc50: both orders place the city's own D2
  player (Chicago bank 10, Havana bank 4) and civilian banks (Chicago 12/4/13/2, Havana 11/10/7). Fresh single-city runs
  (both exes): Chicago channels 0/1/7/8 all D2 samples (SPU bytes matched against car_sfx.bin).
- **Sirens (open, SPU budget):** Driver 1's siren = bank 0 sample 11 (0x24340, 2976 B @ 22 kHz, voices 10-15 in a chase). Driver 2's
  are per city (VOICES2 bank 69 + GameLevel: Chicago 69 6048 B, Havana 70 14848 B, Las Vegas 69, Rio 71 12336 B, all 8 kHz
  loops). No SPU room left in the samples 1-2 space (Chicago 1.3 KB, Havana 5.9 KB free after horns): needs another unused
  Driver 1 bank-0 sample in D2 cities or a smaller block.

## setup_chicago follows the shipped package (Infrastructure 27.10., Strategy after the 'havana 1' ship)
- **Gap:** the auto / --build recipe built only Chicago day + night with the specdmg2-era RECIPE (no d2wheel ride, no shadow
  sidecar), no Extra-draw pairs, no Havana: a rebuild (disc change, new marker) would have silently shipped less.
- **Now:** RECIPE = Polish's cheats6 switches (+ CHI_POLISH_SPCRIDE=d2wheel, CHI_POLISH_SPCSHADOW=1), CHI_NIGHT_MOON only for
  night conversions (NIGHT_RECIPE), XD_RECIPE CHI_POLISH_XDRAW=1; CITIES = [chicago, havana (CHI_CITY=HAVANA, package
  switches CHI_HAVANA_DAY/_NIGHT)] (Las Vegas / Rio join here when shipped); build_levels() converts every city's day /
  night / XD day / XD night (cache <setup cache>/out/<tag>_<tod>_<key>.lev, staged under package names in out/stage/),
  package_cmd_env() passes them (+ CHI_XD_LEVELS=1, CHI_POLISH_MUSIC=1, LA day). The code_key covers every city's level key.
  feature_guard(): the new package must contain every level / city folder / manifest feature id of the installed one,
  else the build fails loudly and the installed package stays (unit-checked: dropping Havana is refused).
- **Check (27.10.):** forced --auto on a marked devtest copy of build-dev (3228 s, 8 conversions + LA day): all 8 levels +
  sidecars byte-identical to var_polish_cheats6_* / var_polish_hav6_*; the package equals build-dev's ('havana 1') except
  havana/city.json (source paths) and the manifest's line endings.
- Note: the playable copy has no driver_personal folder, so its prelaunch line cannot rebuild there (it boots the shipped
  package as is); build-dev's marker predates this code key -> its auto step skips until the next ship re-marks it.

## C120: Havana chase music (Infrastructure 27.10., shared exe window; build-test / build-wip ff9dfc50)
- **Cause:** the C60 chase table (0x8001188C, 10 ints: D1's 8 + Chicago 7 / 8) ended before Havana's songs 10 / 11: the
  lhu read the next stub's code (0xFFF8) -> XM set-position 65528 -> no chase section (copmusic did go to 1).
- **Fix (exe_patches chase_table_patches, CHI_CHASE_TABLE16=0 = old table):** 16 ints at 0x8008A2B0 (zero padding before the
  C114 cave): D1's 8 + xm_coptrackpos_d2 by song slot from cityprofile (Chicago 7 / 8, Havana 0xB / 9, Las Vegas 0x12 / 0x10,
  Rio 0xC / 0xA); base lui/addiu 0x8004CF84/88 -> 0x8008A2B0; the MDEC strings at 0x8001188C are no longer written.
  Patch count 1926. PS1: pure exe data.
- **Check (runner chase_music: felony 0x400, copmusic, table entry, song order position after 4 s):** Havana day 10 -> 11
  (pos 12), night 11 -> 9 (pos 11), Chicago 8 -> 7 (pos 9), Miami 3 -> 11 (pos 12, D1 unchanged). Subset on ff9dfc50:
  cheats_menu, replay_header, chicago_drown, havana_water (harbour 367500/-196500; the test's default spots updated to it),
  ship_check PASS. build-test's own ninja dir is stale (link errors on the newer caves): build-test = build-wip's exe copy.

## C122: pause-menu map in the D2 cities (Infrastructure 27./28.10., shared exe windows; build-test / build-wip 2c28c5e9)
- **Engine (exe_patches c122_patches, CHI_C122=0 off; plugin writes MAPD2 0x80093628 = 1 while d2_city() >= 0 with its own
  minimap frame, 0 = Driver 1 unchanged):** MAPC cave 0x8008A4D0 (zero run after the u16 list ending 0x8008A4CE, 115 words)
  from CITY 3's layout branch 0x80057C40: player overlay pixel u = x_off + z / scale + 49, q = y_off + x / scale + 49 (table
  entry 3; + 49 as D1's CITY 0/5 marker and D2's WorldToFullscreenMap) at screen (256, 120): fp = 256 - q - sx clamped to
  [512 - h, 0] (centred when h <= 512), l50 = w + 32 - u - 120 + sy clamped to [32, w - 208] (D1 centring when w <= 240);
  marker words sp+0x18 / 0x1C set so D1's own '+ l50 / + fp' lands on the player. D-pad held (0x8009752C, active-high:
  left 0x8000, right 0x2000, up 0x1000, down 0x4000) pans 8 px per map frame (MAPSX / MAPSY 0x8009362C / 30, stored clamped,
  reset after 60 vblanks without a map frame (MAPVB 0x80093634): a map frame spans several vblanks, 5 reset every frame).
  MAPW 0x8001188C (the MDEC strings freed by C120): LoadMapTile's CITY 3 east-edge skip only without MAPD2. MAPK 0x8008A440
  (jal from 0x8006C4E8): the map's close test (new presses 0x80097538 = cur & (old ^ cur), FUN_800514E0) ignores the d-pad
  with MAPD2. Assembler: 'div'. Seeds 0x8008A4D0 / 0x8001188C / 0x8008A440. PS1: pure exe + MAPD2 from the city data block.
- **Check (runner pause_map: Show Map = pause row 6; set_input masks are active-low raw, clear_input releases):** LA:
  Driver 1's map and marker unchanged, any d-pad closes it; Chicago: whole width centred (x 64..448), player at the Gold
  Coast on a road, y pans -195..+133, d-pad keeps it open, cross closes; Havana: renders (Necropolis de Colon start), x pans
  its 32 px, y its 112 px. Subset PASS: cheats_menu, havana_drive, chase_music, replay_header, city_switch, ship_check.
- Not done: the second (mission target) marker keeps LA's transform (Take a Ride has none); all w/32 x h/32 tiles are still
  decoded each map frame (Chicago 252; draw-only-visible would cut that, PS1 cost).

## M3 Las Vegas / Rio de Janeiro (Polish 27./28.10., levels vegas1 / rio1)
- **Inputs** (inputs.py): d2_VEGAS.LEV / _night / .DEN / .LCF, d2_RIO.* and d2_SKY2 / SKY3.RAW from D2 disc 2 (same md5 on disc 1).
  d2overlay CITY: VEGAS (68, 457, 288, 672, 189, 0xBB, 1911), RIO (159, 207, 416, 576, 252, 0x44, 2048) (overmap.c).
- **Profiles** (cityprofile VEGAS (+ alias LASVEGAS) / RIO): centre = D2 object extents; start = MISSIONS.BLK 54 / 56
  (Vegas (143285, 621193) rot 2050, Rio (24453, -497793) rot 1025); sky SKY2 / SKY3; car_banks from gamesnd.c car_banks[2] / [3]
  (Havana's profile has 8: 6 where MapCarIndexToBank gives 17: left as shipped); specials SpecialByRegion[2] / [3], default =
  residentModels[4] (Vegas 9, Rio 8); new data fields songs / chase_pos (Chicago (2, 6) / (7, 8), Havana (1, 5) / (11, 9),
  Vegas (3, 0) / (0x12, 0x10), Rio (4, 7) / (0xC, 0xA): REDRIVER2 main.c retail musicType + xm_coptrackpos_d2).
  - Map water: Vegas 7 (the Lakeside lake), Rio 4 (sea + Lagoa). Rio's coast strips are land colour 15 without D2 surface ->
    'void' (written water, drowning, no tiles drawn; D2 places its own sea tiles 783 / 51 there as objects).
  - Water: both draw it at street level (Vegas lake tiles 172 at surface y 0, Rio sea tiles 783 / 51 at 0, flags 0x80):
    water_level 40 (band 76). inside_follow on, no raised_ground (Vegas interchanges stay decks; Rio hills are slopes).
  - Lights: arms -x (Vegas TLIGHT01 2198, SLIGHT01 929, SLIGHT02 688; Rio TLIGHT01 770, SLIGHT01 580) -> turn 32;
    TLIGHT01 -> TLIGHT00, Vegas DLIGHT01 -> SLIGHT00; Vegas TLIGHT02 (46-unit pole) and Rio MLIGHT01 left unnamed.
  - Water slot: Vegas 426 (unnamed in-memory, never placed). Rio has no free slot < 900 (all placed / instance sources / LOD
    targets): new profile switch water_relocate moves D2 model 723 (in-memory, one object) to the last index (day 1256,
    night 1255: convert.relocate_water_slot on the parsed level + its objects in d2_extract_cached).
  - Rio specials: 10 and 12 need 21 slot entries; the slot page (8) has 12 own entries, <= 31 per page -> specials (8, 9, 11).
    Vegas / Rio special 8 / 11: 18 entries (special_slot_entries 18). Rio area_tex_limit 200 (220: 13 areas, 272 KB
    spool > 256 KB; 170: 43 areas, crash in the packer).
- **Converter fixes (Chicago + Havana byte-identical, re-checked: cheats6_day / hav6_day with all sidecars):**
  - Special car pages (minimap tile cache audit): Vegas' minor pages 64 / 19 hold used textures in both halves, only the
    UNUSED TSHADOW crosses the middle: such a page is flipped too (_flippable_used); a pair may also put its major page first.
  - d1models.is_tile: shape flag 0x2000 alone counts as a tile only with type-21 polygons; Vegas model 385 (0x2000, types
    10 / 11) was kept raw and the world renderer read its polygon block as a group table: 'FAIL-FAST unknown dispatch
    0x3A002A00, ra 0x80030B5C' whenever its area was drawn (also by driving). Now converted with a group table, 0x2000 cleared.
  - (Tried and reverted: rewriting D2 types 16 / 22 / 23. Driver 1 has them itself (Miami 16 / 17 / 22 / 23).)
- **Budgets:** Vegas day/night 9 areas, spool 200 KB, CLUT 373, halved 46.5 %, models 997; _xd 10 areas, 240 KB, CLUT 371,
  46.3 %. Rio day/night 27 areas, spool 196 KB, CLUT 367 / 366, halved 71.5 %, models 1267 / 1266; _xd 218 KB, 72.1 %.
  Rio's halving is high (texture-heavy city: ~200 textures per area).
- **In game** (devtest/polish, build-wip exe, package CHI_VEGAS_* / CHI_RIO_*, CHI_D2_ROW_CITY=2 / 3; test-only start override
  cityprofile CHI_START_<CITY>="x,z,rot" (D2 units; rot = D1 heading) for spots far from the start, never for conversions):
  - Vegas: drive day / night / XD (XPVS 729) PASS; police slots 1 / 2 spawn and chase (day, night); freeway ramps +1400
    (2 of 3) smooth; the 70-s and west drives that crashed before the is_tile fix pass. Lake: walled at all 4 approach
    spots tried (no drive-in, as D2's Lakeside).
  - Rio: drive day / night / XD PASS; police slots 1 / 2; ramps / overpass +1240..1390 smooth. Sea drive-ins blocked by
    shore objects at 3 spots tried (no drowning seen yet); the coastal 'void' strip shows no water tiles.
  - Runner caveat: a waypoint / spot pose over water or void drowns the car before the test starts (region waypoint is
    released); far poses still risk stale barrels -> use the start override.


## M3 Las Vegas / Rio wiring (Infrastructure 28.10., build-wip; Q68 B, levels Polish vegas1 / rio1)
- **Menu:** page 2 built from the package (page2_build at chicago_slot_activate): Chicago, Havana, Las Vegas, Rio rows are
  live when assets/<dir>/slot.bin exists (Miami's confirm: Day/Night), else grey. Runner menu paths take_a_ride/vegas|rio
  (page-2 rows 2 / 3). Pictures: assets/<dir>/preview.bin from design/previews/out/<NAME> (VEGAS accepted; RIO = v1
  placeholder until v2).
- **Per city via the set (no new code):** variants Vegas 6 / 7, Rio 8 / 9 (replay header / VARIANT_WORD), songs 12 / 13,
  14 / 15 (chase positions 0x12 / 0x10, 0xC / 0xA), skies after Havana's, D2 car sounds from the set's map, pause map +
  minimap frames (d2overlay VEGAS 288 x 672, RIO 416 x 576), sea word -40 -> BANDW 76 (water_level 40).
- **Glows (columns 4 / 5 of s_glow_words, Polish's geometry):** Vegas TLIGHT00 vertical heads (3 on the arm, D1 draws one
  set: the head at x 681), red / amber / green y -1368 / -1255 / -1142 (thirds, assumed), z 70; Rio x 947, y -1205 / -1101 /
  -998, z 13. Lamps: Driver 1 kind 2 (SLIGHT00, ONE glow, 0x8005310C / 14) and kind 3 (SLIGHT01, two glows, 0x80053118..):
  Vegas SLIGHT00 = D2 DLIGHT01 (double) -> one glow (1104, -3001); Vegas SLIGHT01 single (1136, -2598) -> (1092, -2568) x2;
  Rio SLIGHT01 (640, -1950) -> (596, -1920) x2. (Swapping Vegas' lamp names in the converter would give the double lamp
  both glows.) Words checked in game (havana_drive CITY=vegas|rio records them).
- **Checks (build-wip):** drive day / night / XD, chase_music (Vegas 12 -> 0x12, Rio 14 -> 0xC), car_sounds (D2 banks from
  the set), pause_map (Vegas / Rio centred, clamped, pans) PASS.
- **Drowning:** no reachable water edge in D2's own Vegas (lake walled) or Rio (shore objects) at Polish's 7 spots; the
  band words are set (76). Rio's 'void' coast strips (written water, no tiles) are Polish's coast pass.
- **Havana car_banks model 8:** MapCarIndexToBank: model 8 -> index 7 > 6 -> 4 -> car_banks[1][4] = 17 (the profile had 6):
  fixed in cityprofile (package only; the level is unchanged).
- **Runner pose:** a long pose's waypoint no longer releases the car (it drowned over water / void); it moves on held.
- **Rio "glitchy car" (Design capture): not a bug (Polish): box truck = D2 model 12, p2 = a pose inside a building. Was: geometry within D1s
  limits (player fit 227 polys / 128 verts; Rio models 2 / 10 carry type-18 polys that D1's car builder skips) -> car
  texture pages / CLUTs (Polish: flip / pair change suspected). Rio specials 10 / 12 need 21 slot entries (> 19): backlog.
- **rio2 / vegas2 (Polish 28.10.):**
  - Rio coast: the 'void' strips (land colour 15, no D2 surface) carry Driver 2's own sea tiles (51 / 777 / 783, tile + sea
    flag 0x80, surface y 0): profile sea_tiles_water marks the void cells under those tiles as water (5481 cells; our tiles
    + drowning; D2's tiles still draw on top at y 0). In game: beach -> blue sea to the horizon, a drive east from the start
    reaches the water and sinks. Rio drive-in spot (water-kind shore, no wall): D1 (370500, 21000) heading +x (drowns).
  - Rio halving study: areas are capped at 31 (the specials' area mask is an int32: 185 -> 32+ areas, struct.error). 220: 13
    areas, 78.9 %, spool 272 KB; 200: 27, 71.5 % (173 page units lost); 190: 30, 68.6 % (170), spool 200 KB = rio2; _xd keeps
    200 (190 overflows the mask). Per-area packing (CHI_POLISH_S1) would help but was dropped for the area-switch glitch (Q40 C);
    the real lever is C77 (D2-style VRAM layout, engine). Rio is texture-heavy (~200 per area vs Chicago ~150; Chicago 56 %).
  - Vegas lamps: D1 draws one glow for SLIGHT00, two for SLIGHT01: DLIGHT01 (double) -> SLIGHT01, D2 SLIGHT01 (single) ->
    SLIGHT00. Vegas' CLUT stays at 373 / 384 (11 free): any later texture / car-palette addition needs a CLUT check first.
  - C124 (Strategy / Infrastructure): player choice 0 = D2 model 1 (Take a Drive car) in Vegas and Rio, not the secret car 12;
    the player slot and civilian slot 1 share D2 model 1 (separate AI / player fits, damage rows per slot).
  - C124 converter side: D2 model 1 has no special pages, so Driver 1's pair-by-choice load (pair k = choice k) would have
    shifted every later choice onto the wrong pair: polish_cars.special_order keeps a BLANK pair (negative ids; convert
    writes empty pages, no CLUTs, no details) for a player slot without special pages. Chicago / Havana never reach it.
  - CLUT check (convert.clut_check, report only): it counted the FIRST special pair; with a blank first pair it now takes
    the largest pair. The largest pair is the real worst case (any choice can be loaded): cheats6 23 -> 25 (+2, 366),
    hav6 +5 (340), vegas1 +8 (381), rio2 27 (369). Vegas2 night = 381 / 384 (built with CHI_CLUT_MARGIN=3; the default margin
    4 stops at 380), day / xd 379: Infrastructure to confirm in game (overflow would corrupt the first area slot's palettes).
  - rio2 / vegas2 budgets: rio2 day/night 30 areas, spool 200 KB, CLUT 369, halved 68.6 %, models 1267 / 1266; rio2 _xd 25
    areas (limit 200), 198 KB, 71.4 %; vegas2 day/night 9 areas, 200 KB, CLUT 379 / 381, 46.5 %, 997; _xd 10, 240 KB, 46.4 %.
    In game (devtest/polish, build-wip): day / night / XD drive + police pass for both; Rio sea to the horizon on the
    former void strips; choice 0 = D2 model 1 in both.

- **28.10. rio2 / vegas2 (Polish):** Rio's coast 'void' strips carry D2's sea tiles (drawn, drowning); choice 0 = D2 model 1
  in both (C124; model 1 has no special pages: a blank pair for choice 0, choices 1-3 keep pair k). Vegas lamp names swapped:
  SLIGHT01 = D2 DLIGHT01 (double, kind 3: (+-1104, -3001)), SLIGHT00 = the single lamp (kind 2: (1092, -2568)); glow columns
  swapped in the plugin. Runner rio_water (havana_water CITY=rio at D1 (370500, 21000) heading +x): timer -> -1 (drowns).
  CLUT (Polish: largest special pair counted; vegas2 night 381 / 384, margin 3): runner car_choice (choice poked during
  the menu / load from a second debug connection; Take a Ride's script sets 0 at 0x80068A38) Vegas night choice 3 (D2 8,
  the 30-CLUT pair): no palette corruption seen on the car / world (start + 3 drive screenshots).
- **C125 night roads (Polish 28.10.): cause = Driver 2 darkens ground tiles in its renderer, not in its night textures.**
  REDRIVER2 tile.c DrawTILES: at night every tile is drawn with colour combointensity / 3 (NightAmbient 128 -> 42), in every
  city. Driver 2's NLEVELS road textures are 1.0 of the day ones in Chicago (the converter's 'as bright as by day' rule darkens
  them x0.3: fine) but 0.78-0.79 in Vegas / Rio and 0.63-0.68 in Havana, i.e. under NIGHT_KEEP_RATIO 0.8 -> kept as D2's
  'night designs' -> day-bright roads in Driver 1 (no renderer darkening). Fix (data, profile night_tiles_third for Havana /
  Vegas / Rio; Chicago unchanged, night re-checked byte-identical): at night every texture of a ground-tile model (shape
  0x0400) x 1/3 (Rio 28, Vegas 20, Havana 17 textures). Levels: var_polish_rio3_night / _xd_night, vegas3_night / _xd_night
  (CHI_CLUT_MARGIN=3, CLUT 381 / 379), hav7_night / _xd_night; the day levels stay rio2 / vegas2 / hav6. In game: dark
  roads at the three night starts (screens in devtest/_out/runner/20261028-0508..0512 polish_drive_in).


## C129 D2 traffic lanes study (Analyst 28.10., offline)
- **D2 road model (dr2types.h, dr2roads.h):** STRAIGHTS2 (lump 40, 28 B: Midx, Midz, length, bing, angle 0..4095 any
  value, ConnectIdx[4], NumLanes, LaneDirs, AILanes, pad), CURVES2 (41, 28 B: Midx, Midz = arc centre, start/end
  angle, ConnectIdx[4], gradient, height, NumLanes, LaneDirs, inside = inner radius in 1024 units, AILanes),
  JUNCTIONS2_NEW (43, 12 B: ExitIdx[4], flags; bit 0 = lights, else yield rules). Surface ids: straight id,
  0x2000|junction, 0x4000|curve; position -> id via the surface planes (GetSurfaceIndex = sdGetCell plane.surface - 32,
  RoadInCell for spawns). NumLanes: bits 0-3 lane units (1024 wide, 2 x 512 sub-lanes), bits 4-5 speed id
  (speedLimits 56/97/138), bit 6/7 left/right outer sub-lane = parking; LaneDirs / AILanes bit per unit.
- **D2 civ AI (civ_ai.c):** each car keeps a 13-entry route ring (CIV_ROUTE_ENTRY dir, pathType, distAlongSegment,
  x, z; CIV_STATE ~250 B). CreateNewNode adds nodes every 1024 units on straights, every 128/64/32 angle units on
  curves (inside < 10 / < 20 / else) along the lane (GetNodePos: straights = Mid + dist*(sin,cos) + sideShift
  (NumLanes*512 - lane*512 - 256)*(cos,-sin); curves = Mid + (inside*1024 + lane*512 + 256)*(sin,cos) of start+dist);
  lane changes slide by 128 per node (changeLaneCount). At a segment end GetNextRoadInfo follows ConnectIdx: straight
  <-> curve <-> straight directly, or a junction: 4 exit slots relative to the entry (turn -1024/0/+1024), left
  lane = left/straight, right lane = right/straight, lights (junctionLightsPhase[exitFrom & 1]) or yield; corner
  nodes (pathType 1) built from cornerAngle. CivSteerAngle/CivFindPointOnPath steer the physics car toward a look-ahead
  point on the node path, CivAccel/CivAccelTrafficRules give speed (maxSpeed = speedLimits[speed id], car-ahead,
  lights, junction yield). CheckChangeLanes: random/park lane changes with a collision check; parked cars via
  CreateStationaryCivCar on parking sub-lanes. Spawn: PingInCivCar samples RoadInCell around the player.
  Cops: patrol cars are civ cars until PassiveCopTasks -> InitCopState (CONTROL_TYPE_PURSUER_AI); pursuit uses the
  pathfind.c obstacle/distance map (MapHeight based, omap 128x128) + FindCost, NOT the lane network. leadai.c (mission
  getaway cars) walks straights/curves directly; felony.c reads road info for the player (wrong-way etc.).
- **D1 model:** ROADS 16 B (id, ConnectIdx[2], NumLanes, LaneDirs, length, flags, pad, x, z), JUNCTIONS 44 B (4 entries
  fromJunc/road/flags/extra, cardinal slots 0 -z, 1 +x, 2 +z, 3 -x), ROADBOUNDS = axis-aligned cell rectangles, road
  map cell rot 2 bits. No angle or curve field anywhere. AI: mode 0..3 = the 4 axis directions (exit slot), lane line
  0x80014FC4 = corner*1500 +- lane*1500 on ONE axis (+0x40 = x line, +0x44 = z line, 0x7FFFFFFF none), 0x80017780
  snaps the car onto that line (|d| < 33) or pushes it sideways (d/32 or d/8 into 0x8009B324), headings quantised to
  quadrants (& 0xC00, 0x8001262C), turns only inside junction boxes (0x80021820 cell 0x4000|id, picker 0x80016F0C).
  ROADS readers: civ AI 0x80012E98..0x80019314, player rules 0x8001A9BC (-> 0x8001AC18 / 0x80020AE4, red light
  0x8001AE14), map helpers 0x800213C8/0x80021820/0x80021DE8/0x80021F5C, script 0x800651F0 -> 0x80019314, 0x800394E0.
- **Numbers** (scratch c129_roads.py / c129_diag.py; axis = within 8/4096 of an axis):

  | city | straights (off-axis) | off-axis length | curves (AI) | mean span | junctions (lights) | D2 road lumps |
  |---|---|---|---|---|---|---|
  | Vegas | 525 (74: 66 at ~45 deg) | 13 % (1.3 M units) | 157 (145) | 78 deg, 105 >= 90 deg, r 5-25 k | 184 (0, all flags 2 = yield) | 21.3 KB |
  | Chicago | 779 (2) | 1 % | 151 (151) | 98 deg | 252 (239) | ~29 KB |
  | Havana | 611 (17) | 3 % | 126 (121) | 78 deg | 332 (17) | ~25 KB |
  | Rio | 655 (6) | 1 % | 185 (182) | 88 deg | 279 (63) | ~27 KB |

  Vegas links: straights -> junction 1094, -> curve 452, -> straight 360; speed ids 380 slow / 6 mid / 139 fast;
  parking on 286 straights. Our converted vegas.lev (probe d2_cities_2): 282 D1 roads, 209 junctions; d1roads forces
  every non-z straight onto the x axis (`axis = "z" if a < 8 or a > 2040 else "x"`), curves become corner junctions
  only. Measured: 5 % of the 74 diagonals' centre line lies on a D1 road rect (0 diagonals > 50 % covered; the 12
  roads touched are axis strips crossing them), curve centre lines 15 % (axis straights 60 %, the rest = junction
  boxes / dropped). So Vegas has practically no traffic on diagonals and curves today.
- **Options:** (A) translate to D1 format: impossible to be exact (no angles, one-axis lane lines, quadrant
  headings, 90-degree box turns); at best staircase approximations. (B) D2 civ AI as guest code for D2 cities:
  D2 road lumps resident in guest RAM (21-29 KB/city), D2 CIV_STATE per AI car (~250 B x cars), port of civ_ai.c's
  road-following subset (InitNodeList, CreateNewNode, GetNodePos, GetNextRoadInfo, CheckChangeLanes, CivFindStation /
  FindPointOnPath / SteerAngle, CivAccel(+TrafficRules), PingIn spawn by straight/curve search like leadai.c, no
  surface grid needed) compiled with a PS1 MIPS toolchain into a level-loaded overlay (code est. 15-25 KB; too big
  for exe caves) and hooked at D1's per-car AI entry (0x80013D88 and the mode/lane writers) for D2 slots only.
  Output to the D1 car: the open item is D1's AI drive interface (research_traffic: throttle/steer not found; D1
  moves civ cars along axes with direct lateral velocity 0x8009B324): either kinematic follow (set heading +
  speed toward the D2 path point each frame; exact paths, robust) or locate D1's physics control inputs (D2-like
  feel, more risk). Felony (0x8001A9BC) and red-light checks still read D1 roads: keep the D1 network as is for
  them or give them a D2 road lookup. RAM ~45-60 KB total per D2 city (data + code + state); CPU like D2's own AI
  on PS1 (it shipped at that cost). Recommendation: (B) with kinematic follow first, Vegas first; D1 roads kept for
  player rules/cops until (B) is proven. D2 lights (global 2-phase) map onto D1's cycle; Vegas needs the yield path.
- **Verification plan:** offline: a Python model of GetNodePos/CreateNewNode on Vegas data printing node paths for
  10 diagonal/curve routes, compared with the guest port's traced nodes (exact match). In game (runner, Vegas):
  trace AI car (x, z, heading) at 10 Hz on 3 diagonal boulevards and 3 large curves; pass = path within 256 units of
  the D2 lane line, heading within 64/4096 of the tangent, no axis snapping, speeds = speedLimits per road; compare
  with the same routes in D2 (REDRIVER2 or emulator capture of D2 Vegas); junction turns from diagonal roads,
  yields at flags-2 junctions, no stalls in 10 min, then Chicago/Havana/Rio regression.
- **C128 Vegas night checkup vs Driver 2 (Polish 28.10.).** D2's night (REDRIVER2):
  - buildings / props: draw.c PlotBuildingModel colour = f4colourTable from SetupPlaneColours(combointensity); at night
    combointensity = NightAmbient 128 = 0x808080 and with no weather every plane = ambient: NLEVELS textures drawn as they
    are (1.0), FLAT (no per-face shading). Ground tiles: tile.c combointensity / 3 (C125). Sprites (trees): draw.c
    lightLevel / 3 (Chicago: x2, the 'level bug'). Cars: cars.c night_colours 880 / 905 (vs day 3200) = about 0.28.
  - lights: objanim.c per city / model: Vegas TLIGHT01 (3-head arm, AddTrafficLight x9), TLIGHT02 (POLE: (-4, -537 / -466 /
    -395, -41)), SLIGHT01 AddLightEffect (-840, -1972, -61), DLIGHT01 (+-865, -2249), SLIGHT02 AddSmallStreetLight
    (-620, -101) + AddLightEffect (-620, -1618); Rio TLIGHT01 (-719, -906 / -837 / -762, -22), TLIGHT02 (0, -654 / -578 /
    -509, -21, unplaced), SLIGHT01 (-497, -1437); Havana 0..4 as named; plus lamp streaks (debris.c PreLampStreak / ShowFlare).
  - Differences found in our Vegas night (vegas3) and their fix:
    1. (data, FIXED vegas4) the converter's 'as bright as by day' rule (x0.3, Chicago's look) dimmed 79 Vegas model textures
       that D2 draws at 1.0, incl. the casino signs (FLAMINGO 1.04, IMP01-05 up to 2.46, WSIGN 1.42, NEWY-01..05, EXC,
       MONTENT1, BEGIOM, BELL02, SPHXPAW, DTSYN, MISCSNS, TISNTOP1, SYN-DET1, COKE, MNTDEW ...): neon dull. Profile
       night_models_d2 (Vegas): night model textures stay as D2's NLEVELS, tiles x1/3 (C125), sprites x1/3. In game the
       Flamingo sign is lit (shots 20261028-103908 vegas3 vs -103955 vegas4 polish_drive_in).
    2. (data, FIXED vegas4) TLIGHT02 = D2's pole traffic light was unnamed -> no glows: renamed TLIGHT01 (Driver 1's pole kind),
       turned 48 like Chicago's; lenses (+x face) at (54, -709 / -615 / -521, -5) D1 units (D2 x1.32 after the turn).
    3. (engine) D2 draws night buildings flat (all planes = ambient); Driver 1 keeps its per-face light shading.
    4. (engine) D2 cars are lit at ~0.28 at night (night_colours); Driver 1's night car lighting is its own.
    5. (engine) glows: SLIGHT02 (single lamp + small street light) has no Driver 1 kind (CITY 3 list: TLIGHT00/01,
       SLIGHT00/01); D2's lamp streaks / flare sizes and colours (type 0, colour 3) vs Driver 1's glow sprites.
    6. (Infrastructure, C126) sky.
  - vegas4 levels: day / night / _xd_day / _xd_night (CHI_CLUT_MARGIN=3; CLUT 381 / 379, 9 / 10 areas, spool 200 / 240 KB,
    46.5 %); in game drive day + police, night + XD (XPVS 729) pass.
  - Other cities (same check): the x0.3 rule also dims lit textures D2 draws at 1.0 - Chicago 55 model textures (lit
    signs: CHICTHE1 / CHICTHE2 = Chicago Theatre sign 1.38 / 1.53, BIOGFRNT 1.26, CGTSGN03 / 04, DTL10, WALL4DRK), Havana 10
    (BLAMP2 lamp head 2.09, LPOSTN5 1.13), Rio 20 (heli SIDEHELI / WINDHELI). Chicago's look is user-approved (decision).
    D2 Rio SLIGHT01 has a light effect (-497, -1437) = our glow head (640, -1950) after the turn: consistent.

- **C129 prep (Analyst 28.10.): reference model, D1 drive interface, toolchain.**
  - `chicago/devtools/c129_ref.py` = line-by-line Python model of civ_ai.c (InitNodeList, GetNodePos, CreateNewNode incl.
    left-turn corner nodes, GetNextRoadInfo incl. junction lane rules / lights-yield state / straight-curve lane fit,
    Left/RightBoundLane, CivFindStation / FindPointOnPath / SteerAngle) + a kinematic follower with a yield brake ramp
    (path shape only; no CheckChangeLanes, parking, other cars). rcossin = round(4096 sin) = D1's PsyQ table 0x8008EAA8
    (4096/4096 equal); ratan2 = atan2 (+-1). Vegas run (seed 1, 900 frames): 10 cases, 0 confused: 4 diagonals
    (S204/S202/S209/S201, follower within 18-23 units of the node line), 3 curves (C102 r 22k, C9, C4; 13-283),
    junctions from diagonals: J173 L into curve C27 (493: corner cut), J170 S, J170 R (321). Output devtest/_out/c129/
    (cases.json events, routes.csv nodes with D1 coords, traj.csv, sheet.png). Note: Vegas junctions are all flags 2
    (yield, no lights); some diagonal junctions allow only S from inner lanes (D2 lane rules).
  - **D1 drive interface (static):** AI records 0x80098950 + 0x50 * i (22), car = 0x8009B0A4 + (id + 1) * 0x18C
    (id = record byte 0; car 0 = player). Car: +0x18/+0x1C/+0x20 position (where.t, snapped by 0x80017780), +0xF8 heading
    (4096), +0xF4 steer (wheel angle, +-0x200), +0xF0 thrust, +0x108 speed (record +0x38 = signed copy), +0xC8/+0xD0 a
    second position (player map reads car 0 +0xC8; the dispatcher adds 500 units along the heading each frame before
    the AI's cell probes; role to confirm by one trace), car +3 = 0 marks AI control (0x8001D608 adds the car to
    active_car_list -> normal physics). Per frame (dispatcher 0x8001A30C): state handler table 0x8008539C[record+1]
    (2 = 0x80017DE8 drive: 0x80021820 cell probe, 0x80018100 steer = DIFF(heading, mode << 10): diff / 2 under 0x80,
    else +-0x200 -> car +0xF4; if |diff| < 0x40, 0x80017780 lane hold: |d| < 33 snap +0x18 / +0x20 and steer 0, else
    steer d / 32 (or / 8)); 3 = 0x800181B4 junction), then 0x80013D88 speed: target record +0x3C (0x800142CC: cruise
    130/162/194/226 by record +9 & 3 from 0x800852FC, dist / 24 under 3500-3800 to the junction, 0 under 650 or when
    0x80018F44 blocks; 0x8001262C car-ahead check with quadrant headings & 0xC00 -> 0), thrust car +0xF0 =
    clamp(target - speed, +-32) * 5000 (accel) / 7000 (brake) >> 5; then 0x8001D608.
  - **Minimal D2 hook (guest):** table words 0x800853A4 / 0x800853A8 (states 2 / 3) -> one D2 handler for D2 slots: keeps
    the D2 node ring per record (22 x ~256 B), writes car +0xF4 = clamp(DIFF(car +0xF8, ratan2(look-ahead - pos)),
    +-512) (D2 CivSteerAngle, same +-512 range as D1's steer) and record +0x3C = target speed from the D2 road
    (speed class, yield ramp); 0x80013D88 needs a D2 branch at its record[3] / 0x800142CC step so the target is not
    overwritten (its thrust law can stay). No 0x80017780 snap, no D1 junction cells for these cars. Spawn: hook after
    0x800154A8 (D1 spawn) or replace 0x80016B24's pick with a D2 PingInCivCar (lane point near the player). Speed units
    D1 car +0x108 vs D2 56/97/138 to calibrate by trace. 0x8001262C (car ahead) works by quadrant: fine first, D2's
    box check later.
  - **Toolchain:** no PS1 compiler in D:/recomps. Only exe_patches.py `asm()` (hand MIPS for caves) and an llvm-mingw
    clang 22 (C:/Users/domin/.local/share/retcomm/...; no MIPS backend: "No available targets ... mipsel"). LLVM lacks
    MIPS I load-delay handling anyway; fit: GCC mipsel-none-elf (as PSn00bSDK uses), `-march=r3000 -mabi=32 -msoft-float
    -mno-abicalls -fno-pic -G0 -O2 -ffreestanding -nostdlib`, linked at a fixed guest address (linker script) with D1
    symbols (0x8008EAA8 rcossin, car / record bases) as absolute symbols; ratan2 / SquareRoot0 ship in the overlay
    unless found in D1's libgte. Loading (PS1-native): the overlay blob travels in the D2 city's LEV (an extra lump or
    appended to the D2 road data lump) or as a file next to it, copied by a small cave loader into a reserved RAM range
    at level load (fixed link address, no relocation), entry via the two table words. psxrecomp runs such code: runtime
    overlays are captured -> interpreted until compiled -> native cache (README "Capture-and-compile for overlays");
    exe-cave changes still need the regenerate step.
- **C128 rule for Havana / Rio + Q73 switch (Polish 28.10.):** profile night_models_d2 on for Havana and Rio too (lamp heads
  BLAMP2 / LPOSTN5 lit, heli textures as D2): var_polish_hav8_night / _xd_night (day stays hav6; CLUT 335 / 336) and
  var_polish_rio4_night / _xd_night (day stays rio2; CLUT 369 / 365); in game night + XD drive and police pass. Chicago
  (Q73, user decision): CHI_POLISH_NIGHT_D2=1 applies C125 + C128 to any city (tiles x1/3, sprites x1/3 (D2 itself draws
  Chicago's trees x2: its 'level bug', not copied), other textures as D2's night level: Chicago Theatre / Biograph signs
  lit); test level var_polish_q73_night.lev (cheats6 recipe + the switch, CLUT 364); without it Chicago night stays
  byte-identical (re-checked).


## R65 fixes (Infrastructure 28.10., build-wip / build-test 7d20d592)
- **C126 every D2 city showed Havana's day sky:** sky_vblank only rewrote LoadSky's immediates (0x8004EDE0 / EC / EE00)
  when they held LA's 2 / 3 or Chicago's 13-15; after the first D2 city with a sky >= 16 (Havana day 16/17) the words stuck
  for every later city / time. Now any package sky (13..63) is rewritten. Runner `sky_check` (FIRST=<city> played first,
  then CITY [NIGHT=1]; immediates vs the slot sidecar's first sky + night / rain): old exe stuck at [16, 18, 18], fixed
  Vegas night [20, 21, 21]; suite: havana->vegas, vegas->chicago night, chicago->rio night, rio->havana PASS.
- **C127 sound at the start of loading a D2 map (after any map was played):** the R36 car-sound code restarted car
  channels (key-on) while the next level loaded: the previous level's channels still owned voices 0 / 1, and the player
  slot was placed provisionally in the music block's tail that the load was refilling (spu_voices 0.3 s after the
  confirm: voice 0 vol 0x3F90 at 0x3CB30; tap 3 RMS ~15000 for ~1 s, Miami -> Chicago on 6162815a). Now s_sx_live (game
  frame counter moved in the last 8 vblanks): steps 2-5 only in a running level; outside, sx_restart retargets and keys the
  voice OFF. Runner `d2_load_sound` (FIRST map, quit, D2 map: MMIO key-ons + tap 0 / 3 RMS per 0.1 s from the confirm):
  silent for miami->chicago, chicago->havana, havana->vegas; car_sounds unchanged.
- **C130 Rewind as its own Mods setting:** driver.personal feature `rewind` ('Rewind', Quality of Life, default on;
  build-wip / build-test manifests, mods/preloaded untouched). The runtime applies the launcher's rewind switch after mod
  activation, so driver_personal_rewind_vblank() (called from driver.chicago's model-table vblank) applies the feature on
  the first vblank: on / off regardless of the launcher. Runner `rewind_setting` (WANT=on, and CHI_FEATURES_OFF=
  driver.personal:rewind WANT=off; new env in dt.write_state / session) PASS.
- **C131 'Chicago' section -> 'Full Pro experience':** build_package manifest: package name 'Full Pro experience' (+ warning
  description), group 'Full Pro experience' (3 features), model-table 'Engine Extensions (required)' with the warning
  (required for all custom Driver 2 maps and the custom map changes: Newtown, LA by day, Interview / Desert ...),
  chicago-slot 'Driver 2 cities (own Take a Ride rows, Los Angeles restored)'. Ids unchanged (package driver.chicago,
  feature ids): state.toml, probes, playable copy and plugins key on ids only (grep: no code reads group / names).
- **C133 pole traffic light glows (vegas4 TLIGHT02 -> D1 kind 1):** exe cave LGTY 0x8008A378 (from the glow helper's draw
  call 0x80053810): an x argument >= 0x2000 = kind 1 with its own height: x -= 0x4000, y += LGDY (0x80093638), z += LGDZ
  (0x8009363C). Plugin: Vegas kind-1 word 0x24064306 (lens x 54 + 720 + 0x4000), LGDY +659 / LGDZ -75 (arm head -> pole
  lenses; amber / green 19 / 38 low); 0 elsewhere. C17 cave end tightened to its code (0x8008A378).
- **Levels:** vegas4 (day / night / _xd), hav8_night (+ _xd_night; day hav6), rio4_night (+ _xd_night; day rio2).
- havana_ramp judges only the ramp (until street level + 3 samples): later bumps made it flaky in suites.
- **vegas5 (C132 c, Polish 28.10.):** profile resident_models=("SLIGHT02",) -> convert.make_resident moves the D2 area model
  into the in-memory lump on the parsed level (Driver 1 resolves glow models by name at load, FUN_80052A78); SLIGHT02 is in
  no area list. Head (lamp quad PARK03) (815, -2156, 4) D1 units after the turn 32. Levels var_polish_vegas5_day / _night /
  _xd_day / _xd_night (CLUT 381 / 379, spool 200 / 238 KB). Open observation: downtown start (D2 172000, 682000) + 1.5k north,
  colour noise next to models 46 / 47 (SHOP01A / GHOSTMB / STN2RAIL, areas 7 / 8), also in vegas4.
- **C134 Vegas downtown 'shop glitch' (Polish 28.10.): engine side (minimap), not the shop model.** At the downtown start
  (D2 172383, 678898) the colour noise sits around the minimap frame (screen x 375..520, y 141..238). GPU capture
  (scratchpad vr/cap_shop/cap.json): 16 semi-transparent 32-px quads, tpage 12 (VRAM 768, 0), CLUT 15380, UVs u 155..250 /
  v 30..125 = Driver 1's 4 x 4 minimap tile cache, drawn unclipped beyond the frame and holding garbage, while the map inside
  the frame is right. Same in vegas1 (no blank C124 pair) and vegas4 / vegas5, so not the car pages. Our minimap lump is
  clean (all 189 tiles decode; the downtown window cols 477..605 / rows 158..286 lies inside the 672 x 288 map, toptile 189).
  The shop models 45-48 (SHOP01A / GHOSTMB / STN2RAIL / WALL5 / S-SYN04, page 12, areas 7 / 8, types 10 / 11) are the same
  objects as D2's (42 objects in the box, identical) and draw fine; the dark band under the car is no geometry (D2 has no
  ground tiles there either: roads / paths only) = Driver 1's clear colour.


## C132 D2 night look + C134 frame clear (Infrastructure 28.10., build-wip; Strategy go)
- **Where Driver 1 shades (subagent study + own):** D2 cities run their nights with night flag 0 and LOOK_CITY 3, so Driver 1
  uses its DAY facing colours (FUN_8002D0F4 day branch: scratchpad 0x1F800024..43 = 0x808080 / 0x707070 / 0x606060 /
  0x505050 / 0x404040 by 45-degree facing, lui/ori immediates 0x8002D464..88) and LA's night car colour (DrawCar
  FUN_8003A698: LOOK_CITY 3 -> 0x800971A0 = 0x282828, lui/ori 0x8003A6D0 / D4; one flat colour for every car body poly,
  player and AI; wheels / far cars / later generic drawers read the same word). No GTE car lighting in Driver 1.
- **(a) + (b) (plugin night_look_vblank, CHI_C132_LOOK=0 off):** while a D2 city runs at night the four darker facing
  immediates become 0x808080 (flat, D2 SetupPlaneColours: every plane = ambient) and the car word 0x242323 (D2 night_colours
  880 / 905 of 3200); Driver 1 values otherwise (LA night keeps 0x282828, D1 nights use their own night branch).
  **psx_mod_write_code_word is required** for code immediates: psx_mod_write_word left the native block stale (car colour
  sampled 0x282828 until switched). The glow (s_glow_words) and sky (sky_vblank) immediates now go through the same call:
  before, the D2 glows were drawn with Driver 1's native constants (Havana night shots: lamp glows appear only now).
- **(c) glow kind 4 = SLIGHT02 (exe c132_patches, one shared window):** CITY 3's glow table already holds a 5th entry
  {4, 0, "SLIGHT02"} (count 4 at 0x8008AE68); cave K4 0x8008A6A0 from the dispatch default 0x800530D8 draws one lamp glow
  (like kind 2) at LX4 / LY4 (0x80093640 / 44); the plugin sets count 5 + Vegas (771, -2126) (vegas5 head (815, -2156)
  + (-44, +30)) only while Las Vegas is chosen (vegas5 keeps SLIGHT02 in memory; resolved by name at load).
- **Build note:** this generate grew the generator's shard count (48 -> 54 files): build-wip needed a cmake reconfigure
  (`cmake build-wip`), else link errors on the new shards' functions.
- **C134 Vegas Fremont 'noise' = no frame clear:** Driver 1 never clears the frame (sky + ground cover it); D2 maps have
  spots without ground geometry (Fremont start: D2 has roads / paths only), so old VRAM showed (the minimap-cache quads
  Polish found are clipped by the draw area E3/E4 and were not the cause; MAPD2 off changed nothing). Plugin
  clear_bg_vblank: both DRAWENVs (0x800BDFB4 / 0x800BE034, +0x18 isbg r0 g0 b0) isbg = 1, black, while a D2 city runs
  (CHI_C134=0 off; D1 cities unchanged). Runner `c134_clear` (start CHI_START_VEGAS 172000,682000: neighbour difference
  beside the minimap 40.3 off -> PASS on). The hole itself stays black (as D2's clear).
- Runner `night_capture` (CITY / NIGHT / POSE, screenshot, night-look words, car colour samples, optional GPU frame).

## C135 probe q73 freezes / crash (Infrastructure 29.10., build-wip; user laptop session 28.10. 17:26-17:53, exe 7d20d592)
- **Four events, two causes.** Dumps 17:30 / 17:43 + psx_crash.txt (FAIL-FAST 0x04200374, ra 0x80077AC8, last store
  0x80077AC4) = cause 1; dump 17:37 (in FUN_8002E230's far-car loop, ra 0x8002E650, s0 0x9F0E0554) = cause 2.
  Not the C109 GPU-timeout family, not C126 sky / C127 load-sound code.
- **Cause 1: stale CITY opcode (extras via LA).** Newtown / Desert run LA's Take a Ride 0x7C with CITY_OP_WORD 0x800689F8
  (`lw v0,4(t0)` -> `addiu v0,zero,7/6`). The plugin wrote it with psx_mod_write_word: RAM changed, the native block kept
  its old instruction (it picks the change up only at some later invalidation), so a ride ran with the PREVIOUS choice's
  city id. With the wrong level-table entry the loader read REPLAY.BLK (LBA 15522-15712) into 0x80114600 /
  0x801E0E6C, past 0x80200000, wrapping onto 0x0: exception vectors + BIOS tables gone -> unknown dispatch 0x04200374.
  The 17:37 session's log ('Los Angeles day' -> 'mission 0xAE (level 2)' -> level 6) is a menu path: LA's Day/Night
  screen, back, cursor over Interview (the mission swaps to 0xAE while browsing, harmless: the confirm rewrites 0x7C),
  confirm Desert. Fix: CITY_OP_WORD and switch_words through psx_mod_write_code_word (all plugin code-word writes now do).
  build-dev 6162815a has it too (crash reproduced on an exact copy).
- **Cause 2: special-car block overflow across cities.** specials_vblank gave each special id ONE guest block, sized for
  the first city's special of that id; later cities copied theirs into it. Rio 8 (13684 B) into Vegas 8's block (13460 B):
  the low model's last 224 bytes lay in the next allocation (Vegas 10's block in the runner, another owner in the user's
  session); when that owner wrote, the far-car drawer (lbu type byte, no & 0x1F, table 0x80089FFC) read garbage and
  jumped into nowhere. Chicago 9 -> Havana 9 overflowed by 140 B too (build-dev). Fix: per-slot capacity (>= 16 KiB;
  every special so far <= 14.6 KiB), re-allocated when a bigger one arrives. Host-only (M8: a fixed 16 KiB buffer per
  special slot in guest RAM).
- **Runner:** `extra_load` (CITY=newtown|desert|interview: CITY id, opcode, frames moving), `menu_route` (LA Day/Night ->
  back -> over Interview -> confirm TARGET=desert|newtown; needs CHI_LA_DAY_LEV for LA's Day/Night screen; old exe:
  FAIL-FAST 0x04200374 = the user's crash), `special_swap` (FIRST=vegas CITY=rio, CHI_SPC_CYCLE=3: special blocks never
  overlap, low models' polygon types valid; old exe: Rio 8 overlaps Vegas 10).
- **Regression (build-wip d4ea9929 -> build-test, marked 30.10. 00:14):** 26 runs PASS (extra_load x3, special_swap x2,
  cheats_menu, replay_header, nightmare_start, cd_restore, city_switch, shadow_bus, havana_drive x3, sky_check x2,
  d2_load_sound, car_choice, night_capture x2, c134_clear, rewind_setting, ship_check, flip_wreck rerun).
- **Side finding (not C135, rare, test-induced):** flip_wreck crashed once in ~28 runs (FAIL-FAST 0x000000B0, same
  ra 0x80077AC8): the flipped Miami car slid ~173000 units (z 420k -> 593k) into the sea on its roof; the in-game area
  spool then read from 0x801852BC over 0x80200000. Miami, no D2 data. Runner `wreck_end` (flip_wreck's order + 30 s with
  dma_cdrom_history logging) did not reproduce in 5 runs. Open: does Driver 1's spool size an off-map / sea area wrongly?

## C137 sound inventory (Analyst 30.10., offline: ghq + exe disassembly + disc data; scratch c137_banks.py / c137_budget.py)
- **SPU blocks (InitSound 0x8004D3DC, same in every city):** bank 0 0x28000 (D1 VOICES lump 0, 163,956 B, base 0x1010),
  bank 1 0x400, music 0x19000, mission bank 4 0x21800, bank 3 0x10000 (VOICES lump 1 = police radio, 64,964 B), reverb
  43.5 KB, system 4 KB, ~5.5 KB unallocated. Bank 0 table 0x800BCA74 {addr, size, loop, rate} x 32.
- **Bank 0 samples and their users (call sites with immediate args, D1 exe):**

  | s | bytes | rate / loop | user (call site) | D2 cities today | verdict |
  |---|---|---|---|---|---|
  | 0 | 14096 | 11025 | crash: ch 2 GlobalTimeStep 0x8001C960, StepOneCar 0x8001DCB8, 0x8003FF0C (0x80040430/748), 0x80066778 | played | keep (no D2 crash wired) |
  | 1 | 57744 | 22050 loop | engine, ch 0 / 7 / 8 (FUN_8004C438) | space reused by D2 civ engines / horns (plugin) | dropped already |
  | 2 | 15440 | 22050 loop | idle, ch 1 | reused (same block) | dropped already |
  | 3 | 24800 | 22050 loop | skid, ch 3 | played | keep |
  | 4 | 1920 | 11025 loop | **the siren**: ch 5 / 6 (0x8004C528 / C554), moved to cop cars with car +0x12E == 1 and pitch-swept by phase (record +0xD) in 0x8004CA5C | played (D1 siren in D2 cities) | drop once the D2 siren is loaded |
  | 5 | 6000 | 22050 loop | no static caller (mission script events 0x8006A6C8 take bank / sample from data) | unknown | keep (runtime check) |
  | 6 | 9648 | 11025 | AI horn 0x800180D8: sample 6 + (id & 3, 3 -> 2) | **D1 horns still sound in D2 cities** (any voice) | drop after redirect to D2 civ horns |
  | 7 | 4560 | 11025 | AI horn (same) | same | drop after redirect |
  | 8 | 4144 | 22050 | player horn R1 0x800234D4 (ch 4) + AI horn | plugin retargets ch 4 to the D2 player horn; AI use as 6 | drop after redirect |
  | 9 | 4800 | 22050 | no static caller | unknown | keep (runtime check) |
  | 10 | 1024 | 22050 | BOX_TASTIC hit (smash table 0x8008AE8C via 0x8003FF0C) | played | keep |
  | 11 | 2976 | 22050 | cones / TRAININGCONES hits (pitch 800) + player suspension bump StepOneCar 0x8001E514 (any voice) | played | keep (**not the siren**) |
  | 12 | 4560 | 22050 | barrel / phone / parking meter hits | played | keep |
  | 13 | 10224 | 22050 | bin / barrier / table / chair / umbrella / sign / news / fence hits | played | keep |
  | 14 | 944 | 22050 | no static caller | unknown | keep (runtime check) |
  | 15 | 816 | 22050 | no static caller | unknown | keep (runtime check) |

  Correction to "Sirens (open, SPU budget)": sample 11 (0x24340) is the cone / bump sound (the "voices 10-15 in a chase"
  were cone hits and the player's suspension bumps); Driver 1's siren is sample 4 (0x1C5E0) on channels 5 / 6.
- **Other banks:** bank 3 (police radio) is used in every city: speech queue 0x8004C96C -> channel 9 via 0x8004CF50
  (felony callouts 0x800650E4 samples 7 / 10, 0x800635C0 sample 8, mission events); no D2 cop phrases are wired -> keep.
  Bank 4 (Take a Ride = VOICES lump 2, 117,108 B, tail 20,108 B = the special's engine): samples 0-6 are queued by
  0x8006B9D8 (random 100 + rand % 7 on driving events, condition table 0x8008C354) and mission script events; whether Take
  a Ride fires them is a runtime question (if never, 117 KB would be dead in every D2 city) -> keep until checked.
- **Today's use of the replaced space (car_sfx.bin of probe d2_cities_4, plugin step-1 algorithm):**

  | city | civ banks | civ engines / idles / horns | 2 reserved horns | free in s1-2 (73,184) | music tail - player engine | mission tail - special |
  |---|---|---|---|---|---|---|
  | Chicago | 12 / 4 / 13 | 59,200 | 12,672 | 1,312 | 21,740 - 18,992 = 2,748 | 20,108 - 18,992 = 1,116 |
  | Havana | 10 / 11 / 7 | 59,312 | 7,936 | 5,936 | 28,252 - 18,992 = 9,260 | 1,116 |
  | Las Vegas | 14 / 3 / 4 | 55,504 | 12,000 | 5,680 | 25,356 - 18,992 = 6,364 | 1,116 |
  | Rio | 8 / 7 / 13 | 56,928 | 12,672 | 3,584 | 29,004 - 18,992 = 10,012 | 1,116 |

  (music tail = 0x19000 minus the larger of the city's day / night D2 song banks.)
- **D2 sirens (VOICES2 69 + GameLevel, `& 2` cities 69 + (level & 1) * 2):** one 8 kHz loop each: Chicago 69 = 6,048 B,
  Havana 70 = 14,848, Las Vegas 69 = 6,048, Rio 71 = 12,336. Today none fits the s1-2 space; Vegas fits the music tail
  (6,364), Havana / Rio only there too, Chicago nowhere.
- **Freed by the rule:** s6 + s7 + s8 = 18,352 B contiguous (bank 0 +120,000 .. +138,352 = SPU 0x1E4D0 .. 0x22C80), +
  s4 1,920 once the D2 siren takes over = 20,272 B (beyond the 73,184 B of s1-2 already reused). Every D2 siren fits the
  s6-s8 hole (largest 14,848; 3,504 B left), in all four cities, without touching the music / mission tails.
- **Must not break:** (1) the player-horn trigger: the plugin recognises R1 by channel 4 starting at table entry 8's ADDRESS
  (c4a == s8) - keep an entry-8 address or switch to the call site 0x800234D4; (2) AI horns 0x800180D8 play table entries
  6-8 on any voice: point entries 6 / 7 / 8 at the city's D2 civilian horns (slots 24-26) before the data goes; (3) the
  siren: D1 sweeps the pitch of channels 5 / 6 (0x8004CA5C, phase-based) while D2's siren sample already contains the
  wail (D2 plays it at a fixed pitch, gamesnd.c Start3DSoundVolPitch(..., 129)) -> with a D2 siren in entry 4 that sweep
  must be neutralised (fixed pitch for 5 / 6) and the rate set to 8000; (4) keep crash s0, skid s3, smash / bump s10-13,
  the unknown s5 / s9 / s14 / s15, bank 3 radio, bank 1 and FESAMPS (menus) untouched; D1 cities unchanged (the rewrite is
  per level load, gated on a D2 city, PS1-native as an SPU upload of the siren + 3 table entries).

## Q73 = A: Chicago night = D2 night rules by default (Infrastructure 30.10.)
- cityprofile CHICAGO now has night_tiles_third + night_models_d2 (C125 + C128) like Havana / Vegas / Rio, so the
  converter default and setup_chicago's recipe (level_key hashes the converter sources) give the q73 night without a switch.
  CHI_POLISH_NIGHT_D2 is now an override: 1 = on for any city, 0 = off (Chicago's pre-Q73 night), unset = profile.
- Check: setup recipe (cheats6 + CHI_NIGHT_MOON) night conversion with no switch = var_polish_q73_night byte-identical.

## C129 toolchain (Infrastructure 30.10.)
- GCC MIPS toolchain, user-local, no PATH / registry change: `D:/recomps/tools/gcc-mipsel-none-elf-12.3.0/` = PSn00bSDK v0.24
  release asset `gcc-mipsel-none-elf-12.3.0-windows.zip` (GCC 12.3.0, mipsel-none-elf; github.com/Lameguy64/PSn00bSDK),
  SHA-256 51df48145d5ef4b396d3932b72ccba538cc605c7c7745b32c58c277aa00523c5 (zip kept in tools/dl).
- Status 30.10.: the user added `Bash(D:/recomps/tools/gcc-mipsel-none-elf-12.3.0/bin/*)` (settings.local.json); call it
  by that full D:/ path from Bash only. **Smoke test OK:** `mipsel-none-elf-gcc (GCC) 12.3.0`; a small C file (struct array
  loop, lw / lh, mult, extern call) with `-O2 -march=r3000 -mtune=r3000 -mabi=32 -msoft-float -mno-abicalls -fno-pic -G0
  -mno-gpopt -c` -> elf32-littlemips; objdump: no load-use in the delay slot (the next use is >= 2 instructions later),
  mflo / mult spacing fine, R_MIPS_26 relocation for the call (tail call 'j ext_fn'). Flags = the C129 overlay baseline.
- **C138 Havana mini car (Polish 30.10.):** the mini is D2 model 12 (Havana choice 0, D2's secret car): body 280 x 554 D1
  (model x1.32), colBox (94, 66, 210) -> 124 / 277 half, cPoints (-93..92, -186..226) -> 240 x 544 shadow quad, wheel 33.
  - Shadow: Driver 1 draws it through the physics corners car + 0x88 .. 0xB8, measured 370 x 1040 for EVERY car (Miami's
    D1 car and the Havana mini alike: Driver 1's fixed body box) -> 1.5 x wider, 1.9 x longer than D2's. The plugin's SHD
    offsets (C102, 0x80093480 + 16 car) already stretch the special's quad from .sps.bin; car 0 has none. Data:
    CHI_POLISH_PLAYERSHADOW=1 -> <lev>.pps.bin = "PPS1", 4, per player choice {D2 model, 4 x (x, z) cPoints x1.32,
    colBox half x / z x1.32, length / 1040 x 4096}. hav9 = hav6 day / hav8 night levels byte-identical + .pps.bin.
  - Lights: positions are the mini's own D2 cosmetics x1.32 (head z -260 of -277, brake x 107 of 140: inside the body);
    D2 draws fixed sizes (cosmetic.c HEADLIGHT 18, BRAKE / BACK 17, INDICATOR 20, REVERSE 14 D2 units -> x1.32 24 / 22 / 26 /
    18); Driver 1's glow sizes are its own (engine): a per-car scale (length ratio in .pps.bin) or D2's sizes are Infrastructure's.
  - Box: the car-car box (C42E) already = D2 colBox; the physics corners (shadow, ground contact) are the engine's fixed box.


## C137 step 1: D1 horns + siren replaced in D2 cities (Infrastructure 30.10., build-wip; Analyst inventory above)
- **Package:** car_sfx.bin (CSX2) gets the city's D2 siren as kind 3 (VOICES2 bank 69 Chicago / Vegas, 70 Havana, 71 Rio;
  6,048 / 14,848 / 6,048 / 12,336 B, 8 kHz loop; build_package SIREN_BANK, CHI_C137_SIREN=0 none). Older plugins ignore it.
- **Plugin (c137_bank0, at the fresh bank 0 of a D2 city, after the civilian banks):** entries 6 / 7 / 8 (D1 horns, AI
  horn 0x800180D8 + R1) = the D2 civilian horns of slots 25 / 24 / 26 (fallback 25; entry 8 keeps an address of its own,
  so the R1 -> player-horn retarget still triggers); the freed D1 horn block (18,352 B, SPU 0x1E4D0) holds the D2 siren as
  entry 4 (D1's siren sample 4 dropped). While entry 4 = the D2 siren, the D1 sweep in 0x8004CA5C is neutralised by two
  code words (psx_mod_write_code_word): 0x8004CCB4 subu v1,v1,v0 (0x00621823) -> addiu v1,zero,0x1000 (pitch arg fixed),
  0x8004CC84 subu a3,v0,a3 (0x00473823) -> addiu a3,zero,-2000 (volume fixed); restored in every other level. Doppler
  (scale +0x52, FUN_0004e5e4) stays: siren pitch 0x2E7 = 8000 Hz, up to ~+13 % for an approaching cop. CHI_C137=0: off.
  Host-only (M8: SPU upload + 3 table entries + 2 code words from guest code at level load).
- **Runner `c137_sounds`** (CITY, SECOND=miami|la, DRIVE; Rio sits still: its start faces the sea): entries 6-8 = D2 horns,
  entry 4 = the siren, the words, siren voices at the sample's pitch, R1/R3 player horn = slot 27, then the D1 city has
  Driver 1's table and words back. PASS Vegas / Havana / Rio / Chicago (+ Vegas -> LA, Rio -> LA / Miami); d4ea9929 fails.
- **Open (step 2):** s5 / s9 / s14 / s15 (12,560 B) and Take a Ride bank 4 (117 KB): no static caller; a usage check run
  before any drop. The freed s4 (1,920 B) is unused for now.

## C138 plugin side: D2 player shadow + D2 light sizes (Infrastructure 30.10., build-test 848956e9)
- **Shadow (player_shadow, in shadow_vblank):** car 0's SHD offsets (0x80093480) stretch Driver 1's corner quad to the
  chosen car's D2 size from assets/<city>/plrshadow_<day|night>.bin (= the level's .pps.bin, Polish PPS1; build_package
  copies it like .sps.bin; entry = player choice 0x8009683C), only while a D2 city runs; 0 elsewhere. Physics corners stay
  Driver 1's 370 x 1040 (handling). Shared helper shadow_stretch() with the specials (C102). CHI_C138_SHADOW=0: off.
  Havana mini (hav9, choice 0, D2 model 12): quad 544 x 244 = .pps.bin, 537-556 after a crash drive. Applies to every D2
  city / choice whose level carries a .pps.bin (Polish: CHI_POLISH_PLAYERSHADOW=1 for the other cities).
- **Lights (c138_lights_vblank):** Driver 1's ShowCarlight 0x80043FDC sizes are immediates at 14 call sites (reverse 20
  0x80043970 / 9A8, indicators 30 0x80043BB0 / BF8 / C64 / CBC, brake 25 0x80043DF4 / E3C, night head 30 0x80046398 / 3F0 /
  4AC / 504, night tail 25 0x800465A8 / 5F4); in D2 cities they are Driver 2's fixed sizes x1.32 (head 24, brake / tail 22,
  indicator 26, reverse 18) for every car, Driver 1's elsewhere (switch_words, code-word writes). CHI_C138_LIGHTS=0: off.
  Host-only (M8: SHD words per frame + 14 code words from guest code).
- **Runner `c138_mini`** (CITY, NIGHT; hav9 levels): start shot (as Polish's 20261030-010048 / -010135), shadow quad =
  .pps.bin, physics 1040 x 370, light words, 10 s drive into traffic / wall, alive; PASS day + night. c137_sounds' D1 leg
  checks D1 light words + SHD0 = 0 (PASS Havana -> Miami). Regression: shadow_bus, city_switch, havana_drive, cheats_menu PASS.
- **Polish check (30.10.):** before/after start shots: Driver 1's big dark quad -> shadow under the mini; night glows
  D2-sized. c138_mini night once 5/6 (510 x 243 after wrecking into a wall): Driver 1's own physics corners shrink after
  a wreck (1040 -> 1014-1033 over 4 s) and the shadow keeps its fixed -496 offset. That is Driver 1's own behaviour, not a C138 bug;
  the test's +-12 tolerance after the drive could compare against physics length - 496 instead.
- **Other D2 cities (Polish 30.10.):** CHI_POLISH_PLAYERSHADOW=1 levels var_polish_chi7_* (Chicago: cheats6 recipe, nights
  = q73 = Q73 profile default), vegas6_* (vegas5, CHI_CLUT_MARGIN=3), rio5_* (rio2 day / rio4 night), each day / night /
  xd: every file byte-identical to its source, plus .pps.bin. Choice 0 quads: Chicago D2 model 12 977 x 331, Vegas / Rio
  D2 model 1 869 x 331 / 886 x 321 (choice 3 = model 8: Chicago 1763, Vegas 1749, Rio 2104 long). Start shots on
  build-test 848956e9 day + night: shadow quad = .pps.bin, D2 light words, alive.
  Runner pitfall: Session.menu's page-2 row index (chicago 0 .. rio 3) assumes all four D2 cities are packaged; page 2
  lists only packaged cities, so with only CHI_RIO_* set the Rio row loads Chicago and the Vegas row stalls at Day/Night
  (an extra cross then lands in Miami). Package all four (CHI_HAVANA_* / CHI_VEGAS_* / CHI_RIO_*) and check 0x80096834 = 3.

## C137 step 2: usage check of s5 / s9 / s14 / s15 and Take a Ride bank 4 (Infrastructure 30.10., build-wip)
- **Static (complete start-site list):** every sample start goes through FUN_0004d968(ch, bank, sample, pitch) via
  FUN_0004d6b0 / d740 / d7e4 / d8b0; their 18 + 2 call sites pass bank 0 immediates 0 / 1 / 2 / 3 / 4 / 8 / 11 (engine
  starter FUN_0004c438: 1 / 2 / 3 / 4 only), AI horn 6 + (id & 3, 3 -> 2), smash table 0x8008AE8C (24 entries {key, name,
  sample, vol, pitch} + default 0x8008AEB4: samples 10-13 only), speech queue 0x800BC9BC -> FUN_0004cf50: ids < 100 bank 3,
  >= 100 bank 4 (id - 100) only. The one path with free bank / sample bytes = the mission-script sound slots
  0x800C6F04 + 0x14 (3 x 16 B: flags +0xA, sample +0xB, bank +0xC; FUN_0006a6c8 from the main loop 0x800241C8).
  -> bank 0 s5 / s9 / s14 / s15 have no start site except script slots; bank 4 only via queue ids >= 100 (driving
  comments FUN_0006b9d8 for objective type 4, script slots / random speech list +0x50).
- **Runtime (runner `c137_usage`, plugin trace CHI_C137_TRACE=1 = every channel's sample address per vblank, off by
  default):** Take a Ride with ~60-90 s of driving with turns / crashes / horn + 40-60 s cop chase: Vegas (x2), Chicago,
  Havana, Rio, LA (D1 baseline). Started: bank 0 s0-s4, s8 (D1 R1 path), s11, D2 slots 16-22 / 27, bank 3 radio. Never:
  s5 / s9 / s14 / s15, any bank 4 sample; script slots empty in every run (Rio, Vegas sampled).
- **Verdict:** unused in D2 cities (Take a Ride is the only mode there): s5 / s9 / s14 / s15 (12,560 B) and bank 4
  (117,108 B incl. the special-engine tail's neighbour). Not tested: smash objects (s10-13 stay: listed in the table).
- **What dropping gains:** the game loads bank 0 / bank 4 as whole blobs, so SPU RAM is only won when something new uses
  it. Free in D2 cities now: bank 0 0x1C5E0..0x23F40 (s4 + s5 + s6-8 + s9 = 31,072 B contiguous, of which the D2 siren
  uses <= 14,848 from 0x1E4D0) + s14 / s15 (1,760 B) + the mission block 0x21800 (137 KB; today only its last ~20 KB
  hold the special's engine). Skipping bank 4's CD read in D2 cities would also shorten level loads (exe change).
- **Done (Strategy decision 30.10., build-wip):** (1) bank 4 is not loaded in D2 cities: FUN_0004c29c (level sound load:
  bank 0 = VOICES lump 0, bank 3 = lump 1, bank 4 = the lump of the first (mission threshold, lump) byte pair at 0x8008A96C
  with threshold >= mission; 0xFF = none) -> Take a Ride 0x7C's pair (0xAE, 0) gets lump byte 0x8008A985 = 0xFF while a D2
  city runs mission 0x7C (plugin c137_bank4_vblank, exe DATA byte, no code word, no shared exe window needed), 0x00 for
  everything else (D1 cities, missions 63..174 such as Interview / driving games, future D2 missions). No CD read (117 KB,
  ~57 sectors) and no SPU upload; the stale bank 4 table of the previous level is cleared (rate 0 = FUN_0004d968 plays
  nothing); the special's engine slot now starts at the mission block base (0x52410..0x73C10 = 137 KB, reserve).
  CHI_C137_BANK4=0: off. Host-only (M8: the byte from guest code before the level load).
  (2) s5 / s9 / s14 / s15 stay uploaded: bank 0 is ONE SpuWrite of the whole lump (FUN_0004e214); leaving samples out needs
  a split upload (code patch + per-sample table fix-up) = fragile, skipped; their 12.5 KB count as reserve.
  Runner: c137_sounds (+ lump byte FF / bank 4 table empty / special engine in the block in the D2 city; lump 00 / bank 4
  back in Miami / LA) PASS Vegas -> LA, Chicago -> Miami; `c137_mission` (Undercover first mission 0xAE: bank 4 loaded)
  PASS; car_sounds Vegas, c137_usage LA PASS.
- **Runner fixes (30.10.):** Session.menu raises StepFailed for a D2 row whose city is not packaged (greyed rows are
  skipped by the cursor) and checks the variant word after the load (CITY is 3 for every D2 city); `python -m runner run
  T --day X --night Y` overrides Chicago's levels; city_switch's second ride had run into the attract demo since the
  page menu (menu_again() now navigates from the remembered page, variant-checked); c138_mini reads the shadow quad
  paused in one block along its axes: the shadow stays the D2 size after crashes (the 'fixed offset to the physics
  corners' seen before was separate reads of a moving car).

## C140 probe "d2 cities 6" freeze dumps (Infrastructure 30.10., offline; copies in devtest/_out/c140)
- **Both dumps are wedge kind "slow_frames"** (no FAIL-FAST, no C135 signature: no vector wipe, no far-car dispatch).
- **Session 1 (16:28-16:33):** menu path Rio row -> Day -> back -> page 1 -> cursor over Interview ("Take a Ride ->
  mission 0xAE", C135 browsing artefact) -> Newtown. The mission-parse hook (0x80068928, mission_parse_entry) did NOT run
  for that load: MISSION_SAFE 0x800A0D00 empty, no "C50 ... parsed" / "C79" lines, cops on (0x800976F8 = 1, cap 2),
  "start vector 0 (level 7): y 0" (the vblank fallback found LA's start in the vectors = LA's unmodified script). Result:
  Newtown ran LA's raw Take a Ride script: police (Newtown has no police model -> cars drawn as bare wheels: the user's
  snapshot 16:30 = C141), AI cars at y -1800..-2700 (in the air), the player's car later stuck falling (17 x F5 at
  (-26545, 12578)), then the slow-frames dump; the window was closed (run report: sdl_window_close 16:33:19, dump
  truncated). Same path in the runner (LA Day/Night instead of Rio) ran the hook (menu_route), so the Rio Day/Night
  back-out is the difference; reproduce when the user's game is closed.
- **Session 2 (16:33-):** Rio night ride, then Chicago night: dump 16:40:55 at the Chicago night LOADING screen (snapshot
  16:40:58, FPS 14 "LOADING"); the game went on (Havana mini, Vegas day / night snapshots). Dirty-block ring: ~12,500
  interpreted blocks per frame (pages 0x80030000 group renderer, 0x8002C000 incl. the C132 facing words, 0x8001F000,
  0x8003E000): a load-time hitch on the laptop; to compare with 848956e9 / d4ea9929 once the game is closed.
- Snapshots: 16:30 Newtown bare wheels + air cars (C141); 16:40 Chicago night loading; 16:42 Havana mini (wall-top texture
  noise behind the car); 16:45 / 16:48 Vegas day / night (no visible fault).

- **Fix (build-wip 30.10.):** (1) mission_parse_entry gates the C50 / C79 script work on the mission being parsed (s0 =
  0x7C) instead of the mission word, which the menu routing rewrites (0x7C <-> 0xAE) while the cursor moves; log lines
  "C140 mission parse skipped" / "C140 mission word ... parsed anyway" for the next field report. (2) C141 guard
  (c141_newtown_vblank): while the selector's Newtown runs (CITY 7, mission 0x7C) the cop cap 0x80097760 is forced to 0
  every vblank (Nightmare unaffected: it relies on that cap). Repro: runner `c140_route` (PRE=chicago ride + quit, Rio
  Day/Night back-out, over Interview, Newtown; checks hook, cap, no model-1 car, guard) passes on 106cfe7c too: the
  user's exact timing did not reproduce; the s0 gate + guard cover the observed state. extra_load newtown / desert,
  menu_route desert / newtown PASS on build-wip.

## C143 horn mapping (Analyst 30.10., offline; REDRIVER2 gamesnd.c / civ_ai.c / main.c + D2 MISSIONS.BLK + VOICES2)
- **Driver 2's rule:** a car's horn is sample 2 of its car bank (`GetCarBankSample(slot) * 3 + 2`): traffic honks via
  civ_ai.c (at the player / chased car, max 2 at once, `hornchanflag[2]`), the player via DealWithHorn (main.c, channel 2),
  lead cars via LeadHorn. Bank of a slot (retail, MAX_CAR_RESIDENT_MODELS 5): slots 0 / 1 / 2 own the banks
  MapCarIndexToBank(slot) = car_banks[level][residentModels[slot] - 1]; **slot 3 (the cop in Take a Drive) shares slot 2's
  bank** (`model < 3 ? model : model - 1`); the special slot 4 takes ResidentModelsBodge(): 3 = special-1 bank, 4 =
  special-2 bank, 5 = secret-car bank (SpecialVehicleKludge: Chicago {2, 18, 10}, Havana {2, 17, 4}, Las Vegas
  {9, 11, 13}, Rio {17, 11, 15}). Bodge per city: Chicago model 9 / 11 -> 4, Havana 8 / 9 -> 4, Las Vegas 8 -> 4, Rio
  11 -> 4, model 12 (Take a Drive) -> 5, else 3.
- **Take a Drive residentModels (MISSIONS.BLK 50-57, header +96):** Chicago {1, 2, 3, 0, 10 / 11 night}, Havana
  {1, 2, 3, 0, 11}, Las Vegas day {1, 3, 4, 0, 9}, night {1, 2, 4, 0, 9}, Rio {1, 2, 3, 0, 8}; playerCarModel 1 everywhere.
- **D2 model -> horn bank (truth) vs ours (car_sfx.bin map, probe d2_cities_6):**

  | city | cop | civ 1 / 2 / 3 | specials (D2 bodge) | ours where it differs |
  |---|---|---|---|---|
  | Chicago | 13 (slot 2 = model 3) | 12 / 4 / 13 | 8 -> 2, 9 -> 18, 10 -> 2, 11 -> 18, 12 -> 10 | cop 4; special / choice 8 -> 16, 9 -> 9 |
  | Havana | 7 | 10 / 11 / 7 | 8 -> 17, 9 -> 17, 10 -> 2, 11 -> 2, 12 -> 4 | cop 11; special 11 -> 5 |
  | Las Vegas | 6 (slot 2 = model 4, not in our set: use our 3rd civilian's 4) | 1 -> 14, 2 -> 3, 3 -> 4, 4 -> 6 | 8 -> 11, 9 / 10 / 11 -> 9, 12 -> 13 | cop 3; special 10 -> 2, 11 -> 17, 12 -> 10; choice 2 (10) -> 2 |
  | Rio | 13 | 8 / 7 / 13 | 8 / 9 / 10 -> 17, 11 -> 11, 12 -> 15 | cop 7; special / choice 8 -> 2 |

  Civilian banks and the choices built from civilians / model 12 are right. The profile `car_banks` uses
  MapCarIndexToBank for every model, where Driver 2's Take a Drive uses the slot-2 bank for the cop and
  SpecialVehicleKludge for slot 4. Engines / idles come from the same bank, so they change together.
  Side find: Las Vegas traffic is D2 models 1 / 2 / 3 + cop; Driver 2's Take a Drive runs 1 / 3 / 4 (day), 1 / 2 / 4 (night).
- **Why horns are not tied to models today:** Driver 1's own AI horn (0x800180D8, FUN_8004D740(-1, 0, 6 + (record id & 3,
  3 -> 2))) picks table entry 6 / 7 / 8 by the car's SLOT ID; since C137 those entries hold the three civilian horns
  (slots 25 / 24 / 26), so a car honks with a random civilian horn. The plugin's own honk (step 6) uses the model's bank
  (sx_horn_slot_of_bank), skips the cop (Driver 2's patrol cops do honk, with the slot-2 horn) and plays the special's horn
  (28); the player's R1 horn is the choice's bank (27). Driver 1's path never plays the special's horn; the cop has no slot.
- **Fix route:** (1) data: cityprofile / build_package bank map = Driver 2's slot rules (cop = bank of residentModels[2];
  specials and special / secret player choices = kludge by bodge; Las Vegas cop = its 3rd civilian's bank until the car set
  follows D2); (2) exe (PS1-native, the 8 words at 0x80018084..0x800180A4): the AI horn takes `lbu model, 0x10(record)` and
  an 8-byte model -> table-entry table (written per city: model 1 -> the cop's horn = the slot-2 civilian's, 2-4 -> their
  bank's horn slot, 5 -> 28) instead of `id & 3`; entry 8 keeps an address for the R1 detection; (3) plugin: patrol cops
  (model 1, not pursuing) may honk with that horn (D2 civ_ai).
- **SPU room:** horns are 8 kHz, 1,456-6,336 B. The cop shares a civilian bank (no new sample); corrected special / choice
  banks replace others in the same reserved player / special space (engine + idle <= 18,992 B tails, horn <= reserved
  hmax). Las Vegas: bank 13's horn (6,336) > today's hmax 6,000 -> +672 B reserved (free 5,680 -> 5,008). Chicago bank 18
  (horn 5,520, engine + idle ~17.7 KB at 11 kHz) fits. No other room needed.

## C144 wheel checkup (Analyst 30.10., offline; REDRIVER2 cars.c DrawCarWheels / wheelforces.c, D2 LCF, assets of probe d2_cities_6)
- **Driver 2:** generic wheel models (clean / fast / damaged); per car: tread vertices 16-23 = +-wheelSize, rim 8-15 rotate
  at wheelSize x 1.4142, hub 0-7 untouched; centre (car frame) x = +-17 - disp.vx, z = -disp.vz, y = -wheelSize - disp.vy
  - susCompression + 14 (compression from the ground contact, 0..42). Every tyre stands on the road.
- **Ours:** car_wheels.bin (choices 0-3, AI 1-5) and the specials' sizes = LCF wheelSize x 1.32: **all sizes match Driver 2**
  (Chicago 65 / 91 / 98 / 119, civilians 65-70; Havana mini = model 12, choice 0: 44; Las Vegas choice 0 = model 1: 57; Rio
  civilians 54-61, model 8: 102). x / z = D2 x 1.32 (+-17 f - f vx, FixCarCos dz): match. The plugin's DrawCarWheels hook
  sets tread / hub +-size and the rim word per car (car set 4 in all four sidecars; sizes reloaded per city).
- **Mismatch = height.** Driver 1 draws the wheel centre at -(susp + 50) - disp.vy and sets the ride height to
  -disp.vy - 1, so at rest (D1 susp ~24) the wheel CENTRE sits ~73 above the road (Driver 1's own radius) whatever the size:
  a tyre of radius R floats 73 - R above the road (R < 73) or sinks R - 73 into it. The body rides at the D1 clearance 34
  (+ the d2wheel extras for models 8-12).

  | city | car (role) | R | tyre vs road (ours; D2 = 0) | wheel-to-body vs D2 (minus the civilians' mean) |
  |---|---|---|---|---|
  | Chicago | 0 cop / 1 / 2 / 3 civ | 65 / 69 / 65 / 70 | +8 / +4 / +8 / +3 | +8 / +1 / -6 / -2 |
  | Chicago | 8 (choice 3, special) / 9 (choice 1) / 10 bus (choice 2, AI 5) / 12 (choice 0) | 119 / 91 / 98 / 65 | -46 / -18 / -25 / +8 | +1 each |
  | Havana | civ 0-3 | 65 | +8 | 0 / +8 / -15 / +9 |
  | Havana | **12 mini (choice 0)** / 8 / 9 / 10 / 11 | **44** / 91 / 91 / 88 / 65 | **+29** / -18 / -18 / -15 / +8 | 0 / +1 / 0 / 0 / 0 |
  | Las Vegas | **1 (choice 0, civ)** / 0 cop / 2 / 3 | **57** / 65 / 67 / 65 | **+16** / +8 / +6 / +8 | -4 / -4 / -1 / +9 |
  | Las Vegas | 8 / 9 / 10 / 11 / 12 | 74 / 70 / 88 / 88 / 57 | -1 / +3 / -15 / -15 / +16 | 0 each |
  | Rio | civ 0 cop / 1 / 2 / 3 | 54 / 57 / 58 / 61 | +19 / +16 / +15 / +12 | +21 / -4 / -14 / -4 |
  | Rio | 8 / 9 / 10 / 11 | 102 / 67 / 86 / 65 | -29 / +6 / -13 / +8 | 0 / 0 / -1 / -1 |

  "wheel-to-body" = (73 - 34 - extra) minus Driver 2's (wheelSize - clearance) x 1.32, each minus the city's civilian mean
  (Driver 2's rest compression is not known statically). Models 8-12 already follow D2 through the d2wheel rule; the
  civilians use the fixed 34 (spread -15..+21). The Havana mini's tyres float 29 above the road and fill the arch high
  (reads as "too large"); Las Vegas choice 0 floats 16; Rio's small-wheeled traffic floats 12-19; big specials sink 15-46.
  Scratch: c144_lcf.py (LCF table), c144_geom.py (this table).
- **Fix route:** (1) engine, small (PS1-native like WHEEL_RIM): a per-car draw-only wheel y offset dy = 73 - R at
  DrawCarWheels' four wheel-position sites (the per-car hook already runs; guest version = a byte table by model), so every
  tyre touches the road; (2) data (polish_cosmetics): ride row disp.vy += (73 - R) so the body moves with its wheels, and
  Driver 2's wheel-to-body relation per model for ALL cars (today only 8-12). Risk: ride height drives physics (spawn
  height, collision box); big wheels raise the fire engine / bus by 25-46 (the R35 "spawned high and bounced" case) -> one
  drive test per city. Needs one constant: Driver 2's rest compression (a D2 reference capture or a static solve of
  wheelforces.c).

## C142 no black void: one-shot fog-colour clear (Infrastructure 30.10., build-wip)
- Driver 2 never clears the frame either (REDRIVER2 system.c: SetDefDrawEnv -> isbg 0; D2's maps just have no holes).
  C134's per-frame black clear made unloaded areas a black void. Now clear_bg_vblank clears both DRAWENVs only for 6
  vblanks after a D2 level starts running (in-level heartbeat rising edge), to the level's fog colour 0x80097138
  (0x00BBGGRR); afterwards isbg 0 (Driver 1 / 2: never-drawn spots keep the fog colour, later the last frame stays).
  This still removes C134's old-VRAM noise (Fremont start: neighbour diff 0.0, foreground hole = fog colour instead of
  black / noise). CHI_C142=0: C134's per-frame black clear; CHI_C134=0: no clear at all. Runner c134_clear (+ isbg 0
  after the start, drive shot) PASS. Holes show trails after driving (D1's look, user's choice).

## C143-C146 data bundle (Polish 30.10.): chi8 / hav10 / vegas7 / rio6
- **Levels** (day / night / xd each) = the chi7 / hav9 / vegas6 / rio5 recipe + CHI_POLISH_LIGHTCOG=1 (C145) +
  CHI_POLISH_WHEELROAD=1 (C144) + CHI_POLISH_D2TRAFFIC=day (Vegas set) + CHI_POLISH_CYCLE=1 (Vegas nights; .cyc.bin
  written standalone for the rest) (+ CHI_POLISH_D2BANKS=1 and CHI_POLISH_D2TRAFFIC at package time).
  Drives (current build-test exe, package from these levels, devtest/polish): all 4 cities day + night alive after a 10 s crash drive, no
  spawn bounce (player y span 0), SPU free after the horn reserve: Chicago 1312, Havana 5936, Las Vegas 8224, Rio 3584 B.
  Byte check vs sources: Chicago / Havana differ only in lump 28 (car models) + .cos.bin + .spc.bin; Las Vegas also in the
  car texture pages / names (the new traffic model) + .dmg / .lvl / .whl. New sidecar .cyc.bin (C146) on chi8 / vegas7.
- **C145 lights (polish_cosmetics.light_shift):** Driver 2 draws the body at where + R (cog + v) and every light at
  where + R (light + cog) (cosmetic.c); our bodies carried the cog (x, z) + ride raise, the light rows did not -> lights
  off by -cog x 1.32: Chicago bus (model 10, cog.vz 117) headlights 82 in front of the body, tail lights 157 inside;
  fire engine (8, cog.vz 5) fine. Same error: Rio 8 / 10 (cog 58 / 77), Vegas 9 / 10 (57 / 37), Havana 10 (52), all
  cars by their cog (5-30). Fix: the 8 light / exhaust / smoke points get the body's shift (cog x / z x 1.32 + ride dy).
  The extraInfo 0x5000 brake double-cog quirk (AddBrakeLight) only on Chicago model 8 (cog 5): ignored.
- **C144 ride rows (polish_cosmetics.wheel_road):** R = round(LCF wheelSize x 1.32) (= .whl.bin); ride row
  disp.vy += 73 - R (Driver 1's wheel centre stays 73 above the road, origin + body go down by 73 - R); Driver 2's
  wheel-to-body relation (d2wheel body extras, anchored on the civilians' mean) for every model 0-12 (was 8-12).
  **Infrastructure's draw-only wheel offset must be dy = 73 - R with the same R**; data without it sinks small-wheeled
  bodies onto their wheels (Havana mini 29). Per model R / ride shift / body extra (D1 units):
  Chicago 0 65/+8/+7, 1 69/+4/+1, 2 65/+8/-6, 3 70/+3/-2, 8 119/-46/+15, 9 91/-18/+11, 10 98/-25/+28, 12 65/+8/-13;
  Havana 0-3 65/+8 (-1/+7/-15/+9), 8 91/-18/+19, 9 91/-18/-32, 10 88/-15/-15, 11 65/+8/-3, 12 44/+29/+10;
  Las Vegas 0 65/+8/-5, 1 57/+16/-3, 2 67/+6/-1, 3 65/+8/+9, 4 74/-1/+40, 8 74/-1/-5, 9 70/+3/+10, 10 88/-15/-27,
  11 88/-15/-14, 12 57/+16/-5; Rio 0 54/+19/+21, 1 57/+16/-4, 2 58/+15/-13, 3 61/+12/-4, 8 102/-29/-45, 9 67/+6/-3,
  10 86/-13/-13, 11 65/+8/-9, 12 94/-21/-18. Big wheels raise the physics ride (bus +25, Chicago 8 +46): drive-tested.
- **C143 banks (cityprofile.C143_BANKS, CHI_POLISH_D2BANKS=1 at package time):** cop = the slot-2 civilian's bank
  (Chicago 13, Havana 7, Las Vegas 6, Rio 13); specials / special choices by SpecialVehicleKludge (Chicago 8/10 -> 2, 9/11
  -> 18, 12 -> 10; Havana 8/9 -> 17, 10/11 -> 2, 12 -> 4; Las Vegas 8 -> 11, 9/10/11 -> 9, 12 -> 13; Rio 8/9/10 -> 17,
  11 -> 11, 12 -> 15). **Open for Infrastructure:** car_sfx.bin has one slot map per city, built from the day slot map;
  Las Vegas night's slot 2 is model 2 (bank 3) where the day has model 3 (bank 4) -> needs a night map / per-time car_sfx.
- **Traffic sets (MISSIONS.BLK 50-57 residentModels):** Chicago {1, 2, 3, 0, 10 / night 11}, Havana {1, 2, 3, 0, 11},
  Las Vegas day {1, 3, 4, 0, 9} / night {1, 2, 4, 0, 9}, Rio {1, 2, 3, 0, 8}; times all 1 / 3, weather 0. Ours were
  1 / 2 / 3 everywhere -> Las Vegas follows D2 with CHI_POLISH_D2TRAFFIC=1 (polish_cars, by CHI_D2_LEV; CLUT 381 -> 377).
  build_package refuses day / night levels with different civ damage tables (one dmg_civ / car_sfx map per city), so the
  bundle uses CHI_POLISH_D2TRAFFIC=day (D2's day set 1 / 3 / 4 at both times); the exact night set (1 / 2 / 4) needs per-time
  civ assets (package + plugin: dmg_civ, car_sfx map, civ zone rows) -> Infrastructure, then CHI_POLISH_D2TRAFFIC=1.
  Not changed: Chicago night's starting special is 11 in D2 (ours 10; 11 is not in our Chicago special list).
- **C146 Las Vegas night vs Driver 2 (REDRIVER2 reference):** D2's night code has no Vegas case except night_vectors[2]
  (car light direction) and **ColourCycle** (objanim.c: 12 Vegas neon textures rotate CLUT entries every other frame;
  Chicago 2; Havana / Rio none). Measured at the same start, same orange car (D2 model 1), night / day: road 0.25 vs ours
  0.24, trees 0.16 / 0.17, sidewalk 0.25 / 0.28 (match); **player car 0.28 vs ours 0.05** (Chicago's car: 0.30 / 0.30
  match). The same model 1 in Rio renders lit at night (bundle shots) and our car palettes (pages 5-6) and the car model are
  identical day / night in both levels -> the Las Vegas night player car takes a near-black paint / palette at RUNTIME
  (D2: playerCarColour 1 day and night, REDRIVER2 shows it orange-brown): engine-side check (palette / colour pick); neon static
  (canopy stripe blue where D2 cycles to red); pole traffic-light glows weaker; sky (8, 8, 8) vs D2 (1, 1, 6).
  Data: polish_cycle.py -> <lev>.cyc.bin ("CYC1": name, our page, texture index, start1 / stop1 / speed1 / start2 /
  stop2 / speed2 per cycling texture; vegas7 4-7 entries, chi8 xd NAVPIR34) for an engine ColourCycle (PS1-native: guest
  CLUT row rotate + LoadImage like D2). Missing names (FLAMINGO, ENT1B, F-MTSYN2 ...) are not under their own name in our
  levels (not placed / merged): follow-up.
- **Reference tool:** devtest/polish_r2 = private REDRIVER2 copy (config: 640 x 480, no bilinear / PGXP texture mapping,
  dynamic lights off, image = the D2 disc 2 .bin read-only); DRIVER2/MISSIONS/M50.D2MS / M51.D2MS override Take a Ride
  Chicago day / night with any mission (GameLevel = header city, start patchable at +20): Las Vegas / Rio are locked in a
  fresh profile. Driven with posted key messages (needs brief window focus; SDL drops keys otherwise; the first keys
  after launch replay later) + PrintWindow captures off-screen (scratch r2.py). Only when no user game runs.

## C143 AI horn by model (Infrastructure 30.10., exe window + plugin, build-wip)
- **Exe (c143_patches, 7 of the 9 words 0x80018084..A4):** entry = 6 + HORN[model * 32 + record id] (lbu model 0x10(s1),
  lbu id 0(s1), sll 5, addu, addu gp, lbu -0x3128(a2), a0 = -1, a1 = 0, +6). HORN = 256 bytes in the zero block
  0x80093648..0x80093747 (intr.c's handler stack bottom, ~3 KB below its top 0x80094328). Zero-safe: an all-zero table
  (boot / an older plugin) plays entry 6, never entry 0. Record ids are 0..21 (24 slots < 32).
- **Plugin (c143_horn_table, every vblank):** D1 cities / D2 horns not loaded: id rule (id & 3: 0 / 1 / 2 / 2 = entries
  6 / 7 / 8 / 8, Driver 1 unchanged); D2 city: per model the horn slot of its bank (cop model 1 = the bank map's cop
  entry; Polish's data fix makes that the slot-2 civilian's bank as in Driver 2), special 28, else 25. The plugin's own
  honk now lets patrol cops honk (model 1 with car +0x12E != 1; pursuing cops run the siren). CHI_C143=0: exe group off.
- **Trigger** (FUN_8001A1BC): a car heading against the player (heading difference 0x69C..0x964) within 9000 ahead.
  Runner `c143_horns` (code words, table, turn round and drive against the start lane's traffic, C137 trace): Miami
  entry 6 (D1 rule), Chicago the model-4 horn (slot 26; the trace prints 8, same address since C137); Vegas / Havana no
  oncoming honk in those runs; tables right in all.

## C144 engine: draw-only wheel height per car (Infrastructure 30.10., exe window + plugin, build-wip)
- **Exe (c144_patches):** DrawCarWheels' wheel centre y (0x8003B600..14: -disp.vy - (susp + 50)) gets + WDY (zero block
  0x80093748 = gp-0x3028): site 0x8003B60C 'addiu v0, v0, 0x32' -> 'j WCAVE' with the addiu in the delay slot; WCAVE =
  4 words at 0x80011AC8 (the GPU-timeout text's last 4 bytes + the unreferenced 'LoadImage2'; seeded in
  seeds/ghidra_funcs.txt): lw t9, WDY(gp) / subu v1, v1, v0 / j 0x8003B614 / addu v1, v1, t9 (t9 unused in the wheel
  loop). The C45 near-sub cave's limit is now 0x80011AC8. Zero-safe (0 = Driver 1). 2079 patches.
- **Plugin (wheels_entry, per car):** WDY = 73 - R (the car's D2 wheel size) in D2 cities (car set 4), 0 otherwise.
  CHI_C144=0: off. Physics / ride height untouched (Polish's ride rows move the body; R35 bounce risk is theirs).
- Runner `c144_wheels` (site + cave words, WDY samples, start / drive shots): Havana WDY {8 civilians, 29 the mini} with
  the mini's tyres on the road; Miami WDY 0. PASS.

## C129 plan: Driver 2 civ-AI traffic as a guest overlay (Infrastructure 30.10., Q72 = B; Las Vegas first)
- **One C core, two builds.** REDRIVER2 civ_ai.c is decompiled PS1 C; its road-following subset (InitNodeList,
  GetNodePos, CreateNewNode, GetNextRoadInfo, CheckChangeLanes, CivFindStation / FindPointOnPath / SteerAngle,
  CivAccel(+TrafficRules)) is cut into `chicago/c129/d2civ.c` over its own per-car state (CIV_STATE + a 13-node route
  ring) and a road blob (STRAIGHTS2 / CURVES2 / JUNCTIONS2_NEW + a surface lookup for GetSurfaceRoadInfo), with shims for
  CAR_DATA fields (position, heading, wheel speed), Random2, ratan2 / SquareRoot0 / rcossin. Built twice: host (clang)
  = the reference that prints node paths; mipsel (`-O2 -march=r3000 ... -G0`, the smoke-test flags) = the overlay.
  "Exact match" = guest traces vs the host run on the same data and seeds.
- **Phases:** (1) offline: road blob exporter (per city, from the D2 LEV) + core + host harness (node paths for 10
  diagonal / curve routes in Las Vegas) + mipsel object size check; (2) plumbing: the overlay + road blob in guest RAM
  (loaded per D2 city; PS1 path = the level's data later), an exe hook at D1's per-car AI entry (0x80013D88) for D2
  cities only, kinematic follow (position / heading / speed written to the D1 car from the D2 path point); D1 roads
  kept for felony / cops; (3) spawn on D2 roads (PingIn by straight / curve), lights (D1 cycle) / yield junctions, lane
  changes, parking; (4) runner traces on 3 diagonals + 3 curves in Vegas (within 256 of the lane line, heading within
  64/4096, no axis snapping, speed limits), 10 min soak without stalls, then Chicago / Havana / Rio.
- **Phase 1 done (30.10.):** `chicago/c129/`: d2civ.cpp = civ_ai.c lines 242-1494 + 3032-3274 verbatim (GetLeft/
  RightBoundLane, GetNextRoadInfo, InitNodeList, RemapLaneChange, GetNodePos, CheckChangeLanes, CreateNewNode,
  CivFindStation, CivFindPointOnPath, CivSteerAngle; one change: Random2's unused pointer argument -> 0 for the 64-bit
  host); compat.h / compat.cpp = the D2 types + macros, a reduced CAR_DATA shell (where, direction, wheel_speed, oBox,
  model, carCos, ai.c, id, controlType), globals, Random2 (D2's frame-counter formula), integer SquareRoot0 / ratan2
  (exact over libgte's rcossin: worst error 0), bcollided2d, GetSurfaceRoadInfo. export_roads.py = <city>_roads.bin
  ("D2RD" + the three lumps' records as stored: Vegas 21,320 B, Chicago 29,080 B) + rcossin.bin (Driver 1's table at
  0x8008EAA8 = libgte's). build.sh builds mipsel objects (core 10,828 B text + helpers 1,299 B + 6,668 B shells; no
  libgcc calls, links standalone), the host harness, and out/vegas_ref_paths.txt (10 routes: 5 diagonals at 45 deg, 5
  curves; 2400 frames each at 40 units / frame; kinematic follow = CivSteerAngle (node upkeep) + CivFindStation +
  CivFindPointOnPath at station + speed): all 10 run through junctions / curve chains without a 'confused' stop.
- **Phase 2 design (next):** the overlay must run natively (the C140 dump showed what interpreted pages cost): link it at
  a fixed main-RAM address and register it as a recompiled overlay (game.toml, like FRONTEND / IVIEW.BIN), loaded per
  D2 city with the road blob; needs a free main-RAM window during D2 Take a Ride (~12 KB code + 21-29 KB roads + ~7 KB
  state) -> RAM survey first; entry hook at D1's per-car AI (0x80013D88) for D2 cities; coordinates D2 -> D1 via the
  converter's worldscale (x1.32 + offsets).
- **Phase 2 RAM survey (30.10., user snapshots of d2 cities 6):** heap end in D2 Take a Ride 0x801D8570..0x801DECEC; from
  0x801E0000 a dynamic buffer (likely Driver 1's replay recording: Vegas night after a few minutes filled it to 0x801F3800,
  "Demonstration" text at its start in another run), then DTL.BIN 0x801F8BC0 and the stack. Free gap under 0x801E0000:
  4-30 KB. **No ~50 KB main-RAM window for the overlay in D2 cities today** (the known M8 deficit: D2 cities already keep
  cell objects / carry / specials / surface table in mod memory). Proposal (Strategy): run the same core host-side in the
  plugin now (per-car AI entry hook, native speed), keep the mipsel build verified against the host reference as the
  PS1 path for M8 (after the RAM diet); host-only item added to the M8 list.
- **Phase 2 hook notes (30.10.):** D1's civ AI FUN_80013D88(record a0 = 0x80098950 + 0x50 i, car a1) is called once per car
  from FUN_8001A30C (0x8001A784); it returns early for record[2] == 1 / record[1] in (1, 9), re-plans via FUN_8001A1BC /
  FUN_80021820 + FUN_80016F0C (junction picker) and steers through record fields; the physics then moves the car. A
  kinematic follow must therefore write the car state AFTER physics (position x/y/z + the x16 copies car+0x24..0x2C,
  orientation matrix car+4.., direction, velocities car+0x40 / +0x48, oBox), D2 -> D1 coordinates via worldscale, and skip
  D1's AI for D2-driven slots (return 0 like the parked case). Entry hooks need game.toml mod_function_entry_funcs + a
  regenerate (shared window). Open: the placement decision (host plugin now vs main-RAM overlay after the M8 diet).
- **Decision (Strategy 30.10.):** core host-side in the plugin now (D2 cities only); the mipsel build stays verified against the host path in every C129 test; exact D2 paths remain the pass criterion (runner traces vs the host reference). M8 host-only row added (~50 KB); RAM-diet candidate: Driver 1's replay recording buffer in D2 cities.
