"""lane_compare2.py - (a) per-mode lane counts of D1 roads (ROADBOUNDS axis + road map rot) for D1 LEVs,
(b) D2 Chicago straights' lanes vs the D1 road each lands on in a converted LEV.
usage: python lane_compare2.py D2LEV CONVERTED_LEV D1LEV..."""
import sys, struct, os, math
from collections import Counter, defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from d1cells import extract
from levfile import Lev
import worldscale as ws

def lumps(lev):
    return {l.type: l.data for sec in (lev.loadtime, lev.inmem) for l in sec.lumps}

def recs(d, size, fmt):
    n, = struct.unpack_from("<i", d, 0)
    return [struct.unpack_from(fmt, d, 4 + i * size) for i in range(n)]

def d1map(path):
    lev, hdr, sp, st, regs = extract(path)
    RZ = hdr.regions_down; rid, rot = {}, {}
    for r in regs:
        for i in range(3600):
            k = (r.rx * 60 + i % 60, (RZ - 1 - r.rz) * 60 + i // 60)
            if i < len(r.road_ids): rid[k] = r.road_ids[i]
            if i < len(r.road_values): rot[k] = (r.road_values[i] >> 30) & 3
    L = lumps(lev)
    R = recs(L[8], 16, "<hhhBBhBBhh"); B = recs(L[16], 20, "<iiiiB3x")
    cells = defaultdict(list)
    for k, v in rid.items():
        if v < 0x4000: cells[v].append(k)
    per = {}
    for r, b in zip(R, B):
        cs = cells.get(r[0], [])
        cnt = Counter(rot.get(k, -1) for k in cs)
        along = max(1, r[5]); n = [round(cnt[m] / along, 1) for m in range(4)]
        per[r[0]] = dict(nl=r[3], ld=r[4], dir=b[4], n=n, across=round(len(cs) / along, 1))
    return hdr, rid, R, per

def part_a(path):
    """per-mode lane counts as the engine builds them (0x8009E744 row bytes 0..3, verified 365/365 on a Miami RAM dump):
    lane k < NumLanes -> mode base (0 z-road, 1 x-road) if LaneDirs bit k else base + 2; width = ROADBOUNDS cells across."""
    lev = __import__("levfile").Lev.parse(open(path, "rb").read()); L = lumps(lev)
    R = recs(L[8], 16, "<hhhBBhBBhh"); B = recs(L[16], 20, "<iiiiB3x")
    split, wid, pad = Counter(), Counter(), Counter()
    for r, b in zip(R, B):
        nl, ld = r[3], r[4]; a = sum(ld >> k & 1 for k in range(nl))
        split[(a, nl - a)] += 1
        w = (b[3] - b[1] + 1) if b[4] == 1 else (b[2] - b[0] + 1)
        wid[(nl, w)] += 1; pad[r[7]] += 1
    print("%-14s roads %3d | lanes (base mode, opposite): %s | (NumLanes, bounds cells across): %s | pad +0xB: %s" % (
        os.path.basename(path), len(R), dict(sorted(split.items(), key=lambda kv: -kv[1])[:7]),
        dict(sorted(wid.items(), key=lambda kv: -kv[1])[:6]), dict(pad)))

def part_b(d2path, convpath):
    L = lumps(Lev.parse(open(d2path, "rb").read()))
    ST = recs(L[40], 28, "<iiHhh4hbbbb")
    hdr, rid, R, per = d1map(convpath)
    rw, rh = hdr.cells_across * 2, hdr.cells_down * 2
    uxm, uzm = (rw + 1) * 750, rh * 750
    def cell(x, z):
        vx, vz = ws.to_d1(int(x), int(z)); return (int(math.floor((uxm + vx) / 1500.0)), int(math.floor((uzm - (vz - 750)) / 1500.0)))
    nlc, dirs, ai, park, spd, special = Counter(), Counter(), Counter(), Counter(), Counter(), 0
    lost, total_d2, total_d1, onroad = Counter(), 0, 0, Counter()
    lenw = Counter()
    for s in ST:
        nlb, ld, ail = s[9] & 0xFF, s[10] & 0xFF, s[11] & 0xFF
        nl = nlb & 15; nlc[nl] += 1; spd[(nlb >> 4) & 3] += 1
        park[((nlb >> 6) & 1, (nlb >> 7) & 1)] += 1
        if ld == 0xFF and nl == 1: special += 1; d = (1, 1)
        else:
            hi = sum(ld >> k & 1 for k in range(nl)); d = (nl - hi, hi)
        dirs[d] += 1
        aim = sum(ail >> k & 1 for k in range(nl)); ai[(nl, aim)] += 1
        lenw[nl] += s[2]
        v = rid.get(cell(s[0], s[1]), 0xFFFF)
        if v == 0xFFFF or v >= 0x4000 and v & 0x4000 == 0:
            onroad["none"] += 1; continue
        if v & 0x4000: onroad["junction box"] += 1; continue
        onroad["road"] += 1
        p = per[v]; d1l = p["across"]
        total_d2 += aim; total_d1 += d1l
        lost[(aim, int(d1l))] += 1
    print("D2 straights %d; NumLanes (lane pairs, each 1024 D2 = 1352 D1 units): %s" % (len(ST), dict(sorted(nlc.items()))))
    print("  total length per NumLanes (D2 units /1000):", {k: v // 1000 for k, v in sorted(lenw.items())})
    print("  (lanes one way, lanes other way):", dict(sorted(dirs.items(), key=lambda kv: -kv[1])[:10]), " 0xFF narrow two-way:", special)
    print("  (NumLanes, AI lanes):", dict(sorted(ai.items(), key=lambda kv: -kv[1])[:10]))
    print("  parking (left, right):", dict(park), " speed id:", dict(spd))
    print("midpoint lands on:", dict(onroad))
    print("  (D2 AI lanes, D1 cells across) for straights on a road:", dict(sorted(lost.items(), key=lambda kv: -kv[1])[:12]))
    print("  sum D2 AI lanes %d vs D1 lanes %d" % (total_d2, total_d1))

if __name__ == "__main__":
    part_b(sys.argv[1], sys.argv[2])
    for p in sys.argv[3:]: part_a(p)
