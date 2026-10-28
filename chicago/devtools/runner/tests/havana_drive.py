"""M3 Havana slot: Take a Ride -> page 2 -> Havana (NIGHT=1: night) boots, its asset set and level entry are in use,
the car drives (DRIVE seconds). Needs a package with Havana (env CHI_HAVANA_DAY / CHI_HAVANA_NIGHT for dt.prepare)."""
import os, time
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)


CITY = os.environ.get("CITY", "havana")              # also vegas / rio (M3 Q68 B rows)
SEA = {"havana": -160, "vegas": -40, "rio": -40}


def run(s):
    night = os.environ.get("NIGHT") == "1"
    s.menu("take_a_ride/%s" % CITY + ("/night" if night else ""))
    s.wait_world(what=CITY)
    log = (s.copy_dir / "dev" / "logs")
    s.record("xd", detail="XPVS %d XDD %d" % (s.word(0x80093430), s.word(0x80093408)))
    s.record("city", detail="CITY %d, entry3 %08X, sea %d, flag %d" % (s.word(0x80096834), s.word(0x800BE0A4 + 96),
             s.word(0x80097888) - (1 << 32) if s.word(0x80097888) >> 31 else s.word(0x80097888), s.word(0x8009788C)))
    s.record("glow", detail=" ".join("%08X" % s.word(a) for a in (0x800530E4, 0x800537E4, 0x800537F8, 0x8005380C, 0x80053814,
                                                                  0x80053118, 0x8005311C, 0x8005310C, 0x80053114)))
    s.record("bands", detail="BANDW %d DROWN_RANGE words: sea %d" % (s.word(0x80093624), s.word(0x80097888) - (1 << 32) if s.word(0x80097888) >> 31 else s.word(0x80097888)))
    s.screenshot("start")
    p0 = s.pos()
    s.drive(float(os.environ.get("DRIVE", "20")), s.car(0)[3])
    p1 = s.pos()
    s.screenshot("driven")
    moved = abs(p1[0] - p0[0]) + abs(p1[2] - p0[2])
    sea = int(os.environ.get("SEA", str(SEA.get(CITY, -160))))
    s.check("%s loaded (D2 city flag, sea level %d)" % (CITY, sea), s.word(0x8009788C) == 1 and s.word(0x80097888) == sea & 0xFFFFFFFF,
            "flag %d sea %08X" % (s.word(0x8009788C), s.word(0x80097888)))
    s.check("car drives", moved > 2000 and s.alive(), "moved %d" % moved)
