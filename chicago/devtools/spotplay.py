"""spotplay.py - play Chicago starting at an issue spot, in a normal game window.

    python spotplay.py             list spots, ask which one
    python spotplay.py C4          spot of ROADMAP issue C4 (first spot in its row)
    python spotplay.py blackroofs  spot by name (devtools/spots.json)
    python spotplay.py rampsink --lev work/var_surf.lev   a test level instead of build-dev's
    python spotplay.py rampsink --auto     drive the menus all the way into the game (old behaviour)

Makes devtest/play_<spot>: a copy of build-dev (same exe, same installed Chicago
level, your input/keybind settings) whose package starts Take a Ride at the spot.
Own memory cards and debug port 4377; F9 snapshots land in the shared <app>/dev/dumps; so build-dev and your saves are never touched.
By default the menus are driven only to the Take a Ride city select (user, 2026-10-11:
"load into the map select as fast as possible, I do the rest"); Chicago is in LA's slot.
"""
from __future__ import annotations

import os, re, shutil, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("CHI_TEST_BUILD", "build-dev")   # the user's spot launcher mirrors build-dev (dt defaults to build-test)
import dt  # noqa: E402

FAST_FORWARD = "5"         # PSX_FAST_FORWARD_SPEED for the copies (hold Tab = 500 %)

PORT = 4377
SETTINGS = ["input.ini", "keybinds.ini", "settings.toml", "game_options.toml"]
ROADMAP = dt.APP / "driver_personal" / "ROADMAP.md"


def resolve(arg, sp):
    if arg in sp:
        return arg
    m = re.fullmatch(r"[Cc](\d+)", arg)
    if m and ROADMAP.exists():
        for line in ROADMAP.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.split("|")]
            if len(cells) > 4 and cells[1] == "C" + m.group(1):
                for w in re.findall(r"[A-Za-z_0-9]+", cells[3]):
                    if w in sp:
                        return w
                raise SystemExit("C%s has no spot in ROADMAP.md (spot column: %s)" % (m.group(1), cells[3]))
    raise SystemExit("unknown spot: %s" % arg)


def main():
    sp = dt.spots()
    argv = sys.argv[1:]
    auto = "--auto" in argv
    argv = [a for a in argv if a != "--auto"]
    lev_override = None
    if "--lev" in argv:                       # a test level (path, relative to chicago/ allowed)
        i = argv.index("--lev")
        lev_override = Path(argv[i + 1])
        if not lev_override.is_absolute():
            lev_override = dt.CHI / lev_override
        del argv[i:i + 2]
        if not lev_override.exists():
            raise SystemExit("no such level: %s" % lev_override)
    arg = argv[0] if argv else None
    if not arg:
        for k, v in sp.items():
            print("  %-13s %s" % (k, v.get("note", "")[:90]))
        arg = input("spot name or C-number: ").strip()
    name = resolve(arg, sp)
    start = sp[name]["d2"]
    dev = dt.APP / dt.BUILD
    lev = lev_override or dev / "mods" / "packages" / "driver.chicago" / "0.1.0" / "assets" / "chicago.lev"
    print("preparing %s (D2 %d, %d) from %s, level %s ..." % (name, start[0], start[1], dt.BUILD, lev))
    # a probe on another build (probes.json "build") gets its own copy: prepare() only
    # replaces an exe that is older or differs in size, so a shared copy could keep it
    copy = "play_" + name + ("" if dt.BUILD == "build-dev" else "_" + dt.BUILD.replace("build-", ""))
    d = dt.prepare(copy, start=start, lev=lev if lev.exists() else None)
    for f in SETTINGS:
        if (dev / f).exists():
            shutil.copy2(dev / f, d / f)
    dt.write_state(d, dt.FEATURES + [("driver.personal", "dev-mode")])
    link = d / "dev"                          # snapshots/logs go to the shared <app>/dev
    if not link.exists():
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "New-Item -ItemType Junction -Path '%s' -Target '%s' | Out-Null" % (link, dt.APP / "dev")],
                       check=True)
    log = open(d / "run.log", "w")
    import os
    env = dict(os.environ)
    env.setdefault("PSX_FAST_FORWARD_SPEED", FAST_FORWARD)   # hold Tab: 5x (user, menus / loading)
    subprocess.Popen([str(d / "Driver_Recompiled.exe"), "--no-launcher",
                      "--memcard-dir", str(d / "cards"), "--debug-port", str(PORT)],
                     cwd=d, stdout=log, stderr=subprocess.STDOUT, env=env,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    print("game window starting; going to the Take a Ride city select (don't press anything for ~15 s) ..."
          if not auto else "game window starting; driving the menus to Take a Ride (don't press anything for ~1 min) ...")
    time.sleep(4)
    g = dt.Dbg(port=PORT)
    for _ in range(60):
        try:
            g.frame(); break
        except Exception:
            time.sleep(1)
    if not auto:
        while (g.frame() or 0) < 2300:           # main menu ready
            time.sleep(0.1)
        for b in ["right"] * 5 + ["cross"]:      # Take a Ride -> city select
            g.press(b, hold=0.1, gap=0.35)
        print("ready: Take a Ride city select. Pick Los Angeles (= Chicago); you start at %s." % name)
        return
    dt.to_take_a_ride(g)
    try:
        x, _, z = g.pos()
        dx, dz = dt.d2_of(x, z)
        print("ready: car at D2 %d, %d (%d units from the spot). Have fun; close the window when done."
              % (dx, dz, ((dx - start[0]) ** 2 + (dz - start[1]) ** 2) ** 0.5))
    except Exception as e:
        print("ready (position check failed: %s)" % e)


if __name__ == "__main__":
    main()
