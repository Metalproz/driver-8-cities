"""drivetest.py - drive the player car straight along a direction on a test copy and
record its height: lifts (road map picking a bridge), drops and wrecks.

    python drivetest.py NAME D2X D2Z DIRX DIRZ [--secs 12] [--lev LEV] [--port 4386] [--out DIR]

NAME: devtest copy (created from build-dev), D2X/D2Z: Driver 2 start coordinates,
DIRX/DIRZ: direction to hold in Driver 1 coordinates (e.g. 0 -1 = south).
Prints one compact summary line: y range, biggest height jump per 0.2 s, distance,
damage, upside-down frames; screenshot in the out dir at the biggest jump and the end.
"""
from __future__ import annotations
import json, math, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dt

CAR = 0x8009B0A4
WRECK_COUNT = 0x80096920
CITY = dt.CITY if hasattr(dt, "CITY") else 0x800967F0


def main(a):
    name, x, z, dx, dz = a[0], int(a[1]), int(a[2]), float(a[3]), float(a[4])
    opt = {a[i].lstrip("-"): a[i + 1] for i in range(5, len(a) - 1, 2) if a[i].startswith("--")}
    secs, port = float(opt.get("secs", 12)), int(opt.get("port", 4386))
    out = Path(opt.get("out", dt.run_dir("drive") if hasattr(dt, "run_dir") else "."))
    out.mkdir(parents=True, exist_ok=True)
    lev = opt.get("lev")
    dt.prepare(name, (x, z), lev)
    p, d = dt.launch(name, port)
    res = {"start_d2": [x, z], "dir": [dx, dz], "lev": str(lev or dt.lev_path())}
    samples = []
    city = int(opt.get("city", 2))            # menu position: 0 Miami, 1 SF, 2 LA/Chicago, 3 NY
    try:
        if city == 2:
            dt.to_take_a_ride(d)
        else:                                 # same menu path with another city (original cities check)
            while (d.frame() or 0) < 2300:
                time.sleep(0.1)
            for b in ["right"] * 5 + ["cross"] + ["down"] * city + ["cross", "cross"]:
                d.press(b, hold=0.12, gap=0.8)
            time.sleep(35)
        want = math.atan2(dx, dz)
        t0, last, mask_cross = time.time(), d.pos(), 0xFFFF & ~(1 << dt.BTN["cross"])
        reversing = 0
        d.cmd("set_input", buttons="0x%04X" % mask_cross)
        time.sleep(0.4)
        while time.time() - t0 < secs:
            pos = d.pos()
            mvx, mvz = pos[0] - last[0], pos[2] - last[2]
            m11 = int.from_bytes(d.ram(CAR + 0xC, 2), "little", signed=True)
            dmg = int.from_bytes(d.ram(CAR + 0x17C, 2), "little")
            samples.append((round(time.time() - t0, 2), pos[0], pos[1], pos[2], int(math.hypot(mvx, mvz)), m11, dmg, d.word(WRECK_COUNT)))
            mask = mask_cross
            spd = math.hypot(mvx, mvz)
            if spd > 60:
                err = (math.atan2(mvx, mvz) - want + math.pi) % (2 * math.pi) - math.pi
                if reversing:                             # 3-point turn: back up with opposite lock
                    mask = 0xFFFF & ~(1 << dt.BTN["square"]) & ~(1 << dt.BTN["right" if err > 0 else "left"])
                    reversing -= 1
                elif abs(err) > math.radians(8):
                    mask &= ~(1 << dt.BTN["left" if err > 0 else "right"])
            elif len(samples) > 3 and not reversing:     # stuck (wall ahead): reverse for 6 samples
                reversing = 6
                mask = 0xFFFF & ~(1 << dt.BTN["square"])
            d.cmd("set_input", buttons="0x%04X" % mask)
            last = pos
            time.sleep(0.1)
            if city == 2 and d.word(dt.CITY) != dt.CHICAGO_CITY:
                res["left_chicago"] = True
                break
        d.cmd("clear_input")
        d.shot(out / "end.png")
    except Exception as e:
        res["error"] = repr(e)
    finally:
        p.kill()
    ys = [s[2] for s in samples]
    jumps = [(abs(samples[i][2] - samples[i - 1][2]), i) for i in range(1, len(samples))]
    big = max(jumps) if jumps else (0, 0)
    res.update(samples=samples, y_min=min(ys) if ys else None, y_max=max(ys) if ys else None,
               max_jump=big[0], max_jump_at=samples[big[1]][:4] if samples else None,
               dist=int(math.hypot(samples[-1][1] - samples[0][1], samples[-1][3] - samples[0][3])) if samples else 0,
               damage_end=samples[-1][6] if samples else None, upside_frames=max(s[7] for s in samples) if samples else None,
               min_m11=min(s[5] for s in samples) if samples else None)
    (out / "result.json").write_text(json.dumps(res))
    print("drive %s from d2 %d,%d dir %g,%g: y %s..%s max jump %d at %s dist %d damage %s upside %s m11min %s %s %s" % (
        name, x, z, dx, dz, res["y_min"], res["y_max"], res["max_jump"], res["max_jump_at"], res["dist"],
        res["damage_end"], res["upside_frames"], res["min_m11"], "LEFT CHICAGO" if res.get("left_chicago") else "",
        res.get("error", "")))
    print("samples t:y (every 2nd):", " ".join("%g:%d" % (s[0], s[2]) for s in samples[::2]))
    print("out:", out)


if __name__ == "__main__":
    main(sys.argv[1:])
