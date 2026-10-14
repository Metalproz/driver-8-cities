"""lane_compare.py - D1 road lanes (ROADS + road map cells/rot) for a D1 LEV; compact tables.
usage: python lane_compare.py LEV [LEV...]"""
import sys, struct, os
from collections import Counter, defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from d1cells import extract

def roads_of(lev):
    for sec in (lev.loadtime, lev.inmem):
        for l in sec.lumps:
            if l.type == 8:
                d = l.data; n, = struct.unpack_from("<i", d, 0)
                return [struct.unpack_from("<hhhBBhBBhh", d, 4 + 16 * i) for i in range(n)]

def main(path):
    lev, hdr, sp, st, regs = extract(path)
    RZ = hdr.regions_down
    rid, rot = {}, {}
    for r in regs:
        for i in range(3600):
            c, rw = r.rx * 60 + i % 60, (RZ - 1 - r.rz) * 60 + i // 60
            if i < len(r.road_ids): rid[(c, rw)] = r.road_ids[i]
            if i < len(r.road_values): rot[(c, rw)] = (r.road_values[i] >> 30) & 3
    R = roads_of(lev)
    print("==", os.path.basename(path), "roads", len(R), "junction cells", sum(1 for v in rid.values() if v & 0x4000 and v != 0xFFFF))
    print("NumLanes:", dict(sorted(Counter(r[3] for r in R).items())), " (NumLanes,LaneDirs):", dict(sorted(Counter((r[3], r[4]) for r in R).items())))
    print("flags:", dict(Counter(r[6] for r in R)), " pad:", dict(Counter(r[7] for r in R)))
    # per road: across profile of rot values along its cells
    cells = defaultdict(list)
    for k, v in rid.items():
        if v < 0x4000: cells[v].append(k)
    prof, match, wid = Counter(), Counter(), Counter()
    for r in R:
        idx, nl, ld, ln, x0, z0 = r[0], r[3], r[4], r[5], r[8], r[9]
        cs = cells.get(idx, [])
        if not cs: prof["<no cells>"] += 1; continue
        cols = {c for c, _ in cs}; rows = {w for _, w in cs}
        xdir = len(cols) >= len(rows)        # runs along x (columns)
        acr = sorted(rows if xdir else cols)
        wid[(nl, len(acr))] += 1
        pat = []
        for a in acr:
            rv = Counter(rot.get(k, -1) for k in cs if (k[1] if xdir else k[0]) == a)
            pat.append(rv.most_common(1)[0][0])
        prof[("x" if xdir else "z", nl, ld, tuple(pat))] += 1
        exp = tuple(((1 if xdir else 0) + (2 if ld >> m & 1 else 0)) for m in range(len(acr)))
        match[exp == tuple(pat)] += 1
    print("(NumLanes, cells across):", dict(sorted(wid.items())))
    print("rot == base+2*LaneDirs bit:", dict(match))
    print("top profiles (axis, NumLanes, LaneDirs, rot per cell across low->high):")
    for k, n in prof.most_common(12): print("  ", n, k)

for p in sys.argv[1:]: main(p)
