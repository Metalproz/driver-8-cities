# C92 design: "Uncap GPU usage", a steady 30 FPS with identical visuals (Polish, 24.10., analysis only)

User (24.10.): an emulator setting so the game uses the PC's hardware instead of PS1 limits and reaches a constant 30 FPS;
visuals exactly the same; a toggle in Mods (driver.personal feature, state.toml) so it can be switched off to test real PS1
behaviour before the PS1 port (Milestone 8). Implementation: Infrastructure (runtime + plugin).

## 1. What caps the frame rate today (measured 24.10.)

Runner on devtest/polish, port 4470, build-test = build-dev exe 090235ed, specdmg2, S4 on. The level is STARTED at the
spot (not teleported), standing still for 6 s per heading. Columns:
- guest FPS = game frames per guest vblank x 59.94
- host speed = guest vblanks per wall second (test copies run unpaced, so this is the headroom)

| map / spot | vblanks per game frame | guest FPS | host speed |
|---|---|---|---|
| Chicago l_down_e (downtown, traffic), 4 headings | 2.95 / 3.27 / 3.36 / 3.41 | 20.3 / 18.3 / 17.8 / 17.6 | 270-290 % of real time |
| Miami (Take a Ride start) | 2.16 / 2.19 | 27.7 / 27.4 | 263-265 % |

- **The cap is guest time, not the host.** The PC emulates the PS1 2.6-2.9x faster than real time. The game itself spends
  more than 2 vblanks of emulated R3000A time per frame (Chicago ~1.7-1.9 M guest cycles vs the 1.13 M that fit into 2
  vblanks at 33.87 MHz).
- **The GPU is not the bottleneck.** The runtime does not emulate GPU rasterisation time: GPUSTAT is "ready" at once, and
  only the OT DMA is timed at 1 cycle per word (dma.c DMA_GPU_CYCLES_PER_WORD) + 8 / 5 header / setup cycles
  (dma_gpu_ll.c). Host rendering (OpenGL, SS2) has the same 2.7x headroom.
- **The game's own loop** (FUN_8002360C, main game loop):
  - waits `while (VSync(-1) - last < 2)`, so 30 FPS is the hard maximum
  - then DrawSync(0)
  - runs ONE game step per frame: FUN_800230B0 -> GlobalTimeStep 0x8001BAC0 once, frame_counter 0x800970D8 + 1
  - **Physics advances per game frame, not per vblank.** A 3-vblank frame is a slower game: downtown Chicago runs at
    ~60 % speed today, exactly like heavy scenes on a real PS1.
- **Host pacing:** frame_pacing.c paces guest vblanks to 59.94 Hz wall time (bounded catch-up). Not a limit.

So "uncapped" means one thing for Driver: **give the guest CPU more cycles per vblank** (an emulated overclock), so every
frame's work fits into 2 vblanks. Then the game's own 30 FPS limiter holds the rate steady.

## 2. Lever: guest CPU overclock (runtime)

- **Mechanism:** scale every CPU cycle charge by a Q16 factor (charge x 1/f, with an exact remainder accumulator) before it
  reaches psx_cycle_count. Devices keep their real schedules on psx_cycle_count:
  - vblank / CRTC 59.94 Hz
  - root counters
  - CD-ROM sector timing
  - SPU sample clock
  - DMA
  So more instructions run between two vblanks, while everything time-based stays real-time.
- **Upstream already has this:** docs/UPSTREAM_2026-08-20.md describes the WipEout worktree's `cpu_overclock` (Q16
  remainder in psx_cyc.h / psx_cycles.c fast-charge and fused-load paths; "cpu_overclock = 900"). This checkout
  (runtime/src/psx_cycles.c) does NOT have it, so Infrastructure ports it, including its oracle tests
  (test_psx_cyc_batch.c 2 overclock modes).
- **Factor:**
  - Chicago's worst measured frame needs ~1.7x.
  - Proposal: 200 % by default (worst frame then ~0.96 M cycles < 1.13 M), option 150-400 %.
  - Host cost: ~2x the CPU emulation work per real vblank. This PC has 2.7-2.9x headroom, so ~140 % stays.
- **Toggle:**
  - driver.personal feature `uncap-gpu` (label "Uncap GPU usage (steady 30 FPS)") with option `cpu_percent` (default 200)
  - the plugin activation calls a new runtime API `psx_mod_set_cpu_overclock(percent)`
  - 100 / off = today's exact timing (the reference for Milestone 8)
  - Name kept as the user said it, with a tooltip: "runs the emulated CPU faster so frames never slow down; visuals unchanged".

## 3. What it must NOT change (and why it doesn't)

- **Pixels per frame:** identical. The same game code draws the same primitives; the GPU backend is untouched (no
  interpolation, no frame generation, no resolution / PGXP / render change).
- **Game speed per frame:** identical (one physics step per frame). Wall-clock speed changes only where today's frames
  take > 2 vblanks: those scenes now run at Driver's designed 30-FPS speed instead of slowing down (a real PS1 slows down
  there; that is what switching it off reproduces).
- **Audio:** SPU stays on the guest-time clock at real-time vblanks: pitch and tempo unchanged. CD streaming (music / XA)
  unchanged.
- **Vblank rate:** stays 59.94. Do NOT use crtc_refresh_multiplier; that speeds up the whole game.
- **Saves / memory card / replays:**
  - Replays record pad input per game frame (ControlReplay), so a replay plays the same frames with the setting on or off.
  - Exception to check: anything seeded from the vblank counter can differ: FUN_80022818 picks a spawn with
    `VSync(-1) % 15`, and FUN_8004FFE8 is the RNG. Check: record with the setting on, play with it off (Miami +
    Chicago), compare car positions.

## 4. Risks and checks

- **Area streaming:** at a steady 30 FPS the car covers more ground per real second downtown, while CD reads stay at
  real speed.
  - Re-run the C45 route test (switches, stalls, FPS) and the C81 / out_of_tape tests with the setting on.
  - If stalls rise, pair it with the framework's builtin cd-speed mod (psx.enhancement.cd-speed, divisor 2), not
    "instant": MMX6-type VSync-callback hazard (ENHANCEMENTS L1).
- **Busy-wait loops** (VSync / DrawSync / CD polls) burn more host time per vblank. Fine on host, watch for "-stall"
  watchdog false positives.
- **Timing-sensitive code:**
  - the C38 / C50 / C81 hang family (CD DMA landing on buffers)
  - FMV (MDEC) pacing (CD-driven, should be unaffected)
  - Interview / Undercover intro
  - Run the runner tests (bus_head_on, camera_chicago, out_of_tape, undercover_interview, special_zones) on both settings.
- **PS1 port (M8):** host-only by nature. The PS1 path is the existing C40 work (render cost per frame); the toggle off is
  the PS1 reference.

## 5. Order (Infrastructure)

1. Port the Q16 overclock from the upstream worktree + its oracle tests, then a no-op check: factor 100 gives the same
   cycle digest.
2. Add the runtime API + the driver.personal feature `uncap-gpu`.
3. Measure with c92_measure (scratch script, same method as above): target vblanks per game frame = 2.00 at l_down_e /
   fps_drop_2 / Miami.
4. Run the regression tests with the setting on and off, plus the replay on/off check.
5. Probe "uncap" for the user.
