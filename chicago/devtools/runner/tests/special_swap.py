"""C135 (probe q73: crash in the far-car drawer FUN_8002E230 while driving Rio after Las Vegas): each special id got ONE
guest block, sized for the first city's special of that id, and every later city copied its own special into it (Rio 8 =
13684 bytes into Vegas 8's 13460): the low model's tail lay in the next allocation and was overwritten there.

FIRST (default vegas), quit, CITY (default rio), with CHI_SPC_CYCLE (default 3 s) so several specials load in each city.
Every new clean[5] pointer is matched to its asset entry; its block [clean, low + low size) is recorded.
Checks: no two special blocks overlap; the low model of each special has valid polygon type bytes; the game is alive.
The old exe fails the overlap check (Rio 8 runs into Vegas 10's block)."""
import os, struct, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))   # chicago/ (models.py)
from models import POLY_SIZES

CYCLE = os.environ.get("CHI_SPC_CYCLE", "3")
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True,
               env={"CHI_SPC_CYCLE": CYCLE})
FIRST = os.environ.get("FIRST", "vegas")
CITY = os.environ.get("CITY", "rio")
SECS = float(os.environ.get("SECS", "14"))
D2ROWS = {"chicago": 0, "havana": 1, "vegas": 2, "rio": 3}
VARIANT = {"chicago": (1, 2), "havana": (3, 4), "vegas": (6, 7), "rio": (8, 9)}   # VARIANT_WORD 0x80093620 & 15, day / night
CLEAN5, LOW5 = 0x800A1AC4, 0x800A11F8 + 20
r4 = lambda x: (x + 3) & ~3


def entries(assets, city):
    """{special id: (clean bytes, low bytes)} of the city's specials_day.bin (layout of driver_chicago.c spc_entry)."""
    a = (assets / ("" if city == "chicago" else city) / "specials_day.bin").read_bytes()
    mg, cnt = struct.unpack_from("<II", a, 0)
    p, blk = (60, struct.unpack_from("<i", a, 56)[0]) if mg == 0x53504332 else (28, 0)
    out = {}
    for _ in range(cnt):
        h = struct.unpack_from("<8i", a, p)
        c, d, l = h[2], h[3], h[4]
        q = p + 32 + 820
        out[h[0]] = (a[q:q + c], a[q + r4(c) + r4(d):q + r4(c) + r4(d) + l])
        p += 32 + 820 + r4(c) + r4(d) + r4(l) + blk
    return out


def poly_types_ok(s, base, size):
    """walk the model's polygons as FUN_8002E230 does (type byte, Driver 1 sizes); True when every type is drawable"""
    data = s.ram(base, size)
    npol = struct.unpack_from("<H", data, 0xE)[0]
    q = struct.unpack_from("<I", data, 0x14)[0] - base
    bad = 0
    for _ in range(npol):
        if q < 0 or q >= len(data):
            return False, "polygon walk left the model at %d" % q
        t = data[q]
        if not (t < 12 or 16 <= t < 24):                  # the drawer indexes 0x80089FFC with the whole byte
            bad += 1
        q += POLY_SIZES.get(t & 31, 8)
    return bad == 0, "%d polygons, %d bad type bytes" % (npol, bad)


def watch(s, city, ents, blocks, secs):
    last = None
    t = time.time()
    while time.time() - t < secs:
        mc, ml = s.word(CLEAN5), s.word(LOW5)
        time.sleep(0.1)                                  # the plugin writes clean[5] .. low[5] in one vblank; two TCP
        if (mc, ml) != (s.word(CLEAN5), s.word(LOW5)) or (ml and not mc < ml < mc + 0x8000):   # reads can straddle it
            continue
        if mc and (mc, ml) != last:
            last = (mc, ml)
            head = s.ram(mc, 0x40)
            sid = next((k for k, (c, _l) in ents.items() if len(c) >= 0x40 and head[:0x10] == c[:0x10]
                        and head[0x20:0x40] == c[0x20:0x40]), None)
            if sid is None:
                s.record("special", ok=False, detail="%s: clean[5] %08X matches no asset entry" % (city, mc))
            else:
                low = ents[sid][1]
                end = (ml + len(low)) if ml else (mc + len(ents[sid][0]))
                ok, why = poly_types_ok(s, ml, len(low)) if ml else (True, "no low model")
                blocks.append((city, sid, mc, end, ok, why))
                s.record("special", ok=ok, detail="%s special %d: block %08X..%08X (%d bytes), low %08X: %s"
                         % (city, sid, mc, end, end - mc, ml, why))
        time.sleep(0.25)


def run(s):
    assets = Path(s.dir).parents[2] / s.copy / "mods" / "packages" / "driver.chicago" / "0.1.0" / "assets"   # devtest/<copy>
    blocks = []
    s.menu("take_a_ride/" + FIRST); s.wait_world(what=FIRST)
    watch(s, FIRST, entries(assets, FIRST), blocks, SECS)
    import importlib.util as iu
    sp = iu.spec_from_file_location("cs_", os.path.join(os.path.dirname(os.path.abspath(__file__)), "city_switch.py"))
    cs_ = iu.module_from_spec(sp); sp.loader.exec_module(cs_)
    cs_.quit_to_menu(s)
    s.press("triangle"); time.sleep(2)
    s.press("cross"); time.sleep(1.5)                  # the carousel is still on Take a Ride; page 2, cursor on Chicago
    for _ in range(D2ROWS[CITY]):
        s.press("down", gap=0.8)
    s.press("cross"); time.sleep(3); s.press("cross")
    s.wait_for(s.in_level, 120, "in level (%s)" % CITY)
    s.wait_world(what=CITY)
    v = s.word(0x80093620) & 15
    s.record("city", ok=v in VARIANT[CITY], detail="%s: variant word %d" % (CITY, v))
    watch(s, CITY, entries(assets, CITY), blocks, SECS)
    s.drive(8.0, s.car(0)[3])
    over = []
    uniq = {}
    for b in blocks:
        uniq.setdefault((b[2], b[3]), b)
    ub = sorted(uniq.values(), key=lambda b: b[2])
    for i in range(len(ub)):
        for j in range(i + 1, len(ub)):
            a, b = ub[i], ub[j]
            if a[2] != b[2] and a[2] < b[3] and b[2] < a[3]:
                over.append("%s %d %08X..%08X / %s %d %08X..%08X" % (a[0], a[1], a[2], a[3], b[0], b[1], b[2], b[3]))
    cities = {b[0] for b in blocks}
    s.check("specials loaded in both cities", FIRST in cities and CITY in cities, "%d loads: %s" % (len(blocks), sorted(cities)))
    s.check("no two special blocks overlap", not over, "; ".join(over) or "%d distinct blocks" % len(ub))
    s.check("low models' polygon types valid", all(b[4] for b in blocks), "; ".join("%s %d: %s" % (b[0], b[1], b[5]) for b in blocks if not b[4]))
    s.check("alive after the drive", s.alive())
