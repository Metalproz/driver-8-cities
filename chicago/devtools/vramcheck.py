"""vramcheck.py - runtime VRAM check for the car textures (R32 memory-safety audit): drives Chicago on a devtest copy of
build-test and compares VRAM at the tpages of the given level pages (the permanent car pages 5-8 and the chosen player
car's special pair 13-14 by default) with the level's own texels; prints the mismatching texels per 64-px block whenever
they change (and a screenshot). Areas pages are not checked (they stream).

    python driver_personal/chicago/devtools/vramcheck.py OUT LEVEL [--copy d2c] [--port 4462] [--prep] [--secs 120]
           [--pages 5,6,7,8,13,14]
"""
import argparse, os, sys, time, struct, collections
from pathlib import Path
CHI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHI / "devtools")); sys.path.insert(0, str(CHI))
ap = argparse.ArgumentParser()
ap.add_argument("out"); ap.add_argument("lev")
ap.add_argument("--copy", default="d2c"); ap.add_argument("--port", type=int, default=4462)
ap.add_argument("--prep", action="store_true"); ap.add_argument("--secs", type=int, default=120)
ap.add_argument("--pages", default="5,6,7,8,13,14")
a = ap.parse_args()
os.environ.update(CHI_TEST_BUILD="build-test", CHI_SLOT="1", CHI_MENU_PAGES="1")
import dt
from levfile import Lev
from texpages import read_pages
OUT = Path(a.out).resolve(); OUT.mkdir(parents=True, exist_ok=True)
PAGES = [int(p) for p in a.pages.split(",")]
ti, tp = read_pages(Lev.parse(open(a.lev, "rb").read()))
if a.prep:
    st = open(CHI / "devtools" / "cellprobe.py").read().split('STATE = """')[1].split('"""')[0]
    d0 = dt.prepare(a.copy, None, a.lev)
    (d0 / "mods" / "state.toml").write_text(st)
p, d = dt.launch(a.copy, a.port)
W = d.word


def vram_page(tpage):
    x0, y0 = (tpage & 15) * 64, ((tpage >> 4) & 1) * 256
    words = {}
    for by in range(0, 256, 128):
        hx = d.cmd("vram_peek", x=x0, y=y0 + by, w=64, h=128)["hex"]
        for i in range(64 * 128):
            words[(i % 64, by + i // 64)] = int(hx[4 * i: 4 * i + 4], 16)
    return words


MASK = {}


def compare(page, words):
    pg = tp[page]
    if page not in MASK:                  # only texels inside the page's textures count (free space may hold anything)
        m = bytearray(256 * 256)
        for e in ti.details[page]:
            w, h = e[4] or 256, e[5] or 256
            for y in range(e[3], min(256, e[3] + h)):
                m[y * 256 + e[2]: y * 256 + min(256, e[2] + w)] = bytes([1]) * (min(256, e[2] + w) - e[2])
        MASK[page] = m
    m = MASK[page]
    bad = collections.Counter()
    for (wx, y), v in words.items():
        for k in range(4):
            x = 4 * wx + k
            if m[y * 256 + x] and ((v >> (4 * k)) & 15) != pg.get(x, y):
                bad[x // 64, y // 64] += 1
    return bad


try:
    while (d.frame() or 0) < 2300: time.sleep(0.1)
    for b in ["right"] * 5 + ["cross"]: d.press(b, hold=0.12, gap=0.8)
    time.sleep(1.5)
    d.press("up", hold=0.12, gap=0.5); time.sleep(0.5); d.press("cross", hold=0.12, gap=0.8); time.sleep(1.0)
    d.press("cross", hold=0.12, gap=0.8); time.sleep(3)
    d.press("cross", hold=0.12, gap=0.8)
    t0 = time.time()
    while time.time() - t0 < 90 and not (W(dt.CITY) == 3 and tuple(d.pos()) != (0, 0, 0)): time.sleep(0.5)
    time.sleep(4)
    tps = struct.unpack("<24H", d.ram(0x80086F30, 48))
    last = None; t1 = time.time(); k = 0
    mc = 0xFFFF & ~(1 << dt.BTN["cross"])
    while True:
        res = {pg: compare(pg, vram_page(tps[pg])) for pg in PAGES}
        summary = {pg: sum(b.values()) for pg, b in res.items()}
        if summary != last:
            print("t %3.0f pos %s mismatching texels %s %s" % (time.time() - t1, d.pos(), summary,
                  {pg: sorted(b.items())[:6] for pg, b in res.items() if b}), flush=True)
            d.shot(OUT / ("t%03d.png" % int(time.time() - t1)))
            last = summary
        if time.time() - t1 > a.secs:
            break
        d.cmd("set_input", buttons="0x%04X" % (mc & ~(1 << dt.BTN["left"]) if k % 4 == 3 else mc))
        time.sleep(4.0); k += 1
    d.cmd("set_input", buttons="0xFFFF")
    print("end: alive", dt.alive(d, 2.0), flush=True)
finally:
    p.kill(); time.sleep(1)
