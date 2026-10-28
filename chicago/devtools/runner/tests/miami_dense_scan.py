"""C40 helper: drive Miami from the Take a Ride start and record where the most primitives are drawn (= dense views),
so Miami's dense-spot set is chosen by measurement, not by guess. Writes dense_spots.json in the run dir."""
import json, math, random, time

SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)


def run(s):
    s.menu("take_a_ride/miami")
    s.wait_world(what="Miami start")
    rows = []
    t = time.time(); last = s.pos(); stuck = 0; steer = 0; random.seed(7)
    while time.time() - t < 120:
        p = s.pos(); mv = math.hypot(p[0] - last[0], p[2] - last[2]); last = p
        stuck = stuck + 1 if mv < 60 else 0
        if stuck > 6:
            s.hold("square", "left"); time.sleep(1.2); stuck = 0
        else:
            if random.random() < 0.15:
                steer = random.choice((0, 0, 1, 2))
            s.hold(*(["cross"] + (["left"] if steer == 1 else ["right"] if steer == 2 else [])))
        fps, prims = s.perf(0.75)
        x, y, z, h, _ = s.car(0)
        rows.append({"t": round(time.time() - t, 1), "pos": [x, y, z], "heading": round(math.degrees(h)), "prims": prims, "fps": fps})
        if s.car(0)[4] >= (s.word(0x80096E7C) & 0xFFFF) > 0:
            s.release(); time.sleep(4)
            for b in ("down", "down", "down", "cross"):
                s.press(b, gap=0.5)
            time.sleep(4)
    s.release()
    rows.sort(key=lambda r: -r["prims"])
    picks = []
    for r in rows:
        if all(math.hypot(r["pos"][0] - q["pos"][0], r["pos"][2] - q["pos"][2]) > 4000 for q in picks):
            picks.append(r)
        if len(picks) == 4:
            break
    (s.dir / "dense_spots.json").write_text(json.dumps({"picks": picks, "rows": rows}, indent=0))
    s.record("dense", detail="top prims %s" % [(p["pos"][0], p["pos"][2], p["heading"], p["prims"], p["fps"]) for p in picks])
    s.check("found dense spots", len(picks) >= 3, "%d spots, prims median %d" % (len(picks), sorted(r["prims"] for r in rows)[len(rows) // 2]))
