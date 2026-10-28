"""C122 pause-menu map in the D2 cities: Take a Ride in CITY (chicago|havana|la), pause, open the map (pause menu row
MAPROW, default 'down' x MAPDOWN then cross), screenshot; hold each d-pad direction (D2 cities pan) and screenshot; a d-pad
press must not close it in D2 cities (flag 0x800967E8 stays 1), any other key closes it. Records the pad words 0x8009752C /
0x80097538 while a direction is held, the map words MAPD2 / MAPSX / MAPSY and the player position."""
import os, time
CITY = os.environ.get("CITY", "chicago")
MAPDOWN = int(os.environ.get("MAPDOWN", "6"))
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)
FLAG = 0x800967E8


def words(s):
    sg = lambda v: v - (1 << 32) if v >> 31 else v
    return dict(open=s.word(FLAG), mapd2=s.word(0x80093628), sx=sg(s.word(0x8009362C)), sy=sg(s.word(0x80093630)),
                pad_held=hex(s.word(0x8009752C) & 0xFFFF))


def run(s):
    s.menu("take_a_ride/" + CITY); s.wait_world(what=CITY)
    time.sleep(2)
    x, y, z, h, _ = s.car(0)
    s.record("player", detail="x %d z %d" % (x, z))
    s.press("start", gap=1.5)
    s.screenshot("pause_menu")
    for _ in range(MAPDOWN):
        s.press("down", gap=0.5)
    s.press("cross", gap=1.5)
    s.screenshot("map")
    s.record("map_open", detail=str(words(s)))
    for d in ("left", "right", "up", "down"):
        bit = {"up": 4, "right": 5, "down": 6, "left": 7}[d]
        s.d.cmd("set_input", buttons="0x%04X" % (0xFFFF & ~(1 << bit)))   # active-low raw pad (dt.press)
        time.sleep(0.05)
        s.record("pan_" + d + "_early", detail=str(words(s)))
        trail = []
        for _ in range(8):
            time.sleep(0.1)
            trail.append((s.word(0x8009362C), s.word(0x80093630), s.word(0x80093634), s.word(0x80095250)))
        s.record("pan_" + d, detail=str(words(s)) + " trail sx/sy/vb/vbnow " + str([tuple(v - (1 << 32) if v >> 31 else v for v in t) for t in trail]))
        s.d.cmd("clear_input")
        time.sleep(0.3)
        s.screenshot("map_" + d)
    w = words(s)
    s.check("%s: map still open after d-pad" % CITY, w["open"] == 1 or CITY not in ("chicago", "havana", "vegas", "rio"), str(w))
    s.press("cross", gap=1.0)
    s.record("after_cross", detail=str(words(s)))
