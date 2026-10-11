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

static void area_switch_guard_vblank(void) {
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
     * (a previous load's relocation may be pending, keeping the flag set) */
    if ((flag && !s_last_flag) || (flag && area != s_last_area)) {
        uint32_t lo = psx_mod_read_word(MODEL_SPOOL_BUFFER) & 0x1FFFFFFFu;
        uint32_t hi = lo + MODEL_SPOOL_BYTES;
        if (lo) {
            for (uint32_t i = 0; i < MODEL_TABLE_ENTRIES; i++) {
                uint32_t p = psx_mod_read_word(MODEL_TABLE_ADDR + 4u * i) & 0x1FFFFFFFu;
                if (p >= lo && p < hi)
                    psx_mod_write_word(MODEL_TABLE_ADDR + 4u * i, s_empty_model);
            }
        }
    }
    s_last_flag = flag;
    s_last_area = area;
}

PSX_MOD_CONSTRUCTOR(driver_chicago_register) {
    psx_mod_register_activation_plugin("driver.model-table", model_table_activate);
    psx_mod_register_vblank_plugin("driver.model-table", area_switch_guard_vblank);
}
