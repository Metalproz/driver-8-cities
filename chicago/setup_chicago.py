"""setup_chicago.py - Option A (R25): build the Chicago package from the player's disc images, one command.

    python setup_chicago.py --build build-test        convert day + night from the discs, package, install
    python setup_chicago.py --pkg DIR                 package into DIR (a driver.chicago/0.1.0 folder)
    python setup_chicago.py --levels-only             only the two converted levels (printed paths)

Reads ONLY the registered discs (inputs.py; CHI_INPUTS=disc unless --inputs work), converts Chicago day
(Driver 2 LEVELS/CHICAGO.LEV) and night (NLEVELS/CHICAGO.LEV), then runs build_package.py (sky, music,
disc patches against the player's Driver 1 disc). Deterministic: the same discs, code and switches give
byte-identical files. Cache: <setup cache>/out/chicago_<day|night>_<key>.lev, key = md5 of the converter
sources + every CHI_* switch + the input md5s, so a rebuild only converts again when something changed
(--force: always). Release recipe = RECIPE below (switches every release build uses); CHI_* switches in
the environment override or extend it (experiments). Never installs into build-release; build-dev needs
--dev (only on the user's go, and only while no build-dev exe runs).
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

import inputs

HERE = inputs.HERE
APP = inputs.APP
OUT = os.path.join(inputs.CACHE, "out")
LOGS = os.path.join(inputs.CACHE, "logs")

# switches of the current Chicago release build (b16b recipe: D1 road network for traffic; the rest are
# convert.py defaults). Package: Chicago as its own city with the two-page menu.
# 23.10. (user 52, Polish + Strategy): the player build = probe "special damage 2" (var_polish_specdmg2): RECIPE only, the
# converter defaults stay (QA / EXP / var_* builds unchanged). CHI_NIGHT_MOON acts on night only; CHI_D2_LEV is per level.
# 27.10. (Strategy, after the 'havana 1' ship): the recipe follows the SHIPPED package = Polish's cheats6 levels (+ d2wheel ride,
# shadow sidecar) for every city; CHI_NIGHT_MOON only on night conversions (as Polish ran them); the Extra-draw pair of
# each city adds CHI_POLISH_XDRAW=1. CITIES lists every shipped city (Chicago, Havana; Las Vegas / Rio join here).
RECIPE = {"CHI_ROADS": "1", "CHI_S4": "1", "CHI_POLISH_D2CARS": "1", "CHI_POLISH_CARMIX_HALF": "1",
          "CHI_POLISH_S1_SLOT15": "1", "CHI_POLISH_STREAM_INMEM": "1", "CHI_POLISH_SPECDMG": "1",
          "CHI_POLISH_SPCRIDE": "d2wheel", "CHI_POLISH_SPCSHADOW": "1"}
NIGHT_RECIPE = {"CHI_NIGHT_MOON": "1"}
XD_RECIPE = {"CHI_POLISH_XDRAW": "1"}
PACKAGE_RECIPE = {"CHI_SLOT": "1", "CHI_MENU_PAGES": "1", "CHI_XD_LEVELS": "1"}
# shipped cities: tag (level / staging name), extra converter env, the build_package switches for its day / night level
# (None = the main --chicago / --night arguments), the inputs it needs
CITIES = [
    dict(tag="chicago", env={}, pkg=None, needs=("d2_CHICAGO.LEV", "d2_CHICAGO_night.lev")),
    dict(tag="havana", env={"CHI_CITY": "HAVANA"}, pkg=("CHI_HAVANA_DAY", "CHI_HAVANA_NIGHT"),
         needs=("d2_HAVANA.LEV", "d2_HAVANA_night.lev")),
]
# switches that do not change a converted level (package/test plumbing)
NOT_LEVEL = {"CHI_PKG_DIR", "CHI_START", "CHI_TEST_BUILD", "CHI_SETUP_CACHE", "CHI_SLOT", "CHI_NIGHT", "CHI_MENU_PAGES",
             "CHI_LEV", "CHI_SKY", "CHI_PREVIEW", "CHI_MAP_FRAME", "CHI_PATCHED_EXE", "CHI_COSMETICS_DAY",
             "CHI_COSMETICS_NIGHT", "CHI_POLISH_MUSIC", "CHI_D2_LEV", "CHI_INPUTS"}


def converter_sources():
    """The chicago/*.py files convert.py imports (directly or inside functions), found statically."""
    from modulefinder import ModuleFinder
    mf = ModuleFinder(path=[HERE])
    mf.run_script(os.path.join(HERE, "convert.py"))
    here = os.path.normcase(HERE)
    return sorted(m.__file__ for m in mf.modules.values()
                  if m.__file__ and os.path.normcase(os.path.dirname(os.path.abspath(m.__file__))) == here)


def level_key(env: dict, tod: str) -> str:
    h = hashlib.md5()
    for f in converter_sources():                 # only what convert.py imports: tool/package edits keep the levels
        h.update(os.path.basename(f).encode() + b"\0" + open(f, "rb").read())
    for k in sorted(env):
        if k.startswith("CHI_") and k not in NOT_LEVEL:
            h.update(("%s=%s\n" % (k, env[k])).encode())
    for name in sorted(inputs.INPUTS):
        h.update(inputs.INPUTS[name][3].encode())
    h.update(tod.encode())
    return h.hexdigest()[:10]


def convert(env: dict, tod: str, force: bool, stream: bool = False, tag: str = "chicago") -> str:
    if tod == "night":
        env = dict(env, **NIGHT_RECIPE)
    key = level_key(env, tod)
    out = os.path.join(OUT, "%s_%s_%s.lev" % (tag, tod, key))
    if os.path.exists(out) and not force:
        print("%s %s: cached %s" % (tag, tod, out))
        return out
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(LOGS, exist_ok=True)
    log = os.path.join(LOGS, "%s-convert-%s-%s.log" % (time.strftime("%m%d-%H%M%S"), tag, tod))
    e = dict(env, CHI_D2_LEV=tod)
    t0 = time.time()
    print("%s %s: converting (log %s) ..." % (tag, tod, log), flush=True)
    with open(log, "w", encoding="utf-8", errors="replace") as f:
        if stream:                                   # --auto: the player watches the progress in the console
            p = subprocess.Popen([sys.executable, "-u", "convert.py", out], cwd=HERE, env=e, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            for line in p.stdout:
                f.write(line)
                print("   [%3.0f s] %s" % (time.time() - t0, line.rstrip()[:110]), flush=True)
            r = subprocess.CompletedProcess(p.args, p.wait())
        else:
            r = subprocess.run([sys.executable, "convert.py", out], cwd=HERE, env=e, stdout=f, stderr=subprocess.STDOUT)
    if r.returncode:
        tail = open(log, encoding="utf-8", errors="replace").read().splitlines()[-8:]
        raise SystemExit("%s conversion failed (exit %d):\n  %s" % (tod, r.returncode, "\n  ".join(tail)))
    print("%s %s: %s (%.0f s)" % (tag, tod, out, time.time() - t0))
    # keep the cache lean: older outputs of the same city / variant / time of day go (with their sidecars)
    for old in glob.glob(os.path.join(OUT, "%s_%s_*.lev" % (tag, tod))):
        if old != out:
            for f in [old] + glob.glob(old + ".*"):
                os.remove(f)
    return out


# R36 (user approved 'la day 6' = var_polish_la_day_15): LA by Day is built from the player's Driver 1 disc with Polish's
# polish_laday.py (mode v15: the frozen design/la_day_v11_cluts.json buildings + the v14 vegetation / props) and passed to
# build_package as CHI_LA_DAY_LEV. CHI_LA_DAY=0: no LA day (the LA row stays night only).
LA_DAY = os.environ.get("CHI_LA_DAY", "1") != "0"


def la_day_sources():
    from modulefinder import ModuleFinder
    mf = ModuleFinder(path=[HERE])
    mf.run_script(os.path.join(HERE, "polish_laday.py"))
    here = os.path.normcase(HERE)
    mods = sorted(m.__file__ for m in mf.modules.values()
                  if m.__file__ and os.path.normcase(os.path.dirname(os.path.abspath(m.__file__))) == here)
    design = os.path.join(HERE, "..", "design")
    return mods + sorted(glob.glob(os.path.join(design, "la_day_*.py")) + glob.glob(os.path.join(design, "la_day_*.json")))


def la_day_key(env: dict) -> str:
    h = hashlib.md5()
    for f in la_day_sources():
        h.update(os.path.basename(f).encode() + b"\0" + open(f, "rb").read())
    for k in sorted(env):
        if k.startswith("CHI_POLISH_LA_DAY"):
            h.update(("%s=%s\n" % (k, env[k])).encode())
    for name in sorted(inputs.INPUTS):
        if name.startswith("d1_"):
            h.update(inputs.INPUTS[name][3].encode())
    return h.hexdigest()[:10]


def la_day(env: dict, force: bool, stream: bool = False) -> str:
    """The LA day level (cached like the Chicago levels): <setup cache>/out/la_day_<key>.lev."""
    key = la_day_key(env)
    out = os.path.join(OUT, "la_day_%s.lev" % key)
    if os.path.exists(out) and not force:
        print("LA day: cached %s" % out)
        return out
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(LOGS, exist_ok=True)
    log = os.path.join(LOGS, "%s-la-day.log" % time.strftime("%m%d-%H%M%S"))
    t0 = time.time()
    print("LA day: building (log %s) ..." % log, flush=True)
    with open(log, "w", encoding="utf-8", errors="replace") as f:
        r = subprocess.run([sys.executable, "polish_laday.py", out], cwd=HERE, env=env, stdout=f, stderr=subprocess.STDOUT)
    if r.returncode or not os.path.exists(out):
        tail = open(log, encoding="utf-8", errors="replace").read().splitlines()[-8:]
        raise SystemExit("LA day build failed (exit %d):\n  %s" % (r.returncode, "\n  ".join(tail)))
    print("LA day: %s (%.0f s)" % (out, time.time() - t0), flush=True)
    for old in glob.glob(os.path.join(OUT, "la_day_*.lev")):
        if old != out:
            os.remove(old)
    return out


def md5(path: str) -> str:
    return inputs._md5(path)

def stage(src: str, name: str) -> str:
    """Copy a cached level + its sidecars to OUT/stage/<name> (build_package finds <city>_xd_<tod>.lev next to
    <city>_<tod>.lev by name)."""
    d = os.path.join(OUT, "stage")
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, name)
    for f in glob.glob(dst + "*"):
        os.remove(f)
    for f in [src] + glob.glob(src + ".*"):
        shutil.copyfile(f, dst + f[len(src):])
    return dst


def build_levels(env: dict, force: bool, stream: bool = False, night: bool = True, log=print) -> dict:
    """Every shipped city's levels (day, night, Extra-draw day / night), staged under their package names.
    Returns {tag: {"day": path, "night": path}}. A city whose inputs are missing fails loudly (never a smaller package)."""
    out = {}
    steps = [(c, x, tod) for c in CITIES for x in (False, True) for tod in (("day", "night") if night else ("day",))]
    for i, (c, xd, tod) in enumerate(steps):
        for name in c["needs"]:
            inputs.path(name)                        # SystemExit with the registry message when a disc is missing
        e = dict(env, **c["env"], **(XD_RECIPE if xd else {}))
        tag = c["tag"] + ("_xd" if xd else "")
        if stream:
            print("\n[%d/%d] %s %s%s" % (i + 1, len(steps), c["tag"].capitalize(), "by " + tod, " (Extra draw)" if xd else ""),
                  flush=True)
        lev = convert(e, tod, force, stream=stream, tag=tag)
        p = stage(lev, "%s_%s.lev" % (tag, tod))
        if not xd:
            out.setdefault(c["tag"], {})[tod] = p
    return out


def package_cmd_env(levels: dict, penv: dict):
    """build_package command + env for the staged levels (Chicago = main arguments, others = their switches)."""
    ch = levels["chicago"]
    cmd = [sys.executable, "build_package.py", "--chicago", ch["day"], "--slot"] + (["--night", ch["night"]] if "night" in ch else [])
    penv = dict(penv)
    for c in CITIES:
        if c["pkg"]:
            penv[c["pkg"][0]] = levels[c["tag"]]["day"]
            if "night" in levels[c["tag"]]:
                penv[c["pkg"][1]] = levels[c["tag"]]["night"]
    return cmd, penv


def package_features(pkg: str) -> set:
    """What a package offers: its levels / city asset folders and its manifest's feature ids."""
    f = set()
    a = os.path.join(pkg, "assets")
    for root, dirs, files in os.walk(a):
        rel = os.path.relpath(root, a).replace(os.sep, "/")
        for n in files:
            if n.endswith(".lev"):
                f.add("level " + (n if rel == "." else rel + "/" + n))
        for n in dirs:
            f.add("folder " + (n if rel == "." else rel + "/" + n))
    m = os.path.join(pkg, "manifest.toml")
    if os.path.exists(m):
        import re
        f |= {"feature " + x for x in re.findall(r'(?m)^id\s*=\s*"([^"]+)"', open(m, encoding="utf-8").read())}
    return f


def feature_guard(old_pkg: str, new_pkg: str):
    """A rebuild never ships less than the installed package: missing levels / cities / features fail loudly."""
    if not os.path.isdir(old_pkg):
        return
    lost = sorted(package_features(old_pkg) - package_features(new_pkg))
    if lost:
        raise SystemExit("the new package would drop %d item(s) the installed one has: %s (installed package kept)"
                         % (len(lost), ", ".join(lost[:12])))


# --- automatic pre-launch step (Option A r3, 16.10.) ------------------------------------------------------------------
# The game's runtime (main.cpp, game.toml [game] prelaunch) runs "setup_chicago.py --auto --build-dir EXE_DIR --check"
# hidden before it loads the mods: exit 0 = the build's Chicago package is current (boot at once), 10 = it must be
# (re)built; then it runs the same command without --check in a visible console and boots afterwards.
AUTO_RECIPE = dict(RECIPE, CHI_POLISH_MUSIC="1")        # user 16.10.: Chicago music on in the player's build
AUTO_PACKAGE = dict(PACKAGE_RECIPE)
STAMP = "setup_stamp.txt"


def auto_log(msg: str):
    os.makedirs(LOGS, exist_ok=True)
    line = "%s | %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    with open(os.path.join(LOGS, "auto.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def auto_state():
    """(chicago possible?, problem text, stamp) for the registered discs and the current code/switches."""
    problems = []
    reg = inputs.registry()
    for key in ("d1", "d2_disc1"):
        p = reg.get(key)
        if not p or not os.path.exists(p):
            problems.append("%s is %s" % (inputs.PROFILES[key]["title"], "not registered" if not p else "missing (%s)" % p))
            continue
        try:
            if inputs.identify(p) != key:
                problems.append("%s: not %s" % (p, inputs.PROFILES[key]["title"]))
        except SystemExit as e:
            problems.append(str(e))
    h = hashlib.md5((code_key() + "\0" + inputs.d1_image()).encode())
    chicago = not problems
    return chicago, "; ".join(problems), ("chicago:" if chicago else "no-chicago:") + h.hexdigest()


def code_key() -> str:
    """Hash of everything a package is built from on the code side: converter sources + recipe (level_key),
    the package-side scripts, the patched recompiler input disc/SLUS_008.42 and the menu picture."""
    env = dict(AUTO_RECIPE, CHI_INPUTS="disc")
    h = hashlib.md5()
    keys = [level_key(dict(env, **c["env"], **(XD_RECIPE if xd else {}), **(NIGHT_RECIPE if tod == "night" else {})), tod)
            for c in CITIES for xd in (False, True) for tod in ("day", "night")]
    for part in tuple(keys) + (repr(sorted(AUTO_PACKAGE.items())), repr(sorted(AUTO_RECIPE.items())),
                               repr([(c["tag"], sorted(c["env"].items()), c["pkg"]) for c in CITIES])) + \
            ((la_day_key(env),) if LA_DAY else ()):
        h.update(part.encode() + b"\0")
    package_side = [os.path.join(HERE, f) for f in ("build_package.py", "exe_patches.py", "polish_music.py", "polish_sky.py",
                                                    "polish_map.py", "polish_cosmetics.py", "inputs.py", "psxiso.py",
                                                    "worldscale.py", "levfile.py", "mapinfo.py", "d2overlay.py")]
    for f in package_side + [os.path.join(APP, "disc", "SLUS_008.42")] + sorted(glob.glob(os.path.join(HERE, "..", "design", "previews", "out", "CHICAGO.*"))):
        if os.path.exists(f):
            h.update(open(f, "rb").read())
    return h.hexdigest()


# --- exe binding (16.10., after an unfinished 15:27 build-dev run): a build's package is only (re)built for the
# code state its exe was generated from. <build>/chicago_exe.json holds the exe md5 and the code_key() of that
# state; "setup_chicago.py --mark BUILD" writes it when a freshly generated exe is installed (build-test after each
# regenerate, build-dev on a ship, --dev). auto() skips (logs, boots with the package as is) when the marker is
# missing, the exe is not the marked one or the shared code moved on: never a half-updated package.
MARKER = "chicago_exe.json"


def mark(build_dir: str) -> dict:
    exe = os.path.join(build_dir, "Driver_Recompiled.exe")
    if not os.path.exists(exe):
        raise SystemExit("no exe in %s" % build_dir)
    import exe_patches
    rec = {"exe_md5": md5(exe), "code_key": code_key(), "slus_md5": md5(os.path.join(APP, "disc", "SLUS_008.42")),
           "patches": len(exe_patches.all_patches(inputs.path("d1_SLUS_008.42"))),
           "marked": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(os.path.join(build_dir, MARKER), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    return rec


def binding_problem(build_dir: str) -> str:
    """'' when build_dir's exe is the one marked for the current code state, else why not."""
    mp = os.path.join(build_dir, MARKER)
    if not os.path.exists(mp):
        return "no %s (exe not marked for any code state)" % MARKER
    try:
        rec = json.load(open(mp, encoding="utf-8"))
    except (OSError, ValueError) as e:
        return "unreadable %s: %s" % (MARKER, e)
    exe = os.path.join(build_dir, "Driver_Recompiled.exe")
    if not os.path.exists(exe) or md5(exe) != rec.get("exe_md5"):
        return "exe differs from the marked one (marked %s)" % rec.get("marked")
    if rec.get("code_key") != code_key():
        return "shared code/patches changed since the exe was marked (%s, %s patches)" % (rec.get("marked"), rec.get("patches"))
    return ""


def auto(build_dir: str, check: bool) -> int:
    pkg = os.path.join(os.path.abspath(build_dir), "mods", "packages", "driver.chicago", "0.1.0")
    stamp_file = os.path.join(pkg, STAMP)
    bound = binding_problem(os.path.abspath(build_dir))
    if bound:                                        # never build a package for another exe / code state
        auto_log("auto %s: skipped, package left as is: %s" % (build_dir, bound))
        return 0
    chicago, problem, stamp = auto_state()
    stamp += ":" + md5(os.path.join(os.path.abspath(build_dir), "Driver_Recompiled.exe"))[:10]
    have = open(stamp_file, encoding="utf-8").read().strip() if os.path.exists(stamp_file) else ""
    if have == stamp:
        return 0
    if check:
        return 10
    os.system("title Building Chicago from your Driver 2 discs")
    t0 = time.time()
    if chicago:
        print("=" * 78 + "\n  Building Chicago from your Driver 2 discs...\n  (first time / after an update: about 30 minutes;"
              " the game starts by itself afterwards)\n" + "=" * 78, flush=True)
        auto_log("auto %s: building Chicago (stamp %s, was %s)" % (build_dir, stamp[-10:], have[-10:] or "none"))
    else:
        print("=" * 78 + "\n  Chicago is not available: %s\n  Driver 1's cities work as usual. Register the disc(s)"
              " (python driver_personal/chicago/inputs.py register IMAGE.cue)\n  and start the game again to build"
              " Chicago.\n" % problem + "=" * 78, flush=True)
        auto_log("auto %s: no Chicago (%s)" % (build_dir, problem))
    env = {k: v for k, v in os.environ.items() if not k.startswith("CHI_")}
    env.update(AUTO_RECIPE, CHI_INPUTS="disc")
    os.environ["CHI_INPUTS"] = "disc"
    try:
        tmp = pkg + ".new"
        shutil.rmtree(tmp, ignore_errors=True)
        penv = dict(env, CHI_PKG_DIR=tmp, **AUTO_PACKAGE)
        if chicago:
            levels = build_levels(env, False, stream=True)
            if LA_DAY:
                print("\nLos Angeles by day", flush=True)
                penv["CHI_LA_DAY_LEV"] = la_day(env, False, stream=True)
            print("\ninstalling the package", flush=True)
            cmd, penv = package_cmd_env(levels, penv)
        else:
            cmd = [sys.executable, "build_package.py"]       # engine extensions only (the guard below refuses to
                                                             # replace a package that has cities)
        r = subprocess.run(cmd, cwd=HERE, env=penv, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("build_package failed: " + (r.stderr or r.stdout)[-1500:])
        open(os.path.join(tmp, STAMP), "w", encoding="utf-8").write(stamp + "\n")
        feature_guard(pkg, tmp)
        old = pkg + ".old"
        shutil.rmtree(old, ignore_errors=True)
        if os.path.exists(pkg):
            os.replace(pkg, old)
        os.replace(tmp, pkg)
        shutil.rmtree(old, ignore_errors=True)
    except BaseException as e:
        auto_log("auto %s: FAILED after %.0f s: %s" % (build_dir, time.time() - t0, str(e)[-300:]))
        print("\nChicago could not be built; Driver 1's cities still work. Details: %s" % os.path.join(LOGS, "auto.log"))
        time.sleep(8)
        return 1
    auto_log("auto %s: done in %.0f s (%s)" % (build_dir, time.time() - t0, "Chicago installed" if chicago else "no Chicago"))
    time.sleep(2 if chicago else 6)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--build", help="install into <app>/BUILD/mods/packages/driver.chicago/0.1.0")
    ap.add_argument("--pkg", help="package directory (driver.chicago/0.1.0)")
    ap.add_argument("--dev", action="store_true", help="allow --build build-dev (user's go only)")
    ap.add_argument("--levels-only", action="store_true")
    ap.add_argument("--no-night", action="store_true")
    ap.add_argument("--force", action="store_true", help="convert again even if cached")
    ap.add_argument("--auto", action="store_true", help="pre-launch step for --build-dir (runtime hook)")
    ap.add_argument("--build-dir", help="with --auto: the game's exe folder")
    ap.add_argument("--check", action="store_true", help="with --auto: exit 0 when current, 10 when a build is due")
    ap.add_argument("--mark", metavar="BUILD", help="bind BUILD's exe to the current code/patch state (after installing a "
                    "freshly generated exe there); build-dev needs --dev")
    ap.add_argument("--check-exe", action="store_true",
                    help="build the patched recompiler input (exe_patches --apply) from the D1 image's exe and compare "
                         "it with disc/SLUS_008.42, then exit")
    ap.add_argument("--inputs", default="disc", choices=("disc", "work", "auto"),
                    help="where the D1/D2 inputs come from (default: the registered discs only)")
    a = ap.parse_args()
    if a.mark:
        bd = a.mark if os.path.isabs(a.mark) else os.path.join(APP, a.mark)
        if os.path.basename(os.path.normpath(bd)) == "build-release":
            raise SystemExit("build-release is frozen")
        if os.path.basename(os.path.normpath(bd)) == "build-dev" and not a.dev:
            raise SystemExit("build-dev changes only on the user's go: add --dev")
        print(json.dumps(mark(bd)))
        return
    if a.auto:
        if not a.build_dir:
            raise SystemExit("--auto needs --build-dir")
        sys.exit(auto(a.build_dir, a.check))

    env = dict(os.environ)
    env["CHI_INPUTS"] = a.inputs
    for k, v in AUTO_RECIPE.items():       # = the shipped package (music on)
        env.setdefault(k, v)
    os.environ.update({"CHI_INPUTS": a.inputs})
    # fail early with the registry message, before minutes of converting
    for name in inputs.INPUTS:
        if name != "d2_CITY.RAW":
            inputs.path(name)
    if a.check_exe:
        out = os.path.join(inputs.CACHE, "package", "SLUS_008.42.patched")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        r = subprocess.run([sys.executable, "exe_patches.py", inputs.path("d1_SLUS_008.42"), "--apply", out],
                           cwd=HERE, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("exe_patches failed:" + chr(10) + r.stdout[-1500:] + r.stderr[-1500:])
        ref = os.path.join(APP, "disc", "SLUS_008.42")
        same = md5(out) == md5(ref)
        print("patched exe from the D1 image: %s md5 %s -> %s disc/SLUS_008.42" % (out, md5(out), "IDENTICAL to" if same else "DIFFERS from"))
        sys.exit(0 if same else 1)
    print("inputs: %s (%s)" % (a.inputs, ", ".join("%s=%s" % (k, v) for k, v in sorted(env.items())
                                                   if k.startswith("CHI_") and k not in ("CHI_INPUTS",))))

    levels = build_levels(env, a.force, night=not a.no_night)
    if a.levels_only:
        for t, v in levels.items():
            print(t, " ".join(v.values()))
        return

    if a.build:
        if a.build == "build-release":
            raise SystemExit("build-release is frozen")
        if a.build == "build-dev" and not a.dev:
            raise SystemExit("build-dev changes only on the user's go: add --dev")
        pkg = os.path.join(APP, a.build, "mods", "packages", "driver.chicago", "0.1.0")
    elif a.pkg:
        pkg = os.path.abspath(a.pkg)
    else:
        raise SystemExit("--build NAME or --pkg DIR (or --levels-only)")
    penv = dict(env, CHI_PKG_DIR=pkg)
    for k, v in PACKAGE_RECIPE.items():
        penv.setdefault(k, v)
    if LA_DAY and "CHI_LA_DAY_LEV" not in penv:
        penv["CHI_LA_DAY_LEV"] = la_day(env, a.force)
    cmd, penv = package_cmd_env(levels, penv)
    r = subprocess.run(cmd, cwd=HERE, env=penv, capture_output=True, text=True)
    sys.stdout.write("".join("  package: %s\n" % l for l in r.stdout.splitlines()))
    if r.returncode:
        raise SystemExit("build_package failed:\n%s" % r.stderr[-2000:])
    for f in ("chicago.lev", "chicago_night.lev", "la_day.lev", "sky.bin", "music.bin", "chicago_preview.bin", "chicago_slot.bin"):
        p = os.path.join(pkg, "assets", f)
        if os.path.exists(p):
            print("  %-20s %9d  md5 %s" % (f, os.path.getsize(p), md5(p)))


if __name__ == "__main__":
    main()
