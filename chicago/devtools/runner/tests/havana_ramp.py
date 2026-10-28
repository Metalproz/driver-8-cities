"""M3 Havana ramp (slope-relative check, Polish 27.10.): pose at the ramp's top, drive downhill (+x), sample x / y every 0.1 s. A ramp = the
car descends >= 1500 and never drops faster than the D2 slope allows: per sample dy <= 0.25 x horizontal move + 60
(the car is fast: ~1300 per sample, so a fixed 300 limit failed on the real ramp)."""
import math, os, time
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)


def run(s):
    s.poke32(0x8009681C, 1)
    s.menu("take_a_ride/havana"); s.wait_world(what="havana")
    x, z, h, secs = (float(v) for v in os.environ.get("RAMP", "-153655,-221696,1024,4").split(","))
    s.pose(int(x), int(z), h * 2 * math.pi / 4096)
    ps = [s.pos()]
    s.hold("cross")
    t0 = time.time()
    while time.time() - t0 < secs:
        time.sleep(0.1)
        ps.append(s.pos())
    s.release()
    s.screenshot("ramp_end")
    # judge the ramp only: up to the car reaching street level (y < 300) + 3 samples (28.10.: later bumps / a second raised
    # block on the way made the suite flaky, 3 of ~6 runs; isolated reruns passed)
    end = next((i for i, p in enumerate(ps) if p[1] < 300), len(ps) - 1)
    ramp = ps[:min(len(ps), end + 4)]
    bad = [(a, b) for a, b in zip(ramp, ramp[1:]) if (a[1] - b[1]) > 0.25 * math.hypot(b[0] - a[0], b[2] - a[2]) + 60]
    ys = [p[1] for p in ps]
    s.record("ramp", detail="y %d -> %d over x %d -> %d; falls %s; samples %s" % (ys[0], ys[-1], ps[0][0], ps[-1][0],
             [(int(a[0]), int(a[1]), int(b[1])) for a, b in bad][:5], [(int(p[0]), int(p[1])) for p in ps[::5]]))
    s.check("the raised quarter's ramp leads down smoothly", ys[0] - min(ys) > 1500 and not bad,
            "descent %d, %d samples faster than the slope" % (ys[0] - min(ys), len(bad)))
