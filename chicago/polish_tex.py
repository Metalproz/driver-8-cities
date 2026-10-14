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
