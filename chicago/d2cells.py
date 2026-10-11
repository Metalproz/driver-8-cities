"""d2cells.py — extract every placed object (cell object) from a Driver 2 LEV.

Follows OpenDriver2Tools CDriver2LevelRegion::LoadRegionData / StartIterator /
GetNextPackedCop / UnpackCellObject. Returns unique objects with world
position, Y angle (0..63) and model index, plus which cells listed them.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from levfile import Lev
from mapinfo import MapHeader, SpoolInfo, MAP, SPOOLINFO

BLOCK = 2048


@dataclass
class CellObject:
    x: int
    y: int
    z: int
    yang: int      # 0..63 (64 steps per turn)
    model: int


def unpack_cell_pointers(src: bytes, cells: int) -> list[int]:
    packtype = struct.unpack_from("<i", src, 4)[0]
    data = memoryview(src)[8:]
    words = lambda i: struct.unpack_from("<H", data, 2 * i)[0]
    out = []
    if packtype == 0:
        return [0xFFFF] * cells
    if packtype == 1:
        return [words(i) for i in range(cells)]
    if packtype == 2:
        k = 0
        pcode = words(k); k += 1
        bit = 0x8000
        for _ in range(cells):
            if pcode & bit:
                out.append(words(k)); k += 1
            else:
                out.append(0xFFFF)
            bit >>= 1
            if bit == 0:
                bit = 0x8000
                pcode = words(k); k += 1
        return out
    raise ValueError("bad cell pointer pack type %d" % packtype)


def unpack_object(raw: bytes, off: int, near_x: int, near_z: int) -> CellObject:
    px, py, pz, value = struct.unpack_from("<4H", raw, off)
    x = near_x + struct.unpack("<h", struct.pack("<H", (px - near_x) & 0xFFFF))[0]
    z = near_z + struct.unpack("<h", struct.pack("<H", (pz - near_z) & 0xFFFF))[0]
    y = struct.unpack("<h", struct.pack("<H", py))[0] >> 1
    return CellObject(x, y, z, value & 0x3F, (value >> 6) | ((py & 1) << 10))


def extract(path: str):
    lev = Lev.parse(open(path, "rb").read())
    if lev.d1:
        raise ValueError("expects a Driver 2 LEV")
    hdr = MapHeader.parse(lev.loadtime.get(MAP).data)
    sp = SpoolInfo.parse(lev.inmem.get(SPOOLINFO).data)
    mapdata = lev.loadtime.get(MAP).data
    nstrad = hdr.num_straddlers
    straddlers_raw = mapdata[48: 48 + 8 * nstrad]   # PACKED_CELL_OBJECT[] after header+count

    objects: dict[tuple, CellObject] = {}
    refs: dict[tuple, list] = {}
    rs = hdr.region_size
    spooled = lev.spooled
    for idx, off in enumerate(sp.region_offsets):
        if off == 0xFFFF:
            continue
        rx, rz = idx % hdr.regions_across, idx // hdr.regions_across
        barrel = (rx & 1) + (rz & 1) * 2
        offset, _ca, _cb, pvs, cd0, cd1, cd2, *_ = sp.spools[off]
        base = offset * BLOCK
        ptrs_raw = spooled[base: base + cd1 * BLOCK]
        cells_raw = spooled[base + cd1 * BLOCK: base + (cd1 + cd0) * BLOCK]
        objs_raw = spooled[base + (cd1 + cd0) * BLOCK: base + (cd1 + cd0 + cd2) * BLOCK]
        ptrs = unpack_cell_pointers(ptrs_raw, rs * rs)
        add = sp.cell_objects[barrel] if False else None  # see object_base below
        object_base = sum(sp.cell_objects[:barrel])  # m_cell_objects_add[barrel]

        def cell_num(i):
            return struct.unpack_from("<H", cells_raw, 2 * i)[0]

        for c, ptr in enumerate(ptrs):
            if ptr == 0xFFFF:
                continue
            cx = rx * rs + c % rs
            cz = rz * rs + c // rs
            near_x = (cx - hdr.cells_across // 2) * hdr.cell_size
            near_z = (cz - hdr.cells_down // 2) * hdr.cell_size
            i = ptr
            first = True
            while True:
                num = cell_num(i)
                if not first:
                    pass
                if num & 0x4000:          # typed sub-list marker: skip to its start
                    i += 1
                    num = cell_num(i)
                n = num & 0x3FFF
                if n < nstrad:
                    key = ("s", n)
                    raw, roff = straddlers_raw, 8 * n
                else:
                    key = (idx, n)
                    raw, roff = objs_raw, 8 * (n - object_base - nstrad)
                value, py = struct.unpack_from("<H", raw, roff + 6)[0], struct.unpack_from("<H", raw, roff + 2)[0]
                if not (value == 0xFFFF and (py & 1)):
                    if key not in objects:
                        objects[key] = unpack_object(raw, roff, near_x, near_z)
                    refs.setdefault(key, []).append((cx, cz))
                if num & 0x8000:
                    break
                i += 1
                first = False
    return hdr, sp, objects, refs


if __name__ == "__main__":
    import sys, collections
    hdr, sp, objects, refs = extract(sys.argv[1])
    print("unique objects:", len(objects), " header num_cell_objects:", hdr.num_cell_objects,
          " straddlers:", sum(1 for k in objects if k[0] == "s"), "/", hdr.num_straddlers)
    xs = [o.x for o in objects.values()]; zs = [o.z for o in objects.values()]; ys = [o.y for o in objects.values()]
    print("x %d..%d  z %d..%d  y %d..%d" % (min(xs), max(xs), min(zs), max(zs), min(ys), max(ys)))
    per = collections.Counter(len(v) for v in refs.values())
    print("cells per object:", sorted(per.items())[:10])
    models = collections.Counter(o.model for o in objects.values())
    print("distinct models placed:", len(models), " max model index:", max(models))
