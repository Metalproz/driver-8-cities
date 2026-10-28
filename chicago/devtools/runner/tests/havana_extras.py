"""M3 Havana extras: (a) police: felony held high (0x80097708 = 0x1000) while driving from the start: cop records spawn and
chase (as cops_d1 in Miami), screenshots; (b) the three static FERRY objects (hav6 model 1476 at D1 (576462, 118429),
(431519, 291603), (431483, 298493)): pose on each deck, settle, record y and the drowning timer (a deck holds the car:
y stays near the deck, timer 100), screenshot."""
import math, os, time
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)
FERRIES = [(576462, 118429), (431519, 291603), (431483, 298493)]


def cops(s):
    raw = s.ram(0x80098950, 0x50 * 24)
    return [(i, raw[i * 0x50 + 5], raw[i * 0x50 + 1]) for i in range(24) if raw[i * 0x50 + 5]]


def run(s):
    sg = lambda v: v - (1 << 32) if v >> 31 else v
    s.poke32(0x8009681C, 1)
    s.menu("take_a_ride/havana"); s.wait_world(what="havana")
    x, y, z, h, _ = s.car(0)
    s.poke32(0x80097708, 0x1000)
    seen = set()
    def tick(ss):
        for c in cops(ss):
            seen.add(c[1])
        return False
    s.drive(25.0, h, on_tick=tick)
    s.screenshot("cops")
    s.record("cops", detail="cop slots seen %s, now %s" % (sorted(seen), cops(s)))
    s.check("Havana: police spawn and chase with felony", len(seen) > 0, "slots %s" % sorted(seen))
    s.poke32(0x80097708, 0)
    held = 0
    for k, (fx, fz) in enumerate(FERRIES):
        try:
            s.pose(fx, fz, 0.0)
        except Exception as e:
            s.record("ferry", ok=True, detail="%d: pose failed %s" % (k, str(e)[:80])); continue
        y0 = s.pos()[1]; time.sleep(4.0)
        y1, t = s.pos()[1], sg(s.word(0x800970DC))
        s.screenshot("ferry%d" % k)
        s.record("ferry", detail="%d at (%d, %d): y %d -> %d, drown timer %d" % (k, fx, fz, y0, y1, t))
        if abs(y1 - y0) < 300 and t == 100:
            held += 1
    s.record("ferries", detail="%d of %d decks hold the car" % (held, len(FERRIES)))
