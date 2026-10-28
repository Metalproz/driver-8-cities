"""C91 FEATHER: the player drives head-on into the special (Chicago bus) with the cheat off / on. On: the bus keeps its
speed and heading (others never moved by the player), the player is thrown (velocity change, yaw)."""
import math, os, struct, time

SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)
INFM = 0x800933C4


def vel(s, i):
    b = 0x8009B0A4 + 0x18C * i
    return struct.unpack("<3i", s.ram(b + 0x40, 12))


def run(s):
    from dt import wrecked, play_again
    s.poke32(0x8009681C, 1)
    s.menu("take_a_ride/chicago")
    s.wait_world(what="start")
    res = {}
    for mode in [int(x, 0) for x in os.environ.get("MODES", "0,0x100").split(",")]:
        s.poke32(INFM, mode)
        rows = []
        for k in range(3):
            if wrecked(s.d) or not s.in_level():
                s.release(); play_again(s.d); time.sleep(4)
            s.poke32(0x8009B220, 0)
            s.wait_for(lambda: s.find_model(5) is not None, 60, "a special")
            bi = s.find_model(5); bx, by, bz, bh, _ = s.car(bi)
            px, pz = bx + math.sin(bh) * 2600, bz + math.cos(bh) * 2600
            s.pose(int(px), int(pz), math.atan2(bx - px, bz - pz), settle=0.3, ground=False)
            h0 = s.car(0)[3]; s.hold("cross"); t = time.time()
            bv0 = None; pmax = 0; bdv = 0; yaw = 0; last_p = vel(s, 0)
            while time.time() - t < 3.0:
                time.sleep(0.03)
                pv, bv = vel(s, 0), vel(s, bi)
                d = math.hypot(s.car(0)[0] - s.car(bi)[0], s.car(0)[2] - s.car(bi)[2])
                if bv0 is None and d < 2200: bv0 = bv
                if bv0 is not None and d < 2600:
                    bdv = max(bdv, math.hypot(bv[0] - bv0[0], bv[2] - bv0[2]))
                    pmax = max(pmax, math.hypot(pv[0] - last_p[0], pv[2] - last_p[2]))
                    yaw = max(yaw, abs(math.degrees((s.car(0)[3] - h0 + math.pi) % (2 * math.pi) - math.pi)))
                last_p = pv
            s.release(); time.sleep(1.5)
            rows.append(dict(bus_dv=round(bdv), player_dv=round(pmax), yaw=round(yaw)))
        res[hex(mode)] = rows
        s.record("feather %s" % hex(mode), detail="%s" % rows)
    s.poke32(INFM, 0)
    if "0x0" not in res or "0x100" not in res:
        return
    off, on = res["0x0"], res["0x100"]
    med = lambda r, k: sorted(x[k] for x in r)[1]
    s.check("feather: the bus is not moved by the player", med(on, "bus_dv") < 0.3 * max(med(off, "bus_dv"), 1),
            "bus dv off %s on %s" % ([x["bus_dv"] for x in off], [x["bus_dv"] for x in on]))
    s.check("feather: the player is thrown", med(on, "player_dv") >= med(off, "player_dv"),
            "player dv off %s on %s" % ([x["player_dv"] for x in off], [x["player_dv"] for x in on]))
