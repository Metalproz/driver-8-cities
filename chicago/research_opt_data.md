# Optimisation project (R38), phase 1: data-side research (Polish, 20.10.)

Measured offline (scratchpad optstats.py) on the disc LEVs (LA, Miami, SF, NY) and Chicago day (var_polish_r35_1_day:
16 areas, budget 16 VRAM page slots - 1 CLUT - 2 special = 13 pages per area incl. permanent).

| level | pages | page fill | exact duplicate textures (texels) | same pixels, other CLUT | trimmable border | transparent texels | CLUTs | spooled data zlib | models zlib |
|---|---|---|---|---|---|---|---|---|---|
| LA | 38 | 86 % | 105472 (1.6 pages) | 0 | 3036 | 20720 | 344 (5 near-dup) | 34 % | 43 % |
| MIAMI | 39 | 90 % | 177664 (2.7 pages) | 1920 | 3021 | 27510 | 411 (1 near-dup) | 40 % | 41 % |
| FRISCO | 42 | 87 % | 152576 (2.3 pages) | 8064 | 3974 | 36349 | 360 (0 near-dup) | 27 % | 44 % |
| NEWYORK | 37 | 92 % | 131840 (2.0 pages) | 0 | 3796 | 30905 | 367 (1 near-dup) | 30 % | 43 % |
| CHICAGO | 12 | 84 % | 95232 (1.5 pages) | 0 | 2717 | 22248 | 106 (0 near-dup) | 50 % | 37 % |

Chicago row: read_pages sees the permanent pages + one copy per page index (areas hold different contents per index),
so its page/duplicate numbers cover part of the data. Chicago extra: 2634 texture placements over 16 areas for ~590 unique D2 textures (each texture in ~4.5 areas on average,
max 213 per area); 654 halvings lose 1.21 M texels (= 18.4 page-equivalents summed over the areas).

## 1. Texture data (VRAM)
| idea | gain | visual risk | effort | D1 maps |
|---|---|---|---|---|
| **Dedup exact duplicates** (identical pixels+CLUT under different names: alias the UVs to one copy) | D1 1.6-2.7 pages per city, Chicago 1.5 pages (95 K texels) per area set | none | small (converter remap; for D1 a setup-time repack of the disc LEV) | yes |
| **Tighter packing** (page fill 84-92 %: skyline/guillotine packer with 90° rotation, sort by height) | ~8-14 % of a page set = 1-2 pages per area (Chicago: ~25 fewer halvings per area) | none (rotation = UV order only) | medium (texrepack packer + rotated UVs in remap_polys / SUBDIVISION) | yes (repack) |
| Trim transparent borders | 2.7-4 K texels: negligible | none | small | - |
| Palette variants (same pixels, other CLUT) share pixels | D1 0-8 K texels; Chicago 0 | none | small | marginal |
| UV mirroring/tiling reuse (mirror-duplicates) | ~0 (only 768 texels found, Miami) | - | - | no |
| CLUT merging / k-means shared palettes | CLUTs live in their own slot (1 of 16); near-duplicate CLUTs are rare (0-5). Saving only matters if CLUT rows run out: no VRAM page gain | low-medium (colour shift) | medium | no |
| 4-bit vs 8-bit | all world textures are already 4-bit; 8-bit would double VRAM | - | - | - |
| **Chicago: share pages between neighbouring areas** (textures used in many areas into permanent/shared pages; corr5 + TEX_PROTECT experience: fewer, larger areas cost resolution, smaller areas cost switches) | the 2634 placements hold each texture 4.5x: a "shared core" of the ~120 most-used textures as permanent pages frees area slots for the rest (estimate 1-2 pages per area) | none | medium (texrepack grouping; already have the area/near data) | n/a (D1 already does this by design) |

## 2. Level data in RAM / loading
| idea | gain | risk | effort | D1 maps |
|---|---|---|---|---|
| **Compress spooled region data** (LZ/RLE per region block, decoded at spool time) | spooled data packs to 27-40 % (D1) / 50 % (Chicago, more raw texture pages) with zlib; a PS1-cheap LZ (LZ4/LZSS) gets ~40-55 %: CD reads per area switch roughly halved = shorter LOADING stalls | none visually; CPU decode time on PS1 (LZSS ~1-2 MB/s on R3000) must fit the spool window | large (engine: spool loader decode step, PS1-native; converter writes compressed blocks) | yes (repack D1 LEVs at setup) |
| Models: duplicate model data | ≤ 4 KB per city: negligible | - | - | - |
| Models lump compression (in-memory models packs to 37-44 %) | RAM only if decompressed into the same budget: no RAM gain unless models stay compressed (not practical) ; CD load time of the in-memory section ~-55 % | none | medium (loader) | yes |
| ROADSURF / road map | Chicago ROADSURF 61 KB (6-16 % compressed); D1 5-8 KB. Chicago's own surfaces could be merged further (surface merge tolerance) | low | small | no |
| PVS | already Driver 2's masks in D1's window (C40); 32 KB per barrel fixed | - | - | - |
| Quantisation of cell objects / vertices | object records are 16 B (x,y,z i32): packing to 12 B saves ~25 % of cell data but needs an engine reader change | none | large (engine) | yes |

## 3. Chicago: more textures at full resolution (converter-only)
1. Exact-duplicate aliasing (1.5 pages).  2. Better packer with rotation (~1-2 pages per area).
3. Shared core pages for the most-used textures.  4. Keep C7's height rule and TEX_PROTECT (landmarks last).
Together roughly 3-4 pages per area (estimate, not yet measured by a build) = most of the 654 halvings (≈ 18 page-equivalents summed over 16 areas, ~1.2 per area) could be avoided.
5. Smaller areas only help if area switches stay cheap: with spool compression (2.) more, smaller areas become affordable.

## Recommended order
Data-only first: (a) dedup aliasing, (b) rotation packer, (c) shared core pages (Chicago, then D1 repack at setup);
engine later: (d) LZ-compressed spool blocks (loading), (e) object record packing (RAM).
