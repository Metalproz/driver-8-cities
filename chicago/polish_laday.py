"""polish_laday.py - LA by Day textures (Polish, C63 route C, 16.10.).

Switch CHI_POLISH_LA_DAY=1 (used by `python polish_laday.py OUT.lev`; nothing is shipped hand-made):
Driver 1's LA.LEV is painted for night (257 of 551 textures, 58 % of the texel area, mostly dark: lit shop windows,
window grids on black). A day LA keeps LA's models and swaps those textures for Driver 1's own day textures from
NEWYORK / FRISCO / MIAMI.LEV (same disc, read through inputs.py), picked per texture by size and structure
(edge map of the night texture vs the donor's luminance edges, both 16 x 16); landmarks and lit shopfronts go to
Design instead (list `design_list`, at most DESIGN_MAX).

The swap writes the donor's pixels (resampled to the night texture's rectangle) and the donor's 16-colour CLUT
into the LA page in place. Pages spooled per area are raw 17-block records: every area copy is patched. Textures
in the compressed permanent pages are left alone (re-encoding would move the page data) and listed.
"""
from __future__ import annotations

import json
import os
import struct
import sys

import numpy as np

import inputs
from levfile import Lev
from mapinfo import SpoolInfo, SPOOLINFO
from texpages import read_pages, MAX_CLUTS, BLOCK
from textures import TexInfo

ENABLED = os.environ.get("CHI_POLISH_LA_DAY", "") == "1"
DONORS = ("d1_NEWYORK.lev", "d1_FRISCO.lev", "d1_MIAMI.lev")
DARK_L, NIGHT_SHARE = 48, 0.30
GRID_BLOBS = 8                # more warm blobs than this = a lit window grid (swap), fewer = a shopfront (Design)       # a texture is night-painted when > 45 % of its texels are darker than 48
DESIGN_MAX = 40
MAX_REUSE = 3
AD_WORDS = ("HELI", "CHOP", "MIRA", "BILL", "SIGN", "CASTROL", "MENTOS", "BLIMP", "POSTER", "BOARD", "PAUSE", "TIMER", "DM0", "DM1", "DM2", "DM3", "8BIT", "COP", "CONE", "CRATE", "ARM", "INCAR", "FIXEDCA", "PIZZA", "ALLSTAR")
LANDMARKS = ("MANN", "CHIN", "BEVERL", "SANTAM", "SUNSET", "HOLLY", "RODEX", "FOOD")
COVER_SKIP = ("WHEEL", "WHEL", "WHOFF", "FNT", "WING", "FIN", "CJ-", "LAX", "SKY", "SEA", "CAR", "COP", "PED", "HEAD", "ARM", "8BIT", "DIGIT", "FONT", "CAM", "PLAY", "SAVE", "FRAME", "AUTO", "ARW", "ARROW", "LOOK", "LENS", "DM0", "DM1", "DM2", "DM3", "DAM", "FLARE", "LIGHT", "SMOKE", "SHADOW")
ROAD_WORDS = ("ROAD", "LANE", "PAVE", "KERB", "TAR", "PATH")   # swapped only with donor roads
GROUND_WORDS = ("TLIGHT", "GRASS", "SAND", "SEA", "ROCK", "LAX", "AIRP", "DEBRIS", "BARR", "BENCH", "BIN", "PHONE", "POL", "PED", "HEAD", "CAM", "AUTO", "ARW", "ARROW", "FRAME", "SAVE", "PLAY", "LOOK", "LENS", "REST", "EDIT", "DEL", "ADD", "DAM", "SIDE", "SDE", "FNT", "BWN", "FIN", "LOWHEAD", "MDWING", "CJ-")
SKIP_PREFIX = ("SKY", "BIGSKY", "CAR", "LA_CAR", "DIGIT", "FONT", "SMOKE", "FLARE", "LIGHT", "SHADOW")


def _rgb(w):
    return ((w & 31) << 3, (w >> 5 & 31) << 3, (w >> 10 & 31) << 3)


def textures(lev: Lev):
    """[(name, page, k, x, y, w, h, clut words, index array h x w)] of every texture detail."""
    ti, pages = read_pages(lev)
    nm = lev.loadtime.get(5).data
    out = []
    for pg, page in pages.items():
        for k, (tid, noff, x, y, w, h) in enumerate(ti.details[pg]):
            if k >= len(page.cluts) or w == 0 or h == 0:
                continue
            name = nm[noff:nm.index(b"\0", noff)].decode("latin-1") if noff < len(nm) else "?"
            idx = np.array([[page.get(x + i, y + j) for i in range(w)] for j in range(h)], dtype=np.uint8)
            out.append((name, pg, k, x, y, w, h, struct.unpack("<16H", page.cluts[k]), idx))
    return ti, out


def _lum(clut, idx):
    pal = np.array([0.299 * r + 0.587 * g + 0.114 * b for r, g, b in map(_rgb, clut)])
    return pal[idx]


def _sig(img):
    """16 x 16 edge-magnitude signature (structure without brightness: night windows are lit, day ones dark)."""
    h, w = img.shape
    ys = (np.arange(16) * h // 16)[:, None]; xs = (np.arange(16) * w // 16)[None, :]
    s = img[ys, xs].astype(float)
    e = np.abs(np.diff(s, axis=0, append=s[-1:])) + np.abs(np.diff(s, axis=1, append=s[:, -1:]))
    e -= e.mean()
    n = np.linalg.norm(e)
    return e / n if n else e


def night_info(t):
    name, pg, k, x, y, w, h, clut, idx = t
    L = _lum(clut, idx)
    pal = [_rgb(c) for c in clut]
    warm = np.array([r > 150 and g > 100 and b < 150 and r - b > 40 and (0.299 * r + 0.587 * g + 0.114 * b) > 120 for r, g, b in pal])
    opaque = np.array([c != 0 for c in clut])[idx]           # CLUT word 0 = transparent (trees, sprites)
    if opaque.mean() < 0.9:
        return 0.0, 0.0, L, 0
    from scipy.ndimage import label
    comps = label(warm[idx])[1]                               # lit window grid = many small warm blobs
    return (L < DARK_L)[opaque].mean(), warm[idx].mean(), L, comps


def use_counts(lev: Lev):
    from models import inmem_models, area_models
    from texrepack import model_texrefs
    mem, _ = inmem_models(lev); allm = {**area_models(lev), **mem}
    cnt = {}
    for m in allm.values():
        for t in model_texrefs(m, allm):
            cnt[t] = cnt.get(t, 0) + 1
    return cnt


def build_table():
    la = Lev.parse(open(inputs.path("d1_LA.lev"), "rb").read())
    ti, la_tex = textures(la)
    uses = use_counts(la)
    donors = []
    for dn in DONORS:
        dlev = Lev.parse(open(inputs.path(dn), "rb").read())
        dti, tx = textures(dlev)
        duse = use_counts(dlev)                                  # only textures on world models
        special = {p for p, _ in dti.special}                     # car / sprite pages
        for t in tx:
            if t[0].upper().startswith(SKIP_PREFIX) or t[5] * t[6] < 256 or t[1] in special:
                continue
            if not duse.get((t[1], t[2])) or any(b in t[0].upper() for b in AD_WORDS):
                continue
            pal = np.array([_rgb(c) for c in t[7]], dtype=float) / 255
            sat = (pal.max(1) - pal.min(1)) / np.maximum(pal.max(1), 1e-3)
            if sat[t[8]].mean() > 0.45:                           # ads / signs are saturated
                continue
            L = _lum(t[7], t[8])
            road = any(w in t[0].upper() for w in ROAD_WORDS)
            if (L.mean() >= 90 or road and L.mean() >= 60) and (L < DARK_L).mean() < 0.3:   # a day texture
                donors.append((dn, t, _sig(L), road))
    night = []
    la_special = {p for p, _ in ti.special}
    for t in la_tex:
        nmu = t[0].upper()
        if nmu.startswith(SKIP_PREFIX) or t[1] in la_special or not uses.get((t[1], t[2])):
            continue                                              # cars, frontend, peds: not world textures
        if any(b in nmu for b in AD_WORDS + GROUND_WORDS):
            continue
        dark, warm, L, comps = night_info(t)
        if dark > NIGHT_SHARE or (warm > 0.04 and comps > GRID_BLOBS):
            night.append((t, dark, warm, L, comps))
    # Design list: lit shopfronts / landmarks (few large warm areas, not window grids), most used first
    shopq = lambda n: (n[2] > 0.05 and n[4] <= 3 * GRID_BLOBS) or any(w in n[0][0].upper() for w in LANDMARKS)
    shop = sorted((n for n in night if shopq(n)), key=lambda n: -(uses.get((n[0][1], n[0][2]), 0) + 1) * n[0][5] * n[0][6])
    design = shop[:DESIGN_MAX]
    dkeys = {(n[0][1], n[0][2]) for n in design}
    used = {}
    table = []
    for t, dark, warm, L, comps in night:
        key = (t[1], t[2])
        if key in dkeys:
            continue
        s = _sig(255 - L)
        best = None
        is_road = any(w in t[0].upper() for w in ROAD_WORDS)
        for dn, d, ds, droad in donors:
            if used.get((dn, d[0]), 0) >= MAX_REUSE or droad != is_road:
                continue
            ar = (d[5] / d[6]) / (t[5] / t[6])
            if not 0.5 <= ar <= 2.0:
                continue
            score = float((s * ds).sum()) - 0.3 * abs(np.log(ar)) + 0.15 * ((d[5], d[6]) == (t[5], t[6]))
            if best is None or score > best[0]:
                best = (score, dn, d)
        if best:
            used[(best[1], best[2][0])] = used.get((best[1], best[2][0]), 0) + 1
            table.append({"la": t[0], "page": t[1], "k": t[2], "rect": list(t[3:7]), "donor": best[1], "donor_tex": best[2][0],
                          "donor_page": best[2][1], "donor_k": best[2][2], "score": round(best[0], 3)})
    dl = [{"la": n[0][0], "page": n[0][1], "k": n[0][2], "rect": list(n[0][3:7]), "uses": uses.get((n[0][1], n[0][2]), 0),
           "warm": round(float(n[2]), 3)} for n in design]
    return {"night": len(night), "swaps": table, "design": dl, "donor_pool": len(donors)}


DESIGN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "design")


def reviewed_table():
    """Design's review (design/la_day_swap_review.json: keep / exclude = LA signs that stay / replace with a named
    donor) on the matcher's swaps, plus Design's CLUT-only day repaint of the landmarks / shopfronts
    (design/la_day_repaint.py recipe(), computed from the disc textures). Returns the table for apply()."""
    rev = json.load(open(os.path.join(DESIGN_DIR, "la_day_swap_review.json")))
    la = Lev.parse(open(inputs.path("d1_LA.lev"), "rb").read())
    _, la_tex = textures(la)
    la_by = {}
    for t in la_tex:
        la_by.setdefault(t[0], t)
    dtex = {}

    def donor(level, name):
        if level not in dtex:
            dlev = Lev.parse(open(inputs.path(level + ".lev"), "rb").read())
            dti, tx = textures(dlev)
            special = {p for p, _ in dti.special}
            dtex[level] = {}
            for t in tx:
                if t[1] not in special:
                    dtex[level].setdefault(t[0], t)
        return dtex[level].get(name)
    swaps, missing = [], []
    sys.path.insert(0, DESIGN_DIR)
    import la_day_repaint
    no_donor = set(getattr(la_day_repaint, "VEG_RECIPE", {}))      # v9: these use Design's recipes on LA's own pixels
    for e in rev["swaps"]:
        if e["verdict"] == "exclude" or e["la"] in no_donor:
            continue
        name, lvl = (e["replace_with"], e["replace_from"]) if e["verdict"] == "replace" else (e["donor"], e["from"])
        t, d = la_by.get(e["la"]), donor(lvl, name)
        if t is None or d is None:
            missing.append((e["la"], name)); continue
        swaps.append({"la": e["la"], "page": t[1], "k": t[2], "rect": list(t[3:7]), "donor": lvl + ".lev", "donor_tex": name,
                      "donor_page": d[1], "donor_k": d[2]})
    sys.path.insert(0, DESIGN_DIR)
    import la_day_repaint
    rp = la_day_repaint.recipe()
    repaint = [{"la": v[0], "page": k[0], "k": k[1], "clut": list(v[1])} for k, v in rp.items()]
    # v6 coverage pass (user R30): everything else in LA's world that is still night-painted - vegetation, props,
    # far / LOD ground tiles, sand, the airport apron - gets a CLUT-only day version: vegetation through Design's
    # veg_clut (by name or by a green/brown palette), the rest through Design's role-based day_clut. Swapped,
    # repainted, Design-kept signs, cars / HUD / peds and the sky are left alone.
    done = {(x["page"], x["k"]) for x in swaps} | {(x["page"], x["k"]) for x in repaint}
    keep_signs = set(rev.get("sign_keep", []))
    uses = use_counts(la)
    special = {p for p, _ in TexInfo.parse(la.loadtime.get(34).data).special}
    cover = {"veg": [], "other": []}
    # v7: DT3-11B is the far / tile road (32 tile models, dashed centre line); DT2-35A/B are the palm sprite (Design)
    road_ref = None
    for x in swaps:
        if x["la"] == FAR_ROAD_REF:
            road_ref = donor(x["donor"][:-4], x["donor_tex"])
    for t in la_tex:
        key, nmu = (t[1], t[2]), t[0].upper()
        if t[0] in ENGINE_DAY and key not in done:            # v8: by-name engine textures (crash debris, smoke)
            base = ENGINE_DAY[t[0]]
            clut = la_day_repaint.flat_clut(t[7], base) if base else la_day_repaint.day_clut(t[7], t[0], t[8])
            repaint.append({"la": t[0], "page": t[1], "k": t[2], "clut": [int(c) for c in clut], "class": "engine"})
            cover.setdefault("engine", []).append(t[0]); done.add(key)
            continue
        if key in done or (t[0] in keep_signs and t[0] not in no_donor) or t[1] in special or not uses.get(key):
            continue                                          # (v11: a VEG_RECIPE entry beats the sign-keep list)
        if nmu.startswith(SKIP_PREFIX) or any(b in nmu for b in COVER_SKIP):
            continue
        L = _lum(t[7], t[8]); opaque = np.array([c != 0 for c in t[7]])[t[8]]
        if not opaque.any():
            continue
        Lo = L[opaque]
        if not ((Lo < DARK_L).mean() > NIGHT_SHARE or Lo.mean() < 70):
            continue
        pal = np.array([_rgb(c) for c in t[7]], dtype=float)
        greenish = ((pal[:, 1] > pal[:, 0] * 1.05) & (pal[:, 1] > pal[:, 2] * 1.05))[t[8]][opaque].mean() > 0.4
        recipe_v = getattr(la_day_repaint, "VEG_RECIPE", {}).get(t[0])
        veg = recipe_v is not None or any(w in nmu for w in la_day_repaint.VEG_WORDS) or greenish
        if t[0] in FAR_ROAD and recipe_v is None:
            # far tile road: the same asphalt as the near road (v9: LA's own roads via asphalt_clut, no donor)
            clut = la_day_repaint.asphalt_clut(t[7]) if road_ref is None and hasattr(la_day_repaint, "asphalt_clut")                 else match_clut(t, road_ref)
            veg = False
        elif recipe_v is not None:
            clut = recipe_v(t[7])                             # Design's per-texture recipe (palm, grass, sand ...)
        else:
            clut = la_day_repaint.veg_clut(t[7]) if veg else la_day_repaint.day_clut(t[7], t[0], t[8])
        repaint.append({"la": t[0], "page": t[1], "k": t[2], "clut": [int(c) for c in clut], "class": "veg" if veg else "other"})
        cover["veg" if veg else "other"].append(t[0])
    return {"swaps": swaps, "repaint": repaint, "missing": missing, "cover": cover}


# v8: textures the engine draws by name (not on models): crash debris shards lift like props, smoke by day reads
# light grey (flat base colour); lamp flares / glows / the sun stay (the night flag switches them)
ENGINE_DAY = {"DEBRIS": None}   # SMOKE stays: it is drawn additive, a light smoke CLUT became a white blob (v8 capture)
FAR_ROAD = ("DT3-11B",)       # LA's far / tile road texture (used by 32 tile models)
FAR_ROAD_REF = "ROAD2A"       # the near road whose day donor it should match


def match_clut(t, ref):
    """CLUT of texture t remapped so its luminance quantiles and tint follow the reference texture ref (both
    textures() tuples); bright entries (lane markings, > 150) stay bright."""
    L = _lum(t[7], t[8]).ravel(); R = _lum(ref[7], ref[8]).ravel()
    rp = np.array([_rgb(c) for c in ref[7]], dtype=float)[ref[8]].reshape(-1, 3)
    tint = rp.mean(0) / max(1.0, rp.mean())
    out = []
    for c in t[7]:
        if c == 0:
            out.append(0); continue
        r, g, b = _rgb(c); l = 0.299 * r + 0.587 * g + 0.114 * b
        if l > 150:
            out.append(c); continue
        q = (L <= l).mean()
        v = np.quantile(R, min(0.98, q)) * tint
        v = np.clip(v, 0, 255)
        out.append(int(v[0]) >> 3 | (int(v[1]) >> 3) << 5 | (int(v[2]) >> 3) << 10 | (c & 0x8000))
    return out


def la_day_skybin(out_path, test_slot=None):
    """Driver 1's SKY.BIN + Chicago's skies (13 day, 14 night, 15 rain) + Design's LA day sky as index 16 (free;
    design/la_day_sky.py). test_slot=13 also puts the LA day sky into Chicago's day slot (test copies only)."""
    sys.path.insert(0, DESIGN_DIR)
    import la_day_sky, polish_sky
    sk = polish_sky.read_skybin(open(inputs.path("d1_SKY.BIN"), "rb").read())
    for name in ("day", "night", "rain"):
        sk.append(polish_sky.sky_bmps(name))
    la = la_day_sky.la_day_bmps()
    sk.append(la)
    if test_slot is not None:
        sk[test_slot] = la
    open(out_path, "wb").write(polish_sky.write_skybin(sk))
    return len(sk) - 1


def _design_repaint():
    sys.path.insert(0, DESIGN_DIR)
    import la_day_repaint
    return la_day_repaint


def apply(table, out_path):
    """LA.LEV with the swaps written in place (raw spooled pages, every area copy)."""
    data = bytearray(open(inputs.path("d1_LA.lev"), "rb").read())
    la = Lev.parse(bytes(data))
    ti = TexInfo.parse(la.loadtime.get(34).data)
    permanent = {p for p, _ in ti.permanent} | {p for p, _ in ti.special}
    sp = SpoolInfo.parse(la.inmem.get(SPOOLINFO).data)
    spooled = bytearray(la.spooled)
    donors = {}
    done = skipped = 0
    from texpages import decode_compressed, encode_compressed, pad
    order = list(ti.permanent) + list(ti.special)
    comp, pos = {}, 0
    for page, size in order:                                  # compressed resident pages, in file order
        comp[page] = [decode_compressed(la.tpages[pos: pos + size])[0], la.tpages[pos: pos + size], False]
        pos += (size + BLOCK - 1) // BLOCK * BLOCK
    for s in table["swaps"]:
        if s["donor"] not in donors:
            donors[s["donor"]] = {(t[1], t[2]): t for t in textures(Lev.parse(open(inputs.path(s["donor"]), "rb").read()))[1]}
        d = donors[s["donor"]][(s["donor_page"], s["donor_k"])]
        x, y, w, h = s["rect"]
        src = d[8]
        ys = (np.arange(h) * src.shape[0] // h)[:, None]; xs = (np.arange(w) * src.shape[1] // w)[None, :]
        idx = src[ys, xs]
        grade = getattr(_design_repaint(), "la_grade_clut", None)
        clut = struct.pack("<16H", *[int(c) for c in (grade(list(d[7])) if grade else d[7])])   # v9: one LA wall look
        hit = 0
        if s["page"] in comp:                                 # resident page: patch the decoded page, re-encode below
            pg = comp[s["page"]][0]
            pg.cluts[s["k"]] = clut
            for j in range(h):
                for i in range(w):
                    pg.put(x + i, y + j, int(idx[j, i]))
            comp[s["page"]][2] = True
            done += 1
            continue
        for a in sorted({v[7] for v in sp.spools.values()} - {255}):
            gfx = sp.areas[a][0]
            for kk, page in enumerate(p for p in sp.area_tpages[a] if p != 0xFF):
                if page != s["page"]:
                    continue
                base = (gfx + 17 * kk) * BLOCK
                spooled[base + 4 + 32 * s["k"]: base + 36 + 32 * s["k"]] = clut
                tex0 = base + 4 + 32 * MAX_CLUTS + 28
                for j in range(h):
                    for i in range(0, w, 1):
                        o = tex0 + (y + j) * 128 + (x + i) // 2
                        v = int(idx[j, i])
                        spooled[o] = (spooled[o] & 0x0F) | (v << 4) if (x + i) & 1 else (spooled[o] & 0xF0) | v
                hit += 1
        done += hit > 0
    for r in table.get("repaint", []):                       # Design: CLUT-only day versions (same pixels)
        clut = struct.pack("<16H", *r["clut"])
        if r["page"] in comp:
            comp[r["page"]][0].cluts[r["k"]] = clut; comp[r["page"]][2] = True
        else:
            for a in sorted({v[7] for v in sp.spools.values()} - {255}):
                gfx = sp.areas[a][0]
                for kk, page in enumerate(p for p in sp.area_tpages[a] if p != 0xFF):
                    if page == r["page"]:
                        base = (gfx + 17 * kk) * BLOCK
                        spooled[base + 4 + 32 * r["k"]: base + 36 + 32 * r["k"]] = clut
        done += 1
    la.spooled = bytes(spooled)
    tp, sizes = bytearray(), {}
    for page, size in order:
        pg, blob, changed = comp[page]
        if changed:
            blob = encode_compressed(pg)
        sizes[page] = len(blob)
        tp += pad(bytes(blob))
    la.tpages = bytes(tp)
    lump = la.loadtime.get(34)
    info = bytearray(lump.data)
    p = ti.end - 8 * 16 - 4 - 8 * 16                          # perm XYPAIR list (after its count)
    for base, lst in ((p, ti.permanent), (p + 8 * 16 + 4, ti.special)):
        for kk, (page, size) in enumerate(lst):
            struct.pack_into("<ii", info, base + 8 * kk, page, sizes[page])
    lump.data = bytes(info)
    open(out_path, "wb").write(la.build(keep_layout=False))
    return done, skipped



# --- v12 (Design QUEUE 15-17, user's choice: no donor swaps) ----------------------------------------------------
def v12_entries():
    """Design's hybrid on LA's own pixels: every night-painted texture (la_day_repaint.night_targets) with more than
    1 % lit pixels -> la_day_pixels.day_v3 (new 4-bit indices + CLUT), the others -> day_v2_clut (CLUT only);
    VEG_RECIPE names (roads, grass, palms, cone, post) keep their recipes; ENGINE_DAY (crash debris) as before.
    Returns [(page, k, x, y, w, h, idx or None, clut bytes, name, kind)]."""
    sys.path.insert(0, DESIGN_DIR)
    import la_day_repaint as R, la_day_pixels as P
    la0 = Lev.parse(open(inputs.path("d1_LA.lev"), "rb").read())
    _, tx0 = textures(la0)
    uses = use_counts(la0)
    ents, seen = [], set()
    for t in R.night_targets(tx0, uses):
        if t[0] in R.VEG_RECIPE:
            continue
        # v13 (Design R34, QUEUE 18-20): the region recipe day_v3 (detail transfer LA_DAY_DETAIL, default 0.5 in
        # la_day_pixels) on EVERY night target
        qi, wd = P.day_v3(t); kind = "pixels"
        ents.append((t[1], t[2], t[3], t[4], t[5], t[6], qi, struct.pack("<16H", *[int(c) for c in wd]), t[0], kind))
        seen.add((t[1], t[2]))
    special = {p for p, _ in TexInfo.parse(la0.loadtime.get(34).data).special}
    for t in tx0:
        key = (t[1], t[2])
        if key in seen:
            continue
        f = R.VEG_RECIPE.get(t[0])
        if f is not None and uses.get(key) and t[1] not in special:
            ents.append((*key, *t[3:7], None, struct.pack("<16H", *[int(c) for c in f(list(t[7]))]), t[0], "recipe"))
            seen.add(key)
        elif t[0] in ENGINE_DAY:
            ents.append((*key, *t[3:7], None, struct.pack("<16H", *[int(c) for c in R.day_clut(t[7], t[0], t[8])]), t[0], "engine"))
            seen.add(key)
    return ents


def write_entries(ents, out_path):
    """LA.LEV with the entries written (CLUT, and the 4-bit indices where given) into every page copy."""
    from texpages import decode_compressed, encode_compressed, pad
    la = Lev.parse(open(inputs.path("d1_LA.lev"), "rb").read())
    ti = TexInfo.parse(la.loadtime.get(34).data)
    sp = SpoolInfo.parse(la.inmem.get(SPOOLINFO).data)
    spooled = bytearray(la.spooled)
    order = list(ti.permanent) + list(ti.special)
    comp, pos = {}, 0
    for page, size in order:
        comp[page] = [decode_compressed(la.tpages[pos: pos + size])[0], la.tpages[pos: pos + size], False]
        pos += (size + BLOCK - 1) // BLOCK * BLOCK
    for page, k, x, y, w, h, idx, clut, name, kind in ents:
        if page in comp:
            pg = comp[page][0]
            pg.cluts[k] = clut
            if idx is not None:
                for j in range(h):
                    for i in range(w):
                        pg.put(x + i, y + j, int(idx[j, i]))
            comp[page][2] = True
            continue
        for a in sorted({v[7] for v in sp.spools.values()} - {255}):
            gfx = sp.areas[a][0]
            for kk, pgn in enumerate(p for p in sp.area_tpages[a] if p != 0xFF):
                if pgn != page:
                    continue
                base = (gfx + 17 * kk) * BLOCK
                spooled[base + 4 + 32 * k: base + 36 + 32 * k] = clut
                if idx is None:
                    continue
                tex0 = base + 4 + 32 * MAX_CLUTS + 28
                for j in range(h):
                    for i in range(w):
                        o = tex0 + (y + j) * 128 + (x + i) // 2
                        v = int(idx[j, i])
                        spooled[o] = (spooled[o] & 0x0F) | (v << 4) if (x + i) & 1 else (spooled[o] & 0xF0) | v
    la.spooled = bytes(spooled)
    tp, sizes = bytearray(), {}
    for page, size in order:
        pg, blob, changed = comp[page]
        if changed:
            blob = encode_compressed(pg)
        sizes[page] = len(blob)
        tp += pad(bytes(blob))
    la.tpages = bytes(tp)
    lump = la.loadtime.get(34)
    info = bytearray(lump.data)
    p = ti.end - 8 * 16 - 4 - 8 * 16
    for base, lst in ((p, ti.permanent), (p + 8 * 16 + 4, ti.special)):
        for kk, (page, size) in enumerate(lst):
            struct.pack_into("<ii", info, base + 8 * kk, page, sizes[page])
    lump.data = bytes(info)
    open(out_path, "wb").write(la.build(keep_layout=False))


# --- v15 (user R35: buildings of v11 / probe "la day 3" + vegetation / props of v14) -----------------------------
V15_PROPS = ("LAAIRP~1", "BARREL4", "SIGNNOE", "P-METER", "BIN", "BENCH02", "PHONE", "PHONE2", "SMSIGN3", "BILLBO~1",
             "BILLBO~2", "BARRIE~1", "DT3-11B", "CONE2")


def v15_entries():
    """Buildings: the reviewed donor swaps (graded) + Design's v11 day CLUTs, frozen in design/la_day_v11_cluts.json
    (the repaint recipe code has changed since the user approved v11); vegetation, roads, props, debris: v14's
    entries (VEG_RECIPE veg4/grass4, cone, post, day_v3 props, debris). Returns (swap table, extra entries)."""
    sys.path.insert(0, DESIGN_DIR)
    import la_day_repaint as R
    tab = reviewed_table()
    props = set(R.VEG_RECIPE) | set(ENGINE_DAY) | set(V15_PROPS)
    frozen = json.load(open(os.path.join(DESIGN_DIR, "la_day_v11_cluts.json")))["cluts"]
    rep = []
    for r in tab["repaint"]:
        if r["la"] in props:
            continue
        f = frozen.get("%d:%d" % (r["page"], r["k"]))
        if f:
            r = dict(r, clut=f["clut"])
        rep.append(r)
    keys = {(r["page"], r["k"]) for r in rep}
    for k, f in frozen.items():
        pg, kk = (int(v) for v in k.split(":"))
        if (pg, kk) not in keys:
            rep.append({"la": f["name"], "page": pg, "k": kk, "clut": f["clut"]})
    tab["repaint"] = rep
    extra = [e for e in v12_entries() if e[8] in props]
    return tab, extra

if __name__ == "__main__" and os.environ.get("CHI_POLISH_LA_DAY_MODE", "v15") == "v15":
    tab, extra = v15_entries()
    print("v15: %d swaps, %d building repaints, %d veg/prop entries" % (len(tab["swaps"]), len(tab["repaint"]), len(extra)))
    if len(sys.argv) > 1:
        tmp = sys.argv[1] + ".tmp"
        apply(tab, tmp)
        _src = inputs.path
        inputs.path = lambda n: tmp if n == "d1_LA.lev" else _src(n)    # write the v14 entries on top of the v11 build
        try:
            write_entries(extra, sys.argv[1])
        finally:
            inputs.path = _src
            os.remove(tmp)
        print("wrote", sys.argv[1])
    sys.exit(0)

if __name__ == "__main__" and os.environ.get("CHI_POLISH_LA_DAY_MODE", "v15") == "v12":
    ents = v12_entries()
    import collections as _c
    print("v12 entries: %d %s" % (len(ents), dict(_c.Counter(e[9] for e in ents))))
    if len(sys.argv) > 1:
        write_entries(ents, sys.argv[1]); print("wrote", sys.argv[1])
    sys.exit(0)

if __name__ == "__main__" and os.environ.get("CHI_POLISH_LA_DAY_REVIEW", "1") == "1" and os.path.exists(
        os.path.join(DESIGN_DIR, "la_day_swap_review.json")):
    tab = reviewed_table()
    print("reviewed: %d swaps, %d repaints, missing %s" % (len(tab["swaps"]), len(tab["repaint"]), tab["missing"]))
    if len(sys.argv) > 1:
        print("applied %d (%d skipped) -> %s" % (*apply(tab, sys.argv[1]), sys.argv[1]))
    sys.exit(0)

if __name__ == "__main__":
    tab = build_table()
    json.dump(tab, open(os.path.join("work", "polish_la_day_table.json"), "w"), indent=0)
    print("night textures %d, swaps %d, design %d, donor pool %d" % (tab["night"], len(tab["swaps"]), len(tab["design"]), tab["donor_pool"]))
    if len(sys.argv) > 1:
        print("applied %d swaps (%d in permanent pages skipped) -> %s" % (*apply(tab, sys.argv[1]), sys.argv[1]))
