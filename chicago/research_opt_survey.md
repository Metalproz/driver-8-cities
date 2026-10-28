# Optimisation survey: how PS1 games fit more into 1 MB VRAM / 2 MB RAM (EXP, 2026-10-20)
Sources and evidence level: web search gave little per-game detail; items marked [general] are standard PS1 practice I could not
source from the search; [web] = found in the cited source.

## Per game (what the search could confirm)
- Crash Bandicoot (Naughty Dog): 64 KB data pages swapped as Crash moves through a level; levels > 10 MB streamed without hitches;
  the disc layout was controlled so the drive delivers each section ahead of the player (~300 KB/s). [web]
  https://mjtsai.com/blog/2015/06/18/how-crash-bandicoot-was-fit-into-2mb-of-ram ; background-load claims in forum posts are unverified.
- VRAM facts: 1 MB = 1024x512 16-bit; 4-bit textures cost 1/4 of 16-bit, 8-bit 1/2; CLUTs take VRAM too; texture pages are 2 rows x 16
  tiles of 64x256 16-bit (about 256x256 at 4-bit); CLUTs can sit between framebuffers. [web]
  https://zhamul.itch.io/sauna/devlog/936240/using-psxsplashedit-to-craft-a-scene-for-playstation ;
  https://polycount.com/discussion/226167/ ; https://en.wikipedia.org/wiki/PlayStation_technical_specifications
- DuckStation commits: display width aligned to 4 pixels (nocash), DMA accepted only when FIFO empty or a command incomplete [web]
  https://repo.retrodeck.net/Xargon/Duckstation/commits/commit/0c3cf1f5f8dfc26f2b5db2e082fc75a0bcaf2043/src/core/gpu.cpp?page=3
- Ordering-table buffering instead of multiple video buffers (psxdev forum) [web] https://www.psxdev.net/forum/viewtopic.php?p=4206
- Spyro, Gran Turismo, Ridge Racer 4, WipEout 3, MGS, Vagrant Story, Driver 2 PS1: NOT verified (no usable source found). Driver 2:
  OpenDriver2 is the only reference (REDRIVER2 source: 19 texture slots, per-model car pages; see research_vram_layout.md).

## Top 8 for Driver 1's engine, ranked by likely gain
1. Disc-order streaming (Crash) [web]: put each area's pages and models contiguously in the disc layout, ordered by the path a car takes.
   Gain: fewer area-load stalls (C45). We already control LBAs in the converter; the order is the lever.
2. Shared CLUT pools and 4-bit car/area textures [web+general]: one CLUT per car palette set, reused across texture pages.
   Gain: VRAM slots for car twins and the city (today: +1 permanent page per car set, see NOTES 1135).
3. Denser page packing (atlas) [general]: pack small textures into shared 256x256 pages before halving (texrepack already packs;
   the 672 -> 749 downscaled trade-off suggests room). Gain: fewer halved city textures.
4. Dirty-region VRAM uploads [general]: upload only the page slots that change at an area switch (the menu preview and sky already
   overwrite fixed areas). Gain: smaller switch cost, fewer overwrites.
5. LOD for distant geometry and textures [general]: lower-res texture pages for far buildings (C40 goal). Gain: fewer resident
   textures per region.
6. Display width/height tricks (4-pixel alignment, smaller framebuffers) [web]: lower framebuffer VRAM; small gain, small risk.
7. Ordering-table double buffering [web]: FPS only, not memory.
8. Decompress-at-load for geometry [general]: keep RAM small by unpacking per area; costs load time.
