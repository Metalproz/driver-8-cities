"""C88 NIGHTMARE (user 63 B): every moving traffic car gets a cop slot and chases. CITY env (miami / chicago / ny /
newtown). Measures FPS standing with the cheat off and on, counts pursuers (record state 4 with a slot), checks they
close in, that nothing writes Driver 1's old slot area any more, NY's cap of 8, and the release when switched off.
Invincibility on so the player survives the rams."""
import math, os, time

CITY = os.environ.get("CITY", "miami")
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True,
               env={"CHI_C88_NIGHTMARE": "1", **({"CHI_C88_NM_CAP": os.environ["NM_CAP"]} if os.environ.get("NM_CAP") else {}),
                    **({"CHI_C88_NM_REPLAN": os.environ["NM_REPLAN"]} if os.environ.get("NM_REPLAN") else {})})
NM_CAP = int(os.environ.get("NM_CAP", "0") or 0)
NGHT, INV, REC, SLOT0 = 0x800933C8, 0x8009681C, 0x80098950, 0x800933D4


def pursuers(s):
    raw = s.ram(REC, 0x50 * 24)
    return [(i, raw[i * 0x50 + 5]) for i in range(24) if raw[i * 0x50 + 1] == 4 and raw[i * 0x50 + 5]]


def dists(s, ids):
    px, _, pz, _, _ = s.car(0)
    return {i: math.hypot(s.car(i + 1)[0] - px, s.car(i + 1)[2] - pz) for i in ids}


def hot(s):
    r = s.d.cmd("phase_hot", top=400, set="static")
    return {e["addr"]: e["samples"] for e in r.get("top", [])}, int(r.get("phase_samples_total", 0))


def hot_diff(a, b):
    tot = max(b[1] - a[1], 1)
    d = sorted(((k, v - a[0].get(k, 0)) for k, v in b[0].items()), key=lambda kv: -kv[1])
    return [(k, round(100.0 * v / tot, 1)) for k, v in d[:6] if v > 0]


def run(s):
    s.poke32(INV, 1)
    s.menu("take_a_ride/" + CITY)
    s.wait_world(what="start")
    city = s.word(0x80096834)
    s.d.cmd("wtrace_range", lo="0x000C4E38", hi="0x000C6CD8")
    h0 = hot(s); fps_off, pk_off = s.perf(8.0); h1 = hot(s)
    p0 = pursuers(s)
    s.record("off", detail="city %d, FPS %.1f, packets %d, pursuers %s, slot array %08x" % (city, fps_off, pk_off, p0, s.word(SLOT0)))
    s.poke32(NGHT, 1); time.sleep(3.0)
    p1 = pursuers(s)
    a = dists(s, [i for i, _ in p1]); time.sleep(10.0); b = dists(s, [i for i, _ in p1 if i in a])
    closer = sum(1 for i in a if i in b and (b[i] < a[i] - 500 or b[i] < 3000))   # closed in, or already at the player
    h2 = hot(s); fps_on, pk_on = s.perf(10.0); h3 = hot(s)
    s.record("hot", detail="off %s | on %s" % (hot_diff(h0, h1), hot_diff(h2, h3)))
    p2 = pursuers(s)
    s.screenshot("nightmare")
    s.record("on", detail="FPS %.1f (off %.1f), packets %d, pursuers %d -> %d (slots %s), closed in %d / %d" % (
        fps_on, fps_off, pk_on, len(p1), len(p2), sorted(k for _, k in p2), closer, len(a)))
    cap = 8 if city == 5 else 12
    if NM_CAP: cap = min(cap, NM_CAP)
    s.check("pursuers", len(p1) >= min(cap, 6), "%d pursuers after 3 s (%d after 13 s: wrecked cars drop out, Driver 1's rule)" % (len(p1), len(p2)))
    if cap < 24:
        s.check("cap %d" % cap, len(p2) <= cap, "%d" % len(p2))
    if True:
        s.check("they close in", closer >= max(1, len(a) // 3), "%d of %d" % (closer, len(a)))
    f0, v0 = s.word(0x800970D8), s.word(0x80095250)
    s.drive(20.0, s.car(0)[3])
    f1, v1 = s.word(0x800970D8), s.word(0x80095250)
    s.record("driving", detail="FPS %.1f while driving 20 s with chasers" % (((f1 - f0) & 0xFFFFFFFF) / max((v1 - v0) & 0xFFFFFFFF, 1) * 59.94))
    s.check("alive after 20 s drive with chasers", s.alive(2.0))
    r = s.d.cmd("wtrace_dump", addr_lo="0x000C4E38", addr_hi="0x000C6CD8", count=10)
    old = sorted({e["pc"] for e in r.get("entries", [])})
    s.check("old slot area untouched", not old, "writers %s" % old)
    s.poke32(NGHT, 0); time.sleep(2.0)
    p3 = [k for _, k in pursuers(s) if k > 4]
    s.check("released when off", not p3, "chaser slots left %s" % p3)
    s.check("alive", s.alive(2.0))
