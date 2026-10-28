"""polish_tess.py - split oversized polygons (Polish, 16.10.; quay_wall).

Switch CHI_POLISH_TESS=MAXSPAN (Driver 1 units, e.g. 1500; off when unset). Driver 1 draws a polygon whose
vertices pass behind the camera stretched across the screen (no near clipping; its near subdivision 0x8003110C
only acts close to the camera and still projects the corners). Driver 2's river quay wall model (1115: two
256 x 7152 quads, 9440 D1 units long) showed as huge grey planes at quay_wall. Such quads (FT4 type 11, GT4
type 21) are cut into strips along their long sides, each at most MAXSPAN long, UVs and normals interpolated
like the corners. City-wide: 35 polygons in 11 models longer than 3000 D2 units.

Runs on the converted (scaled) model data before d1models.convert_models; instances keep their own polygons
(none of the affected models is instanced in Chicago - checked by the caller's stats).
"""
from __future__ import annotations

import math
import os
import struct

from models import Model, POLY_SIZES


def max_span():
    v = os.environ.get("CHI_POLISH_TESS", "")
    return int(v) if v.isdigit() else 0


def _lerp(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def _split_quad(p: bytes, t: int, verts: list, span: int):
    """p: one FT4/GT4 polygon (bytes); returns (new polygons, new vertices to append)."""
    vi = list(p[4:8])
    if max(vi) >= len(verts):
        return [p], []
    P = [verts[i] for i in vi]
    if t == 11:
        uv_at = 8
    else:                                   # GT4: v0..v3, n0..n3, uv0..uv3
        uv_at = 12
    uv = [(p[uv_at + 2 * k], p[uv_at + 2 * k + 1]) for k in range(4)]
    d01, d12 = math.dist(P[0], P[1]), math.dist(P[1], P[2])
    # ring 0-1-2-3: split along 1->2 / 0->3 when those are the long sides, else along 0->1 / 3->2
    if d12 >= d01:
        a0, a1, b0, b1 = 0, 3, 1, 2          # strip k: (A_k, B_k, B_k+1, A_k+1) keeps the ring order 0,1,2,3
        L = d12
    else:
        a0, a1, b0, b1 = 0, 1, 3, 2          # strip k: (A_k, A_k+1, B_k+1, B_k) at ring positions 0, 1, 2, 3
        L = d01
    n = math.ceil(L / span)
    if n <= 1:
        return [p], []
    base = len(verts)
    newv, idx = [], {}

    def vid(side, k):
        """vertex index for point k (0..n) on side 'A' (a0->a1) or 'B' (b0->b1)."""
        if (side, k) in idx:
            return idx[(side, k)]
        if k == 0:
            i = vi[a0] if side == "A" else vi[b0]
        elif k == n:
            i = vi[a1] if side == "A" else vi[b1]
        else:
            s0, s1 = (P[a0], P[a1]) if side == "A" else (P[b0], P[b1])
            newv.append(_lerp(s0, s1, k / n))
            i = base + len(newv) - 1
        idx[(side, k)] = i
        return i

    def uvat(side, k):
        u0, u1 = (uv[a0], uv[a1]) if side == "A" else (uv[b0], uv[b1])
        return _lerp(u0, u1, k / n)

    out = []
    for k in range(n):
        # corners in the original ring positions
        corner = {a0: ("A", k), b0: ("B", k), b1: ("B", k + 1), a1: ("A", k + 1)}
        q = bytearray(p)
        for pos in range(4):
            side, kk = corner[pos]
            q[4 + pos] = vid(side, kk)
            u, v = uvat(side, kk)
            q[uv_at + 2 * pos] = max(0, min(255, u))
            q[uv_at + 2 * pos + 1] = max(0, min(255, v))
        out.append(bytes(q))
    if base + len(newv) > 255:               # vertex indices are bytes
        return [p], []
    return out, newv


def tessellate(data: bytes, span: int):
    """One model (own vertices): (new data, number of polygons split) - unchanged when nothing is long."""
    m = Model.parse(-1, data)
    if m.instance_number >= 0 or m.num_polys == 0 or m.vertices <= 0 or m.poly_block >= len(data):
        return data, 0
    verts = [struct.unpack_from("<3h", data, m.vertices + 8 * i) for i in range(m.num_vertices)]
    polys, q = [], m.poly_block
    for _ in range(m.num_polys):
        t = data[q] & 31
        polys.append(bytes(data[q: q + POLY_SIZES[t]]))
        q += POLY_SIZES[t]
    poly_end = q
    newpolys, added, split = [], [], 0
    for p in polys:
        t = p[0] & 31
        if t in (11, 21):
            pts = [verts[i] for i in p[4:8] if i < len(verts)]
            if max((math.dist(a, b) for a in pts for b in pts), default=0) > span:
                parts, nv = _split_quad(p, t, verts + added, span)
                if len(parts) > 1:
                    added += nv
                    newpolys += parts
                    split += 1
                    continue
        newpolys.append(p)
    if not split:
        return data, 0
    # rebuild: vertex block grows by the new vertices, polygon block by the new polygons; other blocks shift
    vblock = b"".join(struct.pack("<4h", x, y, z, 0) for x, y, z in verts + added)
    pblock = b"".join(newpolys)
    hdr_fields = {k: struct.unpack_from("<i", data, k)[0] for k in (0x10, 0x14, 0x18, 0x1C, 0x20)}
    v_end = m.vertices + 8 * m.num_vertices
    segs = sorted({off for off in hdr_fields.values() if 0 < off < len(data)} | {m.vertices, m.poly_block})
    pieces, newoff, pos = [], {}, 0x24 if min(segs) >= 0x24 else min(segs)
    head = bytearray(data[:min(segs)])
    out = bytearray(head)
    for k, s in enumerate(segs):
        e = segs[k + 1] if k + 1 < len(segs) else len(data)
        newoff[s] = len(out)
        if s == m.vertices:
            out += vblock + data[v_end:e]
        elif s == m.poly_block:
            out += pblock + data[poly_end:e]
        else:
            out += data[s:e]
        while len(out) % 4:
            out.append(0)
    for k, off in hdr_fields.items():
        if off in newoff:
            struct.pack_into("<i", out, k, newoff[off])
    struct.pack_into("<h", out, 0x0C, len(verts) + len(added))
    struct.pack_into("<h", out, 0x0E, len(newpolys))
    return bytes(out), split


def tessellate_all(models: dict):
    """{index: data} -> ({index: data}, stats). Instances of a tessellated model keep their own polygons."""
    span = max_span()
    if not span:
        return models, {}
    out, split, nm = {}, 0, 0
    for i, d in models.items():
        nd, s = tessellate(d, span)
        out[i] = nd
        if s:
            split += s; nm += 1
    return out, {"tess_polys": split, "tess_models": nm}
