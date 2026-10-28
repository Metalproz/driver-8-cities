"""polish_slopes.py - Driver 2's surface planes as Driver 1 surface polygons (Polish, C37 prototype, 16.10.).

Switch CHI_POLISH_SLOPES=1 (off when unset). Driver 2 stores the drivable surface per 1024 x 1024 cell as a BSP
of straight cuts at any angle with one plane (a, b, c, d; any orientation) per leaf (REDRIVER2 sdGetCell /
sdHeightOnPlane). Driver 1's ROADSURF already takes any plane (a, c: x / z gradient x 4096, d) on a 4-vertex
box or a 3-vertex triangle at any angle (first match wins; MapHeight 0x8001F5B0 / FindSurfaceD2 0x8001EEB4:
height = ((px a + pz c) >> 12) - d - cell height). Our converter wrote such cells flat or with one axis
slope (cell_slopes: per-axis, <= 0.4) or flat diagonal triangles (CHI_DIAG), so the car stood level inside
D2's sloped ground (diag_ramp: a 45 deg bank down into the river, written as a flat cell).

Here a Driver 1 cell (1500 square) is clipped against the BSP leaves of the Driver 2 cells it overlaps; every
leaf piece becomes triangles with the leaf's own plane (gradient from Driver 2, offset exact at the cell centre).
Only cells whose Driver 2 cells have one level (no stacked decks) and where a piece is sloped or the pieces
differ in height are replaced.

CHI_POLISH_SLOPES_AT="x,z,r;..." (Driver 1 coordinates) limits it to cells within r of these points
(default: the whole city, capped by the surface ids). CHI_POLISH_SLOPES_EXACT=1 (default 1 with the switch):
Driver 1 uses a and c directly as gradients (no division by b, unlike Driver 2), so a unit normal makes a 45 deg
slope only 0.71 steep; exact writes a, c = gradient x 4096 and b = sqrt(4096^2 - a^2 - c^2) (at least 1024).
"""
from __future__ import annotations

import math
import os
import struct

import worldscale as ws
from d2surface import rcos, rsin

ENABLED = os.environ.get("CHI_POLISH_SLOPES", "") == "1"
EXACT = os.environ.get("CHI_POLISH_SLOPES_EXACT", "0") == "1"   # 16.10.: the engine divides by b (exe_patches slope_div)
MIN_G = 0.03                 # a piece steeper than this counts as sloped
MIN_STEP = 40                # pieces whose centre heights differ by this count as a split
MAX_POLYS = 12               # triangles per cell (SIPOLY 52 B each)
DEADBAND = 100


def at_filter():
    v = os.environ.get("CHI_POLISH_SLOPES_AT", "")
    pts = []
    for item in v.split(";"):
        if item.strip():
            x, z, r = (int(t) for t in item.split(","))
            pts.append((x, z, r))
    return pts


# --- Driver 2 BSP leaves -------------------------------------------------------------------------------
def _clip(poly, f):
    """Part of a convex polygon where f(p) < 0 (strict side) and where f(p) >= 0."""
    lo, hi = [], []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        fp, fq = f(p), f(q)
        (lo if fp < 0 else hi).append(p)
        if (fp < 0) != (fq < 0):
            t = fp / (fp - fq)
            m = (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))
            lo.append(m); hi.append(m)
    return lo, hi


def _area(poly):
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))) / 2


def _walk(S, buf, p, poly, out, depth=0):
    """BSP node at byte offset p over the cell-local polygon -> out [(poly, plane index)]."""
    if len(poly) < 3 or _area(poly) < 1 or depth > 40 or p < 0 or p + 4 > len(buf):
        return
    v, = struct.unpack_from("<i", buf, p)
    if v >= 0:
        s = struct.unpack_from("<h", buf, p)[0]
        _leaf(S, buf, s, poly, out, depth)
        return
    sb = lambda val, lo, n: ((val >> lo) & ((1 << n) - 1)) - ((1 << n) if (val >> (lo + n - 1)) & 1 else 0)
    angle, dist, offset = sb(v, 0, 11), sb(v, 11, 12), sb(v, 23, 8)
    co, si = rcos(angle), rsin(angle)
    lo, hi = _clip(poly, lambda q: q[1] * co - q[0] * si - dist * 4096)
    _walk(S, buf, p + 4, lo, out, depth + 1)
    _walk(S, buf, p + 4 * offset, hi, out, depth + 1)


def _leaf(S, buf, ent, poly, out, depth):
    if ent == 0x7FFF or ent < 0:
        out.append((poly, None))
    elif ent & 0x4000:
        no, = struct.unpack_from("<h", buf, 6)
        _walk(S, buf, (no & 0xFFFF) + 4 * (ent & 0x3FFF), poly, out, depth + 1)
    else:
        out.append((poly, ent))


def d2_pieces(S, x0, z0, x1, z1):
    """Driver 2 rectangle (x0 < x1, z0 < z1) -> [(polygon in D2 world coords, plane tuple or None)],
    or None where a Driver 2 cell has several levels / no surface data."""
    out = []
    kx0, kx1 = (x0 - 512) >> 10, (x1 - 1 - 512) >> 10
    kz0, kz1 = (z0 - 512) >> 10, (z1 - 1 - 512) >> 10
    for kx in range(kx0, kx1 + 1):
        for kz in range(kz0, kz1 + 1):
            bx, bz = 512 + 1024 * kx, 512 + 1024 * kz
            cx0, cx1 = max(x0, bx) - bx, min(x1, bx + 1024) - bx
            cz0, cz1 = max(z0, bz) - bz, min(z1, bz + 1024) - bz
            if cx1 <= cx0 or cz1 <= cz0:
                continue
            buf = S._buffer(bx + 1, bz + 1)
            if buf is None:
                return None
            e, = struct.unpack_from("<h", buf, 8 + 2 * ((kx & 63) + (kz & 63) * 64))
            poly = [(cx0, cz0), (cx1, cz0), (cx1, cz1), (cx0, cz1)]
            if e == -1:
                out.append(([(bx + x, bz + z) for x, z in poly], None))
                continue
            if (e & 0x6000) == 0x2000:
                return None                                  # stacked levels: left to the converter
            leaves = []
            _leaf(S, buf, e, poly, leaves, 0)
            for pp, ent in leaves:
                pl = S._plane(buf, ent) if ent is not None else None
                out.append(([(bx + x, bz + z) for x, z in pp], pl))
    return out


# --- Driver 1 cell -------------------------------------------------------------------------------------
def cell_pieces(S, cx, cz):
    """Driver 1 cell centred at (cx, cz): [(local polygon (px east, pz north), gx, gz, y0)] with y (down,
    Driver 1 units) = y0 + gx px + gz pz, or None (stacked / no data / water piece)."""
    xa, za = ws.to_d2(cx - 750, cz - 750)
    xb, zb = ws.to_d2(cx + 750, cz + 750)
    pcs = d2_pieces(S, min(xa, xb), min(za, zb), max(xa, xb), max(za, zb))
    if pcs is None:
        return None
    out = []
    for poly, pl in pcs:
        if pl is None or (pl[0] & 0x1F if pl[0] < 32 else pl[0]) in (6, 9):
            return None
        # plane in Driver 1: y_down = -height * SCALE, linear inside the piece
        mx = sum(p[0] for p in poly) / len(poly); mz = sum(p[1] for p in poly) / len(poly)
        ix, iz = int(round(mx)), int(round(mz))
        h0 = S.height(pl, ix, iz); hx = S.height(pl, ix + 64, iz); hz = S.height(pl, ix, iz + 64)
        gx, gz = -(hx - h0) / 64.0, -(hz - h0) / 64.0     # D1 y-down per unit (scale cancels)
        X, Z = ws.to_d1(ix, iz)
        y_at = -h0 * ws.SCALE
        lp = [(ws.SCALE * p[0] + ws.OFFSET_X - cx, ws.SCALE * p[1] + ws.OFFSET_Z - cz) for p in poly]
        y0 = y_at - gx * (X - cx) - gz * (Z - cz)
        out.append((lp, gx, gz, y0))
    return out


def interesting(pieces):
    if not pieces:
        return False
    if any(math.hypot(gx, gz) >= MIN_G for _, gx, gz, _ in pieces):
        return True
    ys = [y0 for _, _, _, y0 in pieces]
    return max(ys) - min(ys) >= MIN_STEP


def triangles(pieces):
    """[(tri 6-tuple local, gx, gz, y0)]: pieces merged by equal plane, fanned (winding as diagonal_cut)."""
    tris = []
    for lp, gx, gz, y0 in pieces:
        lp = [(max(-750, min(750, int(round(x)))), max(-750, min(750, int(round(z))))) for x, z in lp]
        dedup = []
        for p in lp:
            if not dedup or p != dedup[-1]:
                dedup.append(p)
        if len(dedup) > 1 and dedup[0] == dedup[-1]:
            dedup.pop()
        if len(dedup) < 3 or _area(dedup) < 400:
            continue
        for i in range(1, len(dedup) - 1):
            (x0, z0), (x1, z1), (x2, z2) = dedup[0], dedup[i], dedup[i + 1]
            cr = (x1 - x0) * (z2 - z0) - (z1 - z0) * (x2 - x0)
            if cr == 0:
                continue
            if cr > 0:
                (x1, z1), (x2, z2) = (x2, z2), (x1, z1)
            tris.append(((x0, z0, x1, z1, x2, z2), gx, gz, y0))
    return tris


def plane_words(a, c):
    """(a, b, c) as written: exact gradients (b from the unit length, at least 1024)."""
    b = math.sqrt(max(4096.0 * 4096.0 - a * a - c * c, 1024.0 * 1024.0))
    return int(round(a)), int(round(b)), int(round(c))


def _hull(pts):
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts
    cr = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cr(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


def cell_polys(pieces):
    """Pieces -> (background (gx, gz, y0), [(tri, gx, gz, y0)]): the largest plane group becomes a full-cell
    box placed LAST (first match wins), the other groups' pieces are merged where their union stays convex
    and fanned into triangles."""
    groups = {}
    for lp, gx, gz, y0 in pieces:
        if math.hypot(gx, gz) < MIN_G:
            gx = gz = 0.0
            y0 = 0 if abs(y0) < DEADBAND else y0            # kerbs are street level (convert.HEIGHT_DEADBAND)
        key = (round(gx, 2), round(gz, 2), int(round(y0 / 8.0)))
        groups.setdefault(key, []).append([(round(x, 1), round(z, 1)) for x, z in lp])
    area = {k: sum(_area(p) for p in v) for k, v in groups.items()}
    bg = max(area, key=area.get)
    out = []
    for k, polys in groups.items():
        if k == bg:
            continue
        polys = [p for p in polys if len(p) >= 3]
        merged = True
        while merged and len(polys) > 1:
            merged = False
            for i in range(len(polys)):
                for j in range(i + 1, len(polys)):
                    h = _hull(polys[i] + polys[j])
                    if abs(_area(h) - _area(polys[i]) - _area(polys[j])) <= 0.01 * _area(h) + 50:
                        polys[i] = h; polys.pop(j); merged = True
                        break
                if merged:
                    break
        gx, gz, y8 = k
        for p in polys:
            out += triangles([(p, gx, gz, y8 * 8)])
    return (bg[0], bg[1], bg[2] * 8), out


# C37 sharing (Infrastructure 16.10.): surfaces are cell-local and rotatable, so cells whose quantized pieces match
# share one ROADSURF surface (ids < 900, in-memory lump). CHI_POLISH_SLOPES_Q = "grid,gradient step,offset step":
# triangle corners on a grid (cell edges kept), gradients (x 4096) and plane offsets rounded. "0,0,8" = exact.
_Q = [int(v) for v in os.environ.get("CHI_POLISH_SLOPES_Q", "125,128,32").split(",")]


def qg(v):
    return int(round(v / _Q[1])) * _Q[1] if _Q[1] else v


def qd(v):
    return int(round(v / _Q[2])) * _Q[2]


def qfoot(t):
    """Triangle (x0, z0, x1, z1, x2, z2) snapped to the grid, clockwise as before; None if it collapses."""
    if not _Q[0]:
        return t
    g = _Q[0]
    sn = lambda v: v if abs(v) == 750 else max(-750, min(750, int(round(v / g)) * g))
    p = [(sn(t[0]), sn(t[1])), (sn(t[2]), sn(t[3])), (sn(t[4]), sn(t[5]))]
    cr = (p[1][0] - p[0][0]) * (p[2][1] - p[0][1]) - (p[1][1] - p[0][1]) * (p[2][0] - p[0][0])
    if abs(cr) < 2 * g * g:
        return None
    if cr > 0:
        p[1], p[2] = p[2], p[1]
    return (p[0][0], p[0][1], p[1][0], p[1][1], p[2][0], p[2][1])


def apply(world, hw, planes, C):
    """convert.surface_planes hook: replace the plane lists of matching land cells (hw: {cell: written
    height}) by Driver 2's pieces. C = the convert module (FULL, NO_SWITCH, SLOPE_SIGN, ROAD_UNIT, CELL)."""
    import d2surface
    S = d2surface.Surface(C.D2_LEV)
    half_x, half_z = world["across"] // 2 * C.CELL, world["down"] // 2 * C.CELL
    pts = at_filter()
    n, ntri, skipped = 0, 0, 0
    world["polish_slopes"] = {}
    for k, h in sorted(hw.items()):
        cx, cz = k[0] * C.ROAD_UNIT - half_x, half_z - k[1] * C.ROAD_UNIT
        if pts and not any(abs(cx - x) <= r and abs(cz - z) <= r for x, z, r in pts):
            continue
        pcs = cell_pieces(S, cx, cz)
        if not interesting(pcs):
            continue
        (bgx, bgz, by0), tris = cell_polys(pcs)
        if len(tris) + 1 > MAX_POLYS:
            skipped += 1
            continue
        enc = lambda gx, gz: (qg(int(round(-gx * 4096))) * C.SLOPE_SIGN[0], qg(int(round(-gz * 4096))) * C.SLOPE_SIGN[1])
        pl = []
        for foot, gx, gz, y0 in tris:
            foot = qfoot(foot)
            if foot is None:
                continue
            a, c = enc(gx, gz)
            pl.append((a, c, qd(y0 - h), foot, C.NO_SWITCH))
        a, c = enc(bgx, bgz)
        pl.append((a, c, qd(by0 - h), C.FULL, C.NO_SWITCH))
        planes[k] = (1, pl, (True,) * len(pl))
        world["polish_slopes"][k] = len(tris)
        n += 1; ntri += len(tris)
    print("road map: Polish C37 slopes: %d cells get Driver 2's planes (%d triangles; %d cells over %d polygons skipped)"
          % (n, ntri, skipped, MAX_POLYS))
