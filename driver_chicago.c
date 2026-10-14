/* driver_chicago.c — engine support for the Chicago port (package driver.chicago).
 *
 * model-table: Driver 1 keeps model pointers in an 800-entry table at
 * 0x800A0E20. The package's main_exe patches (chicago/exe_patches.py) point
 * every reference at a 2048-entry table at 0x9F000000; this activation
 * callback allocates that table in mod (Expansion 1) memory before boot, plus
 * the 512 KB cell object buffer (InitCellData patch, see exe_patches.py).
 * Save states include mod memory (local runtime change), so rewind works.
 *
 * area-switch guard: when Driver 1 starts loading another area it streams the
 * new area's textures and models over the same buffer, but objects keep being
 * drawn through the model table entries that point into it, i.e. through
 * half-overwritten data (freezes in the model renderer, stray primitives,
 * crashes). Driver 1's own levels avoid this by layout; Chicago's visibility
 * based area sets cannot. On the frame the "area loading" flag goes up, every
 * entry pointing into the streaming buffer is redirected to an empty model, so
 * those objects are skipped until the loader (0x80033E54) writes the new
 * pointers when the load completes. A switch is recognised by the flag rising
 * or by the current area changing while it is up.
 *
 * placeholders: models of areas that are not loaded are stored as size-0
 * entries in the in-memory model lump, so their table entries point at the
 * next model's size word. Objects of the incoming area are drawn through them
 * while its load is pending, and the group renderer runs off into garbage
 * until it reaches its trap (0x80030B00, a j-self loop: frozen picture, music
 * still playing). Every VBlank those entries are pointed at the empty model. */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

#include "mod_plugins.h"
#include "cpu_state.h"
#include "driver_personal.h"

#define MODEL_TABLE_ADDR    0x9F000000u   /* must match exe_patches.NEW_BASE */
#define MODEL_TABLE_ENTRIES 2048u
#define CELL_OBJECTS_ADDR   0x9F002000u   /* must match exe_patches.CELL_OBJECTS_ADDR */
#define CELL_OBJECTS_BYTES  (512u * 1024u)
#define SEA_LEVEL_ADDR      0x9F082100u   /* must match exe_patches.SEA_LEVEL_ADDR (after the empty model) */
#define CHI_SEA_LEVEL       (-1084)       /* y up: Chicago's water surface, convert.WATER_LEVEL below the street */
#define CITY_NOW            0x80096834u   /* 3 = Chicago */
#define MENU_ADDR           0x9F082110u   /* must match build_package.MENU_ADDR: row table 5 x 16 B */
#define MENU_LABELS         (MENU_ADDR + 0x50u)   /* 5 label pointers */
#define MENU_BYTES          0x200u  /* row table 9 x 16, list at +0xC0, strings at +0x180 */

#define AREA_LOADING_FLAG   0x800969E8u   /* set at 0x8003414C, cleared at 0x80033F50 */
#define CURRENT_AREA        0x800972C0u   /* written at 0x80034140 when a switch starts */
#define MODEL_SPOOL_BUFFER  0x80097238u   /* start of the area model / texture buffer */
#define MODEL_SPOOL_BYTES   0x40000u      /* generous: 63 blocks used by Chicago */

static uint32_t s_empty_model;
static uint32_t s_last_flag, s_last_area = 0xFFFFFFFFu;

/* The main_exe patches hard-code these addresses, so the blocks must be the
 * first mod-memory allocations, in this order. */
static int alloc_fixed(const char* what, uint32_t size, uint32_t align, uint32_t want) {
    uint32_t addr = psx_mod_alloc_guest_memory(size, align);
    if (addr != want) {
        fprintf(stderr, "driver.chicago: FATAL %s at 0x%08X, expected 0x%08X "
                        "(disable other mods that allocate guest memory)\n", what, addr, want);
        return 0;
    }
    fprintf(stdout, "driver.chicago: %s at 0x%08X (%u bytes)\n", what, addr, size);
    return 1;
}

/* An empty MODEL that every draw path survives. The group renderer gets a
 * table with one group that is always culled: its loop runs at least once
 * (0x80030B98), the plane has a zero normal and distance -1 (MAC1 = bk0 + L.V
 * < 0, 0x80030A5C). The ground-tile loops (0x80026FF0 / 0x80027098) decrement
 * the polygon count before testing it, so a model with no polygons runs away
 * (~1 MB of primitives over the kernel, then a fatal dispatch): the model has
 * one polygon of zeros on zero vertices, drawn as an invisible point. A tile
 * listed this frame can reach it when the area-switch guard redirects its
 * model between listing and drawing.
 *   +0x40 group table, +0x80 vertices / normals / collision, +0xA0 polygon */
static void make_empty_model(void) {
    uint32_t m = psx_mod_alloc_guest_memory(256u, 16u);
    if (!m) return;
    for (uint32_t o = 0; o < 256u; o += 4u)
        psx_mod_write_word(m + o, 0);
    psx_mod_write_word(m + 0x04, 0x0000FFFFu);            /* instance_number = -1 */
    psx_mod_write_word(m + 0x0C, 1u << 16);               /* 0 vertices, 1 polygon */
    psx_mod_write_word(m + 0x10, m + 0x80u);              /* vertices */
    psx_mod_write_word(m + 0x14, m + 0xA0u);              /* polygons */
    psx_mod_write_word(m + 0x18, m + 0x80u);              /* normals */
    psx_mod_write_word(m + 0x1C, m + 0x40u);              /* group table */
    psx_mod_write_word(m + 0x20, m + 0x80u);              /* collision (count 0) */
    psx_mod_write_word(m + 0x40, 1u | (24u << 16));       /* 1 group, 1 matrix of 24 bytes */
    psx_mod_write_word(m + 0x54, 0xFFFF0000u);            /* L33 = 0, bk0 = -1 */
    psx_mod_write_word(m + 0x58, 0xFFFFFFFFu);            /* bk1 = bk2 = -1 */
    psx_mod_write_word(m + 0x5C, (4u << 8) | 0x80000000u); /* 0 polygons, 1 sub-entry, sorted */
    psx_mod_write_word(m + 0x60, 4u << 24);               /* sub-entry: nothing to skip */
    s_empty_model = m;
}

static int s_sea_level;
static int s_menu;
static void model_table_activate(void) {
    if (alloc_fixed("model table", MODEL_TABLE_ENTRIES * 4u, 16u, MODEL_TABLE_ADDR) &&
        alloc_fixed("cell object buffer", CELL_OBJECTS_BYTES, 16u, CELL_OBJECTS_ADDR)) {
        make_empty_model();
        /* the sea level the ground query adds for "sea" water cells (exe patch, C35);
         * 0 = Driver 1's own (other cities) */
        if (s_empty_model && alloc_fixed("sea level", 16u, 16u, SEA_LEVEL_ADDR)) {
            psx_mod_write_word(SEA_LEVEL_ADDR, 0);
            s_sea_level = 1;
        }
        /* Take a Ride city menu with a 5th row (chicago-slot; FRONTEND patches in the package
         * point the menu's row table and label list here) */
        if (s_sea_level && alloc_fixed("city menu", MENU_BYTES, 16u, MENU_ADDR))
            s_menu = 1;
    }
}

/* --- Height-aware road surface selection (C16/C17) ---------------------------
 * Driver 1's road-map lookup (0x8001EEB4) takes the FIRST ROADSURF polygon that
 * contains the wheel point (2D test, no height). Chicago's converter writes
 * surfaces with several full-cell planes at different heights (trench under a
 * bridge, street under a deck, ground on a trench wall, lane beside a ramp) and
 * marks them with SURFACEINFO.info = 1. Each vblank this moves, for the 3x3
 * cells around the player, the plane whose height is nearest the car into slot
 * 0, so the unchanged engine loop picks it. The exe has no spare words for a
 * height-aware loop and the recomp rejects code outside its image (C22).
 * Addresses from the lookup's disassembly (NOTES.md): road map header
 * 0x8009E714 {width, height, unitXMid, unitZMid}; 4 region tables 0x8009D8F4
 * (60 x 60 cells, 4 bytes per cell, 240 per row) in a 120-cell ring, quadrant
 * parity at 0x80097374; surface pointers 0x8009D904 (type < 900); player
 * position 0x8009B0BC (x, y up, z), car centre ~160 above its ground. */
#define RM_HEADER     0x8009E714u
#define RM_TABLES     0x8009D8F4u
#define RM_PARITY     0x80097374u
#define SURF_PTRS     0x8009D904u
#define PLAYER_POS    0x8009B0BCu
#define SIPOLY_BYTES  52u
#define CAR_CENTRE    160

static int32_t rd32(uint32_t a) { return (int32_t)psx_mod_read_word(a); }
static int32_t rd16(uint32_t a) {
    uint32_t w = psx_mod_read_word(a & ~3u);
    return (int16_t)((a & 2u) ? (w >> 16) : (w & 0xFFFFu));
}

/* The road-map word of the cell under world (x, z) and the point's coordinates
 * local to that cell (rotation 0), exactly as 0x8001EF00..0x8001F02C does it. */
static uint32_t road_cell(int32_t x, int32_t z, int32_t* px, int32_t* pz) {
    int32_t w = rd32(RM_HEADER), h = rd32(RM_HEADER + 4u);
    int32_t sx = x + rd32(RM_HEADER + 8u), sz = rd32(RM_HEADER + 12u) + 750 - z;
    if (sx < 0 || sz < 0 || w <= 0 || h <= 0)
        return 0;
    int32_t col = sx / 1500, row = sz / 1500;
    if (col >= w || row >= h)
        return 0;
    *px = sx - col * 1500 - 750;
    *pz = -(sz - row * 1500 - 750);
    int32_t ca = (col & 0x7F) + ((col & ~0x7F) >> 4);
    int32_t ra = (row & 0x7F) + ((row & ~0x7F) >> 4);
    if (ca >= 120) ca -= 120;
    if (ra >= 120) ra -= 120;
    int32_t q = 0, par = rd32(RM_PARITY) & 1;
    if (ca >= 60) { ca -= 60; q = 1; }
    if (ra >= 60) { ra -= 60; if (!par) q += 2; }
    else if (par) q += 2;
    uint32_t table = psx_mod_read_word(RM_TABLES + 4u * (uint32_t)q);
    if ((table & 0x1FFFFFFFu) < 0x10000u || (table & 0x1FFFFFFFu) >= 0x200000u)
        return 0;
    return psx_mod_read_word(table + 4u * (uint32_t)ca + 240u * (uint32_t)ra);
}

/* Put the plane the car stands on first in the cell's surface (if marked).
 * Driver 2's rule (dr2roads.c sdGetCell, user 2026-10-12): planes from the top down;
 * the wheel stays on a plane until it is below that plane's switch height, then it
 * takes the next lower one. The switch is Driver 2's own per-level height where the
 * converter found one (SIPOLY pad, relative to the cell height), else the midpoint to
 * the next lower plane, never below that midpoint (an added guard plane must not lift
 * a car) and at least SWITCH_UNDER under the plane. A small hysteresis keeps the
 * current plane. A plane above the wheel never wins any more (the old rule took one
 * up to 100 above: cars rode 70-90 above the street at c20_p2n). */
/* SEL1 debug record (driver_personal_sel_debug): the last selection of this VBlank (the player's own cell) */
static int32_t s_dbg_top_s, s_dbg_best_hgt, s_dbg_y;
static uint32_t s_dbg_stacked, s_dbg_best, s_dbg_cell;
#define SWITCH_HYST  24
#define SWITCH_UNDER 64
#define NO_SWITCH    (-0x8000)
static void select_surface_d2(uint32_t cell, int32_t px, int32_t pz, int32_t y) {
    uint32_t type = (cell >> 16) & 0x3FFu;
    if (!cell || type >= 900u)
        return;
    uint32_t surf = psx_mod_read_word(SURF_PTRS + 4u * type);
    if ((surf & 0x1FFFFFFFu) < 0x10000u || (surf & 0x1FFFFFFFu) >= 0x200000u || rd16(surf + 2u) != 1)
        return;
    int32_t n = rd16(surf + 6u);
    if (n < 2 || n > 8)
        return;
    int32_t hcell = (int16_t)(cell & 0xFFF8u);
    int32_t hgt[8], sw[8], ord[8], cur = 0;
    for (int32_t i = 0; i < n; i++) {
        uint32_t p = surf + 8u + SIPOLY_BYTES * (uint32_t)i;
        int32_t a = rd32(p + 32u), c = rd32(p + 40u), d = rd32(p + 44u), pad = rd16(p + 50u);
        hgt[i] = ((a * px + c * pz) >> 12) - d - hcell;
        sw[i] = pad == NO_SWITCH || pad == 0 ? NO_SWITCH : pad - hcell;   /* 0: a level from before (none) */
        int32_t r = i;                                   /* insertion sort, top first */
        while (r > 0 && hgt[ord[r - 1]] < hgt[i]) { ord[r] = ord[r - 1]; r--; }
        ord[r] = i;
    }
    for (int32_t r = 0; r < n; r++)                      /* rank of the current plane (slot 0) */
        if (ord[r] == 0) cur = r;
    int32_t best = ord[n - 1];                           /* below every switch: the lowest */
    for (int32_t r = 0; r < n - 1; r++) {
        int32_t i = ord[r], mid = (hgt[i] + hgt[ord[r + 1]]) / 2;
        int32_t s = sw[i] == NO_SWITCH || sw[i] < mid ? mid : sw[i];
        if (s > hgt[i] - SWITCH_UNDER)
            s = hgt[i] - SWITCH_UNDER;
        if (r == cur) s -= SWITCH_HYST;                  /* stay on the current plane */
        else if (r < cur) s += SWITCH_HYST;              /* go up only clearly above the switch */
        if (r == 0) s_dbg_top_s = s;
        if (y >= s) { best = i; break; }
    }
    s_dbg_stacked = 1; s_dbg_best = (uint32_t)best; s_dbg_best_hgt = hgt[best];
    if (best == 0)
        return;
    /* The vblank hook runs from the interrupt check and can land inside the
     * engine's polygon loop. The generated polygons share corners and vertex
     * count and differ only in the plane, so only the 4 plane words and the
     * nverts/switch word are swapped (d before it): a torn read mixes at worst a
     * slope with the other plane's d, i.e. an error of a few tens of units, never
     * the other level; nverts is 4 in every polygon. */
    uint32_t p0 = surf + 8u + 32u, pb = surf + 8u + SIPOLY_BYTES * (uint32_t)best + 32u;
    for (uint32_t k = 0; k < 20u; k += 4u) {
        uint32_t w0 = psx_mod_read_word(p0 + k), wb = psx_mod_read_word(pb + k);
        psx_mod_write_word(p0 + k, wb);
        psx_mod_write_word(pb + k, w0);
    }
}

/* The old rule (levels from older converters: every SIPOLY pad is 0): the ground is
 * the highest plane that is not above the wheel (y = car centre minus CAR_CENTRE,
 * plus a tolerance for a compressed suspension): a lower plane can never catch a car
 * that bounced up (wallclimb), a higher one can never pull it down (rampwedge). A car
 * below every plane gets the lowest one. */
#define SELECT_TOLERANCE 100
static void select_surface_nearest(uint32_t cell, int32_t px, int32_t pz, int32_t y) {
    uint32_t type = (cell >> 16) & 0x3FFu;
    if (!cell || type >= 900u)
        return;
    uint32_t surf = psx_mod_read_word(SURF_PTRS + 4u * type);
    if ((surf & 0x1FFFFFFFu) < 0x10000u || (surf & 0x1FFFFFFFu) >= 0x200000u || rd16(surf + 2u) != 1)
        return;
    int32_t n = rd16(surf + 6u);
    if (n < 2 || n > 8)
        return;
    int32_t hcell = (int16_t)(cell & 0xFFF8u);
    int32_t best = -1, besth = -0x7FFFFFFF, lowest = 0, lowh = 0x7FFFFFFF;
    for (int32_t i = 0; i < n; i++) {
        uint32_t p = surf + 8u + SIPOLY_BYTES * (uint32_t)i;
        int32_t a = rd32(p + 32u), c = rd32(p + 40u), d = rd32(p + 44u);
        int32_t hgt = ((a * px + c * pz) >> 12) - d - hcell;
        if (hgt <= y + SELECT_TOLERANCE && hgt > besth) { besth = hgt; best = i; }
        if (hgt < lowh) { lowh = hgt; lowest = i; }
    }
    if (best < 0)
        best = lowest;
    if (best == 0)
        return;
    uint32_t p0 = surf + 8u + 32u, pb = surf + 8u + SIPOLY_BYTES * (uint32_t)best + 32u;
    for (uint32_t k = 0; k < 16u; k += 4u) {
        uint32_t w0 = psx_mod_read_word(p0 + k), wb = psx_mod_read_word(pb + k);
        psx_mod_write_word(p0 + k, wb);
        psx_mod_write_word(pb + k, w0);
    }
}

/* The rule follows the level: the converter writes a switch height or NO_SWITCH into
 * every SIPOLY pad since the Driver 2 rule (2026-10-12); older levels have 0 there and
 * keep the old rule (and loop order) exactly. Set per level, reset on every load. */
static int s_level_d2rule = 0;
static void select_surface(uint32_t cell, int32_t px, int32_t pz, int32_t y) {
    s_dbg_stacked = 0; s_dbg_cell = cell; s_dbg_y = y;
    uint32_t type = (cell >> 16) & 0x3FFu;
    if (!cell || type >= 900u)
        return;
    uint32_t surf = psx_mod_read_word(SURF_PTRS + 4u * type);
    if ((surf & 0x1FFFFFFFu) < 0x10000u || (surf & 0x1FFFFFFFu) >= 0x200000u || rd16(surf + 2u) != 1)
        return;
    int32_t n = rd16(surf + 6u);
    if (n < 2 || n > 8)
        return;
    int d2 = 0;
    for (int32_t i = 0; i < n; i++)
        if (rd16(surf + 8u + SIPOLY_BYTES * (uint32_t)i + 50u) != 0)
            d2 = 1;
    if (d2) {
        s_level_d2rule = 1;
        select_surface_d2(cell, px, pz, y);
    } else {
        select_surface_nearest(cell, px, pz, y);
    }
}

#define SPOOL_SECTORS_LEFT  0x800971F8u   /* > 0 while an area / region spool is in flight */
#define SELECT_IDLE_VBLANKS 60            /* stay idle this long after loading / spooling / restart */
static uint32_t s_select_idle = SELECT_IDLE_VBLANKS;
static int s_level_format = -1;                   /* -1 unknown, 0 old level, 1 with switch pads */

static void surface_select_inner(void) {
    if (getenv("CHI_NO_SELECT"))                  /* bisection switch */
        return;
    if (!psx_mod_game_started())
        return;
    /* Never touch surface data while cell / level data is being (re)loaded: level
     * start, area switches, region spools and Play Again (C26 hardening). */
    /* the total is signed: a total stuck below 0 (seen after a teleport during a
     * load) used to keep the selection idle until the next load (stale planes) */
    if (psx_mod_read_word(AREA_LOADING_FLAG) || (int32_t)psx_mod_read_word(SPOOL_SECTORS_LEFT) > 0) {
        s_select_idle = SELECT_IDLE_VBLANKS;
        s_level_d2rule = 0;
        s_level_format = -1;
        return;
    }
    if (s_select_idle) {
        s_select_idle--;
        return;
    }
    int32_t x = rd32(PLAYER_POS), y = rd32(PLAYER_POS + 4u) - CAR_CENTRE, z = rd32(PLAYER_POS + 8u);
    /* Surfaces are shared by every cell with the same relative planes, so a
     * neighbour with the car cell's surface would override its choice: with the
     * Driver 2 rule the car's own cell goes last and wins (older levels: the old
     * order, centre fifth). */
    for (int k = 1; k <= 9; k++) {
        int kk = s_level_d2rule ? k : (k < 5 ? k : k == 5 ? 9 : k - 1);
        int dx = kk == 9 ? 0 : (kk - 1 + (kk > 4)) % 3 - 1, dz = kk == 9 ? 0 : (kk - 1 + (kk > 4)) / 3 - 1;
        int32_t px = 0, pz = 0;
        uint32_t cell = road_cell(x + dx * 1500, z + dz * 1500, &px, &pz);
        if (cell)
            select_surface(cell, px, pz, y);
    }
}

/* SEL1 record (C17 deck snap, 14.10.; driver_personal.c, 0x9F082440 with the Chicago slot on): +8 road-map word of
 * the player's own cell, +12 car y as the selector sees it, +16 idle countdown | D2 rule << 16 | stacked << 17,
 * +20 chosen plane index | its height << 16, +24 the top plane's switch threshold, +28 slot 0's plane d now */
static void surface_select_vblank(void) {
    s_dbg_stacked = 0; s_dbg_cell = 0; s_dbg_best = 0; s_dbg_best_hgt = 0; s_dbg_top_s = 0; s_dbg_y = 0;
    surface_select_inner();
    uint32_t d0 = 0, type = (s_dbg_cell >> 16) & 0x3FFu;
    if (s_dbg_cell && type < 900u) {
        uint32_t surf = psx_mod_read_word(SURF_PTRS + 4u * type);
        if ((surf & 0x1FFFFFFFu) >= 0x10000u && (surf & 0x1FFFFFFFu) < 0x200000u)
            d0 = psx_mod_read_word(surf + 8u + 44u);
    }
    uint32_t w[6] = { s_dbg_cell, (uint32_t)s_dbg_y,
                      (s_select_idle & 0xFFFFu) | ((uint32_t)s_level_d2rule << 16) | (s_dbg_stacked << 17),
                      (s_dbg_best & 0xFFu) | ((uint32_t)s_dbg_best_hgt << 16), (uint32_t)s_dbg_top_s, d0 };
    driver_personal_sel_debug(w);
}

static void surface_select_vblank(void);

/* Every table entry pointing into the area spool buffer -> the empty model.
 * Returns the number of entries redirected. */
static uint32_t redirect_spool_entries(void) {
    uint32_t lo = psx_mod_read_word(MODEL_SPOOL_BUFFER) & 0x1FFFFFFFu;
    uint32_t hi = lo + MODEL_SPOOL_BYTES, n = 0;
    if (!lo)
        return 0;
    for (uint32_t i = 0; i < MODEL_TABLE_ENTRIES; i++) {
        uint32_t p = psx_mod_read_word(MODEL_TABLE_ADDR + 4u * i) & 0x1FFFFFFFu;
        if (p >= lo && p < hi) {
            psx_mod_write_word(MODEL_TABLE_ADDR + 4u * i, s_empty_model);
            n++;
        }
    }
    return n;
}

/* One vblank callback per plugin id: this one also runs the surface selection. */
/* The sea level offset belongs to levels whose water sits at the sand base (the
 * converter since the Driver 2 level rule, 2026-10-12): their marked surfaces carry
 * switch pads (never 0). Older levels (pads 0, e.g. the shipped var_water_sea) keep
 * Driver 1's own sea level exactly. Checked once per load. */
static int level_has_switch_pads(void) {
    for (uint32_t t = 0; t < 900u; t++) {
        uint32_t surf = psx_mod_read_word(SURF_PTRS + 4u * t);
        if ((surf & 0x1FFFFFFFu) < 0x10000u || (surf & 0x1FFFFFFFu) >= 0x200000u || rd16(surf + 2u) != 1)
            continue;
        return rd16(surf + 8u + 50u) != 0;                  /* first polygon's pad */
    }
    return 0;
}

/* --- Chicago's own city slot (chicago-slot feature, 2026-10-13) ----------------
 * Chicago no longer replaces Los Angeles on the disc: CHICAGO.LEV lies past the disc
 * end (package overlay) and LA.LEV is original. The game resolves the 8 level files
 * once at boot into 0x800BE0A4 (32 B each: 4 x (absolute byte position, size), from
 * the LEV header, 0x800503xx). Chicago shares LA's city index 3 (it was tuned in LA's
 * slot: LA's music, night-only, LA's CITY switches); when Chicago is chosen the plugin
 * writes Chicago's 32 bytes into entry 3 (from assets/chicago_slot.bin, written by
 * build_package), else LA's own, and moves the Take a Ride player start in the
 * mission script (0x13 x z) from LA's to Chicago's. CHICAGO_FLAG_ADDR tells the exe's
 * area rule (and this plugin) that the loaded city is Chicago. */
#define LEVEL_LOC_TABLE     0x800BE0A4u
#define CHICAGO_FLAG_ADDR   0x9F082104u   /* must match exe_patches.CHICAGO_FLAG_ADDR */
#define SLOT_FILE           "mods/packages/driver.chicago/0.1.0/assets/chicago_slot.bin"
#define MISSION_LO          0x80120000u   /* the mission script (Take a Ride start seen at 0x8012A7A8) */
#define MISSION_HI          0x80140000u
#define MISSION_NUMBER      0x80096808u   /* Take a Ride: Miami 0x78/79, SF 0x7A/7B, LA 0x7C, NY 0x7D/7E */
#define NIGHT_FLAG          0x80096850u   /* mission script opcode 0x1F (exe 0x800689C8) */
static int s_slot_enabled, s_slot_chicago, s_la_saved, s_start_done, s_have_night, s_chi_night, s_have_music;
static int s_have_map, s_have_sky;
static uint32_t s_stable_end, s_carsets = 0x10303u;
static uint32_t s_dmg_civ[540], s_dmg_civ_n;        /* civ verts (225 words) + civ polys (315 words) */
static uint32_t s_cos[2][200], s_cos_n[2];          /* C42/C53: cosmetics rows (8 x 100 B) day / night, car set 4 */
static uint32_t s_chi_map[6];
static uint32_t s_chi_entry[8], s_la_entry[8], s_night_entry[8];
static int32_t s_la_start[2], s_chi_start[2];

/* Levels that run in LA's city index 3 through LA's Take a Ride (user, 2026-10-13: two-page
 * city menu): the plugin points level table entry 3 at the chosen level and moves the start.
 * Driver 1's other level files (IVIEW 2, TRAIN 6, CREDITS = Newtown 7) keep their own
 * boot-time entries; forcing their own CITY into Take a Ride crashed (CITY 7), index 3 works. */
enum { V_LA = 0, V_CHICAGO = 1, V_IVIEW = 2, V_TRAIN = 6, V_NEWTOWN = 7 };   /* FLAT (4): not used (user R20, a bare dev level) */
static int s_virtual = V_LA;
static int s_classic = 1;                  /* menu option: classic (5 rows) or pages */
static const int32_t s_level_start[8][2] = {      /* by level index (QA-2 13.10.; Newtown from its roads) */
    { 0, 0 }, { 0, 0 }, { -10500, -22144 }, { 0, 0 }, { 0, 4500 }, { 0, 0 }, { 25227, 29933 }, { 18000, 7500 },
};

static void chicago_slot_activate(void) {
    FILE* f = fopen(SLOT_FILE, "rb");
    uint32_t w[29];
    if (!f) { fprintf(stderr, "driver.chicago: %s missing, Chicago slot off\n", SLOT_FILE); return; }
    size_t n = fread(w, 4, 29, f);
    fclose(f);
    if (n != 12 && n != 20 && n != 27 && n != 28 && n != 29) { fprintf(stderr, "driver.chicago: %s short, Chicago slot off\n", SLOT_FILE); return; }
    for (int i = 0; i < 8; i++) s_chi_entry[i] = w[i];
    s_la_start[0] = (int32_t)w[8]; s_la_start[1] = (int32_t)w[9];
    s_chi_start[0] = (int32_t)w[10]; s_chi_start[1] = (int32_t)w[11];
    s_have_night = n >= 20 && w[12] != 0;           /* + night Chicago's 8 entry words */
    for (int i = 0; s_have_night && i < 8; i++) s_night_entry[i] = w[12 + i];
    s_have_map = n >= 27 && w[20] != 0;             /* + Driver 2's minimap frame (C12) */
    for (int i = 0; s_have_map && i < 6; i++) s_chi_map[i] = w[20 + i];
    s_have_sky = n >= 27 && (w[26] & 1u);           /* + SKY.BIN with Chicago's skies 13-15 (C10) */
    s_have_music = n >= 27 && (w[26] & 2u);         /* + MUSIC.BIN with Chicago's songs 8 / 9 (milestone 2) */
    s_stable_end = n >= 28 ? w[27] : 0u;            /* + C45 stable-page end (skip-resident patch) */
    s_carsets = n >= 29 ? w[28] : 0x10303u;         /* + C51 car-set CITY: day | night << 8 (default LA's) */
    {   /* C42 step 1: Driver 2 civ damage tables (car-set city 4), written to 0x800A0E20 while in use */
        FILE* g = fopen("mods/packages/driver.chicago/0.1.0/assets/dmg_civ.bin", "rb");
        if (g) { s_dmg_civ_n = (uint32_t)fread(s_dmg_civ, 4, 540, g); fclose(g); }
        for (int t = 0; t < 2; t++) {
            g = fopen(t ? "mods/packages/driver.chicago/0.1.0/assets/cosmetics_night.bin"
                        : "mods/packages/driver.chicago/0.1.0/assets/cosmetics_day.bin", "rb");
            if (g) { s_cos_n[t] = (uint32_t)fread(s_cos[t], 4, 200, g); fclose(g); }
        }
    }
    char v[32] = {0};
    psx_mod_option_value("driver.chicago", "chicago-slot", "city", v, sizeof v);
    s_slot_chicago = strcmp(v, "la") != 0;          /* before any menu choice: the mod setting */
    s_virtual = s_slot_chicago ? V_CHICAGO : V_LA;
    char m[16] = {0};
    psx_mod_option_value("driver.chicago", "chicago-slot", "menu", m, sizeof m);
    s_classic = strcmp(m, "pages") != 0;
    s_slot_enabled = 1;
    fprintf(stdout, "driver.chicago: own city slot on, LA slot plays %s\n", s_slot_chicago ? "Chicago" : "Los Angeles");
}

/* Chicago is the loaded city: index 3 and (with its own slot) Chicago chosen; with the
 * old chicago-la feature index 3 always is Chicago. */
static int chicago_active(void) {
    return psx_mod_read_word(0x80096834u) == 3u && (!s_slot_enabled || s_virtual == V_CHICAGO);
}
/* any level other than LA's own runs in index 3 */
static int other_level_active(void) {
    return psx_mod_read_word(0x80096834u) == 3u && (!s_slot_enabled || s_virtual != V_LA);
}

/* The Take a Ride city menu (FRONTEND overlay at 0x801C0000, QA-3's map) in two pages. The
 * row table (handler, leave, confirm, bytes [row, row, up, down]) and the drawn struct list
 * (FRONTEND patch: its base register s0 at 0x801C435C) live in mod memory; the plugin writes
 * both for the current page, sets the highlight, and turns the page when cross is pressed on
 * the last row (whose callbacks do nothing; a confirm returning 0 keeps the menu up). */
#define MENU_CURSOR         0x801CE088u
#define MENU_MARK           0x801CE038u   /* FRONTEND patch word: the overlay with our patches is loaded */
#define MENU_LIST           (MENU_ADDR + 0xC0u)   /* must match build_package.MENU_LIST */
#define MENU_STR            (MENU_ADDR + 0x180u)
#define PAD_PRESS           0x80097538u   /* new presses (the menu loop reads it): 0x40 cross */
#define NOP_FN              0x001C78A8u   /* FRONTEND: jr ra; move v0, zero (an exe address is not a recompiled entry) */
#define CITY_WORD           0x80096834u
enum { R_CITY, R_PAGE, R_GREY };
typedef struct { uint32_t fn[3]; const char* label; uint32_t label_ptr; int kind; int virt; int city; } MenuRow;
static const MenuRow s_page1[] = {
    { { 0x001C43ECu, 0x001C4440u, 0x001C444Cu }, 0, 0x001C0398u, R_CITY, -1, 0 },          /* Miami */
    { { 0x001C44FCu, 0x001C4554u, 0x001C4560u }, 0, 0x001C0388u, R_CITY, -1, 1 },          /* San Francisco */
    { { 0x001C4610u, 0x001C4668u, 0x001C4674u }, 0, 0x001C037Cu, R_CITY, V_LA, 3 },        /* Los Angeles */
    { { 0x001C46FCu, 0x001C4754u, 0x001C4760u }, 0, 0x001C0370u, R_CITY, -1, 5 },          /* New York */
    { { 0x001C4610u, 0x001C4668u, 0x001C4674u }, "Newtown", 0, R_CITY, V_NEWTOWN, 3 },
    { { 0x001C4610u, 0x001C4668u, 0x001C4674u }, "Interview", 0, R_CITY, V_IVIEW, 3 },
    { { 0x001C4610u, 0x001C4668u, 0x001C4674u }, "Training", 0, R_CITY, V_TRAIN, 3 },
    { { NOP_FN, NOP_FN, NOP_FN }, "Driver 2 cities", 0, R_PAGE, -1, -1 },
};
/* classic: the menu as before the pages (5 rows, "Take A Ride:"), package option menu = classic */
static const MenuRow s_classic_rows[] = {
    { { 0x001C43ECu, 0x001C4440u, 0x001C444Cu }, 0, 0x001C0398u, R_CITY, -1, 0 },
    { { 0x001C44FCu, 0x001C4554u, 0x001C4560u }, 0, 0x001C0388u, R_CITY, -1, 1 },
    { { 0x001C4610u, 0x001C4668u, 0x001C4674u }, 0, 0x001C037Cu, R_CITY, V_LA, 3 },
    { { 0x001C46FCu, 0x001C4754u, 0x001C4760u }, 0, 0x001C0370u, R_CITY, -1, 5 },
    { { 0x001C4610u, 0x001C4668u, 0x001C444Cu }, "Chicago", 0, R_CITY, V_CHICAGO, 3 },
};
static const MenuRow s_page2[] = {
    { { 0x001C4610u, 0x001C4668u, 0x001C444Cu }, "Chicago", 0, R_CITY, V_CHICAGO, 3 },   /* Miami's confirm: Day/Night */
    { { NOP_FN, NOP_FN, NOP_FN }, "Havana", 0, R_GREY, -1, -1 },
    { { NOP_FN, NOP_FN, NOP_FN }, "Las Vegas", 0, R_GREY, -1, -1 },
    { { NOP_FN, NOP_FN, NOP_FN }, "Rio", 0, R_GREY, -1, -1 },
    { { NOP_FN, NOP_FN, NOP_FN }, "Driver 1 cities", 0, R_PAGE, -1, -1 },
};
#define MENU_MAX_ROWS 9
/* Newtown / Interview / Training load through their own original missions (EXP 13.10.: the
 * script's CITY opcode, not index 3): Credits 0x7F (CITY 7), Interview 0xAE (2), Desert
 * training 0xAA (6); the plugin swaps LA's Take a Ride mission 0x7C for it after the confirm. */
#define CITY_OP_WORD       0x800689F8u
#define CITY_OP_ORIG       0x8D020004u   /* lw v0, 4(t0) */
/* default since 2026-10-13 (EXP's mission decode): the D1 extras run LA's Take a Ride (free
 * drive, no timer / Game Over) with only the CITY operand switched and the start moved like
 * Chicago's; CHI_EXTRA_LA=0 goes back to their own missions below */
static int extra_via_la(void) {
    static int on = -1;
    if (on < 0) { const char* e = getenv("CHI_EXTRA_LA"); on = !(e && *e == '0'); }
    return on;
}
static int is_extra(int v) { return v == V_NEWTOWN || v == V_IVIEW || v == V_TRAIN; }
static uint32_t extra_mission(int v) {
    if (extra_via_la()) return 0u;
    return v == V_NEWTOWN ? 0x7Fu : v == V_IVIEW ? 0xAEu : v == V_TRAIN ? 0xAAu : 0u;
}
static int s_page;                                        /* 0 = Driver 1 cities, 1 = Driver 2 cities */
static uint32_t s_pad_prev;

static uint32_t str_ptrs[16];
static void write_strings(void) {                          /* every label once, word-packed */
    static const char* all[] = { "Driver 1 cities", "Driver 2 cities", "Newtown", "Interview", "Training",
                                 "Chicago", "Havana", "Las Vegas", "Rio" };
    uint32_t a = MENU_STR;
    for (unsigned i = 0; i < sizeof all / sizeof all[0]; i++) {
        size_t n = strlen(all[i]) + 1;
        str_ptrs[i] = a;
        for (size_t k = 0; k < n; k += 4) {
            uint32_t w = 0;
            for (size_t b = 0; b < 4 && k + b < n; b++) w |= (uint32_t)(uint8_t)all[i][k + b] << (8 * b);
            psx_mod_write_word(a + (uint32_t)k, w);
        }
        a += (uint32_t)((n + 3) & ~3u);
    }
}
static uint32_t label_of(const MenuRow* r) {
    static const char* all[] = { "Driver 1 cities", "Driver 2 cities", "Newtown", "Interview", "Training",
                                 "Chicago", "Havana", "Las Vegas", "Rio" };
    if (!r->label) return r->label_ptr;
    for (unsigned i = 0; i < sizeof all / sizeof all[0]; i++)
        if (!strcmp(r->label, all[i])) return str_ptrs[i];
    return 0;
}
static const MenuRow* page_rows(int* n) {
    if (s_classic) { *n = (int)(sizeof s_classic_rows / sizeof s_classic_rows[0]); return s_classic_rows; }
    if (s_page) { *n = (int)(sizeof s_page2 / sizeof s_page2[0]); return s_page2; }
    *n = (int)(sizeof s_page1 / sizeof s_page1[0]); return s_page1;
}
static int row_kind(const MenuRow* r) { return r->kind; }
static int row_usable(const MenuRow* r) {
    if (row_kind(r) == R_GREY) return 0;
    if (r->kind == R_CITY && r->virt != V_LA && r->virt < 0) {   /* Miami, SF, NY: only when unlocked */
        int unlocked = (int)psx_mod_read_word(0x800967E0u);
        int order = r->city == 0 ? 0 : r->city == 1 ? 1 : 3;      /* menu order: Miami, SF, LA, NY */
        return unlocked < 1 || unlocked > 4 || order < unlocked;
    }
    if (r->virt == V_LA) {
        int unlocked = (int)psx_mod_read_word(0x800967E0u);
        return unlocked < 1 || unlocked > 4 || 2 < unlocked;
    }
    return 1;
}
static void menu_tables(void) {
    if (!str_ptrs[0]) write_strings();
    int n;
    const MenuRow* rows = page_rows(&n);
    int order[MENU_MAX_ROWS], k = 0;
    for (int i = 0; i < n; i++)
        if (row_usable(&rows[i])) order[k++] = i;
    for (int r = 0; r < MENU_MAX_ROWS; r++) {
        const MenuRow* row = &rows[r < n ? r : n - 1];
        for (int w = 0; w < 3; w++)
            psx_mod_write_word(MENU_ADDR + 16u * r + 4u * w, r < n ? row->fn[w] : NOP_FN);
        int up = r, down = r;
        for (int i = 0; i < k; i++)
            if (order[i] == r) { up = order[(i + k - 1) % k]; down = order[(i + 1) % k]; }
        psx_mod_write_word(MENU_ADDR + 16u * r + 12u, (uint32_t)r | ((uint32_t)r << 8) | ((uint32_t)up << 16) | ((uint32_t)down << 24));
    }
    /* the drawn list: page header (y 150), rows from y 180 every 30, terminator */
    uint32_t cur = psx_mod_read_word(MENU_CURSOR);
    int y0 = s_classic ? 210 : 168, step = s_classic ? 40 : 30;
    psx_mod_write_word(MENU_LIST + 0u, ((s_classic ? 150u : 140u) << 16) | 40u);
    psx_mod_write_word(MENU_LIST + 4u, 0);
    psx_mod_write_word(MENU_LIST + 8u, s_classic ? 0x001C0324u : str_ptrs[s_page ? 1 : 0]);   /* "Take A Ride:" */
    psx_mod_write_word(MENU_LIST + 12u, 0xFFFFFFFFu);
    for (int r = 0; r < n; r++) {
        uint32_t s = MENU_LIST + 16u * (uint32_t)(r + 1);
        psx_mod_write_word(s + 0u, ((uint32_t)(y0 + step * r) << 16) | 26u);
        static int grey = -1;                             /* struct byte +5 of a greyed row (font colour) */
        if (grey < 0) { const char* g = getenv("CHI_MENU_GREY"); grey = g ? (int)strtol(g, 0, 0) : 3; }   /* small, dimmer style */
        psx_mod_write_word(s + 4u, row_kind(&rows[r]) == R_GREY ? (uint32_t)grey
                                   : (uint32_t)r == cur ? 1u : 0u);
        psx_mod_write_word(s + 8u, label_of(&rows[r]));
        psx_mod_write_word(s + 12u, 0xFFFFFFFFu);
    }
    uint32_t t = MENU_LIST + 16u * (uint32_t)(n + 1);
    psx_mod_write_word(t + 0u, 0xFFFFFFFFu);
    psx_mod_write_word(t + 4u, 0);
    psx_mod_write_word(t + 8u, 0);
    psx_mod_write_word(t + 12u, 0xFFFFFFFFu);
}
/* what a row's highlight handler does, for the first row after a page turn (the cursor lands
 * there without the menu calling its handler): city index, picture, caption */
static void apply_first_row(void) {
    if (s_page) {                                         /* Chicago: LA's handler */
        psx_mod_write_word(CITY_WORD, 3u);
        psx_mod_write_word(0x801D2DB0u, 0x801D2D60u);
        psx_mod_write_word(0x801CDFC4u, 0x001C037Cu);
        psx_mod_write_word(0x801CDFC0u, (0xC8u << 16) | 0x148u);
        s_virtual = V_CHICAGO; s_slot_chicago = 1;
    } else {                                              /* Miami's handler */
        psx_mod_write_word(CITY_WORD, 0u);
        psx_mod_write_word(0x801D2DB0u, 0x801D2D10u);
        psx_mod_write_word(0x801CDFC4u, 0x001C03ACu);
        psx_mod_write_word(0x801CDFC0u, (0xB6u << 16) | 0x147u);
    }
}

static void chicago_slot_vblank(void) {
    if (s_menu && s_slot_enabled && psx_mod_read_word(MENU_ADDR) == 0)
        menu_tables();                                    /* before the menu's first init reads it */
    if (s_menu && s_slot_enabled && psx_mod_read_word(MENU_MARK) == 0x0172001Au) {
        uint32_t cur = psx_mod_read_word(MENU_CURSOR);
        int n;
        const MenuRow* rows = page_rows(&n);
        uint32_t pad = psx_mod_read_word(PAD_PRESS) & 0xFFFFu;
        if (cur < (uint32_t)n && rows[cur].kind == R_PAGE && (pad & 0x40u) && !(s_pad_prev & 0x40u)) {
            s_page ^= 1;                                  /* cross on the page row: turn the page */
            psx_mod_write_word(MENU_CURSOR, 0);
            apply_first_row();
            cur = 0;
            rows = page_rows(&n);
        }
        s_pad_prev = pad;
        if (cur < (uint32_t)n && rows[cur].virt >= 0) {   /* a row of index 3: which level it loads */
            s_virtual = rows[cur].virt;
            s_slot_chicago = s_virtual == V_CHICAGO;
        }
        menu_tables();
    }
    /* Day/Night for the Chicago row: its confirm (Miami's) sets mission 0x78 and the Day/Night
     * screen adds the choice (0 day / 1 night). With city index 3 that is Chicago: the mission
     * goes back to LA's Take a Ride (0x7C: MISSION.BLK entry 0x5C, city 3) and the choice is kept. */
    if (s_slot_enabled && psx_mod_read_word(CITY_WORD) == 3u) {
        uint32_t m = psx_mod_read_word(MISSION_NUMBER);
        if (m == 0x78u || m == 0x79u || m == 0x7Du) {
            s_chi_night = m != 0x78u;
            s_virtual = V_CHICAGO; s_slot_chicago = 1;
            psx_mod_write_word(MISSION_NUMBER, 0x7Cu);
            fprintf(stdout, "driver.chicago: Chicago %s\n", s_chi_night ? "night" : "day");
        }
    }
    if (s_slot_enabled && !s_classic && psx_mod_read_word(CITY_WORD) == 3u && extra_mission(s_virtual)
        && psx_mod_read_word(MISSION_NUMBER) == 0x7Cu) {
        psx_mod_write_word(MISSION_NUMBER, extra_mission(s_virtual));
        fprintf(stdout, "driver.chicago: Take a Ride -> mission 0x%X (level %d)\n", (unsigned)extra_mission(s_virtual), s_virtual);
    }
    {
        int via_la = extra_via_la() && is_extra(s_virtual);
        int on = s_slot_enabled && !s_classic && via_la && psx_mod_read_word(MISSION_NUMBER) == 0x7Cu;
        uint32_t want_op = 0x24020000u | (uint32_t)(on ? s_virtual : 0);   /* addiu v0, zero, CITY */
        uint32_t w = psx_mod_read_word(CITY_OP_WORD);
        if (on && w != want_op && (w == CITY_OP_ORIG || (w & 0xFFFFFFF8u) == 0x24020000u)) psx_mod_write_word(CITY_OP_WORD, want_op);
        else if (!on && (w & 0xFFFFFFF8u) == 0x24020000u) psx_mod_write_word(CITY_OP_WORD, CITY_OP_ORIG);
    }
    if (s_sea_level)                                       /* the flag word shares the sea level block */
        psx_mod_write_word(CHICAGO_FLAG_ADDR, chicago_active() ? 1u : 0u);
    if (!s_slot_enabled || !psx_mod_game_started())
        return;
    uint32_t cur[8];
    for (int i = 0; i < 8; i++) cur[i] = psx_mod_read_word(LEVEL_LOC_TABLE + 96u + 4u * i);
    if (!s_la_saved) {                                     /* after the boot scan: LA's own entry */
        if (cur[0] == 0 || cur[0] == s_chi_entry[0]) return;
        for (int i = 0; i < 8; i++) s_la_entry[i] = cur[i];
        s_la_saved = 1;
    }
    uint32_t other[8];
    const uint32_t* want = s_la_entry;
    if (s_virtual == V_CHICAGO)
        want = s_chi_night && s_have_night ? s_night_entry : s_chi_entry;
    else if (s_virtual != V_LA && !is_extra(s_virtual)) {   /* another level file: its boot-time entry */
        for (int i = 0; i < 8; i++) other[i] = psx_mod_read_word(LEVEL_LOC_TABLE + 32u * (uint32_t)s_virtual + 4u * i);
        want = other;
    }
    if (cur[0] != want[0] && !psx_mod_read_word(AREA_LOADING_FLAG))
        for (int i = 0; i < 8; i++) psx_mod_write_word(LEVEL_LOC_TABLE + 96u + 4u * i, want[i]);
    /* Take a Ride start: the mission script still names LA's start */
    int extra_run = is_extra(s_virtual) && psx_mod_read_word(CITY_WORD) == (uint32_t)s_virtual;
    if (!other_level_active() && !extra_run)
        return;
    if (extra_mission(s_virtual))                          /* their own missions carry their starts */
        return;
    int32_t sx = s_virtual == V_CHICAGO ? s_chi_start[0] : s_level_start[s_virtual][0];
    int32_t sz = s_virtual == V_CHICAGO ? s_chi_start[1] : s_level_start[s_virtual][1];
    /* the mission parse copies the start into (x, y, z) vectors at once; the car is placed
     * from them only at level start: rewrite x / z there (checked every vblank) */
    static const uint32_t copies[] = { 0x800C71A8u, 0x801FD790u };
    for (unsigned i = 0; i < sizeof copies / sizeof copies[0]; i++)
        if ((int32_t)psx_mod_read_word(copies[i]) == s_la_start[0]
            && (int32_t)psx_mod_read_word(copies[i] + 8u) == s_la_start[1]) {
            psx_mod_write_word(copies[i], (uint32_t)sx);
            psx_mod_write_word(copies[i] + 8u, (uint32_t)sz);
            /* C50 (14.10.): on Play Again the script is parsed again at once, and y is taken from the
             * ground at LA's start in the loaded map; outside a small map (Newtown, Interview, Training)
             * that is garbage (car at y 4524, game stuck). Keep the y of the level's first load. */
            {
                static int32_t first_y[8][2];
                static uint8_t have_y[8][2];
                int v = s_virtual & 7;
                int32_t y = (int32_t)psx_mod_read_word(copies[i] + 4u);
                if (!have_y[v][i]) { first_y[v][i] = y; have_y[v][i] = 1; }
                else if (y != first_y[v][i]) psx_mod_write_word(copies[i] + 4u, (uint32_t)first_y[v][i]);
                fprintf(stdout, "driver.chicago: start vector %u (level %d): y %d, first load %d\n",
                        i, s_virtual, (int)y, (int)first_y[v][i]);
            }
            /* night: LA's own night look (CITY 3) on D2's night textures, without Driver 1's
             * extra night dimming on top (user R15: it should look like D2's night) */
            psx_mod_write_word(NIGHT_FLAG, 0u);
        }
    /* the script itself, rescanned every 30 vblanks: Play Again reloads it with LA's start */
    if (++s_start_done % 30 != 0)
        return;
    for (uint32_t a = MISSION_LO; a < MISSION_HI; a += 4u)
        if (psx_mod_read_word(a) == 0x13u && (int32_t)psx_mod_read_word(a + 4u) == s_la_start[0]
            && (int32_t)psx_mod_read_word(a + 8u) == s_la_start[1]) {
            psx_mod_write_word(a + 4u, (uint32_t)sx);
            psx_mod_write_word(a + 8u, (uint32_t)sz);
            fprintf(stdout, "driver.chicago: Take a Ride start moved (level %d) at 0x%08X\n", s_virtual, (unsigned)a);
        }
}

/* Traffic light glows (2026-10-13): LA's city code (CITY 3, shared with Chicago) draws them at
 * offsets for LA's light models, as immediates in the exe (0x800530E4.., 0x80053764 helper).
 * While Chicago is loaded these words hold Chicago's offsets (model coordinates of the D2
 * signal heads after the converter's quarter turn: TLIGHT01 head at x 0, TLIGHT02 = TLIGHT00
 * at x 565, rows y -957 / -876 / -795, front z -100; one street lamp at x 560, y -1640), and
 * LA's own otherwise. Written only over one of the two known values. */
static const uint32_t s_glow_words[][3] = {          /* address, LA, Chicago */
    { 0x800530E4u, 0x2406FCFEu, 0x24060505u },   /* kind 0 (TLIGHT00) a2: x = a2 - 720 */
    { 0x800530F8u, 0x2406FD26u, 0x240602D0u },   /* kind 1 (TLIGHT01) a2 */
    { 0x800537E4u, 0x2406FA4Cu, 0x2406FC43u },   /* red y */
    { 0x800537F8u, 0x2406FABAu, 0x2406FC94u },   /* amber y */
    { 0x8005380Cu, 0x2406FB28u, 0x2406FCE5u },   /* green y */
    { 0x80053814u, 0x2407FFBAu, 0x2407FF9Cu },   /* z (front face) */
    { 0x80053118u, 0x2405044Cu, 0x24050230u },   /* street lamp 1 x */
    { 0x8005311Cu, 0x2406F79Au, 0x2406F998u },   /* street lamp 1 y */
    { 0x80053130u, 0x2405FBB4u, 0x24050230u },   /* street lamp 2 x (Chicago: the same lamp) */
    { 0x80053138u, 0x2406F79Au, 0x2406F998u },   /* street lamp 2 y */
};
/* Chicago by DAY (user R15, 2026-10-13): LA is night-only, and the exe gives CITY 3 its night
 * look in these places; while Chicago day is loaded they compare CITY with no city (0x7F)
 * instead, so Chicago behaves like the day cities (Miami's colours). Chicago by night keeps
 * LA's night behaviour on D2's night textures. */
static const uint32_t s_day_words[][3] = {           /* address, LA, Chicago day */
    { 0x800298D8u, 0x24020003u, 0x2402007Fu },   /* fog / sky colour pair: LA's dark one */
    { 0x8003A6B4u, 0x24020003u, 0x2402007Fu },   /* ambient 0x282828 */
    { 0x8003B19Cu, 0x24100003u, 0x2410007Fu },   /* 0x80079AF0 calls skipped in LA */
    { 0x8003C974u, 0x24020003u, 0x2402007Fu },   /* 0x800970C0 -> 0x800970AC */
    { 0x80047030u, 0x24020003u, 0x2402007Fu },   /* sun / lens flare skipped in LA */
    { 0x8004B248u, 0x24020003u, 0x2402007Fu },   /* headlights always on */
    { 0x800437E0u, 0x24020003u, 0x2402007Fu },   /* big light halo (night or CITY 3) */
    { 0x80023640u, 0x24020003u, 0x2402007Fu },   /* car lights on (gp+0xD0 for CITY 3 and 5; 0x80025874 -> 0x80046000) */
    /* C39 (13.10.): level init 0x8002360C compares CITY with s1 = 3 (set at 0x80023720) */
    { 0x8002379Cu, 0x14510003u, 0x10000003u },   /* bne v0,s1 -> b: no 0x800430B8 light halo / trail setup */
    { 0x80023CD8u, 0x14510002u, 0x10000002u },   /* bne v0,s1 -> b: lights flag 0x800970E8 stays 0 (player lamps 0x8003B064) */
};
static void switch_words(const uint32_t (*t)[3], unsigned n, int alt) {
    for (unsigned i = 0; i < n; i++) {
        uint32_t cur = psx_mod_read_word(t[i][0]);
        uint32_t want = t[i][alt ? 2 : 1];
        if (cur != want && (cur == t[i][1] || cur == t[i][2]))
            psx_mod_write_word(t[i][0], want);
    }
}
/* Minimap (C12, Polish): the exe's per-city frame table 0x8008B080 (24 bytes per CITY: x / y
 * offset, width, height, toptile | fill << 8, units per pixel) gets Driver 2's map frame in the
 * CITY 3 entry while Chicago is chosen (the level init 0x800541E8 reads it), LA's otherwise. */
#define MAP_ENTRY3          (0x8008B080u + 3u * 24u)
static void minimap_vblank(int chi) {
    static uint32_t la[6];
    static int saved;
    if (!s_have_map) return;
    uint32_t cur[6];
    for (int i = 0; i < 6; i++) cur[i] = psx_mod_read_word(MAP_ENTRY3 + 4u * (uint32_t)i);
    int is_chi = !memcmp(cur, s_chi_map, sizeof cur);
    if (!saved && !is_chi && cur[2] != 0) { memcpy(la, cur, sizeof la); saved = 1; }
    if (!saved) return;
    const uint32_t* want = chi ? s_chi_map : la;
    if (memcmp(cur, want, sizeof cur))
        for (int i = 0; i < 6; i++) psx_mod_write_word(MAP_ENTRY3 + 4u * (uint32_t)i, want[i]);
}
/* Sky (C10, Polish): the level init sets the sky number gp+0xD7C from CITY (CITY 3: 2, rain 3,
 * at 0x8004EDE0 / 0x8004EDEC / 0x8004EE00, then reads SKY.BIN); the package's SKY.BIN carries
 * Chicago's skies as 13 day, 14 night, 15 rain, so these immediates name them while Chicago is
 * chosen. */
static void sky_vblank(int chi) {
    static const uint32_t addr[3] = { 0x8004EDE0u, 0x8004EDECu, 0x8004EE00u };
    if (!s_have_sky) return;
    for (int i = 0; i < 3; i++) {
        uint32_t la = i ? 3u : 2u;
        uint32_t want = 0x24020000u | (chi ? (i ? 15u : s_chi_night ? 14u : 13u) : la);
        uint32_t cur = psx_mod_read_word(addr[i]);
        uint32_t imm = cur & 0xFFFFu;
        if (cur != want && (cur & 0xFFFF0000u) == 0x24020000u && (imm == la || (imm >= 13u && imm <= 15u)))
            psx_mod_write_word(addr[i], want);
    }
}
/* EXPERIMENT ONLY (CHI_C45=1), not a fix: the wait below is deliberate. 0x80032F98 only asks to
 * wait while an AREA load runs (0x800969E8) and the car is within ~6 cells of the boundary towards
 * the new area (gp+0xAC0): it keeps the car out of the new area until its pages / models arrived.
 * Skipping it (part 2) lets the car in with stale textures / models. Real fix: area loads that
 * finish before the car gets there (earlier start, fewer bytes); see design_c45.md.
 * C45 loading stalls (13.10., chicago/design_c45.md): Driver 1's spool-sync loop 0x800334B4 waits
 * (VSync loop 0x80033534..0x800335B4) until the WHOLE spool queue is empty (busy flag 0x800972D4)
 * when the car needs the next region; at an area switch the area's pages + models sit ahead of the
 * region data. While Chicago is loaded: (1) the region entries (type 0, read as one stream) are
 * moved right behind the entry being read, and (2) the loop reads a "region data pending" word
 * instead of the busy flag. The two loop loads are guest instructions (PS1-native: the word lives
 * in main RAM, gp+0x2170, unused by the exe); the queue reorder and the pending word are kept by
 * this plugin for now (host-only prototype; guest-code version once validated, M8). */
#define SPOOL_QUEUE   0x800A7BA4u   /* 16-byte entries: +0 type (0 region, 1 page, 3 models), +2 sectors */
#define SPOOL_READ    0x800969ECu   /* index of the entry being read */
#define SPOOL_WRITE   0x800972B0u   /* next free index */
#define REGION_PENDING 0x800988E0u  /* gp+0x2170 */
#define SPOOL_MAX     59u           /* queue capacity (pair table at 0x800A7F54 follows) */
static const uint32_t s_c45_words[][3] = {      /* address, original, Chicago */
    { 0x8003351Cu, 0x8F820B64u, 0x8F822170u },   /* lw v0, 0xb64(gp) -> lw v0, 0x2170(gp): enter the wait */
    { 0x800335ACu, 0x8F820B64u, 0x8F822170u },   /* the same for the loop condition */
};
static int c45_enabled(void) {
    static int on = -1;
    if (on < 0) { const char* e = getenv("CHI_C45"); on = e && *e == '1'; }   /* off: see below */
    return on;
}
static void spool_entry(uint32_t i, uint32_t w[4]) {
    for (int k = 0; k < 4; k++) w[k] = psx_mod_read_word(SPOOL_QUEUE + 16u * i + 4u * (uint32_t)k);
}
static void spool_put(uint32_t i, const uint32_t w[4]) {
    for (int k = 0; k < 4; k++) psx_mod_write_word(SPOOL_QUEUE + 16u * i + 4u * (uint32_t)k, w[k]);
}
static void c45_vblank(int chi) {
    int on = chi && c45_enabled();
    switch_words(s_c45_words, sizeof s_c45_words / sizeof s_c45_words[0], on);
    if (!on) return;
    uint32_t r = psx_mod_read_word(SPOOL_READ), w = psx_mod_read_word(SPOOL_WRITE);
    if (w > SPOOL_MAX || r > w) { psx_mod_write_word(REGION_PENDING, 0); return; }   /* reset / inconsistent: hands off */
    /* (1) region block first. The reader runs on into the next entry without a new start only
     * inside a region block (0x80034CE0); pages and models are one entry per read, so entries
     * behind a non-region entry being read can be reordered safely. */
    if (r < w && (psx_mod_read_word(SPOOL_QUEUE + 16u * r) & 0xFFu) != 0u && r + 2u < w) {
        uint32_t ins = r + 1u, k = ins;
        while (k < w && (psx_mod_read_word(SPOOL_QUEUE + 16u * k) & 0xFFu) != 0u) k++;
        if (k < w && k > ins) {                        /* region block k..e-1 behind non-region entries */
            uint32_t e = k;
            while (e < w && (psx_mod_read_word(SPOOL_QUEUE + 16u * e) & 0xFFu) == 0u) e++;
            uint32_t n = e - k, blk[8][4], mv[4];
            if (n <= 8u) {
                for (uint32_t j = 0; j < n; j++) spool_entry(k + j, blk[j]);
                for (uint32_t j = k; j-- > ins;) { spool_entry(j, mv); spool_put(j + n, mv); }
                for (uint32_t j = 0; j < n; j++) spool_put(ins + j, blk[j]);
                fprintf(stdout, "driver.chicago: C45 region data (%u entries) moved from %u to %u (read %u, write %u)\n",
                        (unsigned)n, (unsigned)k, (unsigned)ins, (unsigned)r, (unsigned)w);
            }
        }
    }
    {   /* diagnostics: the queue whenever its length changes during an area load */
        static uint32_t last_w = 0xFFFFFFFFu, last_r = 0xFFFFFFFFu;
        if (psx_mod_read_word(0x800969E8u) && (w != last_w || r != last_r) && getenv("CHI_C45_LOG")) {
            char q[200]; int n = 0;
            for (uint32_t i = r; i < w && i < r + 24u && n < 180; i++) {
                uint32_t e = psx_mod_read_word(SPOOL_QUEUE + 16u * i);
                n += snprintf(q + n, sizeof q - (size_t)n, "%u:%u ", (unsigned)(e & 0xFFu), (unsigned)(e >> 16));
            }
            q[n] = 0;
            fprintf(stdout, "driver.chicago: C45 queue r %u w %u: %s\n", (unsigned)r, (unsigned)w, q);
        }
        last_w = w; last_r = r;
    }
    /* (2) region data pending: a region entry still queued or being read */
    uint32_t pending = 0;
    for (uint32_t i = r; i < w && !pending; i++)
        if ((psx_mod_read_word(SPOOL_QUEUE + 16u * i) & 0xFFu) == 0u) pending = 1;
    psx_mod_write_word(REGION_PENDING, pending);
}
/* C38 Play Again hang (13.10./14.10., FAN dumps 221640 / 225502): the region road/cell table decoder
 * 0x80035558 runs inside the CD callback (interrupt context); after a restart it can meet stale data
 * whose format word is not 0/1/2 and then printf "Ulp!!! error" from the interrupt - the CD interrupt
 * is never acknowledged, the reader stops, the spool-done wait 0x80033AF8 never ends (exception storm).
 * An unknown format now takes the format-0 path (cells filled 0xFFFF = empty), as for a region
 * without data. All cities (C38 also hit NY). One guest word; plugin switch now, exe patch later (M8). */
static const uint32_t s_c38_words[][3] = {
    { 0x80035670u, 0x14A20026u, 0x14A2FFCDu },   /* bne a1,v0,error(0x8003570C) -> bne a1,v0,fill-empty(0x800355A8) */
};
static void glow_offsets_vblank(void) {
    int chi = chicago_active();
    (void)s_c38_words;   /* C38: static exe patch now (exe_patches look_city_patches); no RAM rewrite */
    c45_vblank(chi);
    /* C45 part 3: the guest page loop (exe patch group CHI_C45_SKIP) reads the stable-page end from main RAM
     * (gp+0x2174, unused by the exe); 0 = no skipping, so every original city loads as before. Host-only
     * provisioning for now (M8: the PS1 path would carry it in the level or the exe). */
    {
        uint32_t want = chi ? s_stable_end : 0u;
        if (psx_mod_read_word(0x800988E4u) != want) psx_mod_write_word(0x800988E4u, want);
    }
    minimap_vblank(chi);
    sky_vblank(chi);
    switch_words(s_glow_words, sizeof s_glow_words / sizeof s_glow_words[0], chi);
    int chday = other_level_active() && !(s_virtual == V_CHICAGO && s_chi_night);
    /* C47 (14.10.): with the static exe patch (exe_patches look_city_patches) the CITY == 3 sites read
     * LOOK_CITY (0x8009789C: CITY, or 0x7F for Chicago by day) and C3 (0x80097898: 3, or 0x7F) from main
     * RAM; no code word is rewritten, so those functions stay native. Without it (older exe) the code
     * words are switched as before. */
    uint32_t look = chday ? 0x7Fu : psx_mod_read_word(CITY_WORD), c3 = chday ? 0x7Fu : 3u;
    if (psx_mod_read_word(0x8009789Cu) != look) psx_mod_write_word(0x8009789Cu, look);
    if (psx_mod_read_word(0x80097898u) != c3) psx_mod_write_word(0x80097898u, c3);
    /* C51: CARSET_CITY (0x800978A0) picks the damage zone tables (exe patch at 0x8003E5A8): the city whose
     * car set the loaded Chicago level carries (Miami's by day), else CITY */
    uint32_t cs = chicago_active() ? (s_chi_night ? (s_carsets >> 8) & 0xFFu : s_carsets & 0xFFu)
                                   : psx_mod_read_word(CITY_WORD);
    if (psx_mod_read_word(0x800978A0u) != cs) psx_mod_write_word(0x800978A0u, cs);
    /* C17: DROWN_RANGE (0x800978A8, exe_patches DROWN_EDGE): a car with a wheel on sea ground whose y lies in
     * [-1120, -1120 + range) drowns even if its centre cell is not water; Driver 2 cities only (0 = D1 rule) */
    uint32_t dr = chi ? 620u : 0u;
    if (psx_mod_read_word(0x800978A8u) != dr) psx_mod_write_word(0x800978A8u, dr);
    /* C42 step 1: car-set city 4 = Driver 2 traffic cars: their civ damage tables at 0x800A0E20 (verts) /
     * 0x800A11A4 (polys), where the exe's table entry 4 points (exe_patches C42_TABLES) */
    if (cs == 4u && s_dmg_civ_n == 540u && psx_mod_read_word(0x800A0E20u) != s_dmg_civ[0]) {
        for (uint32_t i = 0; i < 540u; i++) psx_mod_write_word(0x800A0E20u + 4u * i, s_dmg_civ[i]);
        fprintf(stdout, "driver.chicago: C42 Driver 2 civ damage tables written to 0x800A0E20\n");
    }
    /* C42/C53: car set 4's cosmetics rows (wheel / light positions) at 0x800A16A0, where entry 4 of the
     * exe's base table points (exe_patches COSMETICS); LoadCosmetics copies them at level load */
    if (cs == 4u) {
        int t = s_chi_night ? 1 : 0;
        if (s_cos_n[t] == 200u && psx_mod_read_word(0x800A16A0u) != s_cos[t][0]) {
            for (uint32_t i = 0; i < 200u; i++) psx_mod_write_word(0x800A16A0u + 4u * i, s_cos[t][i]);
            fprintf(stdout, "driver.chicago: C42 cosmetics rows (%s) written to 0x800A16A0\n", t ? "night" : "day");
        }
    }
    /* The exe patches live in the generated native code, not in RAM (RAM keeps the original image), so the
     * static patch cannot be detected by reading RAM; plugin and generated code are built together from one
     * source state, so this build always has it. s_day_words stays only as documentation of the sites. */
    (void)s_day_words;
}

static void area_switch_guard_vblank(void) {
    driver_personal_fps_tick(1);                          /* FPS stats for test tools (driver_personal.c) */
    surface_select_vblank();
    chicago_slot_vblank();
    glow_offsets_vblank();
    if (s_sea_level) {                                   /* Chicago's water lies 1084 below the street */
        if (s_level_format < 0 && psx_mod_game_started() && !psx_mod_read_word(AREA_LOADING_FLAG))
            s_level_format = level_has_switch_pads();
        psx_mod_write_word(SEA_LEVEL_ADDR, chicago_active() && s_level_format == 1
                                           ? (uint32_t)CHI_SEA_LEVEL : 0u);
    }
    if (!s_empty_model || !psx_mod_game_started())
        return;

    uint32_t flag = psx_mod_read_word(AREA_LOADING_FLAG);
    uint32_t area = psx_mod_read_word(CURRENT_AREA);
    uint32_t spool = psx_mod_read_word(MODEL_SPOOL_BUFFER) & 0x1FFFFFFFu;
    /* placeholders: a main-RAM model (not streamed) preceded by a zero size */
    for (uint32_t i = 0; i < MODEL_TABLE_ENTRIES; i++) {
        uint32_t p = psx_mod_read_word(MODEL_TABLE_ADDR + 4u * i) & 0x1FFFFFFFu;
        if (p < 0x10000u || p >= 0x200000u || (spool && p >= spool && p < spool + MODEL_SPOOL_BYTES))
            continue;
        if (psx_mod_read_word(0x80000000u | (p - 4u)) == 0)
            psx_mod_write_word(MODEL_TABLE_ADDR + 4u * i, s_empty_model);
    }
    /* a new switch: the flag rises, or the area changes while it is still up
     * (a previous load's relocation may be pending, keeping the flag set).
     * Normally area_switch_entry() below has already done this. */
    if ((flag && !s_last_flag) || (flag && area != s_last_area))
        redirect_spool_entries();
    s_last_flag = flag;
    s_last_area = area;
}

/* C33: the switch (0x8003413C) sets the loading flag and calls 0x80033B10, which
 * queues the incoming area's texture pages; they are staged at spool buffer +
 * 0xA000 (block 20, "ori a1,0xa000" at 0x80033B2C), i.e. inside the outgoing
 * area's models when it has more than 20 model blocks (12 Chicago areas, LA
 * too). The first sector lands ~13 ms after the request, often before the next
 * vblank redirects the entries: a model read from texel data (vertex count
 * 0x4F8D) ran the vertex loop over the scratchpad into the I/O registers (I_MASK
 * and timer 1 mode = 0x071A), vblank was masked and VSync waited forever (user
 * hang 193318, region 229, 9 -> 1). This function-entry hook (game.toml
 * [recompiler] mod_function_entry_funcs) runs at the entry of 0x80033B10,
 * before any request is queued, so no entry can point into the buffer while
 * the CD writes it. */
#define AREA_TEXTURE_QUEUE 0x80033B10u

#define CITY               0x80096834u   /* 3 = Chicago (chicago-la feature); other cities untouched */

static void area_switch_entry(struct CPUState* cpu, uint32_t address) {
    (void)cpu; (void)address;
    if (!s_empty_model || !chicago_active())
        return;
    uint32_t n = redirect_spool_entries();
    s_last_flag = psx_mod_read_word(AREA_LOADING_FLAG);
    s_last_area = psx_mod_read_word(CURRENT_AREA);
    fprintf(stdout, "driver.chicago: area switch to %u: %u spool entries redirected at the queue\n",
            (unsigned)s_last_area, (unsigned)n);
}

/* C50 (14.10.): the D1 extras (Newtown, Interview, Training) run LA's Take a Ride script (mission 0x7C)
 * with the CITY opcode switched. Its buffer is a heap block (0x80068360: *0x80097098, 0xC00 bytes); in
 * those levels a region read (CD DMA) lands on it, and Play Again parses it again: the parser
 * 0x80068928(a0 = start, a1 = end) then sat on a size-0 "opcode" forever (game frame 1, car y 4524).
 * This function-entry hook (game.toml mod_function_entry_funcs) moves the script of an extra level into
 * a static area no code uses (0x800A0D00..0x800A0E20, C48 RAM survey) and points the parse there
 * (a0/a1, buffer pointer gp+0x101C, parser struct +0x2B8 / +0x2B4); a restart's loader then reads the
 * script straight into that area. Host-only (M8: a guest version allocates the script buffer there). */
#define MISSION_PARSE      0x80068928u
#define MISSION_BUF_PTR    0x8009778Cu   /* gp+0x101C */
#define MISSION_PTR        0x800C71BCu   /* parser struct 0x800C6F04 + 0x2B8 */
#define MISSION_END_PTR    0x800C71B8u   /* parser struct 0x800C6F04 + 0x2B4 */
#define MISSION_SAFE       0x800A0D00u
#define MISSION_SAFE_END   0x800A0E20u
#define MUSIC_XOR          0x800988ECu   /* gp+0x217C: XORed into the song (exe_patches MUSIC_SELECT) */
static void mission_parse_entry(struct CPUState* cpu, uint32_t address) {
    (void)address;
    /* Chicago music: the loader stores (mission + 3) & 7 ^ MUSIC_XOR right after this parse; Chicago gets
     * song 8 (day) / 9 (night) of the relocated MUSIC.BIN, every other level 0 (its own song) */
    if (s_slot_enabled) {
        uint32_t x = 0;
        if (s_have_music && chicago_active())
            x = (s_chi_night ? 9u : 8u) ^ ((cpu->gpr[16] + 3u) & 7u);
        if (psx_mod_read_word(MUSIC_XOR) != x) {
            psx_mod_write_word(MUSIC_XOR, x);
            fprintf(stdout, "driver.chicago: music word %u (Chicago %s)\n", (unsigned)x,
                    x ? (s_chi_night ? "night: song 9" : "day: song 8") : "off");
        }
    }
    if (!s_slot_enabled || !is_extra(s_virtual) || !extra_via_la() || psx_mod_read_word(MISSION_NUMBER) != 0x7Cu)
        return;
    uint32_t a0 = cpu->gpr[4] | 0x80000000u, a1 = cpu->gpr[5] | 0x80000000u;
    if (a1 <= a0 || a1 - a0 > MISSION_SAFE_END - MISSION_SAFE)
        return;
    uint32_t n = a1 - a0;
    if (a0 != MISSION_SAFE)
        for (uint32_t i = 0; i < n; i += 4u) psx_mod_write_word(MISSION_SAFE + i, psx_mod_read_word(a0 + i));
    /* the script read again from MISSION.BLK names LA's start: move it before the parse (the 30-vblank
     * rescan only covers the original buffer range) */
    for (uint32_t i = 0; i + 8u < n; i += 4u)
        if (psx_mod_read_word(MISSION_SAFE + i) == 0x13u
            && (int32_t)psx_mod_read_word(MISSION_SAFE + i + 4u) == s_la_start[0]
            && (int32_t)psx_mod_read_word(MISSION_SAFE + i + 8u) == s_la_start[1]) {
            psx_mod_write_word(MISSION_SAFE + i + 4u, (uint32_t)s_level_start[s_virtual][0]);
            psx_mod_write_word(MISSION_SAFE + i + 8u, (uint32_t)s_level_start[s_virtual][1]);
        }
    cpu->gpr[4] = MISSION_SAFE;
    cpu->gpr[5] = MISSION_SAFE + n;
    psx_mod_write_word(MISSION_BUF_PTR, MISSION_SAFE);
    psx_mod_write_word(MISSION_PTR, MISSION_SAFE);
    psx_mod_write_word(MISSION_END_PTR, MISSION_SAFE + n);
    fprintf(stdout, "driver.chicago: C50 mission script (%u bytes) parsed from %#x (was %#x), level %d\n",
            (unsigned)n, (unsigned)MISSION_SAFE, (unsigned)a0, s_virtual);
}

PSX_MOD_CONSTRUCTOR(driver_chicago_register) {
    psx_mod_register_activation_plugin("driver.model-table", model_table_activate);
    psx_mod_register_vblank_plugin("driver.model-table", area_switch_guard_vblank);   /* also runs surface_select_vblank */
    psx_mod_register_function_entry_plugin("driver.model-table", AREA_TEXTURE_QUEUE, area_switch_entry);
    psx_mod_register_activation_plugin("driver.chicago-slot", chicago_slot_activate);
    psx_mod_register_function_entry_plugin("driver.chicago-slot", MISSION_PARSE, mission_parse_entry);
}
