"""C88 cop slots moved (24-slot array): without Nightmare Driver 1's own cops still spawn in slots 1-4 and chase (felony
held high, Miami; the player is put in front of a patrol cop), nothing above slot 4 is used, the old slot area stays
untouched."""
import math, time
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)


def cops(s):
    raw = s.ram(0x80098950, 0x50 * 24)
    return [(i, raw[i * 0x50 + 5], raw[i * 0x50 + 1]) for i in range(24) if raw[i * 0x50 + 5]]


def run(s):
    s.poke32(0x8009681C, 1)
    s.menu("take_a_ride/miami"); s.wait_world(what="start")
    s.d.cmd("wtrace_range", lo="0x000C4E38", hi="0x000C6CD8")
    x, y, z, h, _ = s.car(0)
    s.poke32(0x80097708, 0x1000)
    s.drive(25.0, h, on_tick=lambda ss: bool(cops(ss)))
    c = cops(s)
    s.record("patrol", detail="cops %s" % c)
    chase, seen = 0, set(k for _, k, _ in c)
    for t in range(6):
        c = cops(s)
        if not c:
            time.sleep(2); continue
        i = c[0][0]; cx, cy, cz, ch, _ = s.car(i + 1)
        s.pose(int(cx + math.sin(ch) * 2500), int(cz + math.cos(ch) * 2500), ch, settle=0.3, ground=False)
        for _ in range(16):
            s.poke32(0x80097708, 0x1000); time.sleep(0.5)
            cc = cops(s); seen |= set(k for _, k, _ in cc)
            chase += sum(1 for _, _, st in cc if st == 4)
        if chase:
            break
    r = s.d.cmd("wtrace_dump", addr_lo="0x000C4E38", addr_hi="0x000C6CD8", count=10)
    s.record("cops", detail="slots used %s, pursuit samples %d, 0x8009770C %d" % (sorted(seen), chase, s.word(0x8009770C)))
    s.check("Driver 1 cops chase", chase > 0 and seen and max(seen) <= 4, "slots %s, pursuit samples %d" % (sorted(seen), chase))
    s.check("old slot area untouched", not r.get("entries"), "%d writes" % len(r.get("entries", [])))
    s.check("alive", s.alive(2.0))
