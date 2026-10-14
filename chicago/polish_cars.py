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

D1_FROM_D2 = {0: 3, 1: 0, 2: 1, 5: 8, 6: 9, 7: 10, 8: 12}
BASE = 4 + 13 * 12


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
            data = _model_bytes(d2_cm, off)
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
        order += [p for p in pages if p not in order]
    return order


def palettes(d2_pal: bytes, keep_pages: set, remap, extra=()):
    """Driver 1 lump 25 from Driver 2's; remap(tpage, texnum) -> (new page, new texnum) or None.
    extra: further Driver 1 entries (44 bytes each) appended, e.g. the base city's pedestrian palettes."""
    n = struct.unpack_from("<i", d2_pal, 0)[0]
    p = 4
    cluts = []
    out = []
    for _ in range(n):
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
    return struct.pack("<i", len(out)) + b"".join(out)          # Driver 1: count + count x 44 bytes, no terminator


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
            it.twin = tw
            n += 1
    return n


def pack_twins(items, group, plain_pack, free_spot, max_cluts, page_size=256):
    """pack_group for the permanent group with twin items: pairs first into twin pages (clean in
    the left half at x, twin at x + 128), then the other textures first-fit into the free space of
    those pages, the rest by the normal packer (plain_pack)."""
    import numpy as np
    from texrepack import PackedPage
    half = page_size // 2
    pairs = sorted((it for it in items if getattr(it, "twin", None) is not None), key=lambda it: (-it.h, -it.w))
    rest = sorted((it for it in items if getattr(it, "twin", None) is None), key=lambda it: (-it.h, -it.w))
    pages = []          # (PackedPage, occupancy)
    for it in pairs:
        for slot in pages + [None]:
            if slot is None:
                slot = (PackedPage(group), np.zeros((page_size, page_size), dtype=bool))
                pages.append(slot)
            pp, occ = slot
            if len(pp.items) + 2 > max_cluts:
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
            break
    left = []
    for it in rest:
        for pp, occ in pages:
            if len(pp.items) >= max_cluts:
                continue
            pos = free_spot(occ, it.w, it.h)
            if pos is not None:
                x, y = pos
                pp.items.append((it, x, y))
                occ[y:y + it.h, x:x + it.w] = True
                break
        else:
            left.append(it)
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
    slots = [m.get(s) for s in (0, 1, 2)] if mapped else [0, 1, 2]
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


def damage_tables(den: bytes) -> dict:
    """Driver 1 rows for the mapped Driver 2 cars: {"civ_verts", "player_verts", "civ_polys",
    "player_polys", "civ_levels", "player_levels"} as bytes (rows concatenated)."""
    offs = struct.unpack_from("<13i", den, 0)
    m = slot_map()

    def row(d2, start, size):
        if d2 is None or offs[d2] <= 0:
            return b"\xff" + bytes(size - 1)
        o = offs[d2] + start
        return (den[o: o + size] + bytes(size))[:size]

    out = {}
    for name, slots in (("civ", (0, 1, 2)), ("player", (5, 6, 7, 8))):
        out[name + "_verts"] = b"".join(row(m.get(s), 0, DEN_VERTS) for s in slots)
        out[name + "_polys"] = b"".join(row(m.get(s), DEN_VERTS, DEN_POLYS) for s in slots)
        out[name + "_levels"] = b"".join(row(m.get(s), DEN_VERTS + DEN_POLYS, DEN_LEVELS) for s in slots)
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
