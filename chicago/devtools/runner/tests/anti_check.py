"""C96 (cheats 5: 'Antipodean switches itself on'): cheats screen -> page 2 -> one cheat on (ROW, default 4 =
NIGHTMARE) -> leave from page 2 with triangle -> words; then Take a Ride Miami -> words in the level."""
import os, threading, time
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)
CUR = 0x801D2E48
W = dict(hell=0x8009342C, inv=0x8009681C, imm=0x80096820, rear=0x8009D8DC, minis=0x8009D8E0, stilts=0x8009D8E4, lowg=0x8009D8E8,
         anti=0x8009D8EC, infm=0x800933C4, ngt=0x800933C8, spd2=0x800933CC, hdr=0x80097644)


def goto(s, row):
    for _ in range(10):
        c = s.word(CUR)
        if c == row: return True
        s.press("down" if c < row else "up", gap=0.4)
    return s.word(CUR) == row


def words(s):
    return {k: s.word(a) for k, a in W.items()}


def run(s):
    s.press("triangle"); time.sleep(2)
    for b in ["right"] * 3 + ["cross"]:
        s.press(b)
    time.sleep(1.5)
    s.record("enter", detail="%s" % words(s))
    if os.environ.get("INV", "1") == "1":
        goto(s, 1); s.press("cross", gap=0.6)                 # user's steps: INVINCIBILITY on (page 1 row 1)
    goto(s, 7); s.press("cross", gap=0.8)                     # PAGE 2
    goto(s, int(os.environ.get("ROW", "6"))); s.press("cross", gap=0.6)   # 6 = HELL (user's steps)
    s.record("page2 toggled", detail="%s" % words(s))
    s.press(os.environ.get("EXIT", "triangle"), gap=1.5)
    w1 = words(s); s.record("left screen", detail="%s" % w1)
    s.check("antipodean off after leaving", w1["anti"] == 0, "%s" % w1)
    time.sleep(1)
    log = []; stop = [0]
    def watch():
        last = None
        while not stop[0]:
            try:
                cur = (s.word(0x8009342C), s.word(0x8009D8E8), s.word(0x8009D8EC), s.word(0x801CDE5C), s.word(0x801CE038) == 0x0172001A, s.word(0x80097644))
            except Exception:
                cur = None
            if cur != last: log.append((round(time.time() - t0, 2), cur)); last = cur
            time.sleep(0.05)
    t0 = time.time(); th = threading.Thread(target=watch, daemon=True); th.start()
    s.menu("take_a_ride/miami"); s.wait_world(what="start")
    stop[0] = 1; time.sleep(0.1)
    s.record("transitions", detail="(t, (hell, lowg, anti, screen, frontend, hdr)) %s" % log)
    w2 = words(s); s.check("antipodean off in the level", w2["anti"] == 0, "%s" % w2)
