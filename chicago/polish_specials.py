"""polish_specials.py - C42 round 3 (c): Driver 2's regional special vehicles (user R32: option B, the special's textures
in the texture sets of the areas where it spawns).

Driver 2 (REDRIVER2 spool.c): the special slot (residentCarModels[4]) follows the LOADED AREA,
SpecialByRegion[Chicago][area] + 7 = model 12 / 8 (fire engine) / 10 / 9; CheckSpecialSpool swaps it only while no car uses
it. Here: lump slot 4 (resident model 5) is the special. The converter
  - gives every D1 region its special (Driver 2's area of the region, convert.build_world region_d2area),
  - adds each special's textures (clean / damage / low models; Driver 2 special pages, source "C") to the texture sets
    of the areas loadable from its regions (+ MARGIN regions around them): texrepack.EXTRA_MODELS,
  - writes <lev>.spc.bin (build_package -> assets/specials.bin): the four special models with their polygons remapped
    to those area pages, their cosmetics row, wheel size, zone rows, and the region -> special table + the areas that
    hold each special's textures.
The plugin swaps model 5 at runtime (host-only: models in mod memory, polygon groups rebuilt by the plugin after every
area texture load; M8: a guest spool like Driver 2's). CHI_SPECIALS=0: off (slot 4 = Driver 2 model 4, the van).
"""
from __future__ import annotations

import os
import struct

from cityprofile import P as _CITY   # M3: per-city profile
SPECIAL_BY_AREA = list(_CITY.special_by_area)   # spool.c SpecialByRegion[city] (Chicago: row 0)
SPECIALS = tuple(_CITY.specials)
DEFAULT = _CITY.special_default  # Chicago: 10, the most common special (and D2's mission default residentModels[4])
MARGIN = int(os.environ.get("CHI_SPECIALS_MARGIN", "0"))   # 1: also the areas loadable from its regions
MAGIC = 0x53504331               # "1CPS"
MAGIC2 = 0x53504332              # "2CPS": R34 slot asset (+ slot header; per special a slot block after its models)
# R34 (user 25 = A, 18.10.): like Driver 2 (a special-car texture slot loaded with the special model), the special's
# textures live in ONE dedicated slot instead of the area sets: the empty bottom half (256 x 128) of a permanent page
# plus SLOT_N reserved texture entries of that page. Each special's textures are packed (halved where needed) into the
# slot; the plugin uploads texels + CLUTs when it swaps the special in (only while no car uses model 5, so the old
# textures stay until then). CHI_SPECIAL_SLOT=0: R33's area sets.
SLOT = os.environ.get("CHI_SPECIAL_SLOT", "1") != "0"
SLOT_W, SLOT_H, SLOT_N = 256, 128, _CITY.special_slot_entries   # M3 profile (Chicago 16)
# Q45 B (user 23.10.): special damage textures in the slot. Driver 2's damage shift adds the offset to U (cars.c: the
# DENTUVS byte is added to the clut_uv0 / tpage_uv1 / uv3_uv2 words, i.e. to u0/u1/u2; twin = the texture 128 texels to
# the RIGHT on its Driver 2 page, cf. polish_cars.attach_twins). Clean textures in the slot's columns 0..127, each
# damaged copy DMG_OFF = 128 columns to the right (Driver 2's own rule: level byte 1 = L^1 for body polygons, +128 at
# level 2; 3 = no shift; <lev>.spd.bin); textures without a twin anywhere in the rest. Uniform area-filtered downscale
# (palette re-quantised) at the largest scale that packs, then per-texture growth. Default off.
SPECDMG = os.environ.get("CHI_POLISH_SPECDMG", "0") == "1"
DMG_OFF = 128                    # along U (columns)
SPECDMG_INFO = {}                # model -> dict(scale, kept, twinned slot entries)
LEVEL_ROWS = {}                  # model -> 256 B level row (asset() fills it with SPECDMG)


def enabled():
    import polish_cars
    return polish_cars.enabled() and polish_cars.SIX and os.environ.get("CHI_SPECIALS", "1") != "0"


_USABLE = []


def usable() -> set:
    """Specials that fit Driver 1's AI car buffers (fitted clean model <= 150 polygons: the per-car UV offsets 0x800AF97A
    hold 150; Driver 2 model 12 has 152 and stays a player car only)."""
    if not _USABLE:
        import inputs
        import polish_cars as pc
        from levfile import Lev
        from models import Model
        cm = Lev.parse(inputs.read(_CITY.lev_day)).loadtime.get(28).data
        for m in SPECIALS:
            f = pc.fitted(cm, m)
            if f and Model.parse(-1, f[0]).num_polys <= 150:
                _USABLE.append(m)
    return set(_USABLE)


def area_specials(world) -> dict:
    """our area -> its special: like Driver 2 (one special per LOADED area, SpecialByRegion[LoadedArea]) the majority of
    Driver 2's specials over the area's regions (Driver 2's own area of each region, region_d2area)."""
    import collections
    votes = collections.defaultdict(collections.Counter)
    ok = usable()
    for r, a2 in world["region_d2area"].items():
        v = SPECIAL_BY_AREA[a2] if 0 <= a2 < len(SPECIAL_BY_AREA) else 0
        if v and v + 7 in ok:
            votes[world["region_area"][r]][v + 7] += 1
    return {a: c.most_common(1)[0][0] for a, c in votes.items()}


def region_specials(world) -> dict:
    sa = area_specials(world)
    return {r: sa.get(a, 0) for r, a in world["region_area"].items()}


def special_areas(world) -> dict:
    """special model -> our areas whose texture sets carry it (the areas it belongs to; MARGIN 1 adds the areas
    loadable from those areas' regions)."""
    sa = area_specials(world)
    out = {m: {a for a, s in sa.items() if s == m} for m in SPECIALS}
    if MARGIN > 0:
        load = world["loadable"]
        for m in SPECIALS:
            extra = set()
            for r, a in world["region_area"].items():
                if a in out[m]:
                    extra |= set(load.get(r, ()))
            out[m] |= extra
    return out


def slot_mode() -> bool:
    return enabled() and SLOT


def reserve_slot(res) -> dict:
    """R34: a permanent page whose bottom half (v 128..255) is empty and that has SLOT_N free texture entries (<= 31
    per page, the page loader's CLUT rows); SLOT_N placeholder entries (zero CLUTs) are appended to it. Returns the slot
    (page, first entry, x, y, w, h, n)."""
    for idx in res.permanent:
        dets, pg = res.details[idx], res.pages[idx]
        if len(dets) + SLOT_N > 31 or len(pg.cluts) != len(dets):
            continue
        if any(d[3] + (d[5] or 256) > 256 - SLOT_H for d in dets):
            continue
        if any(pg.texels[(256 - SLOT_H) * 128:]):
            continue
        base = len(dets)
        for j in range(SLOT_N):
            dets.append((0, b"SPCSLOT%d" % j, (j % 16) * 16, 256 - SLOT_H, 16, 16))
            pg.cluts.append(bytes(32))
        return dict(page=idx, base=base, x=0, y=256 - SLOT_H, w=SLOT_W, h=SLOT_H, n=SLOT_N)
    raise SystemExit("specials slot: no permanent page with an empty %dx%d bottom half and %d free entries "
                     "(CHI_SPECIAL_SLOT=0 = area sets)" % (SLOT_W, SLOT_H, SLOT_N))


def _sky_pack(sizes, W, H):
    """sizes [(w, h)] -> positions or None (bottom-left skyline in W x H, tallest first)."""
    order = sorted(range(len(sizes)), key=lambda i: (-sizes[i][1], -sizes[i][0]))
    sky = [(0, 0, W)]
    pos = [None] * len(sizes)
    for i in order:
        w, h = sizes[i]
        best = None
        for k in range(len(sky)):
            x = sky[k][0]
            if x + w > W:
                break
            y, width, j = 0, 0, k
            while width < w and j < len(sky):
                y = max(y, sky[j][1])
                width += sky[j][2]
                j += 1
            if width < w or y + h > H:
                continue
            if best is None or (y + h, x) < (best[1] + h, best[0]):
                best = (x, y)
        if best is None:
            return None
        x, y = best
        new = []
        for sx, sy, sw in sky:
            if sx + sw <= x or sx >= x + w:
                new.append((sx, sy, sw))
            else:
                if sx < x:
                    new.append((sx, sy, x - sx))
                if sx + sw > x + w:
                    new.append((x + w, sy, sx + sw - (x + w)))
        new.append((x, y + h, w))
        new.sort()
        sky = []
        for seg in new:
            if sky and sky[-1][1] == seg[1] and sky[-1][0] + sky[-1][2] == seg[0]:
                sky[-1] = (sky[-1][0], seg[1], sky[-1][2] + seg[2])
            else:
                sky.append(seg)
        pos[i] = (x, y)
    return pos


def _shelf_pack(sizes, W, H):
    """sizes [(w, h)] -> positions or None (skyline, else shelves, tallest first)."""
    p = _sky_pack(sizes, W, H)
    if p:
        return p
    order = sorted(range(len(sizes)), key=lambda i: (-sizes[i][1], -sizes[i][0]))
    pos = [None] * len(sizes)
    x = y = shelf = 0
    for i in order:
        w, h = sizes[i]
        if w > W:
            return None
        if x + w > W:
            x, y, shelf = 0, y + shelf, 0
        if y + h > H:
            return None
        pos[i] = (x, y)
        x += w
        shelf = max(shelf, h)
    return pos


_D2PAGES = None


def slot_layout(chi, m: int, remap: dict, permanent: set, slot: dict):
    """(remap overlay, texel block, CLUT list) of special m in the slot: its textures (clean / damage / low models) that
    are not already on a permanent page, halved (longer side, nearest neighbour) largest first until they pack."""
    import polish_cars as pc
    from models import Model
    from texrepack import model_texrefs
    from texpages import read_pages, Page
    global _D2PAGES
    if _D2PAGES is None or _D2PAGES[0] is not chi:
        _D2PAGES = (chi,) + tuple(read_pages(chi))
    _c, ti, pages = _D2PAGES
    cm = chi.loadtime.get(28).data
    ents = pc._entries(cm)
    refs = set()
    for off in ents[m]:
        if off != -1:
            refs |= model_texrefs(Model.parse(-1, pc._model_bytes(cm, off)), {})
    items = []
    for p, d in sorted(refs):
        r = remap.get(("C", p, d))
        if r and r[0] in permanent:
            continue                                    # shared car texture already resident (e.g. page 1 entry 0)
        if p not in pages or d >= len(ti.details[p]):
            continue
        det = ti.details[p][d]
        x, y, w, h = det[2], det[3], det[4] or 256, det[5] or 256
        items.append(dict(p=p, d=d, ox=x, oy=y, ow=w, oh=h, rows=pages[p].rect(x, y, w, h), clut=pages[p].cluts[d]))
    if len(items) > slot["n"]:
        raise SystemExit("special %d: %d textures > %d slot entries" % (m, len(items), slot["n"]))
    if SPECDMG:
        return _slot_layout_dmg(m, items, pages, slot)
    while True:
        pos = _shelf_pack([(len(it["rows"][0]), len(it["rows"])) for it in items], slot["w"], slot["h"])
        if pos:
            break
        it = max(items, key=lambda i: len(i["rows"][0]) * len(i["rows"]))
        w, h = len(it["rows"][0]), len(it["rows"])
        it["rows"] = [r[::2] for r in it["rows"]] if w >= h else it["rows"][::2]
    pg = Page()
    overlay, cluts = {}, []
    for j, (it, (x, y)) in enumerate(zip(items, pos)):
        w, h = len(it["rows"][0]), len(it["rows"])
        pg.blit(x, y, it["rows"])
        cluts.append(it["clut"])
        overlay[("C", it["p"], it["d"])] = (slot["page"], slot["base"] + j, slot["x"] + x, slot["y"] + y,
                                             it["ox"], it["oy"], it["ow"], it["oh"], w, h)
    texels = bytes(pg.texels[: slot["h"] * 128])       # rows 0..h-1 of a 256-wide 4-bit page = the slot block
    cluts += [bytes(32)] * (slot["n"] - len(cluts))
    used = sum(len(i["rows"][0]) * len(i["rows"]) for i in items)
    print("specials slot: model %d, %d textures, %d texels (of %d), halved: %d" % (
        m, len(items), used, slot["w"] * slot["h"],
        sum(1 for i in items if len(i["rows"][0]) * len(i["rows"]) < i["ow"] * i["oh"])))
    return overlay, texels, cluts


def _clut_rgb(clut: bytes):
    """16 CLUT words -> [(r, g, b) or None for transparent (0x0000)]."""
    out = []
    for k in range(16):
        w = struct.unpack_from("<H", clut, 2 * k)[0]
        out.append(None if w == 0 else ((w & 31) * 8, ((w >> 5) & 31) * 8, ((w >> 10) & 31) * 8))
    return out


def downscale(rows, clut: bytes, nw: int, nh: int):
    """Area-filtered resize of 4-bit rows (index lists) to nw x nh: each target texel averages the colours of the source
    texels it covers (weighted by overlap) and takes the nearest opaque palette entry (luma-weighted distance);
    transparent if more than half of its area is transparent."""
    import numpy as np
    src = np.array([list(r) for r in rows], dtype=np.int64)
    oh, ow = src.shape
    if (nw, nh) == (ow, oh):
        return [bytes(int(v) for v in r) for r in src]
    pal = _clut_rgb(clut)
    rgb = np.array([c if c else (0, 0, 0) for c in pal], dtype=np.float64)
    opq = np.array([c is not None for c in pal])
    trans_idx = next((k for k, c in enumerate(pal) if c is None), None)
    opq_idx = [k for k in range(16) if opq[k]] or [0]

    def weights(n_src, n_dst):
        wm = np.zeros((n_dst, n_src))
        f = n_src / n_dst
        for i in range(n_dst):
            a0, a1 = i * f, (i + 1) * f
            for j in range(int(a0), min(n_src, int(np.ceil(a1)))):
                wm[i, j] = max(0.0, min(a1, j + 1) - max(a0, j))
        return wm
    wy, wx = weights(oh, nh), weights(ow, nw)
    col = rgb[src]
    op = opq[src].astype(np.float64)
    tot = wy @ np.ones((oh, ow)) @ wx.T
    opw = wy @ op @ wx.T
    acc = np.stack([wy @ (col[:, :, c] * op) @ wx.T for c in range(3)], axis=2)
    cand = rgb[opq_idx]
    out = []
    for y in range(nh):
        row = bytearray(nw)
        for x in range(nw):
            if trans_idx is not None and opw[y, x] * 2 < tot[y, x]:
                row[x] = trans_idx
                continue
            c = acc[y, x] / max(opw[y, x], 1e-9)
            d = (((cand - c) ** 2) * (0.30, 0.59, 0.11)).sum(axis=1)
            row[x] = opq_idx[int(d.argmin())]
        out.append(bytes(row))
    return out


def _sky_place(sky, w, h, H):
    """Bottom-left skyline placement of one w x h rect in a band of height H; sky = [(x, y, width)] (sorted, covering
    the band width). Returns ((x, y), new sky) or None."""
    best = None
    for k in range(len(sky)):
        x = sky[k][0]
        y, width, j = 0, 0, k
        while width < w and j < len(sky):
            y = max(y, sky[j][1])
            width += sky[j][2]
            j += 1
        if width < w or y + h > H:
            continue
        if best is None or (y + h, x) < (best[1] + h, best[0]):
            best = (x, y)
    if best is None:
        return None
    x, y = best
    new = []
    for sx, sy, sw in sky:
        if sx + sw <= x or sx >= x + w:
            new.append((sx, sy, sw))
        else:
            if sx < x:
                new.append((sx, sy, x - sx))
            if sx + sw > x + w:
                new.append((x + w, sy, sx + sw - (x + w)))
    new.append((x, y + h, w))
    new.sort()
    merged = []
    for seg in new:
        if merged and merged[-1][1] == seg[1] and merged[-1][0] + merged[-1][2] == seg[0]:
            merged[-1] = (merged[-1][0], seg[1], merged[-1][2] + seg[2])
        else:
            merged.append(seg)
    return best, merged


def _pack_dmg(sizes, twinned, W, H):
    """Twinned rects into the top band (rows 0..H/2-1; their twins at +H/2 mirror the same skyline), the others into
    what is left of the top band, then of the bottom band. Returns positions or None."""
    for key in (lambda i: (-sizes[i][1], -sizes[i][0]), lambda i: -sizes[i][0] * sizes[i][1],
                lambda i: (-sizes[i][0], -sizes[i][1])):
        pos = _pack_dmg_order(sizes, twinned, W, H, sorted(range(len(sizes)), key=lambda i: (i not in twinned, key(i))))
        if pos:
            return pos
    return None


def _pack_dmg_order(sizes, twinned, W, H, order):
    half = H // 2
    sky = [(0, 0, W)]
    pos = [None] * len(sizes)
    for i in order:
        if i in twinned:
            r = _sky_place(sky, sizes[i][0], sizes[i][1], half)
            if r is None:
                return None
            pos[i], sky = r
    sky2 = list(sky)
    for i in order:
        if i in twinned:
            continue
        r = _sky_place(sky, sizes[i][0], sizes[i][1], half)
        if r is not None:
            pos[i], sky = r
            continue
        r = _sky_place(sky2, sizes[i][0], sizes[i][1], half)
        if r is None:
            return None
        (x, y), sky2 = r
        pos[i] = (x, y + half)
    return pos


def _slot_layout_dmg(m, items, pages, slot):
    """Q45 B: items with a Driver 2 damage twin (u + 128 on the D2 page, texels present) get it DMG_OFF columns to the
    right of their clean copy."""
    from texpages import Page
    twinned = set()
    for j, it in enumerate(items):
        p, x, y, w, h = it["p"], it["ox"], it["oy"], it["ow"], it["oh"]
        if x + 128 + w <= 256:
            tw = pages[p].rect(x + 128, y, w, h)
            if any(any(r) for r in tw):
                it["twin"] = tw
                twinned.add(j)
    W, H = slot["w"], slot["h"]
    assert W == 2 * DMG_OFF

    def pack(sizes):                                     # the band packer works on rows: pack transposed
        r = _pack_dmg([(h_, w_) for w_, h_ in sizes], twinned, H, W)
        return [(b_, a_) for a_, b_ in r] if r else None

    def dims(it, s):
        return max(2, min(it["ow"], int(it["ow"] * s))), max(2, min(it["oh"], int(it["oh"] * s)))
    pos = pack([dims(it, 1.0) for it in items])
    s = 1.0
    if pos is None:
        lo, hi = 0.05, 1.0
        for _ in range(14):                              # largest uniform scale that packs
            mid = (lo + hi) / 2
            p_ = pack([dims(it, mid) for it in items])
            if p_:
                lo, pos = mid, p_
            else:
                hi = mid
        s = lo
        if pos is None:
            raise SystemExit("special %d: no packing with damage twins" % m)
    # then grow single textures along each axis (the most reduced first, 4 % steps) while everything still packs
    sc = [(s, s) for _ in items]

    def dims2(it, q):
        return max(2, min(it["ow"], int(it["ow"] * q[0]))), max(2, min(it["oh"], int(it["oh"] * q[1])))
    for _ in range(60):
        grown = False
        for j in sorted(range(len(items)), key=lambda k: sc[k][0] * sc[k][1]):
            for ax in (0, 1):
                if sc[j][ax] >= 1.0:
                    continue
                trial = list(sc)
                q = list(sc[j])
                q[ax] = min(1.0, q[ax] * 1.04)
                trial[j] = tuple(q)
                p_ = pack([dims2(it, trial[k]) for k, it in enumerate(items)])
                if p_:
                    sc, pos, grown = trial, p_, True
        if not grown:
            break
    pg = Page()
    overlay, cluts = {}, []
    kept = 0
    for j, (it, (x, y)) in enumerate(zip(items, pos)):
        w, h = dims2(it, sc[j])
        pg.blit(x, y, downscale(it["rows"], it["clut"], w, h))
        if j in twinned:
            pg.blit(x + DMG_OFF, y, downscale(it["twin"], it["clut"], w, h))
        cluts.append(it["clut"])
        kept += w * h
        overlay[("C", it["p"], it["d"])] = (slot["page"], slot["base"] + j, slot["x"] + x, slot["y"] + y,
                                             it["ox"], it["oy"], it["ow"], it["oh"], w, h)
    texels = bytes(pg.texels[: slot["h"] * 128])
    cluts += [bytes(32)] * (slot["n"] - len(cluts))
    area = sum(it["ow"] * it["oh"] for it in items)
    SPECDMG_INFO[m] = dict(scale=s, kept=kept / area, twinned={slot["base"] + j for j in twinned})
    print("specials slot (Q45 B, damage copies at u+%d): model %d, %d textures (%d with a damage copy), scale %.3f, "
          "clean area kept %.1f %% of Driver 2 (%d of %d texels)" % (DMG_OFF, m, len(items), len(twinned), s,
                                                                   100.0 * kept / area, kept, area))
    return overlay, texels, cluts


def level_row(m: int, clean: bytes, slot: dict) -> bytes:
    """Q45 B: 256 DentCar level bytes for special m's (remapped, fitted) clean model: 1 = the polygon's texture has a
    damage copy DMG_OFF columns to the right (shift at level 2), 3 = no shift."""
    from models import Model, POLY_SIZES
    row = bytearray([3] * 256)
    tw = SPECDMG_INFO.get(m, {}).get("twinned", set())
    mm = Model.parse(-1, clean)
    q = mm.poly_block
    for i in range(min(mm.num_polys, 256)):
        t = mm.data[q] & 31
        if t in (20, 21, 22, 23) and mm.data[q + 1] == slot["page"] and mm.data[q + 2] in tw:
            row[i] = 1
        q += POLY_SIZES.get(t, 4)
    return bytes(row)


def extra_models(chi, world) -> dict:
    """texrepack.EXTRA_MODELS: key -> (Model, areas) for the specials' clean / damage / low models (Driver 2 bytes)."""
    if slot_mode():
        return {}                                       # R34: the slot replaces the area sets
    import polish_cars as pc
    from models import Model
    cm = chi.loadtime.get(28).data
    ents = pc._entries(cm)
    areas = special_areas(world)
    out = {}
    for m in SPECIALS:
        for k, off in enumerate(ents[m]):
            if off != -1:
                out[("special", m, k)] = (Model.parse(-1, pc._model_bytes(cm, off)), areas[m])
    return out


def models_bytes(cm: bytes, m: int):
    """(clean, damage, low) Driver 1 bytes of special m as lump28 builds a car (scaled, fitted, cog-shifted)."""
    import polish_cars as pc
    ents = pc._entries(cm)
    out = []
    for k in range(3):
        off = ents[m][k]
        if off == -1:
            out.append(b"")
            continue
        data = pc.scale_model(pc._model_bytes(cm, off))
        f = pc.fitted(cm, m) if k < 2 else None
        if f:
            data = f[k]
        elif k == 2:
            data = pc.shift_model(data, pc.cog_shift(m))
        out.append(data)
    return out


def col_boxes(scale: float) -> dict:
    """R33: Driver 2's colBox (CAR_COSMETICS +212, half x, y, z) of each special x the car scale -> (half x, half z)."""
    import inputs
    lcf = inputs.read(_CITY.lcf)
    offs = struct.unpack_from("<13i", lcf, 0)
    out = {}
    for m in SPECIALS:
        if 0 < offs[m] < len(lcf):
            bx, _by, bz = struct.unpack_from("<3h", lcf, offs[m] + 212)
            out[m] = (int(round(bx * scale)), int(round(bz * scale)))
    return out


def polish_cars_cog(m: int) -> int:
    import polish_cars as pc
    return pc.cog_shift(m)[1]


def asset(chi, world, remap_fn, cos_rows: dict, wheel: dict, zones: dict, boxes: dict = None, slot: dict = None,
          remap: dict = None, permanent=(), remap_with=None) -> bytes:
    """<lev>.spc.bin. remap_fn(bytes) -> bytes with the polygons remapped to the area pages (source "C").
    cos_rows[m] = 100-B cosmetics row, wheel[m] = int16 wheel size, zones[m] = 300 + 420 B zone rows.
    Layout (little endian): magic, n, rx_n, rz_n, region_units, half_x, half_z, then n x {model, area mask (u32),
    clean size, damage size, low size, wheel (i32), box half x, box half z (R33), 100 B cos, 720 B zones, clean, damage,
    low (each padded to 4)},
    then rx_n * rz_n bytes: special model per region (row-major, rz * rx_n + rx)."""
    cm = chi.loadtime.get(28).data
    areas = special_areas(world)
    rs = region_specials(world)
    rx_n, rz_n = world["rx_n"], world["rz_n"]
    boxes = boxes or {}
    body = b""
    for m in SPECIALS:
        blk = b""
        if slot:                                         # R34: polygons into the slot, texels + CLUTs for the plugin
            ov, tex, cl = slot_layout(chi, m, remap, set(permanent), slot)
            rm = dict(remap)
            rm.update(ov)
            c, d, low = (remap_with(x, rm) if x else b"" for x in models_bytes(cm, m))
            blk = tex + b"".join(cl)
            if SPECDMG:
                LEVEL_ROWS[m] = level_row(m, c, slot)
        else:
            c, d, low = (remap_fn(x) if x else b"" for x in models_bytes(cm, m))
        mask = 0
        for a in areas[m]:
            if a < 32:
                mask |= 1 << a
        pad = lambda b: b + bytes((-len(b)) % 4)
        bx, bz = boxes.get(m, (0, 0))
        # R34: high half of the box z word = the box centre's offset along the car's z axis (Driver 2 centres colBox on
        # the body: initOBox where - R * cog = the drawn body's origin; ours sits at the cog shift, polish_cars.cog_shift)
        # R36 (user: the bus box now sticks out at the FRONT and the back can be driven into): the collision matrix's column 2 points opposite to the model's +z (the drawn body moved by +cog z sits BEHIND the box centre: R33's complaint without an offset was the mirror image), so the box centre moves by -cog z
        dz = -polish_cars_cog(m) if bz else 0
        bzw = (bz & 0xFFFF) | ((dz & 0xFFFF) << 16)
        body += struct.pack("<7iI", m, mask, len(c), len(d), len(low), wheel.get(m, 73), bx, bzw)
        body += (cos_rows[m] + bytes(100))[:100] + (zones[m] + b"\xff" * 720)[:720]
        body += pad(c) + pad(d) + pad(low) + blk
    regs = bytes(rs.get((rx, rz), 0) for rz in range(rz_n) for rx in range(rx_n))
    hdr = struct.pack("<7i", MAGIC2 if slot else MAGIC, len(SPECIALS), rx_n, rz_n, world["region_units"],
                      world["half_x"], world["half_z"])
    if slot:   # slot header: page, first entry, x, y, w, h, entries, block bytes (texels w*h/2 + entries * 32 CLUT bytes)
        hdr += struct.pack("<8i", slot["page"], slot["base"], slot["x"], slot["y"], slot["w"], slot["h"], slot["n"],
                           slot["w"] * slot["h"] // 2 + 32 * slot["n"])
    return hdr + body + regs
