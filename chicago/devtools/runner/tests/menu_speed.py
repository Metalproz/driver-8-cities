"""C100: host speed (EMU %) standing in the main menu (frontend) for 10 s, with whatever RUNNER_UNCAP / RUNNER_XDRAW."""
import os, time
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)


def run(s):
    s.press("triangle"); time.sleep(3)
    v0, t0 = s.word(0x80095250), time.time(); time.sleep(10)
    emu = ((s.word(0x80095250) - v0) & 0xFFFFFFFF) / (time.time() - t0) / 59.94 * 100
    s.record("menu", detail="uncap %s xdraw %s: menu EMU %.0f %%" % (os.environ.get("RUNNER_UNCAP"), os.environ.get("RUNNER_XDRAW"), emu))
