"""C40 measurement: FPS + GP0 packets per frame + guest hot functions (phase_hot, static set) at a dense spot, 4 headings
standing (5 s each) + 12 s heading-hold driving along the start heading. Chicago: env SPOT = a spots.json name, the level STARTS there. Miami: SPOT=miami:N =
pick N of the miami_dense_scan run (env MIAMI_SPOTS = its dense_spots.json), reached by pose (wait_world + ensure_area).
Writes fps.json in the run dir."""
import json, math, os, time
from pathlib import Path

SPOTS = json.load(open(Path(__file__).resolve().parents[2] / "spots.json"))
SPOT = os.environ.get("SPOT", "fps_drop_2")
MIAMI = SPOT.startswith("miami")
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True,
               start=None if MIAMI else tuple(SPOTS[SPOT]["d2"]))


def hot(s):
    r = s.d.cmd("phase_hot", top=300, set="static")
    return {e["addr"]: e["samples"] for e in r.get("top", [])}, int(r.get("phase_samples_total", 0))


def run(s):
    s.menu("take_a_ride/miami" if MIAMI else "take_a_ride/chicago")
    if MIAMI:
        pick = json.load(open(os.environ["MIAMI_SPOTS"]))["picks"][int(SPOT.split(":")[1])]
        x, _, z = pick["pos"]
        s.pose(x, z, math.radians(pick["heading"]))
    else:
        s.wait_world(what="world at the start")
    x, y, z, h0, _ = s.car(0)
    res = {"spot": SPOT, "pos": [x, y, z], "standing": []}
    a, ta = hot(s)
    for k in range(4):
        hd = h0 + k * math.pi / 2
        if k:
            s.pose(x, z, hd, y=y, ground=False, settle=0.5)
        fps, pk = s.perf(5.0)
        res["standing"].append({"heading": round(math.degrees(hd)) % 360, "fps": fps, "packets": pk})
        s.screenshot("h%d" % k)
    b, tb = hot(s)
    tot = max(tb - ta, 1)
    diff = sorted(((addr, b.get(addr, 0) - a.get(addr, 0)) for addr in b), key=lambda kv: -kv[1])
    res["hot"] = [(addr, round(100.0 * n / tot, 2)) for addr, n in diff[:25] if n > 0]
    # driving: heading-hold along the start heading (steers back within 8 deg, reverses out when stuck), 12 s
    s.pose(x, z, h0, y=y, ground=False, settle=0.5)
    p0, v0, g0 = s.word(0x800970D8), s.word(0x80095250), int(s.d.cmd("gpu_ring_stats").get("total", 0))
    s.drive(12.0, want=h0)
    p1, v1, g1 = s.word(0x800970D8), s.word(0x80095250), int(s.d.cmd("gpu_ring_stats").get("total", 0))
    fr, vb = (p1 - p0) & 0xFFFFFFFF, (v1 - v0) & 0xFFFFFFFF
    fps, pk = (round(fr / vb * 59.94, 1) if vb else 0.0), (round((g1 - g0) / fr) if fr else 0)
    q = s.pos()
    res["driving"] = {"fps": fps, "packets": pk, "route": "heading-hold %d deg, 12 s" % (round(math.degrees(h0)) % 360),
                      "dist": round(math.hypot(q[0] - x, q[2] - z))}
    st = [r["fps"] for r in res["standing"]]
    res["standing_avg"] = round(sum(st) / len(st), 1)
    (s.dir / "fps.json").write_text(json.dumps(res, indent=1))
    s.record("fps", detail="%s standing %s avg %.1f, packets %s, driving %.1f / %d" % (
        SPOT, st, res["standing_avg"], [r["packets"] for r in res["standing"]], fps, pk))
    s.check("measured", all(v > 0 for v in st))
