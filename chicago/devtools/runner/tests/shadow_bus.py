"""C102: the Chicago special's shadow quad (FUN_8002ADEC) stretched to its .sps.bin size. Waits for the special, poses
the player beside it, reads SHD[car] (0x80093480 + 16 car) and the special's corner quad, screenshot."""
import math, os, struct, time
LEV = os.environ.get("LEV", "var_polish_cheats6")
SESSION = dict(day=LEV + "_day.lev", night=LEV + "_night.lev", s4=True)


def run(s):
    s.poke32(0x8009681C, 1)
    s.menu("take_a_ride/chicago"); s.wait_world(what="start")
    s.wait_for(lambda: s.find_model(5) is not None, 90, "a special")
    bi = s.find_model(5); ci = bi
    bx, by, bz, bh, _ = s.car(bi)
    px, pz = bx + math.cos(bh) * 2600, bz - math.sin(bh) * 2600
    s.pose(int(px), int(pz), math.atan2(bx - px, bz - pz), settle=0.5, ground=False)
    time.sleep(1)
    car = 0x8009B0A4 + 0x18C * ci
    d = struct.unpack("<8h", s.ram(0x80093480 + 16 * ci, 16))
    q = [struct.unpack("<3i", s.ram(car + o, 12)) for o in (0x88, 0x98, 0xA8, 0xB8)]
    side = lambda a, b: int(math.hypot(a[0] - b[0], a[2] - b[2]))
    s.record("shadow", detail="special car %d: offsets %s; corner quad sides P0P1 %d P0P3 %d" % (ci, d, side(q[0], q[1]), side(q[0], q[2])))
    s.check("special has shadow offsets", any(d), "%s" % (d,))
    s.screenshot("bus_shadow")
