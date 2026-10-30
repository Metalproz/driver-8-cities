"""C138 (Havana mini = D2 model 12, choice 0): the player car's shadow quad = the chosen car's D2 size from the level's
.pps.bin (car 0's SHD offsets 0x80093480 on top of Driver 1's fixed 370 x 1040 corners) and the car light glows at
Driver 2's fixed sizes (14 ShowCarlight immediates) while a D2 city runs.

CITY (default havana), NIGHT=1 for night; needs CHI_<CITY>_DAY / _NIGHT = levels with a .pps.bin (hav9). Start shot
(as Polish's before-shots 20261030-010048 / -010135), checks, then DRIVE s (default 10) straight on (crash into whatever
is ahead: wall / traffic), shot, alive. Checks: shadow quad = .pps.bin size (+-8), light words = D2, physics corners
unchanged (370 x 1040)."""
import math, os, struct, time

SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)
CITY = os.environ.get("CITY", "havana")
NIGHT = os.environ.get("NIGHT") == "1"
DRIVE = float(os.environ.get("DRIVE", "10"))
CAR = 0x8009B0A4
LIGHT_D2 = {0x80043970: 0x24070012, 0x800439A8: 0x24070012, 0x80043BB0: 0x2407001A, 0x80043BF8: 0x2407001A,
            0x80043C64: 0x2407001A, 0x80043CBC: 0x2407001A, 0x80043DF4: 0x24070016, 0x80043E3C: 0x24070016,
            0x80046398: 0x24070018, 0x800463F0: 0x24070018, 0x800464AC: 0x24070018, 0x80046504: 0x24070018,
            0x800465A8: 0x24070016, 0x800465F4: 0x24070016}


def s32(v):
    return v - (1 << 32) if v >> 31 else v


def quad(s, with_shd):
    """(length, width) of car 0's shadow quad: corners P0 P1 P3 P2 (+0x88 / 98 / A8 / B8) (+ SHD offsets), read in one
    block while the game is paused (separate reads of a moving / wrecked car gave sizes off by up to 40 %), measured along
    the quad's own axes like the plugin's stretch (axis = side midpoint - centre)."""
    s.d.cmd("pause")
    try:
        c = s.ram(CAR + 0x88, 0x40)
        shd = s.ram(0x80093480, 16)
    finally:
        s.d.cmd("continue")
    p = []
    for k in range(4):
        x, z = struct.unpack_from("<i", c, 0x10 * k)[0], struct.unpack_from("<i", c, 0x10 * k + 8)[0]
        if with_shd:
            dx, dz = struct.unpack_from("<hh", shd, 4 * k)
            x, z = x + dx, z + dz
        p.append((x, z))
    cx, cz = sum(q[0] for q in p) / 4, sum(q[1] for q in p) / 4
    a = 2 * math.dist(((p[0][0] + p[1][0]) / 2, (p[0][1] + p[1][1]) / 2), (cx, cz))
    b = 2 * math.dist(((p[0][0] + p[2][0]) / 2, (p[0][1] + p[2][1]) / 2), (cx, cz))
    return max(a, b), min(a, b)


def run(s):
    s.menu("take_a_ride/%s%s" % (CITY, "/night" if NIGHT else "")); s.wait_world(what=CITY)
    time.sleep(1.0)
    s.screenshot("start")
    pk = s.copy_dir / "mods" / "packages" / "driver.chicago" / "0.1.0" / "assets" / (CITY if CITY != "chicago" else "")
    f = pk / ("plrshadow_%s.bin" % ("night" if NIGHT else "day"))
    choice = s.word(0x8009683C) & 3
    want = None
    if f.exists():
        d = f.read_bytes()
        e = struct.unpack_from("<12i", d, 8 + 48 * choice)
        xs, zs = e[1:9:2], e[2:9:2]
        want = (max(zs) - min(zs), max(xs) - min(xs), e[0])
    phys, shd = quad(s, False), quad(s, True)
    s.record("shadow", detail="choice %d D2 model %s: physics quad %.0f x %.0f, shadow quad %.0f x %.0f, want %s"
             % (choice, want[2] if want else "?", phys[0], phys[1], shd[0], shd[1], want[:2] if want else None))
    s.check("plrshadow asset in the package", want is not None, str(f))
    if want:
        s.check("shadow quad = the car's D2 size (+-8)", abs(shd[0] - want[0]) <= 8 and abs(shd[1] - want[1]) <= 8,
                "%.0f x %.0f vs %d x %d" % (shd[0], shd[1], want[0], want[1]))
    s.check("physics corners unchanged (Driver 1's 1040 x 370)", abs(phys[0] - 1040) <= 16 and abs(phys[1] - 370) <= 16,
            "%.0f x %.0f" % phys)
    bad = {hex(a): hex(s.word(a)) for a, v in LIGHT_D2.items() if s.word(a) != v}
    s.check("light sizes = Driver 2's (14 words)", not bad, str(bad))
    x, y, z, h, _ = s.car(0)
    s.drive(DRIVE, h)
    time.sleep(1.0)
    s.screenshot("after_drive")
    shd2, phys2 = quad(s, True), quad(s, False)
    s.record("after", detail="damage %d, physics quad %.0f x %.0f, shadow quad %.0f x %.0f"
             % (s.word(0x8009B220) & 0xFFFF, phys2[0], phys2[1], shd2[0], shd2[1]))
    if want:   # the plugin stretches to the D2 size along the quad's axes every vblank, whatever the (wrecked) corners
        s.check("shadow still the D2 size after the drive / crash (paused read)",
                abs(shd2[0] - want[0]) <= 8 and abs(shd2[1] - want[1]) <= 8,
                "%.0f x %.0f vs %d x %d (physics %.0f x %.0f)" % (shd2[0], shd2[1], want[0], want[1], phys2[0], phys2[1]))
    s.check("alive", s.alive())
