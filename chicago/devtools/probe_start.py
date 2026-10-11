"""probe_start.py SPOT - screenshots every 2 s while the level starts."""
import sys, time
import dt
spot = sys.argv[1]
dt.prepare("probe", dt.spots()[spot]["d2"])
p, d = dt.launch("probe", 4420)
out = dt.run_dir("start-" + spot)
try:
    while (d.frame() or 0) < 2300: time.sleep(0.1)
    for b in ["right"] * 5 + ["cross", "down", "down", "cross", "cross"]:
        d.press(b, hold=0.12, gap=0.8)
    for k in range(20):
        time.sleep(2)
        d.shot(out / ("t%02d.png" % k))
        print(k, "pos", d.pos(), "area", d.word(dt.AREA), flush=True)
    dt.sheet([out / ("t%02d.png" % k) for k in range(20)], out / "sheet.png", [str(k * 2) + "s" for k in range(20)])
    print("sheet", out / "sheet.png")
finally:
    p.kill()
