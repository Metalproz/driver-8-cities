"""polish_tex.py - texture downscaling quality for the repack (Polish, C7/C31).

Switch CHI_POLISH_TEX (comma list, default "filter" since b11; empty = texrepack unchanged):
  filter  halve with a box filter: each pair of texels becomes the palette colour
          nearest to their average (instead of dropping every second texel), so thin
          details (window frames, sills, lane lines) blend instead of vanishing and
          shimmer less at a distance
  cost    pick the texture to halve by visual loss: among the candidates of the same
          class (seen only from afar first, as before) the one whose halving changes
          the fewest colours goes first (largest first within a loss band), instead of
          simply the largest

texrepack calls `halve(item)` and `pick(cands, fail_areas)` only when the switch is set.
"""
from __future__ import annotations

import os

OPTS = set(filter(None, os.environ.get("CHI_POLISH_TEX", "filter").split(",")))
FILTER = "filter" in OPTS
COST = "cost" in OPTS
LOSS_BAND = 6.0          # RGB (0..255 per channel) mean error band for the "cost" order


def _palette(clut: bytes):
    """16 entries of (r, g, b, opaque) in 0..255; colour word 0 = transparent on the PSX."""
    out = []
    for k in range(16):
        w = clut[2 * k] | clut[2 * k + 1] << 8 if 2 * k + 1 < len(clut) else 0
        out.append(((w & 31) * 255 // 31, (w >> 5 & 31) * 255 // 31, (w >> 10 & 31) * 255 // 31, w != 0))
    return out


def _merge_pair(a, b, pal, cache):
    """Palette index for the average of texels a, b (box filter, requantised)."""
    if a == b:
        return a
    key = (a, b) if a < b else (b, a)
    r = cache.get(key)
    if r is not None:
        return r
    pa, pb = pal[a], pal[b]
    if not (pa[3] and pb[3]):            # transparency involved: keep the old pick (first texel)
        r = a
    else:
        avg = [(pa[c] + pb[c]) / 2 for c in range(3)]
        r = min((k for k in range(16) if pal[k][3]),
                key=lambda k: sum((pal[k][c] - avg[c]) ** 2 for c in range(3)))
    cache[key] = r
    return r


def halved_rows(rows, w, h, clut, filtered=True):
    """The rows after halving the longer side (same rule as texrepack.Item.halve)."""
    if not filtered:
        if w >= h and w > 1:
            return [row[::2] for row in rows]
        return rows[::2] if h > 1 else rows
    pal, cache = _palette(clut), {}
    if w >= h and w > 1:
        out = []
        for row in rows:
            out.append(bytes(_merge_pair(row[i], row[i + 1] if i + 1 < len(row) else row[i], pal, cache)
                             for i in range(0, len(row), 2)))
        return out
    if h > 1:
        out = []
        for j in range(0, len(rows), 2):
            r0 = rows[j]
            r1 = rows[j + 1] if j + 1 < len(rows) else r0
            out.append(bytes(_merge_pair(r0[i], r1[i], pal, cache) for i in range(len(r0))))
        return out
    return rows


def halve(it):
    """Replacement for texrepack.Item.halve (switch 'filter')."""
    it.rows = halved_rows(it.rows, it.w, it.h, it.clut, True)
    it.h = len(it.rows)
    it.w = len(it.rows[0])
    it.shrink += 1


def loss(it):
    """Mean RGB error per texel if `it` were halved now (upsampled back, opaque texels)."""
    key = (it.shrink, it.w, it.h)
    c = getattr(it, "_polish_loss", None)
    if c and c[0] == key:
        return c[1]
    pal = _palette(it.clut)
    new = halved_rows(it.rows, it.w, it.h, it.clut, FILTER)
    horiz = it.w >= it.h and it.w > 1
    err = n = 0
    for j, row in enumerate(it.rows):
        nrow = new[j] if horiz else new[min(j // 2, len(new) - 1)]
        for i, t in enumerate(row):
            p = pal[t]
            if not p[3]:
                continue
            q = pal[nrow[min(i // 2, len(nrow) - 1)] if horiz else nrow[i]]
            err += abs(p[0] - q[0]) + abs(p[1] - q[1]) + abs(p[2] - q[2])
            n += 1
    v = err / (3 * n) if n else 0.0
    it._polish_loss = (key, v)
    return v


def pick(cands, fail_areas):
    """Replacement for the halving choice in texrepack.repack (switch 'cost')."""
    return max(cands, key=lambda it: (not (it.near & fail_areas) and max(it.w, it.h) >= 32,
                                      -int(loss(it) // LOSS_BAND), it.w * it.h))


# --- street-level detail first (Design review 14.10., CHI_POLISH_TEX_HEIGHT=1) ----------------------
# When the budget forces halving, textures used high up (roofs, upper storeys) go before street-level
# ones (shopfronts, window grids at eye height). Height = mean model-space height (-y) of the polygons
# using the texture over all Chicago models; HIGH_FROM units and above count as high.
import os as _os
HEIGHT = _os.environ.get("CHI_POLISH_TEX_HEIGHT", "1") == "1"      # C7 adopted 16.10. (user, probe "look 2"); 0 = off
HIGH_FROM = int(_os.environ.get("CHI_POLISH_TEX_HIGH", "1536"))   # C7 default 16.10. (was 1200)
# C7 round 2 (user 16.10.: blur only from 2-3 storeys up): D2 storeys are 512 units (mode of the vertex-level spacing
# of Chicago's 448 tall models: 510-519). CHI_POLISH_TEX_HIGH_MODE=min rates a texture by its lowest vertex over all
# its polygons instead of the mean height (a facade grid tiled from the ground up counted as high and was softened
# at street level too); with CHI_POLISH_TEX_HIGH=1536 only textures wholly above the 3rd storey go first.
HIGH_MODE = _os.environ.get("CHI_POLISH_TEX_HIGH_MODE", "mean")
HIGH_SHARE = float(_os.environ.get("CHI_POLISH_TEX_HIGH_SHARE", "0.75"))


def texture_heights(models: dict) -> dict:
    """{(page, tex): mean height above the model origin (-y) of the vertices of polygons using it}."""
    import struct as _st
    from models import POLY_SIZES as _PS
    acc = {}
    for i, m in models.items():
        src = models.get(m.instance_number, m) if m.instance_number >= 0 and m.instance_number != i else m
        vb, nv = src.vertices, src.num_vertices
        if m.poly_block >= len(m.data) or vb <= 0 or vb + 8 * nv > len(src.data):
            continue
        q = m.poly_block
        for _ in range(m.num_polys):
            t = m.data[q] & 31
            if t in (4, 5, 7, 9, 10, 11, 17, 20, 21, 22, 23) and m.data[q + 1] != 0xFF:
                ys = []
                for vi in m.data[q + 4: q + 7]:
                    if vi < nv:
                        ys.append(-_st.unpack_from("<h", src.data, vb + 8 * vi + 2)[0])
                if ys:
                    a = acc.setdefault((m.data[q + 1], m.data[q + 2]), [0.0, 0, 1e9, 0])
                    a[0] += sum(ys) / len(ys); a[1] += 1
                    a[2] = min(a[2], min(ys))
                    a[3] += min(ys) >= HIGH_FROM
            q += _PS.get(t, 4)
    if HIGH_MODE == "min":       # C7 r2: high only if the texture's LOWEST use is above HIGH_FROM
        return {k: lo for k, (s, n, lo, up) in acc.items() if n}
    if HIGH_MODE == "share":     # C7 r2: high if at least HIGH_SHARE of its polygons lie wholly above HIGH_FROM
        return {k: (HIGH_FROM if up >= HIGH_SHARE * n else 0) for k, (s, n, lo, up) in acc.items() if n}
    return {k: s / n for k, (s, n, lo, up) in acc.items() if n}


# C45 corr5 (Polish 17.10.): CHI_POLISH_TEX_PROTECT=1 keeps Chicago's landmark textures (Navy Pier, Art Institute,
# Merchandise Mart, Field Museum, Adler, Chinatown, Soldier Field, Wrigley, Hancock, the EL ...) out of the halving
# while any other candidate is left (larger areas share pages and the budget used to fall on them).
PROTECT = _os.environ.get("CHI_POLISH_TEX_PROTECT", "1") == "1"   # default since corr5 (user 17.10.)
LANDMARK_PREFIX = tuple(__import__("cityprofile").P.landmark_prefix)   # M3 profile (Chicago: Navy Pier ... Tribune)


def protected(it) -> bool:
    if not PROTECT:
        return False
    n = it.name.decode("latin-1").upper() if isinstance(it.name, bytes) else str(it.name).upper()
    return n.startswith(LANDMARK_PREFIX)


def pick_height(cands, fail_areas):
    """Halving choice with street-level detail first: high textures, then far-only ones, then the largest."""
    return max(cands, key=lambda it: (not protected(it), getattr(it, "height", 0) >= HIGH_FROM,
                                      not (it.near & fail_areas) and max(it.w, it.h) >= 32, it.w * it.h))
