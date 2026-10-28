# Optimisation project: techniques from the reference games (Infrastructure, 2026-10-20, R39)

Method: the boot executables of the user's discs (Crash Bandicoot SCUS_949.00, WipEout SCUS_943.01, R4 SLUS_007.97,
Gran Turismo SCUS_941.94 + GTMAIN.EXE, Spyro: Year of the Dragon SCUS_944.67) were imported into separate temporary Ghidra
projects (PSX loader, PsyQ library names) outside our project and decompiled; the projects were deleted afterwards.
Only techniques and numbers are recorded here; no code or data of those games is in our project.

## 1. Crash Bandicoot: NSF / NSD paging (verified in code)
- **Pages**: an NSF file is a sequence of 64 KB pages; the NSD file is the index (entry id -> page). Load names are built as
  `\S%X\S%07X.NSD` / `.NSF` (0x800128A4).
- **RAM page pool**: at init the engine tries to allocate 22 (0x16) page frames of 64 KB (1.4 MB) and steps down until the
  allocation succeeds ("Inited and Allocated %d pages"); each frame has an 11-word descriptor (state, page id, ref count,
  last-use stamp).
- **Eviction**: a free frame (state 1) first; otherwise the run of frames with the lowest summed "age" among frames that are
  loaded but not referenced (state 0x14/0x15, ref count 0); runs of several contiguous frames serve multi-page entries
  (0x800141F4). Frames in use are pinned by a reference count. => LRU with pinning.
- **Handles, not pointers**: entries are referenced by 32-bit ids (odd = not resolved yet); a lookup resolves an id to the
  page lazily (0x80015034 / 0x80015978), so data can move or be evicted without dangling pointers.
- **Streaming during play**: pages are requested as the level (zone) progresses; the current zone lists the pages it needs.
- **Textures**: a texture page is a whole 64 KB page uploaded with ONE LoadImage as a 256 x 128 (16-bit) VRAM block into one of
  16 VRAM slots laid out as a 4 x 4 grid (x = (slot % 4) * 256, y = (slot / 4) * 128; 0x80012F10). VRAM slot choice
  (0x8001439C): a free slot, else an unused one, else a slot whose page is not in the current zone's texture list. The RAM
  frame is released after the upload. Sound pages are paged into SPU RAM the same way (8 x 64 KB).

## 2. WipEout: .CMP and VRAM placement (verified in code)
- **CMP** = file count, sizes, then one LZSS stream (0x80046B9C): bit 1 = literal (8 bits), bit 0 = 13-bit absolute position in
  an 8 KB ring buffer (0 = end) + 4-bit length (+2: 2..17 bytes); bits are read one at a time.
- **Numbers** (12 largest CMPs on the disc, decoded locally): 1154 KB -> 1705 KB (ratio 0.68; 4-bit TIM data), average match
  4-5 bytes; cost model of the shipped bitwise loop ~46 cycles per output byte = **~1.4 ms per KB, ~720 KB/s** on the 33.9 MHz
  R3000, i.e. faster than a 2x CD (300 KB/s): decompression never becomes the bottleneck.
- **VRAM**: `LoadTexture` auto-places 4-bit TIMs with a bump allocator: pixels in fixed 32 x 32-texel cells (8 VRAM px wide x
  32 rows, filled down the column, then the next column) and CLUTs in a strip at x 320..383 (16 px per CLUT, next row when
  full) next to its 320-wide framebuffers; 8-bit textures must be pre-placed. Track textures come from one track.cmp.

## 3. Ridge Racer Type 4 / Gran Turismo: VRAM allocation
- **R4** (verified): static slots. Each car gets a whole 64 x 256 VRAM page at x = 0x180 + 0x40 * slot (0x800135B4),
  loaded through a small asynchronous state machine (CD read -> upload -> idle) while the game runs; overlays have fixed
  rects (0x340,0 etc.); per-object CLUT rows at y 64, 16 px per slot (0x8001E84C). No CLUT sharing logic found: CLUTs live
  with their object's slot and are replaced with it.
- **Gran Turismo**: the boot exe is a loader and GTMAIN.EXE's code is reached through tables (only 154 functions found
  statically); no conclusion on its allocator from this pass.

## 4. Spyro: Year of the Dragon
- **Streaming** (verified): its own CD layer (no libcd CdRead) with an asynchronous request state machine (0x8004FA24) and a
  "preseek" (0x80057154: during pauses / idle it seeks the head to the next needed sector so the next read starts without a
  seek). Level data is loaded whole at the level entry (the fly-in screen); in play the stream carries speech / music.
- **Far LOD** (community-documented, not re-derived in this pass): each level part has a low-detail mesh (few polygons, vertex
  colours) for distance and the textured high-detail mesh near the camera; far terrain needs no textures at all.

## 5. What this means for our steps
| step | technique | suggestion for Driver 1 / Chicago |
|---|---|---|
| S2 CLUT pool | R4 / WipEout keep CLUTs in fixed per-slot rows; Crash bundles CLUTs inside its 64 KB texture pages | a **hash-deduplicated CLUT pool** per loaded set (our CLUT data is 82 % duplicates) plus WipEout-style CLUT rows in the never-drawn strip y 496..511 (512 slots); the page loader writes the CLUT table from the pool; no engine re-layout |
| S3 compressed area streaming | WipEout LZSS (0.68, 720 KB/s), Crash 64 KB pages, Spyro preseek | measured on our area pages: LZSS 0.64, **Driver 1's own page codec 0.68** (already in the exe for permanent pages) -> compress area pages with D1's codec, decompress in the loader: -32 % area texture reads (Chicago: 4.6 MB raw area pages), no new decompressor; plus a preseek of the next area's sectors while driving (Spyro) |
| S4 2 MB | Crash: fixed pool of 64 KB frames, LRU + pinning, handles instead of pointers; texture pages freed after upload | replace the 512 KB cell buffer in mod memory with a **frame pool of spool-sized blocks** in main RAM (LRU over regions with pinning for the regions around the camera), the C30 carry buffer becomes "keep the outgoing area's pages pinned until the new area is resident" instead of a copy; release texture staging right after the upload |
| VRAM (S1 / later) | Crash's 4 x 4 grid of 256 x 128 slots, R4 per-object pages | our area pages are 256 x 256 (4-bit, 64 x 256 VRAM): a **half-page granularity** (64 x 128 VRAM) for area textures would let small areas use half pages and pack better; evict by "not in the current area list" like Crash |
| FPS / far detail | Spyro far meshes without textures | untextured far LOD for big buildings (vertex colours) instead of textured low models: fewer texture pages needed for the far city, cheaper drawing |
