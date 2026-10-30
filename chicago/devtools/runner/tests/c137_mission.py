"""C137 step 2: Driver 1 missions keep their bank 4 (the Take a Ride skip is D2-city only). Undercover new game (first
mission): lump byte 0x8008A985 = 00 and the bank 4 table holds samples once the level runs."""
import struct, time

SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)


def run(s):
    s.menu("undercover/new_game")
    time.sleep(5)
    t = s.ram(0x800BCA74 + 0x800, 16 * 32)
    n = sum(1 for k in range(32) if struct.unpack_from("<I", t, 16 * k)[0])
    lb = s.ram(0x8008A985, 1)[0]
    s.record("mission", detail="mission %02X CITY %d, lump byte %02X, bank 4 entries %d"
             % (s.word(0x80096808), s.word(0x80096834), lb, n))
    s.screenshot("mission")
    s.check("Undercover mission: lump byte 00, bank 4 loaded", lb == 0 and n > 0, "lump %02X entries %d" % (lb, n))
    s.check("alive", s.alive())
