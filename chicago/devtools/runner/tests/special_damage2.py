"""48 / C87 on Polish's specdmg2 (u+128 damage copies): side / front hits on the bus go to their zones and show D2 damage
textures; the player's own wall hits (the scenery path with the new zone code) keep working."""
import math, os, time
import importlib.util
from pathlib import Path

SESSION = dict(day=os.environ.get("SD_DAY", "var_polish_specdmg2_day.lev"), night=os.environ.get("SD_NIGHT") or None, s4=True)
_spec = importlib.util.spec_from_file_location("sz", Path(__file__).with_name("special_zones.py"))
sz = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(sz)


def look_at_bus(s, name, along, side):
    bi = s.find_model(5)
    bx, by, bz, bh, _ = s.car(bi)
    fx, fz = math.sin(bh), math.cos(bh); rx, rz = math.cos(bh), -math.sin(bh)
    px, pz = bx + fx * along + rx * side, bz + fz * along + rz * side
    s.pose(int(px), int(pz), math.atan2(bx - px, bz - pz), settle=0.3)
    s.screenshot(name)


def run(s):
    s.menu("take_a_ride/chicago")
    for k in range(3):                                      # three side hits: damage that shows
        d = sz.hit(s, -400, 1500, "side_hit%d" % k)
        s.record("hit", detail="deltas %s contact %s" % (d, sz.hit_along))
        time.sleep(1)
    s.check("bus damaged", any(sz.zones(s, s.find_model(5))), str(sz.zones(s, s.find_model(5))))
    look_at_bus(s, "bus_side_view", -300, 1300)
    time.sleep(1)
    bi = s.find_model(5)
    z = sz.zones(s, bi)
    s.record("bus zones", detail=str(z))
    # the player's wall hits: scenery path (NOSES) for a non-special car, must not change anything or crash
    s.drive(8)
    s.check("game alive after wall / scenery hits", s.alive(2.0))
    s.screenshot("end")
