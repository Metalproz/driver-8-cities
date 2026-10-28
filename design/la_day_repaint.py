"""Design (C63 step 2): DAY versions of the 24 LA landmark / lit-shopfront textures, as a recipe on the disc texture.
Nothing is stored: run `python la_day_repaint.py recipe` to get {(page,k): new CLUT words}, or
`python la_day_repaint.py sheet` to write out/laday/repaint_sheet.png (originals above, day versions below).
The repaint only remaps the 16 CLUT colours of each texture (same pixels, same 4-bit indices, same size), so
the layout stays exactly the one of the original LA place.  Per-entry classes (original colour -> day colour):
  lit      warm bright entries (lit windows, bulbs)         -> daylight glass: cool grey-blue, mid luma (unlit window)
  neon     saturated bright entries (signs)                 -> unlit tube: 55 % desaturated, luma x0.75
  dark     luma < 60 (black walls, shadows)                 -> daylight surface: luma lifted by LIFT(l), warm-neutral
  mid/high everything else                                  -> gain x1.25, capped
  transparent (word 0) stays 0.
Texture-specific overrides (OVERRIDE) tune landmarks (Mann's, Chinese theatre ...).
No hand-painted pixels: HAND_PAINTED stays empty."""
import sys, os, json, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "chicago"))
import numpy as np
HAND_PAINTED = []
OVERRIDE = {"ROD24": {"no_glass": True}, "DT53": {"glass_lit": (138, 158, 180)}}   # la name -> dict(glass_lit=, glass_dark=, no_glass=, neon_keep=)
def lum(c): return 0.299*c[0]+0.587*c[1]+0.114*c[2]
def rgb(w): return ((w&31)<<3, (w>>5&31)<<3, (w>>10&31)<<3)
def word(c, stp=0): return (min(31,int(c[0])>>3))|(min(31,int(c[1])>>3)<<5)|(min(31,int(c[2])>>3)<<10)|stp
def lift(l):          # night black -> daylight wall: 20 -> 75, 60 -> 125, 120 -> 165, 255 -> 255
    return np.interp(l,[0,20,60,120,255],[30,75,125,165,255])
def roles(clut, idx, no_glass=False):
    """Per CLUT entry role from where its pixels sit: wall (big areas), glass_lit (warm bright), glass_dark (dark, small
    scattered blobs = window panes / recesses / interiors), plain (the rest)."""
    from scipy.ndimage import label
    out = {}; tot = float(idx.size); opaque = np.array([c != 0 for c in clut])[idx]
    dark_share = float(np.array([lum(rgb(c)) < 75 and c != 0 for c in clut])[idx].mean())      # R33: mostly-dark texture = dark WALL, not glass
    for e, w in enumerate(clut):
        if w == 0: out[e] = "transparent"; continue
        c = np.array(rgb(w), float); l = lum(c); m = (idx == e)
        area = m.sum() / tot
        if area == 0: out[e] = "plain"; continue
        sat = (c.max() - c.min()) / max(c.max(), 1)
        n = label(m)[1]; mean = m.sum() / max(n, 1)
        if l > 110 and c[0] - c[2] > 40 and (sat < 0.8 or (sat < 0.97 and c[1] > 0.6 * c[0])) and area < 0.18: out[e] = "glass_lit"   # incl. saturated yellow bulbs
        elif l < 75 and area < 0.22 and n >= 3 and mean < 700 and not no_glass and dark_share < 0.5: out[e] = "glass_dark"
        elif area >= 0.18 or (l < 75 and dark_share >= 0.5): out[e] = "wall"
        else: out[e] = "plain"
    return out
def day_clut(clut, name, idx=None):
    ov = OVERRIDE.get(name, {})
    glass_lit = np.array(ov.get("glass_lit", (176, 196, 214))); glass_dark = np.array(ov.get("glass_dark", (66, 82, 100)))
    rl = roles(clut, idx, ov.get("no_glass", False)) if idx is not None else {}
    out = []
    for e, w in enumerate(clut):
        if w == 0: out.append(0); continue
        c = np.array(rgb(w), float); l = lum(c); stp = w & 0x8000
        sat = (c.max() - c.min()) / max(c.max(), 1); role = rl.get(e)
        if role == "glass_lit" or (role is None and l > 110 and c[0] - c[2] > 40 and sat < 0.8):
            n = glass_lit * (0.85 + 0.3 * l / 255)              # window reflecting the bright sky
        elif role == "glass_dark":
            n = glass_dark * (0.8 + 0.5 * l / 75) + (c - l) * 0.25   # window reflecting the shaded street / interior
        else:
            y = float(np.interp(l, [0, 20, 60, 120, 200, 255], [58, 88, 128, 168, 218, 250]))
            k = 0.5 if sat > 0.6 else 0.75
            if role == "wall": y = float(np.interp(l, [0, 20, 60, 120, 200, 255], [92, 112, 140, 172, 215, 248])); k = 0.85
            n = y + (c - l) * k + np.array([4, 2, -6])
            if sat > 0.6 and l > 90: n = n * 0.85                # unlit neon tube: muted, not glowing
        out.append(word(np.clip(n, 0, 255), stp))
    return out
# v4 follow-up (17.10.): lit signs / facades that stayed night-painted. Recipe-repainted instead of swapped or kept.
EXTRA = ["DT53", "SS2-11C", "SS38", "SM27C", "SS10", "SS21", "SS09B", "SS05B", "SS13", "SS07B", "SS18", "SS06", "DT2-08B", "SS11B",
         "DT3-04", "SS17B", "UNTITLED", "SM2-08", "ROD24", "ROD15A", "SM16B",
         "CJ-1"]   # v9 leftovers (the other bright shopfronts in v9 are donor DAY textures with warm interiors: keep)
def load_design():
    d = json.load(open(os.path.join(HERE,"..","findings","c63_la_day_design_list.json")))
    import inputs, polish_laday as L
    from levfile import Lev
    la = Lev.parse(open(inputs.path("d1_LA.lev"),"rb").read()); _,tx = L.textures(la)
    have = {x["la"] for x in d}
    for t in tx:
        if t[0] in EXTRA and t[0] not in have:
            d.append({"la": t[0], "page": t[1], "k": t[2], "rect": list(t[3:7]), "uses": 0, "warm": 0}); have.add(t[0])
    return d
def recipe():
    import inputs, polish_laday as L
    from levfile import Lev
    la = Lev.parse(open(inputs.path("d1_LA.lev"),"rb").read()); _,tx = L.textures(la)
    by = {(t[1],t[2]): t for t in tx}
    return {(d["page"],d["k"]): (d["la"], day_clut(by[(d["page"],d["k"])][7], d["la"], by[(d["page"],d["k"])][8]), by[(d["page"],d["k"])]) for d in load_design()}
def sheet():
    from PIL import Image
    r = recipe(); items = list(r.values()); cols = 6
    S = 100; sh = Image.new("RGB",(cols*(S+6), ((len(items)+cols-1)//cols)*2*(S+14)),(40,40,40))
    from PIL import ImageDraw
    d = ImageDraw.Draw(sh)
    for i,(name,newc,t) in enumerate(items):
        idx = t[8]; ox=(i%cols)*(S+6); oy=(i//cols)*2*(S+14)
        for j,cl in enumerate((t[7], newc)):
            pal = np.array([rgb(c)+(0 if c==0 else 255,) for c in cl], np.uint8)
            im = Image.fromarray(pal[idx],"RGBA"); k=min(S/im.width,S/im.height)
            im = im.resize((max(1,int(im.width*k)),max(1,int(im.height*k))),Image.NEAREST)
            bg = Image.new("RGB",(S,S),(255,0,255)); bg.paste(im,(0,0),im)
            sh.paste(bg,(ox,oy+j*(S+2)))
        d.text((ox,oy+2*S+4),name,fill=(255,255,0))
    sh.save(os.path.join(HERE,"out","laday","repaint_sheet.png")); print("sheet", len(items))
if __name__=="__main__":
    (sheet if len(sys.argv)>1 and sys.argv[1]=="sheet" else recipe)()

# --- vegetation (R30): trees/palms/bushes/grass are painted near-black for LA night ------------------------------
VEG_WORDS = ("PALM", "TREE", "BUSH", "GRASS", "HEDGE", "LEAF", "SHRUB", "PLANT", "FERN", "FLOWER")
def veg_clut(clut, warm=1.0):
    """CLUT remap for night vegetation (v2, sunny LA): near-black leaves -> warm yellow-green by luma (sunlit),
    trunks / brown entries keep hue and are lifted; transparent stays 0. warm 1.0 = palms/trees, 1.15 = dry grass."""
    out = []
    for w in clut:
        if w == 0: out.append(0); continue
        c = np.array(rgb(w), float); l = lum(c); stp = w & 0x8000
        brown = c[0] > c[2] * 1.25 and c[0] >= c[1] and l > 25
        if brown: n = c / max(l, 1) * float(np.interp(l, [0, 40, 120, 255], [70, 95, 150, 225]))
        else:
            y = float(np.interp(l, [0, 10, 20, 40, 80, 255], [86, 94, 102, 112, 126, 165]))   # R33: low contrast, sits with ground and walls
            n = np.array([y * 0.92 * warm, y * 1.0, y * 0.70 / warm])        # r:g:b ~ 0.86:1:0.60 = soft sunny LA green (v3: less saturated)
        out.append(word(np.clip(n, 0, 255), stp))
    return out
def flat_clut(clut, base, spread=0.35):
    """CLUT remap for plain ground-ish textures (sand, rock, concrete): every entry -> base colour modulated by the original luma."""
    out = []
    for w in clut:
        if w == 0: out.append(0); continue
        c = np.array(rgb(w), float); l = lum(c); stp = w & 0x8000
        m = (1 - spread) + spread * 2 * min(l, 80) / 80
        out.append(word(np.clip(np.array(base, float) * m, 0, 255), stp))
    return out
def asphalt_clut(clut):
    """R31: ONE asphalt for road, intersection and path textures (LA's own pixels, no donors): neutral mid-grey from the night
    luma, lane paint keeps its hue at 60 % chroma, tiny warm bias."""
    out = []
    for w in clut:
        if w == 0: out.append(0); continue
        c = np.array(rgb(w), float); l = lum(c); stp = w & 0x8000
        y = float(np.interp(l, [0, 20, 60, 120, 255], [92, 106, 130, 168, 242]))
        out.append(word(np.clip(y + (c - l) * 0.6 + np.array([3, 1, -2]), 0, 255), stp))
    return out
def la_grade_clut(clut):
    """R31 unified LA day look for the donor textures (NY brick, Miami pastel, SF ...): one palette. Luma kept (range squeezed to
    40..236), saturation x0.78, warm LA daylight bias (+7,+2,-9)."""
    out = []
    for w in clut:
        if w == 0: out.append(0); continue
        c = np.array(rgb(w), float); l = lum(c); stp = w & 0x8000
        y = 40 + (l / 255.0) * 196
        out.append(word(np.clip(y + (c - l) * 0.78 + np.array([7, 2, -9]), 0, 255), stp))
    return out
def trunk_clut(clut):
    """palm trunk: weathered grey-brown, shaded by the original luma (the night CLUT's orange/blue entries made yellow-green stripes)"""
    out = []
    for w in clut:
        if w == 0: out.append(0); continue
        c = np.array(rgb(w), float); l = lum(c); stp = w & 0x8000
        y = float(np.interp(l, [0, 40, 120, 255], [0.45, 0.62, 0.85, 1.15]))
        out.append(word(np.clip(np.array([146, 122, 96.]) * y, 0, 255), stp))
    return out
def cone_clut(clut):
    """traffic cone: daylight orange body + soft off-white bands instead of black/white; entries by original luma"""
    out = []
    for w in clut:
        if w == 0: out.append(0); continue
        c = np.array(rgb(w), float); l = lum(c); stp = w & 0x8000
        if l > 90: n = np.array([232, 226, 214.]) * (0.8 + 0.2 * l / 255)          # reflective band
        else:      n = np.array([226, 112, 44.]) * float(np.interp(l, [0, 90], [0.62, 1.0]))   # orange body, shaded
        out.append(word(np.clip(n, 0, 255), stp))
    return out
# per-texture recipe for the v6 cover list (Design 17.10.): name -> function(clut) -> new CLUT
PANE_FIX = ["SS2-59", "ROD04", "DT50", "ROD01", "DT54", "ROD18", "ROD36"]    # v10: donor facades whose small bright-yellow window panes still glow
def pane_clut(clut, idx):
    """only the small bright-yellow entries (lit panes, < 6 % area each) -> daylight glass; walls untouched (use for donor facades)"""
    tot = float(idx.size); out = []
    for e, w in enumerate(clut):
        if w == 0: out.append(0); continue
        c = np.array(rgb(w), float); l = lum(c)
        if c[0] > 185 and c[1] > 150 and c[2] < 130 and c[1] > 0.7 * c[0] and (idx == e).sum() / tot < 0.06:
            out.append(word(np.array([176, 196, 214.]) * (0.85 + 0.3 * l / 255), w & 0x8000))
        else: out.append(w)
    return out
def metal_clut(clut):
    """lamp / sign post: neutral weathered grey metal (the night CLUT is olive)"""
    out = []
    for w in clut:
        if w == 0: out.append(0); continue
        c = np.array(rgb(w), float); l = lum(c); stp = w & 0x8000
        y = float(np.interp(l, [0, 30, 90, 255], [78, 98, 132, 205]))
        out.append(word(np.clip(np.array([y + 3, y + 1, y - 3]), 0, 255), stp))
    return out
VEG_RECIPE = {"RODPOST": metal_clut, "DT2-35A": lambda c: __import__("la_day_v4").veg4_clut(c), "TREE": lambda c: __import__("la_day_v4").veg4_clut(c), "TWALL2": lambda c: __import__("la_day_v4").veg4_clut(c), "DT2-35B": trunk_clut, "CONE2": cone_clut,
              "ROAD2A": asphalt_clut, "ROAD01A": asphalt_clut, "NEWROAD3": asphalt_clut, "NEWROAD4": asphalt_clut, "PATHC": asphalt_clut, "BCKLANE": asphalt_clut, "BCKLANE2": asphalt_clut,
              "GRASS02": lambda c: __import__("la_day_v4").grass4_clut(c),
              "SAND": lambda c: flat_clut(c, (205, 178, 130)), "ROCKS01": lambda c: flat_clut(c, (150, 130, 105)),
              "BARRIER": lambda c: flat_clut(c, (170, 168, 160), 0.3)}
def veg_targets(tex):
    """names of LA textures (list of textures() tuples) the vegetation recipe applies to"""
    return [t for t in tex if any(v in t[0].upper() for v in VEG_WORDS)]

# ======================= R33 (la day 3): ONE unified daylight look for every night-painted LA texture ======================
# No donors: the night art's own layout (doors, frames, windows, signs) stays; each CLUT entry is re-coloured by role:
#   wall / plain  -> the colour of Driver 1's OWN day buildings at that brightness (RAMP = mean colour per luma bin of the day
#                    textures of Miami + San Francisco + New York, read from the disc by make_ramp(); la_day_ramp.json is a cache)
#                    + 80 % of the original chroma (painted details keep their hue),
#   glass_lit     -> daylight glass reflecting the sky (lights OFF), glass_dark -> shaded glass / interior,
#   lamp          -> tiny very bright areas: unlit lamp body (pale, no glow).
def make_ramp():
    import inputs, polish_laday as L
    from levfile import Lev
    S = np.zeros((32, 3)); N = np.zeros(32)
    for dn in ("d1_MIAMI.lev", "d1_FRISCO.lev", "d1_NEWYORK.lev"):
        lev = Lev.parse(open(inputs.path(dn), "rb").read()); ti, tx = L.textures(lev); uses = L.use_counts(lev); sp = {p for p, _ in ti.special}
        for t in tx:
            n = t[0].upper()
            if n.startswith(L.SKIP_PREFIX) or t[1] in sp or not uses.get((t[1], t[2])) or any(w in n for w in L.AD_WORDS + L.GROUND_WORDS + L.ROAD_WORDS): continue
            pal = np.array([L._rgb(c) for c in t[7]], float); op = np.array([c != 0 for c in t[7]]); px = pal[t[8]]; m = op[t[8]]
            lm = px @ np.array([0.299, 0.587, 0.114])
            if lm[m].mean() < 90: continue
            b = (lm // 8).astype(int).clip(0, 31)
            for k in range(32):
                sel = m & (b == k)
                if sel.any(): S[k] += px[sel].sum(0); N[k] += sel.sum()
    return [list(map(int, S[k] / max(N[k], 1))) for k in range(32)]
def ramp():
    p = os.path.join(HERE, "la_day_ramp.json")
    if not os.path.exists(p): json.dump(make_ramp(), open(p, "w"))
    return np.array(json.load(open(p)), float)
Y_DAY = ([0, 8, 16, 30, 60, 120, 200, 255], [104, 110, 118, 132, 152, 178, 214, 246])   # steep at the dark end: black panes stay darker than the wall
STUCCO = [(10, 6, -6), (8, 2, -10), (12, 0, -2), (-3, 6, -3), (-8, 0, 8), (4, 4, -4)]       # cream, sand, pale pink, pale green, blue-grey, neutral (Miami-like variety, per texture)           # night luma -> day luma
def day_v2_clut(clut, idx, name=""):
    import zlib
    tint = np.array(STUCCO[zlib.crc32(name.encode()) % len(STUCCO)], float)
    R_ = ramp(); ov = OVERRIDE.get(name, {}); rl = roles(clut, idx, ov.get("no_glass", False)); tot = float(idx.size); out = []
    glass_lit = np.array(ov.get("glass_lit", (178, 198, 216))); glass_dark = np.array(ov.get("glass_dark", (70, 86, 104)))
    for e, w in enumerate(clut):
        if w == 0: out.append(0); continue
        c = np.array(rgb(w), float); l = lum(c); stp = w & 0x8000; role = rl.get(e); area = (idx == e).sum() / tot
        sat = (c.max() - c.min()) / max(c.max(), 1)
        if role == "glass_lit": n = glass_lit * (0.85 + 0.3 * l / 255)
        elif role == "glass_dark": n = glass_dark * (0.8 + 0.5 * l / 75) + (c - l) * 0.25
        elif l > 200 and area < 0.03 and sat < 0.5: n = np.array([214, 212, 200.])                     # unlit lamp / bulb body
        elif c[0] - c[2] > 35 and 45 < l <= 115 and role != "wall":                                      # warm glow halos of lamps / lit rooms
            f = 150 / 8.0; k0 = int(f); n = R_[k0] * (1 - (f - k0)) + R_[k0 + 1] * (f - k0) + (c - l) * 0.15
        else:
            y = float(np.interp(l, *Y_DAY)); f = y / 8.0; k0 = int(min(f, 30)); k1 = min(k0 + 1, 30)
            base = R_[k0] * (1 - (f - k0)) + R_[k1] * (f - k0)
            n = base + (c - l) * (0.8 if role != "wall" else 0.35) + (tint if role in ("wall", "plain") else 0)
        out.append(word(np.clip(n, 0, 255), stp))
    return out

def night_targets(la_textures, uses):
    """R33: the LA textures that get day_v2_clut(clut, idx, name) - every world texture Polish's night detector flags
    (dark share > 30 % or a lit-window grid), ground/ad/sprite words excluded. NO donor swap for these any more
    (the day art keeps the night art's layout). la_textures = polish_laday.textures(la)[1], uses = use_counts(la)."""
    import polish_laday as L
    out = []
    for t in la_textures:
        n = t[0].upper()
        if n.startswith(L.SKIP_PREFIX) or not uses.get((t[1], t[2])) or any(w in n for w in L.AD_WORDS + L.GROUND_WORDS): continue
        dark, warm, Lm, comps = L.night_info(t)
        if dark > L.NIGHT_SHARE or (warm > 0.04 and comps > L.GRID_BLOBS): out.append(t)
    return out
