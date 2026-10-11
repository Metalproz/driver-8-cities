"""probe_trace.py SPOT [KEYS..] - drive like the capture and log position every 0.25 s."""
import sys, threading, time
import dt
spot = sys.argv[1]
keys = sys.argv[2:] or ["cross"]
import os, lab
lev = lab.variant_lev({"experiment": os.environ.get("EXP", ""), "env": {}}) if os.environ.get("EXP") else None
dt.prepare("probe", dt.spots()[spot]["d2"], lev)
p, d = dt.launch("probe", 4420)
out = dt.run_dir("trace-" + spot)
try:
    dt.to_take_a_ride(d)
    t0 = time.time(); log = []
    for k in range(int(__import__("os").environ.get("SEGS", "6"))):
        stop = time.time() + 2.0
        hold = threading.Thread(target=d.press, args=tuple(keys), kwargs=dict(hold=1.5, gap=0.0))
        hold.start()
        while time.time() < stop:
            pos = d.pos()
            col, row = (pos[0] + 810750) // 1500, (855750 - pos[2]) // 1500
            slot = (col % 120 >= 60) + 2 * ((row % 120 >= 60) ^ (d.word(0x80097374) & 1))
            v = d.word((d.word(0x8009D8F4 + 4 * slot) & 0x1FFFFF | 0x80000000) + 4 * ((row % 60) * 60 + col % 60))
            log.append((round(time.time() - t0, 2), pos, d.word(dt.REGION), d.word(0x800967F4),
                        "cell %d,%d sid %d h %d" % (col, row, (v >> 16) & 0x3FF, -((v & 0xFFFF) ^ 0x8000) + 0x8000 if v & 0x8000 else -(v & 0xFFFF))))
            time.sleep(0.25)
        hold.join()
    d.shot(out / "end.png")
    for row in log: print(*row)
finally:
    p.kill()
