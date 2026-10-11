"""probe_writes.py SPOT LO HI [STEPS] - log writes to a guest range while driving randomly."""
import sys, time, json, random
import dt
spot, lo, hi = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
steps = int(sys.argv[4]) if len(sys.argv) > 4 else 40
dt.prepare("probe", dt.spots()[spot]["d2"])
p, d = dt.launch("probe", 4420)
try:
    dt.to_take_a_ride(d)
    d.cmd("wtrace_arm", lo="0x%08X" % lo, hi="0x%08X" % hi)
    t0 = d.cmd("wtrace_stats").get("newest_seq", 0)
    rnd = random.Random(3)
    for k in range(steps):
        d.press(*rnd.choice([("cross", "left"), ("cross", "right"), ("cross",)]), hold=rnd.choice((0.5, 1.0, 2.0)), gap=0.0)
    ents = [e for e in d.cmd("wtrace_dump", count=500, addr_lo="0x%08X" % lo, addr_hi="0x%08X" % hi).get("entries", []) if e["seq"] > t0]
    import collections
    print("writes:", len(ents), collections.Counter((e["pc"], e["ra"]) for e in ents).most_common(8))
    for e in ents[:12]:
        print(e["frame"], e["addr"], e["old"], "->", e["new"], "pc", e["pc"], "ra", e["ra"])
finally:
    p.kill()
