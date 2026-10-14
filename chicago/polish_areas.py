"""polish_areas.py - area layout along the street network (Polish, C45).

Switch CHI_POLISH_AREAS=1 (default off = convert.py's median splits).

convert.py starts from Driver 2's own areas (super_region per region) and splits every area that
needs more than CHI_AREA_TEX textures at the median of its longest axis. Those straight cuts run
across downtown: 5255 street-network edges cross an area boundary (research_chunks.md), and every
crossing is an area load (300..400 KB, the game waits). With the switch, a split takes the cut
(axis + position, any position that leaves both halves at least MIN_SHARE of the regions) that
crosses the fewest street edges, from a reachability map of the street network:
drivable Driver 2 road surface minus collision boxes at car height, flood-filled from the spawn
(the same method as research_chunks.md), counted per pair of neighbouring Driver 1 regions.
"""
from __future__ import annotations

import collections
import hashlib
import math
import os
import pickle
import struct

import numpy as np

import worldscale as ws

RES = 256                 # Driver 2 units per reachability cell
MIN_SHARE = 0.25          # each half of a split keeps at least this share of the regions
SPAWN_D2 = (9216, 106496)


LIMIT_SHARE = float(os.environ.get("CHI_POLISH_AREAS_SHARE", "1.1"))   # mode 2: merging stops at this share of CHI_AREA_TEX


CORRIDOR_MIN_EDGES = int(os.environ.get("CHI_POLISH_CORRIDOR_MIN", "20"))   # street edges for a corridor


def corridor():
    """CHI_POLISH_CORRIDOR=1 (C45): at a boundary the street network crosses (>= CORRIDOR_MIN_EDGES
    street edges between the two regions), the switch entry moves one region back, so the area
    load starts 30 cells earlier; the border region becomes a corridor that both areas' texture and
    model sets cover (convert.loadable_areas simulates it), so nothing in it needs the other
    area's pages."""
    return os.environ.get("CHI_POLISH_CORRIDOR", "") in ("1", "2")    # 2: + ping-pong-free entries


def mode():
    return os.environ.get("CHI_POLISH_AREAS", "")


def enabled():
    return mode() in ("1", "2")


def reachability(d2_path: str):
    """(reach bool[H, W], X0, Z0) in Driver 2 coordinates, cached in work/."""
    key = hashlib.md5(open(d2_path, "rb").read(1 << 20) + open(__file__, "rb").read()).hexdigest()[:8]
    cache = os.path.join(os.path.dirname(d2_path), "polish_reach_%s.pkl" % key)
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    from PIL import Image, ImageDraw
    from collections import deque
    import d2cells
    from levfile import Lev
    from models import inmem_models, area_models
    from d2surface import Surface
    lev = Lev.parse(open(d2_path, "rb").read())
    surf = Surface(d2_path)
    _hdr, _sp, objects, _refs = d2cells.extract(d2_path)
    objs = list(objects.values()) if isinstance(objects, dict) else objects
    mem, _ = inmem_models(lev)
    allm = {**area_models(lev), **mem}
    X0, Z0 = -surf.half_x, -surf.half_z
    W, H = 2 * surf.half_x // RES, 2 * surf.half_z // RES
    S = 1024
    sw, sh = 2 * surf.half_x // S, 2 * surf.half_z // S
    drive = np.zeros((sh, sw), dtype=bool)
    ground = np.zeros((sh, sw), dtype=np.int32)
    for j in range(sh):
        z = Z0 + j * S + S // 2
        for i in range(sw):
            lv = [(h, t) for h, t in surf.levels(X0 + i * S + S // 2, z) if t not in (6, 9)]
            if lv:
                drive[j, i] = True
                ground[j, i] = min(lv, key=lambda ht: abs(ht[0]))[0]
    f = S // RES
    free = np.repeat(np.repeat(drive, f, 0), f, 1)[:H, :W].copy()
    gnd = np.repeat(np.repeat(ground, f, 0), f, 1)[:H, :W]
    img = Image.new("1", (W, H), 0)
    dr = ImageDraw.Draw(img)
    for o in objs:
        m = allm.get(o.model)
        if m is None:
            continue
        src = allm.get(m.instance_number, m) if m.instance_number >= 0 and m.instance_number != m.index else m
        cb = struct.unpack_from("<i", src.data, 0x20)[0]
        if not cb or cb + 4 > len(src.data):
            continue
        n = struct.unpack_from("<i", src.data, cb)[0]
        for k in range(max(0, min(n, 64))):
            p = cb + 4 + 20 * k
            if p + 20 > len(src.data):
                break
            _t, bx, by, bz, _f, byang, _e, xs, ys, zs = struct.unpack_from("<10h", src.data, p)
            a = -o.yang * 2 * math.pi / 64
            cx = o.x + bx * math.cos(a) + bz * math.sin(a)
            cz = o.z - bx * math.sin(a) + bz * math.cos(a)
            gi, gj = int((cx - X0) // S), int((cz - Z0) // S)
            g = ground[min(max(gj, 0), sh - 1), min(max(gi, 0), sw - 1)]
            if abs((g - 150) - (o.y + by)) > ys / 2 + 150:
                continue
            th = (o.yang + byang) * 64 * 2 * math.pi / 4096
            a0, a1 = (math.sin(th), math.cos(th)), (math.cos(th), -math.sin(th))
            pts = []
            for s0, s1 in ((1, 1), (1, -1), (-1, -1), (-1, 1)):
                px = cx + s0 * zs / 2 * a0[0] + s1 * xs / 2 * a1[0]
                pz = cz + s0 * zs / 2 * a0[1] + s1 * xs / 2 * a1[1]
                pts.append(((px - X0) / RES, (pz - Z0) / RES))
            dr.polygon(pts, fill=1)
    free &= ~np.array(img, dtype=bool)
    reach = np.zeros_like(free)
    i, j = int((SPAWN_D2[0] - X0) // RES), int((SPAWN_D2[1] - Z0) // RES)
    best = min(((di * di + dj * dj, i + di, j + dj) for dj in range(-8, 9) for di in range(-8, 9)
                if 0 <= j + dj < H and 0 <= i + di < W and free[j + dj, i + di]), default=None)
    q = deque()
    if best:
        reach[best[2], best[1]] = True
        q.append((best[1], best[2]))
    while q:
        i, j = q.popleft()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = i + di, j + dj
            if 0 <= a < W and 0 <= b < H and free[b, a] and not reach[b, a] and abs(int(gnd[b, a]) - int(gnd[j, i])) <= 400:
                reach[b, a] = True
                q.append((a, b))
    out = (reach, X0, Z0)
    pickle.dump(out, open(cache, "wb"))
    return out


def region_edges(d2_path: str, rx_n: int, rz_n: int, region_units: int, half_x: int, half_z: int):
    """Counter {(region a, region b): street edges between them} for neighbouring Driver 1 regions
    (a < b as (rx, rz) tuples), plus Counter {region: street cells}."""
    reach, X0, Z0 = reachability(d2_path)
    jj, ii = np.nonzero(reach)
    x1 = np.rint((X0 + ii * RES + RES // 2) * ws.SCALE).astype(np.int64) + ws.OFFSET_X
    z1 = np.rint((Z0 + jj * RES + RES // 2) * ws.SCALE).astype(np.int64) + ws.OFFSET_Z
    rx = np.clip((x1 + half_x) // region_units, 0, rx_n - 1)
    rz = np.clip((z1 + half_z) // region_units, 0, rz_n - 1)
    rid = -np.ones(reach.shape, dtype=np.int64)
    rid[jj, ii] = rz * rx_n + rx
    edges = collections.Counter()
    for a, b in ((rid[:, :-1], rid[:, 1:]), (rid[:-1, :], rid[1:, :])):
        m = (a >= 0) & (b >= 0) & (a != b)
        for p, q in zip(a[m].tolist(), b[m].tolist()):
            ra, rb = (p % rx_n, p // rx_n), (q % rx_n, q // rx_n)
            edges[(min(ra, rb), max(ra, rb))] += 1
    cells = collections.Counter(((r % rx_n, r // rx_n) for r in rid[rid >= 0].tolist()))
    return edges, cells


def best_split(regs, edges):
    """Cut (axis, threshold) of the region list that crosses the fewest street edges, both halves
    keeping at least MIN_SHARE of the regions. Returns the regions that move to the new area."""
    regs = sorted(regs)
    n = len(regs)
    best = None
    rs = set(regs)
    for axis in (0, 1):
        vals = sorted({r[axis] for r in regs})
        for t in vals[1:]:
            moved = [r for r in regs if r[axis] >= t]
            if not (MIN_SHARE * n <= len(moved) <= (1 - MIN_SHARE) * n):
                continue
            ms = set(moved)
            cost = sum(w for (a, b), w in edges.items() if a in rs and b in rs and ((a in ms) != (b in ms)))
            key = (cost, abs(len(moved) - n / 2))
            if best is None or key < best[0]:
                best = (key, moved)
    return best[1] if best else None


def crossing_cost(region_area: dict, edges) -> int:
    return sum(w for (a, b), w in edges.items() if region_area.get(a) != region_area.get(b))


def agglomerate(regions, tex_of_region, edges, limit):
    """CHI_POLISH_AREAS=2: build areas bottom-up. Every region starts alone; the two adjacent
    clusters joined by the most street edges merge while their texture union stays <= limit, so
    boundaries end up where few streets cross. Regions without streets join the neighbouring
    cluster that keeps the smallest texture set. Returns {region: area id}."""
    import heapq
    cluster = {r: i for i, r in enumerate(regions)}
    members = {i: {r} for i, r in enumerate(regions)}
    tex = {i: set(tex_of_region(r)) for i, r in enumerate(regions)}
    w = collections.Counter()
    for (a, b), n in edges.items():
        if a in cluster and b in cluster:
            w[(cluster[a], cluster[b])] += n
            w[(cluster[b], cluster[a])] += n
    def nb_weights(c):
        out = collections.Counter()
        for r in members[c]:
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                o = (r[0] + dx, r[1] + dz)
                if o in cluster and cluster[o] != c:
                    out[cluster[o]] += 0
        for (a, b), n in w.items():
            if a == c:
                out[b] += n
        return out
    heap = [(-n, a, b) for (a, b), n in w.items() if a < b]
    heapq.heapify(heap)
    alive = set(members)
    while heap:
        neg, a, b = heapq.heappop(heap)
        if a not in alive or b not in alive:
            continue
        cur = w.get((a, b), 0)
        if cur != -neg:
            continue
        if len(tex[a] | tex[b]) > limit:
            continue
        # merge b into a
        tex[a] |= tex[b]
        for r in members[b]:
            cluster[r] = a
        members[a] |= members[b]
        alive.discard(b)
        del members[b], tex[b]
        merged = collections.Counter()
        for (x, y), n in list(w.items()):
            if x in (a, b) or y in (a, b):
                del w[(x, y)]
                x2, y2 = (a if x == b else x), (a if y == b else y)
                if x2 != y2:
                    merged[(x2, y2)] += n
        for k, n in merged.items():
            w[k] += n
        for (x, y), n in merged.items():
            if x == a and y in alive:
                heapq.heappush(heap, (-n, min(a, y), max(a, y)))
    # clusters without street contact (water, void): join the adjacent cluster with the smallest union
    changed = True
    while changed:
        changed = False
        for c in sorted(alive):
            if c not in alive:
                continue
            if any(w.get((c, o), 0) for o in alive):
                continue
            nbs = {cluster[(r[0] + dx, r[1] + dz)] for r in members[c] for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
                   if (r[0] + dx, r[1] + dz) in cluster} - {c}
            ok = [(len(tex[o] | tex[c]), o) for o in nbs if len(tex[o] | tex[c]) <= limit]
            if ok:
                _, o = min(ok)
                tex[o] |= tex[c]
                for r in members[c]:
                    cluster[r] = o
                members[o] |= members[c]
                alive.discard(c)
                del members[c], tex[c]
                changed = True
    ids = {c: k for k, c in enumerate(sorted(alive))}
    return {r: ids[c] for r, c in cluster.items()}



# --- ping-pong-free switch entries (C45 round 2) ----------------------------------------------
# The switch rule (exe_patches.AREA_SWITCH_CODE, simulated by convert.loadable_areas) fires on the
# camera's cell: an entry (area, d) fires when the cell is past 17 towards d (d 0/1) or below 13
# (d 2/3) and another area is loaded; a region whose entries do not name the loaded area loads
# its own at once. Two regions on either side of an edge whose fires disagree switch back and
# forth on every crossing of that edge (border regions pointing at each other, or two lateral
# border regions pointing at different areas: corr3 R4, regions 185/186). CHI_POLISH_PINGPONG=1
# (also on with CHI_POLISH_CORRIDOR=2) picks each region's two entries among the usual patterns
# so that no edge ping-pongs (local search; street-heavy edges count more), keeping the
# preloading entry where it is free.
DIRS = {0: (0, 1), 1: (1, 0), 2: (0, -1), 3: (-1, 0)}
OPP = {0: 2, 1: 3, 2: 0, 3: 1}
BAND_LO, BAND_HI, RC = 13, 17, 30


def pingpong_enabled():
    return os.environ.get("CHI_POLISH_PINGPONG", "") == "1" or os.environ.get("CHI_POLISH_CORRIDOR", "") == "2"


def _fire(entries, ix, iz, loaded):
    for area, d in entries:
        if area == loaded:
            continue
        if (d == 0 and iz > BAND_HI) or (d == 1 and ix > BAND_HI) or (d == 2 and iz < BAND_LO) or (d == 3 and ix < BAND_LO):
            return area
    if loaded not in (entries[0][0], entries[1][0]):
        return entries[1][0]
    return loaded


def _edge_cells(d):
    """(cell in R, cell in R + d) pairs along the shared edge."""
    if d == 1:
        return [((RC - 1, k), (0, k)) for k in range(RC)]
    if d == 3:
        return [((0, k), (RC - 1, k)) for k in range(RC)]
    if d == 0:
        return [((k, RC - 1), (k, 0)) for k in range(RC)]
    return [((k, 0), (k, RC - 1)) for k in range(RC)]


def _pp(e1, e2, d, loads):
    n = 0
    for (x1, z1), (x2, z2) in _edge_cells(d):
        for a, b, ea, eb, xa, za, xb, zb in ((1, 2, e1, e2, x1, z1, x2, z2), (2, 1, e2, e1, x2, z2, x1, z1)):
            for L in loads:
                m = _fire(eb, xb, zb, L)
                if m != L and _fire(ea, xa, za, m) == L:
                    n += 1
                    break
    return n


def _entry(e1, e2, d, loads):
    """Cell crossings of the edge (both ways) that start a switch on the first cell after it: the
    loaded area is stable before the edge but the next region fires at once (own-area fallback
    or a band reaching the edge). Such switches coincide with the region spool (C45 corr4 R8)."""
    n = 0
    for (x1, z1), (x2, z2) in _edge_cells(d):
        for ea, eb, xa, za, xb, zb in ((e1, e2, x1, z1, x2, z2), (e2, e1, x2, z2, x1, z1)):
            for L in loads:
                if _fire(ea, xa, za, L) == L and _fire(eb, xb, zb, L) != L:
                    n += 1
                    break
    return n


ENTRY_W = float(os.environ.get("CHI_POLISH_ENTRY_W", "0"))   # weight of switches at region entry (0: corr4)


def fix_pingpong(connected: dict, region_area: dict, edge_weight=None, rounds=12):
    w = edge_weight or {}
    regs = sorted(connected)

    def loads_near(r):
        s = set()
        for dx, dz in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            q = (r[0] + dx, r[1] + dz)
            if q in connected:
                s |= {connected[q][0][0], connected[q][1][0], region_area.get(q)}
        return s

    def cost(r, ent):
        c = 0.0
        for d, (dx, dz) in DIRS.items():
            q = (r[0] + dx, r[1] + dz)
            if q not in connected:
                continue
            ww = 0.05 + w.get(tuple(sorted((r, q))), 0) / 20.0 if w else 1.0   # edges no street crosses count little
            ld = loads_near(r) | loads_near(q)
            c += ww * _pp(ent, connected[q], d, ld)
            if ENTRY_W:
                c += ENTRY_W * ww * _entry(ent, connected[q], d, ld)
        nb, d = ent[0]
        if nb != region_area[r]:                       # preloading towards the street-heavy side: tiny bonus
            dx, dz = DIRS[d]
            c -= 0.001 * w.get(tuple(sorted((r, (r[0] + dx, r[1] + dz)))), 0)
        return c

    def candidates(r):
        a = region_area[r]
        out = [connected[r], [(a, 0), (a, 2)], [(a, 1), (a, 3)]]
        for d, (dx, dz) in DIRS.items():
            q = (r[0] + dx, r[1] + dz)
            if q not in connected:
                continue
            for t in {region_area[q], connected[q][0][0], connected[q][1][0]}:
                if t != a:
                    out.append([(t, d), (a, OPP[d])])
            t, dq = connected[q][0]                     # a lateral neighbour's preload band
            if t != a and dq != OPP[d] and dq != d:
                out.append([(t, dq), (a, OPP[dq])])
        uniq = []
        for e in out:
            if e not in uniq:
                uniq.append(e)
        return uniq

    before = total_pingpong(connected, region_area)
    for _ in range(rounds):
        changed = 0
        for r in regs:
            cur = cost(r, connected[r])
            if cur <= 0:
                continue
            best = min(candidates(r), key=lambda e: cost(r, e))
            if cost(r, best) < cur - 1e-9:
                connected[r] = best
                changed += 1
        for r in regs:                                # pair moves: both sides of a ping-pong edge at once
            for d in (0, 1):
                dx, dz = DIRS[d]
                q = (r[0] + dx, r[1] + dz)
                if q not in connected or not _pp(connected[r], connected[q], d, loads_near(r) | loads_near(q)):
                    continue
                cur = cost(r, connected[r]) + cost(q, connected[q])
                old_r, old_q = connected[r], connected[q]
                best = (cur, old_r, old_q)
                for er in candidates(r):
                    connected[r] = er
                    for eq in candidates(q):
                        connected[q] = eq
                        c = cost(r, er) + cost(q, eq)
                        if c < best[0] - 1e-9:
                            best = (c, er, eq)
                connected[r], connected[q] = best[1], best[2]
                if best[1] is not old_r or best[2] is not old_q:
                    changed += 1
        if not changed:
            break
    after = total_pingpong(connected, region_area)
    print("switch entries: ping-pong cell crossings %d -> %d (CHI_POLISH_PINGPONG)" % (before, after))
    return connected


def total_pingpong(connected, region_area):
    n = 0
    for r in connected:
        for d in (0, 1):
            dx, dz = DIRS[d]
            q = (r[0] + dx, r[1] + dz)
            if q in connected:
                loads = {connected[r][0][0], connected[r][1][0], connected[q][0][0], connected[q][1][0],
                         region_area.get(r), region_area.get(q)}
                n += _pp(connected[r], connected[q], d, loads)
    return n
