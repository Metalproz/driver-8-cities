"""polish_pages.py - stable shared texture pages for area switches (Polish, C45).

Switch CHI_POLISH_SHAREDPAGES=1 (default off = texrepack's per-area page contents only).

Driver 1 streams every page an area lists on each area switch (0x80033B10) and the game may not
enter the new area before they are in. With per-area page contents (CHI_PER_AREA=1) a page index
holds different textures in different areas, so nothing can be skipped. This module takes, before
the per-area packing, every group of textures needed by exactly the same set of 2+ areas and packs
it into whole pages of its own ("stable" pages): one page index per content, listed by exactly that
set of areas, identical bytes in every area's gfx block. Only nearly full pages are kept (a stable
page costs a slot in every area of its set; the rest of the group goes to the per-area packer as
before). Infrastructure's skip-resident patch may skip a stable page that is still resident; the
per-area pages keep their shared indices and are always re-read.

Rule for the engine: stable pages are the area pages whose index is in the level's stable list
(written next to the LEV as <lev>.stable.json and printed by convert.py as "stable pages: ...").
"""
from __future__ import annotations

import collections
import os

FILL = float(os.environ.get("CHI_POLISH_SHAREDPAGES_FILL", "0.85"))    # keep pages filled at least this much
CAP = int(os.environ.get("CHI_POLISH_SHAREDPAGES_CAP", "2"))           # stable pages per area at most


def enabled():
    return os.environ.get("CHI_POLISH_SHAREDPAGES", "") == "1"


def extract(groups: dict):
    """-> ({area set: [PackedPage]}, Counter {area: stable pages listed}); removes the packed
    textures from `groups` (in place)."""
    if not enabled():
        return {}, None
    import texrepack
    stable, load = {}, collections.Counter()
    # widest sets first: a page every area lists is re-read on every switch, so it saves the most
    for g in sorted((g for g in groups if g != "perm" and len(g) >= 2), key=lambda g: (-len(g), sorted(g))):
        items = groups[g]
        if sum(it.w * it.h for it in items) < FILL * texrepack.PAGE * texrepack.PAGE:
            continue
        pages = texrepack.pack_group(items, g)
        keep = [pp for pp in pages
                if len(pp.items) >= texrepack.MAX_CLUTS
                or sum(it.w * it.h for it, _x, _y in pp.items) >= FILL * texrepack.PAGE * texrepack.PAGE]
        room = min(CAP - load[a] for a in g)
        keep = keep[:max(room, 0)]
        if not keep:
            continue
        used = {id(it) for pp in keep for it, _x, _y in pp.items}
        groups[g] = [it for it in items if id(it) not in used]
        stable[g] = keep
        for a in g:
            load[a] += len(keep)
    return stable, load


def stable_indices(res) -> list:
    """Page indices of the stable pages in a RepackResult (area pages without per-area content)."""
    per_area = {idx for (_a, idx) in res.area_page_content}
    return sorted(i for i in res.pages if res.flags.get(i) == 2 and i not in per_area)
