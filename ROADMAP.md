# Driver: 8 Cities — Roadmap and Progress Log

Personal/local only. **End goal:** one copy of Driver 1 (the recompiled Driver 1 engine) where
all 8 cities can be played: Driver 1's **Miami, San Francisco, Los Angeles, New York** and
Driver 2's **Chicago, Havana, Las Vegas, Rio de Janeiro**.

- Technical details (addresses, formats, workflow commands, ruled-out list): `chicago/NOTES.md`
- Install and re-apply after an update: `README.md`
- This file: what is done, what is open, and the long-term backlog. Last updated 2026-10-11.

## Status at a glance

| City | Source | State |
|---|---|---|
| Miami | Driver 1 | original, playable |
| San Francisco | Driver 1 | original, playable |
| Los Angeles | Driver 1 | original, playable (Chicago currently takes its slot when the Chicago feature is on) |
| New York | Driver 1 | original, playable |
| **Chicago** | Driver 2, disc 1 | **in progress:** drivable in Take a Ride (in LA's slot); textured city, collision, area streaming, restart. No traffic or cops yet; visual bugs open |
| Havana | Driver 2, disc 1 | not started |
| Las Vegas | Driver 2, disc 2 | not started |
| Rio de Janeiro | Driver 2, disc 2 | not started |

Overall: we are partway through **Milestone 1** (Chicago world, stage A) of 7 milestones (see Backlog).

---

## Done: detailed log

### 1. Setup and base install (2026-10-09)

- **Quiver library** at `D:\recomps` (portable). Driver added as app "Driver" from
  `alexbeavs-ps1-ports/driver-recomp` v0.3.6, built locally with the psxrecomp CLI
  (verify-disc → generate → rebuild). Uses your USA v1.1 disc (SLUS-00842) and retail
  SCPH1001 BIOS. Local fix: `game.toml` → `disc = "disc/disc1.cue"`.
- **Package "driver.personal"** (in the game's Mods menu):
  - *Developer Mode*: full runtime log to `dev/logs/`; **F9** or **L3+R3** saves a snapshot
    (RAM, registers, screenshots, heartbeat) to `dev/dumps/`; `dev/dump.request` triggers one from outside.
  - *Unlock All*: all 8 cheats plus all 4 cities in Take a Ride / Driving Games, without touching Undercover progress.
  - *Skip Intro*: boots straight to the main menu. Implemented as byte-checked patches, so it
    refuses to patch if the exe ever changes.
- **Debug server** on `127.0.0.1:4370` (PSX_DEBUG_TOOLS) and client `driver_dbg.py`
  (frame/read/watch/snapshot).
- Reverse-engineered addresses for cheats, cities unlocked, missions, movie player, and boot
  sequence (table in README.md).
- README with step-by-step re-apply instructions after a driver-recomp update.

### 2. Chicago research and file tools (2026-10-09)

- Extracted the inputs from your discs: all 4 Driver 1 city LEVs, plus Driver 2 Chicago
  (day and night LEV, .DEN, .LCF) in `chicago/work/`.
- `levfile.py`: reads and writes the LEV container for both games, with a **byte-exact round trip**.
- Mapped the formats of both games: sections, lumps, roads, cells (D1 16-byte vs D2 packed
  8-byte), models, shape flags, and surface (D1 tile road map vs D2 planes/BSP with multiple levels).
- Analysis helpers: `mapinfo.py`, `d1cells.py`, `d2cells.py`, `models.py`, `textures.py`,
  `texpages.py`, `texbudget.py`, `pvs.py`, `checkgroups.py`, `d2surface.py`.
- Decisions (2026-10-09): replace a D1 city first (LA) and add extra cities later; milestone
  1 = Take a Ride with traffic and cops; use D2 music and car models; opening bridges fixed
  down; no on-foot sections; keep the Driver 1 look and feel.

### 3. Engine extensions: executable patches (`exe_patches.py`, 278 words)

| Patch | Why |
|---|---|
| Model table moved to extra memory, 800 → **2048 models** (88 sites) | Chicago has far more models than any D1 city |
| City object (cell) buffer moved to extra memory, 512 KB | Chicago's object lists don't fit |
| Object guard: map objects stop at 0x16800 bytes per frame | Primitive buffer overflowed into the road tables, so cars fell through streets |
| Tile guard: ground tiles stop at 0x12000, tile list capped at 640 | "GP0 unknown command" crash |
| Render trap → skip the model instead of hanging | Freezes on bad models |
| Area switch waits while an area is still loading | Wrong models (e.g. DIESEL sign in the street) |
| Spool guard: a reset fully stops the CD reader and clears its indices and loading flag | Play Again crash, scrambled textures, deadlock |
| Area switch rewrite (5-cell hysteresis; Chicago loads its own area when needed) | Crashes from stale models, since D1 only switches areas at borders |
| Road map decoder rewrite (always terminates) | Endless loop on stale data after Play Again |

Free space used: two dead code blocks ("caves") in the exe; `asm()` in `exe_patches.py` assembles the rewritten routines.

### 4. Runtime and plugin changes

- Runtime (`runtime_patches/`, originals kept in `orig/`, full diff `chicago-runtime.diff`):
  disc files beyond the image end (so new data can be added), save states that include the
  mod memory, CD DMA into mod memory, write guard, L3+R3 snapshot helper, watchdog underflow fix.
- Plugin `driver_chicago.c`: allocates the model table and cell buffer, provides an "empty
  model" for placeholders, an area-switch guard, and clears the screen to dark blue in levels
  so gaps are visible.
- Package **"driver.chicago"** ("Engine Extensions (Chicago)"), built by `build_package.py`.

### 5. The Chicago converter (`convert.py`, ~2.5 min per run → `work/chicago_d1.lev`)

1. World scaled ×1.32 and centred to D1 limits: 540 × 570 cells, 18 × 19 regions (D1 max < 351 regions).
2. Models rebuilt in D1 format: polygon groups and planes, LOD remap, tiles and sprites (trees)
   kept, bounding spheres fitted, LA's engine models appended (LA's plane hidden).
3. Visibility (PVS): per-cell view radius 5–9 chosen by polygon budget.
4. Streaming areas: 21 areas, every region gets switch entries, the switch rule is simulated
   cell by cell so each area covers every region it can be loaded in.
5. Textures repacked per area: at most 31 palettes per page, far-only textures shrink first,
   SUBDIVISION UVs remapped.
6. Road map / collision surface: D2's multi-level surface flattened to D1's single level
   (nearest street level; raised decks that continue over streets flattened), water as model 683.
7. Water tiles: water on every cell with water at any of 4 sample points, with bridge gaps
   closed and Miami's sea texture (sharper than LA's).
8. Configurable via environment switches (`CHI_START`, `CHI_EXPERIMENT`, `CHI_AREA_TEX`, …) for experiments.

### 6. Test infrastructure (2026-10-10)

- Three builds: **build-dev** (your dev client, desktop shortcut "Driver (dev client)"),
  **build-test** (for my tests while you play), and **build-release** (frozen until you
  declare a release).
- `devtools/dt.py`: snapshot summaries, live inspection, parallel captures at issue spots,
  soak tests, disassembly. Runs on copies in `devtest/`, never on your builds or saves.
- `devtools/lab.py`: continuous 6-slot test lab with a job queue, cached converter
  variants, idle soak tests, and regression captures whenever build-dev changes.
- `devtools/spots.json`: 16 named issue spots from your reports (park, overpass_s/e,
  blackwall, bridge, hang, shards, north, floating, quay, inwater, riverbridge, blackroofs,
  missingbld, beach_s, beach_n).
- Probe scripts for tiles, writes, road tables, overflow, and traces (`devtools/probe_*.py`).
- **Dev overlay and car flip (2026-10-11, Live test chat):** on-screen dev panel. **F10** shows game FPS,
  emulation %, X/Y/Z, D2 coordinates, heading, area/region and the wreck countdown. **L3+Triangle / F5** flips
  the car back onto its wheels. Found by reverse engineering: player car struct 0x8009B0A4; wreck rule =
  181 frames upside down (counter 0x80096920). The flip also **repairs the car** (zone damage + total zeroed). The freeze watchdog ignores time spent in the rewind browser.
- Project workflow (2026-10-11): `D:/recomps/CLAUDE.md`, skills `/chi-status /chi-build /chi-spot /chi-levcheck
  /chi-wrapup`, subagents chi-investigator / lev-analyst, `run.py` quiet runner, `levcheck.py` (DriverLevelTool),
  git for driver_personal, shared `WORKLOG.md`, planning chat as root.
- 2026-10-11: `devtools/run.py` (quiet runner), `devtools/levcheck.py` (DriverLevelTool check),
  OpenDriver2Tools source + 1.10 binaries in `D:\recomps\refs\`, `driver_personal/` under git,
  Claude Code project setup in `D:\recomps\CLAUDE.md` + `.claude/` (skills, subagents, guard hook).
- **Region sweep (2026-10-11/12):** `devtools/regionsweep.py` drove 10 s in each of the 111 drivable Chicago regions (batches 0–3 Live test, 4–11 QA-1, build-dev 20:13): **all 111 clean**, no freeze, crash, memory damage or fall under the map.

### 7. Bugs fixed (cause → fix)

| Symptom | Cause | Fix |
|---|---|---|
| Crashes in some streets | stale models: D1 only switches areas at region borders | switch entries everywhere + visibility-based area sets |
| Frozen picture, music still on | placeholder models drawn while loading | redirect to the empty model |
| Freeze + music stops, kernel memory overwritten | empty model had 0 polygons | 1 zero-size polygon |
| Play Again crash / scrambled textures | CD reader kept running after reset | spool reset fixes |
| Wrong models in streets | second area switch during a load | switch waits for the load |
| Invisible buildings, holes, noise | 32 palettes overwrote the next slot's first rows | max 31 palettes per page |
| Fatal "GP0 unknown command" | ground tiles overflowed the primitive buffer | tile guard + list cap |
| Black curves/junctions | LOD detail textures missing from areas | LOD models inherit areas |
| Trees as black squares | sprites had been converted | sprites kept as-is |
| Wrong distant ground textures | SUBDIVISION UVs | remapped |
| Tall objects vanishing | bounding spheres too small | fitted to vertices |
| LA's plane parked in a street | LA engine model | hidden |
| Cars falling through streets (2026-10-10) | primitive overflow into the road map tables (peak 0x235A4 > 0x1E000) | object guard + lower tile cap |
| Shards at Meigs Field, north textures garbage | palette overflow + shrinking | palette and shrink fixes |
| Bridge deck missing | palette overflow | palette fix |
| Black building tops (C4, 2026-10-11) | regions with no area loaded (area -1) | area switch: a region with none loaded loads its own area (exe patch) |
| Buildings missing behind trees (C5, 2026-10-11) | regions with no area loaded (area -1) | same area switch fix as C4 |
| Black wall / missing building faces (C6, 2026-10-11) | regions with no area loaded (area -1) | same area switch fix as C4 |
| Kernel overwritten + freezes at the north map edge (C25, 2026-10-11) | the engine's 2×2 region window read past the region table (Chicago had no empty region ring like LA) | 16×21 region grid with an empty ring (converter) |
| LA hung while loading with the engine patches but without Chicago (C14, 2026-10-12) | fixed along the way by the later engine/plugin fixes (verified by QA-2) | — |

---

## Open issues: Chicago (current work)

| # | Issue | Spot(s) | Status |
|---|---|---|---|
| C1 | **Missing ground strip** near the car (park); all ground missing under the south freeway overpass | park, overpass_s, missingbld | **backlog: visual only** (your decision 2026-10-12): QA-1 drove at park, missingbld and blackwall, and the car never fell, it stays at road height; holes are a rendering issue (single-polygon grass tiles near the camera, see NOTES ruled-out list). overpass_s spawn wreck is checked separately (QA-3) |
| C2 | **Overpasses stretch** close to the camera (D1 has no near-plane clipping); also **lane lines kink on curving highway sections** at polygon edges (affine warping of large D2 road polygons, your snapshots 022312–022344; runtime perspective texturing tried live: no change) | overpass_s, overpass_e | open, **needs an owner**: fix = subdivide large road polygons in the converter (Map quality plan P2; watch the primitive budget). Starts when you prompt for it (next step 6); 19:28: stretched checker slabs near the camera downtown; backlog |
| C3 | Water only in patches beside a bridge, smear in the gaps | riverbridge | **in progress** (Water): your verdict on the probe = good, "getting there". Next after far water (C19): the sand shows the water beneath (C1-like) and is drawn too far, then cut off before the view ends |
| C4 | Black building tops | blackroofs | ✅ **fixed** by the area -1 fix (exe patches 00:17); verified by you 2026-10-11 01:11 (snapshots 011139/011205: roofs normal) |
| C5 | Buildings missing behind trees | missingbld | ✅ **fixed** by the area -1 fix; verified by you 2026-10-11 01:18. The remaining smear moved to C1 (grass holes) and C10 (sky) |
| C6 | Black wall / missing building faces | blackwall | ✅ **fixed** (area -1 fix); verified by you 2026-10-11 02:42 (building faces OK). A ground hole under the car there → C1 |
| C7 | Texture downscaling in dense areas (~600 halvings) | north | improved; still visible; 2026-10-11 19:28: downtown very noisy again, 653 downscaled textures in the combined level (vs ~600); backlog |
| C8 | Rare stall (1 in 19 soaks): CPU stuck in BIOS CD read | overpass_s | ✅ **probably fixed by C25** (closed 2026-10-12, watch): not reproduced. QA-3's 4-min real drive near the south part showed no stall and the kernel intact; the region sweep (111 regions incl. all edges) was clean. Same family as C25 (edge regions reading past the region table), which the 16×21 grid fixed. Reopen if a BIOS CD stall shows up again |
| C9 | Driving into the river (sinking / end of round) | quay, inwater | 🧪 **in build-dev since 13:38, awaiting your test**: pink near water = missing "SEA" texture name → fixed; drowning ends the round (inwater, beach_n); ✅ **drowning works** on build-dev 20:13 and var_c20_full2 (Infrastructure 16:2x, Game Over with the car sinking; QA's "floats" = the car position freezes at Game Over) |
| C10 | LA's sky over Chicago: seams, and **LA's downtown skyline** shows as a dark blocky smear on the horizon to the east (heading ~80–120; seen at blackroofs/missingbld) | — | open (Map quality plan P5) |
| C11 | Loading bar stops halfway (sized for LA) | — | open |
| C12 | Minimap still shows LA | — | open |
| C13 | Damaged-wheel textures wrong | — | open |
| C14 | LA with the engine patches but **without** Chicago hangs while loading | — | ✅ **fixed** (QA-2, 2026-10-12 14:37): with chicago-la OFF the original Los Angeles loads and drives (13,441 units, max jump 95), kernel intact, no hang at 0x80035524. Also verified: Miami, San Francisco (hills) and New York with all engine patches + the Chicago plugin load and drive normally, kernel intact |
| C15 | Sand next to the lake (south near the park, north shore) | beach_s, beach_n | ❌ back in progress with C3 (one flat water level, see C3) |
| C16 | **Driving under a bridge teleports the car up onto the bridge** (highway; car wrecks). Driver 1's road map stores one height per cell, so where a road passes under another (D2 allows it) only one level survives | underbridge, underbridge2, trench_ew, trenchbridge, trenchbridge, wallclimb, median | **mostly fixed** (your test 19:15): ✅ underbridge, ✅ trenchbridge. Partial: deckfall (spawn OK; the shore keeps the car "in the air" over water, low priority until the water is levelled). ❌ wallclimb (the ramp slope plane extends outwards, the car drives in the air). With Height; round 2 in build-dev since 20:13 (highest plane not above the wheel, fitted ramp planes, footprints): please test rampsink, wallclimb, deckfall, bridges |
| C17 | Car **sinks into raised roads and ramps**. Same root cause as C16: decks are flattened to street level in the one-level road map | (live-test snapshots 23:58–00:17), deckfall_w, deckfall_e, deckramp_w, east_ramp_s, east_ramp_w | **partly** (your test 19:15): rampwedge good, needs fine-tuning; ❌ rampsink still has stairs. With Height; round 2 in build-dev since 20:13; **QA-3 final (13:31): the car drops off the top of BOTH south freeway ramps** (`deckfall_w`, `deckfall_e`). No missing cell: the top ramp cell (col 455) has a 2-plane surface (deck -1344 + street), the deck beyond is flat -1352 without a surface; the car falls while still on the 2-plane cell, so the deck plane isn't picked there. Suspect: round 2's plane footprints/guards inside the cell leave the deck plane short at the crest (Strategy). Ready for Infrastructure; **assigned to Infrastructure** with C20 (your go, 13:4x); 🧪 **probe ready in the same probe as C20** (desktop "Driver (probe - trench ends)", work/var_c20.lev): the crest cell now carries only the deck + ramp slope planes (no street plane as in 20:13); Infrastructure's runs: deckfall_e stays on the deck, deckramp_w over the crest and back smoothly; deckfall_w inconclusive (missed the narrow ramp), so your drive decides; QA-2 pre-driving; QA-2 pre-drive 14:01: deckramp_w still drops 1629 → 206 within 1.5 s (contradicts Infrastructure's run), deckfall_e fell once then stayed → Infrastructure round 2, probe on hold; QA-2 re-drive of round 2 (14:29): deckramp_w and deckfall_e stay on the deck (fixed); deckfall_w climbs but falls back before the crest (narrow ramp, maybe the rig's steering); **probe ready for you**; QA-2 (15:20) east freeway: south ramp OK on both levels; **west slope (east_ramp_w)**: build-dev launches + flips, but var_c20_full keeps the car on the street there = **correct** (Infrastructure 17:50: east_ramp_w drives into the SIDE of a one-cell-wide north–south ramp; the real approach east_ramp_s works on both levels; the full-plane level is better here) |
| C18 | **Car lights draw as squares**: headlight and tail-light glows show as translucent rectangles around the car instead of light dots (your snapshots 2026-10-11 01:15–01:16) | any (car lights on) | **backlog**. Likely the same family as C13: Driver 1's own car/effect textures replaced or misplaced by the Chicago texture repack (unverified) |
| C19 | Water further than 9000 units away isn't drawn (Driver 1's far tile range) | riverbridge, quay | 🧪 **probe ready** (desktop "Driver (probe - water)", spots riverfar, lakeview, beach_n, onbridge): water tile without LA's instance number + Miami's sea flags (drawn behind everything) → distant water continuous in Water's captures, no water through the sand, drowning OK. Ships with a plain converter run after your verdict |
| C20 | **Sunken freeway portals**: the col 661-664 trench runs into river tunnels (D2 tunnels have no surface planes, read as sea) and ends under a street; the car is lifted or drowns at those portals (D2 coords 19148,-119243 / 19148,-180607 / 19148,-284016) | c20_p2n, c20_p2s, c20_p3n, c20_wall | 🧪 **probe ready** (desktop "Driver (probe - trench ends)", work/var_c20.lev, also has the C19 far water). Cause: D2 tunnels have no surface, so the 1352 trench met street cells with no ramp. Fix: covered stretches ≤ 12 cells get the trench floor (continuous tunnel), dead ends rise over 6 cells with sloped planes, guards cover the whole street cell beside the trench. Infrastructure's runs: p3n + p2n clean; p2s needs your manual drive (start point inside the trench); **c20_wall still lifts 1399** at the north end of D2's own sloped embankment, so your verdict; QA-2 pre-drives the probe (incl. c20_p2s); QA-2 pre-drive 14:01 of var_c20: p3n no lift (was +3309), p2n jump 719 (was 1373); still bad: p2s_out flip, c20_wall lift ~1335 + flip → Infrastructure round 2, probe on hold; **round 2** (Infrastructure 15:05, var_c20.lev replaced): c20_wall fixed (guard-only cells keep the deepest trench level; holes beside trenches take the trench level; 166k units in the trench, no jump > 20); deckramp_w's drop was the test rig turning back down the ramp; p2s_out flip = start artifact inside the now continuous tunnel. QA-2 re-driving, then to you; QA-2 re-drive of round 2 (14:29): p2s_out (from p2n south) no flip, p3n no lift, p2n no lift while driving; **c20_wall still lifts ~782 + flip** (contradicts Infrastructure); **probe ready for you**; **your decision 2026-10-12: converter-only fix** for the guard hazard (the plugin swaps only plane heights, so a partial guard plane took over the whole cell): all planes of a multi-plane cell get full-cell footprints, the lower floor extends under the upper level, the plugin's height choice picks the floor under the car. Trade-off accepted: leaving a street edge over the trench floats until the cell ends, then drops. Infrastructure building it as a new variant; QA-2 pre-drives; 🧪 **probe for you: desktop "Driver (probe - full planes)"** = work/var_c20_full2.lev (your converter-only concept + the p2n pit fix: a no-surface cell between street and ramp top had been set to trench depth too early); Infrastructure's run: p2n south down the ramp, back up, no pit, no flip; other QA notes look like rig artifacts, your drive decides; **review round done → var_c20_full3.lev** (16:2x): real & fixed #1, #4, #5 (1898 of 2932 ramp cells were false side ramps → 346), #6, #7, #8, #10 (#9 via bucketing); #2 not real, #3 latent. Infrastructure: underbridge, deckfall_e, wall_west clean; wallstop1 no flip; deckramp_w still flips (C17 crest). QA pre-drive running before you get it; 🧪 **for your test now: desktop "Driver (probe - full planes)" = var_c20_full4.lev** (all review fixes + own plane first); spots: underbridge, trenchbridge, c20_p2n south, c20_wall both sides, deckramp_w, deckfall_e/w, rampsink, unevenedge, wallstop1, hs_lift_6_9 |
| C21 | Uneven ground at the north city edge by the lake: single cells 912–1135 below street level (probably D2's lower lakefront path) inside street-level grass; the car falls into pits and flips | unevenn | ✅ **closed: not reachable in normal play** (QA-2, 2026-10-12 14:12): pit cells at 1084/1132 next to street-level grass, but drives from the spot in 4 directions stop at a barrier within ~1 s; no fall, no flip |
| C22 | 🔴 **Crash while driving since the 352-patch engine** (C16/C17 height-aware collision patch, build-dev rebuilt 03:03): every lab soak since 03:17 dies after ~2000 units (game jumps to address 0, return address 1, no fatal message); short captures still pass. Reproduced 2026-10-11 12:33 on a build-dev copy (2/2). Last passing soak 02:52 (278 engine + yesterday's plugin changes) | all soaks (e.g. underbridge2) | ✅ **closed**: exe loop removed, selection now in the plugin (no code outside the compiled image); build-dev 13:38 soak-checked 4/4 |
| C23 | **Curved walls stop the car dead** at full speed at the joints between wall segments instead of letting it slide along (you want smooth sliding). Likely the collision boxes of straight wall segments on curves (overlap/bevel along curves, converter) | wallstop1, wallstop2 | **backlog** (your decision 2026-10-11: major issues first, small details later) |
| C24 | **White untextured debris shards** when smashing props at speed | shards | **backlog** (your decision 2026-10-11: major issues first); group with C13/C18 when it's picked up; 19:28: purple/white untextured props downtown, same family |
| C25 | 🔴 **Kernel memory overwritten, then freezes** in your dev client (build-dev 13:38) in the far north (region 332/333, D2 ≈ -136k, 685k): snapshots from 14:31:40 show "kernel BAD", followed by 3 hang snapshots (last store PC 0x8002CD94) | kernelnorth | ✅ **fixed**: verified by you 2026-10-11 19:1x (kernelbad, no freeze). 16×21 grid with an empty region ring |
| C26 | 🔴 **Freeze after Play Again following drowning in the lake** at the north beach start (`beach_n`): car drowns → Game Over → Play Again → code runs into data | beach_n | ✅ **closed: not a real freeze** (Water, 20:40). Drown → Play Again 7/7, pause → Restart 16/16, Quick Replay/Film Director 4/4 all clean. The lab "hangs" all came after the test drive had pressed Exit and left Chicago (menu / a Miami game); the model-table alarm was memory reused after leaving the level. Follow-up: C27 |
| C27 | **Possible freeze after leaving Chicago** (Exit → menu, or the next game in another city): seen only in automated test drives that wandered out of Chicago; it may also be a test-tool detection error. C8-like | — | ✅ **not reproduced, closed** (QA-3, 2026-10-12 13:15): no freeze over the menu switches and with real driving afterwards (Miami 30 s ×2, Chicago 60 s ×2 after re-entry). The sometimes-failing Exit was the test's own menu navigation |
| C28 | 🔴 **Shore wall across a street** at the north-west lakeshore (`shorewall`): a grey slab (probably one of the new extended shore walls) blocks the street; the car hits it, gets launched and falls under the map into a pit (1177 deep) beside the street | shorewall, shore_strip, shore_bank | **slab fixed in the probe** (one-sided walls, your verdict good). Shore walls stay **without collision** for now (you had no complaint, 19:54; say if you want them solid). Open, cosmetic: sawtooth wall tops with water gaps along diagonal shores (`quaydiag`). The shore physics (slants/launch/pit) is D2 road data (Height); approved probe state + walls facing the water in build-dev since 20:13; QA-3 collecting the shore physics evidence (NW lakeshore), 2026-10-12; **QA-3 (2026-10-12 13:59), ready for a fix:** at the NW shore strip col 425 rows 180–186 (spot shore_strip) the car bounced 34× and was launched up to y 16362: a 2-plane sloped strip (height 0, surface 25) sits between flat land (col 423–424) and a bank at stored 1176 (col 426, surfaces 38/341, spot shore_bank), then water (683) at col 427; the car is squeezed between slope and bank. The 1177 pit and the slanted grey walls elsewhere were not reproduced; **next for Infrastructure** after the C20/C17 round 2 (your go 14:0x) |
| C29 | 🔴 **Blue boxes over inland streets**: huge solid blue boxes at building height above streets + turquoise strips at building bases, inland (area 2, region 232); probably the new far water planes placed over land | blueboxes | 🧪 **probe ready**: RIVER3A only in the areas with walls; permanent pages back to 3; fix in build-dev since 20:13 |
| C30 | Downtown: big black building faces (C6-like) and buildings swapping while an area loads in the far north | — | **backlog** (cosmetic, your rule) |
| C31 | **Facade details flicker** frame to frame (shop windows, trim, window frames on building walls), in many areas. Coplanar decal polygons inside a building model swap depth order (D1 sorts per polygon). Fix idea: the converter pushes decals a few units out along the face normal (d1models.py) | flicker, flicker2 | **backlog** (cosmetic, your rule) |
| C32 | **Purple/cyan shopfronts** on building ground floors (wrong palette in the texture repack), maybe also the purple/white park props | purpleshops | 🧪 in the water probe (Water's one capture faced away, inconclusive); in build-dev since 20:13, check purpleshops |
| C33 | 🔴 **Freeze at an area switch (normal speed)** (9 → 1 inside region 229 while driving west, Chicago's own-entry switch rule, D1 -231083,341528; your hang snapshot 193318). The world renderer loops forever at 0x80030A44–0x80030A4C on garbage model group data (a2 = 0x7FFFFFFF) while the area is still loading (loading flag stuck, 16 sectors left). Same family as the patched trap at 0x80030B00, but a second loop the guard doesn't cover. Not C25 (kernel intact) | areafreeze | 🧪 **in build-dev since 20:13, awaiting your test**: plugin function-entry hook on the area load (Chicago only), 68–126 spool entries redirected per switch, no freeze in Height's drives (10 switches). **Your probe:** `areafreeze`, drive west through the 9→1 switch; QA-2 verifying the fix at areafreeze (driving west through 9→1); **QA-2 (2026-10-12 13:40): 2 passes through the 9→1 switch at areafreeze without a freeze** (kernel intact; before the fix it froze at the first pass) + Height's 10 switches → **very likely fixed**; your own drive there is the final confirmation | **Fixed, in build-dev 20:13** (Height): function-entry hook on 0x80033B10 (game.toml `mod_function_entry_funcs`, Chicago only) redirects the spool entries before the texture pages are queued; build-test + build-dev copy: 10 switches crossed, no freeze. Awaiting user test (areafreeze, drive west).
| C34 | 🔴 **Launch under a bridge** at cell 391,569 (area 17, region 182): reproduced 5 of 20 passes on build-dev 20:13 (QA-1), dy +2281…+4268 within 0.5 s (once ~11,000 in the sweep). Region tables and parity unchanged at the lift → not a stale table. Likely the round-2 guard footprint takeover (plugin swaps only plane words); RAM snapshots devtest/_qa1/lift/ram_pass02..06.bin | hs_lift_6_9 | **major**: QA-1 re-tests the same 20 passes on the probe (var_c20_full2, then the review-fix variant); evidence to Infrastructure; Infrastructure's suspect (16:2x): during the plugin's 60-vblank idle after a spool, slot 0 keeps a plane selected for another cell/height → street plane under the bridge (+2600); also the 3×3 select loop lets a neighbour with the same shared surface override the car's cell (~25 cell-levels with errors ≥ 500). Proposed plugin fix (needs your go): the centre cell decides last, shorter idle. QA-1 testing on var_c20_full3; QA-1 on the probes (16:3x): inconclusive — both var_c20_full2 and full3 spawn the car SUNK at y ≈ -2396 at this spot (build-dev ≈ 100) → possible probe regression, Infrastructure checking; the C34 rerun waits for a street-level spawn; sunk spawn on the probes fixed in **var_c20_full4.lev** (16:55: planes were written lowest first, and during the plugin's idle the engine takes slot 0 → lower road; now the cell's own plane first); QA-1 re-tests C34 on full4; QA-1 (17:05): control on build-dev 4/20 lifts (valid); on full4 not testable yet: crashes (PC=0 after an area switch, one FAIL-FAST dispatch 0xB0) during position write-backs = probably teleport artifacts; retesting with real driving only; **Infrastructure's hypothesis (17:0x):** our SPOOL_DRAIN patch zeroes the spool total too early → it goes negative (−170 seen) → the reader (0x80034CE0, stops only at exactly 0) chains into a stale slot (kernel overwrite, PC=0 / 0xB0) and the plugin stays idle (total ≠ 0) → stale planes → lifts. Proposed fix (engine 1 word beqz→blez + plugin idle only while total > 0) needs your go; QA-1 logging the signed total to confirm |

---

## ⏸ Paused 2026-10-11 ~20:30 (your usage limit). Resume here

- **Your dev client = build-dev 20:13**: C33 area-switch freeze fix (plugin hook, Chicago only), ramp round 2, approved water state. **Your test of it was in progress** (areafreeze west, rampsink, deckfall, bridges, purpleshops).
- **Water:** C19 far water, your priority: cause found (tile 683 inherited LA's instance number → skewed far squares); fix next. Then the sand (water showing through, drawn too far).
- **Height:** waiting for your verdict on 20:13; C20 trench-end observation logged.
- **Live test:** region sweep 40/111 regions clean; the next batch on your go.
- **Backlog by your rule:** C2, C7, C13, C18, C23, C24, C30, C31 (+C32 if still purple).
- **Chats:** this one = recomps-27 [fab41b] (planning), Water, Height, Live-test environment. Their pause lines are in WORKLOG.md.

## QA queue (Strategy keeps it filled; QA-1/2/3 take the top free item when done)

Format: `[owner or free]` item. A QA chat marks an item as its own (`[QA-n]`) when it starts it, and as `[done]` with a pointer to its report. Gameplay faults only (driving, collision, falls, lifts/flips, freezes); cosmetics are backlog.

1. `[done]` (QA-1, 2026-10-12: 111 regions, no under-map; lifts/drops rerun: the 10k lift at region 6,9 did NOT repeat; repeatable: FLIPs only; spots hs_lift_6_9, hs_lift_7_19, hs_drop_8_3; raw devtest/_qa1/height, rerun in the same folder) Height sweep over all 111 regions (lifts/drops/flips/under-map/stuck per cell) → list of new places.
2. `[done]` (round 2 var_c20 14:19; QA-2 report 14:2x: deckramp_w/deckfall_e stay on deck, p2s_out no flip, p3n no lift, wall still lifts ~782 then flips, deckfall_w climbs to 901 and falls) Re-drive the C20/C17 round-2 probe: c20_p2n, c20_p2s, p2s_out, c20_p3n, c20_wall, deckfall_w/e, deckramp_w; better/same/worse vs. the 14:01 numbers.
3. `[done]` (QA-3, 14:4x; table in QA-3's report to Strategy, raw log devtest/_out/logs/1012-140728-qa3_baseline.log) Spot baseline on build-dev 20:13: one real drive at every gameplay spot in spots.json (skip cosmetic ones like flicker/purpleshops); per spot: OK / lift / drop / flip / stuck / freeze. Goal: which known issues are already fixed and which still fail.
4. `[done]` C21 north-edge pits (spot unevenn): QA-2 report 14:1x. Pit block = cells at 1084 and a 1132 band beside grass at 4 (window cols 484-496, rows 225-235). Four drives from the spot (NE, SE, E, S): the car stops against a barrier within about 1 s at y 82-140, never enters the pit cells, no fall or flip. Pits look unreachable by normal driving from there.
5. `[done]` (QA-1, 2026-10-12: offline road-level table from work/road_levels_fd68052b.pkl, 3x3 cells; runtime table at 0x8001EF00 not read) Follow-up of NEW places from the height sweep (item 1): one per QA, with effective road map values per cell.
6. `[free]` After every build-dev ship: a smoke drive of the spots the ship touched.
7. `[done]` (QA-2 report 14:3x: Miami/SF/NY load, kernel ok, no lifts/drops; C14 LA with chicago-la OFF loads and drives; car stops in drives after 25-30 s) **Original cities regression + C14** on build-dev 20:13 (exe with all engine patches + Chicago plugin): (a) with the chicago-la feature ON: Miami, San Francisco, New York each Take a Ride + 60 s real drive (load OK, no freeze, no physics oddities, hills/ramps in SF); (b) with chicago-la OFF (test copy state only): original Los Angeles load + drive = C14 (hung while loading before). Report per city.
8. `[done]` (QA-2 report 15:1x: 4 regions x 300 s, no freeze, kernel ok, no cops seen, felony not read; drives end in wrecks) **Felony/cops robustness in Chicago**: Chicago has no road network for AI yet (Stage B), so cops/traffic may misbehave. Drive aggressively in several regions (speeding, hitting props, ramming) for ~5 min each until felony rises; watch for freezes, crashes, kernel damage, cars spawning inside buildings or falling. Report anything that breaks.
9. `[done]` (QA-2 15:08: mixed; p2n south sinks to the tunnel level on the street = probably street plane missing over covered tunnel cells → Infrastructure) Pre-drive it: c20_wall from BOTH sides (west start D1 -165400,-206700 and the spot), underbridge, trenchbridge, deckramp_w, deckfall_e/w, rampsink, c20_p2n south, c20_p3n.
10. `[done]` (QA-3 15:4x, log 1012-145810-qa3_baseline_probe.log: better floating/underbridge2/c20_wall/wallclimb/shore_strip; worse underbridge +1688, unevenedge, wallstop1, deckfall_e, deckramp_w; no freezes) **Spot baseline on the probe var_c20_full.lev** (same 37 gameplay spots and method, but ignore the first 3 s after spawn and record the start y, so start artifacts don't count as lifts); output a before/after table vs the 20:13 baseline.
11. `[done]` (QA-2 report 15:2x: south ramp reaches deck on both levels; west slope launches+flips on build-dev, missing on var_c20_full) **East freeway (overpass_e)**: QA-2 saw y 771–2031 above the deck + flip there. Like the south freeway check: find the deck and ramp cells from the effective road map (QA-3's method), drive up each ramp on build-dev 20:13 AND on work/var_c20_full.lev; report crest/deck-end falls and launches with cells.
12. `[later: not for Haiku]` (QA-2 looked, released: no Driver 1 symbol map in the repo, Driver 2 playerFelony in REDRIVER2 ai.c/cop_ai.c is the only reference; needs a disassembly pass of Driver 1 or a RAM-diff campaign in Miami, not started) **Research for Stage B (cops/traffic)**: find Driver 1's RAM addresses for the player's felony level, cop spawn/pursuit state and the civilian car slots (REDRIVER2 ai.c/cop_ai.c as a guide, RAM diffs while driving in an original city like Miami where cops work). Output: an address table for NOTES.md.
13. `[QA-2 subagent]` **Height sweep on the probe level** work/var_c20_full4.lev (restarted; full2 got 54 regions: 0 lift/drop): the same method as QA-1's sweep (all 111 regions, ~45 s real driving, lifts/drops/flips/under-map/stuck per cell; reuse QA-1's script, read-only), so we get a before (build-dev, QA-1) / after (probe, QA-2) comparison and catch new problems like the lost east_ramp_w slope.
14. `[done]` (QA-3 15:5x, devtest/_out/logs/1012-155234-qa3_trace.log → Infrastructure) Precise traces (x/y/cell/surface per 0.25 s) of the 5 worse spots on var_c20_full2 (underbridge, unevenedge, wallstop1, deckfall_e, deckramp_w) + underbridge on build-dev, onset cells → Infrastructure.
15. `[done]` (QA-1: reproduced 5/20, no table change → C34) **Reproduce hs_lift_6_9** (rare launch to y ≈ 11,000 under a bridge, area 17, region 6,9, cell 391,569; the map data doesn't explain it → suspect: a height read from a wrong/stale region table). Up to ~20 passes under that bridge in both directions (also through an area switch if one is near); on a launch: immediately read the runtime road-map lookup (0x8001EF00 path: region table pointers at 0x8009D8F4, parity *0x80097374, current area/region) + car position, and dt.py snapshot. On build-dev 20:13.
16. `[done]` (QA-3: inconclusive, no drowning on build-dev either → Infrastructure verifies) **Drowning/restart check on the probe** var_c20_full2 (water level 984/1084 + walls changed): at inwater, quay, beach_n, riverbridge, onbridge, lakeview: drive into the water once each → the car sinks, round ends, Play Again works, no freeze; also check that no street/quay cell drowns the car by mistake (driving along the quays).
17. `[QA-3 subagent]` (now on var_c20_full4.lev; full3 got 14 spots) Re-run QA-3's 37-spot baseline on it → before/after table vs var_c20_full.
18. `[QA-1]` **C34 on the probe**: the same 20 passes at hs_lift_6_9 on work/var_c20_full2.lev (and later on the review-fix variant): does the full-plane level remove the launch? Same evidence capture.
19. `[QA-3 subagent, after 17]` **Original cities, other modes**: in Miami (and one more original city) start each Driving Game once (Pursuit, Getaway, Cross Town Checkpoint, Trail Blazer, Survival) and a short Undercover mission if reachable from a save; does each load and play 60 s without freeze/crash on the current build-dev exe (all engine patches + Chicago plugin)? Report per mode.

## Next steps (agreed order, 2026-10-11)

**Priority rule (yours, 2026-10-11):** the most significant issues first (crashes, freezes, falling through the world, missing water/ground), small details later (cosmetics such as C13, C18, C23, C24).

How a step runs: it is handed to a worker chat, which automates its build/test loop until it judges the step done → **awaiting your test** in build-dev → you approve ("satisfied") → marked done. The next step starts **only when you prompt for it**.


1. **Water and lake shore** (C3, C9, C15, C19): **in progress again** (Ongoing Tests). Your test 14:16 failed (water not filled at quays/parks). Your target: one flat water level everywhere like Miami, at ≈984 below street (beach_n sand base), parks excluded.
2. **Original cities stay intact** (C14, C8): fix LA hanging with the engine patches; add Miami/SF/LA/NY captures to the test lab.
3. ✅ **Quick triage, done**: C4, C5, C6 all fixed by the area -1 fix and verified by you (2026-10-11).
4. **Stage B**: roads, then traffic, then cops (Milestone 1 core).
5. **8-city feasibility study** (research only, alongside 4): every 4-city limit in the exe and menus.
6. **Chicago polish**: C1/C2 time-boxed with a fresh approach, C7, minimap (reuse `d2overlay.py`), sky, loading bar, cars, music.
7. Make the converter work for any D2 city, then the second city.

Not yet: missions, night versions, Driving Games data (wait for the scope answers).

---

## Map quality plan (2026-10-11, ordered by expected payoff)

Detail for "Next steps" 6 (Chicago polish) and the preparation of 4 (Stage B); the order of
"Next steps" wins. Tools now available offline: **DriverLevelTool** (OpenDriver2Tools 1.10, `refs/OpenDriver2Tools-bin`)
parses the converted LEV independently, exports it to OBJ/TGA, shows Driver 1 road data and
collision boxes in a viewer; `devtools/levcheck.py` wraps it. Its source (`regions_d1.cpp`,
`d2_types.h`) is a second description of the Driver 1 road lumps.

| # | Target | Approach | Check |
|---|---|---|---|
| P1 | C1 missing ground near the car | The hole follows *single-polygon* grass tiles. Converter experiment: split every single-polygon tile into a 2×2 grid (4 polygons, same UVs) so no tile takes Driver 1's single-polygon path; compare against `tile_novtx` (already tried) | lab capture `park`, `overpass_s` |
| P2 | C2 overpass stretching | Driver 1 has no near-plane clipping, Driver 2 subdivides big road polys (REDRIVER2 `draw.c` makeMesh 5×5). Converter: subdivide polygons longer than ~1500 units in road-flagged (0x2000) and bridge/overpass models into 2–4 pieces; bounded polygon growth | `overpass_s/e` captures; primitive peak must stay < 0x1E000 |
| P3 | C7 texture downscaling | Compare Driver 2's own per-area texture-page sets (SPOOLINFO area tpages of `d2_CHICAGO.LEV`) with the 16-slot budget the converter assumes; reuse D2's area→page assignment where possible instead of re-deriving; shrink only textures never seen within 2000 units | `levcheck` page count, `north` capture |
| P4 | C12 minimap | Both games carry OVERLAYMAP (lump 24, RNC2 palette + chunks; REDRIVER2 `overmap.c`); `chicago/d2overlay.py` already started on it: convert D2's overlay map with the ×1.32 rescale instead of keeping LA's; DriverLevelTool `-overmap` exports both for a side-by-side check | overhead map in Take a Ride |
| P5 | C10 sky | DriverImageTool unpacks D1 PSX sky and converts D2 `SKYn.RAW`; build Chicago's sky in D1's layout | visual |
| P6 | Stage B roads | See NOTES.md Plan B (counts: 838 straights + 151 curves + 252 junctions vs D1 max 410/258). Validate generated ROADS/JUNCTIONS/BOUNDS offline in the DriverLevelTool viewer before the first game run | viewer road overlay, then traffic |
| P7 | Music (M2) | DriverSoundTool: D2 MUSIC.BIN → XM; check D1 MUSIC.BIN against the demo XM/SBK format the tool already handles | playback |
| P8 | Regression safety | After each converter change: `/chi-levcheck` (object/face deltas) + lab captures of all spots | counts stable |

## Backlog: the road to 8 cities

The large milestones in order. Each one should leave a playable build.

### Milestone 1: Chicago drivable with traffic and cops (in LA's slot)
- [x] Stage A: world (models, textures, streaming, collision, water). Polish = issues C1–C9 above.
- [ ] **Stage B: roads.** Rasterise D2's surface onto D1's road map + ROADSURF; rebuild
      ROADS / JUNCTIONS / BOUNDS from D2's STRAIGHTS2 / CURVES2 / JUNCTIONS2 so traffic AI can drive.
- [ ] **Multi-level roads (C16 + C17), in progress.** Your decision 2026-10-11: engine patch at 0x8001F274 so the
      collision picks the surface polygon nearest the car's height, plus a generated ROADSURF with both levels for
      ~113 crossing cells and sloped planes for ramps. Owner: Height engine; verified with you by Live test at
      `rampsink`, `underbridge`, `trenchbridge`. Must not change the four original cities' driving.
- [ ] **Stage B feasibility (EXP, 2026-10-12):** D2 Chicago 779 straights / 151 curves / 252 junctions; D1 max seen 410 roads / 258 junctions (NY). D1 roads are axis-aligned only (777/779 Chicago straights are), no curves (→ corner junctions or dropped). Merging collinear straights: 557–727 roads (still > 410), 239 junctions (fits; 390 with curve corners). Unknown and decisive: the exe's real road/junction array caps and the LOADTIME buffer size (roads add ~38.6 KB → ~125 KB vs Miami 109 KB). Scripts: devtest/exp_work/. Runtime probe (EXP): **no fixed road array**. ROADS/JUNCTIONS/BOUNDS/JUNCBOUNDS are copied verbatim into a sequential in-memory chain (with SUBDIVISION, ROADSURF, …), unchanged during play; the only limit is the room after the chain (NY 1.9 KB after a ~50 KB chain; Chicago already runs with a ~322 KB in-memory section). Chicago probe (EXP): the road lumps live in the INMEMORY chain (Chicago 322,536 B from 0x80137C38 to 0x80186878; NY 241,684 B; Miami 175,836 B); after it a per-city table (moves with the chain), then free space up to ~0x801C0000 (~235 KB, ~76 KB of it used) → +32.5–38.6 KB of road lumps **likely fit**, unconfirmed. Next: a padded test level to confirm.
- [ ] Civilian traffic on Chicago streets.
- [ ] Cops: spawning, pursuit, roadblocks on Chicago roads.
- [ ] Soak-test stability (no crash/stall across all spots).

### Milestone 2: Chicago feature-complete
- [ ] Own minimap (C12), sky (C10), loading bar (C11).
- [ ] D2 car models (player car, traffic, cops) and D1 exe cosmetics (lights C18, wheels C13).
- [ ] D2 Chicago music → D1 MUSIC.BIN.
- [ ] Night version (D2 ships a night LEV), if D1 modes need it.
- [ ] Driving Games data for Chicago (start points, checkpoints, routes), if in scope (see questions).

### Milestone 3: Reusable converter
- [ ] Remove Chicago-specific assumptions from `convert.py` (names, scale, water model, start position, events) so it takes any D2 city.
- [ ] Shared pipeline for minimap, sky, music, and cars per city.

### Milestone 4: The other Driver 2 cities (each tested first in LA's slot, like Chicago)
- [ ] **Havana** (D2 disc 1). Special: ferry and boat events, floating boats.
- [ ] **Las Vegas** (D2 disc 2). Special: trains and monorail events.
- [ ] **Rio de Janeiro** (D2 disc 2). Special: floating boats.
- [ ] Decide per city what replaces D2's moving events (D1 has no event system: static models, or dropped).
- [ ] Per-city open issues (expect a list like Chicago's for each).

### Milestone 5: Engine support for 8 cities (the big engine step)
- [ ] Find every table in the D1 exe that is sized for 4 cities (LEV file names, start positions, car sets,
      cop settings, music, sky, minimap, Driving Games data, etc.) and extend it to 8.
- [ ] Add the 4 new LEV files and assets to the disc (the runtime can already serve files beyond the image end).
- [ ] Frontend: city selection for 8 cities in Take a Ride and Driving Games (menus, names, pictures).
- [ ] Unlock All and save data: "cities unlocked" goes beyond 4; keep memory-card saves compatible.
- [ ] Fix C14 so original LA works again with the engine patches, then give Chicago its own slot and **restore LA**.
- [ ] Memory and streaming budgets checked for all 8 cities.

### Milestone 6: Game modes in every city
- [ ] Take a Ride in all 8 cities (the core goal).
- [ ] Driving Games in the 4 new cities (D1 games need per-city data: Pursuit, Getaway, Cross Town Checkpoint, Trail Blazer, Survival, Dirt Track).
- [ ] Undercover/story missions in the new cities: only if decided (large effort; D2's missions use a different script system).

### Milestone 7: Release
- [ ] Update build-release once you declare a release; Quiver launches it.
- [ ] Final docs: README re-apply steps for every new part (exe patches, runtime, packages, assets).
- [ ] Back up the converter inputs/outputs and tools (`chicago/work/` is not reproducible without your discs).

---

## Open questions for you

1. **Scope per city:** is "playable" Take a Ride only, or also Driving Games, or even missions?
2. **Order:** after Chicago, which D2 city next?
3. **Timing of the 8-city engine work (M5):** before converting the other cities (each gets its own slot right away), or after (keep testing in LA's slot)?
4. **Day/night:** should the D2 cities offer night versions like D2 does?
