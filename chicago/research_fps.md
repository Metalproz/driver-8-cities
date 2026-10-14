# FPS measurement method and C40 baseline (QA-1)

## Method (speed-independent, use this for later builds)
- Game frames = change of word 0x800970D8 (PHASE) over the window. Assumed to advance once per rendered frame (not yet proven against overlay flips).
- VBlanks = change of the libetc VSync counter 0x80095250 (dt.VCOUNT) over the same window.
- FPS = game frames / VBlanks x 59.94. Windows: 20 s standing, 20 s driving (cross held 0.9 s, gap 0).
- Cross-check (not used for the number): DRAWBUF (0x80097530) flips polled over TCP undercount (about 10 to 25 per window), so they are not usable.
- Script: scratchpad fps2_qa1.py (QA-1). Outputs devtest/_qa1/fps/*_v2.json. Build-test b10_day, classic menu, port 4410.

## Baseline (FPS, window averages)
| spot | standing | driving |
|---|---|---|
| Chicago loop start (17444,110302) | 26.6 | 20.7 |
| Chicago overpass_e (129395,44286) freeway | 30.0 | 7.3 |
| Chicago riverbridge (6780,-2567) | 27.0 | 14.9 |
| Chicago downtown L (23662,54070) | 25.0 | 23.4 |
| Chicago downtown L (-37237,52948) | 20.2 | 20.3 |
| Chicago L run (loop start, drive 40 s; extra run, not a separate L spot) | 26.6 | 22.5 |
| Chicago dense avg (loop, 2 L spots, L run) | 24.6 | 21.7 |
| Miami (default start, 2 runs) | 27.5 | 26.8 / 23.8 (avg 25.3) |
| LA original (control) | 21.6 | 19.2 |

Sanity: Chicago dense driving lands at 20 to 23, close to the user's overlay 22 to 23, so the method is in the right range.
Gap: Chicago dense driving 21.7 vs Miami driving 25.3 (about 3.6 FPS below). Miami measured at one spot only; more Miami spots not yet measured.

## overpass_e repeat check (QA-1)
- Two repeats, 20 s driving (cross held): drive FPS 7.6 and 9.8 (first run 7.3). Standing 30.0 both.
- Screenshots at 10 s (devtest/_qa1/fps/overpass_rep_sheet.png): the car is NOT driving normally on the deck. Repeat 1 is on grass beside the road; repeat 2 is in water. Both show an "Are You Sure? Yes No" dialog (not Play Again; not pressed).
- So the overpass_e driving number is not a freeway-deck measurement: the car leaves the deck. Driving FPS there stays unreliable until the car is steered on the deck.
- Miami downtown and bridge spots: not measured; no Miami coordinates in spots.json (only the Miami default start exists).

## C40 profiling and subdivision variants (Polish, 13.10. ~20:1x)
- Tools: phase_hot (set=static, diffed over a 6 s window) = host samples per guest function (proxy for work);
  FPS = 0x800970D8 frames / server vblanks x 59.94 (same as QA-1's VCOUNT method); finished-frame primitive
  buffer parsed after a buffer swap (scratchpad primparse.py).
- Top Chicago-specific cost: **near subdivision** of polygons flagged 0x20/0x40 (routine 0x8003110C, called from the
  per-object renderer's handler at 0x80030F90; per-polygon loop 0x80030C20): 6.6-7.5 % of samples at the two L spots
  vs 2.4 % in LA. D2's Chicago models carry 0x20 on ~9500 wall quads (1350 x 675 D1 units after x1.32), 0x60 on ~720.
- Switch CHI_POLISH_SUBDIV (d1models.py): `none` = clear both flags; `0,1000000` = all flagged polys to the light fixed
  level 0x60 ("light"); `A,B` = clear below edge A, light below B, keep above.
- Standing FPS, mean of 5 headings (spawn + 4 turns), devtest/polish, build-test exe:

| level | 23662,54070 | -37237,52948 |
|---|---|---|
| base (var_polish_base_1_day, no switches) | 24.9 | 21.0 |
| light (var_polish_c40_sdlight_day) | 28.8 | 23.1 |
| 1400,2800 (var_polish_c40_sd1428_day) | 28.9 | 22.6 |
| none (var_polish_c40_sdnone_day) | 29.9 | 23.5 |

- After removing subdivision the rest at -37237,52948 is not Chicago-specific in kind: road-map/surface queries
  0x8001EEB4 / 0x8001F5B0 / 0x8001E844 (also top in LA) and the object loop 0x80030474, 0x8002D278, 0x8002C5F0,
  0x8002CD84, 0x8002CC64 (~14 %: number of objects in the view radius, idea C).

### D2 PVS lever (Polish, 13.10. ~20:4x)
- Switch CHI_POLISH_PVS=d2 (polish_pvs.py, hook in convert.py): Driver 2's own per-cell PVS (roadm spool block:
  int cbr + PVS; big-endian u16 cell offsets, table at +0x802, nibble code high nibble first, 21 x 21 window,
  REDRIVER2 PVSDecode) mapped onto Driver 1's 19 x 19 window (3000-unit cells): an entry stays if the radius disc has
  it and D2 sees one of its D2 cells from one of the camera cell's D2 cells (conservative union; cells without D2 data
  keep the radius). At the L spots D2 sees ~150/441 cells; over all 57004 covered cells 82 % of the entries stay.
  Region PVS blocks grow (max 19 blocks), so the switch also writes LA's per-barrel buffer sizes (41620, 48161,
  45326, 47442 instead of 32768) and drops the least useful masks per region to stay inside them. Level +1.8 MB.
- FPS (standing, 5 headings): pvs alone 25.8 / 21.1 (base 24.9 / 21.0); light + pvs (var_polish_c40_lightpvs_day)
  **29.0 / 24.2** (light alone 28.8 / 23.1). So PVS adds ~1 FPS at -37237,52948, little at 23662,54070.
- Visual check (3 headings at 23662,54070, base vs pvs): no missing buildings.
- Remaining Chicago cost at -37237,52948 without subdivision: the ground tile path (0x80027E08, 0x800268FC/D8/B8/78,
  0x800277D8, 0x800273BC, 0x80026BB8/BE8: together ~15 % of samples; D2's small ground tiles x1.32) and the
  road-map queries (0x8001EEB4/F5B0/E844, also top in LA).

## Coordinate warning (Strategy, 13.10. 20:5x)
`dt.prepare(name, start=...)` / CHI_START take **Driver 2** coordinates (build_package converts with worldscale.to_d1).
User snapshots and the overlay report **Driver 1** coordinates. The user's slow L spots are D1 23662,54070 / -37237,52948
= spots.json `l_down_e` (d2 -101562,106946) / `l_down_w` (d2 -147698,106096). The C40 runs above labelled "L1 23662,54070 /
L2 -37237,52948" were started with those numbers as D2 coordinates, so they ran at other places (L1 = the C43 glitch spot
`c43_ground`, car stuck at the kerb). Their A/B gains are valid for those places; re-measure at l_down_e/l_down_w follows.

## C40 re-measure at the real spots (QA-1)
Real spots = D2 coordinates from spots.json: l_down_e (-101562,106946), l_down_w (-147698,106096). Method v2: standing 20 s, driving 20 s with cross held and left/right steering every 4 s. Build-test, classic menu, port 4410. FPS = 0x800970D8 delta / VSync delta x 59.94.

| level | l_down_e standing / driving | l_down_w standing / driving |
|---|---|---|
| base_1 | 16.3 / 13.9 | 23.7 / 23.7 |
| c40_lightpvs | 19.7 / 26.8 | 27.2 / 27.9 |
| c40_sdnone | 21.5 / 12.4 | 28.5 / 23.5 |

Screenshot sheet at l_down_e after 10 s driving: devtest/_qa1/fps/real_l_down_e_sheet.png (base_1, c40_lightpvs, c40_sdnone).
- base_1 and c40_lightpvs: car on a normal street, no visible warping.
- c40_sdnone: car tilted and sliding, with a dark patch and cut-off road edge near the car and sky visible where the road should be. Possible missing polygons or warping; not confirmed (car may be in a skid). Needs a closer look.
Note: the earlier L1/L2 numbers (23662,54070 / -37237,52948) are a different place (C43 kerb glitch), kept for the A/B only.

## C40 round 2 (Polish, 13.10. ~22:4x): fps_drop_1 (d2 -41570,-339995)
- Standing FPS over 7 headings (spawn + 6 turns): lightpvs2 26.2 at spawn, 17.8..19.9 looking into downtown
  (primitive buffer up to 0x16098 = near the object guard 0x16800); lightpvs (LA-sized PVS buffers) mean 22.9,
  sdlight (no PVS) 21.8 (levels built from different code states; compare with care).
- Profile of the heaviest view (lightpvs2, 20 FPS): no subdivision left; the top is per-object work
  (0x8002C5F0 cull 4.2 %, 0x80030474 3.6 %, 0x8002CD84 3.4 %, 0x800307FC 2.4 %, 0x80031094/74 group transforms,
  0x8002C6B8, 0x8002D0FC/D260, 0x8002CC64), road-map queries (0x8001EEB4 5.5 %, 0x8001F5B0) and car code
  (0x8003DF94, 0x8003B748, 0x8003E244; 4 traffic cars in view).
- Ground tiles are ~2/3 of the objects around a camera (within 20 000: 368 tiles vs 162 other objects at the C43
  spot), and each goes through the object loop.
- Next levers: (a) engine: cull whole cells against the view before touching their objects (Driver 2 walks only
  cells inside the frustum and nearer than farClip); (b) data: the full D2 PVS masks (+~1 FPS here) need the
  LA-sized PVS buffers (C44 memory question) or a denser PVS encoding; (c) data: merge neighbouring identical
  ground tiles into 2 x 2 tile models (about 4x fewer tile objects; touches the tile path, SUBDIVISION data and
  C1; bigger change); (d) smaller radius only in the densest cells (risk of visible pop-in).

## C47 baseline (EXP, port 4450, test copies uncapped/headless: EMU% above 100 is real output of the copy)
FPS1 block at 0x9F082310 (+4 fps, +8 emu%, once a second), 12 samples per run (every 5 s over 60 s).
| exe | city | mode | city check | avg FPS | avg EMU% |
|---|---|---|---|---|---|
| build-wip | Miami | standing | CITY 0 | 88.9 | 320.2 |
| build-wip | Miami | driving | CITY 0 | 96.7 | 343.1 |
| build-wip | Chicago b13 day | standing | CITY 3 | 74.7 | 290.1 |
| build-wip | Chicago b13 day | driving | CITY 3 | 99.1 | 336.8 |
| build-dev | any | any | - | not measured | not measured |
- build-dev: its copy has no FPS1 block (magic absent) with its own package and with its own mods/state.toml (dev-mode and model-table on); the Chicago pick also landed on CITY 0 with that state. Its exe does not run the chicago-slot plugin ("trusted plugin is unavailable: driver.chicago-slot"), so the slot package cannot be used on it. Dev mode on/off not measured.
- Copies: devtest/c47wip (build-wip at the time of the run) and devtest/c47dev. Results: devtest/exp_work/c47/*.json.
- Caveat: standing/driving on the Chicago run used the same b13 day level as the Miami runs (package from the wip build); the FPS numbers are from one run each (no repeats), so differences under about 10% are noise.

### PVS packing A/B (Polish, 14.10.; same code state, light subdivision + D2 PVS, standing mean of 4 headings / 15 s drive)
| spot | pack (32 KB, clustered masks) | no pack (32 KB, masks dropped) | LA-sized buffers |
|---|---|---|---|
| l_down_e | 23.4 / 24.3 | 23.4 / 22.3 | 24.1 / 16.6 |
| l_down_w | 29.3 / 28.8 | 29.3 / 23.8 | 29.6 / 28.1 |
| fps_drop_1 | 22.2 / 22.3 | 22.7 / 16.1 | 22.9 / 25.6 |
| dense_1 | 28.1 / 29.0 | 27.6 / 29.5 | 28.1 / 29.6 |
| dense_2 | 29.9 / 29.9 | 29.9 / 30.0 | 30.0 / 30.0 |
| dense_3 | 30.1 / (8.7 stuck) | 29.6 / 26.1 | 29.5 / 27.2 |
| standing mean | 27.2 | 27.1 | 27.4 |

Standing differences are within noise (~0.3 FPS); the drive numbers are dominated by the harness (collisions, stuck
car). The denser PVS encoding (CHI_POLISH_PVS_PACK, default on with CHI_POLISH_PVS=d2) brings no measurable FPS, nor
do the LA-sized buffers: the PVS lever is exhausted. Remaining: engine per-cell culling (Infrastructure queue).
