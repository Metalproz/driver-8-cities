"""C140 / C141 (probe d2 cities 6, session 16:28): Rio row -> Day -> back out -> page 1 -> cursor over Interview ->
Newtown. The user's Newtown then ran LA's raw Take a Ride script (mission-parse hook not applied: police in Newtown =
bare wheels). Checks after the Newtown load: the hook's script copy (MISSION_SAFE 0x800A0D00), cop cap 0x80097760 = 0,
no police car (model 1) on the road after DRIVE s, the log's C50 / C79 lines. FROM (default rio) = the D2 row first;
BACKS (default 2) = triangle presses after the Day choice."""
import os, re, struct, time

SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)
FROM = os.environ.get("FROM", "rio")
BACKS = int(os.environ.get("BACKS", "1"))   # triangle on the Day/Night screen ("Rio day" is logged when it opens)
DRIVE = float(os.environ.get("DRIVE", "20"))
D2ROWS = {"chicago": 0, "havana": 1, "vegas": 2, "rio": 3}


def state(s, tag):
    s.record("state", detail="%s: mission %02X CITY %d cursor %d" % (tag, s.word(0x80096808), s.word(0x80096834), s.word(0x801CE088)))


PRE = os.environ.get("PRE", "chicago")   # the user's session played a Chicago ride first, then quit (16:28 log)


def run(s):
    if PRE:
        s.menu("take_a_ride/" + PRE); s.wait_world(what=PRE); time.sleep(5)
        import importlib.util as iu
        sp = iu.spec_from_file_location("cs_", os.path.join(os.path.dirname(os.path.abspath(__file__)), "city_switch.py"))
        cs_ = iu.module_from_spec(sp); sp.loader.exec_module(cs_)
        cs_.quit_to_menu(s)
        s.press("triangle"); time.sleep(2)
        s.press("cross"); time.sleep(1.5)              # the list, page 2 remembered (cursor on Chicago)
    else:
        s.press("triangle"); time.sleep(2)
        for b in ["right"] * 5 + ["cross"]:
            s.press(b)
        time.sleep(1.5)
        for _ in range(7):
            s.press("down", gap=0.6)                    # page row
        s.press("cross", gap=1.0); time.sleep(1)
    for _ in range(D2ROWS[FROM]):
        s.press("down", gap=0.8)
    s.press("cross"); time.sleep(3)
    s.screenshot("day_night")
    state(s, "Day/Night screen")
    for k in range(BACKS):
        s.press("triangle"); time.sleep(2.0)
        s.screenshot("back%d" % (k + 1))
        state(s, "back %d" % (k + 1))
    s.screenshot("list")
    state(s, "list (page 2, cursor on the D2 row)")
    for _ in range(D2ROWS[FROM]):
        s.press("up", gap=0.6)                          # back to the first row
    for _ in range(4):
        s.press("down", gap=0.6)                        # page 2: "Driver 1 cities"
    s.press("cross", gap=1.5)
    for _ in range(5):
        s.press("down", gap=0.8)                        # page 1: Interview (row 5)
    time.sleep(1); state(s, "over Interview")
    s.press("up", gap=0.8)                              # Newtown (row 4)
    time.sleep(1); state(s, "on Newtown")
    s.screenshot("on_newtown")
    s.press("cross"); time.sleep(3)
    s.wait_for(s.in_level, 120, "in level (newtown)")
    s.wait_world(what="newtown")
    safe = s.word(0x800A0D00)
    cap, on = s.word(0x80097760), s.word(0x800976F8)
    x, y, z, h, _ = s.car(0)
    s.drive(DRIVE, int(h))
    rec = s.ram(0x80098950, 0x50 * 24)
    cops = sum(1 for i in range(24) if rec[i * 0x50 + 1] and rec[i * 0x50 + 0x10] == 1)
    s.screenshot("newtown")
    txt = (s.dir / "game.log").read_text(encoding="utf-8", errors="replace") if (s.dir / "game.log").exists() else ""
    if not txt:
        import glob
        logs = sorted(glob.glob(str(s.copy_dir / "dev" / "logs" / "*.log")), key=os.path.getmtime)
        txt = open(logs[-1], encoding="utf-8", errors="replace").read() if logs else ""
    hook = bool(re.search(r"C50 mission script .* level 7", txt))
    s.record("newtown", detail="CITY %d mission %02X, script copy %s, cops on %d cap %d, police cars %d, hook %s, C141 guard %s"
             % (s.word(0x80096834), s.word(0x80096808), "yes" if safe else "EMPTY", on, cap, cops, hook,
                "C141 Newtown" in txt))
    s.check("Newtown loaded (CITY 7)", s.word(0x80096834) == 7)
    s.check("mission-parse hook applied (C50 line, script copy)", hook and safe != 0, "hook %s safe %08X" % (hook, safe))
    s.check("no police in Newtown traffic (cap 0, no model-1 car)", cap == 0 and cops == 0, "cap %d cops %d" % (cap, cops))
    s.poke32(0x80097760, 2); time.sleep(1.0)           # C141 guard: a cap of 2 (LA's script) must go back to 0
    s.check("C141 guard resets the Newtown cop cap", s.word(0x80097760) == 0, "cap %d" % s.word(0x80097760))
    s.check("alive", s.alive())
