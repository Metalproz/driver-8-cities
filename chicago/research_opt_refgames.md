# Optimisation project: how other PS1 games manage memory (Polish, 20.10.)

Offline statistics only, read from the user's own discs (D:/recomps/reference games) with psxiso. Nothing from these
games is copied into the project; only counts and ratios. Scripts: scratchpad refgames.py, refstruct.py.
"zlib" = zlib -6 ratio of a file's first MB: ~0.85-1.0 means the data is already compressed, 0.3-0.5 means it is
stored raw.

## What the discs contain

| game | layout | textures found as TIMs | compression |
|---|---|---|---|
| Crash Bandicoot | 44 NSF level files (2.1-9.6 MB) + 44 small NSD indexes (2-3 KB) + ZBSPTREE.WAD (320 MB, zlib 1.0 = already packed). NSF = a chain of 64 KB pages ("chunks", magic 0x1234 raw / 0x1235 compressed); NSD = the per-level index of every entry -> page, so the engine pages entries in and out of a fixed pool of 64 KB slots while the level plays | none as TIM (textures are page-sized 64 KB chunks uploaded whole to VRAM) | NSF zlib 0.85-0.89: most pages are LZ-compressed, decoded when a page is loaded |
| Spyro: Year of the Dragon | one WAD.WAD (166 MB) with an offset/size table; first 60 entries all 2048-aligned, 8 KB-3 MB each (a level = a few sub-lumps: geometry, textures, objects) | none as TIM (raw VRAM blocks inside the sub-lumps) | WAD zlib 0.47: stored raw; speed from one sequential read per level |
| Gran Turismo | archives COURSE.DAT (24 MB), CAR.DAT (16 MB), STREAM.DAT (237 MB), MENU_IMG.ARC; header magic + entry table, 2048-aligned entries | none as TIM | COURSE/CAR/STREAM zlib 0.76-0.88: packed (own LZ), decoded at load |
| Ridge Racer Type 4 | one R4.BIN (52 MB): a sector-index table (934 entries, values = sector offsets) + R4.STR video | **2653 TIMs, all 4-bit with a 16x1 CLUT** (5.8 M pixels) | R4.BIN zlib 0.44: raw TIMs |
| Metal Gear Solid | STAGE.DIR (72 MB): a directory of named stages ("abst", "d00a" ...) with sector offsets; DEMO/VOX/FACE/BRF .DAT | 2 small 4-bit TIMs (the rest in own formats) | STAGE.DIR zlib 0.53 (partly packed); FACE 0.46 |
| WipEout | 517 small files, 15 tracks each with TRACK/SCENE/SKY/LIBRARY .CMP + .PRM/.TRV/.TRF/.TRS | 98 TIMs: 55 16-bit (menus/backgrounds, 4.3 M px), 39 4-bit, 4 8-bit | **.CMP = count + sizes + LZ-compressed TIMs: 0.385 on average**, decompressed at track load straight into VRAM; geometry .PRM raw (zlib 0.33-0.46) |

## Techniques and what they mean for Driver 1

| technique (who) | numbers seen | for us | gain | PS1 feasibility | plan step |
|---|---|---|---|---|---|
| **LZ-compressed texture bundles decoded at load** (WipEout .CMP, Crash 0x1235 pages, GT archives) | textures to ~38 % (WipEout) | compress area texture pages + region data in the LEV; decode at spool time | CD reads per area switch -40..-60 % (our spooled data packs to 27-50 %, research_opt_data.md) | yes: all three decode on a PS1 (LZSS/LZ77, a few hundred KB/s-1 MB/s) | **S3** (confirms it) |
| **Fixed pool of equal-size pages + a per-level index** (Crash NSF/NSD) | 64 KB pages; index 2-3 KB per level | D1 already streams fixed 2048-sector region blocks; the lesson is the index: list which pages an area needs and keep shared pages resident (= our "stable shared area pages") instead of re-loading them per area | fewer re-loads at switches; D1 C45 skip is the same idea | yes (D1 does this partly) | **S3** (shared area pages) |
| **All world textures 4-bit, one 16-entry CLUT each** (R4: 2653/2653; WipEout tracks) | 100 % 4-bit in R4 | D1 already 4-bit; the win is CLUT handling: many small CLUTs in a dedicated strip | supports a shared CLUT pool / free rows | yes | **S2** |
| **One sequential read per level, sector-aligned sub-lumps** (Spyro WAD, R4.BIN, MGS STAGE.DIR, GT archives: 2048-aligned) | Spyro 60/60 aligned | keep area data contiguous and in disc order of travel (neighbouring areas adjacent on disc) to cut seeks | seek time per switch (largest part of a CD load on real hardware) | yes (converter only: order of area blocks in the LEV) | **S1/S3** (converter, small) |
| Shared vs per-level texture sets (WipEout LIBRARY.CMP per track; Crash shared pages) | per-track library + scene + sky sets | = our "shared core pages" for Chicago | 1-2 pages per area (research_opt_data.md) | yes | **S1** |
| 16-bit full-screen images only for menus (WipEout, GT MENU_IMG) | 55 16-bit TIMs, all menu art | keep in-game 4-bit; the frontend may use 16-bit freely (not loaded in game) | - | - | - |
| Streams for video/voice (R4.STR, SPEECH.STR, VOX.DAT) | 47-460 MB | not a memory topic for us (music/voice already streamed by D1) | - | - | - |

## Ranking for the S1-S5 plan
1. **S3 LZ-compressed area streaming**: the clearest common pattern (WipEout, Crash, GT); our data compresses 2-3.7x.
2. **S1 shared core pages + area data in travel order on disc**: Crash's resident shared pages and Spyro/R4 contiguous
   sector-aligned lumps; converter-only.
3. **S2 CLUT strip / shared CLUT pool**: R4 shows the "4-bit + many 16-entry CLUTs" model at scale (2653 CLUTs).
4. S4 (RAM buffers) and S5 (FPS) get no specific new technique from these discs (their code is not analysed here).
