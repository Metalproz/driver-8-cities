"""texpages.py — Driver texture pages: decode/encode and per-page access.

A page is 256x256 4-bit texels (128 bytes per row, first texel in the low
nibble) plus one 16-colour CLUT per texture detail (detail i <-> palette i).

Storage (OpenDriver2Tools textures.cpp):
  permanent / special pages (tpage section): i32 numPalettes, CLUT[numPalettes],
      then the texels RLE-packed *backwards* (unpackTexture), CD-block padded
  area (swap) pages (spooled): SpooledTextureData_t, 17 blocks:
      i32 numPalettes, CLUT[63], 28 pad bytes, raw texels[32768]
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from levfile import Lev
from mapinfo import SpoolInfo, SPOOLINFO
from textures import TexInfo

TEXINFO = 34
PAGE_BYTES = 128 * 256
MAX_CLUTS = 63
RAW_RECORD = 4 + 32 * MAX_CLUTS + 28 + PAGE_BYTES   # 34816 = 17 blocks
BLOCK = 2048


@dataclass
class Page:
    cluts: list = field(default_factory=list)        # list of 32-byte CLUTs
    texels: bytearray = field(default_factory=lambda: bytearray(PAGE_BYTES))

    def get(self, x: int, y: int) -> int:
        b = self.texels[y * 128 + (x >> 1)]
        return (b >> 4) if x & 1 else (b & 15)

    def put(self, x: int, y: int, v: int):
        i = y * 128 + (x >> 1)
        b = self.texels[i]
        self.texels[i] = ((b & 0x0F) | (v << 4)) if x & 1 else ((b & 0xF0) | v)

    def rect(self, x, y, w, h) -> list[bytes]:
        return [bytes(self.get(x + i, y + j) for i in range(w)) for j in range(h)]

    def blit(self, x, y, rows):
        for j, row in enumerate(rows):
            for i, v in enumerate(row):
                self.put(x + i, y + j, v)


# --- codec ------------------------------------------------------------------

def unpack_texels(src: bytes, pos: int) -> tuple[bytearray, int]:
    """unpackTexture: fills the page from its last byte backwards."""
    out = bytearray(PAGE_BYTES)
    p = PAGE_BYTES - 1
    while p >= 0:
        c = src[pos]; pos += 1
        if c & 0x80:                       # run: next byte repeated 258 - c times (3..130)
            v = src[pos]; pos += 1
            n = 258 - c
            for _ in range(n):
                out[p] = v; p -= 1
        else:                              # literal: c + 1 bytes
            for _ in range(c + 1):
                out[p] = src[pos]; pos += 1; p -= 1
    return out, pos


def pack_texels(texels: bytes) -> bytes:
    """Inverse of unpack_texels (runs of 3..130, literals of 1..128)."""
    data = texels[::-1]                    # encoder walks the page backwards
    out = bytearray()
    i, n = 0, len(data)
    lit = bytearray()

    def flush():
        while lit:
            chunk = lit[:128]
            del lit[:128]
            out.append(len(chunk) - 1)
            out.extend(chunk)

    while i < n:
        j = i
        while j < n and j - i < 130 and data[j] == data[i]:
            j += 1
        run = j - i
        if run >= 3:
            flush()
            out.append(258 - run)
            out.append(data[i])
            i = j
        else:
            lit.append(data[i]); i += 1
            if len(lit) == 128:
                flush()
    flush()
    return bytes(out)


def decode_compressed(blob: bytes) -> tuple[Page, int]:
    n = struct.unpack_from("<i", blob, 0)[0]
    cluts = [bytes(blob[4 + 32 * k: 36 + 32 * k]) for k in range(n)]
    texels, end = unpack_texels(blob, 4 + 32 * n)
    return Page(cluts, texels), end


def encode_compressed(page: Page) -> bytes:
    return struct.pack("<i", len(page.cluts)) + b"".join(page.cluts) + pack_texels(page.texels)


def decode_raw(rec: bytes) -> Page:
    n = struct.unpack_from("<i", rec, 0)[0]
    cluts = [bytes(rec[4 + 32 * k: 36 + 32 * k]) for k in range(n)]
    return Page(cluts, bytearray(rec[4 + 32 * MAX_CLUTS + 28: RAW_RECORD]))


def encode_raw(page: Page) -> bytes:
    assert len(page.cluts) <= MAX_CLUTS
    cl = b"".join(page.cluts) + bytes(32 * (MAX_CLUTS - len(page.cluts)))
    return struct.pack("<i", len(page.cluts)) + cl + bytes(28) + bytes(page.texels)


def pad(b: bytes, unit: int = BLOCK) -> bytes:
    return b + bytes(-len(b) % unit)


# --- reading every page of a level -----------------------------------------

def read_pages(lev: Lev) -> tuple[TexInfo, dict[int, Page]]:
    ti = TexInfo.parse(lev.loadtime.get(TEXINFO).data)
    pages: dict[int, Page] = {}
    p = 0
    for page, size in ti.permanent:
        pages[page], _ = decode_compressed(lev.tpages[p: p + size])
        p += (size + BLOCK - 1) // BLOCK * BLOCK
    for page, size in ti.special:
        pages[page], _ = decode_compressed(lev.tpages[p: p + size])
        p += (size + BLOCK - 1) // BLOCK * BLOCK
    sp = SpoolInfo.parse(lev.inmem.get(SPOOLINFO).data)
    for a in sorted({s[7] for s in sp.spools.values()} - {255}):
        gfx = sp.areas[a][0]
        for k, page in enumerate(x for x in sp.area_tpages[a] if x != 0xFF):
            if page in pages:
                continue
            off = (gfx + 17 * k) * BLOCK
            pages[page] = decode_raw(lev.spooled[off: off + RAW_RECORD])
    return ti, pages


if __name__ == "__main__":
    import sys
    for path in sys.argv[1:]:
        lev = Lev.parse(open(path, "rb").read())
        ti, pages = read_pages(lev)
        # codec self-test on every compressed page: re-encode and compare
        p, ok, worse = 0, 0, 0
        for page, size in ti.permanent + ti.special:
            blob = lev.tpages[p: p + size]
            pg, end = decode_compressed(blob)
            again = encode_compressed(pg)
            pg2, _ = decode_compressed(again)
            ok += pg2.texels == pg.texels and pg2.cluts == pg.cluts
            worse += len(again) > end
            p += (size + BLOCK - 1) // BLOCK * BLOCK
        clut_ok = all(len(pages[i].cluts) >= len(ti.details[i]) for i in pages)
        print("%s: %d pages decoded (of %d); codec round-trip %d/%d ok, %d re-encodes larger; cluts>=details: %s"
              % (path, len(pages), ti.num_pages, ok, len(ti.permanent) + len(ti.special), worse, clut_ok))
