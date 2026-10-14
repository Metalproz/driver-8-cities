# C45 loading stalls: mechanism and engine design (Infrastructure, 2026-10-13)

## Mechanism (measured, devtest/_out/c45_e/g/i/j; no-stall runs c45_a/c/d)
- The stall is Driver 1's own spool-sync wait, not the host: the game frame counter 0x800970D8 and the car freeze
  for 67-101 VBlanks (1.1-1.7 s) while the area loading flag 0x800969E8 is set; the CPU sits in VSync (0x80079CA0..)
  called from **0x800335A4**, the wait loop of **0x800334B4** (main loop call 0x80023758).
- 0x800334B4: model fix-up 0x80033E54 if gp+0xAD8; then, while the spool-busy flag **0x800972D4** is set AND
  **0x80032F98** says the car needs the next region (car cell within a 9-cell margin of its region edge, neighbour
  flags 0x8009730C / 0x80097314), loop { palette LoadImage, DrawOTag, DrawSync, VSync(0) } until 0x800972D4 clears.
- 0x800972D4 clears only when the WHOLE spool queue (0x800A7BA4) is empty. At the stall the queue held the area
  switch's 8 texture pages (type 1, 17 sectors each) + models (type 3, 21 sectors) AHEAD of the region data the car
  needs (type 0: 5 + 18 sectors): 180 sectors at ~2 per VBlank. Area switches whose region data is not needed yet
  (8 of 9 measured) do not stall: the load runs in the background while the game draws normally.
- The area loader 0x80033B10 queues all pages of the new area, resident or not (residency 0x800BE278 only picks the
  slot), so every switch costs ~350 KB (Polish: also with CHI_POLISH_AREAS=2).

## CORRECTION (22:5x, after the prototype runs)
0x80032F98 returns "wait" ONLY while an AREA load runs (0x800969E8, checked at 0x80033228) and the car is within
~6 cells of its region edge towards the new area (direction gp+0xAC0, 0x80033340..). The wait is deliberate: the car
must not enter the new area before that area's pages / models are in. The region entries seen behind the pages in the
trace are incidental. So parts 1+2 below are WRONG as a fix (part 2 lets the car into the new area with stale
textures / models, C33-style); the prototype stays only as an experiment switch (CHI_C45=1, default off).
Runs: C45 off 3 stalls (63-74 VBlanks); prototype on 5 runs 0 stalls - but only because it skips the safety wait.

## Revised plan: area loads must finish before the car is 6 cells from the boundary
- **Fewer bytes per switch (main lever):** (3) skip pages that are already resident in 0x80033B10 (engine, guest
  patch) + Polish: neighbouring areas share pages with identical index/content (corridor layout, CHI_POLISH_AREAS).
  8 pages + model ~160 sectors now; every shared page saves 17 sectors (~0.12 s at 2x).
- **Earlier start, with care:** the switch starts in the hysteresis band (0x8003401C, threshold 13); starting earlier
  replaces the old area's pages while the car still sees them, unless those pages are shared - so it only works
  together with shared pages (same corridor idea as Driver 2).
- (R21: CD speed stays x1, not a lever.)

## Original design (superseded parts 1-2)
1. **Region data first (main fix).** The spool reader 0x80034C74 takes queue entries in order; patch its selection
   so a pending type-0 (region) entry is read before type-1/3 (area pages / models): a small guest routine in a code
   cave that scans the 16-byte queue for the first unread type-0 entry and swaps it to the read index (entries are
   self-contained: type, sectors, CD position, destination, callback). Then the needed region arrives in ~23
   sectors (~0.2 s) instead of after 180.
2. **Wait only for what the car needs.** In 0x800334B4 the loop condition becomes "a type-0 entry is still queued"
   instead of the global busy flag 0x800972D4 (patch at 0x800335AC: call the same queue scan). With (1) the wait,
   when it happens at all, is ~0.2 s; area pages and models keep loading in the background (as for the 8 non-stalling
   switches today). Model install stays gated by gp+0xAD8 (after the load), so no C33-style half-installed models.
3. **Skip resident pages.** In 0x80033B10, a page that is resident (0x800BE278) keeps its slot and is not queued;
   the page/slot pair table 0x800A7F54 (index gp+0xB44, consumed with the spool entries) gets no entry for it.
   Needs the converter to give differing pages different indices across areas (Polish: shared pages identical =
   same index). Cuts the bytes per switch, so background loads finish sooner.
4. **Earlier start (already partly there).** The area switch already starts in the 5-cell hysteresis band
   (0x8003401C rewrite, threshold 13); with (1)+(2) that is enough for most crossings; widening the band only if
   STL1 still shows stalls.

Order: 1+2 together (one test level not needed: pure exe patch, Chicago-gated like the other CITY 3 patches),
measure with the STL1 ring (build-wip, 0x9F082330) on the same drive as the trace (3->16 at D1 161300,44000);
then 3 with Polish's converter change. Risk to check: Driver 1 relies on queue order elsewhere (Play Again reset,
spool reset 0x800337D4, C33 hook on 0x80033B10) - the reorder must keep the reader's indices consistent.
Host-only parts: none in the fix; STL1/FPS1 measurement is dev-only.

## Part 3 in detail: skip resident pages (guest exe patch; implement when Polish's unique-index level exists)
- Data precondition: one page index per distinct page content (identical pages share an index), at most 128 page
  indices in all (residency table 0x800BE278 = 128 bytes). Today indices 0-4 / 9-12 are reused by all areas with
  different content -> skipping would show the old area's textures.
- Page reads are ONE disc stream: at the first page the start code (0x80032EC0) sets the countdown gp+0xAB0 = number
  of queued pages (gp+0xB44); the page callback (0x80034BD4) counts it down and streams on into the next entry
  without a seek; pairs (slot 0x800A7F54 / page 0x800A7F50, index gp+0xB44) are installed in order (0x80033AB8,
  counter gp+0xAE0, both reset when equal).
- **P1 (enqueue loop 0x80033C18..0x80033CFC, rewritten with asm()):** hoist the per-page CITY table lookup / sector
  base out of the loop; a resident page (0x800BE278[page] != 0) with the Chicago flag set gets no queue entry and no
  pair, only its disc offset (t6 += 0x11), t1 and a2 advance.
- **P2 (0x80032EC0 `lw a1,0xb44(gp)` -> `addiu a1,zero,1`):** countdown 1 per page; after each page 0x80032DEC
  takes the next entry, compares the drive position (gp+0xA84) with the entry's sector: contiguous = stream goes on
  (no seek), after a skipped page = seek. Gate: Chicago only (plugin code-word switch now, host-only; in a PS1
  build the D2-city exe path).
- Build/test in an isolated root (devtest/_root_np: own disc copy, generated, build dir; patches as an opt-in group
  CHI_C45_SKIP=1 so the shared default patch list stays unchanged), measure with STL1 on Polish's level.

## Measured + conclusion (14.10.)
- Part 3 (skip resident stable pages, isolated root): stalls 79 -> 72 VBlanks (~9 %, 175 -> 154 sectors); not adopted
  (texture downscale 604 -> 834 for Polish's shared pages).
- Earlier start via the threshold is impossible: an entry fires towards the new area at cell > size - t and back at
  cell < t (region 30 cells); t > 15 toggles every frame, t = 15 is D1's flapping 1-cell band.
- Remaining lever (data): switch entries one region further back (corridor start, placed by the converter) and corridor
  regions drawing only textures both areas share (Driver 2's corridors) -> load starts 30+ cells early, no guard stall,
  no wrong textures. Engine unchanged.
