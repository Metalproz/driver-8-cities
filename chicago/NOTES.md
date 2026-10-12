# Chicago → Driver 1 port

Personal/local only (never published). Driver 2's Chicago replaces Los Angeles
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
| package | `python build_package.py --test-bigmiami work/test_bigmiami.lev --chicago work/chicago_d1.lev` (without the args the chicago-la feature is dropped!) |
| EXE patches | `python exe_patches.py disc/SLUS_008.42.orig --apply disc/SLUS_008.42`, then psxrecomp `generate --bios D:/recomps/games/SCPH1001.BIN`, then `rebuild` |
| test build | `build-test` (CHI_TEST_BUILD=build-test for dt/lab) when the user's dev client is running |
| user's dev client | `build-dev` (desktop shortcut "Driver (dev client)"); the user plays this, with dev mode, snapshots (F9 / L3+R3), hang dumps, debug server :4370. Never write test packages or state into it; rebuild only when it is not running. |
| frozen release | `build-release` (Quiver launches it); updated only when the user declares a release |
| tests | `devtools/dt.py` (snaps, live, spots, soak, addspot, dis) on copies in `<app>/devtest/`; issue spots in `devtools/spots.json`; results `devtest/_out/` |
| user spot play | `Driver (spot).bat` / `devtools/spotplay.py C4|spotname`: windowed copy `devtest/play_<spot>` of build-dev (same exe + installed level, user's input settings, own memcards, port 4377) starting Take a Ride at the spot; menus driven automatically |
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
   full-cell polygon per level (lowest first, d relative to the written height,
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

## Engine patches (`exe_patches.py`, 278 words)

model table (88), cell buffer (4), object guard (16: the batched map-object
draw 0x80030ED0 stops at OBJ_LIMIT 0x16800 per frame), render trap
→ skip model (2), area switch waits while loading (3), spool guard: reset
clears reader/indices/loading flag + empty-entry stop + drained totals (45),
tile guard: tiles (drawn before objects) stop at 0x12000 + tile list cap 640 (26), area switch rewrite
0x8003401C (64: threshold always 13 = 5-cell hysteresis band; Chicago only: a
region whose 2 entries don't name the loaded area, or with none loaded (-1),
loads its own = 2nd entry),
road map RLE decoder rewrite 0x800354D8 (30: bad runs fill the rest, always
ends; old one looped forever on stale buffers after Play Again).
Caves: dead overflow block 0x80051440.., cellsize error block 0x8002E1A0 (both
full); `asm()` in exe_patches.py assembles rewritten routines.
Height-aware road surface selection (C16/C17) is **not an exe patch**: it is done by
`driver_chicago.c` (`surface_select_vblank`): every vblank, for the 3 × 3 cells
around the player (road-map cell via the lookup's own ring addressing: header
0x8009E714, tables 0x8009D8F4, parity 0x80097374; surface pointers 0x8009D904),
a marked surface (SURFACEINFO.info = 1, written by the converter) gets the plane
whose height is nearest the car's ground (player y − 160) moved to slot 0 (only
the 4 plane words are swapped: a torn read during the engine's loop costs tens of
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
