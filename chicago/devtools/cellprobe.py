"""Probe a Chicago test copy at a D2 spot (dt.launch copy; Infrastructure 14.10.).
    python cellprobe.py PORT OUT LEVEL --start=D2X,D2Z --legs=0,0,0 [--build build-test]
  env CP_PTS="x,z;..." CP_R=n   road-map cells (surface id / height / water / road flag) around D1 points + plane lists
  env CP_NEAR=1                 put the player next to the nearest live traffic car, 6 screenshots (near0..5.png) +
                                that car's model index and position (D2 cars: body visible? ride height?)
  env CP_COS=1 / CP_HEAP=1      cosmetics rows at load / heap + cell-buffer sizes
  env C42_NIGHT=1               night (menu: Day/Night down)"""
import argparse, math, os, subprocess, sys, time, json

CHI = "D:/recomps/Apps/Driver-DriverRecompiled/driver_personal/chicago"
GF = os.path.normpath(os.path.join(CHI, "..", "..", "psxrecomp", "tools", "gpu_frame_capture.py"))

ap = argparse.ArgumentParser()
ap.add_argument("port", type=int); ap.add_argument("out"); ap.add_argument("lev"); ap.add_argument("--start", default=""); ap.add_argument("--legs", required=True)
ap.add_argument("--build", default="build-test"); ap.add_argument("--thresh", type=float, default=0.018)
ap.add_argument("--runs", type=int, default=1)
a = ap.parse_args(); a.lev = os.path.abspath(a.lev); a.out = os.path.abspath(a.out)   # shots are written by the game
os.environ["CHI_TEST_BUILD"] = a.build; os.environ["CHI_SLOT"] = "1"; os.environ["CHI_MENU_PAGES"] = "1"
sys.path.insert(0, os.path.join(CHI, "devtools")); sys.path.insert(0, CHI)
import dt
from PIL import Image

STATE = """format_version = 2

[[package]]
id = "driver.chicago"
version = "0.1.0"

[[package]]
id = "driver.personal"
version = "1.0.0"

[[feature]]
package_id = "driver.personal"
id = "skip-intro"
enabled = true

[[feature]]
package_id = "driver.personal"
id = "unlock-all"
enabled = true

[[feature]]
package_id = "driver.chicago"
id = "model-table"
enabled = true

[[feature]]
package_id = "driver.chicago"
id = "chicago-slot"
enabled = true
values = { city = "la" }
"""
AREA = 0x800972C0                       # low byte: current area
start = tuple(int(v) for v in a.start.split(",")) if a.start else None
legs = [tuple(map(float, l.split(","))) for l in a.legs.split(";")]


def dark_fraction(path):
    im = Image.open(path).convert("L"); w, h = im.size
    band = im.crop((0, int(h * 0.08), w, int(h * 0.40))).point(lambda v: 255 if v < 28 else 0)
    return sum(band.histogram()[255:]) / (band.size[0] * band.size[1])



RM_HEADER, RM_TABLES, RM_PARITY = 0x8009E714, 0x8009D8F4, 0x80097374
def cell_word(d, x, z):
    w, h, ox, oz = [d.word(RM_HEADER + 4 * i) for i in range(4)]
    w, h = [v - (1 << 32) if v >= 1 << 31 else v for v in (w, h)]
    ox, oz = [v - (1 << 32) if v >= 1 << 31 else v for v in (ox, oz)]
    sx, sz = x + ox, oz + 750 - z
    if sx < 0 or sz < 0: return None
    col, row = sx // 1500, sz // 1500
    if col >= w or row >= h: return None
    ca = (col & 0x7F) + ((col & ~0x7F) >> 4); ra = (row & 0x7F) + ((row & ~0x7F) >> 4)
    if ca >= 120: ca -= 120
    if ra >= 120: ra -= 120
    q, par = 0, d.word(RM_PARITY) & 1
    if ca >= 60: ca -= 60; q = 1
    if ra >= 60:
        ra -= 60
        if not par: q += 2
    elif par: q += 2
    t = d.word(RM_TABLES + 4 * q)
    if not (0x10000 <= (t & 0x1FFFFFFF) < 0x200000): return ("notab", col, row)
    v = d.word(t + 4 * ca + 240 * ra)
    hgt = v & 0xFFF8; hgt = hgt - 0x10000 if hgt >= 0x8000 else hgt
    return (col, row, (v >> 16) & 0x3FF, hgt, v >> 30, hex(v & 7))

def one_run(out):
    os.makedirs(out, exist_ok=True)
    d0 = dt.prepare("cellprobe", start, a.lev)
    (d0 / "mods" / "state.toml").write_text(STATE)
    p, d = dt.launch("cellprobe", a.port)
    try:
        while (d.frame() or 0) < 2300: time.sleep(0.1)
        for b in ["right"] * 5 + ["cross"]: d.press(b, hold=0.12, gap=0.8)
        time.sleep(1.5)
        d.press("up", hold=0.12, gap=0.5); time.sleep(0.5); d.press("cross", hold=0.12, gap=0.8); time.sleep(1.0)
        d.press("cross", hold=0.12, gap=0.8); time.sleep(3)
        if os.environ.get("C42_NIGHT") == "1": d.press("down", hold=0.12, gap=0.6)
        d.press("cross", hold=0.12, gap=0.8)
        t0 = time.time(); last = None; since = None
        while time.time() - t0 < 90:
            pos = tuple(d.pos()); ok = pos != (0, 0, 0) and abs(pos[1]) < 10000 and d.word(dt.CITY) == 3
            if ok and last == pos:
                since = since or time.time()
                if time.time() - since >= 2: break
            else: since = None
            last = pos if ok else None
            time.sleep(0.5)
        pos = d.pos(); print("player", pos, "area", d.word(AREA) & 0xFF, flush=True)
        d.shot(os.path.join(out, "spawn.png"))
        if os.environ.get("CP_NEAR"):
            import struct as _st
            B = 0x8009B0A4
            for shot in range(6):
                blk = d.ram(B, 0x18C * 12); pp = d.pos()
                cars = []
                for i in range(1, 12):
                    cx, cy, cz = _st.unpack_from("<3i", blk, i * 0x18C + 0x18)
                    if (cx, cy, cz) != (0, 0, 0) and abs(cy - pp[1]) < 300: cars.append((abs(cx - pp[0]) + abs(cz - pp[2]), i, cx, cy, cz))
                if not cars: break
                dist, i, cx, cy, cz = min(cars)
                off = [(-700, 0), (700, 0), (0, -700), (0, 700)][shot % 4]
                tx, tz = cx + off[0], cz + off[1]
                def ww(a, v):
                    for b in range(4): d.cmd("write_ram", addr="0x%08X" % (a + b), val=(v >> (8 * b)) & 0xFF)
                for k, v in enumerate((tx, cy, tz)): ww(B + 0x24 + 4 * k, (v << 4) & 0xFFFFFFFF)
                for k, v in enumerate((tx, cy, tz)): ww(B + 0x18 + 4 * k, v & 0xFFFFFFFF)
                time.sleep(0.4)
                d.shot(os.path.join(out, "near%d.png" % shot))
                print("near", shot, "car", i, "model", d.ram(B + i * 0x18C + 2, 1)[0], (cx, cy, cz), "player", d.pos(), flush=True)
            return
        if os.environ.get("CP_HEAP"):
            W = lambda a: d.word(a)
            print("HEAP window", W(0x8009733C), "objs_total", W(0x800AB050), "straddlers", W(0x80097350),
                  "celldata_total", W(0x800AA7E4), "obj_offsets", [W(0x800AB040 + 4 * i) for i in range(4)],
                  "cd_offsets", [W(0x800AA7D4 + 4 * i) for i in range(4)],
                  "cellptrs", hex(W(0x800970E0)), "celldata", hex(W(0x800970D4)), "objects", hex(W(0x80097108)),
                  "heap_end", hex(W(0x80097098)), "model_spool", hex(W(0x800AA7E8)), "slot_bufs", [hex(W(0x800AA7E8 + 4 * i)) for i in range(4)], flush=True)
            return
        if os.environ.get("CP_COS"):
            for adr in (0x8009AF04, 0x8009AF68, 0x8009AFCC, 0x8009B030):
                print("cos %08X" % adr, d.ram(adr, 32).hex(), "word", hex(d.word(adr)), flush=True)
            print("80096804", hex(d.word(0x80096804)), "model", d.word(0x8009683C), flush=True)
            print("jt", [hex(d.word(0x80010A20 + 4 * i)) for i in range(8)], "code", [hex(d.word(0x80052620 + 4 * i)) for i in range(14)], "carset", hex(d.word(0x800978A0)), flush=True)
            json.dump({"cos": "".join(d.ram(0x8009AF04 + 4 * k, 4).hex() for k in range(100)), "model": d.word(0x8009683C), "carset": hex(d.word(0x800978A0)),
                       "table": d.ram(0x800853D8, 4800).hex(), "rows4": d.ram(0x800A16A0, 800).hex()},
                      open(os.path.join(out, "summary.json"), "w"))
            return
        R = int(os.environ.get("CP_R", "3"))
        for pt in (os.environ.get("CP_PTS") or "%d,%d" % (pos[0], pos[2])).split(";"):
            x, z = map(int, pt.split(","))
            print("== around D1", x, z, "(col,row,sid,height,rot,flags) rows north->south", flush=True)
            seen = set(); surfs = []
            for j in range(R, -R - 1, -1):
                row = []
                for i in range(-R, R + 1):
                    c = cell_word(d, x + i * 1500, z + j * 1500)
                    row.append("%4s/%5s%s%s" % (c[2], c[3], "W" if c and c[2] == 683 else " ", "r" if c and int(c[5], 16) & 1 else " ") if c and len(c) == 6 else "  ----     ")
                print(" ".join(row), flush=True)
                for i in range(-R, R + 1):
                    c = cell_word(d, x + i * 1500, z + j * 1500)
                    if c and len(c) == 6 and c[2] not in seen and c[2] < 900:
                        seen.add(c[2]); sp = d.word(0x8009D904 + 4 * c[2])
                        if 0x10000 <= (sp & 0x1FFFFFFF) < 0x200000:
                            hdr = d.ram(sp, 8); import struct as _st
                            typ, info, head, n = _st.unpack_from("<4h", hdr)
                            if n > 1 or info != 1:
                                pl = []
                                for k in range(min(n, 8)):
                                    b = d.ram(sp + 8 + 52 * k, 52)
                                    xz = _st.unpack_from("<8i", b); a_, b_, c_, d_ = _st.unpack_from("<4i", b, 32); nv, pad = _st.unpack_from("<hh", b, 48)
                                    pl.append((xz[0], xz[1], xz[4], xz[5], a_, c_, d_, nv, pad))
                                surfs.append((c[2], info, n, pl))
            for sf in surfs:
                print("surface", sf[0], "info", sf[1], "n", sf[2], flush=True)
                for q in sf[3]: print("    foot (%d,%d)-(%d,%d) a %d c %d d %d nv %d sw %d" % q, flush=True)
    finally:
        p.kill()

one_run(a.out)
