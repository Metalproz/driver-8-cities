"""Catch a short render artefact right after an area switch and GP0-capture it (C45 corr4 black triangle).

    python tricatch.py PORT OUTDIR LEVEL --start=D2X,D2Z --legs="dx,dz,secs;..." [--build build-test] [--thresh 0.018] [--runs N]

Starts Chicago by day at D2 (x, z) with LEVEL (a devtest copy via dt.prepare / dt.launch), drives the legs
(dx, dz = D1 heading, held with cross, steering from the motion), and after every area switch screenshots
for 3 s: when the sky band (8-40 % of the height) holds more than THRESH dark pixels (luma < 28), it saves
hit_N.png and captures the newest 6 frames' GP0 streams to OUTDIR/runR/gpu (gpu_frame_capture.py: per primitive
op, verts, pc/ra of the issuing guest code, src = packet address in RAM, OT rank). Calibration: the corr4 R8
triangle shot 0.035, normal switch frames 0.006-0.014 (a dark building in view can trigger: check hit_N.png).
summary.json per run: switches, dark-fraction series, hits."""
import argparse, math, os, subprocess, sys, time, json

CHI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GF = os.path.normpath(os.path.join(CHI, "..", "..", "psxrecomp", "tools", "gpu_frame_capture.py"))

ap = argparse.ArgumentParser()
ap.add_argument("port", type=int); ap.add_argument("out"); ap.add_argument("lev"); ap.add_argument("--start", required=True); ap.add_argument("--legs", required=True)
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
start = tuple(int(v) for v in a.start.split(","))
legs = [tuple(map(float, l.split(","))) for l in a.legs.split(";")]


def dark_fraction(path):
    im = Image.open(path).convert("L"); w, h = im.size
    band = im.crop((0, int(h * 0.08), w, int(h * 0.40))).point(lambda v: 255 if v < 28 else 0)
    return sum(band.histogram()[255:]) / (band.size[0] * band.size[1])


def one_run(out):
    os.makedirs(out, exist_ok=True)
    d0 = dt.prepare("tricatch", start, a.lev)
    (d0 / "mods" / "state.toml").write_text(STATE)
    p, d = dt.launch("tricatch", a.port)
    res = {"pid": p.pid, "switches": [], "dark": [], "hits": []}
    try:
        while (d.frame() or 0) < 2300: time.sleep(0.1)
        for b in ["right"] * 5 + ["cross"]: d.press(b, hold=0.12, gap=0.8)
        time.sleep(1.5)
        d.press("up", hold=0.12, gap=0.5); time.sleep(0.5); d.press("cross", hold=0.12, gap=0.8); time.sleep(1.0)
        d.press("cross", hold=0.12, gap=0.8); time.sleep(3)
        d.press("cross", hold=0.12, gap=0.8)
        t0 = time.time(); last = None; since = None
        while time.time() - t0 < 90:             # loaded: position stable for 3 s in Chicago
            pos = tuple(d.pos()); ok = pos != (0, 0, 0) and abs(pos[1]) < 10000 and d.word(dt.CITY) == 3
            if ok and last == pos:
                since = since or time.time()
                if time.time() - since >= 3: break
            else: since = None
            last = pos if ok else None
            time.sleep(0.5)
        t0 = time.time(); lastp = d.pos(); area = d.word(AREA) & 0xFF; sw_t = None; k = 0
        res["start_pos"] = (lastp, area)
        for dx, dz, secs in legs:
            want = math.atan2(dx, dz); tl = time.time(); rev = 0; tnext = 0
            while time.time() - tl < secs:
                th = time.time() - t0
                a2 = d.word(AREA) & 0xFF
                if a2 != area:
                    res["switches"].append((round(th, 2), area, a2, d.pos())); area = a2; sw_t = th
                if sw_t is not None and th - sw_t < 3.0:
                    fp = os.path.join(out, "probe.png"); d.shot(fp); fr = d.frame()
                    df = dark_fraction(fp); res["dark"].append((round(th, 2), fr, round(df, 4)))
                    if df > a.thresh and len(res["hits"]) < 3:
                        n = len(res["hits"]); hp = os.path.join(out, "hit_%d.png" % n); os.replace(fp, hp)
                        subprocess.run([sys.executable, GF, "--port", str(a.port), "--frame", str(d.frame()), "--frames", "6",
                                        "--tag", "hit%d" % n, "--out", os.path.join(out, "gpu"), "--summary"],
                                       stdout=open(os.path.join(out, "gpu_capture_%d.log" % n), "w"), stderr=subprocess.STDOUT, timeout=300)
                        res["hits"].append((round(th, 2), fr, round(df, 4), d.pos()))
                        sw_t = th - 2.0                 # look one more second for a second hit
                if th < tnext:
                    time.sleep(0.01); continue
                tnext = th + 0.1                        # steering every 0.1 s (motion per sample)
                pos = d.pos(); mvx, mvz = pos[0] - lastp[0], pos[2] - lastp[2]; lastp = pos; k += 1
                mask = 0xFFFF & ~(1 << dt.BTN["cross"])
                if rev:
                    mask = 0xFFFF & ~(1 << dt.BTN["square"]); rev -= 1
                elif math.hypot(mvx, mvz) > 30:
                    err = (math.atan2(mvx, mvz) - want + math.pi) % (2 * math.pi) - math.pi
                    if abs(err) > math.radians(8): mask &= ~(1 << dt.BTN["left" if err > 0 else "right"])
                elif k > 40 and k % 20 == 0 and math.hypot(mvx, mvz) < 5:
                    rev = 15
                d.cmd("set_input", buttons="0x%04X" % mask)
                if k % 10 == 0:                         # no felony (cops stay out of the way)
                    d.cmd("write_ram", addr="0x8009B220", val=0); d.cmd("write_ram", addr="0x8009B221", val=0)
        d.cmd("clear_input")
        res["end_pos"] = (d.pos(), d.word(AREA) & 0xFF)
        d.shot(os.path.join(out, "end.png"))
    finally:
        p.kill()
        json.dump(res, open(os.path.join(out, "summary.json"), "w"))
    print(os.path.basename(out), res.get("start_pos"), res.get("end_pos"), "switches", [(s[0], s[1], s[2]) for s in res["switches"]],
          "max dark", max([x[2] for x in res["dark"]] or [0]), "hits", [(h[0], h[2]) for h in res["hits"]], flush=True)


for r in range(a.runs):
    one_run(os.path.join(a.out, "run%d" % r))
