"""probe_roadwrites.py SPOT - who writes into road table slot 0 while driving (cross+left)."""
import sys, collections
import dt
spot = sys.argv[1]
dt.prepare("probe", dt.spots()[spot]["d2"])
p, d = dt.launch("probe", 4420)
try:
    dt.to_take_a_ride(d)
    lo, hi = 0x800EF600, 0x800F6600
    b = d.word(0x80097530) & 0x1FFFFF | 0x80000000
    print("cur buffer struct", hex(b), [hex(d.word(b + 4 * k)) for k in range(4)])
    d.cmd("wtrace_arm", lo="0x%08X" % lo, hi="0x%08X" % hi)
    t0 = d.cmd("wtrace_stats").get("newest_seq", 0)
    for k in range(4):
        d.press("cross", "left", hold=1.5, gap=0.5)
    ents = [e for e in d.cmd("wtrace_dump", count=4000, addr_lo="0x%08X" % lo, addr_hi="0x%08X" % hi).get("entries", []) if e["seq"] > t0]
    print("table", hex(lo), "writes:", len(ents))
    for (pc, ra), n in collections.Counter((e["pc"], e["ra"]) for e in ents).most_common(40):
        print(n, "pc", pc, "ra", ra)
finally:
    p.kill()
