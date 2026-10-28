"""C92: a run recorded with the CPU overclock at 200 % and watched as a Quick Replay at 100 % (MODE=on_off) shows the
same traffic (AI car positions at the same game frames) as Driver 1 does with 100 / 100 (MODE=off_off, reference).
VSync-seeded randomness (FUN_80022818 spawn pick) would make them differ."""
import math, os, time
MODE = os.environ.get("MODE", "on_off")
OC = os.path.join(os.environ.get("TEMP", "."), "chi_test_oc.txt")
open(OC, "w").write("100")
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True, env={"CHI_TEST_OC": OC})
FRAMES = (500, 700, 900, 1100)


def snap(s):
    out = []
    for i in range(1, 12):
        x, y, z, h, _ = s.car(i)
        out.append((x, z))
    return out


def run(s):
    s.poke32(0x8009681C, 1)
    open(OC, "w").write("200" if MODE == "on_off" else "100"); time.sleep(0.5)
    s.menu("take_a_ride/miami"); s.wait_world(what="start")
    rec = {}
    def tick(ss):
        f = ss.word(0x800970D8)
        for F in FRAMES:
            if F not in rec and f >= F: rec[F] = (f, snap(ss))
        return len(rec) == len(FRAMES)
    s.drive(60.0, s.car(0)[3], on_tick=tick)
    s.record("recorded", detail="frames %s" % {F: rec[F][0] for F in rec})
    open(OC, "w").write("100"); time.sleep(0.5)
    s.press("start", gap=1.0)
    for _ in range(5): s.press("down", gap=0.4)
    s.press("cross", gap=0.8)
    s.press("left", gap=0.4); s.press("cross", gap=0.3)        # "Are You Sure?" -> Yes
    s.wait_for(lambda: s.word(0x800970D8) < 100, 40, "replay restarted (frame counter reset)")
    f0 = s.word(0x800970D8)
    rep = {}
    t = time.time()
    while time.time() - t < 60 and len(rep) < len(rec):
        f = s.word(0x800970D8)
        for F in rec:
            if F not in rep and f >= rec[F][0]: rep[F] = (f, snap(s))
        time.sleep(0.02)
    s.screenshot("replay")
    diffs = {}
    for F in rec:
        if F in rep:
            d = [math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(rec[F][1], rep[F][1])]
            diffs[F] = (rec[F][0], rep[F][0], round(sorted(d)[len(d) // 2]), round(max(d)))
    s.record("compare", detail="mode %s replay start frame %d: frame -> (rec f, rep f, median diff, max diff) %s" % (MODE, f0, diffs))
    s.check("replay traffic matches", diffs and all(v[2] < 1500 for v in diffs.values()), "%s" % diffs)
