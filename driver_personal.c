/* driver_personal.c — personal, local-only trusted plugins for Driver (SLUS-00842).
 *
 * Features (toggled in the launcher's Mods list, package "driver.personal"):
 *   dev-mode     session log file + F9 / L3+R3 snapshot (RAM, scratchpad, mod memory, CPU regs,
 *                screenshot, heartbeat) under <app>/dev/, plus an automatic
 *                "-hang" snapshot when the game stops handling VBlank;
 *                top-right overlay (F10: game FPS, emulation speed, position,
 *                area); L3+Triangle / F5 puts the player's car back on its wheels
 *                and repairs it (all damage reset).
 *   unlock-all   see driver_unlock.c.
 *   skip-intro   see driver_intro.c.
 *
 * Linked through CODEGEN_SETUP_SOURCES in the root CMakeLists.txt. Not part of
 * the upstream driver-recomp project; re-apply after updating (see README.md). */

#include "driver_personal.h"

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <math.h>

#include "mod_plugins.h"
#include "cpu_state.h"
#include "gpu.h"
#include "host_osd.h"
#include "psx_rewind.h"
#include "../psxrecomp/runtime/src/png_write.h"

#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <direct.h>
#include <io.h>
#define dp_mkdir(p) _mkdir(p)
#else
#include <sys/stat.h>
#define dp_mkdir(p) mkdir((p), 0755)
#define VK_F5  0
#define VK_F10 0
#endif

extern uint8_t* g_psx_ram;
extern int present_shot_request(const char* path);
extern void gl_renderer_sync_cpu(void);
extern void vk_renderer_sync_cpu(void);
#ifndef PSX_NO_DEBUG_TOOLS
extern CPUState* debug_cpu_ptr;
#endif

static char s_app_dir[1024];
static uint32_t s_vblanks;

/* ---- shared helpers ---------------------------------------------------- */

/* <app>/ : the exe's folder, minus a trailing build-* folder. */
const char* dp_app_dir(void) {
    if (s_app_dir[0])
        return s_app_dir;
#if defined(_WIN32)
    GetModuleFileNameA(NULL, s_app_dir, sizeof(s_app_dir));
#else
    snprintf(s_app_dir, sizeof(s_app_dir), ".");
#endif
    char* slash = strrchr(s_app_dir, '\\');
    if (!slash) slash = strrchr(s_app_dir, '/');
    if (slash) *slash = '\0';
    slash = strrchr(s_app_dir, '\\');
    if (!slash) slash = strrchr(s_app_dir, '/');
    if (slash && strncmp(slash + 1, "build-", 6) == 0)
        *slash = '\0';
    return s_app_dir;
}

int dp_option_enabled(const char* feature, const char* option) {
    char v[16];
    if (!psx_mod_option_value(DP_PACKAGE_ID, feature, option, v, sizeof(v)))
        return 0;
    return strcmp(v, "true") == 0 || strcmp(v, "1") == 0;
}

/* ---- dev-mode ---------------------------------------------------------- */

static int s_dump_key_was_down;

static void dp_timestamp(char* out, size_t cap) {
    time_t t = time(NULL);
    struct tm tmv;
#if defined(_WIN32)
    localtime_s(&tmv, &t);
#else
    localtime_r(&t, &tmv);
#endif
    strftime(out, cap, "%Y%m%d-%H%M%S", &tmv);
}

static int write_file(const char* path, const void* data, size_t len) {
    FILE* f = fopen(path, "wb");
    if (!f) return 0;
    int ok = fwrite(data, 1, len, f) == len;
    return fclose(f) == 0 && ok;
}

static void copy_file(const char* from, const char* to) {
    FILE* in = fopen(from, "rb");
    if (!in) return;
    FILE* out = fopen(to, "wb");
    if (out) {
        char buf[8192];
        size_t n;
        while ((n = fread(buf, 1, sizeof(buf), in)) > 0)
            fwrite(buf, 1, n, out);
        fclose(out);
    }
    fclose(in);
}

/* Native-resolution capture of the display area from VRAM (works headless). */
static void write_native_png(const char* path) {
    GpuDisplayInfo di;
    gpu_get_display_info(&di);
    if (di.disabled || di.width == 0 || di.height == 0) return;
    if (!di.depth24) {
        gl_renderer_sync_cpu();
        vk_renderer_sync_cpu();
    }
    uint32_t w = di.width > 640 ? 640 : di.width;
    uint32_t h = di.height > 512 ? 512 : di.height;
    uint8_t* rgb = (uint8_t*)malloc((size_t)w * h * 3);
    if (!rgb) return;
    for (uint32_t y = 0; y < h; y++)
        for (uint32_t x = 0; x < w; x++) {
            uint8_t* p = rgb + ((size_t)y * w + x) * 3;
            gpu_display_pixel_rgb(&di, x, y, &p[0], &p[1], &p[2]);
        }
    FILE* f = fopen(path, "wb");
    if (f) {
        png_write_rgb(f, rgb, w, h);
        fclose(f);
    }
    free(rgb);
}

static void write_regs_json(const char* path) {
    FILE* f = fopen(path, "w");
    if (!f) return;
    fprintf(f, "{\n  \"vblanks_since_boot\": %u", s_vblanks);
#ifndef PSX_NO_DEBUG_TOOLS
    const CPUState* c = debug_cpu_ptr;
    if (c) {
        fprintf(f, ",\n  \"pc\": \"0x%08X\", \"hi\": \"0x%08X\", \"lo\": \"0x%08X\",\n"
                   "  \"sr\": \"0x%08X\", \"cause\": \"0x%08X\", \"epc\": \"0x%08X\",\n"
                   "  \"gpr\": [",
                c->pc, c->hi, c->lo, c->cop0[12], c->cop0[13], c->cop0[14]);
        for (int i = 0; i < 32; i++)
            fprintf(f, "%s\"0x%08X\"", i ? ", " : "", c->gpr[i]);
        fprintf(f, "],\n  \"badvaddr\": \"0x%08X\"", c->cop0[8]);
    }
#endif
    {   /* C68 (16.10.): the interrupted guest context. When a hang sits in the BIOS exception handler, the CPU registers
         * above are the handler's; the BIOS saved the game's registers in the current thread's TCB
         * (0x108 -> process control block -> TCB; +8 r0..r31, +0x88 EPC, +0x8C hi, +0x90 lo, +0x94 SR, +0x98 cause).
         * Also the 64 words at the guest's sp (locals of the faulting function, e.g. a model index). */
        uint32_t pcb = psx_mod_read_word(0x80000108u), tcb = pcb ? psx_mod_read_word(0x80000000u | (pcb & 0x1FFFFFu)) : 0;
        if (tcb) {
            uint32_t t = 0x80000000u | (tcb & 0x1FFFFFu), g[32];
            for (int i = 0; i < 32; i++) g[i] = psx_mod_read_word(t + 8u + 4u * (uint32_t)i);
            fprintf(f, ",\n  \"guest_tcb\": \"0x%08X\", \"guest_epc\": \"0x%08X\", \"guest_sr\": \"0x%08X\", "
                       "\"guest_cause\": \"0x%08X\",\n  \"guest_sp\": \"0x%08X\", \"guest_gp\": \"0x%08X\", \"guest_ra\": \"0x%08X\",\n"
                       "  \"guest_gpr\": [", t, psx_mod_read_word(t + 0x88u), psx_mod_read_word(t + 0x94u),
                    psx_mod_read_word(t + 0x98u), g[29], g[28], g[31]);
            for (int i = 0; i < 32; i++) fprintf(f, "%s\"0x%08X\"", i ? ", " : "", g[i]);
            fputs("],\n  \"guest_stack\": [", f);
            uint32_t sp = g[29];
            int ok = (sp >= 0x80000000u && sp < 0x80200000u - 0x100u) || (sp >= 0x1F800000u && sp < 0x1F800400u - 0x100u);
            for (int i = 0; ok && i < 64; i++) fprintf(f, "%s\"0x%08X\"", i ? ", " : "", psx_mod_read_word(sp + 4u * (uint32_t)i));
            fputs("]", f);
        }
    }
    fputs("\n}\n", f);
    fclose(f);
}

static char s_last_dump_dir[1200];   /* the newest snapshot dir (the watchdog renames a recovered "-hang" to "-stall") */
static void dev_dump(const char* tag, int main_thread) {
    char ts[32], dir[1200], path[1300];
    dp_timestamp(ts, sizeof(ts));
    snprintf(dir, sizeof(dir), "%s/dev", dp_app_dir());
    dp_mkdir(dir);
    snprintf(dir, sizeof(dir), "%s/dev/dumps", dp_app_dir());
    dp_mkdir(dir);
    snprintf(dir, sizeof(dir), "%s/dev/dumps/%s-v%u%s", dp_app_dir(), ts, s_vblanks, tag);
    dp_mkdir(dir);
    snprintf(s_last_dump_dir, sizeof(s_last_dump_dir), "%s", dir);

    /* C79 (23.10.): RAM and mod memory first, each write's result in dump.txt (a probe hang dump arrived without ram.bin /
     * mod.bin: a failed or skipped write must leave a trace) */
    int ok_ram, ok_sp, ok_mod = -1;
    snprintf(path, sizeof(path), "%s/ram.bin", dir);
    ok_ram = write_file(path, g_psx_ram, 2u * 1024u * 1024u);
    {
        enum { MOD_DUMP_BYTES = 0x90000u };
        uint8_t* mod = (uint8_t*)malloc(MOD_DUMP_BYTES);
        if (mod) {
            for (uint32_t i = 0; i < MOD_DUMP_BYTES; i += 4u) {
                uint32_t w = psx_mod_read_word(0x9F000000u + i);   /* cell objects (Chicago), carry, specials; model table: RAM 0x80115600 since S4a */
                memcpy(mod + i, &w, 4);
            }
            snprintf(path, sizeof(path), "%s/mod.bin", dir);
            ok_mod = write_file(path, mod, MOD_DUMP_BYTES);
            free(mod);
        }
    }
    uint8_t sp[1024];
    for (uint32_t i = 0; i < sizeof(sp); i++)
        sp[i] = psx_mod_read_byte(0x1F800000u + i);
    snprintf(path, sizeof(path), "%s/scratchpad.bin", dir);
    ok_sp = write_file(path, sp, sizeof(sp));
    snprintf(path, sizeof(path), "%s/dump.txt", dir);
    {
        FILE* df = fopen(path, "w");
        if (df) {
            fprintf(df, "tag %s vblanks %u\nram.bin %s\nmod.bin %s\nscratchpad.bin %s\n", tag, s_vblanks,
                    ok_ram ? "ok" : "FAILED", ok_mod < 0 ? "no memory" : (ok_mod ? "ok" : "FAILED"), ok_sp ? "ok" : "FAILED");
            fclose(df);
        }
    }
    fprintf(stdout, "driver.personal: dump %s: ram %s, mod %s\n", dir, ok_ram ? "ok" : "FAILED", ok_mod > 0 ? "ok" : "FAILED");

    snprintf(path, sizeof(path), "%s/regs.json", dir);
    write_regs_json(path);
    snprintf(path, sizeof(path), "%s/screen_native.png", dir);
    write_native_png(path);
    /* What the player sees (filters/upscale); fulfilled on the next present. */
    snprintf(path, sizeof(path), "%s/screen.png", dir);
    if (main_thread)
        present_shot_request(path);

    /* The heartbeat lives in the working directory; check the build folder too. */
    char hb[1200];
    snprintf(path, sizeof(path), "%s/heartbeat.json", dir);
    copy_file("psx_freeze_heartbeat.json", path);
    snprintf(hb, sizeof(hb), "%s/build-release/psx_freeze_heartbeat.json", dp_app_dir());
    snprintf(path, sizeof(path), "%s/heartbeat_build.json", dir);
    copy_file(hb, path);

    fprintf(stdout, "driver.personal: dev dump written to %s\n", dir);
    fflush(stdout);
    if (main_thread)
        host_osd_push("DEV: snapshot saved (dev/dumps)", 2500);
}

/* runtime (local change, main.cpp): L3 + R3 held on any game controller */
int psx_host_controller_l3r3_held(void);

/* F9 (game window focused) or both stick buttons on a controller. */
static int dump_key_down(void) {
    if (psx_host_controller_l3r3_held())
        return 1;
#if defined(_WIN32)
    /* Only while one of our windows has focus. */
    HWND fg = GetForegroundWindow();
    DWORD pid = 0;
    if (!fg) return 0;
    GetWindowThreadProcessId(fg, &pid);
    if (pid != GetCurrentProcessId()) return 0;
    return (GetAsyncKeyState(VK_F9) & 0x8000) != 0;
#else
    return 0;
#endif
}

#if defined(_WIN32)
static DWORD WINAPI freeze_watchdog_thread(LPVOID arg);
#endif

/* Local runtime change (debug_server.c): in-process write guard, prints the
 * storing code to the log. Armed on what the Chicago freeze corrupts: the OT /
 * primitive-base fields of both draw buffer structs and libetc's interrupt
 * chain node (see chicago/NOTES.md). */
extern void psx_debug_add_write_guard(uint32_t lo, uint32_t hi);

/* C116 (user 27.10.): "Developer recording tools" (feature dev-tools, default on) owns the runtime's developer tools:
 * TCP debug server, recorders / rings, freeze heartbeat (psx_mod_request_dev_tools). Off = none of that background
 * work, and no F9 / dump.request snapshot (it needs the recorders). Developer Mode keeps its log, overlay and keys. */
static int s_dev_tools_on;
static void dev_tools_activate(void) {
    s_dev_tools_on = 1;
    psx_mod_request_dev_tools();
}

static void dev_mode_activate(void) {
    char ts[32], path[1300];
    dp_timestamp(ts, sizeof(ts));
    snprintf(path, sizeof(path), "%s/dev", dp_app_dir());
    dp_mkdir(path);
    snprintf(path, sizeof(path), "%s/dev/logs", dp_app_dir());
    dp_mkdir(path);
    snprintf(path, sizeof(path), "%s/dev/logs/driver-%s.log", dp_app_dir(), ts);
    /* Unbuffered: the tail of the log must survive a crash. */
    if (freopen(path, "a", stdout))
        setvbuf(stdout, NULL, _IONBF, 0);
#if defined(_WIN32)
    _dup2(_fileno(stdout), _fileno(stderr));
#endif
    setvbuf(stderr, NULL, _IONBF, 0);
    fprintf(stdout, "driver.personal: developer mode on, log %s\n", path);
    fprintf(stdout, "driver.personal: F9 or L3+R3 (controller) = snapshot; TCP debug server on 127.0.0.1:4370 (if built in)\n");
    fprintf(stdout, "driver.personal: F10 = overlay on/off; F5 or L3+Triangle = put the car back on its wheels and repair it\n");
#if defined(_WIN32)
    CreateThread(NULL, 0, freeze_watchdog_thread, NULL, 0, NULL);
#endif
    psx_debug_add_write_guard(0x800BDFA8u, 0x800BDFB0u);
    psx_debug_add_write_guard(0x800BE028u, 0x800BE030u);
    psx_debug_add_write_guard(0x800CFFCCu, 0x800CFFDCu);
}

/* <app>/dev/dump.request (any content) asks for a snapshot from outside the
 * game, e.g. while someone else is watching the log. Polled twice a second. */
static int dump_requested(void) {
    if (s_vblanks % 30u != 0u)
        return 0;
    char path[1200];
    snprintf(path, sizeof(path), "%s/dev/dump.request", dp_app_dir());
    if (remove(path) != 0)
        return 0;
    fprintf(stdout, "driver.personal: snapshot requested via dev/dump.request\n");
    return 1;
}

/* Freeze watchdog: libetc counts VBlank interrupts in the global VSync(-1)
 * returns (0x80095250). It keeps counting in menus, pauses and loading, and
 * stops when the game no longer handles interrupts (the Chicago freezes and
 * crashes). A background thread checks it twice a second, independent of the
 * emulation loop, and writes one "-hang" snapshot (no screen.png) once it has
 * been stuck for WATCHDOG_MS after having counted; it re-arms when it moves. */
#define VSYNC_COUNTER    0x80095250u
#define WATCHDOG_MS      3000u
#define WATCHDOG_POLL_MS 500u

#if defined(_WIN32)
static DWORD WINAPI freeze_watchdog_thread(LPVOID arg) {
    (void)arg;
    uint32_t last = 0, still_ms = 0, moves = 0;
    int fired = 0;
    for (;;) {
        Sleep(WATCHDOG_POLL_MS);
        if (!g_psx_ram || !psx_mod_game_started())
            continue;
        if (psx_rewind_is_open()) {   /* rewind browser pauses the game */
            still_ms = 0;
            continue;
        }
        uint32_t cur;
        memcpy(&cur, g_psx_ram + (VSYNC_COUNTER & 0x1FFFFFu), 4);
        if (cur != last) {
            last = cur;
            still_ms = 0;
            if (moves < 1000u) moves++;
            if (fired) {
                /* Q42 (23.10.): the counter also stands still while an FMV plays (Undercover's intro): a snapshot whose
                 * game recovered is a stall, not a hang -> "-hang" becomes "-stall" (real hangs keep "-hang") */
                char stall[1200];
                size_t n = strlen(s_last_dump_dir);
                if (n > 5 && strcmp(s_last_dump_dir + n - 5, "-hang") == 0 && n + 1 < sizeof(stall)) {
                    snprintf(stall, sizeof(stall), "%.*s-stall", (int)(n - 5), s_last_dump_dir);
                    if (MoveFileA(s_last_dump_dir, stall))
                        snprintf(s_last_dump_dir, sizeof(s_last_dump_dir), "%s", stall);
                }
                fprintf(stdout, "driver.personal: game VBlank counter moving again (snapshot kept as %s)\n", s_last_dump_dir);
                fired = 0;
            }
            continue;
        }
        if (moves < 4u || fired || (still_ms += WATCHDOG_POLL_MS) < WATCHDOG_MS)
            continue;
        fired = 1;
        moves = 0;
        fprintf(stdout, "driver.personal: game VBlank counter stuck for %u ms, writing a snapshot\n", WATCHDOG_MS);
        dev_dump("-hang", 0);
    }
    return 0;
}
#endif

/* ---- dev overlay + car flip ------------------------------------------- */

#define DRAWBUF_CUR   0x80097530u  /* -> current draw buffer; swaps once per game frame */
#define CUR_AREA      0x800972C0u
#define CUR_REGION    0x8009732Cu
#define AREA_LOADING  0x800969E8u
/* Player car (same layout as Driver 2's hd.where + RigidBodyState). */
#define PLAYER_MAT    0x8009B0A8u  /* 3x3 rotation, s16, 4096 = 1 */
#define PLAYER_POS    0x8009B0BCu  /* x, y, z (y up; street level = 0, car centre ~164) */
#define PLAYER_FPOS   0x8009B0C8u  /* rigid body position << 4 */
#define PLAYER_QUAT   0x8009B0D4u  /* orientation x, y, z, w (4096 = 1) */
#define PLAYER_LINVEL 0x8009B0E4u
#define PLAYER_ANGVEL 0x8009B0F0u
/* 0x80023428: while m[1][1] < 100 this counts game frames; at 181 the car's
 * damage (0x8009B220) is set to max + 100 = wrecked (game over). Upright
 * resets it to 0. */
#define UPSIDE_FRAMES 0x80096920u
#define UPSIDE_WRECK  181
/* Damage: six zone values (int, clamped to 0xFFF) at car+0x114 and the total
 * (u16, HUD bar; wrecked when >= max at 0x80096E7C) at car+0x17C. The game's
 * damage routine 0x8003FB98 adds to both; the Invincibility cheat path
 * 0x80025AC0 zeroes both every frame (= undamaged car), so a repair is the
 * same writes. */
#define PLAYER_ZONEDMG 0x8009B1B8u  /* car 0x8009B0A4 + 0x114, 6 words */
#define PLAYER_DAMAGE  0x8009B220u  /* car + 0x17C, u16 */
#define FLIP_LIFT     150          /* drop the car onto its wheels from this high */
#define FLIP_HOLD     3            /* vblanks the upright state is re-applied */
/* Chicago port: Driver 1 -> Driver 2 coordinates (chicago/worldscale.py). */
#define D2_SCALE      1.32
#define D2_OFFSET_X   157724
#define D2_OFFSET_Z   (-87099)

static int s_overlay_on = 1, s_overlay_key_was_down;
static int s_flip_key_was_down, s_flip_hold;
static int32_t s_flip_state[10];   /* fpos[3], quat[4], pos[3] */
static uint32_t s_fps_last_buf, s_fps_frames, s_fps_vblanks, s_fps, s_emu_pct;
/* FPS stats for test tools (C40, 13.10.): the overlay's own numbers in mod memory, so testers
 * read what the user sees. 8 words, allocated on the first frame (after the plugins' fixed
 * blocks: 0x9F082310 with the Chicago slot on; the address is logged): +0 magic "FPS1",
 * +4 FPS and +8 EMU % (the overlay's, updated once a second), +12 frames drawn and +16 VBlanks
 * since boot (running sums), +20 one-second updates so far. */
#define FPS_STATS_MAGIC 0x31535046u
static uint32_t s_stats_addr, s_tot_frames, s_tot_vblanks, s_stats_updates;
/* Stall ring for test tools (C45, 13.10.), right after the FPS block (+0x20 = 0x9F082330):
 * +0 magic "STL1", +4 stalls (in game: >= STALL_VBLANKS VBlanks between two game frames),
 * +8 longest gap (VBlanks), +12 stalls recorded (ring slot = (n - 1) % 8), +16 ring of 8 x 32 B:
 * gap, player x, z (when the frame came), area before, area after, region before, region after,
 * flags (1 = area loading flag 0x800969E8 set during the gap, 2 = spool sectors left 0x800971F8
 * > 0 during the gap, 4 = a spool / CD read was active at the gap's start). */
#define STALL_MAGIC     0x314C5453u
#define STALL_VBLANKS   6u
#define STALL_RING      8u
/* Plane-selection record for test tools (C17 deck snap, 14.10.), after the stall ring (+0x130 = 0x9F082440):
 * written by driver_chicago.c every VBlank via driver_personal_sel_debug: +0 magic "SEL1", +4 VBlank count,
 * then the 6 words the caller passes (see driver_chicago.c surface_select_vblank). */
#define SEL_MAGIC       0x314C4553u
#define SEL_OFFSET      (0x20u + 16u + 32u * STALL_RING)
#define STATS_BYTES     (SEL_OFFSET + 32u)
#define AREA_WORD       0x800972C0u
#define REGION_WORD     0x8009732Cu
#define LOADING_FLAG    0x800969E8u
#define SPOOL_LEFT      0x800971F8u
static uint32_t s_gap, s_gap_flags, s_last_area, s_last_region, s_stalls, s_longest;
static uint64_t s_fps_t0;

/* runtime (local change, main.cpp): L3 + face button (3 = Triangle) */
int psx_host_controller_l3_combo_held(int face);

static uint64_t now_ms(void) {
#if defined(_WIN32)
    return GetTickCount64();
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000u + (uint64_t)ts.tv_nsec / 1000000u;
#endif
}

/* Key held while one of our windows has focus. */
static int key_down(int vk) {
#if defined(_WIN32)
    HWND fg = GetForegroundWindow();
    DWORD pid = 0;
    if (!fg) return 0;
    GetWindowThreadProcessId(fg, &pid);
    if (pid != GetCurrentProcessId()) return 0;
    return (GetAsyncKeyState(vk) & 0x8000) != 0;
#else
    (void)vk;
    return 0;
#endif
}

static int32_t rd32(uint32_t a) { return (int32_t)psx_mod_read_word(a); }
static int16_t rd16(uint32_t a) { return (int16_t)psx_mod_read_half(a); }

/* <app>/dev/<name> (any content) triggers an action; polled twice a second. */
static int file_requested(const char* name) {
    if (s_vblanks % 30u != 0u)
        return 0;
    char path[1200];
    snprintf(path, sizeof(path), "%s/dev/%s", dp_app_dir(), name);
    if (remove(path) != 0)
        return 0;
    fprintf(stdout, "driver.personal: dev/%s found\n", name);
    return 1;
}

/* Reset all damage (zones + total), like the Invincibility cheat does. */
static void repair_car(void) {
    for (uint32_t i = 0; i < 6; i++)
        psx_mod_write_word(PLAYER_ZONEDMG + 4u * i, 0);
    psx_mod_write_half(PLAYER_DAMAGE, 0);
}

static void flip_apply(void) {
    const int32_t* st = s_flip_state;
    for (uint32_t i = 0; i < 3; i++) {
        psx_mod_write_word(PLAYER_FPOS + 4u * i, (uint32_t)st[i]);
        psx_mod_write_word(PLAYER_POS + 4u * i, (uint32_t)st[7 + i]);
        psx_mod_write_word(PLAYER_LINVEL + 4u * i, 0);
        psx_mod_write_word(PLAYER_ANGVEL + 4u * i, 0);
    }
    for (uint32_t i = 0; i < 4; i++)
        psx_mod_write_word(PLAYER_QUAT + 4u * i, (uint32_t)st[3 + i]);
    psx_mod_write_word(UPSIDE_FRAMES, 0);
    repair_car();
    /* Rotation matrix for the same yaw; the game rebuilds it from the
     * quaternion anyway, this only avoids one frame drawn upside down. */
    int32_t s = st[4], c = st[6];   /* sin/cos of half the heading */
    int16_t sn = (int16_t)((2 * s * c) >> 12), cs = (int16_t)((c * c - s * s) >> 12);
    const int16_t m[9] = { cs, 0, sn,  0, 4096, 0,  (int16_t)-sn, 0, cs };
    for (uint32_t i = 0; i < 9; i++)
        psx_mod_write_half(PLAYER_MAT + 2u * i, (uint16_t)m[i]);
}

/* Upright with the current heading, still, slightly above where it is. */
static void flip_car(void) {
    double qn = 0;
    for (uint32_t i = 0; i < 4; i++) {
        double q = rd32(PLAYER_QUAT + 4u * i);
        qn += q * q;
    }
    if (!psx_mod_game_started() || qn < 3000.0 * 3000.0 || qn > 5000.0 * 5000.0) {
        host_osd_push("DEV: no car to flip", 1500);
        return;
    }
    /* Heading as Driver 2 derives it: ratan2(m[0][2], m[2][2]). */
    double h = atan2((double)rd16(PLAYER_MAT + 4u), (double)rd16(PLAYER_MAT + 16u));
    int32_t* st = s_flip_state;
    for (uint32_t i = 0; i < 3; i++) {
        st[i] = rd32(PLAYER_FPOS + 4u * i);
        st[7 + i] = rd32(PLAYER_POS + 4u * i);
    }
    st[1] += FLIP_LIFT * 16;
    st[8] += FLIP_LIFT;
    st[3] = 0;
    st[4] = (int32_t)lround(sin(h / 2) * 4096.0);
    st[5] = 0;
    st[6] = (int32_t)lround(cos(h / 2) * 4096.0);
    s_flip_hold = FLIP_HOLD;
    fprintf(stdout, "driver.personal: car flipped upright + repaired at %d,%d,%d (m11 was %d, damage was %d)\n",
            st[7], st[8], st[9], rd16(PLAYER_MAT + 8u), (int)psx_mod_read_half(PLAYER_DAMAGE));
    host_osd_push("DEV: car flipped upright + repaired", 1500);
}

void driver_personal_sel_debug(const uint32_t w[6]) {
    if (!s_stats_addr)
        return;
    psx_mod_write_word(s_stats_addr + SEL_OFFSET, SEL_MAGIC);
    psx_mod_write_word(s_stats_addr + SEL_OFFSET + 4u, s_tot_vblanks);
    for (uint32_t i = 0; i < 6u; i++) psx_mod_write_word(s_stats_addr + SEL_OFFSET + 8u + 4u * i, w[i]);
}

/* C115: the overlay's emulation speed (VBlanks per wall second vs 59.94, updated once a second; 0 before the first
 * second) and how many one-second updates there were, for the overclock governor (driver_gameplay.c). */
uint32_t driver_personal_emu_pct(uint32_t* updates) {
    if (updates) *updates = s_stats_updates;
    return s_emu_pct;
}

void driver_personal_fps_tick(int caller) {
    static int owner = -1;
    if (owner < 0) owner = caller;
    if (caller != owner) return;
    uint32_t buf = psx_mod_read_word(DRAWBUF_CUR);
    int in_game = psx_mod_game_started();
    uint32_t loading = psx_mod_read_word(LOADING_FLAG), left = psx_mod_read_word(SPOOL_LEFT);
    if (buf != s_fps_last_buf) {
        s_fps_last_buf = buf;
        s_fps_frames++;
        s_tot_frames++;
        uint32_t area = psx_mod_read_word(AREA_WORD), region = psx_mod_read_word(REGION_WORD);
        if (in_game && s_gap >= STALL_VBLANKS && s_stats_addr && s_last_region != 0u) {   /* not boot / level load */
            uint32_t slot = s_stats_addr + 0x20u + 16u + 32u * (s_stalls % STALL_RING);
            const uint32_t rec[8] = { s_gap, psx_mod_read_word(PLAYER_POS), psx_mod_read_word(PLAYER_POS + 8u),
                                      s_last_area, area, s_last_region, region, s_gap_flags };
            for (int i = 0; i < 8; i++) psx_mod_write_word(slot + 4u * (uint32_t)i, rec[i]);
            s_stalls++;
            if (s_gap > s_longest) s_longest = s_gap;
        }
        s_gap = 0;
        s_gap_flags = (loading || (int32_t)left > 0) ? 4u : 0u;
        s_last_area = area;
        s_last_region = region;
    } else {
        s_gap++;
        if (loading) s_gap_flags |= 1u;
        if ((int32_t)left > 0) s_gap_flags |= 2u;
    }
    s_fps_vblanks++;
    s_tot_vblanks++;
    uint64_t t = now_ms();
    if (!s_fps_t0) s_fps_t0 = t;
    if (t - s_fps_t0 >= 1000u) {
        double sec = (double)(t - s_fps_t0) / 1000.0;
        s_fps = (uint32_t)(s_fps_frames / sec + 0.5);
        s_emu_pct = (uint32_t)(s_fps_vblanks / sec / 59.94 * 100.0 + 0.5);
        s_fps_frames = s_fps_vblanks = 0;
        s_fps_t0 = t;
        s_stats_updates++;
    }
    if (!s_stats_addr) {
        s_stats_addr = psx_mod_alloc_guest_memory(STATS_BYTES, 16u);
        fprintf(stdout, "driver.personal: FPS stats at 0x%08X\n", (unsigned)s_stats_addr);
    }
    if (s_stats_addr) {
        const uint32_t w[6] = { FPS_STATS_MAGIC, s_fps, s_emu_pct, s_tot_frames, s_tot_vblanks, s_stats_updates };
        for (int i = 0; i < 6; i++) psx_mod_write_word(s_stats_addr + 4u * (uint32_t)i, w[i]);
        const uint32_t h[4] = { STALL_MAGIC, s_stalls, s_longest, s_stalls };
        for (int i = 0; i < 4; i++) psx_mod_write_word(s_stats_addr + 0x20u + 4u * (uint32_t)i, h[i]);
    }
}

static void overlay_update(void) {
    driver_personal_fps_tick(0);
    if (!s_overlay_on)
        return;
    char text[256];
    int n = snprintf(text, sizeof(text), "FPS %u  EMU %u%%", s_fps, s_emu_pct);
    if (psx_mod_game_started()) {
        int32_t x = rd32(PLAYER_POS), y = rd32(PLAYER_POS + 4u), z = rd32(PLAYER_POS + 8u);
        int dir = (int)lround(atan2((double)rd16(PLAYER_MAT + 4u),
                                    (double)rd16(PLAYER_MAT + 16u)) * 180.0 / 3.14159265358979);
        if (dir < 0) dir += 360;
        char flipped[48] = "";
        int32_t upside = rd32(UPSIDE_FRAMES);
        if (upside > 0 && upside < UPSIDE_WRECK)
            snprintf(flipped, sizeof(flipped), "\nFLIPPED - wreck in %.1fs (L3+TRI/F5)",
                     (UPSIDE_WRECK - upside) / (double)(s_fps ? s_fps : 30));
        snprintf(text + n, sizeof(text) - (size_t)n,
                 "%s\nX %d  Y %d  Z %d\nD2 %d,%d  HDG %d\nAREA %d  REG %d%s",
                 rd32(AREA_LOADING) ? "  LOADING" : "",
                 x, y, z,
                 (int)lround((x - D2_OFFSET_X) / D2_SCALE),
                 (int)lround((z - D2_OFFSET_Z) / D2_SCALE),
                 dir, rd32(CUR_AREA), rd32(CUR_REGION), flipped);
    }
    host_osd_set_panel(text);
}

static void dev_mode_vblank(void) {
    s_vblanks++;
    int down = dump_key_down();
    if ((down && !s_dump_key_was_down) || dump_requested()) {
        if (s_dev_tools_on) dev_dump("", 1);
        else {
            fprintf(stdout, "driver.personal: snapshot skipped: Developer recording tools are off (Mods)\n");
            host_osd_push("Snapshot off: turn on Developer recording tools in Mods", 2500);
        }
    }
    s_dump_key_was_down = down;

    down = key_down(VK_F10);
    if (down && !s_overlay_key_was_down) {
        s_overlay_on = !s_overlay_on;
        if (!s_overlay_on)
            host_osd_set_panel(NULL);
    }
    s_overlay_key_was_down = down;

    down = psx_host_controller_l3_combo_held(3) || key_down(VK_F5);
    if ((down && !s_flip_key_was_down) || file_requested("flip.request"))
        flip_car();
    s_flip_key_was_down = down;
    if (s_flip_hold > 0) {
        s_flip_hold--;
        flip_apply();
    }
    overlay_update();
}

PSX_MOD_CONSTRUCTOR(driver_personal_register) {
    psx_mod_register_activation_plugin("driver.dev-tools", dev_tools_activate);
    psx_mod_register_activation_plugin("driver.dev-mode", dev_mode_activate);
    psx_mod_register_vblank_plugin("driver.dev-mode", dev_mode_vblank);
}
