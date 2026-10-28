"""d2surface.py - Driver 2 road surface (height + type) lookup, offline.

Port of REDRIVER2 dr2roads.c (sdGetCell, sdGetBSP, sdHeightOnPlane). Each
region's spooled block ends with a "roadm" block: int cbr, PVS data, and at
4 + cbr the surface buffer (shorts): [0] = 2, [1] plane offset (bytes),
[2] level-list offset, [3] BSP node offset, [4..] 64 x 64 cell entries for
1024-unit cells. An entry is -1 (sea), a plane index, 0x4000|node (BSP), or
0x2000|list (several levels: (height threshold, entry) pairs, end -0x8000).
Plane: short surface, a, b, c; int d. Surface types: 0 concrete, 4 grass,
6 water, 8 alley, 9 deep water, 11 sand; 16..31 event planes (bridges),
0x4000|curve = curved road plane.

    s = Surface(inputs.path("d2_CHICAGO.LEV"))   # inputs.py: from the player's Driver 2 disc
    s.levels(x, z) -> [(height, surface type), ...]   (y down: street ~ 0)
"""
from __future__ import annotations

import math
import struct

from levfile import Lev
from mapinfo import MapHeader, SpoolInfo, MAP, SPOOLINFO

BLOCK = 2048
L_CURVES2 = 41
SEA = (-2048, 9)            # REDRIVER2 sea_plane: deep water, 2048 below (height, type)


def rcos(a):
    return int(round(4096 * math.cos(a * 2 * math.pi / 4096)))


def rsin(a):
    return int(round(4096 * math.sin(a * 2 * math.pi / 4096)))


def ratan2(y, x):
    return int(round(math.atan2(y, x) * 4096 / (2 * math.pi))) & 0xFFF


def sbits(v, lo, n):
    v = (v >> lo) & ((1 << n) - 1)
    return v - (1 << n) if v & (1 << (n - 1)) else v


class Surface:
    def __init__(self, path: str):
        lev = Lev.parse(open(path, "rb").read())
        self.hdr = MapHeader.parse(lev.loadtime.get(MAP).data)
        sp = SpoolInfo.parse(lev.inmem.get(SPOOLINFO).data)
        self.across = self.hdr.cells_across * self.hdr.cell_size // 65536
        self.half_x = self.hdr.cells_across // 2 * self.hdr.cell_size
        self.half_z = self.hdr.cells_down // 2 * self.hdr.cell_size
        self.regions = {}
        self.bad = 0
        for idx, off in enumerate(sp.region_offsets):
            if off == 0xFFFF:
                continue
            offset, _a, _b, pvs, cd0, cd1, cd2, _sr, _nca, roadm, roadh = sp.spools[off]
            base = (offset + cd0 + cd1 + cd2) * BLOCK
            blk = lev.spooled[base: base + roadm * BLOCK]
            if len(blk) < 8:
                continue
            cbr, = struct.unpack_from("<i", blk, 0)
            buf = blk[4 + cbr:]
            if len(buf) < 8 or struct.unpack_from("<h", buf, 0)[0] != 2:
                continue
            self.regions[idx] = buf
        self.curves = []
        cv = None
        for sec in (lev.loadtime, lev.inmem):
            try:
                cv = sec.get(L_CURVES2).data
                break
            except Exception:
                pass
        if cv:
            n, = struct.unpack_from("<i", cv, 0)
            for k in range(n):
                mx, mz, start, end = struct.unpack_from("<iihh", cv, 4 + 28 * k)
                gradient, height = struct.unpack_from("<hh", cv, 4 + 28 * k + 20)
                self.curves.append((mx, mz, gradient, height))

    # --- lookup --------------------------------------------------------------
    def _buffer(self, x, z):
        rx = (x - 512 + self.half_x) >> 16
        rz = (z - 512 + self.half_z) >> 16
        return self.regions.get(rz * self.across + rx)

    def _plane(self, buf, index):
        po, = struct.unpack_from("<h", buf, 2)
        o = (po & 0xFFFF) + 12 * index
        if o + 12 > len(buf):
            return None
        surf, a, b, c, d = struct.unpack_from("<4hi", buf, o)
        if struct.unpack_from("<i", buf, o)[0] == -1:
            return None
        return surf, a, b, c, d

    def _bsp(self, buf, node_index, cx, cy):
        no, = struct.unpack_from("<h", buf, 6)
        p = (no & 0xFFFF) + 4 * node_index
        for _ in range(64):
            if p < 0 or p + 4 > len(buf):
                self.bad += 1
                return -1, p
            v, = struct.unpack_from("<i", buf, p)
            if v >= 0:
                return struct.unpack_from("<h", buf, p)[0], p
            angle, dist, offset = sbits(v, 0, 11), sbits(v, 11, 12), sbits(v, 23, 8)
            dot = cy * rcos(angle) - cx * rsin(angle)
            p += 4 if dot < dist * 4096 else 4 * offset
        return -1, p

    def height(self, plane, x, z):
        surf, a, b, c, d = plane
        if (d >> 1 ^ d) & 0x40000000:
            return d ^ 0x40000000
        if (surf & 0xE000) == 0x4000 and b == 0 and self.curves:
            k = (surf & 0x1FFF) - 32
            if 0 <= k < len(self.curves):
                mx, mz, gradient, h = self.curves[k]
                ang = ratan2(mz - z, mx - x)
                return (gradient * ((ang + 2048) & 0xFFF)) // 4096 - h
        if b:
            if b == 0x4000:
                return -d
            lx = a * (((x - 512) & 0xFFFF) + 512)
            ly = c * (((z - 512) & 0xFFFF) + 512)
            return -d - int((lx + ly) / b)
        return 0

    def switches(self, x, z):
        """Driver 2's own level switch heights at (x, z) (sdGetCell): None for a cell with
        one level, else [(height, threshold), ...] top level first; the wheel leaves a
        level for the next lower one when -256 - wheel y > threshold, i.e. once its height
        (y up, like height()) is below -(256 + threshold). The last level has None."""
        buf = self._buffer(x, z)
        if buf is None:
            return None
        cx, cy = (x - 512) & 1023, (z - 512) & 1023
        e, = struct.unpack_from("<h", buf, 8 + 2 * ((((x - 512) >> 10) & 63) + (((z - 512) >> 10) & 63) * 64))
        if e == -1 or (e & 0x6000) != 0x2000:
            return None
        lo, = struct.unpack_from("<h", buf, 4)
        p, pairs = (lo & 0xFFFF) + 2 * (e & 0x1FFF), []
        for _ in range(16):
            if p + 4 > len(buf):
                return None
            thr, ent = struct.unpack_from("<hh", buf, p)
            pairs.append((None if thr == -0x8000 else thr, ent))
            if thr == -0x8000:
                break
            p += 4
        out = []
        for thr, ent in pairs:
            seen = 0
            while ent & 0x4000 and seen < 8:
                ent2, _ = self._bsp(buf, ent & 0x3FFF, cx, cy)
                ent = -1 if ent2 == 0x7FFF else ent2; seen += 1
            pl = self._plane(buf, ent) if ent >= 0 else None
            if pl is None:
                return None                       # a level without a plane: no usable list
            out.append((self.height(pl, x, z), thr))
        return out if len(out) > 1 else None

    def levels(self, x, z):
        """All surfaces at (x, z): [(height, type)], y down (street ~ 0)."""
        buf = self._buffer(x, z)
        if buf is None:
            return [SEA]
        cx, cy = (x - 512) & 1023, (z - 512) & 1023
        e, = struct.unpack_from("<h", buf, 8 + 2 * ((((x - 512) >> 10) & 63) + (((z - 512) >> 10) & 63) * 64))
        if e == -1:
            return [SEA]
        entries = []
        if (e & 0x6000) == 0x2000:
            # [threshold, entry] pairs ..., -0x8000, last entry  (sdGetCell)
            lo, = struct.unpack_from("<h", buf, 4)
            p = (lo & 0xFFFF) + 2 * (e & 0x1FFF)
            for _ in range(16):
                if p + 4 > len(buf):
                    break
                thr, ent = struct.unpack_from("<hh", buf, p)
                entries.append(ent)
                if thr == -0x8000:
                    break
                p += 4
        else:
            entries = [e]
        out = []
        for ent in entries:
            seen = 0
            while ent & 0x4000 and seen < 8:
                ent2, p = self._bsp(buf, ent & 0x3FFF, cx, cy)
                if ent2 == 0x7FFF:
                    ent2 = -1
                ent = ent2; seen += 1
            if ent < 0:
                continue
            pl = self._plane(buf, ent)
            if pl is None:
                out.append(SEA)
                continue
            out.append((self.height(pl, x, z), pl[0] & 0x1F if pl[0] < 32 else pl[0]))
        return out or [SEA]
