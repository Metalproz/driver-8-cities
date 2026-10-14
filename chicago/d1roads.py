"""d1roads.py - Driver 1 road network (ROADS / JUNCTIONS / ROADBOUNDS / JUNCBOUNDS) for Chicago
from Driver 2's road graph, plus the road map cells (roadm road ids, lane directions).

Ported from EXP's devtest/exp_work/build_full.py "merge v2" (ANYL=1 MAXROADS=420 MINDEG2=1:
420 roads, 257 junctions; byte-identical lumps). Driver 1 caps: 420 roads load, 421 resets.
- Straights with the same direction that touch end to end merge into one road (union-find);
  the 420 longest roads are kept. Junctions and curves become D1 junctions (a curve = a corner
  junction) when at least 2 kept roads meet there.
- D1 roads are axis-aligned: dir 0 runs along z, dir 1 along x; the record (x, z) is the low
  corner of the road's cell rectangle, bounds x1 = x - W/2, y1 = z - H/2 (fitted on NY/Miami).

Lanes (Infrastructure 2026-10-13, from Miami's road map): a road cell's rotation bits
(roadh value >> 30) are its lane's travel direction - dir-0 roads 0 / 2, dir-1 roads 1 / 3,
the low side of the road (smaller cell index across) base, the high side base + 2 - and the
AI picks its mode (and the per-mode lane counts) from them. So every road covers at least
2 cells across (one per direction): the cells whose centres lie within the D2 road's width
(NumLanes lane pairs x 1024 D2 units, scaled), else the 2 cells nearest its centre line; at
most 3 (D1's widest roads).

Cell frame = the game's (0x80021820, 0x8001EF00) = the converter's road-map grid (col, row):
col = floor((x + W*750 + 750) / 1500), row = floor((H*750 - z + 750) / 1500) from the top. ROADS /
JUNCTIONS / ROADBOUNDS use it directly (Miami verified: junction (x, z) = its box's low corner).
Storage: spool region (col // 60, rows_of_regions - 1 - row // 60) - the regions count bottom-up
- at index (col % 60) + (row % 60) * 60 (convert.py does this).

Junctions (Miami): every junction owns a box of road-map cells valued 0x4000 | junction id, as
wide as its roads (2x2 .. 3x3); the AI's state 2 -> 3 needs the car's cell to be such a junction
cell (0x80021820 returns 1 there; plain road cells return 0). Its roads start next to the box.
"""
from __future__ import annotations

import math
import struct
from collections import defaultdict

import worldscale as ws
from levfile import Lev

MAX_ROADS = int(__import__("os").environ.get("CHI_MAX_ROADS", "483"))   # exe limit 483 since C48 (D1's own: 422)
SAME_DIR = 8                 # D2 angle units (of 2048 for a line) for "same direction"
TOUCH = 600                  # D2 units between merged straights' ends
# traffic lights (junction type 1): "all" = every junction with 3-4 exits (Miami has them at 63%),
# "d2" = only where Driver 2 has lights (JUNCTIONS2_NEW flags & 1), "none"
LIGHTS = __import__("os").environ.get("CHI_JUNC_LIGHTS", "none" if __import__("os").environ.get("CHI_JUNC_NOLIGHTS") == "1" else "all")
# D2's lanes (research_traffic_d2_vs_d1.md, 2026-10-13): lanes per direction from each straight's AI
# lane units (AILanes; LaneDirs bit 0 = along the straight's angle, 1 = against: right-hand traffic),
# capped at 2 per direction (as Driver 1's cities); a road is a + b cells wide, one cell per lane
D2_LANES = __import__("os").environ.get("CHI_D2_LANES", "1") != "0"
MAX_DIR_LANES = 2
KEEP_ONEWAY = __import__("os").environ.get("CHI_KEEP_ONEWAY", "1") != "0"
WATER_MAX = 0.5              # share of a road's centre cells in water that drops it
LANE_PAIR = 1024             # D2 road width per NumLanes unit (2 x 512)
MAX_WIDTH = int(__import__("os").environ.get("CHI_ROAD_MAXW", "3"))   # cells across a D1 road
BOX_MAX = int(__import__("os").environ.get("CHI_JUNC_BOX_MAX", "4"))   # junction box cells per side


def sin4k(a):
    return math.sin(a * 2 * math.pi / 4096)


def cos4k(a):
    return math.cos(a * 2 * math.pi / 4096)


def _recs(data, size, fmt):
    n, = struct.unpack_from("<i", data, 0)
    return [struct.unpack_from(fmt, data, 4 + i * size) for i in range(n)]


def _sid(v):
    return {0: "S", 0x2000: "J", 0x4000: "C"}.get(v & 0xE000, "?"), v & 0x1FFF


def build(d2_path: str, rw: int, rh: int, water=None) -> dict:
    """rw x rh = the D1 road map in cells; water = set of (col, row) water cells (roads at least
    WATER_MAX in water are left out). Returns {"lumps": {type: bytes}, "cells": {(col, row): roadm
    value (road id or 0x4000 | junction)}, "rot": {(col, row): lane direction of road cells},
    "stats": str}."""
    lev = Lev.parse(open(d2_path, "rb").read())
    L = {l.type: l.data for sec in (lev.loadtime, lev.inmem) for l in sec.lumps}
    # straights: Midx, Midz, length, bing, angle, Conn[4], NumLanes, LaneDirs, AILanes, packing
    ST = [dict(x=r[0], z=r[1], len=r[2], ang=r[4] % 4096, conn=r[5:9], lanes=r[9] & 0xF, ldirs=r[10], ai=r[11])
          for r in _recs(L[40], 28, "<iiHhh4hBBBB")]
    # curves: Midx, Midz, start, end, Conn[4], gradient, height, NumLanes, LaneDirs, inside, AILanes
    CV = [dict(x=r[0], z=r[1], start=r[2] % 4096, end=r[3] % 4096, inside=r[12], lanes=r[10] & 0xF)
          for r in _recs(L[41], 28, "<iihh4hhhbbbb")]
    # junctions: ExitIdx[4], flags (bit 0 = traffic lights; civ_ai.c)
    JL = [bool(r[4] & 1) for r in _recs(L[43], 12, "<4hI")]
    ox, oy = rw // 2, rh // 2
    uxm, uzm = (rw + 1) * 750, rh * 750

    def cell_of(x2, z2):
        vx, vz = ws.to_d1(int(round(x2)), int(round(z2)))
        return ((uxm + vx) / 1500.0, (uzm - (vz - 750)) / 1500.0)

    def ends(s):
        dx, dz = s["len"] / 2 * sin4k(s["ang"]), s["len"] / 2 * cos4k(s["ang"])
        return (s["x"] - dx, s["z"] - dz), (s["x"] + dx, s["z"] + dz)

    # ---- straight groups (union-find over direct links)
    E = [ends(s) for s in ST]
    par = list(range(len(ST)))

    def f(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    def way(st):
        """'two', or the world direction of a one-way straight (D2 one-ways are kept, user R16)."""
        a = st["ang"] % 2048
        al = sum(1 for k in range(st["lanes"]) if st["ai"] >> k & 1 and not st["ldirs"] >> k & 1)
        ag = sum(1 for k in range(st["lanes"]) if st["ai"] >> k & 1 and st["ldirs"] >> k & 1)
        if (al > 0) == (ag > 0):
            return "two"
        z = a < 8 or a > 2040
        along_pos = cos4k(st["ang"]) > 0 if z else sin4k(st["ang"]) > 0
        return ("z" if z else "x") + ("+" if along_pos == (al > 0) else "-")

    for i, s in enumerate(ST):
        for v in s["conn"]:
            if v == -1 or _sid(v)[0] != "S":
                continue
            j = _sid(v)[1]
            da = abs(s["ang"] - ST[j]["ang"]) % 2048
            if min(da, 2048 - da) > SAME_DIR:
                continue
            if D2_LANES and KEEP_ONEWAY and way(s) != way(ST[j]):
                continue                                # no merge across a one-way / two-way change
            if min(math.hypot(a[0] - b[0], a[1] - b[1]) for a in E[i] for b in E[j]) <= TOUCH:
                par[f(i)] = f(j)
    groups = defaultdict(list)
    for i in range(len(ST)):
        groups[f(i)].append(i)
    G = []
    for mem in groups.values():
        s0 = ST[mem[0]]
        a = s0["ang"] % 2048
        dv = (sin4k(s0["ang"]), cos4k(s0["ang"]))
        pts = [p for i in mem for p in E[i]]
        proj = lambda p: p[0] * dv[0] + p[1] * dv[1]
        best = max(mem, key=lambda i: ST[i]["lanes"])
        axis = "z" if (a < 8 or a > 2040) else "x"
        # lanes per D1 direction (b: mode base = north / east, a: the other way), by length
        votes = defaultdict(int)
        for i in mem:
            st = ST[i]
            al = sum(1 for k in range(st["lanes"]) if st["ai"] >> k & 1 and not st["ldirs"] >> k & 1)
            ag = sum(1 for k in range(st["lanes"]) if st["ai"] >> k & 1 and st["ldirs"] >> k & 1)
            to_base = cos4k(st["ang"]) > 0 if axis == "z" else sin4k(st["ang"]) > 0
            b, a2 = (al, ag) if to_base else (ag, al)
            b, a2 = min(b, MAX_DIR_LANES), min(a2, MAX_DIR_LANES)
            votes[(b, a2) if b + a2 else (1, 1)] += st["len"]
        ab = max(votes, key=votes.get)
        G.append(dict(mem=mem, lanes=ST[best]["lanes"], ldirs=ST[best]["ldirs"], ab=ab,
                      axis=axis,
                      lo=min(pts, key=proj), hi=max(pts, key=proj),
                      mid=(sum(ST[i]["x"] for i in mem) / len(mem), sum(ST[i]["z"] for i in mem) / len(mem))))
    # ---- nodes: junctions and curves with the straights attached to them
    attach = defaultdict(list)
    for gi, g in enumerate(G):
        for i in g["mem"]:
            for v in ST[i]["conn"]:
                if v == -1:
                    continue
                t, k = _sid(v)
                if t in ("J", "C"):
                    attach[(t, k)].append((gi, i))

    def curve_pos(c):
        r = c["inside"] * 1024 + 256 + 512 * c["lanes"]
        a = (c["start"] + ((c["end"] - c["start"]) & 4095) // 2) % 4096
        return (c["x"] + r * sin4k(a), c["z"] + r * cos4k(a))

    node_pos = {}
    for n, lst in attach.items():
        if n[0] == "C":
            node_pos[n] = curve_pos(CV[n[1]])
            continue
        cand = [p for gi, i in lst for p in E[i]]
        c = (sum(p[0] for p in cand) / len(cand), sum(p[1] for p in cand) / len(cand))
        for _ in range(3):
            sel = [min(E[i], key=lambda p: math.hypot(p[0] - c[0], p[1] - c[1])) for gi, i in lst]
            c = (sum(p[0] for p in sel) / len(sel), sum(p[1] for p in sel) / len(sel))
        node_pos[n] = c
    gnode = defaultdict(list)
    for n, lst in attach.items():
        for gi, i in lst:
            if n not in gnode[gi]:
                gnode[gi].append(n)

    def group_end_for(gi, n):
        g, p = G[gi], node_pos[n]
        return 0 if math.hypot(g["lo"][0] - p[0], g["lo"][1] - p[1]) <= math.hypot(g["hi"][0] - p[0], g["hi"][1] - p[1]) else 1

    # ---- the longest MAX_ROADS roads; nodes where >= 2 of them meet
    lens_g = [math.hypot(g["hi"][0] - g["lo"][0], g["hi"][1] - g["lo"][1]) for g in G]
    dry, wet = list(range(len(G))), 0
    if water:
        def wet_share(g):
            a, b = cell_of(*g["lo"]), cell_of(*g["hi"])
            n = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1])) + 1)
            pts = [(int(math.floor(a[0] + (b[0] - a[0]) * t / (n - 1))), int(math.floor(a[1] + (b[1] - a[1]) * t / (n - 1))))
                   for t in range(n)]
            return sum(p in water for p in pts) / len(pts)
        dry = [gi for gi in dry if wet_share(G[gi]) < WATER_MAX]
        wet = len(G) - len(dry)
    # Driver 1 cities have (almost) no dead ends (Miami 0, NY 5): a traffic car at a road end
    # without a junction (or at a junction left with one road) stops for good. Such roads are
    # banned and the 420 refilled from the next-longest ones until none is left.
    banned = set()
    for _round in range(100):
        # avenues first; a one-way street counts like a two-lane street (D2 keeps them in pairs)
        weight = (lambda i: lens_g[i] * max(sum(G[i]["ab"]), 2)) if D2_LANES else (lambda i: lens_g[i])
        kept = sorted(sorted([gi for gi in dry if gi not in banned], key=lambda i: -weight(i))[:MAX_ROADS])
        ridx = {gi: k for k, gi in enumerate(kept)}
        nodes = []
        for gi in kept:
            for n in gnode[gi]:
                if n not in nodes and len(set(gj for gj, _ in attach[n] if gj in ridx)) >= 2:
                    nodes.append(n)
        nidx = {n: k for k, n in enumerate(nodes)}
        # ---- roads: cell ranges (game cell = floor of cell_of, as 0x80021820 / 0x8001EF00)
        R = []                                            # per kept road: along, a0, a1, span, high, w
        widths = defaultdict(int)
        for gi in kept:
            g = G[gi]
            lo_c, hi_c = cell_of(*g["lo"]), cell_of(*g["hi"])
            along = 0 if g["axis"] == "x" else 1          # cell axis the road runs along (0 = column)
            across = 1 - along
            a0 = int(math.floor(min(lo_c[along], hi_c[along])))
            a1 = int(math.floor(max(lo_c[along], hi_c[along])))
            # across: cells within the D2 road's width, at least 2, at most MAX_WIDTH
            uc = (lo_c[across] + hi_c[across]) / 2
            hw = g["lanes"] * LANE_PAIR * ws.SCALE / 1500.0 / 2
            span = [i for i in range(int(math.floor(uc - hw)) - 1, int(math.ceil(uc + hw)) + 1)
                    if abs(i + 0.5 - uc) <= hw]
            if len(span) < 2:
                i0 = int(math.floor(uc - 0.5))
                span = [i0, i0 + 1]
            while len(span) > MAX_WIDTH:                  # drop the cell farthest from the centre
                span.remove(max(span, key=lambda i: abs(i + 0.5 - uc)))
            span.sort()
            high = [i + 0.5 > uc for i in span]           # the middle of 3 goes by its centre
            if all(high) or not any(high):
                high = [k >= len(span) / 2 for k in range(len(span))]
            lb, la = 1, 1
            if D2_LANES:                                  # a + b cells centred on the D2 road; the
                lb, la = g["ab"]                          # b lanes (mode base) on the high side
                w = la + lb
                s0 = int(math.floor(uc - w / 2.0 + 0.5))
                span = list(range(s0, s0 + w))
                high = [m >= la for m in range(w)]
            widths[len(span)] += 1
            R.append(dict(along=along, a0=a0, a1=a1, span=span, high=high, la=la, lb=lb))
        # ---- links: end 0 = the low cell end along the road, end 1 = the high end (Miami's ROADS);
        # junction exit slots (Miami / NY): 0 = the road on the -z side (it ends here), 1 = +x
        # (starts here), 2 = +z (starts here), 3 = -x (ends here). The AI's mode is the slot it
        # leaves by, so a road sits in its side's slot. One road per slot and end (the nearest wins);
        # a dropped link stays -1 (dead end).
        node_roads = defaultdict(list)
        for gi in kept:
            r = R[ridx[gi]]
            mid = (r["a0"] + r["a1"]) / 2.0
            for n in gnode[gi]:
                if n in nidx:
                    na = cell_of(*node_pos[n])[r["along"]]
                    e = 0 if na < mid else 1
                    node_roads[nidx[n]].append((abs(na - (r["a0"] if e == 0 else r["a1"])), ridx[gi], e))
        slot_of = {(1, 0): 2, (1, 1): 0, (0, 0): 1, (0, 1): 3}      # (along, end at this junction)
        conn = [[-1, -1] for _ in kept]
        slots = {}
        for k in range(len(nodes)):
            taken = {}
            for dist, ri, e in sorted(node_roads.get(k, [])):
                sl = slot_of[(R[ri]["along"], e)]
                if sl in taken or conn[ri][e] != -1:
                    continue
                taken[sl] = ri
                conn[ri][e] = k
            slots[k] = taken
        if _round == 0 and __import__("os").environ.get("CHI_ROADS_DEBUG"):
            why = defaultdict(int)
            for ri, gi in enumerate(kept):
                if 0 not in G[gi]["ab"]:
                    continue
                for e in (0, 1):
                    if conn[ri][e] != -1:
                        why["linked"] += 1; continue
                    cand = [n for n in gnode[gi] if group_end_for(gi, n) == e]
                    if not cand: why["no D2 node at this end"] += 1
                    elif not any(n in nidx for n in cand): why["node has < 2 kept roads"] += 1
                    else: why["slot taken at the junction"] += 1
            print("one-way road ends (round 0):", dict(why))
        bad = {ri for ri in range(len(kept)) if -1 in conn[ri]}
        bad |= {ri for k in range(len(nodes)) if len(slots[k]) < 2 for ri in slots[k].values()}
        if not bad:
            break
        banned |= {kept[ri] for ri in bad}
    # ---- junction boxes (Miami: the junction's cells, 0x4000 | id, a box as wide as its roads;
    # the record (x, z) is the box's low corner; the roads start right next to the box)
    boxes = []
    for n in nodes:
        k = nidx[n]
        pc = cell_of(*node_pos[n])
        rng = []
        for axis in (0, 1):                           # box columns from z roads, rows from x roads
            sp = [c for ri in slots[k].values() if R[ri]["along"] != axis for c in R[ri]["span"]]
            if sp and max(sp) - min(sp) < 4:
                lo, hi = min(sp), max(sp)
            else:                                     # no crossing road (or misaligned ones): 2 cells
                lo = int(math.floor(pc[axis] - 0.5))
                hi = lo + 1
            if hi - lo + 1 > BOX_MAX:                 # A/B: smaller boxes, centred on the roads
                lo = int(math.floor((lo + hi + 1) / 2.0 - BOX_MAX / 2.0))
                hi = lo + BOX_MAX - 1
            rng.append((lo, hi))
        boxes.append(rng)
        for sl, ri in slots[k].items():               # roads end next to the box
            r, ax = R[ri], R[ri]["along"]
            lo, hi = rng[ax]
            if conn[ri][0] == k:
                r["a0"] = hi + 1
            if conn[ri][1] == k:
                r["a1"] = lo - 1
    roads_rec, bounds_rec, cells, rot = [], [], {}, {}
    for ri, r in enumerate(R):
        if r["a1"] < r["a0"]:                         # squeezed between two boxes: one cell
            r["a1"] = r["a0"]
        along, a0, length, span = r["along"], r["a0"], r["a1"] - r["a0"] + 1, r["span"]
        c0, w = span[0], len(span)
        ldirs = sum(1 << m for m in range(w) if r["high"][m])
        x0, z0 = (a0, c0) if along == 0 else (c0, a0)
        dirc = 1 if along == 0 else 0
        roads_rec.append((ri, conn[ri][0], conn[ri][1], w, ldirs, length, 0, 0, x0, z0))
        x1, y1 = x0 - ox, z0 - oy
        if dirc == 1:
            bounds_rec.append((x1, y1, x1 + length - 1, y1 + w - 1, 1))
        else:
            bounds_rec.append((x1, y1, x1 + w - 1, y1 + length - 1, 0))
        base = 1 if dirc == 1 else 0
        for kk in range(length):
            for m, ci in enumerate(span):
                key = (a0 + kk, ci) if along == 0 else (ci, a0 + kk)
                cells[key] = ri
                rot[key] = base + (2 if r["high"][m] else 0)
    junc_rec, jb_rec = [], []
    for k, ((bx0, bx1), (bz0, bz1)) in enumerate(boxes):
        for i in range(bx0, bx1 + 1):
            for j in range(bz0, bz1 + 1):
                cells[(i, j)] = 0x4000 | k
                rot.pop((i, j), None)
        # Miami: type 1 and entry flags 4 at junctions with 3-4 exits, 0 at corners; pad byte
        # 0x22 (+ runtime bits; 0x800138A0 reads it as row byte 3)
        many = len(slots[k]) >= 3
        n = nodes[k]
        # one-way roads (Miami: all 87 flag-2 entries): the exit whose direction has no lane is banned
        def banned_exit(sl, ri):
            base = 1 if R[ri]["along"] == 0 else 0
            return (R[ri]["lb"] if sl == base else R[ri]["la"]) == 0
        lit = LIGHTS == "all" or (LIGHTS == "d2" and n[0] == "J" and JL[n[1]])
        typ = 1 if many and lit else 0
        flat = []
        for sl in range(4):
            ri = slots[k].get(sl)
            if ri is None:
                flat += [-1, -1, 0, 0]
            else:                                     # fromJunc = the junction at the road's other end
                flat += [conn[ri][1] if conn[ri][0] == k else conn[ri][0], ri,
                         (4 if many else 0) | (2 if banned_exit(sl, ri) else 0), 0]
        # pad byte = box size (Miami / NY / SF): columns << 4 | rows
        junc_rec.append((k, bx0, bz0, flat, typ, (bx1 - bx0 + 1) << 4 | (bz1 - bz0 + 1)))
        # JUNCBOUNDS (Miami 234/234, NY 258/258): two ints, the box centre in world units
        # relative to the map centre: ((x + w/2 - W/2) * 1500, (z + h/2 - H/2) * 1500)
        jb_rec.append((int((bx0 + (bx1 - bx0 + 1) / 2 - ox) * 1500), int((bz0 + (bz1 - bz0 + 1) / 2 - oy) * 1500)))
    bad = sum(1 for r in roads_rec for c in (r[1], r[2]) if c != -1 and not 0 <= c < len(nodes))
    bad += sum(1 for k, px, pz, flat, _, _ in junc_rec for e in range(4)
               if flat[4 * e + 1] != -1 and k not in roads_rec[flat[4 * e + 1]][1:3])
    if bad:
        raise SystemExit("d1roads: %d road/junction link violations" % bad)
    lumps = {
        8: struct.pack("<i", len(roads_rec)) + b"".join(struct.pack("<hhhBBhBBhh", *r) for r in roads_rec),
        9: struct.pack("<i", len(junc_rec)) + b"".join(
            struct.pack("<hBBhBB" + "h" * 16 + "hh", k, typ, pad, 0, 0, 0, *flat, px, pz) for k, px, pz, flat, typ, pad in junc_rec),
        16: struct.pack("<i", len(bounds_rec)) + b"".join(struct.pack("<iiiiB3x", *b[:4], b[4]) for b in bounds_rec),
        17: struct.pack("<i", len(jb_rec)) + b"".join(struct.pack("<ii", *b) for b in jb_rec),
    }
    ow = [gi for gi in range(len(G)) if 0 in G[gi]["ab"]]
    ow_stats = "one-way groups %d (kept %d, banned %d, wet %d)" % (
        len(ow), sum(1 for gi in ow if gi in ridx), sum(1 for gi in ow if gi in banned), sum(1 for gi in ow if gi not in dry))
    box_sizes = defaultdict(int)
    for (bx0, bx1), (bz0, bz1) in boxes:
        box_sizes[(bx1 - bx0 + 1, bz1 - bz0 + 1)] += 1
    stats = (ow_stats + "; " + "roads %d (of %d groups, %d in water left out, %d dead-end roads banned), junctions %d (%d with lights: %s; boxes %s), dead road ends %d, "
             "road cells %d, widths %s" % (
                 len(roads_rec), len(G), wet, len(banned), len(junc_rec), sum(1 for j in junc_rec if j[4]), LIGHTS,
                 dict(sorted(box_sizes.items(), key=lambda kv: -kv[1])[:5]),
                 sum(1 for r in roads_rec for c in r[1:3] if c == -1), len(rot), dict(sorted(widths.items()))))
    return {"lumps": lumps, "cells": cells, "rot": rot, "stats": stats}
