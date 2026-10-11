"""models.py — parse level MODELS (in-memory pack + spooled area models).

MODEL header (OpenDriver2Tools d2_types.h), 36 bytes:
    i16 shape_flags, i16 flags2, i16 instance_number,
    u8 tri_verts, u8 zBias, i16 bounding_sphere, i16 num_point_normals,
    i16 num_vertices, i16 num_polys,
    i32 vertices, i32 poly_block, i32 normals, i32 point_normals, i32 collision_block
Offsets are relative to the model start. Polygon records begin with a type
byte (low 5 bits = primitive type).
"""
from __future__ import annotations

import collections
import struct
from dataclasses import dataclass

from levfile import Lev
from mapinfo import SpoolInfo, SPOOLINFO, MODELS, MODELNAMES

HDR = "<3hBB4h5i"
HDR_SIZE = struct.calcsize(HDR)

# primitive type (byte & 31) -> record size (OpenDriver2Tools PolySizes); 0 = invalid
POLY_SIZE_TABLE = [8, 12, 16, 24, 20, 20, 28, 32, 8, 12, 16, 16, 0, 0, 0, 0,
                   12, 12, 12, 16, 20, 20, 24, 24, 0, 0, 0, 0, 0, 0, 0, 0]
POLY_SIZES = {t: n for t, n in enumerate(POLY_SIZE_TABLE) if n}


@dataclass
class Model:
    index: int
    data: bytes
    shape_flags: int = 0
    flags2: int = 0
    instance_number: int = 0
    bounding_sphere: int = 0
    num_vertices: int = 0
    num_polys: int = 0
    vertices: int = 0
    poly_block: int = 0
    normals: int = 0
    point_normals: int = 0
    collision_block: int = 0

    @classmethod
    def parse(cls, index: int, data: bytes) -> "Model":
        v = struct.unpack_from(HDR, data, 0)
        m = cls(index, data)
        (m.shape_flags, m.flags2, m.instance_number, _tv, _zb, m.bounding_sphere, _npn,
         m.num_vertices, m.num_polys, m.vertices, m.poly_block, m.normals,
         m.point_normals, m.collision_block) = v
        return m

    def poly_types(self) -> list[int]:
        out, p = [], self.poly_block
        for _ in range(self.num_polys):
            if p >= len(self.data):
                break
            t = self.data[p] & 31
            out.append(t)
            size = POLY_SIZES.get(t)
            if size is None:
                out.append(-1)
                break
            p += size
        return out


def model_names(lev: Lev) -> list[str]:
    raw = lev.loadtime.get(MODELNAMES).data
    return [s.decode("latin-1") for s in raw.split(b"\0")]


def inmem_models(lev: Lev) -> dict[int, Model]:
    raw = lev.inmem.get(MODELS).data
    count = struct.unpack_from("<i", raw, 0)[0]
    p, out = 4, {}
    for i in range(count):
        size = struct.unpack_from("<i", raw, p)[0]; p += 4
        if size > 0:
            out[i] = Model.parse(i, raw[p: p + size]); p += size
    return out, count


def area_models(lev: Lev) -> dict[int, Model]:
    """Models spooled with area data (AreaDataStr.model_offset/model_size)."""
    sp = SpoolInfo.parse(lev.inmem.get(SPOOLINFO).data)
    out = {}
    # Only areas referenced by a region's super_region hold valid records;
    # the others are unused slots with leftover bytes.
    used = sorted({s[7] for s in sp.spools.values()} - {255})
    for area in (sp.areas[i] for i in used):
        gfx_off, model_off, _mus, _amb, model_size = area[:5]
        if model_size == 0:
            continue
        blk = lev.spooled[model_off * 2048: (model_off + model_size) * 2048]
        tail = blk[(model_size - 1) * 2048:]
        n = struct.unpack_from("<H", tail, 0)[0]
        ids = struct.unpack_from("<%dH" % n, tail, 2)
        p = 0
        for mid in ids:
            size = struct.unpack_from("<i", blk, p)[0]; p += 4
            if size > 0:
                out.setdefault(mid, Model.parse(mid, blk[p: p + size])); p += size
    return out


if __name__ == "__main__":
    import sys
    for path in sys.argv[1:]:
        lev = Lev.parse(open(path, "rb").read())
        mem, count = inmem_models(lev)
        area = area_models(lev)
        allm = {**area, **mem}
        names = model_names(lev)
        types = collections.Counter()
        bad = 0
        for m in allm.values():
            pt = m.poly_types()
            if -1 in pt:
                bad += 1
            types.update(t for t in pt if t >= 0)
        hdr_ok = sum(1 for m in allm.values() if m.vertices == HDR_SIZE or m.vertices >= HDR_SIZE)
        print(path.split("/")[-1], "%s: pack %d, in-memory %d, area-spooled %d, unique %d, names %d"
              % ("D1" if lev.d1 else "D2", count, len(mem), len(area), len(allm), len(names)))
        print("   poly types:", dict(sorted(types.items())), " models with unknown poly type:", bad)
        print("   vertices-offset == header size (36):", sum(1 for m in allm.values() if m.vertices == HDR_SIZE), "/", len(allm),
              " with collision:", sum(1 for m in allm.values() if m.collision_block > 0),
              " instances:", sum(1 for m in allm.values() if m.instance_number != m.index and m.num_polys == 0))
