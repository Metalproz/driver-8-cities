"""C88 replay header: the new cheats go into 0x80097644 bits 4-7 at game start (LOWG 0x10, INFM 0x20, NGHT 0x40,
SPD2 0x80) next to Driver 1's bits 0-3, and the game still runs."""
import time
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)
LOWG, INFM, NGHT, SPD2, HDR = 0x8009D8E8, 0x800933C4, 0x800933C8, 0x800933CC, 0x80097644


def run(s):
    s.poke32(LOWG, 1); s.poke32(SPD2, 1); s.poke32(INFM, 0x100)    # + FEATHER (INFM word bit 0x100 -> bit 8)
    s.poke32(0x8009342C, 1)                                       # + HELL (C106: bit 9)
    s.menu("take_a_ride/chicago"); s.wait_world(what="start"); time.sleep(1)
    h = s.word(HDR)
    s.check("header bits at game start", h & 0x3F0 == 0x390, "0x80097644 = %08x (want bits 4-9 = 0x390: LOWG + SPD2 + FEATHER + HELL)" % h)
    s.check("alive", s.alive(2.0))
    s.screenshot("game")
