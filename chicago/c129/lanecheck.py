"""C129 lane check: are traced AI cars on Driver 2's lanes?

python lanecheck.py ROADS.bin TRACE.csv [--off X,Z]
TRACE.csv rows: t, frame, slot, x, z, heading (Driver 1 world units, heading 4096 = full turn).
Each sample -> Driver 2 coordinates ((v - off) / 1.32) -> the nearest AI lane centre line (straights: offset across the
road, curves: radius) with a travel direction within 90 deg of the car's heading. Pass criterion (NOTES "C129 plan"):
distance <= 256 (D2 units), heading within 64/4096 of the lane tangent (<= 3 % of samples may exceed it, as Driver 2's own path
does), no axis heading on a diagonal / curve, speed (D2 units / frame between samples of one
car) <= the road's limit (56 / 97 / 138) + 8. Samples off every straight / curve span (inside junctions) are counted apart.
Prints a summary per car and overall; exit 1 when any lane sample fails."""
from __future__ import annotations

import csv, math, struct, sys
from collections import defaultdict

SPEED = (56, 97, 138, 138)


def load(path):
    b = open(path, "rb").read()
    if b[:4] == b"C129":
        off = struct.unpack_from("<2i", b, 4)
        b = b[12:]
    else:
        off = None
    ns, nc, nj = struct.unpack_from("<3i", b, 4)
    st, cv = [], []
    p = 16
    for i in range(ns):
        mx, mz, length, bing, ang = struct.unpack_from("<iiHhh", b, p)
        nl, ld, ai = struct.unpack_from("<BBB", b, p + 22)
        st.append((mx, mz, length, ang, nl, ld, ai)); p += 28
    for i in range(nc):
        mx, mz, s0, e0 = struct.unpack_from("<iihh", b, p)
        nl, ld, ins, ai = struct.unpack_from("<BBbB", b, p + 24)
        cv.append((mx, mz, s0, e0, nl, ld, ins, ai)); p += 28
    return st, cv, off


def lane_ok(nl, ld, ai, lane):
    units = nl & 15
    if not (ai >> (lane // 2)) & 1:
        return None
    # parking sub-lanes (NumLanes bit 6 / 7) stay valid: Driver 2's own route nodes run in them (host reference, 0x1bf)
    if ld == 0xFF and nl == 1:
        return lane & 1
    return (ld >> (lane // 2)) & 1


def diff(a, b):
    return ((b - a + 2048) & 4095) - 2048


def nearest(st, cv, x, z, h):
    best = None
    for i, (mx, mz, length, ang, nl, ld, ai) in enumerate(st):
        dx, dz = x - mx, z - mz
        if abs(dx) > length + 8192 or abs(dz) > length + 8192:
            continue
        a = ang * 2 * math.pi / 4096
        along = dx * math.sin(a) + dz * math.cos(a)
        if abs(along) > length / 2:
            continue
        side = -dx * math.cos(a) + dz * math.sin(a)          # InitNodeList laneDist - NumLanes * 512
        for lane in range((nl & 15) * 2):
            d = lane_ok(nl, ld, ai, lane)
            if d is None:
                continue
            ldir = (ang + 2048) & 4095 if d else ang
            if abs(diff(ldir, h)) >= 1024:
                continue
            centre = lane * 512 + 256 - (nl & 15) * 512
            e = abs(side - centre)
            if best is None or e < best[0]:
                best = (e, abs(diff(ldir, h)), i, lane, SPEED[(nl >> 4) & 3], min(ang & 1023, 1024 - (ang & 1023)) > 64)
    for i, (mx, mz, s0, e0, nl, ld, ins, ai) in enumerate(cv):
        dx, dz = x - mx, z - mz
        r = math.hypot(dx, dz)
        if r > (ins + (nl & 15) + 4) * 1024:
            continue
        ang = int(round(math.atan2(dx, dz) * 4096 / (2 * math.pi))) & 4095
        if ((ang - s0) & 4095) > ((e0 - s0) & 4095):
            continue
        for lane in range((nl & 15) * 2):
            d = lane_ok(nl, ld, ai, lane)
            if d is None:
                continue
            ldir = (ang + 1024) & 4095 if d == 0 else (ang - 1024) & 4095
            if abs(diff(ldir, h)) >= 1024:
                continue
            e = abs(r - (ins * 1024 + lane * 512 + 256))
            if best is None or e < best[0]:
                best = (e, abs(diff(ldir, h)), 0x4000 | i, lane, SPEED[(nl >> 4) & 3], True)
    return best


def main(argv):
    st, cv, off = load(argv[0])
    if "--off" in argv:
        off = tuple(int(v) for v in argv[argv.index("--off") + 1].split(","))
    rows = list(csv.reader(open(argv[1])))
    per = defaultdict(list)
    for r in rows:
        if not r or r[0].startswith("#") or r[0] == "t":
            continue
        t, f, slot, x, z, h = float(r[0]), int(r[1]), int(r[2]), int(r[3]), int(r[4]), int(r[5])
        per[slot].append((t, f, (x - off[0]) / 1.32, (z - off[1]) / 1.32, h & 4095))
    tot = defaultdict(int)
    worst_d = worst_h = 0
    for slot, ss in sorted(per.items()):
        c = defaultdict(int)
        wd = wh = 0
        prev = None
        for t, f, x, z, h in ss:
            nb = nearest(st, cv, x, z, h)
            if nb is None or nb[0] > 1024:
                c["junction/off"] += 1
            else:
                e, hd, road, lane, lim, offaxis = nb
                c["lane"] += 1
                wd, wh = max(wd, e), max(wh, hd)
                if e > 256:
                    c["far"] += 1
                if hd > 64:
                    c["heading"] += 1
                if offaxis and h % 1024 == 0 and hd > 16:
                    c["snapped"] += 1                # an axis heading on a diagonal / curve: Driver 1's quadrant snap
                if prev and f > prev[1]:
                    sp = math.hypot(x - prev[2], z - prev[3]) / (f - prev[1])
                    c["speed>lim"] += sp > lim + 8
            prev = (t, f, x, z)
        worst_d, worst_h = max(worst_d, wd), max(worst_h, wh)
        for k, v in c.items():
            tot[k] += v
        print("slot %2d: %4d samples, lane %d (far %d, heading %d, speed>lim %d), junction/off %d, worst %.0f / %d"
              % (slot, len(ss), c["lane"], c["far"], c["heading"], c["speed>lim"], c["junction/off"], wd, wh))
    # heading: Driver 2's own path (host reference, 10 Vegas routes) leaves 64/4096 on 2.2 % of its lane samples (look-ahead
    # across lane changes / corner nodes): pass = at most 3 %
    ok = (tot["lane"] > 0 and tot["far"] == 0 and tot["heading"] <= 0.03 * tot["lane"] and tot["speed>lim"] == 0
          and tot["snapped"] == 0)
    print("TOTAL %s: lane samples %d, far %d, heading %d (%.1f %%), snapped %d, speed>lim %d, junction/off %d, worst dist %.0f heading %d"
          % ("PASS" if ok else "FAIL", tot["lane"], tot["far"], tot["heading"], 100.0 * tot["heading"] / max(1, tot["lane"]),
             tot["snapped"], tot["speed>lim"], tot["junction/off"], worst_d, worst_h))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
