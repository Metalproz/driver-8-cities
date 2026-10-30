"""polish_cycle.py - C146 (Polish 30.10.): Driver 2's palette-cycling neon (REDRIVER2 objanim.c ColourCycle) as a level
sidecar for the engine.

Driver 2 rotates CLUT entries of a few named textures every other frame (FrameCnt & 1 skipped, not while an area loads):
for each CYCLE_OBJECT {name, start1, stop1, speed1, start2, stop2, speed2} it reads the texture's 16-entry CLUT row from VRAM
once (texture_cluts[page][number]), then on frames where (cycle_timer & speed) == 0 moves entry `start` to `stop`
(memmove start+1..stop down one, old start at stop) for each of the two ranges (-1 = unused) and uploads the row. Las Vegas
has 12 (the Strip neon: DTSYN01-03, F-MTSYN2, SYN-CAS1, SYNSLOT, ENT1B, FLAMINGO, CYCLE-01..04), Chicago 2 (REDRVR,
NAVPIR34), Havana / Rio none (their tables exist but Num_LevCycleObjs = 0). Driver 1 has no such thing, so the neon is
static in our port (C146: the canopy stripe stays blue where Driver 2 shows it cycling to red).

Sidecar <lev>.cyc.bin: "CYC1", count, then per entry (28 B): name (12 B, NUL padded), our texture page, texture index
within that page (the converted level's TEXINFO), start1, stop1, speed1, start2, stop2, speed2 (int16 each). A name
present on several pages gets one entry per copy. The engine finds the CLUT of (page, index) like Driver 2 does.
Usage: python polish_cycle.py LEVEL.lev [...]   (CHI_CITY selects the city's table)
"""
from __future__ import annotations

import struct
import sys

CYCLE = {   # REDRIVER2 objanim.c Lev0 / Lev2 (city -> [(name, start1, stop1, speed1, start2, stop2, speed2)])
    "CHICAGO": [("REDRVR", 6, 10, 2, 11, 15, 2), ("NAVPIR34", 0, 6, 0, 7, 13, 0)],
    "VEGAS": [("DTSYN01", 0, 3, 0, 4, 14, 0), ("DTSYN02", 0, 15, 0, -1, -1, 0), ("F-MTSYN2", 0, 3, 0, 10, 14, 0),
              ("DTSYN03", 0, 3, 0, -1, -1, 0), ("SYN-CAS1", 0, 3, 0, 4, 14, 0), ("SYNSLOT", 0, 3, 0, 4, 7, 0),
              ("ENT1B", 0, 15, 0, -1, -1, 0), ("FLAMINGO", 0, 3, 0, 9, 12, 0), ("CYCLE-01", 0, 5, 1, 6, 11, 1),
              ("CYCLE-02", 0, 3, 3, -1, -1, 0), ("CYCLE-03", 0, 6, 7, 7, 13, 7), ("CYCLE-04", 0, 6, 15, 7, 13, 15)],
}


def entries(lev_bytes: bytes, city: str):
    """[(name, page, index, params)] of the city's cycling textures in a converted level."""
    import texpages
    from levfile import Lev
    table = CYCLE.get(city, [])
    if not table:
        return []
    lev = Lev.parse(lev_bytes)
    ti = texpages.TexInfo.parse(lev.loadtime.get(texpages.TEXINFO).data)
    names = lev.loadtime.get(5).data
    where = {}
    for p in range(ti.num_pages):
        for k, d in enumerate(ti.details[p]):
            nm = names[d[1]: names.index(b"\0", d[1])].decode("latin-1")
            where.setdefault(nm, []).append((p, k))
    out = []
    for name, *par in table:
        for p, k in where.get(name, []):
            out.append((name, p, k, tuple(par)))
    return out


def write(out_path: str, lev_bytes: bytes, city: str) -> int:
    ents = entries(lev_bytes, city)
    blob = struct.pack("<4sI", b"CYC1", len(ents))
    for name, p, k, par in ents:
        blob += name.encode("latin-1")[:12].ljust(12, b"\0") + struct.pack("<8h", p, k, *par)
    open(out_path + ".cyc.bin", "wb").write(blob)
    return len(ents)


if __name__ == "__main__":
    import cityprofile
    for path in sys.argv[1:]:
        ents = entries(open(path, "rb").read(), cityprofile.P.name)
        write(path, open(path, "rb").read(), cityprofile.P.name)
        print(path, len(ents), [(n, p, k) for n, p, k, _ in ents])
