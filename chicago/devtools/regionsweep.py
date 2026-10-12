"""regionsweep.py - quick crash checkup of every drivable Chicago region (user, 2026-10-11).

    python regionsweep.py plan                 list the regions in sweep order (batches of 10)
    python regionsweep.py batch N [--secs S]   run batch N (0-based) and stop

One game client at a time (headless copy devtest/sweep, port 4430). Per region: start
the car on a road cell near the region centre (CHI_START), Take a Ride, drive ~10 s
with random steering, and record freezes (with a CPU dump), game exits, kernel damage,
model-table damage, falls under the map, wrecks, area switches and leaving Chicago.
Results: devtest/_sweep/region_RX_RZ.json, batch_N.txt; build-dev's exe and level.
"""
from __future__ import annotations
import sys, time, json, math, random, struct, pickle, glob, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dt
from freezeprobe import NAMES

NAME, PORT, BATCH = "sweep", 4430, 10
SWEEP = dt.TEST / "_sweep"
UNDER_MAP_Y = -1700                       # below the trench floor (car centre ~ -1188 there)


def regions():
    """Drivable regions, busiest first: (rx, rz, road_cells, spawn D1 x, z)."""
    files = sorted(glob.glob(str(dt.CHI / "work" / "road_levels_*.pkl")), key=os.path.getmtime)
    g = pickle.load(open(files[-1], "rb"))
    cols, rows = max(k[0] for k in g) + 1, max(k[1] for k in g) + 1
    hx, hz = cols // 2 * 1500, rows // 2 * 1500
    road = {}
    for (c, r), lv in g.items():
        if not lv:
            continue
        y, t = sorted(lv, key=lambda hl: (hl[1] in (6, 9), abs(hl[0])))[0]
        if t == 4 and abs(y) < 100:
            road.setdefault((c // 60, r // 60), []).append((c, r))
    out = []
    for (rx, rz), cells in road.items():
        if len(cells) < 30:
            continue
        cc, cr = rx * 60 + 30, rz * 60 + 30
        c, r = min(cells, key=lambda k: (k[0] - cc) ** 2 + (k[1] - cr) ** 2)
        out.append((rx, rz, len(cells), c * 1500 - hx, hz - r * 1500))
    out.sort(key=lambda o: -o[2])
    return out


def to_ride(d, limit=90):
    t = time.time()
    while (d.frame() or 0) < 2300:
        if time.time() - t > limit:
            return False
        time.sleep(0.2)
    for b in ["right"] * 5 + ["cross", "down", "down", "cross", "cross"]:
        d.press(b, hold=0.12, gap=0.6)
    t = time.time()
    while time.time() - t < 45:                # level load: wait until the game draws again
        time.sleep(1.0)
        if d.word(dt.CITY) == dt.CHICAGO_CITY and dt.alive(d, 0.8) and not d.word(dt.LOADING):
            time.sleep(2.0)
            return True
    return d.word(dt.CITY) == dt.CHICAGO_CITY


def cpu_dump(d):
    r = d.cmd("get_registers")
    regs = {n: int(v, 16) if isinstance(v, str) else v for n, v in zip(NAMES, r.get("gpr", []))}
    sp = regs.get("sp", 0) & 0x1FFFFF
    words = struct.unpack("<48I", d.ram(0x80000000 + sp, 192)) if sp else ()
    return {"epc": r.get("cop0_epc"), "regs": {n: "%08X" % regs[n] for n in ("a0", "a1", "a2", "t7", "s0", "s1", "ra", "sp") if n in regs},
            "stack": ["%08X" % w for w in words if 0x80010000 <= w < 0x80090000][:10],
            "area": d.word(dt.AREA), "region": d.word(dt.REGION), "loading": d.word(dt.LOADING),
            "spool_left": d.word(dt.SPOOL_LEFT), "kernel_ok": dt.kernel_ok(d)}


def run_region(rx, rz, x, z, secs, rnd):
    res = {"region": [rx, rz], "spawn_d1": [x, z], "faults": [], "areas": [], "wrecks": 0}
    out = SWEEP / ("region_%d_%d" % (rx, rz))
    out.mkdir(parents=True, exist_ok=True)
    try:
        dt.prepare(NAME, start=dt.d2_of(x, z), lev=dt.APP / "build-dev" / "mods" / "packages" / "driver.chicago" / "0.1.0" / "assets" / "chicago.lev")
    except SystemExit as e:
        res["faults"].append({"kind": "prepare failed", "detail": str(e)})
        return res
    p, d = dt.launch(NAME, PORT)
    try:
        if not to_ride(d):
            ex = dt.exit_info(NAME, p)
            res["faults"].append({"kind": "game exited before driving" if ex else "never reached the drive",
                                  "detail": ex or cpu_dump(d)})
            return res
        res["start_pos"] = d.pos()
        mask = 0xFFFF & ~(1 << dt.BTN["cross"])
        t0, steer_t, last = time.time(), 0, None
        while time.time() - t0 < secs:
            if time.time() - steer_t > 2.0:
                steer_t = time.time()
                m = mask
                s = rnd.choice(("left", "right", None, None))
                if s:
                    m &= ~(1 << dt.BTN[s])
                d.cmd("set_input", buttons="0x%04X" % m)
            time.sleep(0.5)
            ex = dt.exit_info(NAME, p)
            if ex:
                res["faults"].append({"kind": "game exited (crash)", "detail": ex}); break
            a = d.word(dt.AREA)
            if not res["areas"] or res["areas"][-1] != a:
                res["areas"].append(a)
            pos = d.pos(); last = pos
            if pos[1] < UNDER_MAP_Y:
                res["faults"].append({"kind": "under the map", "pos": pos}); d.shot(out / "under_map.png"); break
            if dt.kernel_ok(d) is False:
                res["faults"].append({"kind": "kernel damaged (C25 type)", "detail": cpu_dump(d), "pos": pos}); break
            if d.word(dt.CITY) != dt.CHICAGO_CITY:
                res["faults"].append({"kind": "left Chicago", "pos": pos}); break
            if dt.wrecked(d):
                res["wrecks"] += 1
                d.cmd("clear_input"); dt.play_again(d); steer_t = 0
            if not dt.alive(d, 0.6) and not dt.alive(d, 2.5):
                res["faults"].append({"kind": "FREEZE", "detail": cpu_dump(d), "pos": pos}); d.shot(out / "freeze.png"); break
        d.cmd("clear_input")
        res["end_pos"] = last
        if not res["faults"]:
            bad = dt.table_check(d.ram_all(), d.ram(dt.MODEL_TABLE, dt.MODEL_ENTRIES * 4) + bytes(0x90000),
                                 dt.model_sigs(dt.copy_lev(NAME)))
            if bad:
                res["faults"].append({"kind": "model table damaged", "detail": bad[:4]})
        if res["faults"]:
            d.shot(out / "fault.png")
    except Exception as e:
        ex = dt.exit_info(NAME, p)
        res["faults"].append({"kind": "game exited (crash)" if ex else "tool error", "detail": ex or repr(e)})
    finally:
        try:
            d.cmd("clear_input")
        except Exception:
            pass
        p.kill()
        time.sleep(1.0)
    return res


def main(a):
    regs = regions()
    if not a or a[0] == "plan":
        print("%d drivable regions, %d batches of %d (busiest first)" % (len(regs), (len(regs) + BATCH - 1) // BATCH, BATCH))
        for i, (rx, rz, n, x, z) in enumerate(regs):
            print("batch %d  region %2d,%2d  road cells %4d  spawn D1 %d,%d" % (i // BATCH, rx, rz, n, x, z))
        return
    k = int(a[1])
    secs = float(a[a.index("--secs") + 1]) if "--secs" in a else 10.0
    SWEEP.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(1000 + k)
    lines = []
    for rx, rz, n, x, z in regs[k * BATCH:(k + 1) * BATCH]:
        t = time.time()
        res = run_region(rx, rz, x, z, secs, rnd)
        res["secs"] = round(time.time() - t)
        (SWEEP / ("region_%d_%d.json" % (rx, rz))).write_text(json.dumps(res, indent=1))
        faults = "; ".join(f["kind"] for f in res["faults"]) or "ok"
        lines.append("region %2d,%2d  spawn %d,%d  areas %s  wrecks %d  -> %s" % (rx, rz, x, z, res["areas"], res["wrecks"], faults))
        print(lines[-1], flush=True)
    summary = "batch %d (%d regions, %s s drive each)\n%s\n" % (k, len(lines), secs, "\n".join(lines))
    (SWEEP / ("batch_%d.txt" % k)).write_text(summary)
    print("done:", SWEEP / ("batch_%d.txt" % k))


if __name__ == "__main__":
    main(sys.argv[1:])
