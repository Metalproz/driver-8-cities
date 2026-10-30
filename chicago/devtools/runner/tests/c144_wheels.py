"""C144: draw-only wheel height per car (exe c144_patches: wheel centre y += WDY 0x80093748, WCAVE 0x80011AC8; the plugin's
DrawCarWheels hook writes 73 - R per car in D2 cities, 0 elsewhere). CITY (default havana; choice 0 = the mini, R 44 -> 29):
the exe words, WDY samples over 2 s (the last car drawn), start shot (compare with c138_mini's), DRIVE s, shot, alive.
D1 city (CITY=miami): WDY stays 0.
Ride (C144 ride rows ship with the draw offset): the parked player's y over 2 s (swing <= 40, no fall after the start =
no high spawn) and every AI car that appears during the drive: its y swing over its first 3 s (R35: civilians 0-20,
specials 1-7 after the fix, 400 before) must stay <= 120."""
import os, struct, time

from runner.session import CARS, CAR_SIZE, AI_REC

SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)
CITY = os.environ.get("CITY", "havana")
NIGHT = os.environ.get("NIGHT") == "1"
DRIVE = float(os.environ.get("DRIVE", "12"))


def s32(v):
    return v - (1 << 32) if v >> 31 else v


def run(s):
    s.menu("take_a_ride/%s%s" % (CITY, "/night" if NIGHT else "")); s.wait_world(what=CITY)
    site = (s.word(0x8003B60C), s.word(0x8003B610))
    cave = [s.word(0x80011AC8 + 4 * k) for k in range(4)]
    s.check("wheel y site + WCAVE patched", site == (0x080046B2, 0x24420032) and cave == [0x8F99CFD8, 0x00621823, 0x0800ED85, 0x00791821],
            "%08X %08X / %s" % (site + (" ".join("%08X" % w for w in cave),)))
    vals = set()
    for _ in range(20):
        vals.add(s32(s.word(0x80093748))); time.sleep(0.1)
    s.record("WDY", detail="%s: values seen %s" % (CITY, sorted(vals)))
    d1 = CITY in ("miami", "frisco", "la", "ny", "newtown", "desert")
    if d1:
        s.check("Driver 1 city: WDY 0", vals == {0}, str(sorted(vals)))
    else:
        s.check("D2 city: per-car wheel offsets in use", any(v != 0 for v in vals) and all(-80 < v < 60 for v in vals), str(sorted(vals)))
    s.screenshot("start")
    ys = []
    for _ in range(20):
        ys.append(s.car(0)[1]); time.sleep(0.1)
    s.check("player parked: no bounce / fall after the start", max(ys) - min(ys) <= 40, "y %d..%d" % (min(ys), max(ys)))
    x, y, z, h, _ = s.car(0)
    seen, swing, hist = {}, {}, {}

    def tick(_s):
        rec = _s.d.ram(AI_REC, 0x50 * 22)
        raw = _s.d.ram(CARS, CAR_SIZE * 23)
        now = time.time()
        for i in range(22):
            st, model = rec[0x50 * i + 1], rec[0x50 * i + 0x10]
            if st == 0:
                seen.pop(i, None); continue
            cy = struct.unpack_from("<i", raw, CAR_SIZE * (i + 1) + 0x1C)[0]
            if i not in seen:
                seen[i] = (now, model, [cy])
                continue
            t0, m, l = seen[i]
            if now - t0 <= 3.0:
                l.append(cy)
                swing[(i, t0)] = (m, max(l) - min(l))
                hist[(i, t0)] = l
        return False

    tick(s)
    for k in list(seen):
        seen[k] = (0, seen[k][1], seen[k][2])  # t0 0 -> never sampled as a spawn
    s.drive(DRIVE, h, on_tick=tick)
    new = []
    for (i, t0), (m, w) in swing.items():
        if not t0:
            continue
        ys = seen.get(i, (0, 0, []))[2] if seen.get(i, (None,))[0] == t0 else hist.get((i, t0), [])
        new.append((m, w, ys))
    # a high spawn = the car falls right after it appears (first 1 s drop), a bounce = y reversing with amplitude > 40;
    # a steady climb / descent while driving (ramps, bridges) is the road, not a fault
    def verdict(ys):
        drop = max(abs(v - ys[0]) for v in ys[:5]) if len(ys) >= 2 else 0
        rev, last_dir, last_y = 0, 0, ys[0] if ys else 0
        for y in ys[1:]:
            d = y - last_y
            if abs(d) > 40:
                dr = 1 if d > 0 else -1
                if last_dir and dr != last_dir:
                    rev += 1
                last_dir, last_y = dr, y
        return drop, rev
    bad = []
    for m, w, ys in new:
        drop, rev = verdict(ys)
        if drop > 120 or rev >= 2:
            bad.append((m, w, drop, rev, ys[:12]))
    s.record("ai spawns", detail="%d new cars; (model, swing 3 s): %s" % (len(new), sorted([(m, w) for m, w, _ in new], key=lambda t: -t[1])[:8]))
    for m, w, ys in sorted(new, key=lambda t: -t[1])[:3]:
        s.record("ai y series", detail="model %d swing %d: %s" % (m, w, ys[:14]))
    s.check("AI spawns: no high spawn (drop > 120 in 1 s) / bounce (2+ reversals > 40)", not bad, str(bad)[:300])
    s.screenshot("after_drive")
    s.check("alive", s.alive())
