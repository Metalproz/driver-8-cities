"""build_package.py — write the driver.chicago mod package.

Features:
  model-table    move Driver 1's model table to 2048 entries (patches + plugin)
  test-bigmiami  (test) Miami rebuilt with model indices past 800, served past
                 the end of the disc via the directory record of MIAMI.LEV

usage: build_package.py [--test-bigmiami work/test_bigmiami.lev]
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


def extent_bytes(lba: int, size: int) -> bytes:
    return struct.pack("<I", lba) + struct.pack(">I", lba) + struct.pack("<I", size) + struct.pack(">I", size)


MISSION_BLK_LBA = 63177                         # DRIVER/MISSIONS/MISSION.BLK
LA_START = (376863, -217530)                    # mission opcode 0x13 player start (x, z)
# Driver 2 coordinates (a road tile among the tallest blocks, clear of collision
# boxes); converted to the scaled Driver 1 world with worldscale.to_d1.
CHICAGO_START_D2 = (tuple(int(v) for v in os.environ["CHI_START"].split(","))
                    if os.environ.get("CHI_START") else (9216, 106496))
CHICAGO_START = worldscale.to_d1(*CHICAGO_START_D2)


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
    ap.add_argument("--test-bigmiami")
    ap.add_argument("--chicago", help="converted Chicago LEV (replaces Los Angeles)")
    args = ap.parse_args()

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
    patched = EXE[:-len(".orig")]
    img, base = exe_patches.load_exe(patched)
    stale = [pc for pc, _old, new, _n in plist
             if struct.unpack_from("<I", img, pc - base)[0] != new]
    if stale:
        raise SystemExit("%s lacks %d of the %d current engine patches (first at %08X): run "
                         "exe_patches.py --apply, then psxrecomp generate and rebuild"
                         % (patched, len(stale), len(plist), stale[0]))
    print("engine patches: %d (disc exe matches)" % len(plist))

    if args.test_bigmiami:
        asset = os.path.join(PKG, "assets", "test_bigmiami.lev")
        os.makedirs(os.path.dirname(asset), exist_ok=True)
        shutil.copyfile(args.test_bigmiami, asset)
        size = os.path.getsize(asset)
        rec_off, rec_old = dir_record(b"MIAMI.LEV;1")
        out += [
            "[[feature]]",
            'id = "test-bigmiami"',
            'name = "TEST: Miami with 948 models"',
            'description = "Test only. Replaces Miami with a copy whose objects use model slots past 800, loaded from past the end of the disc. Needs Engine Extensions (Chicago). Start downtown; traffic and cops are not in yet."',
            'group = "Chicago"',
            "default_enabled = false",
            "",
            "[[overlay]]",
            'feature = "test-bigmiami"',
            'target = "disc_user"',
            "offset = %d" % (EXTENSION_LBA * 2048),
            'file = "assets/test_bigmiami.lev"',
            'sha256 = "%s"' % sha256_file(asset),
            "",
            "# DRIVER/LEVELS/MIAMI.LEV directory record: extent (LE+BE) and size (LE+BE)",
            "[[patch]]",
            'feature = "test-bigmiami"',
            'target = "disc_user"',
            "offset = %d" % rec_off,
            'expected = "%s"' % hexbytes(rec_old),
            'replace = "%s"' % hexbytes(extent_bytes(EXTENSION_LBA, size)),
            "",
        ]

    if args.chicago:
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
