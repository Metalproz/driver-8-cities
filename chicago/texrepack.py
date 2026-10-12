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
PER_AREA_CONTENT = __import__("os").environ.get("CHI_PER_AREA", "1") == "1"

# texture names the Driver 1 EXE looks up (strings in SLUS_008.42)
EXE_TEXTURE_NAMES = set("""FOREARM1 FRAMEADV CHOOSECA LIGHTREF CARSHAD BLIMP SMOKE DEBRIS LITTER
SUN2 SKID FLARE1 SPLASH SWBIRD1 SWBIRD2 SKYSUN DROP DIGIT COLLON JEANS1 ARM1 CHEST1 LOWHEAD
ADDCAM AUTO CHASEC CLOCK DELCAM EDITCAM FIXEDCA INCAR LENSCHA LOOKCAR MOVECMP MOVECAM PAUSE
PLAYCAM PLAYPAU SAVE2CA RESTREP SEA""".split())
# + per-city event models the loader requires for the replaced slot (LA: BOEING, table @0x80089E84)
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
WATER_TEXTURE = (b"LASEA", "work/d1_MIAMI.lev", b"SEA")   # LA's 16x16 sea -> Miami's 64x64 (calmer, darker)


def water_from_miami(items):
    """Give the water tile Miami's sea texture: the item keeps LA's source rectangle
    (UVs are remapped from it); pixels, palette, size and name (SEA) change."""
    import os
    if not WATER_TEXTURE or "la_water" in os.environ.get("CHI_EXPERIMENT", ""):
        return
    old_name, path, new_name = WATER_TEXTURE
    it = next((i for i in items if i.src == "B" and i.name == old_name), None)
    if it is None or not os.path.exists(path):
        return
    lev = Lev.parse(open(path, "rb").read())
    ti, pages = read_pages(lev)
    names = lev.loadtime.get(5).data
    for p, dl in enumerate(ti.details):
        for k, (ident, noff, x, y, w, h) in enumerate(dl):
            if p in pages and names[noff: names.index(b"\0", noff)] == new_name:
                it.rows, it.w, it.h = pages[p].rect(x, y, w, h), w, h
                it.clut = pages[p].cluts[k]
                # the engine finds the sea by name (GetTextureInfo("SEA"), 0x8004219C) and
                # draws water near the camera with that page/palette: LA has no "SEA",
                # so it used a stale palette (pink water around a sinking car)
                it.name = b"SEA"
                return


def collect(chicago: Lev, base: Lev, model_areas=None, model_near=None):
    """Gather used textures from both levels, keyed by group."""
    cti, cpages = read_pages(chicago)
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
        it = Item(src, t[0], t[1], name_at(names, noff), x, y, w, h, clut, pg.rect(x, y, w, h), ident)
        it.ow, it.oh = w, h
        return it

    for t in sorted(bused):
        groups["perm"].append(make("B", bti, bpages, bnames, t))
    water_from_miami(groups["perm"])
    for t in sorted(cused):
        it = make("C", cti, cpages, cnames, t)
        it.near = frozenset(tex_near.get(t, ()))
        if it.name.decode("latin-1") in EXE_TEXTURE_NAMES:
            it.name = b"_" + it.name[1:]          # the base city's version must win lookups
        if t in forced:                       # generated models (shore walls): the areas they are seen in
            tex_areas[t] |= FORCED_AREAS      # (forcing it permanent added a page: wrong area textures, C29)
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
    return groups, bti, base, csp


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


def pack_per_area(groups: dict, budget: int):
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
    lists = collections.Counter()
    for it, S in items:
        best = None
        for pg in pages:
            new = S - pg["areas"]
            if any(lists[a] + 1 > cap for a in new):
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
            if any(lists[a] + 1 > cap for a in S):
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


def repack(chicago: Lev, base: Lev, model_areas=None, model_near=None) -> RepackResult:
    groups, bti, base_lev, csp = collect(chicago, base, model_areas, model_near)
    budget = SLOTS - CLUT_SLOT_COST - SPECIAL_LOADED
    shrunk = 0
    area_packed = None
    while model_areas is not None:
        if PER_AREA_CONTENT:
            perm_pages, area_packed, failed = pack_per_area(groups, budget)
            if area_packed is not None:
                packed = {"perm": perm_pages}
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
        max(cands, key=lambda it: (not (it.near & fail_areas) and max(it.w, it.h) >= 32,
                                   it.w * it.h)).halve()
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

    order = ["perm"] + sorted((g for g in packed if g != "perm"), key=lambda g: sorted(g))
    for g in order:
        for pp in packed[g]:
            idx = take_index()
            page = Page()
            dets = []
            for k, (it, x, y) in enumerate(sorted(pp.items, key=lambda e: (e[2], e[1]))):
                page.blit(x, y, it.rows)
                page.cluts.append(it.clut)
                dets.append((it.ident, it.name, x, y, it.w, it.h))
                remap[(it.src, it.page, it.detail)] = (idx, k, x, y, it.x, it.y, it.ow, it.oh, it.w, it.h)
            pages[idx], details[idx] = page, dets
            if g == "perm":
                flags[idx] = 1
                permanent.append(idx)
            else:
                flags[idx] = 2
                for a in g:
                    area_pages[a].append(idx)

    area_page_content = {}
    for pg in (area_packed or []):
        idx = take_index()
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

    report = []
    nperm = len(permanent)
    report.append("downscaled textures: %d (%s)" % (shrunk, ", ".join(
        "%s %dx%d->%dx%d" % (it.name.decode("latin-1"), it.ow, it.oh, it.w, it.h)
        for items in groups.values() for it in items if it.shrink)))
    report.append("permanent pages: %d (groups: %s)" % (nperm, {("perm" if g == "perm" else tuple(sorted(g))): len(v) for g, v in packed.items()}))
    for a in sorted(area_pages):
        total = nperm + len(area_pages[a])
        report.append("area %2d: %d own pages -> %d resident of %d %s" % (
            a, len(area_pages[a]), total, budget, "OK" if total <= budget else "OVER by %d" % (total - budget)))
    return RepackResult(pages, details, flags, permanent, special, dict(area_pages), remap, report, area_page_content)


if __name__ == "__main__":
    chi = Lev.parse(open("work/d2_CHICAGO.LEV", "rb").read())
    base = Lev.parse(open("work/d1_LA.lev", "rb").read())
    res = repack(chi, base)
    print("\n".join(res.report))
    print("total pages: %d repacked + %d special, max index %d" % (len(res.pages), len(res.special), max(list(res.pages) + [p for p, _ in res.special])))
