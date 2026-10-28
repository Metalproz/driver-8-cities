"""M3 Havana water (C17 band per city): pose the car on harbour-level spots next to D2 'no surface' cells, drive towards
them and record the drowning timer 0x800970DC (100 = dry, falling = sinking) / Game Over, car y, BANDW / DROWN_RANGE words.
SPOTS env: 'x,z,heading_4096;...' in Driver 1 coordinates (default: the offline havquay scan near the start)."""
import math, os, time
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)
DEFAULT = "367500,-196500,1024"   # hav6 harbour edge (27.10.; the old hav4-era scan spots are dry land in hav6)


def run(s):
    s.poke32(0x8009681C, 0)
    city = os.environ.get("CITY", "havana")
    s.menu("take_a_ride/" + city + ("/night" if os.environ.get("NIGHT") == "1" else "")); s.wait_world(what=city)
    s.record("words", detail="BANDW %d DROWN_RANGE %d sea %d" % (s.word(0x80093624), s.word(0x800978A8),
             s.word(0x80097888) - (1 << 32) if s.word(0x80097888) >> 31 else s.word(0x80097888)))
    drowned = 0
    for k, spot in enumerate(os.environ.get("SPOTS", DEFAULT).split(";")):
        x, z, h = (int(v) for v in spot.split(","))
        s.pose(x, z, h * 2 * math.pi / 4096)
        y0 = s.pos()[1]
        low, ymin = 100, y0
        s.hold("cross")
        t0 = time.time()
        while time.time() - t0 < 6.0:
            t = s.word(0x800970DC); t = t - (1 << 32) if t >> 31 else t
            low = min(low, t); ymin = min(ymin, s.pos()[1]) if s.pos()[1] < 0 else ymin
            time.sleep(0.1)
        s.release()
        s.screenshot("spot%d" % k)
        s.record("spot", detail="%d: (%d, %d) heading %d: y %d -> %d, drown timer min %d" % (k, x, z, h, y0, s.pos()[1], low))
        if low < 100:
            drowned += 1
        if not s.in_level():
            s.record("left level", detail="spot %d (Game Over?)" % k)
            break
    s.check("a harbour edge drowns at %s's sea level" % city, drowned > 0, "%d spots with a sinking car" % drowned)
