# City preview pictures for the Take a Ride selector (Design, 2026-10-14)

Chicago currently shows LA's picture (LA2). This folder holds a Chicago preview in Driver 1's own format and
style, plus first drafts for Havana / Las Vegas / Rio. Generator: `make_previews.py` (sources in
`chicago/work/design_src/`, ripped game data, not in git). Outputs in `out/`:

| file | what |
|---|---|
| `CHICAGO.png`, `CHICAGO_3x.png` | the picture (RGBA, index 0 transparent) |
| `CHICAGO.4bit` | 128 x 228 px (LA2 quad height, Infrastructure 14.10.), 4-bit, two pixels per byte (low nibble = left pixel), 14592 bytes: the VRAM half-page block |
| `CHICAGO.clut` | 16 colours, 15-bit PSX BGR (`<H` each), 32 bytes: the FECLUT entry |
| `mockup_chicago.png` | pasted into the page-2 menu screenshot at the picture quad (160,190) |
| `all_3x.png`, `HAVANA/VEGAS/RIO.png` | the four D2 cities side by side (the three drafts use D2's own low-res city photos; see plan) |

## Driver 1's preview picture format (found 14.10., disc DRIVER/FRNT)
- `FRNT.B1` / `.B2` / `.B3`: banks of raw 4-bit 256x256 texture pages (header = u32 offsets per page,
  0xFFFFFFFF terminator; B1/B2 7 pages, B3 5 pages = 229404 / 163864 bytes).
- `TPDATA.DAT`: 47 entries (36 bytes: name[16] `NAME.TIM`, u32 index, x, y, w, h in VRAM halfwords; a 4-bit
  picture is 4 px per halfword). City pictures: LA2 index 0x11 (x 0, y 0, w 32, h 228), SF2 0x21 (x 32: right
  half, h 228), MIAMI 0x19 (x 32, h 232), NY2 0x1a (x 0, h 232). So a picture = 128 px wide, 228-232 tall,
  one half of a page: LA2+SF2 share B1 page 3, NY2+MIAMI share B1 page 5.
- `FECLUT.CLT`: u32 count (47) + 47 x 32-byte 16-colour CLUTs, indexed by the TPDATA index (0-based).
- FRONTEND.BIN draws the row's picture as one 128x232 quad at (160,190)-(288,422) (QA-3, research_day_music.md);
  the picture-name pointers (MIAMI/SF2/LA2/NY2, used with "%s.TIM") sit at 0x801CE0AC..B8; the plugin's
  Chicago row currently writes LA's picture word (0x801CDFC0 = 0x00C80148) in apply_first_row.
- Style of the four originals: posterised black-and-white photo collage (11 greys, no dither), gold frame
  (two golds 216/160/8 and 208/152/0, 4 px, rounded corners), one landmark breaking the frame (Liberty's crown,
  Miami's palm, LA's star badge), Miami in sepia. Index 0 = transparent, so the frame's outside shows the menu.

## The Chicago picture
Top: Driver 2's own Chicago skyline from its sky panorama (SKY0.RAW, Sears Tower + Hancock), the tower tops
breaking the frame like NY's Liberty. Bottom: a downtown street of the converted city (authentic D2 Chicago
geometry and textures, probe screenshot) with a car, like Miami's picture. Same 16-colour scheme as LA2/SF2
(11 greys + 2 golds + brown + gold highlight). It is deliberately black-and-white: the D1 pictures are, and
colour would single Chicago out on page 2.

## Insertion (Infrastructure; no engine code needed in principle)
1. Append the 14848-byte block as a new half page: FRNT.B1 page 4 left half has free rows (the Training figure
   uses ~37 % of the half) but not a clean 232-row strip; the clean way is an **8th page appended to FRNT.B1**
   (header: add one offset, file +32768 bytes; the file is a relocated disc_user file like chicago.lev, directory
   record patched like SKY.BIN) with CHICAGO at x 0 and room for HAVANA at x 32 (page 9 for VEGAS/RIO).
2. TPDATA.DAT: add an entry `CHICAGO.TIM`, index 47, x 0, y 0, w 32, h 232 (and FECLUT count 47 -> 48 with
   `CHICAGO.clut` appended). If the loader keys the page by entry order rather than the index, Infrastructure
   checks how TPDATA index -> page/x is resolved (the TIM loader in FRONTEND.BIN that reads "%s.TIM").
3. FRONTEND: a 5th picture name "CHICAGO" + its pointer; the plugin's Chicago row sets the picture word to
   the new page/CLUT instead of LA's 0x00C80148 (apply_first_row and the row highlight handler).
   Simplest runtime alternative if the loader is awkward: the plugin uploads the 4-bit block + CLUT straight into
   LA2's VRAM slot while page 2 is shown and restores LA2 on page 1 (no file changes; needs a VRAM write path).
4. Mod-memory / PS1 path: the data is 14.9 KB + 32 B on disc, nothing in RAM: fine for Milestone 8.

## Plan for Havana / Las Vegas / Rio
- Same pipeline per city; the drafts in `out/` use D2's menu photos (CITY.RAW_1..3, 256x219 red dither), which
  are too low-res: usable only as a placeholder behind the greyed rows.
- Final pictures once each city is converted: top = that city's D2 sky panorama landmark band (SKY1 Havana:
  Capitolio/Malecon skyline, SKY2 Las Vegas: the Strip at dusk, SKY3 Rio: Sugarloaf/Corcovado), bottom = a street
  screenshot of the converted city with a D2 car of that city; breakout motif: Havana = a palm/Capitolio dome,
  Vegas = the "Welcome to Fabulous Las Vegas" sign top (D2's own photo has it), Rio = Christ the Redeemer.
  Las Vegas is the one that wants a night version (D2's Vegas is at its best at night); D1's pictures have no
  day/night variants, so one picture per city.
- Greyed rows: the engine draws the highlighted row's picture only, so greyed cities need no picture until they
  become selectable.
