# C94 design: Mods toggle "Extra draw distance" (1.5x, every city) (Polish, 25.10., analysis only)

User (25.10.): a Mods toggle that draws buildings, cars etc. 1.5x further in every city (Driver 1 and Driver 2); off =
original. Implementation: Infrastructure (exe / plugin / runtime + converter for the D2 cities). Static facts from
ghq.py (D1 v1.1 exe), NOTES (C73 / C40 analyses) and pvs.py. No time estimates (user rule).

## 1. What limits the draw distance today

| limit | where | value today | 1.5x |
|---|---|---|---|
| Cell window of the map draw | FUN_8002C8FC (cell loop, draw of every object cell); window constants 0x12 / 0x13 at 0x8002CB78 / 0x8002CC48 (19 x 19, radius 9), cell pointer window (30^2 x 8 B) | radius <= 9 cells x 3000 = 27000 units | radius 13-14, window 27 x 27 (or 29 x 29) |
| Per-cell view radius (PVS) | Per-cell RLE visibility bit stream over the 19 x 19 window. D2 cities: chosen by the converter (pvs.radius_grid, MAX_RADIUS 9, MIN 5) so the polygons in range fit the primitive budget (0x1E000 x 0.72). Chicago today: radius 9 on 277613 cells, 5-8 on 24787 (downtown). D1 cities: their own Reflections PVS, same 19 x 19 format. | 5..9 | D2: rebuild with a 27 x 27 window. D1: no data beyond 9, so treat outer cells as visible |
| Object cull | cull_objects 0x8002C5F0: frustum side planes only (FUN_8002DADC; FOV 0x800971B4 = 500 - x); NO far plane | none | none |
| Ground tiles | LOD bands rewritten every frame in FUN_8002360C: mid band < 7000 (0x80023A40 `addiu v0, zero, 0x1B58` -> 0x80097148), far band < 9000 (0x80023A4C `0x2328` -> 0x80097144); near < 2000 (0x800287A4); subdivision 6000 / 9000 (0x80030B08). Beyond 9000 no ground tile is drawn (C19: far water) | 9000 | 13500 / 10500, subdivision 9000 / 13500 |
| Car model LOD | full model up to camera depth *0x80096A48 (10000, +4 per zoom; written by the camera setup FUN_8003CFE8 / D4D0 / D810, read 0x8003AB0C), low model beyond (C40 lever 3 already rescales this word) | 10000 | 15000 |
| Cars that exist | traffic / cops exist only inside the AI spawn / removal range (unchanged on purpose: gameplay) | as is | as is (see 3) |
| Primitive buffers | 2 x 0x1E000 B at 0xD8600 / 0xF6600 (fixed D1 RAM, followed by the road map tables); OTs 0xD0200 / 0xD4400 | ~5500 polygons per frame | area 2.25x -> 2.25x polygons: buffers + OT in host mod memory |
| OT depth range | OT 0xD0200..0xD4400 = 4224 entries; z -> OT index shift to check | far objects may clamp into the last OT slot (sorting) | widen the shift or clamp far objects behind the sky |
| Region / area streaming | 2 x 2 region window (regions 90000 units): coverage >= 45000 units in every direction | enough for 40500 | no change (objects are loaded) |
| Area model / texture sets | an area's models + textures = what its regions see within the view radius (converter for D2; original data for D1) | radius 9 | D2: rebuild sets with radius x 1.5 (more models + textures per area). D1: far objects whose model / texture is not in the loaded area must be skipped (C33-type residency guard), else garbage / crash |
| Depth cue / fog | none in Driver 1 (the GTE far-colour registers hold the camera position, C73) | sky dome behind everything | unchanged |

## 2. What the setting scales together (so nothing pops or shows holes)

1. **Exe (gated by one word XDD, plugin-written; 0 = Driver 1 code path):**
   - cell window 19 -> 27 and its pointer window (FUN_8002C8FC)
   - tile bands 7000 / 9000 -> 10500 / 13500 (the two immediates in FUN_8002360C read XDD)
   - subdivision 6000 / 9000 -> 9000 / 13500 (0x80030B08)
   - car LOD depth x 1.5 (the 0x80096A48 reads, like C40 lever 3)
2. **Visibility:**
   - D2 cities: the converter (pvs.py WINDOW / MAX_RADIUS 13, budget from the bigger buffers) writes a second PVS and
     second area sets for "extra" (a switch, e.g. CHI_XDD=1), shipped as extra sidecars / an extra level pair.
   - D1 cities: outside their 19 x 19 PVS the cell loop treats cells as visible within the new radius (no data there).
     That costs polygons but shows no holes.
3. **Residency guard (all cities):** before drawing an object, skip it when its model (or the model's texture page) is not
   resident in the loaded area. Chicago already has the C30 / C33 machinery; D1 cities need the same check. Missing far
   objects then show as "not yet drawn", never as garbage.
4. **Buffers (host only):** primitive buffers and OTs move to host mod memory sized for ~2.25x polygons. The C22 /
   "prim buffer overflow" hang family is the failure mode if they don't.
5. **Not scaled:** AI spawn / removal radius, cop director, area streaming window, physics, audio. The gameplay stays
   identical; only drawing changes.

## 3. Costs and side effects

- **FPS:** ~2.25x more geometry at the far range. Chicago already needs 2.95-3.41 vblanks per frame downtown (C92
  measurement), so with "Extra draw distance" on, "Uncap GPU usage" (C92, guest CPU overclock ~3-4x for these scenes) is
  required for 30 FPS. Recommend: the Mods UI notes "needs Uncap GPU usage", or the feature enables a higher overclock.
- **RAM:** primitive buffers + OTs (+ ~300-400 KB host memory). D2 cities: bigger area model blocks (model spool buffer
  already 176 KB in Chicago, 220 KB in Havana; 256 KB host carry). The converter must keep each area under the carry or
  raise it.
- **VRAM (D2 cities):** wider area texture sets = more halving (Chicago 56 % today), or more pages (C77 / 320 route). The
  extra variant should reuse the same packing but its own sets; measure with the converter before deciding.
- **Visual:**
  - Chicago's d2raw sky has a painted skyline: real far buildings now overlap it. Check river / lake views.
  - Far objects pop in at the new edge instead of the old one (same behaviour, further away).
  - No fog to hide the edge (Driver 1 has none).
- **Cars:** they only exist inside the AI range, so more far cars only appear where they already existed. Full car models
  stay sharper further away (LOD x 1.5).
- **Replays / saves:** unaffected (drawing only).

## 4. PS1 feasibility (Milestone 8)

- Host-only. 2.25x primitive buffers (~540 KB) + OTs exceed the 2 MB PS1 RAM budget next to the area model spool, and
  the R3000A cannot draw 2.25x polygons at playable rates.
- Add to the NOTES host-only list.
- The toggle off is the PS1 reference.

## 5. Checks (runner, levels started at the spot, not posed)

- Toggle off: byte-identical frames to today (gpu_frame_capture diff at 3 spots per city).
- Toggle on, Chicago (l_down_e, riverbridge, quay_wall, fps_drop_2) and Miami / LA / NY / Frisco:
  - no garbage polygons (vramcheck)
  - no missing near objects
  - frame captures show the far ring drawn
  - primitive buffer high-water mark < the new size
  - no "-hang" watchdog dump over a 2-minute drive per city
- With and without "Uncap GPU usage": vblanks per frame (c92_measure method).
