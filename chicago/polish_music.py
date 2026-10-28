"""polish_music.py - Driver 2's Chicago music for Chicago in Driver 1 (Polish, 14.10.; milestone 2).

Driver 1's music (exe facts, original exe):
- 0x8004D208(song) = music init: reads 12 bytes of SOUND\\MUSIC.BIN (name at 0x800106C0) at song * 8
  ({xm, bank, next xm}), loads the XM (bank - xm bytes) and the sample bank (next - bank bytes), uploads the
  bank (0x8004E214). Called at 0x80022B5C with *0x800977A0 unless CITY == 4.
- *0x800977A0 = (mission + 3) & 7, written by the mission loader at 0x800687A8..0x800687B8. Take a Ride:
  Miami 0x78 -> 3 (0x79 -> 4), SF 0x7A -> 5 (0x7B -> 6), LA 0x7C -> 7, NY 0x7D -> 0 (0x7E -> 1).
  Chicago runs LA's Take a Ride (0x7C, plugin), so today it plays LA's song 7.
- MUSIC.BIN (both games): int table {xm, bank} x 8 + end offset, then per song a compressed XM and its VAG
  sample bank. Driver 2's CHICAGO tracks: song 2 (even missions) and 6 (odd) (REDRIVER2 main.c).
  Bank sizes: D1 71-87 KB; D2 song 2 80660, song 6 75572 B: within Driver 1's range.

Files (`python polish_music.py D1_MUSIC D2_MUSIC OUT [--inplace]`):
- default: a 10-song MUSIC.BIN = Driver 1's songs 0-7 unchanged + 8 = D2 song 2 (Chicago day) + 9 = D2 song 6
  (Chicago night). Shipped relocated like SKY.BIN (build_package default since 16.10., CHI_POLISH_MUSIC=0 = off); Chicago needs the
  song word set to 8/9 (engine spec below), every other city keeps (mission + 3) & 7 -> 0..7.
- --inplace: TEST ONLY, same size as Driver 1's file: song 7 (LA, and Chicago today) replaced by D2 song 2, so
  the D1 driver can be tested with D2 data through an in-place disc overlay (LA plays it too).

Song select (engine, Chicago-gated, M8 guest-code friendly): at 0x800687B4 `andi v0,v0,7` + 0x800687B8
`sw v0,0x1030(gp)`, store 8 (day) / 9 (night) instead when Chicago is active (plugin flag word at 0x9F082104,
as in AREA_SWITCH_CODE; night = the plugin's Day/Night choice or *0x80096850 once set). Alternative: the
plugin writes 0x800977A0 from a function-entry hook on 0x8004D208 (a0 = song) when Chicago is active.
"""
from __future__ import annotations

import struct
import sys


def songs(data: bytes):
    t = struct.unpack_from("<17i", data, 0)
    return [(data[t[2 * k]: t[2 * k + 1]], data[t[2 * k + 1]: t[2 * k + 2]]) for k in range(8)]


def pack(entries) -> bytes:
    """entries: [(xm, bank)] -> MUSIC.BIN with len(entries) songs (4-byte aligned parts)."""
    n = len(entries)
    off = 4 * (2 * n + 1)
    table, body = [], bytearray()
    for xm, bank in entries:
        for part in (xm, bank):
            table.append(off + len(body))
            body += part
            while len(body) % 4:
                body.append(0)
    table.append(off + len(body))
    return struct.pack("<%di" % (2 * n + 1), *table) + bytes(body)


def chicago_music(d1: bytes, d2: bytes) -> bytes:
    s1, s2 = songs(d1), songs(d2)
    return pack(s1 + [s2[2], s2[6]])


def inplace_test(d1: bytes, d2: bytes) -> bytes:
    """Same size as d1: song 7 = D2 song 2 (test only)."""
    s1, s2 = songs(d1), songs(d2)
    out = bytearray(pack(s1[:7] + [s2[2]]))
    # pack() wrote a 7+1-song table with 17 ints like the original (8 songs): sizes match the original
    if len(out) > len(d1):
        raise ValueError("D2 song 2 does not fit song 7's space")
    return bytes(out) + bytes(len(d1) - len(out))


if __name__ == "__main__":
    a = sys.argv[1:]
    d1, d2 = open(a[0], "rb").read(), open(a[1], "rb").read()
    data = inplace_test(d1, d2) if "--inplace" in a else chicago_music(d1, d2)
    open(a[2], "wb").write(data)
    t = struct.unpack_from("<%di" % (data[0:4] and (21 if "--inplace" not in a else 17)), data, 0)
    print(a[2], len(data), "table", t)


# --- chase music (C60, Polish 16.10.) ------------------------------------------------------------
# Driver 1 = Driver 2's FunkUpDaBGMTunez at 0x8004CF50: when copmusic (gp+0x500 = 0x80096C70) is 0 and the felony
# 0x80097708 >= 0x293, copmusic = 1 and the song jumps to the pattern-order position xm_coptrackpos[current song
# *0x80097298] (table 0x8008AA04, 8 ints read with lhu) via 0x80073020 (XM set position). Chicago's songs 8 / 9
# index past the table (entries 8 / 9 are InitSound's SPU words 0x28000 / 0x400): no chase music.
# Driver 2's chase positions (REDRIVER2 gamesnd.c xm_coptrackpos_d2): song 2 (Chicago day) 7, song 6 (night) 8.
D1_COPTRACKPOS = (0xB, 0xC, 0xB, 0xB, 8, 0xB, 0xF, 0xC)
CHASE_POS = {8: 7, 9: 8}


def coptrackpos_table() -> bytes:
    """10 ints for a relocated xm_coptrackpos (Driver 1's 8 + Chicago day / night)."""
    return struct.pack("<10i", *D1_COPTRACKPOS, CHASE_POS[8], CHASE_POS[9])
