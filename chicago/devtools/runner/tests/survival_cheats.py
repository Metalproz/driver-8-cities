"""C89: Invincibility / Immunity set before a Survival game stay on in the game (Driver 1 cleared them at the start)."""
import time

SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)
INV, IMM, GTYPE = 0x8009681C, 0x80096820, 0x800967F4


def run(s):
    s.press("triangle"); time.sleep(2)
    for b in ["right"] * 4 + ["cross"]:
        s.press(b)
    time.sleep(1.5)
    for _ in range(4):
        s.press("down", gap=0.6)
    s.poke32(INV, 1); s.poke32(IMM, 1)
    for k in range(6):                                  # Survival -> its city / start screens
        if s.in_level():
            break
        s.press("cross", gap=2.5)
    s.wait_for(s.in_level, 90, "Survival level")
    time.sleep(4)
    s.screenshot("survival")
    s.check("Survival started", s.word(GTYPE) == 0x13, "game type %#x" % s.word(GTYPE))
    s.check("Invincibility kept", s.word(INV) == 1, "0x8009681C = %d" % s.word(INV))
    s.check("Immunity kept", s.word(IMM) == 1, "0x80096820 = %d" % s.word(IMM))
