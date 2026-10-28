"""psxiso.py - stdlib ISO9660 reader for PlayStation disc images (MODE2/2352 BIN, or a CUE naming one).

The one reader for the Driver 1 and Driver 2 discs (Option A, R25; adopted from EXP's prototype
chicago/optiona/d2iso.py (removed 16.10.), which reproduced our hand-copied d2_* files byte for byte).

    python psxiso.py tree IMG [--depth N]          directory tree with sizes
    python psxiso.py get IMG PATH OUT [--raw]      extract one file (--raw: whole 2352-byte sectors, XA/STR)
    python psxiso.py find IMG NAME                 find files by name (case-insensitive)

IMG may be the .bin or the .cue (first FILE of a single MODE2/2352 data track).
Sector layout (MODE2/2352): 12 sync + 4 header + 8 subheader + 2328 data. Form 1 user data = 2048
bytes at offset 24; Form 2 user data = 2324 bytes at offset 24 (submode bit 0x20). ISO9660 file
extents are read as 2048-byte Form 1 user data (Form 2 sectors only through --raw).
Host-only tool (setup time on the player's PC); the PS1 disc builder (M8) will need its own writer.
"""
from __future__ import annotations

import os
import re
import struct
import sys

RAW = 2352


def image_path(path: str) -> str:
    """The BIN of an image given as .bin or .cue (cue: first FILE line, relative to the cue)."""
    if not path.lower().endswith(".cue"):
        return path
    text = open(path, "r", encoding="latin1").read()
    m = re.search(r'^\s*FILE\s+"([^"]+)"\s+BINARY', text, re.M | re.I) or \
        re.search(r'^\s*FILE\s+(\S+)\s+BINARY', text, re.M | re.I)
    if not m:
        raise ValueError("%s: no BINARY FILE line" % path)
    if not re.search(r"TRACK\s+01\s+MODE2/2352", text, re.I):
        raise ValueError("%s: track 1 is not MODE2/2352" % path)
    return os.path.join(os.path.dirname(os.path.abspath(path)), m.group(1))


class Disc:
    def __init__(self, path: str):
        self.path = image_path(path)
        self.f = open(self.path, "rb")
        size = self.f.seek(0, 2)
        if size % RAW:
            raise ValueError("%s: size %d is not a multiple of 2352 (not a MODE2/2352 image)" % (self.path, size))
        self.nsec = size // RAW
        self._dirs = {}

    def close(self):
        self.f.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def sector(self, lba: int) -> bytes:
        self.f.seek(lba * RAW)
        return self.f.read(RAW)

    def user(self, lba: int) -> bytes:
        raw = self.sector(lba)
        if raw[18] & 0x20:              # Form 2 sector
            return raw[24:24 + 2324]
        return raw[24:24 + 2048]

    def read_extent(self, lba: int, size: int, raw_mode: bool = False) -> bytes:
        n = (size + 2047) // 2048
        if raw_mode:
            return b"".join(self.sector(lba + i) for i in range(n))
        self.f.seek(lba * RAW)
        blob = self.f.read(n * RAW)
        out = b"".join(blob[i * RAW + 24: i * RAW + 24 + 2048] for i in range(n))
        return out[:size]

    def pvd(self) -> bytes:
        pv = self.user(16)
        if pv[1:6] != b"CD001":
            raise ValueError("%s: no ISO9660 volume descriptor at sector 16" % self.path)
        return pv

    def volume_id(self) -> str:
        return self.pvd()[40:72].decode("latin1").strip()

    def root(self):
        return dirent(self.pvd()[156:190])

    def listdir(self, d):
        key = d["lba"]
        if key not in self._dirs:
            data = self.read_extent(d["lba"], d["size"])
            out, p = [], 0
            while p < len(data):
                L = data[p]
                if L == 0:
                    p = (p // 2048 + 1) * 2048
                    continue
                e = dirent(data[p:p + L])
                if not e["special"]:
                    out.append(e)
                p += L
            self._dirs[key] = out
        return self._dirs[key]

    def walk(self, d=None, prefix="", depth=99):
        if d is None:
            d = self.root()
        for e in self.listdir(d):
            p = prefix + "/" + e["name"]
            yield p, e
            if e["isdir"] and depth > 0:
                yield from self.walk(e, p, depth - 1)

    def entry(self, path: str):
        d = self.root()
        for name in [p for p in path.replace("\\", "/").split("/") if p]:
            hit = [e for e in self.listdir(d) if e["name"].upper() == name.upper()]
            if not hit:
                raise FileNotFoundError("%s: %s not on the disc" % (os.path.basename(self.path), path))
            d = hit[0]
        return d

    def exists(self, path: str) -> bool:
        try:
            self.entry(path)
            return True
        except FileNotFoundError:
            return False

    def get(self, path: str, raw_mode: bool = False) -> bytes:
        d = self.entry(path)
        if d["isdir"]:
            raise IsADirectoryError(path)
        return self.read_extent(d["lba"], d["size"], raw_mode)


def dirent(e: bytes) -> dict:
    lba = struct.unpack_from("<I", e, 2)[0]
    size = struct.unpack_from("<I", e, 10)[0]
    flags = e[25]
    nl = e[32]
    raw_name = e[33:33 + nl]
    special = raw_name in (b"\x00", b"\x01")
    if raw_name == b"\x00":
        name = "."
    elif raw_name == b"\x01":
        name = ".."
    else:
        name = raw_name.decode("latin1").split(";")[0]
    return {"name": name, "lba": lba, "size": size, "isdir": bool(flags & 2), "special": special}


if __name__ == "__main__":
    cmd, img = sys.argv[1], sys.argv[2]
    d = Disc(img)
    if cmd == "tree":
        depth = int(sys.argv[sys.argv.index("--depth") + 1]) if "--depth" in sys.argv else 99
        for p, e in d.walk(depth=depth):
            print("%s%s %d @%d" % (p, "/" if e["isdir"] else "", e["size"], e["lba"]))
    elif cmd == "get":
        data = d.get(sys.argv[3], raw_mode="--raw" in sys.argv)
        open(sys.argv[4], "wb").write(data)
        print("wrote", len(data))
    elif cmd == "find":
        want = sys.argv[3].upper()
        for p, e in d.walk():
            if e["name"].upper() == want:
                print(p, e["lba"], e["size"])
