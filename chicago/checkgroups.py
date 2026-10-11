"""checkgroups.py — walk every model's polygon group table like Driver 1's
renderer does (see d1models.py) and report models it would misdraw.

usage: python checkgroups.py LEV [LEV ...]
"""
from __future__ import annotations

import collections
import struct
import sys

from levfile import Lev
from models import inmem_models, area_models, POLY_SIZES


def walk(m, table_model):
    """Problems found walking m's polygons with table_model's group table."""
    d, a3 = table_model.data, table_model.point_normals
    if a3 + 4 > len(d):
        return ["table offset outside the model"]
    h = struct.unpack_from("<I", d, a3)[0]
    ng, matbytes = h & 0xFF, h >> 16
    if matbytes < 24 * ((ng + 2) // 3):
        return ["%d groups but only %d matrix bytes" % (ng, matbytes)]
    a2, q, seen = a3 + 4 + matbytes, m.poly_block, 0
    for g in range(ng):
        if a2 + 4 > len(d):
            return ["group %d entry outside the model" % g]
        t1 = struct.unpack_from("<I", d, a2)[0]
        cnt, subbytes, nbytes = t1 & 0xFF, (t1 >> 8) & 0xFF, (t1 >> 16) & 0x3FF
        a2 += 4 + subbytes
        start = q
        for _ in range(cnt):
            if q >= len(m.data):
                return ["group %d runs past the polygon data" % g]
            t = m.data[q] & 31
            if t not in POLY_SIZES:
                return ["group %d: bad polygon type %d" % (g, t)]
            q += POLY_SIZES[t]
        if q - start != nbytes:
            return ["group %d: %d polygon bytes, table says %d" % (g, q - start, nbytes)]
        seen += cnt
    if seen != m.num_polys:
        return ["groups cover %d of %d polygons" % (seen, m.num_polys)]
    return []


def check(path):
    lev = Lev.parse(open(path, "rb").read())
    mem, _ = inmem_models(lev)
    allm = {**area_models(lev), **mem}
    bad, kinds = {}, collections.Counter()
    for i, m in sorted(allm.items()):
        if m.num_polys == 0:
            continue
        src = allm.get(m.instance_number, m) if m.instance_number >= 0 else m
        if src.point_normals == src.poly_block:
            kinds["no table"] += 1
            continue
        probs = walk(m, src)
        kinds["bad" if probs else "ok"] += 1
        if probs:
            bad[i] = probs
    print("%s: %s" % (path, dict(kinds)))
    for i, probs in list(bad.items())[:10]:
        print("   model %d: %s" % (i, "; ".join(probs)))
    return not bad


if __name__ == "__main__":
    ok = all([check(p) for p in sys.argv[1:]])
    sys.exit(0 if ok else 1)
