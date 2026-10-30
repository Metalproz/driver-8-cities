"""C129: write one city's Driver 2 road blob for the civ-AI core + Driver 1's rcossin table.

python export_roads.py CITY [OUTDIR]   (CITY = CHICAGO | HAVANA | VEGAS | RIO; OUTDIR default c129/out)

<city>_roads.bin = "D2RD", nStraights, nCurves, nJunctions (int32 each), then the three lumps' record arrays exactly as
the D2 LEV stores them (STRAIGHTS2 28 B, CURVES2 28 B, JUNCTIONS2_NEW 12 B; dr2types.h layouts): the guest overlay uses
them in place (PS1-native). rcossin.bin = 4096 x (sin, cos) int16 from Driver 1's exe (0x8008EAA8, libgte's table)."""
import os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))


def main():
    city = sys.argv[1].upper()
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "out")
    os.environ["CHI_CITY"] = city
    import inputs, cityprofile as cp
    from levfile import Lev
    lev = Lev.parse(open(inputs.path(cp.P.lev_day), "rb").read())
    L = {l.type: l.data for sec in (lev.loadtime, lev.inmem) for l in sec.lumps}
    blob = bytearray(b"D2RD")
    parts = []
    for t, size in ((40, 28), (41, 28), (43, 12)):
        n = struct.unpack_from("<i", L[t], 0)[0]
        parts.append((n, L[t][4: 4 + n * size]))
    blob += struct.pack("<3i", *(n for n, _ in parts))
    for _, d in parts:
        blob += d
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, "%s_roads.bin" % city.lower()), "wb").write(blob)
    exe = open(inputs.path("d1_SLUS_008.42"), "rb").read()
    off = 0x8008EAA8 - 0x80010000 + 0x800
    tab = exe[off: off + 4096 * 4]
    s0, c0 = struct.unpack_from("<hh", tab, 0)
    s1024, c1024 = struct.unpack_from("<hh", tab, 1024 * 4)
    assert (s0, c0, s1024, c1024) == (0, 4096, 4096, 0), (s0, c0, s1024, c1024)
    open(os.path.join(out, "rcossin.bin"), "wb").write(tab)
    print("%s: %d straights, %d curves, %d junctions -> %d B; rcossin ok" % (city, parts[0][0], parts[1][0], parts[2][0], len(blob)))


if __name__ == "__main__":
    main()
