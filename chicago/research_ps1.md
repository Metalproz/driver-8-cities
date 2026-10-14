# Milestone 8 feasibility: real PS1 budgets (EXP, 2026-10-14)
Sources: LEV headers (levfile, LUMP header words 1,3,5,7 = loadtime, tpages, inmem, spooled sizes) of work/d1_*.lev and work/var_roads_b14_day.lev; ROADMAP C44/C48 lines; NOTES host-only table, VRAM and texture-page notes; disc/disc1.bin size. Values in bytes unless noted. "Est." = my estimate, not measured on hardware.

## 1. Per city (LEV size and parts loaded at once)
| level | file size | LOADTIME | TPAGES section | INMEM | SPOOLED (streamed) |
|---|---|---|---|---|---|
| LA | 5,627,904 | 92,160 | 372,736 | 165,888 | 4,995,072 |
| Miami | 5,060,608 | 110,592 | 401,408 | 176,128 | 4,370,432 |
| New York | 6,854,656 | 100,352 | 485,376 | 243,712 | 6,023,168 |
| Frisco (SF) | 7,264,256 | 88,064 | 440,320 | 231,424 | 6,502,400 |
| Interview (IVIEW) | 917,504 | 81,920 | 204,800 | 51,200 | 577,536 |
| Flat | 2,109,440 | 6,144 | 34,816 | 14,336 | 2,052,096 |
| Chicago b14 day | 14,438,400 | 86,016 | 294,912 | 323,584 | 13,731,840 |
- Loaded at once (LOADTIME + INMEM): 140-430 KB per city (est. the same order on hardware, with the TPAGES section streamed into VRAM in pieces). The spooled part is the streaming data; for Chicago it is 13.7 MB per day level (est. a per-area window, not the whole file).
- Chicago night (b11 night) adds a second 15 MB file on disc (chosen by the day/night pick).

## 2. RAM (2 MB main)
- Main buffers: level heap (headroom C44: 48-105 KB free, ROADMAP line 381; C48 note: ~122 KB heap free, hard limit 422 roads, ROADMAP line 205), spool buffers (fixed sizes; PVS barrels 32768 each per C44), kernel/exe data.
- Mod memory 0x9F000000.. (Expansion 1, NOT real PS1 RAM): model table 2048 x 4 = 8 KB, cell object buffer 512 KB, sea level / Chicago flag, menu block, FPS1/STL1 blocks. On hardware this must go into main RAM: the 512 KB cell buffer alone is about a quarter of the 2 MB (est.: must be sized to the level, and cannot fit the free heap at 48-122 KB as it is).
- Heap shift risk (C44): larger barrel sizes moved the heap by 57 KB and corrupted VRAM at fps_drop_2 — the RAM budget is already tight.

## 3. VRAM (1 MB)
- 16 page slots at x 512-1023 (2 rows), slot-to-page 0x800BE4F8; area pages load slot 14 -> 5 (NOTES).
- Car textures must sit on pages >= 5 (LA 5/6, Miami 3/4, D2 50/58/65 per polish_cars.fixed_pages). One region needs 169 textures; CHI_AREA_TEX < ~170 fails (NOTES).
- TPAGES section sizes above are the texture data per city (LA 372 KB, NY 485 KB, Chicago 295 KB). Whether all of them fit VRAM at once is not measured; the game streams per area (est.).

## 4. CD capacity
- disc/disc1.bin: 747,030,480 bytes raw = 317,617 sectors of 2352 bytes = about 650 MB of 2048-byte user data, i.e. a full 650 MB CD-ROM. The converter already places new files past the disc end (EXTENSION_LBA 320000, CHICAGO_LBA 330000).
- The 8 cities' LEVs: the six D1 LEVs above plus TRAIN (841,728) and CREDITS (929,792) = about 30 MB; Chicago day + night = about 29.6 MB. Total LEV data about 60 MB, est. 2x the original LEV set. A real disc would need either a second disc / a larger medium (not PS1 CD-ROM), or night and day sharing data, or compression. Estimate only; not measured.

## 5. Host-only parts (from NOTES) with estimated effort
| part | PS1 path (NOTES) | effort (est.) |
|---|---|---|
| mod memory 0x9F... (model table, 512 KB cell buffer, flags, menu block, FPS/STL blocks) | main RAM: model table in freed exe/heap, cell buffer sized per level, code cave for small blocks | high (RAM budget) |
| model slots past 800 (2048) | converter keeps <= 800 models, or table in main RAM | medium |
| plugin logic (driver_chicago.c: slot and level-table entry 3 swap, start move, menu pages/rows, Day/Night remap, CITY-opcode switch, glow/day/sky/minimap switches, sea level, ROADSURF selection, area guard, C33 hook) | guest MIPS in the exe (patch sites already known) | high (many patches) |
| runtime changes (disc overlays past the image end, CD DMA into mod memory, save states, write guard, watchdog fix) | DMA/overlays disappear with a real image; save states/guards dev-only | medium (dev-only parts can be dropped) |
| files past the disc end (chicago.lev, chicago_night.lev, SKY.BIN, directory-record patches, FRONTEND.BIN patches) | new ISO/BIN with the files in the file system | medium (but the CD is full: see 4) |
| plugin-only measurement (FPS1/STL1, dev mode) | dev-only | none (drop) |
| converter limits checked on host (texture pages, spool sizes, PVS 32768) | already PS1 limits | low (keep) |

## Open for milestone 8
- Real CD capacity for 8 cities (section 4) is the biggest unknown; night and day duplicates cost about 15 MB each.
- RAM: the mod-memory blocks must move into main RAM (section 2) before any hardware test.
- CPU: FPS on hardware = guest frames; C40 (Chicago FPS) counts.
