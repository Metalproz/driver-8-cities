# Traffic research (EXP, 2026-10-13): Miami AI write trace and spawn path

Scripts: `devtest/exp_work/traffic_agg.py` (trace), `traffic/analyze.py`, `traffic/func.py` and
`traffic/disasm.py` (capstone on disc/SLUS_008.42), `traffic_tables.py` (table dumps). Raw output in `devtest/exp_work/traffic/`.

## Struct layout (new)
- The AI car block at 0x8009B0A4 (stride 0xDEC) is 9 sub-records of 0x18C each (9 x 396 = 3564 = 0xDEC).
  Global record index g = 9*slot + j, sub-record address = 0x8009B0A4 + g*0x18C.
- Sub-record +0 byte = its own id (g+1); +1 byte = 0; +2 byte = state (1/2/3), copied from the per-index
  table at 0x80098950 + 0x50*s6 (+0x10), where s6 = g-... (the init index).
- Per-frame writers (old != new, many frames): 0x8001B470, 0x8001D360/D39C/D788/D790, 0x8001F58C, 0x8001819C,
  0x80017A24, 0x80018384, 0x8004C830, 0x80043A88/43BCC (ra 0x80014E8C). Position (+0x18) is at slot level.
- The road index was NOT found in any slot field in this run (the 0x50 table and the +0x24 pointer
  of that table are set by the init path, see below).

## Spawn/init path (the candidate for "AI spawns once and sits")
- 0x800154A8(a0 = s6 index, a1 = id, a2 = flag byte, a3 = pointer): clears the sub-record, writes +0 = s6+1,
  +1 = 0, then per frame +2 = lbu(0x80098950 + 0x50*s6 + 0x10). Writes of the init loop: pc 0x80015600 / 0x80015630, ra 0x80016CA4.
  The state write is pc 0x80015F90 (ra 0x80015E84). The 0x50 record's +0x24 word is a pointer set to a1/a0 by code
  paths selected by 0x80/0x82/0x83 codes (road or junction lump pointer?), unverified.
- Caller 0x80016B28 (ra 0x80016CA4): skipped when CITY (0x80096834) == 2. It loops: s1 = byte from 0x80058A00(a0, &out);
  0xFF = end, 0xFE = special (0x50 table), otherwise entry = 0x80093180 + 12*s1: s16 id at +0 (-1 = none), u8 at +2, word at +4 (-> a3), word at +8.
  0x80058A00 scans a data table with (x,z) comparisons (player position 0x8009B0BC style values) and returns the index.
- Observed in the trace: during driving in Miami only 1 re-init happened in the captured window (slot 2, frame 19069,
  record id 0x12 cleared and set). Load-time spawn writes were NOT captured (ring overwritten by per-frame noise).

## Tables after load (traffic_tables.py)
- 0x80093180 (12-byte x 85 entries): IDENTICAL in Miami and Chicago (LA slot, CITY 3): 50 zero, 35 ids 0x1CD.. (461, 464, 466...).
  Not city-specific data in this build.
- 0x80098950 (0x50 records): Miami ids 512..519 (ok); Chicago: 0..11 (zeroed/other) and mostly zero bytes.
- AI control byte +3 after load: Miami [1,0,0,0,1,255,0,0]; Chicago [1,0,0,0,0,0,0,0].
  Miami has 1-2 moving traffic slots (position changes per frame); Chicago has no active traffic slot.

## Hypothesis (not yet proven)
Chicago's traffic records are never activated because the spawn search (0x80058A00 + 0x80016B28 loop) finds no entries:
either the search's city data (not the 12-byte table, which is shared) has no Chicago entries, or the ids it returns refer
to roads that the converted network does not contain. Test next: dump 0x80058A00's data pointer and table(s) at load
in Miami vs Chicago (its (x,z) records), and log the return values s1 per call (wtrace on 0x80093180 region and on the
init call at 0x80016B28 with a `wtrace_add` on the stack, or an exec breakpoint-like dump of a1/a0 at 0x800154A8).

## Limits
- wtrace ring (262144 writes) saturates at ~700 writes/frame with 3 active cars: 40 s windows lose 2/3 of the writes.
  Tracing one slot (slot 1 full, 3564 B) with paged dumps works (~70% coverage).
- Headless game runs much faster than real time; dumps must page by frame (dump_into), never unbounded.

## Follow-up (EXP, load-time capture, traffic_load.py)
- Load-time init writes (sub-record id byte at +0, pc 0x80015630, ra 0x80016CA4), sub-record index n = 9*slot + j (id = n):
  - Miami (Take a Ride row 0, CITY 0): n = 10, 19, 20 only; 39 id writes at frames 8076-8157 (re-inits every few frames).
  - Chicago with roads (work/var_v2_420.lev, LA slot row 2, CITY 3): n = 3, 9, 10; 39 id writes at frames 8582-8609.
  So the spawn search DOES return entries in the Chicago-with-roads level; the load-time init is not what is missing.
- Control byte +3 after load: Miami [1,0,0,0,1,255,0,0]; Chicago-with-roads [1,0,0,0,255,255,0,0].
  Miami's moving slot 1 (ctl 0) was NOT among the load-time inits (n=9 absent), so its activation happens later (during play).
  Activation trigger is therefore still open: next step = in-drive trace of ctl +3 writes (slots 1-7, 4-byte ranges only, no full block)
  in both Miami and Chicago-with-roads.
- 0x80058A00 data pointer: *(0x80097530) = a heap address that changes per run (0x800BDFA4 in one run, 0x800BE024 in another).
  Contents at it: 16-byte records of 32-bit words (e.g. 0x002E5000, 0x18, 0x002E6800, 0x88, 0x002EF000, ...), i.e. a per-level
  table built at load. NOT yet matched to the LEV ROADS lump (not done). Inputs (x,z) of the call and per-call return values
  were NOT logged (step 2 open).
- Not done: LEV ROADS byte search in RAM; x,z input logging.

## Activation (EXP, traffic_ctl.py: 8 slots, [+0,+4) ranges, 30-60 s drive, both levels)
- Correction: the pointer at *(0x80097530) is the DRAW buffer (dt.py DRAWBUF); 0x80058A00 is NOT shown to be a spawn search.
  The init chain 0x80016B28 -> 0x800154A8 (ra 0x80016CA4) is real; its table 0x80093180 is shared by both levels.
- ctl byte (slot +3) is not a spawn flag. Writer 0x8001D608 (registration, a0 = slot base, a1 flag):
  a1 != 0 -> +3 = 1 (player-type, slot 0 via ra 0x80023278); a1 = 0 -> +3 = 0 (traffic). It runs per frame for a registered car.
  Caller 0x8001A798 (ra of the writes = 0x8001A798): loop over 0x50-records s2 = 0..21 (table 0x80098950 + 0x50*s2, s1 = base+5).
  It calls 0x8001D608(a1=0) only when the record state byte b1 (= 0x50 record +1) is not 4 and not 2 path, and s2 < 0x16.
- State byte b1 writers: 0x800155A0 (init: 0), 0x80015BA8 (= 1, after 0x8004FFE8 flag test), 0x80015C54 (= 2, after the +0x24 road
  pointer and a 0x80021820 call, after a lookup of a per-car word at +0xD0 scaled by a division-like mult/sra sequence).
- Miami (30-60 s drive): 0x50 records with b1 = 2 for s2 = 0..11 (incl. s2 = 8 = slot 1 record); slot 1 registered every frame
  (2702 writes, +3 = 0), moved (positions change, e.g. (112180,443732)).
- Chicago-with-roads (same drive): b1 = 2 for s2 = 0,3,4,5,6,7,10..14; s2 = 8 and 9 have b1 = 0 (no activation for slot 1);
  slot 1 never registered (0 writes of 0x8001D61C); slots 4/5 +3 = 255 (not a car). Positions of slot 1 static.
  So the gap is b1 of the slot 1 record (s2 = 8) staying 0 in Chicago (the 0x80015BA8/0x80015C54 test fails there), which depends on
  the road pointer (+0x24) and the +0xD0 word/division test. The per-car word +0xD0 and the 0x80021820 road test are the next things to read.
- Next experiment: log b1 writes (pc 0x80015BA8/0x80015C54) for s2 = 8 in both levels with the +0x24 pointer value and the +0xD0 word;
  then check what 0x80021820 returns (road lookup at the pointer?).

## Road check and state machine (EXP, traffic_b1.py: writes + registers of 0x50 records s6 = 8, 9)
- Records: 0x50 table, s6 = 8 -> slot 1 car (sub-record index 9), s6 = 9 -> sub-record 10.
- Road check call (0x80015C54 sets +1 = 2, then 0x80015C5C jal 0x80021820 with a0 = x, a1 = z (world units, from the
  record's car position), a2 = out buffer; the result goes to +8 (0x80015C60 sb)).
- 0x80021820 = wrapper: calls 0x80021690 (lookup of the road-map cell word at (x,z) from the per-level tables pointed by gp+0x8dc/0x8d4),
  stores type (bits 16-25, u16 at out+0), height (low 16 bits, s16 at out+2) and angle (bits 30-31 << 10, at out+4), returns 1 if the cell word != 0.
  This matches the D1 road-map cell packing in NOTES (height | type 10 bits | angle 2 bits).
- Result, both levels: +8 = 1 at every check (Miami: 63 + 185 checks; Chicago-with-roads: 959 + 2657). So the cell lookup finds a cell in
  BOTH levels for the positions the records use. The road-cell check is NOT what fails in Chicago.
- Inputs seen: Miami s6=8 at (105000,420000)..(160500,420000); s6=9 at (114000,442500). Chicago-with-roads s6=8 at (153000,78000)..(195000,69000),
  s6=9 at (151500,78000)..(195000,43500) (same record area as the Chicago player, ~(170000,55000)).
- After the check, both levels go through 0x80017C50 (reset of +1 to 0 at 0x80017D30, every cycle). The continuation 2 -> 3 (0x80017FB4,
  after a test of record +3 and a call to 0x80014FC4 with the car position +0x2C/+0x30/+0x34) and 3 -> 2 (0x800183B8) happens ONLY in Miami
  (Miami s6=8: 4 writes of 3, 4 of 2; Chicago: none). Record +3 (b3) is 0 in the end-of-run dumps of both levels.
- Conclusion so far: the difference is after the cell check, in 0x80014FC4 (and the +3 byte). That lookup is the next thing to decode
  (what does it return for a road/junction at the car's position, and which ROADS/JUNCTIONS field does it read).

## 0x80014FC4 (the 2 -> 3 test) and its tables (EXP, traffic_recs.py)
- Caller 0x80017F80: 0x80014FC4(a0 = record +0x2C, a1 = record +0x30, a2 = record +0x34, a3 = 2; stack: +9 byte, out ptr).
  Output word goes to record +0x40 (0x80017FA8). Not the cell check.
- Body: row = 20 * a0 at table 0x8009E744 (= 0x800A0000 - 0x18BC); a1 selects a byte count and an s16 pair (+4..+0x12, modes 0..3);
  the code then computes 1500*value style offsets (multiplies by 375 via shifts) and a remainder modulo the count byte; it calls 0x8004FFE8 (a per-car value)
  and reads a gp pointer at 0x80097044 (a per-level table, 0x1534B8 Miami, 0x16A77C Chicago). Writes the result to *out.
- Table 0x8009E744 rows are road-level data: 4 corner s16 pairs (e.g. Chicago row 0: (-296,124),(-296,139),(-296,139),(-296,124)) plus count bytes.
  It is a ROADBOUNDS-derived table (20 B per road; ROADBOUNDS lumps: Miami 365 roads, var_v2_420 420, NY 410), 16-bit compressed.
  I could not match the rows byte-for-byte to the LEV ROADBOUNDS records (different encoding).
- Record values at the end of load (s6 = 8, 9): Miami +0x2C = 34, 76; +0x30 = 0, 1; +0x40 = 0, 0x7FFFFFFF.
  Chicago-with-roads +0x2C = 318, 294; +0x30 = 2, 2; +0x40 = 0x7FFFFFFF, 0.
- Candidate failure (NOT confirmed): index 318 is past the 316 rows that fit between 0x8009E744 and 0x800A0000 (6332 B / 20 B),
  so the lookup for road 318 would read the next RAM area. But Miami has 365 roads (rows up to 364) and works, so the capacity limit alone does not
  explain it. Still open: which ROADBOUNDS/JUNCTIONS field the 2 -> 3 test reads (count byte, bounds, junction exits) for the roads near the car.
- Next: a per-call dump of 0x80014FC4 arguments and return (wtrace on record +0x40 writes with registers) in both levels; then compare the count byte
  and corner pairs of the rows the records use (Chicago 318 / 294 vs Miami 34 / 76), and check the table at 0x8009E744 + 20*318 in Chicago RAM.

## Rows, table extent and mode bytes (EXP, traffic_rows.py; cross-checks of the coordinator's questions)
- (a) Table start: header RM_HEADER at 0x8009E714 (12 int32: Miami 600, 840, 450750, 630000 | Chicago 960, 1260, 720750, 945000 | then 1136128,
  1157728, 1179328, 1200928 | 126, 125, 116, 115). The header is 0x30 bytes, so the 20-B table starts exactly at 0x8009E744 (header + 0x30).
  Row 0 is a road row (corners of the road's bounds), not header neighbour data. Confirmed by the content.
- Table end: Miami rows 0..364 are non-zero (365 rows, = ROADBOUNDS count); row 365 is zero. Chicago rows 0..419 (420 rows, row 420 zero).
  The rows run past 0x800A0000 (row 419 at 0x800A07F0) with no collision in the dump. The "316-row capacity" hypothesis is REFUTED.
- Row layout (20 B): 4 bytes of per-mode counts (bytes 0..3), then 4 corner s16 pairs (z negated vs ROADBOUNDS).
  Axis check: roads whose ROADBOUNDS spans Z have bytes 0 and 2 non-zero (Miami 34: 01 00 01 00; Chicago 0: 02 00 02 00);
  roads spanning X have bytes 1 and 3 (Miami 76: 00 02 00 00; Chicago 294: 00 01 00 01; Chicago 318: 00 FF 00 00).
  So mode 0/2 = Z-axis, mode 1/3 = X-axis (inferred from 6 rows).
- Mode of the car record (+0x30): Miami s6=8 -> 0 (road 34, Z, byte0 = 1: passes), s6=9 -> 1 (road 76, X, byte1 = 2: passes).
  Chicago s6=8 and s6=9 -> 2 (Z mode) on roads 318 and 294, which are X-axis: byte 2 = 0 -> the lookup has no count -> no 2 -> 3.
  Candidate cause: the car's mode (direction class) is set to the wrong axis in Chicago (it is copied from the spawn/record init, not from the road).
- (b) +0x40 sentinel: 0 = cleared by the init (0x80015568); 0x7FFFFFFF = "no road result", written by 0x80017A40 (Miami, 736 times, mostly s6=8)
  and by 0x80015E3C (Chicago, 119 times, the fallback path after 0x80016F0C). The 2 -> 3 path itself stores the 0x80014FC4 result at
  0x80017FA8: Miami s6=8 stores 0x00022CA4 and 0x0001C908 (4 times) = real road results; Chicago never stores there.
  So 0x7FFFFFFF is not the discriminator (both cities end on it for s6=8); the discriminator is whether 0x80014FC4 returns a value (Miami) or none (Chicago).
- Open: where the record mode (+0x30) comes from (init argument or spawn descriptor), and the +3 gate byte at 2->3 (lbu +3 must be non-zero).

## +0x30 source (EXP, traffic_mode.py) and correction
- Writer of record +0x30 (mode) is pc 0x800175EC (ra 0x800175A8): mode = stack candidate[ (rand % count) ], where rand = 0x8004FFE8 and count = the
  sum of the four counters built by 0x80013A90 over the 22 car records (match of record +0x28 with the four exit ids of one junction).
  The candidates come from the four 16-bit exit fields of the 44-byte junction record (table pointer 0x80097040: lh +0xA, +0x12, +0x1A, +0x22).
  So mode = the junction exit slot (0..3) a car takes, chosen at random among free exits. It is NOT stored in ROADS.
- Consequence: the "axis" reading of row bytes 0..3 (Z = 0/2, X = 1/3) is an inference from six rows. The mode itself comes from the junction exit
  numbering. Infrastructure's cause (road-cell rotation bits 30-31 = lane travel direction, written as 0 by our converter) is their hypothesis;
  I have not verified it against the converter output.

## Cause (EXP, final)
- Confirmed: 0x80014FC4 (the 2 -> 3 test) returns a value only when the road row count byte for the car's mode is non-zero. Miami passes
  (road 34 mode 0 = byte 0 = 1; road 76 mode 1 = byte 1 = 2). Chicago fails for roads 294 and 318 with mode 2 (byte 2 = 0 in both rows).
- Confirmed not the cause: the road-cell lookup (0x80021820 finds a cell in both levels), table capacity (rows 0..419 are present and contiguous).
- Open: which field of the 20-byte row (bytes 0..3) is the lane direction, and whether build_full writes it with the same convention as the D1 lump
  (Infrastructure's rotation-bits hypothesis). Test that on the new build: count byte for each mode on X-axis roads must be non-zero for the modes the cars use.

## Traffic test (EXP, traffic_test.py)
- Miami (original, row 0), 150 s drive, log every 5 s: active traffic slots (ctl +3 == 0, within 40000 of the player), moving slots (> 0.5 units/s).
  Result: loaded, 0 freezes, kernel ok, 1-2 active slots, one moving steadily at ~3.8 units/s (sample every 16 s). Speed units are world units/s (scale unverified).
- Command for the Chicago build: `python devtest/exp_work/traffic_test.py --city chicago --row 2 --drive 150` (row 2 = LA slot in the current build; use
  the row the build uses for Chicago, e.g. 4 for the 5th-row slot build). Writes devtest/exp_work/traffic/traffic_test_chicago.json.

## Roads build test (EXP, roads build: build-test slot, var_roads_day / var_roads_night, row 4)
- Chicago Day, 150 s (traffic_test.py --slot --row 4): loaded, freezes 0, kernel ok. Active traffic slots (ctl 0) 0 -> 2; moving 0 in
  the samples. The player ended the drive stuck or in a crash (wreck at 16 s in one run, crawl at ~(159880, 37800) for 120 s in another).
  Screenshot traffic_chicago_3.png: player car in a crash (smoke, damage bar) with dark cars ahead; not conclusive whether those are traffic.
- Chicago Night, 150 s: loaded, freezes 0, kernel ok; active 2 slots, moving 1 at t=21 s (2.0 u/s), then 0; player stuck at (158714, 164, 51276).
- Slot matrix rows 0..4 (build-test slot, city la, day + night where offered): all rows loaded (0.5-3.6 s), kernel ok, freezes 0.
  Row 0 Miami, row 1 SF, row 3 NY ok (city 1/5). Row 2 = LA (offered N, city 3 ok). Row 4 = Chicago: Day/Night offered, city 3, chi_flag 1.
  Wrecks in rows 0,1,3,4 are the drive's normal wreck end (not a fault).
- Verdict vs pass criteria: freezes 0 and kernel ok PASS; moving traffic > 0 only in single samples (not sustained) -> NOT established.
  The player also stalls, so the drive stops producing traffic samples early. Needs a driving fix or a longer clear road before counting moving cars.

## Standing test, roads build vs Miami (EXP, traffic_stand.py, 120 s, player not steering)
- Start: Chicago roads build at the default start (169889,164,53476) = the converter's road seed (not a separate midpoint); Miami at its default start.
- Miami: 2->3 transitions 291, 3->2 transitions 270 (pc 0x80017FB4 / 0x800183B8). Traffic slots 1 and 2 (ctl 0) moved > 500 units per 10 s throughout the 120 s.
- Chicago roads build: 2->3 = 0, 3->2 = 0. ctl-0 slots 4 (none moved > 500 units in 10 s). All 22 records end in b1 = 2 (road check passed, no forward step).
  Record +0x40 = 0x7FFFFFFF in 19 of 22 (no road result); records 1, 5, 14 have values. ctl_end [1,0,0,0,254,255,2,0].
- Record state vs road rows (end of run): rec 1 road 164 mode 2, row bytes [01,00,02,00] (count for mode 2 = 2, non-zero), still b1 = 2.
  So the count byte is not the only gate on the new build: the 2->3 step also needs record +3 != 0 (rec 1 has b3 = 0; in Miami, transitions occur at records with b3 = 1)
  and 0x80014FC4 must return a value (Miami's +0x40 gets real values, Chicago's mostly stay 0x7FFFFFFF).
- Stuck records: all 22 (roads 164, 165, 168, 173, 246, 276-278 in Chicago). Miami stuck records: mostly b1 2 at the end too (the moving cars use transitions in between).
- Next: log record +3 and the 0x80014FC4 return for the Chicago records during the standing test (the +3 writer and gate), and compare with Miami's +3 at 2->3.

## +3 writers and junction exit (EXP, partial, traces paused on the coordinator's request)
- Record +3 writers (static): 0x800140AC (= 1 when 0x800138A0(record) returns 1 and +0x34 == 1), 0x800140C8 and 0x800140E8 (= 1 or other values on
  the same path), 0x80013FF8 (= s0 after a call 0x800130D4 and +0x34 == 0), 0x800141A4 (= 0 when +0x34 == 0 and +3 == 0 and the timer +0x3C < 0x5B).
  0x800138A0 (the test) reads: record +0x20 = junction index j (JUNCTIONS 44 B table at 0x80097040 + 44*j, byte +3 of that row: if non-zero the
  test returns 1 at once), else record +0x24 (exit slot, parity t0 = (ex+2)&3) and the junction's 8-byte exit entries (lbu/ lh pairs) compared with
  the record's id byte and the road id.
- Captured in Miami standing test (3000 events): +3 set to 1 by 0x800140E8 (5), 0x80013FF8 (4), 0x800140C8 (3); cleared by 0x800141A4 (2947).
  The 2->3 and 3->2 transitions (0x80017FB4 / 0x800183B8) also write +3 values 3 and 2. The 0x80014FC4 return (0x80017FA8) is real in Miami
  (0x22CA4, 0x1DA9C).
- Chicago roads build standing test: +3 set to 1 only 3 times (0x800140E8 2, 0x80013FF8 1); no transitions. The junction rows at the
  records' +0x20 indices (194-203) have byte +3 = 0 and the exit entries that the test needs are absent.
- Infrastructure's offline finding (junction cells missing in the roadm: Chicago 0 junction cells vs Miami 1247; roadm written into mirrored region rows)
  explains the empty junction exit test. Paused: rerun after the fixed build (Chicago day 120 s + Miami comparison).

## Roads build 2 (EXP): standing test, traffic test, slot matrix
- Standing test (Chicago Day 120 s, default start): 2->3 = 49, 3->2 = 47 (build 1: 0). Still 0 ctl-0 slots moving > 500 units per 10 s.
  Records with a road-check result but no moves: record 2 (p18 = 430, the distance value) and record 12 (474) stay at b1 = 2.
- Miami standing (120 s): 2->3 = 292, 3->2 = 268; slots 1 and 2 moved > 500 per 10 s in every sample (unchanged).
- Traffic test Chicago Day (150 s): loaded, kernel ok, freezes 0; 1-2 active slots, one moving at 4.6 u/s once; the player wrecked at 38 s
  (the drive ends at a wreck, so the sample count is 7).
- Slot matrix rows 0..4 (roads build 2, day + night): all loaded, kernel ok, freezes 0; row 4 Chicago chi_flag 1, Day/Night offered.
- Light phase word 0x800970D8 (a monotonic counter, so &3 is the phase): Miami 579 at 5 s, 1899 at 31 s, 6510 at end (about 51 per second);
  Chicago 869 at 5 s, 2957 at 32 s, 9796 at end (about 77 per second). So it counts at a rate that differs between runs (probably per frame rate
  or real time); the phase = value & 3 changes every ~0.02 s of game count. Not yet tied to traffic.
- Next: per record car-to-junction distance (+0x18) and phase check (+0x24 == phase & 3) at each junction once transitions exist.

## After state 3: what moves the car, and the phase counter (EXP, roads build 2)
- Phase check (static): 0x80014038 loads word 0x800970D8, `& 3`, compares with record +0x24; not equal -> the state machine skips to 0x800141D4.
  So the junction phase gate is: (phase counter & 3) == record +0x24.
- Phase counter vs VSync (40 s standing): Miami phase 2062 (52/s) vs VSync 4462 (112/s), ratio 0.46. Chicago phase 3082 (77/s) vs VSync 8152
  (205/s), ratio 0.38. Not a fixed fraction of frames, not a fixed wall-clock rate: it is a game counter with its own rate per run (not a VSync or frame counter).
- Position writers (traced slot 1 and 2 position +0x18..+0x24, 40 s standing): the same integrator in both cities: pc 0x8001C000 / 0x8001C014 /
  0x8001C028 (ra 0x8001C11C). Miami 13282 position writes (incl. 0x8001D170 / D184, ra 0x8001D28C). Chicago: the integrator writes as often
  (3602 + 2556 entries), so the car IS integrated in Chicago; the car stays still because its velocity input is zero.
- The integrator (0x8001BF88 -> 0x8001C030): reads velocity words at struct +0x0/+4/+8 (per-frame sums), updates the fixed-point position
  at +0xC/+0x10/+0x14 and stores pos >> 4 to car +0x18/+0x1C/+0x20 (and copies to +0xC8..+0xD0). The velocity inputs come from the caller
  (not decoded yet). So the missing piece for Chicago is the velocity/target set after the junction (state 3) step, i.e. what the caller
  writes into the car's velocity words when the record is in state 3.
- Next: compare the car velocity words (struct +0x0..+0x8 and the caller's inputs) in Miami and Chicago at a 2->3 transition; the caller of 0x8001BF88 is the next function to read.

## Roads build 3 (EXP)
- Standing Chicago Day 120 s: 2->3 = 50, 3->2 = 46 (build 2: 49/47). No ctl-0 slot moved > 500 units per 10 s.
- Traffic test Chicago Day: loaded, kernel ok, freezes 0; one sample with a moving car at 91 u/s (t = 10.6 s, not sustained, looks like a jump);
  the player wrecked at 16.8 s (drive ends).
- Screenshot traffic_chicago_1.png: the player car in smoke with a crash marker; no traffic car clearly in view.
- Still no sustained movement, so the velocity-source trace continues (see the struct diff below).
- Struct diff (Miami moving vs Chicago stuck, slot 1 and 2, first 0x120 bytes, 30 s standing): 50 differing words per slot. The
  fields that differ include +0x04..+0x0C and +0x18..+0x2C (positions/matrix), +0x40..+0x60 (velocity-like words, nonzero in Miami only),
  and +0x88..+0xC0 (the 0x800xxxxx-ish values, different in Chicago). Not yet decoded field by field.

## Velocity chain (EXP, partial): integrator, accumulators, wheel loop
- Integrator 0x8001BAC0 (called from 0x800233C4, per frame): for each registered car (list at 0x80053B8, count at gp+0x8C0): v_new = v + acc
  (+0x40 = +0x40 + +0x58 etc.), then zeroes the accumulators +0x68..+0x70. Writers of +0x40/+0x44/+0x48 (pc 0x8001BCF4.., ra 0x8001C11C).
- Force accumulators +0x58..+0x70 are written by the per-wheel loop 0x8001F4EC..0x8001F598 (ra 0x8001EE7C): pc 0x8001F58C (+0x68) and 0x8001F598 (+0x58).
  Inputs: the wheel records a2 (+0x30, +0x40, +0x50), a1 (+0x60 compared with a constant = ground flag), a0 (+8 halfword), and scratchpad
  0x1F800158.. (per-wheel vectors). Miami scratchpad 0x1F800158 = 0x0756 0x0000 0xFD09 0x0078; Chicago 0x1F800158 = 0x2499 0x0000 0x01DA 0x0053 (different
  per-frame vectors, not a fixed zero).
- Force values written at 0x8001F598 (30 s standing): Miami zero for 1543 of 12240 writes (top values -2, -0x206, 0x80); Chicago zero for 8325 of 18774 writes
  (top values 0, -2, 0x206). So Chicago's wheel/contact inputs are zero more often: the contact or wheel inputs (not the AI target) are the first
  thing to compare, and the scratchpad vectors (0x1F800158..) and the per-wheel record fields are where to look.
- Not decoded: which road field feeds the wheel contact (road height/ normal from the road-cell word or ROADS), and the car's throttle source.

## Ground contact check (EXP)
- Car heights from the struct dumps (30 s standing, same moment as the player): Miami traffic slot 1 y = 165 (player y = 164), slot 2 y = 164.
  Chicago roads build 2/3 traffic slot 1 y = 164 (player y = 164), slot 2 y = 163. So the traffic cars sit at the same height as the player in both cities.
- The player stands on the ground in both cities, so a car at the same y is on the ground too. Floating or sinking by more than 1 unit: not seen.
- Not checked: the cell ground height itself (road-cell low 16 bits vs car y, via the 0x80021820 lookup), and the wheel contact flag (+0x60 of the wheel
  records). These need the wheel record pointer and the cell lookup; the y match makes "cars float or sink" unlikely.
- Chicago cars are far from the player: slot 1 at (191998, 164, 64082), slot 2 at (164831, 163, 50566), player at (169889, 164, 53476).

## Wheel records and first zero field (EXP)
- The per-wheel loop 0x8001F490 (entry; loop at 0x8001F4C8) is called from 0x8001EE74 with a0 = car struct, a1 = wheel-set pointer (sp+0x20 built
  by 0x8001D6E4 from the car struct: a1 = car+8, a2 = sp record + 8, sp record +0x30 = 0, +0x34 = car byte +2, +0x60 = 0).
  So the wheel inputs come from the car's own fields (+2 byte, +8 word), not from an AI target.
- Miami vs Chicago slot 1 (30 s standing): car +8 word = 192510 (Miami) vs 0 (Chicago); +0x30 = -10 vs 0; +0x34 = 0x0B51 vs 0x1000;
  +0x38 = -11 vs 0; +0x40 (linear velocity) = -274680 vs 0; +0x58 (force) = 13468 vs 0.
- Writers of car +0x08..+0x0F: 0x8001B468..0x8001B498 (ra 0x8001C11C, and 0x8001B9F4 once). That is the orientation/matrix builder of the integrator
  (the same family as the position writers). So car +0x08 is a matrix element built from the car's quaternion (+0x30..+0x3C).
- First field zero in Chicago and non-zero in Miami along the chain: car +0x08 (word; Miami 192510, Chicago 0). Its input is the car's
  quaternion/heading block (+0x30..+0x3C): Chicago's quaternion is zero except +0x34 = 0x1000. So the first root cause to test is the car's
  initial orientation (quaternion) at spawn, not the wheel contact.
- AI throttle/steer: not found. No writes into the car struct right before 0x8001EE74 besides the wheel-set build.

## AI state machine: which fields state 3 writes (EXP, static, 0x80017C50..0x800183C0)
- Record stores in that range (base s1 = 0x50 record): +0x01 (state, 2 or 3), +0x02, +0x08 / +0x09 / +0x0C / +0x0D / +0x12 (halfword) / +0x14 / +0x17,
  +0x18 / +0x1C / +0x20 (words, from the 2->3 path at 0x80017FD4..0x80017FE8), +0x24 (exit/phase value), +0x28 (word), +0x40 / +0x44 (words, the 0x80014FC4 result).
- The +0x18 / +0x1C / +0x20 words are NOT a target point: they are copied from the stack out-struct sp+0x30..0x38 filled by 0x80021820 (the road-cell wrapper)
  at 0x80017F1C, whose a0/a1 are (x, z) read from a table (s0 / s3) and whose a3 is the out-struct. So +0x18..+0x20 hold cell data (type/height/angle words),
  which explains the "distance" values I logged earlier (p18 = cell type word, not a distance).
- The only speed/steer-like values written by the state machine are +0x40 / +0x44 (0x80014FC4 result, the road result), and those stay 0x7FFFFFFF or a
  value that never becomes a drive target. No store in 0x80017C50..0x800183C0 writes a throttle, a speed target or a steer field of the car struct.
- Note: 0x80021820 is called with a2 = record +0x24 (a value 0..3) in this path, and my earlier decode reads a2 as the out pointer. That looks like an
  argument mix-up in my decode; check the wrapper's argument order before relying on the out-struct conclusion.
- Conclusion for the AI side: the state machine decides which road/junction the car is on, but does not set a drive target; the drive input
  (throttle/steer) must come from another controller, which I have not found. The Chicago/Miami difference in the state machine is the
  2->3 gate; the throttle source is still open.

## Roads build 4 (EXP)
- Standing Chicago Day 120 s: 2->3 = 50, 3->2 = 49 (build 3: 50/46). Slots 1 and 2 moved > 500 units per 10 s at t = 19 and 26 s (in the 120 s run),
  then stopped (all slots back to 0 movement for the rest of the run). Second run (45 s): 49 / 46, same window (t 18.6 and 25.4 s).
- Traffic Chicago Day 150 s: loaded, kernel ok, freezes 0; moving samples: one at 75.7 u/s (t 10.6, a jump), two slots at 2.6 and 0.8 u/s (t 15.9); the
  player then stays in place (no further motion); the drive reports no wreck (the position stalls). 
- Traffic Chicago Night 150 s: loaded, kernel ok, freezes 0; one car moving at 64.4 u/s at t 10.4 (jump-like), player wrecked at 18.7 s.
- Slot matrix rows 0..4 (roads build 4, day + night): all loaded, kernel ok, freezes 0; row 4 Chicago Day/Night offered, chi_flag 1.
- Screenshots: stand_chicago_slot_t18.png and stand_chicago_slot_t25.png (t = the moving window); traffic_chicago_1.png / _3.png from the Day drive;
  traffic_chicago_night_1.png / _3.png from the Night drive. The t25 image shows the player car with a red marker and nearby buildings; a traffic car is not clearly
  identifiable. Same for the other shots: not clearly showing traffic.

## Stop point (EXP, traffic_stop.py, Chicago roads build 4 standing, 0.5 s logs, 60 s)
- Slot 1: (140765,160,55587) at 0 s, (136691,164,55584) at 3 s, (162045,164,24726) at 14.5 s, (162045,164,13737) at 16.1 s, then stops at (191998,164,64082)
  at ~17.7 s and stays there to 60 s. Slot 2: (163536,164,32311) at 0 s, (193410,164,35568) at 11.3 s, (164831,164,35575) at 14.5 s, stops at (164831,163,50566) at ~17 s.
- The speed is not a drive: slot 1 covers ~11000 units in 1.6 s (about 7000 units/s) and about 40000 units in 13 s with jumps. The stop point is the same in every
  run (191998,164,64082 and 164831,163,50566 in earlier runs too), so the stop is a fixed position, not a random slowdown.
- Matrix at the stop (slot 1): 00f0 0000 0000 0000 (orientation values 0x00F0 / 0x1000 = a flat orientation), i.e. the car has no heading change.
- Records at the stop: the record mapping to slots is not confirmed in this log (record s6 index vs slot is still open); state b1 = 2 for most records, +3 = 1 for two.
- Screenshot stop_chicago_slot.png (60 s): the player car from behind, buildings to the sides; a traffic car is not clearly visible.
- Not decoded: the cell (road id and ConnectIdx / dead end / junction box) at (191998,164,64082), because the road-cell lookup is not reachable from the log;
  a cell dump at that position is the next step, plus the Miami comparison (same logging) to check whether Miami cars pass junctions at speeds in the same range.
- Interpretation: the moves are a velocity runaway (thousands of units per second) followed by a fixed stop, so the first thing to check is the velocity
  scale (the accumulator sums in 0x8001BAC0 and the wheel forces), not the road.

## Relocation (EXP): do Miami cars also jump and respawn?
- Yes. Miami standing (60 s, 0.5 s logs, slots 1 and 2): 83 position jumps larger than 2000 units per 0.5 s (typically 4000-6000 units, about 10000 units/s).
  Cars go to (0,0,0) (removed) and reappear at new points. Examples: slot 1 (94457,164,428298) -> (0,0,0) at 2.5 s -> (105000,164,421741) at 4.1 s;
  slot 2 (156770,164,420234) -> (150998,164,420232) -> ... -> (118196,165,399184) at the end. The respawn points (105000 / 103500, 420000-421700) are the
  same coordinates as the road-check inputs seen in the Miami record traces.
- So in Miami too, cars are teleported/relocated repeatedly and drive at thousands of units/s between respawns. The Chicago "stop" points are respawn points
  of the same kind (not special); in Chicago the cars reappear at (191998,164,64082) and (164831,163,50566) and stay.
- Writers of the car position (+0x18, copied as >>4 from the fixed-point block): 0x8001C000 / C014 / C028 (integrator, ra 0x8001C11C) and 0x8001D170 / D184
  (ra 0x8001D28C, the same copy in another loop at 0x8001D108..0x8001D288; it also writes +0xC8). The (0,0,0) reset is the init at 0x800154A8 (0x80015600 clears the
  0x18C block, ra 0x80016CA4), called from the spawn loop 0x80016B28. The respawn point then comes from the spawn entry the search 0x80058A00 returns;
  I did not trace the fixed-point source of the respawn position, so the exact entry that picks (191998,164,64082) is not identified yet.
- Open: why Chicago's two respawn points are always the same and why the cars then do not drive from them (their spawn entries and the road/junction data they read).

## Records of the two Chicago respawn cars vs a Miami respawned car (EXP, 20 s)
- Record mapping: car slot k has its main record at s6 = 9k - 1 (slot 1 -> s6 8, slot 2 -> s6 17). Checked against the position logs.
- Chicago, car at (191998,164,64082) = slot 1 (s6 8): b1 = 2 for the whole 20 s (never 3), +3 = 0, road 294, mode 3, junction 237, exit 2.
  Car at (164831,163,50566) = slot 2 (s6 17): b1 = 2 (never 3), +3 = 0, road 185, mode 0, junction 224, exit 0.
- Miami respawned car (slot 1 at (103316,165,421740) / (98824,164,421738)): s6 8 b1 = 2, road 21, mode 3, junction 18, exit 3; it reaches b1 = 3 for slot 2's
  record (s6 17, road 23, junction 20, exit 3) at t = 11.4 s: the 2 -> 3 step happens.
- Phase gate (phase & 3 vs exit +0x24): Chicago s17 exit 0 and the phase reaches 0 at t = 28.1 s, but the record stays at b1 = 2, so the phase gate is
  not the only blocker: the next test (junction entry test 0x800138A0 or the 0x80014FC4 road lookup for road 185 mode 0 at junction 224) fails.
- Which field differs: the state/mode fields look the same (b1 2, +3 0, mode 0..3). The difference is the junction/road data behind them: Chicago's junctions
  (224, 237) and roads (185, 294) give a failing lookup, while Miami's (junction 18/20, roads 21/23) pass. The junction rows and road rows of those ids are
  the thing to dump (row byte +3 and the exit entries for junction 224 / 237).

## Junction and road rows of the respawn cars (EXP, RAM dump, roads build 4)
- Junction array = pointer 0x80097040 (44 B per junction, id = index: Chicago 224/237 and Miami 20/18 match). Road array = pointer 0x80097044 (16 B, id = index).
- Junction 224 (Chicago, type 1, pad 0): exits {from 225 road 181 flags 4 extra 0 | from 236 road 304 flags 4 | from 223 road 180 flags 4 | from 208 road 303 flags 4}; x,z = (608,748).
- Junction 237 (Chicago, type 0, pad 1): exits {from 238 road 191 flags 0 | (-1,-1) flags 0 | (-1,-1) flags 0 | from 231 road 366 flags 0}; x,z = (667,1061).
  So junction 237 has flags 0 (Miami junctions: flags 4 on all exits) and only 2 valid exits; the car's exit 2 is EMPTY (-1).
- Junction 20 (Miami, type 1): exits {(6,12,4,0), (21,24,4,0), (34,36,4,0), (19,23,4,0)}; x,z = (396,139). Junction 18 (Miami): exits {(4,10,4,0), (19,22,4,0), (32,34,4,0), (17,21,4,0)}.
- Road 185 (Chicago): ridx 185, ConnectIdx 229 / 228, lanes 3, LaneDirs 4, length 36, x0 608, z0 851.
  Road 294 (Chicago): ridx 294, ConnectIdx 148 / 158, lanes 2, LaneDirs 2, length 16, x0 514, z0 722.
  Road 21 (Miami): ConnectIdx 17 / 18, lanes 3, LaneDirs 4, length 15, x0 347, z0 139. Road 23 (Miami): ConnectIdx 19 / 20, lanes 3, LaneDirs 4, length 15, x0 381, z0 139.
- Consistency check (car record road + junction + exit):
  - Miami slot 1 (road 21, junction 18, exit 3): junction 18 exit 3 = road 21 -> consistent. Miami slot 2 (road 23, junction 20, exit 3): junction 20 exit 3 = road 23 -> consistent (this car passes 2->3).
  - Chicago slot 2 (road 185, junction 224, exit 0): junction 224 exit 0 = road 181, and road 185 is in no exit of 224 -> inconsistent.
  - Chicago slot 1 (road 294, junction 237, exit 2): exit 2 is (-1,-1) and road 294 is not in 237's exits -> inconsistent.
- Kinds of difference: (1) Chicago junction 237 flags 0 vs 4 in all Miami junctions, and two -1 exits; (2) the car's road is not an exit of the car's junction in Chicago (both cars), while it is in Miami;
  (3) road 294 LaneDirs 2 and lanes 2 vs LaneDirs 4 / lanes 3 in Miami roads.

## Build 5 (A = lights, B = no lights), fresh prepare (EXP)
- Correction: road 185 z0 is 595 (RAM and LEV agree: 595). My earlier 851 was a decode slip (I read 0x0353 instead of 0x0253).
- Standing Chicago Day 120 s, 0.5 s logs. A (lights): 3 drive steps (50 < d <= 2000 per 0.5 s), 28 relocation jumps (> 2000 per 0.5 s).
  B (no lights): 2 drive steps, 28 relocation jumps. Neither variant drives sustainably; the cars move only in the first ~20 s (t 6-20 s).
- Final state (same in A and B): slot 1 at (178931,164,55317), record s6 8: road 172, junction 213, exit 3, b1 = 2, +3 = 0.
  Slot 2 at (166680,164,55406), record s6 17: road 171, junction 213, exit 3, b1 = 2, +3 = 0. Both stay in state 2 for the rest of the run.
- RAM junction 213 (type 1, lights off in the RAM row? type 1 as in the LEV): exits (from 214, road 172, flags 4), (229, 262, 4), (212, 171, 4), (193, 261, 4).
  Junction 229: exits (230, 186, 4), (-1,-1,0,0), (228, 185, 4), (213, 262, 4); x,z = (608,593).
- RAM roads (16 B, pointer 0x80097044): road 171 conn (213, 212), lanes 3, LaneDirs 6, length 36, x0,z0 (588,595). Road 172 conn (214, 213), lanes 3,
  LaneDirs 6, length 17, (588,576). Road 185 conn (229, 228), lanes 3, LaneDirs 4, length 36, (608,595). RAM = LEV for all three.
- Consistency: road 185 is exit 2 of junction 229 (consistent). Roads 171 and 172 are exits 2 and 0 of junction 213, but the cars' recorded exit is 3, which
  points to road 261 in junction 213. So the car's exit field and the junction's exit order do not match for junction 213 (exit 3 wanted, the car's
  road sits at exit 0/2). Lanes and LaneDirs (3, 6 and 4) are normal.
- Conclusion: the lights setting (A vs B) makes no difference; the failure is the exit selection at junction 213 (the car is on an exit road
  but its exit field points to another road).

## Distance gate (+0x18) in Miami (EXP, 120 s, 0.5 s logs, traffic_stop.py)
- Record +0x18 (first word of the cell block at +0x18) for records with a junction: during the run it falls from several hundred or more to 0-50
  as the car approaches. 251 state 2 -> 3 transitions were seen at 0.5 s sampling. The value just before the step was 2-1642 (examples: 1213 -> 2,
  362 -> 27, 338 -> 10, 547 -> 13, 640 -> 22, 61 -> 13), and just after it 0-48. Miami cars therefore reach the < 650 range on the way in, and the
  step happens there. The distance value is still moving at the sampling rate, so the exact step point is not resolved.
- Records waiting in state 2 with +3 = 0 near a junction: p18 median 5054, 25th percentile 464 (2729 samples). No Miami car stops at 930 to wait.
- Chicago lead car stops with +0x18 = 930 (above 650) and stays: the gate needs < 650, so the car never gets +3. Miami cars do not stop on their way in
  (they keep moving), so the stop itself is what differs.
- Junction box (JUNCBOUNDS, 8 bytes per junction in the LEV, read as hhhh): Miami 20 (14428, 2, -26034, -7), 18 (28964, 1, -26034, -7), 33 (-11072, 1, -2784, -7),
  19 (-11072, 1, -26034, -7), 21 (-25608, 2, -26034, -7). Chicago 213 (-32358, 2, 11536, -1), 229 (-2358, 2, 11536, -1). Read as two int32 pairs
  (x = w0 + 65536*w1, z = w2 + 65536*w3) the Chicago 213 centre is (98714, -54000), which is far from the stopping region (178931, 55317), so this read is
  not confirmed as the box centre. The box size (2 or 3 cells) is not decoded from these 8 bytes.
- The stopping rule (what sets the stop distance 930 in Chicago) is not found: no Miami car brakes before a junction in this test, so there is no Miami
  reference for the stop distance.

## Player-off-road test (EXP, build 5 A, Chicago Day, 120 s)
- Correction (Infrastructure): JUNCBOUNDS 213 is (164250, -54000) by the int32 count-prefixed read (entry i at 4 + 8*i); my 98714 was an offset slip.
- The player was driven 10 s straight ahead (cross held, no steering): (169889,164,53476) -> (154984,164,51302) at the start of the standing run.
- Result: drive steps 0 (excluding relocations), relocation jumps 0, 2->3 transitions 5 (all early), no car passes junction 213. Slot 1 at (151889,165,54113)
  and slot 2 at (166680,164,55406) from ~10 s to 120 s, both records in state 2 with road 171 / exit 1 or 3, junction 213.
- So moving the player off road 262 does not free the cars in this run. The lead car sits at (151889,165,54113), not behind the parked player's old
  spot, and it does not move. The player blocker hypothesis is not supported by this run (not a clean test: the away drive may have changed the car states).

## b6 (EXP, fresh prepare; Chicago Day; all standing runs use 0.5 s logs; relocations = jumps > 2000 per 0.5 s)
- Off-road start (CHI_START 17444,110302 = D1 180750,58500): drive steps 31, relocation jumps 183, 2->3 transitions 165 (0.5 s sampling).
  Junction changes of the two car records: see the line above. Cars do leave their spawn and change junctions (for example 229 -> 213 -> 229 -> 230).
- Default start: drive steps 12, relocation jumps 96, 2->3 = 81; junction changes s8 20, s17 5.
- Traffic test b6 off-start (150 s): loaded, kernel ok, freezes 0; moving samples at 31.6 s (29.4 u/s) and 68.6 s (3.6 u/s); two cars at 0 most of the run.
- Slot matrix rows 0..4 (b6 day and night): all loaded, kernel ok, freezes 0.
- Reading: most of the motion is respawn-driven (relocations 96-183 per run); real drive steps are 12-31 per run and cars do pass junctions, but
  they spend long periods at 0 speed. The off-road start clearly changes the outcome versus the default start (more drive steps and transitions).

## Same metrics, Miami vs Chicago b6 (EXP, 120 s standing, 0.5 s logs)
| run | drive steps | relocation jumps | 2->3 | junction changes (s8,s17) | drive/reloc | 2->3 per reloc |
|---|---|---|---|---|---|---|
| Miami (default start) | 52 | 161 | 260 | 40 | 0.32 | 1.6 |
| Chicago b6 off-road start | 31 | 183 | 165 | 51 | 0.17 | 0.9 |
| Chicago b6 off-road start (series run) | 30 | 184 | 163 | 51 | 0.16 | 0.9 |
| Chicago b6 default start | 12 | 96 | 81 | 25 | 0.13 | 0.8 |
- Not the same range yet: Chicago b6 off-road has about half Miami's drive/relocation ratio and about half its 2->3 per relocation.
- Car at junction 230 (Chicago b6, slot 2 record s17): wanted exit (+0x24) = 0. The junction 230 row (RAM): type 0, exits entry 0 = (-1,-1) empty,
  entry 1 = (-1,-1) empty, entry 2 = (229, road 186, flags 0), entry 3 = (215, road 254, flags 0); x,z = (609,556). So the car's wanted exit slot 0 is
  EMPTY in the junction (no valid road). Junction 213 (slot 1, record s8, exit 3): valid exit (from 193, road 261, flags 4).
- Screenshots: devtest/exp_work/traffic/series_b6_series_06..15.png (1 s steps). Frame 10 shows the player car from behind on a wide road with a building
  line ahead; a traffic car is not clearly identifiable in the frames I checked.
- Reading: traffic is not functionally done. Chicago b6 is about half of Miami on drive ratio and 2->3 per relocation; the wanted exit of a parked car can
  point at an empty exit slot (junction 230, exit 0).

## Exit picker data (EXP, b6 off-road standing run, end state)
- This run did not reproduce the coordinator's case: car 2 ended at (0,0,0) (relocating) with record s17 on junction 229, road 262, exit 2, mode 3.
  The b6 standing run is not deterministic between runs, so the junction-230 case has to be caught in a run that reaches it.
- Record s17 at end: cur road (+0x28) 186, road (+0x2c) 262, junction (+0x20) 229, wanted exit (+0x24) 2, mode (+0x30) 3, lane (+0x09) 0, b1 2, +2 0, +3 0.
- Road 254 (ROADS 16 B, pointer 0x80097044): ConnectIdx (215, 230), lanes 2, LaneDirs 2, length 19, pad byte +0xB = 0 (not one-way), x,z (590, 556).
  Road 254 ROADBOUNDS row (20 B at 0x8009E744 + 20*254): bytes 0..3 = [0, 1, 0, 1] (mode counts: modes 1 and 3 non-zero, modes 0 and 2 zero).
- Road 186 (ROADS): lanes 2, LaneDirs 2, pad 0.
- Junction 230 entries: (-1,-1) x2, (229, road 186, flags 0) at entry 2, (215, road 254, flags 0) at entry 3.
  Check on the way: the entry 2 road 186 is the car's current road (+0x28 = 186), so it is skipped (road == current road). Entry 3 road 254 is valid,
  not one-way (pad 0), and mode 3 has count byte [3] = 1, so 1 - 1 = 0 >= lane (0) passes. With lane 0 road 254 would not be dropped by the lane-count check,
  so the drop would need the car's lane (+0x09) to be >= 1 (the coordinator's case, car on the rot-2 lane). The prefill (sp+0x20..0x23) is not captured here.
- Stack trace of the picker (sp+0x20..0x23) not captured: the run did not reach the junction-230 case.

## Probe smoke test and picker capture (EXP)
- Probe "chicago traffic" copied to devtest/exp_probe2 (no saves; disc read from the OneDrive _disc, read-only; OneDrive untouched).
  slot_test --direct: row 4 Day and Night loaded (3.6 s, kernel ok, freezes 0, Day/Night screen offered), row 2 = LA loaded (city 3, kernel ok).
- Picker capture (b6 off-road start, 120 s, record writes of +0x30 = 0 at pc 0x800175EC, 40 captures): one record s6 14 repeatedly at t 35.5-35.8 s:
  +0x24 exit 0, current road (+0x28) 172, lane (+0x09) 0, junction (+0x20) 214 (type 1), road (+0x2C) 173, b1 2, +3 0.
  Junction 214 runtime byte +3 = 0. Its 4 entries (road, flags, extra): (173, 4, 0), (-1, 0, 0), (172, 4, 0), (255, 4, 0).
  Entry 2 (road 172) is the car's current road (skipped). Entry 0 (road 173) and entry 3 (road 255) have flags 4 (not the flag-2 skip).
  Still to check for these two: ROADS pad +0xB (one-way), the lane-count row byte [mode]-1 >= lane, and the per-slot prefill bytes on the stack.

## Junction 214 gate fields (EXP, b6 off-road standing, 0.5 s logs, 120 s)
- Records at junction 214 with the gate fields (+0x18 cell word, phase & 3, +0x24 exit, +0x34). The gate is phase & 3 == +0x24 (exit 0) with +0x18 < 650.
- Straight cars (road 173, mode 0, +0x34 = 0) go 2 -> 3 when the phase is 0 and +0x18 is small: e.g. t 58.8 s record s6 0 (+0x18 = 41, phase 0) -> state 3 (b3 1);
  t 65.2 s record s6 19 (+0x18 = 45, phase 0) -> state 3. Records with phase 1, 2 or 3 stay in state 2 (for example t 6.6 s s6 14, +0x18 = 434, phase 1: waits).
- Cars with mode 3 and +0x34 = -1 (road 255) at junction 214 also reach state 3 (t 13.0 s s6 18, +0x18 = 41; t 19.6 s s6 2, +0x18 = 4).
- So at junction 214 the gate passes when the phase is 0 and the distance is small; this run's s6 14 did not stop with a valid pick, so it does not reproduce
  the earlier standstill. Not captured here: the return of 0x80012E98 (only observable through the +3 write it blocks).

## b6 vs b6nl (no lights), off-road start, 120 s standing (EXP, fresh prepare)
| run | drive steps | relocations | 2->3 | junction changes (s8,s17) | drive/reloc | 2->3 per reloc |
|---|---|---|---|---|---|---|
| Miami (default start) | 52 | 161 | 260 | 40 | 0.32 | 1.6 |
| b6 run 1 | 31 | 183 | 165 | 51 | 0.17 | 0.9 |
| b6 run 2 (series) | 30 | 184 | 163 | 51 | 0.16 | 0.9 |
| b6nl run 1 | 35 | 182 | 161 | 52 | 0.19 | 0.9 |
| b6nl run 2 | 30 | 184 | 152 | 54 | 0.16 | 0.8 |
- Lights make no difference (b6 and b6nl within noise). Both Chicago variants are about half of Miami on drive/reloc (0.16-0.19 vs 0.32) and on 2->3 per relocation (0.8-0.9 vs 1.6).
- Extra b6 run (the end-state run): 34 drive steps, 178 relocations, 152 2->3, 49 junction changes, drive/reloc 0.19, 2->3 per reloc 0.85.
  So b6 runs span drive/reloc 0.16-0.19 and b6nl 0.16-0.19: no difference from the lights.

## Traffic-light visuals (EXP, final task)
- Positions: Miami junction 20 (grid 396,139) -> world (143250, 164, 423000); Chicago b6 junction 214 box centre (cells 588.5, 574.5) -> world (162000, 164, 84000)
  (cell mapping from build_full cell_of: x = (1500·cx − UXM)... with UXM 720750, UZM 945000 for Chicago; Miami grid 450750 / 631500 per QA-3).
- Player poked to the position after load, 12 shots at 1 s intervals with 0x800970D8 & 3 logged.
- Miami phases over the 12 shots: 0,1,0,1,3,1,1,1,0,3,1,3. Chicago b6: 0,3,0,0,2,3,2,3,0,2,1,2 (the phase is a counter, so its low two bits change within a second).
- Answer: NOT demonstrated. The light head is not clearly in view in these frames (Miami shows a pole with an arm at the top left; Chicago shows
  traffic and cars ahead). The pixel differences between frames are dominated by moving scene parts (camera, cars), not by a light head changing colour.
  Image paths: devtest/exp_work/traffic/tl_miami_00.png (phase 0) and devtest/exp_work/traffic/tl_chicago_01.png (phase 3).

## b8 test (EXP, build-test slot build, var_roads_b8_day/night.lev, port 4450)
- Check 1, regression matrix (slot_test --matrix --rows 0..4, 60 s drives): 9/9 runs loaded (0.5-1.6 s), kernel ok, 0 freezes.
  Every run ended in a wreck (4-51 s) from the drive pattern. Row 4 flag readback 0x366e2734 is the same for day and night (flag address unreliable in this build); night is visible (mean brightness row 4 day 120, night 67). Summary: devtest/_out/1013-181521-slot-test-summary/summary.json
- Check 2, Chicago Day at 20 s: yes, daylight street (sunlit brick, cars, grey-blue cloudy sky). Image: devtest/exp/drive_row4_n0.png.
- Check 3, standing test Chicago Day 120 s, CHI_START=17444,110302, 0.5 s logs: drive steps 23, relocations (>2000) 132, 2->3 = 73, 3->2 = 73 (wtrace pc counts). Loaded, kernel ok. Result file: devtest/exp_work/b8/stand_b8_day.json. Compare b6 31/183/165 (the 2->3 counter differs: 73 here; counting method may differ).
- Check 4, traffic light glow at night (TLIGHT01 at D1 166594,0,55588; car poked 700 units west, heading 1024 unverified): YES, a coloured glow on the signal head. NS/WE logged: shot 0 green lit (294 green px), shots 1-3 red (503 red px, 0 green). Brake lights show as red glowing dots at the tail lamps. Image: devtest/exp_work/b8/glow_night_1.png. Facing is not verified (heading mapping unknown).
- Check 5, R12 spots (Chicago Day, CHI_START = spots.json d2):
  - underbridge: no lift (y -1188 -> -1187 over 10 s). Caveat: the car covered about 183k units of z in 9 s, which is not driving (probably relocation or a teleport); the test is inconclusive.
  - c20_p2n: no fall-through (y 160..238, largest drop about -65 per 0.2 s). Wrecked at 19 s.
  - beach_n: drowning works; water covers the car (only a sliver visible) and the Game Over menu appears. Image: devtest/exp_work/b8/spot_beach_n_drown.png.
- Images used: 4 (drive_row4_n0, glow_night_1, spot_beach_n_drown, plus the glow data was numeric).

## b9 test (QA-1, build-test slot build, var_roads_b9_day/night.lev, port 4410, copy devtest/qa1)
- Check 1, slot matrix rows 0..4 (run before build-test was rebuilt at 18:43): 9/9 runs loaded (0.5-1.6 s), kernel ok, 0 freezes, 0 fatal. Row 4 flag readback 0x366e2734 for day and night (flag address unreliable, as in b8). Log: devtest/_qa1/b9/matrix_log.txt. Caveat: the matrix used slotstate city "chicago", not "la" as requested.
- Checks 2-4 BLOCKED: after the 18:43 rebuild of build-test, the same copy no longer reaches the level. Control run (slot_test row 4 Day, unchanged tool): loaded=N, kernel unknown ("-"), debug server returns no player position; the game log shows bios_backend=HLE (LLE fallback), not the retail BIOS that the matrix used. Standing test (traffic_b9_qa1.py: start 17444,110302, 120 s; also without start and with city "chicago") stays on the title screen (devtest/_qa1/b9/b9_day_t60.png) with all car slots 0. So no drive-step, relocation, 2->3, lane or stop data for b9 yet.
- Next: Infrastructure to check the 18:43 build-test (BIOS boot path / bios_hle default) before b9 can be measured.

## b9 test, rerun (QA-1, rebuilt build-test, classic menu, fresh prepare, start 17444,110302, 120 s Day)
- Loaded, start pos (180750,164,58500), kernel ok, 0 fatal. Log: devtest/_qa1/b9/stand_b9_day2.json; metrics.py: drive steps 26, relocation jumps 142, 2->3 169, junction changes (s8,s17) 41. b8 (old method) was 23/132/73; the 2->3 count differs a lot, so compare with care.
- Lanes (AI record +0x09 lane, road NumLanes at ROADS +6 = 4, LaneDirs +7 = 12 on all 4-lane roads): records on 4-lane roads show lane 0 (921 samples), lane 1 (124), 255 (282, no lane). Both lanes 0 and 1 occur. Which side is lane 0 (kerb side) not determined (no geometry check against road x,z direction).
- Stops (car static 0.5 s, not moving): 60 samples; example car 1 at (165219,165,80816) static 7.6 to 9.9 s, with the AI records' +0x18 cell words logged (devtest/_qa1/b9/stand_b9_day2.json). Wide junction box classification not done.
- Day screenshot devtest/_qa1/b9/b9_day2_t60.png: rear view of the car; tail lamps glow red. Head lights are not visible from this angle, so "head/tail off" is not confirmed.

## b9 lights and lane side (QA-1, day, one run, devtest/_qa1/b9/lights_sheet_day.png)
- Tail lamps: lit in the rear view at 20 s before any braking, and still lit during a square brake hold (lights_day_brake.png). So they look always-on, not brake-only (brake glow not separated).
- Head lights: NOT confirmed. The camera cycle (select) gave sky/building views, no front view of the car; front-view check still open.
- Lane 0 side vs ROADBOUNDS / travel direction: NOT done this round (car-to-AI-record link and road direction not established).

## b9 tail lamps vs Miami (QA-1)
- Miami Day (original city, same b9 copy, rear view at 20 s, before braking): tail lamps UNLIT. Chicago Day: lit red. So the always-on red lamps are a Chicago-only difference (likely ours, not authentic D1). Sheet: devtest/_qa1/b9/rear_compare_chicago_vs_miami.png.

## b9 traffic bug hunt, part 1 (QA-1, Loop start only)
- Place 1 (Loop start, CHI_START 17444,110302, b9 classic menu, 120 s, devtest/_qa1/b9/stand_b9_day2.json): no car static more than 15 s after moving (0 stuck). Car slots 1/2 show large steps (6000 to 55000 units per sample, about 1.1 s apart), 61 and 79 such steps; y stays 163 to 166 (no air or ground jumps). Whether these are fast teleports or the log cadence is NOT decided; needs a per-0.5 s rerun and a screenshot at a jump.
- Places 2 (avenue junction) and 3 (highway stretch): NOT run in this pass.

## b9 traffic hunt, part 2 (QA-1, 90 s each, shots every 10 s)
- Loop start (17444,110302): 8 shots, no traffic car visible; player car parked against a building. Sheet devtest/_qa1/b9/hunt_loop_sheet.png.
- overpass_e (129395,44286): 8 shots, no traffic car visible; player car on the freeway. Sheet devtest/_qa1/b9/hunt_overpass_sheet.png.
- No fault flagged (no car appearing or vanishing mid-view, none parked at green, none in buildings). Downtown junction spot: no junction spot exists in spots.json, so the Loop start was used.
