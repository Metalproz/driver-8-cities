"""mapinfo.py — decode the MAP and SPOOLINFO lumps (shared by Driver 1 and 2).

Structures follow OpenDriver2Tools (DriverLevelTool/driver_routines):
OUT_CELL_FILE_HEADER, CBaseLevelMap::LoadMapLump / LoadSpoolInfoLump,
AreaDataStr and Spool.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from levfile import Lev

MAP, MODELS, SPOOLINFO, TEXTUREINFO, MODELNAMES = 2, 1, 26, 34, 12


@dataclass
class MapHeader:
    cells_across: int
    cells_down: int
    cell_size: int
    num_regions: int
    region_size: int
    num_cell_objects: int
    num_cell_data: int
    ambient_light_level: int
    light_source: tuple
    num_straddlers: int

    @classmethod
    def parse(cls, data: bytes) -> "MapHeader":
        v = struct.unpack_from("<8i3i", data, 0)
        num_straddlers = struct.unpack_from("<i", data, 44)[0]
        return cls(*v[:8], tuple(v[8:11]), num_straddlers)

    @property
    def regions_across(self) -> int:
        return self.cells_across // self.region_size

    @property
    def regions_down(self) -> int:
        return self.cells_down // self.region_size


AREA_FMT = "<4H8B"          # AreaDataStr, 16 bytes
SPOOL_FMT = "<H2B B3B B B B B"  # Spool, 12 bytes


@dataclass
class SpoolInfo:
    model_spool_buffer_size: int
    num_areas: int
    areas: list
    area_tpages: list
    cell_slots: list
    cell_objects: list
    pvs_sizes: list
    region_offsets: list
    spools: dict     # offset -> spool tuple

    @classmethod
    def parse(cls, data: bytes) -> "SpoolInfo":
        p = 0
        model_buf, music_sz = struct.unpack_from("<ii", data, p); p += 8
        p += music_sz
        num_areas = struct.unpack_from("<i", data, p)[0]; p += 4
        areas = [struct.unpack_from(AREA_FMT, data, p + 16 * i) for i in range(num_areas)]
        p += 16 * num_areas
        tpages = [data[p + 16 * i: p + 16 * i + 16] for i in range(num_areas)]
        p += 16 * num_areas
        slots = list(struct.unpack_from("<4i", data, p)); p += 16
        objects = list(struct.unpack_from("<4i", data, p)); p += 16
        pvs = list(struct.unpack_from("<4i", data, p)); p += 16
        n_off = struct.unpack_from("<i", data, p)[0]; p += 4
        offsets = list(struct.unpack_from("<%dH" % n_off, data, p)); p += 2 * n_off
        info_size = struct.unpack_from("<i", data, p)[0]; p += 4
        spools = {}
        for off in sorted(set(o for o in offsets if o != 0xFFFF)):
            spools[off] = struct.unpack_from(SPOOL_FMT, data, p + off)
        return cls(model_buf, num_areas, areas, tpages, slots, objects, pvs, offsets, spools)


def describe(path: str) -> dict:
    lev = Lev.parse(open(path, "rb").read())
    hdr = MapHeader.parse(lev.loadtime.get(MAP).data)
    sp = SpoolInfo.parse(lev.inmem.get(SPOOLINFO).data)
    num_models = struct.unpack_from("<i", lev.inmem.get(MODELS).data, 0)[0]
    num_tpages = struct.unpack_from("<i", lev.loadtime.get(TEXTUREINFO).data, 0)[0]
    used_regions = sum(1 for o in sp.region_offsets if o != 0xFFFF)
    return {
        "format": "D1" if lev.d1 else "D2",
        "cells": "%dx%d @%d" % (hdr.cells_across, hdr.cells_down, hdr.cell_size),
        "regions": "%dx%d (size %d cells), %d with data" % (hdr.regions_across, hdr.regions_down, hdr.region_size, used_regions),
        "cell_objects": hdr.num_cell_objects,
        "cell_data": hdr.num_cell_data,
        "straddlers": hdr.num_straddlers,
        "models": num_models,
        "tpages": num_tpages,
        "areas": sp.num_areas,
        "model_spool_buf": sp.model_spool_buffer_size,
        "slots/barrel": sp.cell_slots,
        "objects/barrel": sp.cell_objects,
        "pvs/barrel": sp.pvs_sizes,
        "inmem_bytes": sum(len(l.data) + 8 for l in lev.inmem.lumps),
        "loadtime_bytes": sum(len(l.data) + 8 for l in lev.loadtime.lumps),
        "tpage_bytes": len(lev.tpages),
        "spooled_bytes": len(lev.spooled),
    }


if __name__ == "__main__":
    import sys
    rows = {p: describe(p) for p in sys.argv[1:]}
    keys = list(next(iter(rows.values())).keys())
    names = [p.split("/")[-1].split("\\")[-1] for p in rows]
    print("%-16s" % "" + "".join("%-34s" % n for n in names))
    for k in keys:
        print("%-16s" % k + "".join("%-34s" % str(rows[p][k]) for p in rows))
