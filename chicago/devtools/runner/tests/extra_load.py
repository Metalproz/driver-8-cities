"""C135 (probe q73 freeze dumps): Take a Ride CITY (newtown | desert | interview) must load and run: CITY word = the level's
own index (7 / 6 / 2: the script's CITY opcode switched through the code-write path) and the game frame counter moves.
Before the fix the opcode write stayed in RAM only (native code kept LA's CITY): the load read REPLAY.BLK past the top of
RAM into the exception vectors (FAIL-FAST unknown dispatch)."""
import os, time
CITY = os.environ.get("CITY", "newtown")
WANT = {"newtown": 7, "desert": 6, "interview": 2}
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)


def run(s):
    s.menu("take_a_ride/" + CITY)
    s.wait_world(what=CITY)
    a = s.word(0x800970D8); time.sleep(4); moving = s.word(0x800970D8) != a
    c = s.word(0x80096834)
    s.record("level", detail="%s: CITY %d, frames moving %s, opcode %08X" % (CITY, c, moving, s.word(0x800689F8)))
    s.check("%s loads and runs (CITY %d)" % (CITY, WANT[CITY]), c == WANT[CITY] and moving and s.alive(), "CITY %d moving %s" % (c, moving))
