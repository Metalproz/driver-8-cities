"""C135 (probe q73, session 17:37: 'Los Angeles day' -> 'Take a Ride -> mission 0xAE (level 2)' -> level 6 -> crash): the
cursor passing Interview while browsing (after backing out of LA's Day/Night screen) already swaps the mission to 0xAE;
the confirmed row must still win (Desert / Newtown: LA's 0x7C + the CITY opcode 6 / 7). The 7d20d592 / 1fe1a6cd exes
crash here (stale CITY opcode, see extra_load); this is the user's exact log sequence.

Path: Take a Ride list -> LA (cross: Day/Night screen) -> back -> down to PASS (default interview) -> up / down to the
TARGET row (default desert) -> confirm. Checks: CITY word and mission number of the target, the level runs, alive."""
import os, time

SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)
ROWS = {"la": 2, "newtown": 4, "interview": 5, "desert": 6}
WANT = {"newtown": (7, 0x7C), "interview": (2, 0xAE), "desert": (6, 0x7C)}   # Newtown / Desert run LA's 0x7C + CITY opcode
PASS = os.environ.get("PASS", "interview")
TARGET = os.environ.get("TARGET", "desert")
MISSION, CITY, CURSOR = 0x80096808, 0x80096834, 0x801CE088


def state(s, tag):
    s.record("state", detail="%s: mission %02X CITY %d cursor %d" % (tag, s.word(MISSION), s.word(CITY), s.word(CURSOR)))


def run(s):
    s.press("triangle"); time.sleep(2)
    for b in ["right"] * 5 + ["cross"]:
        s.press(b)
    time.sleep(1.5)
    for _ in range(ROWS["la"]):
        s.press("down", gap=0.6)
    s.press("cross"); time.sleep(3)
    s.screenshot("la_day_night")
    state(s, "LA Day/Night screen")
    s.press("triangle"); time.sleep(2.5)
    state(s, "back on the list")
    for _ in range(ROWS[PASS] - ROWS["la"]):
        s.press("down", gap=0.8)
    time.sleep(1); state(s, "cursor on " + PASS)
    d = ROWS[TARGET] - ROWS[PASS]
    for _ in range(abs(d)):
        s.press("down" if d > 0 else "up", gap=0.8)
    time.sleep(1); state(s, "cursor on " + TARGET)
    s.screenshot("list_" + TARGET)
    s.press("cross"); time.sleep(3)
    if not s.in_level():
        s.press("cross")
    s.wait_for(s.in_level, 120, "in level (%s)" % TARGET)
    s.wait_world(what=TARGET)
    a = s.word(0x800970D8); time.sleep(4); moving = s.word(0x800970D8) != a
    c, m = s.word(CITY), s.word(MISSION)
    s.screenshot(TARGET)
    s.check("%s after browsing past %s: CITY %d, mission %02X" % (TARGET, PASS, WANT[TARGET][0], WANT[TARGET][1]),
            (c, m) == WANT[TARGET] and moving and s.alive(), "CITY %d mission %02X frames moving %s" % (c, m, moving))
