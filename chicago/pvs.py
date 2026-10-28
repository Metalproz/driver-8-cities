"""pvs.py — Driver 1 visibility (PVS) data for converted cities.

Format (decoder 0x8003A270): per region, a table of 900 u32 offsets (one per
cell, z-major) from the start of the region's PVS block; offset 0 = every cell
of the window visible. A cell's data is an RLE bit stream over the 19 x 19
window of cells around the camera cell (row-major, centre (9, 9)), read until
*0x800973A8 + 1 entries are filled:
    u8 r              r * 8 visible entries (not bounds-checked!)
    u8 c, c bytes     8 entries each, LSB first (c = 0: next run byte)
    ... repeated
Runs are not bounds-checked, so a stream must end with literal bytes.

Chicago has no occlusion data in Driver 1's terms; instead every cell gets a
view radius chosen so the polygons in range stay within the primitive buffer
(0x1E000 bytes per frame; the game hangs at 0x800513D4 when it overflows).
"""
from __future__ import annotations

import struct

import os as _os
# cheats 6 / C94 (Polish 25.10.): CHI_POLISH_XDRAW=1 builds the "Extra draw distance" level variant: a 27 x 27 window
# (radius <= 13, centre (13, 13)) under the feature's 0x50000 primitive buffers. Such a level only works with the feature
# on (the engine then decodes 27 x 27 streams: *0x800973A8 = 729, as 361 today); normal levels are unchanged.
XDRAW = _os.environ.get("CHI_POLISH_XDRAW") == "1"
WINDOW = 27 if XDRAW else 19
ENTRIES = 736 if XDRAW else 368   # covers the window (729 / 361) + the decoder's extra entry, multiple of 8
REGION_CELLS = 30
TABLE = 4 * REGION_CELLS * REGION_CELLS
MAX_RADIUS = 13 if XDRAW else 9
MIN_RADIUS = 5
BYTES_PER_POLY = 20           # measured 8..18.7 per polygon in range (near ground tiles are subdivided)
BUDGET = int((0x50000 if XDRAW else 0x1E000) * 0.72)


def mask(radius: int) -> list[int]:
    c = WINDOW // 2
    return [1 if (x - c) ** 2 + (z - c) ** 2 <= radius * radius + radius else 0
            for z in range(WINDOW) for x in range(WINDOW)]


def encode(bits: list[int]) -> bytes:
    bits = bits + [0] * (ENTRIES - len(bits))
    data = [sum(bits[8 * i + k] << k for k in range(8)) for i in range(ENTRIES // 8)]
    out = bytearray()
    i, last_lit = 0, len(data) - 2          # the last two bytes are always literals
    while i < len(data):
        run = 0
        while i < last_lit and data[i] == 0xFF and run < 255:
            run += 1
            i += 1
        out.append(run)
        lits = []
        while i < len(data) and (i >= last_lit or data[i] != 0xFF) and len(lits) < 255:
            lits.append(data[i])
            i += 1
        out.append(len(lits))
        out += bytes(lits)
    return bytes(out)


def decode(stream: bytes, entries: int) -> list[int]:
    out, p = [], 0
    while len(out) < entries:
        r = stream[p]; p += 1
        out += [1] * (8 * r)
        if len(out) >= entries:
            raise ValueError("stream ends in a run")
        c = stream[p]; p += 1
        for _ in range(c):
            b = stream[p]; p += 1
            out += [(b >> k) & 1 for k in range(8)]
    return out[:entries]


def radius_for(cost_at, cell) -> int:
    """Largest radius whose polygons fit the budget, from cost_at(cell, r)."""
    for r in range(MAX_RADIUS, MIN_RADIUS - 1, -1):
        if cost_at(cell, r) * BYTES_PER_POLY <= BUDGET:
            return r
    return MIN_RADIUS


def region_block(radii: list[int]) -> bytes:
    """PVS block for one region: radii = 900 per-cell radii (z-major)."""
    streams, table = {}, []
    body = bytearray()
    for r in radii:
        if r >= MAX_RADIUS:
            table.append(0)                  # whole window
            continue
        if r not in streams:
            streams[r] = TABLE + len(body)
            body += encode(mask(r))
        table.append(streams[r])
    return struct.pack("<%dI" % len(table), *table) + bytes(body)


if __name__ == "__main__":
    for r in range(MIN_RADIUS, MAX_RADIUS + 1):
        s = encode(mask(r))
        n = WINDOW * WINDOW + 1
        assert decode(s, n) == (mask(r) + [0] * 7)[:n], r
        print("radius", r, "cells", sum(mask(r)), "stream", len(s), "bytes")


def radius_grid(cost, across: int, down: int):
    """cost: {(cx, cz): polygons} -> numpy array [cz, cx] of view radii."""
    import numpy as np
    grid = np.zeros((down, across), dtype=np.int64)
    for (cx, cz), v in cost.items():
        if 0 <= cx < across and 0 <= cz < down:
            grid[cz, cx] += v
    pad = MAX_RADIUS
    padded = np.pad(grid, pad)
    radii = np.full((down, across), MIN_RADIUS, dtype=np.int64)
    for r in range(MIN_RADIUS, MAX_RADIUS + 1):
        total = np.zeros_like(grid)
        m = mask(r)
        c = WINDOW // 2
        for z in range(WINDOW):
            for x in range(WINDOW):
                if m[z * WINDOW + x]:
                    dz, dx = z - c, x - c
                    total += padded[pad + dz: pad + dz + down, pad + dx: pad + dx + across]
        radii[total * BYTES_PER_POLY <= BUDGET] = r
    return radii
