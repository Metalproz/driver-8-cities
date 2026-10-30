"""texrepack.py — repack Chicago's (and the base city's engine) textures into
Driver 1-sized page sets.

Driver 1 has 16 VRAM page slots (NOTES.md). One area is loaded at a time, so
for every area: permanent pages + special pages loaded + that area's pages
must fit. Textures are grouped by the set of areas that need them (permanent
= everywhere) and each group is packed tightly; a page is listed by every
area in its group. Textures and palettes move together (detail i <-> CLUT i);
polygons keep working because UVs are shifted by the rectangle's move.

Output: RepackResult with new pages, details, permanent/special lists, area
page lists and remap[(src, page, detail)] = (new_page, new_detail, dx, dy).
"""
from __future__ import annotations

import collections
import struct
from dataclasses import dataclass, field

from levfile import Lev
from mapinfo import SpoolInfo, SPOOLINFO
from models import inmem_models, area_models, model_names, Model, POLY_SIZES
from texpages import Page, read_pages, MAX_CLUTS as FORMAT_MAX_CLUTS

# Driver 1's own pages hold at most 33 textures (palettes); the raw record has
# room for 63, but more than ~32 per page scrambles palettes in game.
MAX_CLUTS = 31   # palettes per page: 32 fit a slot's 8 CLUT rows, but the page loader
                 # (0x8003394C) uploads npal / 4 + 1 rows, so a page with exactly 32
                 # zeroes the next slot's palettes 0-3 (transparent textures: missing
                 # ground, invisible buildings, noise)

TEXTURED = {4, 5, 7, 9, 10, 11, 17, 20, 21, 22, 23}
PAGE = 256
SLOTS = 16              # VRAM page slots (last one partly holds CLUTs)
SPECIAL_LOADED = 2      # D1 loads 2 x (car types) special pages; Take a Ride = 1 type
CLUT_SLOT_COST = 1      # the CLUT column takes most of one slot
SHARED_TO_PERM = int(__import__("os").environ.get("CHI_SHARED", "99"))   # textures used by this many areas become permanent
MAX_SHRINK = int(__import__("os").environ.get("CHI_SHRINK", "3"))       # halvings allowed per texture
# Per-area page contents need every area switch to reload its pages (Driver 1
# keeps pages that stay listed); shared contents keep Driver 1's behaviour.
CLUT_SHARE = __import__("os").environ.get("CHI_POLISH_CLUTSHARE", "") == "1"   # S1: identical CLUTs on a permanent page share a detail
PLACE_STATS = {}
INMEM_KEEP = None       # Q36 B: in-memory models that stay resident (None = all)
SHORT_ROWS = 170        # S1 slot 15: rows v 0..169 (row 426 of VRAM = loading-screen CLUT)
S1_RESERVE = {}         # Polish S1: area -> pages kept free for its local textures
S1_LOCAL = []           # Polish S1: local (per-area packed) Chicago textures
PER_AREA_CONTENT = __import__("os").environ.get("CHI_PER_AREA", "1") == "1"

# texture names the Driver 1 EXE looks up (strings in SLUS_008.42)
EXE_TEXTURE_NAMES = set("""FOREARM1 FRAMEADV CHOOSECA LIGHTREF CARSHAD BLIMP SMOKE DEBRIS LITTER
SUN2 SKID FLARE1 SPLASH SWBIRD1 SWBIRD2 SKYSUN DROP DIGIT COLLON JEANS1 ARM1 CHEST1 LOWHEAD
ADDCAM AUTO CHASEC CLOCK DELCAM EDITCAM FIXEDCA INCAR LENSCHA LOOKCAR MOVECMP MOVECAM PAUSE
PLAYCAM PLAYPAU SAVE2CA RESTREP SEA""".split())
# + per-city event models the loader requires for the replaced slot (LA: BOEING, table @0x80089E84)
EXTRA_MODELS = {}   # C42 r3 (c): key -> (Model, areas) whose textures join those areas' sets (convert sets it)
SKY_SLOTS = 4   # every Driver 1 city keeps its sky models in slots 0..3
ENGINE_MODEL_NAMES = "CLEANWHEEL FASTWHEEL DAMWHEEL HUBCAP1 PEDHEAD1 PEDHEAD2 PEDHEAD3 PEDHEAD4 BOEING".split()


def model_texrefs(m: Model, allm: dict) -> set:
    out = set()
    src = m                                  # instances have their own polygons
    if src.poly_block >= len(src.data):
        return out
    q = src.poly_block
    for _ in range(src.num_polys):
        t = src.data[q] & 31
        if t in TEXTURED and src.data[q + 1] != 0xFF:
            out.add((src.data[q + 1], src.data[q + 2]))
        q += POLY_SIZES[t]
    return out


def car_models(lev: Lev) -> list[Model]:
    cm = lev.loadtime.get(28).data
    ents = [struct.unpack_from("<3i", cm, 4 + 12 * i) for i in range(13)]
    base = 4 + 12 * 13
    out = []
    for e in ents:
        for off in e:
            if off != -1:
                size = struct.unpack_from("<i", cm, base + off)[0]
                out.append(Model.parse(-1, cm[base + off + 4: base + off + 4 + size]))
    return out


@dataclass
class Item:
    src: str            # "C" (Chicago) or "B" (base city)
    page: int
    detail: int
    name: bytes
    x: int
    y: int
    w: int
    h: int
    clut: bytes
    rows: list
    ident: int = 0      # TEXINF id (kept from the source)
    shrink: int = 0     # times halved
    near: frozenset = frozenset()   # areas in which a model using it is seen up close

    def halve(self):
        """Halve the longer side (nearest-neighbour). UVs are rescaled via remap."""
        import polish_tex                     # CHI_POLISH_TEX=filter: box-filtered halving (Polish, C7)
        if polish_tex.FILTER:
            return polish_tex.halve(self)
        if self.w >= self.h and self.w > 1:
            self.rows = [row[::2] for row in self.rows]
            self.w = len(self.rows[0])
        elif self.h > 1:
            self.rows = self.rows[::2]
            self.h = len(self.rows)
        self.shrink += 1


@dataclass
class PackedPage:
    group: object
    items: list = field(default_factory=list)   # (item, x, y)


@dataclass
class RepackResult:
    pages: dict                  # new page index -> Page
    details: dict                # new page index -> list of (id, name, x, y, w, h)
    flags: dict                  # new page index -> 1 permanent / 2 swap / 4 special
    permanent: list              # new page indices
    special: list                # (new page index, compressed blob) copied from base
    area_pages: dict             # area -> list of new page indices
    remap: dict                  # (src, page, detail) -> (page, detail, nx, ny, ox, oy, ow, oh, nw, nh)
    report: list
    area_page_content: dict = field(default_factory=dict)   # (area, page) -> Page streamed with that area


class Skyline:
    """Bottom-left skyline packer for one 256x256 page."""

    def __init__(self):
        self.sky = [(0, 0, PAGE)]     # (x, y, width) segments

    def place(self, w, h):
        best = None
        for i in range(len(self.sky)):
            x = self.sky[i][0]
            if x + w > PAGE:
                break
            y, width, j = 0, 0, i
            while width < w:
                if j >= len(self.sky):
                    y = None
                    break
                y = max(y, self.sky[j][1])
                width += self.sky[j][2]
                j += 1
            if y is None or y + h > PAGE:
                continue
            if best is None or (y + h, x) < (best[1] + h, best[0]):
                best = (x, y)
        if best is None:
            return None
        x, y = best
        new = []
        for sx, sy, sw in self.sky:
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
        self.sky = merged
        return x, y


def pack_group(items: list, group) -> list[PackedPage]:
    if group == "perm" and any(getattr(it, "twin", None) is not None for it in items):
        import polish_cars                    # CHI_POLISH_CARPAGES=2 (Polish, C49): car damage twins at u+128
        return polish_cars.pack_twins(items, group, pack_group, _free_spot, MAX_CLUTS, PAGE)
    order = sorted(items, key=lambda it: (-it.h, -it.w))
    pages: list[PackedPage] = []
    packers: list[Skyline] = []
    for it in order:
        for pp, sk in zip(pages, packers):
            if len(pp.items) >= MAX_CLUTS:
                continue
            pos = sk.place(it.w, it.h)
            if pos:
                pp.items.append((it, *pos))
                break
        else:
            sk = Skyline()
            pos = sk.place(it.w, it.h)
            assert pos, "texture larger than a page"
            pp = PackedPage(group)
            pp.items.append((it, *pos))
            pages.append(pp)
            packers.append(sk)
    return pages


FORCE_PERM = {b"RIVER3A"}   # Chicago textures of generated models (convert.shore_wall_model), kept in FORCED_AREAS
FORCED_AREAS = set()        # set by convert.py: areas in which the shore walls are seen
WATER_TEXTURE = (b"LASEA", "d1_MIAMI.lev", b"SEA")   # inputs.py name   # LA's 16x16 sea -> Miami's 64x64 (calmer, darker)


NIGHT_WATER = 0.17            # night: Miami Night's rendered sea / Chicago night's (measured 0.161-0.181 per channel, no tint)


def water_from_miami(items, night=False):
    """Give the water tile Miami's sea texture: the item keeps LA's source rectangle
    (UVs are remapped from it); pixels, palette, size and name (SEA) change. At night the
    palette is darkened (CHI_NIGHT_WATER): Miami Night dims its sea through Driver 1's night
    flag, which Chicago's night leaves off (D2's night textures are dark already)."""
    import os
    if not WATER_TEXTURE or "la_water" in os.environ.get("CHI_EXPERIMENT", ""):
        return
    old_name, path, new_name = WATER_TEXTURE
    it = next((i for i in items if i.src == "B" and i.name == old_name), None)
    if it is None:
        return
    import inputs
    lev = Lev.parse(inputs.read(path))
    ti, pages = read_pages(lev)
    names = lev.loadtime.get(5).data
    for p, dl in enumerate(ti.details):
        for k, (ident, noff, x, y, w, h) in enumerate(dl):
            if p in pages and names[noff: names.index(b"\0", noff)] == new_name:
                it.rows, it.w, it.h = pages[p].rect(x, y, w, h), w, h
                it.clut = pages[p].cluts[k]
                f = float(os.environ.get("CHI_NIGHT_WATER", NIGHT_WATER))
                if night and f < 1.0:
                    it.clut = darken_clut(it.clut, f, rnd=True)
                    print("night: water (SEA) darkened x%.2f" % f)
                # the engine finds the sea by name (GetTextureInfo("SEA"), 0x8004219C) and
                # draws water near the camera with that page/palette: LA has no "SEA",
                # so it used a stale palette (pink water around a sinking car)
                it.name = b"SEA"
                return


DAY_LEV = __import__("cityprofile").P.lev_day     # inputs.py name (M3: the city profile's day level) (Option A: from the player's Driver 2 disc)


def darken_clut(clut: bytes, f: float, rnd: bool = False) -> bytes:
    """15-bit palette scaled by f; 0x0000 (transparent) and the STP bit kept, no colour turns
    into 0x0000 (it would become transparent)."""
    out = bytearray(clut)
    for i in range(0, len(clut) - 1, 2):
        c = clut[i] | clut[i + 1] << 8
        if c == 0:
            continue
        r, g, b = c & 31, (c >> 5) & 31, (c >> 10) & 31
        q = (lambda v: int(v * f + 0.5)) if rnd else (lambda v: int(v * f))   # rounding: fewer lost levels
        r, g, b = q(r), q(g), q(b)
        n = (c & 0x8000) | r | g << 5 | b << 10
        if n == 0:
            n = 0x0421
        out[i], out[i + 1] = n & 0xFF, n >> 8
    return bytes(out)


def mean_brightness(rows, clut: bytes) -> float:
    c16 = struct.unpack("<16H", clut[:32].ljust(32, bytes(1)))
    tot = n = 0
    for row in rows:
        for v in row:
            c = c16[v & 15]
            if c:
                tot += (c & 31) + ((c >> 5) & 31) + ((c >> 10) & 31)
                n += 1
    return tot / n if n else 0.0


NIGHT_KEEP_RATIO = 0.8        # night textures this much darker than by day are D2's night designs: kept


def night_same_as_day(chicago: Lev):
    """Night conversion (D2's NLEVELS level): {texture name: day mean brightness}. D2 ships about
    460 textures darkened for the night (0.1-0.4 of the day brightness) and keeps the others
    (ground, roads, many props) as bright as by day, darkening them in its renderer; Driver 1 with
    LA's night look does not, so those are darkened here. None for a day conversion."""
    import os
    import inputs
    src = inputs.d2_lev()
    f = float(os.environ.get("CHI_NIGHT_DARKEN", "0.3"))
    if inputs.is_input(src, DAY_LEV) or f >= 1.0:
        return None, f
    day = Lev.parse(inputs.read(DAY_LEV))
    dti, dpages = read_pages(day)
    dnames = day.loadtime.get(5).data
    out = {}
    for p, pg in dpages.items():
        for k, d in enumerate(dti.details[p]):
            w, h = d[4] or 256, d[5] or 256
            w, h = min(w, PAGE - d[2]), min(h, PAGE - d[3])
            name = dnames[d[1]: dnames.index(b"\0", d[1])]
            out[name] = mean_brightness(pg.rect(d[2], d[3], w, h), pg.cluts[k] if k < len(pg.cluts) else bytes(32))
    return out, f


def collect(chicago: Lev, base: Lev, model_areas=None, model_near=None, cars: Lev = None):
    """Gather used textures from both levels, keyed by group. cars: the level whose car set
    (car models, their textures and special pages) is used (convert.car_set; default the base
    city's); its textures are source "K"."""
    cti, cpages = read_pages(chicago)
    day_tex, dark_f = night_same_as_day(chicago)
    ndark = 0
    night_tiles = set()                       # C125 (CityProfile.night_tiles_third): textures of ground tile models
    # Q73 = A (user 30.10.): every D2 city's profile now carries the C125 + C128 night rules (Chicago included).
    # CHI_POLISH_NIGHT_D2 overrides the profile: 1 = on for any city, 0 = off (Chicago's pre-Q73 look); unset = profile.
    _nd2_raw = __import__("os").environ.get("CHI_POLISH_NIGHT_D2", "")
    _nd2_env = _nd2_raw == "1"
    _nd2_off = _nd2_raw == "0"
    if day_tex is not None and not _nd2_off and (__import__("cityprofile").P.night_tiles_third or _nd2_env):
        _cm, _ = inmem_models(chicago)
        for _m in {**area_models(chicago), **_cm}.values():
            if _m.shape_flags & 0x0400:
                night_tiles |= model_texrefs(_m, {})
        print("night: %d ground-tile textures darkened x1/3 (C125)" % len(night_tiles))
    night_d2 = day_tex is not None and not _nd2_off and (__import__("cityprofile").P.night_models_d2 or _nd2_env)   # C128: as D2's
    if night_d2:                              # sprites (trees): D2 lightLevel / 3 at night (draw.c, not Chicago)
        _cm, _ = inmem_models(chicago)
        _ns = set()
        for _m in {**area_models(chicago), **_cm}.values():
            if _m.shape_flags & 0x4000 and not _m.shape_flags & 0x0400:
                _ns |= model_texrefs(_m, {})
        night_tiles |= _ns
        print("night: %d sprite textures darkened x1/3, other model textures as Driver 2's night level (C128)" % len(_ns))
    bti, bpages = read_pages(base)
    cnames = chicago.loadtime.get(5).data
    bnames = base.loadtime.get(5).data
    name_at = lambda blob, off: blob[off: blob.index(b"\0", off)]

    # Chicago: every texture any Chicago model uses
    cmem, _ = inmem_models(chicago)
    call = {**area_models(chicago), **cmem}
    cused, tex_areas, tex_near = set(), collections.defaultdict(set), collections.defaultdict(set)
    for i, m in call.items():
        refs = model_texrefs(m, call)
        cused |= refs
        if model_areas is not None:
            for t in refs:
                tex_areas[t] |= model_areas.get(i, set())
                if model_near is not None:
                    tex_near[t] |= model_near.get(i, set())
    for _key, (m, areas) in EXTRA_MODELS.items():   # C42 r3 (c): the regional specials (polish_specials)
        refs = model_texrefs(m, {})
        cused |= refs
        if model_areas is not None:
            for t in refs:
                tex_areas[t] |= set(areas)
    cused = {t for t in cused if t[0] < cti.num_pages and t[1] < len(cti.details[t[0]]) and t[0] in cpages}
    import os
    walls = not any(e in ("no_walls", "no_water") for e in os.environ.get("CHI_EXPERIMENT", "").split(","))
    forced = {(p, k) for p in cpages for k, d in enumerate(cti.details[p])
              if walls and name_at(cnames, d[1]) in FORCE_PERM}
    cused |= forced

    csp = SpoolInfo.parse(chicago.inmem.get(SPOOLINFO).data)
    member = collections.defaultdict(set)
    for a in sorted({s[7] for s in csp.spools.values()} - {255}):
        for p in csp.area_tpages[a]:
            if p != 0xFF:
                member[p].add(a)
    cperm = {p for p, _ in cti.permanent}

    # base city: engine textures (EXE names, car models, wheels/peds)
    bspecial = [p for p, _ in bti.special]
    bmem, _ = inmem_models(base)
    ball = {**area_models(base), **bmem}
    bmn = model_names(base)
    bused = set()
    if cars is None or cars is base:
        cars = base
        for m in car_models(base):
            bused |= model_texrefs(m, ball)
    for n in ENGINE_MODEL_NAMES:
        if n in bmn and bmn.index(n) in ball:
            bused |= model_texrefs(ball[bmn.index(n)], ball)
    for i in range(SKY_SLOTS):          # Driver 1 draws models 0..3 as the sky
        bused |= model_texrefs(ball[i], ball)
    for page in bpages:
        if page in bspecial:
            continue
        for k, d in enumerate(bti.details[page]):
            if name_at(bnames, d[1]).decode("latin-1") in EXE_TEXTURE_NAMES:
                bused.add((page, k))
    bused = {t for t in bused if t[0] not in bspecial and t[0] in bpages and t[1] < len(bti.details[t[0]])}

    groups = collections.defaultdict(list)

    def make(src, ti, pages, names, t):
        d = ti.details[t[0]][t[1]]
        ident, noff, x, y, w, h = d
        w, h = w or 256, h or 256
        w, h = min(w, PAGE - x), min(h, PAGE - y)
        pg = pages[t[0]]
        clut = pg.cluts[t[1]] if t[1] < len(pg.cluts) else bytes(32)
        rows = pg.rect(x, y, w, h)
        nm = name_at(names, noff)
        nonlocal ndark
        if src == "C" and day_tex is not None and t in night_tiles:
            clut = darken_clut(clut, 1.0 / 3)           # C125: D2 draws night tiles at combointensity / 3
            ndark += 1
        elif src == "C" and day_tex is not None and not night_d2 and day_tex.get(nm) and \
                mean_brightness(rows, clut) >= NIGHT_KEEP_RATIO * day_tex[nm]:
            clut = darken_clut(clut, dark_f)            # as bright as by day in D2: darkened
            ndark += 1
        it = Item(src, t[0], t[1], nm, x, y, w, h, clut, rows, ident)
        it.ow, it.oh = w, h
        return it

    for t in sorted(bused):
        groups["perm"].append(make("B", bti, bpages, bnames, t))
    sti = bti
    if cars is not base:                  # another city's car set: its car textures outside the special pages
        sti, kpages = read_pages(cars)
        knames = cars.loadtime.get(5).data
        kspecial = {p for p, _ in sti.special}
        kused = set()
        import polish_cars                    # CHI_POLISH_D2CARS=1 (Polish, C42): only the mapped Driver 2 cars
        import polish_carmix                  # CHI_POLISH_D2CARS=mixed: the car set's player cars only
        for m in (polish_cars.models_for(cars) if polish_cars.enabled() else
                  polish_carmix.player_models(cars) if polish_carmix.enabled() else car_models(cars)):
            kused |= model_texrefs(m, {})
        for t in sorted(kused):
            if t[0] not in kspecial and t[0] in kpages and t[1] < len(sti.details[t[0]]):
                groups["perm"].append(make("K", sti, kpages, knames, t))
    import polish_carmix                      # mixed car set (Polish, C42 step 1): D2 traffic/cop textures, source "D"
    if polish_carmix.enabled():
        cspecial = {p for p, _ in cti.special}
        dused = set()
        for m in polish_carmix.civ_models(chicago):
            dused |= model_texrefs(m, {})
        for t in sorted(dused):
            if t[0] not in cspecial and t[0] in cpages and t[1] < len(cti.details[t[0]]):
                groups["perm"].append(make("D", cti, cpages, cnames, t))
    water_from_miami(groups["perm"], night=day_tex is not None)
    import polish_moon                         # CHI_NIGHT_MOON=1 (Polish/Design): D2's moon in the night SKYSUN slot
    if polish_moon.enabled() and day_tex is not None:
        print("night moon: SKYSUN replaced by D2's SKYMOON in %d item(s)" % polish_moon.apply(groups["perm"]))
    import polish_tex
    theights = polish_tex.texture_heights(call) if polish_tex.HEIGHT else {}
    import polish_s1
    S1_LOCAL.clear()
    s1_local, s1_areas = set(), {}
    if polish_s1.ENABLED and model_areas is not None:
        extra = set()
        for _key, (m_, _a) in EXTRA_MODELS.items():
            extra |= model_texrefs(m_, {})
        s1_local, s1_areas = polish_s1.classify(call, {i: m for i, m in cmem.items() if INMEM_KEEP is None or i in INMEM_KEEP},
                                                lambda m_: model_texrefs(m_, call), extra, forced)
    for t in sorted(cused):
        it = make("C", cti, cpages, cnames, t)
        it.height = theights.get(t, 0)
        it.near = frozenset(tex_near.get(t, ()))
        if it.name.decode("latin-1") in EXE_TEXTURE_NAMES:
            it.name = b"_" + it.name[1:]          # the base city's version must win lookups
        if t in forced:                       # generated models (shore walls): the areas they are seen in
            tex_areas[t] |= FORCED_AREAS      # (forcing it permanent added a page: wrong area textures, C29)
        if t in s1_local:                       # S1: packed per area later (polish_s1)
            it.s1_areas = s1_areas[t]
            S1_LOCAL.append(it)
            continue
        if model_areas is not None:
            # residency from where each texture's models are visible (convert.build_world)
            if len(tex_areas.get(t, ())) >= SHARED_TO_PERM:
                key = "perm"                  # needed by many areas: resident everywhere
            elif tex_areas.get(t):
                key = frozenset(tex_areas[t])
            else:
                continue                      # only used by models that are never placed
        else:
            key = "perm" if (t[0] in cperm or t[0] not in member) else frozenset(member[t[0]])
        groups[key].append(it)
    if day_tex is not None:
        print("night: %d textures as bright as by day darkened x%.2f" % (ndark, dark_f))
    return groups, sti, cars, csp


def pack_area_aware(groups: dict, budget: int):
    """Pack with page sharing across area sets: each non-permanent texture goes
    to the page that adds the fewest areas to that page's load list, so small
    textures of different area combinations share pages instead of each
    combination taking a whole page. A page is listed by every area of the
    union of its textures' area sets; no area may exceed the slot budget.
    Returns ({group key: [PackedPage]}, None) or (None, failing area set)."""
    perm = pack_group(groups.get("perm", []), "perm")
    cap = budget - len(perm)
    if cap < 0:
        return None, "perm"
    # widely shared sets first, same sets together: later subsets can then fill
    # those pages at no extra cost (palettes, 32 per page, are the scarce part)
    items = sorted(((it, g) for g, its in groups.items() if g != "perm" for it in its),
                   key=lambda e: (-len(e[1]), sorted(e[1]), -(e[0].w * e[0].h)))
    pages = []                                   # [area set, Skyline, PackedPage]
    load = collections.Counter()
    for it, S in items:
        best = None
        for pg in pages:
            if len(pg[2].items) >= MAX_CLUTS:
                continue
            new = S - pg[0]
            if any(load[a] + 1 > cap for a in new):
                continue
            trial = Skyline()
            trial.sky = list(pg[1].sky)
            if trial.place(it.w, it.h) is None:
                continue
            cost = (len(new), -len(pg[2].items), len(pg[0] - S))
            if best is None or cost < best[0]:
                best = (cost, pg)
        if best is None:
            if any(load[a] + 1 > cap for a in S):
                return None, S
            pg = [set(), Skyline(), PackedPage(None)]
            pages.append(pg)
        else:
            pg = best[1]
        for a in S - pg[0]:
            load[a] += 1
        pg[0] |= S
        x, y = pg[1].place(it.w, it.h)
        pg[2].items.append((it, x, y))
    packed = {"perm": perm}
    for areas, _sk, pp in pages:
        key = frozenset(areas)
        pp.group = key
        packed.setdefault(key, []).append(pp)
    return packed, None


ALIGN = 4      # texture positions on a 4-texel grid (4-bit pages: 2 texels per byte)


def _free_spot(occ, w, h):
    """First (x, y) where a w x h rectangle is free in the boolean map, or None."""
    import numpy as np
    if w > PAGE or h > PAGE:
        return None
    integ = np.zeros((PAGE + 1, PAGE + 1), dtype=np.int32)
    integ[1:, 1:] = occ.cumsum(0).cumsum(1)
    ys = np.arange(0, PAGE - h + 1, ALIGN)
    xs = np.arange(0, PAGE - w + 1, ALIGN)
    if not len(ys) or not len(xs):
        return None
    Y, X = np.meshgrid(ys, xs, indexing="ij")
    s = integ[Y + h, X + w] - integ[Y, X + w] - integ[Y + h, X] + integ[Y, X]
    hit = np.argwhere(s == 0)
    if not len(hit):
        return None
    j, i = hit[0]
    return int(xs[i]), int(ys[j])


def pack_per_area(groups: dict, budget: int, preload=None):
    """Area textures with per-area page contents. Every area streams its own
    copy of each page it lists (its own gfx block on disc), so a page index
    can hold different textures in different areas: two textures only need
    distinct palette slots and non-overlapping pixels if some area needs both.
    Each texture goes to the page whose area lists grow least, at a spot and
    palette slot free in all its areas; no area may list more than `cap` pages.
    Returns (perm pages, area pages, None) or (None, None, failing area set)."""
    import numpy as np
    perm = pack_group(groups.get("perm", []), "perm")
    cap = budget - len(perm)
    if cap < 0:
        return None, None, "perm"
    items = sorted(((it, frozenset(g)) for g, its in groups.items() if g != "perm" for it in its),
                   key=lambda e: (-len(e[1]), -(e[0].w * e[0].h)))
    pages = []          # {"areas": set, "occ": {area: bool map}, "cluts": {area: set}, "items": [...]}
    lists = collections.Counter(preload or {})      # preload: pages already listed per area (Polish shared pages)
    for it, S in items:
        best = None
        for pg in pages:
            new = S - pg["areas"]
            if any(lists[a] + 1 > cap - S1_RESERVE.get(a, 0) for a in new):
                continue
            used = set()
            for a in S:
                used |= pg["cluts"].get(a, set())
            d = next((d for d in range(MAX_CLUTS) if d not in used), None)
            if d is None:
                continue
            occ = np.zeros((PAGE, PAGE), dtype=bool)
            for a in S:
                if a in pg["occ"]:
                    occ |= pg["occ"][a]
            pos = _free_spot(occ, it.w, it.h)
            if pos is None:
                continue
            cost = (len(new), -len(S & pg["areas"]))
            if best is None or cost < best[0]:
                best = (cost, pg, d, pos)
                if cost[0] == 0:
                    break
        if best is None:
            if any(lists[a] + 1 > cap - S1_RESERVE.get(a, 0) for a in S):
                return None, None, S
            pg = {"areas": set(), "occ": {}, "cluts": {}, "items": []}
            pages.append(pg)
            d, pos = 0, (0, 0)
        else:
            _, pg, d, pos = best
        x, y = pos
        for a in S:
            if a not in pg["areas"]:
                lists[a] += 1
            pg["areas"].add(a)
            pg["occ"].setdefault(a, np.zeros((PAGE, PAGE), dtype=bool))[y:y + it.h, x:x + it.w] = True
            pg["cluts"].setdefault(a, set()).add(d)
        pg["items"].append((it, S, d, x, y))
    return perm, pages, None


def repack(chicago: Lev, base: Lev, model_areas=None, model_near=None, cars: Lev = None) -> RepackResult:
    # bti / base_lev below: the level whose special (car) pages are taken (the car set's)
    groups, bti, base_lev, csp = collect(chicago, base, model_areas, model_near, cars)
    budget = SLOTS - CLUT_SLOT_COST - SPECIAL_LOADED + int(__import__("os").environ.get("CHI_POLISH_EXTRA_PAGES", "0"))   # estimate only
    import polish_cars                        # CHI_POLISH_CARPAGES=1 (Polish, C42): traffic/cop car pages kept whole
    fixed = polish_cars.fixed_pages(base_lev, [p for p, _ in bti.special]) if polish_cars.carpages_enabled() else []
    fsrc = "B" if base_lev is base else "K"
    if fixed:
        for g in list(groups):
            groups[g] = [it for it in groups[g] if not (it.src == fsrc and it.page in fixed)]
            if not groups[g] and g != "perm":
                del groups[g]
        budget -= len(fixed)
    if polish_cars.carpages_mode() == "2":
        import polish_carmix
        if polish_carmix.enabled():           # mixed: the traffic/cop textures are Driver 2's (source "D")
            import texpages as _tp
            cti_, _ = _tp.read_pages(chicago)
            npairs = polish_cars.attach_twins(groups, chicago, "D", [p for p, _ in cti_.special])
        else:
            npairs = polish_cars.attach_twins(groups, base_lev, fsrc, [p for p, _ in bti.special])
            if polish_cars.enabled():
                print("car CLUT table: %d palettised textures first" % polish_cars.mark_palette_items(groups, base_lev, fsrc, base))
        print("car damage twins kept at u+128 (CHI_POLISH_CARPAGES=2): %d" % npairs)
        if (polish_carmix.enabled() or polish_cars.enabled()) and polish_carmix.HALF:   # mix2: the D2 car textures take the cost, not the city
            nh = 0
            # CHI_POLISH_D2CARS=1 (C42 engine step): the Driver 2 car textures are source "K" (the car set = the D2
            # level); COPFULL keeps the cop's (slot 0) pages full, shared with civilian slot 1 (same D2 model 3)
            csrc_, keep_ = ("D", polish_carmix.cop_pages(chicago) if polish_carmix.COP_FULL else set())
            if polish_cars.enabled():
                csrc_, keep_ = "K", (polish_carmix.slot_pages(chicago, 0) if polish_carmix.COP_FULL else set())
            for it in groups.get("perm", []):
                if it.src == csrc_ and it.page not in keep_:
                    for _ in range(polish_carmix.HALF):
                        it.halve()
                        if getattr(it, "twin", None) is not None:
                            it.twin.halve()
                    nh += 1
            print("mixed car set: %d Driver 2 car textures halved x%d (twins alike)" % (nh, polish_carmix.HALF))
    shrunk = 0
    area_packed = None
    if __import__("os").environ.get("CHI_POLISH_PACKSTAT") == "1":      # Polish S1 diagnostic: per-area need vs capacity
        import hashlib as _h
        _perm = pack_group(groups.get("perm", []), "perm")
        _cap = (budget - len(_perm)) * PAGE * PAGE
        _need = collections.Counter(); _uniq = {}
        for g, its in groups.items():
            if g == "perm":
                continue
            for it in its:
                for a in g:
                    _need[a] += it.w * it.h
                key = _h.md5(b"".join(bytes(r) for r in it.rows) + it.clut + b"%d,%d" % (it.w, it.h)).hexdigest()
                _uniq.setdefault(key, []).append(it)
        dup = sum(sum(i.w * i.h for i in v[1:]) for v in _uniq.values() if len(v) > 1)
        print("PACKSTAT perm pages %d, area capacity %d texels (%.1f pages); exact-duplicate area textures %d texels in %d groups"
              % (len(_perm), _cap, _cap / 65536, dup, sum(1 for v in _uniq.values() if len(v) > 1)))
        for a in sorted(_need):
            print("PACKSTAT area %2d needs %7d texels = %.2f pages (%.0f %% of capacity)" % (a, _need[a], _need[a] / 65536, 100 * _need[a] / _cap))
        import heapq
        for extra in (0, 1, 2, 3):
            cap2 = _cap + extra * PAGE * PAGE
            halved_any, halvings, lost = set(), 0, 0
            for a in sorted(_need):
                its = [[it.w * it.h, id(it), it.w, it.h, 0, it] for g, its_ in groups.items() if g != "perm" and a in g for it in its_]
                tot = sum(e[0] for e in its)
                h = [(-e[0], e[1], k) for k, e in enumerate(its)]; heapq.heapify(h)
                while tot > 0.92 * cap2 and h:
                    _, _, k = heapq.heappop(h); e = its[k]
                    if e[4] >= 3 or max(e[2], e[3]) < 16:
                        continue
                    if e[2] >= e[3]: e[2] //= 2
                    else: e[3] //= 2
                    new_a = e[2] * e[3]; tot -= e[0] - new_a; lost += e[0] - new_a; e[0] = new_a; e[4] += 1
                    halved_any.add(e[1]); halvings += 1
                    heapq.heappush(h, (-e[0], e[1], k))
            print("PACKSTAT ideal per-area packing (92 %% fill) with +%d page(s) per area: %d textures halved somewhere, %d area-halvings, %.1f page-area units lost"
                  % (extra, len(halved_any), halvings, lost / 65536))
    import polish_pages                       # CHI_POLISH_SHAREDPAGES=1 (Polish, C45): stable shared pages
    stable, stable_load = polish_pages.extract(groups) if (model_areas is not None and PER_AREA_CONTENT) else ({}, None)
    short_items = []                          # S1 slot 15 (CHI_POLISH_S1_SLOT15): 5th permanent page, rows 0..169
    if __import__("os").environ.get("CHI_POLISH_S1_SLOT15") == "1" and model_areas is not None:
        import numpy as np
        occ = np.zeros((PAGE, PAGE), dtype=bool); occ[SHORT_ROWS:, :] = True
        nareas = lambda g: 99 if g == "perm" else len(g)
        cands = sorted(((g, it) for g, its in groups.items() for it in its if it.src == "C"),
                       key=lambda e: (-nareas(e[0]), -(e[1].w * e[1].h)))
        for g, it in cands:
            if len(short_items) >= MAX_CLUTS:
                break
            if it.h > SHORT_ROWS:
                continue
            pos = _free_spot(occ, it.w, it.h)
            if pos is None:
                continue
            x, y = pos
            occ[y:y + it.h, x:x + it.w] = True
            short_items.append((it, x, y))
            groups[g].remove(it)
        for g in [g for g, its in groups.items() if not its and g != "perm"]:
            del groups[g]
        print("S1 slot 15: %d shared textures on the short permanent page (%d texels)"
              % (len(short_items), sum(it.w * it.h for it, _x, _y in short_items)))
    S1_RESERVE.clear()
    if S1_LOCAL:                              # S1: split each area's pages between global and local textures by need
        _permn = len(pack_group(groups.get("perm", []), "perm"))
        _cap = budget - _permn
        _g, _l = collections.Counter(), collections.Counter()
        for g, its in groups.items():
            if g != "perm":
                for it in its:
                    for a in g:
                        _g[a] += it.w * it.h
        for it in S1_LOCAL:
            for a in it.s1_areas:
                _l[a] += it.w * it.h
        for a in set(_g) | set(_l):
            S1_RESERVE[a] = min(_cap - 1, int(round(_cap * _l[a] / max(1, _g[a] + _l[a]))))
        print("S1 reserve (pages per area for local textures): %s" % dict(sorted(S1_RESERVE.items())))
    while model_areas is not None:
        if PER_AREA_CONTENT:
            perm_pages, area_packed, failed = pack_per_area(groups, budget, stable_load)
            if area_packed is not None:
                packed = {"perm": perm_pages, **stable}
                break
        else:
            packed, failed = pack_area_aware(groups, budget)
            if packed is not None:
                break
        # halve the largest Chicago texture involved (area textures of the failing
        # areas, else permanent Chicago textures), then pack again
        cands = [it for g, items in groups.items() for it in items
                 if it.src == "C" and it.shrink < MAX_SHRINK
                 and (failed == "perm" and g == "perm" or failed != "perm" and g != "perm" and g & failed)]
        if not cands:
            cands = [it for it in groups.get("perm", []) if it.src == "C" and it.shrink < MAX_SHRINK]
        if not cands:
            per = collections.Counter(a for g, items in groups.items() if g != "perm" for it in items for a in g)
            raise RuntimeError("textures cannot fit even with downscaling (%s); permanent textures %d; area textures: %s"
                               % (failed, len(groups.get("perm", [])), dict(sorted(per.items()))))
        # textures only seen from afar in the failing areas go first (largest
        # first), then those seen up close
        fail_areas = failed if failed != "perm" else frozenset()
        # (only textures that stay at least 16 pixels on the halved side)
        import polish_tex                     # CHI_POLISH_TEX=cost: halve by visual loss (Polish, C7)
        (polish_tex.pick_height(cands, fail_areas) if polish_tex.HEIGHT else
         polish_tex.pick(cands, fail_areas) if polish_tex.COST else
         max(cands, key=lambda it: (not (it.near & fail_areas) and max(it.w, it.h) >= 32,
                                    it.w * it.h))).halve()
        shrunk += 1
    if model_areas is None:
        packed = {g: pack_group(items, g) for g, items in groups.items()}
    while model_areas is None:
        nperm = len(packed.get("perm", []))
        load = collections.Counter()
        for g, pps in packed.items():
            if g != "perm":
                for a in g:
                    load[a] += len(pps)
        over = [(nperm + n - budget, a) for a, n in load.items() if nperm + n > budget]
        if not over:
            break
        _, area = max(over)
        # shrink the largest texture among this area's own groups, then repack them
        cands = [(it.w * it.h, id(it), it, g) for g, items in groups.items()
                 if g != "perm" and area in g for it in items if it.shrink < MAX_SHRINK]
        if not cands:
            need = sum(it.w * it.h for g, items in groups.items() if g != "perm" and area in g for it in items) / 65536.0
            permpx = sum(it.w * it.h for it in groups.get("perm", [])) / 65536.0
            allpx = sum(it.w * it.h for g, items in groups.items() for it in items) / 65536.0
            print("area %d needs %.1f pages of area textures; permanent textures %.1f pages; all textures %.1f pages; %d groups" % (area, need, permpx, allpx, len(groups)))
            mine = sorted(((len(pps), sorted(g)) for g, pps in packed.items() if g != "perm" and area in g), reverse=True)
            raise RuntimeError("area %d cannot fit even with downscaling: %d permanent pages + %d area pages > %d; "
                               "groups (pages, areas): %s" % (area, nperm, load[area], budget, mine[:12]))
        _, _, it, g = max(cands, key=lambda c: (c[0], -len(c[3])))
        it.halve()
        shrunk += 1
        packed[g] = pack_group(groups[g], g)

    special = []
    p = 0
    for page, size in bti.permanent:
        p += (size + 2047) // 2048 * 2048
    for page, size in bti.special:
        special.append((page, bytes(base_lev.tpages[p: p + size])))
        p += (size + 2047) // 2048 * 2048
    reserved = set()    # special pages are renumbered after the repacked ones by the caller

    pages, details, flags, remap = {}, {}, {}, {}
    area_pages = collections.defaultdict(list)
    permanent = []
    next_index = 0

    def take_index():
        nonlocal next_index
        while next_index in reserved:
            next_index += 1
        idx = next_index
        next_index += 1
        return idx

    report_fixed = []
    clut_saved = 0
    order = ["perm"] + sorted((g for g in packed if g != "perm"), key=lambda g: sorted(g))
    for g in order:
        for pp in packed[g]:
            idx = take_index()
            page = Page()
            dets = []
            k = -1
            shared_at = {}
            for it, x, y in sorted(pp.items, key=lambda e: (not getattr(e[0], "palette", False),
                                                            not getattr(e[0], "carfirst", False), e[2], e[1])):
                page.blit(x, y, it.rows)
                if getattr(it, "pixels_only", False):     # C42 r3 (b): damage twin, drawn through its clean texture
                    continue
                if (g == "perm" and CLUT_SHARE and it.src == "C" and not it.name.startswith(b"_")
                        and not getattr(it, "palette", False) and not getattr(it, "carfirst", False)
                        and getattr(it, "twin", None) is None and it.clut in shared_at):
                    # S1 CLUT sharing: a polygon takes its CLUT from (page, detail) and its UVs from itself, so a
                    # Chicago texture with the same 16 colours as an earlier one on this page reuses that detail
                    remap[(it.src, it.page, it.detail)] = (idx, shared_at[it.clut], x, y, it.x, it.y, it.ow, it.oh, it.w, it.h)
                    clut_saved += 1
                    continue
                k += 1
                page.cluts.append(it.clut)
                dets.append((it.ident, it.name, x, y, it.w, it.h))
                remap[(it.src, it.page, it.detail)] = (idx, k, x, y, it.x, it.y, it.ow, it.oh, it.w, it.h)
                if it.src == "C" and not it.name.startswith(b"_"):
                    shared_at.setdefault(it.clut, k)
            pages[idx], details[idx] = page, dets
            if g == "perm":
                flags[idx] = 1
                permanent.append(idx)
            else:
                flags[idx] = 2
                for a in g:
                    area_pages[a].append(idx)
        if g == "perm" and fixed:             # whole car pages (polish_cars.fixed_pages), content and layout kept
            from texpages import read_pages
            _fti, fpages = read_pages(base_lev)
            fnames = base_lev.loadtime.get(5).data
            for fp in fixed:
                idx = take_index()
                src_pg = fpages[fp]
                page = Page()
                page.texels[:] = src_pg.texels
                page.cluts = list(src_pg.cluts)
                dets = []
                for k, d in enumerate(bti.details[fp]):
                    w, h = d[4] or 256, d[5] or 256
                    dets.append((d[0], fnames[d[1]: fnames.index(b"\0", d[1])], d[2], d[3], w, h))
                    remap[(fsrc, fp, k)] = (idx, k, d[2], d[3], d[2], d[3], w, h, w, h)
                pages[idx], details[idx] = page, dets
                flags[idx] = 1
                permanent.append(idx)
                report_fixed.append("%d->%d (%d textures)" % (fp, idx, len(dets)))

    if short_items:
        idx = take_index()
        page = Page(); dets = []
        for k, (it, x, y) in enumerate(short_items):
            page.blit(x, y, it.rows); page.cluts.append(it.clut)
            dets.append((it.ident, it.name, x, y, it.w, it.h))
            remap[(it.src, it.page, it.detail)] = (idx, k, x, y, it.x, it.y, it.ow, it.oh, it.w, it.h)
        pages[idx], details[idx] = page, dets
        flags[idx] = 1 | 0x80                 # Infrastructure: loaded into slot 15 (960,256), 64 x 170
        permanent.append(idx)
        report_fixed.append("short slot-15 page %d (%d textures)" % (idx, len(short_items)))

    area_page_content = {}
    for pg in (area_packed or []):
        idx = take_index()
        pg["idx"] = idx
        flags[idx] = 2
        dets = {}
        for it, S, d, x, y in pg["items"]:
            dets.setdefault(d, (it.ident, it.name, x, y, it.w, it.h))
            remap[(it.src, it.page, it.detail)] = (idx, d, x, y, it.x, it.y, it.ow, it.oh, it.w, it.h)
        ndet = max(dets) + 1
        details[idx] = [dets.get(d, (0, b"_UNUSED", 0, 0, 1, 1)) for d in range(ndet)]
        for a in sorted(pg["areas"]):
            page = Page()
            page.cluts = [bytes(32)] * ndet
            for it, S, d, x, y in pg["items"]:
                if a in S:
                    page.blit(x, y, it.rows)
                    page.cluts[d] = it.clut
            area_page_content[(a, idx)] = page
            area_pages[a].append(idx)
        pages[idx] = area_page_content[(min(pg["areas"]), idx)]

    remap_area = {}
    PLACE_STATS.clear(); PLACE_STATS.update(placements=0, halved=0, lost=0)
    if S1_LOCAL:                              # Polish S1: every area packs its own local textures
        import polish_s1, hashlib, numpy as np, polish_tex
        remap.update(polish_s1.assign_virtual(S1_LOCAL))
        B0 = SLOTS - CLUT_SLOT_COST - SPECIAL_LOADED
        local_idx, s1_halved, s1_halvings, s1_new = [], set(), 0, {}

        def pick(cands, a):          # largest current copy first (spreads the halvings), high / far-only weighted up
            return max(cands, key=lambda c: (not polish_tex.protected(c.it),
                                             c.w * c.h * (1.5 if getattr(c.it, "height", 0) >= polish_tex.HIGH_FROM else 1.0)
                                             * (1.5 if a not in c.it.near else 1.0)))
        for a in sorted({x for it in S1_LOCAL for x in it.s1_areas}):
            uniq = {}
            for it in S1_LOCAL:
                if a in it.s1_areas:
                    k = hashlib.md5(b"".join(bytes(r) for r in it.rows) + it.clut + b"%d,%d,%d" % (it.w, it.h, it.shrink)).hexdigest()
                    uniq.setdefault(k, []).append(it)
            copies = []
            for v in uniq.values():
                c = polish_s1._Copy(v[0]); c.aliases = v; copies.append(c)
            base_pages = [(pg["idx"], pg["occ"][a], pg["cluts"][a]) for pg in (area_packed or []) if a in pg["areas"]]
            cap_new = B0 - len([i for i in permanent if not flags.get(i, 0) & 0x80]) - len(area_pages[a])
            place, nnew, nh = polish_s1.pack_area(a, copies, base_pages, cap_new, _free_spot, PAGE, MAX_CLUTS, np, pick)
            s1_halvings += nh; s1_new[a] = nnew
            for c in copies:
                n_al = len(c.aliases)
                PLACE_STATS["placements"] += n_al
                if c.shrink:
                    PLACE_STATS["halved"] += n_al
                    PLACE_STATS["lost"] += (c.it.ow * c.it.oh - c.w * c.h) * n_al
            while len(local_idx) < nnew:
                i_ = take_index(); local_idx.append(i_); flags[i_] = 2
            rm = remap_area.setdefault(a, {})
            for c, (ref, d, x, y) in place.items():
                idx = ref[1] if ref[0] == "g" else local_idx[ref[1]]
                page = area_page_content.get((a, idx))
                if page is None:
                    page = Page(); page.cluts = []; area_page_content[(a, idx)] = page
                    area_pages[a].append(idx)
                while len(page.cluts) <= d:
                    page.cluts.append(bytes(32))
                page.blit(x, y, c.rows); page.cluts[d] = c.it.clut
                dl = details.setdefault(idx, [])
                while len(dl) <= d:
                    dl.append((0, b"_UNUSED", 0, 0, 1, 1))
                if dl[d][1] == b"_UNUSED":
                    dl[d] = (c.it.ident, c.it.name, x, y, c.w, c.h)
                if c.shrink:
                    s1_halved.add((c.it.src, c.it.page, c.it.detail))
                for it in c.aliases:
                    vp, vd = it.vkey
                    rm[("X", vp, vd)] = (idx, d, x, y, it.x, it.y, it.ow, it.oh, c.w, c.h)
        for i_ in local_idx:
            pages[i_] = next(v for (a_, j), v in area_page_content.items() if j == i_)
        print("S1 per-area packing: %d local textures, %d halved in some area (%d area-halvings), new pages per area %s"
              % (len(S1_LOCAL), len(s1_halved), s1_halvings, s1_new))

    report = []
    for g, its in groups.items():                       # global placements (area sets; permanent = every area)
        n_g = 16 if g == "perm" else len(g)
        for it in its:
            if it.src != "C":
                continue
            PLACE_STATS["placements"] += n_g
            if it.shrink:
                PLACE_STATS["halved"] += n_g
                PLACE_STATS["lost"] += (it.ow * it.oh - it.w * it.h) * n_g
    report.append("texture placements (" + __import__("cityprofile").P.label + ", per area): %d, halved %d (%.1f %%), texels lost %.1f page-area units"
                  % (PLACE_STATS["placements"], PLACE_STATS["halved"], 100.0 * PLACE_STATS["halved"] / max(1, PLACE_STATS["placements"]),
                     PLACE_STATS["lost"] / 65536.0))
    if CLUT_SHARE:
        report.append("CLUT sharing on permanent pages (CHI_POLISH_CLUTSHARE): %d palettes saved" % clut_saved)
    nperm = len([i for i in permanent if not flags.get(i, 0) & 0x80])   # (the short slot-15 page has its own slot)
    report.append("downscaled textures: %d (%s)" % (shrunk, ", ".join(
        "%s %dx%d->%dx%d" % (it.name.decode("latin-1"), it.ow, it.oh, it.w, it.h)
        for items in groups.values() for it in items if it.shrink)))
    if report_fixed:
        report.append("car pages kept whole (CHI_POLISH_CARPAGES): " + ", ".join(report_fixed))
    report.append("permanent pages: %d (groups: %s)" % (nperm, {("perm" if g == "perm" else tuple(sorted(g))): len(v) for g, v in packed.items()}))
    budget += len(fixed)                      # (the fixed car pages are in nperm)
    for a in sorted(area_pages):
        total = nperm + len(area_pages[a])
        report.append("area %2d: %d own pages -> %d resident of %d %s" % (
            a, len(area_pages[a]), total, budget, "OK" if total <= budget else "OVER by %d" % (total - budget)))
    res = RepackResult(pages, details, flags, permanent, special, dict(area_pages), remap, report, area_page_content)
    res.remap_area = remap_area
    if "keep_carpages" not in __import__("os").environ.get("CHI_EXPERIMENT", "").split(","):
        renumber_permanent(res)
    return res


# Driver 1's car texture setup (0x8003BDC8, store 0x8003C218) writes one palette word per car
# polygon to 0x800BEA04 + 600 * (page - 5) + 20 * texture: the car models' city textures must sit
# on pages >= CAR_PAGE_BASE (LA: 5 and 6). Ours (permanent pages 0-2) wrote below that buffer,
# into the texture page count table (0x800BE2F8), and every texture looked up by name on a page
# >= 1 got a garbage sprite record (dark-square halos / brake lights). The permanent pages swap
# indices with the pages at CAR_PAGE_BASE.. (Infrastructure 2026-10-13).
CAR_PAGE_BASE = 5


def renumber_permanent(res: RepackResult):
    perm = sorted(res.permanent)
    total = len(res.pages)
    if not perm or perm[0] >= CAR_PAGE_BASE or CAR_PAGE_BASE + len(perm) > total:
        return
    m = {}
    for i, pg in enumerate(perm):
        t = CAR_PAGE_BASE + i
        if pg != t:
            m[pg], m[t] = t, pg
    f = lambda i: m.get(i, i)
    res.pages = {f(i): v for i, v in res.pages.items()}
    res.details = {f(i): v for i, v in res.details.items()}
    res.flags = {f(i): v for i, v in res.flags.items()}
    res.permanent = [f(i) for i in res.permanent]
    res.area_pages = {a: [f(i) for i in v] for a, v in res.area_pages.items()}
    res.remap = {k: (f(v[0]),) + tuple(v[1:]) for k, v in res.remap.items()}
    res.area_page_content = {(a, f(i)): v for (a, i), v in res.area_page_content.items()}
    res.remap_area = {a: {k: (f(v[0]),) + tuple(v[1:]) for k, v in rm.items()} for a, rm in getattr(res, "remap_area", {}).items()}
    res.report.append("permanent pages renumbered for the car texture setup: %s" % sorted(m.items()))


if __name__ == "__main__":
    import inputs
    chi = Lev.parse(inputs.read(DAY_LEV))
    base = Lev.parse(inputs.read("d1_LA.lev"))
    res = repack(chi, base)
    print("\n".join(res.report))
    print("total pages: %d repacked + %d special, max index %d" % (len(res.pages), len(res.special), max(list(res.pages) + [p for p, _ in res.special])))
