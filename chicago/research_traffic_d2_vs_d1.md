# Traffic lanes and AI: Driver 2 Chicago vs our Driver 1 import (lev-analyst, 2026-10-13, offline)

Scripts: `chicago/devtools/lane_compare2.py D2LEV CONVLEV D1LEV...` (D2 straights vs D1 roads, per-city engine lane
split), `chicago/devtools/lane_compare.py LEV...` (road-map cell rot per road). Inputs: work/d2_CHICAGO.LEV,
work/var_roads_b8_day.lev, work/d1_*.lev, EXP's Miami RAM dump devtest/exp_work/traffic/rows_miami.json, SLUS_008.42 disassembly.

## 1. How each game encodes lanes

**Driver 2** (dr2roads.h, civ_ai.c GetNodePos): `NumLanes & 15` = lane UNITS across, each 1024 D2 units wide
(= 1352 D1 units = 0.9 D1 cell) and split into 2 sub-lanes of 512. Per unit k: `LaneDirs` bit k = direction,
`AILanes` bit k = civ cars may use it. `NumLanes` bits 4-5 = speed id (speedLimits 56/97/138), bit 6/7 = outermost
sub-lane left/right is parking. Lane 0 is at one edge (sideShift = NumLanes*512 - lane*512 - 256).

**Driver 1** (verified):
- The AI's per-road per-mode lane counts (RAM rows 0x8009E744, bytes 0..3) are built from ROADS only:
  for lane k < NumLanes, LaneDirs bit k set -> mode base (0 = z-road, 1 = x-road), clear -> base + 2.
  Matches the Miami RAM dump for **365/365 roads**. The road-map cell rot does NOT feed these counts
  (cells match only 196/365; Miami one-way roads keep two-way cell rot).
- Lane position (0x80014FC4): `corner(mode) * 1500 ± lane * 1500` - one lane = one 1500 cell, mode 0/1 lanes counted
  from one ROADBOUNDS corner, mode 2/3 from the opposite corner. Lanes beyond the counts leave cells unused (a median).
- All 4 D1 cities: NumLanes == ROADBOUNDS cells across (1, 2 or 3; never more), max 2 lanes per direction.
  Lane splits (base, opposite): Miami (2,1) 88, (1,1) 87, (1,2) 56, one-way (0,2)/(2,0) 108; SF (1,1) 197, (1,2) 88;
  NY (1,1) 222, (1,2) 174. **Ours: (1,1) for all 375 roads.** ROADS pad +0xB is 0 in shipped data (0x80|side = no entry, picker).
- **Junction pad byte (+3) = box size: high nibble = columns (x cells), low nibble = rows (z cells)** - Miami 234/234,
  NY 258/258, SF 223/223. d1roads writes 0x22 always: right for today's 2x2 boxes, WRONG for any wider box
  (b1-b5 had 3x3/4x4 boxes with 0x22 -> likely cause of the "lead car stops 930 before the box" deadlock that led to b6).
- Entry flags: 2 = exit banned (picker skips it; Miami: exactly the wrong-way slots of one-way roads), 4 = signalled entry, 1 = frequent on NY/SF unsignalled junctions
  (NY 341 entries; meaning unverified: probably stop/yield). lightsTimer/lightsNS/WE = 0 everywhere (unused).

## 2. Lane mapping D2 straight -> our D1 road

| D2 AI lanes per direction | straights | share of straight length | our D1 |
|---|---|---|---|
| (1,1) two-way | 328 | 48% | (1,1) ok |
| (2,2) avenues (`>>.<<` 144, `>><<` 72) | 216 | 38% | (1,1): **half the lanes lost** |
| (3,2) / (3,3) / (2,1) | 42 / 14 / 43 | 1% each | (1,1) |
| (1,0) / (2,0) one-way | 94 / 11 | 4% / 1% | two-way: **direction wrong** |
| (0,0) no AI lanes | 31 | 7% | gets 2 AI lanes |
- D2 width in D1 cells (length share): 2 cells 51%, 4 cells 12%, 5 cells 32% (avenues: 2+2 lanes + a non-AI median unit).
- Parking: 65 straights left edge, 35 right, 3 both (all on `><` streets: the outer half of lane unit 0 is parking).
- Turn pockets: short straights with an extra lane before junctions (`>><` 20, `><<` 19, ~1000 units each).
  d1roads takes the MAX lanes of a merged group (`best = max(mem, key=lanes)`), so a pocket can set a whole road's width.
- Coverage: straight midpoints on a D1 road 73% of D2 straight length, 27% on no road (cap 420, short pieces, water).
- Lane length on covered straights: D2 AI 28.3 M vs D1 22.4 M units-lanes, and none of it multi-lane.

**Recipe for d1roads.py** (per merged road, from the length-weighted majority straight of the group, not the max):
1. a, b = AI lane units travelling each way (AILanes & LaneDirs over k < NumLanes&15); cap each at 2 first (D1-proven), 3 later.
   (0,0) roads -> use (1,1) or drop; one-way (n,0) -> NumLanes n, LaneDirs all 0 or all 1 (as Miami's 108 one-way roads).
2. NumLanes = a + b; LaneDirs = b set bits (the side d1roads already uses for "high side = bit set", rot base+2),
   so the engine counts give mode base = b lanes, base+2 = a lanes. Keep today's side convention (it drives right-hand in game).
3. Cells across: variant A (D1-proven): exactly a + b cells, centred on the D2 road; variant B: all cells inside the D2
   width (median/parking cells stay inside the bounds, lanes start from each corner so they stay empty). B is untested
   (NumLanes != width never occurs in D1 data) - put it behind a switch.
4. Cell rot per cell = base + 2 on the b-side cells, base on the a-side (and on a median: nearest side).
5. Junction box = the crossing roads' widths (not capped at 2), pad = (cols << 4) | rows, roads start next to the box.
6. One-way roads: set entry flag |2 on the junction entry whose slot has lane count 0 (Miami: all 87 flag-2 entries
   sit on one-way roads at the slot with count[slot] = 0, no two-way road has one) - else cars pick the wrong-way exit
   and 0x80014FC4 finds no lane (the old Chicago stall).
7. Turn pockets: ignore at first (majority config); later optional: split the road at the pocket (costs roads; 45 left under 420).

## 3. AI logic: D2 vs D1

| feature | Driver 2 (civ_ai.c) | Driver 1 (exe) | D1 route |
|---|---|---|---|
| multi-lane roads | up to 3/dir in Chicago, per-lane AI bit | per-mode counts from ROADS, 1 cell/lane, ≤ 2/dir in shipped cities | DATA (recipe) |
| turning lanes | GetNextRoadInfo: leftmost lane no right turn, rightmost no left, middle straight only | picker prefill 0x80016F0C..0x80017100: 1 lane = all turns; lane 0 = straight + slot (mode+1); last lane = straight + slot (mode+3); middle = straight; straight only if target road has count > lane; else fallback 0x80017490 (any legal exit) | DATA: already in the engine, inactive because every road has 1 lane/dir |
| one-way streets | LaneDirs | LaneDirs all-same + entry flag 2 at the wrong-way slot (Miami 87/87) | DATA |
| banned turns | exits validated per lane dir | entry flag 2 | DATA |
| traffic lights | global 2-phase NS/EW (512-frame cycle, green 150, amber 50), turning cars yield on green | global 4-phase, one approach slot per phase (0x800970D8 & 3 == exit slot, 0x80021C10); type 1 junctions | DATA: equivalent; per-junction timing would be ENGINE (not needed) |
| unsignalled priority | flags bit 1 = major road, YIELD_TURN / YIELD_STRAIGHT | entry flag 1 (NY/SF) probably stop/yield - unverified | DATA after one EXP check |
| speed per road | speed id per straight (56/97/138) | no per-road speed field known (ROADS flags +0xA bit 0 only changes a spawn offset in 0x80014FC4) | ENGINE, small-medium: plugin table road -> max speed at the AI cruise-speed write (to locate) |
| lane changes on straights | CheckChangeLanes: random/overtake/park, indicator, collision check | not seen: lane set at spawn / junction (0x80014FC4 lane 0xFF = random) - unverified | ENGINE, large (new state + lateral offset) |
| parked cars | parking sub-lanes, CreateStationaryCivCar, maxParkedCars | no parking data in ROADS | ENGINE large; DATA alternative: static car models in cells (not damageable) |
| curves | 151 curves with lanes | none (corner junctions) | DATA (as now) |
| network size | 779 straights | ROADS cap 420 (421 resets) | DATA: pick roads by AI-lane length; ENGINE to lift cap (unknown cost) |

## 4. Proposal (priority order)

1. **DATA - lanes per direction (recipe 1-4 + 6, variant A, cap 2/dir) + one-way roads with flag-2 bans.** Effect: avenues (38% of straight
   length) get 2+2 lanes, D1's own lane-turn rules switch on (outer lanes turn, inner lanes go straight), one-way
   streets drive one way. Effort: ~40 lines in d1roads.py, one test run on a Loop avenue.
2. **DATA - junction pad byte = box size and boxes as wide as the roads** (required by 1; 2+2 roads need 4x4 boxes,
   Miami max seen 3x3). Effect: fixes the box/pad mismatch; retest the 930-stop with wide boxes. Effort: 2 lines + box rule.
3. **DATA - lane config by length-weighted majority, not max** (stops turn pockets widening roads). Effort: 1 line.
4. **DATA - road selection by AI lane length** (avenues first), (0,0) roads last. Effect: more of the 27% uncovered
   length that matters gets traffic. Effort: small.
5. **DATA - lights only where D2 has them (CHI_JUNC_LIGHTS=d2: 239/252 anyway), entry flag 2 for D2-banned exits,
   entry flag 1 on the minor-road entries of D2 priority junctions (flags bit 1) after EXP confirms flag 1 = yield.**
6. **Variant B / 3 lanes per direction** (D2 3+2, 3+3 roads; median cells) once 1-2 are stable. Small data change, risk:
   untested in D1 (no city has NumLanes != width or 3/dir).
7. ENGINE, only if the user wants more: per-road speed (medium), lane changes (large), parked cars (large).
   Lights need no engine change (both games use one global cycle).

Open checks for the first test run: which side lane 0 sits on (lane 0 turns to slot mode+1 - must be the kerb lane for
right-hand traffic), and cars in lane 1 at T-junctions without a straight exit (the fallback should pick any legal exit).


## Highways and D2 multi-lane AI (QA-2, 13.10.; notes devtest/qa2_research/traffic_highways.txt)
- The big roads = speed id 2 (fastest, speedLimit 138): 102 straights, 1,638k units, ALL with AI lanes, mostly 2 per direction:
  NL5 out3/in2 AI 2+2 (44 straights, 1,285k units); NL6 AI 2+3 (17); NL6 AI 3+2 (14); NL7 AI 3+3 (9); NL5 AI 2+2 (8).
  The highways are NOT in the (0,0) no-AI group (31 straights, all speed 0/1). Largest: (-25088,-550912), (-86528,-550912), (-216576,685056).
- D2 civ lane logic (civ_ai.c): CheckChangeLanes = random change to an adjacent AI lane (same direction, not parking), gated by a
  collision box check; changeLaneIndicateCount 161. GetLeftBoundLane/GetRightBoundLane: the outermost AI lanes; GetNextRoadInfo
  gives left-lane cars the left exits and right-lane cars the right exits (turn lanes). No overtaking logic.
- For D1: the turn-lane rule exists in D1 already (data only); lane changes on straights = R17 (b), decided "later".
