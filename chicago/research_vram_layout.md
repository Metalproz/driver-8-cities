# VRAM layout: D2 vs D1 for D2 cities (EXP, 2026-10-20, offline)

## 1. D2 layout (REDRIVER2 Game/C texture.c, tile.c, cars.c)
- Texture slots: tpageslots[19], slot_tpagepos[19] (texture.c 99-106); update_slotinfo(tpage, slot, pos) binds a page to a slot (383).
- Permanent pages: LoadPermanentTPagesFromTIM loads every bound slot (texture.c 435-466); LoadPermanentTPages (475) reads the level's permanent list.
- Car textures: cars.c picks the page by texture_pages[texture_set] | 0x20 (cars.c 568); per resident car model the page set comes from the car's texture_set (1110-1172), so each car model has its own page(s) in a slot (no shared car page table).
- Area textures: streamed per area into the free slots; tile.c draws terrain tiles with the page of the cell (no per-tile page table).
- D2 PC texture map: 19 slots (vs D1's 15 usable + 1). Framebuffer and sky/menu pages: not traced in this round.

## 2. Our Chicago map on D1's layout (NOTES 113, 162-164, 1048-1058, 1135)
| page (VRAM y) | content | source |
|---|---|---|
| 0-4 | D1 city/area pages (area slots, not permanent) | D1 LoadInAreaTSets |
| 5-8 | car pages: traffic and cop (permanent, D2 civ = 5 permanent pages in the D2 car set) | NOTES 162, 1048 |
| 8 (left half) | sky page; chicago_preview.bin overwrites x 512..639 (menu) | NOTES 792 |
| 13-14 (y 256, x 832..959) | empty in the menu dump (room for area pages) | NOTES 499 |
| area slot 14 -> page 5 | area pages load into slot 14 | NOTES 113 |
Budget: 16 page slots at x 512..1023 (2 rows); CHI_AREA_TEX < ~170 textures per region; car twins at u+128 (NOTES 1054).

## 3. D2-style layout for D2 cities only: what it gives and what it takes
- Gain: 19 slots instead of 15 usable: 4 more pages for area textures (fewer halved city textures) and room for D2's per-model car pages with their damage twins (today the twin pages cost +1 permanent page each set).
- D1 functions that own the layout: LoadInAreaTSets 0x80033B10 (slot search: slotsused < 0xF, AreaTPages per area, up to 16 entries); the slot-page table and CLUT base (0x800BE4F8, 0x800BE1BC, written by FUN_00051ADC at 0x80051DC8 and read by FUN_0003A068); car page setup 0x8003BDC8 (CLUT per car polygon at 0x800BEA04 + 600*(page-5) + 20*tex).
- Gate per city: the CITY word (0x80096834) is set per route; a D2-only layout can branch on CITY (2 = Interview, 3 = Chicago slot) in LoadInAreaTSets and the car page setup, leaving D1 cities on the original slot count and page numbers. This needs an exe patch (guest code), not data alone.
- PS1 limits: 1 MB VRAM = 16 pages of 256x256 at 4 bpp (x 512..1023 for slots); 19 slots would need the framebuffer and sky/menu pages moved, which the D1 menu uses (13-14 empty, 0..4 framebuffers): feasibility to check per page.
- Recommendation: gate per city (CITY-indexed slot count) as a guest-code patch; do not change the shared layout for D1 maps.
