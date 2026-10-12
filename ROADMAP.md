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

---

## Open issues: Chicago (current work)

| # | Issue | Spot(s) | Status |
|---|---|---|---|
| C1 | **Missing ground strip** near the car (park); all ground missing under the south freeway overpass | park, overpass_s, missingbld | under investigation; also pink/green noise on sand/ground tiles close to the car near water (water step, 2026-10-11); also grass holes beyond the road at missingbld (2026-10-11); long ruled-out list in NOTES.md; the hole follows single-polygon grass tiles within 2000 units of the camera |
| C2 | **Overpasses stretch** close to the camera (D1 has no near-plane clipping); also **lane lines kink on curving highway sections** at polygon edges (affine warping of large D2 road polygons, your snapshots 022312–022344; runtime perspective texturing tried live: no change) | overpass_s, overpass_e | open, **needs an owner**: fix = subdivide large road polygons in the converter (Map quality plan P2; watch the primitive budget). Starts when you prompt for it (next step 6); 19:28: stretched checker slabs near the camera downtown; backlog |
| C3 | Water only in patches beside a bridge, smear in the gaps | riverbridge | **in progress** (Water): your verdict on the probe = good, "getting there". Next after far water (C19): the sand shows the water beneath (C1-like) and is drawn too far, then cut off before the view ends |
| C4 | Black building tops | blackroofs | ✅ **fixed** by the area -1 fix (exe patches 00:17); verified by you 2026-10-11 01:11 (snapshots 011139/011205: roofs normal) |
| C5 | Buildings missing behind trees | missingbld | ✅ **fixed** by the area -1 fix; verified by you 2026-10-11 01:18. The remaining smear moved to C1 (grass holes) and C10 (sky) |
| C6 | Black wall / missing building faces | blackwall | ✅ **fixed** (area -1 fix); verified by you 2026-10-11 02:42 (building faces OK). A ground hole under the car there → C1 |
| C7 | Texture downscaling in dense areas (~600 halvings) | north | improved; still visible; 2026-10-11 19:28: downtown very noisy again, 653 downscaled textures in the combined level (vs ~600); backlog |
| C8 | Rare stall (1 in 19 soaks): CPU stuck in BIOS CD read | overpass_s | open; probably the same cause as C25 (edge regions reading past the region table), recheck after the C25 fix |
| C9 | Driving into the river (sinking / end of round) | quay, inwater | 🧪 **in build-dev since 13:38, awaiting your test**: pink near water = missing "SEA" texture name → fixed; drowning ends the round (inwater, beach_n) |
| C10 | LA's sky over Chicago: seams, and **LA's downtown skyline** shows as a dark blocky smear on the horizon to the east (heading ~80–120; seen at blackroofs/missingbld) | — | open (Map quality plan P5) |
| C11 | Loading bar stops halfway (sized for LA) | — | open |
| C12 | Minimap still shows LA | — | open |
| C13 | Damaged-wheel textures wrong | — | open |
| C14 | LA with the engine patches but **without** Chicago hangs while loading | — | open (older); must be fixed before LA and Chicago can coexist |
| C15 | Sand next to the lake (south near the park, north shore) | beach_s, beach_n | ❌ back in progress with C3 (one flat water level, see C3) |
| C16 | **Driving under a bridge teleports the car up onto the bridge** (highway; car wrecks). Driver 1's road map stores one height per cell, so where a road passes under another (D2 allows it) only one level survives | underbridge, underbridge2, trench_ew, trenchbridge, trenchbridge, wallclimb, median | **mostly fixed** (your test 19:15): ✅ underbridge, ✅ trenchbridge. Partial: deckfall (spawn OK; the shore keeps the car "in the air" over water, low priority until the water is levelled). ❌ wallclimb (the ramp slope plane extends outwards, the car drives in the air). With Height; round 2 in build-dev since 20:13 (highest plane not above the wheel, fitted ramp planes, footprints): please test rampsink, wallclimb, deckfall, bridges |
| C17 | Car **sinks into raised roads and ramps**. Same root cause as C16: decks are flattened to street level in the one-level road map | (live-test snapshots 23:58–00:17) | **partly** (your test 19:15): rampwedge good, needs fine-tuning; ❌ rampsink still has stairs. With Height; round 2 in build-dev since 20:13 |
| C18 | **Car lights draw as squares**: headlight and tail-light glows show as translucent rectangles around the car instead of light dots (your snapshots 2026-10-11 01:15–01:16) | any (car lights on) | **backlog**. Likely the same family as C13: Driver 1's own car/effect textures replaced or misplaced by the Chicago texture repack (unverified) |
| C19 | Water further than 9000 units away isn't drawn (Driver 1's far tile range) | riverbridge, quay | **Water's priority now (yours, 19:4x, "till we fix it")**: only water where water belongs, visible far out without chunks or gaps, **done the way Miami/NY/LA do it** (copy Driver 1's own distant-water method); **cause found** (Water 23:20): water tile 683 inherited instance number 7 from LA's tile 316, so the engine uses model 7's vertices → far tiles become skewed squares (the chunks/gaps) |
| C20 | **Sunken freeway portals**: the col 661-664 trench runs into river tunnels (D2 tunnels have no surface planes, read as sea) and ends under a street; the car is lifted or drowns at those portals (D2 coords 19148,-119243 / 19148,-180607 / 19148,-284016) | — | **backlog** (found by the C16 chat, 2026-10-11; needs a tunnel floor in the road map, i.e. a road-data source other than the D2 surface); Height's drive 20:13: hit a trench wall near D1 (-165400,-206700), later flipped at (-159800,-203200) after reversing; probably this family |
| C21 | Uneven ground at the north city edge by the lake: single cells 912–1135 below street level (probably D2's lower lakefront path) inside street-level grass; the car falls into pits and flips | unevenn | **backlog, low priority** (you: not a drivable area in normal play). One-level road map limit; may improve with the engine patch |
| C22 | 🔴 **Crash while driving since the 352-patch engine** (C16/C17 height-aware collision patch, build-dev rebuilt 03:03): every lab soak since 03:17 dies after ~2000 units (game jumps to address 0, return address 1, no fatal message); short captures still pass. Reproduced 2026-10-11 12:33 on a build-dev copy (2/2). Last passing soak 02:52 (278 engine + yesterday's plugin changes) | all soaks (e.g. underbridge2) | ✅ **closed**: exe loop removed, selection now in the plugin (no code outside the compiled image); build-dev 13:38 soak-checked 4/4 |
| C23 | **Curved walls stop the car dead** at full speed at the joints between wall segments instead of letting it slide along (you want smooth sliding). Likely the collision boxes of straight wall segments on curves (overlap/bevel along curves, converter) | wallstop1, wallstop2 | **backlog** (your decision 2026-10-11: major issues first, small details later) |
| C24 | **White untextured debris shards** when smashing props at speed | shards | **backlog** (your decision 2026-10-11: major issues first); group with C13/C18 when it's picked up; 19:28: purple/white untextured props downtown, same family |
| C25 | 🔴 **Kernel memory overwritten, then freezes** in your dev client (build-dev 13:38) in the far north (region 332/333, D2 ≈ -136k, 685k): snapshots from 14:31:40 show "kernel BAD", followed by 3 hang snapshots (last store PC 0x8002CD94) | kernelnorth | ✅ **fixed**: verified by you 2026-10-11 19:1x (kernelbad, no freeze). 16×21 grid with an empty region ring |
| C26 | 🔴 **Freeze after Play Again following drowning in the lake** at the north beach start (`beach_n`): car drowns → Game Over → Play Again → code runs into data | beach_n | ✅ **closed: not a real freeze** (Water, 20:40). Drown → Play Again 7/7, pause → Restart 16/16, Quick Replay/Film Director 4/4 all clean. The lab "hangs" all came after the test drive had pressed Exit and left Chicago (menu / a Miami game); the model-table alarm was memory reused after leaving the level. Follow-up: C27 |
| C27 | **Possible freeze after leaving Chicago** (Exit → menu, or the next game in another city): seen only in automated test drives that wandered out of Chicago; it may also be a test-tool detection error. C8-like | — | **open, check once**: make the test tools menu-aware (stop when the city isn't Chicago, confirm dialogs properly), then one run: Exit from Chicago → menu → start Miami |
| C28 | 🔴 **Shore wall across a street** at the north-west lakeshore (`shorewall`): a grey slab (probably one of the new extended shore walls) blocks the street; the car hits it, gets launched and falls under the map into a pit (1177 deep) beside the street | shorewall | **slab fixed in the probe** (one-sided walls, your verdict good). Shore walls stay **without collision** for now (you had no complaint, 19:54; say if you want them solid). Open, cosmetic: sawtooth wall tops with water gaps along diagonal shores (`quaydiag`). The shore physics (slants/launch/pit) is D2 road data (Height); approved probe state + walls facing the water in build-dev since 20:13 |
| C29 | 🔴 **Blue boxes over inland streets**: huge solid blue boxes at building height above streets + turquoise strips at building bases, inland (area 2, region 232); probably the new far water planes placed over land | blueboxes | 🧪 **probe ready**: RIVER3A only in the areas with walls; permanent pages back to 3; fix in build-dev since 20:13 |
| C30 | Downtown: big black building faces (C6-like) and buildings swapping while an area loads in the far north | — | **backlog** (cosmetic, your rule) |
| C31 | **Facade details flicker** frame to frame (shop windows, trim, window frames on building walls), in many areas. Coplanar decal polygons inside a building model swap depth order (D1 sorts per polygon). Fix idea: the converter pushes decals a few units out along the face normal (d1models.py) | flicker, flicker2 | **backlog** (cosmetic, your rule) |
| C32 | **Purple/cyan shopfronts** on building ground floors (wrong palette in the texture repack), maybe also the purple/white park props | purpleshops | 🧪 in the water probe (Water's one capture faced away, inconclusive); in build-dev since 20:13, check purpleshops |
| C33 | 🔴 **Freeze at an area switch (normal speed)** (9 → 1 inside region 229 while driving west, Chicago's own-entry switch rule, D1 -231083,341528; your hang snapshot 193318). The world renderer loops forever at 0x80030A44–0x80030A4C on garbage model group data (a2 = 0x7FFFFFFF) while the area is still loading (loading flag stuck, 16 sectors left). Same family as the patched trap at 0x80030B00, but a second loop the guard doesn't cover. Not C25 (kernel intact) | areafreeze | 🧪 **in build-dev since 20:13, awaiting your test**: plugin function-entry hook on the area load (Chicago only), 68–126 spool entries redirected per switch, no freeze in Height's drives (10 switches). **Your probe:** `areafreeze`, drive west through the 9→1 switch | **Fixed, in build-dev 20:13** (Height): function-entry hook on 0x80033B10 (game.toml `mod_function_entry_funcs`, Chicago only) redirects the spool entries before the texture pages are queued; build-test + build-dev copy: 10 switches crossed, no freeze. Awaiting user test (areafreeze, drive west).

---

## ⏸ Paused 2026-10-11 ~20:30 (your usage limit). Resume here

- **Your dev client = build-dev 20:13**: C33 area-switch freeze fix (plugin hook, Chicago only), ramp round 2, approved water state. **Your test of it was in progress** (areafreeze west, rampsink, deckfall, bridges, purpleshops).
- **Water:** C19 far water, your priority: cause found (tile 683 inherited LA's instance number → skewed far squares); fix next. Then the sand (water showing through, drawn too far).
- **Height:** waiting for your verdict on 20:13; C20 trench-end observation logged.
- **Live test:** region sweep 40/111 regions clean; the next batch on your go.
- **Backlog by your rule:** C2, C7, C13, C18, C23, C24, C30, C31 (+C32 if still purple).
- **Chats:** this one = recomps-27 [fab41b] (planning), Water, Height, Live-test environment. Their pause lines are in WORKLOG.md.

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
