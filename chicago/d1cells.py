"""d1cells.py — decode the spooled regions of a Driver 1 LEV.

Per region (OpenDriver2Tools CDriver1LevelRegion::LoadRegionData), in 2048-byte
blocks starting at Spool.offset:
    roadm   roadm_size blocks   RLE (s16 len, u16 road id), 60x60 = 3600 cells
    roadh   roadh_size blocks   RLE (u32 len, u32 value) over (2*region_size)^2
    ptrs    cell_data_size[1]   packed cell pointers (same packing as D2)
    cells   cell_data_size[0]   CELL_DATA_D1 {u16 num, u16 next_ptr}
    objects cell_data_size[2]   CELL_OBJECT {i32 x,y,z; u8 pad, yang; u16 type}
Used both to learn the format and to validate the converter's output.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from levfile import Lev
from mapinfo import MapHeader, SpoolInfo, MAP, SPOOLINFO
from d2cells import unpack_cell_pointers, CellObject

BLOCK = 2048
ROAD_CELLS = 3600


@dataclass
class D1Region:
    index: int
    rx: int
    rz: int
    barrel: int
    road_ids: list = field(default_factory=list)     # 3600 u16
    road_values: list = field(default_factory=list)  # (2*rs)^2 u32
    cell_ptrs: list = field(default_factory=list)
    cells: list = field(default_factory=list)        # (num, next_ptr)
    objects: list = field(default_factory=list)      # CellObject
    sizes: tuple = ()


def decode_roadm(raw: bytes) -> list[int]:
    out, p = [], 0
    while len(out) < ROAD_CELLS:
        length, value = struct.unpack_from("<hH", raw, p); p += 4
        if length == -1:
            break
        out.extend([value] * length)
    return out


def decode_roadh(raw: bytes, count: int) -> list[int]:
    out, p = [], 0
    while len(out) < count:
        length, value = struct.unpack_from("<II", raw, p); p += 8
        out.extend([value] * length)
    return out


def extract(path: str):
    lev = Lev.parse(open(path, "rb").read())
    if not lev.d1:
        raise ValueError("expects a Driver 1 LEV")
    mapdata = lev.loadtime.get(MAP).data
    hdr = MapHeader.parse(mapdata)
    sp = SpoolInfo.parse(lev.inmem.get(SPOOLINFO).data)
    nstrad = hdr.num_straddlers
    straddlers = [struct.unpack_from("<3iBBH", mapdata, 48 + 16 * i) for i in range(nstrad)]
    rs = hdr.region_size
    regions = []
    for idx, off in enumerate(sp.region_offsets):
        if off == 0xFFFF:
            continue
        rx, rz = idx % hdr.regions_across, idx // hdr.regions_across
        barrel = (rx & 1) + (rz & 1) * 2
        offset, _a, _b, pvs, cd0, cd1, cd2, _sr, _nca, roadm, roadh = sp.spools[off]
        p = offset * BLOCK
        seg = {}
        for name, n in (("roadm", roadm), ("roadh", roadh), ("ptrs", cd1), ("cells", cd0), ("objs", cd2)):
            seg[name] = lev.spooled[p: p + n * BLOCK]; p += n * BLOCK
        reg = D1Region(idx, rx, rz, barrel, sizes=(roadm, roadh, cd1, cd0, cd2, pvs))
        reg.road_ids = decode_roadm(seg["roadm"])
        reg.road_values = decode_roadh(seg["roadh"], (2 * rs) * (2 * rs))
        reg.cell_ptrs = unpack_cell_pointers(seg["ptrs"], rs * rs)
        reg.cells = [struct.unpack_from("<HH", seg["cells"], 4 * i) for i in range(len(seg["cells"]) // 4)]
        reg.objects = [struct.unpack_from("<3iBBH", seg["objs"], 16 * i) for i in range(len(seg["objs"]) // 16)]
        regions.append(reg)
    return lev, hdr, sp, straddlers, regions


def unique_objects(hdr, sp, straddlers, regions):
    """Walk every cell chain; return {key: CellObject} and per-key cell refs."""
    objects, refs, flags = {}, {}, {}
    rs = hdr.region_size
    nstrad = hdr.num_straddlers
    slots_add = [sum(sp.cell_slots[:b]) for b in range(4)]
    objs_add = [sum(sp.cell_objects[:b]) for b in range(4)]
    for reg in regions:
        for c, ptr in enumerate(reg.cell_ptrs):
            if ptr == 0xFFFF:
                continue
            cx, cz = reg.rx * rs + c % rs, reg.rz * rs + c // rs
            i = ptr
            while True:
                num, nxt = reg.cells[i]
                n = num           # Driver 1 uses the full 16 bits (no 0x3FFF mask in the EXE)
                flags[num & 0xC000] = flags.get(num & 0xC000, 0) + 1
                if n < nstrad:
                    key, o = ("s", n), straddlers[n]
                else:
                    key, o = (reg.index, n), reg.objects[n - objs_add[reg.barrel] - nstrad]
                x, y, z, pad, yang, typ = o
                if not (x == -1 and y == -1 and z == -1 and typ == 0xFFFF):
                    objects.setdefault(key, CellObject(x, y, z, yang, typ))
                    refs.setdefault(key, []).append((cx, cz))
                if nxt == 0xFFFF:
                    break
                i = nxt - slots_add[reg.barrel]
    return objects, refs, flags


if __name__ == "__main__":
    import sys, collections
    lev, hdr, sp, straddlers, regions = extract(sys.argv[1])
    objects, refs, flags = unique_objects(hdr, sp, straddlers, regions)
    print("unique objects:", len(objects), " header num_cell_objects:", hdr.num_cell_objects,
          " straddlers used:", sum(1 for k in objects if k[0] == "s"), "/", hdr.num_straddlers)
    print("num flag bits seen:", {hex(k): v for k, v in flags.items()})
    print("cells per object:", sorted(collections.Counter(len(v) for v in refs.values()).items())[:10])
    r = regions[0]
    print("region0 sizes (roadm, roadh, ptrs, cells, objs, pvs):", r.sizes,
          " road ids:", len(r.road_ids), " road values:", len(r.road_values))
    vals = collections.Counter()
    for reg in regions:
        for v in reg.road_values:
            vals[(v >> 16) & 1023] += 1
    print("distinct surface types used:", len(vals), " most common:", vals.most_common(5))
