"""C90 / user 66: with Nightmare on, the felony meter is full on every map of the session: Miami, back to the menu,
then Chicago."""
import time
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)


def quit_to_menu(s):
    s.press("start", gap=1.5)
    for _ in range(7): s.press("down", gap=0.4)
    s.press("cross", gap=1.0); s.press("left", gap=0.4); s.press("cross", gap=1.0)
    time.sleep(5)                                        # the menu (before the attract demo starts)


def run(s):
    s.poke32(0x8009681C, 1); s.poke32(0x800933C8, 1)
    fel = []
    for city in ("miami", "chicago"):
        if fel: quit_to_menu(s)
        s.menu("take_a_ride/" + city); s.wait_world(what="start"); time.sleep(5)
        f = [s.word(0x80097708) for _ in range(5) if not time.sleep(1.0)]
        fel.append((city, min(f)))
    s.check("felony full on both maps", all(v >= 0x1000 for _, v in fel), "%s" % fel)
