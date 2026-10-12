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

#include "mod_plugins.h"

#define MODEL_TABLE_ADDR    0x9F000000u   /* must match exe_patches.NEW_BASE */
#define MODEL_TABLE_ENTRIES 2048u
#define CELL_OBJECTS_ADDR   0x9F002000u   /* must match exe_patches.CELL_OBJECTS_ADDR */
#define CELL_OBJECTS_BYTES  (512u * 1024u)

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

static void model_table_activate(void) {
    if (alloc_fixed("model table", MODEL_TABLE_ENTRIES * 4u, 16u, MODEL_TABLE_ADDR) &&
        alloc_fixed("cell object buffer", CELL_OBJECTS_BYTES, 16u, CELL_OBJECTS_ADDR))
        make_empty_model();
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
#define SELECT_TOLERANCE 100   /* a plane up to this far above the wheel point still counts as ground (suspension, pitch) */

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

/* Put the plane nearest ground height y first in the cell's surface (if marked). */
static void select_surface(uint32_t cell, int32_t px, int32_t pz, int32_t y) {
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
    /* The ground is the highest plane that is not above the wheel (y = car centre
     * minus CAR_CENTRE, plus a tolerance for a compressed suspension): a lower plane
     * can never catch a car that bounced up (wallclimb), a higher one can never pull
     * it down (rampwedge). A car below every plane gets the lowest one. */
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
    /* The vblank hook runs from the interrupt check and can land inside the
     * engine's polygon loop. The generated polygons share corners and vertex
     * count and differ only in the plane, so only the 4 plane words are swapped
     * (d last): a torn read mixes at worst a slope with the other plane's d,
     * i.e. an error of a few tens of units, never the other level. */
    uint32_t p0 = surf + 8u + 32u, pb = surf + 8u + SIPOLY_BYTES * (uint32_t)best + 32u;
    for (uint32_t k = 0; k < 16u; k += 4u) {
        uint32_t w0 = psx_mod_read_word(p0 + k), wb = psx_mod_read_word(pb + k);
        psx_mod_write_word(p0 + k, wb);
        psx_mod_write_word(pb + k, w0);
    }
}

#define SPOOL_SECTORS_LEFT  0x800971F8u   /* > 0 while an area / region spool is in flight */
#define SELECT_IDLE_VBLANKS 60            /* stay idle this long after loading / spooling / restart */
static uint32_t s_select_idle = SELECT_IDLE_VBLANKS;

static void surface_select_vblank(void) {
    if (getenv("CHI_NO_SELECT"))                  /* bisection switch */
        return;
    if (!psx_mod_game_started())
        return;
    /* Never touch surface data while cell / level data is being (re)loaded: level
     * start, area switches, region spools and Play Again (C26 hardening). */
    if (psx_mod_read_word(AREA_LOADING_FLAG) || psx_mod_read_word(SPOOL_SECTORS_LEFT)) {
        s_select_idle = SELECT_IDLE_VBLANKS;
        return;
    }
    if (s_select_idle) {
        s_select_idle--;
        return;
    }
    int32_t x = rd32(PLAYER_POS), y = rd32(PLAYER_POS + 4u) - CAR_CENTRE, z = rd32(PLAYER_POS + 8u);
    for (int dz = -1; dz <= 1; dz++)
        for (int dx = -1; dx <= 1; dx++) {
            int32_t px = 0, pz = 0;
            uint32_t cell = road_cell(x + dx * 1500, z + dz * 1500, &px, &pz);
            if (cell)
                select_surface(cell, px, pz, y);
        }
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
static void area_switch_guard_vblank(void) {
    surface_select_vblank();
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
    if (!s_empty_model || psx_mod_read_word(CITY) != 3u)
        return;
    uint32_t n = redirect_spool_entries();
    s_last_flag = psx_mod_read_word(AREA_LOADING_FLAG);
    s_last_area = psx_mod_read_word(CURRENT_AREA);
    fprintf(stdout, "driver.chicago: area switch to %u: %u spool entries redirected at the queue\n",
            (unsigned)s_last_area, (unsigned)n);
}

PSX_MOD_CONSTRUCTOR(driver_chicago_register) {
    psx_mod_register_activation_plugin("driver.model-table", model_table_activate);
    psx_mod_register_vblank_plugin("driver.model-table", area_switch_guard_vblank);   /* also runs surface_select_vblank */
    psx_mod_register_function_entry_plugin("driver.model-table", AREA_TEXTURE_QUEUE, area_switch_entry);
}
