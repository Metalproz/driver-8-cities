"""d1models.py — make Driver 2 model data drawable by Driver 1's renderer.

The MODEL header is the same in both games, but Driver 1's world renderer
(0x80030980) reads the field at +0x1C (Driver 2: point normals) as a polygon
group table, and Driver 2's point normals there crash it.

Group table (decoded from the renderer and LA's models):
    u32 header   ngroups | nmat << 8 | matbytes << 16     nmat = (ngroups - 1) // 3
    matrices     ceil(ngroups / 3) x 24 bytes. Each loads the GTE light matrix
                 (3 plane normals, 4096 = 1.0) and the background colour
                 (3 plane distances). MVMVA gives one value per group; a group
                 is drawn when its value > 0 (back-face culling of whole groups).
    per group    u32 entry   count | subbytes << 8 | polybytes << 16 (10 bits)
                             | light << 26 (3 bits) | absolute << 30 | sorted << 31
                 sub-entries (subbytes / 4) x u32, the LOD thresholds:
                             s16 threshold (drawn if threshold / 2 + value > 0),
                             skip count & 0x1F, skip bytes / 4 << 16, entry bytes << 24
    light   = facing direction in 45 degree steps, added to the model's own
              rotation (absolute: used as is, for roofs and floors)
    sorted  = from this group on, polygons are depth-sorted (one per model)
The polygons must be stored in group order. Instanced models take the group
table (and vertices) from their source model at load time (0x80052434), so an
instance's polygons are put in the same order as its source's.

Ground tiles and other flat-shaded models (shape flags 0x0400 / 0x2000) are
drawn by a different path (0x80027240 ...) that takes type 21 polygons with an
explicit colour + GPU code 0x2C and no group table; both games store them the
same way, so they are kept as is (+0x1C = polygon block, as in Driver 1).
Sprite models (shape flag 0x4000: trees) are kept as is for the same reason.

Converted groups hold polygons with the same facing (normal quantised to
1/32) and get that plane, with the distance of the farthest vertex, so whole
back-facing groups are skipped like in Driver 1 (the per-frame primitive
buffer, 0x1E000 bytes at 0x800513D4, overflows without it downtown). Mixed
groups always pass (zero normal, distance 0x7FFF). Each group has one
sub-entry that always draws. Polygon types 20/21 carry an extra colour word in Driver 2
whose meaning differs in Driver 1, so they become the plain textured types 10/11.
"""
from __future__ import annotations

import math
import struct

from models import Model, POLY_SIZES, HDR_SIZE

VERT_OFF = {8: 1, 9: 1, 10: 4, 11: 4, 20: 4, 21: 4}
SHRINK = {20: 10, 21: 11}          # drop the trailing colour word
MAX_GROUP_POLYS = 255
MAX_GROUP_BYTES = 0x3FC            # 10-bit field, and the sub-entry's byte count / 4 is 8 bits
MAX_GROUPS = 255
ALWAYS = 0x7FFF                    # plane distance that always passes (with a zero normal)
NORMAL_STEPS = 32                  # normal quantisation for grouping (about 1.8 degrees)
PLANE_MARGIN = 4
TILE_FLAGS = 0x0400 | 0x2000       # drawn without a group table


SPRITE_FLAG = 0x4000               # trees: billboard + shadow, drawn by 0x8002C6DC


def is_tile(m: Model) -> bool:
    return bool(m.shape_flags & TILE_FLAGS)


def is_sprite(m: Model) -> bool:
    """Sprite models are drawn by a fixed-layout path (0x8002C6DC) that reads
    the two type-21 polygons at +0 and +0x14 of the polygon block and fixed
    vertices, as stored by both games; they must not be regrouped or shrunk."""
    return bool(m.shape_flags & SPRITE_FLAG)


def split_polys(m: Model):
    out, q = [], m.poly_block
    for _ in range(m.num_polys):
        t = m.data[q] & 31
        size = POLY_SIZES[t]
        rec = m.data[q: q + size]
        if t in SHRINK:
            rec = bytes([(rec[0] & 0xE0) | SHRINK[t]]) + rec[1: POLY_SIZES[SHRINK[t]]]
        out.append(rec)
        q += size
    return out


def poly_normal(poly: bytes, verts):
    """Unit normal (x, y, z) in Driver 1's convention (the one its group planes
    use: a face is front-facing while n . camera < n . face), or None."""
    t = poly[0] & 31
    off = VERT_OFF.get(t)
    if off is None:
        return None
    idx = poly[off: off + 3]
    if max(idx) >= len(verts):
        return None
    a, b, c = (verts[i] for i in idx)
    u = [b[k] - a[k] for k in range(3)]
    v = [c[k] - a[k] for k in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    length = math.sqrt(sum(x * x for x in n))
    return None if length == 0 else tuple(x / length for x in n)


def group_key(poly: bytes, verts):
    """(absolute, light index, quantised normal or None), matching Driver 1's
    own data: walls get a light direction in 45 degree steps, roofs and
    floors the absolute light 0."""
    n = poly_normal(poly, verts)
    if n is None:
        return True, 0, None
    q = tuple(round(x * NORMAL_STEPS) for x in n)
    if abs(n[1]) >= 0.7:
        return True, 0, q
    return False, round(math.degrees(math.atan2(-n[2], n[0])) / 45) % 8, q


def plane(q, members, polys, verts):
    """Culling plane (nx, ny, nz, d) for polygons sharing quantised normal q:
    drawn while n . camera < d, with d = the farthest vertex along n."""
    length = math.sqrt(sum(x * x for x in q))
    n = [round(x / length * 4096) for x in q]
    far = max(sum(n[k] * verts[i][k] for k in range(3))
              for p in members for i in polys[p][VERT_OFF[polys[p][0] & 31]:][:4] if i < len(verts))
    d = -(-far // 4096) + PLANE_MARGIN
    return (*n, d) if -32768 < d < 32767 else None


def plan_groups(polys, verts):
    """-> (order, groups): order = new polygon order (old indices); groups =
    [(absolute, light, plane or None, count, nbytes)]."""
    buckets = {}
    for i, p in enumerate(polys):
        buckets.setdefault(group_key(p, verts), []).append(i)
    if len(buckets) > MAX_GROUPS // 2:          # too many facings: no culling planes
        merged = {}
        for (absolute, light, _q), members in buckets.items():
            merged.setdefault((absolute, light, None), []).extend(members)
        buckets = merged
    order, groups = [], []
    for key in sorted(buckets, key=lambda k: (k[0], k[1], k[2] or ())):
        absolute, light, q = key
        members = buckets[key]
        pl = plane(q, members, polys, verts) if q is not None else None
        cur, nbytes = [], 0
        for i in members:
            size = len(polys[i])
            if cur and (len(cur) == MAX_GROUP_POLYS or nbytes + size > MAX_GROUP_BYTES):
                groups.append((absolute, light, pl, len(cur), nbytes))
                order += cur
                cur, nbytes = [], 0
            cur.append(i)
            nbytes += size
        if cur:
            groups.append((absolute, light, pl, len(cur), nbytes))
            order += cur
    if len(groups) > MAX_GROUPS:
        raise ValueError("model needs %d polygon groups (max %d)" % (len(groups), MAX_GROUPS))
    return order, groups


def group_table(groups) -> bytes:
    ng = len(groups)
    nmat = (ng + 2) // 3
    out = bytearray(struct.pack("<I", ng | (max(nmat - 1, 0) << 8) | ((24 * nmat) << 16)))
    for m in range(nmat):
        rows = [g[2] or (0, 0, 0, ALWAYS) for g in groups[3 * m: 3 * m + 3]]
        rows += [(0, 0, 0, ALWAYS)] * (3 - len(rows))
        L = [c for r in rows for c in r[:3]]
        bk = [r[3] for r in rows]
        out += struct.pack("<10h", L[0], L[1], L[2], L[3], L[4], L[5], L[6], L[7], L[8], bk[0])
        out += struct.pack("<2h", bk[1], bk[2])
    for k, (absolute, light, _pl, count, nbytes) in enumerate(groups):
        out += struct.pack("<I", count | (4 << 8) | (nbytes << 16) | (light << 26)
                           | (int(absolute) << 30) | ((1 if k == 0 else 0) << 31))
        out += struct.pack("<I", min(count, 31) | ((nbytes // 4) << 16) | (4 << 24))
    return bytes(out)


def vertices(m: Model):
    return [struct.unpack_from("<3h", m.data, m.vertices + 8 * i) for i in range(m.num_vertices)]


def rebuild(m: Model, polys, order, table: bytes | None) -> bytes:
    """Rewrite the polygon block in place (it can only shrink) and append the
    group table; table None keeps +0x1C (instances get it from their source)."""
    data = bytearray(m.data)
    block = b"".join(polys[i] for i in order)
    old_end = m.poly_block + sum(POLY_SIZES[m.data[q] & 31] for q in _offsets(m))
    data[m.poly_block: old_end] = block + bytes(old_end - m.poly_block - len(block))
    if table is not None:
        while len(data) % 4:
            data.append(0)
        struct.pack_into("<i", data, 0x1C, len(data))
        data += table
    return bytes(data)


def _offsets(m: Model):
    q = m.poly_block
    for _ in range(m.num_polys):
        yield q
        q += POLY_SIZES[m.data[q] & 31]


def standalone(m: Model, src: Model) -> Model:
    """Copy an instance's source geometry into it (vertices, collision)."""
    coll = b""
    if src.collision_block:
        n = struct.unpack_from("<i", src.data, src.collision_block)[0]
        coll = src.data[src.collision_block: src.collision_block + 4 + 20 * n]
    polys = m.data[m.poly_block: m.poly_block + sum(POLY_SIZES[m.data[q] & 31] for q in _offsets(m))]
    verts = src.data[src.vertices: src.vertices + 8 * src.num_vertices]
    hdr = bytearray(m.data[:HDR_SIZE])
    v_off = HDR_SIZE
    c_off = v_off + len(verts)
    p_off = c_off + len(coll)
    struct.pack_into("<h", hdr, 4, -1)
    struct.pack_into("<h", hdr, 0x0C, src.num_vertices)
    struct.pack_into("<5i", hdr, 0x10, v_off, p_off, p_off, p_off, c_off if coll else 0)
    return Model.parse(m.index, bytes(hdr) + verts + coll + polys)


def convert_models(models: dict[int, bytes]) -> tuple[dict[int, bytes], dict]:
    """Convert a set of Driver 2 models (index -> data, instances resolved
    within the set). Returns (index -> new data, stats)."""
    parsed = {i: Model.parse(i, d) for i, d in models.items()}
    out, plans = {}, {}
    stats = {"models": 0, "groups": 0, "tiles": 0, "sprites": 0, "instances": 0, "deinstanced": 0}
    for i, m in parsed.items():
        if is_tile(m) or is_sprite(m):
            data = bytearray(m.data)
            struct.pack_into("<i", data, 0x1C, m.poly_block)
            out[i] = bytes(data)
            stats["sprites" if is_sprite(m) and not is_tile(m) else "tiles"] += 1
            continue
        if m.num_polys == 0 or m.instance_number >= 0 and m.instance_number != i:
            continue
        polys = split_polys(m)
        order, groups = plan_groups(polys, vertices(m))
        plans[i] = (order, [len(polys[k]) for k in order])
        out[i] = rebuild(m, polys, order, group_table(groups))
        stats["models"] += 1
        stats["groups"] += len(groups)
    for i, m in parsed.items():
        if i in out:
            continue
        if m.num_polys == 0:
            out[i] = m.data
            continue
        src = m.instance_number
        polys = split_polys(m)
        plan = plans.get(src)
        if plan and len(polys) == len(plan[0]) and [len(polys[k]) for k in plan[0]] == plan[1]:
            out[i] = rebuild(m, polys, plan[0], None)
            stats["instances"] += 1
            continue
        if src not in parsed:
            raise ValueError("model %d instances %d, which is not in the set" % (i, src))
        alone = standalone(m, parsed[src])
        polys = split_polys(alone)
        order, groups = plan_groups(polys, vertices(alone))
        out[i] = rebuild(alone, polys, order, group_table(groups))
        stats["deinstanced"] += 1
    return out, stats
