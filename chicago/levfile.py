"""levfile.py — read/write the Driver 1 / Driver 2 (PSX) LEV container.

Layout (offsets in bytes, all little-endian):

    0x000  LUMP(37 LUMPDESC, 0x7F8) + OUT_CITYLUMP_INFO (8 x u32), zero padded to 0x800
    loadtime_offset  LUMP(35 LOADTIME, n) + sub-lumps
    tpage_offset     permanent texture pages (raw)
    inmem_offset     LUMP(36 INMEMORY, n) + sub-lumps
    spooled_offset   spooled region/area data (raw, 2048-byte blocks)

Sub-lumps are LUMP(type, size) + payload, 4-byte aligned. Driver 1 prefixes the
list with an int count; Driver 2 ends it with type 255.

The container keeps every byte it does not interpret ("tail" / padding), so
Lev.parse(data).build() reproduces the input exactly; that round-trip is the
writer's correctness test.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

LUMP_NAMES = {
    0: "TEXTURES", 1: "MODELS", 2: "MAP", 3: "UNUSED", 4: "MOVEABLE", 5: "TEXTURENAMES",
    6: "ROADINFO", 7: "ROADMAP", 8: "ROADS", 9: "JUNCTIONS", 10: "ROADSURF", 11: "ROADHEIGHT",
    12: "MODELNAMES", 13: "EVENTMODELS", 14: "PVS", 15: "REGIONTSETS", 16: "ROADBOUNDS",
    17: "JUNCBOUNDS", 18: "CAMERAPATHS", 19: "LAMPS", 20: "SUBDIVISION", 21: "LOWDETAILTABLE",
    22: "MOTIONCAPTURE", 23: "TEXT", 24: "OVERLAYMAP", 25: "PALLET", 26: "SPOOLINFO",
    28: "CAR_MODELS", 33: "CHAIR", 34: "TEXTUREINFO", 35: "LOADTIME", 36: "INMEMORY",
    37: "LUMPDESC", 40: "STRAIGHTS2", 41: "CURVES2", 42: "JUNCTIONS2", 43: "JUNCTIONS2_NEW",
}

LUMPDESC, LOADTIME, INMEMORY = 37, 35, 36
END_MARKER = 255
SECTOR = 2048


def align(n: int, a: int) -> int:
    return (n + a - 1) // a * a


@dataclass
class Lump:
    type: int
    data: bytes

    @property
    def name(self) -> str:
        return LUMP_NAMES.get(self.type, "?%d" % self.type)


@dataclass
class LumpList:
    """A LOADTIME / INMEMORY section: wrapper lump + sub-lumps."""
    kind: int                        # 35 or 36
    d1: bool                         # Driver 1: int count prefix, no end marker needed
    lumps: list[Lump] = field(default_factory=list)
    gap_after: list[bytes] = field(default_factory=list)   # bytes between lumps (alignment)
    tail: bytes | None = None        # end marker / trailing bytes (None = synthesise)
    declared_size: int | None = None  # wrapper size as stored (None = compute)

    @classmethod
    def parse(cls, data: bytes, off: int, d1: bool) -> "LumpList":
        kind, size = struct.unpack_from("<II", data, off)
        body = data[off + 8: off + 8 + size]
        out = cls(kind=kind, d1=d1, declared_size=size)
        p = 0
        count = 1 << 30
        if d1:
            count = struct.unpack_from("<i", body, 0)[0]
            p = 4
        while len(out.lumps) < count and p + 8 <= len(body):
            t, n = struct.unpack_from("<Ii", body, p)
            if t == END_MARKER:
                break
            out.lumps.append(Lump(t, bytes(body[p + 8: p + 8 + n])))
            q = p + 8 + n
            aligned = align(q, 4)
            out.gap_after.append(bytes(body[q:aligned]))
            p = aligned
        out.tail = bytes(body[p:])
        return out

    def build(self, keep_declared: bool = True) -> bytes:
        parts = []
        if self.d1:
            parts.append(struct.pack("<i", len(self.lumps)))
        for i, lump in enumerate(self.lumps):
            parts.append(struct.pack("<Ii", lump.type, len(lump.data)))
            parts.append(lump.data)
            cur = sum(map(len, parts))
            gap = self.gap_after[i] if i < len(self.gap_after) else None
            if gap is None or len(gap) != align(cur, 4) - cur:
                gap = b"\0" * (align(cur, 4) - cur)
            parts.append(gap)
        if self.tail is not None:
            parts.append(self.tail)
        elif not self.d1:
            parts.append(struct.pack("<II", END_MARKER, 0))
        body = b"".join(parts)
        size = self.declared_size if (keep_declared and self.declared_size is not None) else len(body)
        return struct.pack("<II", self.kind, size) + body

    def find(self, lump_type: int) -> list[Lump]:
        return [l for l in self.lumps if l.type == lump_type]

    def get(self, lump_type: int) -> Lump:
        found = self.find(lump_type)
        if len(found) != 1:
            raise KeyError("expected one lump %d, found %d" % (lump_type, len(found)))
        return found[0]


@dataclass
class Lev:
    d1: bool
    loadtime: LumpList
    tpages: bytes
    inmem: LumpList
    spooled: bytes
    header_pad: bytes = b""
    # section capacities as stored (for exact round trip); None = compute
    sizes: dict | None = None

    @classmethod
    def parse(cls, data: bytes) -> "Lev":
        t, n = struct.unpack_from("<II", data, 0)
        if t != LUMPDESC:
            raise ValueError("not a LEV file (first lump %d)" % t)
        lt_off, lt_sz, tp_off, tp_sz, im_off, im_sz, sp_off, sp_sz = struct.unpack_from("<8I", data, 8)
        # Driver 1: LOADTIME body starts with a lump count, so its second word is
        # the first lump's type; in Driver 2 the second word is that lump's size.
        second = struct.unpack_from("<I", data, lt_off + 12)[0]
        d1 = second < 64
        lev = cls(
            d1=d1,
            loadtime=LumpList.parse(data, lt_off, d1),
            tpages=bytes(data[tp_off: tp_off + tp_sz]),
            inmem=LumpList.parse(data, im_off, d1),
            spooled=bytes(data[sp_off: sp_off + sp_sz]),
            header_pad=bytes(data[8 + 32: lt_off]),
            sizes={"loadtime": lt_sz, "inmem": im_sz, "header": n,
                   "loadtime_raw": bytes(data[lt_off: lt_off + lt_sz]),
                   "inmem_raw": bytes(data[im_off: im_off + im_sz]),
                   "end": bytes(data[sp_off + sp_sz:])},
        )
        return lev

    def build(self, keep_layout: bool = True) -> bytes:
        """Serialise. keep_layout=True reuses stored section capacities."""
        def section(lumplist: LumpList, key: str) -> bytes:
            body = lumplist.build(keep_declared=keep_layout)
            cap = self.sizes[key] if (keep_layout and self.sizes) else align(len(body), SECTOR)
            if len(body) > cap:
                raise ValueError("%s section grew past its capacity" % key)
            raw = self.sizes.get(key + "_raw") if (keep_layout and self.sizes) else None
            pad = raw[len(body):cap] if raw is not None and len(raw) == cap else b"\0" * (cap - len(body))
            return body + pad

        lt = section(self.loadtime, "loadtime")
        im = section(self.inmem, "inmem")
        tp = self.tpages
        sp = self.spooled

        lt_off = SECTOR
        tp_off = lt_off + len(lt)
        im_off = tp_off + len(tp)
        sp_off = im_off + len(im)
        head = struct.pack("<II", LUMPDESC, self.sizes["header"] if self.sizes else 0x7F8)
        head += struct.pack("<8I", lt_off, len(lt), tp_off, len(tp), im_off, len(im), sp_off, len(sp))
        pad = self.header_pad if len(self.header_pad) == SECTOR - len(head) else b"\0" * (SECTOR - len(head))
        end = self.sizes.get("end", b"") if (keep_layout and self.sizes) else b""
        out = head + pad + lt + tp + im + sp + end
        return out

    def summary(self) -> str:
        lines = ["format %s  tpages %d  spooled %d" % ("D1" if self.d1 else "D2", len(self.tpages), len(self.spooled))]
        for name, ll in (("LOADTIME", self.loadtime), ("INMEMORY", self.inmem)):
            lines.append("  %s (%d lumps)" % (name, len(ll.lumps)))
            for l in ll.lumps:
                lines.append("    %-16s %8d" % (l.name, len(l.data)))
        return "\n".join(lines)


if __name__ == "__main__":
    import sys
    for path in sys.argv[1:]:
        raw = open(path, "rb").read()
        lev = Lev.parse(raw)
        rebuilt = lev.build()
        print(path, "round-trip", "OK" if rebuilt == raw else "MISMATCH (%d vs %d bytes)" % (len(rebuilt), len(raw)))
