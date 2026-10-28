"""polish_pvs.py - Driver 2's own cell visibility (PVS) for Driver 1's PVS (Polish, C40).

Switch CHI_POLISH_PVS (default d2 since b13, user verdict 13.10.; anything else = pvs.py's view radius only).

pvs.py gives every Driver 1 cell (3000 units) a circular view radius (5..9 cells, by polygon
budget) and no occlusion, so the per-object renderer walks and culls every object around
the camera, also behind the tall blocks. Driver 2 ships per-cell occlusion data: each
region's "roadm" spool block starts with int cbr and cbr bytes of PVS (REDRIVER2 map.c:
big-endian u16 cell offsets at +0 (32 x 32 cells of 2048 units, one more entry for the end), an
encoding table at +0x802, nibble-coded run data, decoded by PVSDecode into a 21 x 21 window
around the camera cell, pvs[dx + 10 + (dz + 10) * 21]; an empty cell = all visible).

A Driver 1 window entry is kept only if the radius disc has it AND Driver 2 sees one of
the Driver 2 cells overlapping it from one of the Driver 2 cells overlapping the camera
cell (conservative union; Driver 2 cells without data count as all visible). So nothing
Driver 2 itself would draw is removed.
"""
from __future__ import annotations

import hashlib
import os
import pickle
import struct

import numpy as np

import pvs as d1pvs
import worldscale as ws
from levfile import Lev
from mapinfo import MapHeader, SpoolInfo, MAP, SPOOLINFO

BLOCK = 2048
SQ = 21                      # Driver 2 PVS window
W1 = d1pvs.WINDOW            # Driver 1 window (19)


def enabled():
    return os.environ.get("CHI_POLISH_PVS", "d2") == "d2"


def _decode(celldata: bytes, table: bytes) -> np.ndarray:
    """REDRIVER2 PVSDecode -> 21 x 21 uint8 (row = dz + 10, column = dx + 10)."""
    n = len(celldata)
    nyb = []
    for b in celldata:
        nyb += [b >> 4, b & 15]                # M_SHRT_2(c, c >> 4) & 0xf0f, stored little-endian
    nyb += [0, 0, 0]                       # the C decoder may read just past the end
    buf = bytearray(SQ * SQ + 8)
    sym_of = lambda k: table[k] << 8 | table[k + 1]   # M_SHRT_2 = big-endian
    pix, i = 0, 0
    while i < n * 2:
        ni = nyb[i]; i += 1
        if ni < 12:
            sym = sym_of(ni * 2)
        else:
            if i == n * 2:
                break
            sym = (ni & 3) * 16 + nyb[i]; i += 1
            if sym < 60:
                sym = sym_of(sym * 2 + 24)
            else:
                sym = ((sym & 3) * 16 + nyb[i]) * 16 + nyb[i + 1]
                i += 2
        pix += sym >> 1
        if pix < len(buf):
            buf[pix] = 1
        pix += 1
        if sym & 1:
            if pix < len(buf):
                buf[pix] = 1
            pix += 1
    d = np.frombuffer(bytes(buf[:SQ * SQ]), dtype=np.uint8).copy()
    d[SQ * SQ - 1] ^= 1
    # op[0] ^= op[21], from the second-to-last row upwards (column pass, bottom-up)
    for k in range(SQ * SQ - SQ - 1, -1, -1):
        d[k] ^= d[k + SQ]
    # *op ^= op[1] within each row, right to left (excluding the last column)
    g = d.reshape(SQ, SQ)
    for c in range(SQ - 2, -1, -1):
        g[:, c] ^= g[:, c + 1]
    return g.copy()


class D2Pvs:
    def __init__(self, path: str):
        key = hashlib.md5(open(path, "rb").read(1 << 20) + open(__file__, "rb").read()).hexdigest()[:8]
        import inputs                     # Option A: caches in the setup cache (chicago/work in work mode)
        cache = os.path.join(inputs.cache_dir(), "polish_pvs_%s.pkl" % key)
        lev = Lev.parse(open(path, "rb").read())
        self.hdr = MapHeader.parse(lev.loadtime.get(MAP).data)
        self.cs = self.hdr.cell_size
        self.half_x = self.hdr.cells_across // 2 * self.cs
        self.half_z = self.hdr.cells_down // 2 * self.cs
        if os.path.exists(cache):
            self.cells = pickle.load(open(cache, "rb"))
            return
        sp = SpoolInfo.parse(lev.inmem.get(SPOOLINFO).data)
        rs = self.hdr.region_size
        ra = self.hdr.cells_across // rs
        self.cells = {}                                   # (cx, cz) -> 21x21 array or None (= all visible)
        for idx, off in enumerate(sp.region_offsets):
            if off == 0xFFFF:
                continue
            offset, _a, _b, _pvs, cd0, cd1, cd2, _sr, _nca, roadm, _roadh = sp.spools[off]
            base = (offset + cd0 + cd1 + cd2) * BLOCK
            blk = lev.spooled[base: base + roadm * BLOCK]
            if len(blk) < 8:
                continue
            cbr, = struct.unpack_from("<i", blk, 0)
            bp = blk[4:4 + cbr]
            if len(bp) < 0x802 + 32:
                continue
            table = bp[0x802:]
            rx, rz = idx % ra, idx // ra
            for cell in range(rs * rs):
                a, b = struct.unpack_from(">HH", bp, cell * 2)
                cx, cz = rx * rs + cell % rs, rz * rs + cell // rs
                self.cells[(cx, cz)] = _decode(bp[a:b], table) if b > a else None
        pickle.dump(self.cells, open(cache, "wb"))

    def d2_cells(self, x0, z0, x1, z1):
        """Driver 2 cells overlapping the Driver 1 rectangle [x0, x1) x [z0, z1) (Driver 1 units)."""
        a = ws.to_d2(x0, z0)
        b = ws.to_d2(x1 - 1, z1 - 1)
        c0 = (min(a[0], b[0]) + self.half_x) // self.cs, (min(a[1], b[1]) + self.half_z) // self.cs
        c1 = (max(a[0], b[0]) + self.half_x) // self.cs, (max(a[1], b[1]) + self.half_z) // self.cs
        return c0, c1


def masks_for_grid(d2: D2Pvs, radii: np.ndarray, cell: int, half_x: int, half_z: int):
    """{(cx, cz): 361-entry bit list (window row-major, row = dz + 9, column = dx + 9)} for every
    Driver 1 cell where all overlapping Driver 2 cells carry PVS data (others keep the radius)."""
    down, across = radii.shape
    R = W1 // 2
    off = np.arange(-R, R + 1)
    k = ws.SCALE
    # Driver 1 cell edges -> Driver 2 cell index ranges, per axis (same formula as to_d2)
    def rng_x(c):            # c: array of Driver 1 cell x indices -> (first, last) Driver 2 cell
        x0 = c * cell - half_x
        a = np.rint((x0 - ws.OFFSET_X) / k).astype(np.int64)
        b = np.rint((x0 + cell - 1 - ws.OFFSET_X) / k).astype(np.int64)
        return (a + d2.half_x) // d2.cs, (b + d2.half_x) // d2.cs
    def rng_z(c):
        z0 = c * cell - half_z
        a = np.rint((z0 - ws.OFFSET_Z) / k).astype(np.int64)
        b = np.rint((z0 + cell - 1 - ws.OFFSET_Z) / k).astype(np.int64)
        return (a + d2.half_z) // d2.cs, (b + d2.half_z) // d2.cs
    out = {}
    stats = {"cells": 0, "kept_entries": 0, "radius_entries": 0}
    discs = {r: np.array(d1pvs.mask(r), dtype=bool).reshape(W1, W1) for r in range(d1pvs.MIN_RADIUS, d1pvs.MAX_RADIUS)}
    full = np.ones((W1, W1), dtype=bool)
    ax0, ax1 = rng_x(np.arange(across))
    az0, az1 = rng_z(np.arange(down))
    for cz in range(down):
        for cx in range(across):
            a0, a1, b0, b1 = int(ax0[cx]), int(ax1[cx]), int(az0[cz]), int(az1[cz])
            srcs = [(a, b) for a in range(a0, a1 + 1) for b in range(b0, b1 + 1)]
            known = [d2.cells.get(s_, "missing") for s_ in srcs]
            if any(kk is None or isinstance(kk, str) for kk in known):
                continue
            U = np.zeros((b1 - b0 + SQ, a1 - a0 + SQ), dtype=np.uint8)
            for (a, b), kk in zip(srcs, known):
                U[b - b0: b - b0 + SQ, a - a0: a - a0 + SQ] |= kk
            S = np.zeros((U.shape[0] + 1, U.shape[1] + 1), dtype=np.int32)
            S[1:, 1:] = U.cumsum(0).cumsum(1)
            gx0, gz0 = a0 - 10, b0 - 10
            nx = np.clip(cx + off, 0, across - 1)
            nz = np.clip(cz + off, 0, down - 1)
            i0, i1 = ax0[nx] - gx0, ax1[nx] - gx0          # per window column
            j0, j1 = az0[nz] - gz0, az1[nz] - gz0          # per window row
            out_x = (i1 < 0) | (i0 >= U.shape[1])
            out_z = (j1 < 0) | (j0 >= U.shape[0])
            i0c, i1c = np.clip(i0, 0, U.shape[1] - 1), np.clip(i1, 0, U.shape[1] - 1)
            j0c, j1c = np.clip(j0, 0, U.shape[0] - 1), np.clip(j1, 0, U.shape[0] - 1)
            J0, I0 = np.meshgrid(j0c, i0c, indexing="ij")
            J1, I1 = np.meshgrid(j1c, i1c, indexing="ij")
            v = S[J1 + 1, I1 + 1] - S[J0, I1 + 1] - S[J1 + 1, I0] + S[J0, I0]
            vis = (v > 0) | out_z[:, None] | out_x[None, :]   # beyond Driver 2's window: the radius decides
            r = int(radii[cz, cx])
            disc = discs.get(r, full)
            bits = vis & disc
            stats["cells"] += 1
            stats["kept_entries"] += int(bits.sum())
            stats["radius_entries"] += int(disc.sum())
            out[(cx, cz)] = bits.flatten().astype(np.uint8).tolist()
    return out, stats


LA_BARRELS = (41620, 48161, 45326, 47442)   # LA's own per-barrel PVS buffer sizes (SPOOLINFO)
# C44 (13.10.): the barrel buffers are allocated back to back in the level heap (pointers at 0x800AA7E8,
# 0x801A4FEC..); LA's sizes moved everything after them up by 57 KB. Default now keeps the converter's
# 32768 per barrel (memory layout unchanged); CHI_POLISH_PVS_BUF=la restores LA's sizes.
def barrels():
    if os.environ.get("CHI_POLISH_PVS_BUF", "") == "la":
        return LA_BARRELS
    return (32768,) * 4


def _cluster_fit(build, masks, limit):
    """Denser PVS (C40 round 2): cells share one stream per cluster of similar masks; a cluster's
    mask is the OR of its members (a superset of each, so nothing visible is dropped). Leader
    clustering with a growing tolerance T (extra visible entries a member may receive) until the
    region block fits `limit`. Returns the block or None."""
    ints = [None if m is None else int("".join("1" if b else "0" for b in reversed(m)), 2) for m in masks]
    idx = [i for i, v in enumerate(ints) if v is not None]
    for T in (2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128):
        leaders = []                                   # [mask int, members]
        for i in sorted(idx, key=lambda i: -ints[i].bit_count()):
            v = ints[i]
            best = None
            for L in leaders:
                add = (L[0] | v).bit_count() - v.bit_count()
                grow = (L[0] | v).bit_count() - L[0].bit_count()
                if add <= T and grow <= T and (best is None or add < best[0]):
                    best = (add, L)
            if best is None:
                leaders.append([v, [i]])
            else:
                best[1][0] |= v
                best[1][1].append(i)
        out = list(masks)
        for v, members in leaders:
            bits = [(v >> k) & 1 for k in range(len(masks[members[0]]))]
            for i in members:
                out[i] = bits
        blob = build(out)
        if len(blob) <= limit:
            return blob
    return None


def region_block(radii_cells, masks_cells, limit=None) -> bytes:
    """Like pvs.region_block, with an explicit window mask per cell where given. With `limit`
    (bytes), masks with the smallest gain fall back to their radius disc until the block fits."""
    masks = list(masks_cells)

    def build(ms):
        streams, table, body = {}, [], bytearray()
        for r, m in zip(radii_cells, ms):
            bits = m if m is not None else (None if r >= d1pvs.MAX_RADIUS else d1pvs.mask(r))
            if bits is None or all(bits):
                table.append(0)
                continue
            st = d1pvs.encode(list(bits))
            if st not in streams:
                streams[st] = d1pvs.TABLE + len(body)
                body += st
            table.append(streams[st])
        return struct.pack("<%dI" % len(table), *table) + bytes(body)

    blob = build(masks)
    if limit is None or len(blob) <= limit:
        return blob
    if os.environ.get("CHI_POLISH_PVS_PACK", "1") == "1":
        packed = _cluster_fit(build, masks, limit)
        if packed is not None:
            return packed
    def gain(i):
        r = radii_cells[i]
        disc = d1pvs.mask(r) if r < d1pvs.MAX_RADIUS else [1] * (W1 * W1)
        return sum(disc) - sum(masks[i])
    order = sorted((i for i, m in enumerate(masks) if m is not None), key=gain)
    step = max(1, len(order) // 20)
    while len(blob) > limit and order:
        for i in order[:step]:
            masks[i] = None
        order = order[step:]
        blob = build(masks)
    return blob
