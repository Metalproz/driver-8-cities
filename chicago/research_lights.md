# Traffic lights: D1 vs D2 vs Chicago (QA-3, 2026-10-13)

Scope: offline parsing of LEVs and D2 source. No game run (RAM phase search NOT done).
Scripts: scratchpad only.

## 1. Driver 1 (d1_MIAMI.lev, also NY/LA/FRISCO)

- JUNCTIONS lump (9): int count, then 44-byte records:
  `id s16, type s8, pad, lightsTimer s16, lightsNS s8, lightsWE s8, entries[4] {fromJunc s16, road s16, flags s16, extraFlags s16}, x s16, z s16`
  (struct in OpenDriver2Tools d2_types.h, DRIVER1_JUNCTION).
- Miami: 234 junctions, type 1 = 148, type 0 = 86. Entry flags: type 1 uses flags 4 (446 entries), 6 (85), 1 (21);
  type 0 uses 0 / 1 / 2. Bit meanings NOT confirmed.
- lightsTimer, lightsNS, lightsWE are 0 in every junction of every D1 level checked. They are runtime state,
  so the file does not hold the phase; the exe sets it when the level loads.
- NY: 256 type 0 + 2 type 1. LA: 35 type 1 + 1 of each of several other type values (types 255, 28, 31, ...).
  So type 1 is NOT a clean "signal" marker across cities; type-to-behaviour mapping still unknown.
- Models: MODELNAMES lump (12) holds the names (index = model slot; empty names are placeholders).
  Miami: slot 88 = TLIGHT01, 89 = TLIGHT02, 402..418 = TLIGHT03..TLIGHT18 (SIGN*_TASTIC around them).
  NY: 498/499 SLIGHT00/01, 500 TLIGHT01, 517 SLIGHT02, 614 TLIGHT00.
- Cell objects (CELL_OBJECT, d1cells.py): Miami has 363 objects of TLIGHT slots (320 of them slot 88).
  The objects are plain placed models, so the light poles are static cell objects.
- Animation of the coloured lamps: not verified (would need the TLIGHT model's textures or a Miami spot run).

## 2. Driver 2 (refs/REDRIVER2/src_rebuild/Game/C, d2_CHICAGO.LEV)

- Junctions: JUNCTIONS2_NEW (43), 12-byte records `ExitIdx[4] s16, flags u32` (DRIVER2_JUNCTION).
  Chicago: 252 junctions. flags&1 (traffic light) on 239; 13 have only flags&2 (yield/stop).
- civ_ai.c ~555-590: junction flag 1 -> CIV_AI_CTRL_WAIT_TRAFFIC_LIGHT, trafficLightPhaseId = exitFrom & 1,
  the car stops unless junctionLightsPhase[phase] == 3 (green). Turning cars wait at the node, straight cars yield.
- civ_ai.c:1650: junctionLightsPhase[0..1] = TrafficLightCycle(0/1) every frame.
- civ_ai.c:1655 TrafficLightCycle(exit): NO RAM state. Phase = (CameraCnt - frameStart) & 511 (512-frame cycle).
  - exits 0/2: red 0..255, green 256..405 (3), yellow 406..455 (2), red 456..511.
  - exits 1/3: green 0..149 (3), yellow 150..199 (2), red 200..511.
  So D2 lights are a pure time function, and the phase pair is 1/3 vs 0/2 (exitFrom & 1).
- D2 Chicago cell objects: TLIGHT01 759, TLIGHT02 52 (traffic lights); SLIGHT01 860 (street lights).
- Whether D2 TLIGHT models animate in draw.c: not checked.

## 3. Our converted Chicago (work/chicago_d1.lev, current)

- ROADS, JUNCTIONS and JUNCBOUNDS are EMPTY (4-byte lumps, count 0). convert.py:2206-2208 writes them empty.
  So there is no junction data and no light phase data in the level. Traffic AI cannot stop at lights
  because there are no roads (Stage B / P6 not done).
- Models: the converter keeps D2 model names in MODELNAMES (TLIGHT01 @1179, TLIGHT02 @1182, SLIGHT01 @1174).
  Cell objects: 759 use 1179 (D2 TLIGHT01), 52 use 1182, 860 use 1174, and 735 use slot 88 (D1 TLIGHT01 slot,
  name blank in the converted list) and 20 use slot 89. Likely the converter maps some TLIGHT01 onto the D1 model
  table slot 88 (the D1 model table holds D1 TLIGHT01), but this was not confirmed in convert.py (no TLIGHT
  mapping found there; check models.py / model_table_patches.toml).
- Result: the lights are present as static models (poles). They are not wired to any phase.
  Missing: junction records with the light flag, lightsTimer/NS/WE state, and any road the AI can use.

## Open / not done

- RAM phase search (D1 lightsTimer / lightsNS / lightsWE in the Miami junction array): not done. The D1 exe
  has no symbol map in the project. Method: on a Miami devtest copy (port 4440), snapshot memory a few
  times and look for the 44-byte junction pattern (id, type 1 ...), then watch the lightsTimer word and
  the NS/WE bytes for a cycle.
- D1 type-to-behaviour mapping (type 0 vs 1, entry flags 4/6/1/2): not confirmed.
- Whether D1 TLIGHT models change colour (texture or model swap): not checked.

## Proposal

1. Lights depend on roads: do Stage B / P6 first (ROADS/JUNCTIONS from D2). Without roads a light has no
   effect on AI.
2. Converter: map D2 junctions with flags&1 to D1 type-1 junctions (lightsNS/WE + lightsTimer start values).
   Fill lightsTimer / NS / WE from the D2 phase logic (512-frame cycle), or keep a runtime timer if the
   exe does not drive it on its own.
3. Before converter work: one RAM run on Miami to confirm that the exe advances lightsTimer and flips
   lightsNS/WE every few seconds (this decides whether the converter must set the phase or only the start).
4. Check that the converted TLIGHT objects resolve to the D1 TLIGHT model slots (88/89/402..418), not to
   D2 models.

## Runtime check (QA-3, 2026-10-13, Miami Day/Night, devtest/qa3, port 4440)

Setup: Take a Ride -> city row 0 (Miami) -> Day (or Down+Cross for Night). Scripts in scratchpad only.

- (a) JUNCTIONS in RAM: found, base 0x80154B94, 44-byte stride, one match for the first 3 records of
  d1_MIAMI.lev (inmem lump 9, count 234). Only difference from the file: byte 3 (the file has 0x22 there, RAM has
  0x00 or 0x01; this is the 'pad' byte of section 1, meaning unknown). Search masks bytes 3-7.
  lightsTimer / lightsNS / lightsWE (bytes 4-7) of J0..J2: 0,0,0 for all 16 samples over 30 s (every 2 s). No change.
  wtrace_range armed on 0x80154B94..+132 for 5 s: 0 writes. The trace total was not printed, so the ring itself
  was not checked against a known writer. Result: the D1 phase fields are NOT driven in Miami at rest. Either the
  phase is not used by the exe, or it changes only with traffic (not tested).
- (b) Not tested. Start position (3 shots, 5 s apart) shows no junction or light model. A drive of 24 s forward
  ended in a hedge/palm strip (damage up), no light in view. Needs a Miami junction spot to test.
- (c) Miami NIGHT (1 shot after load): street lamp heads are lit (white and orange points on the lamp arms and
  in the distance), but there is no obvious halo or glow sprite. Weak yes.

### (b) follow-up (2026-10-13, not completed)
- Junction x/z (s16) are road-grid cells, not world units. ROADMAP lump (7) = 600 x 840 cells, cell = 1500 units
  (regions_d1.cpp:389-390: cell = (unitXMid + vx)/1500, z mirrored). Partial fit: world z = 630000 - 1500*z_j
  puts 34 of 120 TLIGHT objects within 3000 units of a junction; x offset NOT resolved (search too slow, aborted).
- Car placement by junction was not done, so no light was checked with the car near one. Status: open.

### (b) run (2026-10-13, simpler route)
- Light: TLIGHT model 88 at world (134050, 0, -33650). Car poked to (134000, 169, -30650) = 3000 units south of
  the light, standing still, 4 shots 4 s apart (devtest/qa3/shots/tl_sheet.png).
- Result: the light is NOT in view in any of the 4 shots (only the road, buildings and a round blue sign).
  Facing is unknown (no heading address used), so the car may face away. Colour change: NOT observed.
  AI stop at the light: not checked.
- Poke note: poking x=142924 (a light 9000 units away) left x at 133964 (no effect); z poke worked. Cause not known.

## Chicago light glows (QA-3, 2026-10-13)

Setup: build-test slot package (CHI_SLOT=1, CHI_NIGHT=var_roads_b6_night.lev, city "la"), devtest/qa3, port 4440.
Take a Ride row 4 = Chicago (city 3). Night = flag 1, Day = flag 0. Player placed at the light/lamp
position minus 2000 or 700 units on x, heading 0/1024/2048/3072 (x 4 headings), 6 shots 1 s apart, NS/WE logged.
Objects: TLIGHT01 (model 1179) at (166594, 0, 55588); SLIGHT01 (model 1174) at (171241, -22, 52631).
Screenshots: devtest/qa3/shots_night and shots_day (512x240).

- Traffic light, Night, 700 units: no coloured glow at the signal head. The signal box is dark; the only red
  sprites in frame sit on the player car's tail lights.
- Traffic light, Day, 700 units: the signal head is visible (green lit), with no glow sprites beside it.
- Street lamp, Night and Day, 700 units: the pole is visible; no glow sprite in frame.
- NS/WE change in the logs (about every 1 s, so the cycle runs faster than 300 frames at 60 fps); the
  glow state was not visible in these frames, so the NS/WE dependence is not confirmed.
- Limits: at 2000 units the objects were too small to judge in 512x240 frames. The heading convention
  is unverified (the car ended up in odd poses at some headings).
