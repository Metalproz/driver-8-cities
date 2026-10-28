# runner: scripted game tests (Q42)

`cd driver_personal/chicago/devtools; python -m runner list | run NAME... [--port 4468] [--copy runner] [--build build-test] [--reuse]`
Results: `devtest/_out/runner/<time>-<test>/` (steps.jsonl, result.json, report.html, PNG, WAV, game.log).
MCP: `python runner/mcp_server.py` (stdio). Test copies only (devtest/<copy>, own port, PID kill); never build-dev.

## Start at a spot vs. pose (teleport)

- **Start at a spot** = the level STARTS there: the package's start position (`dt.prepare(name, d2_start, lev)` /
  `CHI_START=x,z`, D2 coordinates). The game loads that place like any level start (all regions, textures, models).
  Use this for visual / FPS / "what the player sees after loading" checks.
- **Pose** = a TELEPORT inside a running level (`Session.pose`, MCP `pose`; plugin CHI_TEST_POSE, Chicago / LA only).
  It holds the car at x, z until `wait_world()` sees the world loaded and drawn: no area load running, the region word
  unchanged and no CD sector read for 1.5 s; otherwise it FAILS (StepFailed). Then it releases the car; if the car drops
  or rises by more than 200 (the pose y was not the ground's) it is posed again at the landed height and repaired.
- Areas: Driver 1 switches the texture / model AREA only when the car crosses a border region's edge, so a teleport can
  land in a region whose area is not loaded (grey / white ground). `ensure_area()` (part of pose) reads the region's
  area from the spool info: a plain region is reloaded (old_region = -1, the level-start path), a border region whose
  areas do not include the loaded one FAILS ("start at the spot instead").
- Before 23.10. (fix after Polish's C40 report) `pose` only waited for the area-load flag, which is still 0 right after a
  teleport: screenshots, FPS and ground-height results right after a long pose could come from an undrawn world.

## Rules for checks
- Visual / FPS numbers: start at the spot (`Session(start=(d2x, d2z))`), or pose + `wait_world` (never right after a pose without it).
- Collisions with moving AI cars vary per run (aim): judge medians over several rams (bus_head_on: 4).
