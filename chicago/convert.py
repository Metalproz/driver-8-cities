"""convert.py — build a Driver 1 LEV of Driver 2's Chicago (stage A, v0).

Inputs (Option A: read from the player's discs via inputs.py): Driver 2 CHICAGO.LEV (world) and Driver 1 LA.LEV (the replaced city,
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
from d1models import convert_models, near_vertex_count
import inputs
import pvs
import worldscale as ws
from cityprofile import P as CITY   # M3: per-city profile (CHI_CITY, default Chicago)
from d2cells import CellObject

# D1 lump ids
L_TEXNAMES, L_MODELS, L_MAP, L_ROADMAP, L_ROADS, L_JUNCS, L_ROADSURF = 5, 1, 2, 7, 8, 9, 10
L_MODELNAMES, L_ROADBOUNDS, L_JUNCBOUNDS, L_SUBDIV, L_LOD, L_MOCAP = 12, 16, 17, 20, 21, 22
L_OVERLAY, L_PALLET, L_SPOOL, L_CARMODELS, L_CHAIR, L_TEXINFO = 24, 25, 26, 28, 33, 34

CELL = 3000
EXPERIMENT = set(os.environ.get('CHI_EXPERIMENT', '').split(','))
D2_LEV = inputs.d2_lev()   # Option A: CHI_D2_LEV = day (default) / night / a path; read from the player's discs (inputs.py)
# Car set (car models, car palettes, car texture pages, police car) by D2 city and time of day
# (user R19, 13.10.: Chicago by day takes Miami's day-designed cars, by night LA's); CHI_CARS
# overrides (la, miami, sf, ny). C42 (Driver 2's own cars) can add its set here.
CAR_SET_LEVS = {"la": "d1_LA.lev", "miami": "d1_MIAMI.lev", "sf": "d1_FRISCO.lev",     # inputs.py names
                "ny": "d1_NEWYORK.lev"}
CAR_SETS = {(CITY.name, k): v for k, v in CITY.car_sets.items()}   # M3: from the city profile


def car_set() -> str:
    if os.environ.get("CHI_POLISH_D2CARS") == "1":     # Polish C42: Driver 2's own cars (polish_cars.py)
        return "d2"
    if os.environ.get("CHI_CARS"):
        return os.environ["CHI_CARS"]
    day = CITY.is_day_lev(D2_LEV)
    return CAR_SETS.get((CITY.name, "day" if day else "night"), "la")
ROADS = os.environ.get("CHI_ROADS") == "1"   # D1 road network for traffic (d1roads.py; Stage B, 2026-10-13)   # D2 source city (night Chicago: work/d2_CHICAGO_night.lev)
CAR_PALETTE_ENTRIES = {}   # set where the PALLET lump is built
CLUT_BASE_POS = int(os.environ.get("CHI_CLUT_BASE", "38"))   # CLUT positions taken before the pages palettes (Infrastructure; calibrate)
BIG_OBJECT = 3000      # bounding radius above which an object spans cells
BIG_TILE = int(os.environ.get("CHI_BIG_TILE", "3000"))   # same for ground tiles (tried 1500
                       # for the ground holes: no visible change, 9x the straddlers)
NEAR_CELLS = 2         # cells around a region whose models count as seen up close
AREA_BAND_LOW = 13        # area switch threshold (exe_patches.AREA_SWITCH_CODE): cells < 13 / > 17
SWITCH_LAG = int(os.environ.get("CHI_SWITCH_LAG", "0"))           # cells the car may cross while an area loads (no new switch meanwhile)
AREA_TEXTURE_LIMIT = int(os.environ.get("CHI_AREA_TEX", str(CITY.area_tex_limit)))   # textures one area may need (13 VRAM pages x 32 palettes, minus permanent + packing slack)
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
            if r is None:                    # (Polish S1 second pass: global textures stay as they are)
                q += POLY_SIZES[t]
                continue
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
HIDDEN_ENGINE_MODELS = set(CITY.hidden_engine_models)
# C45 (Infrastructure 16.10.): header byte +6 = vertices of always-plain polygons (d1models.near_vertex_count); without
# it near objects draw those polygons from stale screen points (the quay's dark beams). CHI_TRI_VERTS=0 = old output,
# plain = only always-plain polygons counted (exe without C67).
# C70 (Infrastructure 16.10.): quay walls that hang from street level down to the water (or below it) were drawn over
# the road at the car: Driver 1 sorts every polygon of a "sorted" model by its own depth, and a wall piece's average
# depth can be nearer than the big road tile pieces in front of it. Such low walls (every placement: top at most
# LOW_WALL_TOP above the street, bottom at least LOW_WALL_BOTTOM below it; plus SHOREWALL) lose the sorted flag of their
# group table for their polygons wholly below the street (those groups come first, unsorted: object depth), so they
# are drawn behind the road; parapets and railings above the street stay sorted. CHI_LOW_WALLS=0 = old output.
LOW_WALLS = os.environ.get("CHI_LOW_WALLS", "1") != "0"
LOW_WALL_TOP, LOW_WALL_BOTTOM = 400, 850
LOW_WALL_IDS = {}                    # id -> below-street model y; filled by convert() before build_models


def low_wall_models(obj_list, models: dict, world=None) -> dict:
    yr = {}
    for mid, d in models.items():
        m = Model.parse(mid, d)
        if m.vertices <= 0 or m.num_vertices <= 0 or m.vertices + 8 * m.num_vertices > len(d):
            continue
        ys = [struct.unpack_from("<3h", d, m.vertices + 8 * i)[1] for i in range(m.num_vertices)]
        yr[mid] = (min(ys), max(ys))
    for mid, d in models.items():                    # instances: the source's vertices
        m = Model.parse(mid, d)
        if mid not in yr and m.instance_number >= 0 and m.instance_number in yr:
            yr[mid] = yr[m.instance_number]
    ok, bad, top = set(), set(), {}
    for o in obj_list:
        r = yr.get(o.model)
        if r is None or r[1] - r[0] <= 300:
            continue
        (ok if o.y + r[0] >= -LOW_WALL_TOP and o.y + r[1] >= LOW_WALL_BOTTOM else bad).add(o.model)
        top[o.model] = min(top.get(o.model, o.y), o.y)
    # C70 round 3 (16.10.): only the UNDERGROUND faces go to the object-depth groups: a polygon wholly below the
    # street (50 units under it at every placement) whose visible side (-normal, d1models.plane: drawn while
    # n . camera < d) looks at land (no sea_kinds water cell 400 units in front of it) at most placements. The faces
    # that look at the water stay depth-sorted (round 2 sent them all to object depth: the river side of the quay
    # walls was then hidden by the water tiles).
    import d1models
    kinds = sea_kinds(world["across"], world["down"])
    half_x, half_z = world["across"] // 2 * CELL, world["down"] // 2 * CELL
    places = {}
    for o in obj_list:
        if o.model in ok - bad:
            places.setdefault(o.model, []).append(o)
    out = {}
    for mid in ok - bad:
        d = models[mid]
        m = Model.parse(mid, d)
        if m.num_polys == 0 or m.poly_block >= len(d):
            continue
        verts = d1models.vertices(m)
        polys = d1models.split_polys(m)
        lim = -top[mid] + 50
        under = set()
        for i, pb in enumerate(polys):
            t = pb[0] & 31
            if t not in d1models.VERT_OFF:
                continue
            n = 4 if t in (9, 11, 21) else 3
            idx = [j for j in pb[d1models.VERT_OFF[t]: d1models.VERT_OFF[t] + n] if j < len(verts)]
            if not idx or any(verts[j][1] < lim for j in idx):
                continue
            nrm = d1models.poly_normal(pb, verts)
            if nrm is None or abs(nrm[1]) > 0.7:
                continue                                   # floors / roofs: not a wall face
            mx = sum(verts[j][0] for j in idx) / len(idx); mz = sum(verts[j][2] for j in idx) / len(idx)
            land = water = 0
            for o in places.get(mid, []):
                a = o.yang * 64 * 2 * math.pi / 4096; ca, sa = math.cos(a), math.sin(a)
                vx, vz = mx - 400 * nrm[0], mz - 400 * nrm[2]          # 400 units out on the visible side
                wx, wz = o.x + vx * ca + vz * sa, o.z - vx * sa + vz * ca
                col, row = int(round((wx + half_x) / ROAD_UNIT)), int(round((half_z - wz) / ROAD_UNIT))
                if kinds.get((col, row)) == "water":
                    water += 1
                else:
                    land += 1
            if land > water:
                under.add(i)
        if under:
            out[mid] = under
    return out


def unsorted_groups(d: bytes) -> bytes:
    """Clear the 'sorted' bit (31) of the first group entry (d1models.group_table)."""
    gt = struct.unpack_from("<I", d, 0x1C)[0]
    if gt <= 0 or gt + 8 > len(d):
        return d
    hdr = struct.unpack_from("<I", d, gt)[0]
    e = gt + 4 + (hdr >> 16)
    if e + 4 > len(d):
        return d
    b = bytearray(d)
    struct.pack_into("<I", b, e, struct.unpack_from("<I", b, e)[0] & 0x7FFFFFFF)
    return bytes(b)


TRI_VERTS = os.environ.get("CHI_TRI_VERTS", "plain") != "0"   # plain (default) / all (test) / 0 = old


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


QUAY_RAIL_SRC = CITY.quay_rail_src   # balustrade + wall-face models; their rail-only copies follow SHOREWALL


def quay_rail_index(chi: Lev) -> int:
    return far_water_index(chi) + FAR_WATER + SHORE_WALLS


def rail_only(data: bytes, cut: int = 60) -> bytes:
    """A converted model with every polygon that reaches more than `cut` below its origin collapsed to a point
    (same polygon count and group tables, nothing drawn): the balustrade of a quay wall without the wall face."""
    import d1models
    from models import Model, POLY_SIZES
    m = Model.parse(-1, data)
    vs = [struct.unpack_from("<3h", data, m.vertices + 8 * i) for i in range(m.num_vertices)]
    b = bytearray(data); q = m.poly_block
    for _ in range(m.num_polys):
        t = b[q] & 31
        off = d1models.VERT_OFF.get(t)
        if off is not None:
            nv = 4 if t in (9, 11, 21) else 3
            ids = [i for i in b[q + off:q + off + nv]]
            if ids and max(vs[i][1] for i in ids if i < len(vs)) > cut:
                for k in range(nv):
                    b[q + off + k] = ids[0]
        q += POLY_SIZES.get(t, 4)
    return bytes(b)


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
    for i, q in light_turns(chi, {**carea, **cmem}).items():
        if i in chi_all:
            chi_all[i] = turn_model(chi_all[i], q)
    import d1models
    d1models.BELOW_Y.clear()
    if LOW_WALLS:
        d1models.BELOW_Y.update(LOW_WALL_IDS)
    conv, stats = convert_models(chi_all)
    print("models: %(models)d converted (%(groups)d groups), %(tiles)d tiles kept, %(instances)d instances, "
          "%(deinstanced)d de-instanced" % stats)
    conv = fit_bounding_spheres(conv)
    # flags2 0x4000 is Driver 2's GRASS but Driver 1's WATER (waves, sinking: 0x8001F074,
    # 0x8001F410); a start among Chicago's grass tiles sank the car and ended the game
    conv = {i: d[:2] + struct.pack("<H", struct.unpack_from("<H", d, 2)[0] & ~0x4000) + d[4:] for i, d in conv.items()}
    # shape flag 0x0004 is Driver 1's "light" mark (set at load for the named light models,
    # 0x80052B38; objects of such models fill the 11-entry glow list 0x800A663C); Driver 2
    # models carry it for other reasons (21 in Chicago), which crowded the real lights out
    conv = {i: struct.pack("<H", struct.unpack_from("<H", d, 0)[0] & ~0x0004) + d[2:] for i, d in conv.items()}
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
    if TRI_VERTS:                                   # C45: plain polygons near the camera (d1models.near_vertex_count)
        conv = {i: near_vertex_count(d) for i, d in conv.items()}
        for i, d in list(conv.items()):             # instances without own polygons: the source's count
            inst = struct.unpack_from("<h", d, 4)[0]
            if inst >= 0 and inst != i and inst in conv and struct.unpack_from("<h", d, 14)[0] == 0:
                conv[i] = d[:6] + conv[inst][6:7] + d[7:]
    if LOW_WALLS and LOW_WALL_IDS:                  # C70: (d1models.BELOW_Y) below-street parts of low quay walls unsorted
        print("low walls (below-street polygons at object depth):", len(LOW_WALL_IDS), sorted(LOW_WALL_IDS)[:20])
    if STREAM_INMEM and STREAM_KEEP:              # Q36 B: the moved in-memory models are streamed per area
        moved = set(cmem) - STREAM_KEEP
        data = {i: conv[i] for i in cmem if i not in moved}
        area_data = {i: conv[i] for i in carea if i not in cmem}
        area_data.update({i: conv[i] for i in moved})
        cmem = {i: m for i, m in cmem.items() if i not in moved}
    else:
        data = {i: conv[i] for i in cmem}               # index -> bytes (in-memory models)
        area_data = {i: conv[i] for i in carea if i not in cmem}   # area-spooled models

    names = list(cnames)
    for k, n in enumerate(names):
        if n in LIGHT_RENAME and "keep_lightmodels" not in EXPERIMENT:
            names[k] = LIGHT_RENAME[n]
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
        if SKY_SUBDIV:
            data[i] = sky_subdivide(data[i], i)
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
        if TRI_VERTS:
            data[len(names) - 1] = near_vertex_count(data[len(names) - 1])
    if SHORE_WALLS:
        assert len(names) == far_water_index(chi) + FAR_WATER
        names.append("SHOREWALL")
        data[len(names) - 1] = shore_wall_model(res, fallback)
        if TRI_VERTS:
            data[len(names) - 1] = near_vertex_count(data[len(names) - 1])
        if LOW_WALLS:
            data[len(names) - 1] = unsorted_groups(data[len(names) - 1])
    if QUAY_FILL:
        assert len(names) == quay_rail_index(chi), (len(names), quay_rail_index(chi))
        for m in QUAY_RAIL_SRC:                     # C70 r2: balustrade-only copies of the quay walls
            names.append("QRAIL%d" % m)
            data[len(names) - 1] = rail_only(data[m])
        for m in QUAY_DROP:                         # C70 r3: invisible copies that keep the collision boxes
            names.append("QGHOST%d" % m)
            data[len(names) - 1] = rail_only(data[m], cut=-100000)
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

STREAM_INMEM = os.environ.get("CHI_POLISH_STREAM_INMEM", "") == "1"
STREAM_MAX_AREAS = int(os.environ.get("CHI_POLISH_STREAM_MAXAREAS", "99"))   # models seen in more areas stay in memory
STREAM_KEEP = set()


def stream_keep(chi: Lev, cmem: dict, models_all: dict, world, lodt, nlod) -> set:
    """In-memory models that must stay resident (Q36 B): ground tiles (SUBDIVISION UVs), LOD targets, the base city's
    sky slots, light models (named, glow list at load), the water model, models never placed (events may use them),
    models seen in more than STREAM_MAX_AREAS areas, and instance sources of every kept model."""
    names = model_names(chi)
    keep = set()
    lod_targets = {t for i in range(nlod) for t in (lodt[i], lodt[nlod + i]) if t != 0xFFFF and t != i}
    lights = set(light_turns(chi, models_all)) | {i for i, n in enumerate(names) if n in LIGHT_RENAME}
    for i, m in cmem.items():
        vis = world["model_vis"].get(i, ())
        if (m.shape_flags & 0x2400 or i in lod_targets or i < SKY_SLOTS or i in lights or i == WATER_MODEL
                or not vis or len(vis) > STREAM_MAX_AREAS or (QUAY_FILL and i in tuple(QUAY_RAIL_SRC) + tuple(QUAY_DROP))):
            keep.add(i)                             # (quay models: their rail-only / ghost copies are built from them)
    todo = list(keep)
    while todo:
        src = models_all[todo.pop()].instance_number
        if src >= 0 and src in cmem and src not in keep:
            keep.add(src); todo.append(src)
    return keep


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
    # Driver 2 drew its river with flat street-level tiles in cells without a driving
    # surface; our water is drawn behind everything (Miami's sea flags), so they hid it
    kinds = sea_kinds(across, down) if "no_water" not in EXPERIMENT and "keep_rivertiles" not in EXPERIMENT else {}
    dropped = 0
    turns = light_turns(chi, models_all)
    for o in objects.values():
        x, z = ws.to_d1(o.x, o.z)
        m = models_all.get(o.model)
        if kinds and m is not None and m.shape_flags & 0x0400 and abs(ws.s(o.y)) < 200 and                 kinds.get(((x + half_x + ROAD_UNIT // 2) // ROAD_UNIT, (half_z - z + ROAD_UNIT // 2) // ROAD_UNIT)) == "water":
            # Polish R35 (bridge hole at quay_wall): keep tiles that stand on a real D2 surface (a quay path whose
            # road cell the overhead map paints as river); only tiles over D2's sea are river tiles
            if not (KEEP_SHORE_TILES and any(t not in (6, 9) for h, t in _d2surf().levels(o.x, o.z))):
                dropped += 1
                continue
        yang = (o.yang - turns[o.model]) & 63 if o.model in turns else o.yang
        obj_list.append(CellObject(x, ws.s(o.y), z, yang, o.model))
    if turns:
        print("light models turned a quarter (glow facing):", sorted(turns))
    if dropped:
        print("Driver 2 river tiles dropped:", dropped)
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
                    if inside_world(x, z, across, down):
                        wy = BASIN_Y if (cx, cz) in BASIN_CELLS else (max(near) if near else WATER_Y)
                        obj_list.append(CellObject(x, wy, z, 0, WATER_MODEL))
        print("water tiles:", len(wc))
        if FAR_WATER:
            fw = far_water_blocks(across, down)
            lift = int(os.environ.get("CHI_FAR_LIFT", "0"))     # test: raise the planes into view
            fw = [(x, y, z) for x, y, z in fw if inside_world(x - FAR_SIZE // 2, z - FAR_SIZE // 2, across, down)
                  and inside_world(x + FAR_SIZE // 2 - 1, z + FAR_SIZE // 2 - 1, across, down)]
            for x, y, z in fw:
                obj_list.append(CellObject(x, y - lift, z, 0, far_water_index(chi)))
            print("far water planes:", len(fw))
        if SHORE_WALLS:
            sw = [w for w in shore_walls(across, down) if inside_world(w[0], w[2], across, down)]
            for x, y, z, yang in sw:
                obj_list.append(CellObject(x, y, z, yang, far_water_index(chi) + FAR_WATER))
            print("shore walls:", len(sw))
    if QUAY_FILL:
        # Polish C70 r2 (user R31, quay_wall): the lower river-walk pieces under the quay (D2 models 1000, 1115,
        # 117/119/122 at y ~990) and our fillers go inside the boxes, and every 1500 tile there without water gets
        # a water tile at the river's level, so no empty / void spot shows. The balustrade 1114 stays.
        before = len(obj_list)
        _QUAY_GRID["g"] = road_levels(dict(across=across, down=down, rx_n=across // REGION_CELLS, rz_n=down // REGION_CELLS))
        sites = quay_sites()
        import math as _m
        _grid = {}
        for sx, sz in sites:
            _grid.setdefault((int(sx) // QUAY_SITE_R, int(sz) // QUAY_SITE_R), []).append((sx, sz))
        def inbox(x, z):
            gx, gz = int(x) // QUAY_SITE_R, int(z) // QUAY_SITE_R
            return any(_m.hypot(x - sx, z - sz) <= QUAY_SITE_R
                       for i in (-1, 0, 1) for j in (-1, 0, 1) for sx, sz in _grid.get((gx + i, gz + j), ()))
        filler = far_water_index(chi) + FAR_WATER if SHORE_WALLS else -1
        rails = {m: quay_rail_index(chi) + k for k, m in enumerate(QUAY_RAIL_SRC)}
        ghosts = {m: quay_rail_index(chi) + len(QUAY_RAIL_SRC) + k for k, m in enumerate(QUAY_DROP)}
        kept = []
        for o in obj_list:
            if inbox(o.x, o.z):
                if o.model == filler:
                    continue
                if o.model in (QUAY_GHOST or QUAY_DROP) and o.y > 600:   # keep the collision, hide the visuals (R31)
                    o = CellObject(o.x, o.y, o.z, o.yang, ghosts[o.model]); kept.append(o); continue
                if o.model in rails and QUAY_GHOST is None:
                    o = CellObject(o.x, o.y, o.z, o.yang, rails[o.model])
            kept.append(o)
        obj_list = kept
        boxes = [(int(sx), int(sz), QUAY_SITE_R) for sx, sz in sites]
        have = set()                                       # 1500 sub-cells already under a (3060-wide) water tile
        for o in obj_list:
            if o.model == WATER_MODEL:
                for dx in (-750, 750):
                    for dz in (-750, 750):
                        have.add(((o.x + dx) // 1500, (o.z + dz) // 1500))
        wgrid = {}
        for o in obj_list:
            if o.model == WATER_MODEL:
                wgrid.setdefault((o.x // 6000, o.z // 6000), []).append(o.y)
        def local_wy(x, z):                         # the nearest existing water tiles' level (river vs lake differ)
            ys = [y for i in (-1, 0, 1) for j in (-1, 0, 1) for y in wgrid.get((x // 6000 + i, z // 6000 + j), ())]
            return max(ys) if ys else WATER_Y
        wy = WATER_Y
        added = 0
        done_cells = set()
        for bx, bz, br in boxes:
            for x in range((bx - br) // 1500 * 1500 + 750, bx + br, 1500):
                for z in range((bz - br) // 1500 * 1500 + 750, bz + br, 1500):
                    if (x // 1500, z // 1500) in have or (x // 1500, z // 1500) in done_cells or not inbox(x, z)                             or not inside_world(x, z, across, down):
                        continue
                    done_cells.add((x // 1500, z // 1500))
                    col, row = (x + half_x + ROAD_UNIT // 2) // ROAD_UNIT, (half_z - z + ROAD_UNIT // 2) // ROAD_UNIT
                    if kinds and kinds.get((col, row)) is None and not _quay_low(col, row):
                        continue                    # real street / land cell: no water over it
                    obj_list.append(CellObject(x, local_wy(x, z), z, 0, WATER_MODEL)); added += 1
        print("quay fill: %d sites, %d objects changed / dropped, %d water tiles added (y %d)" % (len(sites), sum(1 for o in obj_list if o.model >= quay_rail_index(chi)), added, wy))
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
    region_d2area = dict(region_area)                # C42 r3 (c): Driver 2's own area per region (SpecialByRegion)

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
                if corridor_edges is not None:       # Polish C45: the neighbour the streets cross to most
                    nb, d = max(nbs, key=lambda e: corridor_edges.get(tuple(sorted(((rx, rz), (rx + dirs[e[1]][0], rz + dirs[e[1]][1])))), 0))
                connected[(rx, rz)] = [(nb, d), (a, opposite[d])]
            else:
                connected[(rx, rz)] = [(a, 0), (a, 2)] if (rx + rz) % 2 else [(a, 1), (a, 3)]
        if corridor_edges is not None:               # CHI_POLISH_CORRIDOR=1 (Polish, C45): load 30 cells earlier
            borders = {r for r, e in connected.items() if e[0][0] != e[1][0]}
            for (rx, rz), entries in list(connected.items()):
                (nb, d), (a, _back) = entries
                if nb == a:
                    continue
                dx, dz = dirs[d]
                w = corridor_edges.get(tuple(sorted(((rx, rz), (rx + dx, rz + dz)))), 0)
                prev = (rx - dx, rz - dz)
                if w >= polish_areas.CORRIDOR_MIN_EDGES and region_area.get(prev) == a and prev not in borders:
                    connected[prev] = [(nb, d), (a, opposite[d])]   # the border region becomes the corridor
        if polish_areas.pingpong_enabled():          # Polish C45: no edge switches back and forth
            polish_areas.fix_pingpong(connected, region_area, corridor_edges if corridor_edges is not None else street_edges)
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

    import polish_areas                              # CHI_POLISH_AREAS=1|2 (Polish, C45): areas along the streets
    street_edges = polish_areas.region_edges(D2_LEV, rx_n, rz_n, REGION_CELLS * CELL, half_x, half_z)[0]         if (polish_areas.enabled() or polish_areas.corridor()) else None
    corridor_edges = street_edges if polish_areas.corridor() else None
    if not polish_areas.enabled():
        street_edges = None
    if street_edges is not None and polish_areas.mode() == "2":
        region_area.update(polish_areas.agglomerate(sorted(region_area), lambda r: textures_of(region_seen.get(r, set())),
                                                    street_edges, polish_areas.LIMIT_SHARE * AREA_TEXTURE_LIMIT))
        print("areas: street-merged start layout, %d areas" % len(set(region_area.values())))
    over_ok = set()                                  # M3: single-region areas over the limit the profile accepts
    while True:
        connected = switch_entries()
        loadable = loadable_areas(connected)
        area_regions = collections.defaultdict(set)
        for reg, las in loadable.items():
            for la in las:
                area_regions[la].add(reg)
        counts = {a: len(textures_of(set().union(*(region_seen.get(r, set()) for r in area_regions[a]))))
                  for a in sorted(set(region_area.values()))}
        big = [(n, a) for a, n in counts.items() if n > AREA_TEXTURE_LIMIT and a not in over_ok]
        if not big:
            break
        _, a = max(big)
        regs = sorted(r for r, ra in region_area.items() if ra == a)
        if len(regs) < 2:
            if not CITY.area_single_over_ok:
                raise RuntimeError("area %d: one region already needs %d textures (loadable in %d regions; %.2f areas per region)" % (
                    a, counts[a], len(area_regions[a]), sum(map(len, loadable.values())) / len(loadable)))
            print("areas: area %d (one region) needs %d textures > %d: kept, the texture packer halves more there (M3 profile)"
                  % (a, counts[a], AREA_TEXTURE_LIMIT))
            over_ok.add(a)
            continue
        new_id = min(set(range(64)) - set(region_area.values()))
        moved = polish_areas.best_split(regs, street_edges) if street_edges is not None else None
        if not moved:
            xs = sorted(r[0] for r in regs)
            zs = sorted(r[1] for r in regs)
            axis = 0 if xs[-1] - xs[0] >= zs[-1] - zs[0] else 1
            mid = sorted(r[axis] for r in regs)[len(regs) // 2]
            moved = [r for r in regs if r[axis] >= mid]
            if len(moved) == len(regs):
                moved = regs[len(regs) // 2:]
        for r in moved:
            region_area[r] = new_id
    if street_edges is not None:
        print("areas: street edges crossing an area boundary: %d" % polish_areas.crossing_cost(region_area, street_edges))
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
                used_areas=used_areas, hdr2=hdr2, region_d2area=region_d2area, loadable=loadable,
                region_units=REGION_CELLS * CELL, half_x=half_x, half_z=half_z)


_d2_cache = {}


def d2_extract_cached():
    if "v" not in _d2_cache:
        _d2_cache["v"] = d2_extract(D2_LEV)
        if CITY.water_relocate:                    # M3 Rio: the water slot's own objects use the model's new index
            n = relocated_index()
            moved = 0
            for o in _d2_cache["v"][2].values():
                if o.model == WATER_MODEL:
                    o.model = n; moved += 1
            print("water slot: Driver 2 model %d -> %d (%d objects)" % (WATER_MODEL, n, moved))
    return _d2_cache["v"]


def relocated_index() -> int:
    """M3 (CityProfile.water_relocate): the new index of the Driver 2 model that held the water slot = the city's model
    count (it becomes the last Driver 2 model)."""
    return struct.unpack_from("<i", Lev.parse(open(D2_LEV, "rb").read()).inmem.get(L_MODELS).data, 0)[0]


def make_resident(chi: Lev, names):
    """M3 Vegas (vegas5, C132 c): the named Driver 2 AREA models get their data into the in-memory model lump (the area
    spool copies are then left out: build_models takes area models 'not in cmem'), so Driver 1 finds them by name at load."""
    allnames = model_names(chi)
    areas = area_models(chi)
    lump = chi.inmem.get(L_MODELS)
    raw = lump.data
    count = struct.unpack_from("<i", raw, 0)[0]
    want = {allnames.index(n): n for n in names if n in allnames}
    out, p = bytearray(raw[:4]), 4
    done = []
    for i in range(count):
        size = struct.unpack_from("<i", raw, p)[0]
        body = raw[p + 4: p + 4 + max(size, 0)]
        p += 4 + max(size, 0)
        if i in want and size <= 0 and i in areas:
            body = areas[i].data
            done.append(want[i])
        out += struct.pack("<i", len(body) if body else size) + body
    out += raw[p:]
    lump.data = bytes(out)
    print("resident models (in memory): %s" % done)


def relocate_water_slot(chi: Lev):
    """M3 Rio: no model slot < 900 is free (all placed, instance sources or LOD targets). The Driver 2 model at
    WATER_MODEL is appended as model `count` (its objects follow, d2_extract_cached) and its slot is left to the
    water tile, so no area model list writes over the water tile at run time (Havana hav6 lesson)."""
    k = WATER_MODEL
    lump = chi.inmem.get(L_MODELS)
    raw = lump.data
    count = struct.unpack_from("<i", raw, 0)[0]
    p, entry = 4, None
    for i in range(count):
        size = struct.unpack_from("<i", raw, p)[0]
        if i == k:
            entry = raw[p: p + 4 + max(size, 0)]
        p += 4 + max(size, 0)
    if not entry or struct.unpack_from("<i", entry, 0)[0] <= 0:
        raise RuntimeError("water_relocate: model %d is no in-memory model" % k)
    lump.data = struct.pack("<i", count + 1) + raw[4:p] + entry + raw[p:]
    nl = chi.loadtime.get(L_MODELNAMES)
    names = nl.data.split(b"\0")
    blob = b"\0".join(names[:count] + [names[k]]) + b"\0"
    nl.data = blob + bytes(-len(blob) % 4)
    ll = chi.inmem.get(L_LOD)
    nlod = len(ll.data) // 4
    t = list(struct.unpack_from("<%dH" % (2 * nlod), ll.data))
    a, b = t[:nlod], t[nlod:]
    a.append(count if a[k] == k else a[k]); b.append(count if b[k] == k else b[k])
    ll.data = struct.pack("<%dH" % (2 * len(a)), *(a + b))
    return count


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


# Traffic light glows (Infrastructure 2026-10-13): Driver 1 draws them on models found by NAME
# (CITY 3 = LA's table: TLIGHT00 kind 0, TLIGHT01 kind 1, SLIGHT01 kind 3) at offsets that
# assume the signal faces -z (LA's lights; 0x80053764 / 0x8004343C pick the glow's visibility
# and the NS/WE state from the object's yang). D2's TLIGHT01 faces -x, so it (and the
# instances that borrow its vertices) is turned a quarter (model' = R(48): (x, z) -> (-z, x))
# and its objects get yang + 16, which leaves the world unchanged. D2's TLIGHT02 (an arm,
# facing -z) becomes TLIGHT00 so it gets kind 0. The plugin sets Chicago's glow offsets.
LIGHT_TURN = dict(CITY.light_turn)            # model name -> quarter-turn steps (of 64); Chicago {"TLIGHT01": 48}
LIGHT_RENAME = dict(CITY.light_rename)         # Chicago {"TLIGHT02": "TLIGHT00"}


def light_turns(chi: Lev, models_all: dict) -> dict:
    """{model index: q} for the turned light models and their instances."""
    if "keep_lightmodels" in EXPERIMENT:
        return {}
    names = model_names(chi)
    src = {i: LIGHT_TURN[n] for i, n in enumerate(names) if n in LIGHT_TURN}
    out = dict(src)
    for i, m in models_all.items():
        if m is not None and m.instance_number in src:
            out[i] = src[m.instance_number]
    return out


def turn_model(data: bytes, q: int) -> bytes:
    """Vertices (own ones) and collision boxes turned by q (multiple of 16) yang steps:
    R(16) maps (x, z) -> (z, -x) (the engine's quadrant rule, 0x80043544)."""
    d = bytearray(data)
    k = (q // 16) % 4

    def rot(x, z):
        for _ in range(k):
            x, z = z, -x
        return x, z
    inst, = struct.unpack_from("<h", d, 4)
    nverts, = struct.unpack_from("<h", d, 0x0C)
    verts, coll = struct.unpack_from("<i", d, 0x10)[0], struct.unpack_from("<i", d, 0x20)[0]
    if inst < 0 and verts + 8 * nverts <= len(d):
        for j in range(nverts):
            x, y, z = struct.unpack_from("<3h", d, verts + 8 * j)
            x, z = rot(x, z)
            struct.pack_into("<3h", d, verts + 8 * j, x, y, z)
    if coll and coll + 4 <= len(d):
        n, = struct.unpack_from("<i", d, coll)
        for j in range(max(0, n)):
            p = coll + 4 + 20 * j
            if p + 20 > len(d):
                break
            typ, x, y, z, flags, yang, empty, xs, ys, zs = struct.unpack_from("<10h", d, p)
            x, z = rot(x, z)
            # box yang is in 64ths (0..63, D1 and D2 data), like q (Polish's note, 14.10.; was (yang + 64q) & 4095)
            struct.pack_into("<10h", d, p, typ, x, y, z, flags, (yang + q) & 63, empty, xs, ys, zs)
    return bytes(d)


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


# C76 (Infrastructure 20.10., user: diagonal 'cut' lines in the sky): Driver 1's dome is 4 quadrant models x 12 quads, each
# drawn as ONE affine-textured quad (FUN_0004F34C) with a 64 x 42 sky piece; Driver 1's soft skies hide the warping along
# the quad diagonals, Driver 2's skyline (straight building edges) shows it. Chicago's dome quads are split 2 x 2 (48 per
# quadrant; the original 20 vertices keep their indices, the horizon-line pick 0x33ADF3 still finds them): a sub-quad
# carries 0x80 | its parent piece in byte 1 and its own UVs (the piece's quarter, table layout TL, TR, BL, BR) in bytes
# 8..15; exe group C76D (sky_dome_patches) makes the dome loop take the piece from byte 1 when bit 7 is set and the
# piece draw take those UVs (CLUT of the parent). Driver 1's domes (byte 1 = their page index < 128) draw as before.
SKY_SUBDIV = os.environ.get("CHI_SKY_SUBDIV", "0") == "1"   # parked (user R36: probe-33 sky approved; FPS -0.3)
# the piece rows split (0 = cap / upper clouds, 1 = clouds + skyline tops, 2 = skyline + horizon): the soft top row
# keeps its 4 quads (FPS: +96 instead of +144 sky quads)
SKY_SUBDIV_ROWS = {int(v) for v in os.environ.get("CHI_SKY_SUBDIV_ROWS", "1,2").split(",") if v.strip()}
SKY_PIECE_MAP = (0, 2, 6, 10, 1, 5, 9, 4, 8, 11, 7, 3, 2, 11, 7, 3, 6, 10, 8, 4, 0, 1, 5, 9, 9, 0, 4, 8, 5, 1, 10, 6,
                 2, 3, 7, 11, 0, 4, 8, 3, 9, 5, 1, 7, 11, 2, 6, 10)   # exe 0x8008AA8C: piece of quad k in quadrant q


def sky_subdivide(data: bytes, quadrant: int) -> bytes:
    nv, npl = struct.unpack_from("<hH", data, 12)
    vo, po = struct.unpack_from("<ii", data, 16)
    if npl != 12 or nv < 4:
        return data
    V = [list(struct.unpack_from("<4h", data, vo + 8 * i)) for i in range(nv)]
    polys = [bytearray(data[po + 20 * k: po + 20 * k + 20]) for k in range(npl)]
    if any(p[0] & 31 != 5 for p in polys):
        return data
    mids = {}

    def mid(a, b):
        key = (min(a, b), max(a, b))
        if key not in mids:
            va, vb = V[a], V[b]
            V.append([(va[0] + vb[0] + (1 if va[0] + vb[0] > 0 else 0)) // 2, (va[1] + vb[1]) // 2,
                      (va[2] + vb[2]) // 2, 0])
            mids[key] = len(V) - 1
        return mids[key]

    out = []
    for k, p in enumerate(polys):
        piece = SKY_PIECE_MAP[12 * quadrant + k]
        if piece // 4 not in SKY_SUBDIV_ROWS:
            out.append(bytes(p))                           # unmarked: Driver 1's own piece lookup
            continue
        bl, br, tr, tl = p[4], p[5], p[6], p[7]          # FUN_0004F34C: xy0 = v[4] (uv BL), v[5] BR, v[7] TL, v[6] TR
        t, b, l_, r_ = mid(tl, tr), mid(bl, br), mid(tl, bl), mid(tr, br)
        cx = [sum(V[i][c] for i in (tl, tr, bl, br)) // 4 for c in range(3)]
        V.append(cx + [0]); c = len(V) - 1
        grid = {(0, 0): tl, (1, 0): t, (2, 0): tr, (0, 1): l_, (1, 1): c, (2, 1): r_, (0, 2): bl, (1, 2): b, (2, 2): br}
        u0, v0 = 64 * (piece % 4), 42 * (piece // 4)
        us = (u0, (2 * u0 + 63 + 1) // 2, u0 + 63)
        vs = (v0, (2 * v0 + 41 + 1) // 2, v0 + 41)
        for j in range(2):
            for i in range(2):
                q = bytearray(p)
                q[1] = 0x80 | piece
                q[4], q[5], q[6], q[7] = grid[(i, j + 1)], grid[(i + 1, j + 1)], grid[(i + 1, j)], grid[(i, j)]
                q[8:16] = bytes((us[i], vs[j], us[i + 1], vs[j], us[i], vs[j + 1], us[i + 1], vs[j + 1]))
                out.append(bytes(q))
    if len(V) > 120:
        return data
    hdr = bytearray(data[:vo])
    vbytes = b"".join(struct.pack("<4h", *v) for v in V)
    npo = vo + len(vbytes)
    struct.pack_into("<hH", hdr, 12, len(V), len(out))
    struct.pack_into("<iiii", hdr, 16, vo, npo, npo, npo)
    return bytes(hdr) + vbytes + b"".join(out)


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
    from models import POLY_SIZES
    every = os.environ.get("CHI_SUBDIV_ALL", "1") != "0"
    done = set()
    for m in {**carea, **cmem}.values():
        if not (m.shape_flags & 0x2400) or m.vertices < 0x30 or m.num_polys == 0:
            continue
        # C74 (18.10.): the mid-band tile routine 0x80026C38 reads one word PER POLYGON from the list at +0x2C
        # (s5 += 4; the vertex block follows the list), not just the first; tiles with several polygons (66 of 157
        # in Chicago) kept Driver 2's page coordinates in their other records (sand patch, 150740). Each record is
        # remapped with the polygon texture whose original rectangle holds its nine (u, v) points (polygon k first).
        texs, q = [], m.poly_block
        for k in range(m.num_polys):
            t = m.data[q] & 31
            texs.append((m.data[q + 1], m.data[q + 2]))
            q += POLY_SIZES.get(t, 4)
        n = min(m.num_polys, (m.vertices - 0x2C) // 4) if every else 1
        for k in range(n):
            off = struct.unpack_from("<I", m.data, 0x2C + 4 * k)[0] >> 16
            if not off or off in done or off + 18 > len(d):
                continue
            pts = [(d[off + 2 * j], d[off + 2 * j + 1]) for j in range(9)]
            r = None
            for t in [texs[k]] + texs:
                c = remap.get(("C",) + t)
                if c and all(c[4] - 1 <= u <= c[4] + c[6] and c[5] - 1 <= v <= c[5] + c[7] for u, v in pts):
                    r = c
                    break
            r = r or remap.get(("C",) + texs[k]) or fallback
            np_, nd, nx, ny, ox, oy, ow, oh, nw, nh = r
            for j, (u, v) in enumerate(pts):
                d[off + 2 * j] = min(max(nx + (u - ox) * nw // ow, nx), nx + nw - 1)
                d[off + 2 * j + 1] = min(max(ny + (v - oy) * nh // oh, ny), ny + nh - 1)
            done.add(off)
    return bytes(d)


def clut_check(path):
    """S2/slot-15 (Infrastructure 21.10.): permanent, loaded special/car, sky and map CLUTs share one allocator of
    192 + 32 x (first area slot) positions (Chicago 384). Count, from the written level: 38 fixed + palettes of the
    permanent pages + of the 2 special pages loaded in play + one per car palette entry (PALLET lump).
    Calibrated: var_polish_s1_cars1 = 384, var_d2cars16 = 374 (measured in game)."""
    from texpages import read_pages as _rp
    lev = Lev.parse(open(path, "rb").read())
    ti, pages = _rp(lev)
    pal = lev.loadtime.get(L_PALLET).data
    npal = sum(len(pages[p].cluts) for p, _ in ti.permanent) + sum(len(pages[p].cluts) for p, _ in ti.special[:2])
    if any(not pages[p].cluts for p, _ in ti.special):   # C124 blank pair first: the check takes the largest pair (check only)
        sp_ = [len(pages[p].cluts) for p, _ in ti.special]
        npal += max(sum(sp_[k:k + 2]) for k in range(0, len(sp_), 2)) - sum(sp_[:2])
    first_area_slot = len(ti.permanent) - sum(1 for p, _ in ti.permanent if ti.positions[p][0] & 0x80) + 2
    cap = int(os.environ.get("CHI_CLUT_CAP", str(192 + 32 * first_area_slot)))
    pos = CLUT_BASE_POS + npal + struct.unpack_from("<i", pal, 0)[0]
    print("CLUT allocator: %d of %d positions (permanent + 2 special pages %d palettes, car palette entries %d)"
          % (pos, cap, npal, struct.unpack_from("<i", pal, 0)[0]))
    margin = int(os.environ.get("CHI_CLUT_MARGIN", "4"))      # keep a few positions free (the count is calibrated, not exact)
    if pos > cap - margin:
        msg = "CLUT allocator overflow: %d > %d - margin %d (the first area slot's palettes would be overwritten)" % (pos, cap, margin)
        if os.environ.get("CHI_CLUT_CHECK", "error") == "error":
            raise RuntimeError(msg)
        print("WARNING: " + msg)


S1_COPY_HASH = {}
AREA_COPY_HASH = {}   # model id -> hashes of its copies in all areas (carried models must be identical)


def s1_diff_table(world) -> bytes:
    """Q36 B fallback (b), for the engine: per ordered pair of areas loadable from one region (A -> B), the streamed
    model ids present in both whose per-area copy differs (other texture spots): the plugin hides those carried
    models until B's load completes. Format: u16 pair count, then per pair u8 A, u8 B, u16 n, n x u16 model id."""
    pairs = set()
    for reg, la in world["loadable"].items():
        la = sorted(la)
        pairs.update((x, y) for x in la for y in la if x != y)
    out = []
    for a, b in sorted(pairs):
        ids = sorted(i for (aa, i), h in S1_COPY_HASH.items() if aa == a and (b, i) in S1_COPY_HASH and S1_COPY_HASH[(b, i)] != h)
        out.append(struct.pack("<BBH", a, b, len(ids)) + struct.pack("<%dH" % len(ids), *ids))
    return struct.pack("<H", len(out)) + b"".join(out)


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
        rma = getattr(res, "remap_area", {}).get(a)
        for i in ids:
            md = area_data[i]
            if rma:                                       # Polish S1: this area's spots of the local textures
                md = remap_polys(md, "X", rma, None)
                S1_COPY_HASH[(a, i)] = hash(md)
            AREA_COPY_HASH.setdefault(i, []).append(hash(md))
            body += struct.pack("<i", len(md)) + md
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
    empty_vals = None                      # the shared block's road map (M3 hav5: only regions with the same one share it)

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
        shareable = not any(cells) and full_view and reg not in world.get("road_ids", {})
        if shareable and empty_block is not None and world["road_values"][reg] == empty_vals:
            if conn not in empty_records:
                empty_records[conn] = len(spool_records)
                spool_records += record(empty_block, conn)
            region_offsets[reg[1] * rx_n + reg[0]] = empty_records[conn]
            continue
        start = len(spooled) // BLOCK
        ids = world.get("road_ids", {}).get(reg)
        roadm = pad(rle_roadm(ids) if ids else struct.pack("<hH", ROAD_CELLS_PER_REGION, 0xFFFF) + struct.pack("<hH", -1, 0))
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
        reg_radii = [int(world["radii"][reg[1] * REGION_CELLS + cz, reg[0] * REGION_CELLS + cx])
                     for cz in range(REGION_CELLS) for cx in range(REGION_CELLS)]
        pvs_masks = polish_pvs_masks(world)          # CHI_POLISH_PVS=d2 (Polish, C40): Driver 2's own PVS
        if pvs_masks is None:
            pvs_blob = pad(pvs.region_block(reg_radii))
        else:
            import polish_pvs
            limit = polish_pvs.barrels()[b] - len(roadm) - len(roadh) - BLOCK   # stays within LA's buffers
            pvs_blob = pad(polish_pvs.region_block(reg_radii, [pvs_masks.get((reg[0] * REGION_CELLS + cx, reg[1] * REGION_CELLS + cz))
                                                              for cz in range(REGION_CELLS) for cx in range(REGION_CELLS)],
                                                   limit=limit - BLOCK))
        spooled += roadm + roadh + ptr_blob + cell_blob + objs_blob + pvs_blob
        fields = (start, len(pvs_blob) // BLOCK, len(cell_blob) // BLOCK, len(ptr_blob) // BLOCK,
                  len(objs_blob) // BLOCK, len(roadm) // BLOCK, len(roadh) // BLOCK)
        if shareable and empty_block is None:
            # (a region without objects inside the city, e.g. Havana's centre (7,10) / (8,10): its building blocks
            # took the shared block's all-water road map, the map edge's)
            empty_block, empty_vals = fields, world["road_values"][reg]
            empty_records[conn] = len(spool_records)
        region_offsets[reg[1] * rx_n + reg[0]] = len(spool_records)
        spool_records += record(fields, conn)
    return bytes(spooled), areas, slots_max, objs_max, region_offsets, bytes(spool_records), total_cell_data


WATER_MODEL = CITY.water_model   # free in-memory slot (Chicago 683) < 900 (road map ids must be < 900)
WATER_SRC = 316              # LA's water tile (shape flags 0x04A1, 1500 x 1500, LASEA)
WATER_SCALE = 2              # LA's 1500 tile stretched to one per 3000 cell (with real corner vertices, see water_model)
WATER_Y = int(os.environ.get("CHI_WATER_Y", str(CITY.water_level)))               # water surface below street level: the sand base (one ocean level; quay gaps closed by shore walls)
WATER_NEAR = 4               # water tiles on water cells within this many cells of land
WATER_LEVEL = int(os.environ.get("CHI_WATER_LEVEL", str(CITY.water_level)))  # one level for all water: 100 under the sand base (beach_n car y -820 = sand 984;
                             # at equal height water and sand tiles swapped draw order: water through the sand); 0 = per shore
WATER_BELOW_SHORE = 100      # water this far under the lowest shore nearby
WATER_SHORE_RADIUS = 8       # road cells (12000 units)
WATER_MAX_DEPTH = 2000
WATER_CLOSE = int(os.environ.get("CHI_WATER_CLOSE", "4"))   # land gaps (bridges) filled between water cells
WATER_GROW = int(os.environ.get("CHI_WATER_GROW", "0"))     # cells of water under the shore (0: water only where there is water)
BEACH_GROW = int(os.environ.get("CHI_BEACH_GROW", "0"))     # display-only water this many cells under low land (beaches): gaps show water; 0 since R12 (user 2026-10-13: seen from below while drowning; was 2)


def _city_key() -> str:
    """M3: converter caches must not mix cities. Chicago (day and night share the geometry) keeps its old keys (""),
    any other Driver 2 level adds its file name."""
    if CITY.name == "CHICAGO" and CITY.is_lev(D2_LEV):
        return ""
    return os.path.basename(D2_LEV).upper()


def surface_grid(across, down):
    """Driver 2 surface per 3000-unit cell, sampled at its 4 quarter points:
    {(cx, cz): (land?, wet?)} (cached)."""
    import pickle, hashlib
    from d2surface import Surface
    key = hashlib.md5(open("d2surface.py", "rb").read() + _city_key().encode()).hexdigest()[:8]
    cache = os.path.join(inputs.cache_dir(), "surface_grid4_%d_%d_%s.pkl") % (across, down, key)
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    surf = Surface(D2_LEV)
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


MAP_WATER = tuple(CITY.map_water)   # overhead-map palette of water (Chicago: river 1, lake 12; Havana: sea 4)


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
    key = hashlib.md5((open("d2overlay.py", "rb").read() + repr((across, down, ws.OFFSET_X, ws.OFFSET_Z, sorted(grid.items())[:50])).encode() + b"v4" + _city_key().encode() + (b"" if MAP_WATER == (1, 12) else repr(MAP_WATER).encode()) + (b"seatiles" if CITY.sea_tiles_water else b""))).hexdigest()[:8]
    cache = os.path.join(inputs.cache_dir(), "sea_kinds_%s.pkl") % key
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    ov = Overlay(D2_LEV)
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
            wet += any(ov.at(dx + ox, dz + oz) in MAP_WATER for ox in (-r, 0, r) for oz in (-r, 0, r))
        frac = wet / len(comp[::max(1, len(comp) // 4000)])
        edge = any(k[0] in (0, w - 1) or k[1] in (0, h - 1) for k in comp)
        kind = "water" if frac >= 0.3 else ("void" if edge else "inside")
        if edge and len(comp) > 100000:        # the lake joins the land outside the city: per cell
            for (col, row) in comp:
                dx, dz = ws.to_d2(col * ROAD_UNIT - half_x, half_z - row * ROAD_UNIT)
                out[(col, row)] = "water" if ov.at(dx, dz) in MAP_WATER else "void"
            continue
        for k in comp:
            out[k] = kind
    if CITY.sea_tiles_water:                   # M3 Rio (rio2): Driver 2's own sea tiles mark water (the coast strips)
        import d2cells as _d2c
        from models import inmem_models as _im, area_models as _am
        _lev = Lev.parse(open(D2_LEV, "rb").read())
        _all = {**_am(_lev), **_im(_lev)[0]}
        _ext = {}
        for i, m in _all.items():
            if m.shape_flags & 0x80 and m.shape_flags & 0x0400:
                src = _all.get(m.instance_number, m) if m.instance_number >= 0 else m
                try:
                    vs = [struct.unpack_from("<3h", src.data, src.vertices + 8 * k) for k in range(src.num_vertices)]
                    _ext[i] = (min(v[0] for v in vs), max(v[0] for v in vs), min(v[2] for v in vs), max(v[2] for v in vs))
                except struct.error:
                    pass
        marked = 0
        for o in _d2c.extract(D2_LEV)[2].values():
            e = _ext.get(o.model)
            if not e:
                continue
            xs = (o.x + e[0], o.x + e[1]); zs = (o.z + e[2], o.z + e[3])
            (x0, z0), (x1, z1) = ws.to_d1(xs[0], zs[0]), ws.to_d1(xs[1], zs[1])
            for col in range(int((min(x0, x1) + half_x) // ROAD_UNIT), int((max(x0, x1) + half_x) // ROAD_UNIT) + 2):
                for row in range(int((half_z - max(z0, z1)) // ROAD_UNIT), int((half_z - min(z0, z1)) // ROAD_UNIT) + 2):
                    if out.get((col, row)) == "void":
                        out[(col, row)] = "water"; marked += 1
        print("sea kinds: %d void cells under Driver 2 sea tiles become water" % marked)
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
    if WATER_LEVEL:                            # user (2026-10-11): one ocean level everywhere, at the sand base
        return {k: WATER_LEVEL for k, v in kinds.items() if v == "water"}
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


_iw = __import__("os").environ.get("CHI_POLISH_INSIDEWATER", "basin")   # R36: basin default (user approved); "0" = off
INSIDE_BASIN = _iw == "basin"      # C75: per-hole rule from D2's geometry (exposed holes get water)
INSIDE_WATER = 1 if INSIDE_BASIN else int(_iw or 0)   # (radius rule: 3000-cells from water; too coarse)


TALL_SHARE = 0.35
BASIN_CELLS = set()                # 3000-cells filled as basins (water_cells)
BASIN_Y = int(__import__('os').environ.get('CHI_POLISH_BASIN_Y', '24'))   # basin water just below street / sand level (sand -22, y down)
BASIN_MIN = 5                      # road cells; smaller holes are building interiors
WATER_TEX = CITY.water_tex   # a basin's own rim / water textures


def exposed_inside_cells(kinds, across, down, wall=1000):
    """C75 per-hole rule from Driver 2's own geometry: 'inside' road cells (enclosed no-surface holes) form holes;
    a hole whose own and surrounding objects (1-cell ring) are all lower than `wall` above the street is an open
    basin / pool (Buckingham Fountain: rim 384, centre 768), where Driver 2's water level shows; a hole walled by
    tall facades (building blocks: 2000+) is a building interior and stays dry. Returns the basin road cells."""
    import collections, d2cells
    from models import inmem_models, area_models
    _, _, objects, _ = d2cells.extract(D2_LEV)
    d2 = Lev.parse(open(D2_LEV, "rb").read())
    mem, _ = inmem_models(d2); allm = {**area_models(d2), **mem}
    half_x, half_z = across // 2 * CELL, down // 2 * CELL
    inside = {k for k, v in kinds.items() if v == "inside"}
    comp, n = {}, 0
    for k in inside:
        if k in comp:
            continue
        stack = [k]; comp[k] = n
        while stack:
            c = stack.pop()
            for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = (c[0] + d[0], c[1] + d[1])
                if nb in inside and nb not in comp:
                    comp[nb] = n; stack.append(nb)
        n += 1
    height = {}
    tallest = collections.defaultdict(int)
    count = collections.Counter(); tall_n = collections.Counter(); wet_n = collections.Counter()
    from texrepack import model_texrefs
    from textures import TexInfo
    ti2 = TexInfo.parse(d2.loadtime.get(34).data); nm2 = d2.loadtime.get(5).data
    def _tn(p, k):
        try:
            no = ti2.details[p][k][1]; return nm2[no:nm2.index(b"\0", no)].decode("latin-1").upper()
        except Exception:
            return ""
    wet_model = {}
    for o in objects.values():
        m = allm.get(o.model)
        if m is None:
            continue
        if o.model not in height:
            src = allm.get(m.instance_number, m) if m.instance_number >= 0 and m.instance_number != o.model else m
            try:
                ys = [struct.unpack_from("<3h", src.data, src.vertices + 8 * i)[1] for i in range(src.num_vertices)] if src.vertices > 0 else [0]
            except struct.error:
                ys = [0]
            height[o.model] = -min(ys)
        h = height[o.model] - o.y
        x, z = ws.to_d1(o.x, o.z)
        col, row = (x + half_x + ROAD_UNIT // 2) // ROAD_UNIT, (half_z - z + ROAD_UNIT // 2) // ROAD_UNIT
        for dc in (-1, 0, 1):
            for dr in (-1, 0, 1):
                c = comp.get((col + dc, row + dr))
                if c is not None:
                    tallest[c] = max(tallest[c], h)
                    count[c] += 1; tall_n[c] += h >= wall
                    if o.model not in wet_model:
                        wet_model[o.model] = any(w in _tn(*r) for r in model_texrefs(m, allm) for w in WATER_TEX)
                    wet_n[c] += wet_model[o.model]
                    break
            else:
                continue
            break
    # mostly low objects (rims, paving, plants; a fountain's few tall centre pieces allowed) = open basin
    size = collections.Counter(comp.values())
    # (D2 top-down check 18.10.: the 1-3 cell holes on the north lakefront lie under building roofs: dry)
    basins = {c for c in range(n) if count[c] >= 4 and tall_n[c] <= TALL_SHARE * count[c] and wet_n[c] and size[c] >= BASIN_MIN}
    out = {k for k, c in comp.items() if c in basins}
    print("inside holes: %d holes, %d basins (water-edge textures, <= %d%% of their objects %d+ high) = %d road cells" % (n, len(basins), TALL_SHARE * 100, wall, len(out)))
    return out


KEEP_SHORE_TILES = __import__("os").environ.get("CHI_POLISH_KEEPSHORETILES", "1") == "1"
_SURF = {}


def _d2surf():
    if "s" not in _SURF:
        from d2surface import Surface
        _SURF["s"] = Surface(D2_LEV)
    return _SURF["s"]


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
    if INSIDE_WATER:
        # Polish (user R33, monument): Driver 2 shows its global water level through every no-surface hole; an
        # enclosed hole ("inside") next to the lake / river is a pool or basin there, not ground: give it water
        inside = set()
        for cz in range(down):
            for cx in range(across):
                cells = [(2 * cx + i, rows - 1 - (2 * cz + j)) for i in (0, 1) for j in (0, 1)]
                if any(kinds.get(c) == "inside" for c in cells):
                    inside.add((cx, cz))
        if INSIDE_BASIN:
            # per hole from Driver 2's own geometry: a no-surface road cell under a tall model (building interior)
            # stays dry; an exposed one (fountain basin, pool) shows D2's water level -> water tile
            exposed = exposed_inside_cells(kinds, across, down)
            add = {c for c in inside if any(((2 * c[0] + i, rows - 1 - (2 * c[1] + j)) in exposed) for i in (0, 1) for j in (0, 1))}
        else:
            add = {c for c in inside if any((c[0] + dx, c[1] + dz) in wet for dx in range(-INSIDE_WATER, INSIDE_WATER + 1)
                                            for dz in range(-INSIDE_WATER, INSIDE_WATER + 1))}
        print("inside water: %d cells next to the lake / river" % len(add - out))
        if INSIDE_BASIN:
            # R35: the basin water continues one cell under the surrounding sand / paving (like the beaches), so no
            # gap shows at the rim; at BASIN_Y it stays below the ground there
            ring = {(cx + dx, cz + dz) for (cx, cz) in add for dx in (-1, 0, 1) for dz in (-1, 0, 1)}
            add = (add | ring) - out
            BASIN_CELLS.update(add)
        out |= add
    if BEACH_GROW:                             # display-only water under low land next to the water (beaches)
        world = dict(across=across, down=down, rx_n=across // REGION_CELLS, rz_n=down // REGION_CELLS)
        grid = road_levels(world)
        def ground(c):
            lv = sorted(grid.get(c, [(0, 0)]), key=lambda hl: (hl[1] in (6, 9), abs(hl[0])))
            return lv[0][0]
        low = set()
        for (cx, cz) in land:
            cells = [(2 * cx + i, rows - 1 - (2 * cz + j)) for i in (0, 1) for j in (0, 1)]
            if all(kinds.get(c) is not None or ground(c) >= WATER_LEVEL - 500 for c in cells):
                low.add((cx, cz))
        front = set(out)
        for _ in range(BEACH_GROW):
            front = {(cx + dx, cz + dz) for (cx, cz) in front for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
                     if (cx + dx, cz + dz) in low and (cx + dx, cz + dz) not in out}
            out |= front
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
    # LA's 316 is an instance (+4 = 7): at load the engine (0x80052434) gave it the vertices
    # of Chicago's model 7, and far tiles (0x800268FC: first 4 vertices) became skewed
    # 1364 x 1430 squares per 3000 cell, the chunks to the horizon
    struct.pack_into("<h", d, 4, -1)
    if "water_tileflag" not in EXPERIMENT:     # as Miami's sea (0x00A1): no tile flag, so water goes
        struct.pack_into("<H", d, 0, struct.unpack_from("<H", d, 0)[0] & ~0x0400)   # to the back OT slots
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


FAR_WATER = "no_farwater" not in EXPERIMENT and "no_water" not in EXPERIMENT   # user choice C19: far water planes
FAR_SIZE = 6000              # far water plane: 2 x 2 cells, 2 x 2 quads of the water texture
FAR_SHORE = 4                # road cells of open water around it: 1 put planes under a camera on the beach (no near clipping: overhead sheet)
FAR_REACH = 24               # road cells from land (36000 units): beyond that it is never seen


def inside_world(x, z, across, down) -> bool:
    """Inside the regions that may hold objects: the outer region ring stays empty."""
    mx, mz = across // 2 * CELL - REGION_CELLS * CELL, down // 2 * CELL - REGION_CELLS * CELL
    return -mx <= x < mx and -mz <= z < mz


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


SHORE_WALLS = "no_walls" not in EXPERIMENT and "no_water" not in EXPERIMENT and CITY.wall_texture is not None   # quay walls down to the water (984 level)
WALL_TEXTURE = CITY.wall_texture   # Chicago: Driver 2's RIVER3A: concrete quay wall with a dark waterline (forced resident)
WALL_DEPTH = CITY.wall_depth if CITY.wall_depth else 2000 + CITY.water_level - 1084   # from the bank down, past the water (WATER_LEVEL; Chicago 2000)
WALL_TOP_GAP = 40            # wall top this far under the bank edge: no overlap with the ground at the rim
WALL_YANG = tuple(int(v) for v in os.environ.get("CHI_WALL_YANG", "48,16,32,0").split(","))   # land +x, -x, below, above (x verified at quaydiag 2026-10-11: 16/48 faced the land)


def shore_wall_model(res, fallback) -> bytes:
    """A 1500-wide vertical quay wall (both faces), top at the model origin."""
    import d1models
    h, w = WALL_DEPTH, ROAD_UNIT // 2
    verts = [(-w, 0, 0), (w, 0, 0), (w, h, 0), (-w, h, 0)]
    uv = [(128, 64), (223, 64), (223, 127), (128, 127)]
    _, page, det = WALL_TEXTURE
    # one face, towards the water (model -z): seen from the street it is a back face and
    # culled; two-sided, the near side smeared across the street (no near clipping)
    face = bytes([11, page, det, 0, 0, 1, 2, 3]) + b"".join(bytes(t) for t in uv)
    if d1models.poly_normal(face, verts)[2] > 0:
        face = bytes([11, page, det, 0, 3, 2, 1, 0]) + b"".join(bytes(t) for t in uv[::-1])
    vblock = b"".join(struct.pack("<4h", x, y, z, 0) for x, y, z in verts)
    p_off = 36 + len(vblock)
    hdr = struct.pack("<3hBB4h5i", 0x0001, 0, -1, 0, 0, int(w * 1.5), 0, 4, 1, 36, p_off, p_off, p_off, 0)
    conv, _ = d1models.convert_models({0: hdr + vblock + face})
    return remap_polys(conv[0], "C", res.remap, fallback)


SHORE_FIX = __import__("os").environ.get("CHI_POLISH_SHOREFIX", "1") == "1"  # Polish: no walls hanging from raised levels (default since 16.10., C70 round 2)
SHORE_RAISED = 300            # a bank level this far above the street counts as raised


QUAY_CLEAN = __import__("os").environ.get("CHI_POLISH_QUAYCLEAN", "1") == "1" and bool(CITY.quay_models)   # R36: default (user approved)   # Polish C70: no fillers at D2's quays
QUAY_MODELS = CITY.quay_models
QUAY_DROP = CITY.quay_drop   # lower river-walk / below-street quay pieces (C70 r2)
_qf = __import__("os").environ.get("CHI_POLISH_QUAYFILL", "4")   # R36: mode 4 default (user approved map fixes 2); "0" = off
QUAY_FILL = _qf in ("1", "2", "3", "4") and bool(CITY.quay_rail_src)   # M3: Chicago-only lists (empty elsewhere)
# mode 2 (user R33): the sloped quay walls are the REAL ones (1113/1114 faces, 1115 stay); only the vertical fronts
# standing before them (1000 and the lower-walk boxes 117/119/122) go invisible (collision kept); water fill as mode 1
QUAY_GHOST = CITY.quay_ghost_2 if _qf == "2" else CITY.quay_ghost_34 if _qf in ("3", "4") else None
# mode 3 (user R34): the lower-walk boxes 117/119/122 ARE the quay seen from across the river (hiding them left an
# empty spot); only the vertical front 1000 before the sloped wall goes invisible (collision kept)
QUAY_SPOT = CITY.quay_spot      # quay_wall (D1)
QUAY_STRETCH = 12000               # lower-walk pieces this close to quay_wall define the clean-up stretch
QUAY_SITE_R = 2500                 # ... and everything this close to such a piece is cleaned


def quay_sites():
    """D1 positions of Driver 2's lower river-walk pieces (QUAY_DROP models below the street) along the stretch
    around quay_wall."""
    import math, d2cells
    _, _, objects, _ = d2cells.extract(D2_LEV)
    out = []
    for o in objects.values():
        if o.model in QUAY_DROP and o.y > 500:
            x, z = ws.to_d1(o.x, o.z)
            if _qf == "4" or math.hypot(x - QUAY_SPOT[0], z - QUAY_SPOT[1]) <= QUAY_STRETCH:   # 4: city-wide (R35)
                out.append((x, z))
    return out


def _quay_low(col, row):
    """A road-map cell whose only D2 levels lie well below the street (the lower river walk)."""
    grid = _QUAY_GRID.get("g")
    lv = grid.get((col, row), []) if grid else []
    return bool(lv) and all(y > 500 for y, t in lv if t not in (6, 9))


_QUAY_GRID = {}   # Driver 2's river quay walls with balustrade (9462 D1 units long)
QUAY_R = 1600                      # a filler wall this close to a D2 quay wall line is dropped


def quay_segments():
    """Driver 2's quay-wall lines in Driver 1 coordinates: [((x0, z0), (x1, z1))] (model z axis rotated by yang)."""
    import math, d2cells
    _, _, objects, _ = d2cells.extract(D2_LEV)
    out = []
    for o in objects.values():
        if o.model in QUAY_MODELS:
            a = o.yang * 2 * math.pi / 64
            x0, z0 = ws.to_d1(o.x, o.z)
            L = 7168 * ws.SCALE
            out.append(((x0, z0), (x0 + math.sin(a) * L, z0 + math.cos(a) * L)))
    return out


def _seg_dist(p, a, b):
    import math
    ax, az = a; bx, bz = b; px, pz = p
    dx, dz = bx - ax, bz - az
    t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / max(1e-9, dx * dx + dz * dz)))
    return math.hypot(px - ax - t * dx, pz - az - t * dz)


def shore_walls(across, down):
    """(x, y, z, yang) per water/land edge where the bank stands above the water:
    the wall hides the gap between the bank's edge and the water below it."""
    kinds = sea_kinds(across, down)
    wh = water_heights(across, down)
    grid = road_levels(dict(across=across, down=down, rx_n=across // REGION_CELLS, rz_n=down // REGION_CELLS))
    half_x, half_z = across // 2 * CELL, down // 2 * CELL
    out = []
    for (col, row), kind in kinds.items():
        if kind != "water":
            continue
        # land at (dc, dr); the face (model -z) must point back at the water: rotation
        # (64 = 360 degrees) for water towards -x (land +x), +x, +z (land below: row+1), -z
        for dc, dr, yang in ((1, 0, WALL_YANG[0]), (-1, 0, WALL_YANG[1]), (0, 1, WALL_YANG[2]), (0, -1, WALL_YANG[3])):
            n = (col + dc, row + dr)
            if n not in grid or kinds.get(n) is not None:
                continue
            if any(kinds.get((n[0] + dc * k, n[1] + dr * k)) == "water" for k in range(1, WATER_CLOSE + 1)):
                continue                       # bridge deck: water again on the far side, no wall under it
            lv = sorted(grid[n], key=lambda hl: (hl[1] in (6, 9), abs(hl[0])))
            gy = 0 if abs(lv[0][0]) < HEIGHT_DEADBAND else lv[0][0]
            if SHORE_FIX and gy < -SHORE_RAISED:
                # Polish (quay_wall, 15.10.): a land cell whose only D2 level is raised (a structure top, a deck)
                # hung a 2000-high wall from up there: huge grey planes across the street. Take the bank level of
                # the land neighbours instead (median of their street-near levels), else no wall.
                near = sorted(min((h for h, t in grid.get((n[0] + i, n[1] + j), []) if t not in (6, 9)), key=abs, default=None)
                              for i in (-1, 0, 1) for j in (-1, 0, 1) if (i or j) and kinds.get((n[0] + i, n[1] + j)) is None
                              and grid.get((n[0] + i, n[1] + j)))
                near = [h for h in near if h is not None and -SHORE_RAISED <= h <= 1000]
                if not near:
                    continue
                gy = near[len(near) // 2]
                gy = 0 if abs(gy) < HEIGHT_DEADBAND else gy
            if gy > wh.get((col, row), WATER_Y) - 100:
                continue                       # beach at or below the water: no wall
            x = col * ROAD_UNIT - half_x + dc * ROAD_UNIT // 2
            z = half_z - row * ROAD_UNIT - dr * ROAD_UNIT // 2
            out.append((x, gy + WALL_TOP_GAP, z, yang))
    if QUAY_CLEAN:
        # Polish C70 (user R30): at Driver 2's own quays (balustrade walls 1113-1115) our generated fillers were the
        # low / below-street faces the user kept seeing; D2 has none there. Beach walls elsewhere stay.
        segs = quay_segments()
        keep = [w for w in out if not any(_seg_dist((w[0], w[2]), a, b) <= QUAY_R for a, b in segs)]
        print("shore walls: %d of %d dropped at Driver 2's quays (CHI_POLISH_QUAYCLEAN)" % (len(out) - len(keep), len(out)))
        out = keep
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
WALLTOP = int(os.environ.get("CHI_WALLTOP", "0"))        # ground cells beside a sunken road follow it (off since the plugin selects the highest plane below the wheel; the trench enters those cells as a guard plane)
MEDIAN_SNAP = int(os.environ.get("CHI_MEDIAN_SNAP", "40"))  # a cell this little above a neighbour takes the neighbour's level (median kerbs; 0: off)
SURF_SEP = 300                # levels this far apart in one cell become separate ROADSURF planes (engine patch picks the nearest to the wheel)
SLOPE_MAX = 0.4               # steeper fits are embankments (0.66-1.06 vs ramps <= 0.31): the cell stays flat
SLOPE_MIN = 30                # height change across a cell (1500) from which a sloped plane is written
SLOPE_SIGN = (int(os.environ.get("CHI_SLOPE_SX", "1")), int(os.environ.get("CHI_SLOPE_SZ", "1")))   # sign of the plane's x / z gradient (verified in game)
SURF_MAX = int(os.environ.get("CHI_SURF_MAX", "896"))   # distinct ROADSURF surfaces (type ids are plain model ids < 900; 120 B each in memory)
SURF_Q = 64                   # quantisation of plane offsets (fewer distinct surfaces)
OWN_Q = 8                     # the cell's own levels: exact (the road map's height step)
OWN_TOL = int(os.environ.get("CHI_OWN_TOL", "32"))   # the surface merge may move own levels by this much at most
GUARD_Q = int(os.environ.get("CHI_GUARD_Q", "64"))   # neighbour-level planes (guards): coarser, they only need to catch the car
SLOPE_Q = 128                 # quantisation of plane gradients (/4096): 1.8 deg, <= 23 units at a cell edge


def road_levels(world):
    """Driver 2 surface levels at every 1500-unit road cell: {(col, row): [(ground y, type)]},
    col/row as the game counts them (row 0 at the top, max z). Cached."""
    import pickle, hashlib
    from d2surface import Surface
    key = hashlib.md5(open("d2surface.py", "rb").read() + repr(
        (world["rx_n"], world["rz_n"], world["across"], world["down"], ws.SCALE)).encode() + _city_key().encode()).hexdigest()[:8]
    cache = os.path.join(inputs.cache_dir(), "road_levels_%s.pkl") % key
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    surf = Surface(D2_LEV)
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


TUNNEL_GAP = int(os.environ.get("CHI_TUNNEL_GAP", "12"))   # covered trench stretches (no D2 surface) filled up to this many cells
END_RAMP = int(os.environ.get("CHI_END_RAMP", "6"))         # cells over which a dead-ending trench rises to the street
BRIDGE_GAP = 2                # street cells over a trench (D2 gives only the bridge) treated as a bridge


def trench_ends(world, grid, choice, kinds):
    """C20: a sunken freeway (trench, ~1352 down) runs into tunnels. Driver 2 has no
    surface plane inside them (no-surface cells, read as sea / building blocks) and
    under a street only the street level, so the trench met a 1352 step: cars were
    launched or flipped at the portals. (1) Covered stretches between two trench
    segments (<= TUNNEL_GAP cells, no surface at all) get the trench floor. (2) Where
    a trench still ends against street level or a longer covered stretch, its last
    END_RAMP cells rise linearly to the street (sloped ROADSURF planes: no stairs).
    Returns {cell: (gx, gz)} slopes for surface_planes."""
    dirs = ((1, 0), (-1, 0), (0, 1), (0, -1))
    tunnel = set()
    def trench_set():
        return {k for k, (y, t) in choice.items()
                if y >= 600 and t not in (6, 9) and (kinds.get(k) != "inside" or k in tunnel)}
    nosurf = lambda k: k in grid and kinds.get(k) in ("inside", "void")
    trench, filled = trench_set(), 0
    for k in sorted(trench):
        y0, t0 = choice[k]
        for d in dirs:
            n = (k[0] + d[0], k[1] + d[1])
            if n in trench or not nosurf(n):
                continue
            path, c = [], n
            while nosurf(c) and len(path) <= TUNNEL_GAP:
                path.append(c); c = (c[0] + d[0], c[1] + d[1])
            if len(path) <= TUNNEL_GAP and c in trench and abs(choice[c][0] - y0) < 200:
                for q in path:
                    if choice[q][0] != y0:
                        choice[q] = (y0, t0); filled += 1
                    tunnel.add(q)
                    world.setdefault("filled", set()).add(q)
    # a street crossing the trench on a bridge, where Driver 2's surface gives only the
    # bridge (<= BRIDGE_GAP cells, trench at the same depth on the far side): the trench
    # runs on underneath (the street stays the cell's upper plane); it is no dead end
    trench, bridged = trench_set(), 0
    for k in sorted(trench):
        y0, t0 = choice[k]
        for d in dirs:
            path, c = [], (k[0] + d[0], k[1] + d[1])
            while c in choice and c not in trench and not nosurf(c) and kinds.get(c) != "water" \
                    and abs(choice[c][0]) < 300 and len(path) <= BRIDGE_GAP:
                path.append(c); c = (c[0] + d[0], c[1] + d[1])
            if path and len(path) <= BRIDGE_GAP and c in trench and abs(choice[c][0] - y0) < 200:
                for q in path:
                    choice[q] = (y0, t0); bridged += 1
                trench.update(path)
    trench = trench_set()
    ramps = {}
    # user R10: no ramps where Driver 2 has none (only its own ramps stay drivable)
    for k in (trench if "keep_trenchramps" in EXPERIMENT else ()):
        y0 = choice[k][0]
        for d in dirs:
            n = (k[0] + d[0], k[1] + d[1])
            if n in trench or n not in choice:
                continue
            ny, nt = choice[n]
            if kinds.get(n) == "water" or (abs(ny) >= 300 and not nosurf(n)):
                continue                       # the river, or a different level: not a dead end
            back = [(k[0] - d[0] * i, k[1] - d[1] * i) for i in range(END_RAMP)]
            if not all(b in trench and abs(choice[b][0] - y0) < 200 for b in back):
                continue                       # only along the trench's axis (it is narrower than the ramp)
            run = {}                           # across the end: a trench is a few cells wide; the long
            for s in (1, -1):                  # side of a wide sunken area (a beach, a lower road
                i, c = 0, k                    # beside the river) is no end and keeps its wall
                while (c[0] + d[1] * s, c[1] + d[0] * s) in trench and abs(choice[(c[0] + d[1] * s, c[1] + d[0] * s)][0] - y0) < 200 and i < END_RAMP:
                    i += 1; c = (c[0] + d[1] * s, c[1] + d[0] * s)
                run[s] = i
            if run[1] + run[-1] + 1 > END_RAMP:
                continue
            # a bend (the trench goes on beside the street ahead, wallstop1) or a trench
            # resuming just ahead is no dead end either
            if any((n[0] + d[0] * j + d[1] * i, n[1] + d[1] * j + d[0] * i) in trench
                   and abs(choice[(n[0] + d[0] * j + d[1] * i, n[1] + d[1] * j + d[0] * i)][0] - y0) < 200
                   for j in range(3) for i in range(-run[-1] - 2, run[1] + 3)):
                continue
            g = y0 / float(END_RAMP * ROAD_UNIT)
            slope = {(1, 0): (-g, 0.0), (-1, 0): (g, 0.0), (0, 1): (0.0, g), (0, -1): (0.0, -g)}[d]
            for i, b in enumerate(back):       # i = 0: the end cell, next to the street
                h = int(round(y0 * (i + 0.5) / END_RAMP))
                if b not in ramps or h < ramps[b][0]:
                    ramps[b] = (h, slope)
    slopes = {}
    for b, (h, slope) in ramps.items():
        choice[b] = (h, choice[b][1])
        slopes[b] = slope
    # cells beside a trench without any D2 surface (a pillar, a building corner): a car
    # hugging the wall that enters one would be lifted to street level; keep it down.
    # After the ramps, and only beside cells still at trench depth: a hole next to a
    # ramp's top stays at street level (it was a 1352 pit before the ramp, C20 p2n).
    # Not void cells: they are the map's drowning boundary (outside the city)
    holes = 0
    for k in sorted(trench_set()):
        y0, t0 = choice[k]
        if y0 < 600 or k in ramps:
            continue
        for d in dirs:
            n = (k[0] + d[0], k[1] + d[1])
            if n in choice and n not in ramps and kinds.get(n) not in ("water", "void") and n not in world.get("bed", ()) and choice[n][0] < y0 \
                    and not any(t not in (6, 9) for _, t in grid.get(n, [])):
                choice[n] = (y0, t0); holes += 1
                world.setdefault("filled", set()).add(n)
    print("road map: trench ends: %d covered cells filled, %d bridge cells, %d holes beside trenches, %d ramp cells"
          % (filled, bridged, holes, len(ramps)))
    return slopes


# Driver 2 surfaces of rail inclines (not marked as such in the data, found by the user):
# col 369 rows 873-879 climbs from the trench (1352) to street level (R8, the user's
# 19:14 track), rows 860-866 is its twin to the north (one 1-cell V with the floor between)
RAIL_INCLINES = set(CITY.rail_inclines)
RAIL_CUTS = list(CITY.rail_cuts)       # seeds of rail trenches (user R10: under c20_p2n's bridge)
RAIL_FLOOR = CITY.rail_floor
EDGE_WATER_MIN = int(os.environ.get("CHI_EDGE_WATER_MIN", "6"))   # of 9 samples water: a water-edge cell becomes water
BED_DEPTH = 1700 + CITY.water_level - 1084   # (Chicago 1700) land levels this deep next to water are D2's river / lake bed
GUARD_MIN_BELOW = int(os.environ.get("CHI_GUARD_MIN_BELOW", "300"))   # a neighbour's level becomes a guard plane only this far below (a sunken road / trench floor: a car along its wall must not be pushed up)
NO_SWITCH = -0x8000            # SIPOLY pad: no Driver 2 switch height (the plugin uses the midpoint)


def level_switches(world):
    """Driver 2's own level switch heights (d2surface.switches) at every road cell centre
    with several D2 levels: {cell: {level y down: switch y down}}; the wheel leaves that
    level for the next lower one once it is deeper than the switch. Cached."""
    import pickle, hashlib
    from d2surface import Surface
    key = hashlib.md5(open("d2surface.py", "rb").read() + repr(
        (world["rx_n"], world["rz_n"], world["across"], world["down"], ws.SCALE, "switch1")).encode() + _city_key().encode()).hexdigest()[:8]
    cache = os.path.join(inputs.cache_dir(), "level_switches_%s.pkl") % key
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    surf = Surface(D2_LEV)
    half_x, half_z = world["across"] // 2 * CELL, world["down"] // 2 * CELL
    out = {}
    for row in range(world["rz_n"] * 60):
        for col in range(world["rx_n"] * 60):
            dx, dz = ws.to_d2(col * ROAD_UNIT - half_x, half_z - row * ROAD_UNIT)
            lv = surf.switches(dx, dz)
            if lv:
                out[(col, row)] = {int(round(-h * ws.SCALE)): int(round((256 + t) * ws.SCALE))
                                   for h, t in lv if t is not None}
    pickle.dump(out, open(cache, "wb"))
    return out


def sea_fixed_cells(world):
    """Cells whose road_levels entry was replaced by nearby land levels because the
    Driver 2 surface says sea at the cell centre (river banks, quays). Cached."""
    import pickle, hashlib
    from d2surface import Surface
    key = hashlib.md5(open("d2surface.py", "rb").read() + repr(
        (world["rx_n"], world["rz_n"], world["across"], world["down"], ws.SCALE, "seafix1")).encode() + _city_key().encode()).hexdigest()[:8]
    cache = os.path.join(inputs.cache_dir(), "sea_fixed_%s.pkl") % key
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    surf = Surface(D2_LEV)
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
    p, ids, empty = 4, [], []
    for i in range(min(n, limit)):
        size, = struct.unpack_from("<i", models_lump, p)
        if size >= 4:
            f1, f2 = struct.unpack_from("<2H", models_lump, p + 4)
            if not (f1 & 0x80) and not (f2 & 0x4000) and i not in (GRASS_ID, WATER_MODEL):
                ids.append(i)
        elif i not in (GRASS_ID, WATER_MODEL):
            empty.append(i)            # driver_chicago.c points empty models at a plain placeholder
        p += 4 + size
    return ids + empty


def cell_slopes(world, cells, choice):
    """Sloped cells among `cells`: {cell: (gx, gz)} = ground y (down) change per unit
    along +x / +z (Driver 1 world axes), from Driver 2 surface samples 600 units off
    the centre; only where the four samples lie on one plane (not a step)."""
    from d2surface import Surface
    surf = Surface(D2_LEV)
    half_x, half_z = world["across"] // 2 * CELL, world["down"] // 2 * CELL
    out = {}
    for (col, row) in cells:
        gy0 = choice[(col, row)][0]
        gy0 = 0 if abs(gy0) < HEIGHT_DEADBAND else gy0
        x0, z0 = col * ROAD_UNIT - half_x, half_z - row * ROAD_UNIT
        s = []
        for ox, oz in ((300, 0), (-300, 0), (0, 300), (0, -300)):
            dx, dz = ws.to_d2(x0 + ox, z0 + oz)
            lv = [int(round(-h * ws.SCALE)) for h, t in surf.levels(dx, dz) if t not in (6, 9)]
            # kerbs / raised sidewalks (-22) are street level, as in the written heights:
            # they tilted the street cells beside them by ~23 (user R8, 604,794)
            lv = [0 if abs(y) < HEIGHT_DEADBAND else y for y in lv]
            lv = [y for y in lv if abs(y - gy0) < 450]
            s.append(min(lv, key=lambda y: abs(y - gy0)) if lv else None)
        g = []
        for p, m in ((s[0], s[1]), (s[2], s[3])):     # per axis: both samples on one plane through the centre
            ok = p is not None and m is not None and abs(p + m - 2 * gy0) <= 40
            g.append((p - m) / 600.0 if ok else 0.0)
        gx, gz = g
        if max(abs(gx), abs(gz)) > SLOPE_MAX:
            continue                     # an embankment / wall face (45 deg at 7_16 rolled cars), not a road
        if max(abs(gx), abs(gz)) * ROAD_UNIT >= SLOPE_MIN:
            out[(col, row)] = (gx, gz)
    return out


FULL = (-750, -750, 750, 750)             # a plane's footprint inside the cell (px0, pz0, px1, pz1)


def refine_ramps(world, grid, choice, kinds):
    """Narrow or diagonal ramps (D2 ramp/deck surfaces) are missed by the cell-centre
    sample: the cell reads as the ground beside them and the car drives at ground
    level inside the ramp. For ground cells that carry or neighbour a level 100..1400
    away from their own, the 3 x 3 cells around them are sampled at 9 points each and
    the non-ground samples of the nearest such level are fitted with a plane; it is
    added to the cell as an extra sloped plane (the plugin takes the highest plane
    below the wheel, so a car on the ramp follows it, a car on the ground beside it
    stays down). Returns {cell: (height at the centre, gx, gz)}."""
    from d2surface import Surface
    surf = Surface(D2_LEV)
    half_x, half_z = world["across"] // 2 * CELL, world["down"] // 2 * CELL
    land = lambda k: k in choice and choice[k][1] not in (6, 9) and kinds.get(k) != "inside"
    cand = set()
    for k, (y, t) in choice.items():
        if not land(k) or t not in GROUND_TYPES:
            continue
        near = []
        for dc in range(-2, 3):                          # a 5 x 5 window: narrow ramps are missed
            for dr in range(-2, 3):                      # by every centre sample along their run
                n = (k[0] + dc, k[1] + dr)
                if land(n):
                    near += [L for L, tt in grid[n] if tt not in (6, 9) and tt not in GROUND_TYPES]
        if any(100 <= abs(L - y) <= 1400 for L in near):
            cand.add(k)
    samples = {}

    def cell_samples(col, row):
        if (col, row) not in samples:
            x0, z0 = col * ROAD_UNIT - half_x, half_z - row * ROAD_UNIT
            pts = []
            for ox in (-500, 0, 500):
                for oz in (-500, 0, 500):
                    dx, dz = ws.to_d2(x0 + ox, z0 + oz)
                    for h, t in surf.levels(dx, dz):
                        if t not in (6, 9) and t not in GROUND_TYPES:
                            pts.append((ox, oz, int(round(-h * ws.SCALE))))
            samples[(col, row)] = pts
        return samples[(col, row)]

    out = {}
    for (col, row) in cand:
        y0 = choice[(col, row)][0]
        pts = []
        for dc in (-1, 0, 1):
            for dr in (-1, 0, 1):
                pts += [(ox + dc * ROAD_UNIT, oz - dr * ROAD_UNIT, y) for ox, oz, y in cell_samples(col + dc, row + dr)]
        ramp = sorted((p for p in pts if 100 <= abs(p[2] - y0) <= 1400), key=lambda p: p[2])
        if len(ramp) < 4:
            continue
        best, cur = [], [ramp[0]]                     # the largest cluster of heights within 450
        for p in ramp[1:]:
            if p[2] - cur[-1][2] <= 450:
                cur.append(p)
            else:
                best = max(best, cur, key=len); cur = [p]
        best = max(best, cur, key=len)
        if len(best) < 4:
            continue
        n = len(best)
        mx = sum(p[0] for p in best) / n; mz = sum(p[1] for p in best) / n; my = sum(p[2] for p in best) / n
        sxx = sum((p[0] - mx) ** 2 for p in best); szz = sum((p[1] - mz) ** 2 for p in best)
        sxy = sum((p[0] - mx) * (p[2] - my) for p in best); szy = sum((p[1] - mz) * (p[2] - my) for p in best)
        gx = sxy / sxx if sxx > 1e-6 else 0.0
        gz = szy / szz if szz > 1e-6 else 0.0
        yc = int(round(my - gx * mx - gz * mz))       # the ramp plane at the cell centre
        out[(col, row)] = (yc, gx, gz, FULL)
    print("road map: %d ground cells get a fitted ramp plane (of %d candidates)" % (len(out), len(cand)))
    return out


def surface_planes(world, grid, choice, kinds):
    """ROADSURF planes per cell, relative to the cell's written height: the cell's
    own level (sloped where the D2 surface slopes) plus every level of its own or
    its 4 neighbours that lies SURF_SEP or more away (deck over street, trench under
    a bridge, ground on a trench wall, lane beside a ramp): with the engine patch the
    wheel takes the plane nearest its height, so cars above and below both keep
    their road. The own plane first (the engine takes the first hit while the
    plugin is idle), then lowest first.
    Returns {cell: [(a, c, d), ...]} with d in y-down units."""
    switches = world.get("switches", {}) if "no_d2switch" not in EXPERIMENT else {}
    if world.get("deck_switch"):                         # C17 deck fix: the deck only for a car already near it
        switches = {k: dict(v) for k, v in switches.items()}
        for k, sw in world["deck_switch"].items():
            switches.setdefault(k, {}).update(sw)
    xslopes = world.get("extra_slopes", {})          # trench end ramps (C20), also in covered cells
    filled = world.get("filled", set())            # covered / hole cells the trench pass made floor
    land = {k: v for k, v in choice.items() if v[1] not in (6, 9) and (kinds.get(k) != "inside" or k in xslopes or k in filled)}
    hw ={k: written_height(v[0]) for k, v in land.items()}
    cand = set()
    for k, h in hw.items():
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            hn = hw.get((k[0] + d[0], k[1] + d[1]))
            if hn is not None and 40 <= abs(hn - h) < 450:
                cand.add(k)
    slopes = cell_slopes(world, cand, choice)
    slopes.update(xslopes)
    if "keep_rampfoot" not in EXPERIMENT:
        # a ramp's end cell centred at the flat level beside it: its slope only dips under
        # / rises over that level (the foot of underbridge2's slip road, ~90 under the
        # trench floor): flat. Cells part-way up keep their slope (deckramp_w)
        for k in [k for k in slopes if k in hw]:
            reach_k = (abs(slopes[k][0]) + abs(slopes[k][1])) * 750
            if any(n in hw and n not in slopes and abs(hw[n] - hw[k]) < min(reach_k, 40)
                   for n in ((k[0] + 1, k[1]), (k[0] - 1, k[1]), (k[0], k[1] + 1), (k[0], k[1] - 1))):
                del slopes[k]
    ramps = refine_ramps(world, grid, choice, kinds)
    borrowed = 0                                   # ground beside a sloped ramp that took the ramp's
    for k, h in hw.items():                        # height (wall-top rule): follow its slope too
        if k in slopes or any(abs(written_height(y) - h) < SURF_SEP for y, t in grid[k] if t not in (6, 9)):
            continue
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (k[0] + d[0], k[1] + d[1])
            if n in slopes and hw.get(n) == h:
                slopes[k] = slopes[n]
                borrowed += 1
                break
    bed = world.get("bed", set())
    rail = world.get("rail", set())                 # rail cuts feed no guard planes
    # a bank by the water (not deeper than the water itself: a trench / lower road along
    # the river stays a guard source)
    wet = lambda n: hw[n] < WATER_LEVEL + 100 and (n in bed or any(
        kinds.get((n[0] + i, n[1] + j)) in ("water", "void") for i in range(-2, 3) for j in range(-2, 3)))
    planes, nmulti = {}, 0
    for k, h in hw.items():
        own = {written_height(y) for y, t in grid[k] if t not in (6, 9)}
        levels = set(own)
        tilt = {}                                   # level -> (a, c) of a sloped neighbour whose plane it is
        dry_levels = set()                          # neighbour levels away from the water's edge
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (k[0] + d[0], k[1] + d[1])
            if n in land and n in slopes and "keep_rampext" not in EXPERIMENT:
                # a ramp's plane only on the ramp's own cells (user R8: no second Y plane
                # over other drivable ground; an invisible ramp beside underbridge's real
                # one): of a sloped neighbour only its other real levels (a deck above it)
                other = [L for L in (written_height(y) for y, t in grid[n] if t not in (6, 9))
                         if abs(L - hw[n]) >= SURF_SEP]
                levels.update(other)
                if not wet(n) and n not in rail:
                    dry_levels.update(other)
            elif n in land:
                levels.update(written_height(y) for y, t in grid[n] if t not in (6, 9))
                if not wet(n) and n not in rail:
                    dry_levels.update(written_height(y) for y, t in grid[n] if t not in (6, 9))
                    dry_levels.add(hw[n])
                if n in slopes:                     # the neighbour's own plane at OUR centre
                    ngx, ngz = slopes[n]
                    at_centre = hw[n] + int(round((-ngx * d[0] + ngz * d[1]) * ROAD_UNIT))   # we are at (-dx, +dz) cells from n (row+1 = south = -z)
                    levels.add(at_centre)
                    tilt[at_centre] = (ngx, ngz)
                else:
                    levels.add(hw[n])
        if k in ramps and "keep_rampext" in EXPERIMENT:   # a narrow ramp crossing this ground cell
            # (off, user R8: as a full-cell plane it reached far beyond the ramp's footprint)
            ry, rgx, rgz, rbox = ramps[k]
            rw = written_height(ry)
            levels.add(rw); tilt[rw] = (rgx, rgz); own.add(rw)
        stacked = any(abs(L - h) >= SURF_SEP for L in own)
        gx, gz = slopes.get(k, (0.0, 0.0))
        reach = int((abs(gx) + abs(gz)) * 750)               # the own plane's rise within the cell
        sep = SURF_SEP + 2 * reach                           # a ramp must not see the street beside it
        ds = [0]
        for L in sorted(levels, reverse=True):               # lowest (largest y-down) first
            dd = L - h
            # sloped continuations may be close, and so may the cell's own street over a
            # trench end ramp (a street car there keeps its street, C20; not the trench
            # level below that the ramp replaced)
            if dd and L not in own and "keep_guards" not in EXPERIMENT and (
                    dd < GUARD_MIN_BELOW or L not in dry_levels or (gx, gz) != (0.0, 0.0)):
                # (a ramp cell carries its own plane only: user R10, underbridge2)
                # user rule (R9): no stacked drivable planes unless a bridge (the cell's own
                # D2 levels) or needed to drive: only a sunken road's floor beside this cell
                # (a car along a trench wall), not levels above it, nor banks by the water
                continue
            if dd and (abs(dd) >= sep or L in tilt or (k in xslopes and L in own and dd < 0)) and all(abs(dd - e) >= 40 for e in ds):
                if L in tilt and L not in own and "keep_lifttilt" not in EXPERIMENT:
                    # a sloped neighbour's plane continued over this cell: the plugin takes a
                    # plane up to 100 above the wheel, so a part above the own plane and within
                    # 128 of it (a ramp that meets this street, extended past its end) lifts
                    # every car here: 70-90 above the street at c20_p2n (user, 2026-10-12).
                    # Continuations wholly below (a lower road running under) or far above
                    # (a deck ramp's) stay
                    tgx, tgz = tilt[L]
                    ext = (abs(tgx - gx) + abs(tgz - gz)) * 750
                    if -dd + ext > 0 and -dd - ext < 128:
                        continue
                ds.append(dd)
        if len(ds) == 1 and (gx, gz) == (0.0, 0.0):
            continue
        # priority: 0 = the cell itself is stacked (deck over street, trench under a bridge),
        # 1 = sloped own plane (ramps), 2 = only neighbour levels (guards beside decks/trenches).
        # Surface ids are scarce (plain model ids < 900): guards and ramps keep only the
        # nearest neighbour level, stacked cells keep every level.
        prio = 0 if stacked else (1 if (gx, gz) != (0.0, 0.0) else 2)
        if prio == 0:                                        # stacked: its own levels only
            ds = [dd for dd in ds if dd == 0 or any(abs(L - h - dd) < SURF_Q for L in own)]
        elif len(ds) > 2:                                    # nearest level, plus the deepest level below
            keep = [0, min((dd for dd in ds if dd), key=abs)]  # (a trench beside an embankment's end: a car
            deep = max(ds)                                       # at trench depth needs that plane, C20 wall)
            if deep >= 600 and abs(keep[1]) < 300 and "guard_nearest" not in EXPERIMENT:
                keep.append(deep)
            ds = keep
        # the cell's own plane first, then lowest first: while the plugin does not select
        # (level start, 60 vblanks after a spool) the engine takes the first plane, and
        # with full-cell guards a lowest-first order spawned cars on the level under a
        # bridge (hs_lift_6_9: y -2396 instead of the street)
        ds.sort(key=lambda dd: (dd != 0, -dd))
        pl, ex = [], []
        swr = {written_height(L): (h - sw) or 1 for L, sw in switches.get(k, {}).items()}   # pad = switch y up + cell height (0 = none: older levels)
        for dd in ds:
            tgx, tgz = (gx, gz) if dd == 0 else tilt.get(h + dd, (0.0, 0.0))
            a = int(round(-tgx * 4096 / SLOPE_Q)) * SLOPE_Q * SLOPE_SIGN[0]
            c = int(round(-tgz * 4096 / SLOPE_Q)) * SLOPE_Q * SLOPE_SIGN[1]
            # every plane covers the whole cell (user, 2026-10-12): the plugin swaps only the
            # plane words into slot 0, so a third-cell guard it picked took over the full
            # cell (lift at the slip road beside the trench); with identical footprints its
            # height rule decides alone: lower levels run under the upper ones, a car keeps
            # the highest plane not above its wheel (a car leaving a street edge floats to
            # the end of that cell, then drops). Guards continue the neighbour's road as is
            # the cell's own levels exact (8 = the road map's height step: a street over a
            # trench end ramp rounded to 64 sat 16 off = kerb steps at C20, user 175535);
            # guards coarser (surface ids are scarce); the merge moves only guards
            exact = dd == 0 or (h + dd) in own
            q = (OWN_Q if exact else GUARD_Q) if "own_q64" not in EXPERIMENT else (SURF_Q if exact else GUARD_Q)
            pl.append((a, c, 0 if dd == 0 else int(round(dd / q)) * q, FULL, swr.get(h + dd, NO_SWITCH) if exact else NO_SWITCH))
            ex.append(exact)
        planes[k] = (prio, pl, tuple(ex))
        nmulti += len(ds) > 1
    print("road map: ROADSURF planes on %d cells (%d with several levels, %d sloped of %d candidates, %d borrowed slopes)"
          % (len(planes), nmulti, len(slopes), len(cand), borrowed))
    if "keep_fullcells" not in EXPERIMENT:
        split_cells(world, grid, hw, land, slopes, planes)
    import polish_slopes
    if polish_slopes.ENABLED:                     # Polish C37: Driver 2's sloped planes at any angle (CHI_POLISH_SLOPES)
        polish_slopes.apply(world, hw, planes, sys.modules[__name__])
    return planes


SPLIT_TOL = 150               # a sample's D2 level matches a cell's level within this (plus a ramp's rise)
SPLIT_SAMPLES = (-562, -187, 187, 562)   # 4 x 4 points inside the cell (local px east, pz north)


SPLIT_STACK = os.environ.get("CHI_POLISH_SPLITSTACK", "1") == "1"   # Polish C23 (default since b15): stacked own level counts as own (trench under a cover)


def split_samples(world, keys):
    """Top D2 levels (y down, scaled) at 4 x 4 points of each cell (cached)."""
    import pickle, hashlib
    from d2surface import Surface
    key = hashlib.md5(open("d2surface.py", "rb").read() + repr((sorted(keys), world["across"], world["down"],
                                                                 ws.SCALE, SPLIT_SAMPLES, D2_LEV)).encode()).hexdigest()[:8]
    cache = os.path.join(inputs.cache_dir(), "split_samples_%s.pkl") % key
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    surf = Surface(D2_LEV)
    half_x, half_z = world["across"] // 2 * CELL, world["down"] // 2 * CELL
    out = {}
    for col, row in keys:
        smp = {}
        for px in SPLIT_SAMPLES:
            for pz in SPLIT_SAMPLES:
                dx, dz = ws.to_d2(col * ROAD_UNIT - half_x + px, half_z - row * ROAD_UNIT + pz)
                smp[(px, pz)] = sorted({int(round(-h * ws.SCALE)) for h, t in surf.levels(dx, dz) if t not in (6, 9)})
        out[(col, row)] = smp
    pickle.dump(out, open(cache, "wb"))
    return out


# C37 (14.10.): diagonal level boundaries (embankments, trench walls, deck edges) as a straight cut
# through the cell instead of whole-cell steps: the neighbour's part as 1-3 triangles (the engine's
# 3-vertex test works at any angle; 4-vertex polygons are boxes), the cell's own level as a full-cell
# box after them. Angle in 15-degree steps, offset on a 250-unit grid where it fits, heights in
# 100-unit steps (fewer distinct surfaces: ids are scarce). CHI_DIAG=1.
DIAG = os.environ.get("CHI_DIAG", "") == "1"
DIAG_Q = 100


def diagonal_cut(cls):
    """cls: {(px, pz): "O" | "N"} for the cell's sample points. The neighbour part of the best straight
    cut that separates O from N, as triangles (6-tuples, local coordinates), or None."""
    import math
    if "O" not in cls.values() or "N" not in cls.values():
        return None
    best = None
    for th in range(0, 180, 15):
        cx, cz = math.cos(math.radians(th)), math.sin(math.radians(th))
        proj = {pt: pt[0] * cx + pt[1] * cz for pt in cls}
        o = [v for pt, v in proj.items() if cls[pt] == "O"]
        nn = [v for pt, v in proj.items() if cls[pt] == "N"]
        for sgn in (1, -1):                               # N on the + side (sgn 1) or the - side
            lo, hi = (max(o), min(nn)) if sgn > 0 else (max(nn), min(o))
            if lo >= hi:
                continue
            gap = hi - lo
            if th % 90 == 0:
                continue                                  # axis cuts are the plain split's job
            if best is None or gap > best[0]:
                best = (gap, th, sgn, lo, hi)
    if best is None:
        return None
    gap, th, sgn, lo, hi = best
    mid = (lo + hi) / 2
    snap = round(mid / 250) * 250
    off = snap if lo < snap < hi else round(mid / 50) * 50
    cx, cz = math.cos(math.radians(th)), math.sin(math.radians(th))
    # clip the cell square to the neighbour's side: sgn * (p . n - off) > 0
    sq = [(-750, -750), (750, -750), (750, 750), (-750, 750)]
    f = lambda p: sgn * (p[0] * cx + p[1] * cz - off)
    poly = []
    for i in range(4):
        p, q = sq[i], sq[(i + 1) % 4]
        if f(p) >= 0:
            poly.append(p)
        if (f(p) >= 0) != (f(q) >= 0):
            t = f(p) / (f(p) - f(q))
            poly.append((int(round(p[0] + t * (q[0] - p[0]))), int(round(p[1] + t * (q[1] - p[1])))))
    if len(poly) < 3:
        return None
    tris = []
    for i in range(1, len(poly) - 1):
        (x0, z0), (x1, z1), (x2, z2) = poly[0], poly[i], poly[i + 1]
        if (x1 - x0) * (z2 - z0) - (z1 - z0) * (x2 - x0) > 0:   # same winding as the verified prototype
            (x1, z1), (x2, z2) = (x2, z2), (x1, z1)
        tris.append((x0, z0, x1, z1, x2, z2))
    return tris


def split_cells(world, grid, hw, land, slopes, planes):
    """User rule (R12, 2026-10-13): only what is visible may be drivable. A road-map cell is
    1500 units wide; where a level step runs through it (a narrow ramp beside the ground under
    a bridge, a bridge deck whose edge ends inside a rail cut's cell) one full-cell level made
    invisible ground drivable or left a visible deck edge without a floor. Such a cell gets two
    side-by-side planes instead, each over the part where D2 shows that level: its own level
    and its neighbour's. The parts do not overlap, so the engine picks the plane by position
    (4-vertex polygons: box test) and the plugin's height rule stays out (surface info 2).
    Only clean splits along the axis towards that neighbour; cells with their own stacked
    levels keep the height rule."""
    cands = {}
    for k, h in hw.items():
        if k in planes and planes[k][0] == 0:
            continue                                   # stacked (bridge over street): height rule
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (k[0] + d[0], k[1] + d[1])
            if n in land and abs(hw[n] - h) >= SURF_SEP:
                cands.setdefault(k, []).append((d, n))
    samples = split_samples(world, list(cands))
    nsplit = ndiag = ntri = 0
    for k, nbrs in cands.items():
        h = hw[k]
        gx, gz = slopes.get(k, (0.0, 0.0))
        smp = samples[k]
        own_at = lambda px, pz: h + gx * px + gz * pz               # gx, gz: y-down gradients (+x east, +z north)
        for d, n in nbrs:
            hn = hw[n]
            ngx, ngz = slopes.get(n, (0.0, 0.0))
            # the neighbour's plane in our local frame: n's centre is at (d0 * 1500, -d1 * 1500)
            cx, cz = d[0] * ROAD_UNIT, -d[1] * ROAD_UNIT
            nb_at = lambda px, pz: hn + ngx * (px - cx) + ngz * (pz - cz)
            tol = SPLIT_TOL + int((abs(gx) + abs(gz) + abs(ngx) + abs(ngz)) * 750)
            cls = {}
            for (px, pz), lv in smp.items():
                if not lv:
                    cls[(px, pz)] = "X"; continue
                top = min(lv)                           # the visible level from above
                o, m = abs(top - own_at(px, pz)) <= tol, abs(top - nb_at(px, pz)) <= tol
                if SPLIT_STACK and not o and any(abs(l - own_at(px, pz)) <= tol for l in lv):
                    o = True                            # Polish C23: own level runs on under a cover (stacked): not the neighbour's part
                cls[(px, pz)] = "O" if o and not m else "N" if m and not o else "X"
            if "X" in cls.values():
                continue
            ax = 0 if d[0] else 1                       # axis of the step: px for east/west, pz for north/south
            sgn = d[0] if d[0] else -d[1]               # +1: the neighbour lies at +px / +pz
            on = [pt[ax] * sgn for pt, c in cls.items() if c == "O"]
            nn = [pt[ax] * sgn for pt, c in cls.items() if c == "N"]
            if not on or not nn or max(on) >= min(nn):
                if DIAG and not any(c == "X" for c in cls.values()):
                    tri = diagonal_cut(cls)             # C37: a straight diagonal boundary instead
                    if tri:
                        a = int(round(-gx * 4096 / SLOPE_Q)) * SLOPE_Q * SLOPE_SIGN[0]
                        c = int(round(-gz * 4096 / SLOPE_Q)) * SLOPE_Q * SLOPE_SIGN[1]
                        na = int(round(-ngx * 4096 / SLOPE_Q)) * SLOPE_Q * SLOPE_SIGN[0]
                        nc = int(round(-ngz * 4096 / SLOPE_Q)) * SLOPE_Q * SLOPE_SIGN[1]
                        dn = int(round((nb_at(0, 0) - h) / DIAG_Q)) * DIAG_Q
                        # neighbour part as triangles first (first match wins), then the cell's own
                        # level over the whole cell for the rest
                        pl = [(na, nc, dn, t, NO_SWITCH) for t in tri] + [(a, c, 0, FULL, NO_SWITCH)]
                        planes[k] = (0, pl, (True,) * len(pl))
                        ndiag += 1
                        ntri += len(tri)
                        if os.environ.get("CHI_DIAG_LIST") and (ndiag <= 40 or os.environ["CHI_DIAG_LIST"] == "all"):
                            half_x, half_z = world["across"] // 2 * CELL, world["down"] // 2 * CELL
                            x1, z1 = k[0] * ROAD_UNIT - half_x, half_z - k[1] * ROAD_UNIT
                            rc = world.get("road_cells", set())
                            nroad = sum((k[0] + i, k[1] + j) in rc for i in (-1, 0, 1) for j in (-1, 0, 1))
                            print("C37 cell %s D1 %d,%d D2 %s step %d road %d" % (k, x1, z1, tuple(int(v) for v in ws.to_d2(x1, z1)), dn, nroad))
                        if os.environ.get("CHI_DIAG_CELL") == "%d,%d" % k:
                            print("C37 cell %s h %d own slope %s nb %s hn %d dn %d tri %s" % (k, h, (gx, gz), d, hn, dn, tri))
                            for (px, pz) in sorted(cls, key=lambda p: (-p[1], p[0])):
                                print("  %6d %6d %s %s" % (px, pz, cls[(px, pz)], sorted(smp[(px, pz)])))
                        break
                continue                                # not separable along the axis
            cut = (max(on) + min(nn)) // 2 * sgn        # boundary in local coordinates
            lo, hi = (-750, cut) if sgn > 0 else (cut, 750)
            olo, ohi = lo, hi
            nlo, nhi = (cut, 750) if sgn > 0 else (-750, cut)
            foot = lambda a0, a1: (a0, -750, a1, 750) if ax == 0 else (-750, a0, 750, a1)
            a = int(round(-gx * 4096 / SLOPE_Q)) * SLOPE_Q * SLOPE_SIGN[0]
            c = int(round(-gz * 4096 / SLOPE_Q)) * SLOPE_Q * SLOPE_SIGN[1]
            na = int(round(-ngx * 4096 / SLOPE_Q)) * SLOPE_Q * SLOPE_SIGN[0]
            nc = int(round(-ngz * 4096 / SLOPE_Q)) * SLOPE_Q * SLOPE_SIGN[1]
            # the neighbour plane's offset at OUR centre (y down, relative to our height)
            dn = int(round(nb_at(0, 0) - h))
            dn = int(round(dn / OWN_Q)) * OWN_Q
            planes[k] = (0, [(a, c, 0, foot(olo, ohi), NO_SWITCH), (na, nc, dn, foot(nlo, nhi), NO_SWITCH)], (True, True))
            nsplit += 1
            break
    print("road map: %d cells split between two levels (visible parts only; %d candidates)" % (nsplit, len(cands)))
    if DIAG:
        print("road map: C37 %d cells split diagonally (%d triangles)" % (ndiag, ntri))


def _rot_plane(pl, k):
    """Plane (a, c, d, (x0, z0, x1, z1), switch) in world-local coords expressed in the surface
    frame of rotation k (the engine maps the point (X, Z) to R_k(X, Z) before testing)."""
    a, c, d, foot, sw = pl
    tri = len(foot) == 6                                # C37: triangle (x0, z0, x1, z1, x2, z2)
    pts = [foot[0:2], foot[2:4], foot[4:6]] if tri else \
        [(foot[0], foot[1]), (foot[0], foot[3]), (foot[2], foot[3]), (foot[2], foot[1])]
    if k == 1:
        a, c = -c, a; pts = [(-z, x) for x, z in pts]
    elif k == 2:
        a, c = -a, -c; pts = [(-x, -z) for x, z in pts]
    elif k == 3:
        a, c = c, -a; pts = [(z, -x) for x, z in pts]
    if tri:
        return (a, c, d, tuple(v for p in pts for v in p), sw)
    xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    return (a, c, d, (min(xs), min(zs), max(xs), max(zs)), sw)


def _canonical(pl):
    """The rotation k (0-3) and plane list whose representation is smallest."""
    best = None
    for k in range(4):
        r = tuple(_rot_plane(p, k) for p in pl)
        if best is None or r < best[1]:
            best = (k, r)
    return best


import polish_slopes as _PSLOPES


def roadsurf_lump(planes, ids, force=None):
    """Driver 1 ROADSURF lump (int count; SURFACEINFO {type, info, heading, numpolys}
    + SIPOLY 52 B {xz[4] int pairs, plane a b c d, nverts, pad}) with one surface per
    distinct plane list; info = 1 marks them for the height-aware engine patch.
    Returns (bytes, {cell: type id}). Plane (a, b, c) is the unit normal x 4096."""
    import collections, math
    groups, best, canon = collections.Counter(), {}, {}
    exact = {}                                 # per surface: which planes are the cells' own levels
    force = force or {}
    for k, v in planes.items():
        pr, p = v[0], v[1]
        if k in force:                         # road cell: the rotation is its lane's direction
            rot = force[k]
            key = tuple(_rot_plane(q, rot) for q in p)
        else:
            rot, key = _canonical(p)           # (rotation keeps the plane order)
        canon[k] = (rot, key)
        groups[key] += 1
        best[key] = min(best.get(key, 9), pr)
        m = v[2] if len(v) > 2 else (False,) * len(p)
        exact[key] = tuple(x or y for x, y in zip(exact.get(key, m), m))
    cap = min(SURF_MAX, len(ids))
    # over the id cap: a rare surface joins a more common one with the same slopes and
    # footprints whose plane offsets differ by <= tol (only as coarse as needed). The
    # cells' own levels move by <= OWN_TOL at most and no guard crosses the own plane
    # (the signature holds each offset's sign); guards move by <= tol
    sign = lambda d: (d > 0) - (d < 0)
    sig = lambda g: tuple((a, c, f, sign(d), e, w) for (a, c, d, f, w), e in zip(g, exact[g]))
    merged, used, per_tol = {}, None, {}
    for tol in (64, 128, 192, 256):
        if len(groups) <= cap:
            break
        bucket = collections.defaultdict(set)
        for g in groups:
            bucket[sig(g)].add(g)
        for g in sorted(groups, key=lambda g: groups[g]):
            if len(groups) <= cap:
                break
            if g not in groups:
                continue
            cand = [h for h in bucket[sig(g)] if h != g and groups[h] >= groups[g]
                    and all(abs(pd - qd) <= (min(tol, OWN_TOL) if e else tol)
                            for (_, _, pd, _, _), (_, _, qd, _, _), e in zip(g, h, exact[g]))]
            if not cand:
                continue
            h = max(cand, key=lambda h: groups[h])
            groups[h] += groups.pop(g)
            best[h] = min(best[h], best.pop(g))
            bucket[sig(g)].discard(g)
            merged[g], used = h, tol
            per_tol[tol] = per_tol.get(tol, 0) + 1
    if merged:
        def final(g):
            while g in merged:
                g = merged[g]
            return g
        canon = {k: (rot, final(key)) for k, (rot, key) in canon.items()}
        print("road map: %d surfaces merged into similar ones (guard offsets within %d; per step %s)" % (len(merged), used, per_tol))
    order = sorted(groups, key=lambda g: (best[g], -groups[g]))
    if len(groups) > cap:
        lost = order[cap:]
        print("road map: %d distinct surfaces, keeping %d (dropped: %d cells, worst priority %d)"
              % (len(groups), cap, sum(groups[g] for g in lost), min(best[g] for g in lost)))
    keep = order[:cap]
    sid = {g: ids[i] for i, g in enumerate(keep)}
    out = bytearray(struct.pack("<i", len(keep)))
    for g in keep:
        out += struct.pack("<4h", sid[g], 1 if all(f == FULL for _, _, _, f, _ in g) else 2, 0, len(g))
        for a, c, d, foot, sw in g:
            n = math.sqrt(a * a + 4096.0 * 4096.0 + c * c)
            if len(foot) == 6:                              # C37 triangle: 3 points (last repeated), nverts 3
                out += struct.pack("<8i", *foot, foot[4], foot[5])
            else:
                x0, z0, x1, z1 = foot
                out += struct.pack("<8i", x0, z0, x0, z1, x1, z1, x1, z0)
            if _PSLOPES.ENABLED and _PSLOPES.EXACT:        # Polish C37: a, c are the engine's gradients (no / b)
                out += struct.pack("<4i", *_PSLOPES.plane_words(a, c), d)
            else:
                out += struct.pack("<4i", int(round(a * 4096 / n)), int(round(4096 * 4096 / n)), int(round(c * 4096 / n)), d)
            out += struct.pack("<hh", 3 if len(foot) == 6 else 4, sw)   # pad: the D2 level switch height (plugin)
    cells = {k: (sid[key], rot) for k, (rot, key) in canon.items() if key in sid}
    proto = os.environ.get("CHI_PROTO_TRI")        # C37 prototype: "col,row" gets two triangles
    if proto and len(keep) < len(ids):              # split along the cell's diagonal, one raised by 150
        k = tuple(int(v) for v in proto.split(","))
        x0, z0, x1, z1 = FULL
        out[0:4] = struct.pack("<i", len(keep) + 1)
        out += struct.pack("<4h", ids[len(keep)], 0, 0, 2)          # info 0: the plugin leaves it alone
        for tri, d in ((((x0, z0), (x0, z1), (x1, z1)), 0), (((x0, z0), (x1, z1), (x1, z0)), -150)):
            out += struct.pack("<8i", *[v for p in tri + (tri[-1],) for v in p])
            out += struct.pack("<4i", 0, 4096, 0, d) + struct.pack("<hh", 3, 0)
        cells[k] = (ids[len(keep)], 0)
        print("road map: C37 prototype: cell %s gets two triangles (surface %d)" % (k, ids[len(keep)]))
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
    if "keep_bed" not in EXPERIMENT:
        # Driver 2's river / lake bed and quay slopes run down under the water (1700 to
        # 4500 below the street, type 0) next to water: as road the car drove down
        # them under the water surface instead of drowning (QA-2 region 7,2: slow
        # slide to y -2082; hs_lift_6_9's "lower road" under the bridge, 2583). The
        # deepest road is the trench (1352). Such levels go; a cell with none left is water
        grid, bed = dict(grid), 0
        world["bed"] = set()                       # (the trench holes pass keeps them water)
        for k, lv in list(grid.items()):
            if any(t not in (6, 9) and y >= BED_DEPTH for y, t in lv) and any(
                    kinds.get((k[0] + i, k[1] + j)) in ("water", "void") for i in range(-3, 4) for j in range(-3, 4)):
                grid[k] = [(y, t) for y, t in lv if t in (6, 9) or y < BED_DEPTH] or [(WATER_Y, 9)]
                bed += 1
                world["bed"].add(k)
        print("road map: %d cells lose a river/lake bed level (water there)" % bed)
    if os.environ.get("CHI_BANK_WATER", "1") != "0":     # default since b16 (14.10.)
        # C28 (14.10.): D2's shore banks lie a little BELOW the water surface (NW lakeshore: a strip at
        # 1176 between the street and the lake at 1080). As ground the car dropped into them and sat
        # under the water line without drowning (stuck, FAN r14 shorewall y -997). Ground cells whose
        # levels all lie under the water surface but above the trench floor (1352: Lower Wacker, rail
        # trenches stay) become water, flooding outward from water cells through such cells only
        lo, hi = WATER_Y + 40, RAIL_FLOOR - 100
        wet = {k for k, v in kinds.items() if v == "water"} | {
            k for k, lv in grid.items() if lv and all(t in (6, 9) for y, t in lv)}
        bank = lambda k: bool(grid.get(k)) and all(t not in (6, 9) and lo <= y < hi for y, t in grid[k])
        front = [k for k in grid if bank(k) and any((k[0] + i, k[1] + j) in wet for i in (-1, 0, 1) for j in (-1, 0, 1))]
        seen, depth, nb = set(front), dict.fromkeys(front, 0), 0
        while front:
            k = front.pop()
            grid[k] = [(WATER_Y, 9)]
            nb += 1
            for n in ((k[0] + 1, k[1]), (k[0] - 1, k[1]), (k[0], k[1] + 1), (k[0], k[1] - 1)):
                if n not in seen and bank(n):
                    seen.add(n); depth[n] = depth[k] + 1; front.append(n)
        world.setdefault("bank_water", set()).update(seen)
        print("road map: C28 %d shore-bank cells under the water surface become water (max %d cells from the water)"
              % (nb, max(depth.values() or [0])))
    if "keep_edgecentre" not in EXPERIMENT:
        # a road cell is one level, taken at its centre: at a quay or bridge edge a cell
        # that is mostly river read street and the car drove at street height over the
        # water (user R10, hs_lift_6_9). Land cells beside water whose 3 x 3 samples are
        # mostly water (>= EDGE_WATER_MIN of 9) become water, unless land runs straight
        # through the centre (a bridge / causeway across the cell)
        from d2surface import Surface
        surf = Surface(D2_LEV)
        half_x, half_z = world["across"] // 2 * CELL, world["down"] // 2 * CELL
        water_k = {k for k, v in kinds.items() if v == "water"}
        flipped = 0
        for k, lv in list(grid.items()):
            if not any(t not in (6, 9) for y, t in lv) or not any(
                    (k[0] + i, k[1] + j) in water_k for i in (-1, 0, 1) for j in (-1, 0, 1)):
                continue
            x0, z0 = k[0] * ROAD_UNIT - half_x, half_z - k[1] * ROAD_UNIT
            land = {}
            for i in (-1, 0, 1):
                for j in (-1, 0, 1):
                    lvs = surf.levels(*ws.to_d2(x0 + 500 * i, z0 + 500 * j))
                    land[(i, j)] = any(t not in (6, 9) for h, t in lvs)
            if sum(not v for v in land.values()) < EDGE_WATER_MIN:
                continue
            if all(land[(i, 0)] for i in (-1, 0, 1)) or all(land[(0, j)] for j in (-1, 0, 1)):
                continue                           # a strip through the centre: a bridge
            grid[k] = [(WATER_Y, 9)]
            world.setdefault("bed", set()).add(k)  # (stays water in the trench holes pass)
            flipped += 1
        print("road map: %d water-edge cells taken as water (mostly water inside)" % flipped)
    if os.environ.get("CHI_DECK_FIX", "1") != "0":       # default since b16 (14.10.)
        # C17 deck lift (14.10., after the water-edge rule, which would flip filled gaps back): D2's elevated Lake Shore Drive (curved planes, -1352) crosses the shore water
        # diagonally, so its deck-only cells touch only at their corners (a car on the deck dropped through the
        # gaps) and a car from the street entering one was snapped up 1352 (one level per cell). (1) Corner gaps:
        # of the two cells beside a diagonal deck-to-deck step without deck, the one on the x side gets the deck
        # level (water -> deck-only, land -> deck + its own level). (2) Deck-only cells beside land get that
        # land's levels as lower planes, so the plane selection keeps a car from the street low (under the deck
        # it reaches the next water cell and drowns, DROWN_EDGE) instead of lifting it onto the deck
        is_wet = lambda lv: bool(lv) and all(t in (6, 9) for y, t in lv)
        deck_of = lambda lv: min((y, t) for y, t in lv) if lv and not is_wet(lv) and min(y for y, t in lv) <= -500 else None
        deck_only = lambda lv: bool(lv) and not is_wet(lv) and all(y <= -500 for y, t in lv)
        if CITY.raised_ground:                    # M3 Havana: a raised quarter's ground is no deck (its shore cells got the
            _dk = deck_only                       # main level as an extra plane and wrote it: 2700 steps on the quarter's edge)
            deck_only = lambda lv: _dk(lv) and not all(any(abs(y - g) <= 150 for g in CITY.raised_ground) for y, t in lv)
        has_deck = lambda k, dy: any(abs(y - dy) <= 300 for y, t in grid.get(k, []) if t not in (6, 9))
        filled, gaps = 0, set()
        for k in sorted(k for k, lv in grid.items() if deck_only(lv)):
            dy, dt_ = deck_of(grid[k])
            for sx, sz in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                n = (k[0] + sx, k[1] + sz)
                if not (deck_only(grid.get(n, [])) and has_deck(n, dy)):
                    continue
                a, b = (k[0] + sx, k[1]), (k[0], k[1] + sz)
                if has_deck(a, dy) or has_deck(b, dy):
                    continue
                if is_wet(grid.get(a, [])) or not grid.get(a):
                    grid[a] = [(dy, dt_)]
                else:
                    grid[a] = sorted(set(grid[a]) | {(dy, dt_)})
                filled += 1
                gaps.add(a)
        lowered, inland = 0, 0
        for k in sorted(k for k, lv in grid.items() if deck_only(lv)):
            if not any(is_wet(grid.get((k[0] + i, k[1] + j), [])) and not (CITY.inside_follow and kinds.get((k[0] + i, k[1] + j)) == "inside")
                       for i in (-1, 0, 1) for j in (-1, 0, 1)):   # (M3 Havana: a building block is no water: its ramps up to the raised quarters kept the street)
                inland += 1                         # over land (building blocks): no invisible ground under it
                continue
            low = set()
            for n in ((k[0] + 1, k[1]), (k[0] - 1, k[1]), (k[0], k[1] + 1), (k[0], k[1] - 1)):
                for y, t in grid.get(n, []):
                    if t not in (6, 9) and y > -500 and not any(abs(y - q) < 100 for q, _ in low):
                        low.add((y, t))
            if low:
                grid[k] = sorted(set(grid[k]) | low)
                lowered += 1
                # its deck plane switches only 300 under the deck (the midpoint between the deck and a strip
                # 968 down lay just 190 above the street: a street car with a bounce took the deck, FAN r19)
                dy = min(y for y, t in grid[k])
                world.setdefault("deck_switch", {})[k] = {dy: dy + 300}
        print("road map: C17 deck fix: %d corner gaps filled, %d deck-only cells at the water get lower planes "
              "(%d deck-only cells inland left alone)" % (filled, lowered, inland))
    choice = {}
    for k, lv in grid.items():
        lv = sorted(lv, key=lambda hl: (hl[1] in (6, 9), abs(hl[0])))
        choice[k] = lv[0]
        if kinds.get(k) == "inside":           # building block: plain ground, no drowning
            choice[k] = (0, 0)
    if CITY.inside_follow:
        # M3 Havana (hav5): building blocks (no D2 surface, enclosed) take the level of the nearest
        # street cell instead of street level 0: a block inside a raised quarter at 0 dropped cars
        # 2700 at every block edge (Chicago: blocks stay 0, its streets are at 0)
        inside = {k for k in choice if kinds.get(k) == "inside"}
        front = sorted(k for k in inside if any(
            (n in choice and n not in inside and choice[n][1] not in (6, 9))
            for n in ((k[0] + 1, k[1]), (k[0] - 1, k[1]), (k[0], k[1] + 1), (k[0], k[1] - 1))))
        src = {}
        for k in front:
            ys = sorted((choice[n][0] for n in ((k[0] + 1, k[1]), (k[0] - 1, k[1]), (k[0], k[1] + 1), (k[0], k[1] - 1))
                         if n in choice and n not in inside and choice[n][1] not in (6, 9)), key=abs)
            src[k] = ys[0]
        done = set(front)
        while front:
            nxt = []
            for k in front:
                choice[k] = (src[k], 0)
                for n in ((k[0] + 1, k[1]), (k[0] - 1, k[1]), (k[0], k[1] + 1), (k[0], k[1] - 1)):
                    if n in inside and n not in done:
                        done.add(n); src[n] = src[k]; nxt.append(n)
            front = nxt
        print("road map: %d building-block cells follow their nearest street's level (%d raised)"
              % (len(done), sum(1 for k in done if choice[k][0] <= -HEIGHT_DEADBAND)))
    if "keep_rail" not in EXPERIMENT:
        # rail cuts (user R10: the trench under c20_p2n's bridge is railway): a bridge
        # over it keeps only its street, the rail floor stays but feeds no guard planes
        world["rail"] = set()
        for seed in RAIL_CUTS:
            todo = [seed] if seed in grid else []
            seen = set(todo)
            while todo:
                k = todo.pop()
                for dd_ in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    n = (k[0] + dd_[0], k[1] + dd_[1])
                    if n not in seen and any(t not in (6, 9) and y >= 600 for y, t in grid.get(n, [])):
                        seen.add(n); todo.append(n)
            world["rail"] |= seen
        for k in world["rail"]:
            top = [(y, t) for y, t in grid[k] if t not in (6, 9) and y < 600]
            if top:                                    # a bridge across the cut
                grid[k] = top
        print("road map: %d rail cut cells (bridges over them keep the street only)" % len(world["rail"]))
        # rail inclines (the L leaving the freeway trench): Driver 2 has a surface there but
        # fences them off; here they connected the trench with the street (user R8,
        # 19:14 snapshots). Their cells become trench floor: no way up, no way down
        for k in RAIL_INCLINES:
            if k in choice:
                grid[k] = [(RAIL_FLOOR, 0)]
                choice[k] = (RAIL_FLOOR, 0)
        print("road map: %d rail incline cells blocked" % sum(k in choice for k in RAIL_INCLINES))
    if "no_trench" not in EXPERIMENT:
        trench_rule(world, grid, choice, kinds)
    world["extra_slopes"] = trench_ends(world, grid, choice, kinds) if "no_trenchends" not in EXPERIMENT else {}
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
        world["switches"] = level_switches(world)
        planes = surface_planes(world, grid, choice, kinds)
        world["roadsurf"], surf_ids = roadsurf_lump(planes, world["plain_ids"], world.get("lane_rot"))
    if os.environ.get("CHI_POLISH_CELLDUMP"):     # Polish debug: col,row,radius,file -> pickle of the cells' levels
        import pickle
        c0, r0, rad, fn = os.environ["CHI_POLISH_CELLDUMP"].split(",")
        c0, r0, rad = int(c0), int(r0), int(rad)
        win = {(c, r): {"grid": grid.get((c, r)), "choice": choice.get((c, r)), "kind": kinds.get((c, r)),
                        "plane": (planes.get((c, r)) if SURF else None), "sid": surf_ids.get((c, r)),
                        "slope": world["extra_slopes"].get((c, r))}
               for c in range(c0 - rad, c0 + rad + 1) for r in range(r0 - rad, r0 + rad + 1)}
        pickle.dump(win, open(fn, "wb"))
    out = {}
    road_cells = world.get("road_cells", set())
    for rz in range(world["rz_n"]):
        for rx in range(world["rx_n"]):
            vals = []
            for a in range(60):
                for b in range(60):
                    # a region's block holds its 60 x 60 cells with row 0 at its top (max z)
                    cell = (rx * 60 + b, (world["rz_n"] - 1 - rz) * 60 + a)
                    gy, t = choice[cell]
                    sid, ang = surf_ids.get(cell, (GRASS_ID if t in ROAD_TYPES_GRASS else 0,
                                                   world.get("lane_rot", {}).get(cell, 0)))
                    if abs(gy) < HEIGHT_DEADBAND:                # kerbs / raised grass: street level
                        gy = 0
                    low = gy & 0xFFF8
                    if t in (6, 9) and "no_water" not in EXPERIMENT and "water_nocells" not in EXPERIMENT:
                        wy = wheights.get((rx * 60 + b, (world["rz_n"] - 1 - rz) * 60 + a), WATER_Y)
                        sid, low = WATER_MODEL, wy & 0xFFF8          # water surface: waves, sinking
                        vals.append(ROAD_TOP | (sid << 16) | (low & 0xFFFF) | WATER_FLAG)
                        continue
                    if cell in road_cells:              # Miami: road / junction cells 0 in bits 26-29, bit 0 set
                        vals.append((ang << 30) | (sid << 16) | (low & 0xFFFF) | 1)
                    else:
                        vals.append((ang << 30) | ROAD_TOP | (sid << 16) | (low & 0xFFFF) | ROAD_FLAG)
            out[(rx, rz)] = vals
    return out


def rle_roadm(ids):
    """roadm block: (s16 run length, u16 road id) runs over the region's 3600 cells, then -1."""
    runs, k = bytearray(), 0
    while k < len(ids):
        j = k
        while j < len(ids) and ids[j] == ids[k]:
            j += 1
        runs += struct.pack("<hH", j - k, ids[k])
        k = j
    return bytes(runs) + struct.pack("<hH", -1, 0)


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


def s4_pvs_buffers(world, offsets, records):
    """S4 (CHI_S4=1): per-barrel buffer sizes as Driver 1 sizes its own levels. LoadRegionData (0x800342D4) spools a
    region's roadm to buffer + 0, roadh to buffer + 0x1000 (both decoded by callbacks) and then the PVS to buffer + 0,
    so a barrel needs max(roadm, 0x1000 + roadh, pvs) over its regions (exactly D1's SPOOLINFO values for Miami / LA /
    NY / SF). Chicago: 90 KB instead of 4 x 32 KB (-38 KB of level heap)."""
    need = [0x1000] * 4
    for idx, off in enumerate(offsets):
        if off == 0xFFFF:
            continue
        rx, rz = idx % world["rx_n"], idx // world["rx_n"]
        sp = struct.unpack_from("<H2B B3B B B B B", records, off)
        pvs, roadm, roadh = sp[3], sp[9], sp[10]
        b = (rx & 1) + 2 * (rz & 1)
        need[b] = max(need[b], roadm * 2048, 0x1000 + roadh * 2048, pvs * 2048)
    return need


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
    pvs_bufs = __import__("polish_pvs").barrels() if __import__("polish_pvs").enabled() else [PVS_BUFFER] * 4
    if os.environ.get("CHI_S4", "0") == "1":
        pvs_bufs = s4_pvs_buffers(world, offsets, records)
    out += struct.pack("<4i", *slots) + struct.pack("<4i", *objs) + struct.pack("<4i", *pvs_bufs)
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

_POLISH_PVS = {}


def polish_pvs_masks(world):
    """CHI_POLISH_PVS=d2: per-cell window masks from Driver 2's PVS (polish_pvs.py), else None."""
    import polish_pvs
    if not polish_pvs.enabled():
        return None
    if "masks" not in _POLISH_PVS:
        d2 = polish_pvs.D2Pvs(D2_LEV)
        across, down = ws.CELLS_ACROSS, ws.CELLS_DOWN
        masks, st = polish_pvs.masks_for_grid(d2, world["radii"], CELL, across // 2 * CELL, down // 2 * CELL)
        print("pvs: Driver 2 PVS on %d cells, window entries %d of %d kept (%.0f%%)" % (
            st["cells"], st["kept_entries"], st["radius_entries"], 100.0 * st["kept_entries"] / max(st["radius_entries"], 1)))
        _POLISH_PVS["masks"] = masks
    return _POLISH_PVS["masks"]


STABLE_PAGES = []           # stable shared texture pages of this conversion (polish_pages)


def polish_overlay(base_lump: bytes) -> bytes:
    """CHI_POLISH_MAP=1: Driver 2's Chicago map as the minimap (polish_map.py, C12; needs the
    plugin to write polish_map.params into the CITY 3 entry of the exe table 0x8008B080)."""
    import polish_map
    if not polish_map.enabled():
        return base_lump
    data, prm = polish_map.lump(D2_LEV, base_lump)
    print("minimap: Driver 2 overlay map, %d bytes, exe table words for CITY 3: %s" % (len(data), prm[:6]))
    return data


def convert(out_path: str):
    chi = Lev.parse(open(D2_LEV, "rb").read())
    if CITY.water_relocate:
        relocate_water_slot(chi)
    if CITY.resident_models:
        make_resident(chi, CITY.resident_models)
    base = Lev.parse(inputs.read("d1_LA.lev"))
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
    import texrepack
    texrepack.FORCED_AREAS = set(world["model_vis"].get(far_water_index(chi) + FAR_WATER, set())) if SHORE_WALLS else set()
    print("shore wall texture areas:", sorted(texrepack.FORCED_AREAS))
    cset = car_set()
    cars = base if cset == "la" else (chi if cset == "d2" else Lev.parse(inputs.read(CAR_SET_LEVS[cset])))
    csrc = "B" if cars is base else "K"           # texture source key of the car set (texrepack)
    print("car set:", cset)
    import polish_specials                          # C42 r3 (c): the specials' textures in their areas' sets
    texrepack.EXTRA_MODELS = polish_specials.extra_models(chi, world) if (cset == "d2" and polish_specials.enabled()) else {}
    if texrepack.EXTRA_MODELS:
        print("specials: textures in the areas %s" % {m: sorted(a) for m, a in polish_specials.special_areas(world).items()})
    import polish_s1
    if STREAM_INMEM:                                # Q36 B (Polish 21.10.): in-memory models streamed per area
        keep = stream_keep(chi, cmem0, models0, world, lodt, nlod)
        moved = set(cmem0) - keep
        sets = {a: set(v) for a, v in world["area_model_ids"].items()}
        for m in moved:
            for a in world["model_vis"].get(m, ()):
                if a in sets:
                    sets[a].add(m)
        for a, ids in sets.items():                 # instance sources of streamed models: in memory or in the area
            todo = list(ids)
            while todo:
                src = models0[todo.pop()].instance_number
                if src >= 0 and src not in keep and src not in ids and src in models0:
                    ids.add(src); todo.append(src)
        world["area_model_ids"] = {a: sorted(v) for a, v in sets.items()}
        STREAM_KEEP.clear(); STREAM_KEEP.update(keep)
        texrepack.INMEM_KEEP = keep
        mb = {a: sum(len(cmem0[m].data) for m in v if m in moved) for a, v in sets.items()}
        print("stream in-memory models (CHI_POLISH_STREAM_INMEM): %d of %d move into the area spools (%d KB of D2 data); "
              "kept %d; per area +KB %s" % (len(moved), len(cmem0), sum(len(cmem0[m].data) for m in moved) // 1024, len(keep),
                                           {a: v // 1024 for a, v in sorted(mb.items())}))
    polish_s1.AREA_MODELS = world["area_model_ids"]
    polish_s1.PIN_MODELS = set()
    if os.environ.get("CHI_POLISH_S1_PIN", "0") == "1":
        # Infrastructure (21.10.): during an area switch the C30 carry draws the outgoing area's models with the new
        # area's pages for ~0.5-1 s; models seen from regions where two areas can be loaded (boundaries, corridors)
        # therefore keep their textures at one spot in every area
        for reg, seen in world["region_seen"].items():
            if len(world["loadable"].get(reg, ())) > 1:
                polish_s1.PIN_MODELS.update(seen)
        print("S1: %d models seen from switch regions keep one texture spot" % len(polish_s1.PIN_MODELS))
    if os.environ.get("CHI_POLISH_PACKSTAT") == "1":     # S1 estimate: RAM if the in-memory models were streamed per area
        _cm, _ = inmem_models(chi)
        _per = {a: sum(len(_cm[m].data) for m in _cm if a in world["model_vis"].get(m, ())) for a in world["used_areas"]}
        print("PACKSTAT in-memory model bytes visible per area (D2 sizes): %s; whole lump %d" % (_per, sum(len(m.data) for m in _cm.values())))
    res = repack(chi, base, world["model_vis"], None if "no_near" in EXPERIMENT else world["model_near"], cars)
    import polish_pages                              # CHI_POLISH_SHAREDPAGES=1 (Polish, C45)
    if polish_pages.enabled():
        STABLE_PAGES[:] = polish_pages.stable_indices(res)
        print("stable pages: %s (%d); per-area pages: %s" % (STABLE_PAGES, len(STABLE_PAGES),
              sorted({i for (_a, i) in res.area_page_content})))
    print("\n".join(res.report))

    # S2/slot-15 (Infrastructure 20.10.): permanent, special/car, sky and map CLUTs share one allocator of
    # 192 + 32 x (first area slot) positions (Chicago 384); ~CLUT_BASE_POS + palettes of the permanent + special pages
    # (Infrastructure 21.10.): 37 fixed + permanent pages + the 2 special pages loaded in play + one per car palette
    # entry (PALLET lump, built below; counted from the car set's list): calibrated 38 + ... = 384 (cars1) / 374 (d2cars16)
    _npal = sum(len(res.pages[i].cluts) for i in res.permanent) + sum(struct.unpack_from("<i", b, 0)[0] for _p, b in res.special[:2])
    # special (car) pages: renumber right after the repacked pages, keep content
    flip = set()
    if cset == "d2":                               # Polish C42: Driver 1's pair order for the player cars
        import polish_cars
        order = polish_cars.special_order(chi, [p for p, _ in res.special])
        blobs = dict(res.special)
        if any(p < 0 for p in order):                  # C124: blank pairs for player cars without special pages
            from texpages import decode_compressed as _dc0, encode_compressed as _ec0, Page as _Pg
            _ref, _e = _dc0(next(iter(blobs.values())))
            for p in order:
                if p < 0:
                    blobs[p] = _ec0(_Pg([], bytearray(len(_ref.texels))))
            print("d2 cars: blank special pairs for player slots without special pages: %s" % [p for p in order if p < 0])
        # R32 (user 'd2 cars 3': player car rear window / damaged bonnet glitched): Driver 1 keeps its MINIMAP tile cache
        # (4 x 4 tiles of 32 px, FUN_00056278: slot of the chosen car's first special page + 0x8008B140 offsets) in the
        # FIRST page of the player car's special pair at u 128..255, v 0..127; Driver 1's own minor pages leave it free,
        # Driver 2's are full there (BONSPEC5's damage twin, WINDSPEC ...), so the map tiles overwrote them. The minor
        # page's two halves are swapped when its lower half holds only textures no car uses (TSHADOW in all four):
        # the minimap then overwrites TSHADOW. CHI_SPECIAL_FLIP=0: off.
        if os.environ.get("CHI_SPECIAL_FLIP", "1") != "0":
            from texrepack import model_texrefs as _mtr
            from texpages import read_pages as _rp, decode_compressed as _dc, encode_compressed as _ec
            used = set()
            for m_ in polish_cars.models_for(chi):
                used |= _mtr(m_, {})
            cti2, _ = _rp(chi)

            def _top_free(p):                          # no used texture in the top half (the audit's rule)
                return p < 0 or not any((p, k) in used for k, e in enumerate(cti2.details[p]) if e[3] < 128)

            def _flippable(p):
                if p < 0:                              # C124 blank page
                    return False
                dets = cti2.details[p]
                bottom = [k for k, e in enumerate(dets) if e[3] >= 128]
                cross = any(e[3] < 128 < e[3] + (e[5] or 256) for e in dets)
                return not cross and not any((p, k) in used for k in bottom)
            def _flippable_used(p):                    # M3 Las Vegas: only USED textures may not cross the middle
                if p < 0:
                    return False
                dets = cti2.details[p]                 # (Vegas' TSHADOW, unused by the cars, spans 112..240)
                return not any((p, k) in used and (e[3] >= 128 or e[3] < 128 < e[3] + (e[5] or 256))
                               for k, e in enumerate(dets))
            # M3 Las Vegas: a pair whose minor page can neither keep its top half free nor be flipped takes its major
            # page first when that one can (pages are addressed by remapped number, so the order inside a pair only
            # decides which page hosts the tile cache). Chicago / Havana never reach this (their minor pages pass)
            swapped = []
            for j in range(0, len(order) - 1, 2):
                p0, p1 = order[j], order[j + 1]
                if (not _top_free(p0) and not _flippable(p0) and not _flippable_used(p0)
                        and (_top_free(p1) or _flippable(p1) or _flippable_used(p1))):
                    order[j], order[j + 1] = p1, p0
                    swapped.append((p1, p0))
            if swapped:
                print("d2 cars: special pairs with the major page first (minimap tile cache): %s" % swapped)
            for p in order[0::2]:
                if _flippable(p) or (not _top_free(p) and _flippable_used(p)):   # (as before: also top-free pages)
                    pg, _end = _dc(blobs[p])
                    pg.texels = bytearray(pg.texels[128 * 128:] + pg.texels[:128 * 128])
                    blobs[p] = _ec(pg)
                    flip.add(p)
            print("d2 cars: special pages with halves swapped (minimap tile cache): %s" % sorted(flip))
        res.special = [(p, blobs[p]) for p in order]
        print("d2 cars: special pages in pair order %s (of %s)" % (order, sorted(blobs)))
    from texpages import read_pages
    bti, _ = read_pages(cars)
    bnames = cars.loadtime.get(5).data
    res.special_details = {}
    special_new = {}
    nxt = max(res.pages) + 1
    fy = lambda old, y: (y + 128) % 256 if old in flip else y
    for old, _blob in res.special:
        special_new[old] = nxt
        res.special_details[old] = [(d[0], bnames[d[1]: bnames.index(b"\0", d[1])], d[2], fy(old, d[3]), *d[4:])
                                    for d in (bti.details[old] if old >= 0 else [])]
        for k, d in enumerate(bti.details[old] if old >= 0 else []):
            w, h = d[4] or 256, d[5] or 256
            res.remap[(csrc, old, k)] = (nxt, k, d[2], fy(old, d[3]), d[2], d[3], w, h, w, h)
        nxt += 1
    if cset == "d2":                                  # R32 memory-safety audit: the minimap tile cache vs the player cars
        from texrepack import model_texrefs as _mtr2
        firsts = {old for old in order[0::2]} if order else set()
        bad = []
        for m_ in polish_cars.models_for(chi):
            for (p_, k_) in _mtr2(m_, {}):
                r_ = res.remap.get((csrc, p_, k_))
                if p_ not in firsts or not r_:
                    continue
                x_, y_, w_, h_ = r_[2], r_[3], r_[8], r_[9]
                for dx in (0, 128):                  # the clean rect and its Driver 2 damage twin (+128)
                    if x_ + dx < 256 and x_ + dx + w_ > 128 and y_ < 128:
                        bad.append((p_, k_, x_ + dx, y_))
        if bad:
            raise RuntimeError("player car textures in the minimap tile cache (first special page, u 128..255, v 0..127): %s"
                               % sorted(set(bad))[:8])
        print("d2 cars: minimap tile cache clear of the player cars' textures (audit)")

    # R32 (VRAM audit): LoadSky (0x8004ED34) uploads the sky panorama to VRAM (512, 0) = slot 0x8 = the FIRST permanent
    # page in load order, and Driver 1 levels list their PCSKY page first (LA 2, Miami 30: PCSKY 256 x 128 reserves its
    # top half). Ours listed page 5 first, so the sky overwrote the top half of the civilian car page (half / garbled
    # civilian textures). The page holding PCSKY is now loaded first.
    sky_pg = [i for i in res.permanent if any(dd[1] == b"PCSKY" for dd in res.details.get(i, []))]
    if sky_pg and res.permanent[0] != sky_pg[0]:
        res.permanent = sky_pg[:1] + [i for i in res.permanent if i != sky_pg[0]]
    print("permanent load order (first = sky slot 0x8): %s" % list(res.permanent))
    spc_slot = None
    if cset == "d2" and polish_specials.slot_mode():  # R34: the specials' dedicated texture slot (plugin uploads)
        spc_slot = polish_specials.reserve_slot(res)
        print("specials slot: page %d entries %d..%d, bottom %dx%d" % (spc_slot["page"], spc_slot["base"],
              spc_slot["base"] + spc_slot["n"] - 1, spc_slot["w"], spc_slot["h"]))
    texnames, texinfo, tpages, num_pages = texture_lumps(res, special_new)

    if LOW_WALLS:
        LOW_WALL_IDS.clear()
        LOW_WALL_IDS.update(low_wall_models(world["obj_list"], {i: ws.scale_model(m.data) for i, m in models0.items()}, world))
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
    road_lumps = {}
    if ROADS:
        import d1roads
        # a first road map (no roads yet) says where the water is: roads there are left out
        water = set()
        for (rx, rz), vals in road_values(world).items():
            for idx, v in enumerate(vals):
                if (v >> 16) & 0x3FF == WATER_MODEL:
                    water.add((rx * 60 + idx % 60, (world["rz_n"] - 1 - rz) * 60 + idx // 60))
        net = d1roads.build(D2_LEV, world["across"] * CELL // ROAD_UNIT, world["down"] * CELL // ROAD_UNIT, water)
        print("roads:", net["stats"])
        road_lumps = net["lumps"]
        # d1roads' cells are this grid's (col, row); a region block (rx, rz) holds rows
        # (rz_n - 1 - rz) * 60 + a at index a * 60 + b (as road_values writes roadh)
        rz_n = world["rz_n"]
        world["lane_rot"] = net["rot"]
        world["road_cells"] = set(net["cells"])
        world["road_ids"] = {}
        for (i, j), v in net["cells"].items():
            world["road_ids"].setdefault((i // 60, rz_n - 1 - j // 60), [0xFFFF] * ROAD_CELLS_PER_REGION)[(i % 60) + (j % 60) * 60] = v
    world["road_values"] = road_values(world)
    vals = [v for vs in world["road_values"].values() for v in vs]
    hs = collections.Counter((((v & 0xFFF8) ^ 0x8000) - 0x8000) // 500 * 500 for v in vals)
    print("road map: %d cells, grass %d, heights (500-unit bins): %s" % (
        len(vals), sum(1 for v in vals if (v >> 16) & 0x3FF == GRASS_ID), sorted(hs.items())))
    S1_COPY_HASH.clear(); AREA_COPY_HASH.clear()
    spooled, areas, slots, objs, offsets, records, total_cd = build_spooled(world, area_data, res, chi)
    # The model spool buffer also stages area texture pages (34 KB each) at an
    # offset inside it, so it must be at least as big as the base city's.
    base_model_buf = struct.unpack_from("<i", base.inmem.get(L_SPOOL).data, 0)[0]
    model_buf = max(max(a[2] for a in areas.values()), base_model_buf)

    base_sp_raw = base.inmem.get(L_SPOOL).data
    spool = spoolinfo_lump(base_sp_raw, SpoolInfo.parse(base_sp_raw), world, areas, slots, objs, offsets, records, model_buf)
    mapl = map_lump(world, total_cd, MapHeader.parse(chi.loadtime.get(L_MAP).data), MapHeader.parse(base.loadtime.get(L_MAP).data))

    # car models: the car set's, with texture pages remapped
    fallback = res.remap[next(iter(res.remap))]
    cm = bytearray(cars.loadtime.get(L_CARMODELS).data)
    if cset == "d2":
        cm = bytearray(polish_cars.lump28(chi.loadtime.get(L_CARMODELS).data))
    import polish_carmix                             # Polish C42 step 1: mixed set (D2 traffic/cop + the set's player cars)
    import polish_cars                               # (local name in convert(): bind it on every path, not only cset d2)
    if polish_cars.enabled() and os.environ.get("CHI_POLISH_CARPAL_MERGE", "1") == "1":
        print("car textures with identical palettes merged (CLUT allocator): %d"
              % polish_cars.merge_identical_car_textures(chi.loadtime.get(L_PALLET).data, res, csrc))
    slot_src = {}
    if polish_carmix.enabled():
        raw, slot_src = polish_carmix.lump28(chi.loadtime.get(L_CARMODELS).data, cars.loadtime.get(L_CARMODELS).data)
        cm = bytearray(raw)
    ents = [struct.unpack_from("<3i", cm, 4 + 12 * i) for i in range(13)]
    cbase = 4 + 12 * 13
    for slot, e in enumerate(ents):
        for off in e:
            if off == -1:
                continue
            size = struct.unpack_from("<i", cm, cbase + off)[0]
            a = cbase + off + 4
            cm[a: a + size] = remap_polys(bytes(cm[a: a + size]), slot_src.get(slot) or csrc, res.remap, fallback)
    # palettes: the car set's, tpage field remapped for renumbered pages
    pal = bytearray(cars.loadtime.get(L_PALLET).data)
    base_tex_by_name = {}
    if cars is not base:
        lti, _ = read_pages(base)
        lnames = base.loadtime.get(5).data
        for pg, dl in enumerate(lti.details):
            for k, d in enumerate(dl):
                base_tex_by_name.setdefault(lnames[d[1]: lnames.index(b"\0", d[1])], (pg, k))

    def name_of_car_tex(pg, k):
        if pg < 0 or pg >= len(bti.details) or k < 0 or k >= len(bti.details[pg]):
            return None
        d = bti.details[pg][k]
        return bnames[d[1]: bnames.index(b"\0", d[1])]
    total = struct.unpack_from("<i", pal, 0)[0]
    if cset == "d2" or polish_carmix.enabled():      # Polish C42: Driver 2 palettes -> Driver 1 format
        from texrepack import model_texrefs
        import polish_cars
        mixed = polish_carmix.enabled()
        keep = {tp for m in (polish_carmix.civ_models(chi) if mixed else polish_cars.models_for(chi))
                for tp, _k in model_texrefs(m, {})}
        def _r(tp, tn):
            r = res.remap.get(("D" if mixed else csrc, tp, tn))
            return (r[0], r[1]) if r else None
        bpal = base.loadtime.get(L_PALLET).data      # the base city's pedestrian palettes (ARM1, JEANS1, ...)
        peds = []
        for q in range(4, 4 + 44 * struct.unpack_from("<i", bpal, 0)[0], 44):
            a_, t_, tp_ = struct.unpack_from("<3i", bpal, q)
            r = res.remap.get(("B", tp_, t_))
            if r:
                peds.append(struct.pack("<3i", a_, r[1], r[0]) + bpal[q + 12: q + 44])
        cop = polish_cars.cop_palettes(chi, _r) if not mixed else []    # C59: the D2 cop's own paint for palettes 0..3
        pal = bytearray(polish_cars.palettes(chi.loadtime.get(L_PALLET).data, keep, _r, peds + cop))
        if not mixed:                               # C42 r3 (b): only entries inside Driver 1's car CLUT table
            cp0 = texrepack.CAR_PAGE_BASE
            ents_ = [bytes(pal[q:q + 44]) for q in range(4, len(pal), 44)]
            ok_ = [e_ for e_ in ents_ if cp0 <= struct.unpack_from("<i", e_, 8)[0] < cp0 + polish_cars.CLUT_PAGES
                   and struct.unpack_from("<i", e_, 4)[0] < polish_cars.CLUT_TEXTURES]
            print("d2 cars: car CLUT table: %d of %d palette entries kept (pages %d-%d, textures < %d)"
                  % (len(ok_), len(ents_), cp0, cp0 + polish_cars.CLUT_PAGES - 1, polish_cars.CLUT_TEXTURES))
            pal = bytearray(struct.pack("<i", len(ok_)) + b"".join(ok_))
            # the palettised models' polygons write the table too (FUN_0003BDC8): all of them must be inside
            for s_ in polish_cars.PALETTE_SLOTS:
                d2_ = polish_cars.slot_map().get(s_)
                ents2 = polish_cars._entries(chi.loadtime.get(L_CARMODELS).data)
                if d2_ is None or ents2[d2_][0] == -1:
                    continue
                bad = sorted({_r(p_, k_) for p_, k_ in model_texrefs(Model.parse(-1, polish_cars._model_bytes(
                    chi.loadtime.get(L_CARMODELS).data, ents2[d2_][0])), {})
                    if _r(p_, k_) and not (cp0 <= _r(p_, k_)[0] < cp0 + polish_cars.CLUT_PAGES
                                           and _r(p_, k_)[1] < polish_cars.CLUT_TEXTURES)})
                if bad:
                    raise RuntimeError("car CLUT table: civilian slot %d textures outside pages %d-%d / < %d: %s"
                                       % (s_, cp0, cp0 + 1, polish_cars.CLUT_TEXTURES, bad[:6]))
        print("d2 cars: %d cop palette entries (own CLUTs)" % len(cop))
        print("d2 cars: %d pedestrian palette entries kept" % len(peds))
        total = 0
        print("d2 cars: %d palette entries" % struct.unpack_from("<i", pal, 0)[0])
    p = 4
    for _ in range(total):
        palette, texnum, tpage = struct.unpack_from("<3i", pal, p)
        if palette == -1:
            break
        r = res.remap.get((csrc, tpage, texnum))
        if r is None and cars is not base:        # pedestrian palettes (ARM1, CHEST1, ...): the base city's textures
            r = res.remap.get(("B",) + base_tex_by_name.get(name_of_car_tex(tpage, texnum), (-1, -1)))
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
        Lump(L_ROADS, road_lumps.get(L_ROADS, struct.pack("<i", 0))),
        Lump(L_JUNCS, road_lumps.get(L_JUNCS, struct.pack("<i", 0))),
        Lump(L_ROADBOUNDS, road_lumps.get(L_ROADBOUNDS, struct.pack("<i", 0))),
        Lump(L_JUNCBOUNDS, road_lumps.get(L_JUNCBOUNDS, struct.pack("<i", 0))),
        # far ground tiles index this table from model +0x2C (d1models.py)
        Lump(L_SUBDIV, subdiv_lump + water_sub),
        Lump(L_ROADSURF, world["roadsurf"]),
        Lump(L_OVERLAY, polish_overlay(base.inmem.get(L_OVERLAY).data)),
        Lump(L_CHAIR, base.inmem.get(L_CHAIR).data),
        Lump(L_LOD, lod_lump),
    ])
    # in-memory section budget: the engine keeps these lumps resident (LA ~100 KB; the
    # 02:40 Chicago level 243,712 B; 286,720 B with the first ROADSURF was fine in
    # sequential tests, no hard limit verified yet) - logged so growth is never silent
    print("inmem section: %d bytes (%s)" % (sum(8 + len(l.data) for l in inmem.lumps),
          ", ".join("%d:%d" % (l.type, len(l.data)) for l in inmem.lumps)))
    lev = Lev(d1=True, loadtime=load, tpages=tpages, inmem=inmem, spooled=spooled)
    out = lev.build(keep_layout=False)
    tmp = out_path + ".tmp"                 # atomic: test copies must never see a half-written level
    open(tmp, "wb").write(out)
    os.replace(tmp, out_path)
    if STABLE_PAGES:                                 # Polish C45: stable page indices for the skip-resident patch
        import json
        open(out_path + ".stable.json", "w").write(json.dumps({"stable_pages": STABLE_PAGES}))
    import polish_carmix
    if polish_carmix.enabled():                      # Polish C42 step 1: civ damage rows (slots 0-2) for build_package
        den = os.path.splitext(D2_LEV)[0] + ".DEN"
        if not os.path.exists(den) or not CITY.is_day_lev(D2_LEV):
            den = inputs.path(CITY.den)                             # night LEV: same cars, same DEN
        open(out_path + ".dmg.bin", "wb").write(polish_carmix.damage_civ(den))
        print("mixed car set: damage rows (civ verts 900 + civ polys 1260) ->", out_path + ".dmg.bin")
    if car_set() == "d2":                             # C42 engine step (17.10.): all-Driver 2 set, damage + cosmetics rows
        import polish_cars, polish_cosmetics, tempfile
        den = os.path.splitext(D2_LEV)[0] + ".DEN"
        if not os.path.exists(den) or not CITY.is_day_lev(D2_LEV):
            den = inputs.path(CITY.den)
        _cm28 = chi.loadtime.get(L_CARMODELS).data
        import polish_specials
        t = polish_cars.damage_tables(open(den, "rb").read(), polish_cars.fit_maps(_cm28), polish_cars.fit_maps(_cm28, True),
                                      extra=polish_specials.SPECIALS)
        # civ rows = AI resident models 1..3 (slots 0..2; the exe table pointer sits one row lower), player rows = choices 0..3
        open(out_path + ".dmg.bin", "wb").write(t["civ_verts"] + t["civ_polys"] + t["player_verts"] + t["player_polys"])
        open(out_path + ".lvl.bin", "wb").write(polish_cars.level_rows(
            open(den, "rb").read(), polish_cars.fit_maps(_cm28), polish_cars.fit_maps(_cm28, True),
            twin_ok=lambda p_, k_: (csrc, p_, k_) in polish_cars.TWINNED, d2_cm=_cm28))
        with tempfile.TemporaryDirectory() as td:
            cos = polish_cosmetics.build(inputs.path(CITY.lcf), td, inputs.path(CITY.lev_day))[0]["day"]
            open(out_path + ".cos.bin", "wb").write(open(cos, "rb").read())
        # collision boxes of the player choices 0..3 (D2 CAR_COSMETICS colBox at +212, half x, y, z) x SCALE -> 4 x 3 int32
        lcf = open(inputs.path(CITY.lcf), "rb").read()
        offs = struct.unpack_from("<13i", lcf, 0)
        box = b""
        for c in range(4):
            d2m = polish_cars.slot_map().get(5 + c)
            bx = struct.unpack_from("<3h", lcf, offs[d2m] + 212) if d2m is not None and offs[d2m] > 0 else (0, 0, 0)
            box += struct.pack("<3i", *(int(round(v * polish_cars.SCALE)) for v in bx))
        open(out_path + ".box.bin", "wb").write(box)
        # C42 r3: wheel size per car (D2 CAR_COSMETICS wheelSize x SCALE; tread +-size, rim size * 1.4142 like D2 cars.c):
        # player choices 0..3 (slots 5..8), then AI resident models 1..3 (1..5 with six models: slots 0..4) -> 7 / 9 int16
        wsz = []
        for d1 in (5, 6, 7, 8) + polish_cars.AI_SLOTS:
            d2m = polish_cars.slot_map().get(d1)
            v = struct.unpack_from("<h", lcf, offs[d2m] + 114)[0] if d2m is not None and offs[d2m] > 0 else 0
            wsz.append(int(round(v * polish_cars.SCALE)))
        open(out_path + ".whl.bin", "wb").write(struct.pack("<%dh" % len(wsz), *wsz))
        if os.environ.get("CHI_POLISH_PLAYERSHADOW") == "1":
            # C138 (Havana's mini car): Driver 1 draws every car's shadow through its physics corners (car + 0x88 .. 0xB8),
            # a fixed 370 x 1040 box (measured: Miami and the Havana mini alike) -> 1.3 x wider / 1.9 x longer than the mini
            # (D2 cPoints span 245 x 548 after x1.32). <lev>.pps.bin = "PPS1", 4, then per player choice 0..3 {D2 model,
            # 4 x (x, z) = Driver 2's cPoints[0..3] x the car scale (SetShadowPoints, car frame), colBox half x / z x scale,
            # car length / 1040 x 4096 (a glow scale for the car's lights)} for the plugin's shadow offsets (SHD, C102) on car 0
            pps = struct.pack("<2i", 0x31535050, 4)
            for c in range(4):
                d2m = polish_cars.slot_map().get(5 + c)
                if d2m is None or offs[d2m] <= 0:
                    pps += struct.pack("<i", -1) + bytes(8 * 4 + 12)
                    continue
                pts = [struct.unpack_from("<3h", lcf, offs[d2m] + 116 + 8 * k_) for k_ in range(4)]
                pps += struct.pack("<i", d2m)
                for cx_, _cy, cz_ in pts:
                    pps += struct.pack("<2i", int(round(cx_ * polish_cars.SCALE)), int(round(cz_ * polish_cars.SCALE)))
                bx_, _by, bz_ = struct.unpack_from("<3h", lcf, offs[d2m] + 212)
                length = (max(p[2] for p in pts) - min(p[2] for p in pts)) * polish_cars.SCALE
                pps += struct.pack("<3i", int(round(bx_ * polish_cars.SCALE)), int(round(bz_ * polish_cars.SCALE)),
                                   int(round(4096 * length / 1040.0)))
            open(out_path + ".pps.bin", "wb").write(pps)
            print("player shadow corners (C138): %s (%d bytes)" % (out_path + ".pps.bin", len(pps)))
        if polish_specials.enabled():                # C42 r3 (c): the four specials for the plugin's runtime swap
            cosb = open(out_path + ".cos.bin", "rb").read()
            sm = polish_cars.slot_map()
            row_of = {sm.get(5 + r): r for r in range(4)}
            zone = dict(t["extra"])                  # AI-fitted zone rows of the specials (R33: player cars fit differently)
            spc_cos = {m: cosb[100 * row_of[m]: 100 * row_of[m] + 100] for m in polish_specials.SPECIALS if m in row_of}
            spc_whl = {m: wsz[row_of[m]] for m in polish_specials.SPECIALS if m in row_of}
            for m in polish_specials.SPECIALS:       # M3: specials that are no player choice (Havana's 11)
                if m not in row_of:
                    spc_cos[m] = polish_cosmetics.special_row(inputs.path(CITY.lcf), inputs.path(CITY.lev_day), m, cosb[96:100])
                    spc_whl[m] = int(round(struct.unpack_from("<h", lcf, offs[m] + 114)[0] * polish_cars.SCALE))
            sa = polish_specials.asset(chi, world, lambda b: remap_polys(b, "C", res.remap, fallback),
                                       spc_cos, spc_whl, zone,
                                       polish_specials.col_boxes(polish_cars.SCALE), slot=spc_slot, remap=res.remap,
                                       permanent=res.permanent,
                                       remap_with=lambda b_, rm_: remap_polys(b_, "C", rm_, fallback))
            open(out_path + ".spc.bin", "wb").write(sa)
            print("specials: %d bytes -> %s" % (len(sa), out_path + ".spc.bin"))
            # M3 (Infrastructure, C82 SPTW per city): <lev>.spt.bin = "SPT1", n, civilian reference twistRateY (D2 model 1),
            # then n x {model, twistRateY} from the city's LCF (CAR_COSMETICS +230); Chicago = the plugin's old table
            spt = struct.pack("<3i", 0x31545053, len(polish_specials.SPECIALS), struct.unpack_from("<h", lcf, offs[1] + 230)[0])
            for m_ in polish_specials.SPECIALS:
                spt += struct.pack("<2i", m_, struct.unpack_from("<h", lcf, offs[m_] + 230)[0])
            open(out_path + ".spt.bin", "wb").write(spt)
            if os.environ.get("CHI_POLISH_SPCSHADOW") == "1":
                # cheats 6: <lev>.sps.bin = "SPS1", n, then n x {model, 4 x (x, z)} = Driver 2's cPoints[0..3] (handling.c
                # SetShadowPoints: the shadow quad) x the car scale, car frame (Driver 1 and 2 models both face -z)
                sps = struct.pack("<2i", 0x31535053, len(polish_specials.SPECIALS))
                for m_ in polish_specials.SPECIALS:
                    sps += struct.pack("<i", m_)
                    for k_ in range(4):
                        cx_, _cy, cz_ = struct.unpack_from("<3h", lcf, offs[m_] + 116 + 8 * k_)
                        sps += struct.pack("<2i", int(round(cx_ * polish_cars.SCALE)), int(round(cz_ * polish_cars.SCALE)))
                open(out_path + ".sps.bin", "wb").write(sps)
                print("specials shadow corners (cheats 6): %s (%d bytes)" % (out_path + ".sps.bin", len(sps)))
            if polish_specials.SPECDMG and polish_specials.LEVEL_ROWS:
                # Q45 B: <lev>.spd.bin = "SPD1", n, DMG_OFF, then n x {model i32, 256 B DentCar level row of its clean
                # model (1 = damage copy DMG_OFF texels right (u), shift at level 2; 3 = no shift)}
                spd = struct.pack("<3i", 0x31445053, len(polish_specials.SPECIALS), polish_specials.DMG_OFF)
                for m_ in polish_specials.SPECIALS:
                    spd += struct.pack("<i", m_) + polish_specials.LEVEL_ROWS.get(m_, bytes([3] * 256))
                open(out_path + ".spd.bin", "wb").write(spd)
                print("specials damage rows (Q45 B, u + DMG_OFF): %s (%d bytes; %s)" % (out_path + ".spd.bin", len(spd), ", ".join(
                    "model %d: %d shifting polygons" % (m_, polish_specials.LEVEL_ROWS[m_].count(1))
                    for m_ in polish_specials.SPECIALS if m_ in polish_specials.LEVEL_ROWS)))
        print("d2 car set: wheel sizes (choices 0-3, AI 1-%d):" % len(polish_cars.AI_SLOTS), wsz)
        print("d2 car set: damage rows (civ %d + player 2880) + cosmetics rows (%d) ->" % (720 * len(polish_cars.AI_SLOTS),
              os.path.getsize(out_path + ".cos.bin")), out_path + ".dmg.bin / .cos.bin")
    clut_check(out_path)
    multi = [i for i, hs in AREA_COPY_HASH.items() if len(hs) > 1]
    print("area model copies: %d models in more than one area (%d copies), %d with differing copies" % (
        len(multi), sum(len(AREA_COPY_HASH[i]) for i in multi), sum(1 for i in multi if len(set(AREA_COPY_HASH[i])) > 1)))
    if S1_COPY_HASH:
        tab = s1_diff_table(world)
        open(out_path + ".s1d.bin", "wb").write(tab)
        print("S1 switch table (models whose spot differs between neighbouring areas) -> %s (%d bytes)" % (out_path + ".s1d.bin", len(tab)))
    print("wrote %s: %d bytes; models %d, objects %d (straddlers %d), regions %d, areas %d, pages %d"
          % (out_path, len(out), count, len(world["obj_list"]), len(world["straddlers"]),
             sum(1 for o in offsets if o != 0xFFFF), len(areas), num_pages))


if __name__ == "__main__":
    convert(sys.argv[1] if len(sys.argv) > 1 else "work/chicago_d1.lev")
