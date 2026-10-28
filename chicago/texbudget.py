"""texbudget.py — how many texture pages each area really needs (Chicago + LA engine)."""
import sys, struct, collections
from levfile import Lev
from models import inmem_models, area_models, model_names, POLY_SIZES, Model
from mapinfo import SpoolInfo, SPOOLINFO
from textures import TexInfo

TEXTURED = {4, 5, 7, 9, 10, 11, 17, 20, 21, 22, 23}


def model_texrefs(m, allm):
    out = set()
    src = allm.get(m.instance_number) if m.instance_number >= 0 else m
    if not src or src.poly_block >= len(src.data):
        return out
    q = src.poly_block
    for _ in range(src.num_polys):
        t = src.data[q] & 31
        if t in TEXTURED and src.data[q + 1] != 0xFF:
            out.add((src.data[q + 1], src.data[q + 2]))
        q += POLY_SIZES[t]
    return out


def valid(ti, t):
    return t[0] < ti.num_pages and t[1] < len(ti.details[t[0]])


def rect_texels(ti, t):
    if not valid(ti, t):
        return 0
    det = ti.details[t[0]]
    if t[1] >= len(det):
        return 0
    d = det[t[1]]
    return (d[4] or 256) * (d[5] or 256)


if __name__ == "__main__":
    import inputs
    lev = Lev.parse(inputs.read("d2_CHICAGO.LEV"))
    ti = TexInfo.parse(lev.loadtime.get(34).data)
    sp = SpoolInfo.parse(lev.inmem.get(SPOOLINFO).data)
    mem, _ = inmem_models(lev)
    allm = {**area_models(lev), **mem}
    used = set().union(*(model_texrefs(m, allm) for m in allm.values()))
    bad = {t for t in used if not valid(ti, t)}
    print("texture refs past a page's detail list:", len(bad), sorted(bad)[:10])
    perm = [p for p, _ in ti.permanent]
    P = sum(rect_texels(ti, t) for t in used if t[0] in perm) / 65536
    print("permanent: %d pages hold %.2f pages of used texels" % (len(perm), P))
    worst = 0
    for a in sorted({s[7] for s in sp.spools.values()} - {255}):
        pages = [p for p in sp.area_tpages[a] if p != 0xFF]
        A = sum(rect_texels(ti, t) for t in used if t[0] in pages) / 65536
        worst = max(worst, A + P)
        print("area %2d: %d pages hold %.2f used -> resident %.2f" % (a, len(pages), A, A + P))
    print("worst resident Chicago world: %.2f pages" % worst)
