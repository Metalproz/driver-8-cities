"""C37 / C86: at diag_ramp and slope_ref the car tilts with the ground and never falls through (MapHeight + FindSurface).
Each spot is a level START (package start at the spot, not a teleport): the world is loaded like a normal start."""
import json, math, os, struct, time
from pathlib import Path
import importlib.util

SPOTS = json.load(open(Path(__file__).resolve().parents[2] / "spots.json"))
CASE = os.environ.get("SLOPE_SPOT", "slope_ref")
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True, start=tuple(SPOTS[CASE]["d2"]))


def tilt(s):
    raw = s.ram(0x8009B0A4 + 4, 18)
    m = struct.unpack_from("<9h", raw, 0)
    return round(math.degrees(math.acos(max(-1.0, min(1.0, abs(m[4]) / 4096.0)))), 1)


def run(s):
    s.menu("take_a_ride/chicago")
    s.wait_world(what="world at the start")
    name = CASE
    ys, ts = [], []
    for phase, btn in (("rest", None), ("forward", "cross"), ("back", "square")):
        if btn:
            s.hold(btn)
        t = time.time()
        while time.time() - t < 3.0:
            ys.append(s.pos()[1]); ts.append(tilt(s)); time.sleep(0.1)
        s.release()
        s.screenshot("%s_%s" % (name, phase))
    jumps = max(abs(a - b) for a, b in zip(ys, ys[1:]))
    s.check(name + " tilt", max(ts) >= 3.0, "tilt deg min %.1f max %.1f, start pos %s" % (min(ts), max(ts), s.pos()))
    # a car climbing the ramp at speed moves ~280 per 0.1 s; a fall-through is a larger step
    s.check(name + " no fall-through", jumps < 400, "y %d..%d, largest step %d" % (min(ys), max(ys), jumps))
