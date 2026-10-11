"""convert.py — build a Driver 1 LEV of Driver 2's Chicago (stage A, v0).

Inputs: work/d2_CHICAGO.LEV (world) and work/d1_LA.lev (the replaced city,
which supplies Driver 1's engine assets: car models, palettes, pedestrian
motion capture, wheels, pedestrian heads, HUD/effect textures).

v0 scope: textures (texrepack.py), models, placed objects re-gridded to D1's
3000-unit cells / 30-cell regions, areas with border switching, empty PVS
(= everything visible), flat placeholder ground, empty road network.
"""
from __future__ import annotations

import collections
import os
import math
import struct
import sys

from levfile import Lev, Lump, LumpList
from mapinfo import MapHeader, SpoolInfo, MAP, SPOOLINFO
from models import Model, inmem_models, area_models, model_names, POLY_SIZES
from d2cells import extract as d2_extract
from texpages import encode_compressed, encode_raw, pad, BLOCK, RAW_RECORD
from texrepack import repack, car_models, ENGINE_MODEL_NAMES, SKY_SLOTS
from d1models import convert_models
import pvs
import worldscale as ws
from d2cells import CellObject

# D1 lump ids
L_TEXNAMES, L_MODELS, L_MAP, L_ROADMAP, L_ROADS, L_JUNCS, L_ROADSURF = 5, 1, 2, 7, 8, 9, 10
L_MODELNAMES, L_ROADBOUNDS, L_JUNCBOUNDS, L_SUBDIV, L_LOD, L_MOCAP = 12, 16, 17, 20, 21, 22
L_OVERLAY, L_PALLET, L_SPOOL, L_CARMODELS, L_CHAIR, L_TEXINFO = 24, 25, 26, 28, 33, 34

CELL = 3000
EXPERIMENT = set(os.environ.get('CHI_EXPERIMENT', '').split(','))
BIG_OBJECT = 3000      # bounding radius above which an object spans cells
BIG_TILE = int(os.environ.get("CHI_BIG_TILE", "3000"))   # same for ground tiles (tried 1500
                       # for the ground holes: no visible change, 9x the straddlers)
NEAR_CELLS = 2         # cells around a region whose models count as seen up close
AREA_BAND_LOW = 13        # area switch threshold (exe_patches.AREA_SWITCH_CODE): cells < 13 / > 17
SWITCH_LAG = int(os.environ.get("CHI_SWITCH_LAG", "0"))           # cells the car may cross while an area loads (no new switch meanwhile)
AREA_TEXTURE_LIMIT = int(os.environ.get("CHI_AREA_TEX", "220"))   # textures one area may need (13 VRAM pages x 32 palettes, minus permanent + packing slack)
REGION_CELLS = 30
ROAD_UNIT = 1500
# per-vertex UVs: (offset, count). Types 9 and 17 are compact (12 bytes) and
# map the whole texture detail, so only their page/detail is remapped.
UVOFF = {4: (8, 3), 10: (8, 3), 20: (8, 3), 5: (8, 4), 11: (8, 4), 21: (8, 4),
         22: (12, 3), 23: (12, 4)}
PAGE_ONLY = {9, 17}


# ---------------------------------------------------------------------------
# textures

def texture_lumps(res, special_new):
    """TEXTURENAMES + TEXTUREINFO + tpage section from a RepackResult."""
    num_pages = max(list(res.pages) + list(special_new.values())) + 1
    names = bytearray()
    name_off = {}

    def name(n: bytes) -> int:
        if n not in name_off:
            name_off[n] = len(names)
            names.extend(n + b"\0")
        return name_off[n]

    page_details = {}
    for idx, dets in res.details.items():
        page_details[idx] = [(ident, name(n), x, y, w & 0xFF, h & 0xFF) for ident, n, x, y, w, h in dets]
    for old, new in special_new.items():
        page_details[new] = [(d[0], name(d[1]), *d[2:]) for d in res.special_details[old]]

    tpages = bytearray()
    perm_list, spec_list = [], []
    for idx in res.permanent:
        blob = encode_compressed(res.pages[idx])
        perm_list.append((idx, len(blob)))
        tpages += pad(blob)
    for old, blob in res.special:
        spec_list.append((special_new[old], len(blob)))
        tpages += pad(blob)

    info = bytearray(struct.pack("<ii", num_pages, sum(len(v) for v in page_details.values())))
    offset = 0
    for i in range(num_pages):
        flags = res.flags.get(i, 4 if i in special_new.values() else 0)
        info += struct.pack("<II", flags, offset)
        offset += 32768
    info += struct.pack("<II", 1, offset)
    for i in range(num_pages):
        dets = page_details.get(i, [])
        info += struct.pack("<i", len(dets))
        for d in dets:
            info += struct.pack("<HH4B", *d)
    for lst in (perm_list, spec_list):
        info += struct.pack("<i", len(lst))
        for k in range(16):
            info += struct.pack("<ii", *(lst[k] if k < len(lst) else (0, 0)))
    return bytes(names), bytes(info), bytes(tpages), num_pages


def remap_polys(data: bytes, src: str, remap: dict, fallback) -> bytes:
    m = Model.parse(-1, data)
    if m.poly_block >= len(data):      # instances have their own polygons too
        return data
    b = bytearray(data)
    q = m.poly_block
    for _ in range(m.num_polys):
        t = b[q] & 31
        if (t in UVOFF or t in PAGE_ONLY) and b[q + 1] != 0xFF:
            r = remap.get((src, b[q + 1], b[q + 2])) or fallback
            np_, nd, nx, ny, ox, oy, ow, oh, nw, nh = r
            b[q + 1], b[q + 2] = np_, nd
            if t in UVOFF:
                off, n = UVOFF[t]
                for k in range(n):
                    u, v = b[q + off + 2 * k], b[q + off + 2 * k + 1]
                    u2 = nx + (u - ox) * nw // ow
                    v2 = ny + (v - oy) * nh // oh
                    b[q + off + 2 * k] = min(max(u2, nx), nx + nw - 1)
                    b[q + off + 2 * k + 1] = min(max(v2, ny), ny + nh - 1)
        q += POLY_SIZES[t]
    return bytes(b)


# ---------------------------------------------------------------------------
# models

# Engine models the replaced slot's loader needs by name but whose events place
# them at that city's coordinates: LA's airport plane stood broken in a Chicago
# street. Kept, but drawn as nothing.
HIDDEN_ENGINE_MODELS = {"BOEING"}


def hide_model(data: bytes) -> bytes:
    """Keep only the first polygon, with all its vertex indices 0 (a point):
    whatever loop draws the model still finds a polygon, and nothing shows."""
    m = Model.parse(-1, data)
    d = bytearray(data)
    struct.pack_into("<H", d, 0x0E, 1)                  # num_polys
    q = m.poly_block
    t = d[q] & 31
    from d1models import VERT_OFF
    off = VERT_OFF.get(t, 4)
    n = 3 if t in (8, 10, 20) else 4
    for k in range(n):
        d[q + off + k] = 0
    return bytes(d)


def tiles_without_near_cull(conv: dict) -> dict:
    """Ground tiles pick a near-range routine for their 2nd.. polygons from 3-bit
    fields at +0x24 (table 0x8001040C, path 0x800287A4). Routine 4 subdivides
    2 x 2 and adds a backface test (NCLIP, 0x80028A48) on projected vertices,
    which drops Chicago's larger polygons when a corner is behind the camera
    (holes in front of the car); routine 3 draws the same without the test."""
    out = {}
    for i, d in conv.items():
        flags = struct.unpack_from("<H", d, 0)[0]
        n = struct.unpack_from("<H", d, 0x0E)[0]
        if not (flags & 0x2400) or n < 2 or len(d) < 0x28:
            out[i] = d
            continue
        w = struct.unpack_from("<I", d, 0x24)[0]
        bits = w >> 2
        for k in range(n - 1):
            if (bits >> (3 * k)) & 7 == 4:
                bits = (bits & ~(7 << (3 * k))) | (3 << (3 * k))
        w = (bits << 2) | (w & 3)
        out[i] = d[:0x24] + struct.pack("<I", w) + d[0x28:]
    return out


def fit_bounding_spheres(conv: dict) -> dict:
    """Driver 2's bounding sphere (+0x08) covers the horizontal footprint only
    (a 7680-high facade 1022 wide has 511); Driver 1 culls objects with it in
    3D (0x8002C5F0: view planes with the radius as margin), so tall buildings,
    lamp posts and raised ground pieces vanished when their base left the view.
    Every model gets at least the radius of its vertices (instances: their
    source's)."""
    parsed = {i: Model.parse(i, d) for i, d in conv.items()}
    radius = {}
    for i, m in parsed.items():
        src = parsed.get(m.instance_number, m) if m.instance_number not in (-1, 0xFFFF) else m
        try:
            vs = [struct.unpack_from("<3h", src.data, src.vertices + 8 * k) for k in range(src.num_vertices)]
        except struct.error:
            continue
        if vs:
            radius[i] = math.ceil(max(math.sqrt(x * x + y * y + z * z) for x, y, z in vs))
    out = {}
    for i, d in conv.items():
        bs = struct.unpack_from("<h", d, 8)[0]
        r = min(radius.get(i, 0), 0x7FFF)
        out[i] = d[:8] + struct.pack("<h", r) + d[10:] if r > bs else d
    return out


def far_water_index(chi: Lev) -> int:
    """The far water model goes after Chicago's models and the base city's engine models."""
    return struct.unpack_from("<i", chi.inmem.get(1).data, 0)[0] + len(ENGINE_MODEL_NAMES)


def build_models(chi: Lev, base: Lev, res):
    cmem, ccount = inmem_models(chi)
    carea = area_models(chi)
    cnames = model_names(chi)[:ccount]
    fallback = res.remap[next(iter(res.remap))]

    def remap_c(m):
        return remap_polys(m.data, "C", res.remap, fallback)

    # Driver 2 models -> Driver 1 polygon groups (d1models.py), converted as one
    # set so instances follow their source's polygon order.
    chi_all = {i: ws.scale_model(remap_c(m)) for i, m in {**carea, **cmem}.items()}
    conv, stats = convert_models(chi_all)
    print("models: %(models)d converted (%(groups)d groups), %(tiles)d tiles kept, %(instances)d instances, "
          "%(deinstanced)d de-instanced" % stats)
    conv = fit_bounding_spheres(conv)
    # flags2 0x4000 is Driver 2's GRASS but Driver 1's WATER (waves, sinking: 0x8001F074,
    # 0x8001F410); a start among Chicago's grass tiles sank the car and ended the game
    conv = {i: d[:2] + struct.pack("<H", struct.unpack_from("<H", d, 2)[0] & ~0x4000) + d[4:] for i, d in conv.items()}
    if "tile_novtx" in EXPERIMENT:               # D1 layout: single-polygon tiles point +0x10 at the polygons
        def novtx(d):
            fl, n = struct.unpack_from("<H", d, 0)[0], struct.unpack_from("<H", d, 0x0E)[0]
            if fl & 0x2400 and n == 1:
                d = d[:0x10] + d[0x14:0x18] + d[0x14:]
            return d
        conv = {i: novtx(d) for i, d in conv.items()}
    if "tile_flip" in EXPERIMENT:                # reverse the winding of single-polygon tiles (v1<->v3)
        def flip(d):
            fl, n = struct.unpack_from("<H", d, 0)[0], struct.unpack_from("<H", d, 0x0E)[0]
            if not (fl & 0x2400 and n == 1):
                return d
            q = struct.unpack_from("<I", d, 0x14)[0]
            b = bytearray(d)
            if b[q] & 31 in (21, 11, 9, 23):
                b[q + 5], b[q + 7] = b[q + 7], b[q + 5]                      # vertex 1 <-> 3
                b[q + 10:q + 12], b[q + 14:q + 16] = b[q + 14:q + 16], b[q + 10:q + 12]   # uv1 <-> uv3
            return bytes(b)
        conv = {i: flip(d) for i, d in conv.items()}
    if "tile_nocull" in EXPERIMENT:              # tried for the park strip: no change
        conv = tiles_without_near_cull(conv)
    if "clear_sf6" in EXPERIMENT:
        conv = {i: struct.pack("<H", struct.unpack_from("<H", d, 0)[0] & ~6) + d[2:] for i, d in conv.items()}
    nocoll = None
    for e in EXPERIMENT:
        if e == "no_coll":
            nocoll = set(conv)
        elif e.startswith("no_coll="):
            nocoll = {int(v) for v in e[8:].split("+")}
    if nocoll:
        conv = {i: (d[:0x20] + bytes(4) + d[0x24:] if i in nocoll else d) for i, d in conv.items()}
    data = {i: conv[i] for i in cmem}               # index -> bytes (in-memory models)
    area_data = {i: conv[i] for i in carea if i not in cmem}   # area-spooled models

    names = list(cnames)
    for k, n in enumerate(names):
        if n in ENGINE_MODEL_NAMES:
            names[k] = "_" + n[1:]           # the base city's version must win lookups

    # engine models from the base city, appended
    bmem, _ = inmem_models(base)
    ball = {**area_models(base), **bmem}
    bnames = model_names(base)

    # sky: Driver 1 draws models 0..3 as the sky dome; Chicago's slots 0..3 hold
    # Driver 2's unplaced BASE1..4, so the base city's sky models replace them.
    for i in range(SKY_SLOTS):
        data[i] = remap_polys(ball[i].data, "B", res.remap, fallback)
        names[i] = bnames[i]
    new_index = {}
    for n in ENGINE_MODEL_NAMES:
        new_index[bnames.index(n)] = len(names)
        names.append(n)
    for old, new in new_index.items():
        raw = bytearray(remap_polys(ball[old].data, "B", res.remap, fallback))
        inst = struct.unpack_from("<h", raw, 4)[0]
        if inst >= 0:
            if inst not in new_index:
                raise RuntimeError("engine model instance of non-engine model %d" % inst)
            struct.pack_into("<h", raw, 4, new_index[inst])
        if bnames[old] in HIDDEN_ENGINE_MODELS:
            raw = bytearray(hide_model(bytes(raw)))
        data[new] = bytes(raw)
    if FAR_WATER:
        assert len(names) == far_water_index(chi), (len(names), far_water_index(chi))
        names.append("FARWATER")
        data[len(names) - 1] = far_water_model(res, fallback)
    count = len(names)

    lump = bytearray(struct.pack("<i", count))
    for i in range(count):
        if i in data:
            lump += struct.pack("<i", len(data[i])) + data[i]
        else:
            lump += struct.pack("<i", 0)
    namelump = b"\0".join(n.encode("latin-1") for n in names) + b"\0"

    lod = chi.inmem.get(L_LOD).data
    t = list(struct.unpack_from("<%dH" % (2 * ccount), lod))
    t1, t2 = t[:ccount], t[ccount:]
    for _ in range(count - ccount):
        t1.append(0xFFFF)
        t2.append(0xFFFF)
    lodlump = struct.pack("<%dH" % (2 * count), *(t1 + t2))
    return bytes(lump), namelump, lodlump, area_data, count, cmem, carea


# ---------------------------------------------------------------------------
# map, regions, areas

def build_world(chi: Lev, models_all: dict, inmem_ids: set, base: Lev):
    hdr2, sp2, objects, refs = d2_extract_cached()
    # At least the replaced city's grid: game code (start positions, events) still
    # uses that city's coordinates, and every position must map to a valid region.
    base_hdr = MapHeader.parse(base.loadtime.get(L_MAP).data)
    # Chicago scaled by worldscale.SCALE and centred: the largest grid Driver 1 allows
    across, down = ws.CELLS_ACROSS, ws.CELLS_DOWN
    rx_n, rz_n = across // REGION_CELLS, down // REGION_CELLS
    half_x, half_z = across // 2 * CELL, down // 2 * CELL

    def cell_of(x, z):
        return (x + half_x) // CELL, (z + half_z) // CELL

    # object -> covered D1 cells, from its model's bounding sphere
    obj_list = []
    for o in objects.values():
        x, z = ws.to_d1(o.x, o.z)
        obj_list.append(CellObject(x, ws.s(o.y), z, o.yang, o.model))
    if "no_water" not in EXPERIMENT and "water_noobj" not in EXPERIMENT:
        wc = water_cells(across, down)
        n = CELL // (1500 * WATER_SCALE)         # LA's tile is 1500 wide; far tiles (shape 0x20, 0x800274B8)
        step = CELL // n                         # use a fixed 1500 corner table, so the tile is never stretched
        wh = water_heights(across, down)
        rows = down // REGION_CELLS * 60
        for cx, cz in wc:
            for i in range(n):
                for j in range(n):
                    x, z = cx * CELL + step * i + step // 2 - half_x, cz * CELL + step * j + step // 2 - half_z
                    col, row = (x + half_x + ROAD_UNIT // 2) // ROAD_UNIT, (half_z - z + ROAD_UNIT // 2) // ROAD_UNIT
                    near = [wh[k] for k in ((col, row), (col - 1, row), (col, row - 1), (col - 1, row - 1)) if k in wh]
                    obj_list.append(CellObject(x, max(near) if near else WATER_Y, z, 0, WATER_MODEL))
        print("water tiles:", len(wc))
        if FAR_WATER:
            fw = far_water_blocks(across, down)
            for x, y, z in fw:
                obj_list.append(CellObject(x, y, z, 0, far_water_index(chi)))
            print("far water planes:", len(fw))
    # Driver 1 lists ~89% of objects only in their centre cell (measured on LA);
    # only objects larger than a cell are also listed in the cells they cover.
    covered = []
    for o in obj_list:
        m = models_all.get(o.model)
        r = ws.s(abs(m.bounding_sphere)) if m else 0
        if r <= (BIG_TILE if m and m.shape_flags & 0x2400 else BIG_OBJECT):
            covered.append([cell_of(o.x, o.z)])
            continue
        x0, z0 = cell_of(o.x - r, o.z - r)
        x1, z1 = cell_of(o.x + r, o.z + r)
        cells = [(cx, cz) for cx in range(max(0, x0), min(across - 1, x1) + 1)
                 for cz in range(max(0, z0), min(down - 1, z1) + 1)]
        if not cells:
            cells = [cell_of(o.x, o.z)]
        covered.append(cells)

    region_of = lambda c: (c[0] // REGION_CELLS, c[1] // REGION_CELLS)
    straddlers, local = [], collections.defaultdict(list)
    obj_num = {}
    for k, cells in enumerate(covered):
        regs = {region_of(c) for c in cells}
        if len(regs) > 1:
            obj_num[k] = ("s", len(straddlers))
            straddlers.append(k)
        else:
            (reg,) = regs
            obj_num[k] = (reg, len(local[reg]))
            local[reg].append(k)

    cell_lists = collections.defaultdict(list)
    for k, cells in enumerate(covered):
        for c in cells:
            cell_lists[c].append(k)

    # --- per-region visibility (independent of areas) -----------------------
    # per-cell view radius (pvs.py): polygons placed in each cell
    import numpy as np
    from texrepack import model_texrefs
    cost = collections.Counter()
    for c, objs in cell_lists.items():
        for k in objs:
            m = models_all.get(obj_list[k].model)
            cost[c] += m.num_polys if m else 0
    radii = pvs.radius_grid(cost, across, down)
    if "pvs_full" in EXPERIMENT:
        radii[:] = pvs.MAX_RADIUS
    cell_model_ids = {c: {obj_list[k].model for k in objs} for c, objs in cell_lists.items()}
    pad = pvs.MAX_RADIUS + 1
    discs = {}
    for r in range(pvs.MIN_RADIUS, pvs.MAX_RADIUS + 1):
        R = r + 1
        discs[r] = [(dx, dz) for dz in range(-R, R + 1) for dx in range(-R, R + 1) if dx * dx + dz * dz <= R * R + R]
    region_seen = {}                                 # region -> models visible from it
    for rz in range(rz_n):
        for rx in range(rx_n):
            x0, z0 = rx * REGION_CELLS, rz * REGION_CELLS
            sub = radii[z0:z0 + REGION_CELLS, x0:x0 + REGION_CELLS]
            vis = np.zeros((REGION_CELLS + 2 * pad, REGION_CELLS + 2 * pad), dtype=bool)
            for r in range(pvs.MIN_RADIUS, pvs.MAX_RADIUS + 1):
                mask = sub == r
                if mask.any():
                    for dx, dz in discs[r]:
                        vis[pad + dz: pad + dz + REGION_CELLS, pad + dx: pad + dx + REGION_CELLS] |= mask
            seen = set()
            for vz, vx in zip(*np.nonzero(vis)):
                seen |= cell_model_ids.get((x0 + int(vx) - pad, z0 + int(vz) - pad), set())
            region_seen[(rx, rz)] = seen
    # models close to each region (its cells + NEAR_CELLS around): their
    # textures are seen up close, so the texture packer shrinks them last
    region_near = {}
    for rz in range(rz_n):
        for rx in range(rx_n):
            x0, z0 = rx * REGION_CELLS - NEAR_CELLS, rz * REGION_CELLS - NEAR_CELLS
            near = set()
            for cz in range(z0, z0 + REGION_CELLS + 2 * NEAR_CELLS):
                for cx in range(x0, x0 + REGION_CELLS + 2 * NEAR_CELLS):
                    near |= cell_model_ids.get((cx, cz), set())
            region_near[(rx, rz)] = near

    # --- areas ----------------------------------------------------------------
    # Driver 1 switches the loaded area only inside border regions (0x80033F9C);
    # elsewhere it keeps whatever was loaded, so an area entered from an
    # unexpected side stays wrong and its objects are drawn through stale model
    # pointers (the Chicago freezes/crashes). Here every region gets switch
    # entries (border pair, or its own area twice) and the thresholds are moved
    # to the region middle (EXE patch), so the loaded area always matches.
    # Area sets are then built from what each region can see, and areas that
    # would need too many textures (32 palettes per VRAM page) are split.
    d2_area = {}
    for idx, off in enumerate(sp2.region_offsets):
        if off != 0xFFFF:
            d2_area[(idx % hdr2.regions_across, idx // hdr2.regions_across)] = sp2.spools[off][7]
    d2_region_units = hdr2.region_size * hdr2.cell_size
    d2_half_x = hdr2.cells_across // 2 * hdr2.cell_size
    d2_half_z = hdr2.cells_down // 2 * hdr2.cell_size

    def d2_area_at(x, z):
        x, z = ws.to_d2(x, z)
        return d2_area.get(((x + d2_half_x) // d2_region_units, (z + d2_half_z) // d2_region_units), 255)

    region_area = {}
    for rz in range(rz_n):
        for rx in range(rx_n):
            votes = collections.Counter()
            for sx in range(5):
                for sz in range(5):
                    x = rx * REGION_CELLS * CELL - half_x + (sx * 2 + 1) * REGION_CELLS * CELL // 10
                    z = rz * REGION_CELLS * CELL - half_z + (sz * 2 + 1) * REGION_CELLS * CELL // 10
                    votes[d2_area_at(x, z)] += 1
            real = [(n, a) for a, n in votes.items() if a != 255]
            region_area[(rx, rz)] = max(real)[1] if real else 255
    # regions outside Driver 2's areas take the nearest area (breadth-first)
    frontier = [r for r, a in region_area.items() if a != 255]
    while frontier and any(a == 255 for a in region_area.values()):
        nxt = []
        for (rx, rz) in frontier:
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = (rx + dx, rz + dz)
                if region_area.get(nb) == 255:
                    region_area[nb] = region_area[(rx, rz)]
                    nxt.append(nb)
        frontier = nxt

    texof = {}

    def textures_of(models):
        out = set()
        for m in models:
            if m not in texof:
                texof[m] = model_texrefs(models_all[m], models_all) if m in models_all else set()
            out |= texof[m]
        return out

    dirs = {0: (0, 1), 1: (1, 0), 2: (0, -1), 3: (-1, 0)}    # D1: 0 +z, 1 +x, 2 -z, 3 -x
    opposite = {0: 2, 1: 3, 2: 0, 3: 1}

    def switch_entries():
        # a region has room for two entries (area, direction): border regions get
        # (neighbour area, towards it) + (own area, back); inner regions their own
        # area twice, on alternating axes (checkerboard), so a stale area loaded in
        # the middle band (cells 13-17, no switching) never crosses a second region
        connected = {}
        for (rx, rz), a in region_area.items():
            nbs = [(region_area[(rx + dx, rz + dz)], d) for d, (dx, dz) in dirs.items()
                   if region_area.get((rx + dx, rz + dz), a) != a]
            if nbs:
                nb, d = nbs[0]
                connected[(rx, rz)] = [(nb, d), (a, opposite[d])]
            else:
                connected[(rx, rz)] = [(a, 0), (a, 2)] if (rx + rz) % 2 else [(a, 1), (a, 3)]
        return connected

    def loadable_areas(connected):
        """Every area that can be loaded while the camera is in a region: simulate
        the switch rule (0x80033F9C: an entry fires when the cell inside the region
        passes 17 towards its direction or 13 away from it, and no switch starts
        while one is loading; the car can cross SWITCH_LAG cells meanwhile)."""
        lo, hi = AREA_BAND_LOW, REGION_CELLS - AREA_BAND_LOW
        nx, nz = rx_n * REGION_CELLS, rz_n * REGION_CELLS

        def fire(cx, cz, loaded):
            reg = (cx // REGION_CELLS, cz // REGION_CELLS)
            ix, iz = cx % REGION_CELLS, cz % REGION_CELLS
            for area, d in connected[reg]:
                if area == loaded:
                    continue
                if (d == 0 and iz > hi) or (d == 1 and ix > hi) or (d == 2 and iz < lo) or (d == 3 and ix < lo):
                    return area
            if loaded not in (connected[reg][0][0], connected[reg][1][0]):
                return connected[reg][1][0]        # exe_patches.AREA_OWN: stale area -> own area
            return loaded

        seen = set()
        todo = []
        for cz in range(nz):
            for cx in range(nx):
                s = (cx, cz, region_area[(cx // REGION_CELLS, cz // REGION_CELLS)], 0)
                seen.add(s); todo.append(s)
        while todo:
            cx, cz, loaded, lag = todo.pop()
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                x, z = cx + dx, cz + dz
                if not (0 <= x < nx and 0 <= z < nz):
                    continue
                if lag:
                    s = (x, z, loaded, lag - 1)
                else:
                    now = fire(x, z, loaded)
                    s = (x, z, now, SWITCH_LAG if now != loaded else 0)
                if s not in seen:
                    seen.add(s); todo.append(s)
        out = collections.defaultdict(set)
        for cx, cz, loaded, _ in seen:
            out[(cx // REGION_CELLS, cz // REGION_CELLS)].add(loaded)
        return out

    while True:
        connected = switch_entries()
        loadable = loadable_areas(connected)
        area_regions = collections.defaultdict(set)
        for reg, las in loadable.items():
            for la in las:
                area_regions[la].add(reg)
        counts = {a: len(textures_of(set().union(*(region_seen.get(r, set()) for r in area_regions[a]))))
                  for a in sorted(set(region_area.values()))}
        big = [(n, a) for a, n in counts.items() if n > AREA_TEXTURE_LIMIT]
        if not big:
            break
        _, a = max(big)
        regs = sorted(r for r, ra in region_area.items() if ra == a)
        if len(regs) < 2:
            raise RuntimeError("area %d: one region already needs %d textures (loadable in %d regions; %.2f areas per region)" % (
                a, counts[a], len(area_regions[a]), sum(map(len, loadable.values())) / len(loadable)))
        new_id = min(set(range(64)) - set(region_area.values()))
        xs = sorted(r[0] for r in regs)
        zs = sorted(r[1] for r in regs)
        axis = 0 if xs[-1] - xs[0] >= zs[-1] - zs[0] else 1
        mid = sorted(r[axis] for r in regs)[len(regs) // 2]
        moved = [r for r in regs if r[axis] >= mid]
        if len(moved) == len(regs):
            moved = regs[len(regs) // 2:]
        for r in moved:
            region_area[r] = new_id
    print("areas:", len(counts), "textures per area:", counts,
          "loadable areas per region: %.2f" % (sum(map(len, loadable.values())) / len(loadable)))

    # area model sets: every streamed model visible from a region, in each area
    # that region can load
    used_areas = sorted(set(region_area.values()))
    sets = {a: set() for a in used_areas}
    model_vis = collections.defaultdict(set)         # every model -> areas it is visible in
    model_near = collections.defaultdict(set)        # every model -> areas it is seen close up in
    for reg, seen in region_seen.items():
        loadable_here = loadable[reg]
        streamed = {m for m in seen if m not in inmem_ids and m in models_all}
        for la in loadable_here:
            sets[la].update(streamed)
            for m in seen:
                model_vis[m].add(la)
            for m in region_near[reg]:
                model_near[m].add(la)
    for a, ids in sets.items():                      # instances need their source loaded
        todo = list(ids)
        while todo:
            src = models_all[todo.pop()].instance_number
            if src >= 0 and src not in inmem_ids and src not in ids and src in models_all:
                ids.add(src); todo.append(src)
    used_areas = sorted(sets)                        # every area, even without streamed models
    area_model_ids = {a: sorted(sets[a]) for a in used_areas}

    return dict(across=across, down=down, rx_n=rx_n, rz_n=rz_n, obj_list=obj_list, covered=covered,
                straddlers=straddlers, local=local, obj_num=obj_num, cell_lists=cell_lists,
                region_area=region_area, connected=connected, area_model_ids=area_model_ids,
                model_vis=model_vis, model_near=model_near, radii=radii, region_seen=region_seen,
                used_areas=used_areas, hdr2=hdr2)


_d2_cache = {}


def d2_extract_cached():
    if "v" not in _d2_cache:
        _d2_cache["v"] = d2_extract("work/d2_CHICAGO.LEV")
    return _d2_cache["v"]


def pack_cell_pointers(ptrs: list[int]) -> bytes:
    """Packtype 2: 16-cell bitmask words, each followed by its present pointers."""
    words = []
    for i in range(0, len(ptrs), 16):
        group = ptrs[i: i + 16]
        mask = 0
        vals = []
        for k, p in enumerate(group):
            if p != 0xFFFF:
                mask |= 0x8000 >> k
                vals.append(p)
        words.append(mask)
        words.extend(vals)
    body = struct.pack("<%dH" % len(words), *words)
    # first word = byte length of (packtype word + packed data); verified on
    # every packed region of LA, Miami and San Francisco
    return struct.pack("<ii", 4 + len(body), 2) + body


def cell_object(o) -> bytes:
    return struct.pack("<3iBBH", o.x, o.y, o.z, 0, o.yang, o.model)


def instance_order(ids, area_data, inmem_ids, area):
    """The area loader (0x80033E54) copies an instance's pointers from its
    source as they are, so the source must be in memory or earlier in the list."""
    pos = {i: k for k, i in enumerate(ids)}
    out, done = [], set()

    def add(i):
        if i in done:
            return
        src = struct.unpack_from("<h", area_data[i], 4)[0]
        if src >= 0 and src != i and src not in inmem_ids:
            if src not in pos:
                raise RuntimeError("area %d: model %d instances %d, which is neither in memory "
                                   "nor in the area" % (area, i, src))
            add(src)
        done.add(i)
        out.append(i)

    for i in ids:
        add(i)
    return out


def subdiv_textures(cmem, carea):
    """Lowest SUBDIVISION texture offset referenced by a ground tile (+0x2C high
    half); the lump holds tile vertices below it."""
    offs = [struct.unpack_from("<I", m.data, 0x2C)[0] >> 16 for m in {**carea, **cmem}.values()
            if m.shape_flags & 0x2400 and m.vertices >= 0x30]
    return min(o for o in offs if o)


def replace_model(lump: bytes, index: int, data: bytes) -> bytes:
    """Replace model <index> in a MODELS lump (count, then size + data per model)."""
    n, = struct.unpack_from("<i", lump, 0)
    p, out = 4, bytearray(lump[:4])
    for i in range(n):
        size, = struct.unpack_from("<i", lump, p)
        body = lump[p + 4: p + 4 + size]
        if i == index:
            body = data
        out += struct.pack("<i", len(body)) + body
        p += 4 + size
    out += lump[p:]
    return bytes(out)


def remap_subdivision(lump: bytes, cmem, carea, remap: dict, fallback) -> bytes:
    """Ground tiles drawn at a distance (0x80026C38) take their texture
    coordinates from SUBDIVISION: 20-byte records (+0x2C high half) of nine
    (u, v) pairs, one per point of the tile's 3 x 3 grid, in the page layout
    of the tile's texture. Remap them like the polygon UVs (remap_polys)."""
    d = bytearray(lump)
    if "no_subremap" in EXPERIMENT:
        return bytes(d)
    done = set()
    for m in {**carea, **cmem}.values():
        if not (m.shape_flags & 0x2400) or m.vertices < 0x30 or m.num_polys == 0:
            continue
        off = struct.unpack_from("<I", m.data, 0x2C)[0] >> 16
        if not off or off in done or off + 18 > len(d):
            continue
        q = m.poly_block
        r = remap.get(("C", m.data[q + 1], m.data[q + 2])) or fallback
        np_, nd, nx, ny, ox, oy, ow, oh, nw, nh = r
        for k in range(9):
            u, v = d[off + 2 * k], d[off + 2 * k + 1]
            d[off + 2 * k] = min(max(nx + (u - ox) * nw // ow, nx), nx + nw - 1)
            d[off + 2 * k + 1] = min(max(ny + (v - oy) * nh // oh, ny), ny + nh - 1)
        done.add(off)
    return bytes(d)


def build_spooled(world, area_data, res, chi: Lev):
    across, rx_n, rz_n = world["across"], world["rx_n"], world["rz_n"]
    obj_list, obj_num = world["obj_list"], world["obj_num"]
    nstrad = len(world["straddlers"])
    spooled = bytearray()
    areas = {}

    # area blocks: textures (raw pages) then models (+ count/id trailer block)
    for a in world["used_areas"]:
        gfx = len(spooled) // BLOCK
        pages = [] if "no_area_tex" in EXPERIMENT else res.area_pages.get(a, [])
        for idx in pages:
            spooled += pad(encode_raw(res.area_page_content.get((a, idx), res.pages[idx])))
        model_off = len(spooled) // BLOCK
        ids = instance_order([i for i in world["area_model_ids"][a] if i in area_data], area_data,
                             world["inmem_ids"], a)
        body = bytearray()
        for i in ids:
            body += struct.pack("<i", len(area_data[i])) + area_data[i]
        body = pad(bytes(body))
        trailer = pad(struct.pack("<H", len(ids)) + struct.pack("<%dH" % len(ids), *ids))
        spooled += body + trailer
        model_size = (len(body) + len(trailer)) // BLOCK
        areas[a] = (gfx, model_off, model_size, len(pages))

    # regions
    per_region = {}
    for rz in range(rz_n):
        for rx in range(rx_n):
            reg = (rx, rz)
            cells = []
            for cz in range(REGION_CELLS):
                for cx in range(REGION_CELLS):
                    cells.append(world["cell_lists"].get((rx * REGION_CELLS + cx, rz * REGION_CELLS + cz), []))
            per_region[reg] = cells     # every region gets a record (see EMPTY below)

    barrel = lambda reg: (reg[0] & 1) + (reg[1] & 1) * 2
    slots_max, objs_max = [0] * 4, [0] * 4
    for reg, cells in per_region.items():
        b = barrel(reg)
        slots_max[b] = max(slots_max[b], sum(len(c) for c in cells))
        objs_max[b] = max(objs_max[b], len(world["local"].get(reg, [])))
    slots_max = [((s + 511) // 512) * 512 or 512 for s in slots_max]
    objs_max = [((s + 127) // 128) * 128 or 128 for s in objs_max]
    slots_add = [sum(slots_max[:b]) for b in range(4)]
    objs_add = [sum(objs_max[:b]) for b in range(4)]

    spool_records = bytearray()
    region_offsets = [0xFFFF] * (rx_n * rz_n)
    total_cell_data = 0
    # Driver 1 does not skip an empty (0xFFFF) entry for the region the player
    # is in, so every region gets a record. Empty regions share one data block,
    # but each keeps its own area switch entries (one record per distinct set).
    empty_block = None                     # record fields of the shared empty data block
    empty_records = {}                     # switch entries -> record offset

    def record(fields, conn):
        start, pvs_n, cell_n, ptr_n, obj_n, roadm_n, roadh_n = fields
        ca = [(c | (d << 6)) for c, d in conn] + [0, 0]
        return struct.pack("<H2BB3BBBBB", start, ca[0], ca[1], pvs_n, cell_n, ptr_n, obj_n,
                           255, len(conn), roadm_n, roadh_n)

    for reg in sorted(per_region, key=lambda r: (r[1], r[0])):
        cells = per_region[reg]
        b = barrel(reg)
        conn = tuple(world["connected"][reg])
        full_view = all(int(r) >= pvs.MAX_RADIUS for r in world["radii"][reg[1] * REGION_CELLS:(reg[1] + 1) * REGION_CELLS,
                                                                           reg[0] * REGION_CELLS:(reg[0] + 1) * REGION_CELLS].flatten())
        shareable = not any(cells) and full_view
        if shareable and empty_block is not None:
            if conn not in empty_records:
                empty_records[conn] = len(spool_records)
                spool_records += record(empty_block, conn)
            region_offsets[reg[1] * rx_n + reg[0]] = empty_records[conn]
            continue
        start = len(spooled) // BLOCK
        roadm = pad(struct.pack("<hH", ROAD_CELLS_PER_REGION, 0xFFFF) + struct.pack("<hH", -1, 0))
        roadh = pad(rle_roadh(world["road_values"][reg]) if "flat_ground" not in EXPERIMENT
                    else struct.pack("<II", ROAD_CELLS_PER_REGION, FLAT_GROUND))
        ptrs, celldata = [], []
        for objs in cells:
            if not objs:
                ptrs.append(0xFFFF)
                continue
            ptrs.append(len(celldata))
            for k, oi in enumerate(objs):
                kind, n = obj_num[oi]
                num = n if kind == "s" else nstrad + objs_add[b] + n
                nxt = 0xFFFF if k == len(objs) - 1 else len(celldata) + 1 + slots_add[b]
                celldata.append((num, nxt))
        total_cell_data += len(celldata)
        ptr_blob = pad(pack_cell_pointers(ptrs))
        cell_blob = pad(b"".join(struct.pack("<HH", *c) for c in celldata) or bytes(4))
        objs_blob = pad(b"".join(cell_object(obj_list[oi]) for oi in world["local"].get(reg, [])) or bytes(16))
        pvs_blob = pad(pvs.region_block([int(world["radii"][reg[1] * REGION_CELLS + cz, reg[0] * REGION_CELLS + cx])
                                         for cz in range(REGION_CELLS) for cx in range(REGION_CELLS)]))
        spooled += roadm + roadh + ptr_blob + cell_blob + objs_blob + pvs_blob
        fields = (start, len(pvs_blob) // BLOCK, len(cell_blob) // BLOCK, len(ptr_blob) // BLOCK,
                  len(objs_blob) // BLOCK, len(roadm) // BLOCK, len(roadh) // BLOCK)
        if shareable:
            empty_block = fields
            empty_records[conn] = len(spool_records)
        region_offsets[reg[1] * rx_n + reg[0]] = len(spool_records)
        spool_records += record(fields, conn)
    return bytes(spooled), areas, slots_max, objs_max, region_offsets, bytes(spool_records), total_cell_data


WATER_MODEL = 683            # free in-memory Chicago slot < 900 (road map ids must be < 900)
WATER_SRC = 316              # LA's water tile (shape flags 0x04A1, 1500 x 1500, LASEA)
WATER_SCALE = 2              # LA's 1500 tile stretched to one per 3000 cell (with real corner vertices, see water_model)
WATER_Y = int(os.environ.get("CHI_WATER_Y", "300"))               # water surface below street level (900 left a gap under D2 quay walls and bridges)
WATER_NEAR = 4               # water tiles on water cells within this many cells of land
WATER_BELOW_SHORE = 100      # water this far under the lowest shore nearby
WATER_SHORE_RADIUS = 8       # road cells (12000 units)
WATER_MAX_DEPTH = 2000
WATER_CLOSE = int(os.environ.get("CHI_WATER_CLOSE", "4"))   # land gaps (bridges) filled between water cells
WATER_GROW = int(os.environ.get("CHI_WATER_GROW", "0"))     # cells of water under the shore (0: water only where there is water)


def surface_grid(across, down):
    """Driver 2 surface per 3000-unit cell, sampled at its 4 quarter points:
    {(cx, cz): (land?, wet?)} (cached)."""
    import pickle, hashlib
    from d2surface import Surface
    key = hashlib.md5(open("d2surface.py", "rb").read()).hexdigest()[:8]
    cache = "work/surface_grid4_%d_%d_%s.pkl" % (across, down, key)
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    surf = Surface("work/d2_CHICAGO.LEV")
    half_x, half_z = across // 2 * CELL, down // 2 * CELL
    grid = {}
    for cz in range(down):
        for cx in range(across):
            land = wet = False
            for ox in (CELL // 4, 3 * CELL // 4):
                for oz in (CELL // 4, 3 * CELL // 4):
                    lv = surf.levels(*ws.to_d2(cx * CELL + ox - half_x, cz * CELL + oz - half_z))
                    land |= any(t not in (6, 9) for _, t in lv)
                    wet |= any(t in (6, 9) for _, t in lv)
            grid[(cx, cz)] = (land, wet)
    pickle.dump(grid, open(cache, "wb"))
    return grid


def sea_kinds(across, down):
    """Driver 2 has no water surface: the lake, the river, building interiors and
    the land outside the city all read as "no surface" (sea). Its overhead map
    (d2overlay.py) draws the real water: lake = palette 12, river = 1 (thin, so
    one pixel of slack). Returns {(col, row): "water" | "void" | "inside"} for the
    no-surface 1500-unit road cells: void = joined to the map edge (outside the
    city, drowning keeps it as a boundary), inside = enclosed (building blocks)."""
    import pickle, hashlib
    from d2overlay import Overlay
    world = dict(across=across, down=down, rx_n=across // REGION_CELLS, rz_n=down // REGION_CELLS)
    grid = road_levels(world)
    key = hashlib.md5((open("d2overlay.py", "rb").read() + repr(sorted(grid.items())[:50]).encode() + b"v3")).hexdigest()[:8]
    cache = "work/sea_kinds_%s.pkl" % key
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    ov = Overlay("work/d2_CHICAGO.LEV")
    half_x, half_z = across // 2 * CELL, down // 2 * CELL
    sea = {k for k, lv in grid.items() if all(t in (6, 9) for _, t in lv)}
    w, h = world["rx_n"] * 60, world["rz_n"] * 60
    r = ov.scale * 2                           # map / world misfit of a few pixels
    out = {}
    for start in sea:                          # connected no-surface areas (4-neighbours)
        if start in out:
            continue
        comp, todo = [], [start]
        out[start] = None
        while todo:
            k = todo.pop()
            comp.append(k)
            for n in ((k[0] + 1, k[1]), (k[0] - 1, k[1]), (k[0], k[1] + 1), (k[0], k[1] - 1)):
                if n in sea and n not in out:
                    out[n] = None; todo.append(n)
        wet = 0
        for (col, row) in comp[::max(1, len(comp) // 4000)]:
            dx, dz = ws.to_d2(col * ROAD_UNIT - half_x, half_z - row * ROAD_UNIT)
            wet += any(ov.at(dx + ox, dz + oz) in (1, 12) for ox in (-r, 0, r) for oz in (-r, 0, r))
        frac = wet / len(comp[::max(1, len(comp) // 4000)])
        edge = any(k[0] in (0, w - 1) or k[1] in (0, h - 1) for k in comp)
        kind = "water" if frac >= 0.3 else ("void" if edge else "inside")
        if edge and len(comp) > 100000:        # the lake joins the land outside the city: per cell
            for (col, row) in comp:
                dx, dz = ws.to_d2(col * ROAD_UNIT - half_x, half_z - row * ROAD_UNIT)
                out[(col, row)] = "water" if ov.at(dx, dz) in (1, 12) else "void"
            continue
        for k in comp:
            out[k] = kind
    for _ in range(3):                         # shore: map misfit leaves void strips at the water
        grow = [k for k, v in out.items() if v == "void" and any(
            out.get(n) == "water" for n in ((k[0] + 1, k[1]), (k[0] - 1, k[1]), (k[0], k[1] + 1), (k[0], k[1] - 1)))]
        for k in grow:
            out[k] = "water"
    pickle.dump(out, open(cache, "wb"))
    return out


def water_heights(across, down):
    """Water surface (road value: down from street level) per real-water road cell.
    The river is banked at street level (water at WATER_Y); the lake shore drops
    to beaches far below the streets (median 586, p90 2022), where a lake at
    WATER_Y floated above the sand. Each water cell sits WATER_BELOW_SHORE under
    the lowest shore within WATER_SHORE_RADIUS cells, at least WATER_Y, at most
    WATER_MAX_DEPTH."""
    import numpy as np
    from scipy.ndimage import maximum_filter
    kinds = sea_kinds(across, down)
    world = dict(across=across, down=down, rx_n=across // REGION_CELLS, rz_n=down // REGION_CELLS)
    grid = road_levels(world)
    w, h = world["rx_n"] * 60, world["rz_n"] * 60
    shore = np.full((h, w), -10 ** 6, dtype=np.int32)
    for (col, row), lv in grid.items():
        if kinds.get((col, row)) is None and any(kinds.get(n) == "water" for n in
                                                  ((col + 1, row), (col - 1, row), (col, row + 1), (col, row - 1))):
            lv = sorted(lv, key=lambda hl: (hl[1] in (6, 9), abs(hl[0])))
            shore[row, col] = min(lv[0][0], WATER_MAX_DEPTH)
    low = maximum_filter(shore, size=2 * WATER_SHORE_RADIUS + 1)
    return {k: int(min(max(WATER_Y, low[k[1], k[0]] + WATER_BELOW_SHORE), WATER_MAX_DEPTH))
            for k, v in kinds.items() if v == "water"}


def water_cells(across, down):
    """Cells that get a water tile: every 3000-unit cell with real water (sea_kinds)
    in one of its four road cells, plus land gaps of up to WATER_CLOSE cells
    between water (bridges: Driver 2 has no water level under them), WATER_GROW
    cells under the shore, within WATER_NEAR cells of land (open lake far out is
    never seen)."""
    kinds = sea_kinds(across, down)
    rows = down // REGION_CELLS * 60
    wet, land = set(), set()
    for cz in range(down):
        for cx in range(across):
            cells = [(2 * cx + i, rows - 1 - (2 * cz + j)) for i in (0, 1) for j in (0, 1)]
            k = [kinds.get(c) for c in cells]
            if "water" in k:
                wet.add((cx, cz))
            if None in k:
                land.add((cx, cz))
    out = set(wet)
    for (cx, cz) in wet:                       # close: land runs between two water cells
        for dx, dz in ((1, 0), (0, 1)):
            for n in range(2, WATER_CLOSE + 2):
                if (cx + dx * n, cz + dz * n) in wet:
                    if all((cx + dx * k, cz + dz * k) not in wet for k in range(1, n)):
                        out.update((cx + dx * k, cz + dz * k) for k in range(1, n))
                    break
    for _ in range(WATER_GROW):                # grow under the shore
        out |= {(cx + dx, cz + dz) for (cx, cz) in out for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
                if 0 <= cx + dx < across and 0 <= cz + dz < down}
    near = set()
    for (cx, cz) in land:
        for dx in range(-WATER_NEAR, WATER_NEAR + 1):
            for dz in range(-WATER_NEAR, WATER_NEAR + 1):
                near.add((cx + dx, cz + dz))
    return sorted(out & near)


def water_model(base: Lev, res, fallback, sub_off: int):
    """LA's water tile, scaled, textures remapped; returns (model bytes, SUBDIVISION
    bytes to append at sub_off: 9-vertex grid then the texture record)."""
    bmem, _ = inmem_models(base)
    ball = {**area_models(base), **bmem}
    m = ball[WATER_SRC]
    # LA's tile has no vertex array (+0x10 points at its polygon); far tiles (shape
    # 0x20, 0x800274B8) read four corner vertices from there, so a stretched tile
    # shrank back to 1500 squares in the distance. Give it real corners (the outer
    # points of its 3 x 3 SUBDIVISION grid, matched by UV), scaled like the grid.
    w0 = struct.unpack_from("<I", m.data, 0x2C)[0]
    bsub0 = base.inmem.get(L_SUBDIV).data
    grid0 = [struct.unpack_from("<3h", bsub0, (w0 & 0xFFFF) + 8 * k) for k in range(9)]
    rec0 = bsub0[(w0 >> 16): (w0 >> 16) + 18]
    q0 = m.poly_block
    corners = []
    for i in range(4):
        uv = (m.data[q0 + 8 + 2 * i], m.data[q0 + 9 + 2 * i])
        k = next(k for k in range(9) if (rec0[2 * k], rec0[2 * k + 1]) == uv)
        x, y, z = grid0[k]
        corners.append(struct.pack("<4h", x * WATER_SCALE, y, z * WATER_SCALE, 0))
    poly = m.data[q0: q0 + 20]
    hdr = bytearray(m.data[:q0])
    struct.pack_into("<4i", hdr, 0x10, q0, q0 + 32, q0 + 32, q0 + 32)   # vertices, polygons, normals, +0x1C
    d = bytearray(remap_polys(bytes(hdr) + b"".join(corners) + poly, "B", res.remap, fallback))
    struct.pack_into("<h", d, 8, min(0x7FFF, abs(m.bounding_sphere) * WATER_SCALE))
    struct.pack_into("<H", d, 2, struct.unpack_from("<H", d, 2)[0] | 0x4000)   # flags2 water: cars sink (like LA's 330)
    w = struct.unpack_from("<I", m.data, 0x2C)[0]
    bsub = base.inmem.get(L_SUBDIV).data
    vb, tr = w & 0xFFFF, w >> 16
    grid = bytearray()
    for k in range(9):
        x, y, z, p = struct.unpack_from("<4h", bsub, vb + 8 * k)
        grid += struct.pack("<4h", x * WATER_SCALE, y, z * WATER_SCALE, p)
    rec = bytearray(bsub[tr: tr + 20])
    q = m.poly_block
    r = res.remap.get(("B", m.data[q + 1], m.data[q + 2])) or fallback
    np_, nd, nx, ny, ox, oy, ow, oh, nw, nh = r
    for k in range(9):
        u, v = rec[2 * k], rec[2 * k + 1]
        rec[2 * k] = min(max(nx + (u - ox) * nw // ow, nx), nx + nw - 1)
        rec[2 * k + 1] = min(max(ny + (v - oy) * nh // oh, ny), ny + nh - 1)
    struct.pack_into("<I", d, 0x2C, ((sub_off + 72) << 16) | sub_off)
    return bytes(d), bytes(grid + rec)


FAR_WATER = any(e.startswith("farwater") for e in EXPERIMENT) and "no_water" not in EXPERIMENT   # opt-in until verified
FAR_SIZE = 6000              # far water plane: 2 x 2 cells, 2 x 2 quads of the water texture
FAR_SHORE = 1                # road cells of open water around it (only over water, never over land)
FAR_REACH = 24               # road cells from land (36000 units): beyond that it is never seen


def far_water_model(res, fallback) -> bytes:
    """A flat object (not a ground tile) of 4 x 4 water quads: drawn like a
    building, so the lake also shows beyond the 9000-unit ground tile range."""
    import d1models
    n, half = FAR_SIZE // 3000, FAR_SIZE // 2
    step = FAR_SIZE // n
    verts = [(-half + i * step, 0, -half + j * step) for j in range(n + 1) for i in range(n + 1)]
    uv = [(241, 25), (241, 11), (255, 11), (255, 25)]           # LASEA rectangle, as LA's water tile
    polys = []
    for j in range(n):
        for i in range(n):
            loop = [j * (n + 1) + i, (j + 1) * (n + 1) + i, (j + 1) * (n + 1) + i + 1, j * (n + 1) + i + 1]
            poly = bytes([11, 0, 10, 0] + loop) + b"".join(bytes(t) for t in uv)
            if d1models.poly_normal(poly, verts)[1] > 0:            # face up (model y up = negative)
                loop = loop[::-1]
                poly = bytes([11, 0, 10, 0] + loop) + b"".join(bytes(t) for t in uv[::-1])
            polys.append(poly)
    vblock = b"".join(struct.pack("<4h", x, y, z, 0) for x, y, z in verts)
    pblock = b"".join(polys)
    v_off = 36
    p_off = v_off + len(vblock)
    hdr = struct.pack("<3hBB4h5i", 0x0001, 0, -1, 0, 0, int(half * 1.415), 0, len(verts), len(polys),
                      v_off, p_off, p_off, p_off, 0)
    raw = hdr + vblock + pblock
    conv, _ = d1models.convert_models({0: raw})
    return remap_polys(conv[0], "B", res.remap, fallback)


def far_water_blocks(across, down):
    """Far water planes: (x, y, z) per 4 x 4 cell block of open lake."""
    kinds = sea_kinds(across, down)
    wh = water_heights(across, down)
    rows = down // REGION_CELLS * 60
    half_x, half_z = across // 2 * CELL, down // 2 * CELL
    land = {k for k in road_levels(dict(across=across, down=down, rx_n=across // REGION_CELLS,
                                        rz_n=down // REGION_CELLS)) if kinds.get(k) is None}
    import numpy as np
    from scipy.ndimage import binary_dilation
    w, h = across * 2, rows
    lm = np.zeros((h, w), bool)
    for c, r in land:
        lm[r, c] = True
    near_land = binary_dilation(lm, iterations=FAR_SHORE)
    reach = binary_dilation(lm, iterations=FAR_REACH)
    out = []
    b = FAR_SIZE // ROAD_UNIT                  # road cells per block side
    for bz in range(0, h - b + 1, b):
        for bx in range(0, w - b + 1, b):
            cells = [(bx + i, bz + j) for i in range(b) for j in range(b)]
            if any(kinds.get(k) != "water" or near_land[k[1], k[0]] for k in cells):
                continue
            if not reach[bz + b // 2, bx + b // 2]:
                continue
            y = max(wh.get(k, WATER_Y) for k in cells)
            out.append((bx * ROAD_UNIT - half_x + FAR_SIZE // 2 - ROAD_UNIT // 2, y,
                        half_z - bz * ROAD_UNIT - FAR_SIZE // 2 + ROAD_UNIT // 2))
    return out


ROAD_CELLS_PER_REGION = 3600
ROAD_TOP = 0xF << 26          # bits 26-29 as on almost all of LA's cells (not read by the height code)
ROAD_FLAG = 4                 # bit 2, set on 87% of LA's cells
GRASS_ID = 0                  # plain ground: in Driver 1, flags2 0x4000 means WATER (waves, drowning);
                              # Driver 2 reused it for grass, so Chicago's grass models must not be used
ROAD_TYPES_GRASS = (4, 11)    # D2 grass, sand
DECK_HEIGHT = 500           # a level this far above another one in the same cell = deck
WATER_FLAG = int(os.environ.get("CHI_WATER_FLAG", "4"))   # LA: 0
HEIGHT_DEADBAND = 100         # |ground y| below this -> 0 (a start on raised grass, -24, ended the game)
RAMP_STEP = int(os.environ.get("CHI_RAMP_STEP", "0"))     # 0 = a street bridging a trench drops in at the bridge edge; N = stepped ramp (<= N per cell) over 6 cells, which the user found worse (car inside the geometry for a long stretch)
GROUND_TYPES = (0, 4, 11, 12)  # D2 surface types that are plain ground (not a road); >= 0x4000 = kerb/pavement
WALLTOP = int(os.environ.get("CHI_WALLTOP", "1"))        # ground cells beside a sunken road follow it (0: off)
MEDIAN_SNAP = int(os.environ.get("CHI_MEDIAN_SNAP", "40"))  # a cell this little above a neighbour takes the neighbour's level (median kerbs; 0: off)
SURF_SEP = 300                # levels this far apart in one cell become separate ROADSURF planes (engine patch picks the nearest to the wheel)
SLOPE_MIN = 30                # height change across a cell (1500) from which a sloped plane is written
SLOPE_SIGN = (int(os.environ.get("CHI_SLOPE_SX", "1")), int(os.environ.get("CHI_SLOPE_SZ", "1")))   # sign of the plane's x / z gradient (verified in game)
SURF_MAX = int(os.environ.get("CHI_SURF_MAX", "320"))   # distinct ROADSURF surfaces (type ids are plain model ids < 900; 120 B each in memory)
SURF_Q = 64                   # quantisation of plane offsets and gradients (fewer distinct surfaces)


def road_levels(world):
    """Driver 2 surface levels at every 1500-unit road cell: {(col, row): [(ground y, type)]},
    col/row as the game counts them (row 0 at the top, max z). Cached."""
    import pickle, hashlib
    from d2surface import Surface
    key = hashlib.md5(open("d2surface.py", "rb").read() + repr(
        (world["rx_n"], world["rz_n"], world["across"], world["down"], ws.SCALE)).encode()).hexdigest()[:8]
    cache = "work/road_levels_%s.pkl" % key
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    surf = Surface("work/d2_CHICAGO.LEV")
    half_x, half_z = world["across"] // 2 * CELL, world["down"] // 2 * CELL
    grid = {}
    for row in range(world["rz_n"] * 60):
        for col in range(world["rx_n"] * 60):
            # the game's cell (0x8001EF00): column (x + half_x + 750) / 1500, row
            # (half_z - z + 750) / 1500 counted from the top. Verified on LA's water.
            dx, dz = ws.to_d2(col * ROAD_UNIT - half_x, half_z - row * ROAD_UNIT)
            lv = surf.levels(dx, dz)
            if all(t in (6, 9) for _, t in lv):      # sea: check around (BSP misses ~3%)
                near = [l for ox, oz in ((400, 0), (-400, 0), (0, 400), (0, -400))
                        for l in surf.levels(dx + ox, dz + oz) if l[1] not in (6, 9)]
                if len(near) >= 2:
                    lv = near
            grid[(col, row)] = sorted({(int(round(-h * ws.SCALE)), t) for h, t in lv})   # y down
    pickle.dump(grid, open(cache, "wb"))
    return grid


def sea_fixed_cells(world):
    """Cells whose road_levels entry was replaced by nearby land levels because the
    Driver 2 surface says sea at the cell centre (river banks, quays). Cached."""
    import pickle, hashlib
    from d2surface import Surface
    key = hashlib.md5(open("d2surface.py", "rb").read() + repr(
        (world["rx_n"], world["rz_n"], world["across"], world["down"], ws.SCALE, "seafix1")).encode()).hexdigest()[:8]
    cache = "work/sea_fixed_%s.pkl" % key
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    surf = Surface("work/d2_CHICAGO.LEV")
    half_x, half_z = world["across"] // 2 * CELL, world["down"] // 2 * CELL
    out = set()
    for row in range(world["rz_n"] * 60):
        for col in range(world["rx_n"] * 60):
            dx, dz = ws.to_d2(col * ROAD_UNIT - half_x, half_z - row * ROAD_UNIT)
            if all(t in (6, 9) for _, t in surf.levels(dx, dz)):
                out.add((col, row))
    pickle.dump(out, open(cache, "wb"))
    return out


def trench_rule(world, grid, choice, kinds):
    """Roads below street level (sunken freeways in a trench, y >= 300 down) keep their
    height where a street bridges over them: the lower road wins, because Driver 1's
    one-level road map would otherwise lift a car in the trench onto the bridge
    (C16). The bridge street gets a stepped ramp (<= RAMP_STEP per cell) down into
    the trench and up again on the other side, along its own road cells. Cells with
    a raised deck as well (3 levels) and sea-fixed river-bank cells are left alone."""
    seafix = sea_fixed_cells(world)
    sunken, bridges = {}, []
    for k, lv in grid.items():
        if k in seafix or choice[k][1] in (6, 9) or kinds.get(k) == "inside":
            continue
        land = [(y, t) for y, t in lv if t not in (6, 9)]
        st = [(y, t) for y, t in land if -300 < y < 300]
        lo = [(y, t) for y, t in land if y >= 300]
        hi = [(y, t) for y, t in land if y <= -300]
        if st and lo and not hi:
            sunken[k] = min(lo)                # the shallowest sunken level
            if any(t not in GROUND_TYPES and t < 0x4000 for _, t in st):
                bridges.append(k)              # a real road above: ramp its approaches
    road = lambda k: (k in choice and choice[k][1] not in (6, 9) and abs(choice[k][0]) < 300
                      and choice[k][1] not in GROUND_TYPES and choice[k][1] < 0x4000)
    ramp = {}
    for k in bridges:
        depth = sunken[k][0]
        n = max(1, -(-depth // RAMP_STEP) - 1) if RAMP_STEP > 0 else 0   # ramp cells per side (0: plain drop)
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for i in range(1, n + 1):
                c = (k[0] + d[0] * i, k[1] + d[1] * i)
                if c in sunken or not road(c):
                    break
                h = depth * (n + 1 - i) // (n + 1)
                ramp[c] = max(ramp.get(c, 0), h)
    side = {}                                  # kerbs / grass beside a ramp follow it: a car
    for c, h in ramp.items():                  # hugging the road's edge must not be lifted
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (c[0] + d[0], c[1] + d[1])
            if n in ramp or n in sunken or n not in choice:
                continue
            y, t = choice[n]
            if t not in (6, 9) and abs(y) < 300 and (t in GROUND_TYPES or t >= 0x4000):
                side[n] = max(side.get(n, 0), h)
    ramp.update(side)
    for k, lv in sunken.items():
        choice[k] = lv
    for k, h in ramp.items():
        choice[k] = (h, choice[k][1])
    walltop = {}                               # ground on top of a trench wall follows the trench:
    if WALLTOP:                                # a car hugging the wall must not be lifted (its centre
        for k, (y, t) in choice.items():       # crosses the cell border before the wall box stops it)
            if y < 300 or t in (6, 9):
                continue
            for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (k[0] + d[0], k[1] + d[1])
                if n in choice and n not in seafix and kinds.get(n) != "inside":
                    ny, nt = choice[n]
                    if nt not in (6, 9) and abs(ny) < 300 and (nt in GROUND_TYPES or nt >= 0x4000):
                        walltop[n] = max(walltop.get(n, 0), y)
        for k, y in walltop.items():
            choice[k] = (y, choice[k][1])
    snap = {}                                  # median kerbs in the trench (1329 next to lanes at
    if MEDIAN_SNAP:                            # 1352): a cell within MEDIAN_SNAP above a neighbour
        for k, (y, t) in choice.items():       # takes the neighbour's (lower) level
            if t in (6, 9) or abs(y) < HEIGHT_DEADBAND:
                continue
            best = y
            for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = choice.get((k[0] + d[0], k[1] + d[1]))
                if n and n[1] not in (6, 9) and 0 < n[0] - y <= MEDIAN_SNAP:
                    best = max(best, n[0])
            if best != y:
                snap[k] = (best, t)
        choice.update(snap)
    print("road map: %d cells snapped to a lower neighbour within %d (medians)" % (len(snap), MEDIAN_SNAP))
    print("road map: %d sunken cells keep the lower level (%d under a bridging road), %d ramp cells (%d beside the road), %d wall-top cells"
          % (len(sunken), len(bridges), len(ramp), len(side), len(walltop)))


SURF = "no_surf" not in EXPERIMENT


def written_height(gy):
    """The height a cell's road-map word carries for ground y `gy` (deadband, 8-unit steps)."""
    if abs(gy) < HEIGHT_DEADBAND:
        gy = 0
    return ((gy & 0xFFF8) ^ 0x8000) - 0x8000


def plain_model_ids(models_lump: bytes, limit=900):
    """Model indices below `limit` whose flags carry neither water bit (flags 0x80,
    flags2 0x4000): usable as ROADSURF surface ids (the road map's type field is
    both; the engine reads the model's flags for water/waves)."""
    n, = struct.unpack_from("<i", models_lump, 0)
    p, ids = 4, []
    for i in range(min(n, limit)):
        size, = struct.unpack_from("<i", models_lump, p)
        if size >= 4:
            f1, f2 = struct.unpack_from("<2H", models_lump, p + 4)
            if not (f1 & 0x80) and not (f2 & 0x4000) and i not in (GRASS_ID, WATER_MODEL):
                ids.append(i)
        p += 4 + size
    return ids


def cell_slopes(world, cells, choice):
    """Sloped cells among `cells`: {cell: (gx, gz)} = ground y (down) change per unit
    along +x / +z (Driver 1 world axes), from Driver 2 surface samples 600 units off
    the centre; only where the four samples lie on one plane (not a step)."""
    from d2surface import Surface
    surf = Surface("work/d2_CHICAGO.LEV")
    half_x, half_z = world["across"] // 2 * CELL, world["down"] // 2 * CELL
    out = {}
    for (col, row) in cells:
        gy0 = choice[(col, row)][0]
        x0, z0 = col * ROAD_UNIT - half_x, half_z - row * ROAD_UNIT
        s = []
        for ox, oz in ((300, 0), (-300, 0), (0, 300), (0, -300)):
            dx, dz = ws.to_d2(x0 + ox, z0 + oz)
            lv = [int(round(-h * ws.SCALE)) for h, t in surf.levels(dx, dz) if t not in (6, 9)]
            lv = [y for y in lv if abs(y - gy0) < 450]
            s.append(min(lv, key=lambda y: abs(y - gy0)) if lv else None)
        g = []
        for p, m in ((s[0], s[1]), (s[2], s[3])):     # per axis: both samples on one plane through the centre
            ok = p is not None and m is not None and abs(p + m - 2 * gy0) <= 40
            g.append((p - m) / 600.0 if ok else 0.0)
        gx, gz = g
        if max(abs(gx), abs(gz)) * ROAD_UNIT >= SLOPE_MIN:
            out[(col, row)] = (gx, gz)
    return out


def surface_planes(world, grid, choice, kinds):
    """ROADSURF planes per cell, relative to the cell's written height: the cell's
    own level (sloped where the D2 surface slopes) plus every level of its own or
    its 4 neighbours that lies SURF_SEP or more away (deck over street, trench under
    a bridge, ground on a trench wall, lane beside a ramp): with the engine patch the
    wheel takes the plane nearest its height, so cars above and below both keep
    their road. Lowest plane first (an unpatched engine takes the first hit).
    Returns {cell: [(a, c, d), ...]} with d in y-down units."""
    land = {k: v for k, v in choice.items() if v[1] not in (6, 9) and kinds.get(k) != "inside"}
    hw = {k: written_height(v[0]) for k, v in land.items()}
    cand = set()
    for k, h in hw.items():
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            hn = hw.get((k[0] + d[0], k[1] + d[1]))
            if hn is not None and 40 <= abs(hn - h) < 450:
                cand.add(k)
    slopes = cell_slopes(world, cand, choice)
    planes, nmulti = {}, 0
    for k, h in hw.items():
        levels = {written_height(y) for y, t in grid[k] if t not in (6, 9)}
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (k[0] + d[0], k[1] + d[1])
            if n in land:
                levels |= {written_height(y) for y, t in grid[n] if t not in (6, 9)}
                levels.add(hw[n])
        ds = [0]
        for L in sorted(levels, reverse=True):               # lowest (largest y-down) first
            dd = L - h
            if abs(dd) >= SURF_SEP and all(abs(dd - e) >= SURF_SEP for e in ds):
                ds.append(dd)
        gx, gz = slopes.get(k, (0.0, 0.0))
        if len(ds) == 1 and (gx, gz) == (0.0, 0.0):
            continue
        ds.sort(reverse=True)
        pl = []
        for dd in ds:
            if dd == 0:
                a = int(round(-gx * 4096 / SURF_Q)) * SURF_Q * SLOPE_SIGN[0]
                c = int(round(-gz * 4096 / SURF_Q)) * SURF_Q * SLOPE_SIGN[1]
                pl.append((a, c, 0))
            else:
                pl.append((0, 0, int(round(dd / SURF_Q)) * SURF_Q))
        planes[k] = pl
        nmulti += len(ds) > 1
    print("road map: ROADSURF planes on %d cells (%d with several levels, %d sloped of %d candidates)"
          % (len(planes), nmulti, len(slopes), len(cand)))
    return planes


def roadsurf_lump(planes, ids):
    """Driver 1 ROADSURF lump (int count; SURFACEINFO {type, info, heading, numpolys}
    + SIPOLY 52 B {xz[4] int pairs, plane a b c d, nverts, pad}) with one surface per
    distinct plane list; info = 1 marks them for the height-aware engine patch.
    Returns (bytes, {cell: type id}). Plane (a, b, c) is the unit normal x 4096."""
    import collections, math
    groups = collections.Counter(tuple(p) for p in planes.values())
    cap = min(SURF_MAX, len(ids))
    if len(groups) > cap:
        print("road map: %d distinct surfaces, keeping the %d most used" % (len(groups), cap))
    keep = [g for g, _ in groups.most_common(cap)]
    sid = {g: ids[i] for i, g in enumerate(keep)}
    out = bytearray(struct.pack("<i", len(keep)))
    for g in keep:
        out += struct.pack("<4h", sid[g], 1, 0, len(g))
        for a, c, d in g:
            n = math.sqrt(a * a + 4096.0 * 4096.0 + c * c)
            out += struct.pack("<8i", -750, -750, -750, 750, 750, 750, 750, -750)
            out += struct.pack("<4i", int(round(a * 4096 / n)), int(round(4096 * 4096 / n)), int(round(c * 4096 / n)), d)
            out += struct.pack("<hxx", 4)
    cells = {k: sid[tuple(p)] for k, p in planes.items() if tuple(p) in sid}
    return bytes(out), cells


def road_values(world):
    """Driver 1 road map (roadh) from Driver 2's surface (d2surface.py): per
    1500-unit cell a u32 (rotation << 30 | bits 26-29 | surface id << 16 |
    height). Surface id 0 / a model without a ROADSURF shape = flat ground at
    y = -height (0x8001F3A8); water = WATER_MODEL (flags2 0x4000: waves, sinking).
    Driver 1 has one level per cell (0x8001F274: first shape polygon containing
    the point wins), so of several Driver 2 levels the one nearest street level
    is used, and raised decks that continue over streets (freeway overpasses,
    their ramps) are flattened to street level: otherwise the car drives off
    the deck's end where the street below takes over and falls (Game Over)."""
    grid = road_levels(world)
    kinds = sea_kinds(world["across"], world["down"])
    wheights = water_heights(world["across"], world["down"])
    choice = {}
    for k, lv in grid.items():
        lv = sorted(lv, key=lambda hl: (hl[1] in (6, 9), abs(hl[0])))
        choice[k] = lv[0]
        if kinds.get(k) == "inside":           # building block: plain ground, no drowning
            choice[k] = (0, 0)
    if "no_trench" not in EXPERIMENT:
        trench_rule(world, grid, choice, kinds)
    raised = {k for k, (gy, t) in choice.items() if t not in (6, 9) and gy <= -HEIGHT_DEADBAND}
    under = {k for k, lv in grid.items() if k not in raised and choice[k][1] not in (6, 9)
             and any(t not in (6, 9) and gy <= -DECK_HEIGHT for gy, t in lv)}
    seen, flat = set(), 0
    for k in raised:
        if k in seen:
            continue
        comp, todo = [], [k]
        seen.add(k)
        while todo:
            c = todo.pop()
            comp.append(c)
            for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (c[0] + d[0], c[1] + d[1])
                if n in raised and n not in seen:
                    seen.add(n); todo.append(n)
        touches = any((c[0] + i, c[1] + j) in under for c in comp for i in (-1, 0, 1) for j in (-1, 0, 1))
        if touches and "keep_decks" not in EXPERIMENT and not SURF:
            for c in comp:
                choice[c] = (0, choice[c][1])
            flat += len(comp)
    print("road map: %d raised cells, %d flattened (decks over streets), %d under decks"
          % (len(raised), flat, len(under)))
    surf_ids, world["roadsurf"] = {}, struct.pack("<i", 0)
    if SURF:
        planes = surface_planes(world, grid, choice, kinds)
        world["roadsurf"], surf_ids = roadsurf_lump(planes, world["plain_ids"])
    out = {}
    for rz in range(world["rz_n"]):
        for rx in range(world["rx_n"]):
            vals = []
            for a in range(60):
                for b in range(60):
                    # a region's block holds its 60 x 60 cells with row 0 at its top (max z)
                    cell = (rx * 60 + b, (world["rz_n"] - 1 - rz) * 60 + a)
                    gy, t = choice[cell]
                    sid = surf_ids.get(cell, GRASS_ID if t in ROAD_TYPES_GRASS else 0)
                    if abs(gy) < HEIGHT_DEADBAND:                # kerbs / raised grass: street level
                        gy = 0
                    low = gy & 0xFFF8
                    if t in (6, 9) and "no_water" not in EXPERIMENT and "water_nocells" not in EXPERIMENT:
                        wy = wheights.get((rx * 60 + b, (world["rz_n"] - 1 - rz) * 60 + a), WATER_Y)
                        sid, low = WATER_MODEL, wy & 0xFFF8          # water surface: waves, sinking
                        vals.append(ROAD_TOP | (sid << 16) | (low & 0xFFFF) | WATER_FLAG)
                        continue
                    vals.append(ROAD_TOP | (sid << 16) | (low & 0xFFFF) | ROAD_FLAG)
            out[(rx, rz)] = vals
    return out


def rle_roadh(vals):
    runs, k = bytearray(), 0
    while k < len(vals):
        j = k
        while j < len(vals) and vals[j] == vals[k]:
            j += 1
        runs += struct.pack("<II", j - k, vals[k])
        k = j
    return bytes(runs)
PVS_BUFFER = 32768        # empty PVS (4 KB) + road ids (7.2 KB) + road values (14.4 KB) + slack
FLAT_GROUND = int(next((e[7:] for e in EXPERIMENT if e.startswith("ground=")), "0"), 0)


def spoolinfo_lump(base_sp_raw: bytes, base_sp: SpoolInfo, world, areas, slots, objs, offsets, records, model_buf):
    # keep the base city's music/ambient header block verbatim
    music_sz = struct.unpack_from("<i", base_sp_raw, 4)[0]
    out = bytearray(struct.pack("<ii", model_buf, music_sz))
    out += base_sp_raw[8: 8 + music_sz]
    num_areas = max(world["used_areas"]) + 1
    out += struct.pack("<i", num_areas)
    tp = bytearray()
    for a in range(num_areas):
        if a in areas:
            gfx, moff, msize, ntp = areas[a]
            out += struct.pack("<4H8B", gfx, moff, 0, 0, msize, 0, ntp, 0, 0, 0, 0, 0)
            pages = [] if "no_area_tex" in EXPERIMENT else world["res"].area_pages.get(a, [])
            tp += bytes(pages) + b"\xff" * (16 - len(pages))
        else:
            out += bytes(16)
            tp += b"\xff" * 16
    out += tp
    # The per-barrel "PVS" buffer also receives the region's road data (roadm +
    # unpacked roadh = 3600 x (2 + 4) bytes), so it must be far bigger than our
    # empty PVS block (LA uses ~45 KB per barrel).
    out += struct.pack("<4i", *slots) + struct.pack("<4i", *objs) + struct.pack("<4i", *([PVS_BUFFER] * 4))
    out += struct.pack("<i", len(offsets)) + struct.pack("<%dH" % len(offsets), *offsets)
    out += struct.pack("<i", len(records)) + records
    return bytes(out)


def map_lump(world, total_cell_data, chi_hdr: MapHeader, base_hdr: MapHeader):
    head = struct.pack("<8i3i", world["across"], world["down"], CELL, world["rx_n"] * world["rz_n"],
                       REGION_CELLS, len(world["obj_list"]), total_cell_data,
                       base_hdr.ambient_light_level, *base_hdr.light_source)
    body = struct.pack("<i", len(world["straddlers"]))
    body += b"".join(cell_object(world["obj_list"][k]) for k in world["straddlers"])
    return head + body


# ---------------------------------------------------------------------------

def convert(out_path: str):
    chi = Lev.parse(open("work/d2_CHICAGO.LEV", "rb").read())
    base = Lev.parse(open("work/d1_LA.lev", "rb").read())
    cmem0, _ = inmem_models(chi)
    models0 = {**area_models(chi), **cmem0}
    world = build_world(chi, models0, set(cmem0), base)
    # LOD targets (near DETAIL_* road pieces, far LOW_* lights) are never placed
    # in cells, only swapped in by distance (L_LOD), so they inherit the areas
    # of the model they replace; otherwise textures only they use (the curve /
    # junction detail texture) are left out of every area's pages.
    lod = chi.inmem.get(L_LOD).data
    nlod = len(lod) // 4
    lodt = struct.unpack_from("<%dH" % (2 * nlod), lod)
    for i in range(nlod):
        for tgt in (lodt[i], lodt[nlod + i]):
            if tgt != 0xFFFF and tgt != i and world["model_vis"].get(i):
                world["model_vis"][tgt] |= world["model_vis"][i]
                world["model_near"][tgt] |= world["model_near"][i]
    print("area model sets (D1 visibility):", {a: len(v) for a, v in world["area_model_ids"].items()})
    res = repack(chi, base, world["model_vis"], None if "no_near" in EXPERIMENT else world["model_near"])
    print("\n".join(res.report))

    # special (car) pages: renumber right after the repacked pages, keep content
    from texpages import read_pages
    bti, _ = read_pages(base)
    bnames = base.loadtime.get(5).data
    res.special_details = {}
    special_new = {}
    nxt = max(res.pages) + 1
    for old, _blob in res.special:
        special_new[old] = nxt
        res.special_details[old] = [(d[0], bnames[d[1]: bnames.index(b"\0", d[1])], *d[2:])
                                    for d in bti.details[old]]
        for k, d in enumerate(bti.details[old]):
            w, h = d[4] or 256, d[5] or 256
            res.remap[("B", old, k)] = (nxt, k, d[2], d[3], d[2], d[3], w, h, w, h)
        nxt += 1

    texnames, texinfo, tpages, num_pages = texture_lumps(res, special_new)

    models_lump, names_lump, lod_lump, area_data, count, cmem, carea = build_models(chi, base, res)
    fallback = res.remap[next(iter(res.remap))]
    subdiv_lump = remap_subdivision(ws.scale_subdivision(chi.inmem.get(L_SUBDIV).data, subdiv_textures(cmem, carea)),
                                    cmem0, models0, res.remap, fallback)
    water_sub = b""
    if "no_water" not in EXPERIMENT:
        wdata, water_sub = water_model(base, res, fallback, len(subdiv_lump))
        models_lump = replace_model(models_lump, WATER_MODEL, wdata)
    all_models = {**carea, **cmem}

    world["res"] = res
    world["inmem_ids"] = set(cmem)
    hist = collections.Counter(world["radii"].flatten().tolist())
    print("view radius per cell:", dict(sorted(hist.items())))
    world["plain_ids"] = plain_model_ids(models_lump)
    world["road_values"] = road_values(world)
    vals = [v for vs in world["road_values"].values() for v in vs]
    hs = collections.Counter((((v & 0xFFF8) ^ 0x8000) - 0x8000) // 500 * 500 for v in vals)
    print("road map: %d cells, grass %d, heights (500-unit bins): %s" % (
        len(vals), sum(1 for v in vals if (v >> 16) & 0x3FF == GRASS_ID), sorted(hs.items())))
    spooled, areas, slots, objs, offsets, records, total_cd = build_spooled(world, area_data, res, chi)
    # The model spool buffer also stages area texture pages (34 KB each) at an
    # offset inside it, so it must be at least as big as the base city's.
    base_model_buf = struct.unpack_from("<i", base.inmem.get(L_SPOOL).data, 0)[0]
    model_buf = max(max(a[2] for a in areas.values()), base_model_buf)

    base_sp_raw = base.inmem.get(L_SPOOL).data
    spool = spoolinfo_lump(base_sp_raw, SpoolInfo.parse(base_sp_raw), world, areas, slots, objs, offsets, records, model_buf)
    mapl = map_lump(world, total_cd, MapHeader.parse(chi.loadtime.get(L_MAP).data), MapHeader.parse(base.loadtime.get(L_MAP).data))

    # car models: base city's, with texture pages remapped
    fallback = res.remap[next(iter(res.remap))]
    cm = bytearray(base.loadtime.get(L_CARMODELS).data)
    ents = [struct.unpack_from("<3i", cm, 4 + 12 * i) for i in range(13)]
    cbase = 4 + 12 * 13
    for e in ents:
        for off in e:
            if off == -1:
                continue
            size = struct.unpack_from("<i", cm, cbase + off)[0]
            a = cbase + off + 4
            cm[a: a + size] = remap_polys(bytes(cm[a: a + size]), "B", res.remap, fallback)
    # palettes: base city's, tpage field remapped for renumbered pages
    pal = bytearray(base.loadtime.get(L_PALLET).data)
    total = struct.unpack_from("<i", pal, 0)[0]
    p = 4
    for _ in range(total):
        palette, texnum, tpage = struct.unpack_from("<3i", pal, p)
        if palette == -1:
            break
        r = res.remap.get(("B", tpage, texnum))
        if r:
            struct.pack_into("<3i", pal, p, palette, r[1], r[0])
        p += 12 + 32

    rw, rh = world["across"] * CELL // ROAD_UNIT, world["down"] * CELL // ROAD_UNIT
    load = LumpList(kind=35, d1=True, lumps=[
        Lump(L_TEXNAMES, texnames),
        Lump(L_TEXINFO, texinfo),
        Lump(L_MODELNAMES, names_lump),
        Lump(L_ROADMAP, struct.pack("<ii", rw, rh)),
        Lump(L_PALLET, bytes(pal)),
        Lump(L_MAP, mapl),
        *[Lump(l.type, l.data) for l in base.loadtime.find(L_MOCAP)],
        Lump(L_CARMODELS, bytes(cm)),
    ])
    inmem = LumpList(kind=36, d1=True, lumps=[
        Lump(L_MODELS, models_lump),
        Lump(L_SPOOL, spool),
        Lump(L_ROADS, struct.pack("<i", 0)),
        Lump(L_JUNCS, struct.pack("<i", 0)),
        Lump(L_ROADBOUNDS, struct.pack("<i", 0)),
        Lump(L_JUNCBOUNDS, struct.pack("<i", 0)),
        # far ground tiles index this table from model +0x2C (d1models.py)
        Lump(L_SUBDIV, subdiv_lump + water_sub),
        Lump(L_ROADSURF, world["roadsurf"]),
        Lump(L_OVERLAY, base.inmem.get(L_OVERLAY).data),
        Lump(L_CHAIR, base.inmem.get(L_CHAIR).data),
        Lump(L_LOD, lod_lump),
    ])
    lev = Lev(d1=True, loadtime=load, tpages=tpages, inmem=inmem, spooled=spooled)
    out = lev.build(keep_layout=False)
    tmp = out_path + ".tmp"                 # atomic: test copies must never see a half-written level
    open(tmp, "wb").write(out)
    os.replace(tmp, out_path)
    print("wrote %s: %d bytes; models %d, objects %d (straddlers %d), regions %d, areas %d, pages %d"
          % (out_path, len(out), count, len(world["obj_list"]), len(world["straddlers"]),
             sum(1 for o in offsets if o != 0xFFFF), len(areas), num_pages))


if __name__ == "__main__":
    convert(sys.argv[1] if len(sys.argv) > 1 else "work/chicago_d1.lev")
