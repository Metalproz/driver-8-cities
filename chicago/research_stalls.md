# Chicago stall map (C45)

## STL1 baseline run (QA-3, build-wip, b13, 2026-10-13 22:2x) - INVALID for Chicago

Result: the four 3-minute routes ran in NEW YORK (CITY 5, start -136176, 164, -358832), not Chicago. The Chicago
selection (up to the page-2 row, then Chicago) did not happen in this run, so the cursor landed on NY. The stall
numbers below are therefore NOT Chicago data. Rerun needed after the menu path is fixed.

What the readouts did show (NY, valid as a reading of the counters only):
- STL1 counter (stalls): 3 to 4 per run, all reached within the first 30-60 s; no new stall during the 150 s after that.
- STL1 longest gap: 956 VBlanks (about 16 s), recorded at load (ring entries with x=z=0, area 0, before the level).
- The ring entries after load show area 0 -> 3 with region 0 -> 70 (load), and one entry at region 54/70 (area 3).
- FPS1 read 66-98 during the runs (not the ~25 the overlay showed earlier); the car was stationary in NY (no drive).
- The damage reset was applied (1-4 per run).

Open: fix the Chicago menu path for this copy (check the page-2 row, the Chicago row and CITY 3 before the drive), then
rerun the four routes. Real driving only (no pokes). Earlier (teleport) freeze results in this file are invalid.

## Spot-start routes (QA-3, build-wip b13, dt.prepare with spot start) - INVALID for Chicago

Both routes (S1 from fps_drop_1, S2 from l_down_e) loaded MIAMI (CITY 0, pos 130539,168,427944), not Chicago: the
spot start did not take effect in this build path. The car stayed still (34-35 stuck-reverse triggers per run).
STL1 delta during drive: 1 per route, longest gap 317 VBlanks (about 5.3 s), ring: one entry at the same position,
area 1 -> 1, region 116 -> 116, flags 0. FPS1 380-396 (headless copy runs uncapped; above 60 is expected).
Open: make the spot start load Chicago (check CITY 0x80096834 = 3 before the drive), then rerun both routes.
