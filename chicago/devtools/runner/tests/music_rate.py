"""cheats 9 user: 'Chicago music much slower after: pick Hell -> play a Driver 1 map -> exit -> play Chicago'.
FIRST (miami; 'none' = straight to Chicago) with HELL=1, quit to the menu, Take a Ride SECOND (chicago): emulation
speed (VBlanks per wall second), FPS, the XM player words and 8 s of audio."""
import os, time
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)
VSYNC = 0x80095250


def quit_to_menu(s):
    s.press("start", gap=1.5)
    for _ in range(7): s.press("down", gap=0.4)
    s.press("cross", gap=1.0); s.press("left", gap=0.4); s.press("cross", gap=1.0)
    time.sleep(6)


def speed(s, secs=6.0):
    v0, t0 = s.word(VSYNC), time.time(); time.sleep(secs)
    v1, t1 = s.word(VSYNC), time.time()
    return round(((v1 - v0) & 0xFFFFFFFF) / (t1 - t0) / 59.94 * 100, 1)


def state(s, tag):
    w = {k: hex(s.word(a)) for k, a in dict(hell=0x8009342C, ngt=0x800933C8, xdd=0x80093408, mus=0x80096C88,
                                             mus_on=0x80096C78, song=0x80097298, c70=0x80096C70).items()}
    s.record("state", detail="%s: %s" % (tag, w))


def run(s):
    a, b = os.environ.get("FIRST", "miami"), os.environ.get("SECOND", "chicago")
    if os.environ.get("HELL", "1") == "1": s.poke32(0x8009342C, 1)
    if os.environ.get("INV", "1") == "1": s.poke32(0x8009681C, 1)       # Hell would wreck the standing player
    if a != "none":
        s.menu("take_a_ride/" + a); s.wait_world(what=a)
        if os.environ.get("HELL", "1") == "1": s.poke32(0x8009342C, 1)
        time.sleep(float(os.environ.get("PLAY", "25")))
        e1 = speed(s); state(s, a); s.record("speed", detail="%s: EMU %.1f %%" % (a, e1))
        s.audio("first_" + a, secs=6.0)
        quit_to_menu(s); s.screenshot("menu_after_quit")
    if a == "none":
        s.menu("take_a_ride/" + b)
    else:                     # back on the main menu with the cursor on Take A Ride (menu() starts from the title)
        s.press("cross"); time.sleep(1.5)
        for _ in range(7): s.press("down", gap=0.6)
        s.press("cross", gap=1.0); time.sleep(1); s.press("cross"); time.sleep(3); s.press("cross")
        s.wait_for(s.in_level, 120, "in level (%s)" % b); time.sleep(3)
    s.wait_world(what=b); time.sleep(8)
    state(s, b); s.screenshot(b)
    e2 = speed(s); fps = s.perf(4.0)[0]
    s.record("speed", detail="%s: EMU %.1f %%, FPS %.1f" % (b, e2, fps))
    s.audio("second_" + b, secs=8.0)
    s.check("%s runs at full speed" % b, e2 >= 97.0, "EMU %.1f %%" % e2)
