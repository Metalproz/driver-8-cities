"""CLUT budget check (Polish 28.10.: vegas2 night 381 / 384 counting the largest special pair): player choice CHOICE
(0x8009683C, poked before the menu) in CITY (NIGHT=1), screenshots at the start and while driving (palette corruption on
cars / world would show as wrong colours)."""
import os, time
CITY = os.environ.get("CITY", "vegas")
CHOICE = int(os.environ.get("CHOICE", "3"))
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)


def run(s):
    # Take a Ride's mission script sets choice 0 (parse 0x80068A38) before the level builds the cars: keep poking the
    # choice from a second debug connection while the menu / load runs
    import threading, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    import dt
    stop = threading.Event()
    def poker():
        d2 = dt.Dbg(s.port) if hasattr(dt, "Dbg") else None
        while not stop.is_set():
            try:
                (d2 or s.d).cmd("write_ram", addr="0x8009683C", val=CHOICE)
            except Exception:
                pass
            time.sleep(0.02)
    th = threading.Thread(target=poker, daemon=True); th.start()
    s.menu("take_a_ride/%s%s" % (CITY, "/night" if os.environ.get("NIGHT") == "1" else ""))
    time.sleep(3); stop.set(); th.join()
    s.wait_world(what=CITY)
    s.record("choice", detail="choice word %d (wanted %d)" % (s.word(0x8009683C) & 3, CHOICE))
    s.screenshot("start")
    h = s.car(0)[3]
    for k in range(3):
        s.drive(7.0, h)
        s.screenshot("drive%d" % k)
    s.check("choice %d in use" % CHOICE, (s.word(0x8009683C) & 3) == CHOICE, "word %d" % s.word(0x8009683C))
