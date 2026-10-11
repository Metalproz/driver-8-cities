"""probe_primuse.py SPOT [KEYS..] - peak primitive buffer use while driving."""
import sys, threading, time
import dt
spot = sys.argv[1]; keys = sys.argv[2:] or ["cross", "left"]
dt.prepare("probe", dt.spots()[spot]["d2"])
p, d = dt.launch("probe", 4420)
try:
    dt.to_take_a_ride(d)
    peak = {}; late = []
    for k in range(4):
        th = threading.Thread(target=d.press, args=tuple(keys), kwargs=dict(hold=1.5, gap=0.0)); th.start()
        t_end = time.time() + 2.0; n = 0
        while time.time() < t_end:
            b = d.word(0x80097530) & 0x1FFFFF | 0x80000000
            raw = d.ram(b, 12)
            cur, start = int.from_bytes(raw[0:4], "little") & 0x1FFFFF, int.from_bytes(raw[8:12], "little") & 0x1FFFFF
            peak[start] = max(peak.get(start, 0), cur - start); n += 1
            if cur - start > 0x16000:
                r = d.cmd("get_registers")
                late.append((cur - start, r.get("pc"), r.get("ra")))
        th.join()
        print("seg", k, "samples", n, {hex(s): hex(v) for s, v in peak.items()}, "pos", d.pos(), flush=True)
    import collections
    print("late samples", len(late))
    for (pc, ra), c in collections.Counter((x[1], x[2]) for x in late).most_common(12):
        print(c, pc, ra, hex(max(x[0] for x in late if x[1] == pc)))
finally:
    p.kill()
