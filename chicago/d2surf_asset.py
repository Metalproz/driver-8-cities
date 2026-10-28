"""d2surf_asset.py - Driver 2's own road surface data for the C37 phase 1 lookup (Infrastructure 17.10.).

The package asset assets/d2_surface.bin (build_package, CHI_D2_SURF=1) carries Driver 2's per-region surface blocks
(the same bytes d2surface.Surface reads: cell table, planes, level lists, BSP nodes) plus the curve table, so the
plugin (driver_chicago.c d2surf_*) can answer MapHeight / FindSurfaceD2 with Driver 2's exact planes (sdGetCell +
sdHeightOnPlane). Host-only for now (phase 2: guest code + per-region streaming, Milestone 8 list).

Layout (little endian):
  +0  'D2SF'   +4 version 1   +8 regions across   +12 half_x   +16 half_z
  +20 scale x 65536 (D1 units per D2 unit)   +24 OFFSET_X   +28 OFFSET_Z
  +32 n_regions   +36 n_curves
  +40 n_regions x (region index, byte offset, byte size)
  then n_curves x (mx, mz, gradient, height) as int32 x 4, then the region blocks.
"""
from __future__ import annotations

import struct

import worldscale as ws


def build(d2_lev_path: str) -> bytes:
    import d2surface
    S = d2surface.Surface(d2_lev_path)
    regs = sorted(S.regions.items())
    head = struct.pack("<4s7i", b"D2SF", 1, S.across, S.half_x, S.half_z, int(round(ws.SCALE * 65536)),
                       ws.OFFSET_X, ws.OFFSET_Z)
    head += struct.pack("<2i", len(regs), len(S.curves))
    table_size = 12 * len(regs)
    curves = b"".join(struct.pack("<4i", mx, mz, g, h) for mx, mz, g, h in S.curves)
    off = len(head) + table_size + len(curves)
    table, blobs = b"", b""
    for idx, buf in regs:
        table += struct.pack("<3i", idx, off + len(blobs), len(buf))
        blobs += bytes(buf)
        blobs += bytes((-len(blobs)) % 4)
    return head + table + curves + blobs


if __name__ == "__main__":
    import sys
    import inputs
    data = build(inputs.d2_lev())
    open(sys.argv[1], "wb").write(data)
    print("d2_surface.bin: %d bytes" % len(data))
