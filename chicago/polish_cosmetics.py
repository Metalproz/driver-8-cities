"""polish_cosmetics.py - C42: Driver 1 car_cosmetics rows for Chicago (Polish, 14.10.). Switch CHI_POLISH_COSMETICS=1.

Driver 1 (Ghidra pass 2): car_cosmetics 0x8009AF04 = 4 runtime rows of 100 B, filled by LoadCosmetics 0x80052620 from
the exe table 0x800853D8: 8 rows of 100 B per CITY (base 0 Miami, 8 SF, 0x10 Interview, 0x18 LA + Chicago, 0x20 NY,
0x28 Newtown); runtime row 0 = base + player car choice (0..3), rows 1-3 = base + 5, 6, 7 (the AI models).
Row layout: 8 SVECTORs (headLight, frontInd, backInd, brakeLight, revLight, policeLight, exhaust, smoke; D2 order),
wheelDisp[4] at +0x40, then 2 shorts (4096, 8 in every Driver 1 row; kept).

Driver 2 (REDRIVER2 cosmetic.c / cars.c): CHICAGO.LCF = 13 offsets + CAR_COSMETICS (236 B) per model: 9 SVECTORs
(+ fire), wheelDisp[4], extraInfo, powerRatio, cbYoffset, susCoeff, traction, wheelSize, ...

Wheel placement: D2 x = +-17 - disp.vx, z = -disp.vz, y = -wheelSize - disp.vy - susCompression + 14;
D1 x = +-25 - disp.vx (wheels 0/1 +, 2/3 -), z = -disp.vz, y = -(suspension + 50) - disp.vy.
Same picture: vx' = vx + 8 (wheels 0/1) / vx - 8 (2/3), vz' = vz, vy' = vy + wheelSize - 64 (suspension
conventions assumed equal at rest; D1's StepOneCar also reads the wheel rows, so the ride height must be checked).
Wheel size: D1 draws the tread at a fixed radius 0x65 (= D2's sizeScale = wheelSize * 1.4142); see SIZE_TABLE.

Output (`python polish_cosmetics.py [OUTDIR]`): chicago_cosmetics_day.bin / _night.bin = 8 rows x 100 B to replace
the exe table rows at 0x800853D8 + 0x18 * 100 while Chicago is loaded: rows 0-4 from the D1 car set of that
time of day (day Miami base 0, night LA base 0x18: the player cars are the set's), rows 5-7 = D2 cop, civ 0, civ 1.
"""
from __future__ import annotations

import os
import struct
import sys

EXE = "D:/recomps/Apps/Driver-DriverRecompiled/disc/SLUS_008.42.orig"
TABLE = 0x800853D8
ROW = 100
BASES = {"miami": 0, "sf": 8, "la": 0x18, "ny": 0x20}
D2_FOR_ROW = {5: 3, 6: 0, 7: 1}         # exe rows base+5..7 (AI models) <- D2 models (polish_cars slot map 0<-3, 1<-0, 2<-1)
D1_RADIUS = 0x65


def enabled():
    return os.environ.get("CHI_POLISH_COSMETICS", "") == "1"


def exe_rows(base: int):
    exe = open(EXE, "rb").read()
    t = struct.unpack_from("<I", exe, 0x18)[0]
    o = 0x800 + (TABLE & 0x1FFFFFFF) - (t & 0x1FFFFFFF) + base * ROW
    return [exe[o + k * ROW: o + (k + 1) * ROW] for k in range(8)]


def d2_models(lcf: bytes):
    offs = struct.unpack_from("<13i", lcf, 0)
    out = {}
    for m, o in enumerate(offs):
        if 0 < o < len(lcf):
            sv = [struct.unpack_from("<4h", lcf, o + 8 * i) for i in range(13)]
            sh = struct.unpack_from("<6h", lcf, o + 104)
            out[m] = dict(lights=sv[:9], wheels=sv[9:13], wheelSize=sh[5], susCoeff=sh[3])
    return out


def d1_row(d2: dict, tail: bytes) -> bytes:
    out = bytearray()
    for vx, vy, vz, pad in d2["lights"][:8]:           # D2 order = D1 order; 'fire' has no D1 slot
        out += struct.pack("<4h", vx, vy, vz, 0)
    for i, (vx, vy, vz, pad) in enumerate(d2["wheels"]):
        dx = 8 if i < 2 else -8
        out += struct.pack("<4h", vx + dx, vy + d2["wheelSize"] - 64, vz, 0)
    return bytes(out) + tail


def build(lcf_path: str, outdir: str):
    d2 = d2_models(open(lcf_path, "rb").read())
    files = {}
    for tod, cset in (("day", "miami"), ("night", "la")):
        rows = exe_rows(BASES[cset])
        new = list(rows)
        for r, m in D2_FOR_ROW.items():
            new[r] = d1_row(d2[m], rows[r][96:100])
        path = os.path.join(outdir, "var_polish_cosmetics_chicago_%s.bin" % tod)
        open(path, "wb").write(b"".join(new))
        files[tod] = path
    size = [(m, d2[m]["wheelSize"], round(d2[m]["wheelSize"] * 1.4142), D1_RADIUS) for m in (3, 0, 1)]
    return files, size


if __name__ == "__main__":
    outdir = sys.argv[1] if len(sys.argv) > 1 else "work"
    files, size = build("work/d2_CHICAGO.LCF", outdir)
    print(files)
    print("D2 model, wheelSize, D2 tread radius (wheelSize*1.4142), D1 fixed radius:")
    for row in size:
        print("  ", row, "-> D1 draws %.0f%% too big" % (100.0 * (row[3] / row[2] - 1)))
