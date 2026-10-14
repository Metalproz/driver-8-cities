# Research: Chicago day/night Take a Ride entries and Driver 2 music in Driver 1

Author: EXP (read-only research, 2026-10-13). Evidence from the user's discs and the local source trees.
Scratch outputs (not shipped): EXP scratchpad (lump script, extracted D2 MUSIC.BIN, 8 XM files).

## A. Daylight

### A1. Which LEV the converter uses
- `convert.py` reads `work/d2_CHICAGO.LEV` at all ~10 call sites (lines 637, 867, 898, 1229, 1382, 1406, 1529, 1570, 1932, 2093). `d2_CHICAGO_night.lev` is not referenced in the converter or build scripts. The current build is the DAY level.

### A2. Day vs night LEV (levfile.py lump compare)
- `work/d2_CHICAGO.LEV` = day. `work/d2_CHICAGO_night.lev` = night, byte-identical to the disc file `/DRIVER2/NLEVELS/CHICAGO.LEV` (sha1 prefix 9f632aaab5cd).
- Disc layout: `LEVELS/` (day, 10915840 B), `NLEVELS/` (night, same size), `MLEVELS/` and `MNLEVELS/` (mission variants, smaller). Driver 2 keeps day and night as two full files.

| Lump | Day vs night |
|---|---|
| TEXTURENAMES, MAP, PALLET, MODELNAMES, MOTIONCAPTURE, CAR_MODELS, SUBDIVISION, LOWDETAILTABLE, OVERLAYMAP, CHAIR, STRAIGHTS2, CURVES2, JUNCTIONS2_NEW | identical |
| TEXTUREINFO (1045 entries) | 80 entries differ (from entry 2 on); 8-byte records whose offset-like field changes, so these texture slots point at different page data |
| tpages (permanent texture pages) | night is 10240 B shorter (565248 vs 555008); no 2 KB block matches in place; best shift match is 10240 B (127 of 271 blocks), so the night pages are a re-packed set |
| MODELS (inmem, 172716 B) | differs (first at byte 301), same size |
| SPOOLINFO | differs (first at byte 100), same size |
| spooled area (8214528 B) | 872 of 4011 2 KB blocks differ, in 11 contiguous ranges of about 80 blocks (region/area data: probably lit or lamp data and night models) |

Reading: the night file changes textures (lit windows, re-packed texture pages), models and area data. Palettes, map, road and car lumps are the same. A night conversion is the same converter run on the other input file, plus whatever the texture re-pack needs.

### A3. How Driver 1 does Miami 1 / Miami 2
- Driver 1 has ONE LEV per city on its disc: `/DRIVER/LEVELS/` has CREDITS, FLAT, FRISCO, IVIEW, LA, MIAMI, NEWYORK, TRAIN (no day/night copies). `d1_MIAMI.lev` has one PALLET (2996 B), one TEXTUREINFO, no second texture or lighting set.
- Take a Ride lists Miami 1/2, SF 1/2, LA 1/2, NY 1/2 (NOTES). CITY (0x80096834) holds only the city index (Miami 0, SF 1, LA 3, NY 5). The "1/2" choice is a separate runtime variable or mode flag in the exe, not a file.
- Not determined: the exact variable and what it changes (lighting, colour, weather). Needs an exe-side probe near the CITY code (0x80068A00 / 0x8006ECC4 per NOTES). Open.

### A4. Conclusion for "Chicago 1 = day, Chicago 2 = night"
1. Two converted LEVs (day from `LEVELS/CHICAGO.LEV`, night from `NLEVELS/CHICAGO.LEV`), with the exe loading the file for the chosen entry. This matches Driver 2. Needs: a converter path parameter (small); a level-path switch in the exe. The 8-slot path table at 0x80086EC0 is full and Chicago takes LA's slot, so entry 2 needs a free index (the CREDITS index 7 crash in NOTES is related) or a runtime path override keyed on the entry. Effort: converter about 0.5 day; exe/path change 1-3 days; moderate risk.
2. One LEV plus a runtime switch (swap the 80 texture entries and tpage data on load, plus models and area data). Needs texture reload on switch; the engine does not do this for D1 cities. More work and risk than option 1.
Recommendation: option 1 with a path-override hook. Engine change: needs the user's decision.

## B. Music

### B1. Driver 2 MUSIC.BIN
- Disc: `/DRIVER2/SOUND/MUSIC.BIN` (777944 B) on `D:/recomps/games/Driver 2 (Disc 1) (v1.1).bin`. Local and usable.
- Format (DriverSoundTool `driver_sound.cpp`): 8 entries of `{xm_offset, bank_offset}` (`XM_SONGS 8`), then per song a compressed XM module and its own VAG sample bank (`LoadSoundBank`).
- Parsed: all 8 songs are "Extended Module", 8 channels. Driver 1's MUSIC.BIN has the same layout (886840 B).
- Extraction done in the EXP scratchpad: `DriverSoundTool.exe -bin2xm MUSIC.BIN` gives `MUSIC_song0..7.xm` (decompressed XM). `-bin2xm` did not write the sample banks as WAV (log: "sample count 0/1"). VAG export needs another option (`-psx2xm` / `-sbk2wav` exist in the tool; not tested).
- Chicago tracks: `REDRIVER2/src_rebuild/Game/C/main.c` (lines ~545-578) sets the D2 music id from GameLevel and the mission-number parity. GameLevel 0 (Chicago) = track 2 (even mission) or 6 (odd). Havana = 1/5, Rio = 0/3, Vegas = 4/7. gWantNight changes start positions and mission numbers, not the music id, so Chicago day and night both use tracks 2 and 6 in the D2 code.
- Sizes of extracted XM: song 2 = 305038 B, song 6 = 280170 B. File offsets: song 2 xm@192028 bank@218784; song 6 xm@596688 bank@612132.

### B2. Driver 1 music on its disc
- Disc: `/DRIVER/SOUND/MUSIC.BIN` (886840 B), `FETUNE.XM` (frontend), `FESAMPS.SBK`, `FETUNE.SBK`, `VOICES.BLK`, and XA streams in `/DRIVER/XA/` (CUTS, MV1-5, NMAJ). No VAB or SEQ files.
- Same container as D2: 8 XM songs (8 channels) with per-song VAG banks. The D1 exe references `SOUND\MUSIC.BIN` (string in SLUS_008.42.orig).
- D1 song table (xm offset / bank offset / xm length): 0 (68 / 24176 / 24108), 1 (99380 / 130988 / 31608), 2 (213728 / 243288 / 29560), 3 (329692 / 361184 / 31492), 4 (441236 / 469228 / 27992), 5 (549296 / 577288 / 27992), 6 (664044 / 697160 / 33116), 7 (768844 / 807652 / 38808).
- How D1 picks music per city: not in NOTES. The D2 source `#ifndef PSX` block (main.c ~535-553, `gDriver1Music`) gives a D1 mapping used by the D2 PC port: Take a Ride GameLevel 0 = songs 0/1, 1 = 5/6, 2 = 2/7, 3 = 3/4 (mission parity picks the member). Two songs per city, four cities. The LA pair and the D1 CITY index are not verified from the exe. Open.
- Runtime: the recomp runs the PS1 code and emulates the SPU (psxrecomp/runtime spu.h). Music is played by the guest's own driver from MUSIC.BIN, so D2 songs only play if the D1 driver accepts the D2 song/bank data. The layout matches in the tool's view; not tested.

### B3. Conclusion: D2 Chicago music in D1
Plausible path: put D2 songs 2 and 6 into Chicago's slot of D1's MUSIC.BIN (the LA pair, once confirmed), keeping the other six songs. Day and night would use the same two songs, as in Driver 2.
Open risks:
1. MUSIC.BIN has only 8 song slots. Taking LA's pair removes LA's music, but the user wants D1 cities to keep theirs. Keeping it needs more slots (exe change to read an extra index from another file, or a second music file) or a loader change.
2. VAG sample banks must fit D1's SPU sample memory and bank loader. Not tested.
3. The LA-pair mapping in the D1 exe is not verified (needs an exe probe of the music id code).
4. D2 has no separate night track: Chicago 1 and 2 would share songs unless one entry uses song 2 and the other song 6 (a choice for the user).
Effort: extraction and parsing (done, under 1 h); MUSIC.BIN rebuild with the swapped songs (0.5-1 day, bank re-pack check); runtime test on the D1 driver (1-2 days incl. SPU sample-size check). XA streaming is not suitable: D2 music is XM sequences, not XA.

## Open items
- A3: exe variable for Miami 1/2 and what it changes.
- A4: which path/index the second Chicago entry uses (engine decision).
- B2: exact D1 song index used by LA (and each city), from the exe.
- B3: whether the D1 driver plays the D2 song/bank layout unchanged.

## 5th slot arrays (EXP, 2026-10-13, partial: static part done, RAM part blocked)

Method: the SLUS text (disc/SLUS_008.42.orig, text at RAM 0x80010000, file offset 0x800) decoded word by word with the bundled capstone (MIPS32 LE). Driver 1 code uses KUSEG mirror addresses in lui: base 0x800A0018 appears as `lui 0x000A` + lo, so the lui immediate is the high half with bit 31 cleared (same for all bases below).

Static sites (lui + lo, or lo in the load/store offset, within 12 instructions):
- 0x800A0018: 1 site, 8004BBAC (`lw $v1,0x18($a3)`). No CITY load in the 60 instructions before it.
- 0x800A0E20: 27 sites (8001F060 ... 8005F334). Most are plain `addiu rX,rX,0xe20` followed by shifts (sll 1..6 or *3/*5 via addu): generic table or struct access, the CITY index is not visible at most. Sites with a CITY load (`lw ...,0x6834(..)`) in the preceding 60 instructions: 8003A750, 8003ADA0, 80052AD8 (`lw $v0,0xe20($s3)`, shift by 2 after it), 8005A228, 8005A664. Strides seen there: x4 and x2/x5 combinations; not yet decoded per site (needs a read of each window).
- 0x800A531C, 0x800BD97E, 0x800C0014, 0x8009B23C: no lui+lo site found (exact match, also with ori). Either they are reached through a register built with addu (not a constant), or they are data written by the loader. Not resolved.
- Extra: 0x8009B23C is next to DAMAGE (0x8009B220, dt.py), so it may be the player/vehicle block, not a per-city table.

RAM part: NOT done. Only one dump exists: Chicago in the LA slot (CITY 3, in-game, from the build-dev package, saved as scratchpad `ram_chicago_LAslot.bin`, 2 MB). The menu drive to the Take a Ride city list was not reliable on devtest/exp: with the Chicago package the game goes straight into Chicago (no city list); with the package off (orig mode), the title/attract timing was inconsistent and the presses landed on the intro, title and office screens. CITY read back 2, 0, 0 (title values, not a city choice). Miami 1/2, SF, NY dumps and the Day/Night flag diff are therefore open.
Needed to finish: a fixed start (save state or a memcard with the Take a Ride city list reached) on devtest/exp, or a run with the user/QA recipe. Port 4420 PID 37724 is QA-2's game (not touched).

### 5th slot arrays: update (EXP, 2026-10-13, RAM part done with the recipe)
Recipe (from the earlier EXP runs, exp_city.py): triangle, right x5, cross, N downs, cross (city), 3 s, cross (Day/Night screen: Day is default, down = Night), 32 s wait. Package: prepare("exp") WITHOUT start (Chicago package on). City index by downs: Miami 0, SF 1, LA(Chicago) 2, NY 3 (CITY 0, 1, 3, 5). So the list is 4 cities; "Miami 1/2" is the city plus the Day/Night screen, not a separate city row. Dumps: 2 MB RAM at 0x80000000 (scratchpad ram_*.bin): miami_day, miami_day2 (noise baseline), miami_night, sf_day, ny_day, chicago_la (Chicago package, LA slot, downs 2).

Day/Night flag: found. Words 0x801D2DB8 and 0x801D2DC0 are 0 on Day and 1 on Night:
- on the Day/Night screen: Day 0, after down (Night) 1, after up (Day) 0 (dn_A/B/C dumps, same run, only 66 words change between A and B);
- after the load: miami_day 0 / miami_night 1 (both words). Other dumps: sf_day 0, ny_day 0.
- chicago_la shows non-flag values at these addresses (0x326C2431): the Chicago package data seems to overlay this area in the LA slot run. Needs a re-check on a clean Chicago day/night pair before using it as a flag.
Noise: the first whole-RAM diff (miami_day vs day2) gives 2372 changed words, so a diff of loaded runs alone is not usable; the same-run cursor diff was.

Per-city arrays (6 windows of 8 KB each, from the bases; md5 and nonzero counts in scratchpad arrays.py output):
- 0x800A531C: identical for Miami day and night (0 words differ), differs for SF (103), NY (101), Chicago (153). So a per-city table, loaded per level, not changed by Day/Night. Best candidate for the city table.
- 0x800A0018: Miami day vs night differ only at the tail (37 words from 0xA1AA0); SF/NY/Chicago differ throughout (310-538 words). Per-city, with some night-specific tail.
- 0x800A0E20: Miami day/night differ in 51 words (tail); SF 469, NY 784, Chicago 413. Per-city; the night difference is small.
- 0x800BD97E: Miami night 6 words; SF 405, NY 479, Chicago 432. Per-city.
- 0x800C0014: Miami night 47 words; SF 640, NY 718, Chicago 1869. Per-city; Chicago has only 37 nonzero words here (the Chicago run is not comparable at this base).
- 0x8009B23C: dynamic, not a city table: miami_day vs miami_day2 (same state) already differ, and the window changes in every run (865-990 words). Likely the live player/vehicle block next to DAMAGE (0x8009B220).
Length: not inferred. The stride of each table is not decoded yet (the 27 sites of 0x800A0E20 need reading), and the windows above are 8 KB samples, so "is index 5 (NY) valid" is still open: the NY dumps have data past the Miami/SF extents at 0x800A531C and 0x800C0014 (more nonzero words), which suggests NY entries exist there but the entry layout is unknown.

### Day/Night flag and the 0x800A531C writers (update 2, EXP 2026-10-13)

Day/Night flag, confirmed by write trace (not only by diffs):
- Writes to 0x801D2DC0: the pick itself. Miami Night: 0 -> 1 by pc 0x801C2C04 (ra 0x801C2744, menu code) on the cross after down. This is the setter.
- Writes to 0x801D2DB8: a per-frame mirror. pc 0x801C4B60 writes it every frame (old = new), and it follows DC0 one frame later.
- Values: Miami day 0 / night 1 (both words), SF day 0, NY day 0. The Day/Night screen cursor (same run): Day 0, Night 1, back to Day 0.
- Chicago (LA slot, package on): there is NO Day/Night screen. After the city cross the level loads directly (screenshot, and the trace over 0x801D2DB0-0x801D2DD0 has zero writes in the Chicago pick). The Chicago dumps have ASCII-like data at both words (0x326C2431 / 0x326E2434) in both day and night runs. So the Chicago pair cannot be made with the current build: the LA slot has no Night entry yet. Confirm after the 1/2 entries exist.
- Answer to "which of the two": 0x801D2DC0 is the real flag (the setter); 0x801D2DB8 is its per-frame copy. Both are the same in all D1 cities checked (Miami, SF, NY).

0x800A531C (the 8 KB window), writers during the load (Miami, wtrace over 0x800A5DC0-0x800A6700, load frames 7614-7759):
- Two sources, both computed in the exe, none a raw copy of a file:
  1. An exe-static block: 32-byte entries copied from 0x800A6E8C to 0x800A668C (call 0x8002DC70, a2 = 0x1D = 29 entries seen). Content is identical in all six dumps (md5 match), so this part does not depend on the city.
  2. Per-object entries at 0x800A5E3C + index*32, written by 0x8002D17C (213 writes) and the copy at 0x80079F5C (GTE store). The index is a byte (+0xD) of a per-object record, so the content follows the level's object data, not CITY. The function does not load CITY (0x6834) anywhere in the writer.
  3. The trig/angle writer at 0x8002DB00 (lhu from the 4096-entry sine table, sh into 0x800A5E1C..0x800A5E30) runs at load with inputs that depend on the level.
- Stride: 32 bytes per entry (sll 5, and the a2 = 0x1D copy count). Length: at least 29 entries (0x1D).
- Stored content: the nonzero 32-byte blocks (119 stable blocks in the Miami window) are NOT found in d1_MIAMI, d1_FRISCO, d1_NEWYORK, d1_LA or the SLUS (byte search). So the content is computed at load, not stored in the LEV or in a CITY-indexed exe table. The exe part (1) is shared by all cities.
- Answer for the 5th city: no CITY-indexed exe table is involved in this array. A 5th city needs its LEV to supply the same kind of per-object records (indices into the entry block); no new exe table entry is needed for 0x800A531C. Not checked: the exact LEV lump that supplies the object indices (the per-object record is probably in the MAP or PALLET-side lumps); that is the next step if the 5th city's array turns out wrong.
- The other per-city bases (0x800A0018, 0x800A0E20, 0x800BD97E, 0x800C0014) were not traced; they are still open.

Check: original LA (chicago-la OFF in the copy's state.toml, city index 2 downs): NO Day/Night screen after the city pick; the level loads directly (screenshot la_orig_after_city.png, 3 s after cross, same timing where Miami/SF/NY show the screen). So the missing screen is LA's own behaviour in D1, not our Chicago feature.


**Correction (user, 2026-10-13):** original LA in Driver 1 is NIGHT-only (no Day/Night screen because it has no day variant). Our Chicago in LA's slot currently loads D2's DAY level there.

## Take a Ride menu (QA-3, 2026-10-13): map for a 5th city row

Probe: devtest/qa3 (port 4440, own PID, stopped). Read-only; no code or shared files changed.
Exe: SLUS RAM -> file offset = RAM - 0x80010000 + 0x800. Overlay code/data is RAM only (not in SLUS).

| item | address | what it is (verified in this run) |
|---|---|---|
| row table (4 x 16 B) | 0x801CE048 .. 0x801CE087 | per row: word0 = handler address (stored 24-bit, 0x001Cxxxx), word1/word2 = pointers, word3 = bytes [row, row, UP, DOWN] |
| row 0 Miami | handler 0x801C43EC; sw $zero -> CITY at 0x801C442C | CITY 0; neighbours up 3 / down 1 |
| row 1 SF | handler 0x801C44FC; sw 1 -> CITY at 0x801C453C | CITY 1; up 0 / down 2 |
| row 2 LA (Chicago slot) | handler 0x801C4610; sw 3 -> CITY at 0x801C4650 | CITY 3; up 1 / down 3 |
| row 3 NY | handler 0x801C46FC; sw 5 -> CITY at 0x801C473C | CITY 5; up 2 / down 0 (wrap) |
| cursor (row index) | 0x801CE088 (word) | written at pc 0x801C2C04 (ra 0x801C2744), values 0..3 |
| dispatch | 0x801C2C90..0x801C2C9C | sll 4; addu with s2 = 0x801CE048; lw; jalr (handler per row) |
| CITY | 0x80096834 | written only by the row handler constants above (the wtrace showed pc 0x801C473C for NY) |
| names table (SLUS) | 0x80096D64..0x80096D9C, stride 8 | CREDITS(7) TRAIN(6) NEWYORK(5) FLAT(4) LA(3) IVIEW(2) FRISCO(1) MIAMI(0), from 0x80096D98 - 8*i |
| row text | not ASCII anywhere in SLUS or disc | pictures/texture font in FRONTEND overlay (not located) |
| city picture | disc name list has MIAMI.TIM, NY2.TIM (near TANRICO/TCHASE/TTRAIN TIM names) | per-row picture panel, one per row (Miami shown on screen); other row pictures not located |

Findings:
- Row count is not a compare: the wrap is in the neighbour bytes of the table (3 -> 0 and 0 -> 3). The "max row 3" is
  the table's data; there is no "cursor > 3" check in the trace.
- Day/Night (flag 0x801D2DC0 per NOTES): Miami, SF and NY handlers call 0x801C2114 with a1 = 0x801CDFE8 (lui 0x1D + addiu -8216);
  the LA handler (0x801C4610) takes a different path (calls 0x801C11E4 after a state check, 0x800741F0, 0x80079B00, 0x80074158)
  and only reaches 0x801C2114 at its end. So LA's skip is code in the LA handler, not a per-row flag in the table bytes (the bytes do not differ). Not fully decoded.
- The NOTES "flag written at pc 0x801C2C04" is the generic store helper: the same pc writes the cursor (s1 = 0x801CE088).
- Overlay pointers are 24-bit in RAM (0x001C43EC): a RAM scan for 0x801Cxxxx values misses them.

What to patch for a 5th row (CHICAGO, after NY):
1. Table: 16 B more after 0x801CE087, but 0x801CE088 is the cursor, so move the cursor (and check nothing else lives at 0x801CE098).
   Rows 0..3 neighbour bytes must change: NY down = 4, row 4 up = 3 / down = 0; byte0/byte1 = 4.
2. New handler: copy the NY handler (0x801C46FC) to a free overlay range (code space), change its sw constant to the new CITY, and
   set word0 of row 4 to its address (24-bit form). Day/Night: copy the branch the chosen row needs (LA-like = no screen).
3. CITY index 8: the level path table at 0x80086EC0 has 8 entries and CITY 6/7 and a switch with 8 cases; CITY 7 crashed
   (NOTES). An index 8 needs every per-city table extended, not only the menu. Simplest first test: CITY 3 (LA slot = Chicago) stays, a 5th row
   would need a free index; flag this to Infrastructure before patching.
4. Graphics: row text and picture are not located; a 5th row needs a text entry and a picture (FRONTEND TIM), both not found yet.
Open: row text/picture source (FRONTEND.BIN offset), row drawing loop (row count 4 in code), LA handler Day/Night decode.

### Take a Ride menu, part 2 (QA-3, requested by the coordinator)

Probe: devtest/qa3 again (port 4440, own PID 4452, stopped). Read-only.

Correction to the part-1 table: the LA handler is 0x801C4610..0x801C4670 only (sets CITY=3, small state, jr ra; NO call to
0x801C2114). The code at 0x801C4674 is a separate function: it checks the word 0x800967F4 (lw from 0x8009 + 26612) == 19,
then calls 0x801C11E4 / 0x800741F0 / 0x80079B00 / 0x801C2114 / 0x80074158. It is not the table handler for row 2.
- 0x801C11E4 is a level/menu init helper (no CITY read, no row test; calls 0x800747B4, 0x800746F4, 0x80074684, 0x8007457C).
- Decision: the Day/Night screen is opened by the 0x801C2114 calls in the Miami, SF and NY handlers (a1 = 0x801CDFE8). LA's
  handler has no such call, so LA skips the screen by code structure (per-row, not a flag or a CITY compare). The caller that
  shows the Day/Night screen after the handler returns was not decoded.

1. Row drawing and text (labels from the FRONTEND overlay)
- FRONTEND.BIN: ISO LBA 88, size 78600 (raw sector user data at +24 from 2352-byte sectors). Loaded at RAM 0x801C0000:
  file offset = RAM - 0x801C0000 (48-byte samples match at 0x0, 0x400, 0x2000, 0x8000).
- Strings in FRONTEND (file offset = RAM - 0x801C0000): "Take A Ride:" 0x344, "Choose your city:" 0x324,
  row labels New York 0x370, Los Angeles 0x37C, San Francisco 0x388, Miami 0x398; picture names NY2 0x3A0, LA2 0x3A4,
  SF2 0x3A8, MIAMI 0x3AC (used with "%s.TIM" at 0x230); Night 0x3B4, Day 0x3BC.
- Pointer tables in RAM (words): label pointers Miami 0x801CE09C, SF 0x801CE0A0, LA 0x801CE0A4, NY 0x801CE0A8;
  picture-name pointers MIAMI 0x801CE0AC, SF2 0x801CE0B0, LA2 0x801CE0B4, NY2 0x801CE0B8 (stride 4, order of the rows is
  reversed in the picture list). A second stride-16 pointer set at 0x801CE000/10/20/30 has Miami, SF, LA, NY too (role not
  checked). The row table of part 1 (0x801CE048, 16 B, neighbour bytes) is unchanged.
- Picture TIM names are listed in TPDATA.DAT (ISO LBA 17771, size 11904), a name list for the frontend textures.
  The TIM files themselves are not ISO directory entries: they are likely in the FRNT bank file FRNT.B1 (LBA 17368,
  size 229404), unverified. No per-city TIM sizes are available from the directory.
- Frame capture (gpu_frame_capture, frame 19185, menu with Miami highlighted): 62 packets, 51 textured quads.
  Row labels are per-glyph PolyFT4 quads (one glyph = one quad). Attributed func 0x1FC02B80 (no row-level attribution);
  the glyph call sites are in SLUS: Miami row pcs 0x8007AFAC, SF 0x8007AEE0, LA 0x800764B0/0x80074610, NY 0x80075474/0x80079B2C.
  The row loop itself (count 4) was not found: those call sites are per-row draws from one loop, the loop's address not decoded.
- Picture quad: (160,190)-(288,422) 128x232 from texture page 0x001D2D14 region, drawn at pc 0x80075464.

2. Room for a 5th row (screen 320x470)
- Labels: Take A Ride title at y=158; rows at y=218 (Miami), 258 (SF), 298 (LA), 338 (NY): constant step 40 px, glyph height 36.
- A 5th row at y=378 (to 414) fits; x range 13..130 does not overlap the picture panel (x 160..288). It fits without moving the picture.

3. LA path: see the correction above (handler structure, no CITY test, no per-row flag).

### City-list label loop (QA-3, part 3)

Found in FRONTEND.BIN (RAM 0x801C0000 + offset) and confirmed by a write trace in a run (devtest/qa3, port 4440, own PID 9516, stopped):
- Menu init function starts at 0x801C41F0 (sw cursor = 0 at 0x801C420C: the cursor 0x801CE088 is cleared here).
- Row struct base a1 = 0x801CDFE8, stride 16 (struct+8 = label pointer, +12..+14 = bytes '0').
- Title: 0x801C4244 writes 0x001C0344 ("Take A Ride:") to 0x801CDFF0 (struct 0).
- Label loop: 0x801C424C..0x801C426C. a0 = 0..3; source table a2 = lui 0x001D + (-8036) = 0x801CE09C; per row:
  lw v0,0(a2 + 4*a0) (Miami 0x1C0398, SF 0x1C0388, LA 0x1C037C, NY 0x1C0370), stored at struct(a0+1)+8 =
  0x801CE000 + 16*a0 ... (writes observed at 0x801CE000, 0x801CE010, 0x801CE020, 0x801CE030 at pc 0x801C4264).
  Bound: `slti $v0,$a0,4` at 0x801C4268 with bne back to 0x801C424C (4 iterations).
- Second 4-iteration loop: 0x801C4298..0x801C42B4 (`slti` at 0x801C42B0): sb 48 into struct+12..14 for the rows.
- Neighbour bytes of the row table 0x801CE048 are also written here (pc 0x801C4338..0x801C4354, the cursor-row
  table of part 1 is initialised in this function).
- The per-frame DRAW loop (count 4, computing y = 158 + 40*row?) was NOT found: no y writes occur in this init; y is
  probably computed in the draw function that reads the struct list. Still open. The step 40 px from part 2 is observed
  from the glyph quads, not from code.
- Init is called once at menu entry (frame 4631 in this run), not per frame.

## Menu text size and capacity (QA-3, 2026-10-13)

Status: static findings only. No runtime size test was run (time spent on the static trace; see open items).

1. Text size: no scale or font-size field found. Row struct (base 0x801CDFE8, stride 16): +8 label pointer, +12..+14 bytes
   written '0' (0x30) by the second init loop at 0x801C4298..0x801C42B4. Their meaning is not decoded. Glyphs are per-glyph
   PolyFT4 quads drawn from SLUS (call sites 0x8007AFAC, 0x8007AEE0, 0x800764B0, 0x80074610, 0x80075474, 0x80079B2C),
   so the size would sit in those draw routines, not in FRONTEND.BIN. Not found.
2. Row y: no y is written in the init (0x801C41F0..0x801C42B4). Struct-base users in FRONTEND (lines of the disassembly):
   0x801C4218, 0x801C428C, 0x801C4368, 0x801C43B0, 0x801C447C, 0x801C44A0, 0x801C4590, 0x801C45B4, 0x801C46B0,
   0x801C46E0, 0x801C4790, 0x801C47B4, 0x801C4AA8. The per-frame draw loop was not located. Observed rows: 218, 258,
   298, 338 (step 40, glyph height 36); the 5th row at 378 is the plan.
   Capacity estimate (not measured): at the current size and step 40, rows from 218 fit to 454 (6 rows, bottom 470).
   If the title block moves the first row to 178, 7 rows fit (last at 418, bottom 454).
3. Title: 0x801C4244 writes 0x001C0344 ("Take A Ride:") to 0x801CDFF0, i.e. the label pointer of struct 0. Structs 1..4
   are the four city rows (0x801CE000 + 16*row, written by the label loop at 0x801C424C). Renaming the title = changing
   the pointer at 0x801CDFF0 to another string in FRONTEND (e.g. "Choose your city:" at file offset 0x324) or a new string
   in the overlay. Permanent change needs a FRONTEND.BIN patch (the overlay is loaded from the disc image).
Open: the scale field, the per-frame draw loop (y) and a runtime size poke test on port 4440.


## Extra levels: starts, roads, names (QA-2, 13.10., offline; full table devtest/qa2_research/extra_levels.txt)
| level | city op | LEV | ROADS | JUNCTIONS | start (x,z) from MISSION.BLK | name |
|---|---|---|---|---|---|---|
| IVIEW | 2 | LEVELS\IVIEW.LEV (LBA 6058, 917 KB) | 804 | – | -10500,-22144 | not in exe/FRONTEND ("Interview" = working label) |
| FLAT | 4 | LEVELS\FLAT.LEV (LBA 1481, 2.1 MB) | 68 | 180 | none (no 0x22 = 4 mission) | working label "Flat" |
| TRAIN | 6 | LEVELS\TRAIN.LEV (LBA 15072, 842 KB) | 20 | 48 | 11 candidates, e.g. 25227,29933 | "Training" (menu word) |
| CREDITS | 7 | LEVELS\CREDITS.LEV (LBA 1027, 908 KB) | 260 | 664 | 346726,-173362 / 19483,-42820 | "Newtown" (user) |
Starts = the first 0x13 after each 0x22 hit (heuristic). All four LEVs parse; ROADS > 0 on all.

## Extra levels via Take a Ride (EXP, build-test slot package, LA row 2, Day, CHI_START unset)
Two ways: (a) CITY 0x80096834 poked to N right after the city-pick confirm; (b) entry 3 (0x800BE0A4+96, 32 bytes = 4 x (pos,size)) overwritten with entry N (0x800BE0A4+32*N) right after the confirm, CITY left at 3. Per-run files: devtest/_out/b9_city<N>/ and devtest/_out/b9_entry<N>/ (psx_last_run_report.json, run.log); data in devtest/exp_work/b9/.
- IVIEW (2), CITY: loads (1.8 s), start = LA start (376863,164,-217530), drove 2.1 s, y 164 flat, kernel NOT ok, FATAL "unknown dispatch addr=0x000000B0 ra=0x80077AC8" (B0 family).
- IVIEW (2), entry: no load, FATAL "DISPATCH misaligned target 0x00072ACD", kernel ok.
- FLAT (4), CITY: no load, same FATAL B0 at ra 0x80077AC8 during load (kernel not ok).
- FLAT (4), entry: no load in 90 s, no FATAL, kernel ok (hung in load or menu, not diagnosed).
- TRAIN (6), CITY and entry: no load, starvation_watchdog (4.0 s without heartbeat), connection reset.
- CREDITS/Newtown (7), CITY: no load, starvation_watchdog (4.0 s), same as before.
- CREDITS/Newtown (7), entry: no load, DISPATCH FATAL misaligned target 0x00070A92 (kernel ok).
Summary: no extra level drives in Take a Ride with either method. IVIEW loads with CITY but dies on B0 within 2 s; the entry copy gives a misaligned dispatch target. Start position for CITY-IVIEW is LA's start (off-map for IVIEW's own geometry; the car is parked and reports y 164).

## Extra levels: file trace and jump-pointer writer (EXP, b10, build-test, LA row 2, Day)
- .plt table: 0x80086EE0 holds 'LEVELS\MIAMI.plt', 'FRISCO.plt', 'iview.plt', 'LA.plt', 'Flat.plt', 'NEWYORK.plt', 'TRAIN.plt', 'CREDITS.plt' (index 0..7, same order as the .LEV table at 0x80086EC0). The names exist only as strings in SLUS_008.42; no .plt file is on the disc image (/DRIVER/LEVELS has only the 8 .LEV files: CREDITS 1027, FLAT 1481, FRISCO 2511, IVIEW 6058, LA 6506, MIAMI 9254, NEWYORK 11725, TRAIN 15072, LBA in parentheses).
- Sector history (cdrom_sector_history, 400 entries after the confirm, LBA mapped to the LEVELS list above):
  - CITY=2 (IVIEW, loads): IVIEW.LEV 350 sectors + LA.LEV 45. So the CITY route really opens IVIEW.LEV.
  - Entry-3 swap to IVIEW: LA.LEV 115 sectors, no IVIEW.LEV read (the swap does not redirect the LEV read). 281 further reads at LBAs outside the LEVELS list.
  - Entry-3 swap to CREDITS: LA.LEV 96 sectors, no CREDITS.LEV read.
  So the entry-3 copy only changes the level data that is used at load time, while the car is in LA's level; the misaligned targets come from LA data with another level's entry values.
- Writer of the jump pointer: the fatal is raised in func 0x80074404 (generated/SLUS_008.42_full_29.c): it loads a pointer from 0x8008E910 (lui 9 + lw 0xE910), then loads a field at +0x20 and jumps through [+8] with ra 0x80074450. The wtrace on 0x8008E900..0x8008E930 captured only the first 512 writes (cap): all at 0x8008E920..2F from pc 0xBFC02B7C (BIOS-side copy) with ra 0x80074798, and 0x80075D84 / ra 0x80075D68. No write to the pointer word 0x8008E910 was in the captured window, so the writer of the bad target is NOT identified yet (needs a filtered wtrace on 0x8008E910..13 armed before the load, or the post-confirm ring with count above 512).
- Not done: original Training (TRAIN.LEV) and fresh-boot intro (IVIEW) file traces for comparison (menu navigation not scripted).
- Data: devtest/exp_work/b10/{entry2,city2,entry7}.json; reports devtest/_out/b10_<tag>/psx_last_run_report.json.

## Extra levels: CITY route, pre- vs post-confirm (EXP, b13, build-test, slot state "chicago", LA row 2 control OK)
- Control (LA row 2, no poke, slot state "chicago"): loads 0.5 s, kernel ok, drives 15 s, LA.LEV only. The earlier "la" state (Chicago in LA's slot) was not a plain LA control and is not used here.
- CITY poke BEFORE the city-pick confirm: overwritten by the confirm (CITY reads 3 afterwards), LA loads. No effect for 2, 4, 6, 7.
- CITY poke right AFTER the confirm (the working route):
  - IVIEW (2): loads, LEV reads IVIEW.LEV 350 + LA 45 sectors; start (376863,164,-217530) = LA's start; kernel NOT ok after ~1 s, FATAL "unknown dispatch addr=0x000000B0 ra=0x80077AC8" (B0), drive garbage (spool 65209).
  - FLAT (4): not loaded, same B0 FATAL (ra 0x80077AC8) during load.
  - TRAIN (6): not loaded, starvation_watchdog (4.0 s), connection reset.
  - CREDITS (7): this run the poke did not take (CITY 3, LA loaded); earlier (state "la") it gave starvation_watchdog. Not drivable, no traffic check possible.
- Entry-3 swap and the pre-confirm poke both make LA load with a misaligned target (0x72ACD/0x70A92) in the "la" state; the clean control does not do that, so those runs are not evidence on their own.
- Drivability and traffic for FLAT, TRAIN, CREDITS: not reached (no level loads and drives).
- Data: devtest/exp_work/b13 runs (stdout in scratchpad); the b10 files are from the "la" state.

## Original load paths vs Take a Ride (EXP, b15, build-test, clean state "chicago")
Scope: Interview (Undercover > New Game, IVIEW) and Take a Ride Miami (row 0). Training (TRAIN) and Options > Credits (CREDITS) were NOT traced: their menu route is not mapped yet (only the Undercover page is known: New Game, Load Saved Game; Car Chases page: Load Film Replays, Play Chase 1-4).
Writes to 0x80096800..0x80096900 from the last menu confirm to the first LEV sector (wtrace, 512 cap):
| word | Take a Ride Miami (row 0) | Interview (IVIEW) | writer pc (ra) |
|---|---|---|---|
| CITY 0x80096834 | 0 (written 0 at 0x80068A00, no change) | 0 -> 2 | Interview: 0x80024C24 (ra 0x80024C00); Miami: 0x80068A00 (ra 0x80068B50), value 0 |
| 0x80096808 | 0xFFFFFFFF -> 0x78 (pc 0x001C44BC, not a KSEG0 address: overlay/loader code), 0x78 -> 0x78 | -> 0xAE | Interview: 0x80024C0C (ra 0x80024C00) |
| 0x80096854 | 0 (no write) | 0 -> 1 at 0x80024C04 (ra 0x80024C00), 1 -> 0 at 0x80068C38 | Interview 0x80024C04 |
| 0x8009686C | 1 -> 0 at 0x80068C38 (ra 0x80068670) | same | same |
| 0x80096844, 0x80096899, 0x80096898, 0x80096818, 0x80096890, 0x8009687C, 0x80096878, 0x80096850, 0x8009683C | written 0 (no value change) | written 0 (no value change) | 0x80024780, 0x800247F4, 0x800247F8, 0x80024F7C, 0x80026064, 0x800260C8, 0x800260E4, 0x800228C0, 0x80068600 |
| 0x80096858 | 0 | 0 | 0x80068C38 |
Differing words (value): CITY (0 vs 2), 0x80096808 (0x78 vs 0xAE), 0x80096854 (0 vs 1 transient, set in the Interview path only). Writers are the menu/mission code at 0x80024Cxx (interview), the Take a Ride city code at 0x80068Axx (CITY=0 for Miami).
Load result: IVIEW loads (kernel ok) with the car at (-10500, 164, -22144) at the first LEV sector + poll window. Miami read reported (0,0,0): the car was not placed yet when read (first LEV sector at frame 6732), so Miami's start is not measured here.
Caveat: the 0x80096808 writer pc of Miami (0x001C44BC) is outside KSEG0: treat that write as overlay code, not verified.
Next: map the Training and Credits menu routes (page list), then repeat with the same window and a longer post-load read for the start.

## Map table: mission word, CITY, start (EXP, b17, build-test, clean state "chicago")
Read: 0x80096808 3.5 s after the first LEV sector (the LEV named by the sector trace), CITY 0x80096834, car position after placement. Data: devtest/exp_work/b14/map_*.json.
| map (route) | mission 0x80096808 | CITY | start x,y,z | LEV read (sector trace) |
|---|---|---|---|---|
| Miami (Take a Ride row 0) | 0x78 (120) | 0 | 134000, 164, 420739 | MIAMI.LEV |
| SF (Take a Ride row 1) | 0x7A (122) | 1 | -389478, 159, 179363 | FRISCO.LEV |
| LA (Take a Ride row 2) | 0x7C (124) | 3 | 376863, 164, -217530 | LA.LEV |
| NY (Take a Ride row 3) | 0x7D (125) | 5 | -136176, 164, -358832 | NEWYORK.LEV |
| Training (Training > Car park) | 0xAD (173) | 2 | -10500, 163, -22144 | IVIEW.LEV (not TRAIN.LEV) |
| Interview (Undercover > New Game) | 0xAE (174) | 2 | -10500, 164, -22144 | IVIEW.LEV |
| Credits | not reached | - | - | CREDITS.LEV (not in any menu page) |
- Menu map (triangle opens the page strip): 0 Undercover (New Game, Load Saved Game), 1 Car Chases, 2 Training (Car park, Desert), 3 Cheats (not checked), 4 Driving Games (not checked), 5 Take A Ride, 6 Options (Sound, Gameplay, View Controls, Center Screen: no credits), 7 High Scores (View, Load, Save: no credits).
- Credits is not in any of the checked menus. Cheats and Driving Games are not checked yet.
- Training loads IVIEW.LEV, not TRAIN.LEV: the sector trace shows IVIEW with the Interview's start. TRAIN.LEV (LBA 15072) is not read by the Car park route.
- Mission words: 0x78 Miami, 0x7A SF, 0x7C LA, 0x7D NY; 0x79 and 0x7B unused here (possibly FLAT or other entries, not checked). Interview/Training 0xAE/0xAD.
- Disassembly 0x80024BC0..0x80024C40 (dt.py dis): NO mission-to-city table in that range. The Interview block writes literal constants: 0x80024C08 addiu 0xAE -> 0x80096808 (mission), 0x80024C18 addiu 2 -> CITY 0x80096834 (at 0x80024C24), 0x80024C14 addiu 5 -> 0x800967F4, 0x80024C04 addiu 1 -> 0x80096854. The Take a Ride/Miami values come from a different code path (CITY writer 0x80068A00, not here).

## Desert, Credits, and the CITY writer (EXP, b17/b18, build-test, clean state "chicago")
| map (route) | mission 0x80096808 | CITY | start x,y,z | LEV read |
|---|---|---|---|---|
| Training > Desert | 0xAA (170) | 6 | -6913, 209, -103397 | TRAIN.LEV |
| Cheats > CREDITS (first cheat item) | 0x7F (127) | 7 | 19494, 165, 16219 | CREDITS.LEV (Newtown) |
- Training > Car park is IVIEW (0xAD, city 2); Training > Desert is TRAIN (0xAA, city 6). So TRAIN is the Desert route.
- Cheats page: CREDITS, INVINCIBILITY, IMMUNITY, REAR WHEEL, MINI'S, STILTS, NULL, ANTIPODEAN (the CREDITS entry is the first item). Driving Games page: Choose Your Race Types: Pursuit, Getaway, Cross Town Checkpoint, Trail Blazer, Survival, Dart Track (not run). Screens: devtest/exp_work/b14/cheat_dg_sheet.png.
- Mission to CITY: the CITY writer 0x80068A00 (dis 0x800689F8: lw v0,4($t0); sw v0,0x6834) is an opcode case of a mission-script interpreter (the opcode = word at $t0, jump table at 0x800110D8, opcode-0x13). CITY is the operand word of the script stream (t0+4), not a table indexed by the mission number: the mission number selects the script, and that script carries the city operand.

Map table, complete for the menu routes checked:
Miami 0x78/0, SF 0x7A/1, LA 0x7C/3, NY 0x7D/5, Interview 0xAE/2 (IVIEW), Training Car park 0xAD/2 (IVIEW), Training Desert 0xAA/6 (TRAIN), Cheats Credits 0x7F/7 (CREDITS).

## Mission scripts: Interview (0xAE), Desert (0xAA) vs Take a Ride (0x78, 0x7C) (EXP, MISSION.BLK on disc, LBA 63177)
- MISSION.BLK starts with an offset index: word 0 = 0x1F0 (124 words = 124 entries, offsets monotonic, last entry ends near 0x11450). Entry i = bytes [offs[i], offs[i+1]).
- Take a Ride entries decoded (25 words each): entry 0x58 (Miami, mission 0x78) and 0x5C (LA, mission 0x7C) differ only in word 5 (CITY operand 0 vs 3, after the 0x22 CITY opcode), word 12/13 (0x20B70,0x66B83 vs 0x5C01F,0xFFFCAE46: likely start x,z, not yet confirmed), and word 15 (0xC00 vs 0x5). Opcodes seen: 0x13 at word 10, 0x22 CITY, 0x2D, 0x34, 0x32, 0x26, 0x37, 0x0B, 0x0A (not decoded further).
- Interview 0xAE (index 0x8E = 142) and Desert 0xAA (0x8A = 138) are OUTSIDE the 124-entry index, so they are not read with the mission-0x20 rule. Their entries are not located yet (the index lookup for missions >= 0x9C is not known).
- So the timer, objective and fail-condition opcodes of 0xAE/0xAA are NOT identified in this step. Next: find the function that computes the MISSION.BLK entry index (search the generated C for the MISSION.BLK loader near the 0x800503xx boot scan) and decode the opcode operand counts from the interpreter at 0x800687D4 / jump table 0x800110D8.
- Free-drive candidate for Take a Ride: the 0x78/0x7C entries carry no timer/objective opcode in the decoded words (none of the decoded opcodes is a timer). Not confirmed: the Game Over at ~40 s for the Interview/Desert is probably from a mission record outside these 25 words.

## FLAT crash under LA's Take a Ride script (EXP, build-wip, CHI_MENU_PAGES=1, port 4450)
Run: Take a Ride page 1 row Flat (6 downs) -> DISPATCH FATAL misaligned target 0xD33DE3EE, EPC 0x8005134C, frame 7163. Report: devtest/_out/b19_flat/psx_last_run_report.json.
1. Fault location: EPC 0x8005134C is `lbu $v0, 0xd9c($gp)` inside the function starting at 0x800512FC (a wait loop on gp+0xD9C; 0x80051680 sets that flag after its call to 0x8007A53C). The bad target is not from this loop: $ra = 0x80000000, $a0 = 0x01000001. recent_fn (last 16): ... 0x8007F544 trampoline <- 0x80051680 <- 0x8007F2D0 <- 0x800801A4 <- 0x80081560 <- 0x8007A4FC <- 0x8005122C. dispatch_tail ends at 0x000000B0: the trampoline 0x8007F544 is `addiu t2,0,0xB0; jr t2` with t1 = BIOS function number (0x17, 0x5B, 0x0A ... per entry), so the crash path is a BIOS (B0) call through the trampoline, with a garbage jump target.
2. CITY 4 switches: 8-case tables (8004ED88, 800525BC, 80052624) send index 4 to the same label as another index (default or shared); 80050C8C sends every index to 0x50CBC. 6-case switch 80052CF8 (index 4 < 6 is valid) -> 0x53254, the same label as index 2. So no switch sends CITY 4 to a missing entry; CITY 4 takes default paths.
   Light glow table 0x8008AE3C (8 pointers): [0x8ACAC (Miami), 0x8AD1C (SF), 0 (city 2), 0x8AD7C (LA), 0 (FLAT city 4), 0x8ADCC (NY), 0 (city 6), 0 (city 7)]. CITY 4 is NULL, as are 2, 6, 7. IVIEW (city 2) loads with the same NULL, so a NULL here is not by itself fatal.
   Table 0x8008B080 (per-city words): index 4 = 0x60 (valid). Sky 0x800974EC is runtime data, not in the exe image.
3. One-line fix idea (unverified): make FLAT's city-4 entries copies of LA's (city 3) before the level start: CITY 4 -> 3 for the glow pointer (0x8008AE3C[4] = 0x8AD7C) and the sky/light words, or skip the B0 call that the FLAT level makes (its t1 function number is not identified yet).
Bug hunt (paused): route 1 stuck point repeats at (155875,164,38245); screenshot devtest/exp_work/bughunt/r1_stuck_1.png shows the car against a building facade: a real (visible) wall, not an invisible one, so no spot added.

## FLAT crash: B0 calls, wait loop, kernel table (EXP, build-wip, CHI_MENU_PAGES=1)
- Call sites: 0x80077AC0 `jal 0x8007F544` (ra 0x80077AC8, the same ra as the earlier B0 "unknown dispatch" reports) and 0x80077968. The stub at 0x8007F544 is `addiu t2,0,0xB0; jr t2; addiu t1,0,0x17`, so every caller of 0x8007F544 is BIOS B0 function 0x17. The stub at 0x8007F554 is function 0x5B, 0x8007F564 is 0x0A (and so on). 0x80051680 and 0x8007F2D0 have no jal callers (reached by jump or table).
- B0 table entry for fn 0x17 (0x80000874 + 0x17*4) = 0x0F40 in both FLAT and IVIEW runs; no writes to 0x80000870..0x80000900 in either run. So the kernel B0 table is not the source of 0xD33DE3EE.
- Crash registers (report cpu.gpr): t1 = 0x17, t2 = 0xB0, t6 = 0xD33DE3EE, ra = 0x80000000, sp = 0x80094300, gp = 0x80096770, k0 = 0xA000E1FC. The bad value is in t6 at the fault, so it was loaded from memory (a stack or table slot) before the jump. A stack trace over 0x80094000..0x80094400 with 0.25 s polls (512-write ring) did not catch the store (the ring overflows between polls).
- Wait loop 0x800512FC: `lbu v0, 0xd9c(gp)` at 0x8005134C = byte 0x8009750C; `beqz v0, loop`. The byte is set to 1 by 0x80051680 (`sb v0, 0xd9c(gp)` after `jal 0x8007A53C`). It is a "ready" flag written by the level-start init, not traced in IVIEW (the loop was not reached in the IVIEW run). Next: wtrace 0x8009750C on IVIEW to see the setter, then on FLAT.
- Not done: the B0 call list with t1/a0-a2 over the last 200 frames (sreg_trace_* only covers hard-coded focus functions in debug_server.c, and pc_break is DuckStation-only). Needs a runtime hook (Infrastructure).

## FLAT: offline LEV check and wait-byte comparison (EXP)
- Input: FLAT.LEV (2109440 B, disc LBA 1481) and IVIEW.LEV (917504 B, LBA 6058), extracted to the scratch folder (not to work/). levcheck.py: both exit 0, 0 suspicious lines; texture pages FLAT 54, IVIEW 23 (tpages 34816 vs 204800 words, spooled 2052096 vs 577536).
- Lump types (levfile.Lev.parse, D1 format): LOADTIME: FLAT 5 lumps {5, 34, 12, 7, 2}; IVIEW 11 lumps {5, 34, 12, 7, 25, 2, 22 x4, 28}. So FLAT has no type 25, no type 22 (4 entries) and no type 28. INMEM: FLAT 10 {1, 26, 8, 9, 16, 17, 20, 10, 33, 21}; IVIEW 8 {1, 26, 8, 16, 20, 10, 33, 21}: FLAT has extra types 9 and 17.
  This is the first concrete difference: FLAT's loadtime set lacks the lumps IVIEW uses; the level loader may read a missing lump (empty pointer) at the start. Not verified which type 25/22/28 is.
- Wait byte 0x8009750C (wtrace 0x80097500..0x80097520): IVIEW and FLAT do the same protocol: set to 1 by 0x8005127C and 0x80051698 (frame 7362 FLAT, 8107 IVIEW), cleared by 0x80051308 / 0x8005131C in the wait function 0x800512FC. The flag is not the difference; FLAT crashes at frame 7397 after the flag was cleared.
- Status: Flat: open, the lump difference above is the lead; the exact crash path needs a runtime hook (Infrastructure). Low priority map (per coordinator).

## Bug hunt 2 (EXP, b10 Chicago, build-test, state "la", row 4, starts from spots.json)
Routes (60 s or until wreck), faults: fall-through (y drop > 500 from the 8-sample max), lift (y step > 300 in 0.5 s), freeze (VCOUNT stall > 2 s).
- beach_n straight (lake shore, into the water): 107 samples, no fault; ended at y -943 (in the lake).
- underbridge straight (under the bridge, y -1188 held): 107 samples, no fault; covered 460k units north in 53 s (about 4.3k per 0.5 s, consistent with the normal speed scale).
- c20_p2n straight (bridge edge): 107 samples, no fault; the car stayed at about y 164.
- c20_p2n zig (bridge edge, zigzag): wrecked at 37.7 s, no fault before the wreck.
- underbridge zig and beach_n zig: run from the c20 start by mistake (the package was not re-prepared), no fault. Re-run needed for real coverage of those spots.
- Not covered: the west map edge and the L (no coordinates in spots.json); the river bridge (no spot).
Result: no real fault in the 5 valid runs.

## L street and west edge (EXP, b10 Chicago, state "la", row 4)
- Spots added (dt.py addspot, D1 coords as given): l_down_e (23662, 54070) = D2 (-101562, 106946); l_down_w (-37237, 52948) = D2 (-147698, 106096).
- l_down_w straight (westend start, 53 s): no fault; ended at (-37452, 163, 56691): only 3.7k units in 53 s, against 14k for l_down_e straight. Matches the user's "slow" report: the car barely progresses here. Not a fault by the fault list (no fall, lift, freeze), so the cause is not established.
- l_down_e straight (east end, 53 s): no fault; ended at (19591, 164, 68504), 14k units.
- The "l_down_w zig" run started from the e spot by mistake (no re-prepare): no fault, not valid coverage.
- West map edge: not covered. The minimum x of the road extent was not computed (no ROADBOUNDS read); l_down_w is the furthest west point tested, at x -37237.

## l_down_w blocked point and west edge (EXP, follow-up)
- l_down_w straight repeat (53 s): the car again ends blocked at (-37443, 163, 56690), 3.7k units. Screenshot devtest/exp_work/bughunt2/l_down_w_straight_end.png: a grey concrete block/pillar on the left and a storefront facade ahead, exhaust smoke at the front. Visible geometry in front of the car, so a visible obstacle (not conclusively invisible); no spot added.
- West edge: ROADMAP "Map edge (EXP 12.10.)" has no coordinates (only "west the car drops into water, Game Over within ~10 s"). No edge spot added; the minimum road x was not computed.

## FLAT with cars (var_flat_cars.lev): last CD reads before the hang (EXP, build-wip, CHI_MENU_PAGES=1, CHI_FLAT=var_flat_cars.lev)
- Repro: Take a Ride page 1 row Flat, cross; cdrom_sector_history polled every 0.15 s (history: devtest/exp_work/b20/flat_hist_flat.json). Hang: frames 7375 (last read) to 9117, watchdog after 4 s.
- Relocated FLAT.LEV: LBA 345000 (computed: CHICAGO 330000, night 337000, sky 344000 + size rules of build_package.py), 1157 sectors, end 346156. The reads are inside it.
- Last reads (ascending, seq 437-448): LBA 345071 .. 345082 = FLAT file sectors 71..82 = offsets 0x11800..0x29000. The header of var_flat_cars.lev: loadtime 0x800 (75776 B), tpages 0x13000 (225280 B), inmem 0x4A000 (14336 B), spooled 0x4D800 (2052096 B). Sector 71..82 is inside the TEXTURE PAGES section (0x13000..0x4A000), so the loader is streaming texture pages; the read stops one sector after 0x29000 and nothing else is read.
- IVIEW (Undercover > New Game, original IVIEW at LBA 6058, the working load): its reads are in the same kind of tpage section (IVIEW tpages 0x14800..0x32000), but the history captured after the confirm runs descending LBAs 6323..6310 and the level is alive at frame 9882. A direct point-by-point match was not captured (the 40-entry window is only the end of the load).
- Fix idea (unverified, for flatfix.py): the texture page section is shorter than the pages the loader asks for. Check that the texinfo lump (34) of var_flat_cars.lev references only pages inside 225280 bytes; if IVIEW's special pages (63..) point beyond the section end, pad tpages to the max referenced page end or copy IVIEW's page data into the same section.

## Night bug hunt (EXP, b11 night, straight routes, 60 s each, spot starts)
- l_down_e (under the L): no fault; night street with lit windows, tail lamps visible; reads as dark but drivable.
- l_down_w: no fault; blocked at 3.7k units again (visible pillar, as in day).
- beach_n (lake shore): wrecked into the water (drowned at ~36 s); the drowning Game Over is normal. No ground or water gap.
- underbridge (river bridge): no fault; the road is very dark, the car's tail lamps are the main light. Too dark to judge the road edge (candidate for "too dark" report). Sheet: devtest/exp_work/bughunt2/nsheet_underbridge.png.
- No freeze, fall, lift or missing ground in the 4 night routes. Sheets: devtest/exp_work/bughunt2/nsheet_*.png.

## C39: Chicago day shows night lights (EXP, globals diff, build-wip, slot la, pages menu)
Dumps (after load + 10 s): devtest/exp_work/c39/{miday,minight,chday}.json; ranges 0x80096700..0x80097800 and 0x80023600..0x80023700 (1153 words each).
- Night flag 0x80096850: Miami day 0, Miami night 1, Chicago day 0 (correct). Menu day/night flag 0x801D2DC0: 0 / 1 / 0 (correct). So the day/night choice itself is not wrong in Chicago day.
- 0x80023640 (named as the lights flag gp+0xD0): the same word in all three = 0x24020003 (an instruction: addiu v0,zero,3), so it is code, not a flag. Not a suspect.
- CITY 0x80096834: Miami 0 / 0, Chicago day 7 (this package's Chicago CITY value in pages layout).
- Words differing Chicago day vs Miami day: 171. Miami day vs night: 89.
- Suspects (Chicago day equals Miami night and differs from Miami day):
  | address | Miami day | Miami night | Chicago day |
  |---|---|---|---|
  | 0x80097744 | 0x000000EE | 0x00000101 | 0x00000101 |
  | 0x80097448 | 0x00000014 | 0x00000000 | 0x00000000 |
  | 0x8009770C | 0x00000002 | 0x00000000 | 0x00000000 |
- Only 0x80097744 is a non-zero shared value; 0x80097448 and 0x8009770C are zero in night and Chicago day. Next: find the readers of 0x80097744 (wtrace read or code search for lw from 0x80097744) and check whether the light code keys on it.
- Caveat: a shared value can also be a coincidence; the light flags may be read through another table (CITY 7 indexing). Not resolved.

## C39 redo: verified Chicago day dump (EXP, build-wip, slot la, pages menu)
- Chicago day dumped via Take a Ride > Driver 2 cities (7 downs from Miami, cross, first entry, cross for Day). Verified: CITY 0x80096834 = 3, position (169889, 164, 53476) = Chicago's start. Earlier "Chicago day" dump (CITY 7 = Newtown) is void.
- Night flag 0x80096850 and menu flag 0x801D2DC0: Miami day 0, Miami night 1, Chicago day 0 (correct).
- Words differing Chicago day vs Miami day: 175. Of these, Chicago day equals Miami night in 8 words (suspects):
  | address | Miami day | Miami night | Chicago day |
  |---|---|---|---|
  | 0x80096AA4 | 0x0 | 0x4 | 0x4 |
  | 0x800970E8 | 0x0 | 0x1 | 0x1 |
  | 0x80097448 | 0x14 | 0x0 | 0x0 |
  | 0x80097458 | 0x0 | 0x2 | 0x2 |
  | 0x80097460 | 0x0 | 0x2 | 0x2 |
  | 0x80097484 | 0x0 | 0xA0 | 0xA0 |
  | 0x8009770C | 0x2 | 0x0 | 0x0 |
  | 0x80097744 | 0xEE | 0x101 | 0x101 |
- Dump files: devtest/exp_work/c39/{miday,minight,chday_c}.json. Next: find the readers of these 8 words (wtrace on the light/glow code) and check which one is the light state.

## C39 writers of the 8 suspect words (EXP, Chicago day load, wtrace, devtest/exp_work/c39/writers.json)
Each word traced with a 4-byte filter; dumps capped at 64 entries (the frequent writers fill the cap).
| word | writers (pc, ra) seen | last write (old -> new, frame) |
|---|---|---|
| 0x80096AA4 | 0x800466A0 (ra 0x80046674), per frame | 4 -> 4 (10874) |
| 0x800970E8 | 0x80023B2C and 0x80023CE0 (ra 0x800238BC) | 0 -> 1 (10809) |
| 0x80097448 | 0x80043150 (ra 0x800237AC), per frame | 0 -> 0 (10867) |
| 0x80097458 | 0x80046280 (ra 0x8003B0AC), 0x800463A4, 0x800463F8 (ra 0x800463CC) | 2 -> 0 (10790) |
| 0x80097460 | 0x80046284 (ra 0x8003B0AC), 0x800464B8, 0x8004650C | 2 -> 0 (10790) |
| 0x80097484 | 0x80041210 (ra 0x800411C4), per frame | A0 -> A0 (10778) |
| 0x8009770C | 0x80063690 and 0x80063970 (ra 0x80063624), 0x80063CEC (ra 0x80022D3C) | 0 -> 1 (10810) |
| 0x80097744 | 0x80063CF0 (ra 0x80022D3C), once | 0 -> 0x101 (10609, load) |
- 0x80097744 is written once at load time by 0x80063CF0 (ra 0x80022D3C) with 0x101: the setter of the value Miami night also has. Most of the others are per-frame writers that also write a day value in Chicago. Not yet checked which of these is the light state (next: disassemble 0x80063CF0 and 0x80022D3C; check what calls 0x80063624).
