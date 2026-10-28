"""C92: host speed (EMU % = guest vblanks per wall second / 59.94; test copies run unpaced, so this is the headroom)
and guest FPS, standing 10 s. CITY=chicago starts at SPOT (default fps_drop_2), CITY=miami at the Take a Ride start.
RUNNER_UNCAP sets the overclock; IDLE=1 sets PSX_IDLE_SKIP=1."""
import json, os, time
from pathlib import Path
CITY = os.environ.get("CITY", "chicago")
SPOTS = json.load(open(Path(__file__).resolve().parents[2] / "spots.json"))
SPOT = os.environ.get("SPOT", "fps_drop_2")
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True,
               start=tuple(SPOTS[SPOT]["d2"]) if CITY == "chicago" else None,
               env={"PSX_IDLE_SKIP": os.environ.get("IDLE", "0"), **({"CHI_XD_PARTS": os.environ["XD_PARTS"]} if os.environ.get("XD_PARTS") else {})}, dev_mode=os.environ.get("DEV", "1") == "1")


def run(s):
    s.menu("take_a_ride/" + CITY); s.wait_world(what="start")
    series = []                                        # EMU % per 2 s window from the level start (warm-up)
    for _ in range(6):
        a, ta = s.word(0x80095250), time.time(); time.sleep(2.0)
        series.append(round(((s.word(0x80095250) - a) & 0xFFFFFFFF) / (time.time() - ta) / 59.94 * 100))
    s.record("series", detail="EMU %% per 2 s since level start: %s" % series)
    ds0 = s.d.cmd("dirty_ram_stats")
    p0, v0, t0 = s.word(0x800970D8), s.word(0x80095250), time.time()
    time.sleep(10)
    p1, v1, t1 = s.word(0x800970D8), s.word(0x80095250), time.time()
    ds1 = s.d.cmd("dirty_ram_stats")
    dd = {k: ds1[k] - ds0[k] for k in ds1 if isinstance(ds1.get(k), (int, float)) and isinstance(ds0.get(k), (int, float)) and ds1[k] != ds0[k] and k != "id"}
    s.record("dirty", detail="interpreter deltas over the window: %s" % dict(sorted(dd.items(), key=lambda kv: -abs(kv[1]))[:8]))
    vb = (v1 - v0) & 0xFFFFFFFF
    emu = vb / (t1 - t0) / 59.94 * 100
    fps = ((p1 - p0) & 0xFFFFFFFF) / max(vb, 1) * 59.94
    st = s.d.cmd("idle_skip") if os.environ.get("IDLE") == "1" else {}
    s.record("speed", detail="%s uncap %s idle %s dev %s: EMU %.0f %%, FPS %.1f %s" % (CITY, os.environ.get("RUNNER_UNCAP", "off"), os.environ.get("IDLE", "0"), os.environ.get("DEV", "1"), emu, fps, st))
