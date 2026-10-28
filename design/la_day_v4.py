"""Design R34 (la day 4): RICH daylight colour for LA's building textures, matched to Driver 1's own Miami / SF / NY day textures.
Measured on those day textures (building textures in use, mean luma > 90): luma p10 38-48, p50 124-150, p90 215-226, p98 239-248;
saturation mean 0.18-0.26, p90 0.43-0.64; 3-9 % near-black (< 25). Hue families (k-means of their mid-tones): warm brown-grey
(115,103,86), tan (189,172,152), (155,134,112), steel (103,119,130), brick (157,91,58), sky blue (147,164,189), ochre (195,162,113),
mustard (192,140,55) -> HUES (+ a few richer LA ones).
Recipe per texture: dominant wall entry = area-weighted median luma l_w; every entry keeps its brightness RELATIVE to the wall
(y = Yw * (l / l_w) ** 0.85, so recesses / doorways / frames stay darker and can go truly black, bright trim stays light), the colour
comes from the texture's hue family (hash of the name) at that luma, plus 70 % of the painted detail chroma. Lights OFF: lit windows ->
deep daylight glass (not pale), dark panes -> near-black glass, lamp bulbs -> unlit pale metal."""
import sys, os, zlib, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "chicago"))
import numpy as np
import la_day_repaint as R
HUES = [(115, 103, 86), (189, 172, 152), (155, 134, 112), (103, 119, 130), (157, 91, 58), (147, 164, 189), (195, 162, 113), (192, 140, 55),
        (205, 120, 85), (96, 140, 148), (214, 160, 150), (160, 172, 132)]        # + terracotta, teal, coral pink, sage (sunny-LA richness)
GLASS_LIT = np.array([66, 90, 122.]); GLASS_DARK = np.array([24, 32, 44.])
def hue_for(name):
    h = np.array(HUES[zlib.crc32(name.encode()) % len(HUES)], float); h = h / (h @ np.array([0.299, 0.587, 0.114])); return 0.82 * h + 0.18
def wall_luma(clut, idx):
    pal = np.array([R.rgb(c) for c in clut], float); L = pal[idx] @ np.array([0.299, 0.587, 0.114]); op = np.array([c != 0 for c in clut])[idx]
    return float(np.median(L[op])) if op.any() else 40.0
def yw_for(name): return 150.0 + (zlib.crc32(name[::-1].encode()) % 41 - 20)          # 130..170 per texture
def map_rgb(rgb, L, name, l_w):
    """per-pixel / per-entry day colour for non-light pixels. rgb (...,3), L (...)"""
    l_w = max(l_w, 6.0); yw = yw_for(name); y = np.clip(yw * (np.maximum(L, 0.5) / l_w) ** 0.5, 0, 228)
    y = np.where(L >= 6, np.maximum(y, 0.42 * yw), y)                                          # night noise in the darks must not become mosaic
    y = np.where(L < 6, np.minimum(y, 14), y)                                              # real black stays black
    base = y[..., None] * hue_for(name)
    sat = (rgb.max(-1) - rgb.min(-1)) / np.maximum(rgb.max(-1), 1)
    detail = (rgb - L[..., None]) * np.where(sat > 0.25, 0.7, 0.25)[..., None]               # painted trim / signs keep their hue
    return np.clip(base + detail, 0, 255)
def wall_table(clut, idx, name, k=3):
    """REGION-level tones: the texture's non-light entries are grouped into <= k luma groups (area-weighted 1-D k-means); every entry of a
    group gets ONE colour (so night noise in the darks collapses into one wall tone); only small saturated entries (trim, signs) keep
    their own hue. Returns (16, 3) colours."""
    pal = np.array([R.rgb(c) for c in clut], float); L = pal @ np.array([0.299, 0.587, 0.114]); tot = float(idx.size)
    area = np.array([(idx == e).sum() / tot for e in range(16)]); op = np.array([c != 0 for c in clut])
    rl = R.roles(clut, idx, False)
    use = [e for e in range(16) if op[e] and area[e] > 0 and rl.get(e) not in ("glass_lit",) and L[e] >= 6]
    out = np.zeros((16, 3))
    if not use: return out
    l_w = wall_luma(clut, idx)
    lv = np.log(L[use] + 4.0); wv = area[use]; cs = np.quantile(lv, np.linspace(0.15, 0.85, min(k, len(use))))   # init
    for _ in range(12):
        g = np.argmin(np.abs(lv[:, None] - cs[None]), 1)
        for j in range(len(cs)):
            if (g == j).any(): cs[j] = np.average(lv[g == j], weights=wv[g == j] + 1e-6)
    g = np.argmin(np.abs(lv[:, None] - cs[None]), 1)
    for j in range(len(cs)):
        sel = [use[i] for i in range(len(use)) if g[i] == j]
        if not sel: continue
        lm = np.exp(cs[j]) - 4.0; mean = np.average(pal[sel], axis=0, weights=[area[e] + 1e-6 for e in sel])
        base = map_rgb(mean, np.array(lm), name, l_w)
        for e in sel:
            sat = (pal[e].max() - pal[e].min()) / max(pal[e].max(), 1)
            out[e] = base + ((pal[e] - L[e]) * 0.7 if (sat > 0.35 and area[e] < 0.12) else 0)
    for e in range(16):
        if op[e] and area[e] > 0 and L[e] < 6: out[e] = np.array([14, 12, 12.])                 # real black stays black
    return np.clip(out, 0, 255)
def day_v4_clut(clut, idx, name=""):
    rl = R.roles(clut, idx, False); tot = float(idx.size); wt = wall_table(clut, idx, name); out = []
    for e, w in enumerate(clut):
        if w == 0: out.append(0); continue
        c = np.array(R.rgb(w), float); L = c @ np.array([0.299, 0.587, 0.114]); role = rl.get(e); area = (idx == e).sum() / tot
        if role == "glass_lit": n = GLASS_LIT * (0.8 + 0.4 * L / 255)
        elif role == "glass_dark" and L > 14: n = GLASS_DARK * (0.7 + 0.8 * L / 75)
        elif L > 200 and area < 0.03 and (c.max() - c.min()) / max(c.max(), 1) < 0.5: n = np.array([196, 192, 178.])
        else: n = wt[e] if area > 0 else map_rgb(c, np.array(L), name, wall_luma(clut, idx))
        out.append(R.word(np.clip(n, 0, 255), w & 0x8000))
    return out
# ---- vegetation: deep natural greens with real shadow ----
def veg4_clut(clut, warm=1.0):
    out = []
    for w in clut:
        if w == 0: out.append(0); continue
        c = np.array(R.rgb(w), float); L = c @ np.array([0.299, 0.587, 0.114]); stp = w & 0x8000
        if c[0] > c[2] * 1.25 and c[0] >= c[1] and L > 25:                                     # brown trunk / dry parts
            n = c / max(L, 1) * float(np.interp(L, [0, 40, 120, 255], [40, 80, 140, 215]))
        else:
            y = float(np.interp(L, [0, 8, 20, 40, 80, 255], [34, 52, 76, 104, 138, 200]))      # deep shadows up to sunlit tips
            n = np.array([y * 0.64 * warm, y * 1.0, y * 0.34 / warm])                        # rich green, r:g:b 0.64:1:0.34
        out.append(R.word(np.clip(n, 0, 255), stp))
    return out
def grass4_clut(clut): return veg4_clut(clut, 1.12)
