"""C88 menu (layout 2): page 1 = Driver 1's list (CREDITS .. STILTS, ANTIPODEAN) + PAGE 2 at the bottom; page 2 = LOW
GRAVITY, INFINITE MASS, SUPER SPEED, NIGHTMARE, FEATHER, HELL + PAGE 1. Toggles go to the true words when
the screen is left; Driver 1's tables come back."""
import time
from PIL import Image

SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)
CUR, ROWS, UNL = 0x801D2E48, 0x800967D8, 0x8008671C
LOWG, ANTI, INFM, SPD2, INV = 0x8009D8E8, 0x8009D8EC, 0x800933C4, 0x800933CC, 0x8009681C


def goto(s, row):
    for _ in range(10):
        c = s.word(CUR)
        if c == row:
            return True
        s.press("down" if c < row else "up", gap=0.4)
    return s.word(CUR) == row


def run(s):
    s.press("triangle"); time.sleep(2)
    unlock0 = [s.word(UNL + 0x38 * k) for k in range(8)]
    for b in ["right"] * 3 + ["cross"]:
        s.press(b)
    time.sleep(1.5)
    s.check("cheats screen", s.word(0x801CDE5C) == 6)
    p1 = s.screenshot("page1")
    vis1 = [k for k in range(s.word(ROWS)) if s.word(UNL + 0x38 * k) == 0xFFFFFFFE]
    s.check("page 1 rows 0-7 visible", vis1 == list(range(8)), "%s" % vis1)
    goto(s, 6); s.press("cross", gap=0.6)                     # ANTIPODEAN (row 6 proxy)
    goto(s, 7); s.press("cross", gap=0.8)                     # PAGE 2
    p2 = s.screenshot("page2")
    vis2 = [k for k in range(s.word(ROWS)) if s.word(UNL + 0x38 * k) == 0xFFFFFFFE]
    s.check("page 2 rows", vis2 == [1, 2, 3, 4, 5, 6, 7] and s.word(CUR) == 1, "visible %s, cursor %d" % (vis2, s.word(CUR)))
    s.press("down", gap=0.4)
    s.check("cursor skips nothing it should not", s.word(CUR) == 2, "cursor %d" % s.word(CUR))
    s.press("cross", gap=0.6)                                 # INFINITE MASS
    goto(s, 1); s.press("cross", gap=0.6)                     # LOW GRAVITY
    goto(s, 7); s.press("cross", gap=0.8)                     # PAGE 1 (row 6 = HELL since C99)
    s.check("back on page 1", s.word(ROWS) == 8 and s.word(CUR) == 7, "rows %d cursor %d" % (s.word(ROWS), s.word(CUR)))
    s.press("triangle", gap=1.5)
    got = dict(lowg=s.word(LOWG), anti=s.word(ANTI), infm=s.word(INFM), spd2=s.word(SPD2), inv=s.word(INV))
    s.check("true words after leaving", got == dict(lowg=1, anti=1, infm=0x20, spd2=0, inv=0), "%s" % got)
    unlock1 = [s.word(UNL + 0x38 * k) for k in range(8)]
    s.check("tables restored", unlock1 == unlock0 and s.word(ROWS) == 8, "%s" % ["%x" % v for v in unlock1])
    a, b = Image.open(p1), Image.open(p2)
    sh = Image.new("RGB", (a.width + b.width, a.height)); sh.paste(a, (0, 0)); sh.paste(b, (a.width, 0)); sh.save(str(s.dir / "pages.png"))
