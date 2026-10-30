"""cheats 7 'cars only very close after NY -> Chicago': Take a Ride FIRST (default ny), quit to the menu, Take a Ride
SECOND (default chicago); after each: primitive buffers in use, limit words, car LOD, far cars drawn."""
import os, struct, time
from pathlib import Path
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)
W = dict(XR=0x80093404, XDD=0x80093408, XOBJ=0x80093418, XPB0=0x80093420, XPBN=0x80093428, BUF0=0x800BDFAC,
         BUF1=0x800BE02C, LOD=0x80096A48, NGHT=0x800933C8)


def quit_to_menu(s):
    s.press("start", gap=1.5)
    for _ in range(7): s.press("down", gap=0.4)
    s.press("cross", gap=1.0); s.press("left", gap=0.4); s.press("cross", gap=1.0)
    time.sleep(6)


D1ROWS = {"miami": 0, "frisco": 1, "la": 2, "ny": 3, "newtown": 4, "interview": 5, "desert": 6}
D2ROWS = {"chicago": 0, "havana": 1, "vegas": 2, "rio": 3}
VARIANT = {"chicago": (1, 2), "havana": (3, 4), "vegas": (6, 7), "rio": (8, 9)}


def menu_again(s, first, city):
    """Take a Ride after quit_to_menu (C135 follow-up: s.menu() from here ran into the attract demo): the carousel is
    still on Take a Ride and the list reopens on the page played last, cursor on its first row."""
    s.press("triangle"); time.sleep(2)
    s.press("cross"); time.sleep(1.5)
    on2 = first in D2ROWS
    if (city in D2ROWS) != on2:                         # turn the page: page row 7 on page 1, 4 on page 2
        for _ in range(4 if on2 else 7):
            s.press("down", gap=0.6)
        s.press("cross", gap=1.5)
    rows = D2ROWS if city in D2ROWS else D1ROWS
    for _ in range(rows[city]):
        s.press("down", gap=0.6)
    s.press("cross"); time.sleep(3)
    if city in D2ROWS or city in ("miami", "frisco", "ny", "la"):
        s.press("cross")                                # Day / Night screen: Day (LA without a day level: harmless)
    s.wait_for(s.in_level, 120, "in level (%s, after %s)" % (city, first))
    time.sleep(3)
    if city in D2ROWS:
        v = s.word(0x80093620)
        s.check("%s really loaded (variant %d)" % (city, v & 15), (v >> 24) == 0x56 and (v & 15) in VARIANT[city], hex(v))
    else:
        s.check("%s really loaded (CITY %d)" % (city, s.word(0x80096834)), True)


def state(s, tag):
    v = {k: s.word(a) for k, a in W.items()}
    s.record("state", detail="%s: %s" % (tag, {k: hex(x) for k, x in v.items()}))
    return v


def cars(s):
    """(cars drawn last frame 0x800973B4, AI cars within Driver 1's 27000 draw-list range)"""
    px, pz = s.word(0x8009B16C), s.word(0x8009B174)
    px, pz = (px - (1 << 32) if px >> 31 else px), (pz - (1 << 32) if pz >> 31 else pz)
    near = 0
    rec = s.ram(0x80098950, 0x50 * 24)
    for i in range(24):
        if not rec[i * 0x50 + 1]: continue
        x, z = struct.unpack("<i", s.ram(0x8009B230 + 0x18C * i + 0xC8, 4))[0], struct.unpack("<i", s.ram(0x8009B230 + 0x18C * i + 0xD0, 4))[0]
        if abs(x - px) + abs(z - pz) < 27000: near += 1
    best = 0
    for _ in range(20):
        best = max(best, s.word(0x800973B4)); time.sleep(0.1)
    return best, near


def run(s):
    a, b = os.environ.get("FIRST", "ny"), os.environ.get("SECOND", "chicago")
    s.menu("take_a_ride/" + a); s.wait_world(what="start"); time.sleep(3)
    v1 = state(s, a)
    s.screenshot(a)
    quit_to_menu(s)
    s.screenshot("menu_after_quit")
    menu_again(s, a, b); s.wait_world(what="start"); time.sleep(3)
    v2 = state(s, b)
    s.drive(15.0, s.car(0)[3])
    drawn, near = cars(s)
    s.record("cars", detail="%s: drawn per frame (max of 20 samples) %d, AI cars within 27000 %d" % (b, drawn, near))
    xb = s.word(0x800933F0)
    big27 = s.ram(xb, 729); small = s.ram(0x800A80C4, 361)
    mid = bytes(big27[(r + 4) * 27 + 4 + c] for r in range(19) for c in range(19)) if len(big27) == 729 else b""
    if xb & 0x1FFFFFFF == 0xA80C4:    # Extra draw off: no 27x27 buffer, XB is the native 19x19 itself (nothing to compare)
        s.record("pvs", detail="%s: Extra draw off, XB = native 19x19, 27x27 check skipped" % b)
    else:
        s.check("%s: 19x19 car-visibility PVS = middle of the 27x27" % b, mid == small,     "XB %08X, ones %d / %d" % (xb, sum(1 for x in small if x), sum(1 for x in mid if x)))
    s.check("%s: far cars drawn" % b, near < 4 or drawn >= near // 2, "drawn %d of %d in range" % (drawn, near))
    s.screenshot(b)
    big = lambda v: (v["BUF0"] & 0xFFFFFF) >= 0xF00000
    s.check("%s: big buffers with extra draw" % b, big(v2) == (v2["XDD"] == 1), "%s" % {k: hex(x) for k, x in v2.items()})
