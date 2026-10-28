"""C99 HELL: Miami, CHEAT=hell (word 0x8009342C) or nightmare (0x800933C8); drive DRIVE s; pursuers (AI state 4): count,
top speed (car +0x40 velocity), highest damage (car +0x17C, wreck = 0x4651), pursuers lost (state 4 -> other)."""
import math, os, struct, time
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)
WORD = {"hell": 0x8009342C, "nightmare": 0x800933C8}


def run(s):
    cheat = os.environ.get("CHEAT", "hell")
    s.poke32(WORD[cheat], 1)
    s.menu("take_a_ride/miami"); s.wait_world(what="start")
    want = s.car(0)[3]
    if os.environ.get("POSE"):                           # x,z,heading (rad): the same straight for both cheats
        x, z, hd = (float(v) for v in os.environ["POSE"].split(","))
        s.pose(int(x), int(z), hd); want = hd
    st = dict(n=0, vmax=0, dmax=0, lost=0, f0=0, tgt=0, far=0, ps=0)
    last = {}
    sp = []
    vel = []; pvel = []
    prev = {}
    def tick(ss):
        cur = {}
        now = time.time()
        pv = struct.unpack("<3i", ss.ram(0x8009B0A4 + 0x40, 12)); pvel.append(int(math.hypot(pv[0], pv[2])))
        p = ss.pos()
        if "p" in last:
            st["ps"] = max(st["ps"], int(math.hypot(p[0] - last["p"][0], p[2] - last["p"][2]) / (now - last["t"])))
        for i in range(24):
            rec = ss.ram(0x80098950 + 0x50 * i, 8)
            if rec[1] != 4: continue
            car = 0x8009B230 + 0x18C * i
            vx, vy, vz = struct.unpack("<3i", ss.ram(car + 0x40, 12))
            d = struct.unpack("<h", ss.ram(car + 0x17C, 2))[0]
            cur[i] = 1
            vel.append(int(math.hypot(vx, vz)))
            f0 = struct.unpack("<i", ss.ram(car + 0xF0, 4))[0]; st["f0"] = max(st["f0"], f0)
            k = rec[5]
            if k:
                slot = ss.word(0x800933D8) + 0x7A8 * k
                st["tgt"] = max(st["tgt"], struct.unpack("<i", ss.ram(slot + 0x24, 4))[0])
            px, pz = ss.pos()[0], ss.pos()[2]
            cx, cz = struct.unpack("<i", ss.ram(car + 0xC8, 4))[0], struct.unpack("<i", ss.ram(car + 0xD0, 4))[0]
            if math.hypot(cx - px, cz - pz) > 8000: st["far"] = max(st["far"], int(math.hypot(vx, vz)))
            if i in last and math.hypot(cx - px, cz - pz) > 3000:
                ox, oz, ot = last[i]
                sp.append(int(math.hypot(cx - ox, cz - oz) / (now - ot)))
            last[i] = (cx, cz, now)
            st["vmax"] = max(st["vmax"], int(math.hypot(vx, vz))); st["dmax"] = max(st["dmax"], d)
        last["p"], last["t"] = p, now
        st["lost"] += sum(1 for i in prev if i not in cur)
        st["n"] = max(st["n"], len(cur)); prev.clear(); prev.update(cur)
    s.drive(float(os.environ.get("DRIVE", "30")), want, on_tick=tick)
    sp.sort(); vel.sort(); pvel.sort()
    s.record("vel", detail="%s: pursuer |v| p50 %d p90 %d; player |v| p50 %d p90 %d" % (cheat, vel[len(vel)//2] if vel else 0,
             vel[len(vel)*9//10] if vel else 0, pvel[len(pvel)//2] if pvel else 0, pvel[len(pvel)*9//10] if pvel else 0))
    s.record("speeds", detail="%s: pursuer ground speed (units/s, >3000 from the player) p50 %s p90 %s max %s; player max %d" % (
        cheat, sp[len(sp) // 2] if sp else 0, sp[len(sp) * 9 // 10] if sp else 0, sp[-1] if sp else 0, st["ps"]))
    s.record("pursuers", detail="%s: max pursuers %d, top speed %d (far from the player %d), max drive f0 %d, max target %d, max damage %d, dropped out %d" % (cheat, st["n"], st["vmax"], st["far"], st["f0"], st["tgt"], st["dmax"], st["lost"]))
    s.check("pursuers chase", st["n"] >= 5, "%d" % st["n"])
    if cheat == "hell":
        s.check("no pursuer near a wreck", st["dmax"] < 0x4651, "max damage %d" % st["dmax"])
    s.check("alive", s.alive(2.0))
