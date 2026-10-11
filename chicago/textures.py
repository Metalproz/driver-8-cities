"""textures.py — TEXTUREINFO lump (same layout in Driver 1 and 2).

    i32 numPages, i32 numTextures, TEXPAGE_POS[numPages+1] {u32 flags, u32 offset},
    per page: i32 numDetails + TEXINF[numDetails] {u16 id, u16 nameoffset, u8 x,y,w,h},
    i32 numPermanent, XYPAIR[16] {i32 page, i32 size}, i32 numSpec, XYPAIR[16]
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

TEXTUREINFO, TEXTURENAMES = 34, 5
FLAG_NAMES = {1: "PERMANENT", 2: "SWAPABLE", 4: "SPECIAL", 8: "DAMAGED", 16: "8BIT", 32: "PALNUM", 64: "PARENT"}


@dataclass
class TexInfo:
    num_pages: int
    num_textures: int
    positions: list
    details: list = field(default_factory=list)   # per page: list of (id, nameoff, x, y, w, h)
    permanent: list = field(default_factory=list)  # (page, size)
    special: list = field(default_factory=list)

    @classmethod
    def parse(cls, data: bytes) -> "TexInfo":
        n, ntex = struct.unpack_from("<ii", data, 0)
        p = 8
        pos = [struct.unpack_from("<II", data, p + 8 * i) for i in range(n + 1)]
        p += 8 * (n + 1)
        ti = cls(n, ntex, pos)
        for _ in range(n):
            nd = struct.unpack_from("<i", data, p)[0]; p += 4
            ti.details.append([struct.unpack_from("<HH4B", data, p + 8 * k) for k in range(nd)])
            p += 8 * nd
        nperm = struct.unpack_from("<i", data, p)[0]; p += 4
        ti.permanent = [struct.unpack_from("<ii", data, p + 8 * k) for k in range(nperm)]; p += 8 * 16
        nspec = struct.unpack_from("<i", data, p)[0]; p += 4
        ti.special = [struct.unpack_from("<ii", data, p + 8 * k) for k in range(nspec)]; p += 8 * 16
        ti.end = p
        return ti


def flags_str(f: int) -> str:
    return "|".join(n for b, n in FLAG_NAMES.items() if f & b) or "0"


if __name__ == "__main__":
    import sys, collections
    from levfile import Lev
    for path in sys.argv[1:]:
        lev = Lev.parse(open(path, "rb").read())
        raw = lev.loadtime.get(TEXTUREINFO).data
        ti = TexInfo.parse(raw)
        flags = collections.Counter(flags_str(f) for f, _ in ti.positions[:-1])
        print(path.split("/")[-1], "pages", ti.num_pages, "textures", ti.num_textures,
              "details", sum(map(len, ti.details)), "parsed", ti.end, "/", len(raw))
        print("   page flags:", dict(flags))
        print("   permanent:", ti.permanent)
        print("   special:", ti.special)
