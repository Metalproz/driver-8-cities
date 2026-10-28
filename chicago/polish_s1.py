"""polish_s1.py - optimisation step S1: per-area texture packing (Polish, 20.10., CHI_POLISH_S1=1).

Measured (texrepack CHI_POLISH_PACKSTAT): every Chicago area needs 101-175 % of its 9 free texture pages; today
every area texture keeps ONE spot (page, x, y, CLUT) in all areas that use it, so an area's pages are only
partly used by that area and 654 textures end up halved.

Area models are streamed per area (each area block holds its own copy of the model data), so a texture used only
by such models can sit at a different spot in every area:
  * "global" textures (used by in-memory models, ground tiles with SUBDIVISION UVs, specials, generated
    models, permanent) are packed as before;
  * "local" textures get a virtual (page, detail) in the converted models (UVs unchanged), and after packing
    every area packs its own local set into its free space (global pages' free spots + its own extra pages);
    each area halves its own copies when they do not fit (largest / far-only first, like polish_tex);
  * convert.build_spooled rewrites each area's model copies from the virtual spots to that area's spots
    (remap_area), exact duplicates (same pixels + CLUT + size) share one placement per area.
No engine change: per-vertex UVs, per-area page contents (existing mechanism)."""
from __future__ import annotations

import collections
import hashlib
import os

ENABLED = os.environ.get("CHI_POLISH_S1", "") == "1"
PIN_MODELS = set()          # models seen from boundary regions (carried across a switch): one spot in all areas
AREA_MODELS = {}            # set by convert: area -> ids of the models streamed in it
VPAGE0 = 128                # virtual pages for local textures (never written)
FILL_TRIES = 3


def classify(call: dict, cmem: dict, refs_of, extra_refs: set, forced: set):
    """(local textures {(page, det)}, areas per local texture). call: all Chicago models."""
    model_of = collections.defaultdict(set)
    for i, m in call.items():
        for t in refs_of(m):
            model_of[t].add(i)
    in_area = collections.defaultdict(set)
    for a, ids in AREA_MODELS.items():
        for i in ids:
            in_area[i].add(a)
    local, areas = set(), {}
    for t, ms in model_of.items():
        if t in extra_refs or t in forced:
            continue
        if any(i in cmem or (call[i].shape_flags & 0x2400) or i in PIN_MODELS for i in ms):
            continue
        s = set()
        for i in ms:
            s |= in_area.get(i, set())
        if s:
            local.add(t)
            areas[t] = frozenset(s)
    return local, areas


def assign_virtual(local_items):
    """(src, page, det) -> virtual (vpage, vdet, x, y, x, y, w, h, w, h): identity UVs."""
    rm, vp, vd = {}, VPAGE0, 0
    for it in local_items:
        if vd >= 250:
            vp, vd = vp + 1, 0
        it.vkey = (vp, vd)
        rm[(it.src, it.page, it.detail)] = (vp, vd, it.x, it.y, it.x, it.y, it.ow, it.oh, it.ow, it.oh)
        vd += 1
    return rm


class _Copy:
    """One area's copy of a local texture (halved independently)."""
    def __init__(self, it):
        self.it, self.rows, self.w, self.h, self.shrink = it, it.rows, it.w, it.h, it.shrink

    def halve(self):
        if self.w >= self.h and self.w > 1:
            self.rows = [r[::2] for r in self.rows]; self.w = len(self.rows[0])
        elif self.h > 1:
            self.rows = self.rows[::2]; self.h = len(self.rows)
        self.shrink += 1


def pack_area(a, copies, base_pages, cap_new, free_spot, PAGE, MAX_CLUTS, np, pick):
    """Place one area's local copies: first into the free space of the pages the area already lists
    (base_pages: [(idx, occ bool map, used clut set)]), then into up to cap_new new pages.
    Halves copies (pick) until everything fits. Returns ({copy: (page_ref, d, x, y)}, new page count, halvings)."""
    halvings = 0
    avail = sum(PAGE * PAGE - int(occ.sum()) for _i, occ, _c in base_pages) + cap_new * PAGE * PAGE
    target = 0.93 * avail
    while True:
        total = sum(c.w * c.h for c in copies)
        while total > target:
            cand = [c for c in copies if c.shrink < 3 and max(c.w, c.h) >= 16]
            if not cand:
                break
            c = pick(cand, a); before = c.w * c.h; c.halve(); halvings += 1; total -= before - c.w * c.h
        place, new = {}, []
        pages = [(("g", idx), occ.copy(), set(cl)) for idx, occ, cl in base_pages]
        ok = True
        for c in sorted(copies, key=lambda c: -(c.w * c.h)):
            spot = None
            for ref, occ, cl in pages:
                d = next((d for d in range(MAX_CLUTS) if d not in cl), None)
                if d is None:
                    continue
                pos = free_spot(occ, c.w, c.h)
                if pos is not None:
                    spot = (ref, occ, cl, d, pos); break
            if spot is None:
                if len(new) >= cap_new:
                    ok = False; break
                ref = ("l", len(new)); occ = np.zeros((PAGE, PAGE), dtype=bool); cl = set()
                pages.append((ref, occ, cl)); new.append(ref)
                pos = free_spot(occ, c.w, c.h)
                if pos is None:
                    ok = False; break
                spot = (ref, occ, cl, 0, pos)
            ref, occ, cl, d, (x, y) = spot
            occ[y:y + c.h, x:x + c.w] = True; cl.add(d)
            place[c] = (ref, d, x, y)
        if ok:
            return place, len(new), halvings
        if not [c for c in copies if c.shrink < 3 and max(c.w, c.h) >= 16]:
            raise RuntimeError("S1: area %d local textures cannot fit: %d copies, %d texels now, base pages %d (free %d texels), new pages %d"
                               % (a, len(copies), sum(c.w * c.h for c in copies), len(base_pages),
                                  sum(PAGE * PAGE - int(o.sum()) for _i, o, _c in base_pages), cap_new))
        target = 0.97 * sum(c.w * c.h for c in copies)
