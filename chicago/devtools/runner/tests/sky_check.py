"""C126 (user R65: every D2 city showed Havana's day sky): Take a Ride in CITY (chicago|havana|vegas|rio, NIGHT=1) after
FIRST (optional: another D2 city played first, then quit; the bug kept the first city's sky number); the level's sky
immediates LoadSky reads (0x8004EDE0 day / night, 0x8004EE00 rain) must be the city's own: its slot sidecar's first sky
(flags bits 8-15; Chicago 13) + 1 at night, rain + 2. Screenshot of the sky."""
import os, struct, time
CITY = os.environ.get("CITY", "vegas")
NIGHT = os.environ.get("NIGHT") == "1"
DIRS = {"chicago": None, "havana": "havana", "vegas": "vegas", "rio": "rio"}
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)


def expected(s):
    a = s.copy_dir / "mods" / "packages" / "driver.chicago" / "0.1.0" / "assets"
    f = a / "chicago_slot.bin" if DIRS[CITY] is None else a / DIRS[CITY] / "slot.bin"
    w = struct.unpack_from("<27I", f.read_bytes())
    first = (w[26] >> 8) & 0xFF or 13
    return first + (1 if NIGHT else 0)


def run(s):
    first = os.environ.get("FIRST")
    if first:
        import importlib.util as iu
        sp = iu.spec_from_file_location("cs_", os.path.join(os.path.dirname(os.path.abspath(__file__)), "city_switch.py"))
        cs = iu.module_from_spec(sp); sp.loader.exec_module(cs)
        s.menu("take_a_ride/" + first); s.wait_world(what=first); time.sleep(3)
        cs.quit_to_menu(s)
        # after the quit: the carousel is still on Take a Ride, page 2 shown, cursor on its first row (car_sounds)
        s.press("triangle"); time.sleep(2)
        s.press("cross"); time.sleep(1.5)
        for _ in range({"chicago": 0, "havana": 1, "vegas": 2, "rio": 3}[CITY]):
            s.press("down", gap=0.8)
        s.press("cross"); time.sleep(3)
        if NIGHT:
            s.press("down")
        s.press("cross")
        s.wait_for(s.in_level, 120, "in level (second city)")
        time.sleep(3)
    else:
        s.menu("take_a_ride/%s%s" % (CITY, "/night" if NIGHT else ""))
    s.wait_world(what=CITY)
    time.sleep(2)
    sky = s.word(0x800974EC)                              # (LoadSky's CITY 3 flag word, recorded only)
    imms = [s.word(a) & 0xFFFF for a in (0x8004EDE0, 0x8004EDEC, 0x8004EE00)]
    want = expected(s)
    s.record("sky", detail="%s %s: sky number %d, immediates %s, expected %d" % (CITY, "night" if NIGHT else "day", sky, imms, want))
    s.screenshot("sky")
    s.check("%s %s sky = its own (%d, rain %d)" % (CITY, "night" if NIGHT else "day", want, want - NIGHT + 2),
            imms[0] == want and imms[2] == want - NIGHT + 2, "imm %s" % imms)
