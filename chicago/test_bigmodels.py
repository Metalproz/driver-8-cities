"""test_bigmodels.py — build a Miami LEV that uses model indices past 800.

Copies in-memory models to new indices (653..), the most-placed ones above
800, and points every placed object at its copy. If the relocated model table
(exe_patches.py) is complete, the city looks and plays exactly like Miami.

usage: test_bigmodels.py IN.lev OUT.lev [copies]
"""
from __future__ import annotations

import collections
import struct
import sys

from levfile import Lev
from models import inmem_models
from d1cells import extract, unique_objects

MODELS, MODELNAMES, LOWDETAILTABLE, MAP = 1, 12, 21, 2


def build(src: str, dst: str, copies: int = 200):
    raw = open(src, "rb").read()
    lev, hdr, sp, straddlers, regions = extract(src)
    objects, refs, _ = unique_objects(hdr, sp, straddlers, regions)
    placed = collections.Counter(o.model for o in objects.values())

    mem, count = inmem_models(lev)
    candidates = [i for i in mem if placed[i] and mem[i].instance_number < 0]
    # cheapest first, then put the most-placed copies at the highest indices
    chosen = sorted(sorted(candidates, key=lambda i: len(mem[i].data))[:copies], key=lambda i: placed[i])
    # empty (size 0) slots up to index 800, then the copies
    first = max(count, 800)
    remap = {src_i: first + k for k, src_i in enumerate(chosen)}
    new_count = first + len(chosen)

    # MODELS: append copies (in-memory, so size > 0)
    mlump = lev.inmem.get(MODELS)
    body = bytearray(mlump.data)
    struct.pack_into("<i", body, 0, new_count)
    body += struct.pack("<i", 0) * (first - count)
    for src_i in chosen:
        data = mem[src_i].data
        body += struct.pack("<i", len(data)) + data
    mlump.data = bytes(body)

    # MODELNAMES: one name per model, NUL separated
    nlump = lev.loadtime.get(MODELNAMES)
    names = nlump.data.split(b"\0")
    base_names = names[:count]
    extra = [b""] * (first - count) + [("X%03d" % k).encode() for k in range(len(chosen))]
    nlump.data = b"\0".join(base_names + extra) + b"\0" + b"\0" * (len(nlump.data) - len(b"\0".join(names)))

    # LOWDETAILTABLE: two u16 tables of num_models entries
    llump = lev.inmem.get(LOWDETAILTABLE)
    t = list(struct.unpack_from("<%dH" % (2 * count), llump.data))
    t1, t2 = t[:count], t[count:]
    for _ in range(first - count):
        t1.append(0xFFFF); t2.append(0xFFFF)
    for src_i in chosen:
        for table in (t1, t2):
            v = table[src_i]
            table.append(remap.get(v, v) if v != src_i else remap[src_i])
    llump.data = struct.pack("<%dH" % (2 * new_count), *(t1 + t2))

    # objects: straddlers in MAP, per-region objects in the spooled section
    mapl = lev.loadtime.get(MAP)
    mdata = bytearray(mapl.data)
    moved = 0
    for i in range(hdr.num_straddlers):
        typ = struct.unpack_from("<H", mdata, 48 + 16 * i + 14)[0]
        if typ in remap:
            struct.pack_into("<H", mdata, 48 + 16 * i + 14, remap[typ]); moved += 1
    mapl.data = bytes(mdata)

    spooled = bytearray(lev.spooled)
    for reg in regions:
        offset, _a, _b, _pvs, cd0, cd1, cd2, _sr, _nca, roadm, roadh = sp.spools[sp.region_offsets[reg.index]]
        start = (offset + roadm + roadh + cd1 + cd0) * 2048
        for k in range(cd2 * 2048 // 16):
            at = start + 16 * k + 14
            typ = struct.unpack_from("<H", spooled, at)[0]
            if typ in remap:
                struct.pack_into("<H", spooled, at, remap[typ]); moved += 1
    lev.spooled = bytes(spooled)

    lev.sizes = None   # recompute section layout
    out = lev.build(keep_layout=False)
    open(dst, "wb").write(out)
    above = sum(1 for i in remap.values() if i >= 800)
    print("models %d -> %d (%d copies, %d at index >= 800), objects remapped %d, file %d -> %d bytes"
          % (count, new_count, len(chosen), above, moved, len(raw), len(out)))


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 200)
