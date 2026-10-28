"""capture_city.py - one-command capture of LA by day / LA by night / Chicago day / Chicago night on a devtest copy of
build-test (current state: 6-model car set, 3-disc Option A, pages menu, LA day overlay). For Design / QA / EXP.

    python driver_personal/chicago/devtools/capture_city.py OUTDIR MODE [--copy design] [--port 4490] [--prep]
           [--chicago LEV] [--night LEV] [--laday LEV] [--drive SECS]

MODE: laday | lanight | chiday | chinight. --prep (re)builds the copy's package from the given levels (needed after a
build-test update or a level change; ~1 min). Writes OUTDIR/MODE_menu.png, MODE_0.png (start), MODE_1.png (after
driving), prints the look words (city, night flag, LOOK_CITY, sky, plane / fog colours). Launches through dt.launch
(BELOW_NORMAL, own port; checks the port is free); kills only its own process.
"""
import argparse, os, sys, time
from pathlib import Path
CHI = Path(__file__).resolve().parents[1]
WORK = CHI / "work"
sys.path.insert(0, str(CHI / "devtools")); sys.path.insert(0, str(CHI))

ap = argparse.ArgumentParser()
ap.add_argument("out"); ap.add_argument("mode", choices=["laday", "lanight", "chiday", "chinight"])
ap.add_argument("--copy", default="design"); ap.add_argument("--port", type=int, default=4490)
ap.add_argument("--prep", action="store_true")
ap.add_argument("--chicago", default=str(WORK / "var_d2cars16_day.lev"))
ap.add_argument("--night", default=str(WORK / "var_d2cars16_night.lev"))
ap.add_argument("--laday", default=str(WORK / "var_polish_la_day_8.lev"))
ap.add_argument("--drive", type=float, default=2.5)
a = ap.parse_args()
os.environ.update(CHI_TEST_BUILD="build-test", CHI_SLOT="1", CHI_MENU_PAGES="1", CHI_POLISH_SKY="d2raw",
                  CHI_NIGHT=a.night, CHI_LA_DAY_LEV=a.laday)
import dt
STATE = open(CHI / "devtools" / "cellprobe.py").read().split('STATE = """')[1].split('"""')[0]
OUT = Path(a.out).resolve(); OUT.mkdir(parents=True, exist_ok=True)
if a.prep:
    d0 = dt.prepare(a.copy, None, a.chicago)
    (d0 / "mods" / "state.toml").write_text(STATE)
p, d = dt.launch(a.copy, a.port)
W = d.word
try:
    while (d.frame() or 0) < 2300:
        time.sleep(0.1)
    # pages menu: Take a Ride -> city list; Chicago = up from the top row, LA = two rows down; a Day / Night screen
    # follows for Chicago and for LA (when an LA day level is packaged)
    for b in ["right"] * 5 + ["cross"]:
        d.press(b, hold=0.12, gap=0.8)
    time.sleep(1.5)
    if a.mode.startswith("chi"):
        d.press("up", hold=0.12, gap=0.5); time.sleep(0.5)
    else:
        d.press("down", hold=0.12, gap=0.5); d.press("down", hold=0.12, gap=0.5); time.sleep(0.5)
    d.press("cross", hold=0.12, gap=0.8); time.sleep(1.0)
    if a.mode.startswith("chi"):
        d.press("cross", hold=0.12, gap=0.8); time.sleep(3)
    else:
        time.sleep(1.5)
    if a.mode.endswith("night"):
        d.press("down", hold=0.12, gap=0.6)
    d.shot(OUT / ("%s_menu.png" % a.mode))
    d.press("cross", hold=0.12, gap=0.8)
    t0 = time.time()
    while time.time() - t0 < 90 and not (W(dt.CITY) == 3 and tuple(d.pos()) != (0, 0, 0)):
        time.sleep(0.5)
    time.sleep(5)
    d.shot(OUT / ("%s_0.png" % a.mode))
    if a.drive > 0:
        d.press("cross", hold=a.drive, gap=0.3)
        d.shot(OUT / ("%s_1.png" % a.mode))
    rgb = lambda w: (w & 0xFF, (w >> 8) & 0xFF, (w >> 16) & 0xFF)
    print(a.mode, "city", W(dt.CITY), "night", W(0x80096850), "look", hex(W(0x8009789C)), "c3", hex(W(0x80097898)),
          "sky", W(0x800974EC), "plane", rgb(W(0x80097150)), "fog", rgb(W(0x80097138)), "carset", W(0x800978A0),
          "pos", d.pos(), "alive", dt.alive(d, 2.0), flush=True)
finally:
    p.kill(); time.sleep(1)
