"""C88: a new cheat blocks high scores like Driver 1's own cheats: FUN_8006C964's record flag 0x80096F00 is written
from the 'cheat on' path 0x8006CA80 (Survival, SUPER SPEED on) and not from it without cheats."""
import time
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)
SPD2, FLAG = 0x800933CC, 0x00096F00


def survival(s):
    s.press("triangle"); time.sleep(2)
    for b in ["right"] * 4 + ["cross"]:
        s.press(b)
    time.sleep(1.5)
    for _ in range(4):
        s.press("down", gap=0.6)
    for k in range(6):
        if s.in_level():
            break
        s.press("cross", gap=2.5)
    s.wait_for(s.in_level, 90, "Survival level"); time.sleep(3)


def writers(s):
    r = s.d.cmd("wtrace_dump", addr_lo="0x%08X" % FLAG, addr_hi="0x%08X" % (FLAG + 4), count=20)
    return sorted({"%s ra %s v1 %s" % (e["pc"], e["ra"], e["v1"]) for e in r.get("entries", [])})


def run(s):
    import dt
    s.d.cmd("wtrace_range", lo="0x%08X" % FLAG, hi="0x%08X" % (FLAG + 4))
    survival(s)
    mx = s.word(dt.MAX_DAMAGE) & 0xFFFF
    for k in range(2): s.d.cmd("write_ram", addr="0x%08X" % (dt.DAMAGE + k), val=(mx >> (8 * k)) & 0xFF)
    s.d.cmd("wtrace_clear")
    dt.play_again(s.d)
    s.wait_for(lambda: writers(s), 30, "restart without cheats", fail=False)
    off = writers(s)
    s.record("no cheat", detail="0x80096F00 written by %s, value %d" % (off, s.word(0x80096F00)))
    s.d.cmd("wtrace_clear"); s.poke32(SPD2, 1)
    mx = s.word(dt.MAX_DAMAGE) & 0xFFFF
    for k in range(2): s.d.cmd("write_ram", addr="0x%08X" % (dt.DAMAGE + k), val=(mx >> (8 * k)) & 0xFF)
    time.sleep(2); dt.play_again(s.d)
    s.wait_for(lambda: writers(s), 30, "restart with SUPER SPEED", fail=False)
    s.screenshot("restart2")
    on = writers(s)
    s.record("super speed", detail="0x80096F00 written by %s, value %d" % (on, s.word(0x80096F00)))
    s.check("cheat path taken with SUPER SPEED", any(w.startswith("0x8006CA80") and " v1 0x00000001" in w for w in on), "%s" % on)
    s.check("not taken without cheats", not any(" v1 0x00000001" in w and w.startswith("0x8006CA80") for w in off), "%s" % off)
    s.check("alive", s.alive(2.0))
