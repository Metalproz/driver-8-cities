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

import exe_patches
import worldscale

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", ".."))
# The patches must be computed against the ORIGINAL executable; disc/SLUS_008.42
# itself already carries them (it is the recompiler input).
EXE = os.path.join(APP, "disc", "SLUS_008.42.orig")
DISC_BIN = os.path.join(APP, "disc", "disc1.bin")
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


def chicago_skybin() -> bytes:
    """Driver 1's SKY.BIN with Chicago's skies (Driver 2's SKY0.RAW) appended as 13 day,
    14 night, 15 rain (polish_sky.py, C10); the plugin sets the sky number for Chicago."""
    import polish_sky
    data = open(os.path.join(HERE, "work", "d1_SKY.BIN"), "rb").read()
    skies = polish_sky.read_skybin(data)
    assert len(skies) == polish_sky.NSKY and polish_sky.write_skybin(skies) == data
    for name in ("day", "night", "rain"):
        skies.append(polish_sky.sky_bmps(name))
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
    if lump(lev_path) == lump(os.path.join(HERE, "work", "d1_LA.lev")):
        return None
    import polish_map
    from d2overlay import Overlay
    return polish_map.params(Overlay(os.path.join(HERE, "work", "d2_CHICAGO.LEV")))


def car_set_city(lev_path: str) -> int:
    """C51: the Driver 1 city whose car set (lump 28) a converted level carries, found by the lump size
    (the converter only renumbers texture pages in it); its CITY index picks the damage zone tables."""
    from levfile import Lev
    size = len(Lev.parse(open(lev_path, "rb").read()).loadtime.get(28).data)
    for name, city in (("LA", 3), ("MIAMI", 0), ("FRISCO", 1), ("NEWYORK", 5)):
        ref = os.path.join(HERE, "work", "d1_%s.lev" % name)
        if os.path.exists(ref) and len(Lev.parse(open(ref, "rb").read()).loadtime.get(28).data) == size:
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
                    if os.environ.get("CHI_START") else (9216, 106496))
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


def main():
    if not os.path.isfile(EXE):
        raise SystemExit("missing %s (copy of the stock boot EXE)" % EXE)
    ap = argparse.ArgumentParser()
    ap.add_argument("--chicago", help="converted Chicago LEV (replaces Los Angeles)")
    ap.add_argument("--slot", action="store_true", help="Chicago as its own city (LA restored); also CHI_SLOT=1")
    ap.add_argument("--night", default=os.environ.get("CHI_NIGHT"), help="with --slot: converted NIGHT Chicago LEV (Day/Night screen picks it); also CHI_NIGHT")
    ap.add_argument("--install", action="store_true",
                    help="write the dev client's package source mods/preloaded (build-dev installs only); "
                         "without it a CHI_PKG_DIR target is required")
    args = ap.parse_args()
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
    patched = os.environ.get("CHI_PATCHED_EXE") or EXE[:-len(".orig")]
    img, base = exe_patches.load_exe(patched)
    stale = [pc for pc, _old, new, _n in plist
             if struct.unpack_from("<I", img, pc - base)[0] != new]
    if stale:
        raise SystemExit("%s lacks %d of the %d current engine patches (first at %08X): run "
                         "exe_patches.py --apply, then psxrecomp generate and rebuild"
                         % (patched, len(stale), len(plist), stale[0]))
    print("engine patches: %d (disc exe matches)" % len(plist))

    if args.chicago and (args.slot or os.environ.get("CHI_SLOT")):
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
            open(sky_asset, "wb").write(chicago_skybin())
            sky_off, sky_old = iso_record([b"DRIVER", b"DATA", b"SKY.BIN;1"])
        elif os.path.exists(sky_asset):
            os.remove(sky_asset)
        # Chicago music (milestone 2, Polish): a relocated MUSIC.BIN with D1's songs 0-7 byte-identical and
        # D2 Chicago day / night as songs 8 / 9 (the song-select stub plays them for Chicago only)
        music_asset = os.path.join(PKG, "assets", "music.bin")
        music = os.environ.get("CHI_POLISH_MUSIC") == "1"
        music_lba = sky_lba + ((os.path.getsize(sky_asset) // 2048 // 1000 + 1) * 1000 if sky else 0)
        if music:
            shutil.copyfile(os.path.join(HERE, "work", "var_polish_music_chicago.BIN"), music_asset)
            music_off, music_old = iso_record([b"DRIVER", b"SOUND", b"MUSIC.BIN;1"])
            print("music: Chicago songs 8/9 (MUSIC.BIN relocated to LBA %d)" % music_lba)
        elif os.path.exists(music_asset):
            os.remove(music_asset)
        stable_end = stable_pages_end(args.chicago)
        print("stable pages: below index %d (C45 skip-resident)" % stable_end if stable_end else "stable pages: none")
        # sidecar: entry 8, starts 4, night entry 8 (zeros: none), minimap 6 (zeros: LA's), flags (1 = sky),
        # stable-page end (C45: area pages below it have one content everywhere and may be skipped when resident)
        with open(os.path.join(PKG, "assets", "chicago_slot.bin"), "wb") as f:
            # C42 step 1: a level with Driver 2 traffic cars carries <lev>.dmg.bin (polish_cars damage blob:
            # civ verts 900 B at 0, civ polys 1260 B at 2100); its civ part goes into the package and the
            # level's car-set city becomes 4 (the exe's table entry 4 points at the plugin-written copy)
            dmg_asset = os.path.join(PKG, "assets", "dmg_civ.bin")
            d2civ = {}
            for tag, lev_path in (("day", args.chicago), ("night", args.night)):
                dmg = [q for q in (lev_path + ".dmg.bin", os.path.splitext(lev_path)[0] + ".dmg.bin")
                       if os.path.exists(q)] if lev_path else []
                if dmg:                                  # polish_cars names it <name>.dmg.bin
                    blob = open(dmg[0], "rb").read()
                    if len(blob) == 2160:                # polish_carmix: the civ rows only (verts 900 + polys 1260)
                        d2civ[tag] = blob
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
            cday = 4 if "day" in d2civ else car_set_city(args.chicago)
            cnight = 4 if "night" in d2civ else (car_set_city(args.night) if args.night else 3)
            cars = cday | cnight << 8 | 0x10000
            # C42 / C53: a car set 4 level (Driver 2 cars) needs its cosmetics rows (8 x 100 B: wheels, lights;
            # Polish's polish_cosmetics.py), written by the plugin to 0x800A16A0 where the exe's base table points
            for tag, cset in (("day", cday), ("night", cnight)):
                cos_asset = os.path.join(PKG, "assets", "cosmetics_%s.bin" % tag)
                if cset == 4:
                    src = os.environ.get("CHI_COSMETICS_" + tag.upper()) or os.path.join(
                        HERE, "work", "var_polish_cosmetics_chicago_%s.bin" % tag)
                    if not os.path.exists(src) or os.path.getsize(src) != 800:
                        raise SystemExit("car set 4 (%s) needs 800-B cosmetics rows: %s" % (tag, src))
                    shutil.copyfile(src, cos_asset)
                elif os.path.exists(cos_asset):
                    os.remove(cos_asset)
            print("car sets (CITY of the damage tables): day %d, night %d" % (cars & 0xFF, (cars >> 8) & 0xFF))
            f.write(struct.pack("<8I4i8I6I3I", *entry, *LA_START, *CHICAGO_START, *(night or [0] * 8),
                                *(mm or [0] * 6), (1 if sky else 0) | (2 if music else 0), stable_end, cars))
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
        ] if music else []) + menu_patches()
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
