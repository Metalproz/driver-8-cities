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
#include <math.h>

#include "mod_plugins.h"
#include "cpu_state.h"
#include "driver_personal.h"
#include "gpu.h"

/* M3 (Havana slot): each Driver 2 city has its own asset set: Chicago's in assets/, Havana's in assets/havana/ (built
 * with build_package CHI_HAVANA_DAY / _NIGHT). One set is loaded at a time (city_assets_load), the one of the city the
 * selector chose; every Driver 2 feature below reads the loaded set. */
#define ASSET_ROOT "mods/packages/driver.chicago/0.1.0/assets/"
/* M3 / Q68 (user 68 B, 27.10.): every Driver 2 city is a virtual city run in Driver 1's CITY slot D2_SLOT_CITY (LA's 3).
 * A D2 city id (0 Chicago, 1 Havana, 2 Las Vegas, 3 Rio) is kept apart from the slot: asset set, slot sidecar, songs,
 * level variant codes and glows key on the id; only chicago_active() / the level entry know the slot. A later move to
 * an own CITY index changes D2_SLOT_CITY (and the exe tables), not the per-city code.
 * PS1 path (Milestone 8, host-only today): the choice is a host plugin decision (asset set from the package, level
 * table entry 3 rewritten). Guest-side it becomes one guest word (the variant code, already mirrored in VARIANT_WORD and
 * the replay header) read by a small exe routine at the level load that selects the level path / CD position and the
 * city's data block (sidecar tables in guest RAM) instead of the plugin. */
#define D2_SLOT_CITY 3u
enum { D2C_CHICAGO = 0, D2C_HAVANA = 1, D2C_VEGAS = 2, D2C_RIO = 3, D2C_N = 4 };
static const struct { const char* name; const char* dir; const char* slot; const char* preview; uint32_t song_base, variant;
                      int glow; } s_d2c[D2C_N] = {
    { "Chicago",   "",        "chicago_slot.bin", "chicago_preview.bin",  8u, 1u, 2 },
    { "Havana",    "havana/", "slot.bin",         "preview.bin",         10u, 3u, 3 },
    { "Las Vegas", "vegas/",  "slot.bin",         "preview.bin",         12u, 6u, 4 },
    { "Rio",       "rio/",    "slot.bin",         "preview.bin",         14u, 8u, 5 },
};
static int s_assets_city = 0;                    /* the loaded asset set = D2 city id (assets/<dir>) */
static int s_have_city[D2C_N];                   /* the package carries assets/<dir><slot> */
static int s_have_havana;                        /* the page-2 Havana row is live (Havana's set, or the debug override) */
static const char* apath(const char* name) {
    static char buf[4][192]; static int k;
    char* b = buf[k++ & 3];
    snprintf(b, sizeof buf[0], "%s%s%s", ASSET_ROOT, s_d2c[s_assets_city].dir, name);
    return b;
}
/* test switch CHI_D2_ROW_CITY=N (2 Las Vegas, 3 Rio; Polish / runner copies): page 2's Havana row loads D2 city N's set
 * (its rows are wired once the levels land); unset / 0 / 1 = Havana */
static int row_city_override(void) {
    static int v = -1;
    if (v < 0) { const char* e = getenv("CHI_D2_ROW_CITY"); v = e ? atoi(e) : 0; if (v < 2 || v >= D2C_N) v = 0; }
    return v;
}

#define MODEL_TABLE_ADDR    0x80115600u   /* must match exe_patches.NEW_BASE (S4a: main RAM; the 8 KB mod block at
                                             0x9F000000 stays allocated so the other blocks keep their addresses) */
#define MODEL_TABLE_ENTRIES 2048u
#define CELL_OBJECTS_ADDR   0x9F002000u   /* must match exe_patches.CELL_OBJECTS_ADDR */
#define CELL_OBJECTS_BYTES  (512u * 1024u)
#define SEA_LEVEL_ADDR      0x80097888u   /* must match exe_patches.SEA_LEVEL_ADDR (S4a: RAM word gp+0x1118) */
#define S4_FLAG_ADDR        0x80097890u   /* S4a: gp+0x1120, exe cave S4C: 1 = cell objects on the heap when they fit */
#define CHI_SEA_LEVEL       (-1084)       /* y up: Chicago's water surface, convert.WATER_LEVEL below the street */
/* C84 (23.10.): since S4a the model table lives in main RAM (0x80115600), which the frontend and the FMV player use
 * outside a level: the vblank's table work (placeholders, spool redirect, carry release) wrote s_empty_model into the
 * FMV player's memory -> Undercover > New Game crashed in the intro FMV (jump to 0x9F079F08). The table is touched only
 * while a level runs: s_lvl_beat = the vblank of the last in-level hook call (MapHeight / FindSurface / DrawCarWheels /
 * far-car LOD / area texture queue / mission parse), within LVL_BEAT_MAX vblanks. */
static uint32_t s_vbl_n, s_lvl_beat, s_lvl_seen;
#define LVL_BEAT() do { s_lvl_beat = s_vbl_n; s_lvl_seen = 1u; } while (0)
#define LVL_BEAT_MAX 30u
#define CITY_NOW            0x80096834u   /* 3 = Chicago */
#define MENU_ADDR           0x9F082110u   /* must match build_package.MENU_ADDR: row table 5 x 16 B */
#define MENU_LABELS         (MENU_ADDR + 0x50u)   /* 5 label pointers */
#define MENU_BYTES          0x200u  /* row table 9 x 16, list at +0xC0, strings at +0x180 */
#define CAR_TABLES_BYTES    0xC00u        /* C42E player zone rows: verts 4 x 300 at +0, polys 4 x 420 at +1200 */

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
static uint32_t s_car_tables;   /* C42E: player zone rows block (allocated when first needed; 0x9F082310 = FPS overlay) */
static void model_table_activate(void) {
    if (alloc_fixed("model table slot (unused since S4a)", MODEL_TABLE_ENTRIES * 4u, 16u, 0x9F000000u) &&
        alloc_fixed("cell object buffer", CELL_OBJECTS_BYTES, 16u, CELL_OBJECTS_ADDR)) {
        make_empty_model();
        /* the sea level the ground query adds for "sea" water cells (exe patch, C35);
         * 0 = Driver 1's own (other cities) */
        if (s_empty_model && alloc_fixed("flag block slot (sea level / Chicago flag: RAM words since S4a)", 16u, 16u, 0x9F082100u)) {
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

static int chicago_active(void);
/* C37 phase 1 (Infrastructure 17.10., user's Option B): Driver 2's own road surface for Driver 2 cities.
 * assets/d2_surface.bin (d2surf_asset.py, CHI_D2_SURF=1 at package time) holds Driver 2's per-region surface blocks.
 * At the entry of MapHeight (0x8001F5B0) and FindSurfaceD2 (0x8001EEB4) (game.toml mod_function_entry_funcs) this hook
 * looks the query point up exactly as Driver 2 does (dr2roads.c sdGetCell: level list by the wheel's height, BSP,
 * sdHeightOnPlane) and writes that plane, re-expressed in the cell's rotated local coordinates, into polygon 0 of the
 * cell's ROADSURF surface with a full-cell footprint; the unchanged engine loop then takes it as its first hit (height
 * and the normal for the car's tilt). Cells without a surface or Driver 2 sea keep Driver 1's answer (the surface's
 * own polygon 0 is restored). The vblank plane selector is off while this is active. Host-only (Milestone 8 list:
 * phase 2 = the same lookup as guest code in dead space + per-region blocks streamed with the region spool). */
#define MAPHEIGHT_FN   0x8001F5B0u
#define FINDSURF_FN    0x8001EEB4u
static uint32_t s_d2sf_scratch;
static int s_d2sf_stage = 99;                 /* mod memory: one SURFACEINFO + one SIPOLY (60 bytes) */
#define D2SF_SCRATCH   s_d2sf_scratch
static uint8_t* s_d2sf;                       /* the asset */
static long s_d2sf_size;
static int32_t s_d2sf_across, s_d2sf_halfx, s_d2sf_halfz, s_d2sf_scale, s_d2sf_offx, s_d2sf_offz;
static int32_t s_d2sf_nreg, s_d2sf_ncurve;
static const uint8_t* s_d2sf_regbuf[4096];
static int32_t s_d2sf_reglen[4096];
static const int32_t* s_d2sf_curves;
static uint8_t s_d2sf_saved[900][52];
static uint8_t s_d2sf_isaved[900], s_d2sf_dirty[900];
static int16_t s_d2sf_cos[4096], s_d2sf_sin[4096];   /* filled at load (the BSP walk ran libm per node) */

static int32_t le32(const uint8_t* p) { return (int32_t)((uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24); }
static int16_t le16(const uint8_t* p) { return (int16_t)((uint16_t)p[0] | (uint16_t)p[1] << 8); }

static void d2sf_load(void) {
    if (s_d2sf)
        return;
    FILE* f = fopen(apath("d2_surface.bin"), "rb");
    if (!f)
        return;
    fseek(f, 0, SEEK_END);
    s_d2sf_size = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t* b = (uint8_t*)malloc((size_t)s_d2sf_size);
    if (!b || fread(b, 1, (size_t)s_d2sf_size, f) != (size_t)s_d2sf_size || memcmp(b, "D2SF", 4) != 0) {
        free(b); fclose(f); return;
    }
    fclose(f);
    s_d2sf_across = le32(b + 8); s_d2sf_halfx = le32(b + 12); s_d2sf_halfz = le32(b + 16);
    s_d2sf_scale = le32(b + 20); s_d2sf_offx = le32(b + 24); s_d2sf_offz = le32(b + 28);
    s_d2sf_nreg = le32(b + 32); s_d2sf_ncurve = le32(b + 36);
    for (int32_t i = 0; i < s_d2sf_nreg; i++) {
        int32_t idx = le32(b + 40 + 12 * i), off = le32(b + 44 + 12 * i), len = le32(b + 48 + 12 * i);
        if (idx >= 0 && idx < 4096 && off > 0 && off + len <= s_d2sf_size) { s_d2sf_regbuf[idx] = b + off; s_d2sf_reglen[idx] = len; }
    }
    s_d2sf_curves = (const int32_t*)(b + 40 + 12 * s_d2sf_nreg);
    for (int a = 0; a < 4096; a++) {
        s_d2sf_cos[a] = (int16_t)lround(4096.0 * cos((double)a * 6.283185307179586 / 4096.0));
        s_d2sf_sin[a] = (int16_t)lround(4096.0 * sin((double)a * 6.283185307179586 / 4096.0));
    }
    if (!s_d2sf_scratch) s_d2sf_scratch = psx_mod_alloc_guest_memory(64u, 16u);
    if (!s_d2sf_scratch) { free(b); return; }
    s_d2sf = b;
    fprintf(stdout, "driver.chicago: C37 Driver 2 surface lookup on (%d regions, %ld bytes)\n", (int)s_d2sf_nreg, s_d2sf_size);
}

/* M3: another city's asset set: drop the loaded surface asset (d2sf_load reads the new one on its next call) and the
 * saved Driver 1 surface records (they belong to the previous city's level) */
static void d2sf_unload(void) {
    free(s_d2sf); s_d2sf = NULL; s_d2sf_size = 0; s_d2sf_nreg = 0;
    memset(s_d2sf_regbuf, 0, sizeof s_d2sf_regbuf); memset(s_d2sf_reglen, 0, sizeof s_d2sf_reglen);
    memset(s_d2sf_isaved, 0, sizeof s_d2sf_isaved); memset(s_d2sf_dirty, 0, sizeof s_d2sf_dirty);
}

static int32_t d2sf_rcos(int32_t a) { return s_d2sf_cos[a & 4095]; }
static int32_t d2sf_rsin(int32_t a) { return s_d2sf_sin[a & 4095]; }
static int32_t sbits32(uint32_t v, int lo, int n) {
    int32_t x = (int32_t)((v >> lo) & ((1u << n) - 1u));
    return (x & (1 << (n - 1))) ? x - (1 << n) : x;
}

/* sdGetCell for a Driver 2 point (x, z, y down): plane record pointer (12 bytes) or NULL (sea / no data) */
static const uint8_t* d2sf_cell(int32_t x, int32_t z, int32_t vy) {
    int32_t cx = x - 512, cz = z - 512;
    int32_t rx = (cx + s_d2sf_halfx) >> 16, rz = (cz + s_d2sf_halfz) >> 16;
    if (rx < 0 || rz < 0 || rx >= s_d2sf_across) return NULL;
    int32_t ridx = rz * s_d2sf_across + rx;
    if (ridx < 0 || ridx >= 4096 || !s_d2sf_regbuf[ridx]) return NULL;
    const uint8_t* buf = s_d2sf_regbuf[ridx];
    int32_t len = s_d2sf_reglen[ridx];
    if (le16(buf) != 2) return NULL;
    uint32_t po = (uint16_t)le16(buf + 2), lo = (uint16_t)le16(buf + 4), no = (uint16_t)le16(buf + 6);
    int32_t lx = cx & 1023, ly = cz & 1023;
    uint32_t so = 8u + 2u * (uint32_t)(((cx >> 10) & 63) + ((cz >> 10) & 63) * 64);
    if (so + 2 > (uint32_t)len) return NULL;
    int32_t s = le16(buf + so);
    if (s == -1) return NULL;
    uint32_t sp = 0;                            /* byte offset of the current 'surface' short when inside a list */
    int inlist = 0;
    if ((s & 0x6000) == 0x2000) {
        sp = lo + 2u * (uint32_t)(s & 0x1FFF);
        for (int k = 0; k < 16; k++) {
            if (sp + 4 > (uint32_t)len) return NULL;
            int32_t thr = le16(buf + sp);
            if (-256 - vy > thr) { sp += 4; if (le16(buf + sp) == -0x8000) break; }
            else break;
        }
        sp += 2;
        inlist = 1;
        s = le16(buf + sp);
    }
    for (int guard = 0; guard < 8 && (s & 0x4000); guard++) {
        uint32_t np = no + 4u * (uint32_t)(s & 0x3FFF);
        for (int k = 0; k < 64; k++) {
            if (np + 4 > (uint32_t)len) return NULL;
            uint32_t v = (uint32_t)le32(buf + np);
            if ((int32_t)v >= 0) break;
            int32_t angle = sbits32(v, 0, 11), dist = sbits32(v, 11, 12), off = sbits32(v, 23, 8);
            int32_t dot = ly * d2sf_rcos(angle) - lx * d2sf_rsin(angle);
            np += (dot < dist * 4096) ? 4u : 4u * (uint32_t)off;
        }
        int32_t r = le16(buf + np);
        if (r == 0x7FFF) {
            if (!inlist) return NULL;
            sp += 4;                            /* next level of the list */
            if (sp + 2 > (uint32_t)len) return NULL;
            s = le16(buf + sp);
            continue;
        }
        s = r;
    }
    if (s < 0) return NULL;
    uint32_t pp = po + 12u * (uint32_t)s;
    if (pp + 12 > (uint32_t)len || le32(buf + pp) == -1) return NULL;
    return buf + pp;
}

static int32_t d2sf_height(const uint8_t* pl, int32_t x, int32_t z) {
    int32_t surf = le16(pl), a = le16(pl + 2), b = le16(pl + 4), c = le16(pl + 6), d = le32(pl + 8);
    if (((d >> 1) ^ d) & 0x40000000) return d ^ 0x40000000;
    if ((surf & 0xE000) == 0x4000 && b == 0 && s_d2sf_curves) {
        int32_t k = (surf & 0x1FFF) - 32;
        if (k >= 0 && k < s_d2sf_ncurve) {
            const int32_t* cv = s_d2sf_curves + 4 * k;
            int32_t ang = (int32_t)lround(atan2((double)(cv[1] - z), (double)(cv[0] - x)) * 4096.0 / 6.283185307179586) & 0xFFF;
            return (cv[2] * ((ang + 2048) & 0xFFF)) / 4096 - cv[3];
        }
    }
    if (b) {
        if (b == 0x4000) return -d;
        int64_t lx = (int64_t)a * (((x - 512) & 0xFFFF) + 512), ly = (int64_t)c * (((z - 512) & 0xFFFF) + 512);
        return -d - (int32_t)((lx + ly) / b);
    }
    return 0;
}

/* entry hook for MapHeight / FindSurfaceD2: a0 = the query position (x, y down, z) */
extern uint8_t* g_psx_ram;
static inline uint32_t fr32u(uint32_t a) {
    if ((a & 0x1FFFFFFFu) >= 0x200000u) return psx_mod_read_word(a);   /* scratchpad / mod memory */
    uint32_t v; memcpy(&v, g_psx_ram + (a & 0x1FFFFCu), 4); return v;
}
static inline int32_t fr32(uint32_t a) { return (int32_t)fr32u(a); }
static inline int32_t fr16(uint32_t a) {
    if ((a & 0x1FFFFFFFu) >= 0x200000u) return (int16_t)psx_mod_read_half(a);
    int16_t v; memcpy(&v, g_psx_ram + (a & 0x1FFFFEu), 2); return v;
}
/* road_cell with direct RAM reads (the hook runs for every MapHeight / FindSurfaceD2 call) */
static uint32_t road_cell_fast(int32_t x, int32_t z) {
    int32_t w = fr32(RM_HEADER), h = fr32(RM_HEADER + 4u);
    int32_t sx = x + fr32(RM_HEADER + 8u), sz = fr32(RM_HEADER + 12u) + 750 - z;
    if (sx < 0 || sz < 0 || w <= 0 || h <= 0) return 0;
    int32_t col = sx / 1500, row = sz / 1500;
    if (col >= w || row >= h) return 0;
    int32_t ca = (col & 0x7F) + ((col & ~0x7F) >> 4), ra = (row & 0x7F) + ((row & ~0x7F) >> 4);
    if (ca >= 120) ca -= 120;
    if (ra >= 120) ra -= 120;
    int32_t q = 0, par = fr32(RM_PARITY) & 1;
    if (ca >= 60) { ca -= 60; q = 1; }
    if (ra >= 60) { ra -= 60; if (!par) q += 2; }
    else if (par) q += 2;
    uint32_t table = fr32u(RM_TABLES + 4u * (uint32_t)q);
    if ((table & 0x1FFFFFFFu) < 0x10000u || (table & 0x1FFFFFFFu) >= 0x200000u) return 0;
    return fr32u(table + 4u * (uint32_t)ca + 240u * (uint32_t)ra);
}
static void d2sf_entry(struct CPUState* cpu, uint32_t address) {
    (void)address;
    LVL_BEAT();
    static int tried = -1;                            /* M3: the city whose asset was tried last */
    if (!s_d2sf && tried != s_assets_city) { tried = s_assets_city; d2sf_load(); }
    if (!s_d2sf || !chicago_active())
        return;
    {   static int stage = -1;
        if (stage < 0) { const char* e = getenv("CHI_D2SF_STAGE"); stage = e && *e ? atoi(e) : 99; }
        if (stage == 0) return;
        s_d2sf_stage = stage; }
    uint32_t pos = cpu->gpr[4];
    int32_t x = fr32(pos), y = fr32(pos + 4u), z = fr32(pos + 8u);
    int32_t ox = fr32(RM_HEADER + 8u), oz = fr32(RM_HEADER + 12u), w = fr32(RM_HEADER), h = fr32(RM_HEADER + 4u);
    int32_t sx = ox + x, sz = oz - (z - 750);
    if (sx < 0 || sz < 0 || w <= 0 || h <= 0 || sx / 1500 >= w || sz / 1500 >= h)
        return;
    uint32_t cell = road_cell_fast(x, z);
    if (s_d2sf_stage == 1) return;
    uint32_t type = (cell >> 16) & 0x3FFu;
    {   static int dbg = -1; static uint32_t n;
        if (dbg < 0) dbg = getenv("CHI_D2SF_DEBUG") != NULL;
        if (dbg && (n++ % 997u) == 0u) {
            double sc_ = (double)s_d2sf_scale / 65536.0;
            fprintf(stdout, "driver.chicago: d2sf q %d,%d,%d cell %08x type %u surf %08x d2pl %p\n", (int)x, (int)y, (int)z,
                    (unsigned)cell, (unsigned)type, (unsigned)(type < 900u ? psx_mod_read_word(SURF_PTRS + 4u * type) : 0u),
                    (const void*)d2sf_cell((int32_t)lround((x - s_d2sf_offx) / sc_), (int32_t)lround((z - s_d2sf_offz) / sc_), (int32_t)lround(y / sc_)));
        } }
    if (!cell || type >= 900u)
        return;
    {   /* Driver 1 water cells (model flags2 0x4000: waves, drowning) keep Driver 1's water: the converter decided
         * them (sea, river, banks below the water line, C28) */
        static uint8_t water[900]; static uint32_t calls;
        if ((calls++ & 4095u) == 0u) memset(water, 0, sizeof water);     /* refresh now and then (level loads) */
        if (!water[type]) {
            uint32_t mdl = psx_mod_read_word(MODEL_TABLE_ADDR + 4u * type);
            water[type] = (mdl && (psx_mod_read_half(mdl + 2u) & 0x4000u)) ? 1 : 2;
        }
        if (water[type] == 1)
            return;
    }
    /* a cell without a ROADSURF surface borrows a one-polygon scratch surface in mod memory for this query (its
     * pointer goes back to 0 before any other query; only MapHeight / FindSurfaceD2 read the pointers), so a
     * Driver 2 slope never ends at such a cell's flat Driver 1 height (cars rolled at the border) */
    static uint32_t borrowed = 0xFFFFFFFFu;
    if (borrowed != 0xFFFFFFFFu && borrowed != type) {
        psx_mod_write_word(SURF_PTRS + 4u * borrowed, 0u);
        borrowed = 0xFFFFFFFFu;
    }
    uint32_t surf = fr32u(SURF_PTRS + 4u * type);
    int scratch = 0;
    if (surf == D2SF_SCRATCH || surf == 0u) {
        surf = D2SF_SCRATCH; scratch = 1;
    } else if ((surf & 0x1FFFFFFFu) < 0x10000u || (surf & 0x1FFFFFFFu) >= 0x200000u || fr16(surf + 6u) < 1)
        return;
    uint32_t p0 = surf + 8u;
    /* Driver 2 coordinates */
    double sc = (double)s_d2sf_scale / 65536.0;
    int32_t x2 = (int32_t)(((int64_t)(x - s_d2sf_offx) << 16) / s_d2sf_scale);
    int32_t z2 = (int32_t)(((int64_t)(z - s_d2sf_offz) << 16) / s_d2sf_scale);
    int32_t vy2 = (int32_t)(((int64_t)y << 16) / s_d2sf_scale);
    const uint8_t* pl = d2sf_cell(x2, z2, vy2);
    if (s_d2sf_stage == 2) return;
    if (!pl) {                                      /* sea / no data: Driver 1's own surface */
        if (scratch) {
            if (borrowed == type) { psx_mod_write_word(SURF_PTRS + 4u * type, 0u); borrowed = 0xFFFFFFFFu; }
            return;
        }
        if (s_d2sf_dirty[type]) {
            for (uint32_t k = 0; k < 52u; k += 4u)
                psx_mod_write_word(p0 + k, (uint32_t)le32(s_d2sf_saved[type] + k));
            s_d2sf_dirty[type] = 0;
        }
        return;
    }
    if (scratch) {
        /* borrowed below, once the plane is known */
    } else if (!s_d2sf_isaved[type]) {
        for (uint32_t k = 0; k < 52u; k += 4u) {
            uint32_t v = psx_mod_read_word(p0 + k);
            memcpy(s_d2sf_saved[type] + k, &v, 4);
        }
        s_d2sf_isaved[type] = 1;
    }
    /* C37 round 2 (17.10., user: janky at the joins of slopes): Driver 2's surface is flat planes meeting in creases
     * (ramp -> trench floor, ramp -> street); Driver 1's stiffer car bounced at each crease (pitch overshoot ~70 % at
     * slope_ref's foot, nose dive at its crest). Near the player the answer is the mean over a cross of radius
     * CHI_D2SF_SMOOTH (D2 units, default 512, 0 = exact planes) with central-difference gradients: a plane gives
     * exactly its own height and slope, a crease becomes a vertical curve of 2 R. Samples more than SMOOTH_LIM off the
     * centre plane's own extension (kerbs, walls, other levels) are replaced by that extension. */
    static int32_t smoothR = -1;
    if (smoothR < 0) { const char* e = getenv("CHI_D2SF_SMOOTH"); smoothR = e && *e ? atoi(e) : 512; }
    const uint8_t* npl[4] = { pl, pl, pl, pl };
    int smooth = 0;
    static const int32_t sdx[4] = { 1, -1, 0, 0 }, sdz[4] = { 0, 0, 1, -1 };
    if (smoothR > 0) {
        int32_t ppx = fr32(0x8009B0BCu), ppz = fr32(0x8009B0C4u);
        if (labs(x - ppx) + labs(z - ppz) < 3000)
            for (int k = 0; k < 4; k++) {
                npl[k] = d2sf_cell(x2 + sdx[k] * smoothR, z2 + sdz[k] * smoothR, vy2);
                if (npl[k] != pl) smooth = 1;
            }
    }
    /* the polygon written for a plane depends only on the plane, the cell's rotation / height and the clamp: skip
     * the work (and the guest writes) when this surface already holds it */
    static const uint8_t* last_pl[900];
    static uint32_t last_key[900];
    uint32_t key = (cell & 0xC000FFFFu) ^ (address == FINDSURF_FN ? 0x00010000u : 0u) ^ (scratch ? 0x00020000u : 0u);
    static int32_t last_d[900];
    if (!smooth && last_pl[type] == pl && last_key[type] == key && (scratch || s_d2sf_dirty[type])
        && (scratch ? (int32_t)psx_mod_read_word(p0 + 44u) : fr32(p0 + 44u)) == last_d[type])               /* still ours (a level load restores the lump) */
        return;
    if (s_d2sf_stage == 3) return;
    /* y down (D1) at the point and its gradient along x / z (D1 units; the scale cancels) */
    int32_t h0 = d2sf_height(pl, x2, z2), hx = d2sf_height(pl, x2 + 32, z2), hz = d2sf_height(pl, x2, z2 + 32);
    double T0 = h0 * sc, gx = (double)(hx - h0) / 32.0, gz = (double)(hz - h0) / 32.0;   /* sdHeightOnPlane is y down (d2surface.levels) */
    if (smooth) {
        /* R31 (user 18.10.: "a very slight bump while driving UP" slope_ref): CHI_D2SF_KERNEL=tri (default) adds the
         * half-radius cross: per axis weights 1 2 3 2 1 at -R, -R/2, 0, R/2, R (a triangle kernel: the crease becomes a
         * curve whose curvature also ramps in, no step at its ends); box = the R cross only (round 2) */
        static int tri = -1;
        if (tri < 0) { const char* e = getenv("CHI_D2SF_KERNEL"); tri = !(e && strcmp(e, "box") == 0); }
        int32_t hk[4], hh[4];
        for (int pass = 0; pass < (tri ? 2 : 1); pass++) {
            int32_t r = pass ? smoothR / 2 : smoothR;
            for (int k = 0; k < 4; k++) {
                int32_t qx = x2 + sdx[k] * r, qz = z2 + sdz[k] * r;
                const uint8_t* q = pass ? d2sf_cell(qx, qz, vy2) : npl[k];
                int32_t ext = d2sf_height(pl, qx, qz);
                int32_t h = q ? d2sf_height(q, qx, qz) : ext;
                (pass ? hh : hk)[k] = labs(h - ext) > 120 ? ext : h;   /* SMOOTH_LIM: a kerb / wall / other level */
            }
        }
        if (tri) {
            T0 = (6.0 * h0 + 2.0 * (hh[0] + hh[1] + hh[2] + hh[3]) + hk[0] + hk[1] + hk[2] + hk[3]) / 18.0 * sc;
            gx = 0.5 * (double)(hh[0] - hh[1]) / smoothR + 0.5 * (double)(hk[0] - hk[1]) / (2.0 * smoothR);
            gz = 0.5 * (double)(hh[2] - hh[3]) / smoothR + 0.5 * (double)(hk[2] - hk[3]) / (2.0 * smoothR);
        } else {
            T0 = (2.0 * h0 + hk[0] + hk[1] + hk[2] + hk[3]) / 6.0 * sc;
            gx = (double)(hk[0] - hk[1]) / (2.0 * smoothR);
            gz = (double)(hk[2] - hk[3]) / (2.0 * smoothR);
        }
    }
    /* MapHeight's local coordinates: lx east, lz = rows (south); u / v by the rotation bits */
    int32_t lx = sx % 1500 - 750, lz = sz % 1500 - 750;
    int32_t u, v; double Tu, Tv;
    if (cell & 0x40000000u) { u = lz; v = lx; Tu = -gz; Tv = gx; }
    else                    { u = lx; v = -lz; Tu = gx; Tv = gz; }
    if (cell & 0x80000000u) { u = -u; v = -v; Tu = -Tu; Tv = -Tv; }
    {   static int gsign;
        if (!gsign) { const char* e = getenv("CHI_D2SF_GSIGN"); gsign = (e && *e == '-') ? -1 : 1; }
        Tu *= gsign; Tv *= gsign; }
    if (address == FINDSURF_FN) {   /* the car body's contact normal: Driver 1's physics rolls cars on Driver 2's 45 deg banks */
        static double maxg = -1.0;
        if (maxg < 0.0) { const char* e = getenv("CHI_D2SF_MAXTILT"); double deg = e && *e ? atof(e) : 30.0; maxg = tan(deg * 3.14159265358979 / 180.0); }
        double g = sqrt(Tu * Tu + Tv * Tv);
        if (g > maxg && g > 0.0) { Tu *= maxg / g; Tv *= maxg / g; }
    }
    double k = 4096.0 / sqrt(1.0 + Tu * Tu + Tv * Tv);
    int32_t A = (int32_t)lround(Tu * k), B = (int32_t)lround(k), C = (int32_t)lround(Tv * k);
    if (B < 1) B = 1;
    int32_t cellh = (int16_t)(fr32u(0x80096858u) ? (cell & 0xFFFFu) : (cell & 0xFFF8u));   /* MapHeight's local_30 */
    int32_t D = (int32_t)(((int64_t)u * A + (int64_t)v * C) / B) - (int32_t)lround(T0) - cellh;
    int foot_ok = 0;
    if (scratch) {
        /* a cell without a surface: when Driver 2's plane gives Driver 1's own flat answer, leave it alone */
        if (A == 0 && C == 0 && labs(lround(T0) + cellh) <= 40) {   /* the converter snaps the street (D2 ~22) to 0 */
            if (borrowed == type) { psx_mod_write_word(SURF_PTRS + 4u * type, 0u); borrowed = 0xFFFFFFFFu; }
            return;
        }
        static int scratch_foot;
        foot_ok = scratch_foot; scratch_foot = 1;
        if (borrowed != type || psx_mod_read_word(SURF_PTRS + 4u * type) != D2SF_SCRATCH) {
            psx_mod_write_word(D2SF_SCRATCH, type);       /* SURFACEINFO: type, info 0 */
            psx_mod_write_word(D2SF_SCRATCH + 4u, 1u << 16);   /* heading 0, one polygon */
            psx_mod_write_word(SURF_PTRS + 4u * type, D2SF_SCRATCH);
            borrowed = type;
        }
    } else
        foot_ok = s_d2sf_dirty[type];
    static const int32_t full[8] = { -760, -760, -760, 760, 760, 760, 760, -760 };
    if (!foot_ok) {
        for (int i = 0; i < 8; i++) psx_mod_write_word(p0 + 4u * (uint32_t)i, (uint32_t)full[i]);
        psx_mod_write_half(p0 + 48u, 4u);
    }
    psx_mod_write_word(p0 + 32u, (uint32_t)A);
    psx_mod_write_word(p0 + 36u, (uint32_t)B);
    psx_mod_write_word(p0 + 40u, (uint32_t)C);
    psx_mod_write_word(p0 + 44u, (uint32_t)D);
    if (!scratch) s_d2sf_dirty[type] = 1;
    last_pl[type] = smooth ? NULL : pl; last_key[type] = key; last_d[type] = D;
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
    if (s_d2sf && chicago_active())               /* C37 phase 1: Driver 2's own lookup answers every query */
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
#define CHICAGO_FLAG_ADDR   0x8009788Cu   /* must match exe_patches.CHICAGO_FLAG_ADDR (S4a: RAM word gp+0x111C) */
#define SLOT_FILE           "mods/packages/driver.chicago/0.1.0/assets/chicago_slot.bin"
#define MISSION_LO          0x80120000u   /* the mission script (Take a Ride start seen at 0x8012A7A8) */
#define MISSION_HI          0x80140000u
#define MISSION_NUMBER      0x80096808u   /* Take a Ride: Miami 0x78/79, SF 0x7A/7B, LA 0x7C, NY 0x7D/7E */
#define NIGHT_FLAG          0x80096850u   /* mission script opcode 0x1F (exe 0x800689C8) */
static int s_slot_enabled, s_slot_chicago, s_la_saved, s_start_done, s_have_night, s_chi_night, s_have_music;
static int s_have_map, s_have_sky;
static uint32_t s_stable_end, s_carsets = 0x10303u;
static uint32_t s_dmg_civ[900], s_dmg_civ_n;        /* civ verts (75 words per model) + polys (105 per model); 3 or 5 models */
static uint32_t s_civ_block, s_pbuf;
static void specials_vblank(uint32_t cs);
static int32_t s_spc_reach, s_player_reach;   /* R35: the loaded special's broad-phase extra reach over Driver 1's 209 / 585 (C42E PBS high half) */
static void sfx_vblank(uint32_t cs);
static uint8_t* s_sfx; static uint32_t s_sfx_n;
static uint32_t s_spc_valid, s_spc_cur, s_spc_wheel;
static uint32_t s_spc_unloadable;
static int32_t s_pps[2][2 + 12 * 4]; static uint32_t s_pps_n[2];   /* C138: "PPS1", 4, per choice {model, 4 x (x, z), box x / z, ratio} */
static int32_t s_sps[2][2 + 9 * 16]; static uint32_t s_sps_n[2];   /* C102: "SPS1", n, n x {model, 4 x (x, z)} */
static uint8_t* s_spc[4]; static uint32_t s_spc_n[4];   /* 2/3: the extra-draw levels (C101) */                 /* C42 r3 (b): civ zone rows / car polygon buffer in mod memory */
static uint32_t s_dmg_ply[720], s_dmg_ply_n;        /* C42E: player verts (300 words) + polys (420 words), D2 player cars */
static int32_t s_car_box[12]; static uint32_t s_car_box_n;
static int16_t s_car_whl[9]; static uint32_t s_car_whl_n;
/* Q45 B (Polish CHI_POLISH_SPECDMG, <lev>.spd.bin): "SPD1", n, DMG_OFF (64), n x {model, 256 B DentCar level row over the
 * special's clean polygon order (1 = shifts at level 2, 3 = none)}; LTAB row 5 takes the loaded special's row, the exe
 * (c42d DCAVE2, Q45 B) shifts row 5 by 64 instead of 128 */
static uint8_t s_spd[2][16u + 4u * 260u]; static uint32_t s_spd_n[2];
static int32_t s_spt[2][3u + 2u * 16u]; static uint32_t s_spt_n[2];   /* C82: <lev>.spt.bin "SPT1", n, civ twist, n x {model, twist} */
static const uint8_t* spd_row(int t, uint32_t model) {
    const uint8_t* b = s_spd[t & 1];
    uint32_t n = s_spd_n[t & 1], cnt;
    if (n < 12u || memcmp(b, "SPD1", 4) != 0) return NULL;
    memcpy(&cnt, b + 4, 4);
    for (uint32_t i = 0; i < cnt && 12u + 260u * (i + 1u) <= n; i++) {
        uint32_t m; memcpy(&m, b + 12u + 260u * i, 4);
        if (m == model) return b + 16u + 260u * i;
    }
    return NULL;
}
static void spd_write_row5(uint32_t blk, int t, uint32_t model) {
    const uint8_t* r = spd_row(t, model);
    static int on = -1;
    if (on < 0) { const char* e = getenv("CHI_Q45B"); on = !(e && *e == '0'); }
    for (uint32_t i = 0; i < 256u; i += 4u) {
        uint32_t w = 0x03030303u;
        if (r && on) memcpy(&w, r + i, 4);
        psx_mod_write_word(blk + 5u * 256u + i, w);
    }
}
static uint8_t s_dmg_lvl[2304]; static uint32_t s_dmg_lvl_n, s_lvl_block;   /* C42 r3: D2 damage kinds, AI 1..3 + choices 0..3 */    /* C42 r3: wheel size (tread) per choice 0..3, AI 1..3 */   /* C42E: player choices 0..3: half x, y, z (D2 colBox x1.32) */
static uint32_t s_cos[2][250], s_cos_n[2];          /* C42/C53: cosmetics rows (8 or 10 x 100 B) day / night, car set 4 */
static uint8_t s_cyc[4][8 + 28 * 24]; static uint32_t s_cyc_n[4];
/* C147 (3): per-time civilian sets (Driver 2: Las Vegas day 1/3/4, night 1/2/4): the package writes *_night assets only when
 * the night level's civilians differ; [0] day, [1] night; civ_time_select() copies the running time's set into the active
 * arrays (s_dmg_civ, s_dmg_lvl, s_car_whl) and the car-sound map. */
static uint32_t s_t_dmg_civ[2][900], s_t_dmg_civ_n[2]; static uint8_t s_t_dmg_lvl[2][2304]; static uint32_t s_t_dmg_lvl_n[2];
static int16_t s_t_car_whl[2][9]; static uint32_t s_t_car_whl_n[2]; static uint8_t s_sx_map_night[28]; static int s_sx_map_night_ok, s_civ_t = -1;   /* C147 (2): CYC1 per variant (day, night, xd day, xd night) */
static uint32_t s_chi_map[6];
static uint32_t s_chi_entry[8], s_la_entry[8], s_night_entry[8], s_xd_entry[2][8];
static int s_have_xd, s_lvl_xd;   /* C101: extra-draw level pair in the package / the level table points at it */
/* C63 LA by Day (17.10.): the LA row gets Miami's confirm (Day/Night screen) when the package carries an LA day
 * level (sidecar words 29-36, build_package CHI_LA_DAY_LEV); "day" points level table entry 3 at it and plays
 * LA's Take a Ride (0x7C) with the night flag off, the day look (LOOK_CITY 0x7F), a day sky and song 2 */
static uint32_t s_laday_entry[8];
static int s_have_laday, s_la_day, s_have_laday_sky;
static int32_t s_la_start[2], s_chi_start[2];

/* Levels that run in LA's city index 3 through LA's Take a Ride (user, 2026-10-13: two-page
 * city menu): the plugin points level table entry 3 at the chosen level and moves the start.
 * Driver 1's other level files (IVIEW 2, TRAIN 6, CREDITS = Newtown 7) keep their own
 * boot-time entries; forcing their own CITY into Take a Ride crashed (CITY 7), index 3 works. */
enum { V_LA = 0, V_CHICAGO = 1, V_IVIEW = 2, V_HAVANA = 4, V_TRAIN = 6, V_NEWTOWN = 7, V_VEGAS = 8, V_RIO = 9 };   /* FLAT (4): not used (user R20, a
     * bare dev level); V_HAVANA / V_VEGAS / V_RIO = D2 cities (virtual, CITY 3: Q68 user 68 B; ids s_d2c) */
static int s_virtual = V_LA;
static int s_iv_sel;                                      /* C80: the selector's Interview is running (timer off) */
static int s_classic = 1;                  /* menu option: classic (5 rows) or pages */
static const int32_t s_level_start[8][2] = {      /* by level index (QA-2 13.10.; Newtown from its roads) */
    { 0, 0 }, { 0, 0 }, { -10500, -22144 }, { 0, 0 }, { 0, 4500 }, { 0, 0 }, { 25227, 29933 }, { 18000, 7500 },
};

static void preview_load(void);
/* M3: (re)load one city's asset set (0 Chicago, 1 Havana). Returns 0 when its slot sidecar is missing / short. */
static uint32_t s_sky_base = 13u, s_song_base = 8u;   /* SKY.BIN number of the city's day sky (+1 night, +2 rain); song */
static int32_t s_sea_y = -1084, s_start_rot;                       /* the city's water surface (y up), sidecar word 53 */
static void d2sf_unload(void);
static void sx_reset(void);
static int s_prev_have, s_prev_state;
static void preview_vblank(int chicago_row);
static int city_assets_load(int city) {
    int old = s_assets_city;
    preview_vblank(0);                               /* LA's picture back before another city's preview */
    s_assets_city = city;
    if (city < 0 || city >= D2C_N) return 0;
    FILE* f = fopen(apath(s_d2c[city].slot), "rb");
    uint32_t w[55];
    if (!f) { fprintf(stderr, "driver.chicago: %s missing\n", apath(s_d2c[city].slot)); s_assets_city = old; return 0; }
    size_t n = fread(w, 4, 55, f);
    fclose(f);
    if (n != 12 && n != 20 && n != 27 && n != 28 && n != 29 && n != 37 && n != 53 && n != 54 && n != 55) { fprintf(stderr, "driver.chicago: slot sidecar short (%u words)\n", (unsigned)n); s_assets_city = old; return 0; }
    for (int t = 0; t < 4; t++) { free(s_spc[t]); s_spc[t] = NULL; s_spc_n[t] = 0; }
    free(s_sfx); s_sfx = NULL; s_sfx_n = 0;
    sx_reset();                                      /* C121: the car-sound parse belongs to the old set */
    s_dmg_civ_n = s_dmg_ply_n = s_car_box_n = s_dmg_lvl_n = s_car_whl_n = 0;
    s_sps_n[0] = s_sps_n[1] = s_spt_n[0] = s_spt_n[1] = s_spd_n[0] = s_spd_n[1] = s_cos_n[0] = s_cos_n[1] = 0;
    s_sky_base = n >= 27 && ((w[26] >> 8) & 0xFFu) ? (w[26] >> 8) & 0xFFu : 13u;
    s_song_base = s_d2c[city].song_base;
    s_sea_y = n >= 54 ? (int32_t)w[53] : -1084;
    s_start_rot = n >= 55 ? (int32_t)w[54] : 0;     /* the start heading (0 = LA's script heading) */
    for (int i = 0; i < 8; i++) s_chi_entry[i] = w[i];
    s_la_start[0] = (int32_t)w[8]; s_la_start[1] = (int32_t)w[9];
    s_chi_start[0] = (int32_t)w[10]; s_chi_start[1] = (int32_t)w[11];
    s_have_night = n >= 20 && w[12] != 0;           /* + night Chicago's 8 entry words */
    for (int i = 0; s_have_night && i < 8; i++) s_night_entry[i] = w[12 + i];
    s_have_map = n >= 27 && w[20] != 0;             /* + Driver 2's minimap frame (C12) */
    for (int i = 0; s_have_map && i < 6; i++) s_chi_map[i] = w[20 + i];
    s_have_sky = n >= 27 && (w[26] & 1u);           /* + SKY.BIN with Chicago's skies 13-15 (C10) */
    s_have_music = n >= 27 && (w[26] & 2u);         /* + MUSIC.BIN with Chicago's songs 8 / 9 (milestone 2) */
    s_have_laday_sky = n >= 27 && (w[26] & 4u);     /* + Design's LA day sky as SKY.BIN 16 (C63) */
    s_stable_end = n >= 28 ? w[27] : 0u;            /* + C45 stable-page end (skip-resident patch) */
    s_carsets = n >= 29 ? w[28] : 0x10303u;         /* + C51 car-set CITY: day | night << 8 (default LA's) */
    s_have_laday = n >= 37 && w[29] != 0;           /* + C63 LA day level's 8 entry words */
    for (int i = 0; s_have_laday && i < 8; i++) s_laday_entry[i] = w[29 + i];
    s_have_xd = n >= 53 && w[37] != 0 && w[45] != 0;  /* + C101 extra-draw day / night entries */
    for (int i = 0; s_have_xd && i < 8; i++) { s_xd_entry[0][i] = w[37 + i]; s_xd_entry[1][i] = w[45 + i]; }
    {   /* C42 step 1: Driver 2 civ damage tables (car-set city 4), written to 0x800A0E20 while in use */
        FILE* g = fopen(apath("dmg_civ.bin"), "rb");
        if (g) { s_dmg_civ_n = (uint32_t)fread(s_dmg_civ, 4, 900, g); fclose(g); }
        for (int t = 0; t < 2; t++) {                    /* C147 (3): per-time civilian sets (day = the plain assets) */
            g = t ? fopen(apath("dmg_civ_night.bin"), "rb") : NULL;
            s_t_dmg_civ_n[t] = g ? (uint32_t)fread(s_t_dmg_civ[t], 4, 900, g) : 0u;
            if (g) fclose(g);
            g = t ? fopen(apath("dmg_levels_night.bin"), "rb") : NULL;
            s_t_dmg_lvl_n[t] = g ? (uint32_t)fread(s_t_dmg_lvl[t], 1, sizeof s_t_dmg_lvl[t], g) : 0u;
            if (g) fclose(g);
            g = t ? fopen(apath("car_wheels_night.bin"), "rb") : NULL;
            s_t_car_whl_n[t] = g ? (uint32_t)fread(s_t_car_whl[t], 2, 9, g) : 0u;
            if (g) fclose(g);
        }
        s_sx_map_night_ok = 0;
        g = fopen(apath("car_sfx_night_map.bin"), "rb");
        if (g) { s_sx_map_night_ok = fread(s_sx_map_night, 1, 28, g) == 28u; fclose(g); }
        s_civ_t = -1;
        g = fopen(apath("dmg_player.bin"), "rb");
        if (g) { s_dmg_ply_n = (uint32_t)fread(s_dmg_ply, 4, 720, g); fclose(g); }
        g = fopen(apath("car_boxes.bin"), "rb");
        if (g) { s_car_box_n = (uint32_t)fread(s_car_box, 4, 12, g); fclose(g); }
        g = fopen(apath("dmg_levels.bin"), "rb");
        if (g) { s_dmg_lvl_n = (uint32_t)fread(s_dmg_lvl, 1, sizeof s_dmg_lvl, g); fclose(g); }
        g = fopen(apath("car_sfx.bin"), "rb");   /* C42 r3 (e): D2 car engine sounds */
        if (g) {
            fseek(g, 0, SEEK_END); long sz = ftell(g); fseek(g, 0, SEEK_SET);
            if (sz > 4 && sz < (1 << 20) && (s_sfx = (uint8_t*)malloc((size_t)sz)) != NULL) s_sfx_n = (uint32_t)fread(s_sfx, 1, (size_t)sz, g);
            fclose(g);
        }
        for (int t = 0; t < 4; t++) {                    /* C42 r3 (c): regional specials (convert polish_specials); 2/3 = xd */
            static const char* nm[4] = { "specials_day", "specials_night", "specials_xd_day", "specials_xd_night" };
            char path[128];
            snprintf(path, sizeof path, "%s", apath(nm[t])); { size_t l_ = strlen(path); if (l_ + 4 < sizeof path) strcpy(path + l_, ".bin"); }
            g = fopen(path, "rb");
            if (g) {
                fseek(g, 0, SEEK_END); long sz = ftell(g); fseek(g, 0, SEEK_SET);
                if (sz > 28 && sz < (8 << 20) && (s_spc[t] = (uint8_t*)malloc((size_t)sz)) != NULL)
                    s_spc_n[t] = (uint32_t)fread(s_spc[t], 1, (size_t)sz, g);
                fclose(g);
            }
        }
        for (int t = 0; t < 2; t++) {                    /* C102: the specials' shadow quads (Polish .sps.bin, SPS1) */
            g = fopen(apath(t ? "spcshadow_night.bin" : "spcshadow_day.bin"), "rb");
            if (g) { s_sps_n[t] = (uint32_t)fread(s_sps[t], 4, sizeof s_sps[t] / 4, g); fclose(g); }
        }
        for (int t = 0; t < 2; t++) {                    /* C138: the player cars' D2 shadow quads (Polish .pps.bin, PPS1) */
            s_pps_n[t] = 0;
            g = fopen(apath(t ? "plrshadow_night.bin" : "plrshadow_day.bin"), "rb");
            if (g) { s_pps_n[t] = (uint32_t)fread(s_pps[t], 4, sizeof s_pps[t] / 4, g); fclose(g); }
        }
        for (int t = 0; t < 2; t++) {                    /* C82: the specials' twistRateY per city (Polish .spt.bin) */
            g = fopen(apath(t ? "spctwist_night.bin" : "spctwist_day.bin"), "rb");
            if (g) { s_spt_n[t] = (uint32_t)fread(s_spt[t], 4, sizeof s_spt[t] / 4, g); fclose(g); }
        }
        for (int t = 0; t < 2; t++) {                    /* Q45 B: the specials' DentCar level rows (polish SPECDMG, .spd.bin) */
            g = fopen(apath(t ? "specdmg_night.bin" : "specdmg_day.bin"), "rb");
            if (g) { s_spd_n[t] = (uint32_t)fread(s_spd[t], 1, sizeof s_spd[t], g); fclose(g); }
        }
        for (int t = 0; t < 4; t++) {                    /* C147 (2): Driver 2's palette-cycling neon (Polish .cyc.bin, CYC1) */
            static const char* nm[4] = { "colcycle_day.bin", "colcycle_night.bin", "colcycle_xd_day.bin", "colcycle_xd_night.bin" };
            s_cyc_n[t] = 0;
            g = fopen(apath(nm[t]), "rb");
            if (g) { s_cyc_n[t] = (uint32_t)fread(s_cyc[t], 1, sizeof s_cyc[t], g); fclose(g); }
        }
        g = fopen(apath("car_wheels.bin"), "rb");
        if (g) { s_car_whl_n = (uint32_t)fread(s_car_whl, 2, 9, g); fclose(g); }
        memcpy(s_t_dmg_civ[0], s_dmg_civ, sizeof s_dmg_civ); s_t_dmg_civ_n[0] = s_dmg_civ_n;   /* C147 (3): the day set */
        memcpy(s_t_dmg_lvl[0], s_dmg_lvl, sizeof s_dmg_lvl); s_t_dmg_lvl_n[0] = s_dmg_lvl_n;
        memcpy(s_t_car_whl[0], s_car_whl, sizeof s_car_whl); s_t_car_whl_n[0] = s_car_whl_n;
        for (int t = 0; t < 2; t++) {
            g = fopen(apath(t ? "cosmetics_night.bin" : "cosmetics_day.bin"), "rb");
            if (g) { s_cos_n[t] = (uint32_t)fread(s_cos[t], 4, 250, g); fclose(g); }
        }
    }
    d2sf_unload();
    s_prev_have = 0; s_prev_state = -1;
    preview_load();
    fprintf(stdout, "driver.chicago: %s assets loaded\n", s_d2c[city].name);
    return 1;
}

static void page2_build(void);
static void chicago_slot_activate(void) {
    if (!city_assets_load(0)) { fprintf(stderr, "driver.chicago: Chicago slot off\n"); return; }
    for (int c = 1; c < D2C_N; c++) {   /* M3: the other D2 cities' sets the package carries (build switches) */
        char path[192];
        snprintf(path, sizeof path, "%s%s%s", ASSET_ROOT, s_d2c[c].dir, s_d2c[c].slot);
        FILE* h = fopen(path, "rb");
        s_have_city[c] = h != NULL;
        if (h) fclose(h);
    }
    s_have_city[0] = 1;
    s_have_havana = s_have_city[D2C_HAVANA] || (row_city_override() > 0 && s_have_city[row_city_override()]);
    page2_build();
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
static const int s_d2_virt[D2C_N] = { V_CHICAGO, V_HAVANA, V_VEGAS, V_RIO };
static int d2_id_of(int v) { for (int c = 0; c < D2C_N; c++) if (s_d2_virt[c] == v) return c; return -1; }
static int d2_virtual(int v) { return d2_id_of(v) >= 0; }
static int chicago_active(void) {   /* M3: d2_city(): a Driver 2 city (its asset set loaded) is running in the D2 slot */
    return psx_mod_read_word(0x80096834u) == D2_SLOT_CITY && (!s_slot_enabled || d2_virtual(s_virtual));
}
/* the running D2 city id, -1 when none (pause map / music / minimap / drowning key on this, not on the slot) */
static int d2_city(void) { return chicago_active() ? s_assets_city : -1; }
/* any level other than LA's own runs in index 3 */
static int other_level_active(void) {
    return psx_mod_read_word(0x80096834u) == 3u && (!s_slot_enabled || s_virtual != V_LA);
}
/* M3: the selector's choice; a Driver 2 city loads its own asset set (Havana falls back to Chicago without one) */
static int city_assets_load(int city);
static void select_virtual(int v) {
    if (v == V_HAVANA && row_city_override() > 0) v = s_d2_virt[row_city_override()];   /* debug: the row loads city N */
    int id = d2_id_of(v);
    if (id > 0 && s_assets_city != id && !city_assets_load(id)) { v = V_CHICAGO; id = 0; }
    if (id == 0 && s_assets_city != 0) city_assets_load(0);
    s_virtual = v;
}
/* C63: LA's Take a Ride by day is chosen (story / Undercover LA missions stay LA night) */
static int la_day_active(void) {
    return s_slot_enabled && s_have_laday && s_la_day && s_virtual == V_LA
        && psx_mod_read_word(0x80096834u) == 3u && psx_mod_read_word(0x80096808u) == 0x7Cu;
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
    { { 0x001C4610u, 0x001C4668u, 0x001C4674u }, "Desert", 0, R_CITY, V_TRAIN, 3 },   /* C65: TRAIN.LEV (CITY 6) */
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
static const MenuRow s_page2h[] = {   /* M3: the package carries Havana (assets/havana/): its row is a city like Chicago's */
    { { 0x001C4610u, 0x001C4668u, 0x001C444Cu }, "Chicago", 0, R_CITY, V_CHICAGO, 3 },
    { { 0x001C4610u, 0x001C4668u, 0x001C444Cu }, "Havana", 0, R_CITY, V_HAVANA, 3 },    /* LA's handler, Day/Night confirm */
    { { NOP_FN, NOP_FN, NOP_FN }, "Las Vegas", 0, R_GREY, -1, -1 },
    { { NOP_FN, NOP_FN, NOP_FN }, "Rio", 0, R_GREY, -1, -1 },
    { { NOP_FN, NOP_FN, NOP_FN }, "Driver 1 cities", 0, R_PAGE, -1, -1 },
};
/* M3 / Q68 B: page 2 built from the package (chicago_slot_activate): a D2 city whose asset set the package carries is a
 * row like Chicago's (Miami's confirm: Day/Night), the others stay grey. */
static MenuRow s_page2d[D2C_N + 1];
static void page2_build(void) {
    for (int c = 0; c < D2C_N; c++) {
        int live = s_have_city[c] || (c == D2C_HAVANA && s_have_havana);
        MenuRow r = { { NOP_FN, NOP_FN, NOP_FN }, s_d2c[c].name, 0, R_GREY, -1, -1 };
        if (live) { r.fn[0] = 0x001C4610u; r.fn[1] = 0x001C4668u; r.fn[2] = 0x001C444Cu; r.kind = R_CITY; r.virt = s_d2_virt[c]; r.city = 3; }
        s_page2d[c] = r;
    }
    s_page2d[D2C_N] = s_page2[sizeof s_page2 / sizeof s_page2[0] - 1];   /* "Driver 1 cities" */
}
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
/* C64 (16.10., EXP research_classic_maps.md 6): Interview runs its own first mission 0xAE through the original
 * mission start (FUN_80022818: the interview setup, its traffic, (0xAE + 3) & 7 = song 1 = New York night) */
static int via_la_for(int v) { return extra_via_la() && v != V_IVIEW; }
static uint32_t extra_mission(int v) {
    if (via_la_for(v)) return 0u;
    return v == V_NEWTOWN ? 0x7Fu : v == V_IVIEW ? 0xAEu : v == V_TRAIN ? 0xAAu : 0u;
}
static int s_page;                                        /* 0 = Driver 1 cities, 1 = Driver 2 cities */
static uint32_t s_pad_prev;

static uint32_t str_ptrs[16];
static void write_strings(void) {                          /* every label once, word-packed */
    static const char* all[] = { "Driver 1 cities", "Driver 2 cities", "Newtown", "Interview", "Desert",
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
    static const char* all[] = { "Driver 1 cities", "Driver 2 cities", "Newtown", "Interview", "Desert",
                                 "Chicago", "Havana", "Las Vegas", "Rio" };
    if (!r->label) return r->label_ptr;
    for (unsigned i = 0; i < sizeof all / sizeof all[0]; i++)
        if (!strcmp(r->label, all[i])) return str_ptrs[i];
    return 0;
}
static const MenuRow* page_rows(int* n) {
    if (s_classic) { *n = (int)(sizeof s_classic_rows / sizeof s_classic_rows[0]); return s_classic_rows; }
    if (s_page) { *n = D2C_N + 1; return s_page2d; }
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
        for (int w = 0; w < 3; w++) {
            uint32_t fn = r < n ? row->fn[w] : NOP_FN;
            if (w == 2 && r < n && row->virt == V_LA && s_have_laday)
                fn = 0x001C444Cu;                         /* C63: Miami's confirm = the Day/Night screen */
            psx_mod_write_word(MENU_ADDR + 16u * r + 4u * w, fn);
        }
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
        select_virtual(V_CHICAGO); s_slot_chicago = 1;
    } else {                                              /* Miami's handler */
        psx_mod_write_word(CITY_WORD, 0u);
        psx_mod_write_word(0x801D2DB0u, 0x801D2D10u);
        psx_mod_write_word(0x801CDFC4u, 0x001C03ACu);
        psx_mod_write_word(0x801CDFC0u, (0xB6u << 16) | 0x147u);
    }
}

/* Chicago's own Take a Ride picture (Design 14.10., design/previews; assets/chicago_preview.bin = 128 x 232 4-bit
 * + 16-colour CLUT). The Chicago row borrows LA's handler, i.e. LA2's quad: texpage 0x0008 (VRAM x 512, y 0), u 0..127,
 * v 0..227, CLUT 0x447C (VRAM 960, 273). While the Chicago row is highlighted the plugin uploads Chicago's block
 * (rows 2..229 of the 232) and CLUT over LA2's with a GP0 0xA0 CPU->VRAM copy, the command libgpu's LoadImage
 * sends; any other row restores LA2 from a copy taken before the first upload. Host-only (M8: a FRNT.B1 page +
 * TPDATA / FECLUT entries and the Chicago row's own quad). */
#define PREVIEW_X 512
#define PREVIEW_Y 0
#define PREVIEW_W 32               /* halfwords = 128 4-bit pixels */
#define PREVIEW_H 228
#define PREVIEW_CLUT_X 960
#define PREVIEW_CLUT_Y 273
static uint16_t s_prev_chi[PREVIEW_W * 232], s_prev_chi_clut[16], s_prev_la[PREVIEW_W * PREVIEW_H], s_prev_la_clut[16];
static int s_prev_have, s_prev_saved, s_prev_rows;
static void vram_upload(int x, int y, int w, int h, const uint16_t* px) {
    gpu_write_gp0(0xA0000000u);
    gpu_write_gp0(((uint32_t)y << 16) | (uint32_t)x);
    gpu_write_gp0(((uint32_t)h << 16) | (uint32_t)w);
    for (int i = 0; i + 1 < w * h; i += 2)
        gpu_write_gp0((uint32_t)px[i] | ((uint32_t)px[i + 1] << 16));
}
static int vram_matches(int x, int y, int w, int h, const uint16_t* px) {
    for (int i = 0; i < w * h; i += 37)
        if (gpu_vram_peek(x + i % w, y + i / w) != px[i]) return 0;
    return 1;
}
static void preview_load(void) {
    FILE* f = fopen(apath(s_d2c[s_assets_city].preview), "rb");
    if (!f) return;
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    s_prev_rows = (int)((size - 32) / (2 * PREVIEW_W));         /* 228 (exact) or 232 (rows 2..229 shown) */
    if (s_prev_rows == 228 || s_prev_rows == 232)
        s_prev_have = fread(s_prev_chi, 2, (size_t)(PREVIEW_W * s_prev_rows), f) == (size_t)(PREVIEW_W * s_prev_rows)
                      && fread(s_prev_chi_clut, 2, 16, f) == 16;
    fclose(f);
}
/* C73/C46 (17.10., Polish: "ghost towers" in the sky): the menu mark stays in RAM after the frontend, so this ran
 * every vblank in game too and, with the Chicago row still under the cursor, put the picture back over VRAM
 * x 512, y 0..227 = the left half of the level's sky page (texpage 8), i.e. dome pieces 0/1 of every band showed it.
 * Now only a change of the highlighted row uploads (Chicago picture) or restores (LA2); the cursor does not move in
 * game, so the level's own sky upload stays intact. */
static int s_prev_state = -1;
static void preview_vblank(int chicago_row) {
    if (!s_prev_have)
        return;
    if (chicago_row == s_prev_state)
        return;
    s_prev_state = chicago_row;
    const uint16_t* chi = s_prev_chi + (s_prev_rows == 232 ? 2 * PREVIEW_W : 0);   /* LA2's quad shows 228 rows */
    if (chicago_row) {
        if (vram_matches(PREVIEW_X, PREVIEW_Y, PREVIEW_W, PREVIEW_H, chi))
            return;
        if (!s_prev_saved) {                              /* LA2 as the frontend loaded it */
            for (int i = 0; i < PREVIEW_W * PREVIEW_H; i++)
                s_prev_la[i] = gpu_vram_peek(PREVIEW_X + i % PREVIEW_W, PREVIEW_Y + i / PREVIEW_W);
            for (int i = 0; i < 16; i++) s_prev_la_clut[i] = gpu_vram_peek(PREVIEW_CLUT_X + i, PREVIEW_CLUT_Y);
            s_prev_saved = 1;
        }
        vram_upload(PREVIEW_X, PREVIEW_Y, PREVIEW_W, PREVIEW_H, chi);
        vram_upload(PREVIEW_CLUT_X, PREVIEW_CLUT_Y, 16, 1, s_prev_chi_clut);
    } else if (s_prev_saved && vram_matches(PREVIEW_X, PREVIEW_Y, PREVIEW_W, PREVIEW_H, chi)) {
        vram_upload(PREVIEW_X, PREVIEW_Y, PREVIEW_W, PREVIEW_H, s_prev_la);
        vram_upload(PREVIEW_CLUT_X, PREVIEW_CLUT_Y, 16, 1, s_prev_la_clut);
    }
}

/* C88 (24.10., layout 2 after the user's probe review): Cheats screen pages (FRONTEND screen id 0x801CDE5C == 6).
 * Driver 1's screen: row k (0..count-1, count 0x800967D8 = 8) is drawn when its unlock entry 0x8008671C + 0x38 k starts
 * with -2, name from the pointer table 0x801CEA40, On/Off from 0x8009681C (row 1) / 0x80096820 (row 2) / 0x8009D8DC +
 * 4 (k - 3) (row 0 none); cross runs the jump table 0x801C0728 (rows 1-5, 7 toggle their word, row 0 = credits, row 6 =
 * no-op 0x801C74D4). Driver 1's unused row 6 ("NULL") stays hidden.
 *  Page 1: CREDITS, INVINCIBILITY, IMMUNITY, REAR WHEEL, MINIS, STILTS, ANTIPODEAN (row 6, shown / toggled through row 6's
 *          word as a proxy), PAGE 2 (row 7).
 *  Page 2: rows 1.. = LOW GRAVITY, INFINITE MASS, SUPER SPEED, NIGHTMARE, FEATHER, HELL (C99; CHI_C88_NIGHTMARE=0 hides both), then PAGE 1; row 0 and
 *          the rest hidden (count = last row + 1). Room for 2 more cheats (rows up to 6, the page row 7).
 * Every cheat row shows / toggles its row's Driver 1 word as a proxy: the true values live in tv[] while the screen is
 * up (synced back every vblank, written to the real words when the screen is left). Page rows: jump -> the no-op, the
 * plugin turns the page on cross. Hidden rows: unlock word -3 (driver.personal's unlock-all leaves -3 alone). Page rows
 * have no On/Off: a FRONTEND draw patch (0x801C765C..88, written here on screen entry, checked word by word) skips the
 * On/Off when the row's unlock entry +4 (first code step, unused once unlocked) is negative; cheat rows get a positive
 * value there (row 6, Driver 1's NULL row, has -1). Triangle leaves the screen as in Driver 1 (tables restored). Host-only (M8: the draw patch in the package's
 * FRONTEND patches, labels in the overlay's tail, the table writes from guest code). CHI_C88_MENU=0: off. */
static int nightmare_enabled(void) {
    static int v = -1;
    if (v < 0) { const char* e = getenv("CHI_C88_NIGHTMARE"); v = !(e && *e == '0'); }
    return v;
}
#define CH_SCREEN 0x801CDE5Cu
#define CH_UNLOCK 0x8008671Cu
#define CH_NAMES  0x801CEA40u
#define CH_CURSOR 0x801D2E48u
#define CH_COUNT  0x801D2E50u
#define CH_JUMP   0x801C0728u   /* cross jump table (FRONTEND data, KUSEG targets) */
#define CH_ROWS   0x800967D8u   /* number of cheat rows (8) */
#define CH_NOOP   0x001C74D4u
#define CH_HIDDEN 0xFFFFFFFDu
enum { C_NONE = -1, C_INV, C_IMM, C_REAR, C_MINIS, C_STILTS, C_LOWG, C_ANTI, C_INFM, C_SPD2, C_NGHT, C_FTHR, C_HELL, C_N,
       C_ORIG = 99, C_PAGE = 100 };
static const uint32_t c_real[C_N] = { 0x8009681Cu, 0x80096820u, 0x8009D8DCu, 0x8009D8E0u, 0x8009D8E4u, 0x8009D8E8u,
                                      0x8009D8ECu, 0x800933C4u, 0x800933CCu, 0x800933C8u, 0x800933C4u, 0x8009342Cu };
/* the INFM word carries two cheats (exe c88 car-car block / replay bits): 0x20 INFINITE MASS, 0x100 FEATHER */
static uint32_t ch_get(int c) {
    uint32_t w = psx_mod_read_word(c_real[c]);
    return c == C_INFM ? (w & 0x20u) != 0u : c == C_FTHR ? (w & 0x100u) != 0u : w != 0u;
}
static void ch_put_all(const uint32_t* tv) {
    for (int c = 0; c < C_N; c++) if (c != C_INFM && c != C_FTHR) psx_mod_write_word(c_real[c], tv[c]);
    psx_mod_write_word(0x800933C4u, (tv[C_INFM] ? 0x20u : 0u) | (tv[C_FTHR] ? 0x100u : 0u));
}
static uint32_t ch_row_word(uint32_t k) { return k == 1u ? 0x8009681Cu : k == 2u ? 0x80096820u : 0x8009D8DCu + 4u * (k - 3u); }
static const uint32_t ch_draw_old[12] = { 0x1200000Fu, 0x02202821u, 0x00003021u, 0x00C03821u, 0x0C039BC5u, 0xAFA00010u,
                                          0x8E820000u, 0x00000000u, 0x14560004u, 0x3C04001Cu, 0x08071DA5u, 0x26A4079Cu };
/* lw v0,4(s2) / move a1,s1 / beqz s0,769C / move a2,zero / bltz v0,769C / move a3,zero / jal 0x800E6F14 /
 * sw zero,0x10(sp) / lw v0,0(s4) / nop / beq v0,s6,7694 (On) / addiu a0,s5,0x79C   (768C / 7690 = Off, unchanged) */
static const uint32_t ch_draw_new[12] = { 0x8E420004u, 0x02202821u, 0x1200000Du, 0x00003021u, 0x0440000Bu, 0x00003821u,
                                          0x0C039BC5u, 0xAFA00010u, 0x8E820000u, 0x00000000u, 0x10560003u, 0x26A4079Cu };
static void cheats_vblank(void) {
    static int on = -1, page, inited, rows[8];
    static uint32_t blk, saved_names[8], saved_jump[8], saved_step[8], saved_count, pad_prev, tv[C_N];
    static uint32_t str_lg, str_im, str_nm, str_ss, str_p1, str_p2, str_ft, str_hl;
    if (on < 0) { const char* e = getenv("CHI_C88_MENU"); on = !(e && *e == '0'); }
    if (!on) return;
    /* C105 (user: 'Antipodean switches itself on'): screen id 6 (0x801CDE5C) is any row-list screen, also Take a Ride's
     * city list, where the plugin then re-laid the Cheats rows and moved values between proxy words (Hell -> LOW
     * GRAVITY's word, shown as ANTIPODEAN On). The Cheats screen is the one whose current menu definition pointer
     * 0x801CDC8C is 0x001C0020 (runner screen_sig: city list 0x1C0038, others 0x1C000C / 0x1C0028). */
    int screen = psx_mod_read_word(MENU_MARK) == 0x0172001Au && psx_mod_read_word(CH_SCREEN) == 6u
                 && psx_mod_read_word(0x801CDC8Cu) == 0x001C0020u;
    if (!inited && !screen) return;
    if (inited) {                                        /* sync: row proxies -> true values */
        for (uint32_t k = 1; k < 8u; k++)
            if (rows[k] >= 0 && rows[k] < C_N) tv[rows[k]] = psx_mod_read_word(ch_row_word(k)) ? 1u : 0u;
    }
    if (!screen) {                                       /* left the screen: Driver 1's tables + the true values back */
        for (uint32_t k = 0; k < 8u; k++) {
            psx_mod_write_word(CH_NAMES + 4u * k, saved_names[k]); psx_mod_write_word(CH_JUMP + 4u * k, saved_jump[k]);
            psx_mod_write_word(CH_UNLOCK + 0x38u * k + 4u, saved_step[k]);
            if (psx_mod_read_word(CH_UNLOCK + 0x38u * k) == CH_HIDDEN) psx_mod_write_word(CH_UNLOCK + 0x38u * k, 0xFFFFFFFEu);
        }
        psx_mod_write_word(CH_ROWS, saved_count);
        ch_put_all(tv);
        inited = 0; page = 0;
        return;
    }
    if (!blk) {                                          /* labels (the menu font has letters / digits only) */
        static const char* s[8] = { "LOW GRAVITY", "INFINITE MASS", "NIGHTMARE", "SUPER SPEED", "PAGE 1", "PAGE 2", "FEATHER", "HELL" };
        uint32_t* dst[8] = { &str_lg, &str_im, &str_nm, &str_ss, &str_p1, &str_p2, &str_ft, &str_hl };
        blk = psx_mod_alloc_guest_memory(160u, 16u);
        if (!blk) return;
        uint32_t a = blk;
        for (int i = 0; i < 8; i++) {
            size_t n = strlen(s[i]) + 1; *dst[i] = a;
            for (size_t k = 0; k < n; k += 4) {
                uint32_t w = 0;
                for (size_t b = 0; b < 4 && k + b < n; b++) w |= (uint32_t)(uint8_t)s[i][k + b] << (8 * b);
                psx_mod_write_word(a + (uint32_t)k, w);
            }
            a += (uint32_t)((n + 3) & ~(size_t)3);
        }
    }
    uint32_t pad = psx_mod_read_word(PAD_PRESS) & 0xFFFFu, press = pad & ~pad_prev;
    pad_prev = pad;
    int want = page;
    if (!inited) {
        int ok = 1;                                      /* the draw patch (overlay code, checked word by word) */
        for (int i = 0; i < 12; i++) {
            uint32_t w = psx_mod_read_word(0x801C765Cu + 4u * (uint32_t)i);
            if (w != ch_draw_old[i] && w != ch_draw_new[i]) ok = 0;
        }
        if (!ok) { on = 0; return; }                     /* unexpected overlay: leave Driver 1's screen alone */
        for (int i = 0; i < 12; i++) psx_mod_write_code_word(0x801C765Cu + 4u * (uint32_t)i, ch_draw_new[i]);
        for (uint32_t k = 0; k < 8u; k++) {
            saved_names[k] = psx_mod_read_word(CH_NAMES + 4u * k); saved_jump[k] = psx_mod_read_word(CH_JUMP + 4u * k);
            saved_step[k] = psx_mod_read_word(CH_UNLOCK + 0x38u * k + 4u);
        }
        saved_count = psx_mod_read_word(CH_ROWS);
        for (int c = 0; c < C_N; c++) tv[c] = ch_get(c);
        inited = 1; page = -1; want = 0; press = 0;
    }
    uint32_t cur = psx_mod_read_word(CH_CURSOR);
    int at = cur < 8u ? rows[cur] : C_NONE;
    if (page >= 0 && (press & 0x40u)) {
        if (at == C_PAGE) want = !page;
        else if (cur == 6u && at >= 0 && at < C_N) {    /* row 6's jump is a no-op: toggle here */
            tv[at] = !tv[at]; psx_mod_write_word(ch_row_word(6u), tv[at]);
        }
    }
    if (want != page) {
        int lay[8];
        for (int k = 0; k < 8; k++) lay[k] = C_NONE;
        if (want == 0) {
            lay[0] = C_ORIG; lay[1] = C_INV; lay[2] = C_IMM; lay[3] = C_REAR; lay[4] = C_MINIS; lay[5] = C_STILTS;
            lay[6] = C_ANTI; lay[7] = C_PAGE;
        } else {
            int k = 1;
            lay[k++] = C_LOWG; lay[k++] = C_INFM; lay[k++] = C_SPD2;
            if (nightmare_enabled()) lay[k++] = C_NGHT;
            lay[k++] = C_FTHR;
            if (nightmare_enabled()) lay[k++] = C_HELL;
            lay[k] = C_PAGE;
        }
        int last = 0, page_row = 7;
        for (uint32_t k = 0; k < 8u; k++) {
            uint32_t un = CH_UNLOCK + 0x38u * k, nm = saved_names[k];
            rows[k] = lay[k];
            psx_mod_write_word(CH_JUMP + 4u * k, saved_jump[k]);
            psx_mod_write_word(un + 4u, saved_step[k]);
            if (lay[k] == C_NONE) { psx_mod_write_word(un, CH_HIDDEN); psx_mod_write_word(CH_NAMES + 4u * k, nm); continue; }
            psx_mod_write_word(un, 0xFFFFFFFEu); last = (int)k;
            if (lay[k] == C_PAGE) {
                page_row = (int)k; nm = want ? str_p1 : str_p2;
                psx_mod_write_word(CH_JUMP + 4u * k, CH_NOOP);
                psx_mod_write_word(un + 4u, 0xFFFFFFFFu);                /* no On/Off (draw patch) */
            } else if (lay[k] >= 0 && lay[k] < C_N) {
                if (lay[k] == C_LOWG) nm = str_lg; else if (lay[k] == C_INFM) nm = str_im;
                else if (lay[k] == C_SPD2) nm = str_ss; else if (lay[k] == C_NGHT) nm = str_nm;
                else if (lay[k] == C_FTHR) nm = str_ft; else if (lay[k] == C_HELL) nm = str_hl;
                else if (lay[k] == C_ANTI) nm = saved_names[7];
                psx_mod_write_word(ch_row_word(k), tv[lay[k]]);
                if ((int32_t)saved_step[k] < 0) psx_mod_write_word(un + 4u, 0u);   /* row 6 (NULL) has -1 there: On/Off back */
                if (k == 6u) psx_mod_write_word(CH_JUMP + 4u * k, CH_NOOP);
            }
            psx_mod_write_word(CH_NAMES + 4u * k, nm);
        }
        if (rows[0] == C_NONE) psx_mod_write_word(CH_JUMP, CH_NOOP);
        psx_mod_write_word(CH_ROWS, (uint32_t)last + 1u);
        uint32_t n = 0;
        for (int k = 0; k <= last; k++) n += rows[k] != C_NONE;
        psx_mod_write_word(CH_COUNT, n);
        if (page >= 0) psx_mod_write_word(CH_CURSOR, want ? 1u : (uint32_t)page_row);
        page = want;
    }
}

static int level_entry_apply(void) {   /* 0: LA's own entry not known yet */
    uint32_t cur[8];
    for (int i = 0; i < 8; i++) cur[i] = psx_mod_read_word(LEVEL_LOC_TABLE + 96u + 4u * i);
    if (!s_la_saved) {                                     /* after the boot scan: LA's own entry */
        if (cur[0] == 0 || cur[0] == s_chi_entry[0] || (s_have_laday && cur[0] == s_laday_entry[0])
            || (s_have_night && cur[0] == s_night_entry[0])
            || (s_have_xd && (cur[0] == s_xd_entry[0][0] || cur[0] == s_xd_entry[1][0]))) return 0;
        for (int i = 0; i < 8; i++) s_la_entry[i] = cur[i];
        s_la_saved = 1;
    }
    uint32_t other[8];
    const uint32_t* want = s_la_entry;
    if (d2_virtual(s_virtual)) {
        want = s_chi_night && s_have_night ? s_night_entry : s_chi_entry;
        /* C101: 'Extra draw distance' on (driver.personal owns the C94 words: XDD 0x80093408 = 1) -> its level pair */
        if (s_have_xd && psx_mod_read_word(0x80093408u) == 1u) want = s_xd_entry[s_chi_night && s_have_night ? 1 : 0];
    }
    else if (la_day_active())
        want = s_laday_entry;                              /* C63: LA's day level */
    else if (s_virtual != V_LA && !is_extra(s_virtual)) {   /* another level file: its boot-time entry */
        for (int i = 0; i < 8; i++) other[i] = psx_mod_read_word(LEVEL_LOC_TABLE + 32u * (uint32_t)s_virtual + 4u * i);
        want = other;
    }
    if (cur[0] != want[0] && !psx_mod_read_word(AREA_LOADING_FLAG))
        for (int i = 0; i < 8; i++) psx_mod_write_word(LEVEL_LOC_TABLE + 96u + 4u * i, want[i]);
    {   /* C101: the level table's entry 3 is one of the extra-draw levels (its PVS is 27 x 27) */
        uint32_t e0 = psx_mod_read_word(LEVEL_LOC_TABLE + 96u);
        s_lvl_xd = s_have_xd && (e0 == s_xd_entry[0][0] || e0 == s_xd_entry[1][0]);
    }
    return 1;
}

/* M3 fixes (27.10., Strategy go; each separately revertible: CHI_VARIANT_REPLAY=0 / CHI_VARIANT_STATE=0 / CHI_VARIANT_LA=0).
 * Which level runs in CITY 3 is the plugin's host-side choice (LA, LA day, Chicago day / night, Havana day / night);
 * guest RAM did not record it. Variant codes: 0 LA (night, original), 1 Chicago day, 2 Chicago night, 3 Havana day,
 * 4 Havana night, 5 LA day.
 * (1) replays: bits 12-15 of the replay header word 0x80097644 (MCARD's packer keeps them; Driver 1 and the C88 / C106
 *     packers use bits 0-9) carry the variant of the game being recorded; a replay start (0x80096899 set) restores it at
 *     the mission parse, before the level loads. Quick Replay keeps the session's choice anyway.
 * (2) save states / rewind: the variant is mirrored into the zero-block word VARIANT_WORD (0x80093620, magic 0x56 in the
 *     top byte); restore_vblank re-applies it (asset set, level entry).
 * (3) the selector's choice holds for Take a Ride (mission 0x7C, the only menu with the page-2 city selector); any other
 *     mission starting in CITY 3 (LA's Undercover missions, Driving Games: their own D1 city list) runs LA, so no record
 *     is ever written under LA's key from a Chicago / Havana run (Take a Ride keeps no records). */
#define VARIANT_WORD   0x80093620u
#define REPLAY_HDR     0x80097644u
#define REPLAY_FLAG    0x80096899u
static int variant_switch(const char* name) {
    const char* e = getenv(name);
    return !(e && *e == '0');
}
/* variant codes: 0 LA, 5 LA day; D2 city id c: s_d2c[c].variant (+1 night) = Chicago 1/2, Havana 3/4, Las Vegas 6/7,
 * Rio 8/9 (4 bits in the replay header, 10..15 free) */
static uint32_t cur_variant(void) {
    int id = d2_id_of(s_virtual);
    if (id >= 0) return s_d2c[id].variant + (s_chi_night ? 1u : 0u);
    if (s_virtual == V_LA && s_have_laday && s_la_day) return 5u;
    return 0u;
}
static void apply_variant(uint32_t v, const char* why) {
    if (v > 9u || v == cur_variant()) return;
    int id = -1;
    for (int c = 0; c < D2C_N; c++) if (v == s_d2c[c].variant || v == s_d2c[c].variant + 1u) id = c;
    if (id > 0 && !s_have_city[id]) return;                 /* a replay of a city this package does not carry */
    select_virtual(id >= 0 ? s_d2_virt[id] : V_LA);
    s_chi_night = id >= 0 && v == s_d2c[id].variant + 1u;
    s_la_day = v == 5u;
    fprintf(stdout, "driver.chicago: level variant %u (%s)\n", (unsigned)v, why);
    level_entry_apply();
}
/* every vblank: the running game's variant into the header bits (not while a replay plays) and the mirror word */
static void variant_vblank(void) {
    if (!s_slot_enabled || psx_mod_read_word(CITY_WORD) != 3u || !psx_mod_game_started()) return;
    uint32_t v = cur_variant();
    if (variant_switch("CHI_VARIANT_REPLAY") && !psx_mod_read_byte(REPLAY_FLAG)) {
        uint32_t h = psx_mod_read_word(REPLAY_HDR), want = (h & ~0xF000u) | (v << 12);
        if (h != want) psx_mod_write_word(REPLAY_HDR, want);
    }
    if (variant_switch("CHI_VARIANT_STATE")) {
        uint32_t w = 0x56000000u | v;
        if (psx_mod_read_word(VARIANT_WORD) != w) psx_mod_write_word(VARIANT_WORD, w);
    }
}
/* the mission parse at a game / replay start (s0 = the mission number): (1) a replay's variant, (3) LA outside Take a Ride */
static void variant_parse(uint32_t mission) {
    if (!s_slot_enabled || mission != psx_mod_read_word(MISSION_NUMBER)) return;   /* in-game script parses: s0 differs */
    if (psx_mod_read_byte(REPLAY_FLAG)) {
        if (variant_switch("CHI_VARIANT_REPLAY") && mission == 0x7Cu)
            apply_variant((psx_mod_read_word(REPLAY_HDR) >> 12) & 0xFu, "replay header");
        return;
    }
    if (psx_mod_read_word(CITY_WORD) == 3u && (mission == 0x78u || mission == 0x79u || mission == 0x7Du))
        return;                                           /* a D2 / LA row's Day/Night confirm, remapped to 0x7C */
    if (variant_switch("CHI_VARIANT_LA") && mission != 0x7Cu && cur_variant() != 0u && !is_extra(s_virtual))
        apply_variant(0u, "not Take a Ride: Los Angeles");
}

static void chicago_slot_vblank(void) {
    cheats_vblank();
    variant_vblank();
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
            if (rows[cur].virt != s_virtual) select_virtual(rows[cur].virt);
            s_slot_chicago = s_virtual == V_CHICAGO;
        }
        preview_vblank(cur < (uint32_t)n && d2_virtual(rows[cur].virt));
        menu_tables();
    }
    /* Day/Night for the Chicago row: its confirm (Miami's) sets mission 0x78 and the Day/Night
     * screen adds the choice (0 day / 1 night). With city index 3 that is Chicago: the mission
     * goes back to LA's Take a Ride (0x7C: MISSION.BLK entry 0x5C, city 3) and the choice is kept. */
    if (s_slot_enabled && psx_mod_read_word(CITY_WORD) == 3u) {
        uint32_t m = psx_mod_read_word(MISSION_NUMBER);
        if ((m == 0x78u || m == 0x79u || m == 0x7Du) && s_virtual == V_LA && s_have_laday) {
            s_la_day = m == 0x78u;                        /* C63: the LA row's Day/Night choice */
            psx_mod_write_word(MISSION_NUMBER, 0x7Cu);
            fprintf(stdout, "driver.chicago: Los Angeles %s\n", s_la_day ? "day" : "night");
        } else if (m == 0x78u || m == 0x79u || m == 0x7Du) {
            s_chi_night = m != 0x78u;
            if (d2_id_of(s_virtual) <= 0) select_virtual(V_CHICAGO);   /* the Chicago row (or LA's confirm) */
            s_slot_chicago = 1;
            psx_mod_write_word(MISSION_NUMBER, 0x7Cu);
            fprintf(stdout, "driver.chicago: %s %s\n", s_d2c[s_assets_city].name, s_chi_night ? "night" : "day");
        }
    }
    if (s_slot_enabled && !s_classic && psx_mod_read_word(CITY_WORD) == 3u && extra_mission(s_virtual)
        && psx_mod_read_word(MISSION_NUMBER) == 0x7Cu) {
        psx_mod_write_word(MISSION_NUMBER, extra_mission(s_virtual));
        fprintf(stdout, "driver.chicago: Take a Ride -> mission 0x%X (level %d)\n", (unsigned)extra_mission(s_virtual), s_virtual);
        if (extra_mission(s_virtual) == 0xAEu) s_iv_sel = 1;
    }
    /* C80 (user R43: the selector's Interview without its timer): the IVIEW.BIN overlay (0x801E0000) adds 2 per update
     * to its timer 0x801E4278 (store 0x801E0738, a jump's delay slot) and ends the test at 0x1000 (0x801E0714); the
     * clock is drawn by 0x801E1248 (jal 0x801E0424). Only the selector's Interview (s_iv_sel: set by its Take a Ride
     * confirm, cleared when the frontend loads again; Undercover's interview keeps its timer): both become nops, re-checked
     * every vblank (Play Again reloads the overlay). RAM code: the runtime drops a native copy of changed code.
     * CHI_C80=0: unchanged. Host-only (M8: the same two words patched by guest code after the overlay load). */
    {
        static int c80 = -1, mark_prev = 1;
        if (c80 < 0) { const char* e = getenv("CHI_C80"); c80 = !(e && *e == '0'); }
        int mark = psx_mod_read_word(MENU_MARK) == 0x0172001Au;
        if (mark && !mark_prev) s_iv_sel = 0;                /* a new frontend session */
        mark_prev = mark;
        if (c80 && s_iv_sel && psx_mod_read_word(CITY_WORD) == 2u && psx_mod_read_word(0x801E0714u) == 0x28621000u) {
            if (psx_mod_read_word(0x801E0738u) == 0xAC824278u) psx_mod_write_word(0x801E0738u, 0u);
            if (psx_mod_read_word(0x801E0424u) == 0x0C078492u) {
                psx_mod_write_word(0x801E0424u, 0u);
                fprintf(stdout, "driver.chicago: C80 Interview (selector): timer + clock off\n");
            }
            /* C85 (user: hits never end the test, no X marks; the comments stay): the hit counter 0x801E35B8 (0..4) is
             * stored at 0x801E0D7C after the comment / speech; the X marks (0x801E1BCC) and the stop at 4 (0x801E0828)
             * read it -> the store becomes a nop, hits stay 0 (Polish 23.10.). CHI_C85=0: unchanged. */
            static int c85 = -1;
            if (c85 < 0) { const char* e = getenv("CHI_C85"); c85 = !(e && *e == '0'); }
            if (c85 && psx_mod_read_word(0x801E0D7Cu) == 0xAC8235B8u) {
                psx_mod_write_word(0x801E0D7Cu, 0u);
                fprintf(stdout, "driver.chicago: C85 Interview (selector): hits never counted\n");
            }
        }
    }
    {
        int via_la = via_la_for(s_virtual) && is_extra(s_virtual);
        int on = s_slot_enabled && !s_classic && via_la && psx_mod_read_word(MISSION_NUMBER) == 0x7Cu;
        uint32_t want_op = 0x24020000u | (uint32_t)(on ? s_virtual : 0);   /* addiu v0, zero, CITY */
        /* C135 (probe q73 freeze dumps): code words MUST go through psx_mod_write_code_word; a plain data write left the
         * native block running 'lw v0,4(t0)' (LA's CITY 3) while the plugin ran Newtown / Desert: the level loaded with
         * the wrong city's tables and a REPLAY.BLK read ran past the top of RAM into the exception vectors (FAIL-FAST
         * unknown dispatch 0x04200374 / 0x0C010034, ra 0x80077AC8). */
        uint32_t w = psx_mod_read_word(CITY_OP_WORD);
        if (on && w != want_op && (w == CITY_OP_ORIG || (w & 0xFFFFFFF8u) == 0x24020000u)) psx_mod_write_code_word(CITY_OP_WORD, want_op);
        else if (!on && (w & 0xFFFFFFF8u) == 0x24020000u) psx_mod_write_code_word(CITY_OP_WORD, CITY_OP_ORIG);
    }
    if (s_sea_level)                                       /* the flag word shares the sea level block */
        psx_mod_write_word(CHICAGO_FLAG_ADDR, chicago_active() ? 1u : 0u);
    {   /* S4a (20.10.): CHI_S4=1 -> the exe keeps a level's cell objects on the heap when they fit (Driver 1's own
         * layout, PS1-native); 0 (default for now) = the mod buffer for every city as before */
        static int s4 = -1;
        if (s4 < 0) {                                        /* env CHI_S4=1, or a file chi_s4.flag next to the exe (probes) */
            const char* e = getenv("CHI_S4");
            if (e && *e) s4 = (*e == '1') ? 1 : 0;
            else { FILE* f = fopen("chi_s4.flag", "rb"); s4 = f ? 1 : 0; if (f) fclose(f); }
            fprintf(stdout, "driver.chicago: S4 (cell objects on the heap when they fit) %s\n", s4 ? "on" : "off");
        }
        if (psx_mod_read_word(S4_FLAG_ADDR) != (uint32_t)s4) psx_mod_write_word(S4_FLAG_ADDR, (uint32_t)s4);
    }
    if (!s_slot_enabled || !psx_mod_game_started())
        return;
    if (!level_entry_apply())
        return;
    /* Take a Ride start: the mission script still names LA's start */
    int extra_run = is_extra(s_virtual) && psx_mod_read_word(CITY_WORD) == (uint32_t)s_virtual;
    if (!other_level_active() && !extra_run)
        return;
    if (extra_mission(s_virtual))                          /* their own missions carry their starts */
        return;
    int32_t sx = d2_virtual(s_virtual) ? s_chi_start[0] : s_level_start[s_virtual][0];
    int32_t sz = d2_virtual(s_virtual) ? s_chi_start[1] : s_level_start[s_virtual][1];
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
/* M3 Havana (hav4: D2 TLIGHT1 -> TLIGHT00, SLIGHT1 -> SLIGHT01): its signal head is HORIZONTAL (lenses at x 446 / 550 /
 * 654, y -1094..-1051, front z +71); Driver 1's code places red / amber / green by y only, so all three glows sit on
 * the middle lens (x 550, y -1072); street lamp head x 359, y -1790 (Polish: SLIGHT01 head x 403, y -1820, with
 * Chicago's offset between Polish's head and the plugin's glow point: -44 / +30). */
static const uint32_t s_glow_words[][6] = {          /* address, LA, Chicago, Havana, Las Vegas, Rio */
    { 0x800530E4u, 0x2406FCFEu, 0x24060505u, 0x240604F6u , 0x24060579u, 0x24060683u },   /* kind 0 (TLIGHT00) a2: x = a2 - 720 */
    { 0x800530F8u, 0x2406FD26u, 0x240602D0u, 0x240602D0u , 0x24064306u, 0x240602D0u },   /* kind 1 (TLIGHT01) a2; Vegas (vegas4
                                     pole light, lens x 54): 774 + 0x4000 = C133's own-height mark (exe cave LGTY) */
    { 0x800537E4u, 0x2406FA4Cu, 0x2406FC43u, 0x2406FBD0u , 0x2406FAA8u, 0x2406FB4Bu },   /* red y */
    { 0x800537F8u, 0x2406FABAu, 0x2406FC94u, 0x2406FBD0u , 0x2406FB19u, 0x2406FBB3u },   /* amber y */
    { 0x8005380Cu, 0x2406FB28u, 0x2406FCE5u, 0x2406FBD0u , 0x2406FB8Au, 0x2406FC1Au },   /* green y */
    { 0x80053814u, 0x2407FFBAu, 0x2407FF9Cu, 0x24070047u , 0x24070046u, 0x2407000Du },   /* z (front face) */
    { 0x80053118u, 0x2405044Cu, 0x24050230u, 0x24050167u , 0x24050450u, 0x24050254u },   /* kind 3 SLIGHT01 lamp 1 x */
    { 0x8005311Cu, 0x2406F79Au, 0x2406F998u, 0x2406F902u , 0x2406F447u, 0x2406F880u },   /* kind 3 lamp 1 y */
    { 0x80053130u, 0x2405FBB4u, 0x24050230u, 0x24050167u , 0x2405FBB0u, 0x24050254u },   /* kind 3 lamp 2 x (Chicago / Havana / Rio: the same lamp) */
    { 0x80053138u, 0x2406F79Au, 0x2406F998u, 0x2406F902u , 0x2406F447u, 0x2406F880u },   /* kind 3 lamp 2 y */
    { 0x8005310Cu, 0x2405FC7Cu, 0x2405FC7Cu, 0x2405FC7Cu , 0x24050444u, 0x2405FC7Cu },   /* kind 2 SLIGHT00 lamp x (one glow) */
    { 0x80053114u, 0x2406F6D2u, 0x2406F6D2u, 0x2406F6D2u , 0x2406F5F8u, 0x2406F6D2u },   /* kind 2 lamp y */
};
/* glow words: column 1 LA, 2 Chicago, 3 Havana, 4 Las Vegas, 5 Rio (written only over one of the known values).
 * Las Vegas (vegas1, Polish 28.10.): vertical heads (3 identical on the arm; Driver 1 draws one glow set: the head nearest
 * the pole, x 681), lenses in thirds y -1368 / -1255 / -1142 (texture not split per lens: assumed), front z 70; SLIGHT00
 * = D2 DLIGHT01, double-headed like LA's lamp: heads (+-1148, -3031) -> glow (+-1104, -3001) (Chicago's -44 / +30 offset,
 * mirrored); vegas2 (Polish 28.10.) names it SLIGHT01 = kind 3 (0x80053118.., two glows: +-1104, -3001) and the single lamp
 * (1136, -2598) SLIGHT00 = kind 2 (0x8005310C / 14, one glow) -> (1092, -2568). (vegas1 had the names the other way.) Rio (rio1): one head x 947, red -1205 / amber -1101 / green -998 (separate lens textures), front z 13; lamp
 * SLIGHT01 only (as Chicago / Havana: both lamp words) head (640, -1950) -> (596, -1920). Neither city has a TLIGHT01. */
/* C133: kind 1's own lens height / depth against kind 0's (exe cave LGTY, words LGDY / LGDZ): Las Vegas' pole light
 * (vegas4, Polish: lenses (54, -709 / -615 / -521, -5)) vs the arm head (-1368 / -1255 / -1142, z 70): +659, -75 (amber /
 * green land 19 / 38 below their lens: one shared offset). 0 elsewhere. */
static void switch_glow_kind1(int col) {
    int32_t dy = col == 4 ? 659 : 0, dz = col == 4 ? -75 : 0;
    if ((int32_t)psx_mod_read_word(0x80093638u) != dy) psx_mod_write_word(0x80093638u, (uint32_t)dy);
    if ((int32_t)psx_mod_read_word(0x8009363Cu) != dz) psx_mod_write_word(0x8009363Cu, (uint32_t)dz);
}
static void switch_glow(int col) {
    switch_glow_kind1(col);
    for (unsigned i = 0; i < sizeof s_glow_words / sizeof s_glow_words[0]; i++) {
        uint32_t cur = psx_mod_read_word(s_glow_words[i][0]), want = s_glow_words[i][col];
        int known = 0;
        for (int c = 1; c < 6; c++) known |= cur == s_glow_words[i][c];
        if (cur != want && known)
            psx_mod_write_code_word(s_glow_words[i][0], want);   /* code immediates: executable-RAM path */
    }
}
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
            psx_mod_write_code_word(t[i][0], want);              /* code: executable-RAM path */
    }
}
/* Minimap (C12, Polish): the exe's per-city frame table 0x8008B080 (24 bytes per CITY: x / y
 * offset, width, height, toptile | fill << 8, units per pixel) gets Driver 2's map frame in the
 * CITY 3 entry while Chicago is chosen (the level init 0x800541E8 reads it), LA's otherwise. */
#define MAP_ENTRY3          (0x8008B080u + 3u * 24u)
static void minimap_vblank(int chi) {
    /* LA's own entry, as in the exe (C62 16.10.: it used to be copied from RAM on the first vblank,
     * which during boot ran before the exe was loaded and saved garbage: LA's minimap all red) */
    static const uint32_t la[6] = { 324u, 175u, 192u, 416u, 78u, 2812u };
    if (!s_have_map) return;
    uint32_t cur[6];
    for (int i = 0; i < 6; i++) cur[i] = psx_mod_read_word(MAP_ENTRY3 + 4u * (uint32_t)i);
    if (!chi && cur[2] == 0) return;                      /* exe data not loaded yet */
    const uint32_t* want = chi ? s_chi_map : la;
    if (memcmp(cur, want, sizeof cur))
        for (int i = 0; i < 6; i++) psx_mod_write_word(MAP_ENTRY3 + 4u * (uint32_t)i, want[i]);
}
/* Sky (C10, Polish): the level init sets the sky number gp+0xD7C from CITY (CITY 3: 2, rain 3,
 * at 0x8004EDE0 / 0x8004EDEC / 0x8004EE00, then reads SKY.BIN); the package's SKY.BIN carries
 * Chicago's skies as 13 day, 14 night, 15 rain, so these immediates name them while Chicago is
 * chosen. */
/* C63: LA by day takes Design's LA day sky (SKY.BIN 16, in the package's relocated SKY.BIN, sidecar flag 4), else one
 * of Driver 1's day skies (Miami day 4, rain Miami rain 6); CHI_LADAY_SKY=n picks another (rain = n + 2 for Miami 4 /
 * NY 7 / SF 10) */
static uint32_t laday_sky(int rain) {
    static int sky = -1;
    if (sky < 0) { const char* e = getenv("CHI_LADAY_SKY"); sky = e && *e ? atoi(e) & 0xFF : (s_have_laday_sky ? 16 : 4); }
    return (uint32_t)(rain && (sky == 4 || sky == 7 || sky == 10) ? sky + 2 : sky);
}
static void sky_vblank(int chi) {
    static const uint32_t addr[3] = { 0x8004EDE0u, 0x8004EDECu, 0x8004EE00u };
    int c = chi && s_have_sky, d = la_day_active();
    if (!s_have_sky && !s_have_laday) return;
    for (int i = 0; i < 3; i++) {
        uint32_t la = i ? 3u : 2u;
        uint32_t want = 0x24020000u | (c ? s_sky_base + (i ? 2u : s_chi_night ? 1u : 0u) : d ? laday_sky(i) : la);
        uint32_t cur = psx_mod_read_word(addr[i]);
        uint32_t imm = cur & 0xFFFFu;
        if (cur != want && (cur & 0xFFFF0000u) == 0x24020000u
            && (imm == la || (imm >= 13u && imm < 64u) || imm == laday_sky(0) || imm == laday_sky(1)))   /* C126: any of the
            package's skies (13.. = Chicago, LA day, Havana, Las Vegas, Rio), not only Chicago's 13-15 */
            psx_mod_write_code_word(addr[i], want);   /* code immediates */
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
/* C45 test tool (16.10., test copies only: env CHI_TEST_POSE = a file path, unset = off): holds the player car at
 * the pose in that file ("x y z angle" in world units / 4096ths of a turn, re-read every 6 vblanks; no file or a bad
 * line = hands off) and re-applies it every vblank (position, matrix, quaternion, zero velocities), so the chase
 * camera settles on the same view every run (deterministic camera test, scratch c45cam.py). Host-only test aid. */
static void test_pose_vblank(void) {
    static int init, on, have, tick;
    static char path[512];
    static int32_t px, py, pz, pa;
    if (!init) {
        const char *e = getenv("CHI_TEST_POSE");
        init = 1;
        if (e && *e) { on = 1; snprintf(path, sizeof path, "%s", e); }
    }
    if (!on) return;
    if ((tick++ % 6) == 0) {
        FILE *f = fopen(path, "r");
        int a, b, c, d;
        have = 0;
        if (f) {
            if (fscanf(f, "%d %d %d %d", &a, &b, &c, &d) == 4) { px = a; py = b; pz = c; pa = d; have = 1; }
            fclose(f);
        }
    }
    /* C40 (24.10.): any city (Miami dense spots for the FPS comparison); still test copies only (env CHI_TEST_POSE) */
    if (!have || !psx_mod_game_started() || psx_mod_read_word(0x8009B0BCu) == 0u) return;
    const uint32_t B = 0x8009B0A4u;
    double ang = 2.0 * 3.14159265358979 * (double)pa / 4096.0;
    int16_t c = (int16_t)lround(4096.0 * cos(ang)), sn = (int16_t)lround(4096.0 * sin(ang));
    int16_t m[9] = { c, 0, sn, 0, 4096, 0, (int16_t)-sn, 0, c };
    for (int k = 0; k < 9; k++) psx_mod_write_half(B + 4u + 2u * (uint32_t)k, (uint16_t)m[k]);
    int32_t w[16] = { px, py, pz, px * 16, py * 16, pz * 16, 0, (int32_t)lround(4096.0 * sin(ang / 2.0)), 0,
                      (int32_t)lround(4096.0 * cos(ang / 2.0)), 0, 0, 0, 0, 0, 0 };
    for (int k = 0; k < 16; k++) psx_mod_write_word(B + 0x18u + 4u * (uint32_t)k, (uint32_t)w[k]);
}
/* C92 test aid (test copies only, env CHI_TEST_OC=<file>): the file holds a CPU percent (100..400) that is applied at
 * once, so a runner test can record with the overclock on and replay with it off in one session. Host-only. */
static void test_oc_vblank(void) {
    static int init, on; static char path[512]; static uint32_t tick;
    if (!init) { const char* e = getenv("CHI_TEST_OC"); init = 1; if (e && *e) { on = 1; snprintf(path, sizeof path, "%s", e); } }
    if (!on || (tick++ % 10u) != 0u) return;
    FILE* f = fopen(path, "r");
    int v;
    if (f) { if (fscanf(f, "%d", &v) == 1) psx_mod_set_cpu_overclock((uint32_t)v); fclose(f); }
}
/* M3: a Driver 2 city's own start heading (sidecar word 54; Havana 1025 = D2's Take a Drive rotation). LA's Take a Ride
 * script spawns the car with LA's heading; on the first frames of a level start (car still at the start, not moving)
 * the plugin turns it in place: orientation matrix, quaternion (+0x30) and heading (+0xF8), as the runner pose tool does.
 * Once per level start (the game frame counter going back re-arms it). Host-only (M8: the heading in the mission script
 * or a per-city start table). */
static void start_heading_vblank(void) {
    static uint32_t last_fc, done;
    uint32_t fc = psx_mod_read_word(0x800970D8u);
    if (fc < last_fc) done = 0;
    last_fc = fc;
    if (done || !s_start_rot || !chicago_active() || !psx_mod_game_started() || fc > 60u) return;
    const uint32_t B = 0x8009B0A4u;
    int32_t x = (int32_t)psx_mod_read_word(B + 0x18u), y = (int32_t)psx_mod_read_word(B + 0x1Cu), z = (int32_t)psx_mod_read_word(B + 0x20u);
    if (x == 0 && z == 0) return;
    if (labs((long)(x - s_chi_start[0])) > 400 || labs((long)(z - s_chi_start[1])) > 400) { done = 1; return; }
    double ang = 2.0 * 3.14159265358979 * (double)s_start_rot / 4096.0;
    int16_t c = (int16_t)lround(4096.0 * cos(ang)), sn = (int16_t)lround(4096.0 * sin(ang));
    int16_t m[9] = { c, 0, sn, 0, 4096, 0, (int16_t)-sn, 0, c };
    for (int k = 0; k < 9; k++) psx_mod_write_half(B + 4u + 2u * (uint32_t)k, (uint16_t)m[k]);
    int32_t w[16] = { x, y, z, x * 16, y * 16, z * 16, 0, (int32_t)lround(4096.0 * sin(ang / 2.0)), 0,
                      (int32_t)lround(4096.0 * cos(ang / 2.0)), 0, 0, 0, 0, 0, 0 };
    for (int k = 0; k < 16; k++) psx_mod_write_word(B + 0x18u + 4u * (uint32_t)k, (uint32_t)w[k]);
    psx_mod_write_word(B + 0xF8u, (uint32_t)(s_start_rot & 4095));
    if (fc < 12u) return;                             /* held over the first frames (the spawn settles them) */
    done = 1;
    fprintf(stdout, "driver.chicago: start heading %d (frame %u)\n", (int)s_start_rot, (unsigned)fc);
}
/* C132 (user: the Driver 2 night look; D2 cities at night only, CHI_C132_LOOK=0 = off). D2 cities run their nights with
 * Driver 1's night flag 0 and LOOK_CITY 3, so Driver 1 draws them with its DAY facing colours and LA's night car colour:
 * (a) FUN_8002D0F4's day branch loads the 8 facing colours 0x808080 / 0x707070 / 0x606060 / 0x505050 / 0x404040 (scratchpad
 *     0x1F800024..43, by 45-degree facing): D2 draws night buildings flat (draw.c SetupPlaneColours: every plane = ambient
 *     0x80) -> the four darker immediates become 0x808080 while a D2 night runs;
 * (b) DrawCar (FUN_8003A698) forces the car colour word 0x800971A0 to 0x282828 for LOOK_CITY 3 at night (LA's night):
 *     D2's night cars are lit at 880 / 905 of 3200 (cars.c night_colours) -> 0x242323 (R / G 35, B 36).
 * Host-written code immediates like the glows (M8: a guest flag word / data words instead). */
static const uint32_t s_night_look_words[][3] = {    /* address, Driver 1, D2 night */
    { 0x8002D46Cu, 0x3C060070u, 0x3C060080u }, { 0x8002D470u, 0x34C67070u, 0x34C68080u },
    { 0x8002D474u, 0x3C040060u, 0x3C040080u }, { 0x8002D478u, 0x34846060u, 0x34848080u },
    { 0x8002D47Cu, 0x3C020050u, 0x3C020080u }, { 0x8002D480u, 0x34425050u, 0x34428080u },
    { 0x8002D484u, 0x3C030040u, 0x3C030080u }, { 0x8002D488u, 0x34634040u, 0x34638080u },
    { 0x8003A6D0u, 0x3C020028u, 0x3C020024u }, { 0x8003A6D4u, 0x34422828u, 0x34422323u },
};
static void night_look_vblank(int chi) {
    static int on = -1;
    if (on < 0) { const char* e = getenv("CHI_C132_LOOK"); on = !(e && *e == '0'); }
    int col = on && chi && s_chi_night ? 2 : 1;
    for (unsigned i = 0; i < sizeof s_night_look_words / sizeof s_night_look_words[0]; i++) {
        uint32_t cur = psx_mod_read_word(s_night_look_words[i][0]), want = s_night_look_words[i][col];
        if (cur != want && (cur == s_night_look_words[i][1] || cur == s_night_look_words[i][2]))
            psx_mod_write_code_word(s_night_look_words[i][0], want);   /* code: the executable-RAM path (native blocks) */
    }
    /* (c) glow kind 4 = SLIGHT02 (exe_patches c132_patches: cave K4, words LX4 / LY4 0x80093640 / 44): CITY 3's table count
     * 0x8008AE68 = 5 only while a city whose level keeps SLIGHT02 resident is chosen (Las Vegas, vegas5 keeps it in memory), else Driver 1's 4
     * (the 5th entry would keep model id 0 where nothing resolves it). */
    int k4 = s_slot_enabled && s_virtual == V_VEGAS && on;
    uint32_t cnt = k4 ? 5u : 4u;
    if (psx_mod_read_word(0x8008AE68u) != cnt) psx_mod_write_word(0x8008AE68u, cnt);
    int32_t lx = k4 ? 771 : 0, ly = k4 ? -2126 : 0;          /* vegas5: SLIGHT02 head (815, -2156) + (-44, +30) */
    if ((int32_t)psx_mod_read_word(0x80093640u) != lx) psx_mod_write_word(0x80093640u, (uint32_t)lx);
    if ((int32_t)psx_mod_read_word(0x80093644u) != ly) psx_mod_write_word(0x80093644u, (uint32_t)ly);
}
/* C134 (Polish 28.10.: Vegas downtown 'colour noise'): Driver 1 never clears the frame (its sky + ground tiles always cover
 * it); Driver 2 cities have spots without ground geometry, so the previous VRAM content showed there (the noise at the
 * Fremont start = garbage that was never drawn over). C134 cleared every frame to black (isbg = 1 in both DRAWENVs
 * 0x800BDFB4 / 0x800BE034: isbg +0x18, r0 g0 b0 +0x19..1B).
 * C142 (user review d2 cities 6: unloaded areas / 'loading zones' became a black void; keep Driver 1's look where the
 * last frame stays): Driver 2 itself never clears either (REDRIVER2 system.c SetDefDrawEnv: isbg 0). So the clear is now
 * one-shot: for CLEAR_VBL vblanks after a D2 level starts running (in-level heartbeat rising edge) both buffers clear to
 * the level's fog colour (0x80097138, 0x00BBGGRR, set at level init), which wipes the old VRAM garbage; then isbg = 0 as
 * in Driver 1 / 2 (never-drawn spots keep the fog colour until something is drawn there, then show the last frame).
 * D1 cities: isbg 0 as before. CHI_C134=0: off; CHI_C142=0: C134's clear every frame. (M8: a guest data word.) */
#define CLEAR_VBL 6u
static void clear_bg_vblank(int chi) {
    static int on = -1, every = -1;
    if (on < 0) { const char* e = getenv("CHI_C134"); on = !(e && *e == '0'); }
    if (every < 0) { const char* e = getenv("CHI_C142"); every = e && *e == '0'; }
    static int was_in;
    static uint32_t left;
    int in_level = s_lvl_seen && s_vbl_n - s_lvl_beat <= LVL_BEAT_MAX;
    if (chi && in_level && !was_in) left = CLEAR_VBL;            /* a D2 level started running */
    was_in = chi && in_level;
    int clear = on && chi && (every || left > 0u);
    if (left) left--;
    uint32_t fog = psx_mod_read_word(0x80097138u) & 0x00FFFFFFu;
    static const uint32_t env[2] = { 0x800BDFB4u, 0x800BE034u };
    for (int i = 0; i < 2; i++) {
        uint32_t a = env[i] + 0x18u, w = psx_mod_read_word(a);    /* isbg | r0 << 8 | g0 << 16 | b0 << 24 */
        if (psx_mod_read_half(env[i] + 4u) != 0x200u) continue;    /* not a DRAWENV (yet) */
        uint32_t want = clear ? (1u | (every ? 0u : fog << 8)) : 0u;
        if (w != want && (w & 0xFFu) <= 1u) psx_mod_write_word(a, want);
    }
}
/* C147 (2) (Polish C146: Driver 2's neon cycles, ours was static): REDRIVER2 objanim.c ColourCycle, per game frame while
 * not paused (D2: StepSim then ColourCycle unless fast-forward): nothing while an area loads (phase back to 0), odd frames
 * skipped; phase 0 reads each cycling texture's 16-entry CLUT row from VRAM, later even frames rotate entry start..stop
 * down by one (old start at stop) for both ranges when (cycle_timer & speed) == 0 and upload the row; cycle_timer counts
 * the stepping calls. Table = the level variant's .cyc.bin (CYC1: name, our page, texture index, start1 / stop1 / speed1,
 * start2 / stop2 / speed2). Driver 1 equivalents: frame counter 0x800970D8 (paused: it stands still), page loaded =
 * tpageslots 0x800BE4F8 (16 slot bytes) holds the page, CLUT word 0x80087030[page * 32 + tex] (as texture_cluts).
 * A CLUT row another loaded texture shares is left alone (would cycle that one too; logged once).
 * Host-only (M8: guest table + StoreImage / LoadImage of the 16-entry rows per frame, like D2). CHI_C147_CYCLE=0: off. */
static int vram_put(int x, int y, int w, int h, const uint16_t* px);
static void colour_cycle_vblank(int chi) {
    static int en = -1;
    if (en < 0) { const char* e = getenv("CHI_C147_CYCLE"); en = !(e && *e == '0'); }
    static uint32_t last_fc, timer, logged;
    static int phase, cur_t = -1;
    static uint16_t buf[24][16];
    static uint16_t clut[24];
    int t = (s_chi_night ? 1 : 0) + (s_lvl_xd ? 2 : 0);
    int in_level = s_lvl_seen && s_vbl_n - s_lvl_beat <= LVL_BEAT_MAX;
    const uint8_t* c = s_cyc[t];
    uint32_t n = s_cyc_n[t] >= 8u && !memcmp(c, "CYC1", 4) ? (uint32_t)c[4] | ((uint32_t)c[5] << 8) : 0u;
    if (n > 24u || 8u + 28u * n > s_cyc_n[t]) n = 0;
    uint32_t fc = psx_mod_read_word(0x800970D8u);
    if (!en || !chi || !in_level || !n || t != cur_t) { phase = 0; timer = 0; cur_t = t; last_fc = fc; return; }
    if (fc == last_fc) return;                               /* no new game frame (paused, menu) */
    uint32_t steps = fc - last_fc; last_fc = fc;
    if (steps > 4u) steps = 1u;
    if (psx_mod_read_word(AREA_LOADING_FLAG)) { phase = 0; return; }
    uint8_t slots[16];
    for (uint32_t s = 0; s < 16u; s++) slots[s] = psx_mod_read_byte(0x800BE4F8u + s);
    for (uint32_t k = 0; k < steps; k++) {
        uint32_t frame = fc - steps + 1u + k;
        if (frame & 1u) continue;
        for (uint32_t i = 0; i < n; i++) {
            const uint8_t* e = c + 8u + 28u * i;
            int16_t par[8]; memcpy(par, e + 12, 16);
            uint32_t page = (uint16_t)par[0], tex = (uint16_t)par[1];
            if (page >= 128u || tex >= 32u) continue;
            int loaded = 0;
            for (uint32_t s = 0; s < 16u; s++) if (slots[s] == page) loaded = 1;
            if (!loaded) continue;
            if (phase == 0) {
                uint16_t cw = psx_mod_read_half(0x80087030u + 2u * (page * 32u + tex));
                clut[i] = 0;
                int cx = (cw & 63u) << 4, cy = cw >> 6;
                if (!cw || cx + 16 > 1024 || cy >= 512) continue;
                int shared = 0;                               /* another loaded texture with this CLUT row? */
                for (uint32_t s = 0; s < 16u && !shared; s++) {
                    if (slots[s] == 0xFFu || slots[s] >= 128u) continue;
                    for (uint32_t x = 0; x < 32u; x++)
                        if ((slots[s] != page || x != tex) && psx_mod_read_half(0x80087030u + 2u * (slots[s] * 32u + x)) == cw) { shared = 1; break; }
                }
                if (shared) {
                    if (!(logged & (1u << i))) { logged |= 1u << i; fprintf(stdout, "driver.chicago: C147 cycle: %.12s CLUT %04X shared, not cycled\n", (const char*)e, cw); }
                    continue;
                }
                clut[i] = cw;
                for (int j = 0; j < 16; j++) buf[i][j] = gpu_vram_peek(cx + j, cy);
                continue;
            }
            if (!clut[i]) continue;
            for (int r = 0; r < 2; r++) {
                int start = par[2 + 3 * r], stop = par[3 + 3 * r], speed = par[4 + 3 * r];
                if (start < 0 || stop > 15 || start >= stop || (timer & (uint32_t)speed) != 0u) continue;
                uint16_t tmp = buf[i][start];
                memmove(&buf[i][start], &buf[i][start + 1], (size_t)(stop - start) * 2u);
                buf[i][stop] = tmp;
            }
            vram_put((clut[i] & 63u) << 4, clut[i] >> 6, 16, 1, buf[i]);
        }
        if (phase) timer++;
        else phase = 1;
    }
}

static void glow_offsets_vblank(void) {
    test_oc_vblank();
    test_pose_vblank();
    start_heading_vblank();
    int chi = chicago_active();
    night_look_vblank(chi);
    clear_bg_vblank(chi);
    colour_cycle_vblank(chi);
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
    {   /* C12 zoom (16.10.): MAP_CLUT_EXTRA (0x800978A4 = gp+0x1134, exe_patches MAP_CLUT) moves the map CLUT read
         * behind a Driver 2 map's larger tile table (polish_map CLUT_AT = 2 x tiles + 8, word aligned, when the
         * map has more than D1's 160 tile slots); 0 = map + 0x148 as in every D1 city */
        uint32_t tiles = s_have_map ? (s_chi_map[4] & 0xFFu) : 0u;
        uint32_t extra = (chi && tiles > 160u) ? (((2u * tiles + 8u + 3u) & ~3u) - 0x148u) : 0u;
        if (psx_mod_read_word(0x800978A4u) != extra) psx_mod_write_word(0x800978A4u, extra);
    }
    /* C37 (16.10.): D2_PLANES (0x80097880 = gp+0x1110, exe_patches slope_div): -1 = MapHeight / FindSurfaceD2 divide
     * the plane by b (Driver 2's sdHeightOnPlane, exact slopes), 0 = Driver 1's >> 12 (bit-identical) */
    if (psx_mod_read_word(0x80097880u) != (chi ? 0xFFFFFFFFu : 0u)) psx_mod_write_word(0x80097880u, chi ? 0xFFFFFFFFu : 0u);
    /* C45 quay (16.10.): NEAR_SUB (0x80097894 = gp+0x1124, exe_patches NEAR_SUB) = Driver 2's near-only
     * subdivision (big world quads leaving the guard band, big tiles reaching the camera); 0 in every D1 city */
    {   /* bit 0 = world quads, bit 1 = tiles; CHI_NEAR_SUB_BITS overrides the Driver 2 value (tests) */
        static int bits = -1;
        if (bits < 0) { const char* e = getenv("CHI_NEAR_SUB_BITS"); bits = e && *e ? atoi(e) & 3 : 3; }
        uint32_t want = chi ? (uint32_t)bits : 0u;
        if (psx_mod_read_word(0x80097894u) != want) psx_mod_write_word(0x80097894u, want);
        /* NEAR_PIECE (0x800978AC = gp+0x113C): sub-pieces with avg sz / 2 < 0x20 + this are dropped (D1: 0) */
        static int piece = -1;
        if (piece < 0) { const char* e = getenv("CHI_NEAR_PIECE"); piece = e && *e ? atoi(e) & 0x3FF : 96; }
        uint32_t pw = chi ? (uint32_t)piece : 0u;
        if (psx_mod_read_word(0x800978ACu) != pw) psx_mod_write_word(0x800978ACu, pw);
    }
    sky_vblank(chi);
    switch_glow(!chi ? 1 : s_d2c[s_assets_city].glow);
    int chday = (other_level_active() && !(d2_virtual(s_virtual) && s_chi_night)) || la_day_active();
    /* C63: LA by day: LA's Take a Ride script sets the night flag (opcode 0x1F) in the parse; cleared here every
     * vblank (the parse runs before the level load, whose readers come after several CD-wait vblanks) */
    if (la_day_active() && psx_mod_read_word(NIGHT_FLAG) != 0u) psx_mod_write_word(NIGHT_FLAG, 0u);
    /* C47 (14.10.): with the static exe patch (exe_patches look_city_patches) the CITY == 3 sites read
     * LOOK_CITY (0x8009789C: CITY, or 0x7F for Chicago by day) and C3 (0x80097898: 3, or 0x7F) from main
     * RAM; no code word is rewritten, so those functions stay native. Without it (older exe) the code
     * words are switched as before. */
    uint32_t look = chday ? 0x7Fu : psx_mod_read_word(CITY_WORD), c3 = chday ? 0x7Fu : 3u;
    if (psx_mod_read_word(0x8009789Cu) != look) psx_mod_write_word(0x8009789Cu, look);
    if (psx_mod_read_word(0x80097898u) != c3) psx_mod_write_word(0x80097898u, c3);
    /* C63 (Design 18.10.): LA by day: the far-street flat quads take the plane word 0x80097150 and the fog word
     * 0x80097138 (set once per level by 0x800298BC, read by 0x800270D4; 0x00BBGGRR); they held LA's night values.
     * Day: plane (112, 111, 105), fog (226, 212, 190). LA night and the D1 cities keep the exe's values. */
    if (la_day_active()) {
        if (psx_mod_read_word(0x80097150u) != 0x00696F70u) psx_mod_write_word(0x80097150u, 0x00696F70u);
        if (psx_mod_read_word(0x80097138u) != 0x00BED4E2u) psx_mod_write_word(0x80097138u, 0x00BED4E2u);
    }
    /* C55 (16.10.): SUN_CITY (0x80097884, exe sky-sun test 0x8004702C) = LOOK_CITY, except Chicago: 0x7F by day,
     * 0x7E by night (the moon disc is drawn, its glare skipped by the exe stub 0x80011868) */
    {
        uint32_t sun = chicago_active() ? (s_chi_night ? 0x7Eu : 0x7Fu) : look;
        if (psx_mod_read_word(0x80097884u) != sun) psx_mod_write_word(0x80097884u, sun);
    }
    /* C51: CARSET_CITY (0x800978A0) picks the damage zone tables (exe patch at 0x8003E5A8): the city whose
     * car set the loaded Chicago level carries (Miami's by day), else CITY */
    uint32_t cs = chicago_active() ? (s_chi_night ? (s_carsets >> 8) & 0xFFu : s_carsets & 0xFFu)
                                   : psx_mod_read_word(CITY_WORD);
    if (psx_mod_read_word(0x800978A0u) != cs) psx_mod_write_word(0x800978A0u, cs);
    /* C17: DROWN_RANGE (0x800978A8, exe_patches DROWN_EDGE): a car with a wheel on sea ground whose y lies in
     * [-1120, -1120 + range) drowns even if its centre cell is not water; Driver 2 cities only (0 = D1 rule) */
    /* M3: the band [-(water + 36), -(water + 36) + range) must stay below the street: Chicago's deep water (1084) keeps 620,
     * Havana's shallow harbour (160) gets range = band start, i.e. up to y 0 */
    uint32_t dr = chi ? (uint32_t)(-s_sea_y + 36 < 620 ? -s_sea_y + 36 : 620) : 0u;
    if (psx_mod_read_word(0x800978A8u) != dr) psx_mod_write_word(0x800978A8u, dr);
    /* M3: BANDW 0x80093624 (exe_patches C17 band cave) = the band start: 36 under the city's water (Chicago 1120,
     * Havana 2786); 0 in the D1 cities (DROWN_RANGE 0 there anyway) */
    {
        uint32_t band = chi ? (uint32_t)(-s_sea_y + 36) : 0u;
        if (psx_mod_read_word(0x80093624u) != band) psx_mod_write_word(0x80093624u, band);
    }
    /* C66 (17.10.): NEARCULL (0x80093390, exe_patches c66_patches): car polygons whose RTPT saturated (vertex behind / at
     * the camera) are rejected in Chicago; 0 = Driver 1's drawing (garbled near polygons) in the D1 cities */
    {
        uint32_t nc = chi ? 0x80000000u : 0u;
        if (psx_mod_read_word(0x80093390u) != nc) psx_mod_write_word(0x80093390u, nc);
    }
    /* Chicago night moon (Design SKY_SPRITES, 14.10.): D1's sun/flare routine draws SKYSUN at the day vector
     * 0x80096C24 (x, y, z halfwords) at night too; Chicago night (whose LEV may carry D2's SKYMOON in the SKYSUN
     * slot, CHI_NIGHT_MOON) puts it where D2 puts its moon: (-32000, -11500, -18000). Everything else: D1's sun
     * (-32000, -11000, -5000). Host-only (M8: a per-city vector table or the night LEV). */
    {
        int moon = chicago_active() && s_chi_night;
        uint32_t w0 = moon ? ((uint32_t)(uint16_t)-32000 | ((uint32_t)(uint16_t)-11500 << 16))
                           : ((uint32_t)(uint16_t)-32000 | ((uint32_t)(uint16_t)-11000 << 16));
        uint32_t w1 = moon ? (uint32_t)(uint16_t)-18000 : (uint32_t)(uint16_t)-5000;
        if (psx_mod_read_word(0x80096C24u) != w0) psx_mod_write_word(0x80096C24u, w0);
        if ((psx_mod_read_word(0x80096C28u) & 0xFFFFu) != w1)
            psx_mod_write_word(0x80096C28u, (psx_mod_read_word(0x80096C28u) & 0xFFFF0000u) | w1);
    }
    {   /* R35 (exe_patches C35T): THRS 0x800933B8 = the player thrust scale (1/4096) in car set 4: the player choice's
         * cosmetics row (COS entry 0, +96) carries Driver 2's powerRatio x 4915 x 1.32 / 7200 (convert polish_cosmetics);
         * 0 elsewhere = Driver 1's thrust (Miami choice 3 keeps its 19/16) */
        uint32_t cs4 = psx_mod_read_word(0x800978A0u);
        int32_t v = (int32_t)(int16_t)psx_mod_read_half(0x800A0E20u + 96u);
        uint32_t want = (cs4 == 4u && chicago_active() && v >= 1024 && v <= 8192 && v != 4096) ? (uint32_t)v : 0u;
        if (psx_mod_read_word(0x800933CCu)) {           /* C88 SUPER SPEED (SPD2): thrust x 2 (drag is linear: top speed x 2) */
            uint32_t base = want ? want : ((psx_mod_read_word(0x8009683Cu) == 3u && psx_mod_read_word(0x80096834u) == 0u)
                                           ? 4864u : 4096u);   /* C35T's Miami choice-3 rule (19 / 16) */
            want = 2u * base;
        }
        if (psx_mod_read_word(0x800933B8u) != want) psx_mod_write_word(0x800933B8u, want);
    }
    /* C42 step 1 / r3 (b): car-set city 4 = Driver 2 traffic cars: their civ zone rows (resident models 1..3 or 1..5,
     * verts 300 B + polys 420 B per model) in a mod-memory block; entry 4 of the exe's civ verts / polys pointer tables
     * (0x8008A6EC / 0x8008A72C) points one row before it (row 0 = the player's, unused). The old place 0x800A0E20 holds
     * the six-model tables now (exe_patches c42m_patches). */
    {
        uint32_t nm = s_dmg_civ_n == 900u ? 5u : (s_dmg_civ_n == 540u ? 3u : 0u);
        if (cs == 4u && nm && !s_civ_block) s_civ_block = psx_mod_alloc_guest_memory(3600u, 16u);
        if (cs == 4u && nm && s_civ_block) {
            uint32_t pv = s_civ_block + 1500u;            /* polys rows after 5 verts rows */
            if (psx_mod_read_word(0x8008A6ECu) != s_civ_block - 300u) psx_mod_write_word(0x8008A6ECu, s_civ_block - 300u);
            if (psx_mod_read_word(0x8008A72Cu) != pv - 420u) psx_mod_write_word(0x8008A72Cu, pv - 420u);
            if (psx_mod_read_word(s_civ_block) != s_dmg_civ[0] || psx_mod_read_word(pv) != s_dmg_civ[75u * nm]) {
                for (uint32_t i = 0; i < 375u; i++) psx_mod_write_word(s_civ_block + 4u * i, i < 75u * nm ? s_dmg_civ[i] : 0xFFFFFFFFu);
                for (uint32_t i = 0; i < 525u; i++) psx_mod_write_word(pv + 4u * i, i < 105u * nm ? s_dmg_civ[75u * nm + i] : 0xFFFFFFFFu);
                fprintf(stdout, "driver.chicago: C42 Driver 2 civ zone rows (%u models) at 0x%08X\n", nm, s_civ_block);
            }
        }
    }
    /* C42 r3 (b) (exe_patches c42m_patches): six resident car models. PBUF / PCAP (0x800933A0 / A4): car set 4 builds its
     * models into a mod-memory polygon buffer (6 Driver 2 models ~ 900 entries; Driver 1's buffer has 666), 0 = Driver 1's
     * buffer and cap. SPAWN (16 bytes at 0x800932B8): the civilian model by rand & 15; Driver 1's {2, 3} x 8, car set 4
     * Driver 2's list (civ_ai.c modelRandomList: 4 x each civilian, one more each, 1 / 16 the special), models 4 / 5 only
     * while loaded (clean pointers 0x800A1AC0 / C4). Host-only parts (M8 list): the buffer size, the per-car-set choice. */
    {
        enum { PCAP_D2 = 1400u };
        if (cs == 4u && !s_pbuf) s_pbuf = psx_mod_alloc_guest_memory((PCAP_D2 + 2u + 240u) * 24u, 16u);   /* + group 5 (specials) */
        uint32_t pb = cs == 4u && s_pbuf ? s_pbuf : 0u, pc = pb ? PCAP_D2 : 0u;
        if (psx_mod_read_word(0x800933A0u) != pb) psx_mod_write_word(0x800933A0u, pb);
        if (psx_mod_read_word(0x800933A4u) != pc) psx_mod_write_word(0x800933A4u, pc);
        uint8_t sp[16];
        for (int i = 0; i < 16; i++) sp[i] = (uint8_t)(2 + (i & 1));
        specials_vblank(cs);
        sfx_vblank(cs);
        if (cs == 4u) {
            int m4 = psx_mod_read_word(0x800A1AC0u) != 0u;
            int m5 = (s_spc[(s_chi_night ? 1 : 0) + (s_lvl_xd ? 2 : 0)] ? (int)s_spc_valid : 1) && psx_mod_read_word(0x800A1AC4u) != 0u;
            static const uint8_t d2[16] = { 2, 3, 2, 3, 2, 3, 2, 3, 4, 4, 4, 4, 2, 3, 4, 5 };
            for (int i = 0; i < 16; i++) {
                uint8_t m = d2[i];
                if ((m == 4 && !m4) || (m == 5 && !m5)) m = (uint8_t)(2 + (i & 1));
                if (m == 5 && !m4) m = (uint8_t)(2 + (i & 1));
                sp[i] = m;
            }
        }
        /* R32 (exe_patches c42p / c42l): civilian palettes PALT (16 bytes at 0x800932EC: Driver 1 1..4; car set 4 1..5 =
         * Driver 2's four colour variants + the base paint) and the cop lights: COPW (0x800933A8: y delta << 16 | z) and
         * the x table 0x8008A8D8 ("p`P@@P`p" in Driver 1; Chicago: Driver 2's fixed pair at the cop model's roof bar,
         * lump model 0: x +-50, y -120, z 46 vs Driver 1's -164 / 15) */
        int d2c = cs == 4u;
        {
            uint32_t cw = d2c ? ((uint32_t)44u << 16) | 46u : 15u;
            if (psx_mod_read_word(0x800933A8u) != cw) psx_mod_write_word(0x800933A8u, cw);
        }
        if (psx_mod_read_word(0x800932C8u) == 0x8F87CC30u) {
            static const uint8_t pal_d1[4] = { 1, 2, 3, 4 };
            for (int i = 0; i < 4; i++) {
                uint32_t w = 0;
                for (int k = 0; k < 4; k++) w |= (uint32_t)(d2c ? (uint8_t)(1 + (4 * i + k) % 5) : pal_d1[k]) << (8 * k);
                if (psx_mod_read_word(0x800932ECu + 4u * (uint32_t)i) != w) psx_mod_write_word(0x800932ECu + 4u * (uint32_t)i, w);
            }
            uint32_t x0 = d2c ? 0x32323232u : 0x40506070u, x1 = d2c ? 0x32323232u : 0x70605040u;   /* "p`P@" "@P`p" */
            if (psx_mod_read_word(0x8008A8D8u) != x0) psx_mod_write_word(0x8008A8D8u, x0);
            if (psx_mod_read_word(0x8008A8DCu) != x1) psx_mod_write_word(0x8008A8DCu, x1);
        }
        /* only once the mod plan is in RAM (PCAVE's first word there): the plan's expected-byte guard at the exe entry
         * would reject the whole plan (boot unmodified) if this text page already held the plugin's bytes */
        for (int i = 0; i < 4 && psx_mod_read_word(0x800932C8u) == 0x8F87CC30u; i++) {
            uint32_t w = (uint32_t)sp[4 * i] | ((uint32_t)sp[4 * i + 1] << 8) | ((uint32_t)sp[4 * i + 2] << 16) | ((uint32_t)sp[4 * i + 3] << 24);
            if (psx_mod_read_word(0x800932B8u + 4u * (uint32_t)i) != w) psx_mod_write_word(0x800932B8u + 4u * (uint32_t)i, w);
        }
    }
    /* C42E (17.10., exe_patches c42e_patches): player zone rows at CAR_TABLES_ADDR (entry 4 of the player tables):
     * Driver 2 player cars' rows, or Driver 1's (copied from DTL, the entry-0 tables) for a car set 4 level with
     * Driver 1 player cars; DentCar's player rule and the player's collision box by main-RAM words (0 = Driver 1) */
    {
        if (cs == 4u && !s_car_tables) {
            s_car_tables = psx_mod_alloc_guest_memory(CAR_TABLES_BYTES, 16u);
            fprintf(stdout, "driver.chicago: C42E car tables at 0x%08X\n", s_car_tables);
        }
        const uint32_t CAR_TABLES_ADDR = s_car_tables;
        int d2p = cs == 4u && s_dmg_ply_n == 720u && s_car_tables;
        if (cs == 4u && s_car_tables) {
            /* entry 4 (car set 4) of the player verts / polys pointer tables -> this block */
            if (psx_mod_read_word(0x8008A6CCu) != CAR_TABLES_ADDR) psx_mod_write_word(0x8008A6CCu, CAR_TABLES_ADDR);
            if (psx_mod_read_word(0x8008A70Cu) != CAR_TABLES_ADDR + 1200u) psx_mod_write_word(0x8008A70Cu, CAR_TABLES_ADDR + 1200u);
            if (d2p) {
                if (psx_mod_read_word(CAR_TABLES_ADDR) != s_dmg_ply[0] || psx_mod_read_word(CAR_TABLES_ADDR + 1200u) != s_dmg_ply[300]) {
                    for (uint32_t i = 0; i < 720u; i++) psx_mod_write_word(CAR_TABLES_ADDR + 4u * i, s_dmg_ply[i]);
                    fprintf(stdout, "driver.chicago: C42E Driver 2 player damage rows written to 0x%08X\n", CAR_TABLES_ADDR);
                }
            } else {
                uint32_t sv = psx_mod_read_word(0x8008A6BCu) | 0x80000000u, sp = psx_mod_read_word(0x8008A6FCu) | 0x80000000u;
                if (sv != 0x80000000u && psx_mod_read_word(sv) != 0u
                    && (psx_mod_read_word(CAR_TABLES_ADDR) != psx_mod_read_word(sv)
                        || psx_mod_read_word(CAR_TABLES_ADDR + 1200u) != psx_mod_read_word(sp))) {
                    for (uint32_t i = 0; i < 300u; i++) psx_mod_write_word(CAR_TABLES_ADDR + 4u * i, psx_mod_read_word(sv + 4u * i));
                    for (uint32_t i = 0; i < 420u; i++) psx_mod_write_word(CAR_TABLES_ADDR + 1200u + 4u * i, psx_mod_read_word(sp + 4u * i));
                }
            }
        }
        uint32_t w[4] = { 0 };                         /* PDMG PBX PBZ PBS (exe_patches C42E_GP: 0x80093380..8C) */
        /* C42 r3 (exe_patches c42d_patches): Driver 2's DentCar rule with its per-polygon damage kinds: a 2 KB block in mod
         * memory = AI rows by resident model (row 0 unused) + player rows by choice; RULEB 1, LTABC / LTABP its rows */
        uint32_t nai = s_dmg_lvl_n == 2304u ? 5u : (s_dmg_lvl_n == 1792u ? 3u : 0u);   /* AI rows (models 1..nai) */
        int ruleb = d2p && nai;
        static uint32_t lvl_choice = 0xFFFFFFFFu;
        if (ruleb && !s_lvl_block) s_lvl_block = psx_mod_alloc_guest_memory(1536u, 16u);
        uint32_t ch = psx_mod_read_word(0x8009683Cu) & 3u;
        if (ruleb && s_lvl_block && lvl_choice != ch) {     /* row 0 = the player's choice, rows 1..5 = AI models 1..5; (L ^ 1) */
            for (uint32_t i = 0; i < 1536u; i += 4u) {
                uint32_t v = 0;
                for (uint32_t k = 0; k < 4u; k++) {
                    uint32_t at = i + k, row = at >> 8, col = at & 255u;
                    uint32_t src = row == 0u ? (256u * (nai + ch) + col) : (row <= nai ? 256u * (row - 1u) + col : 0xFFFFFFFFu);
                    v |= (uint32_t)(src < s_dmg_lvl_n ? s_dmg_lvl[src] & 3u : 3u) << (8u * k);   /* R33: final L ^ 1 (convert) */
                }
                psx_mod_write_word(s_lvl_block + i, v);
            }
            lvl_choice = ch;
            if (s_spc_cur) spd_write_row5(s_lvl_block, s_chi_night ? 1 : 0, s_spc_cur);   /* Q45 B: keep the special's row */
        }
        ruleb = ruleb && s_lvl_block;
        {
            uint32_t rw[2] = { ruleb ? 1u : 0u, ruleb ? s_lvl_block : 0u };
            static const uint32_t ra[2] = { 0x80093398u, 0x8009339Cu };
            for (int i = 0; i < 2; i++)
                if (psx_mod_read_word(ra[i]) != rw[i]) psx_mod_write_word(ra[i], rw[i]);
        }
        if (d2p) {
            w[0] = ruleb ? 1u : 2u;                    /* player: clamp 3 ^ 1 = 2 (D2 rule) / 3 ^ 2 = 1, shift 7 (+128) */
            static int boxes = -1;   /* CHI_C42E_BOX=0: Driver 1's box for the player too (tests) */
            if (boxes < 0) { const char* e = getenv("CHI_C42E_BOX"); boxes = !(e && *e == '0'); }
            if (boxes && s_car_box_n == 12u) {
                uint32_t c = psx_mod_read_word(0x8009683Cu) & 3u;
                int32_t bx = s_car_box[3 * c], bz = s_car_box[3 * c + 2];
                if (bx > 0 && bz > 0) {                /* D1 scenery width 169 vs car-car 186: the same ratio */
                    w[1] = (uint32_t)bx; w[2] = (uint32_t)bz; int32_t ex = (bz * 585 + 260) / 520 - 585, ey = (bx * 209 + 93) / 186 - 209;   /* broad-phase extra reach */
                    int32_t reach = (ex > 0 ? ex : 0) + (ey > 0 ? ey : 0);
                    s_player_reach = reach;                          /* C40: the player's own extra (per-car pad) */
                    /* R35 (user: a slow touch on the bus / fire engine threw the car away): the broad phase admits a pair only
                     * within Driver 1's 209 / 585 + 90 + this margin, so a bus box (870 + 154 offset) was tested only once
                     * the boxes overlapped deeply -> a huge push-out. The margin covers the loaded special too (both are
                     * needed for one pair: the sum keeps player-special pairs right). */
                    reach += s_spc_reach;
                    w[3] = (uint32_t)((bx * 169 + 93) / 186) | ((uint32_t)reach << 16);
                }
            }
        }
        if (!w[3]) s_player_reach = 0;
        {   /* C40 lever 1 (exe c40m: the broad phase 0x8001FB70 reads lh t2, car + 0x16): each car's OWN broad-phase extra
             * in the pad of its matrix (MATRIX: 9 shorts + 2 pad bytes; 0 in 600 RAM dumps, cleared when a car record
             * is re-initialised, rewritten here every vblank). Before, the player's + the special's reach went to EVERY
             * car (R35): every traffic pair passed the broad phase and the C82 window and ran the full SAT (C40 day 1:
             * FUN_80067A44 2.3 %, GlobalTimeStep pair loop 3.3 % of guest time). Player: its D2 box's reach; model 5:
             * the special's; others 0 = Driver 1's 90. D1 cities: all 0. */
            for (uint32_t c = 0; c < 25u; c++) {
                int32_t ex = c == 0u ? s_player_reach : 0;
                if (c && s_spc_reach && (psx_mod_read_byte(0x80098950u + 0x50u * (c - 1u) + 0x10u) & 7u) == 5u) ex += s_spc_reach;
                uint32_t a = 0x8009B0A4u + 0x18Cu * c + 0x16u;
                if ((int16_t)psx_mod_read_half(a) != (int16_t)ex) psx_mod_write_half(a, (uint16_t)(int16_t)ex);
            }
        }
        static const uint32_t gpw[4] = { 0x80093380u, 0x80093384u, 0x80093388u, 0x8009338Cu };   /* zero block, see exe_patches C42E */
        for (int i = 0; i < 4; i++)
            if (psx_mod_read_word(gpw[i]) != w[i]) psx_mod_write_word(gpw[i], w[i]);
    }
    /* C42/C53: car set 4's cosmetics rows (wheel / light positions) at 0x800A16A0, where entry 4 of the
     * exe's base table points (exe_patches COSMETICS); LoadCosmetics copies them at level load */
    if (cs == 4u) {
        int t = s_chi_night ? 1 : 0;
        uint32_t nw = s_cos_n[t] == 250u ? 250u : (s_cos_n[t] == 200u ? 200u : 0u);   /* 10 rows (c42m: entries 1..5 = rows 5..9) */
        if (nw && (psx_mod_read_word(0x800A16A0u) != s_cos[t][0] || psx_mod_read_word(0x800A16A0u + 4u * (nw - 1u)) != s_cos[t][nw - 1u])) {
            for (uint32_t i = 0; i < nw; i++) psx_mod_write_word(0x800A16A0u + 4u * i, s_cos[t][i]);
            fprintf(stdout, "driver.chicago: C42 cosmetics rows (%s) written to 0x800A16A0\n", t ? "night" : "day");
        }
    }
    /* The exe patches live in the generated native code, not in RAM (RAM keeps the original image), so the
     * static patch cannot be detected by reading RAM; plugin and generated code are built together from one
     * source state, so this build always has it. s_day_words stays only as documentation of the sites. */
    (void)s_day_words;
}

static void carry_release(void);
/* C42 r3 (c) (Infrastructure 18.10.): Driver 2's regional special vehicles (user R32: option B). Driver 2 (spool.c
 * CheckSpecialSpool) puts SpecialByRegion[area] + 7 into the special slot when no car uses it. Here resident model 5 is
 * the special: assets/specials_<day|night>.bin (convert polish_specials) carries the four specials (8, 9, 10, 12) with
 * their polygons remapped to the AREA texture pages that hold them, the region -> special table and each special's area
 * mask. When the player's region asks for another special and no car uses model 5, its models are copied to mod memory
 * (pointers relocated like 0x80052944), clean / damage / low [5], cosmetics row 5, zone rows, the DentCar level row (3 =
 * no texture shift: the specials' damage textures are not in the area sets) and the wheel size are set, and polygon group 5
 * is built here (a port of FUN_0003BDC8 for a non-player, non-palettised model) into its own buffer range. The group is
 * rebuilt after every area texture load (the builder bakes tpage / CLUT words of the area pages). Model 5 spawns only
 * while the loaded area holds the special's textures; outside, group 5 is hidden. Host-only (M8: a guest spool like
 * Driver 2's). */
#define SPC_STRUCT   (0x800A1078u + 5u * 0x3Cu)
#define SPC_BUF_IDX  1402u                      /* group 5 entries start here in the car polygon buffer (PCAP_D2 + 2) */
#define SPC_BUF_MAX  240u
static uint32_t s_spc_mem[16], s_spc_cap[16], s_spc_built_area = 0xFFFFFFFFu;

static int32_t s_spc_box[2];
/* R34 slot asset ("2CPS"): 7 header ints + slot header (page, first entry, x, y, w, h, entries, block bytes); every entry
 * ends with its slot block (texels w * h / 2 bytes, then entries x 32-byte CLUTs) */
static int32_t s_spc_slot[8];
static const uint8_t* s_spc_blk;
static uint32_t spc_first(const uint8_t* a, uint32_t n, uint32_t* blk) {
    uint32_t mg; memcpy(&mg, a, 4);
    if (mg == 0x53504332u && n >= 60u) { memcpy(s_spc_slot, a + 28, 32); *blk = (uint32_t)s_spc_slot[7]; return 60u; }
    s_spc_slot[7] = 0; *blk = 0u; return 28u;
}
static int spc_entry(const uint8_t* a, uint32_t n, uint32_t model, uint32_t* mask, const uint8_t** parts,
                     uint32_t* sizes, int32_t* wheel, const uint8_t** cos, const uint8_t** zones) {
    uint32_t cnt; memcpy(&cnt, a + 4, 4);
    uint32_t blk, p = spc_first(a, n, &blk);
    for (uint32_t i = 0; i < cnt && p + 32 + 820 <= n; i++) {
        int32_t h[8]; memcpy(h, a + p, 32);
        const uint8_t* q = a + p + 32;
        uint32_t c = (uint32_t)h[2], d = (uint32_t)h[3], l = (uint32_t)h[4];
        uint32_t pc = (c + 3u) & ~3u, pd = (d + 3u) & ~3u, pl = (l + 3u) & ~3u;
        if ((uint32_t)h[0] == model) {
            *mask = (uint32_t)h[1]; *wheel = h[5]; *cos = q; *zones = q + 100;
            s_spc_box[0] = h[6]; s_spc_box[1] = h[7];
            parts[0] = q + 820; parts[1] = q + 820 + pc; parts[2] = q + 820 + pc + pd;
            sizes[0] = c; sizes[1] = d; sizes[2] = l;
            s_spc_blk = blk && p + 32 + 820 + pc + pd + pl + blk <= n ? q + 820 + pc + pd + pl : NULL;
            return 1;
        }
        p += 32 + 820 + pc + pd + pl + blk;
    }
    return 0;
}

/* copy a model to guest memory at dst and relocate its section pointers (0x10 vertices, 0x14 polygons, 0x18 normals,
 * 0x1C point normals) to dst + offset, as the loader's 0x80052944 does */
static void spc_put_model(uint32_t dst, const uint8_t* src, uint32_t size) {
    for (uint32_t i = 0; i < size; i += 4) {
        uint32_t w = 0; memcpy(&w, src + i, (i + 4 <= size) ? 4 : size - i);
        psx_mod_write_word(dst + i, w);
    }
    for (uint32_t f = 0x10; f <= 0x1C; f += 4) {
        uint32_t off; memcpy(&off, src + f, 4);
        psx_mod_write_word(dst + f, dst + off);
    }
}

/* FUN_0003BDC8 for a model with a2 = a3 = stack = 0 (AI, not palettised): passes 2 (0x14, 0x16), 3 (0x15, 0x17), 4 (0, 1);
 * entry = 6 words (vertex bytes, normal bytes, CLUT << 16 | uv0, tpage << 16 | uv1, uv2 (| uv3 << ...), polygon index) */
static uint32_t spc_build_group(uint32_t model, uint32_t sa, uint32_t buf, uint32_t cap) {
    static const uint8_t psize[32] = { 8, 12, 16, 24, 20, 20, 28, 32, 8, 12, 16, 16, 0, 0, 0, 0,   /* 0x80089F1C */
                                       12, 12, 12, 16, 20, 20, 24, 24, 0, 0, 0, 0, 0, 0, 0, 0 };
    static const uint32_t cnt_field[7] = { 0x10, 0x18, 0x00, 0x08, 0x30, 0x20, 0x28 };
    static const uint32_t ptr_field[7] = { 0x14, 0x1C, 0x04, 0x0C, 0x34, 0x24, 0x2C };
    uint32_t polys = psx_mod_read_word(model + 0x14u), np = psx_mod_read_half(model + 0xEu);
    uint32_t n = 0;
    for (int k = 0; k < 7; k++) { psx_mod_write_word(sa + cnt_field[k], 0); psx_mod_write_word(sa + ptr_field[k], buf); }
    psx_mod_write_word(sa + 0x38u, psx_mod_read_word(model + 0x10u));
    uint32_t p2w2 = 0, p2w3 = 0;   /* struct 0's first pass-2 entry: CLUT / tpage halves for the flat polygons (FUN_0003BBF8) */
    {
        uint32_t s0p = psx_mod_read_word(0x800A1078u + 0x04u);
        if ((s0p & 0x1FFFFFFFu) >= 0x10000u) { p2w2 = psx_mod_read_word(s0p + 8u) & 0xFFFF0000u; p2w3 = psx_mod_read_word(s0p + 12u) & 0xFFFF0000u; }
    }
    static const int passes[3] = { 2, 3, 4 };
    for (int pi = 0; pi < 3; pi++) {
        int pass = passes[pi];
        uint32_t start = n, q = polys;
        for (uint32_t idx = 0; idx < np && n + 2 <= cap; idx++) {
            uint8_t b[32] = { 0 };
            uint32_t t = psx_mod_read_byte(q) & 31u, sz = psize[t] ? psize[t] : 4u;
            for (uint32_t j = 0; j < sz && j < 32; j++) b[j] = (uint8_t)psx_mod_read_byte(q + j);
            q += sz;
            uint32_t e = buf + 24u * n, w[6] = { 0, 0, 0, 0, 0, idx };
            int add = 0;
            uint32_t page = b[1], tex = (uint32_t)b[2] | ((uint32_t)b[3] << 8);
            uint32_t clut = page < 128u && tex < 32u ? psx_mod_read_half(0x80087030u + 2u * (page * 32u + tex)) : 0u;
            uint32_t tp = page < 128u ? psx_mod_read_half(0x80086F30u + 2u * page) : 0u;
#define U16(o) ((uint32_t)b[o] | ((uint32_t)b[(o) + 1] << 8))
            if (pass == 4 && t == 0) {
                w[0] = b[1] | (b[2] << 8) | (b[3] << 16); w[2] = p2w2; w[3] = p2w3; add = 1;
            } else if (pass == 4 && t == 1) {
                w[0] = b[4] | (b[5] << 8) | (b[6] << 16); w[2] = p2w2; w[3] = p2w3;
                for (int j = 0; j < 6; j++) psx_mod_write_word(e + 4u * (uint32_t)j, w[j]);
                n++; e += 24u;
                w[0] = b[4] | (b[6] << 8) | (b[7] << 16); add = 1;
            } else if (pass == 2 && t == 0x14) {
                w[0] = b[4] | (b[5] << 8) | (b[6] << 16); w[2] = (clut << 16) | U16(8); w[3] = (tp << 16) | U16(10); w[4] = U16(12); add = 1;
            } else if (pass == 3 && t == 0x15) {
                w[0] = b[4] | (b[5] << 8) | ((uint32_t)b[7] << 16) | ((uint32_t)b[6] << 24);
                w[2] = (clut << 16) | U16(8); w[3] = (tp << 16) | U16(10); w[4] = (U16(12) << 16) | U16(14); add = 1;
            } else if (pass == 2 && t == 0x16) {
                w[0] = b[4] | (b[5] << 8) | (b[6] << 16); w[1] = b[8] | (b[9] << 8) | (b[10] << 16);
                w[2] = (clut << 16) | U16(12); w[3] = (tp << 16) | U16(14); w[4] = U16(16); add = 1;
            } else if (pass == 3 && t == 0x17) {
                w[0] = b[4] | (b[5] << 8) | ((uint32_t)b[7] << 16) | ((uint32_t)b[6] << 24);
                w[1] = b[8] | (b[9] << 8) | ((uint32_t)b[11] << 16) | ((uint32_t)b[10] << 24);
                w[2] = (clut << 16) | U16(12); w[3] = (tp << 16) | U16(14); w[4] = (U16(16) << 16) | U16(18); add = 1;
            }
#undef U16
            if (add) {
                for (int j = 0; j < 6; j++) psx_mod_write_word(e + 4u * (uint32_t)j, w[j]);
                n++;
            }
        }
        uint32_t fi = pass == 2 ? 2u : (pass == 3 ? 3u : 4u);
        psx_mod_write_word(sa + cnt_field[fi], n - start);
        psx_mod_write_word(sa + ptr_field[fi], buf + 24u * start);
    }
    return n;
}

/* R34: upload the special's slot block (texels into the slot rectangle of the slot page's tpage, CLUTs into the VRAM
 * spots of the page's reserved entries, as the page loader placed them: tpage 0x80086F30[page], CLUT 0x80087030[page * 32
 * + entry]). check != 0: only report whether VRAM still holds it (sampled). */
/* R35 (user: a fire-truck region "completely messed up the loaded memory"): the GP0 0xA0 upload (vram_upload) feeds the
 * GPU's command stream; when the game is itself mid-way through a CPU -> VRAM transfer or a command (area texture
 * streaming), the injected words became its pixel / parameter data and corrupted VRAM. The slot is now written straight
 * into the runtime's VRAM (+ dirty rows + the renderer's mirror, like a completed GP0 transfer), bounds-checked, without
 * touching the GP0 state. Host-only. */
uint16_t* gpu_get_vram_ptr(void);
void gr_vram_transfer_in(int x, int y, int w, int h, const uint16_t* data);
void gpu_vram_dirty_mark_rows(uint32_t y0, uint32_t h);
static int vram_put(int x, int y, int w, int h, const uint16_t* px) {
    uint16_t* v = gpu_get_vram_ptr();
    if (!v || x < 0 || y < 0 || w <= 0 || h <= 0 || x + w > 1024 || y + h > 512) return 0;
    for (int r = 0; r < h; r++) memcpy(v + (size_t)(y + r) * 1024u + (size_t)x, px + (size_t)r * (size_t)w, (size_t)w * 2u);
    gpu_vram_dirty_mark_rows((uint32_t)y, (uint32_t)h);
    gr_vram_transfer_in(x, y, w, h, px);
    return 1;
}
static int spc_slot_upload(const uint8_t* blk, int check) {
    if (!blk || s_spc_slot[7] <= 0) return 0;
    uint32_t page = (uint32_t)s_spc_slot[0] & 63u, base = (uint32_t)s_spc_slot[1], n = (uint32_t)s_spc_slot[6];
    uint32_t sx = (uint32_t)s_spc_slot[2], sy = (uint32_t)s_spc_slot[3], w = (uint32_t)s_spc_slot[4], h = (uint32_t)s_spc_slot[5];
    uint32_t tp = psx_mod_read_half(0x80086F30u + 2u * page);
    int vx = (int)((tp & 15u) * 64u + sx / 4u), vy = (int)(((tp >> 4) & 1u) * 256u + sy), vw = (int)(w / 4u);
    static uint16_t px[64 * 256];
    /* bounds: the slot must lie inside its own 64 x 256 tpage, the block inside the asset entry */
    if (w == 0u || h == 0u || w > 256u || sx + w > 256u || sy + h > 256u || (uint32_t)vw * h > sizeof px / 2u
        || (uint32_t)s_spc_slot[7] < w * h / 2u + 32u * n || n > 32u) return 0;
    memcpy(px, blk, (size_t)vw * h * 2u);
    if (check) {
        if (!vram_matches(vx, vy, vw, (int)h, px)) return 0;
    } else if (!vram_put(vx, vy, vw, (int)h, px)) return 0;
    for (uint32_t j = 0; j < n && base + j < 32u; j++) {
        uint32_t c = psx_mod_read_half(0x80087030u + 2u * (page * 32u + base + j));
        uint16_t cl[16]; memcpy(cl, blk + w * h / 2u + 32u * j, 32);
        int cx = (int)((c & 0x3Fu) * 16u), cy = (int)((c >> 6) & 0x1FFu);
        if (!c || cx + 16 > 1024 || cy >= 512) continue;
        if (check) { if (gpu_vram_peek(cx + 1, cy) != cl[1] || gpu_vram_peek(cx + 15, cy) != cl[15]) return 0; }
        else vram_put(cx, cy, 16, 1, cl);
    }
    return 1;
}

static uint32_t s_spc_vb;
static void specials_vblank(uint32_t cs) {
    s_spc_vb++;
    /* C98 (cheats 5 menu strip / black box, Polish's VRAM diff): chicago_active() and game_started stay true after quitting
     * to the menu, so the 64-vblank slot check re-uploaded the special's block (VRAM x704-767 y128-255) over the
     * frontend's sprites. Nothing here while no level runs (C84 heartbeat: in-level hooks within LVL_BEAT_MAX vblanks;
     * the FRONTEND mark word can survive in RAM during a level, so it is not used). */
    int in_level = s_lvl_seen && s_vbl_n - s_lvl_beat <= LVL_BEAT_MAX;   /* else: the 'off' branch below (state reset) */
    int t = (s_chi_night ? 1 : 0) + (s_lvl_xd && s_spc[2 + (s_chi_night ? 1 : 0)] ? 2 : 0);
    const uint8_t* a = s_spc[t];
    uint32_t an = s_spc_n[t];
    if (!in_level || cs != 4u || !a || an < 28u || !s_pbuf || !chicago_active() || !psx_mod_game_started()
        || psx_mod_read_word(0x800A1AC4u) == 0u) {
        if (psx_mod_read_word(0x800933ACu)) psx_mod_write_word(0x800933ACu, 0u);
        if (psx_mod_read_word(0x800933B0u)) psx_mod_write_word(0x800933B0u, 0u);
        if (psx_mod_read_word(0x800933B4u)) psx_mod_write_word(0x800933B4u, 0u);
        if (psx_mod_read_word(0x800933BCu)) psx_mod_write_word(0x800933BCu, 0u);
        if (psx_mod_read_word(0x800933C0u)) psx_mod_write_word(0x800933C0u, 0u);
        s_spc_reach = 0;
        static int dbg_once;
        if (cs == 4u && !dbg_once && getenv("CHI_SPC_DEBUG")) {
            fprintf(stderr, "driver.chicago: specials off: asset %p n %u pbuf %08x chi %d started %d clean5 %08x\n", (void*)a, an,
                    s_pbuf, chicago_active(), psx_mod_game_started(), psx_mod_read_word(0x800A1AC4u));
            dbg_once = 1;
        }
        s_spc_cur = 0; s_spc_valid = 0; s_spc_built_area = 0xFFFFFFFFu;
        return;
    }
    if (psx_mod_read_word(AREA_LOADING_FLAG)) return;
    int32_t hdr[7]; memcpy(hdr, a, 28);
    if (((uint32_t)hdr[0] != 0x53504331u && (uint32_t)hdr[0] != 0x53504332u) || hdr[4] <= 0) return;
    uint32_t rx_n = (uint32_t)hdr[2], rz_n = (uint32_t)hdr[3];
    if (rx_n * rz_n > an) return;
    const uint8_t* regs = a + an - rx_n * rz_n;
    int32_t px = fr32(0x8009B0BCu), pz = fr32(0x8009B0C4u);
    int32_t rx = (px + hdr[5]) / hdr[4], rz = (pz + hdr[6]) / hdr[4];
    uint32_t want = (rx >= 0 && rz >= 0 && (uint32_t)rx < rx_n && (uint32_t)rz < rz_n) ? regs[(uint32_t)rz * rx_n + (uint32_t)rx] : 0u;
    uint32_t area = psx_mod_read_word(0x800972C0u) & 0xFFu;
    {   /* like Driver 2 (SpecialByRegion[LoadedArea]): the special of the LOADED area (the one whose textures it holds);
         * the region's own special only when no special covers the loaded area */
        uint32_t cnt; memcpy(&cnt, a + 4, 4);
        uint32_t blk, p = spc_first(a, an, &blk);
        for (uint32_t i = 0; i < cnt && p + 32 + 820 <= an; i++) {
            int32_t h[8]; memcpy(h, a + p, 32);
            if (((uint32_t)h[1] >> (area & 31u)) & 1u) { want = (uint32_t)h[0]; break; }
            p += 32 + 820 + (((uint32_t)h[2] + 3u) & ~3u) + (((uint32_t)h[3] + 3u) & ~3u) + (((uint32_t)h[4] + 3u) & ~3u) + blk;
        }
    }
    int used = 0;                                        /* any car using model 5 */
    /* R35 (user: buses spawn too high and bounce): the civilian spawn puts every car at the civilians' ride height; the
     * special rests lower in y by the difference of the cosmetics rows' wheel y (row 5 vs model 2's row: bus -257 vs
     * -150), so it dropped / bounced. A newly placed model-5 car gets that difference added (y and the x16 copy), i.e.
     * it spawns with its wheels on the road. Host-only (M8: the spawn sites add the model's wheel y). */
    static int32_t last_x[25], last_z[25]; static uint8_t last_m[25]; static uint32_t last_vb;   /* C88: 24 AI cars */
    int contiguous = (s_spc_vb == last_vb + 1u);      /* this loop also ran on the previous vblank */
    last_vb = s_spc_vb;
    int32_t dyw = (int32_t)(int16_t)psx_mod_read_half(0x800A0E20u + 200u + 66u) - (int32_t)(int16_t)psx_mod_read_half(0x800A0E20u + 500u + 66u);
    for (uint32_t i = 1; i < 25u; i++) {
        uint32_t car = 0x8009B0A4u + 0x18Cu * i, rec = 0x80098950u + 0x50u * (i - 1u);
        int32_t cx = fr32(car + 0x18u), cz = fr32(car + 0x20u);
        uint8_t cm = psx_mod_read_byte(rec + 0x10u);
        int live = (cx | fr32(car + 0x1Cu) | cz) != 0;
        int fresh = contiguous && live && (last_m[i] != cm || abs(cx - last_x[i]) + abs(cz - last_z[i]) > 3000);
        last_x[i] = live ? cx : 0; last_z[i] = live ? cz : 0; last_m[i] = live ? cm : 0xFF;
        if (fresh && cm == 5u && dyw > 0 && dyw < 1000) {
            psx_mod_write_word(car + 0x1Cu, (uint32_t)(fr32(car + 0x1Cu) + dyw));
            psx_mod_write_word(car + 0x28u, (uint32_t)(fr32(car + 0x28u) + dyw * 16));
        }
        if (live && cm == 5u) {
            used = 1;
            /* R34 (user: far buses drawn wrong): the civilian spawn gives every car a palette (c42p PALT 1..5); Driver 1's
             * far draw FUN_0002E230 switches to the car-palette handlers (CLUT from the car CLUT table of car pages 5-6)
             * whenever the drawn car's palette (0x80096990) != 0, so the special's slot textures got CLUT 0 (pale box).
             * Driver 2 gives specials palette 0 (civ_ai.c: residentCarModels > 4 -> palette 0). Host-only (M8: the 4 c42p
             * sites skip PALT for model 5). */
            if (psx_mod_read_byte(rec + 0x11u)) psx_mod_write_byte(rec + 0x11u, 0u);
        }
    }
    uint32_t mask = 0, sizes[3] = { 0, 0, 0 }; int32_t wheel = 73; const uint8_t *parts[3], *cosr = NULL, *zones = NULL;
    {   static uint32_t dbg_last;
        static const char* e = (const char*)1;
        if (e == (const char*)1) e = getenv("CHI_SPC_DEBUG");
        uint32_t key = want | (area << 8) | ((uint32_t)used << 16) | (s_spc_cur << 20);
        if (e && *e == '1' && key != dbg_last) {
            int ok_ = spc_entry(a, an, want, &mask, parts, sizes, &wheel, &cosr, &zones);
            fprintf(stderr, "driver.chicago: specials: region %d,%d want %u area %u used %d cur %u entry %d mask %08x\n",
                    rx, rz, want, area, used, s_spc_cur, ok_, mask);
            dbg_last = key;
        }
    }
    {   /* test aid (R35, devtest only): CHI_SPC_CYCLE=N swaps to the next special every N seconds even while one is in
         * use, to exercise the slot upload during area loads */
        static int cyc = -1; static uint32_t cyc_t;
        if (cyc < 0) { const char* e = getenv("CHI_SPC_CYCLE"); cyc = e && *e ? atoi(e) : 0; }
        if (cyc > 0 && ++cyc_t >= (uint32_t)cyc * 60u) {
            static const uint32_t order[3] = { 8u, 9u, 10u };
            static uint32_t k;
            cyc_t = 0; want = order[k++ % 3u]; used = 0;
            fprintf(stdout, "driver.chicago: C42 special cycle -> %u (area %u)\n", want, area);
        }
    }
    /* S1 follow-up (21.10., user: bus textures garbled up close): a swap while a model-5 car still exists leaves that car's
     * per-car near data (dented vertices 0x800B09BC, u-shift bytes 0x800AF97A, filled at its spawn from the old special)
     * under the new special's polygons and textures: garbage up close, the far (low) model looks right. Swap only after
     * model 5 has been unused for 2 s (a car slot that is momentarily empty during a respawn no longer counts as free). */
    static uint32_t free_vb;
    free_vb = used ? 0u : free_vb + 1u;
    if (free_vb < 120u && !getenv("CHI_SPC_CYCLE")) used = 1;
    if (want && want != s_spc_cur && !used && spc_entry(a, an, want, &mask, parts, sizes, &wheel, &cosr, &zones)
        && (s_spc_slot[7] > 0 || ((mask >> (area & 31u)) & 1u)) && sizes[0] >= 0x24u) {   /* R34 slot: any area */
        uint16_t npolys; memcpy(&npolys, parts[0] + 0xE, 2);
        if (npolys > 150u) s_spc_unloadable = want;      /* model 12 (152): never pending (no spawn stop for it) */
        if (npolys <= 150u) {                            /* the AI per-car UV buffer holds 150 polygons */
            uint32_t slot = want & 15u;
            uint32_t need = ((sizes[0] + 3u) & ~3u) + ((sizes[1] + 3u) & ~3u) + ((sizes[2] + 3u) & ~3u) + 64u;
            /* C135 (probe q73 crash in the far-car drawer, Vegas -> Rio): the slot's block was allocated once with the FIRST
             * city's size and reused by every later city: Rio's special 8 (13684 bytes) wrote 224 bytes past Vegas's block
             * (13460), so its low model's tail lay in the next allocation; when that owner wrote there, FUN_8002E230 read a
             * garbage polygon type and dispatched into nowhere. Chicago 9 -> Havana 9 overflowed too (+140). The block now
             * has a capacity (at least 16 KiB, every special so far is <= 14.6 KiB) and is replaced when a bigger one comes.
             * Host-only (M8: one fixed 16 KiB special buffer per slot in guest RAM). */
            if (need > s_spc_cap[slot]) {
                uint32_t cap = need > 16384u ? (need + 1023u) & ~1023u : 16384u;
                uint32_t nb = psx_mod_alloc_guest_memory(cap, 16u);
                if (nb) { s_spc_mem[slot] = nb; s_spc_cap[slot] = cap; }
                else { s_spc_mem[slot] = 0; s_spc_cap[slot] = 0; }
            }
            uint32_t m = s_spc_mem[slot];
            if (m) {
                uint32_t mc = m, md = mc + ((sizes[0] + 3u) & ~3u), ml = md + ((sizes[1] + 3u) & ~3u);
                spc_put_model(mc, parts[0], sizes[0]);
                if (sizes[1]) spc_put_model(md, parts[1], sizes[1]);
                if (sizes[2]) spc_put_model(ml, parts[2], sizes[2]);
                psx_mod_write_word(0x800A1AC4u, mc);                       /* clean[5] */
                psx_mod_write_word(0x800A11E0u + 20u, sizes[1] ? md : mc);  /* damage[5] (DAMG6) */
                psx_mod_write_word(0x800A11F8u + 20u, sizes[2] ? ml : 0u);  /* low[5] (LOWM6) */
                for (uint32_t i = 0; i < 100u; i += 4u) { uint32_t w; memcpy(&w, cosr + i, 4); psx_mod_write_word(0x800A0E20u + 500u + i, w); }
                if (s_civ_block) {                                         /* model 5's zone rows: verts row 5, polys row 5 */
                    for (uint32_t i = 0; i < 300u; i += 4u) { uint32_t w; memcpy(&w, zones + i, 4); psx_mod_write_word(s_civ_block + 1200u + i, w); }
                    for (uint32_t i = 0; i < 420u; i += 4u) { uint32_t w; memcpy(&w, zones + 300u + i, 4); psx_mod_write_word(s_civ_block + 1500u + 1680u + i, w); }
                }
                if (s_lvl_block)                                           /* Q45 B row (3 = no shift without .spd) */
                    spd_write_row5(s_lvl_block, t, want);
                s_spc_wheel = (uint32_t)wheel;
                s_spc_cur = want;
                s_spc_built_area = 0xFFFFFFFFu;
                if (s_spc_blk) spc_slot_upload(s_spc_blk, 0);              /* R34: its textures into the slot */
                fprintf(stdout, "driver.chicago: C42 special %u loaded as model 5 (region %d,%d)\n", want, rx, rz);
            }
        }
    }
    if (!s_spc_cur) { s_spc_valid = 0; return; }
    if (!spc_entry(a, an, s_spc_cur, &mask, parts, sizes, &wheel, &cosr, &zones)) { s_spc_valid = 0; return; }
    {   /* R33 (exe_patches C42B BOXCAVE): the special's car-car box = Driver 2's colBox x 1.32 (0 = Driver 1's box);
         * R34: SPBO 0x800933B4 = the box centre's offset along the car's z axis (high half of the asset's box z word) */
        uint32_t bx = s_spc_box[0] > 0 ? (uint32_t)s_spc_box[0] : 0u, bz = (uint32_t)s_spc_box[1] & 0xFFFFu;
        uint32_t bo = (uint32_t)(int32_t)(int16_t)((uint32_t)s_spc_box[1] >> 16);
        if (psx_mod_read_word(0x800933ACu) != bx) psx_mod_write_word(0x800933ACu, bx);
        if (psx_mod_read_word(0x800933B0u) != bz) psx_mod_write_word(0x800933B0u, bz);
        if (psx_mod_read_word(0x800933B4u) != bo) psx_mod_write_word(0x800933B4u, bo);
        /* C82 (exe_patches c82 / TW): SPTW 0x800933BC = the special's yaw kick in the car-car response. Driver 1 uses 0x37
         * for every car; Driver 2 twistRateY / 2 per model (CHICAGO.LCF: cars 224, models 8 / 10 = 50, 9 = 120) ->
         * 0x37 x twistRateY / 224. CHI_C82_TW=0: Driver 1's 0x37. */
        {
            static int tw_on = -1;
            if (tw_on < 0) { const char* e = getenv("CHI_C82_TW"); tw_on = !(e && *e == '0'); }
            uint32_t tr = s_spc_cur == 8u || s_spc_cur == 10u ? 50u : (s_spc_cur == 9u ? 120u : 224u), ref = 224u;
            {   /* the city's own values when the level ships them (.spt.bin; Chicago's equal this table) */
                int t2 = s_chi_night ? 1 : 0;
                const int32_t* q = s_spt[t2];
                if (s_spt_n[t2] >= 3u && q[0] == 0x31545053 && q[2] > 0)
                    for (int32_t i = 0; i < q[1] && 3u + 2u * (uint32_t)i + 1u < s_spt_n[t2]; i++)
                        if ((uint32_t)q[3 + 2 * i] == s_spc_cur) { tr = (uint32_t)q[4 + 2 * i]; ref = (uint32_t)q[2]; break; }
            }
            uint32_t tw = tw_on ? (0x37u * tr + ref / 2u) / ref : 0u;
            if (psx_mod_read_word(0x800933BCu) != tw) psx_mod_write_word(0x800933BCu, tw);
            /* C87 (exe NOSE cave): Driver 2's damage-zone length for the special: lbody = colBox.vz / 2 -> the nose is scaled
             * to Driver 1's 260: SPLB = 260 x 4096 / (SPBZ / 2) (0 = Driver 1). CHI_C87_ZONES=0: off. */
            static int z_on = -1;
            if (z_on < 0) { const char* e = getenv("CHI_C87_ZONES"); z_on = !(e && *e == '0'); }
            uint32_t splb = (z_on && bz) ? (uint32_t)((2u * 260u * 4096u) / bz) : 0u;
            if (psx_mod_read_word(0x800933C0u) != splb) psx_mod_write_word(0x800933C0u, splb);
        }
        int32_t ob = (int32_t)(int16_t)bo, ex = bz ? (((int32_t)bz + (ob < 0 ? -ob : ob)) * 585 + 260) / 520 - 585 : 0;
        int32_t ey = bx ? ((int32_t)bx * 209 + 93) / 186 - 209 : 0;
        s_spc_reach = (ex > 0 ? ex : 0) + (ey > 0 ? ey : 0);
    }
    int ok = (mask >> (area & 31u)) & 1u;
    if (s_spc_blk) {                         /* R34 slot: resident everywhere; build once, re-upload if VRAM lost it */
        static uint32_t tick;
        if ((++tick & 63u) == 0u && !spc_slot_upload(s_spc_blk, 1)) {
            spc_slot_upload(s_spc_blk, 0);
            fprintf(stdout, "driver.chicago: C42 special %u slot re-uploaded\n", s_spc_cur);
        }
        ok = 1;
        area = 0x100u;                       /* one build per swap (s_spc_built_area reset by the swap) */
    }
    if (ok && s_spc_built_area != area) {    /* (re)build after a texture load: tpage / CLUT words of the area pages */
        uint32_t mm = s_spc_mem[s_spc_cur & 15u];
        uint32_t ml = mm + ((sizes[0] + 3u) & ~3u) + ((sizes[1] + 3u) & ~3u);
        psx_mod_write_word(0x800A11F8u + 20u, sizes[2] ? ml : 0u);  /* low[5] back */
        if (s_lvl_block)
            spd_write_row5(s_lvl_block, t, s_spc_cur);
        uint32_t n = spc_build_group(psx_mod_read_word(0x800A1AC4u), SPC_STRUCT, s_pbuf + 24u * SPC_BUF_IDX, SPC_BUF_MAX);
        s_spc_built_area = area;
        fprintf(stdout, "driver.chicago: C42 special %u group built (%u entries, area %u)\n", s_spc_cur, n, area);
    } else if (!ok && s_spc_built_area != 0xFFFFFFFEu) {   /* textures not loaded: hide group 5 */
        for (uint32_t f = 0; f < 0x38u; f += 8u) psx_mod_write_word(SPC_STRUCT + f, 0u);
        psx_mod_write_word(0x800A11F8u + 20u, 0u);                     /* no far (low) model either */
        s_spc_built_area = 0xFFFFFFFEu;
    }
    /* S1 follow-up (21.10., user: buses no longer appear when driving back into a bus area, fire trucks do in theirs): in
     * slot mode the loaded special spawned everywhere (1/16 of the civilians), so with ~22 cars one was nearly always on
     * the road and the swap to the area's special (only while no car uses model 5) never came. Like Driver 2's spool (the
     * special follows the loaded area): while another special is wanted, model 5 stops spawning; the ones on the road
     * drive off / despawn, then the swap loads the wanted one. */
    int pending = want && want != s_spc_cur && want != s_spc_unloadable;
    s_spc_valid = (uint32_t)(ok && !pending);
}

/* C42 r3 (e) (Infrastructure 18.10., user R32 option A3): Driver 2's car engine sounds. Driver 1 plays every car with
 * bank 0's samples 1 (engine loop, 57.7 KB @ 22 kHz) and 2 (15.4 KB loop): the player on channels 0 / 1, the two nearest
 * AI cars on channels 7 / 8 (FUN_0004C438 starts them, FUN_0004CA5C moves them to cars each frame). In Chicago (car set 4)
 * after the level's bank 0 is in SPU RAM, the plugin writes Driver 2's car banks 12 / 4 / 13 (engine + idle loops,
 * assets/car_sfx.bin, 66.3 KB) into the 71.5 KB of samples 1-2 and points bank 0's table at them: samples 1 / 2 = bank 12
 * (the player and civilian model 2 = D2 1), 16 / 17 = bank 4 (D2 2 and the cop, as Driver 2's mapping), 18 / 19 = bank 13
 * (D2 3); the table's rate field makes FUN_0004D968 / 0x4DACC pitch them for 16 kHz. An AI engine channel that moves to a
 * car of another model is restarted on that model's sample (voice start address + key-on). Driver 1's horn / siren /
 * other samples stay. Host-only (M8: a Chicago SFX lump on the disc + the same table / restart in guest code). */
extern uint8_t* spu_get_ram_ptr(void);
extern void spu_write(uint32_t addr, uint32_t value);
extern uint32_t spu_read(uint32_t addr);
static uint32_t s_sfx_done_addr;                        /* bank 0 sample-1 address the replacement was done for */
#define SFX_TAB 0x800BCA74u                             /* bank 0 table: {addr, size, loop, rate} x 32 (bank b at + b * 0x200) */

static uint32_t sfx_sample_for_model(uint32_t model) {
    switch (model) {
        case 1: case 3: return 16u;                    /* cop (D2 0) and civilian D2 2: bank 4 */
        case 4: return 18u;                            /* D2 3: bank 13 */
        default: return 1u;                            /* civilian D2 1, the special, the player: bank 12 */
    }
}


/* R36 (user: Driver 2's exact model -> bank mapping + horns): assets/car_sfx.bin "CSX2" (build_package car_sfx_v2): every
 * sample of the civilian banks (Driver 2's MapCarIndexToBank: cop + D2 2 -> 4, D2 1 -> 12, D2 3 -> 13), of the player
 * choices' banks and of the specials' banks (engine / idle resampled to 11 kHz, horn 8 kHz) + a map (bank by Driver 1
 * model / player choice / special). SPU RAM (Driver 1's InitSound blocks, nothing of Driver 1's lost):
 *   - bank 0 samples 1-2 (73184 B, Driver 1's engine loops, unused in Chicago): the civilian engines / idles, their
 *     horns, the player's horn and the special's horn;
 *   - the music block's tail (block 0x19000 minus the loaded song bank, >= 21 KB in Chicago): the player's engine / idle;
 *   - the mission block's tail (0x21800 minus Take a Ride's bank, ~20 KB): the special's engine / idle (reloaded when the
 *     special swaps; only while no car uses it).
 * Bank 0 table slots: 1 / 2 player engine / idle (channels 0 / 1 restarted on them), 16..23 civilian / special engines,
 * 24..28 horns. AI engine channels 7 / 8 follow their car's model. Horns (new: Driver 1 has none; sample 0 is the crash):
 * the player's on R3 (held = repeated), civilians honk at the player like Driver 2's civ_ai (a car closing on the player
 * ahead of it, max one at a time, cooldown), all on voice 4 (channel 4: two-player only). Host-only (M8: guest code). */
#define SFX_V2_MAGIC 0x32585343u
#define SFX_BANK_BASE 0x800BD484u
typedef struct { int32_t bank, kind, size, loop, rate; uint32_t off; } SfxSmp;
static SfxSmp s_sx[48]; static int s_sx_n; static const uint8_t* s_sx_map; static const uint8_t* s_sx_map_day;
static uint32_t s_sx_done, s_sx_player, s_sx_spc, s_sx_slot_ok;
static uint32_t s_sx_reg[2][2];                    /* [0] music tail, [1] mission tail: {start, end} */
static void sx_reset(void) { s_sx_n = 0; s_sx_map = s_sx_map_day = NULL; s_sx_done = 0; s_sx_player = 0xFFFFFFFFu; s_sx_spc = 0; }

static int sx_find(int bank, int kind) {
    for (int i = 0; i < s_sx_n; i++) if (s_sx[i].bank == bank && s_sx[i].kind == kind) return i;
    return -1;
}
static void sx_civ_banks(void);
static int sx_parse(void) {
    if (s_sx_n) return 1;
    uint32_t mg; memcpy(&mg, s_sfx, 4);
    if (mg != SFX_V2_MAGIC || s_sfx_n < 8u) return 0;
    int32_t n; memcpy(&n, s_sfx + 4, 4);
    if (n <= 0 || n > 48 || 8u + 20u * (uint32_t)n + 28u > s_sfx_n) return 0;
    uint32_t dp = 8u + 20u * (uint32_t)n + 28u;
    s_sx_map = s_sx_map_day = s_sfx + 8u + 20u * (uint32_t)n;
    if (s_civ_t == 1 && s_sx_map_night_ok) s_sx_map = s_sx_map_night;   /* C147 (3) */
    for (int i = 0; i < n; i++) {
        int32_t h[5]; memcpy(h, s_sfx + 8u + 20u * (uint32_t)i, 20);
        s_sx[i].bank = h[0]; s_sx[i].kind = h[1]; s_sx[i].size = h[2]; s_sx[i].loop = h[3]; s_sx[i].rate = h[4];
        s_sx[i].off = dp;
        dp += ((uint32_t)h[2] + 15u) & ~15u;
        if (dp > s_sfx_n) return 0;
    }
    s_sx_n = n;
    sx_civ_banks();
    return 1;
}
/* copy sample i to SPU address dst, table slot `slot` */
static void sx_put(uint8_t* spu, int i, uint32_t dst, uint32_t slot) {
    memcpy(spu + dst, s_sfx + s_sx[i].off, (size_t)s_sx[i].size);
    uint32_t e = SFX_TAB + 16u * slot;
    psx_mod_write_word(e, dst);
    psx_mod_write_word(e + 4u, (uint32_t)s_sx[i].size);
    psx_mod_write_word(e + 8u, (uint32_t)s_sx[i].loop);
    psx_mod_write_word(e + 12u, (uint32_t)s_sx[i].rate);
}
/* end of the samples of SPU bank b (table at SFX_TAB + b * 0x200), 0 when empty */
static uint32_t sx_bank_end(uint32_t b) {
    uint32_t end = 0;
    for (uint32_t k = 0; k < 32u; k++) {
        uint32_t a = psx_mod_read_word(SFX_TAB + 0x200u * b + 16u * k), z = psx_mod_read_word(SFX_TAB + 0x200u * b + 16u * k + 4u);
        if (a && z && a < 0x80000u && a + z > end) end = a + z;
    }
    return end;
}
/* C127 (user R65: a sound at the start of loading a D2 map after any map was played): while no game frame runs (menu /
 * loading screen) the previous level's car channels still own their voices; restarting them keyed the engine on over the
 * music block that the load is refilling (spu_voices: voice 0 vol 0x3F90 at 0x3CB30, ~1 s loud noise). s_sx_live = the
 * game's frame counter moved in the last 8 vblanks; outside of it a restart only retargets the channel (attr address /
 * rate) and keys the voice OFF; the game keys its car channels on itself when the level starts. */
static int s_sx_live;
/* restart a logical channel's voice on table slot `slot` (attr addr + rate, voice start address, key on) */
static void sx_restart(uint32_t ch, uint32_t slot) {
    uint32_t base = 0x800BD498u + 0x84u * ch, e = SFX_TAB + 16u * slot;
    uint32_t want = psx_mod_read_word(e);
    if (!want || want == psx_mod_read_word(base + 0x1Cu)) return;
    uint32_t vmask = psx_mod_read_word(base) & 0xFFFFFFu, v = 0;
    while (v < 24u && !(vmask & (1u << v))) v++;
    if (v >= 24u) return;
    psx_mod_write_word(base + 0x1Cu, want);
    psx_mod_write_word(base + 0x44u, psx_mod_read_word(e + 12u));
    if (!s_sx_live) {                                        /* C127: no key-on outside of a running game */
        if (v < 16u) spu_write(0x1F801D8Cu, 1u << v); else spu_write(0x1F801D8Eu, 1u << (v - 16u));
        return;
    }
    spu_write(0x1F801C06u + 16u * v, (want >> 3) & 0xFFFFu);
    if (v < 16u) spu_write(0x1F801D88u, 1u << v); else spu_write(0x1F801D8Au, 1u << (v - 16u));
}
/* C121 (probe havana 1: Havana played Driver 1 / wrong car sounds): the civilian banks come from the loaded set's map
 * (Driver 2's car_banks[city] via build_package), not Chicago's fixed 12 / 4 / 13: the bank of D1 model 2 (civilian D2 1,
 * also the player's default) -> engine slots 20 / 21, horn 25; the cop's (model 1) -> 16 / 17, horn 24; the next other
 * bank of models 3 / 4 -> 18 / 19, horn 26. Chicago's map gives exactly the old 12 / 4 / 13 layout. */
static int s_civ_bank[3];                              /* [0] slots 20/21 + 25, [1] 16/17 + 24, [2] 18/19 + 26 */
static void sx_civ_banks(void) {
    s_civ_bank[0] = s_civ_bank[1] = s_civ_bank[2] = 0;
    if (!s_sx_map) return;
    s_civ_bank[0] = s_sx_map[2];
    s_civ_bank[1] = s_sx_map[1] != s_civ_bank[0] ? s_sx_map[1] : 0;
    for (int m = 3; m <= 4 && !s_civ_bank[2]; m++)
        if (s_sx_map[m] && s_sx_map[m] != s_civ_bank[0] && s_sx_map[m] != s_civ_bank[1]) s_civ_bank[2] = s_sx_map[m];
}
static uint32_t sx_engine_slot_of_bank(int bank) {
    if (!bank) return 0u;
    if (bank == s_civ_bank[0]) return 20u;
    if (bank == s_civ_bank[1]) return 16u;
    if (bank == s_civ_bank[2]) return 18u;
    return 0u;
}
static uint32_t sx_horn_slot_of_bank(int bank) {
    if (!bank) return 0u;
    if (bank == s_civ_bank[0]) return 25u;
    if (bank == s_civ_bank[1]) return 24u;
    if (bank == s_civ_bank[2]) return 26u;
    return 0u;
}

/* the horn voice (voice 4 = channel 4, used by Driver 1 only with two players) */
static void sx_horn_play(uint32_t slot, int32_t vol) {
    uint32_t e = SFX_TAB + 16u * slot, a = psx_mod_read_word(e), rate = psx_mod_read_word(e + 12u);
    if (!a || !rate) return;
    uint32_t v = 4u;
    if (vol < 0) vol = 0; if (vol > 0x3FFF) vol = 0x3FFF;
    spu_write(0x1F801C00u + 16u * v, (uint32_t)vol);
    spu_write(0x1F801C02u + 16u * v, (uint32_t)vol);
    uint32_t pitch = rate * 4096u / 44100u;
    spu_write(0x1F801C04u + 16u * v, pitch > 0x3FFFu ? 0x3FFFu : pitch);
    spu_write(0x1F801C06u + 16u * v, (a >> 3) & 0xFFFFu);
    spu_write(0x1F801C08u + 16u * v, 0x00FFu);      /* ADSR: fast attack, sustain level max */
    spu_write(0x1F801C0Au + 16u * v, 0x0000u);      /* sustain hold, release fast */
    spu_write(0x1F801D88u, 1u << v);
}

/* C137 (user rule Q71, Analyst inventory NOTES "C137 sound inventory"): in a D2 city every Driver 1 sound that a Driver 2
 * sound replaces leaves SPU RAM. Driver 1's horns (bank 0 samples 6 / 7 / 8, 18,352 B contiguous; AI horn 0x800180D8 plays
 * entry 6 + (id & 3, 3 -> 2) on any voice, R1 entry 8 on channel 4) -> entries 6 / 7 / 8 point at the city's D2 civilian
 * horns (slots 25 / 24 / 26; entry 8 keeps an address of its own, the R1 detection below compares channel 4 with it) and
 * the freed block holds the city's D2 siren (car_sfx kind 3, 8 kHz loop) as entry 4 = Driver 1's siren (sample 4 dropped).
 * Driver 1 sweeps the siren's pitch and volume by its phase (0x8004CA5C: arg car*4 - phase*48 + 0x1000, vol -2000 -
 * phase*30); Driver 2's siren holds the wail in the sample and plays it at a fixed pitch (gamesnd.c), so while the D2
 * siren is in entry 4 the two code words become constants (pitch arg 0x1000, vol -2000). D1 cities: untouched (bank 0
 * reloads from the disc, the code words go back). CHI_C137=0: off. Host-only (M8: the same SPU upload + 3 table entries +
 * 2 code words from guest code at level load). */
#define SIREN_PITCH_PC   0x8004CCB4u   /* subu v1, v1, v0 -> addiu v1, zero, 0x1000 */
#define SIREN_PITCH_ORIG 0x00621823u
#define SIREN_PITCH_D2   0x24031000u
#define SIREN_VOL_PC     0x8004CC84u   /* subu a3, v0, a3 -> addiu a3, zero, -2000 */
#define SIREN_VOL_ORIG   0x00473823u
#define SIREN_VOL_D2     0x2407F830u
static uint32_t s_siren_addr;                          /* SPU address of the D2 siren in entry 4 (0 = none) */
static int s_bank4_skip;                                /* C137 step 2: bank 4 not loaded (D2 Take a Ride) */
static int c137_on(void) {
    static int on = -1;
    if (on < 0) { const char* e = getenv("CHI_C137"); on = !(e && *e == '0'); }
    return on;
}
static void siren_words(int d2) {
    static const uint32_t w[2][3] = { { SIREN_PITCH_PC, SIREN_PITCH_ORIG, SIREN_PITCH_D2 },
                                      { SIREN_VOL_PC, SIREN_VOL_ORIG, SIREN_VOL_D2 } };
    for (int i = 0; i < 2; i++) {
        uint32_t cur = psx_mod_read_word(w[i][0]), want = w[i][d2 ? 2 : 1];
        if (cur != want && (cur == w[i][1] || cur == w[i][2])) psx_mod_write_code_word(w[i][0], want);
    }
}
/* step 1 of a fresh bank 0 in a D2 city (the civilian horns are in slots 24-26 by now) */
static void c137_bank0(uint8_t* spu) {
    s_siren_addr = 0;
    if (!c137_on()) return;
    uint32_t e[3], z[3];
    for (uint32_t k = 0; k < 3u; k++) { e[k] = psx_mod_read_word(SFX_TAB + 16u * (6u + k)); z[k] = psx_mod_read_word(SFX_TAB + 16u * (6u + k) + 4u); }
    int hole = e[0] && z[0] && e[1] == e[0] + z[0] && e[2] == e[1] + z[1] && z[2] && e[2] + z[2] <= 0x80000u;
    static const uint32_t src[3] = { 25u, 24u, 26u };
    int horns = 0;
    for (uint32_t k = 0; k < 3u; k++) {
        uint32_t sl = psx_mod_read_word(SFX_TAB + 16u * src[k]) ? src[k] : 25u;
        if (!psx_mod_read_word(SFX_TAB + 16u * sl)) continue;
        for (uint32_t w = 0; w < 4u; w++)
            psx_mod_write_word(SFX_TAB + 16u * (6u + k) + 4u * w, psx_mod_read_word(SFX_TAB + 16u * sl + 4u * w));
        horns++;
    }
    int is = -1;
    for (int i = 0; i < s_sx_n; i++) if (s_sx[i].kind == 3) { is = i; break; }
    if (horns == 3 && hole && is >= 0 && (uint32_t)s_sx[is].size <= e[2] + z[2] - e[0]) {
        sx_put(spu, is, e[0], 4u);
        s_siren_addr = e[0];
    }
    fprintf(stdout, "driver.chicago: C137 D1 horns -> D2 civilian horns (%d of 3); D2 siren %s (bank %d, %d B at SPU 0x%05X, "
                    "D1 horn block %u B)\n", horns, s_siren_addr ? "in entry 4" : "not loaded", is >= 0 ? s_sx[is].bank : -1,
            is >= 0 ? s_sx[is].size : 0, e[0], hole ? e[2] + z[2] - e[0] : 0u);
}

static void civ_time_select(void) {
    int t = s_chi_night ? 1 : 0;
    if (t == s_civ_t) return;
    s_civ_t = t;
    int nd = t && s_t_dmg_civ_n[1], nl = t && s_t_dmg_lvl_n[1], nw = t && s_t_car_whl_n[1];
    memcpy(s_dmg_civ, s_t_dmg_civ[nd], sizeof s_dmg_civ); s_dmg_civ_n = s_t_dmg_civ_n[nd];
    memcpy(s_dmg_lvl, s_t_dmg_lvl[nl], sizeof s_dmg_lvl); s_dmg_lvl_n = s_t_dmg_lvl_n[nl];
    memcpy(s_car_whl, s_t_car_whl[nw], sizeof s_car_whl); s_car_whl_n = s_t_car_whl_n[nw];
    if (s_sx_map_day) { s_sx_map = t && s_sx_map_night_ok ? s_sx_map_night : s_sx_map_day; sx_civ_banks(); }
    if (nd || nl || nw || (t && s_sx_map_night_ok))
        fprintf(stdout, "driver.chicago: C147 night civilian set (damage %d, levels %d, wheels %d, sound map %d)\n", nd, nl, nw, t && s_sx_map_night_ok);
}
static void sfx_v2_vblank(void) {
    uint8_t* spu = spu_get_ram_ptr();
    civ_time_select();
    if (!spu || !sx_parse()) return;
    {   /* C127: is a game frame running (frame counter moved within 8 vblanks)? */
        static uint32_t last_fc, vb, last_move;
        uint32_t fc = psx_mod_read_word(0x800970D8u);
        vb++;
        if (fc != last_fc) { last_fc = fc; last_move = vb; }
        s_sx_live = vb - last_move <= 8u;
    }
    uint32_t a1 = psx_mod_read_word(SFX_TAB + 16u), sz1 = psx_mod_read_word(SFX_TAB + 20u);
    uint32_t a2 = psx_mod_read_word(SFX_TAB + 32u), sz2 = psx_mod_read_word(SFX_TAB + 36u);
    uint32_t base0 = psx_mod_read_word(SFX_BANK_BASE);
    /* 1. a freshly (completely) loaded Driver 1 bank 0: civilian engines / idles / horns into samples 1-2's space */
    /* (Driver 1's untouched table = a fresh load, also on every later level load: no "done" address check) */
    if (sz1 == 57744u && sz2 == 15440u && a1 == base0 + 0x3710u && a2 == a1 + sz1 && a1 + sz1 + sz2 <= 0x80000u) {
        uint32_t at = a1, lim = a1 + sz1 + sz2, ok = 1;
        const int civ_banks[3] = { s_civ_bank[0], s_civ_bank[1], s_civ_bank[2] };   /* C121: the set's own banks */
        static const int order[3] = { 0, 1, 2 };
        for (int kk = 0; kk < 3 && ok; kk++)
            for (int kind = 0, k = order[kk]; kind < 3 && ok && civ_banks[k]; kind++) {
                int i = sx_find(civ_banks[k], kind);
                if (i < 0) continue;
                uint32_t slot = kind == 2 ? sx_horn_slot_of_bank(civ_banks[k]) : sx_engine_slot_of_bank(civ_banks[k]) + (uint32_t)kind;
                if (at + (uint32_t)s_sx[i].size > lim) { ok = 0; break; }
                sx_put(spu, i, at, slot);
                at = (at + (uint32_t)s_sx[i].size + 15u) & ~15u;
            }
        /* player / special horns: reserved behind them (the largest horn each) */
        uint32_t hmax = 0;
        for (int i = 0; i < s_sx_n; i++) if (s_sx[i].kind == 2 && (uint32_t)s_sx[i].size > hmax) hmax = (uint32_t)s_sx[i].size;
        hmax = (hmax + 15u) & ~15u;
        s_sx_reg[0][0] = s_sx_reg[0][1] = s_sx_reg[1][0] = s_sx_reg[1][1] = 0;
        static uint32_t horn_at[2];
        horn_at[0] = at; horn_at[1] = at + hmax;
        if (!ok || horn_at[1] + hmax > lim) { horn_at[0] = horn_at[1] = 0; }
        psx_mod_write_word(SFX_TAB + 16u * 27u, horn_at[0]);  /* address only for now; size etc. when the slot loads */
        psx_mod_write_word(SFX_TAB + 16u * 28u, horn_at[1]);
        c137_bank0(spu);                                    /* C137: D1 horns out, D2 siren in */
        /* player engine / idle stay on Driver 2's bank 12 until the player slot is placed (slots 1 / 2 = 20 / 21) */
        for (uint32_t k = 0; k < 2u; k++)
            for (uint32_t w = 0; w < 4u; w++)
                psx_mod_write_word(SFX_TAB + 16u * (1u + k) + 4u * w, psx_mod_read_word(SFX_TAB + 16u * (20u + k) + 4u * w));
        for (uint32_t ch = 0; ch < 16u; ch++) {            /* voices already on Driver 1's samples 1 / 2 */
            uint32_t b = 0x800BD498u + 0x84u * ch, cur = psx_mod_read_word(b + 0x1Cu);
            if (cur == a1 || cur == a2) { psx_mod_write_word(b + 0x1Cu, 0u); sx_restart(ch, ch == 1u ? 2u : 1u); }
        }
        s_sx_done = base0 + 0x3710u; s_sx_player = 0xFFFFFFFFu; s_sx_spc = 0; s_sx_slot_ok = ok;
        fprintf(stdout, "driver.chicago: R36 car sounds: civilian banks in SPU 0x%05X..0x%05X (horns reserved to 0x%05X)\n",
                a1, at, horn_at[1] + hmax);
    }
    if (!base0 || s_sx_done != base0 + 0x3710u) return;
    if (!s_sx_live) return;                              /* C127: the rest once the level runs (banks all loaded) */
    /* 2. the block tails (the music / mission banks are loaded by now) */
    uint32_t b2 = psx_mod_read_word(SFX_BANK_BASE + 8u), b3 = psx_mod_read_word(SFX_BANK_BASE + 12u), b4 = psx_mod_read_word(SFX_BANK_BASE + 16u);
    uint32_t m_end = sx_bank_end(2u), q_end = sx_bank_end(4u);
    if (!s_sx_reg[0][1] && m_end > b2 && b3 > m_end && b3 <= 0x80000u) { s_sx_reg[0][0] = (m_end + 15u) & ~15u; s_sx_reg[0][1] = b3; }
    if (!s_sx_reg[1][1] && q_end > b4 && b4 + 0x21800u <= 0x80000u && q_end < b4 + 0x21800u) { s_sx_reg[1][0] = (q_end + 15u) & ~15u; s_sx_reg[1][1] = b4 + 0x21800u; }
    else if (!s_sx_reg[1][1] && !q_end && s_bank4_skip && b4 && b4 + 0x21800u <= 0x80000u) { s_sx_reg[1][0] = b4; s_sx_reg[1][1] = b4 + 0x21800u; }   /* C137: no bank 4 */
    /* a later bank load into those blocks (beyond what we reserved) cancels the slot */
    if (s_sx_reg[0][1] && m_end > s_sx_reg[0][0]) { s_sx_reg[0][1] = 0; s_sx_player = 0xFFFFFFFFu; }
    if (s_sx_reg[1][1] && q_end > s_sx_reg[1][0]) { s_sx_reg[1][1] = 0; s_sx_spc = 0; }
    /* 3. the player's slot (choice -> bank) */
    uint32_t choice = psx_mod_read_word(0x8009683Cu) & 3u;
    int pbank = s_sx_map ? (int)s_sx_map[8u + choice] : 0;
    if (s_sx_player != choice && s_sx_reg[0][1] && pbank) {
        int ie = sx_find(pbank, 0), ii = sx_find(pbank, 1), ih = sx_find(pbank, 2);
        uint32_t at = s_sx_reg[0][0];
        if (ie >= 0 && ii >= 0 && at + (((uint32_t)s_sx[ie].size + 15u) & ~15u) + (uint32_t)s_sx[ii].size <= s_sx_reg[0][1]) {
            sx_put(spu, ie, at, 1u);
            sx_put(spu, ii, (at + (uint32_t)s_sx[ie].size + 15u) & ~15u, 2u);
            uint32_t ha = psx_mod_read_word(SFX_TAB + 16u * 27u);
            if (ih >= 0 && ha) sx_put(spu, ih, ha, 27u);
            sx_restart(0u, 1u); sx_restart(1u, 2u);
            fprintf(stdout, "driver.chicago: R36 player car sound: Driver 2 bank %d (choice %u)\n", pbank, choice);
        }
        s_sx_player = choice;
    }
    /* 4. the special's slot (follows the loaded special) */
    uint32_t sp = s_spc_cur & 15u;
    int sbank = s_sx_map && s_spc_cur ? (int)s_sx_map[12u + sp] : 0;
    if (s_sx_spc != s_spc_cur && s_sx_reg[1][1] && sbank) {
        int ie = sx_find(sbank, 0), ii = sx_find(sbank, 1), ih = sx_find(sbank, 2);
        uint32_t at = s_sx_reg[1][0];
        if (ie >= 0 && ii >= 0 && at + (((uint32_t)s_sx[ie].size + 15u) & ~15u) + (uint32_t)s_sx[ii].size <= s_sx_reg[1][1]) {
            sx_put(spu, ie, at, 22u);
            sx_put(spu, ii, (at + (uint32_t)s_sx[ie].size + 15u) & ~15u, 23u);
            uint32_t ha = psx_mod_read_word(SFX_TAB + 16u * 28u);
            if (ih >= 0 && ha) sx_put(spu, ih, ha, 28u);
            fprintf(stdout, "driver.chicago: R36 special %u car sound: Driver 2 bank %d\n", s_spc_cur, sbank);
        }
        s_sx_spc = s_spc_cur;
    }
    /* 5. AI engine channels 7 / 8: the model of the car each one follows */
    for (uint32_t ch = 7; ch <= 8; ch++) {
        uint32_t base = 0x800BD498u + 0x84u * ch;
        uint32_t pos = psx_mod_read_word(base + 0x5Cu) | 0x80000000u;
        if (pos < 0x8009B16Cu || pos >= 0x8009B16Cu + 0x18Cu * 25u || (pos - 0x8009B16Cu) % 0x18Cu) continue;
        uint32_t car = (pos - 0x8009B16Cu) / 0x18Cu;
        if (car == 0u) continue;
        uint32_t model = psx_mod_read_byte(0x80098950u + 0x50u * (car - 1u) + 0x10u) & 7u;
        uint32_t slot = model == 5u ? (s_sx_spc && psx_mod_read_word(SFX_TAB + 16u * 22u) ? 22u : 20u)
                                    : sx_engine_slot_of_bank(s_sx_map ? (int)s_sx_map[model] : 12);
        if (!slot) slot = 20u;
        sx_restart(ch, slot);
    }
    /* 7 (C83, user: the engine sounds "slightly different" from Driver 2): the player's engine pitch in Driver 2's range.
     * Driver 1 (FUN_0004DACC): pitch = rate (+0x44) x (scale (+0x52) x arg >> 12) / 44100, arg (+0x50) = revs / 4 -
     * vol / 128 + 1000 -> 0.23x .. 1.97x (burnout revs ~28300). Driver 2 (REDRIVER2 gamesnd.c): revs / 4 + revsvol / 64
     * + 1500, burnout revs 20160 -> ~0.35x .. 1.6x. Map: arg' = (arg - 1000) x 0.71 + 1414 (revs x 20160 / 28300,
     * revsvol / 64 ~ -86), applied through the channel's rate (one frame behind, like the game's own update); only while
     * channel 0 plays the Driver 2 player engine (slot 1). CHI_C83_PITCH=0: Driver 1's mapping. */
    {
        static int pitch_on = -1;
        if (pitch_on < 0) { const char* e = getenv("CHI_C83_PITCH"); pitch_on = !(e && *e == '0'); }
        uint32_t c0 = 0x800BD498u, e1 = SFX_TAB + 16u, smp = psx_mod_read_word(e1), base = psx_mod_read_word(e1 + 12u);
        int32_t arg = (int16_t)psx_mod_read_half(c0 + 0x50u);
        if (pitch_on && smp && base && psx_mod_read_word(c0 + 0x1Cu) == smp && arg > 0x80) {
            int32_t a2 = (arg - 1000) * 71 / 100 + 1414;
            if (a2 < 1300) a2 = 1300;
            uint32_t rate = (uint32_t)((uint64_t)base * (uint32_t)a2 / (uint32_t)arg);
            if (psx_mod_read_word(c0 + 0x44u) != rate) psx_mod_write_word(c0 + 0x44u, rate);
        }
    }
    /* 6. horns. Driver 1's own horn: R1 starts bank 0 sample 8 on channel 4 (FUN_0004D740, every 11 frames while held);
     * that channel is retargeted to the player car's Driver 2 horn. Civilians honk at the player like Driver 2's
     * civ_ai (horn to the player) on the same voice while the player is not honking. */
    uint32_t c4 = 0x800BD498u + 0x84u * 4u, c4a = psx_mod_read_word(c4 + 0x1Cu);
    uint32_t s8 = psx_mod_read_word(SFX_TAB + 16u * 8u);
    uint32_t phs = psx_mod_read_word(SFX_TAB + 16u * 27u + 4u) ? 27u : 25u, pha = psx_mod_read_word(SFX_TAB + 16u * phs);
    static uint32_t horn_busy, cool[23], tick;
    tick++;
    uint32_t endx = spu_read(0x1F801D9Cu) & (1u << 4);
    if (c4a && s8 && c4a == s8) { sx_restart(4u, phs); horn_busy = 1u; return; }      /* the player's horn */
    if (c4a && c4a != s8 && c4a != pha && !horn_busy) return;     /* channel 4 holds something else (two players) */
    if (horn_busy && endx) horn_busy = 0;
    int32_t px = fr32(0x8009B0BCu), pz = fr32(0x8009B0C4u);
    if (horn_busy || (tick & 7u)) return;
    /* a civilian closing on the player ahead of it honks (Driver 2 civ_ai: horn to the player), max one at a time */
    for (uint32_t i = 1; i < 23u; i++) {
        if (cool[i]) { cool[i] = cool[i] > 8u ? cool[i] - 8u : 0u; continue; }
        uint32_t car = 0x8009B0A4u + 0x18Cu * i, rec = 0x80098950u + 0x50u * (i - 1u);
        int32_t cx = fr32(car + 0x18u), cz = fr32(car + 0x20u);
        if (!(cx | cz)) continue;
        uint32_t model = psx_mod_read_byte(rec + 0x10u) & 7u;
        if (model == 0u || (model == 1u && psx_mod_read_byte(car + 0x12Eu) == 1u)) continue;   /* C143: patrol cops honk
                                                             * (D2 civ_ai), pursuing ones run their siren */
        int32_t dx = px - cx, dz = pz - cz;
        int64_t d2 = (int64_t)dx * dx + (int64_t)dz * dz;
        if (d2 > (int64_t)1800 * 1800 || d2 < (int64_t)300 * 300) continue;
        int32_t fx = (int16_t)psx_mod_read_half(car + 4u + 4u), fz = (int16_t)psx_mod_read_half(car + 4u + 16u);   /* forward (m02, m22) */
        double dist = sqrt((double)d2), ahead = ((double)dx * fx + (double)dz * fz) / (4096.0 * dist);
        int32_t vx = fr32(car + 0x40u), vz = fr32(car + 0x48u);
        double sp = sqrt((double)vx * vx + (double)vz * vz) / 4096.0;
        if (ahead < 0.85 || sp < 4.0) continue;              /* the player right in front, the civilian still moving */
        if ((rand() & 3) != 0) { cool[i] = 60u; continue; }
        int bank = s_sx_map ? (int)s_sx_map[model] : 0;
        uint32_t hs = model == 5u ? (psx_mod_read_word(SFX_TAB + 16u * 28u + 4u) ? 28u : 25u) : sx_horn_slot_of_bank(bank);
        if (!hs) hs = 25u;
        int32_t cxm = fr32(0x8009D768u), czm = fr32(0x8009D770u);
        double dc = sqrt((double)(cx - cxm) * (cx - cxm) + (double)(cz - czm) * (cz - czm));
        int32_t vol = (int32_t)(0x2800 * (1.0 - dc / 9000.0));
        if (vol < 0x400) continue;
        sx_horn_play(hs, vol); horn_busy = 2u; cool[i] = 300u;
        break;
    }
}

/* C137 step 2 (Strategy 30.10., user rule: only sound data that is used stays loaded): Take a Ride never starts a bank 4
 * sample in a D2 city (NOTES "C137 step 2": static start-site list + traced runs), so its VOICES lump (117 KB) is not read
 * there. FUN_0004c29c (level sound load) picks bank 4's lump from the byte pairs (mission threshold, lump) at 0x8008A96C,
 * first pair with threshold >= mission; Take a Ride 0x7C lands on (0xAE, 0) whose lump byte 0x8008A985 becomes 0xFF (= no
 * bank 4: no CD read, no SPU upload) only while a D2 city runs mission 0x7C; 0x00 again for anything else (D1 cities,
 * missions, future D2 missions keep the mission-script path). The stale bank 4 table of the previous level is cleared
 * (rate 0: FUN_0004d968 then plays nothing). The freed mission block (0x21800 B) is the special engine's region and the
 * reserve. Exe DATA only (no code word). CHI_C137_BANK4=0: off. Host-only (M8: the same byte from guest code). */
#define TAR_BANK4_LUMP 0x8008A985u
static void c137_bank4_vblank(void) {
    static int en = -1;
    if (en < 0) { const char* e = getenv("CHI_C137_BANK4"); en = c137_on() && !(e && *e == '0'); }
    int skip = en && s_slot_enabled && chicago_active() && psx_mod_read_word(MISSION_NUMBER) == 0x7Cu;
    uint32_t cur = psx_mod_read_byte(TAR_BANK4_LUMP), want = skip ? 0xFFu : 0x00u;
    if (cur != want && (cur == 0x00u || cur == 0xFFu) && psx_mod_read_byte(TAR_BANK4_LUMP - 1u) == 0xAEu)
        psx_mod_write_byte(TAR_BANK4_LUMP, want);
    s_bank4_skip = skip;
    if (skip && psx_mod_read_word(SFX_TAB + 0x200u * 4u))
        for (uint32_t k = 0; k < 32u * 4u; k++) psx_mod_write_word(SFX_TAB + 0x200u * 4u + 4u * k, 0u);
}
/* C143 (user: horns per car model as in Driver 2; Analyst NOTES "C143 horn mapping"): the exe's AI horn (c143_patches,
 * 0x80018084..A4) plays bank 0 entry 6 + HORN[model * 32 + record id] (zero block 0x80093648, 256 bytes; all zero = entry
 * 6 everywhere). Written every vblank (the zero block is cleared at boot): Driver 1 cities / no D2 horns loaded = Driver
 * 1's id rule (id & 3: 0 / 1 / 2 / 2 -> entries 6 / 7 / 8 / 8, unchanged); a D2 city with its horns in SPU = per model:
 * the horn slot of the model's bank (cop = model 1 = the slot-2 civilian's bank once the data map says so, Driver 2), the
 * special 28, else 25 (minus 6). Host-only for now (M8: the same table written by guest code at level load). */
#define C143_TAB 0x80093648u
static void c143_horn_table(void) {
    int d2 = chicago_active() && s_sx_map && psx_mod_read_word(SFX_TAB + 16u * 25u) != 0u && s_sx_done != 0u;
    static uint8_t t[256];
    for (uint32_t m = 0; m < 8u; m++) {
        uint32_t hs = 25u;
        if (d2) {
            if (m == 5u) hs = psx_mod_read_word(SFX_TAB + 16u * 28u + 4u) ? 28u : 25u;
            else if (m >= 1u && m <= 4u) { uint32_t h = sx_horn_slot_of_bank((int)s_sx_map[m]); if (h) hs = h; }
        }
        for (uint32_t id = 0; id < 32u; id++)
            t[m * 32u + id] = (uint8_t)(d2 ? hs - 6u : ((id & 3u) == 3u ? 2u : (id & 3u)));
    }
    for (uint32_t k = 0; k < 64u; k++) {
        uint32_t w; memcpy(&w, t + 4u * k, 4);
        if (psx_mod_read_word(C143_TAB + 4u * k) != w) psx_mod_write_word(C143_TAB + 4u * k, w);
    }
}
/* C137 step 2 diagnostic (CHI_C137_TRACE=1, off by default): which bank / sample each of the 16 logical channels starts.
 * Every start (FUN_0004d968, all 4 callers) stores the sample's SPU address in the channel attr (+0x1C), which stays there
 * until the channel's next start, so a per-vblank compare also catches the shortest samples. Logs each (bank, sample)
 * the first time and a count summary every 60 s. */
static void c137_trace_vblank(void) {
    static int en = -1;
    if (en < 0) { const char* e = getenv("CHI_C137_TRACE"); en = e && *e == '1'; }
    if (!en) return;
    static uint32_t last[16], vb, cnt[5][32];
    for (uint32_t ch = 0; ch < 16u; ch++) {
        uint32_t a = psx_mod_read_word(0x800BD498u + 0x84u * ch + 0x1Cu);
        if (!a || a == last[ch]) continue;
        last[ch] = a;
        int fb = -1, fk = -1;
        for (uint32_t b = 0; b < 5u && fb < 0; b++)
            for (uint32_t k = 0; k < 32u; k++)
                if (psx_mod_read_word(SFX_TAB + 0x200u * b + 16u * k) == a) { fb = (int)b; fk = (int)k; break; }
        if (fb < 0) { fprintf(stdout, "driver.chicago: C137 trace: ch %u addr 0x%05X (no table entry)\n", ch, a); continue; }
        if (!cnt[fb][fk]++)
            fprintf(stdout, "driver.chicago: C137 trace: first bank %d sample %d (ch %u, addr 0x%05X, CITY %u)\n", fb, fk, ch, a,
                    psx_mod_read_word(CITY_WORD));
    }
    if (++vb % 3600u == 0u) {
        char buf[512]; int n = 0;
        for (int b = 0; b < 5; b++) for (int k = 0; k < 32; k++)
            if (cnt[b][k] && n < 480) n += snprintf(buf + n, sizeof buf - (size_t)n, " %d/%d:%u", b, k, cnt[b][k]);
        fprintf(stdout, "driver.chicago: C137 trace summary (bank/sample:starts):%s\n", n ? buf : " none");
    }
}
static void sfx_vblank(uint32_t cs) {
    c137_trace_vblank();
    c143_horn_table();
    {   /* C137: the fixed-pitch siren words only while entry 4 holds the D2 siren (any other level: Driver 1's) */
        int d2 = cs == 4u && s_siren_addr && chicago_active() && psx_mod_read_word(SFX_TAB + 16u * 4u) == s_siren_addr;
        siren_words(d2);
    }
    if (cs != 4u || !s_sfx || s_sfx_n < 4u || !chicago_active() || !psx_mod_game_started()) return;
    {   uint32_t mg; memcpy(&mg, s_sfx, 4);
        if (mg == SFX_V2_MAGIC) { sfx_v2_vblank(); return; } }
    uint8_t* spu = spu_get_ram_ptr();
    if (!spu) return;
    uint32_t a1 = psx_mod_read_word(SFX_TAB + 16u), sz1 = psx_mod_read_word(SFX_TAB + 20u);
    uint32_t a2 = psx_mod_read_word(SFX_TAB + 32u), sz2 = psx_mod_read_word(SFX_TAB + 36u);
    /* a freshly loaded Driver 1 bank 0: sample 1 57744 B, sample 2 15440 B right behind it */
    uint32_t base0 = psx_mod_read_word(0x800BD484u);   /* bank 0's SPU address (SpuMalloc at InitSound) */
    /* only a COMPLETE load: LoadSoundBank copies the table, uploads the data, then adds the base to every entry */
    if (sz1 == 57744u && sz2 == 15440u && a1 == base0 + 0x3710u && a2 == a1 + sz1 && a1 + sz1 + sz2 <= 0x80000u
        && a1 != s_sfx_done_addr) {
        int32_t cnt; memcpy(&cnt, s_sfx, 4);
        /* layout: bank 12's engine at sample 1's address, its idle at sample 2's address (channels 0 / 1 keep playing
         * from their start addresses), banks 4 / 13 behind bank 12's engine inside sample 1's old space */
        static const uint32_t slot_of[6] = { 1u, 2u, 16u, 17u, 18u, 19u };
        uint32_t dp = 4u + 20u * (uint32_t)cnt, at = a1, ok = 1;
        for (int32_t i = 0; i < cnt && i < 6 && ok; i++) {
            int32_t h[5]; memcpy(h, s_sfx + 4u + 20u * (uint32_t)i, 20);
            uint32_t size = (uint32_t)h[2], pad = (size + 15u) & ~15u;
            uint32_t dst = i == 1 ? a2 : at, lim = i == 1 ? a2 + sz2 : a2;
            if (dp + size > s_sfx_n || dst + size > lim) { ok = 0; break; }
            memcpy(spu + dst, s_sfx + dp, size);
            uint32_t e = SFX_TAB + 16u * slot_of[i];
            psx_mod_write_word(e, dst);
            psx_mod_write_word(e + 4u, size);
            psx_mod_write_word(e + 8u, (uint32_t)h[3]);
            psx_mod_write_word(e + 12u, (uint32_t)h[4]);
            dp += pad;
            if (i != 1) at += pad;
        }
        for (uint32_t ch = 0; ch < 16u; ch++) {          /* voices already on samples 1 / 2: the new pitch base */
            uint32_t b = 0x800BD498u + 0x84u * ch, cur = psx_mod_read_word(b + 0x1Cu);
            if (cur == a1 || cur == a2) psx_mod_write_word(b + 0x44u, 16000u);
        }
        s_sfx_done_addr = a1;
        fprintf(stdout, "driver.chicago: C42 Driver 2 car sounds in SPU RAM 0x%05X..0x%05X\n", a1, at);
    }
    if (s_sfx_done_addr != a1) return;
    /* AI engine channels 7 / 8: the model of the car each one follows */
    for (uint32_t ch = 7; ch <= 8; ch++) {
        uint32_t base = 0x800BD498u + 0x84u * ch;
        uint32_t pos = psx_mod_read_word(base + 0x5Cu) | 0x80000000u;   /* 0x800BD4F4 + ch * 0x84: the car's position (KUSEG) */
        if (pos < 0x8009B16Cu || pos >= 0x8009B16Cu + 0x18Cu * 25u || (pos - 0x8009B16Cu) % 0x18Cu) continue;
        uint32_t car = (pos - 0x8009B16Cu) / 0x18Cu;
        if (car == 0u) continue;
        uint32_t model = psx_mod_read_byte(0x80098950u + 0x50u * (car - 1u) + 0x10u);
        uint32_t smp = sfx_sample_for_model(model), e = SFX_TAB + 16u * smp;
        uint32_t want = psx_mod_read_word(e), cur = psx_mod_read_word(base + 0x1Cu);   /* attr addr (0x800BD4B4) */
        if (!want || want == cur) continue;
        uint32_t vmask = psx_mod_read_word(base) & 0xFFFFFFu;    /* SpuVoiceAttr.voice */
        uint32_t v = 0;
        while (v < 24u && !(vmask & (1u << v))) v++;
        if (v >= 24u) continue;
        psx_mod_write_word(base + 0x1Cu, want);
        psx_mod_write_word(base + 0x44u, psx_mod_read_word(e + 12u));   /* 0x800BD4DC: the sample rate (pitch base) */
        spu_write(0x1F801C06u + 16u * v, (want >> 3) & 0xFFFFu);       /* voice start address */
        if (v < 16u) spu_write(0x1F801D88u, 1u << v); else spu_write(0x1F801D8Au, 1u << (v - 16u));   /* key on */
    }
}

/* C40 lever 3 (24.10.): Driver 2's car LOD distance in a Driver 2 city. Driver 1 draws a car's full model up to camera
 * depth *0x80096A48 (10000, +4 per zoom step; set by the camera setup FUN_8003CFE8 / D4D0 / D810, read at 0x8003AB0C);
 * Driver 2 switches to the low model beyond CAR_LOD_SWITCH_DISTANCE 5500 (REDRIVER2 cars.c) = 7260 at x1.32. In
 * Chicago the full D2 car models (quads, ~120 polys) cost 3.6 % of guest time vs 0.3 % in Miami (C40 day 1). The plugin
 * scales the camera's value by 7260 / 10000 whenever the game writes a new one. CHI_C40_LOD=1: on (default off: measured
 * 24.10.: car draw share 3.6 -> 2.6 % but no FPS change at the 4 dense spots). Host-only
 * (M8: the same scale at the two reads in guest code). */
static void car_lod_vblank(void) {
    static int on = -1;
    static uint32_t last;
    if (on < 0) { const char* e = getenv("CHI_C40_LOD"); on = e && *e == '1'; }   /* default OFF: no FPS gain measured (24.10.) */
    if (!on || !chicago_active() || !psx_mod_game_started()) { last = 0; return; }
    uint32_t v = psx_mod_read_word(0x80096A48u);
    if (v == last || v < 1000u || v > 100000u) return;
    last = v * 726u / 1000u;
    psx_mod_write_word(0x80096A48u, last);
}

/* C88 cop slots (exe c88_slot_patches): Driver 1's 4 cop slots live in a 24-slot array here; the exe reads its address
 * from 4 zero-block words, written every vblank (the zero block is cleared at boot). Host memory for now (M8: the array
 * in RAM under the stack, 24 x 1960 B = 46 KB; NY 8 slots). */
#define NM_SLOTS 24u
#define NM_STRIDE 0x7A8u
static uint32_t s_nm_slots;
/* C94 draw-distance words (exe_patches C94_WORDS, zero block 0x800933F0..0x80093424; the zero block is cleared at boot,
 * so they have no image value): Driver 1's values every vblank unless driver.personal's "Extra draw distance" set
 * XDD (0x80093408) = 1 and owns them. */
/* C96: with NIGHTMARE on, the level is set up with the two big primitive buffers (driver_gameplay.c) so Driver 1's car
 * budget (FUN_80014A8C: cars nearest first, low model once the buffer is nearly full) keeps every near chaser's full
 * model; the object / tile limits stay Driver 1's. XPBN follows the buffers the level really uses. */
extern int dp_big_prim_buffers(uint32_t* pb0, uint32_t* pb1);
extern int dp_big_prim_buffers_active(void);
static void c94_defaults_vblank(void) {
    if (psx_mod_read_word(0x80093408u) == 1u) return;
    uint32_t w[15] = { 0x000A80C4u, 19u, 19u, 4u, 18u, 9u, 0u, 0x000A76ACu, 7000u, 9000u,
                       0x16800u, 0x12000u, 0x000D8600u, 0x000F6600u, (uint32_t)-0x1E000 };
    uint32_t b0, b1;
    if ((psx_mod_read_word(0x800933C8u) || psx_mod_read_word(0x8009342Cu)) && dp_big_prim_buffers(&b0, &b1)) { w[12] = b0; w[13] = b1; }
    if (dp_big_prim_buffers_active()) w[14] = (uint32_t)-0x50000;
    for (uint32_t i = 0; i < 15u; i++)
        if (psx_mod_read_word(0x800933F0u + 4u * i) != w[i]) psx_mod_write_word(0x800933F0u + 4u * i, w[i]);
}

/* C113: shadow near-plane guard (exe_patches c113_patches): SNEAR 0x80093438 = minimum corner SZ for a car shadow (any
 * corner nearer = the shadow is skipped that frame); 0 = Driver 1. Default 128 (H 256 / 2 = the GTE divide-overflow bound:
 * a corner at / behind the camera plane); CHI_SHADOW_NEAR=<sz> overrides, 0 = off. */
static void c113_snear_vblank(void) {
    static int v = -1;
    if (v < 0) { const char* e = getenv("CHI_SHADOW_NEAR"); v = e && *e ? atoi(e) : 128; if (v < 0) v = 0; }
    if (psx_mod_read_word(0x80093438u) != (uint32_t)v) psx_mod_write_word(0x80093438u, (uint32_t)v);
}

/* C114: pursuer indicators (exe_patches c114_patches): PIND 0x8009343C = highest cop slot that gets a red triangle on the
 * bottom edge (0 = Driver 1: every pursuer). CHI_PURSUIT_IND=<slots> applies while Nightmare (0x800933C8) or Hell
 * (0x8009342C) runs; default 0 until the user decides (recommended 4 = Driver 1's own cop slots). */
static void c114_pind_vblank(void) {
    static int lim = -1;
    if (lim < 0) { const char* e = getenv("CHI_PURSUIT_IND"); lim = e && *e ? atoi(e) : 0; if (lim < 0) lim = 0; }
    uint32_t want = (lim && (psx_mod_read_word(0x800933C8u) || psx_mod_read_word(0x8009342Cu))) ? (uint32_t)lim : 0u;
    if (psx_mod_read_word(0x8009343Cu) != want) psx_mod_write_word(0x8009343Cu, want);
}

static void cop_slots_vblank(void) {
    c94_defaults_vblank();
    c113_snear_vblank();
    c114_pind_vblank();
    {   /* C101: XPVS 0x80093430 = 729 while an extra-draw Chicago level runs (exe decodes its 27 x 27 PVS natively; the
         * cops' 19 x 19 view goes through XTMP 0x80093434), else 0 (Driver 1's 19 x 19) */
        static uint32_t xtmp;
        if (!xtmp) xtmp = psx_mod_alloc_guest_memory(27u * 27u + 7u, 16u);
        uint32_t want = (s_lvl_xd && xtmp && chicago_active()) ? 729u : 0u;
        if (psx_mod_read_word(0x80093434u) != xtmp) psx_mod_write_word(0x80093434u, xtmp);
        if (psx_mod_read_word(0x80093430u) != want) psx_mod_write_word(0x80093430u, want);
    }
    if (!s_nm_slots) s_nm_slots = psx_mod_alloc_guest_memory(NM_SLOTS * NM_STRIDE, 16u);
    uint32_t b = s_nm_slots ? s_nm_slots : 0x800C4E38u;   /* no memory: Driver 1's array (exe loops then overrun!) */
    if (psx_mod_read_word(0x800933D4u) != b) {
        psx_mod_write_word(0x800933D4u, b);                       /* SLOT0 */
        psx_mod_write_word(0x800933D8u, b - NM_STRIDE);           /* SLOT1 (1-based) */
        psx_mod_write_word(0x800933DCu, b - 0x4E38u);             /* SLOTM: replaces 'lui 0xc', + 0x4E38 / 0x4690 / 0x6CD8 kept */
        psx_mod_write_word(0x800933E0u, b + NM_SLOTS * NM_STRIDE);/* SLOTE */
    }
}

/* C88 NIGHTMARE (NGHT 0x800933C8, user 63 B; CHI_C88_NIGHTMARE=0: row hidden, no effect): every moving traffic car (AI record
 * +1 state 2 / 3) gets a cop slot from 5.. and pursuit state 4, exactly as Driver 1's FUN_80063B74 + FUN_8001548C set
 * up a cop (slot cleared, +0x78C 1, +0x790 0, +0x794 1, +0x40 0, +0x7A4 = the car, record +5 = slot + 1, +8 = 0, count
 * 0x80097764 + 1); Driver 1 frees it when the car goes (FUN_80063AB4). Cops on (0x800976F8), felony kept high and the
 * pursuit 'seen' (0x80097744 = 0, 0x8009770C = 2) so nobody gives up. NY: at most 8 slots in use (the PS1 budget). Off:
 * the chasers' slots are released and they go back to traffic. Take a Ride / Survival etc. alike; mission cars (states
 * other than 2 / 3) are left alone. Host-only (M8: the same loop as guest code in the AI update). */
static uint32_t s_nm_last_fc = 0xFFFFFFFFu;
static uint32_t s_nm_mine;                               /* bit k = slot k (0-based) was given to a chaser here */
static int nightmare_active(void) {
    return nightmare_enabled() && psx_mod_game_started() && (psx_mod_read_word(0x800933C8u) || psx_mod_read_word(0x8009342Cu))
           && psx_mod_read_word(0x8009B0BCu) != 0u && s_nm_slots && psx_mod_read_word(0x800933D4u) == s_nm_slots;
}
/* give AI record i a chaser slot (5..24) set up like Driver 1's FUN_80063B74 + FUN_8001548C, pursuit state 4.
 * 0 when no slot is free or the car is not eligible. */
static int nightmare_take(uint32_t i) {
    uint32_t rec = 0x80098950u + 0x50u * i, st = psx_mod_read_byte(rec + 1u);
    if ((st != 2u && st != 3u) || psx_mod_read_byte(rec + 5u)) return 0;
    if (psx_mod_read_byte(rec + 0x10u) == 5u && s_spc_cur && !s_spc_valid) return 0;   /* special: only while it is the
                                                                                 * loaded area's special (no swap pending) */
    uint32_t car = 0x8009B230u + 0x18Cu * i;
    if ((int16_t)psx_mod_read_half(car + 0x17Cu) >= 0x4651) return 0;   /* wrecked: Driver 1 drops such a cop at once */
    uint32_t k = 4u;
    while (k < NM_SLOTS && psx_mod_read_word(s_nm_slots + k * NM_STRIDE + 0x78Cu)) k++;
    if (k >= NM_SLOTS) return 0;
    uint32_t sl = s_nm_slots + k * NM_STRIDE;
    for (uint32_t o = 0; o < NM_STRIDE; o += 4u) psx_mod_write_word(sl + o, 0u);
    psx_mod_write_word(sl + 0x78Cu, 1u); psx_mod_write_word(sl + 0x794u, 1u); psx_mod_write_word(sl + 0x7A4u, car);
    psx_mod_write_byte(rec + 5u, k + 1u);
    psx_mod_write_byte(rec + 8u, 0u);                     /* not a lane-traffic car (Driver 1's cops: 0) */
    psx_mod_write_byte(rec + 1u, 4u);
    s_nm_mine |= 1u << k;                                 /* not counted in 0x80097764: see nightmare_vblank */
    return 1;
}
/* C88 Nightmare r3 (user 25.10.): every traffic car is a chaser FROM ITS SPAWN. FUN_800154A8 (the spawn) ends with
 * FUN_8001B720(car, 1) (jal 0x80015FA4): its entry is hooked, and a freshly placed traffic car (state 2) takes a
 * chaser slot before its first frame, so it starts the pursuit where it spawned (no turn-off from a driving lane).
 * Its model, palette, horn / engine stay traffic (Driver 1 ties the siren and the lights to the police model). */
static void nightmare_spawn_entry(CPUState* cpu, uint32_t address) {
    (void)address;
    if (cpu->gpr[31] != 0x80015FACu || cpu->gpr[5] != 1u || !nightmare_active()) return;
    uint32_t id = psx_mod_read_byte(cpu->gpr[4]);
    if (id >= 1u && id <= 24u && nightmare_take(id - 1u))
        psx_mod_write_word(0x800933E8u, psx_mod_read_word(0x800933E8u) + 1u);   /* spawn-time chasers (test counter) */
}
static void nightmare_vblank(void) {
    uint32_t mine = s_nm_mine;                                /* bit k = slot k (0-based) was given to a chaser here */
    int on = nightmare_active();
    if (!on) {
        if (mine && psx_mod_game_started()) {            /* release: back to traffic */
            for (uint32_t i = 0; i < 24u; i++) {
                uint32_t rec = 0x80098950u + 0x50u * i, k = psx_mod_read_byte(rec + 5u);
                if (k && k <= NM_SLOTS && (mine >> (k - 1u) & 1u)) {
                    psx_mod_write_word(s_nm_slots + (k - 1u) * NM_STRIDE + 0x78Cu, 0u);
                    psx_mod_write_byte(rec + 5u, 0u); psx_mod_write_byte(rec + 8u, 1u);
                    if (psx_mod_read_byte(rec + 1u) == 4u) psx_mod_write_byte(rec + 1u, 2u);
                }
            }
        }
        s_nm_mine = 0;
        s_nm_last_fc = 0xFFFFFFFFu;                      /* the next level start is 'fresh' */
        if (psx_mod_read_word(0x800933E4u)) psx_mod_write_word(0x800933E4u, 0u);   /* Driver 1's re-plan cadence */
        return;
    }
    static int replan = -1;                              /* CHI_C88_NM_REPLAN=n (4/8/16/32, Roadmap 65; default 0 = Driver 1's 4):
                                                          * every pursuer re-plans every n frames while Nightmare is on */
    if (replan < 0) { const char* e = getenv("CHI_C88_NM_REPLAN"); replan = e ? atoi(e) : 0; if (replan < 0 || replan > 64) replan = 0; }
    {
        uint32_t m = replan >= 8 ? (uint32_t)(replan >= 64 ? 63 : replan >= 32 ? 31 : replan >= 16 ? 15 : 7) : 0u;
        if (psx_mod_read_word(0x800933E4u) != m) psx_mod_write_word(0x800933E4u, m);
    }
    /* C90: only while the game itself runs a frame (frame counter 0x800970D8 moved): nothing during the loading screen
     * (cue mid loading, wrong sound setup) or the pause menu (horns kept sounding). A new level / restart (counter back
     * to a small value) starts with the felony meter full. */
    uint32_t fc = psx_mod_read_word(0x800970D8u);
    int ran = fc != s_nm_last_fc, fresh = s_nm_last_fc == 0xFFFFFFFFu || fc < s_nm_last_fc;
    s_nm_last_fc = fc;
    if (!ran) return;
    (void)fresh;
    /* r3 (user: police cars spawn and chase too): Driver 1's director spawns cops while its count 0x80097764 is below
     * the wanted number (FUN_80064A64); chasers in slots 5.. must not count, so the count is set to the real cops in
     * slots 1-4 every running frame (Driver 1's frees decrement it for chasers too). */
    {
        uint32_t cops = 0;
        for (uint32_t k = 0; k < 4u; k++) cops += psx_mod_read_word(s_nm_slots + k * NM_STRIDE + 0x78Cu) != 0u;
        if (psx_mod_read_word(0x80097764u) != cops) psx_mod_write_word(0x80097764u, cops);
    }
    /* user 66: the felony meter stays full the whole session while Nightmare is on (every map, every restart) */
    if ((int32_t)psx_mod_read_word(0x80097708u) < 0x1000) psx_mod_write_word(0x80097708u, 0x1000u);
    psx_mod_write_word(0x800976F8u, 1u);                 /* cops on (Newtown: its cap 0 keeps the director's cops away) */
    psx_mod_write_word(0x80097744u, 0u);
    psx_mod_write_word(0x8009770Cu, 2u);
    static int envcap = -1;                              /* CHI_C88_NM_CAP=n: at most n slots in use (user 25.10.: no cap on
                                                          * PC; NY's 8 is the real-PS1 RAM budget, NOTES M8 list) */
    if (envcap < 0) { const char* e = getenv("CHI_C88_NM_CAP"); envcap = e ? atoi(e) : 0; if (envcap < 0) envcap = 0; }
    uint32_t cap = NM_SLOTS;
    if (envcap > 0 && (uint32_t)envcap < cap) cap = (uint32_t)envcap;
    uint32_t used = 0;
    for (uint32_t k = 0; k < NM_SLOTS; k++) {
        if (psx_mod_read_word(s_nm_slots + k * NM_STRIDE + 0x78Cu)) used++;
        else s_nm_mine &= ~(1u << k);
    }
    /* specials: release a chasing special when another special is pending (the player entered another special's
     * region) so it drives off / despawns like Driver 1 traffic and the swap can happen */
    if (s_spc_cur && !s_spc_valid)
        for (uint32_t i = 0; i < 24u; i++) {
            uint32_t rec = 0x80098950u + 0x50u * i, k = psx_mod_read_byte(rec + 5u);
            if (k > 4u && k <= NM_SLOTS && psx_mod_read_byte(rec + 0x10u) == 5u && (s_nm_mine >> (k - 1u) & 1u)) {
                psx_mod_write_word(s_nm_slots + (k - 1u) * NM_STRIDE + 0x78Cu, 0u);
                psx_mod_write_byte(rec + 5u, 0u); psx_mod_write_byte(rec + 8u, 1u);
                if (psx_mod_read_byte(rec + 1u) == 4u) psx_mod_write_byte(rec + 1u, 2u);
                s_nm_mine &= ~(1u << (k - 1u)); used--;
            }
        }
    /* C108 (user: every car chases; runner nm_thin: 21 -> 2 pursuers when the player is boxed in): a chaser that Driver 1
     * wrecked (damage +0x17C >= 0x4651: the pursuit handler frees it at once) stays on the road as traffic next to the
     * player, the 24 AI records stay full and nothing new spawns. Wrecked cars stay wrecked (Hell is the never-wreck
     * cheat); such a car is removed exactly like Driver 1's own despawn (FUN_80017C50: state and lane flag 0, its index
     * back on the free stack 0x80099AF0 / 0x80096FC4) once it is out of view (behind the camera: depth through the
     * camera matrix 0x800BBE84 < 0, or > 15000 away) after 2 s, or after 10 s anyway; the director then spawns a fresh
     * car, which the spawn hook makes a chaser. */
    {
        static uint16_t wreck_frames[24];
        int32_t cx = (int32_t)psx_mod_read_word(0x8008A8F0u), cy = (int32_t)psx_mod_read_word(0x8008A8F4u),
                cz = (int32_t)psx_mod_read_word(0x8008A8F8u);
        int32_t m20 = (int16_t)psx_mod_read_half(0x800BBE84u + 12u), m21 = (int16_t)psx_mod_read_half(0x800BBE84u + 14u),
                m22 = (int16_t)psx_mod_read_half(0x800BBE84u + 16u);
        for (uint32_t i = 0; i < 24u; i++) {
            uint32_t rec = 0x80098950u + 0x50u * i, st = psx_mod_read_byte(rec + 1u);
            uint32_t car = 0x8009B230u + 0x18Cu * i;
            if (!((st == 2u || st == 3u) && !psx_mod_read_byte(rec + 5u) && (int16_t)psx_mod_read_half(car + 0x17Cu) >= 0x4651)) {
                wreck_frames[i] = 0; continue;
            }
            if (wreck_frames[i] < 0xFFFFu) wreck_frames[i]++;
            int32_t x = (int32_t)psx_mod_read_word(car + 0xC8u), y = (int32_t)psx_mod_read_word(car + 0xCCu),
                    z = (int32_t)psx_mod_read_word(car + 0xD0u);
            double dx = (double)(x - cx), dy = (double)(-y - cy), dz = (double)(z - cz);
            double depth = (m20 * dx + m21 * dy + m22 * dz) / 4096.0, dist = sqrt(dx * dx + dz * dz);
            int unseen = depth < 0 || dist > 15000;
            if ((wreck_frames[i] >= 60u && unseen) || wreck_frames[i] >= 300u) {
                uint32_t n = psx_mod_read_word(0x80096FC4u);
                if (n == 0u || n > 24u) continue;                 /* free stack not as expected: leave it */
                psx_mod_write_byte(rec + 1u, 0u); psx_mod_write_byte(rec + 8u, 0u);
                psx_mod_write_word(0x80096FC4u, n - 1u);
                psx_mod_write_byte(0x80099AF0u + n - 1u, (uint8_t)i);
                wreck_frames[i] = 0;
            }
        }
    }
    /* fallback for cars that were on the road before Nightmare acted (the level's first frames): nearest first */
    int32_t px = (int32_t)psx_mod_read_word(0x8009B16Cu), pz = (int32_t)psx_mod_read_word(0x8009B174u);
    uint32_t order[24], no = 0;
    double dist[24];
    for (uint32_t i = 0; i < 24u; i++) {
        uint32_t rec = 0x80098950u + 0x50u * i, st = psx_mod_read_byte(rec + 1u);
        if ((st != 2u && st != 3u) || psx_mod_read_byte(rec + 5u)) continue;
        uint32_t car = 0x8009B230u + 0x18Cu * i;
        double dx = (double)((int32_t)psx_mod_read_word(car + 0xC8u) - px), dz = (double)((int32_t)psx_mod_read_word(car + 0xD0u) - pz);
        uint32_t j = no++;
        dist[i] = dx * dx + dz * dz;
        while (j > 0 && dist[order[j - 1]] > dist[i]) { order[j] = order[j - 1]; j--; }
        order[j] = i;
    }
    for (uint32_t n = 0; n < no && used < cap; n++)
        used += (uint32_t)nightmare_take(order[n]);
}

/* C102 (cheats 5: the bus's shadow is the size of its wheel quad): Driver 1's shadow (FUN_8002ADEC) is one quad through
 * the car's 4 corner points (car +0x88 / 0x98 / 0xA8 / 0xB8 = P0 P1 P3 P2, also the physics' points); the exe reads a
 * copy plus SHD[car] (0x80093480 + 16 car: 4 x (dx, dz) i16). For the loaded Chicago special (model 5) the offsets
 * stretch the quad along its own two axes to the .sps.bin size (Driver 2's cPoints x 1.32: half length = (zmax - zmin)
 * / 2, half width = (xmax - xmin) / 2); the axes come from the quad itself (a = (P0+P1)/2 - c, b = (P0+P3)/2 - c, the
 * longer one = length). Every vblank (the orientation changes slowly; positions are not used). 0 elsewhere. */
/* the SHD offsets that stretch car `car`'s corner quad to half length hl / half width hw along its own axes (0 = unusable) */
static int shadow_stretch(uint32_t car, double hl, double hw, int16_t d[8]) {
    static const uint32_t off[4] = { 0x88u, 0x98u, 0xA8u, 0xB8u };   /* P0 P1 P3 P2 */
    double px[4], pz[4], cx = 0, cz = 0;
    for (int k = 0; k < 4; k++) {
        px[k] = (double)(int32_t)psx_mod_read_word(car + off[k]); pz[k] = (double)(int32_t)psx_mod_read_word(car + off[k] + 8u);
        cx += px[k] / 4; cz += pz[k] / 4;
    }
    double ax = (px[0] + px[1]) / 2 - cx, az = (pz[0] + pz[1]) / 2 - cz;   /* a: P0 P1 side */
    double bx = (px[0] + px[2]) / 2 - cx, bz = (pz[0] + pz[2]) / 2 - cz;   /* b: P0 P3 side */
    double la = sqrt(ax * ax + az * az), lb = sqrt(bx * bx + bz * bz);
    if (!(la > 50 && lb > 50 && la < 5000 && lb < 5000)) return 0;
    double ka = (la >= lb ? hl : hw) / la, kb = (la >= lb ? hw : hl) / lb;
    static const int sa[4] = { 1, 1, -1, -1 }, sb[4] = { 1, -1, 1, -1 };
    for (int k = 0; k < 4; k++) {
        double nx = cx + sa[k] * ka * ax + sb[k] * kb * bx, nz = cz + sa[k] * ka * az + sb[k] * kb * bz;
        double dx = nx - px[k], dz = nz - pz[k];
        if (dx > 3000) dx = 3000; if (dx < -3000) dx = -3000; if (dz > 3000) dz = 3000; if (dz < -3000) dz = -3000;
        d[2 * k] = (int16_t)lround(dx); d[2 * k + 1] = (int16_t)lround(dz);
    }
    return 1;
}
/* C138 (Polish: the Havana mini's shadow 1.5 x too wide, 1.9 x too long): Driver 1's corner quad is its fixed 370 x 1040
 * body box for every player car; in a D2 city car 0's quad is stretched like the special's (C102) to the chosen car's
 * D2 cPoints x 1.32 from the level's .pps.bin (PPS1 entry = player choice 0x8009683C). The physics corners stay
 * (handling). Host-only (M8: the same SHD words written by guest code per frame). CHI_C138_SHADOW=0: off. */
static void player_shadow(int t) {
    static int had, en = -1;
    if (en < 0) { const char* e = getenv("CHI_C138_SHADOW"); en = !(e && *e == '0'); }
    const int32_t* q = s_pps[t];
    int16_t d[8] = {0};
    int use = 0;
    if (en && chicago_active() && psx_mod_game_started() && s_pps_n[t] >= 2u + 12u && q[0] == 0x31535050) {
        uint32_t ch = psx_mod_read_word(0x8009683Cu) & 3u;
        if ((int32_t)ch < q[1] && 2u + 12u * ch + 12u <= s_pps_n[t]) {
            const int32_t* e = q + 2 + 12 * ch;
            int32_t x0 = e[1], x1 = e[1], z0 = e[2], z1 = e[2];
            for (int c = 1; c < 4; c++) {
                if (e[1 + 2 * c] < x0) x0 = e[1 + 2 * c]; if (e[1 + 2 * c] > x1) x1 = e[1 + 2 * c];
                if (e[2 + 2 * c] < z0) z0 = e[2 + 2 * c]; if (e[2 + 2 * c] > z1) z1 = e[2 + 2 * c];
            }
            double hl = (z1 - z0) / 2.0, hw = (x1 - x0) / 2.0;
            use = hl > 0 && hw > 0 && shadow_stretch(0x8009B0A4u, hl, hw, d);
        }
    }
    if (!use && !had) return;
    if (!use) memset(d, 0, sizeof d);
    for (int k = 0; k < 4; k++)
        psx_mod_write_word(0x80093480u + 4u * (uint32_t)k, (uint32_t)(uint16_t)d[2 * k] | ((uint32_t)(uint16_t)d[2 * k + 1] << 16));
    had = use;
}
static void shadow_vblank(void) {
    static uint8_t had[25];
    player_shadow(s_chi_night ? 1 : 0);
    int t = s_chi_night ? 1 : 0;
    const int32_t* q = s_sps[t];
    int ok = chicago_active() && psx_mod_game_started() && s_spc_cur && s_sps_n[t] >= 2u && q[0] == 0x31535053;
    double hl = 0, hw = 0;
    if (ok) {
        ok = 0;
        for (int32_t k = 0; k < q[1] && 2u + 9u * (uint32_t)k + 8u < s_sps_n[t]; k++) {
            const int32_t* e = q + 2 + 9 * k;
            if ((uint32_t)e[0] != s_spc_cur) continue;
            int32_t x0 = e[1], x1 = e[1], z0 = e[2], z1 = e[2];
            for (int c = 1; c < 4; c++) {
                if (e[1 + 2 * c] < x0) x0 = e[1 + 2 * c]; if (e[1 + 2 * c] > x1) x1 = e[1 + 2 * c];
                if (e[2 + 2 * c] < z0) z0 = e[2 + 2 * c]; if (e[2 + 2 * c] > z1) z1 = e[2 + 2 * c];
            }
            hl = (z1 - z0) / 2.0; hw = (x1 - x0) / 2.0; ok = hl > 0 && hw > 0;
            break;
        }
    }
    for (uint32_t ci = 1; ci < 25u; ci++) {
        uint32_t rec = 0x80098950u + 0x50u * (ci - 1u), car = 0x8009B0A4u + 0x18Cu * ci, shd = 0x80093480u + 16u * ci;
        int16_t d[8] = {0};
        int use = ok && psx_mod_read_byte(rec + 1u) != 0u && psx_mod_read_byte(rec + 0x10u) == 5u;
        if (use && !shadow_stretch(car, hl, hw, d)) { use = 0; memset(d, 0, sizeof d); }
        if (!use && !had[ci]) continue;
        for (int k = 0; k < 4; k++)
            psx_mod_write_word(shd + 4u * (uint32_t)k, (uint32_t)(uint16_t)d[2 * k] | ((uint32_t)(uint16_t)d[2 * k + 1] << 16));
        had[ci] = (uint8_t)use;
    }
}

/* C107 (rewind / state loads, user decision B): guest RAM, VRAM, mod memory and (runtime C107) the GPU-DMA aperture come
 * back from the state; the plugin's own host-side caches do not. A restore shows as the game's VBlank counter
 * 0x80095250 going back; then the caches that mirror guest state are re-derived from the restored RAM: the area
 * switch tracker (no spool redirect / carry release for a load the state already contains), the special's tpage / CLUT
 * build (rebuilt next vblank), Nightmare's frame gate (the next running frame counts as fresh). */
static void restore_vblank(void) {
    static uint32_t last_vb;
    uint32_t vb = psx_mod_read_word(0x80095250u);
    if (last_vb && vb + 2u < last_vb) {
        s_last_flag = psx_mod_read_word(AREA_LOADING_FLAG);
        s_last_area = psx_mod_read_word(CURRENT_AREA);
        s_spc_built_area = 0xFFFFFFFFu;
        s_nm_last_fc = 0xFFFFFFFFu;
        {   /* M3 fix (2): the restored state's level variant (asset set, level entry) */
            uint32_t w = psx_mod_read_word(VARIANT_WORD);
            if (variant_switch("CHI_VARIANT_STATE") && (w >> 24) == 0x56u && psx_mod_read_word(CITY_WORD) == 3u)
                apply_variant(w & 0xFu, "state restore");
        }
        fprintf(stdout, "driver.chicago: state restore seen (vblank %u -> %u): plugin caches re-derived\n",
                (unsigned)last_vb, (unsigned)vb);
    }
    last_vb = vb;
}

/* C138 (Polish: the Havana mini's light glows oversized): Driver 1's ShowCarlight 0x80043FDC sizes are immediates at its 14
 * call sites (reverse 20, indicators 30, brake 25, night headlights 30, night tail 25); Driver 2 draws every car with
 * fixed sizes (cosmetic.c: HEADLIGHT 18, BRAKE / BACK 17, INDICATOR 20, REVERSE 14 D2 units -> x1.32 = 24 / 22 / 26 / 18).
 * While a D2 city runs those immediates are Driver 2's (every car); Driver 1's elsewhere. CHI_C138_LIGHTS=0: off.
 * Host-only (M8: the same 14 code words from guest code at level load). */
static const uint32_t s_c138_light_words[][3] = {
    { 0x80043970u, 0x24070014u, 0x24070012u }, { 0x800439A8u, 0x24070014u, 0x24070012u },   /* AddReverseLight 20 -> 18 */
    { 0x80043BB0u, 0x2407001Eu, 0x2407001Au }, { 0x80043BF8u, 0x2407001Eu, 0x2407001Au },   /* AddIndicatorLight 30 -> 26 */
    { 0x80043C64u, 0x2407001Eu, 0x2407001Au }, { 0x80043CBCu, 0x2407001Eu, 0x2407001Au },
    { 0x80043DF4u, 0x24070019u, 0x24070016u }, { 0x80043E3Cu, 0x24070019u, 0x24070016u },   /* AddBrakeLight 25 -> 22 */
    { 0x80046398u, 0x2407001Eu, 0x24070018u }, { 0x800463F0u, 0x2407001Eu, 0x24070018u },   /* AddNightLights head 30 -> 24 */
    { 0x800464ACu, 0x2407001Eu, 0x24070018u }, { 0x80046504u, 0x2407001Eu, 0x24070018u },
    { 0x800465A8u, 0x24070019u, 0x24070016u }, { 0x800465F4u, 0x24070019u, 0x24070016u },   /* AddNightLights tail 25 -> 22 */
};
/* C141 / C140 (probe d2 cities 6: Newtown spawned police drawn as bare wheels): C79 rewrites LA's script to cop cap 0 in
 * the mission-parse hook; after a Rio Day/Night back-out the hook did not apply and LA's cap 2 stayed. Hook-independent
 * guard: while the selector's Newtown runs (CITY 7 via LA's Take a Ride 0x7C), the cop cap 0x80097760 is 0 every vblank
 * (Newtown has no police model; Nightmare keeps working: it relies on this cap, NOTES C88). CHI_C79=0: off. */
static void c141_newtown_vblank(void) {
    static int en = -1;
    if (en < 0) { const char* e = getenv("CHI_C79"); en = !(e && *e == '0'); }
    if (!en || !s_slot_enabled || s_virtual != V_NEWTOWN || psx_mod_read_word(CITY_WORD) != 7u
        || psx_mod_read_word(MISSION_NUMBER) != 0x7Cu || !psx_mod_game_started())
        return;
    if (psx_mod_read_word(0x80097760u) != 0u) {
        psx_mod_write_word(0x80097760u, 0u);
        static uint32_t told;
        if (!told++) fprintf(stdout, "driver.chicago: C141 Newtown: cop cap forced to 0 (the script still had it)\n");
    }
}
/* C148 (user: the glows do not match the car's size): exe c148_patches turn the 14 size immediates into 'lh a3, LSZ+k(gp)'
 * (LSZ 0x80093750: reverse, indicator, brake, head, tail halfwords). The DrawCar entry hook (0x8003A698, a0 = car, 0 =
 * player; PlayerCarFX / AddNightLights run inside it, the AI indicators / brake right after it) writes the car's sizes:
 * Driver 1's (20 / 30 / 25 / 30 / 25) outside D2 cities, else Driver 2's fixed ones (18 / 26 / 22 / 24 / 22, x1.32)
 * scaled for the player's car by its D2 length ratio (.pps.bin, length / 1040 x 4096; the Havana mini ~0.53).
 * The vblank keeps the table valid between frames; old exes (immediates) keep the C138 word switch. CHI_C148_LIGHTS=0:
 * no per-car scaling. Host-only (M8: a guest table per car model written at level load + the same lh sites). */
#define LSZ 0x80093750u
static int lsz_patched(void) { return psx_mod_read_word(0x80043970u) == 0x8787CFE0u; }
static void lsz_write(const int16_t v[5]) {
    for (uint32_t k = 0; k < 5u; k++)
        if ((int16_t)psx_mod_read_half(LSZ + 2u * k) != v[k]) psx_mod_write_half(LSZ + 2u * k, (uint16_t)v[k]);
}
static int32_t car_light_ratio(uint32_t car);
static void lsz_for_car(uint32_t car) {
    static const int16_t d1[5] = { 20, 30, 25, 30, 25 }, d2[5] = { 18, 26, 22, 24, 22 };
    static int en = -1, sc = -1;
    if (en < 0) { const char* e = getenv("CHI_C138_LIGHTS"); en = !(e && *e == '0'); }
    if (sc < 0) { const char* e = getenv("CHI_C148_LIGHTS"); sc = !(e && *e == '0'); }
    if (!en || !chicago_active()) { lsz_write(d1); return; }
    int32_t ratio = sc ? car_light_ratio(car) : 4096;
    int16_t v[5];
    for (int k = 0; k < 5; k++) { int32_t x = (d2[k] * ratio + 2048) >> 12; v[k] = (int16_t)(x < 6 ? 6 : x); }
    lsz_write(v);
}
/* C148 (user: the ground headlight / light pool does not match the car's size): FUN_80040BAC (a0 = car index) builds the
 * pool polygon from immediate car-space points and rotates each with FUN_8004EAC0 (calls 0x80040DD4 / 0x80040E30, return
 * 0x80040DDC / 0x80040E38). Entry hooks: 0x80040BAC remembers the car, 0x8004EAC0 scales the point (x / z) by the car's
 * D2 length ratio when called from there (player's car in a D2 city; 4096 = unchanged). CHI_C148_BEAM=0: off.
 * Host-only (M8: a 6-word cave at the two call sites scaling by a per-car table word). */
static uint32_t s_beam_car = 0xFFu;
static int32_t car_light_ratio(uint32_t car) {
    static int sc = -1;
    if (sc < 0) { const char* e = getenv("CHI_C148_LIGHTS"); sc = !(e && *e == '0'); }
    int t = s_chi_night ? 1 : 0;
    const int32_t* q = s_pps[t];
    if (!sc || car != 0u || !chicago_active() || s_pps_n[t] < 2u + 12u || q[0] != 0x31535050) return 4096;
    uint32_t ch = psx_mod_read_word(0x8009683Cu) & 3u;
    if ((int32_t)ch >= q[1] || 2u + 12u * ch + 12u > s_pps_n[t]) return 4096;
    int32_t r = q[2 + 12 * ch + 11];
    return r > 1024 && r < 8192 ? r : 4096;
}
static void beam_entry(struct CPUState* cpu, uint32_t address) {
    (void)address;
    s_beam_car = cpu->gpr[4];
}
static void rotpoint_entry(struct CPUState* cpu, uint32_t address) {
    (void)address;
    static int en = -1;
    if (en < 0) { const char* e = getenv("CHI_C148_BEAM"); en = !(e && *e == '0'); }
    uint32_t ra = cpu->gpr[31];
    if (!en || (ra != 0x80040DDCu && ra != 0x80040E38u)) return;
    int32_t r = car_light_ratio(s_beam_car);
    if (r == 4096) return;
    /* width: the car's D2 half width (.pps.bin colBox x, x1.32) against Driver 1's 185; length: points on the body
     * scale, points past Driver 1's bumper (half length 520) keep their throw beyond the car's own bumper */
    int32_t rw = 4096, t = s_chi_night ? 1 : 0;
    const int32_t* q = s_pps[t];
    uint32_t ch = psx_mod_read_word(0x8009683Cu) & 3u;
    if (q[0] == 0x31535050 && (int32_t)ch < q[1] && q[2 + 12 * ch + 9] > 40 && q[2 + 12 * ch + 9] < 400) rw = q[2 + 12 * ch + 9] * 4096 / 185;
    uint32_t v = cpu->gpr[4];
    int32_t x = (int32_t)psx_mod_read_word(v), z = (int32_t)psx_mod_read_word(v + 8u);
    int32_t hl = (520 * r) >> 12;
    int32_t nz = z > 520 ? z - 520 + hl : z < -520 ? z + 520 - hl : (int32_t)(((int64_t)z * r) >> 12);
    psx_mod_write_word(v, (uint32_t)(int32_t)(((int64_t)x * rw) >> 12));
    psx_mod_write_word(v + 8u, (uint32_t)nz);
}
static void drawcar_entry(struct CPUState* cpu, uint32_t address) {
    (void)address;
    if (lsz_patched()) lsz_for_car(cpu->gpr[4]);
}
static void c138_lights_vblank(void) {
    static int en = -1;
    if (en < 0) { const char* e = getenv("CHI_C138_LIGHTS"); en = !(e && *e == '0'); }
    if (lsz_patched()) { lsz_for_car(0xFFu); return; }   /* C148 exe: data table (AI default between frames) */
    switch_words(s_c138_light_words, sizeof s_c138_light_words / sizeof s_c138_light_words[0], en && chicago_active());
}

extern void driver_personal_rewind_vblank(void);   /* C130: the Mods 'Rewind' choice (driver_personal.c) */
static void civ_time_select(void);
static void area_switch_guard_vblank(void) {
    driver_personal_rewind_vblank();
    civ_time_select();                                   /* C147 (3): day / night civilian set */
    restore_vblank();
    shadow_vblank();
    c138_lights_vblank();
    c137_bank4_vblank();
    c141_newtown_vblank();
    s_vbl_n++;
    car_lod_vblank();
    cop_slots_vblank();
    nightmare_vblank();
    driver_personal_fps_tick(1);                          /* FPS stats for test tools (driver_personal.c) */
    surface_select_vblank();
    chicago_slot_vblank();
    glow_offsets_vblank();
    {   /* C122 (exe_patches c122_patches): MAPD2 = the running D2 city has its own minimap frame -> the pause map centres on
         * the player, clamps, pans with the d-pad; 0 = Driver 1's map. PS1 path: part of the city's data block. */
        static int mapd2_on = -1;
        if (mapd2_on < 0) { const char* e = getenv("CHI_MAPD2"); mapd2_on = !(e && *e == '0'); }   /* test switch */
        uint32_t want = (mapd2_on && d2_city() >= 0 && s_have_map) ? 1u : 0u;
        if (psx_mod_read_word(0x80093628u) != want) psx_mod_write_word(0x80093628u, want);
    }
    if (s_sea_level) {                                   /* Chicago's water lies 1084 below the street */
        if (s_level_format < 0 && psx_mod_game_started() && !psx_mod_read_word(AREA_LOADING_FLAG))
            s_level_format = level_has_switch_pads();
        psx_mod_write_word(SEA_LEVEL_ADDR, chicago_active() && (s_level_format == 1 || s_assets_city != D2C_CHICAGO)
                                           ? (uint32_t)s_sea_y : 0u);   /* M3: the city's water (Chicago -1084) */
    }
    if (!s_empty_model || !psx_mod_game_started())
        return;
    if (!s_lvl_seen || s_vbl_n - s_lvl_beat > LVL_BEAT_MAX)   /* C84: no level running (frontend, FMV) */
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
    if (!flag && s_last_flag)
        carry_release();
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

/* C30 (17.10.): buildings popping out during an area load. The redirect above left every streamed model of the
 * outgoing area on the empty model until the load completes (~1 s): all area buildings vanished (user snapshot
 * probe_look 20261016-184018: area 12 loading, 708 entries on the empty model, no streamed model left). Now the
 * streamed models are first copied into a carry buffer in mod memory (their absolute vertex / polygon / normal /
 * collision pointers relocated) and the entries point at the copies; the loader's own pointers replace them when the
 * load completes, and copies the new area does not use go to the empty model then. Models shared by both areas
 * (the buildings around the switch) therefore never disappear; with the corridor layout (CHI_POLISH_CORRIDOR=2) they
 * draw from pages both areas share. Host-only (M8: a PS1 version needs a second model buffer in RAM).
 * CHI_C30_CARRY=0 = the old redirect only. */
#define CARRY_BYTES 0x40000u
static uint32_t s_carry, s_carry_used, s_carry_n;
static int carry_enabled(void) {
    static int on = -1;
    if (on < 0) { const char* e = getenv("CHI_C30_CARRY"); on = !(e && *e == '0'); }
    return on;
}
static uint32_t carry_spool_models(void) {
    uint32_t lo = psx_mod_read_word(MODEL_SPOOL_BUFFER) & 0x1FFFFFFFu, hi = lo + MODEL_SPOOL_BYTES, n = 0;
    if (!lo || !carry_enabled())
        return 0;
    if (!s_carry)
        s_carry = psx_mod_alloc_guest_memory(CARRY_BYTES, 16u);
    if (!s_carry)
        return 0;
    s_carry_used = 0;
    /* pass 1: copy every plain streamed model; remember source range -> copy (instances point into their source) */
    enum { CARRY_MAX = 2048 };
    static uint32_t src_lo[CARRY_MAX], src_sz[CARRY_MAX], dst_of[CARRY_MAX], ent[CARRY_MAX];
    uint32_t m = 0;
    for (uint32_t i = 0; i < MODEL_TABLE_ENTRIES && m < CARRY_MAX; i++) {
        uint32_t p = psx_mod_read_word(MODEL_TABLE_ADDR + 4u * i) & 0x1FFFFFFFu;
        if (p < lo || p >= hi)
            continue;
        uint32_t size = psx_mod_read_word(0x80000000u | (p - 4u));
        if (size < 36u || size > 0x10000u || p + size > hi || s_carry_used + size + 8u > CARRY_BYTES)
            continue;                                         /* not a plain model: left to the redirect */
        uint32_t dst = s_carry + s_carry_used + 4u;
        psx_mod_write_word(dst - 4u, size);
        for (uint32_t k = 0; k < size; k += 4u)
            psx_mod_write_word(dst + k, psx_mod_read_word(0x80000000u | (p + k)));
        src_lo[m] = p; src_sz[m] = size; dst_of[m] = dst; ent[m] = i; m++;
        s_carry_used += (size + 8u + 3u) & ~3u;
    }
    /* pass 2 (opt2d, 21.10.: streamed instance models point into their SOURCE model, which may be another streamed model;
     * left as is they pointed into the spool buffer the staging overwrites -> garbage polygons, dispatch fatal in the
     * world renderer 0x80030B5C): every data pointer into the spool buffer goes to the copy of the model it points into;
     * a model with a pointer into an uncarried part of the buffer goes to the empty model (redirect) instead */
    for (uint32_t j = 0; j < m; j++) {
        uint32_t dst = dst_of[j], ok = 1;
        for (uint32_t f = 16u; f <= 32u; f += 4u) {            /* vertices, poly_block, normals, point_normals, collision */
            uint32_t v = psx_mod_read_word(dst + f), pv = v & 0x1FFFFFFFu;
            if (pv < lo || pv >= hi)
                continue;                                    /* resident data (in-memory source) or 0: keep */
            uint32_t q = (pv >= src_lo[j] && pv < src_lo[j] + src_sz[j]) ? j : CARRY_MAX;
            for (uint32_t t = 0; q == CARRY_MAX && t < m; t++)
                if (pv >= src_lo[t] && pv < src_lo[t] + src_sz[t]) q = t;
            if (q == CARRY_MAX) { ok = 0; break; }
            psx_mod_write_word(dst + f, dst_of[q] + (pv - src_lo[q]));
        }
        psx_mod_write_word(MODEL_TABLE_ADDR + 4u * ent[j], ok ? dst : s_empty_model);
        if (ok) n++;
    }
    s_carry_n = n;
    return n;
}
/* the load completed: carried copies the loader did not replace (models of the outgoing area only) -> empty model */
static void carry_release(void) {
    if (!s_carry || !s_carry_n)
        return;
    uint32_t n = 0;
    for (uint32_t i = 0; i < MODEL_TABLE_ENTRIES; i++) {
        uint32_t p = psx_mod_read_word(MODEL_TABLE_ADDR + 4u * i);
        if (p >= s_carry && p < s_carry + CARRY_BYTES) {
            psx_mod_write_word(MODEL_TABLE_ADDR + 4u * i, s_empty_model);
            n++;
        }
    }
    fprintf(stdout, "driver.chicago: C30 load complete: %u of %u carried models released\n", (unsigned)n, (unsigned)s_carry_n);
    s_carry_n = 0;
}

static void area_switch_entry(struct CPUState* cpu, uint32_t address) {
    (void)cpu; (void)address;
    LVL_BEAT();
    if (!s_empty_model || !chicago_active())
        return;
    uint32_t c = s_carry_n ? 0u : carry_spool_models();   /* a switch during a pending load keeps the first copies */
    if (c)
        fprintf(stdout, "driver.chicago: C30 area switch: %u streamed models carried (%u bytes)\n", (unsigned)c, (unsigned)s_carry_used);
    uint32_t n = redirect_spool_entries();
    s_last_flag = psx_mod_read_word(AREA_LOADING_FLAG);
    s_last_area = psx_mod_read_word(CURRENT_AREA);
    fprintf(stdout, "driver.chicago: area switch to %u: %u spool entries redirected at the queue\n",
            (unsigned)s_last_area, (unsigned)n);
}

/* C42 r3 (17.10.): wheel size per car, like Driver 2 (cars.c: wheelSize from CAR_COSMETICS; tread vertices 16..23 = +-size,
 * rim 8..15 rotated at size * 14142 / 10000). Driver 1 draws every wheel at tread 73 / rim 101 (the shared wheel models'
 * vertices; the rim radius 0x65 in DrawCarWheels). This entry hook (0x8003B208, per car) sets the shared wheel models'
 * hub (0..7) and tread vertices to the car's size and the rim word WHEEL_RIM (0x80093394 = rim - 101, read by the
 * exe's rim sites, exe_patches c42w_patches); Driver 1 cars and other cities get 73 / 0. Host-only (M8: the same few stores
 * in guest code at the function start, size from a per-model table). */
/* R33 (user: far cars change colour): Driver 1 draws a far car's low model with FUN_0002E230 and the world polygon
 * handlers, which take each texture's CLUT from 0x80087030[page * 32 + texture] = the base paint; the near model takes the
 * car's palette from the car CLUT table 0x800BE9FC. Entry hook (game.toml) on FUN_0002E230: for the low model of a
 * palettised civilian (resident models 2-4) the CLUT words of its textures are set to the palette of the car being drawn
 * (0x80096990: 1 = base, 2..5 = table slots 0..3), so near and far match. Only car low models read those words at draw
 * time (near models bake theirs). Host-only (M8: the same few stores in a guest wrapper of the low-model call). */
static uint32_t s_lod_model[5], s_lod_n[5]; static uint16_t s_lod_tex[5][128];
static void lod_entry(struct CPUState* cpu, uint32_t address) {
    (void)address;
    LVL_BEAT();
    if (psx_mod_read_word(0x800978A0u) != 4u || !chicago_active()) return;
    uint32_t mp = cpu->gpr[4];
    int m = -1;
    for (int k = 2; k <= 4; k++)
        if (mp && psx_mod_read_word(0x800A11F8u + 4u * (uint32_t)k) == mp) { m = k; break; }
    if (m < 0) return;
    if (s_lod_model[m] != mp) {                         /* the (page, texture) list of this low model */
        uint32_t polys = psx_mod_read_word(mp + 0x14u), np = psx_mod_read_half(mp + 0xEu), q = polys, n = 0;
        static const uint8_t psize[32] = { 8, 12, 16, 24, 20, 20, 28, 32, 8, 12, 16, 16, 0, 0, 0, 0,   /* 0x80089F1C */
                                           12, 12, 12, 16, 20, 20, 24, 24, 0, 0, 0, 0, 0, 0, 0, 0 };
        for (uint32_t i = 0; i < np && n < 128u; i++) {
            uint32_t t = psx_mod_read_byte(q) & 31u;
            if (t >= 20u && t <= 23u) {
                uint32_t pt = psx_mod_read_byte(q + 1u) | (psx_mod_read_byte(q + 2u) << 8);
                int dup = 0;
                for (uint32_t j = 0; j < n && !dup; j++) dup = s_lod_tex[m][j] == pt;
                if (!dup) s_lod_tex[m][n++] = (uint16_t)pt;
            }
            q += psize[t] ? psize[t] : 4u;
        }
        s_lod_n[m] = n; s_lod_model[m] = mp;
    }
    uint32_t pal = psx_mod_read_word(0x80096990u) & 0xFFu, first = psx_mod_read_word(0x800975CCu);
    uint32_t slot = pal <= 1u ? 0x10u : 4u * ((pal - 2u) & 3u);
    for (uint32_t j = 0; j < s_lod_n[m]; j++) {
        uint32_t page = s_lod_tex[m][j] & 0xFFu, tex = s_lod_tex[m][j] >> 8;
        if (page < first || page > first + 1u || tex >= 30u) continue;
        uint32_t clut = psx_mod_read_word(0x800BE9FCu + 600u * (page - first) + 20u * tex + slot) & 0xFFFFu;
        if (clut && psx_mod_read_half(0x80087030u + 2u * (page * 32u + tex)) != clut)
            psx_mod_write_half(0x80087030u + 2u * (page * 32u + tex), (uint16_t)clut);
    }
}

#define WHEEL_RIM 0x80093394u
static void wheels_entry(struct CPUState* cpu, uint32_t address) {
    (void)address;
    LVL_BEAT();
    static int last = -1;
    int ws = 73;
    if ((s_car_whl_n == 7u || s_car_whl_n == 9u) && psx_mod_read_word(0x800978A0u) == 4u && chicago_active()) {
        uint32_t car = cpu->gpr[4], model = car ? psx_mod_read_word(cpu->gpr[29] + 0x10u) : 0u;
        int v = car == 0u ? s_car_whl[psx_mod_read_word(0x8009683Cu) & 3u]
                          : (model == 5u && s_spc_cur ? (int)s_spc_wheel
                             : (model >= 1u && model <= s_car_whl_n - 4u ? s_car_whl[4u + model - 1u] : 0));
        if (v > 20 && v < 300) ws = v;
    }
    {   /* C144 (Analyst: D2 tyres float 73 - R above the road): draw-only wheel centre offset WDY (exe c144_patches) */
        static int en = -1;
        if (en < 0) { const char* e = getenv("CHI_C144"); en = !(e && *e == '0'); }
        uint32_t dy = en && ws != 73 ? (uint32_t)(73 - ws) : 0u;
        if (psx_mod_read_word(0x80093748u) != dy) psx_mod_write_word(0x80093748u, dy);
    }
    if (ws == last)
        return;
    last = ws;
    int rim = ws == 73 ? 101 : (int)lround(ws * 1.4142);   /* Driver 1's own wheel: exactly its 101 */
    psx_mod_write_word(WHEEL_RIM, (uint32_t)(rim - 101));
    static const int8_t hub[8][2] = { {1,-1}, {1,1}, {-1,1}, {-1,-1}, {1,1}, {1,-1}, {-1,-1}, {-1,1} };
    static const int8_t tread[8][2] = { {-1,0}, {-1,0}, {0,-1}, {0,-1}, {0,1}, {0,1}, {1,0}, {1,0} };
    /* C148 (user: the mini's tyres too big again after driving a little): DrawCarWheels picks gCleanWheelModelPtr
     * 0x800970C0, gFastWheelModelPtr 0x800970AC (spinning) and, for the player's damaged wheels, gDamWheelModelPtr
     * 0x800970C4 (this one was never resized) */
    for (int m = 0; m < 3; m++) {
        uint32_t mdl = psx_mod_read_word(m == 2 ? 0x800970C4u : m ? 0x800970ACu : 0x800970C0u);
        if ((mdl & 0x1FFFFFFFu) < 0x10000u || (mdl & 0x1FFFFFFFu) >= 0x200000u) continue;
        uint32_t vtx = psx_mod_read_word(mdl + 0x10u);
        if ((vtx & 0x1FFFFFFFu) < 0x10000u || (vtx & 0x1FFFFFFFu) >= 0x200000u || psx_mod_read_half(mdl + 12u) != 24u) continue;
        /* vertices 8..15 (rim) are written by DrawCarWheels itself at the RIM radius for whichever model it draws */
        for (int i = 0; i < 8; i++) {
            psx_mod_write_half(vtx + 8u * (uint32_t)i + 2u, (uint16_t)(int16_t)(hub[i][0] * ws));
            psx_mod_write_half(vtx + 8u * (uint32_t)i + 4u, (uint16_t)(int16_t)(hub[i][1] * ws));
            psx_mod_write_half(vtx + 8u * (uint32_t)(16 + i) + 2u, (uint16_t)(int16_t)(tread[i][0] * ws));
            psx_mod_write_half(vtx + 8u * (uint32_t)(16 + i) + 4u, (uint16_t)(int16_t)(tread[i][1] * ws));
        }
    }
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
    LVL_BEAT();
    variant_parse(cpu->gpr[16]);                          /* M3 fixes (1) / (3): before the level loads */
    /* Chicago music: the loader stores (mission + 3) & 7 ^ MUSIC_XOR right after this parse; Chicago gets
     * song 8 (day) / 9 (night) of the relocated MUSIC.BIN, every other level 0 (its own song) */
    if (s_slot_enabled) {
        uint32_t x = 0;
        if (s_have_music && chicago_active())
            x = (s_song_base + (s_chi_night ? 1u : 0u)) ^ ((cpu->gpr[16] + 3u) & 7u);   /* M3: Chicago 8 / 9, Havana 10 / 11 */
        else if (la_day_active())   /* the in-game script calls (0x80068C6C) parse too: mission word, not s0 */
            /* C63: LA by day plays song 2 ("The Briefcase", EXP 16.10.); the chase switch takes song 2's own position */
            x = 2u ^ ((psx_mod_read_word(MISSION_NUMBER) + 3u) & 7u);
        else if (cpu->gpr[16] == 0x7Cu && s_virtual == V_TRAIN)
            /* C65: the selector's Desert (LA's Take a Ride 0x7C with CITY 6) plays Miami's night song (4) */
            x = 4u ^ ((cpu->gpr[16] + 3u) & 7u);
        if (psx_mod_read_word(MUSIC_XOR) != x) {
            psx_mod_write_word(MUSIC_XOR, x);
            fprintf(stdout, "driver.chicago: music word %u (%s)\n", (unsigned)x,
                    x ? s_d2c[s_assets_city].name : "off");
        }
    }
    /* C140 (probe d2 cities 6: Newtown ran LA's raw script after a Rio Day/Night back-out and an Interview hover; police,
     * cars in the air, the car falling, then a stall): the gate read the mission WORD, which the menu routing rewrites
     * (0x7C <-> 0xAE) while the cursor moves; the mission being parsed is s0 (the loader's argument), so gate on that. */
    uint32_t parsed = cpu->gpr[16];
    if (!s_slot_enabled || !is_extra(s_virtual) || !via_la_for(s_virtual) || parsed != 0x7Cu) {
        if (s_slot_enabled && is_extra(s_virtual) && via_la_for(s_virtual) && psx_mod_read_word(MISSION_NUMBER) == 0x7Cu)
            fprintf(stdout, "driver.chicago: C140 mission parse skipped: s0 %#x, mission word 0x7C, level %d\n",
                    (unsigned)parsed, s_virtual);
        return;
    }
    if (psx_mod_read_word(MISSION_NUMBER) != 0x7Cu)
        fprintf(stdout, "driver.chicago: C140 mission word %#x while parsing 0x7C (level %d): parsed anyway\n",
                (unsigned)psx_mod_read_word(MISSION_NUMBER), s_virtual);
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
    /* C79 (user R43: Newtown = traffic + the player only): LA's Take a Ride ends "b 32 26(2)" = cops on (0x800976F8 = 1),
     * cop cap 2 (0x80097760); Newtown's own script has "26(0) 31". Rewrite to cops off / cap 0 for the selector's Newtown
     * (Desert keeps LA's cops until the user decides, Roadmap Q44). CHI_C79=0: unchanged. */
    {
        static int c79 = -1;
        if (c79 < 0) { const char* e = getenv("CHI_C79"); c79 = !(e && *e == '0'); }
        if (c79 && s_virtual == V_NEWTOWN)
            for (uint32_t i = 0; i + 8u < n; i += 4u)
                if (psx_mod_read_word(MISSION_SAFE + i) == 0x32u && psx_mod_read_word(MISSION_SAFE + i + 4u) == 0x26u
                    && psx_mod_read_word(MISSION_SAFE + i + 8u) < 5u) {
                    psx_mod_write_word(MISSION_SAFE + i, 0x31u);
                    psx_mod_write_word(MISSION_SAFE + i + 8u, 0u);
                    fprintf(stdout, "driver.chicago: C79 Newtown: cops off (script +%u)\n", (unsigned)i);
                }
    }
    cpu->gpr[4] = MISSION_SAFE;
    cpu->gpr[5] = MISSION_SAFE + n;
    psx_mod_write_word(MISSION_BUF_PTR, MISSION_SAFE);
    psx_mod_write_word(MISSION_PTR, MISSION_SAFE);
    psx_mod_write_word(MISSION_END_PTR, MISSION_SAFE + n);
    fprintf(stdout, "driver.chicago: C50 mission script (%u bytes) parsed from %#x (was %#x), level %d\n",
            (unsigned)n, (unsigned)MISSION_SAFE, (unsigned)a0, s_virtual);
}

/* C129 phase 2 (user: Driver 2's traffic lanes, a "perfect replica"; Strategy 30.10.: the D2 civ-AI core runs host-side
 * in the plugin for now, D2 cities only; NOTES "C129 plan"). The core = chicago/c129 (REDRIVER2 civ_ai.c road following,
 * the same sources as the verified mipsel build) in c129_plugin.cpp, working in Driver 2 coordinates on the city's D2
 * road blob (package asset c129_roads.bin: "C129", D1 offset x / z, then export_roads.py's "D2RD" blob; D1 = D2 x 1.32 +
 * offset, the converter's worldscale). Hook = the entry of FUN_8004C15C (called once per frame right after
 * GlobalTimeStep = after physics; game.toml). Every civilian D1 spawns (record state 2, resident model 2-5) is put on the
 * nearest D2 lane point running along its heading and its record goes to state 10 (handler table entry 10 = the empty
 * one; exe c129_patches make FUN_80013D88 return early for states >= 9, so Driver 1's speed / lane logic never touches
 * it); each frame the core advances it (kinematic follow) and the car's x / z (+ the <<4 copies), velocity, yaw
 * (quaternion rotated about y, matrix rebuilt) and heading are written; y and pitch / roll stay physics'. Driver 1 still
 * despawns it far from the player (record cleared -> detached). Cops, the player, felony / red-light rules: Driver 1's
 * roads as before. D1 cities: nothing. CHI_C129=1 on (test switch; default off until verified).
 * Host-only (M8: the mipsel build of the same core as a guest overlay after the RAM diet). */
extern int c129_roads_load(const void* blob, uint32_t size, const int16_t* rcossin);
extern void c129_reset(void);
extern void c129_frame(void);
extern int c129_attach(int slot, int x, int z, int heading, int maxd, int* ox, int* oz, int* odir, int* oroad, int* olane);
extern void c129_detach(int slot);
extern int c129_step(int slot, int speed, int* ox, int* oz, int* odir, int* oroad, int* olane, int* octrl);
extern int c129_speed_limit(int slot);
#define C129_REC   0x80098950u
#define C129_CARS  0x8009B0A4u
#define C129_STATE 10u
static int s_c129_city = -2, s_c129_ok;
static int32_t s_c129_off[2];
static uint8_t s_c129_on[22];
static int32_t s_c129_spd[22], s_c129_pos[22][2];
static uint32_t s_c129_att, s_c129_fail, s_c129_lost, s_c129_fc;
static int c129_enabled(void) {
    static int en = -1;
    if (en < 0) { const char* e = getenv("CHI_C129"); en = e && *e == '1'; }
    return en;
}
static int32_t c129_to_d1(int32_t v, int axis) { return (int32_t)lround(v * 1.32) + s_c129_off[axis]; }
static int32_t c129_to_d2(int32_t v, int axis) { return (int32_t)lround((v - s_c129_off[axis]) / 1.32); }
static void c129_load_city(void) {
    s_c129_ok = 0;
    memset(s_c129_on, 0, sizeof s_c129_on);
    FILE* f = fopen(apath("c129_roads.bin"), "rb");
    if (!f) { fprintf(stdout, "driver.chicago: C129 no road blob for this city\n"); return; }
    static uint8_t buf[64 * 1024];
    size_t n = fread(buf, 1, sizeof buf, f);
    fclose(f);
    if (n < 28 || memcmp(buf, "C129", 4) != 0) { fprintf(stdout, "driver.chicago: C129 road blob bad\n"); return; }
    memcpy(s_c129_off, buf + 4, 8);
    static int16_t tab[4096 * 2];
    for (uint32_t i = 0; i < 4096u * 2u; i += 2) {
        uint32_t w = psx_mod_read_word(0x8008EAA8u + 2u * i);
        tab[i] = (int16_t)(w & 0xFFFFu); tab[i + 1] = (int16_t)(w >> 16);
    }
    s_c129_ok = c129_roads_load(buf + 12, (uint32_t)(n - 12), tab);
    fprintf(stdout, "driver.chicago: C129 D2 roads %s (offset %d, %d)\n", s_c129_ok ? "loaded" : "REJECTED",
            (int)s_c129_off[0], (int)s_c129_off[1]);
}
/* yaw the car to `dir` (4096 = full turn) keeping physics' pitch / roll: q' = qy(delta) * q, matrix as LongQuaternion2Matrix */
static void c129_set_yaw(uint32_t car, int32_t dir) {
    int16_t m02 = (int16_t)psx_mod_read_half(car + 4u + 4u), m22 = (int16_t)psx_mod_read_half(car + 4u + 16u);
    double cur = atan2((double)m02, (double)m22), want = dir * (2.0 * 3.14159265358979 / 4096.0);
    double d = want - cur, s = sin(d / 2.0), c = cos(d / 2.0);
    double qx = (int32_t)psx_mod_read_word(car + 0x30u), qy = (int32_t)psx_mod_read_word(car + 0x34u);
    double qz = (int32_t)psx_mod_read_word(car + 0x38u), qw = (int32_t)psx_mod_read_word(car + 0x3Cu);
    /* Hamilton product (0, s, 0, c) * (qx, qy, qz, qw) */
    double nx = c * qx + s * qz, ny = c * qy + s * qw, nz = c * qz - s * qx, nw = c * qw - s * qy;
    double len = sqrt(nx * nx + ny * ny + nz * nz + nw * nw);
    if (len < 1.0) return;
    double k = 4096.0 / len;
    int32_t q[4] = { (int32_t)lround(nx * k), (int32_t)lround(ny * k), (int32_t)lround(nz * k), (int32_t)lround(nw * k) };
    for (int i = 0; i < 4; i++) psx_mod_write_word(car + 0x30u + 4u * (uint32_t)i, (uint32_t)q[i]);
#define FHR(a) (((a) + (1 << 10)) >> 11)
    int32_t yy = FHR(q[1] * q[1]), zz = FHR(q[2] * q[2]), xx = FHR(q[0] * q[0]), zw = FHR(q[2] * q[3]), xy = FHR(q[0] * q[1]);
    int32_t xz = FHR(q[0] * q[2]), yw = FHR(q[1] * q[3]), xw = FHR(q[0] * q[3]), yz = FHR(q[1] * q[2]);
#undef FHR
    int16_t m[9] = { (int16_t)(4096 - (yy + zz)), (int16_t)(xy - zw), (int16_t)(xz + yw),
                     (int16_t)(xy + zw), (int16_t)(4096 - (xx + zz)), (int16_t)(yz - xw),
                     (int16_t)(xz - yw), (int16_t)(yz + xw), (int16_t)(4096 - (xx + yy)) };
    for (int i = 0; i < 9; i++) psx_mod_write_half(car + 4u + 2u * (uint32_t)i, (uint16_t)m[i]);
    psx_mod_write_word(car + 0xF8u, (uint32_t)(dir & 4095));
}
static void c129_post_physics_entry(struct CPUState* cpu, uint32_t address) {
    (void)cpu; (void)address;
    if (!c129_enabled()) return;
    int city = chicago_active() ? s_assets_city : -1;
    if (city != s_c129_city) {
        if (s_c129_ok) c129_reset();
        s_c129_city = city;
        s_c129_ok = 0;
        if (city >= 0) c129_load_city();
    }
    if (city < 0 || !s_c129_ok) return;
    uint32_t fc = psx_mod_read_word(0x800970D8u);
    if (fc == s_c129_fc) return;                    /* once per game frame */
    s_c129_fc = fc;
    c129_frame();
    for (uint32_t i = 0; i < 22u; i++) {
        uint32_t rec = C129_REC + 0x50u * i;
        uint32_t st = psx_mod_read_byte(rec + 1u), model = psx_mod_read_byte(rec + 0x10u);
        uint32_t car = C129_CARS + ((uint32_t)psx_mod_read_byte(rec) + 1u) * 0x18Cu;
        if (s_c129_on[i] && st != C129_STATE) { c129_detach((int)i); s_c129_on[i] = 0; s_c129_lost++; }
        if (!s_c129_on[i]) {
            if (st != 2u || model < 2u || model > 5u) continue;
            int32_t x = (int32_t)psx_mod_read_word(car + 0x18u), z = (int32_t)psx_mod_read_word(car + 0x20u);
            int32_t h = (int32_t)psx_mod_read_word(car + 0xF8u) & 4095;
            int ox, oz, od, road, lane;
            if (!c129_attach((int)i, c129_to_d2(x, 0), c129_to_d2(z, 1), h, 3000, &ox, &oz, &od, &road, &lane)) {
                s_c129_fail++;
                continue;
            }
            s_c129_on[i] = 1; s_c129_att++;
            s_c129_spd[i] = c129_speed_limit((int)i) / 2;
            s_c129_pos[i][0] = c129_to_d1(ox, 0); s_c129_pos[i][1] = c129_to_d1(oz, 1);
            psx_mod_write_byte(rec + 1u, (uint8_t)C129_STATE);
            psx_mod_write_word(car + 0x18u, (uint32_t)s_c129_pos[i][0]);
            psx_mod_write_word(car + 0x20u, (uint32_t)s_c129_pos[i][1]);
            psx_mod_write_word(car + 0x24u, (uint32_t)(s_c129_pos[i][0] << 4));
            psx_mod_write_word(car + 0x2Cu, (uint32_t)(s_c129_pos[i][1] << 4));
            c129_set_yaw(car, od);
            if (s_c129_att <= 8u)
                fprintf(stdout, "driver.chicago: C129 attach rec %u model %u road %#x lane %d (moved %d)\n", i, model, road, lane,
                        (int)lround(hypot((double)(s_c129_pos[i][0] - x), (double)(s_c129_pos[i][1] - z))));
            continue;
        }
        int lim = c129_speed_limit((int)i);
        if (s_c129_spd[i] < lim) s_c129_spd[i] += 2;
        if (s_c129_spd[i] > lim) s_c129_spd[i] -= 4;
        if (s_c129_spd[i] < 0) s_c129_spd[i] = 0;
        int ox, oz, od, road, lane, ctrl;
        if (!c129_step((int)i, s_c129_spd[i], &ox, &oz, &od, &road, &lane, &ctrl)) {
            c129_detach((int)i); s_c129_on[i] = 0; s_c129_lost++;
            psx_mod_write_byte(rec + 1u, 1u);          /* confused: parked (Driver 1's state 1, FUN_80013D88 idles it) */
            continue;
        }
        int32_t nx = c129_to_d1(ox, 0), nz = c129_to_d1(oz, 1);
        int32_t vx = nx - s_c129_pos[i][0], vz = nz - s_c129_pos[i][1];
        s_c129_pos[i][0] = nx; s_c129_pos[i][1] = nz;
        psx_mod_write_word(car + 0x18u, (uint32_t)nx);
        psx_mod_write_word(car + 0x20u, (uint32_t)nz);
        psx_mod_write_word(car + 0x24u, (uint32_t)(nx << 4));
        psx_mod_write_word(car + 0x2Cu, (uint32_t)(nz << 4));
        psx_mod_write_word(car + 0x40u, (uint32_t)(vx << 12));
        psx_mod_write_word(car + 0x48u, (uint32_t)(vz << 12));
        psx_mod_write_word(car + 0x50u, 0u);           /* no yaw spin from physics: the path sets the heading */
        c129_set_yaw(car, od);
    }
    static uint32_t vb;
    if (++vb % 1800u == 0u)
        fprintf(stdout, "driver.chicago: C129 attached %u, not on a D2 lane %u, released %u\n", s_c129_att, s_c129_fail, s_c129_lost);
}

PSX_MOD_CONSTRUCTOR(driver_chicago_register) {
    psx_mod_register_activation_plugin("driver.model-table", model_table_activate);
    psx_mod_register_vblank_plugin("driver.model-table", area_switch_guard_vblank);   /* also runs surface_select_vblank */
    psx_mod_register_function_entry_plugin("driver.model-table", AREA_TEXTURE_QUEUE, area_switch_entry);
    psx_mod_register_activation_plugin("driver.chicago-slot", chicago_slot_activate);
    psx_mod_register_function_entry_plugin("driver.chicago-slot", MISSION_PARSE, mission_parse_entry);
    psx_mod_register_function_entry_plugin("driver.model-table", MAPHEIGHT_FN, d2sf_entry);
    psx_mod_register_function_entry_plugin("driver.model-table", FINDSURF_FN, d2sf_entry);
    psx_mod_register_function_entry_plugin("driver.model-table", 0x8003B208u, wheels_entry);
    psx_mod_register_function_entry_plugin("driver.model-table", 0x8002E230u, lod_entry);   /* R33: far-car palettes */
    psx_mod_register_function_entry_plugin("driver.model-table", 0x8001B720u, nightmare_spawn_entry);   /* C88 r3 */
    psx_mod_register_function_entry_plugin("driver.model-table", 0x8004C15Cu, c129_post_physics_entry);   /* C129 */
    psx_mod_register_function_entry_plugin("driver.model-table", 0x8003A698u, drawcar_entry);   /* C148 light sizes */
    psx_mod_register_function_entry_plugin("driver.model-table", 0x80040BACu, beam_entry);      /* C148 light pool car */
    psx_mod_register_function_entry_plugin("driver.model-table", 0x8004EAC0u, rotpoint_entry);  /* C148 light pool scale */
}
