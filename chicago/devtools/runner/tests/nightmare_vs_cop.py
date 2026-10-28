"""C88 NIGHTMARE: a chaser (slot 5..) behaves like Driver 1's own cop (slot 1-4) in the same chase (Miami, player
standing, Invincibility): route planning active (slot +0x790), closing speed while far, contacts (< 900 units).
Driver 1's cops only re-planned on 'frame % 4 == slot - 1' (never for slots 5..) and chasers kept the lane-traffic
flag (record +8); both fixed."""
import math, time

SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True,
               env={"CHI_C88_NIGHTMARE": "1"})


def recs(s):
    raw = s.ram(0x80098950, 0x50 * 24)
    return {i: (raw[i * 0x50 + 5], raw[i * 0x50 + 8]) for i in range(24) if raw[i * 0x50 + 1] == 4 and raw[i * 0x50 + 5]}


def run(s):
    s.poke32(0x8009681C, 1)
    s.menu("take_a_ride/miami"); s.wait_world(what="start")
    s.poke32(0x800933C8, 1)
    for _ in range(80):                                   # wait for one of Driver 1's cops in pursuit
        if any(k <= 4 for k, _ in recs(s).values()):
            break
        time.sleep(0.5)
    base = s.word(0x800933D4)
    st = {"cop": dict(route=0, n=0, close=[], contact=0, lane=0), "chaser": dict(route=0, n=0, close=[], contact=0, lane=0)}
    last = {}
    import struct
    spd = {"cop": {}, "chaser": {}}
    for _ in range(60):
        r = recs(s); px, _, pz, _, _ = s.car(0)
        for i, (k, lane) in r.items():
            g = st["cop" if k <= 4 else "chaser"]
            g["n"] += 1; g["lane"] += lane
            g["route"] += s.word(base + (k - 1) * 0x7A8 + 0x790) != 0
            c = s.car(i + 1); d = math.hypot(c[0] - px, c[2] - pz)
            if d < 900: g["contact"] += 1
            if i in last and last[i] > 3000: g["close"].append((last[i] - d) / 0.4)
            vx, vy, vz = struct.unpack("<3i", s.ram(0x8009B230 + 0x18C * i + 0x40, 12))
            if d > 2500:
                t_ = "cop" if k <= 4 else "chaser"; spd[t_][i] = max(spd[t_].get(i, 0), math.hypot(vx, vz))
            last[i] = d
        time.sleep(0.4)
    out = {}
    for t, g in st.items():
        n = max(g["n"], 1)
        out[t] = dict(samples=g["n"], route=round(g["route"] / n, 2), contact=round(g["contact"] / n, 2), lane=g["lane"],
                      close=round(sum(g["close"]) / len(g["close"])) if g["close"] else None)
    for t in out:
        v = sorted(spd[t].values()); out[t]["topspeed_median"] = round(v[len(v) // 2]) if v else None
    s.record("compare", detail="%s" % out)
    c, h = out["cop"], out["chaser"]
    s.check("cop and chasers seen", c["samples"] > 0 and h["samples"] > 0, "%s" % out)
    s.check("chasers plan routes like the cop", h["route"] >= 0.5 * c["route"] and h["route"] > 0, "cop %s chaser %s" % (c["route"], h["route"]))
    s.record("closing", detail="cop %s chaser %s units/s (noisy: one cop)" % (c["close"], h["close"]))
    s.check("top speed like the cop", c["topspeed_median"] is None or h["topspeed_median"] is None
            or h["topspeed_median"] >= 0.7 * c["topspeed_median"], "cop %s chaser %s" % (c["topspeed_median"], h["topspeed_median"]))
    s.check("alive", s.alive(2.0))
