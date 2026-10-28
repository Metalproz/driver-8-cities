"""C81: Chicago night; the replay tape's write pointer is moved near its end -> "Out of Tape"; drive on, no hang."""
import math, time

SESSION = dict(day="var_polish_opt2d_day.lev", night="var_polish_opt2d_night.lev", s4=True)
TAPE_PTR, TAPE_END = 0x800BEED4, 0x800BEEE0       # player stream (FUN_80058814 / FUN_8005BFF0)
ROUTE = ((-101562, 106946), (0, 1))                 # l_down_e_N (Driver 2 coords, heading north)


def run(s):
    s.menu("take_a_ride/chicago/night")
    (x2, z2), (dx, dz) = ROUTE
    want = math.atan2(dx, dz)
    s.pose(int(x2 * 1.32 + 157724), int(z2 * 1.32 - 87099), want)
    s.drive(8, want)
    ptr, end = s.word(TAPE_PTR), s.word(TAPE_END)
    s.check("tape advancing", 0x1FA000 < (ptr & 0x1FFFFFFF) < (end & 0x1FFFFFFF), "ptr %08x end %08x" % (ptr, end))
    s.poke32(TAPE_PTR, ptr + 3 * ((end - 3 * 15 - ptr) // 3))
    hit = {}

    def tick(ss):
        if "t" not in hit and ss.word(TAPE_PTR) + 3 >= ss.word(TAPE_END):
            hit["t"] = time.time(); ss.record("out_of_tape", detail="pos %s" % (ss.pos(),))
        return "t" in hit and time.time() - hit["t"] > 1.0
    s.drive(60, want, tick)
    s.check("out of tape reached", "t" in hit)
    if "t" in hit:
        s.screenshot("out_of_tape")
    vs0, areas, last = s.word(0x80095250), 0, s.word(0x800972C0)
    t = time.time()                                  # 2 min on: game over / play again or keep driving
    while time.time() - t < 120:
        if s.car(0)[4] >= s.word(0x80096E7C) & 0xFFFF or not s.in_level():
            time.sleep(4)
            for b in ("down", "down", "down", "cross"):
                s.press(b, gap=0.5)
            time.sleep(4)
            s.pose(int(x2 * 1.32 + 157724), int(z2 * 1.32 - 87099), want)
        s.drive(10, want)
        a = s.word(0x800972C0)
        areas += a != last; last = a
    s.check("no hang after out of tape", s.alive(3.0), "vsync %d -> %d, area changes %d" % (vs0, s.word(0x80095250), areas))
    s.screenshot("end")
