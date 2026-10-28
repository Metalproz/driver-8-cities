/* driver_gameplay.c — "unlock-all" for Driver (USA v1.1,
 * SLUS-00842). Addresses come from the retail executable; the game addresses
 * them through KUSEG (lui 0x0009 / $gp = 0x00096770).
 *
 * unlock-all mirrors what the game itself does when the Undercover story is
 * finished (frontend code at 0x80024E7C): every entry of the cheat-code table
 * gets -2 in its first slot, which is the game's own "cheat unlocked" marker.
 * The Undercover script raises the unlocked-city count with max(cities, n)
 * (0x8006EC04); we raise it to all four. Mission progress (0x800967F8) is not
 * touched, so Undercover saves keep their real position.
 *
 * skip-intro is declarative (main_exe patches in the package manifest). */

#include "driver_personal.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "mod_plugins.h"
#include "cpu_state.h"

/* ---- unlock-all -------------------------------------------------------- */

#define CHEAT_TABLE      0x0008671Cu  /* 13 L/R-button steps + terminator each */
#define CHEAT_STRIDE     0x38u
#define CHEAT_COUNT      0x000967D8u  /* $gp+0x68, 8 on retail */
#define CHEAT_MAX        8u
#define CHEAT_UNLOCKED   0xFFFFFFFEu  /* -2 */
#define CITIES_UNLOCKED  0x000967E0u  /* $gp+0x70, 2 on a new game */
#define CITIES_ALL       4u

static void unlock_all_vblank(void) {
    if (!psx_mod_game_started())
        return;
    uint32_t n = psx_mod_read_word(CHEAT_COUNT);
    if (n > CHEAT_MAX)
        n = CHEAT_MAX;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t slot = CHEAT_TABLE + i * CHEAT_STRIDE;
        uint32_t v = psx_mod_read_word(slot);           /* -3 = a row the Cheats screen pages hide (driver.chicago) */
        if (v != CHEAT_UNLOCKED && v != 0xFFFFFFFDu)
            psx_mod_write_word(slot, CHEAT_UNLOCKED);
    }
    if ((int32_t)psx_mod_read_word(CITIES_UNLOCKED) < (int32_t)CITIES_ALL)
        psx_mod_write_word(CITIES_UNLOCKED, CITIES_ALL);
}

/* ---- uncap-gpu (C92) ---------------------------------------------------- */
/* "Uncap GPU usage": the emulated CPU runs at cpu_percent % (option, default 200) of the PS1's speed, so Driver's own
 * 30 FPS limiter holds where heavy scenes (Chicago downtown) needed 3 vblanks per frame. Vblank, timers, CD and SPU
 * stay real-time, the GPU output per frame is unchanged. Off = exact PS1 timing (the Milestone 8 reference). */
static int s_uncap_pct, s_xd_pct;        /* overclock wanted by Uncap (its option) and by Extra draw distance (400) */
/* C100 (cheats 5: main menu under 100 % EMU at a 60 FPS cap, slow loading screens): only the in-level main loop has the
 * frame-wait skip; the frontend, loading screens, FMVs and the pause menu spin in their own waits, which an overclocked
 * CPU made 2-4x as expensive on the host. The overclock is now on only while the game's frame counter 0x800970D8
 * advances (driving / replays), 100 % (exact timing) elsewhere. */
static int s_oc_cur = 100;
static int s_oc_cap = 400;            /* C115 host guard ceiling (overclock_guard) */
/* C111 (user 26.10.): Extra draw distance raises the CPU speed only as far as its frames need: s_xd_pct moves between
 * 200 and 400 % from the frame-wait hook's verdicts (uncap_wait_entry: a frame that reaches its VSync wait before
 * 2 vblanks have passed had slack; one that arrives later missed its 30 FPS budget). Late frames in a 30-frame window:
 * +50 %; 120 frames in a row with slack: -25 %. */
static uint32_t s_xd_late, s_xd_frames, s_xd_slack_run;
static void xd_adapt(int late) {
    if (!s_xd_pct) return;
    s_xd_frames++;
    if (late) { s_xd_late++; s_xd_slack_run = 0; } else s_xd_slack_run++;
    if (s_xd_frames >= 30u) {
        if (s_xd_late && s_xd_pct < s_oc_cap) s_xd_pct = s_xd_pct + 50 > 400 ? 400 : s_xd_pct + 50;
        s_xd_frames = s_xd_late = 0;
    }
    if (s_xd_slack_run >= 120u && s_xd_pct > 200) { s_xd_pct -= 25; s_xd_slack_run = 0; }
}
/* C115 (cheats 9 user: Chicago music much slower after Hell -> a Driver 1 map -> exit -> Chicago): (1) the adaptive
 * Extra-draw speed carried the last level's 400 % into the next one; it starts again at 200 % when the game's frame
 * counter goes back (a new level, a restart, a rewind). (2) Host guard: whatever Uncap / Extra draw want, an overclock
 * the host cannot run in real time slows the whole emulation (music, engine sounds, timers). When the overlay's
 * emulation speed (driver_personal.c, once a second) reads below 97 % while overclocked, the ceiling drops 50 points
 * (down to 100 = exact PS1 speed); 10 s at >= 99 % raise it 25 again (up to 400). */
extern uint32_t driver_personal_emu_pct(uint32_t* updates);
/* C119 (probe havana 1, laptop: the guard walked 300 -> 100 % and then flapped 100 <-> 125 %). Lab finding: with the
 * frame-wait skip a lower CPU speed only saves host time once the guest drops from 30 to 20 FPS (3 vblanks per frame),
 * so one 50-point step usually changes nothing; on a host that is short anyway the old rule gave away 30 FPS for a few
 * points of speed. Rule now: (a) only seconds spent in a level count (menus / loading / pause run at 100 % and always
 * read full speed, which used to re-raise the ceiling); (b) emulation < 97 % while overclocked = probe: 3 in-level
 * seconds at 100 %; full speed there = the overclock was the cause, the ceiling stays at 100 and climbs again in 25 %
 * steps; still short at 100 % = the host is short anyway: the ceiling goes back unless 100 % gained >= CHI_OC_GAIN
 * points (default 10; speed then wins over FPS); after keeping the overclock the guard holds 60 s; (c) each kept cut
 * doubles the full-speed seconds needed before the next raise (10 .. 320 s), so a borderline host settles instead of
 * flapping; (d) a host short even at 100 % is logged once; (e) no verdicts in the first 8 in-level seconds (level start
 * / after a pause: spooling reads low; the user log cut 300 -> 150 % within seconds of the level start).
 * CHI_OC_GUARD=1 = the C115 rule. */
static int s_guard_v1 = -1, s_guard_gain = 10;
static void overclock_guard(int menu) {
    static uint32_t last_upd, good, menu_seen, hold, probe, vn, need = 10u, short_logged, warm;
    static int prev_cur, prev_emu, vsum, r[3];
    static uint32_t nr;
    uint32_t upd, emu = driver_personal_emu_pct(&upd);
    if (s_guard_v1 < 0) {
        const char* e = getenv("CHI_OC_GUARD"); s_guard_v1 = e && e[0] == '1';
        e = getenv("CHI_OC_GAIN"); if (e) s_guard_gain = atoi(e);
    }
    if (menu) menu_seen = 1;
    if (upd == last_upd || !emu) return;
    last_upd = upd;
    if (s_guard_v1) {                                     /* C115 rule */
        if (emu < 97u && s_oc_cur > 100) {
            int c = s_oc_cur - 50; s_oc_cap = c < 100 ? 100 : c; good = 0;
            fprintf(stdout, "driver.personal: emulation %u %% at CPU %d %%: CPU ceiling now %d %%\n", (unsigned)emu, s_oc_cur, s_oc_cap);
        } else if (emu >= 99u && s_oc_cap < 400 && ++good >= 10u) {
            s_oc_cap = s_oc_cap + 25 > 400 ? 400 : s_oc_cap + 25; good = 0;
        }
        return;
    }
    if (menu_seen) { menu_seen = 0; warm = 0; nr = 0; return; }   /* (a) a second with menu / loading / pause: no verdict */
    if (warm < 8u) { warm++; return; }                    /* (e) first 8 s in a level: spooling, no verdict */
    if (!probe) { r[nr % 3u] = (int)emu; nr++; }          /* last 3 in-level seconds at this speed */
    int avg3 = nr >= 3u ? (r[0] + r[1] + r[2]) / 3 : 100;
    if (hold) hold--;
    if (probe) {                                          /* (b) 3 s at 100 % */
        vsum += (int)emu;
        if (++vn < 3u) return;
        probe = 0;
        int avg = vsum / 3;
        if (avg >= 97 || avg - prev_emu >= s_guard_gain) {
            need = need * 2u > 320u ? 320u : need * 2u;   /* (c) */
            fprintf(stdout, "driver.personal: emulation %d %% at CPU 100 %% (%d %% at %d %%): CPU ceiling 100 %%, raise after %u s at full speed\n",
                    avg, prev_emu, prev_cur, (unsigned)need);
        } else {
            s_oc_cap = prev_cur; hold = 60u; nr = 0;
            fprintf(stdout, "driver.personal: emulation %d %% at CPU 100 %% (%d %% at %d %%): host short anyway, CPU ceiling back to %d %%\n",
                    avg, prev_emu, prev_cur, s_oc_cap);
        }
        good = 0;
        return;
    }
    if (emu < 97u) {
        good = 0;
        if (s_oc_cur > 100 && !hold && avg3 < 97) {      /* 3-second average, not one dip */
            prev_cur = s_oc_cur; prev_emu = avg3; vsum = 0; vn = 0; probe = 1; s_oc_cap = 100; nr = 0;
            fprintf(stdout, "driver.personal: emulation %d %% at CPU %d %%: probing 100 %%\n", avg3, s_oc_cur);
        } else if (s_oc_cur <= 100 && !short_logged) {   /* (d) */
            short_logged = 1;
            fprintf(stdout, "driver.personal: emulation %u %% at CPU 100 %% (no overclock): the host is short of full speed\n", (unsigned)emu);
        }
    } else if (emu >= 99u && s_oc_cap < 400 && ++good >= need) {
        s_oc_cap = s_oc_cap + 25 > 400 ? 400 : s_oc_cap + 25; good = 0;
    }
}
static void overclock_apply(void) {
    int pct = s_uncap_pct > s_xd_pct ? s_uncap_pct : s_xd_pct;
    static uint32_t last_fc, last_move;
    static uint32_t vb;
    vb++;
    uint32_t fc = psx_mod_read_word(0x800970D8u);
    if (fc < last_fc && s_xd_pct) {                       /* C115 (1): a new level starts at 200 % again */
        if (s_xd_pct != 200) fprintf(stdout, "driver.personal: new level: Extra draw CPU %d -> 200 %%\n", s_xd_pct);
        s_xd_pct = 200; s_xd_frames = s_xd_late = s_xd_slack_run = 0;
    }
    if (fc != last_fc) { last_fc = fc; last_move = vb; }
    overclock_guard(vb - last_move > 8u);
    if (pct > s_oc_cap) pct = s_oc_cap;
    if (vb - last_move > 8u) pct = 100;                   /* no game frame for 8 vblanks: menu / loading / pause / FMV */
    if (pct < 100) pct = 100;
    if (pct != s_oc_cur) { s_oc_cur = pct; psx_mod_set_cpu_overclock((uint32_t)pct); }
}
static void uncap_gpu_activate(void) {
    char v[16];
    int pct = 200;
    if (psx_mod_option_value(DP_PACKAGE_ID, "uncap-gpu", "cpu_percent", v, sizeof(v)))
        pct = atoi(v);
    if (pct < 100) pct = 100;
    if (pct > 400) pct = 400;
    s_uncap_pct = pct;
}
static void uncap_gpu_vblank(void) { overclock_apply(); }
/* Extra draw distance (C94) needs ~2x guest CPU in dense views (NY start 19.8 FPS at 200 %, 30 at 400 %): while it is on
 * the CPU runs at 400 % (Uncap is implied; the frame-wait skip below keeps light frames as cheap as before). */
static void extra_draw_activate(void) {
    s_xd_pct = 200;                                       /* C111: adaptive 200..400 % (xd_adapt) */
}

/* Frame-wait skip (C92, user 67): Driver's main loop (FUN_8002360C, 0x80024254) polls VSync(-1) until two vblanks
 * have passed since the last frame (0x80096924). With the overclock on that spin costs twice the host time per
 * vblank; when VSync(-1) is called from there and the frame still has to wait, guest time jumps to the next vblank
 * (the guest would only have spun until then). Off = exact timing (the runtime does nothing without the overclock). */
static void uncap_wait_entry(struct CPUState* cpu, uint32_t address) {
    (void)address;
    if (cpu->gpr[4] != 0xFFFFFFFFu || cpu->gpr[31] != 0x8002425Cu) return;
    static uint32_t last_frame_vb;                       /* C111: one verdict per game frame (the wait loops) */
    uint32_t start = psx_mod_read_word(0x80096924u);
    int late = psx_mod_read_word(0x80095250u) - start >= 2u;
    if (start != last_frame_vb) { last_frame_vb = start; xd_adapt(late); }
    if (late) return;
    psx_mod_skip_to_next_vblank();
}

/* ---- extra-draw (C94) ---------------------------------------------------- */
/* "Extra draw distance": the map is drawn 1.5x further (cell window 19 -> 27, radius 9 -> 13), ground-tile bands
 * 7000 / 9000 -> 10500 / 13500, cars keep their full model 1.5x further. The exe (exe_patches c94) reads its window,
 * PVS buffer, object list, tile bands and primitive-buffer limits from zero-block words (image data = Driver 1); this
 * plugin writes the 1.5x set every vblank (the exe image is loaded after a launch-time activation would run), with
 * the 27 x 27 PVS buffer (ring = 1: no PVS data beyond radius 9), a 4096-entry object list and two 320 KB primitive
 * buffers in host memory (GPU-DMA addressable). Host-only (M8 list): the PS1 has neither the RAM nor the GPU time. */
#define XW_ADDR(o) (0x80093380u + (o))
/* C96: two 0x50000 primitive buffers in the GPU-DMA aperture (KUSEG form like 0x000D8600: Driver ORs len << 24 into the
 * pointer), shared by Extra draw distance and Nightmare (driver_chicago.c). Host-only (M8 list). */
int dp_big_prim_buffers(uint32_t* pb0, uint32_t* pb1) {
    static uint32_t b0, b1;
    static int tried;
    if (!tried) {
        tried = 1;
        b0 = psx_mod_alloc_gpu_dma_memory(0x50000u, 16u) & 0x00FFFFFFu;
        b1 = psx_mod_alloc_gpu_dma_memory(0x50000u, 16u) & 0x00FFFFFFu;
        if (!b0 || !b1) b0 = b1 = 0;
    }
    if (pb0) *pb0 = b0;
    if (pb1) *pb1 = b1;
    return b0 && b1;
}
/* the buffers the level really draws into (set only at level setup 0x800515BC from XPB0 / XPB1): the limit words must
 * match them, never the requested ones (a level set up with Driver 1's buffers keeps them until the next setup) */
int dp_big_prim_buffers_active(void) {
    return (psx_mod_read_word(0x800BDFACu) & 0x00FFFFFFu) >= 0x00F00000u &&
           (psx_mod_read_word(0x800BE02Cu) & 0x00FFFFFFu) >= 0x00F00000u;
}
static uint32_t s_xd_pvs, s_xd_list, s_xd_pb0, s_xd_pb1;
static void extra_draw_vblank(void) {
    if (!s_uncap_pct) overclock_apply();                  /* Uncap's own vblank does it when that feature is on */
    if (!s_xd_pvs) {
        s_xd_pvs = psx_mod_alloc_guest_memory(27u * 27u + 3u, 16u);
        s_xd_list = psx_mod_alloc_guest_memory(4096u * 4u, 16u);
        dp_big_prim_buffers(&s_xd_pb0, &s_xd_pb1);
        if (!s_xd_pvs || !s_xd_list || !s_xd_pb0 || !s_xd_pb1) { s_xd_pvs = 0xFFFFFFFFu; return; }
        for (uint32_t i = 0; i < 27u * 27u; i++) psx_mod_write_byte(s_xd_pvs + i, 1u);
    }
    if (s_xd_pvs == 0xFFFFFFFFu) return;                  /* no memory: Driver 1 values stay */
    static const uint32_t off[15] = { 0x70, 0x74, 0x78, 0x7C, 0x80, 0x84, 0x88, 0x8C, 0x90, 0x94, 0x98, 0x9C, 0xA0, 0xA4, 0xA8 };
    int big = dp_big_prim_buffers_active();               /* limits follow the buffers in use (C96) */
    uint32_t val[15] = { s_xd_pvs, 27u, 27u, 6u, 26u, 13u, 1u, s_xd_list, 10500u, 13500u,
                         big ? 0x50000u - 0x7800u : 0x16800u, big ? 0x28800u : 0x12000u, s_xd_pb0, s_xd_pb1,
                         big ? (uint32_t)-0x50000 : (uint32_t)-0x1E000 };   /* ... XPB0 XPB1 XPBN */
    static int parts = -1;                               /* test aid CHI_XD_PARTS: 1 window, 2 list, 4 tile bands, 8 buffers, 16 car LOD, 32 limits */
    if (parts < 0) { const char* e = getenv("CHI_XD_PARTS"); parts = e ? atoi(e) : 63; }
    static const uint32_t d1[15] = { 0x000A80C4u, 19u, 19u, 4u, 18u, 9u, 1u, 0x000A76ACu, 7000u, 9000u,
                                     0x16800u, 0x12000u, 0x000D8600u, 0x000F6600u, (uint32_t)-0x1E000 };   /* XDD stays 1: owner flag */
    static const int part_of[15] = { 1, 1, 1, 1, 1, 1, 0, 2, 4, 4, 32, 32, 8, 8, 0 };
    for (int i = 0; i < 15; i++) if (part_of[i] && !(parts & part_of[i])) val[i] = d1[i];
    if (!(parts & 1)) val[6] = 1u;
    for (int i = 0; i < 15; i++)
        if (psx_mod_read_word(XW_ADDR(off[i])) != val[i]) psx_mod_write_word(XW_ADDR(off[i]), val[i]);
    /* car LOD: the camera setup writes 0x80096A48 (10000 + zoom); scale each new value by 1.5 */
    static uint32_t last;
    uint32_t v = psx_mod_read_word(0x80096A48u);
    /* not with Nightmare on (user R60: its crowd of near cars must keep full models; the extra far full models cost the
     * primitive budget first) */
    if ((parts & 16) && psx_mod_game_started() && !psx_mod_read_word(0x800933C8u) && !psx_mod_read_word(0x8009342Cu) && v != last && v >= 1000u && v <= 100000u) {
        last = v * 3u / 2u;
        psx_mod_write_word(0x80096A48u, last);
    }
}

PSX_MOD_CONSTRUCTOR(driver_gameplay_register) {
    psx_mod_register_vblank_plugin("driver.extra-draw", extra_draw_vblank);
    psx_mod_register_activation_plugin("driver.extra-draw", extra_draw_activate);
    psx_mod_register_function_entry_plugin("driver.uncap-gpu", 0x80079B00u, uncap_wait_entry);
    psx_mod_register_vblank_plugin("driver.unlock-all", unlock_all_vblank);
    psx_mod_register_activation_plugin("driver.uncap-gpu", uncap_gpu_activate);
    psx_mod_register_vblank_plugin("driver.uncap-gpu", uncap_gpu_vblank);
}
