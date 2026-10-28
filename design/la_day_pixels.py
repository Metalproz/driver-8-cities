"""Design R33 round 2: pixel-level DAY version of a night-painted LA texture (same size, same layout, lights OFF).
day_v3(t) -> (idx array h x w uint8, clut: 16 words); t = polish_laday.textures() tuple. Steps (all scripted, Option A):
 1. lit = warm bright pixels; glow = their warm halo (dilated ring).
 2. wall colour for every other pixel: D1 day ramp (la_day_repaint.ramp) + per-texture stucco tint + 55 % of the original chroma.
 3. lit components: rectangular blobs (fill >= 0.55) = window panes -> flat dark daylight glass with a soft top highlight (like D1's
    own day windows); big blobs (>= 6 % of the texture or >= 24 px wide) = shop interiors -> dim, readable (original luma structure,
    neutral warm, ~35 % of its brightness); everything else (lamps, bulbs, halos) is replaced by the surrounding wall colour
    (masked gaussian fill).
 4. re-quantised to 16 colours (median cut, no dither); transparent pixels keep a word-0 entry."""
import sys, os, zlib
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "chicago"))
import numpy as np
import os as _os
from scipy import ndimage as ndi
import la_day_repaint as R
GLASS = np.array([34, 46, 66.]); GLASS_HI = np.array([78, 96, 124.])   # deep glass (no pale sky-blue)
def _wall_old(rgb, L, name):
    tint = np.array(R.STUCCO[zlib.crc32(name.encode()) % len(R.STUCCO)], float); rp = R.ramp()
    y = np.interp(L, *R.Y_DAY); f = np.clip(y / 8.0, 0, 30); k0 = f.astype(int); k1 = np.minimum(k0 + 1, 30); fr = (f - k0)[..., None]
    base = rp[k0] * (1 - fr) + rp[k1] * fr
    return base + (rgb - L[..., None]) * 0.35 + tint
import la_day_v4 as V4
def _wall(rgb, L, name, l_w): return V4.map_rgb(rgb, L, name, l_w)
def region_wall(rgb, L, op, name, l_w, tot, det=None):
    """R34 region approach: smooth the night luma (median + blur) so noise in the darks disappears, split into REGIONS shadow / wall / light
    relative to the dominant wall luma, colour every region with ONE tone of the texture's hue family (shadow 0.5, wall 1.0, light 1.3 x Yw),
    keep real black (smoothed luma < 6) and the hue of small saturated detail (trim, signs)."""
    DET = float(_os.environ.get("LA_DAY_DETAIL", "0.5")) if det is None else det
    Ls = ndi.gaussian_filter(L, 0.5) if DET > 0 else ndi.gaussian_filter(ndi.median_filter(L, size=3), 0.7); r = Ls / max(l_w, 6.0)
    yw = V4.yw_for(name); h = V4.hue_for(name)
    reg = np.where(r < 0.5, 0, np.where(r < 1.7, 1, 2))
    if DET <= 0: reg = ndi.median_filter(reg, size=3)                                                        # clean region borders (flat version)
    tone = np.array([0.52, 1.0, 1.32])[reg] * yw
    out = tone[..., None] * h
    if DET > 0:                                                                                              # detail transfer (bricks, panels, window frames)
        Lm = ndi.median_filter(L, size=9); d = L - Lm
        iso = np.abs(L - ndi.median_filter(L, size=3)) > 28                                                   # isolated high-amplitude outliers = night speckle
        d = np.where(iso, 0, d); sc = DET * min(yw / max(l_w, 6.0), 3.0)
        out = out + np.clip(d * sc, -34, 34)[..., None] * h
    sat = (rgb.max(-1) - rgb.min(-1)) / np.maximum(rgb.max(-1), 1)
    lab, n = ndi.label((sat > 0.35) & op)
    if n:
        sizes = ndi.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1)); small = np.isin(lab, np.where(sizes < 0.06 * tot)[0] + 1)
        out = out + np.where(small[..., None], (rgb - L[..., None]) * 0.7, 0)
    blk = ndi.binary_opening(Ls < 6, iterations=1)
    bl, bn = ndi.label(blk)                                                    # only SMALL black regions stay black (recesses, doorways);
    if bn:                                                                      # big ones were the night wall -> shadow tone
        bs = ndi.sum(np.ones_like(bl), bl, index=np.arange(1, bn + 1)); blk = np.isin(bl, np.where(bs < 0.035 * tot)[0] + 1)
    out[blk] = np.array([14, 12, 12.])
    return np.clip(out, 0, 255)
def day_v3(t):
    name, pg, k, x, y, w, h, clut, idx = t
    pal = np.array([R.rgb(c) for c in clut], float); op = np.array([c != 0 for c in clut])[idx]
    rgb = pal[idx]; L = rgb @ np.array([0.299, 0.587, 0.114]); warm = (rgb[..., 0] - rgb[..., 2]) > 25
    lit = ((L > 105) & warm & op)
    wl, wn = ndi.label((L > 185) & op & ~lit)                                      # bright non-warm rectangles = lit panes too (DT3-03)
    for i in range(1, wn + 1):
        m = wl == i; a = m.sum(); ys, xs = np.where(m); bw = xs.max() - xs.min() + 1; bh = ys.max() - ys.min() + 1
        if 12 <= a <= 0.04 * w * h and a / float(bw * bh) >= 0.68 and 0.4 < bw / float(bh) < 2.5: lit |= m
    ring = ndi.binary_dilation(lit, iterations=6) & ~lit & (L > 28) & warm
    tot = float(w * h); l_wall = V4.wall_luma(clut, idx)
    # window-grid textures (many small rectangular cells): regular pattern, no detail transfer (R34 v13 fix)
    lab0, n0 = ndi.label(lit); rects = []
    for i in range(1, n0 + 1):
        m = lab0 == i; a = m.sum()
        if a < 4 or a > 0.02 * tot: continue
        ys, xs = np.where(m); bw = xs.max() - xs.min() + 1; bh = ys.max() - ys.min() + 1
        if a / float(bw * bh) >= 0.55 and 0.25 < bw / float(bh) < 4: rects.append((ys.min(), ys.max() + 1, xs.min(), xs.max() + 1))
    grid = len(rects) >= 8
    wall = region_wall(rgb, L, op, name, l_wall, tot, det=0.0 if grid else None)   # region tones (night noise collapsed)
    cells = np.zeros(L.shape, bool)
    if grid:
        for (y0, y1, x0, x1) in rects: cells[y0:y1, x0:x1] = True                  # cells cleaned to rectangles
        cells |= ndi.binary_closing(lit, structure=np.ones((1, 3), bool))           # tiny ragged cells merge into regular strips
    letters = np.zeros_like(lit); mask_fill = np.zeros_like(lit); glass = np.zeros_like(lit); inter = np.zeros_like(lit)
    lab, n = ndi.label(ndi.binary_closing(lit, iterations=1) | lit); tot = float(w * h)
    for i in range(1, n + 1):
        m = lab == i; a = m.sum(); ys, xs = np.where(m); bw = xs.max() - xs.min() + 1; bh = ys.max() - ys.min() + 1
        if a >= 6 and a / float(bw * bh) >= 0.68 and bw <= 44 and bh <= 44: glass |= m                  # clean rectangle = window pane
        elif (a >= 0.06 * tot or bw >= 24) and L[m].std() >= 30:                        # detailed = shop interior (region level)
            reg = ndi.binary_fill_holes(ndi.binary_closing(ndi.binary_dilation(m, iterations=2), iterations=3)) & op; inter |= reg
        elif a >= 0.06 * tot or bw >= 24:                                              # smooth gradient = lamp glow -> wall
            mask_fill |= m
            Lb = ndi.gaussian_filter(np.where(m, L, L[m].mean()), 3); letters |= m & ((L - Lb) > 30)
        elif a >= 6 and a / float(bw * bh) >= 0.55 and 0.25 < bw / float(bh) < 4: glass |= m
        else: mask_fill |= m
    if grid: glass = cells & op; mask_fill &= ~cells; inter &= ~cells
    mask_fill |= ring & ~cells
    out = wall.copy()
    # glass panes: flat dark glass, soft highlight on the top third of each pane
    if glass.any():
        gl, gn = ndi.label(glass)
        for i in range(1, gn + 1):
            m = gl == i; ys, xs = np.where(m); y0, y1 = ys.min(), ys.max(); span = max(y1 - y0, 1)
            for yy in range(y0, y1 + 1):
                t_ = max(0.0, 1.0 - (yy - y0) / (0.45 * span)); row = m[yy]
                out[yy, row] = GLASS * (1 - 0.7 * t_) + GLASS_HI * 0.7 * t_
    # big near-black regions (black-glass shopfronts, deep doorways): ONE dark glass area with a soft top reflection
    dk, dn = ndi.label((L < 22) & op); dshare = ((L < 22) & op).mean()
    for i in range(1, dn + 1):
        if dshare >= 0.45: break                                                   # whole texture is a dark wall, not a glass front
        m = dk == i; ys, xs = np.where(m)
        if m.sum() >= 0.05 * tot and (xs.max() - xs.min() + 1) >= 16 and not (inter & m).any():
            y0, y1 = ys.min(), ys.max(); span = max(y1 - y0, 1)
            for yy in range(y0, y1 + 1):
                f = max(0.0, 1.0 - (yy - y0) / (0.6 * span)); out[yy, m[yy]] = np.array([26, 32, 42.]) * (1 - f) + np.array([62, 78, 98.]) * f
    # shop interiors: dim but readable
    if inter.any():
        dim = L[..., None] + (rgb - L[..., None]) * 0.62                            # desaturate (orange speckle)
        dim = ndi.median_filter(dim, size=(3, 3, 1))                                # calm per-pixel flicker
        dim = dim * 0.70 + np.array([-4, 0, 9.])                                     # 36 % darker, slight cool glass tint
        out[inter] = dim[inter]
    # lamps / halos: surrounding wall colour (masked gaussian fill)
    if mask_fill.any():
        keep = (~mask_fill & ~glass & ~inter & op & ~letters).astype(float)[..., None]
        fill = np.zeros_like(out); done = np.zeros(out.shape[:2], bool)
        for sg in (4, 8, 16, 32):
            num = ndi.gaussian_filter(out * keep, (sg, sg, 0)); den = ndi.gaussian_filter(keep, (sg, sg, 0))
            ok = (den[..., 0] > 0.04) & ~done; fill[ok] = (num / np.maximum(den, 1e-3))[ok]; done |= ok
        if (~done).any():
            kp = keep[..., 0] > 0
            fill[~done] = np.median(out[kp], axis=0) if kp.any() else np.array([150, 140, 125.])
        out[mask_fill] = fill[mask_fill]
    if letters.any(): out[letters & ~inter] = np.array([214, 204, 184.])          # unlit sign lettering stays legible
    out = np.clip(out, 0, 255)
    # quantise to 16 colours, keep a transparent entry when needed
    from PIL import Image
    need_t = (~op).any(); nc = 15 if need_t else 16
    img = Image.fromarray(out.astype(np.uint8)); q = img.quantize(colors=nc, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    qp = (q.getpalette() or [])[:3 * nc]; qp += [0] * (3 * nc - len(qp)); qi = np.array(q, np.uint8)
    words = [R.word(qp[3 * i:3 * i + 3]) | 0x0000 for i in range(nc)]
    words = [wd if wd != 0 else R.word((8, 8, 8)) for wd in words]
    if need_t: words.append(0); qi = np.where(op, qi, 15).astype(np.uint8)
    while len(words) < 16: words.append(R.word((8, 8, 8)))
    return qi, words
