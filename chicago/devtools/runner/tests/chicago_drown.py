"""C17 band per city (M3): drowning still works. CITY=chicago: (a) a river cell (spot 'inwater', posed in the water:
centre-cell rule) and (b) the bank edge c28_bank_w driven east into the lake strip (the C17 band: a wheel on sea ground,
y in [-1120, -500)); CITY=la: a D1 water tile next to land (Driver 1's own rule; BANDW / DROWN_RANGE must stay 0).
Per case: the drowning timer 0x800970DC (100 dry, falling while sinking, < 0 Game Over), then Play Again for the next.
CASES env overrides: 'name,x,z,heading4096,drive_s;...' (Driver 1 coordinates)."""
import math, os, time
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)
DEFAULT = {
    "chicago": "lake_in,275250,53250,1024,0;lake_edge,273750,53250,1024,4;lake_edge2,266250,63750,1024,4",   # water model 683 tiles
    # D1 cities: the band words must stay 0 (checked); LA's water tiles (model 316) lie in the far west harbour, whose
    # area the teleport cannot force from the start (ensure_area), so no drive-in case by default (CASES to add one)
    "la": "",
}
TIMER = 0x800970DC


def s32(v):
    return v - (1 << 32) if v >> 31 else v


def play_again(s):
    for _ in range(3):
        s.press("down", gap=0.5)
    s.press("cross", gap=1.0)
    s.wait_for(s.in_level, 90, "in level after Play Again", fail=False)
    time.sleep(3)


def run(s):
    city = os.environ.get("CITY", "chicago")
    s.menu("take_a_ride/" + city); s.wait_world(what=city)
    s.poke32(0x8009681C, 1)                                   # Invincibility: a crash must not end the case (drowning still does)
    bw, dr = s.word(0x80093624), s.word(0x800978A8)
    s.record("words", detail="%s: BANDW %d DROWN_RANGE %d" % (city, bw, dr))
    if city != "chicago":
        s.check("D1 city: band words untouched (0)", bw == 0 and dr == 0, "BANDW %d DROWN_RANGE %d" % (bw, dr))
    sank = 0
    cases = [c for c in os.environ.get("CASES", DEFAULT.get(city, "")).split(";") if c]
    for k, c in enumerate(cases):
        f = c.split(",")
        name, x, z, h, drive = f[0], int(f[1]), int(f[2]), int(f[3]), float(f[4])
        for i in range(5, len(f) - 1, 2):                    # waypoints: let the areas on the way load
            try:
                s.pose(int(f[i]), int(f[i + 1]), h * 2 * math.pi / 4096)
            except Exception as e:
                s.record("waypoint", ok=True, detail="%s: %s" % (f[i:i + 2], str(e)[:80]))
        s.pose(x, z, h * 2 * math.pi / 4096)
        if drive:
            s.hold("cross")
        low, t0, over = 100, time.time(), False
        while time.time() - t0 < 14.0:
            if drive and time.time() - t0 > drive:
                s.release()
            t = s32(s.word(TIMER))
            low = min(low, t)
            if not s.in_level():
                over = True
                break
            time.sleep(0.1)
        s.release()
        s.screenshot("case_%s" % name)
        s.record("case", detail="%s: (%d, %d) heading %d: y %d, drown timer min %d, game over %s" % (name, x, z, h, s.pos()[1], low, over))
        if low < 100:
            sank += 1
        if over or low < 0:
            play_again(s)
    if cases:
        s.check("%s: a car in / driven into the water drowns" % city, sank > 0, "%d of %d cases sank" % (sank, len(cases)))
