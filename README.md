# driver.personal — local tools for Driver Recompiled

Personal, local-only additions to this install of
[driver-recomp](https://github.com/alexbeavs-ps1-ports/driver-recomp) v0.3.6
(Driver, USA v1.1, SLUS-00842). Not part of the upstream project; not for
publishing.

## Features (game launcher → Mods, package "Driver - Personal Tools")

| Feature | What it does |
|---|---|
| **Developer Mode** | Logs everything the runtime prints to `dev/logs/driver-<time>.log`. **F9** (game window focused) or **L3 + R3** (both stick buttons, any controller) saves a snapshot to `dev/dumps/<time>-v<vblank>/`: `ram.bin` (2 MB main RAM), `scratchpad.bin`, `regs.json`, `screen.png` (what you see), `screen_native.png` (raw PS1 frame), `heartbeat.json` (runtime state + recent-frame ring). Creating `dev/dump.request` triggers the same snapshot from outside the game. **Overlay** (top right, **F10** toggles): game FPS (frames the game actually draws), emulation speed, position X/Y/Z, Driver 2 coordinates (Chicago), heading, area/region, and a wreck countdown while the car is upside down. **L3 + Triangle** or **F5** (or `dev/flip.request`) puts the car back on its wheels, same heading, clears the game's upside-down counter (181 game frames upside down = wrecked) and **repairs the car** (all six damage zones and the total reset, like the Invincibility cheat does each frame; a car already declared wrecked stays wrecked). |
| **Unlock All** | Does what finishing the story does: all 8 cheats appear in the Cheats menu (Credits, Invincibility, Immunity, Rear Wheel, Minis, Stilts, Null, Antipodean) and all four cities can be chosen in Take a Ride / Driving Games. Undercover mission progress is untouched. Saving afterwards stores the cities on the memory card. |
| **Skip Intro** | Boots straight to the main menu: copyright/GT/Reflections screens cut to one frame (their fades remain) and the intro movie is not played. Story cutscenes still play. |

Mods take effect on the next game launch.

## Live debugging

The build keeps the runtime's TCP debug server (`127.0.0.1:4370`, local
only). While the game runs:

```
python driver_personal/driver_dbg.py frame
python driver_personal/driver_dbg.py read 0x800967E0 16
python driver_personal/driver_dbg.py watch 0x800967F8 4
python driver_personal/driver_dbg.py snapshot        # needs Developer Mode
```

All commands: `psxrecomp/TCP_COMMANDS.md`. The debug tools cost roughly 14%
of emulation headroom; the game still has plenty to spare. To drop them, remove
the `PSX_DEBUG_TOOLS` line from `CMakeLists.txt` and rebuild.

## Known addresses (USA v1.1)

The game addresses RAM through KUSEG; `$gp = 0x00096770`.

| Address | Meaning |
|---|---|
| `0x8008671C + i*0x38` | Cheat i button sequence (13 steps + `-1`); first word `-2` = unlocked |
| `0x800967D8` | Number of cheats (8) |
| `0x800967E0` | Cities unlocked (2 on a new game, 4 = all) |
| `0x800967F8` | Current Undercover mission (70–73 = final missions) |
| `0x800967C4` | Mission result flag (1 pass, -1 fail) — don't poke |
| `0x8009681C` / `0x80096820` | Invincibility / Immunity cheat toggles |
| `0x8009D8DC..` | Rear wheel, Minis, Stilts, Low gravity, Antipodean toggles |
| `0x8006D610` | `PlayMovie(id)` — runs `DRIVER/NFMV/NFMV.EXE` |
| `0x800245F0` | Boot sequence (copyright, logos, intro movie, FRONTEND.BIN) |

## Files

- `driver_personal.c` — Developer Mode plugin; `driver_gameplay.c` — Unlock All.
- `../mods/preloaded/packages/driver.personal/1.0.0/manifest.toml` — features;
  Skip Intro is declarative guarded patches there.
- `CMakeLists.upstream.txt` — the original root `CMakeLists.txt`.

## After updating driver-recomp

An update replaces `CMakeLists.txt` and `game.toml`. Re-apply:

1. In `CMakeLists.txt`: before `include(".../runtime.cmake")` add
   `set(PSX_DEBUG_TOOLS ON CACHE BOOL "TCP debug server + heartbeat" FORCE)`;
   add `driver_personal/driver_personal.c` and `driver_personal/driver_gameplay.c`
   to `CODEGEN_SETUP_SOURCES`; append the POST_BUILD step that copies
   `mods/preloaded/packages` into `$<TARGET_FILE_DIR:psx-runtime>/mods/packages`.
2. In `game.toml`: `disc = "disc/disc1.cue"`, and under `[recompiler]`:
   `mod_function_entry_funcs = ["0x80033B10"]` (C33 area-switch hook in `driver_chicago.c`;
   without it the hook is never called and area switches can freeze).
3. Rebuild (from this folder's parent):
   `python psxrecomp/psxrecomp_cli.py rebuild --project-root . --config game.toml --build-dir build-release --target psx-runtime --exe-basename Driver_Recompiled --disc disc/disc1.cue --no-pgo --prune-after build-intermediates`

### Chicago port changes (also re-apply after an update)

4. Runtime: copy the edited `psxrecomp/runtime/src/{iso_reader_c.cpp,mod_runtime.cpp,memory.c,boot_state.c,dma.c,debug_server.c,main.cpp,starvation_ring.c,host_osd.c,gpu_gl_renderer.c,gpu_vk_renderer.c}`
   and `runtime/include/{mod_runtime.h,boot_state.h,host_osd.h}` changes back (originals are in
   `runtime_patches/orig/`, full diff in `runtime_patches/chicago-runtime.diff`).
5. Patched executable: rebuild `disc/SLUS_008.42` from `disc/SLUS_008.42.orig` with
   `python driver_personal/chicago/exe_patches.py disc/SLUS_008.42.orig --apply disc/SLUS_008.42`
   (model table, cell buffer, primitive-buffer guard, area switch, render trap, spool guard), then run `generate` (with `--bios`)
   before `rebuild`.
6. Add `driver_personal/driver_chicago.c` to `CODEGEN_SETUP_SOURCES` and run
   `python driver_personal/chicago/build_package.py` to regenerate the driver.chicago package.

If a future version changes the game executable, the Skip Intro patches fail
their byte checks instead of patching the wrong code.

## Dev client and test tools (Chicago port)

- `build-dev` is the dev client the user plays (desktop shortcut "Driver (dev
  client)" or `Driver (dev client).bat`); `build-release` is the frozen release.
- `chicago/devtools/dt.py`: snapshot summaries, live inspection of a running
  game, parallel captures at known issue spots, soaks, disassembly. Test runs
  use copies in `<app>/devtest/` and never touch build-dev/build-release.
- Project knowledge: `chicago/NOTES.md`.
