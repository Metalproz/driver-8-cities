"""build_package.py — write the driver.chicago mod package.

Features:
  model-table    move Driver 1's model table to 2048 entries (patches + plugin)
  chicago-la / chicago-slot   Chicago (see main())

usage: build_package.py --chicago work/chicago_d1.lev [--slot] [--night LEV]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import struct
import sys

import exe_patches
import inputs
import worldscale

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", ".."))
# The patches must be computed against the ORIGINAL executable; disc/SLUS_008.42
# itself already carries them (it is the recompiler input).
EXE = inputs.path("d1_SLUS_008.42")   # Option A: the stock exe from the player's D1 image (md5-checked); work mode: disc/SLUS_008.42.orig
DISC_BIN = inputs.d1_image()   # the player's Driver 1 disc (game.toml [game] discs[0], else disc.cfg): every disc patch is made against it
# CHI_PKG_DIR: write the package elsewhere (test copies), never into the preloaded one
PKG = os.environ.get("CHI_PKG_DIR") or os.path.join(APP, "mods", "preloaded", "packages", "driver.chicago", "0.1.0")

LEVELS_DIR_LBA = 1026            # DRIVER/LEVELS directory sector
EXTENSION_LBA = 320000           # first sector used past the disc end (317615)
CHICAGO_LBA = 330000             # converted Chicago (after the Miami test)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hexbytes(b: bytes) -> str:
    return " ".join("%02x" % c for c in b)


def dir_record(name: bytes):
    """(disc_user offset of the extent field, current 16 bytes) for a LEVELS file."""
    with open(DISC_BIN, "rb") as f:
        f.seek(LEVELS_DIR_LBA * 2352 + 24)
        sec = f.read(2048)
    i = 0
    while i < 2048 and sec[i]:
        n, nl = sec[i], sec[i + 32]
        if sec[i + 33:i + 33 + nl] == name:
            return LEVELS_DIR_LBA * 2048 + i + 2, sec[i + 2:i + 18]
        i += n
    raise KeyError(name)


def iso_record(path: list[bytes]):
    """(disc_user offset of the extent field, current 16 bytes) of a file given by its ISO path,
    e.g. [b"DRIVER", b"DATA", b"SKY.BIN;1"]."""
    def sector(lba):
        with open(DISC_BIN, "rb") as f:
            f.seek(lba * 2352 + 24)
            return f.read(2048)
    pvd = sector(16)
    lba, size = struct.unpack_from("<I", pvd, 156 + 2)[0], struct.unpack_from("<I", pvd, 156 + 10)[0]
    for k, name in enumerate(path):
        found = None
        for s in range((size + 2047) // 2048):
            sec, i = sector(lba + s), 0
            while i < 2048 and sec[i]:
                n, nl = sec[i], sec[i + 32]
                if sec[i + 33:i + 33 + nl] == name:
                    found = ((lba + s) * 2048 + i + 2, sec[i + 2:i + 18])
                    break
                i += n
            if found:
                break
        if not found:
            raise KeyError(name)
        if k == len(path) - 1:
            return found
        lba, size = struct.unpack_from("<I", found[1], 0)[0], struct.unpack_from("<I", found[1], 8)[0]


# C42 r3 (e), user R32 option A3: Driver 2's car engine sounds for Chicago. Driver 2 loads one car bank per resident model
# from SOUND\VOICES2.BLK (gamesnd.c LoadBankFromLump / MapCarIndexToBank; Chicago: civ 1 -> 12, civ 2 and the cop -> 4,
# civ 3 -> 13). Three shared banks replace Driver 1's two engine samples (bank 0 samples 1-2, 71.5 KB of SPU RAM): their
# engine and idle loops (66.3 KB, 16 kHz) go into that space at runtime (plugin, host-only). Horns stay Driver 1's.
CAR_SFX_BANKS = (12, 4, 13)
# R36 (user: horns + Driver 2's exact model -> bank mapping): Driver 2's MapCarIndexToBank for Chicago
# (car_banks[0] = {12, 4, 13, 5, 16, 9, 2, 15, 10}; index = model - 1, model 0 -> 1, > 6 -> -3): D2 model -> bank.
D2_CHICAGO_BANK = dict(__import__("cityprofile").P.car_banks)   # M3 profile (Chicago: car_banks[0])
CAR_SFX_V2 = os.environ.get("CHI_CAR_SFX_V2", "1") != "0"
CAR_SFX_RATE = int(os.environ.get("CHI_CAR_SFX_RATE", "11025"))   # engine / idle loops resampled (SPU RAM budget)


def car_sfx_v2() -> bytes:
    """R36 assets/car_sfx.bin "CSX2": magic, count, then per sample {bank, kind (0 engine / 1 idle / 2 horn), size, loop,
    rate} (5 x int32); a 28-byte map: bank of Driver 1 resident model 0..7 (8), of player choice 0..3 (4), of the
    special by Driver 2 model 0..15 (16); then the VAG data (each padded to 16). Banks: the civilians' (shared, Driver 2's
    mapping) + the player choices' and the specials' (one of each loaded at a time by the plugin). Engine / idle loops are
    resampled to CAR_SFX_RATE (Driver 1's SPU RAM has no room for 16 kHz), horns (8 kHz) stay."""
    import polish_cars, polish_specials, vag
    v2 = inputs.read("d2_VOICES2.BLK")
    offs = struct.unpack_from("<73I", v2, 0)
    sm = polish_cars.slot_map()
    civ = [0] * 8
    for d1 in range(1, 6):
        d2 = sm.get(d1 - 1)
        if d2 is not None and d1 < 5:
            civ[d1] = D2_CHICAGO_BANK.get(d2, 0)
    player = [D2_CHICAGO_BANK.get(sm.get(5 + c), 0) if sm.get(5 + c) is not None else 0 for c in range(4)]
    spc = [0] * 16
    for m in polish_specials.SPECIALS:
        spc[m] = D2_CHICAGO_BANK.get(m, 0)
    banks = []
    for b in [civ[k] for k in range(8)] + player + spc:
        if b and b not in banks:
            banks.append(b)
    hdr, data = [], b""
    for b in banks:
        blk = v2[offs[b]: offs[b + 1]]
        n = struct.unpack_from("<I", blk, 0)[0]
        body = blk[4 + 16 * n:]
        for kind in range(min(n, 3)):
            o, size, loop, rate = struct.unpack_from("<4I", blk, 4 + 16 * kind)
            smp = body[o: o + size]
            if kind < 2 and CAR_SFX_RATE and CAR_SFX_RATE != rate:
                smp, rate = vag.convert(smp, rate, CAR_SFX_RATE, bool(loop)), CAR_SFX_RATE
            hdr.append(struct.pack("<5i", b, kind, len(smp), loop, rate))
            data += smp + bytes((-len(smp)) % 16)
    mp = bytes(civ) + bytes(player) + bytes(spc)
    return struct.pack("<Ii", 0x32585343, len(hdr)) + b"".join(hdr) + mp + data


def car_sfx() -> bytes:
    """assets/car_sfx.bin: count, then per sample {bank, kind (0 engine / 1 idle), size, loop, rate} (5 x int32), then the
    VAG data of the samples back to back (each padded to 16)."""
    v2 = inputs.read("d2_VOICES2.BLK")
    offs = struct.unpack_from("<73I", v2, 0)
    hdr, data = [], b""
    for b in CAR_SFX_BANKS:
        blk = v2[offs[b]: offs[b + 1]]
        n = struct.unpack_from("<I", blk, 0)[0]
        body = blk[4 + 16 * n:]
        for kind in (0, 1):
            o, size, loop, rate = struct.unpack_from("<4I", blk, 4 + 16 * kind)
            smp = body[o: o + size]
            hdr.append(struct.pack("<5i", b, kind, len(smp), loop, rate))
            data += smp + bytes((-len(smp)) % 16)
    return struct.pack("<i", len(hdr)) + b"".join(hdr) + data


def chicago_skybin(la_day: bool = False, extra=None) -> bytes:
    """Driver 1's SKY.BIN with Chicago's skies (Driver 2's SKY0.RAW) appended as 13 day,
    14 night, 15 rain (polish_sky.py, C10); the plugin sets the sky number for Chicago.
    la_day (C63, 17.10.): + Design's LA day sky as 16 (design/la_day_sky.py recipe on the player's D1 sky 10,
    built here at package time, Option A); the plugin's LA by day takes it (sidecar flag 4)."""
    import polish_sky
    data = inputs.read("d1_SKY.BIN")
    skies = polish_sky.read_skybin(data)
    assert len(skies) == polish_sky.NSKY and polish_sky.write_skybin(skies) == data
    for name in ("day", "night", "rain"):
        skies.append(polish_sky.sky_bmps(name))
    if la_day:
        sys.path.insert(0, os.path.join(HERE, "..", "design"))
        import la_day_sky
        skies.append(la_day_sky.la_day_bmps())
    for e in extra or []:                              # M3: another Driver 2 city's skies (Havana: day, night, rain)
        skies.append(e)
    return polish_sky.write_skybin(skies)


def minimap_params(lev_path: str):
    """A level with Driver 2's overhead map (convert.py CHI_POLISH_MAP=1, C12) carries an
    OVERLAYMAP lump that is not LA's: its frame for the exe's CITY 3 minimap entry, else None."""
    from levfile import Lev
    def lump(path):
        lev = Lev.parse(open(path, "rb").read())
        for sec in (lev.loadtime, lev.inmem):
            try:
                return sec.get(24).data
            except Exception:
                pass
    data = lump(lev_path)
    if data == lump(inputs.path("d1_LA.lev")):
        return None
    import polish_map
    stored = polish_map.stored_params(data)            # C12 r2: the frame the level's lump was built with
    if stored:
        return stored
    from d2overlay import Overlay
    # a lump without a stored frame comes from a level converted before 16.10. 19:xx: its tiles were built with the
    # old defaults (F 1.5, no nudge), not with today's C12 defaults; the env still overrides
    if "CHI_POLISH_MAP_F" not in os.environ:
        import importlib
        saved = {k: os.environ.get(k) for k in ("CHI_POLISH_MAP_F", "CHI_POLISH_MAP_NUDGE")}
        os.environ["CHI_POLISH_MAP_F"] = "1.5"
        os.environ.setdefault("CHI_POLISH_MAP_NUDGE", "0,0")
        try:
            importlib.reload(polish_map)
            return polish_map.params(Overlay(inputs.path(__import__("cityprofile").P.lev_day)))
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            importlib.reload(polish_map)
    return polish_map.params(Overlay(inputs.path(__import__("cityprofile").P.lev_day)))


def car_set_city(lev_path: str) -> int:
    """C51: the Driver 1 city whose car set (lump 28) a converted level carries, found by the lump size
    (the converter only renumbers texture pages in it); its CITY index picks the damage zone tables."""
    from levfile import Lev
    size = len(Lev.parse(open(lev_path, "rb").read()).loadtime.get(28).data)
    for name, city in (("LA", 3), ("MIAMI", 0), ("FRISCO", 1), ("NEWYORK", 5)):
        if len(Lev.parse(inputs.read("d1_%s.lev" % name)).loadtime.get(28).data) == size:
            return city
    return 3


def stable_pages_end(lev_path: str) -> int:
    """C45: <lev>.stable.json (Polish, CHI_POLISH_SHAREDPAGES) lists the area pages with one content in
    every area that lists them; they come first. The engine skips a resident page below the returned
    index, so every area page index at or above it must be per-area, and below it stable. 0 = none."""
    import json
    path = lev_path + ".stable.json"
    if not os.path.exists(path):
        return 0
    stable = set(json.load(open(path))["stable_pages"])
    if not stable:
        return 0
    from levfile import Lev
    from mapinfo import SpoolInfo, SPOOLINFO
    lev = Lev.parse(open(lev_path, "rb").read())
    sp = SpoolInfo.parse(lev.inmem.get(SPOOLINFO).data)
    area_pages = {p for tp in sp.area_tpages for p in tp if p != 0xFF}
    end = max(stable) + 1
    bad = sorted(p for p in area_pages if (p < end) != (p in stable))
    if bad:
        raise SystemExit("stable pages %s are not the area pages below %d (mixed: %s)" % (sorted(stable), end, bad))
    return end


def extent_bytes(lba: int, size: int) -> bytes:
    return struct.pack("<I", lba) + struct.pack(">I", lba) + struct.pack("<I", size) + struct.pack(">I", size)


MISSION_BLK_LBA = 63177                         # DRIVER/MISSIONS/MISSION.BLK
LA_START = (376863, -217530)                    # mission opcode 0x13 player start (x, z)
# Driver 2 coordinates (a road tile among the tallest blocks, clear of collision
# boxes); converted to the scaled Driver 1 world with worldscale.to_d1.
CHICAGO_START_D2 = (tuple(int(v) for v in os.environ["CHI_START"].split(","))
                    if os.environ.get("CHI_START") else tuple(__import__("cityprofile").P.start_d2))
CHICAGO_START = worldscale.to_d1(*CHICAGO_START_D2)


FRONTEND_LBA, FRONTEND_BASE = 88, 0x801C0000   # FRONTEND.BIN, loaded at 0x801C0000 (QA-3)
MENU_ADDR = 0x9F082110                          # driver_chicago.c MENU_ADDR: row table (9 rows), labels
MENU_LIST = MENU_ADDR + 0xC0                    # driver_chicago.c MENU_LIST: the drawn struct list (two pages)


def menu_patches():
    """Take a Ride city menu with a 5th row CHICAGO (FRONTEND.BIN, disc user data). The row
    table moves to mod memory (the plugin fills 5 rows there: the overlay's table sits right
    before the cursor and the label/picture lists), the label list too (5 entries), the row
    count 4 -> 5 (table init 0x801C2644, label loop). The 5th row struct goes where the
    struct list ended (0x801CE038, y 370), the terminator into the old table, and the
    label text into the old table's rows."""
    import exe_patches
    with open(DISC_BIN, "rb") as f:
        raw = b""
        for k in range(39):
            f.seek((FRONTEND_LBA + k) * 2352 + 24); raw += f.read(2048)
    word = lambda a: struct.unpack_from("<I", raw, a - FRONTEND_BASE)[0]
    lo = MENU_ADDR & 0xFFFF
    code = [  # (address, expected instruction, new instruction)
        (0x801C41DC, "lui a0, 0x1d", "lui a0, 0x9F08"),
        (0x801C41E0, "addiu a0, a0, -0x1fb8", "addiu a0, a0, %#x" % lo),
        (0x801C41E4, "addiu a1, zero, 4", "addiu a1, zero, 9"),
        (0x801C4238, "lui v1, 0x1d", "lui v1, 0x9F08"),
        (0x801C4240, "addiu a2, v1, -0x1f64", "addiu a2, v1, %#x" % (lo + 0x50)),
        (0x801C4268, "slti v0, a0, 4", "slti v0, a0, 5"),
        (0x801C4374, "lui s2, 0x1d", "lui s2, 0x9F08"),
        (0x801C4384, "addiu a0, s2, -0x1fb8", "addiu a0, s2, %#x" % lo),
        # the drawn struct list (header + rows): base s0 -> mod memory, written by the plugin per page
        (0x801C435C, "lui s0, 0x1d", "lui s0, 0x9F08"),
        (0x801C4368, "addiu a1, s0, -0x2018", "addiu a1, s0, %#x" % (MENU_LIST & 0xFFFF)),
        (0x801C43B0, "addiu a0, s0, -0x2018", "addiu a0, s0, %#x" % (MENU_LIST & 0xFFFF)),
    ]
    words = []
    for a, old, new in code:
        o, n = exe_patches.asm(a, [old])[0], exe_patches.asm(a, [new])[0]
        if word(a) != o:
            raise SystemExit("FRONTEND %08X: %08X, expected %s" % (a, word(a), old))
        words.append((a, struct.pack("<I", o), struct.pack("<I", n), new))
    data = [
        (0x801CE038, struct.pack("<I", 0xFFFFFFFF), struct.pack("<I", 0x0172001A), "5th row struct: y 370, x 26"),
        (0x801CE048, raw[0xE048:0xE058], struct.pack("<4I", 0xFFFFFFFF, 0, 0, 0xFFFFFFFF), "struct list terminator"),
        (0x801CE058, raw[0xE058:0xE060], b"Chicago\0", "5th row label"),
    ]
    out = []
    for a, old, new, note in words + data:
        if raw[a - FRONTEND_BASE: a - FRONTEND_BASE + len(old)] != old:
            raise SystemExit("FRONTEND %08X differs from the expected bytes" % a)
        out += ["# FRONTEND %08X: %s" % (a, note), "[[patch]]", 'feature = "chicago-slot"', 'target = "disc_user"',
                "offset = %d" % (FRONTEND_LBA * 2048 + a - FRONTEND_BASE),
                'expected = "%s"' % hexbytes(old), 'replace = "%s"' % hexbytes(new), ""]
    return out


def start_patches():
    """Move every LA mission start (opcode 0x13 x z) to downtown Chicago."""
    with open(DISC_BIN, "rb") as f:
        f.seek(MISSION_BLK_LBA * 2352)
        raw = f.read(40 * 2352)
    blk = b"".join(raw[k * 2352 + 24: k * 2352 + 24 + 2048] for k in range(40))
    want = struct.pack("<ii", *LA_START)
    out = []
    at = blk.find(want)
    while at != -1:
        if struct.unpack_from("<i", blk, at - 4)[0] == 0x13:
            out += ["# MISSION.BLK +0x%X: player start (opcode 0x13) LA -> Chicago downtown" % at,
                    "[[patch]]", 'feature = "chicago-la"', 'target = "disc_user"',
                    "offset = %d" % (MISSION_BLK_LBA * 2048 + at),
                    'expected = "%s"' % hexbytes(want),
                    'replace = "%s"' % hexbytes(struct.pack("<ii", *CHICAGO_START)), ""]
        at = blk.find(want, at + 1)
    if not out:
        raise SystemExit("LA start position not found in MISSION.BLK")
    return out


def city_assets(day, night, adir, xd_src=None):
    """M3: the per-city car / specials / damage / cosmetics assets of one Driver 2 city into adir (assets/ for Chicago,
    assets/havana/ for Havana). Returns (cars, d2ply): the car-set CITY word (day | night << 8 | 0x10000) and whether the
    levels carry Driver 2 player cars. Body moved unchanged from main() (Chicago's package stays byte-identical)."""
    xd_src = xd_src or {}
    args = argparse.Namespace(chicago=day, night=night)
    # C42 step 1: a level with Driver 2 traffic cars carries <lev>.dmg.bin (polish_cars damage blob:
    # civ verts 900 B at 0, civ polys 1260 B at 2100); its civ part goes into the package and the
    # level's car-set city becomes 4 (the exe's table entry 4 points at the plugin-written copy)
    dmg_asset = os.path.join(adir, "dmg_civ.bin")
    # C42 engine step (17.10.): an all-Driver 2 level (CHI_POLISH_D2CARS=1) carries 5040 B = civ 2160 + player rows
    # (verts 4 x 300 + polys 4 x 420) -> assets/dmg_player.bin (the plugin points player table entry 4 at it)
    ply_asset = os.path.join(adir, "dmg_player.bin")
    d2ply = {}
    d2civ = {}
    for tag, lev_path in (("day", args.chicago), ("night", args.night)):
        dmg = [q for q in (lev_path + ".dmg.bin", os.path.splitext(lev_path)[0] + ".dmg.bin")
               if os.path.exists(q)] if lev_path else []
        if dmg:                                  # polish_cars names it <name>.dmg.bin
            blob = open(dmg[0], "rb").read()
            if len(blob) == 2160:                # polish_carmix: the civ rows only (verts 900 + polys 1260)
                d2civ[tag] = blob
            elif len(blob) == 5040:              # convert.py, car set d2: civ 2160 + player 2880
                d2civ[tag], d2ply[tag] = blob[:2160], blob[2160:]
            elif len(blob) == 6480:              # C42 r3 (b), six resident models: civ 5 x (300 + 420) + player 2880
                d2civ[tag], d2ply[tag] = blob[:3600], blob[3600:]
            elif len(blob) >= 3360:
                d2civ[tag] = blob[0:900] + blob[2100:3360]
            else:
                raise SystemExit("%s: unexpected damage blob size %d" % (dmg[0], len(blob)))
    if d2civ:
        if len(set(d2civ.values())) > 1:
            raise SystemExit("day and night levels carry different Driver 2 civ damage tables")
        open(dmg_asset, "wb").write(next(iter(d2civ.values())))
    elif os.path.exists(dmg_asset):
        os.remove(dmg_asset)
    if d2ply:
        if len(set(d2ply.values())) > 1 or len(d2ply) != len(d2civ):
            raise SystemExit("day and night levels carry different Driver 2 player cars (build both with CHI_POLISH_D2CARS=1)")
        open(ply_asset, "wb").write(next(iter(d2ply.values())))
        print("d2 player cars: player damage rows (2880 B) -> assets/dmg_player.bin")
    elif os.path.exists(ply_asset):
        os.remove(ply_asset)
    box_asset = os.path.join(adir, "car_boxes.bin")   # C42E: player collision boxes (convert .box.bin)
    box_src = [q + ".box.bin" for q in (args.chicago, args.night) if q and os.path.exists(q + ".box.bin")]
    if d2ply and box_src:
        shutil.copyfile(box_src[0], box_asset)
    elif os.path.exists(box_asset):
        os.remove(box_asset)
    lvl_asset = os.path.join(adir, "dmg_levels.bin")   # C42 r3: D2 per-polygon damage kinds (.lvl.bin)
    lvl_src = [q + ".lvl.bin" for q in (args.chicago, args.night) if q and os.path.exists(q + ".lvl.bin")]
    if d2ply and lvl_src:
        shutil.copyfile(lvl_src[0], lvl_asset)
    elif os.path.exists(lvl_asset):
        os.remove(lvl_asset)
    for tag_, x_ in xd_src.items():                 # C101: the xd levels' specials (area placement differs)
        if d2ply and os.path.exists(x_ + ".spc.bin"):
            shutil.copyfile(x_ + ".spc.bin", os.path.join(adir, "specials_xd_%s.bin" % tag_))
    for tag_, lev_ in (("day", args.chicago), ("night", args.night)):   # C42 r3 (c): regional specials per level
        spc_asset = os.path.join(adir, "specials_%s.bin" % tag_)   # (their area-page placement differs)
        if d2ply and lev_ and os.path.exists(lev_ + ".spc.bin"):
            shutil.copyfile(lev_ + ".spc.bin", spc_asset)
        elif os.path.exists(spc_asset):
            os.remove(spc_asset)
        sps_asset = os.path.join(adir, "spcshadow_%s.bin" % tag_)   # C102: the specials' shadow quads (SPS1)
        if d2ply and lev_ and os.path.exists(lev_ + ".sps.bin"):
            shutil.copyfile(lev_ + ".sps.bin", sps_asset)
        elif os.path.exists(sps_asset):
            os.remove(sps_asset)
        spt_asset = os.path.join(adir, "spctwist_%s.bin" % tag_)   # C82: the specials' twistRateY (Polish SPT1)
        if d2ply and lev_ and os.path.exists(lev_ + ".spt.bin"):
            shutil.copyfile(lev_ + ".spt.bin", spt_asset)
        elif os.path.exists(spt_asset):
            os.remove(spt_asset)
        spd_asset = os.path.join(adir, "specdmg_%s.bin" % tag_)   # Q45 B: specials' DentCar level rows
        if d2ply and lev_ and os.path.exists(lev_ + ".spd.bin"):
            shutil.copyfile(lev_ + ".spd.bin", spd_asset)
        elif os.path.exists(spd_asset):
            os.remove(spd_asset)
    sfx_asset = os.path.join(adir, "car_sfx.bin")      # C42 r3 (e): Driver 2 car engine sounds
    if d2ply and os.environ.get("CHI_CAR_SFX", "1") != "0":
        open(sfx_asset, "wb").write(car_sfx_v2() if CAR_SFX_V2 else car_sfx())
        print("car sounds: Driver 2 banks %s -> %s" % (CAR_SFX_BANKS, sfx_asset))
    elif os.path.exists(sfx_asset):
        os.remove(sfx_asset)
    whl_asset = os.path.join(adir, "car_wheels.bin")   # C42 r3: wheel size per car (convert .whl.bin)
    whl_src = [q + ".whl.bin" for q in (args.chicago, args.night) if q and os.path.exists(q + ".whl.bin")]
    if d2ply and whl_src:
        shutil.copyfile(whl_src[0], whl_asset)
    elif os.path.exists(whl_asset):
        os.remove(whl_asset)
    cday = 4 if "day" in d2civ else car_set_city(args.chicago)
    cnight = 4 if "night" in d2civ else (car_set_city(args.night) if args.night else 3)
    cars = cday | cnight << 8 | 0x10000
    # C42 / C53: a car set 4 level (Driver 2 cars) needs its cosmetics rows (8 x 100 B: wheels, lights;
    # Polish's polish_cosmetics.py), written by the plugin to 0x800A16A0 where the exe's base table points
    for tag, cset in (("day", cday), ("night", cnight)):
        cos_asset = os.path.join(adir, "cosmetics_%s.bin" % tag)
        if cset == 4:
            src = os.environ.get("CHI_COSMETICS_" + tag.upper())
            lev_path = args.chicago if tag == "day" else args.night
            if not src and lev_path and os.path.exists(lev_path + ".cos.bin"):
                src = lev_path + ".cos.bin"          # C42 engine step: the level's own rows (convert.py, car set d2)
            if not src:                      # Option A: made from the player's discs (D2 LCF + LEV, D1 exe)
                import polish_cosmetics
                gen = os.path.join(inputs.CACHE, "package")
                os.makedirs(gen, exist_ok=True)
                src = polish_cosmetics.build(inputs.path(__import__("cityprofile").P.lcf), gen)[0][tag]
            if not os.path.exists(src) or os.path.getsize(src) not in (800, 1000):   # 8 rows, 10 with six resident models (c42m)
                raise SystemExit("car set 4 (%s) needs 800- or 1000-B cosmetics rows: %s" % (tag, src))
            shutil.copyfile(src, cos_asset)
        elif os.path.exists(cos_asset):
            os.remove(cos_asset)
    print("car sets (CITY of the damage tables): day %d, night %d" % (cars & 0xFF, (cars >> 8) & 0xFF))
    return cars, d2ply


HAVANA_DIR = "havana"                           # M3: assets/havana/ = Havana's per-city assets (plugin: driver_chicago.c)


def city_assets_mode(adir: str, day: str, night: str | None, out_json: str) -> None:
    """M3 (Havana slot): run as CHI_CITY=<city> build_package.py --city-assets ADIR --day X [--night Y] --json OUT.
    Writes the city's assets into ADIR (car / specials / damage / cosmetics rows, Driver 2 surface, preview) and a JSON
    with what the Chicago run puts into the city's slot sidecar and the shared SKY.BIN / MUSIC.BIN."""
    import json, pickle, polish_sky
    P = __import__("cityprofile").P
    os.makedirs(adir, exist_ok=True)
    xd_src = {}
    if os.environ.get("CHI_XD_LEVELS") == "1" and night:   # C101 pair of this city (<name>_xd_<day|night>.lev)
        for tag_, lev_ in (("day", day), ("night", night)):
            x = lev_.replace("_%s.lev" % tag_, "_xd_%s.lev" % tag_)
            if x != lev_ and os.path.exists(x):
                xd_src[tag_] = x
        if len(xd_src) != 2:
            xd_src = {}
    for tag_ in ("day", "night"):
        q = os.path.join(adir, "specials_xd_%s.bin" % tag_)
        if os.path.exists(q) and tag_ not in xd_src:
            os.remove(q)
    cars, d2ply = city_assets(day, night, adir, xd_src)
    mm = minimap_params(day) if os.environ.get("CHI_MAP_FRAME", "1") != "0" else None
    surf = os.path.join(adir, "d2_surface.bin")
    if os.environ.get("CHI_D2_SURF", "1") != "0":
        import d2surf_asset
        open(surf, "wb").write(d2surf_asset.build(inputs.d2_lev()))
    elif os.path.exists(surf):
        os.remove(surf)
    prev_asset = os.path.join(adir, "preview.bin")
    prev_src = os.path.join(HERE, "..", "design", "previews", "out", P.name)
    if os.environ.get("CHI_PREVIEW", "1") != "0" and os.path.exists(prev_src + ".4bit"):
        open(prev_asset, "wb").write(open(prev_src + ".4bit", "rb").read() + open(prev_src + ".clut", "rb").read())
    elif os.path.exists(prev_asset):
        os.remove(prev_asset)
    skies = [polish_sky.sky_bmps(n) for n in ("day", "night", "rain")] if P.sky_raw else []
    pickle.dump(skies, open(out_json + ".skies", "wb"))
    start = worldscale.to_d1(*P.start_d2)
    json.dump({"city": P.name, "cars": cars, "d2ply": bool(d2ply), "mm": list(mm) if mm else None,
               "stable_end": stable_pages_end(day), "start": list(start), "water": P.water_level, "rot": P.start_rot,
               "xd": xd_src}, open(out_json, "w"))
    print("%s assets -> %s (cars 0x%X, start %s)" % (P.label, adir, cars, start))


# M3 / Q68 (user 68 B): the other Driver 2 cities, virtual cities in CITY 3 like Chicago, in D2 city id order (plugin
# driver_chicago.c s_d2c: 1 Havana, 2 Las Vegas, 3 Rio). Build switch per city: CHI_<KEY>_DAY (+ CHI_<KEY>_NIGHT) =
# converted levels -> assets/<dir>/ + <dir>.lev / <dir>_night.lev (+ _xd pair with CHI_XD_LEVELS=1) after the last file,
# skies appended to SKY.BIN, D2 songs at the city's fixed song slots (Havana 10 / 11, Las Vegas 12 / 13, Rio 14 / 15).
# Without a city's switch nothing of it is written (byte-identical package).
EXTRA_CITIES = [("HAVANA", HAVANA_DIR, "CHI_HAVANA"), ("VEGAS", "vegas", "CHI_VEGAS"), ("RIO", "rio", "CHI_RIO")]


def extra_city_assets(name, dirn, key):
    """CHI_<key>_DAY (+ _NIGHT) -> assets/<dirn>/ (a subprocess with CHI_CITY=<name>: the converter modules bind the city
    profile at import). None without the switch."""
    day = os.environ.get(key + "_DAY")
    if not day:
        return None
    import json, pickle, subprocess
    adir = os.path.join(PKG, "assets", dirn)
    out = os.path.join(adir, "city.json")
    os.makedirs(adir, exist_ok=True)
    env = dict(os.environ, CHI_CITY=name)
    for k in ("CHI_START", "CHI_COSMETICS_DAY", "CHI_COSMETICS_NIGHT", "CHI_LA_DAY_LEV", "CHI_NIGHT"):
        env.pop(k, None)
    cmd = [sys.executable, os.path.abspath(__file__), "--city-assets", adir, "--day", day, "--json", out]
    if os.environ.get(key + "_NIGHT"):
        cmd += ["--night", os.environ[key + "_NIGHT"]]
    subprocess.run(cmd, cwd=HERE, env=env, check=True)
    info = json.load(open(out))
    info["skies"] = pickle.load(open(out + ".skies", "rb"))
    os.remove(out + ".skies")
    info["day"], info["night"] = day, os.environ.get(key + "_NIGHT")
    info["name"], info["dir"] = name, dirn
    return info


def extra_cities():
    """[(dirn, info)] of the packaged extra cities in id order; drops the asset folders of the others."""
    got = []
    for name, dirn, key in EXTRA_CITIES:
        info = extra_city_assets(name, dirn, key)
        if info:
            got.append((dirn, info))
        elif os.path.isdir(os.path.join(PKG, "assets", dirn)):
            shutil.rmtree(os.path.join(PKG, "assets", dirn))
    return got

def main():
    if not os.path.isfile(EXE):
        raise SystemExit("missing %s (copy of the stock boot EXE)" % EXE)
    ap = argparse.ArgumentParser()
    ap.add_argument("--chicago", help="converted Chicago LEV (replaces Los Angeles)")
    ap.add_argument("--slot", action="store_true", help="Chicago as its own city (LA restored); also CHI_SLOT=1")
    ap.add_argument("--night", default=os.environ.get("CHI_NIGHT"), help="with --slot: converted NIGHT Chicago LEV (Day/Night screen picks it); also CHI_NIGHT")
    ap.add_argument("--city-assets", help="M3: (with CHI_CITY) write one Driver 2 city's assets into this dir and exit")
    ap.add_argument("--day", help="--city-assets: the city's converted day LEV")
    ap.add_argument("--json", help="--city-assets: info file for the Chicago run")
    ap.add_argument("--install", action="store_true",
                    help="write the dev client's package source mods/preloaded (build-dev installs only); "
                         "without it a CHI_PKG_DIR target is required")
    args = ap.parse_args()
    if args.city_assets:
        city_assets_mode(args.city_assets, args.day, args.night, args.json)
        return
    # 13.10.: a test script without CHI_PKG_DIR overwrote the preloaded package (the source every
    # rebuild copies into its build dir): writing there now needs --install
    if not os.environ.get("CHI_PKG_DIR") and not args.install:
        raise SystemExit("build_package: no CHI_PKG_DIR (test copy) and no --install: refusing to write %s" % PKG)

    os.makedirs(PKG, exist_ok=True)
    out = [
        "format_version = 5",
        'id = "driver.chicago"',
        'version = "0.1.0"',
        'channel = "developer"',
        'name = "Driver - Chicago (work in progress)"',
        'author = "local"',
        'description = "Local-only work in progress: engine support and test data for porting Driver 2\'s Chicago into Driver 1."',
        'resolver = "declarative"',
        'save_compatibility = "shared"',
        "",
        "[[target]]",
        'game_id = "SLUS-00842"',
        'disc_sha256 = "%s"' % sha256_file(DISC_BIN),
        "",
        "[[feature]]",
        'id = "model-table"',
        'name = "Engine Extensions (Chicago)"',
        'description = "Lets levels use up to 2048 models (Driver 1 allows 800) and keeps the city object buffer in extra memory. Needed by the Chicago level; harmless for the original cities. Keep it on: the game code is compiled with it, so turning it off runs those parts slower."',
        'group = "Chicago"',
        "default_enabled = true",
        "",
        "[[plugin]]",
        'feature = "model-table"',
        'id = "driver.model-table"',
        "",
        exe_patches.toml(EXE, "model-table"),
    ]
    # The package's engine patches must be the ones the native code was generated from:
    # every patched word must already be in disc/SLUS_008.42 (exe_patches --apply, then
    # psxrecomp generate + rebuild). A stale disc exe means a package/engine mismatch.
    plist = exe_patches.all_patches(EXE)
    # CHI_PATCHED_EXE: the recompiler input of an isolated root (opt-in patch groups such as
    # CHI_C45_SKIP=1 must be checked against that exe, not the shared disc/SLUS_008.42)
    patched = os.environ.get("CHI_PATCHED_EXE") or os.path.join(APP, "disc", "SLUS_008.42")
    img, base = exe_patches.load_exe(patched)
    stale = [pc for pc, _old, new, _n in plist
             if struct.unpack_from("<I", img, pc - base)[0] != new]
    if stale:
        raise SystemExit("%s lacks %d of the %d current engine patches (first at %08X): run "
                         "exe_patches.py --apply, then psxrecomp generate and rebuild"
                         % (patched, len(stale), len(plist), stale[0]))
    print("engine patches: %d (disc exe matches)" % len(plist))

    if args.chicago and (args.slot or os.environ.get("CHI_SLOT")):
        extras = extra_cities()                          # M3: Havana / Las Vegas / Rio (build switches CHI_<CITY>_DAY / _NIGHT)
        # Chicago as its own city (2026-10-13): LA.LEV and LA's starts stay original; the
        # plugin (driver.chicago-slot) puts Chicago's disc position into the game's level
        # table entry 3 (0x800BE0A4 + 96: 4 x (byte position, size) from the LEV header,
        # as the boot scan 0x800503xx computes them) when Chicago is chosen, and moves the
        # Take a Ride start in the mission script. Sidecar: 8 + 4 little-endian ints.
        asset = os.path.join(PKG, "assets", "chicago.lev")
        os.makedirs(os.path.dirname(asset), exist_ok=True)
        shutil.copyfile(args.chicago, asset)
        hdr = struct.unpack_from("<8I", open(asset, "rb").read(40), 8)
        entry = []
        for k in range(4):
            entry += [CHICAGO_LBA * 2048 + hdr[2 * k], hdr[2 * k + 1]]
        # night Chicago (optional): right after the day file, on a 1000-sector boundary;
        # the sidecar then carries its 8 entry words too (20 ints)
        night_asset = os.path.join(PKG, "assets", "chicago_night.lev")
        night_lba = CHICAGO_LBA + (os.path.getsize(asset) // 2048 // 1000 + 1) * 1000
        night = []
        if args.night:
            shutil.copyfile(args.night, night_asset)
            nh = struct.unpack_from("<8I", open(night_asset, "rb").read(40), 8)
            for k in range(4):
                night += [night_lba * 2048 + nh[2 * k], nh[2 * k + 1]]
        elif os.path.exists(night_asset):
            os.remove(night_asset)
        # minimap frame (C12) and Chicago's skies (C10, a relocated SKY.BIN with 3 more skies:
        # Driver 1's 13 stay byte-identical; CHI_SKY=0 keeps the original)
        mm = minimap_params(args.chicago) if os.environ.get("CHI_MAP_FRAME", "1") != "0" else None
        print("minimap: %s" % ("Driver 2's map, CITY 3 frame %s" % (mm,) if mm else "LA's (level has LA's overlay)"))
        sky_asset = os.path.join(PKG, "assets", "sky.bin")
        sky = os.environ.get("CHI_SKY", "1") != "0"
        last = night_lba if night else CHICAGO_LBA
        last_size = os.path.getsize(night_asset if night else asset)
        sky_lba = last + (last_size // 2048 // 1000 + 1) * 1000
        if sky:
            open(sky_asset, "wb").write(chicago_skybin(la_day=bool(os.environ.get("CHI_LA_DAY_LEV")),
                                                       extra=[sk for _d, e in extras for sk in e["skies"]] or None))
            sky_off, sky_old = iso_record([b"DRIVER", b"DATA", b"SKY.BIN;1"])
        elif os.path.exists(sky_asset):
            os.remove(sky_asset)
        # Chicago music (milestone 2, Polish): a relocated MUSIC.BIN with D1's songs 0-7 byte-identical and
        # D2 Chicago day / night as songs 8 / 9 (the song-select stub plays them for Chicago only)
        music_asset = os.path.join(PKG, "assets", "music.bin")
        music = os.environ.get("CHI_POLISH_MUSIC", "1") != "0"   # C60 (16.10.): default on (user R23); 0 = off
        music_lba = sky_lba + ((os.path.getsize(sky_asset) // 2048 // 1000 + 1) * 1000 if sky else 0)
        if music:
            # Option A: built here from the player's discs (polish_music: D1 songs 0-7 + D2 Chicago day/night);
            # CHI_MUSIC_BIN = a ready file instead (experiments)
            if os.environ.get("CHI_MUSIC_BIN"):
                shutil.copyfile(os.environ["CHI_MUSIC_BIN"], music_asset)
            else:
                import polish_music
                d2m = inputs.read("d2_MUSIC.BIN")
                mus = polish_music.chicago_music(inputs.read("d1_MUSIC.BIN"), d2m)
                if extras:                               # M3: + the D2 cities' songs at fixed slots: Havana 10 / 11,
                    import cityprofile as cp_            # Las Vegas 12 / 13, Rio 14 / 15 (up to the last packaged city)
                    s1_, s2_ = polish_music.songs(inputs.read("d1_MUSIC.BIN")), polish_music.songs(d2m)
                    last_ = max(k for k, (n_, _d, _k) in enumerate(EXTRA_CITIES) if any(e["name"] == n_ for _x, e in extras))
                    add_ = [s2_[2], s2_[6]]               # Chicago 8 / 9 (as chicago_music)
                    for n_, _d, _k in EXTRA_CITIES[:last_ + 1]:
                        add_ += [s2_[cp_.PROFILES[n_].songs[0]], s2_[cp_.PROFILES[n_].songs[1]]]
                    mus = polish_music.pack(s1_ + add_)
                open(music_asset, "wb").write(mus)
            music_off, music_old = iso_record([b"DRIVER", b"SOUND", b"MUSIC.BIN;1"])
            print("music: Chicago songs 8/9 (MUSIC.BIN relocated to LBA %d)" % music_lba)
        elif os.path.exists(music_asset):
            os.remove(music_asset)
        # C63 LA by Day (17.10.): an LA day level (Polish's polish_laday: LA.LEV with day textures), right after the
        # last relocated file on a 1000-sector boundary; the sidecar carries its 8 entry words (words 29-36) and the
        # plugin points level table entry 3 at it when "Los Angeles - Day" is chosen. CHI_LA_DAY_LEV=path (opt-in)
        laday_asset = os.path.join(PKG, "assets", "la_day.lev")
        tail_lba, tail_file = ((music_lba, music_asset) if music else (sky_lba, sky_asset) if sky
                               else (last, night_asset if night else asset))
        laday_lba = tail_lba + (os.path.getsize(tail_file) // 2048 // 1000 + 1) * 1000
        laday = []
        if os.environ.get("CHI_LA_DAY_LEV"):
            shutil.copyfile(os.environ["CHI_LA_DAY_LEV"], laday_asset)
            lh = struct.unpack_from("<8I", open(laday_asset, "rb").read(40), 8)
            for k in range(4):
                laday += [laday_lba * 2048 + lh[2 * k], lh[2 * k + 1]]
            print("LA day: %s at LBA %d" % (os.path.basename(os.environ["CHI_LA_DAY_LEV"]), laday_lba))
        elif os.path.exists(laday_asset):
            os.remove(laday_asset)
        # C101 (25.10.): the 'Extra draw distance' level pair (Polish CHI_POLISH_XDRAW: native 27 x 27 PVS, wider area
        # sets; only .lev and .spc.bin differ). CHI_XD_LEVELS=1: <name>_xd_<day|night>.lev next to the given levels go
        # into the package after the last relocated file; the sidecar carries their 16 entry words (words 37-52) and the
        # plugin loads them while the feature is on. Off (default): package unchanged.
        xd_assets, xd_entries, xd_src = [], [], {}
        if os.environ.get("CHI_XD_LEVELS") == "1" and args.night:
            for tag_, lev_ in (("day", args.chicago), ("night", args.night)):
                x = lev_.replace("_%s.lev" % tag_, "_xd_%s.lev" % tag_)
                if x == lev_ or not os.path.exists(x):
                    raise SystemExit("CHI_XD_LEVELS: %s not found" % x)
                xd_src[tag_] = x
            prev_lba, prev_file = (laday_lba, laday_asset) if laday else (tail_lba, tail_file)
            for tag_ in ("day", "night"):
                xa = os.path.join(PKG, "assets", "chicago_xd_%s.lev" % tag_)
                shutil.copyfile(xd_src[tag_], xa)
                xl = prev_lba + (os.path.getsize(prev_file) // 2048 // 1000 + 1) * 1000
                xh = struct.unpack_from("<8I", open(xa, "rb").read(40), 8)
                for k in range(4):
                    xd_entries += [xl * 2048 + xh[2 * k], xh[2 * k + 1]]
                xd_assets.append((xl, xa))
                prev_lba, prev_file = xl, xa
                print("extra-draw level %s: %s at LBA %d" % (tag_, os.path.basename(xd_src[tag_]), xl))
        else:
            for tag_ in ("day", "night"):
                for xa in (os.path.join(PKG, "assets", "chicago_xd_%s.lev" % tag_),
                           os.path.join(PKG, "assets", "specials_xd_%s.bin" % tag_)):
                    if os.path.exists(xa):
                        os.remove(xa)
        # M3: each extra city's day / night levels (+ C101 extra-draw pair) after the last relocated file, on 1000-sector
        # boundaries (their 8 entry words each go into assets/<dir>/slot.bin)
        city_levels = {}                                  # dirn -> (entry, night, xd)
        if xd_assets:
            prev_lba, prev_file = xd_assets[-1][0], xd_assets[-1][1]
        else:
            prev_lba, prev_file = (laday_lba, laday_asset) if laday else (tail_lba, tail_file)
        hav_assets = []                                   # (lba, file) of every extra city's level (overlays below)
        for dirn, hav in extras:
            hav_entry, hav_night, hav_xd = [], [], []
            for tag_, src_ in (("day", hav["day"]), ("night", hav["night"])):
                if not src_:
                    continue
                ha = os.path.join(PKG, "assets", "%s%s.lev" % (dirn, "" if tag_ == "day" else "_night"))
                shutil.copyfile(src_, ha)
                hl = prev_lba + (os.path.getsize(prev_file) // 2048 // 1000 + 1) * 1000
                hh = struct.unpack_from("<8I", open(ha, "rb").read(40), 8)
                ent = []
                for k in range(4):
                    ent += [hl * 2048 + hh[2 * k], hh[2 * k + 1]]
                (hav_entry if tag_ == "day" else hav_night).extend(ent)
                hav_assets.append((hl, ha))
                prev_lba, prev_file = hl, ha
                print("%s %s: %s at LBA %d" % (hav["name"].capitalize(), tag_, os.path.basename(src_), hl))
            for tag_ in ("day", "night") if hav.get("xd") else ():   # its C101 extra-draw pair (slot words 37-52)
                ha = os.path.join(PKG, "assets", "%s_xd_%s.lev" % (dirn, tag_))
                shutil.copyfile(hav["xd"][tag_], ha)
                hl = prev_lba + (os.path.getsize(prev_file) // 2048 // 1000 + 1) * 1000
                hh = struct.unpack_from("<8I", open(ha, "rb").read(40), 8)
                for k in range(4):
                    hav_xd.extend([hl * 2048 + hh[2 * k], hh[2 * k + 1]])
                hav_assets.append((hl, ha))
                prev_lba, prev_file = hl, ha
                print("%s extra-draw %s: %s at LBA %d" % (hav["name"].capitalize(), tag_, os.path.basename(hav["xd"][tag_]), hl))
            city_levels[dirn] = (hav_entry, hav_night, hav_xd)
        for _n, dirn, _k in EXTRA_CITIES:
            if dirn in city_levels:
                continue
            for ha in ("%s.lev" % dirn, "%s_night.lev" % dirn, "%s_xd_day.lev" % dirn, "%s_xd_night.lev" % dirn):
                if os.path.exists(os.path.join(PKG, "assets", ha)):
                    os.remove(os.path.join(PKG, "assets", ha))
        # C37 phase 1 (17.10.): Driver 2's own road surface blocks for the plugin's MapHeight / FindSurfaceD2 hook
        # (d2surf_asset.py; host-only, ~2.2 MB). Default since the user's 'slopes 3' verdict (R31, 18.10.); CHI_D2_SURF=0 = off
        surf_asset = os.path.join(PKG, "assets", "d2_surface.bin")
        if os.environ.get("CHI_D2_SURF", "1") != "0" and args.chicago:
            import d2surf_asset
            open(surf_asset, "wb").write(d2surf_asset.build(inputs.d2_lev()))
            print("d2 surface: %d bytes" % os.path.getsize(surf_asset))
        elif os.path.exists(surf_asset):
            os.remove(surf_asset)
        # Chicago's own Take a Ride picture (Design, design/previews/out): 4-bit 128 x 232 + 16-colour CLUT; the
        # plugin shows it over LA2 while the Chicago row is highlighted (CHI_PREVIEW=0 keeps LA's picture)
        prev_asset = os.path.join(PKG, "assets", "chicago_preview.bin")
        prev_src = os.path.join(HERE, "..", "design", "previews", "out", __import__("cityprofile").P.name)
        if os.environ.get("CHI_PREVIEW", "1") != "0" and os.path.exists(prev_src + ".4bit"):
            blk, clut = open(prev_src + ".4bit", "rb").read(), open(prev_src + ".clut", "rb").read()
            if len(blk) not in (64 * 228, 64 * 232) or len(clut) != 32:   # 228 rows = LA2's quad; 232 cropped
                raise SystemExit("preview: unexpected sizes %d / %d" % (len(blk), len(clut)))
            open(prev_asset, "wb").write(blk + clut)
        elif os.path.exists(prev_asset):
            os.remove(prev_asset)
        stable_end = stable_pages_end(args.chicago)
        print("stable pages: below index %d (C45 skip-resident)" % stable_end if stable_end else "stable pages: none")
        # sidecar: entry 8, starts 4, night entry 8 (zeros: none), minimap 6 (zeros: LA's), flags (1 = sky),
        # stable-page end (C45: area pages below it have one content everywhere and may be skipped when resident)
        cars, d2ply = city_assets(args.chicago, args.night, os.path.join(PKG, "assets"), xd_src)
        with open(os.path.join(PKG, "assets", "chicago_slot.bin"), "wb") as f:
            f.write(struct.pack("<8I4i8I6I3I", *entry, *LA_START, *CHICAGO_START, *(night or [0] * 8),
                                *(mm or [0] * 6), (1 if sky else 0) | (2 if music else 0)
                                | (4 if sky and laday else 0), stable_end, cars))
            if laday or xd_entries:                      # C63: + LA day's 8 entry words (37 ints)
                f.write(struct.pack("<8I", *(laday or [0] * 8)))
            if xd_entries:                               # C101: + the extra-draw day / night entries (53 ints)
                f.write(struct.pack("<16I", *xd_entries))
        nsky = 13 + 3 + (1 if laday else 0)              # the first sky number after Chicago's (and LA day's)
        for dirn, hav in extras:                         # M3: each extra city's sidecar, chicago_slot.bin's layout (55 ints);
            hav_entry, hav_night, hav_xd = city_levels[dirn]   # flags: bit 0 sky, bit 1 music, bits 8-15 its first sky
            hflags = (1 | nsky << 8 if sky and hav["skies"] else 0) | (2 if music else 0)   # number (day, +1 night, +2 rain)
            with open(os.path.join(PKG, "assets", dirn, "slot.bin"), "wb") as f:
                f.write(struct.pack("<8I4i8I6I3I", *hav_entry, *LA_START, *hav["start"], *(hav_night or [0] * 8),
                                    *(hav["mm"] or [0] * 6), hflags, hav["stable_end"], hav["cars"]))
                f.write(struct.pack("<8I16I", *([0] * 8), *(hav_xd or [0] * 16)))
                f.write(struct.pack("<i", -int(hav["water"])))   # word 53: the city's water surface (y up)
                f.write(struct.pack("<i", int(hav.get("rot", 0))))   # word 54: the start heading (4096 = full turn)
            print("%s slot: skies from %d, cars 0x%X" % (hav["name"].capitalize(), nsky, hav["cars"]))
            nsky += len(hav["skies"]) if sky else 0
        out += [
            "[[feature]]",
            'id = "chicago-slot"',
            'name = "Chicago (own city, Los Angeles restored)"',
            'description = "Work in progress: Chicago from Driver 2 as its own city (5th Take a Ride row, with Day/Night). Los Angeles is the original again. Needs Engine Extensions (Chicago)."',
            'group = "Chicago"',
            "default_enabled = false",
            "",
            "[[plugin]]",
            'feature = "chicago-slot"',
            'id = "driver.chicago-slot"',
            "",
            "[[option]]",
            'feature = "chicago-slot"',
            'id = "city"',
            'label = "Take a Ride: the Los Angeles row starts"',
            'type = "choice"',
            'default = "chicago"',
            "",
            "[[option.choice]]",
            'value = "chicago"',
            'label = "Chicago"',
            "",
            "[[option.choice]]",
            'value = "la"',
            'label = "Los Angeles (original)"',
            "",
            "[[option]]",
            'feature = "chicago-slot"',
            'id = "menu"',
            'label = "Take a Ride city menu"',
            'type = "choice"',
            'default = "%s"' % ("pages" if os.environ.get("CHI_MENU_PAGES") == "1" else "classic"),
            "",
            "[[option.choice]]",
            'value = "classic"',
            'label = "Classic (Chicago as the 5th row)"',
            "",
            "[[option.choice]]",
            'value = "pages"',
            'label = "Two pages (Driver 1 / Driver 2 cities)"',
            "",
            "[[overlay]]",
            'feature = "chicago-slot"',
            'target = "disc_user"',
            "offset = %d" % (CHICAGO_LBA * 2048),
            'file = "assets/chicago.lev"',
            'sha256 = "%s"' % sha256_file(asset),
            "",
        ] + ([
            "[[overlay]]",
            'feature = "chicago-slot"',
            'target = "disc_user"',
            "offset = %d" % (night_lba * 2048),
            'file = "assets/chicago_night.lev"',
            'sha256 = "%s"' % sha256_file(night_asset),
            "",
        ] if night else []) + ([
            "[[overlay]]",
            'feature = "chicago-slot"',
            'target = "disc_user"',
            "offset = %d" % (sky_lba * 2048),
            'file = "assets/sky.bin"',
            'sha256 = "%s"' % sha256_file(sky_asset),
            "",
            "# DRIVER/DATA/SKY.BIN directory record -> the copy with Chicago's skies",
            "[[patch]]",
            'feature = "chicago-slot"',
            'target = "disc_user"',
            "offset = %d" % sky_off,
            'expected = "%s"' % hexbytes(sky_old),
            'replace = "%s"' % hexbytes(extent_bytes(sky_lba, os.path.getsize(sky_asset))),
            "",
        ] if sky else []) + ([
            "[[overlay]]",
            'feature = "chicago-slot"',
            'target = "disc_user"',
            "offset = %d" % (music_lba * 2048),
            'file = "assets/music.bin"',
            'sha256 = "%s"' % sha256_file(music_asset),
            "",
            "# DRIVER/SOUND/MUSIC.BIN directory record -> the copy with Chicago's songs 8 / 9",
            "[[patch]]",
            'feature = "chicago-slot"',
            'target = "disc_user"',
            "offset = %d" % music_off,
            'expected = "%s"' % hexbytes(music_old),
            'replace = "%s"' % hexbytes(extent_bytes(music_lba, os.path.getsize(music_asset))),
            "",
        ] if music else []) + ([
            "[[overlay]]",
            'feature = "chicago-slot"',
            'target = "disc_user"',
            "offset = %d" % (laday_lba * 2048),
            'file = "assets/la_day.lev"',
            'sha256 = "%s"' % sha256_file(laday_asset),
            "",
        ] if laday else []) + sum(([
            "[[overlay]]",
            'feature = "chicago-slot"',
            'target = "disc_user"',
            "offset = %d" % (xl * 2048),
            'file = "assets/%s"' % os.path.basename(xa),
            'sha256 = "%s"' % sha256_file(xa),
            "",
        ] for xl, xa in xd_assets + hav_assets), []) + menu_patches()
    elif args.chicago:
        asset = os.path.join(PKG, "assets", "chicago.lev")
        os.makedirs(os.path.dirname(asset), exist_ok=True)
        shutil.copyfile(args.chicago, asset)
        size = os.path.getsize(asset)
        rec_off, rec_old = dir_record(b"LA.LEV;1")
        out += [
            "[[feature]]",
            'id = "chicago-la"',
            'name = "Chicago (replaces Los Angeles)"',
            'description = "Work in progress: Chicago from Driver 2, converted for Driver 1 and loaded in place of Los Angeles. Needs Engine Extensions (Chicago). Start downtown; traffic and cops are not in yet."',
            'group = "Chicago"',
            "default_enabled = false",
            "",
            "[[overlay]]",
            'feature = "chicago-la"',
            'target = "disc_user"',
            "offset = %d" % (CHICAGO_LBA * 2048),
            'file = "assets/chicago.lev"',
            'sha256 = "%s"' % sha256_file(asset),
            "",
        ] + start_patches() + [
            "# DRIVER/LEVELS/LA.LEV directory record: extent (LE+BE) and size (LE+BE)",
            "[[patch]]",
            'feature = "chicago-la"',
            'target = "disc_user"',
            "offset = %d" % rec_off,
            'expected = "%s"' % hexbytes(rec_old),
            'replace = "%s"' % hexbytes(extent_bytes(CHICAGO_LBA, size)),
            "",
        ]

    path = os.path.join(PKG, "manifest.toml")
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    print("wrote", path)


if __name__ == "__main__":
    main()
