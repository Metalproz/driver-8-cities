"""fps_dense.py - FPS over a fixed dense-spot set (C40 "dense set" method, see chicago/research_fps.md).

    python fps_dense.py --level work/var_roads_b12_day.lev [--spots chi_dense] [--secs 15]

Per spot: 15 s standing, then 15 s driving with cross held and left/right steering every 4 s.
FPS = game frame counter 0x800970D8 delta / VSync counter 0x80095250 delta * 59.94 (speed-independent).
Build-test exe, classic menu (Chicago = 4 downs + Day), own copy devtest/qa1, debug port 4410 (QA-1 only).
Output: devtest/_qa1/dense/<level>_<spot>.json and one summary line per spot + the dense average.
Spot coordinates are Driver 2 (CHI_START) values, as in spots.json.
"""
import argparse, json, os, struct, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dt  # noqa: E402

PHASE = 0x800970D8           # game frame counter (legacy, not used for the number)
FPS1 = 0x9F082310            # overlay FPS struct (Infrastructure): magic, fps, emu%, frames, vblanks, updates
FPS1_MAGIC = 0x31535046      # "FPS1"
PORT, NAME = 4410, "qa1"
OUT = dt.APP / "devtest" / "_qa1" / "dense"

# Dense set. Chicago entries are d2 coordinates; Miami needs entries once spots are found (see research_fps.md).
SPOTS = {
    "miami_start": [
        ("miami_start", None),               # Take a Ride Miami (row 0), same method as the QA-1 baseline
    ],
    "chi_dense": [
        ("l_down_e", (-101562, 106946)),     # user slow spot under the L, east end
        ("l_down_w", (-147698, 106096)),     # user slow spot under the L, west end
        ("fps_drop_1", (-41570, -339995)),   # intersection with downtown skyline (Live test drop spot)
        ("dense_1", (-146545, 474738)),      # spots.json purpleshops: shopfronts on building ground floors
        ("dense_2", (-447920, 206720)),      # spots.json blackroofs: building tops
        ("dense_3", (-83825, 343524)),       # spots.json blueboxes: building-height geometry above street
    ],
}


def write_slot_state(d0, city):
    """Feature state for the Chicago city-slot build (copied from the slot test helper; no scratchpad import)."""
    (d0 / "mods" / "state.toml").write_text("""format_version = 2

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
values = { city = "%s" }
""" % city)


def fps1(d):
    magic, fps, emu, frames, vblanks, upd = struct.unpack("<6I", d.ram(FPS1, 24))
    return magic, fps, frames, vblanks


def fps_of(d, secs_stand, secs_drive, steer=True):
    """Overlay FPS (FPS1 struct, Infrastructure). Per 1 s window: frames delta / VBlanks delta x 59.94.
    Guard: magic must be FPS1; window dropped when the VBlank delta < 30, FPS > 120 or frames did not increase."""
    res = {}
    for tag, secs, drive in (("standing", secs_stand, False), ("driving", secs_drive, True)):
        wins = []
        t_start = time.time()
        while time.time() - t_start < secs:
            m0, _, f0, v0 = fps1(d)
            t0 = time.time()
            while time.time() - t0 < 1.0:
                if drive:
                    k = int((time.time() - t_start) // 4) % 3 if steer else 0
                    if k == 0:
                        d.press("cross", hold=0.9, gap=0.0)
                    else:
                        d.press("cross", "left" if k == 1 else "right", hold=0.9, gap=0.0)
                else:
                    time.sleep(0.5)
            m1, _, f1, v1 = fps1(d)
            dv = (v1 - v0) & 0xFFFFFFFF; df = (f1 - f0) & 0xFFFFFFFF
            fps = df / dv * 59.94 if dv else 0.0
            wins.append((m0 == FPS1_MAGIC and m1 == FPS1_MAGIC, dv, df, round(fps, 1)))
        valid = [w[3] for w in wins if w[0] and w[1] >= 30 and w[2] > 0 and 0 < w[3] <= 120]
        res[tag] = round(sum(valid) / len(valid), 1) if valid else None
        res[tag + "_valid"] = "%d/%d" % (len(valid), len(wins))
    return res


def write_slot_state(d0, city):
    """Feature state for the Chicago city-slot build (copied from the slot test helper; no scratchpad import)."""
    (d0 / "mods" / "state.toml").write_text("""format_version = 2

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
values = { city = "%s" }
""" % city)


def fps_of(d, secs_stand, secs_drive, steer=True):
    """Guarded FPS: 1 s windows; a window is dropped when the VSync delta is < 30, FPS is > 120 or the
    frame counter did not increase. Returns mean of valid windows plus the valid/total counts."""
    res = {}
    for tag, secs, drive in (("standing", secs_stand, False), ("driving", secs_drive, True)):
        wins = []
        t_start = time.time()
        while time.time() - t_start < secs:
            p0, v0 = d.word(PHASE), d.word(dt.VCOUNT)
            t0 = time.time()
            while time.time() - t0 < 1.0:
                if drive:
                    k = int((time.time() - t_start) // 4) % 3 if steer else 0
                    if k == 0:
                        d.press("cross", hold=0.9, gap=0.0)
                    else:
                        d.press("cross", "left" if k == 1 else "right", hold=0.9, gap=0.0)
                else:
                    time.sleep(0.5)
            p1, v1 = d.word(PHASE), d.word(dt.VCOUNT)
            dv = (v1 - v0) & 0xFFFFFFFF; dp = (p1 - p0) & 0xFFFFFFFF
            fps = dp / dv * 59.94 if dv else 0.0
            wins.append((dv, dp, round(fps, 1)))
        valid = [w[2] for w in wins if w[0] >= 30 and w[1] > 0 and 0 < w[2] <= 120]
        res[tag] = round(sum(valid) / len(valid), 1) if valid else None
        res[tag + "_valid"] = "%d/%d" % (len(valid), len(wins))
    return res


def run_spot(level, name, d2, secs_stand, secs_drive, steer):
    row = 0 if d2 is None else 4
    city = "la" if d2 is None else "chicago"
    os.environ["CHI_SLOT"] = "1"; os.environ["CHI_NIGHT"] = str(level)
    dt.BUILD = os.environ.get("CHI_TEST_BUILD", "build-wip")
    dt.prepare(NAME, d2, str(level))
    write_slot_state(dt.TEST / NAME, city)
    p, d = dt.launch(NAME, PORT)
    rec = {"level": str(level), "spot": name, "d2": list(d2), "loaded": False}
    try:
        while (d.frame() or 0) < 2300:
            time.sleep(0.1)
        d.press("triangle", hold=0.12, gap=0.8); time.sleep(2)
        for b in ["right"] * 5 + ["cross"]:
            d.press(b, hold=0.12, gap=0.8)
        for _ in range(row):
            d.press("down", hold=0.12, gap=0.8)
        d.press("cross", hold=0.12, gap=0.8)
        time.sleep(3); d.press("cross", hold=0.12, gap=0.8)   # Day/Night screen: Day
        t0 = time.time(); last = None; since = None
        while time.time() - t0 < 90:
            pos = tuple(d.pos()); ok = pos != (0, 0, 0) and abs(pos[1]) < 10000
            if ok and last == pos:
                since = since or time.time()
                if time.time() - since >= 3:
                    rec["loaded"] = True; break
            else:
                since = None
            last = pos if ok else None
            time.sleep(0.5)
        if rec["loaded"]:
            time.sleep(2)
            rec.update(fps_of(d, secs_stand, secs_drive, steer))
            rec["kernel_ok"] = dt.kernel_ok(d)
    except Exception as e:  # keep the set going
        rec["error"] = repr(e)[:200]
    finally:
        p.kill(); rec["killed"] = p.pid
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / ("%s_%s.json" % (Path(str(level)).stem, name))).write_text(json.dumps(rec, default=str))
    print("%s %s loaded=%s standing=%s driving=%s kernel=%s err=%s" % (
        Path(str(level)).stem, name, rec["loaded"], rec.get("standing"), rec.get("driving"),
        rec.get("kernel_ok"), rec.get("error")), flush=True)
    return rec


MIAMI_OUT = dt.APP / "devtest" / "_qa1" / "dense"


def miami_route(secs=60, seg=15):
    """Miami reference: Take a Ride Miami (row 0, Day), drive ~60 s with steering, FPS per 15 s segment,
    screenshots every 10 s. Segments with the most buildings in view are picked by eye from the sheet."""
    os.environ["CHI_SLOT"] = "1"; os.environ["CHI_NIGHT"] = str(MIAMI_LEV)
    dt.BUILD = os.environ.get("CHI_TEST_BUILD", "build-wip")
    dt.prepare(NAME, None, str(MIAMI_LEV))
    write_slot_state(dt.TEST / NAME, "la")
    p, d = dt.launch(NAME, PORT)
    rec = {"level": str(MIAMI_LEV), "route": "miami_start_60s", "segments": [], "loaded": False}
    try:
        while (d.frame() or 0) < 2300:
            time.sleep(0.1)
        d.press("triangle", hold=0.12, gap=0.8); time.sleep(2)
        for b in ["right"] * 5 + ["cross"]:
            d.press(b, hold=0.12, gap=0.8)
        d.press("cross", hold=0.12, gap=0.8)           # Miami row 0
        time.sleep(3); d.press("cross", hold=0.12, gap=0.8)
        t0 = time.time(); last = None; since = None
        while time.time() - t0 < 90:
            pos = tuple(d.pos()); ok = pos != (0, 0, 0) and abs(pos[1]) < 10000
            if ok and last == pos:
                since = since or time.time()
                if time.time() - since >= 3:
                    rec["loaded"] = True; break
            else:
                since = None
            last = pos if ok else None
            time.sleep(0.5)
        if rec["loaded"]:
            time.sleep(2)
            MIAMI_OUT.mkdir(parents=True, exist_ok=True)
            t0 = time.time(); k_seg = 0
            while time.time() - t0 < secs:
                ts = time.time(); p0, v0 = d.word(PHASE), d.word(dt.VCOUNT)
                n_shot = int((time.time() - t0) // 10)
                while time.time() - ts < seg and time.time() - t0 < secs:
                    k = int((time.time() - t0) // 4) % 3
                    if k == 0:
                        d.press("cross", hold=0.9, gap=0.0)
                    else:
                        d.press("cross", "left" if k == 1 else "right", hold=0.9, gap=0.0)
                    if int((time.time() - t0) // 10) >= n_shot + 1:
                        n_shot += 1
                        d.shot(str(MIAMI_OUT / ("miami_t%02d.png" % int(time.time() - t0))))
                p1, v1 = d.word(PHASE), d.word(dt.VCOUNT)
                dv = (v1 - v0) & 0xFFFFFFFF; dp = (p1 - p0) & 0xFFFFFFFF
                rec["segments"].append({"t_end": round(time.time() - t0, 1), "pos": list(d.pos()),
                                        "fps": round(dp / dv * 59.94, 1) if dv else None})
                k_seg += 1
            rec["kernel_ok"] = dt.kernel_ok(d)
    except Exception as e:
        rec["error"] = repr(e)[:200]
    finally:
        p.kill(); rec["killed"] = p.pid
    (MIAMI_OUT / "miami_route.json").write_text(json.dumps(rec, default=str))
    print("miami route loaded=%s segments=%s kernel=%s err=%s" % (rec["loaded"], [(x["t_end"], x["fps"]) for x in rec["segments"]], rec.get("kernel_ok"), rec.get("error")), flush=True)
    return rec


MIAMI_LEV = None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", required=True)
    ap.add_argument("--spots", default="chi_dense")
    ap.add_argument("--secs", type=float, default=15)
    ap.add_argument("--no-steer", action="store_true")
    ap.add_argument("--miami", action="store_true", help="Miami reference route (level must be the Miami-capable b12 lev)")
    a = ap.parse_args()
    if a.miami:
        global MIAMI_LEV
        MIAMI_LEV = a.level
        miami_route()
        return
    recs = [run_spot(a.level, name, d2, a.secs, a.secs, not a.no_steer) for name, d2 in SPOTS[a.spots]]
    vals = [r["driving"] for r in recs if r.get("driving") is not None]
    vals_s = [r["standing"] for r in recs if r.get("standing") is not None]
    if vals:
        print("DENSE AVG level=%s standing=%.1f driving=%.1f n=%d" % (
            Path(str(a.level)).stem, sum(vals_s) / len(vals_s), sum(vals) / len(vals), len(vals)), flush=True)


if __name__ == "__main__":
    main()
