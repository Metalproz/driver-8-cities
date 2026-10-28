"""C84 / C80: Undercover > New Game plays the intro and starts the interview WITH its timer (selector patches off)."""
import time

SESSION = dict(day="var_polish_opt2d_day.lev", night="var_polish_opt2d_night.lev", s4=True)
TIMER, STORE, CLOCK, HITS = 0x801E4278, 0x801E0738, 0x801E0424, 0x801E0D7C


def run(s):
    s.menu("undercover/new_game")
    s.wait_for(lambda: s.word(0x80096834) == 2 and s.word(0x80096808) == 0xAE, 30, "interview level (CITY 2, mission 0xAE)")
    time.sleep(5)
    a = s.word(TIMER); time.sleep(3); b = s.word(TIMER)
    if a == b:                                      # a late start press may have paused the game
        s.press("start", gap=1.0); a = s.word(TIMER); time.sleep(3); b = s.word(TIMER)
    s.check("timer runs", b > a, "timer %#x -> %#x" % (a, b))
    s.check("overlay unpatched", (s.word(STORE), s.word(CLOCK), s.word(HITS)) == (0xAC824278, 0x0C078492, 0xAC8235B8),
            "%08x %08x %08x" % (s.word(STORE), s.word(CLOCK), s.word(HITS)))
    s.screenshot("interview")
    s.hold("cross")
    path, m = s.audio("interview_audio", secs=5.0)
    s.release()
    s.check("audio present", m.get("rms", 0) > 50, str(m))
