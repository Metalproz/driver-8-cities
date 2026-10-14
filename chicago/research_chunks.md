# C45 part b: reachable network, area/region layout and per-switch loads (Polish, 2026-10-13)

Offline analysis; the stall map from QA-3 (research_stalls.md) was not there yet when this was written.

## 1. Reachability (where a car can get to)
- Method (scratchpad reach.py, D2 coordinates): drivable = Driver 2 road surface (d2surface, 1024 grid) that is
  not water/sea; minus every collision box (D2 COLLISION_PACKET: centre = object + R(-yang)(xpos, zpos), angle
  (obj.yang + box.yang)*64, half sizes xsize/2, zsize/2) that reaches car height over the ground there, rasterised
  at 256 units; 4-connected flood fill from the Take a Ride start (9216, 106496) with at most 400 units of height
  step between neighbours. Approximation: one ground level per 1024 cell (decks over streets count as the lower
  level), walls only from collision boxes.
- Result: 2.27 M reachable 256-unit cells; the reachable set is the whole street network of the overhead map
  (parks, Navy Pier, Meigs Field, the trench freeway included). Images:
  - `driver_personal/findings/chicago_reach_topdown.png` (green = reachable, grey = drivable but sealed off,
    dark blue = collision boxes at car height; north up)
  - `driver_personal/findings/chicago_reach_iso.png` (isometric, colour = height: the brown line is the sunken
    trench freeway)

## 2. Current layout vs Driver 2's own
| | our Chicago (b12) | Driver 2 Chicago | LA (D1) | Miami (D1) |
|---|---|---|---|---|
| texture/model areas | 21 | 19 (11 used by streets) | 6 | 7 |
| texture pages in the level | 21 (per-area page contents) | 70 | 74 | 82 |
| load per area switch (2 KB sectors, textures + models) | 35..201, typically 150..190 (300..400 KB) | 67..229, typically 90..110 (~200 KB) | | |
| region records (spooled) | 336 regions, 12.4 MB (37 KB avg) | 134 regions, 8.2 MB (61 KB avg) | 59 | 60 |

- Area boundaries crossed by the street network (256-unit edges where the "own" area changes between two
  reachable neighbours): **5255 for our layout** (21 areas, checkerboard of 2 switch entries per region). Busiest:
  areas 6/18 (533 edges, 344/314 KB), 12/15 (360, 402/360 KB), 8/12 (332), 3/12 (313), 9/20, 0/2, 3/16, 1/9 ...
- Driver 2 assigns each region a super_region (its area) only in the area cores and leaves corridors of regions
  without one between them; those regions list connected_areas with a load flag, so D2 starts loading the next
  area early and asynchronously while the car is in the corridor. Downtown is ONE D2 area (area 7, 521 k road cells),
  the other street areas are the north side, the west side, Grant Park/Museum campus and the south. Image:
  `driver_personal/findings/chicago_areas_d1_vs_d2.png` (left: our own areas per region; right: D2's super_region,
  black gaps = transition corridors).
- Why ours stalls: every switch reloads the whole area (all its page contents differ per area, CHI_PER_AREA=1,
  plus its models: 300..400 KB, about 1 s at 2x CD speed), there are 3.6 x more road crossings of area boundaries
  than D2 has, and the exe patch "area switch waits while loading" turns each load into a pause.

## 3. Proposal (for Infrastructure; data parts can be done by Polish behind switches)
1. **Engine (largest effect):** load the next area asynchronously like D1/D2 do, not with the game waiting: start
   the load when the car enters the 5-cell hysteresis band (the region's 2nd entry), keep drawing with the old
   area until it has arrived, then switch. If the wait patch exists because of the C33 freeze, keep it only for
   the case "car already deep inside the new area and the data is not there".
2. **Data: fewer boundaries on the streets.** Re-partition regions into areas with the texture budget as the
   constraint and the number of street-network crossing edges (this map) as the cost, following Driver 2's
   corridors (river, park, freeway trench, rail yards) instead of the checkerboard. Target: under 2000 crossing
   edges, no boundary along a main avenue.
3. **Data: smaller loads per switch.** Neighbouring areas keep textures they share on the same page index with
   the same content so Driver 1 does not reload them (Driver 1 keeps pages that stay listed); only the differing
   pages stream. Costs some texture budget (C7): measure downscaling vs bytes per switch.
4. Check that build-dev has the CD speed / fast-loading packages enabled (psx.enhancement.cd-speed /
   fast-loading are installed in build-test); they shorten every load.

## 4. Data-side results (Polish, 2026-10-13 22:xx)
- Switch CHI_POLISH_AREAS (polish_areas.py, hooks in convert.build_world): `1` = oversize areas are split by the
  straight cut (axis + any position, both halves >= 25 % of the regions) that crosses the fewest street edges;
  `2` = additionally the start layout is built bottom-up (regions merge along the strongest street connections
  while the texture union stays <= CHI_POLISH_AREAS_SHARE x CHI_AREA_TEX, default 1.1), then the usual limit check
  splits with mode 1's cut. Street edges = the reachability map counted per pair of neighbouring Driver 1 regions
  (layout only; never used for roads or traffic).
- Street-network edges crossing an area boundary (same metric for all; scratchpad areacost.py):

| layout | crossings | areas | load per switch (mean, textures + models) | downscaled textures |
|---|---|---|---|---|
| current (b12) | 5255 | 21 | 338 KB | 604 |
| mode 1 | 4287 | 21 | 346 KB | 609 |
| mode 2, share 0.6 / 0.7 / 0.8 / 0.9 | 4932 / 3647 / 2988 / 2827 | 29 / 24 / 21 / 21 | ~350 KB | 673 / 724 / 786 / 801 |
| **mode 2, share 1.1 (default)** | **2628** | 21 | 356 KB | 730 |

  A local search (moving boundary regions) gave nothing lasting (the limit check split again); removed. The < 2000
  target is not reachable with Driver 1's texture budget: every region sees up to 9 cells (27 000 units) around it,
  so an area's texture set is large and Chicago needs ~21 areas whatever the shape.
- **Per-switch size cannot shrink on the data side:** Driver 1's area loader (0x80033B10) queues EVERY page listed
  for the new area (17 sectors each, page + CLUTs) and only reuses slots of pages that stay listed; it never skips
  a load. LA does the same (7 pages = 119 sectors per switch), it just has 6 areas. So "keep shared pages identical"
  needs an engine change: in 0x80033B10, skip the read when the page's resident flag (table 0x800BE278) is set
  and the page keeps its slot; the converter then has to give pages with different content different indices
  (CHI_PER_AREA=0 style packing or one index per content), which costs texture budget.
- Candidate level: work/var_polish_c45_areas_day.lev (mode 2 + light subdivision + PVS): half the boundary
  crossings of b12, +126 downscaled textures.

## 5. Corridors (Polish, 14.10.): load earlier, no engine change
- Switch CHI_POLISH_CORRIDOR=1 (convert.switch_entries + polish_areas.corridor): (a) a border region whose
  neighbour areas lie in several directions gets its switch entry toward the neighbour the streets cross to most
  (default: the first found); (b) where >= CHI_POLISH_CORRIDOR_MIN (20) street edges cross a boundary, the switch
  entry moves one region back: the load starts at cell 17 of the region before the border region, i.e. 43 cells
  before the boundary instead of 13, and the border region becomes a corridor. Both areas' texture/model sets
  include everything visible from the corridor (loadable_areas simulates the rule), so nothing in it depends on
  the other area's pages (per-area packing places a texture needed by both areas identically in both).
- Street crossings of area boundaries per direction, by switch lead (scratchpad corrcheck.py; same code state):

| level | crossings | lead 43 cells (corridor) | lead 13 cells (border entry) | no lead (switch only inside the new area) | downscaled |
|---|---|---|---|---|---|
| baseline (current defaults) | 10510 | 0 | 6340 (60 %) | 4170 (40 %) | 672 |
| CORRIDOR=1 | 13552 (25 areas) | 1134 (8 %) | 9210 (68 %) | 3208 (24 %) | 651 |
| **AREAS=2 + CORRIDOR=1** | **5836** (22 areas) | 451 (8 %) | 3741 (64 %) | **1644 (28 %)** | **558** |

- Candidate: work/var_polish_c45_corr3_day.lev (AREAS=2 + CORRIDOR=1, current defaults otherwise): 44 % fewer
  boundary crossings, 61 % fewer crossings without any lead, no texture cost (fewer downscaled textures than the
  baseline). Loads and renders (l_down_e run). Remaining no-lead crossings: corners (two neighbour areas, only one
  entry slot) and border regions back to back.
