"""probe_roadtab.py SPOT - which region's road values sit in each of the 4 live tables."""
import sys, struct, time
sys.path.insert(0, "..")
import dt
from d1cells import extract
spot = sys.argv[1]
dt.prepare("probe", dt.spots()[spot]["d2"])
lev, hdr, sp, st, regions = extract(dt.lev_path())
byval = {}
for r in regions:
    byval.setdefault(tuple(r.road_values), []).append(r.index)
p, d = dt.launch("probe", 4420)
try:
    dt.to_take_a_ride(d)
    time.sleep(3)
    print("pos", d.pos(), "region", d.word(dt.REGION), "flag 0x80097374 =", d.word(0x80097374),
          "regions_across", hdr.regions_across)
    for s in range(4):
        ptr = d.word(0x8009D8F4 + 4 * s)
        vals = struct.unpack("<3600I", d.ram(ptr & 0x1FFFFF | 0x80000000, 3600 * 4))
        hit = byval.get(tuple(vals))
        if not hit:   # nearest region by matching cells
            best = max(regions, key=lambda r: sum(a == b for a, b in zip(r.road_values, vals)))
            hit = "~%d (%d/3600 match)" % (best.index, sum(a == b for a, b in zip(best.road_values, vals)))
        print("slot", s, hex(ptr), "region", hit)
finally:
    p.kill()
