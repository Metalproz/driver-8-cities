"""worldscale.py — Driver 2 -> Driver 1 world scale.

Driver 2's world is built smaller than Driver 1's: a D1 car is ~1,050 units
long against ~760 in D2 (x1.38), a D1 road tile ~1,550 wide against ~1,060
(x1.46). Chicago is therefore scaled up. Driver 1 allows at most 350 regions of
30 x 3000 units, so the largest grid is 18 x 19 regions (1.62M x 1.71M units);
Chicago spans 1.27M units north-south, which fits at x1.32 (cars ~4% large).
The scaled city is centred on the grid.
"""
from __future__ import annotations

import struct

from cityprofile import P as _P

SCALE = 1.32
# centre of the city's D2 object extents (Chicago: x -461056..222080, z -570880..702848 -> -119488, 65984)
OFFSET_X = -round(_P.centre_d2[0] * SCALE)
OFFSET_Z = -round(_P.centre_d2[1] * SCALE)
# 18 x 19 regions = 342 (max 350) fills the engine's region table: at the map's top row the
# 2x2 region window asks for the row above (index 342+), which from column 8 on reads past
# the 350-entry table (C25: garbage region offset, CD read into address 0, kernel overwritten).
# LA keeps a ring of empty regions around its city. CHI_WORLD=480x630 (16 x 21 = 336) gives
# Chicago that ring (land: ~301 x 561 cells).
import os as _os
CELLS_ACROSS, CELLS_DOWN = (tuple(int(v) for v in _os.environ["CHI_WORLD"].split("x"))
                            if _os.environ.get("CHI_WORLD") else tuple(_P.cells))   # default since 2026-10-11 18:05 (C25); 540x570 = the old grid


def s(v: float) -> int:
    return int(round(v * SCALE))


def clamp16(v: int) -> int:
    return max(-32768, min(32767, v))


def to_d1(x: int, z: int) -> tuple[int, int]:
    return s(x) + OFFSET_X, s(z) + OFFSET_Z


def to_d2(x: int, z: int) -> tuple[int, int]:
    return int(round((x - OFFSET_X) / SCALE)), int(round((z - OFFSET_Z) / SCALE))


def scale_model(data: bytes) -> bytes:
    """Vertices (own ones only; instances borrow their source's), bounding
    sphere and collision boxes of one D2 model."""
    d = bytearray(data)
    inst, = struct.unpack_from("<h", d, 4)
    bsphere, = struct.unpack_from("<h", d, 8)
    struct.pack_into("<h", d, 8, clamp16(s(bsphere)))
    nverts, = struct.unpack_from("<h", d, 0x0C)
    verts, coll = struct.unpack_from("<i", d, 0x10)[0], struct.unpack_from("<i", d, 0x20)[0]
    own = inst < 0 and verts + 8 * nverts <= len(d)
    if own:
        for k in range(nverts):
            x, y, z = struct.unpack_from("<3h", d, verts + 8 * k)
            struct.pack_into("<3h", d, verts + 8 * k, clamp16(s(x)), clamp16(s(y)), clamp16(s(z)))
    if coll and coll + 4 <= len(d):
        n, = struct.unpack_from("<i", d, coll)
        for j in range(max(0, n)):
            p = coll + 4 + 20 * j
            if p + 20 > len(d):
                break
            typ, x, y, z, flags, yang, empty, xs, ys, zs = struct.unpack_from("<10h", d, p)
            struct.pack_into("<10h", d, p, typ, clamp16(s(x)), clamp16(s(y)), clamp16(s(z)), flags, yang,
                             empty, clamp16(s(xs)), clamp16(s(ys)), clamp16(s(zs)))
    return bytes(d)


def scale_subdivision(lump: bytes, texture_start: int) -> bytes:
    """SUBDIVISION lump: SVECTOR blocks (ground tile vertices, 9 per tile) up to
    texture_start (the lowest texture offset a tile model references), texture
    data after it. Only the vertices are scaled."""
    d = bytearray(lump)
    for p in range(0, texture_start, 8):
        x, y, z, pad = struct.unpack_from("<4h", d, p)
        if pad != 0:
            raise ValueError("SUBDIVISION: no SVECTOR at %d (pad %d)" % (p, pad))
        struct.pack_into("<3h", d, p, clamp16(s(x)), clamp16(s(y)), clamp16(s(z)))
    return bytes(d)
