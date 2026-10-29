"""C135 (probe q73: freezes loading Newtown after Interview, Desert after LA day + Interview): Take a Ride SEQ (comma list,
default 'interview,newtown,la,interview,desert') one after another (quit to the menu in between; the carousel stays on
Take a Ride and the list on page 1), each must reach a running level (game frame counter moving) without a crash."""
import os, time
SEQ = os.environ.get("SEQ", "interview,newtown,la,interview,desert").split(",")
ROWS = {"miami": 0, "frisco": 1, "la": 2, "ny": 3, "newtown": 4, "interview": 5, "desert": 6}
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)


def running(s, secs=4.0):
    a = s.word(0x800970D8); time.sleep(secs); return s.word(0x800970D8) != a and s.alive()


def run(s):
    import importlib.util as iu
    sp = iu.spec_from_file_location("cs_", os.path.join(os.path.dirname(os.path.abspath(__file__)), "city_switch.py"))
    cs = iu.module_from_spec(sp); sp.loader.exec_module(cs)
    ok = []
    for k, city in enumerate(SEQ):
        if k == 0:
            s.menu("take_a_ride/" + city)
        else:
            cs.quit_to_menu(s)
            try:
                s.menu("take_a_ride/" + city)                 # as city_switch (ny -> chicago)
            except Exception as e:
                s.record("load", ok=False, detail="%s: %s" % (city, str(e)[:120])); ok.append((city, False)); break
        time.sleep(4)
        want = {"interview": 2, "newtown": 7, "la": 3, "desert": 6, "miami": 0, "frisco": 1, "ny": 5}[city]
        r = running(s) and s.word(0x80096834) == want
        s.record("level", detail="%d %s: CITY %d (want %d), running %s" % (k, city, s.word(0x80096834), want, r))
        ok.append((city, r))
        if not r:
            break
    s.check("all extras loaded and run in sequence", len(ok) == len(SEQ) and all(r for _, r in ok), str(ok))
