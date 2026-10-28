"""polish_cars.py - Driver 2's own Chicago cars in Driver 1's car slots (Polish, C42 data prototype).

Switch CHI_POLISH_D2CARS=1 (default off = convert.car_set(): a Driver 1 city's car set).

Lump 28 (car models) is the same container in both games: int count, 13 x {clean, damage, low}
offsets (-1 = none) from base 4 + 13*12, each model = int size + MODEL. Driver 2 Chicago fills 9
slots: 0-4 civilian cars (one Driver 2 permanent page each, ~30 textures of which the models use the
10 first-damage-stage ones) and 8, 9, 10, 12 special cars (two special pages each). Driver 1 uses 7
slots: 0 cop (LA: COP1..5), 1-2 civilian cars (permanent pages), 5-8 the player's cars (two special
pages each; Driver 1 loads the pair of the chosen car: pair k = slot 5 + k).

Slot map (Driver 1 slot <- Driver 2 slot), first test: 0 <- 3 (Driver 2's cop is a civilian model,
residentCarModels[3], REDRIVER2 civ_ai.c; no police textures in Chicago), 1 <- 0, 2 <- 1,
5..8 <- 8, 9, 10, 12. Override: CHI_POLISH_D2CARS_MAP="0:3,1:0,2:1,5:8,6:9,7:10,8:12".

Palettes (lump 25, colour variants): Driver 2 = int count, then {palette, texnum, tpage, clut_number}
+ 32-byte CLUT when clut_number == -1, else a reference to the clut_number-th CLUT so far (REDRIVER2
ProcessPalletLump); Driver 1 = int count, then {palette, texnum, tpage} + 32-byte CLUT each. Only
entries of the mapped cars' pages are kept, texture (page, number) remapped by the converter.

Driver 1 keeps its handling, damage zones and wheel positions (exe tables per slot): the Driver 2 bodies
get Driver 1's physics and Driver 1's wheel placement for that slot (see report).
"""
from __future__ import annotations

import os
import struct

# C59 / R31 (user 18.10.: "chasing cops are a regular blue traffic car"): Driver 2 Chicago's own missions (MISSIONS.BLK,
# MS_MISSION.residentModels, 34 of 37 Chicago missions) set residentCarModels = {1, 2, 3, 0, special}: civilians = lump
# models 1, 2, 3, the COP = lump model 0 (page 58: POLSIGN1 / BLUELYN, the police livery; REDRIVER2 civ_ai.c
# externalCopModel = residentCarModels[3], palette 0). Model 3 (page 50) is a plain light-blue civilian sedan: the
# earlier map {0: 3} (EXP's 'model 3 = police') put it on every cop. Driver 2's lump 25 has colour variants only for
# models 1 (page 65) and 2 (page 62); models 0, 3, 4 have one paint. Driver 1: resident model 1 = the cop (slot 0),
# palettised civilians = resident 2-3 (slots 1-2) -> D2 1 / 2; slots 3-4 (six models) -> D2 3 and D2 4.
D1_FROM_D2 = dict(__import__("cityprofile").P.d1_from_d2)   # M3 profile; Chicago {0: 0, 1: 1, 2: 2, 5: 12, 6: 9, 7: 10, 8: 8}: player choice 0 (default) = D2 12, the fire engine last (Strategy 17.10.)
# C42 r3 (b) (Infrastructure 17.10.): six resident models like Driver 2 (exe_patches c42m_patches): lump slots 3 and 4 =
# resident models 4 and 5 <- Driver 2's third civilian 3 and model 4 (Driver 2 PSX: slot 4 = SPECIAL_CAR_SLOT, default
# model 4; specials per region = step c). CHI_POLISH_CARS_SIX=0: 4 models.
SIX = os.environ.get("CHI_POLISH_CARS_SIX", "1") != "0"
AI_SLOTS = (0, 1, 2, 3, 4) if SIX else (0, 1, 2)
# C42 r3 (c): with the regional specials (polish_specials, CHI_SPECIALS=1 default) slot 4 is the special slot: it loads
# Driver 2's default special 10 and the plugin swaps it per area; CHI_SPECIALS=0 keeps Driver 2 model 4 (the van).
SPECIALS_ON = os.environ.get("CHI_SPECIALS", "1") != "0"
if SIX:
    D1_FROM_D2.update({3: 3, 4: 10 if SPECIALS_ON else 4})
BASE = 4 + 13 * 12
# C57 (EXP 16.10.): Driver 2 models are in Driver 2 units; worldscale.SCALE (1.32) applies to them too
# (vertices + bounding sphere of the clean, damage and low models). CHI_POLISH_CARS_SCALE=1 = unscaled.
SCALE = float(os.environ.get("CHI_POLISH_CARS_SCALE", "1.32"))


def scale_model(data: bytes, f: float = None) -> bytes:
    """MODEL bytes with bounding_sphere (+8) and the vertices (count +12, offset +16, 8 B each) scaled."""
    f = SCALE if f is None else f
    if f == 1.0:
        return data
    b = bytearray(data)
    bs = struct.unpack_from("<h", b, 8)[0]
    struct.pack_into("<h", b, 8, min(32767, int(round(bs * f))))
    nv = struct.unpack_from("<h", b, 12)[0]
    vo = struct.unpack_from("<i", b, 16)[0]
    for i in range(nv):
        o = vo + 8 * i
        if o + 6 > len(b):
            break
        x, y, z = struct.unpack_from("<3h", b, o)
        struct.pack_into("<3h", b, o, *(max(-32768, min(32767, int(round(v * f)))) for v in (x, y, z)))
    return bytes(b)


def enabled():
    return os.environ.get("CHI_POLISH_D2CARS", "") == "1"


def slot_map():
    s = os.environ.get("CHI_POLISH_D2CARS_MAP")
    if not s:
        return dict(D1_FROM_D2)
    return {int(a): int(b) for a, b in (p.split(":") for p in s.split(","))}


def _entries(cm: bytes):
    return [struct.unpack_from("<3i", cm, 4 + 12 * i) for i in range(13)]


def _model_bytes(cm: bytes, off: int) -> bytes:
    size = struct.unpack_from("<i", cm, BASE + off)[0]
    return cm[BASE + off + 4: BASE + off + 4 + size]


# --- C58 (Infrastructure 17.10.): Driver 1's car buffers ------------------------------------------------------------
# Driver 1 builds the four resident car models (player + 3 AI) into ONE car polygon buffer 0x800AB728 of 666 entries
# (FUN_0003BDC8, cap 0x29A at DAT_000973B0; a textured quad = 1 entry, a flat quad = 2), keeps per-car damage UV offsets
# of 150 bytes per AI car (0x800AF97A + car * 0x96; player 260) indexed by polygon, and 128 deformed vertices per car
# (0x800B09BC + car * 0x400). Driver 2's car models are ~250 triangles / up to 131 vertices: the buffer filled up at
# resident 2 and resident 3 (lump slot 2) got NO polygons = the invisible traffic cars (wheels only) of C58, and the
# UV / vertex buffers overflowed into the next car. fit_model() keeps Driver 2's geometry and fits those limits: triangle
# pairs sharing an edge with the same texture, UVs and normals become one quad (drawn as exactly the same two triangles),
# flat triangle pairs one flat quad; above 128 vertices the shortest edges are welded (1-3 per model, a few units).
FIT = os.environ.get("CHI_POLISH_CARS_FIT", "1") != "0"
MAX_VERTS = 128
FIT_ANGLE = float(os.environ.get("CHI_POLISH_CARS_FITANGLE", "30"))   # R33: max bend between paired triangles (deg)
import math as _math
FIT_COS = _math.cos(_math.radians(min(FIT_ANGLE, 180.0)))


def _polys(m):
    from models import POLY_SIZES
    out, q = [], m.poly_block
    for _ in range(m.num_polys):
        t = m.data[q] & 31
        out.append(bytearray(m.data[q:q + POLY_SIZES[t]]))
        q += POLY_SIZES[t]
    return out


def _pverts(b):
    t = b[0] & 31
    if t == 0:
        return [1, 2, 3]
    if t in (20, 22):
        return [4, 5, 6]
    if t in (1, 21, 23):
        return [4, 5, 6, 7]
    return []


def fit_model(clean: bytes, damage, fit_cos: float = -2.0):
    """(clean', damage', vmap, pmap): vmap / pmap = old index -> new index (None = gone)."""
    from models import Model
    m = Model.parse(-1, clean)
    P = _polys(m)
    nv = m.num_vertices
    V = [list(struct.unpack_from("<3h", clean, m.vertices + 8 * i)) for i in range(nv)]
    VD = None                                         # R34: the damage model's positions (same vertex order)
    if damage:
        try:
            md = Model.parse(-1, damage)
            if md.num_vertices == nv:
                VD = [list(struct.unpack_from("<3h", damage, md.vertices + 8 * i)) for i in range(nv)]
        except Exception:
            VD = None
    alias = list(range(nv))
    def find(i):
        while alias[i] != i:
            i = alias[i]
        return i
    # 1. weld the shortest edges until <= MAX_VERTS distinct vertices
    live = nv
    while live > MAX_VERTS:
        best = None
        for b in P:
            vs = [find(b[k]) for k in _pverts(b)]
            for k in range(len(vs)):
                a, c = vs[k], vs[(k + 1) % len(vs)]
                if a == c:
                    continue
                d = sum((V[a][j] - V[c][j]) ** 2 for j in range(3))
                if best is None or d < best[0]:
                    best = (d, min(a, c), max(a, c))
        _d, keep, drop = best
        alias[drop] = keep
        live -= 1
    kept = [i for i in range(nv) if find(i) == i]
    newidx = {o: k for k, o in enumerate(kept)}
    vmap = [newidx[find(i)] for i in range(nv)]
    # remap polygons, drop degenerate ones
    pm0, P2 = [], []
    for b in P:
        for k in _pverts(b):
            b[k] = vmap[b[k]]
        vs = [b[k] for k in _pverts(b)]
        if len(set(vs)) < len(vs):
            pm0.append(None)
            continue
        pm0.append(len(P2))
        P2.append(b)
    # 2. pair triangles into quads
    def info(b):
        t = b[0] & 31
        if t == 20:
            return t, [b[4], b[5], b[6]], None, [bytes(b[8 + 2 * k:10 + 2 * k]) for k in range(3)], (b[1], b[2])
        if t == 22:
            return t, [b[4], b[5], b[6]], [b[8], b[9], b[10]], [bytes(b[12 + 2 * k:14 + 2 * k]) for k in range(3)], (b[1], b[2])
        if t == 0:
            return t, [b[1], b[2], b[3]], None, None, bytes(b[4:8])
        return None
    import collections
    edge = collections.defaultdict(list)
    I = {}
    for i, b in enumerate(P2):
        x = info(b)
        if x is None:
            continue
        I[i] = x
        for k in range(3):
            edge[frozenset((x[1][k], x[1][(k + 1) % 3]))].append(i)
    partner = {}
    for e, lst in sorted(edge.items(), key=lambda kv: sorted(kv[0])):
        for x_ in range(len(lst)):
            for y_ in range(x_ + 1, len(lst)):
                i, j = lst[x_], lst[y_]
                if i in partner or j in partner:
                    continue
                A, B = I[i], I[j]
                if A[0] != B[0] or A[4] != B[4] or len(set(A[1]) & set(B[1])) != 2:
                    continue
                ok = True
                for vv in e:
                    ka, kb = A[1].index(vv), B[1].index(vv)
                    if A[3] is not None and A[3][ka] != B[3][kb]:
                        ok = False
                    if A[2] is not None and A[2][ka] != B[2][kb]:
                        ok = False
                if ok and fit_cos > -1.5:                 # R33: nearly coplanar pairs only (a dent bends a quad; Driver 1
                    def nrm_(tri, VV=V):                   # culls the whole quad by its first triangle -> holes)
                        p0, p1, p2 = (VV[find(v)] for v in tri)
                        ax, ay, az = (p1[c] - p0[c] for c in range(3))
                        bx, by, bz = (p2[c] - p0[c] for c in range(3))
                        nx, ny, nz = ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx
                        l = (nx * nx + ny * ny + nz * nz) ** 0.5 or 1.0
                        return nx / l, ny / l, nz / l
                    na, nb = nrm_(A[1]), nrm_(B[1])
                    if na[0] * nb[0] + na[1] * nb[1] + na[2] * nb[2] < fit_cos:
                        ok = False
                    elif VD is not None:                  # R34 (user: hole in the damaged hood): coplanar when dented too
                        da, db = nrm_(A[1], VD), nrm_(B[1], VD)
                        if da[0] * db[0] + da[1] * db[1] + da[2] * db[2] < fit_cos:
                            ok = False
                if ok:
                    partner[i], partner[j] = j, i
    out, pm1 = [], [None] * len(P2)
    for i, b in enumerate(P2):
        if pm1[i] is not None:
            continue
        j = partner.get(i)
        if j is None:
            pm1[i] = len(out)
            out.append(bytes(b))
            continue
        A, B = I[i], I[j]
        sa_sb = [v for v in A[1] if v in B[1]]
        ux = [k for k in range(3) if A[1][k] not in B[1]][0]
        # A in its winding, rotated to start at its unique vertex: (x, s_a, s_b); B's unique vertex d
        ka = [(ux + k) % 3 for k in range(3)]
        x, s_a, s_b = (A[1][k] for k in ka)
        kd = [k for k in range(3) if B[1][k] not in A[1]][0]
        d = B[1][kd]
        t = A[0]
        if t == 0:                                    # flat: Driver 1 splits F4 as (0,1,2) + (0,2,3)
            ring = [s_a, d, s_b, x]
            q = bytes([(b[0] & ~31) | 1, 0, 0, 0] + ring) + A[4]
        else:                                         # textured: ring order (the builder swaps 2/3 into GPU Z order)
            ring_k = [("A", ka[0]), ("A", ka[1]), ("B", kd), ("A", ka[2])]
            uv = b"".join(A[3][k] if w == "A" else B[3][k] for w, k in ring_k)
            ring = [x, s_a, d, s_b]
            head = bytes([(b[0] & ~31) | (21 if t == 20 else 23), b[1], b[2], b[3]]) + bytes(ring)
            col = bytes(b[16:20]) if t == 20 else bytes(b[20:24])
            if t == 20:
                q = head + uv + col
            else:
                nrm = bytes(A[2][k] if w == "A" else B[2][k] for w, k in ring_k)
                q = head + nrm + uv + col
        pm1[i] = pm1[j] = len(out)
        out.append(q)
    pmap = [None if a is None else pm1[a] for a in pm0]
    block = b"".join(out)
    c = bytearray(clean)
    assert len(block) <= sum(len(b) for b in P)
    c[m.poly_block:m.poly_block + len(block)] = block
    struct.pack_into("<h", c, 14, len(out))
    for k, o in enumerate(kept):
        struct.pack_into("<3h", c, m.vertices + 8 * k, *V[o])
    struct.pack_into("<h", c, 12, len(kept))
    dmg = None
    if damage is not None:
        dm = Model.parse(-1, damage)
        dd = bytearray(damage)
        DV = [struct.unpack_from("<3h", damage, dm.vertices + 8 * i) for i in range(dm.num_vertices)]
        for k, o in enumerate(kept):
            if o < len(DV):
                struct.pack_into("<3h", dd, dm.vertices + 8 * k, *DV[o])
        struct.pack_into("<h", dd, 12, min(len(kept), dm.num_vertices))
        dmg = bytes(dd)
    return bytes(c), dmg, vmap, pmap


_FITS = {}
SHIFT = os.environ.get("CHI_POLISH_CARS_COG", "1") != "0"   # C42 r3: body at D2's cog (0 = model origin as before)


def cog_shift(d2: int):
    """(dx, dz) in Driver 1 units: Driver 2's cog after FixCarCos x SCALE (polish_cosmetics.body_shift)."""
    if not SHIFT:
        return (0, 0)
    import inputs, polish_cosmetics
    cx, cz = polish_cosmetics.body_shift(open(inputs.path(__import__("cityprofile").P.lcf), "rb").read(), d2)
    dy = -polish_cosmetics.ride_extras().get(d2, 0)        # R35: higher clearance = the body raised (y up is negative)
    return (int(round(cx * SCALE)), int(round(cz * SCALE)), dy)


def shift_model(data: bytes, sh) -> bytes:
    if not sh or all(v == 0 for v in sh):
        return data
    dy = sh[2] if len(sh) > 2 else 0
    b = bytearray(data)
    nv = struct.unpack_from("<h", b, 12)[0]
    vo = struct.unpack_from("<i", b, 16)[0]
    for i in range(nv):
        o = vo + 8 * i
        if o + 6 > len(b):
            break
        x, y, z = struct.unpack_from("<3h", b, o)
        struct.pack_into("<3h", b, o, x + sh[0], y + dy, z + sh[1])
    return bytes(b)


def fitted(d2_cm: bytes, d2: int, player: bool = False):
    """Cached fit_model of a Driver 2 model (clean, damage, vmap, pmap); None when CHI_POLISH_CARS_FIT=0. player: the
    player-car version (R33: only nearly coplanar triangle pairs become quads, FIT_ANGLE; the player's buffers hold 260
    polygons), else every pair (AI cars: <= 150 polygons)."""
    if not FIT:
        return None
    key = (id(d2_cm), d2, player)
    if key not in _FITS:
        ents = _entries(d2_cm)
        sh = cog_shift(d2)
        clean = shift_model(scale_model(_model_bytes(d2_cm, ents[d2][0])), sh)
        dam = shift_model(scale_model(_model_bytes(d2_cm, ents[d2][1])), sh) if ents[d2][1] != -1 else None
        _FITS[key] = fit_model(clean, dam, FIT_COS if player else -2.0)
    return _FITS[key]


def fit_maps(d2_cm: bytes, player: bool = False) -> dict:
    """{d2 model: (vmap, pmap)} for the mapped models (damage_tables remaps the DEN rows with it)."""
    out = {}
    for d2 in set(slot_map().values()):
        f = fitted(d2_cm, d2, player)
        if f:
            out[d2] = (f[2], f[3])
    return out


def lump28(d2_cm: bytes) -> bytes:
    """Driver 1 lump 28 with the mapped Driver 2 car models (clean, damage, low)."""
    ents = _entries(d2_cm)
    m = slot_map()
    body = bytearray()
    table = []
    count = 0
    for d1 in range(13):
        d2 = m.get(d1)
        row = []
        for k in range(3):
            off = ents[d2][k] if d2 is not None else -1
            if off == -1:
                row.append(-1)
                continue
            data = scale_model(_model_bytes(d2_cm, off))
            f = fitted(d2_cm, d2, d1 >= 5) if k < 2 else None   # C58: clean + damage fitted to Driver 1's car buffers
            if f:
                data = f[k]
            elif k == 2:                               # the low model: the same body shift (cog)
                data = shift_model(data, cog_shift(d2))
            row.append(len(body))
            body += struct.pack("<i", len(data)) + data
            while len(body) % 4:
                body.append(0)
            count += 1
        table.append(row)
    out = struct.pack("<i", count) + b"".join(struct.pack("<3i", *r) for r in table) + bytes(body)
    return out


def models_for(cars_lev):
    """Model objects of the mapped Driver 2 cars (texrepack.collect: which textures the cars need)."""
    from models import Model
    cm = cars_lev.loadtime.get(28).data
    ents = _entries(cm)
    out = []
    for d2 in sorted(set(slot_map().values())):
        for off in ents[d2]:
            if off != -1:
                out.append(Model.parse(-1, _model_bytes(cm, off)))
    return out


def special_order(cars_lev, special_pages):
    """Driver 2 special pages in Driver 1's pair order (pair k = player slot 5 + k), each pair
    (minor page, major page) like LA's list; pages no mapped car uses are dropped."""
    from models import Model
    from texrepack import model_texrefs
    import collections
    cm = cars_lev.loadtime.get(28).data
    ents = _entries(cm)
    sp = set(special_pages)
    order = []
    for d1 in (5, 6, 7, 8):
        d2 = slot_map().get(d1)
        if d2 is None or ents[d2][0] == -1:
            continue
        m = Model.parse(-1, _model_bytes(cm, ents[d2][0]))
        cnt = collections.Counter()
        q = m.poly_block
        from models import POLY_SIZES
        for _ in range(m.num_polys):
            t = m.data[q] & 31
            if t in (4, 5, 7, 9, 10, 11, 17, 20, 21, 22, 23) and m.data[q + 1] in sp:
                cnt[m.data[q + 1]] += 1
            q += POLY_SIZES.get(t, 4)
        pages = [p for p, _n in sorted(cnt.items(), key=lambda kv: kv[1])]   # minor first
        if not pages and cnt == collections.Counter() and m.num_polys:
            # C124 (Vegas / Rio 28.10.): choice 0 = D2 model 1, a palettised civilian without special pages. Driver 1 loads
            # the pair of the CHOSEN car (pair k = choice k), so the slot keeps a blank pair (negative ids, convert makes
            # them empty pages) instead of shifting the later cars onto the wrong pairs. Chicago / Havana never get here.
            order += [-(2 * d1 + 1), -(2 * d1 + 2)]
            continue
        order += [p for p in pages if p not in order]
    return order


def palettes(d2_pal: bytes, keep_pages: set, remap, extra=()):
    """Driver 1 lump 25 from Driver 2's; remap(tpage, texnum) -> (new page, new texnum) or None.
    extra: further Driver 1 entries (44 bytes each) appended, e.g. the base city's pedestrian palettes."""
    # R32 (user: civilians drawn white / half): the first word is the number of STORED CLUTs, not of entries;
    # REDRIVER2 ProcessPalletLump reads entries until palette == -1. Reading only that many entries dropped every entry
    # after them (model 2's BON31, DOOR31, BWING31, BOOT31, windows, roof: their palettes 2-4 drew CLUT 0).
    p = 4
    cluts = []
    out = []
    while True:
        if p + 16 > len(d2_pal):
            break
        palette, texnum, tpage, clut_no = struct.unpack_from("<4i", d2_pal, p)
        if palette == -1:
            break
        if clut_no == -1:
            clut = d2_pal[p + 16: p + 48]
            cluts.append(clut)
            p += 48
        else:
            clut = cluts[clut_no] if 0 <= clut_no < len(cluts) else bytes(32)
            p += 16
        if tpage not in keep_pages or palette > 3:      # Driver 1 has 4 colour variants (0..3), Driver 2 5
            continue
        r = remap(tpage, texnum)
        if r is None:
            continue
        out.append(struct.pack("<3i", palette, r[1], r[0]) + clut)
    out += list(extra)
    if os.environ.get("CHI_POLISH_CARPAL_MERGE", "1") == "1":    # S1: identical entries (after merged textures) once only
        seen, uniq = set(), []
        for e in out:
            if e not in seen:
                seen.add(e); uniq.append(e)
        out = uniq
    return struct.pack("<i", len(out)) + b"".join(out)          # Driver 1: count + count x 44 bytes, no terminator


def merge_identical_car_textures(d2_pal: bytes, res, src: str) -> int:
    """S1 / CLUT allocator relief (Polish 21.10., CHI_POLISH_CARPAL_MERGE): car textures on the same permanent page
    whose base CLUT AND all colour-variant CLUTs (Driver 2 PALLET) are identical (left/right lights, wings, doors) are
    drawn through one texture number: their polygons are redirected to the first one, so each pair costs one set of
    palette entries in the CLUT allocator instead of two. Returns the number of redirected textures."""
    import collections
    p, cluts, var = 4, [], collections.defaultdict(dict)
    while p + 16 <= len(d2_pal):
        palette, texnum, tpage, clut_no = struct.unpack_from("<4i", d2_pal, p)
        if palette == -1:
            break
        if clut_no == -1:
            clut = d2_pal[p + 16: p + 48]; cluts.append(clut); p += 48
        else:
            clut = cluts[clut_no] if 0 <= clut_no < len(cluts) else bytes(32); p += 16
        r = res.remap.get((src, tpage, texnum))
        if r and palette <= 3:
            var[(r[0], r[1])][palette] = clut
    leader = {}
    for (pg, det), vs in sorted(var.items()):
        page = res.pages.get(pg)
        if page is None or det >= len(page.cluts):
            continue
        key = (pg, page.cluts[det], tuple(sorted(vs.items())))
        leader.setdefault(key, det)
        if leader[key] != det:
            leader[(pg, det)] = leader[key]
    n = 0
    for k, r in list(res.remap.items()):
        new = leader.get((r[0], r[1]))
        if isinstance(new, int) and k[0] == src:
            res.remap[k] = (r[0], new) + tuple(r[2:]); n += 1
    return n


def cop_palettes(cars_lev, remap) -> list:
    """C59: Driver 1 gives every AI car a palette 1..4 (AI record +0x11), the cop too; Driver 2's cop (model 3) has no
    colour variants in lump 25 (its one paint is the police livery), so without entries Driver 1 drew it with stray
    CLUTs (noise). Entries palette 0..3 = the textures' own CLUT for the cop model's (slot 0) textures."""
    from models import Model
    from texrepack import model_texrefs
    from texpages import read_pages
    d2 = slot_map().get(0)
    if d2 is None:
        return []
    cm = cars_lev.loadtime.get(28).data
    ents = _entries(cm)
    if ents[d2][0] == -1:
        return []
    ti, tp = read_pages(cars_lev)
    out = []
    for page, k in sorted(model_texrefs(Model.parse(-1, _model_bytes(cm, ents[d2][0])), {})):
        if page not in tp or k >= len(tp[page].cluts):
            continue
        r = remap(page, k)
        if r is None:
            continue
        for pal in range(4):
            out.append(struct.pack("<3i", pal, r[1], r[0]) + bytes(tp[page].cluts[k]))
    return out


# --- whole car pages (damage twins) ----------------------------------------------------------
# Driver 1 shows car damage by shifting a polygon's u: civilian cars and the cop by +128 (BCK1 ->
# BCK1DAM, COP3 -> COP3DAM, same v), the player's cars by +64 per stage (xxxDM0 .. xxxDM3).
# Driver 2's civilian pages use the same +128 layout (FWING11 -> FWING12). texrepack packs each
# texture on its own, so the twin at u+128 is lost and damaged traffic shows a neighbour texture.
# CHI_POLISH_CARPAGES=1 (on with CHI_POLISH_D2CARS=1) keeps the traffic / cop cars' texture
# pages whole as permanent pages (one VRAM slot less for area pages per page).

def _is_d2(lev):
    return not getattr(lev, "d1", False)


def carpages_mode():
    """"1" = whole car pages, "2" = twin pages (clean + damage twin at u+128, rest of the page free
    for other permanent textures; default with CHI_POLISH_D2CARS=1), "" = off."""
    m = os.environ.get("CHI_POLISH_CARPAGES", "2")   # "2" default since b15 (C49); "0" = off
    if m == "0":
        return ""
    if m in ("1", "2"):
        return m
    return "2" if enabled() else ""


def carpages_enabled():
    return carpages_mode() == "1"


# C42 r3 (b): a damage twin is only ever drawn through its clean texture (DentCar shifts u by +128 on the clean polygon:
# same texture number, same CLUT, as in Driver 2's denting.c), so it needs its pixels at u+128 but no texture entry and no
# CLUT slot (a page holds 32): the twin pages hold twice the car textures (CHI_POLISH_TWIN_PIXELS=0: entries as before).
TWIN_PIXELS = os.environ.get("CHI_POLISH_TWIN_PIXELS", "1") != "0"
TWINNED = set()        # R33: (source, page, texture) whose +128 damage twin attach_twins packed


def attach_twins(groups, lev, src, special_pages):
    """CHI_POLISH_CARPAGES=2: give every traffic/cop car texture whose damage twin sits at u+128 on
    its source page a `twin` Item (packed at +128 by pack_twins); car items get `carfirst` (low
    texture numbers: Driver 1's car CLUT table has 30 entries per page). Returns the number of pairs."""
    from texpages import read_pages
    from texrepack import Item
    pages = set(fixed_pages(lev, special_pages))
    ti, tp = read_pages(lev)
    names = lev.loadtime.get(5).data
    have = {(it.src, it.page, it.detail) for its in groups.values() for it in its}
    n = 0
    for its in groups.values():
        for it in its:
            if it.src != src or it.page not in pages:
                continue
            it.carfirst = True
            d = ti.details[it.page][it.detail]
            w, h = d[4] or 256, d[5] or 256
            if it.w != w or it.h != h or w > 128:
                continue
            k = next((k for k, e in enumerate(ti.details[it.page])
                      if e[2] == d[2] + 128 and e[3] == d[3] and (e[4] or 256) == w and (e[5] or 256) == h), None)
            if k is None or (src, it.page, k) in have:
                continue
            e = ti.details[it.page][k]
            pg = tp[it.page]
            tw = Item(src, it.page, k, names[e[1]: names.index(b"\0", e[1])], e[2], e[3], w, h,
                      pg.cluts[k] if k < len(pg.cluts) else bytes(32), pg.rect(e[2], e[3], w, h), e[0])
            tw.ow, tw.oh = w, h
            tw.carfirst = True
            tw.pixels_only = TWIN_PIXELS          # C42 r3 (b): no texture entry / CLUT slot of its own
            it.twin = tw
            TWINNED.add((src, it.page, it.detail))
            n += 1
    return n


# --- C42 r3 (b): Driver 1's car CLUT table (Infrastructure 17.10.) ------------------------------------------------------
# The palette loader (FUN_00056610) and the car builder (FUN_0003BDC8, palettised models) write one CLUT word per
# (page, texture) to 0x800BE9FC + 600 * (page - first car page) + 20 * min(texture, 30): a table of TWO pages (first car
# page = 5 in city slot 3) of 30 textures. Behind it lie live variables (the 4x4 minimap tile grid 0x800BEEAC, the skid
# buffer ends 0x800BEED4.., the font copy 0x800BF2EC): d2cars6 put civilian textures on pages 7/8 and wrote 32 palette
# words + the builder's words into them (e.g. 0x800BEEE8). Palettised = the civilian models 2-3 (lump slots 1-2) and the
# pedestrians: their textures are packed first (first two car pages, lowest texture numbers); convert.py keeps only
# palette entries inside the table and refuses a level whose palettised model polygons fall outside.
PALETTE_SLOTS = (1, 2, 3) if SIX else (1, 2)   # R33: Driver 2's model 3 (our model 4) has 5 colour variants too
CLUT_PAGES, CLUT_TEXTURES = 2, 30


def mark_palette_items(groups, cars_lev, src, base_lev):
    """Set `palette` on the items of the palettised civilian models (cars_lev textures, source src) and of the base city's
    pedestrian palettes (source "B"). Returns the number marked."""
    from models import Model
    from texrepack import model_texrefs
    cm = cars_lev.loadtime.get(28).data
    ents = _entries(cm)
    m = slot_map()
    keys = set()
    for s in PALETTE_SLOTS:
        d2 = m.get(s)
        if d2 is None:
            continue
        for off in ents[d2]:
            if off != -1:
                keys |= {(src, p, k) for p, k in model_texrefs(Model.parse(-1, _model_bytes(cm, off)), {})}
    bpal = base_lev.loadtime.get(25).data
    for q in range(4, 4 + 44 * struct.unpack_from("<i", bpal, 0)[0], 44):
        _a, t, tp = struct.unpack_from("<3i", bpal, q)
        keys.add(("B", tp, t))
    n = 0
    for its in groups.values():
        for it in its:
            if (it.src, it.page, it.detail) in keys:
                it.palette = True
                n += 1
    return n


def pack_twins(items, group, plain_pack, free_spot, max_cluts, page_size=256):
    """pack_group for the permanent group with twin items: pairs first into twin pages (clean in
    the left half at x, twin at x + 128), then the other textures first-fit into the free space of
    those pages, the rest by the normal packer (plain_pack)."""
    import numpy as np
    from texrepack import PackedPage
    half = page_size // 2
    pal = lambda it: not getattr(it, "palette", False)          # C42 r3 (b): palettised first (the CLUT table's 2 pages)
    pairs = sorted((it for it in items if getattr(it, "twin", None) is not None), key=lambda it: (pal(it), -it.h, -it.w))
    rest = sorted((it for it in items if getattr(it, "twin", None) is None), key=lambda it: (pal(it), -it.h, -it.w))
    pages = []          # (PackedPage, occupancy)
    nclut = lambda pp: sum(1 for e in pp.items if not getattr(e[0], "pixels_only", False))
    npal = lambda pp: sum(1 for e in pp.items if getattr(e[0], "palette", False))   # <= CLUT_TEXTURES per page

    def place_pair(it):
        for slot in pages + [None]:
            if slot is None:
                slot = (PackedPage(group), np.zeros((page_size, page_size), dtype=bool))
                pages.append(slot)
            pp, occ = slot
            if nclut(pp) + (1 if getattr(it.twin, "pixels_only", False) else 2) > max_cluts:
                continue
            if getattr(it, "palette", False) and npal(pp) >= CLUT_TEXTURES:
                continue
            m = np.ones_like(occ)
            m[:, :half] = occ[:, :half] | occ[:, half:]
            pos = free_spot(m, it.w, it.h)
            if pos is None:
                continue
            x, y = pos
            pp.items += [(it, x, y), (it.twin, x + half, y)]
            occ[y:y + it.h, x:x + it.w] = True
            occ[y:y + it.h, x + half:x + half + it.w] = True
            return

    def place_single(it, new_page):
        for slot in pages + ([None] if new_page else []):
            if slot is None:
                slot = (PackedPage(group), np.zeros((page_size, page_size), dtype=bool))
                pages.append(slot)
            pp, occ = slot
            if nclut(pp) >= max_cluts:
                continue
            if getattr(it, "palette", False) and npal(pp) >= CLUT_TEXTURES:
                continue
            pos = free_spot(occ, it.w, it.h)
            if pos is not None:
                x, y = pos
                pp.items.append((it, x, y))
                occ[y:y + it.h, x:x + it.w] = True
                return True
        return False

    # palettised pairs, palettised singles (pedestrians), then the other pairs, then the rest
    for it in pairs:
        if not pal(it):
            place_pair(it)
    for it in rest:
        if not pal(it):
            place_single(it, True)
    for it in pairs:
        if pal(it):
            place_pair(it)
    left = [it for it in rest if pal(it) and not place_single(it, False)]
    return [pp for pp, _ in pages] + plain_pack(left, group)


def fixed_pages(cars_lev, special_pages=()):
    """Texture pages of the traffic / cop car models (Driver 1 slots 0-2) to keep whole: pages
    with >= 4 of their textures used (not the city page that only gives UNDER)."""
    from models import Model
    from texrepack import model_texrefs
    import collections
    cm = cars_lev.loadtime.get(28).data
    ents = _entries(cm)
    m = slot_map()
    mapped = enabled() or (os.environ.get("CHI_POLISH_D2CARS", "") == "mixed" and _is_d2(cars_lev))
    slots = [m.get(s) for s in AI_SLOTS] if mapped else [0, 1, 2]
    used = set()
    for s in slots:
        if s is None or ents[s][0] == -1:
            continue
        for off in ents[s][:1]:
            if off != -1:
                used |= model_texrefs(Model.parse(-1, _model_bytes(cm, off)), {})
    pages = collections.Counter(p for p, _k in used)
    return sorted(p for p, n in pages.items() if n >= 4 and p not in set(special_pages))


# --- damage zone tables (engine spec in research_d2_cars.md) --------------------------------
# Driver 1's damage code (0x8003E6A0) takes per-model zone tables through four pointers set at
# 0x8003E5D8..E4 from per-city tables (+ CITY * 4): civilian/cop vertices 0x8008A6DC -> *0x800973E0,
# player vertices 0x8008A6BC -> *0x800973E4, civilian/cop polygons 0x8008A71C -> *0x800973D0, player
# polygons 0x8008A6FC -> *0x800973D4. Rows: civilian/cop by Driver 1 slot 0..2, player by car choice
# 0..3 (= slot 5..8); a row is 6 zones x 50 vertex numbers (300 B) or 6 zones x 70 polygon numbers
# (420 B), 0xFF-terminated. Driver 2's CHICAGO.DEN has the same rows per Driver 2 model (int offsets
# [13], then per model: verts 300, polys 420, per-polygon damage-level kind 255/256).
DEN_VERTS, DEN_POLYS, DEN_LEVELS = 300, 420, 256


def damage_tables(den: bytes, fits: dict = None, fits_player: dict = None, extra=()) -> dict:
    """Driver 1 rows for the mapped Driver 2 cars: {"civ_verts", "player_verts", "civ_polys",
    "player_polys", "civ_levels", "player_levels"} as bytes (rows concatenated). fits: fit_maps() of the
    level's car models (C58): vertex / polygon numbers renumbered like the fitted models."""
    offs = struct.unpack_from("<13i", den, 0)
    m = slot_map()

    def remap(raw, size, mp):
        # zones of size // 6 bytes, each a 0xFF-terminated list of numbers
        z = size // 6
        out = b""
        for k in range(6):
            seq, seen = [], set()
            for v in raw[k * z:(k + 1) * z]:
                if v == 0xFF:
                    break
                n = mp[v] if v < len(mp) else None
                if n is not None and n not in seen:
                    seen.add(n)
                    seq.append(n)
            seq = seq[:z - 1]
            out += bytes(seq) + b"\xff" * (z - len(seq))
        return out

    def row(d2, start, size, fs):
        if d2 is None or offs[d2] <= 0:
            return b"\xff" + bytes(size - 1)
        o = offs[d2] + start
        raw = (den[o: o + size] + bytes(size))[:size]
        if fs and d2 in fs and start < DEN_VERTS + DEN_POLYS:
            raw = remap(raw, size, fs[d2][0] if start == 0 else fs[d2][1])
        return raw

    out = {}
    for name, slots, fs in (("civ", AI_SLOTS, fits), ("player", (5, 6, 7, 8), fits_player or fits)):
        out[name + "_verts"] = b"".join(row(m.get(s), 0, DEN_VERTS, fs) for s in slots)
        out[name + "_polys"] = b"".join(row(m.get(s), DEN_VERTS, DEN_POLYS, fs) for s in slots)
        out[name + "_levels"] = b"".join(row(m.get(s), DEN_VERTS + DEN_POLYS, DEN_LEVELS, fs) for s in slots)
    out["extra"] = {d2: row(d2, 0, DEN_VERTS, fits) + row(d2, DEN_VERTS, DEN_POLYS, fits) for d2 in extra}   # AI-fitted
    return out


def level_rows(den: bytes, fits: dict, fits_player: dict = None, twin_ok=None, d2_cm: bytes = None) -> bytes:
    """C42 r3 (17.10.): Driver 2's per-polygon damage kind L (gHDCarDamageLevels, 0 body / 1 lights) for D2's DentCar rule
    offset = ((L^1) ^ ((L^1)|level)) * 64 (exe_patches c42d_patches), renumbered like the fitted models: 7 (9 with SIX)
    rows of 256 B = AI resident models 1..3 (1..5: slots 0..4), then player choices 0..3 (slots 5..8).
    R33: the bytes are the final DCAVE values L ^ 1 (the plugin writes them as they are): player rows (Driver 2 special
    pages kept whole) L ^ 1; AI rows 1 (body rule: clean, its +128 twin at level 2; only the +128 twin is packed, not the
    +64 light stage) or 3 (no shift) for a polygon whose texture has no +128 twin in the packed pages (twin_ok)."""
    offs = struct.unpack_from("<13i", den, 0)
    m = slot_map()
    out = b""
    for d1 in AI_SLOTS + (5, 6, 7, 8):
        d2 = m.get(d1)
        row = bytearray(b"\x01" * 256)
        fs = (fits_player or fits) if d1 >= 5 else fits
        if d2 is not None and offs[d2] > 0:
            raw = den[offs[d2] + DEN_VERTS + DEN_POLYS: offs[d2] + DEN_VERTS + DEN_POLYS + DEN_LEVELS]
            pmap = fs[d2][1] if fs and d2 in fs else list(range(256))
            done = set()
            for old, new in enumerate(pmap):
                if new is None or new >= 256 or new in done or old >= len(raw):
                    continue
                row[new] = ((raw[old] & 1) ^ 1) if d1 >= 5 else 1
                done.add(new)
            if d1 < 5 and twin_ok is not None and d2_cm is not None:
                f = fitted(d2_cm, d2, False)
                if f:
                    from models import Model, POLY_SIZES
                    mm = Model.parse(-1, f[0])
                    q = mm.poly_block
                    for i in range(min(mm.num_polys, 256)):
                        t = mm.data[q] & 31
                        if t in (20, 21, 22, 23) and not twin_ok(mm.data[q + 1], mm.data[q + 2]):
                            row[i] = 3
                        q += POLY_SIZES.get(t, 4)
        out += bytes(row)
    return out


def write_damage_blob(den_path: str, out_path: str):
    """One file: the six tables back to back (order and sizes as damage_tables, civ 3 rows, player
    4 rows), for the engine change to point the four zone pointers (+ level tables) at."""
    t = damage_tables(open(den_path, "rb").read())
    order = ["civ_verts", "player_verts", "civ_polys", "player_polys", "civ_levels", "player_levels"]
    blob = b"".join(t[k] for k in order)
    open(out_path, "wb").write(blob)
    off = 0
    layout = []
    for k in order:
        layout.append("%s @%d (%d)" % (k, off, len(t[k])))
        off += len(t[k])
    return layout
