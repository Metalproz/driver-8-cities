"""inputs.py - Option A (R25): every Driver 1 / Driver 2 input is read from the player's own disc images.

Nothing derived from either game ships: the converter, the package build and the Polish tools ask this
module for their inputs by name (the old work/ file names), and get a file extracted from a registered
disc image (verified by md5) into the setup cache.

Discs (one version each, user 16.10.): Driver 1 USA v1.1 (SLUS_008.42), Driver 2 USA v1.1 disc 1
(SLUS_011.61) + disc 2 (SLUS_013.18). Registry = the app's own disc list, <app>/game.toml [game]:
    discs = [D1, D2 disc 1, D2 disc 2], disc_serials = [SLUS-00842, SLUS-01161, SLUS-01318], boot_discs = 1
The launcher lists all three (disc 1 boots; 2 + 3 are "setup input" discs: runtime patch in main.cpp,
boot_discs); the Driver 2 discs are only read here. Keys: d1, d2_disc1, d2_disc2 (disc 2 holds the same
Chicago files as disc 1, but no SOUND/ folder). D1 fallback: the app's disc.cfg.

    python inputs.py register IMG [IMG...]     identify each image (volume id, boot exe md5) and write the
                                               roster into <app>/game.toml (+ build-test, build-wip; never
                                               build-dev / build-release: their exes need the patch first)
    python inputs.py status                    registered discs, mode, inputs (cached / missing)
    python inputs.py extract                   extract + verify every input into the setup cache

Mode CHI_INPUTS: auto (default: the discs when the needed one is registered, else work/), disc (discs
only; error when missing), work (the old hand copies in chicago/work; the user's files stay untouched).
Setup cache: <app>/setup_cache/ (CHI_SETUP_CACHE overrides): inputs/<disc profile>/<file>, converter
caches in convert/ (disc mode; work mode keeps them in chicago/work as before), levels in out/.
Host-only (setup time on the player's PC); M8's disc builder will take the same two disc sets.
"""
from __future__ import annotations

import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", ".."))
WORK = os.path.join(HERE, "work")
GAME_TOML = os.environ.get("CHI_GAME_TOML") or os.path.join(APP, "game.toml")          # the registry: [game] discs (+ disc_serials)
REGISTER_BUILDS = ("build-test", "build-wip")       # same roster (their exe carries the boot_discs patch)
CACHE = os.environ.get("CHI_SETUP_CACHE") or os.path.join(APP, "setup_cache")

# disc profiles: ISO volume id, boot exe (path, md5), the full-image md5 of the known good dump (Redump;
# informational: a dump that differs elsewhere but carries the same files is accepted)
PROFILES = {
    "d1": dict(title="Driver (USA) (v1.1)", volume="SLUS_00842", exe=("SLUS_008.42", "eee7d0579fff820950579ec1fad85c46"),
               image_md5="b0e1270a6c916e1c6be860fc46b76863", cache="d1_usa_v11"),
    "d2_disc1": dict(title="Driver 2 (USA) (Disc 1) (v1.1)", volume="SLUS_01161",
                     exe=("SLUS_011.61", "22ad964346ecddf6be1089a42e84730c"),
                     image_md5="390b80b6c39be0d15fec8a8fb389c907", cache="d2_usa_v11"),
    "d2_disc2": dict(title="Driver 2 (USA) (Disc 2) (v1.1)", volume="SLUS_01318",
                     exe=("SLUS_013.18", "22ad964346ecddf6be1089a42e84730c"),
                     image_md5="d86b5e6235d30eddd653509b3182d5b6", cache="d2_usa_v11"),
}

# input name (= the old chicago/work file name) -> (discs to read it from, in order; disc path; size; md5)
INPUTS = {
    "d1_LA.lev": (("d1",), "DRIVER/LEVELS/LA.LEV", 5627904, "f540448560f35b029b6d9f6a7a8c4ecd"),
    "d1_MIAMI.lev": (("d1",), "DRIVER/LEVELS/MIAMI.LEV", 5060608, "e9e5ac71feb24cf08e74831f62a9ed49"),
    "d1_FRISCO.lev": (("d1",), "DRIVER/LEVELS/FRISCO.LEV", 7264256, "61d3211ca2d4e7c728644733a468cbe4"),
    "d1_NEWYORK.lev": (("d1",), "DRIVER/LEVELS/NEWYORK.LEV", 6854656, "a40ed441dad77a38a326e16908784426"),
    "d1_IVIEW.lev": (("d1",), "DRIVER/LEVELS/IVIEW.LEV", 917504, "b95c2f3664339292988e32a320bd0c59"),
    "d1_FLAT.lev": (("d1",), "DRIVER/LEVELS/FLAT.LEV", 2109440, "b7acff23a9f22543d5334833e735fdf4"),
    "d1_SKY.BIN": (("d1",), "DRIVER/DATA/SKY.BIN", 228988, "45bc5539d3aeb183e5ef4e2aeb78e11c"),
    "d1_MUSIC.BIN": (("d1",), "DRIVER/SOUND/MUSIC.BIN", 886840, "fbdf348e766c5fe2b05496ef7b89c154"),
    "d2_CHICAGO.LEV": (("d2_disc1", "d2_disc2"), "DRIVER2/LEVELS/CHICAGO.LEV", 10915840, "332ab0cf8b2df726e485ca57fdeaa6b5"),
    "d2_CHICAGO_night.lev": (("d2_disc1", "d2_disc2"), "DRIVER2/NLEVELS/CHICAGO.LEV", 10915840, "73200159ca7ff75c41e83a6950631156"),
    "d2_CHICAGO.DEN": (("d2_disc1", "d2_disc2"), "DRIVER2/LEVELS/CHICAGO.DEN", 12727, "f12a73364fba11315075a1d15f1fefff"),
    "d2_CHICAGO.LCF": (("d2_disc1", "d2_disc2"), "DRIVER2/LEVELS/CHICAGO.LCF", 3120, "57f2165825436f7b2418df50c9ab3e30"),
    # M3 (user 54/55): Havana, Driver 2 disc 1 (cityprofile.HAVANA)
    "d2_HAVANA.LEV": (("d2_disc1",), "DRIVER2/LEVELS/HAVANA.LEV", 10915840, "2fe3dfde2da26b084a69e70515625cfa"),
    "d2_HAVANA_night.lev": (("d2_disc1",), "DRIVER2/NLEVELS/HAVANA.LEV", 10915840, "f6d0c26651733730e534b4df0d4a711f"),
    "d2_HAVANA.DEN": (("d2_disc1",), "DRIVER2/LEVELS/HAVANA.DEN", 12727, "663b255800e2db6a21b9c07e4a840e88"),
    "d2_HAVANA.LCF": (("d2_disc1",), "DRIVER2/LEVELS/HAVANA.LCF", 3120, "fbbdc71442cd996e8618946398d764bf"),
    "d2_SKY1.RAW": (("d2_disc1",), "DRIVER2/DATA/SKY1.RAW", 327680, "a382b2359e9bad885ebb7d2681869f14"),   # Havana (sky.c skyNum 1)
    # M3 Las Vegas / Rio (Strategy 27.10., user request): Driver 2 disc 2 (same files on disc 1)
    "d2_VEGAS.LEV": (("d2_disc2", "d2_disc1"), "DRIVER2/LEVELS/VEGAS.LEV", 10915840, "9d79e4696d648e5d76cfd7e035e6e561"),
    "d2_VEGAS_night.lev": (("d2_disc2", "d2_disc1"), "DRIVER2/NLEVELS/VEGAS.LEV", 10915840, "b7081bef632cbca63f09e15cb099707f"),
    "d2_VEGAS.DEN": (("d2_disc2", "d2_disc1"), "DRIVER2/LEVELS/VEGAS.DEN", 12727, "139ea2dd76271ae0b0d7eaf01ca1ce50"),
    "d2_VEGAS.LCF": (("d2_disc2", "d2_disc1"), "DRIVER2/LEVELS/VEGAS.LCF", 3120, "78b8ed8a904a648b374a6aedd83400fd"),
    "d2_RIO.LEV": (("d2_disc2", "d2_disc1"), "DRIVER2/LEVELS/RIO.LEV", 10915840, "708ca54a847d5a9828ee1fae4473fc5c"),
    "d2_RIO_night.lev": (("d2_disc2", "d2_disc1"), "DRIVER2/NLEVELS/RIO.LEV", 10915840, "ca7861394be68bb35464d112d419d417"),
    "d2_RIO.DEN": (("d2_disc2", "d2_disc1"), "DRIVER2/LEVELS/RIO.DEN", 12727, "80f487cc553347077e40995301f82f05"),
    "d2_RIO.LCF": (("d2_disc2", "d2_disc1"), "DRIVER2/LEVELS/RIO.LCF", 3120, "520709972fb9b1be03764a7968ecca5b"),
    "d2_SKY2.RAW": (("d2_disc2", "d2_disc1"), "DRIVER2/DATA/SKY2.RAW", 327680, "d91930a621effff1f6ba0aef1accbd34"),   # Las Vegas (skyNum 2)
    "d2_SKY3.RAW": (("d2_disc2", "d2_disc1"), "DRIVER2/DATA/SKY3.RAW", 327680, "5071dcfa0d09cfe17c96efa1f542736a"),   # Rio (skyNum 3)
    "d2_SKY0.RAW": (("d2_disc1", "d2_disc2"), "DRIVER2/DATA/SKY0.RAW", 327680, "54a1bd5e2df09db6c1f54f38d3c28e5b"),
    "d2_MUSIC.BIN": (("d2_disc1",), "DRIVER2/SOUND/MUSIC.BIN", 777944, "b153580d82d6091a3b234179873bc1b2"),
    "d2_CITY.RAW": (("d2_disc1", "d2_disc2"), "DRIVER2/DATA/CITY.RAW", 131072, "96454a28767e3235eb316dda4cfd6ff4"),
    "d2_VOICES2.BLK": (("d2_disc1",), "DRIVER2/SOUND/VOICES2.BLK", 2377156, "41241f744c2f7a526a58dd56aaa9db88"),
    # Driver 1's boot exe, unpatched: base of every engine patch (exe_patches, build_package); the patched
    # recompiler input disc/SLUS_008.42 = exe_patches.py --apply of this file (checked by setup_chicago --check-exe)
    "d1_SLUS_008.42": (("d1",), "SLUS_008.42", 555008, "eee7d0579fff820950579ec1fad85c46"),
}
# work mode: inputs that never lived in chicago/work
WORK_PATHS = {"d1_SLUS_008.42": os.path.join(APP, "disc", "SLUS_008.42.orig")}


class InputError(SystemExit):
    pass


def mode() -> str:
    m = os.environ.get("CHI_INPUTS", "auto").lower()
    if m not in ("auto", "disc", "work"):
        raise InputError("CHI_INPUTS=%s: expected auto, disc or work" % m)
    return m


def _norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(p))


# --- registry ---------------------------------------------------------------------------------
SERIAL_KEYS = {"SLUS-00842": "d1", "SLUS-01161": "d2_disc1", "SLUS-01318": "d2_disc2"}
KEY_SERIALS = {v: k for k, v in SERIAL_KEYS.items()}


def _toml_discs(path: str):
    """([game] discs, disc_serials) of a game.toml (absolute paths; relative ones are app-root relative)."""
    import re
    if not os.path.exists(path):
        return [], []
    text = open(path, encoding="utf-8").read()
    game = re.search(r"^\[game\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    body = game.group(1) if game else ""
    def arr(key):
        m = re.search(r"^%s\s*=\s*\[(.*?)\]" % key, body, re.M | re.S)
        return re.findall(r'"([^"]*)"', m.group(1)) if m else None
    discs = arr("discs")
    if discs is None:
        m = re.search(r'^disc\s*=\s*"([^"]*)"', body, re.M)
        discs = [m.group(1)] if m else []
    discs = [d if os.path.isabs(d) else os.path.join(APP, d) for d in discs]
    return discs, arr("disc_serials") or []


def registry() -> dict:
    """key -> image path, from <app>/game.toml [game] discs (by disc_serials, else by volume id);
    the D1 fallback is the app's disc.cfg."""
    discs, serials = _toml_discs(GAME_TOML)
    reg = {}
    for i, d in enumerate(discs):
        key = SERIAL_KEYS.get(serials[i]) if i < len(serials) else None
        if key is None:
            try:
                key = identify(d)
            except InputError:
                continue
        reg.setdefault(key, d)
    cfg = os.path.join(APP, "disc.cfg")
    if "d1" not in reg and os.path.exists(cfg):
        line = open(cfg, encoding="utf-8", errors="replace").read().strip().splitlines()
        if line and line[0].strip():
            reg["d1"] = line[0].strip()
    return reg


def identify(path: str):
    """(profile key, notes) of a disc image; raises InputError with a clear message if it is none of ours."""
    import psxiso
    try:
        disc = psxiso.Disc(path)
    except (OSError, ValueError) as e:
        raise InputError("%s: not a readable MODE2/2352 disc image (%s)" % (path, e))
    with disc:
        try:
            vol = disc.volume_id()
        except ValueError as e:
            raise InputError(str(e))
        hit = [k for k, p in PROFILES.items() if p["volume"] == vol]
        if not hit:
            raise InputError("%s: volume %r is none of the supported discs (%s)"
                             % (path, vol, ", ".join(p["title"] for p in PROFILES.values())))
        key = hit[0]
        exe, md5 = PROFILES[key]["exe"]
        try:
            got = hashlib.md5(disc.get(exe)).hexdigest()
        except FileNotFoundError:
            raise InputError("%s: volume %s but no %s on it" % (path, vol, exe))
        if got != md5:
            raise InputError("%s: %s with another boot exe (md5 %s): only %s is supported (other versions/regions "
                             "give a different conversion)" % (path, exe, got, PROFILES[key]["title"]))
    return key


def write_roster(game_toml: str, reg: dict):
    """Write [game] discs / disc_serials / boot_discs; every other line of the file stays as it is."""
    keys = [k for k in PROFILES if k in reg]
    if not keys or keys[0] != "d1":
        raise InputError("Driver 1 (USA) (v1.1) must be registered first (it is the disc the game boots)")
    raw = open(game_toml, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines, out, section, skipping, done = raw.splitlines(), [], None, False, False
    q = lambda vals: "[" + ", ".join('"%s"' % v for v in vals) + "]"
    roster = ["discs = %s" % q(reg[k].replace("\\", "/") for k in keys),
              "disc_serials = %s" % q(KEY_SERIALS[k] for k in keys),
              "# driver_personal (Option A): only disc 1 boots; the Driver 2 discs are setup inputs (city data)",
              "boot_discs = 1"]
    for line in lines:
        t = line.strip()
        if skipping:                                   # inside a multi-line discs = [ ... ] array
            skipping = "]" not in t
            continue
        if t.startswith("["):
            section = t
        if section == "[game]":
            key = t.split("=")[0].strip() if "=" in t else ""
            if key in ("disc", "discs", "disc_serials", "boot_discs") or \
                    t.startswith("# driver_personal (Option A): only disc 1 boots"):
                skipping = key in ("discs", "disc_serials") and "]" not in t
                continue
            out.append(line)
            if key == "exe" and not done:
                out += roster
                done = True
            continue
        out.append(line)
    if not done:
        raise InputError("%s: no [game] exe line to put the disc list after" % game_toml)
    open(game_toml, "w", encoding="utf-8", newline="").write(nl.join(out) + (nl if raw.endswith(("\n", "\r")) else ""))


def register(paths):
    reg = registry()
    for p in paths:
        key = identify(p)
        reg[key] = os.path.abspath(p).replace("\\", "/")
        print("registered %-9s %s  (%s)" % (key, PROFILES[key]["title"], reg[key]))
    for t in [GAME_TOML] + [os.path.join(APP, b, "game.toml") for b in REGISTER_BUILDS]:
        if os.path.exists(t):
            write_roster(t, reg)
            print("  roster written:", t)


def disc_path(key: str, required: bool = True):
    p = registry().get(key)
    if p and os.path.exists(p):
        return p
    if required:
        raise InputError("%s is not registered%s: python driver_personal/chicago/inputs.py register IMAGE.cue"
                         % (PROFILES[key]["title"], " (missing file %s)" % p if p else ""))
    return None


def d1_image() -> str:
    """Driver 1's BIN (the package's disc patches are made against it)."""
    import psxiso
    p = disc_path("d1", required=False)
    return psxiso.image_path(p) if p else os.path.join(APP, "disc", "disc1.bin")


# --- inputs ---------------------------------------------------------------------------------------
def _md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _cached(name: str) -> str:
    discs, _iso, _size, _md5sum = INPUTS[name]
    return os.path.join(CACHE, "inputs", PROFILES[discs[0]]["cache"], name)


def _from_disc(name: str) -> str:
    discs, iso, size, md5 = INPUTS[name]
    out = _cached(name)
    if os.path.exists(out) and os.path.getsize(out) == size:
        return out
    import psxiso
    keys = [k for k in discs if disc_path(k, required=False)]
    if not keys:
        raise InputError("%s needs %s: python driver_personal/chicago/inputs.py register IMAGE.cue"
                         % (name, " or ".join(PROFILES[k]["title"] for k in discs)))
    for k in keys:
        with psxiso.Disc(disc_path(k)) as disc:
            if not disc.exists(iso):
                continue
            data = disc.get(iso)
        if len(data) != size or hashlib.md5(data).hexdigest() != md5:
            raise InputError("%s on %s differs from %s (size %d, md5 %s): wrong disc version?"
                             % (iso, disc_path(k), PROFILES[k]["title"], len(data), hashlib.md5(data).hexdigest()))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        tmp = out + ".tmp"
        open(tmp, "wb").write(data)
        os.replace(tmp, out)
        return out
    raise InputError("%s: %s is on none of the registered discs %s" % (name, iso, keys))


def disc_mode_for(name: str) -> bool:
    m = mode()
    if m == "work":
        return False
    if m == "disc":
        return True
    return any(disc_path(k, required=False) for k in INPUTS[name][0])


def path(name: str) -> str:
    """The file holding input `name` (an INPUTS key): extracted from the discs, or chicago/work."""
    if name not in INPUTS:
        raise KeyError(name)
    if disc_mode_for(name):
        return _from_disc(name)
    p = WORK_PATHS.get(name) or os.path.join(WORK, name)
    if not os.path.exists(p):
        raise InputError("%s: no registered disc and no %s (python driver_personal/chicago/inputs.py register IMAGE.cue)"
                         % (name, p))
    return p


def read(name: str) -> bytes:
    with open(path(name), "rb") as f:
        return f.read()


def resolve(p: str) -> str:
    """A path given by a user or switch: an old work/<input> spelling (or a bare input name) goes through
    the resolver, anything else is used as is (experiments)."""
    base = os.path.basename(p)
    if base in INPUTS and (os.path.dirname(p) == "" or _norm(os.path.dirname(p)) == _norm(WORK)):
        return path(base)
    return p


def d2_lev() -> str:
    """Driver 2 source city of a conversion: CHI_D2_LEV = day (default) / night / a path."""
    from cityprofile import P                    # M3: the city's day / night level (CHI_CITY, default Chicago)
    v = os.environ.get("CHI_D2_LEV", "day")
    if v.lower() == "day":
        return path(P.lev_day)
    if v.lower() == "night":
        return path(P.lev_night)
    return resolve(v)


def is_input(p: str, name: str) -> bool:
    """Is p the input `name` (its resolved file, or the old work copy)?"""
    return _norm(p) in (_norm(path(name)), _norm(os.path.join(WORK, name)))


def cache_dir() -> str:
    """Where converter caches go: chicago/work in work mode (as before), the setup cache otherwise."""
    from cityprofile import P
    if not disc_mode_for(P.lev_day):
        return WORK
    d = os.path.join(CACHE, "convert")
    os.makedirs(d, exist_ok=True)
    return d


def status():
    reg = registry()
    print("mode: %s   setup cache: %s" % (mode(), CACHE))
    for k, prof in PROFILES.items():
        p = reg.get(k)
        state = "not registered" if not p else ("MISSING FILE" if not os.path.exists(p) else "ok")
        print("  %-9s %-32s %s %s" % (k, prof["title"], state, p or ""))
    for name, (discs, iso, size, md5) in INPUTS.items():
        try:
            src = "disc" if disc_mode_for(name) else "work"
        except InputError as e:
            src = "error: %s" % e
        c = _cached(name)
        print("  %-22s %-5s %s" % (name, src, "cached" if os.path.exists(c) else "-"))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "register":
        register(sys.argv[2:])
    elif cmd == "extract":
        os.environ["CHI_INPUTS"] = "disc"
        for name in INPUTS:
            p = path(name)
            print("%-22s %s  md5 %s" % (name, p, "ok" if _md5(p) == INPUTS[name][3] else "BAD"))
    else:
        status()
