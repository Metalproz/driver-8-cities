# Optimisation project, phase 1: VRAM / RAM audit + ideas (Infrastructure, 2026-10-20, R38)

Data: runtime captures in play (Take a Ride, build-test, var_d2cars16 / Driver 1 Miami, 3 VRAM dumps 6 s apart, RAM, gpu_state),
offline audit of the level files (d1_MIAMI.lev, var_d2cars16_day.lev). Scripts: scratch opt_rt.py / opt_an.py / opt_tex_audit.py.

## 1. VRAM (1024 x 512 x 16 bit)
| region | Miami | Chicago | notes |
|---|---|---|---|
| x 0..511 | 2 framebuffers 512 x 240 (y 0 and 256), draw areas (0,0..511,239) / (0,256..511,495) | same | display 512 x 240, 15 bit |
| rows 240..255 (x 0..511) | 30 of 32 16x16 blocks static, non-zero | same | holds data (something uploaded there); not drawn |
| rows 496..511 (x 0..511) | 20 of 32 blocks zero | same | free strip (512 x 16, never drawn) |
| x 512..959 | 14 texture pages (perm, car, special/player, area slots) | same | zero 16x16 blocks: 2.3 % (Miami) / 4.0 % (Chicago) |
| x 960..1023 (2 page columns) | CLUT column: 267 distinct CLUT positions (rows 16..370); lower half 560 / 1024 slots used, 75 duplicates | 385 distinct (rows 16..415); lower half 763 / 1024, 108 duplicates | 2048 CLUT slots in all |
- **Inside the texture pages** (level data): Miami rect-used 93-98 %, non-zero texels 80-92 %. Chicago permanent pages 65 % rect-used
  (car pages: palettised layout + twins), area pages 86.7 % rect-used and only **68.5 % non-zero**: our per-area overlay pages
  (one page index, different content per area) keep every texture at a fixed spot across all its areas, so a loaded area sees
  its own subset and ~30 % of each area page is empty for it.
- **CLUTs** (level data): Miami 778 stored / 418 distinct (46 % duplicates); Chicago 3921 stored / 688 distinct (82 % duplicates:
  each area copy of a page repeats its CLUTs). In VRAM per loaded set: 75 (Miami) / 108 (Chicago) duplicate CLUT slots.
- **Duplicate textures** (pixels + CLUT): Miami 27.5 % of all stored texels are extra copies (shared textures stored once per area
  on the disc), Chicago 69.8 % (area overlay copies). Permanent + area doubles: Miami 34816 texels, Chicago 14592 (small).
- Framebuffer: no reclaimable columns at 512 wide; 512 x 224 would free 2 x 512 x 16 (visible: 16 fewer lines); single buffer
  = tearing. Both rejected (not "same or better").

## 2. RAM (2 MB main + the runtime's mod memory)
- Free in play (zero 4 KB blocks): Miami 300 KB (largest run 148 KB at 0x801D3000), Chicago 132 KB (56 KB at 0x801EA000).
- Level lumps in RAM: INMEMORY Miami 167 KB / Chicago 337 KB (MODELS 115 / 202, ROADSURF 5 / 60 (D2 surface), OVERLAYMAP 11 / 21,
  SUBDIVISION 7 / 19); LOADTIME (car models etc., load-time only) 100 / 145 KB. Streamed data on the disc: 4.3 MB / 12.4 MB.
- Fixed engine buffers: primitive buffers 2 x 120 KB (0xD8600 / 0xF6600; the LOADTIME buffer reuses them at load), OTs 2 x ~17 KB,
  road map tables (ring of 4 region tables), spool buffer, area model buffer (39 / 49 x 2 KB blocks).
- **Mod memory (not on a real PS1, M8 blocker)**: model table 8 KB (0x9F000000, 2048 entries; all cities since the table move),
  cell object buffer 512 KB (0x9F002000, all cities), plugin blocks: C30 carry buffer 256 KB, car polygon buffer ~40 KB, specials
  ~90 KB, civ zone rows / car tables / LTAB ~10 KB; host-only data (D2 surface table 2.2 MB, car sounds, sky/music assets) is
  outside guest RAM. Non-zero mod memory in play: 208 KB (Miami) / 224 KB (Chicago) of the first 576 KB dumped.

## 3. Ideas (gain, risk, PS1-native, effort)
| # | idea | gain | risk | PS1 | effort |
|---|---|---|---|---|---|
| 1 | **Per-area packing in the converter** (each area's set packed tight; shared textures keep one spot only where areas really overlap; else per-area positions) | Chicago area pages 68 -> ~90 % used: ~+25 % area texture room, halved city textures 654 -> ~300 | low (data only; per-area UV remaps need models per area or shared positions) | yes | 3-4 d |
| 2 | **Shared-CLUT pool**: the page loader de-duplicates CLUTs (hash -> one VRAM slot) | 75-108 slots per set now; with idea 1 / more pages it keeps the CLUT column from overflowing; with the CLUT rows packed, half a page column (64 x 256) could hold textures | medium (CLUT table writer 0x80051ADC area, CLUT row allocator) | yes | 2-3 d |
| 3 | **CLUTs into the never-drawn strip y 496..511** (512 x 16 = 512 CLUT slots) | frees 512 CLUT slots of the column -> with idea 2 ~a quarter page more texture room | low (strip never drawn; check rows 240..255's owner first) | yes | 1-2 d |
| 4 | **Compressed area pages** (Driver 1 compresses only permanent pages; area pages are raw 34 KB each) | area switch reads ~-40 %, loading / stalls shorter, disc image smaller | medium (area loader + decompress time per page ~ms) | yes | 3-4 d |
| 5 | **Stable / shared area pages** (C45 skip, Polish SHAREDPAGES): pages identical in neighbouring areas are not re-uploaded | fewer uploads on area switches (Chicago: 70 % of area texels are repeats) | low-medium (C45 exists, disabled by default) | yes | 1-2 d |
| 6 | Cell object buffer + carry buffer back into 2 MB: measure the real peak of the 512 KB cell buffer, shrink; carry buffer only for the outgoing area's visible models | M8: -300..600 KB of mod memory | medium (overflow = missing objects) | yes (needed for M8) | 3-5 d |
| 7 | Free init-only code / front-end data during play (menus, FMV/loader code) for buffers | ~50-150 KB RAM (to be measured) | medium (must reload for menus) | yes | 3+ d |
| 8 | CD speed: 2x -> faster seeks / read (runtime option) | loading only, host | low | no (host) | 0.5 d |
| 9 | FPS: near subdivision cost (C40), object batch in world_renderer, tile renderer; GPU-side: fewer large affine quads, sort-free far objects | 5-15 % at dense spots (to measure per hot spot) | medium | yes | 2-5 d each |
| - | 4-bit everywhere | none: every page is already 4 bpp (sky/fonts too) | - | - | - |
| - | 512 x 224 display / single buffer / 320 wide | rejected (visible change) | - | - | - |

Recommended order: 1 (biggest visual gain, data only), 3 + 2 (CLUT room, cheap), 5 + 4 (loading), 6 (M8 RAM), then FPS.
