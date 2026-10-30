"""publish_playable.py - publish the dev client (build-dev) as a self-contained folder on the
OneDrive desktop, so it syncs to the user's laptop and runs there exactly like at home:
dev mode, logs, F9 / L3+R3 snapshots, overlay, test-spot starts.

    python driver_personal/publish_playable.py            publish/update
    python driver_personal/publish_playable.py --dry-run  show how much would be copied
    pythonw driver_personal/publish_playable.py --if-changed   scheduled task: publish only when build-dev
        or the spot list changed and has been stable for 2 min; quiet otherwise; logs to WORKLOG.md

Folder contents: game exe + runtime folders, mods (Chicago package + the dev client's
features), disc image, retail BIOS, the user's settings/controls, and three launchers:
  Play Driver.bat    normal start (resets the Chicago start to downtown)
  Play at spot.bat   choose a test spot (spots.txt, precomputed here) as the Take a Ride start
  fixpaths.ps1       rewrites the absolute BIOS/disc/memcard paths to the folder's location
Snapshots and logs go to <folder>/dev (dp_app_dir = exe folder) and sync back to the PC.
Saves live in <folder>/saves and are never overwritten by a publish. Dev files are not copied.
Personal use only: the disc image and BIOS are the user's own dumps.
"""
from __future__ import annotations

import datetime, json, os, shutil, struct, subprocess, sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
DEV = APP / "build-dev"
NAME = "Driver Chicago (playable)"
DEFAULT_START_D2 = (9216, 106496)          # build_package.py's default CHICAGO_START_D2

RUNTIME_FILES = ["Driver_Recompiled.exe", "game.toml", "game_options.toml", "input.ini", "keybinds.ini",
                 "settings.toml", "psx_game_version.txt", "psxrecomp_exe_name-psx-runtime.txt",
                 "chi_s4.flag"]  # S4 switch (C81 era): mirror it when the source build has it
RUNTIME_DIRS = ["assets", "bios", "mods"]
# Option A (16.10.): the copies carry the ORIGINAL Driver 1 image under its own name (from the app's disc list,
# game.toml [game] discs[0]) + the patched exe; the laptop has no D:/recomps/games. The Driver 2 discs stay on the
# PC: the copies get the Chicago package already built from them, so their game.toml lists only disc 1.
sys.path.insert(0, str(APP / "driver_personal" / "chicago"))
import inputs as _inputs                                      # noqa: E402
D1_BIN = Path(_inputs.d1_image())
D1_CUE = D1_BIN.with_suffix(".cue")
DISC_SRC = [D1_BIN, D1_CUE, APP / "disc" / "SLUS_008.42", APP / "disc" / "SYSTEM.CNF"]
BIOS = APP / "psxrecomp" / "bios" / "SCPH1001.BIN"
SPOTS = APP / "driver_personal" / "chicago" / "devtools" / "spots.json"
# for a live-lookup chat on the laptop: debug client, command list, technical notes, roadmap
DEVTOOLS = [APP / "driver_personal" / "driver_dbg.py", APP / "psxrecomp" / "TCP_COMMANDS.md",
            APP / "driver_personal" / "chicago" / "NOTES.md", APP / "driver_personal" / "ROADMAP.md", SPOTS]
LAPTOP_CHAT = r"""# Live lookup on this PC (for a Claude chat opened in this folder)

This folder is a published copy of the user's Driver dev client (Chicago port, personal use).
The main project lives on the user's desktop PC (D:\recomps); its planning chat tracks
snapshots and logs from here (dev\dumps, dev\logs) after OneDrive syncs them.

- While the game runs, its debug server listens on 127.0.0.1:4370 (one JSON request per
  connection): `python devtools/driver_dbg.py frame | read ADDR N | watch ADDR N | snapshot`.
  Full command list: devtools/TCP_COMMANDS.md.
- Addresses, formats, known bugs and the ruled-out list: devtools/NOTES.md. Open issues: devtools/ROADMAP.md.
  Test spots: devtools/spots.json (Driver 2 coordinates) / spots.txt.
- F9 or L3+R3 saves a snapshot to dev/dumps/<time>/ (ram.bin, regs.json, screen.png, heartbeat.json).
  Summarize with short scripts; don't read whole dumps.
- Don't change files here except saves/ and dev/: the next publish from the PC overwrites everything else.
  Fixes are made on the desktop PC; write findings to dev/notes-from-laptop.md so the PC chats see them.
"""

FIXPATHS_PS1 = r'''# Rewrites the absolute paths in settings.toml / bios.cfg / disc.cfg to this folder.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$fw = $here -replace '\\', '/'
Set-Content -Path (Join-Path $here 'bios.cfg') -Value "$here\bios\SCPH1001.BIN" -Encoding ascii
Set-Content -Path (Join-Path $here 'disc.cfg') -Value "$fw/disc/D1NAME.cue" -Encoding ascii
# game.toml: one disc (the original Driver 1 image here); the Driver 2 input discs stay on the PC
$gt = Join-Path $here 'game.toml'
if (Test-Path $gt) {
  $g = Get-Content $gt -Raw
  $g = $g -replace '(?m)^(disc_serials|boot_discs|prelaunch) *=.*\r?\n', ''
  $g = $g -replace '(?m)^# driver_personal \(Option A\).*\r?\n', ''
  $g = $g -replace '(?m)^discs? *=.*$', ('disc = "' + $fw + '/disc/D1NAME.cue"')
  [IO.File]::WriteAllText($gt, $g)
}
$st = Join-Path $here 'settings.toml'
if (Test-Path $st) {
  $t = Get-Content $st -Raw
  $t = $t -replace '(?m)^path = ".*SCPH1001\.BIN"', ('path = "' + $fw + '/bios/SCPH1001.BIN"')
  $t = $t -replace '(?m)^path = ".*(disc1|Wheelman)[^"]*"', ('path = "' + $fw + '/disc/D1NAME.bin"')
  $t = $t -replace '(?m)^dir(\s*)= ".*"', ('dir$1= "' + $fw + '/saves"')
  $t = $t -replace '(?m)^card1(\s*)= ".*"', ('card1$1= "' + $fw + '/saves/card1.mcd"')
  $t = $t -replace '(?m)^card2(\s*)= ".*"', ('card2$1= "' + $fw + '/saves/card2.mcd"')
  [IO.File]::WriteAllText($st, $t)
}
'''

SPOT_PS1 = r'''# Sets the Chicago start position (Take a Ride, Los Angeles = Chicago).
# Usage: spot.ps1 [name]   (no name: list the spots and ask; "default" = normal downtown start)
param([string]$name = "")
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$spots = @{}; $notes = @{}
foreach ($l in Get-Content (Join-Path $here 'spots.txt')) {
  $p = $l.Split('|')
  if ($p.Count -ge 3) { $spots[$p[0]] = $p[1]; $notes[$p[0]] = $p[2] }
}
if (-not $name) {
  $spots.Keys | Sort-Object | ForEach-Object { "{0,-14} {1}" -f $_, $notes[$_] }
  $name = Read-Host "spot name (Enter = default start)"
  if (-not $name) { $name = "default" }
}
if (-not $spots.ContainsKey($name)) { Write-Host "unknown spot: $name"; exit 1 }
$m = Join-Path $here 'mods\packages\driver.chicago\0.1.0\manifest.toml'
$lines = [IO.File]::ReadAllLines($m); $mark = $false
for ($i = 0; $i -lt $lines.Length; $i++) {
  if ($lines[$i] -like '*player start (opcode 0x13)*') { $mark = $true }
  elseif ($mark -and $lines[$i] -like 'replace = *') { $lines[$i] = 'replace = "' + $spots[$name] + '"'; $mark = $false }
}
[IO.File]::WriteAllLines($m, $lines)
# slot builds (Chicago = own city row): the start lives in chicago_slot.bin (8I 4i: LA x z, Chicago x z at +40)
$s = Join-Path $here 'mods\packages\driver.chicago\0.1.0\assets\chicago_slot.bin'
if (Test-Path $s) {
  $b = [IO.File]::ReadAllBytes($s); $v = $spots[$name].Split(' ')
  for ($k = 0; $k -lt 8; $k++) { $b[40 + $k] = [Convert]::ToByte($v[$k], 16) }
  [IO.File]::WriteAllBytes($s, $b)
  Write-Host "start set to: $name  (Take a Ride -> Chicago row)"
} else { Write-Host "start set to: $name  (Take a Ride -> Los Angeles = Chicago)" }
'''

# every launcher first activates its Chicago package (dev client's or a probe's) from packages_store
USE_PKG = r'''robocopy "%~dp0packages_store\{slug}\driver.chicago" "%~dp0mods\packages\driver.chicago" /MIR /NJH /NJS /NFL /NDL /NP >nul
'''

PLAY_BAT = r'''@echo off
rem Driver with Chicago (dev client copy): normal downtown start. Dev mode: F9 snapshots -> dev\dumps
cd /d "%~dp0"
''' + USE_PKG.format(slug="dev") + r'''powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0spot.ps1" default
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fixpaths.ps1"
rem hold Tab = fast forward at 500 % (menus / loading screens)
if not defined PSX_FAST_FORWARD_SPEED set PSX_FAST_FORWARD_SPEED=5
start "" "%~dp0Driver_Recompiled.exe" --memcard-dir "%~dp0saves"
'''

SPOT_BAT_T = r'''@echo off
rem Driver with Chicago: {title}. Pick a test spot as the Take a Ride start (Los Angeles = Chicago), then play.
cd /d "%~dp0"
''' + USE_PKG + r'''powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0spot.ps1" %*
if errorlevel 1 (pause & exit /b 1)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fixpaths.ps1"
rem hold Tab = fast forward at 500 % (menus / loading screens)
if not defined PSX_FAST_FORWARD_SPEED set PSX_FAST_FORWARD_SPEED=5
start "" "%~dp0Driver_Recompiled.exe" --memcard-dir "%~dp0saves"
'''
SPOT_BAT = SPOT_BAT_T.replace("{title}", "dev client copy").replace("{slug}", "dev")

PROBES_FILE = Path(os.environ.get("CHI_PROBES_FILE") or APP / "driver_personal" / "probes.json")   # override: tests
# R27 (user 16.10.): every probe made after these six carries all 3 discs ("discs": 3, the default); the six keep
# the old 1-disc copy (Driver 1 only) unless probes.json says otherwise.
LEGACY_ONE_DISC = {"city selector", "quay fix 2", "look test", "slopes preview", "minimap", "discs build"}
PROBE_PKG_BUILD = APP / "devtest" / "_probe_pkgs"
PROBE_ROOT_NAME = "Driver Probe Tests"   # user 2026-10-12: probes live in their own folder, never in the dev client copy

# a probe copy has its package installed directly (no packages_store)
PROBE_PLAY_BAT = PLAY_BAT.replace(USE_PKG.format(slug="dev"), "").replace("(dev client copy)", "(PROBE {name})")
PROBE_SPOT_BAT = SPOT_BAT_T.replace(USE_PKG, "")
# the probes share one disc image in '<root>/_disc' (747 MB) instead of one per probe
PROBE_FIXPATHS_PS1 = (FIXPATHS_PS1
    .replace(r"$fw = $here -replace '\\', '/'",
             r"$fw = $here -replace '\\', '/'" + "\n" + r"$dw = (Split-Path -Parent $here) -replace '\\', '/'")
    .replace(r'"$fw/disc/D1NAME.cue"', r'"$dw/_disc/D1NAME.cue"')
    .replace(r"""('disc = "' + $fw + '/disc/D1NAME.cue"')""", r"""('disc = "' + $dw + '/_disc/D1NAME.cue"')""")
    .replace(r"""('path = "' + $fw + '/disc/D1NAME.bin"')""", r"""('path = "' + $dw + '/_disc/D1NAME.bin"')"""))
FIXPATHS_PS1 = FIXPATHS_PS1.replace("D1NAME", D1_BIN.stem)
PROBE_FIXPATHS_PS1 = PROBE_FIXPATHS_PS1.replace("D1NAME", D1_BIN.stem)
# 3-disc probes (R27): the game.toml keeps the roster (D1 + Driver 2 disc 1 + 2, all from <root>/_disc; disc_serials,
# boot_discs = 1 and require_discs = 3 are written at publish time), only the paths are rewritten here
D2_STEMS = [Path(_inputs.disc_path(k, required=False) or "missing").stem for k in ("d2_disc1", "d2_disc2")]
PROBE3_FIXPATHS_PS1 = (PROBE_FIXPATHS_PS1
    .replace(r"""  $g = $g -replace '(?m)^(disc_serials|boot_discs|prelaunch) *=.*\r?\n', ''""",
             r"""  $g = $g -replace '(?m)^prelaunch *=.*\r?\n', ''""")
    .replace(r"""  $g = $g -replace '(?m)^# driver_personal \(Option A\).*\r?\n', ''""" + "\n", "")
    .replace(r"""('disc = "' + $dw + '/_disc/%s.cue"')""" % D1_BIN.stem,
             r"""('discs = ["' + $dw + '/_disc/%s.cue", "' + $dw + '/_disc/%s.cue", "' + $dw + '/_disc/%s.cue"]')""" % (D1_BIN.stem, D2_STEMS[0], D2_STEMS[1])))



def all_probes() -> dict:
    """Every current probe in probes.json: name -> slug, level, build folder, description."""
    if not PROBES_FILE.exists():
        return {}
    out = {}
    for name, p in json.loads(PROBES_FILE.read_text(encoding="utf-8")).items():
        if name.startswith("_"):
            continue
        lev = APP / "driver_personal" / "chicago" / p["lev"]
        if lev.exists():
            out[name] = {"slug": "probe_" + "".join(c if c.isalnum() else "_" for c in name), "lev": lev,
                         "build": APP / p.get("build", "build-dev"), "what": p.get("what", ""),
                         "slot": bool(p.get("slot")),   # slot = Chicago as its own Take a Ride row (CHI_SLOT=1)
                         "night": APP / "driver_personal" / "chicago" / p["night"] if p.get("night") else None,   # slot: night LEV (CHI_NIGHT)
                         "menu": p.get("menu"),   # slot: "pages" = two-page Take a Ride menu (CHI_MENU_PAGES=1)
                         "env": {k: str(v) for k, v in p.get("env", {}).items()},   # extra package-build switches
                         # R27: 3 = the copy carries and requires all 3 discs (default for new probes); 1 = Driver 1 only
                         "discs": int(p.get("discs", 1 if name in LEGACY_ONE_DISC else 3))}
    return out


def probes() -> dict:
    return {}                                   # the dev client copy carries no probes any more (see publish_probes)


def copy_tree(src: Path, dst: Path, dry: bool) -> int:
    n = 0
    for f in src.rglob("*"):
        if f.is_file():
            n += copy_file(f, dst / f.relative_to(src), dry)
    return n


def copy_d2_discs(disc_dir: Path, dry: bool) -> int:
    """R27: both Driver 2 images (.bin + .cue, original names) into the probes' shared _disc, only when missing or
    changed (size / time); a fresh copy is checked against the known dump md5."""
    import hashlib
    n = 0
    for key in ("d2_disc1", "d2_disc2"):
        cue = Path(_inputs.disc_path(key))
        cue = cue if cue.suffix.lower() == ".cue" else cue.with_suffix(".cue")
        binf = cue.with_suffix(".bin")
        for src in (binf, cue):
            c = copy_file(src, disc_dir / src.name, dry)
            n += c
            if c and src is binf and not dry:
                h = hashlib.md5()
                with open(disc_dir / src.name, "rb") as f:
                    for chunk in iter(lambda: f.read(1 << 22), b""):
                        h.update(chunk)
                if h.hexdigest() != _inputs.PROFILES[key]["image_md5"]:
                    raise SystemExit("%s: copy differs from the known dump (md5 %s)" % (disc_dir / src.name, h.hexdigest()))
    return n


def three_disc_game_toml(path: Path) -> None:
    """R27: the copy's game.toml lists all 3 discs (paths set by fixpaths.ps1), requires them, never pre-builds."""
    reg = {"d1": "_disc/%s.cue" % D1_BIN.stem, "d2_disc1": "_disc/%s.cue" % D2_STEMS[0], "d2_disc2": "_disc/%s.cue" % D2_STEMS[1]}
    _inputs.write_roster(str(path), reg)
    t = path.read_text(encoding="utf-8")
    nl = "\r\n" if "\r\n" in t else "\n"
    lines = [l for l in t.splitlines() if not l.strip().startswith(("prelaunch", "require_discs"))]
    i = next(k for k, l in enumerate(lines) if l.strip().startswith("boot_discs"))
    lines.insert(i + 1, "require_discs = 3   # R27: this copy refuses to start without all 3 discs")
    path.write_text(nl.join(lines) + nl, encoding="utf-8", newline="")


def desktop() -> Path:
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                         capture_output=True, text=True).stdout.strip()
    return Path(out)


def running_from(folder: Path) -> bool:
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_Process -Filter \"Name='Driver_Recompiled.exe'\" | "
                          "ForEach-Object { $_.ExecutablePath }"], capture_output=True, text=True).stdout
    return any(str(folder).lower() in line.lower() for line in out.splitlines())


def spot_table() -> str:
    """name|replace bytes|note per spot (Driver 1 start x, z as build_package.py writes them)."""
    sys.path.insert(0, str(APP / "driver_personal" / "chicago"))
    import worldscale
    hexb = lambda x, z: " ".join("%02x" % c for c in struct.pack("<ii", int(x), int(z)))
    rows = ["default|%s|normal start (downtown)" % hexb(*worldscale.to_d1(*DEFAULT_START_D2))]
    for k, v in json.loads(SPOTS.read_text(encoding="utf-8")).items():
        note = " ".join(v.get("note", "").replace("|", "/").split())[:100]
        rows.append("%s|%s|%s" % (k, hexb(*worldscale.to_d1(*v["d2"])), note))
    return "\n".join(rows) + "\n"


def copy_file(src: Path, dst: Path, dry: bool) -> int:
    if dst.exists() and dst.stat().st_size == src.stat().st_size and dst.stat().st_mtime >= src.stat().st_mtime:
        return 0
    if not dry:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return src.stat().st_size


STAMP_NAME = ".published_from.txt"
STABLE_S = 120


def source_stamp() -> tuple[str, float]:
    """Fingerprint of what the copy depends on + the newest change time."""
    files = [DEV / "Driver_Recompiled.exe", DEV / "mods/state.toml", SPOTS, PROBES_FILE,
             *sorted((DEV / "mods/packages").rglob("manifest.toml")),
             *sorted((DEV / "mods/packages").rglob("*.lev")),
             *[p["lev"] for p in probes().values()]]
    files = [f for f in files if f.exists()]
    stamp = "\n".join("%s %d %d" % (f.relative_to(APP), f.stat().st_size, int(f.stat().st_mtime)) for f in files)
    return stamp, max(f.stat().st_mtime for f in files)


# user rule 17.10. (R30): quick-city-select is OFF in every published copy (the dev client's own state may differ)
OFF_FEATURES = ("quick-city-select",)


def force_off(state_path: Path) -> None:
    """Disable the OFF_FEATURES in a published mods/state.toml."""
    if not state_path.exists():
        return
    t = state_path.read_text(encoding="utf-8")
    for f in OFF_FEATURES:
        t = t.replace('id = "%s"\nenabled = true' % f, 'id = "%s"\nenabled = false' % f)
    state_path.write_text(t, encoding="utf-8")


def probe_package(p: dict) -> Path:
    built = PROBE_PKG_BUILD / p["slug"] / "driver.chicago" / "0.1.0"
    lev_out = built / "assets" / "chicago.lev"
    # the package's manifest carries the [[patch]] list (dirty code pages run interpreted from guest RAM), so it
    # must be rebuilt when the level, the patch list, the package builder or the probe's exe changes (C36, 21:28)
    deps = [p["lev"], p.get("night") or p["lev"], APP / "driver_personal" / "chicago" / "exe_patches.py",
            APP / "driver_personal" / "chicago" / "build_package.py", p["build"] / "Driver_Recompiled.exe"]
    newest = max(f.stat().st_mtime for f in deps if f.exists())
    # Strategy 30.10.: mtimes alone missed a probe switched to an OLDER level file; the stamp now also names every input
    # file (lev, night, file-valued env such as CHI_VEGAS_DAY) with its size and mtime, and the slot / night / menu options
    def _fid(v):
        try:
            f = Path(str(v))
            return [str(f.resolve()), f.stat().st_size, int(f.stat().st_mtime)] if f.is_file() else v
        except (OSError, ValueError):
            return v
    env_stamp = json.dumps({"env": {k: _fid(v) for k, v in p.get("env", {}).items()}, "lev": _fid(p["lev"]),
                            "night": _fid(p.get("night")), "slot": p.get("slot"), "menu": p.get("menu")},
                           sort_keys=True, default=str)
    stamp_file = built.parent / "probe_env.json"
    same_env = stamp_file.exists() and stamp_file.read_text(encoding="utf-8") == env_stamp
    if not lev_out.exists() or lev_out.stat().st_mtime < newest or not same_env:
        sys.path.insert(0, str(APP / "driver_personal" / "chicago" / "devtools"))
        import dt
        shutil.rmtree(built.parent, ignore_errors=True)
        old = {k: os.environ.get(k) for k in ("CHI_SLOT", "CHI_NIGHT", "CHI_MENU_PAGES", *p.get("env", {}))}
        os.environ.update(p.get("env", {}))
        if p.get("slot"):
            os.environ["CHI_SLOT"] = "1"
            if p.get("night"):
                os.environ["CHI_NIGHT"] = str(p["night"])
            if p.get("menu") == "pages":
                os.environ["CHI_MENU_PAGES"] = "1"
        try:
            dt.build_package(lev=p["lev"], pkg_dir=built)
            stamp_file.write_text(env_stamp, encoding="utf-8")
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    return built.parent


def publish_probes(dry: bool, spots_only: bool) -> None:
    """One self-contained copy per probe in '<Desktop>/Driver Probe Tests/<name>': the probe's own exe (build-dev
    or a test build, frozen at publish time) + build-dev's runtime + the probe's Chicago package + launchers.
    OneDrive syncs it to the laptop; the dev client copy is never touched. spots_only (the scheduled task): only
    refresh the spot list, so a test build that is still being worked on never reaches a published probe."""
    root = Path(os.environ["CHI_PROBE_ROOT"]) if os.environ.get("CHI_PROBE_ROOT") else desktop() / PROBE_ROOT_NAME
    plist = all_probes()
    if not spots_only and any(p["discs"] == 3 for p in plist.values()):
        copied3 = copy_d2_discs(root / "_disc", dry)
        print("Driver 2 discs in %s: %.1f MB %s" % (root / "_disc", copied3 / 1e6, "to copy" if dry else "copied"))
    table = spot_table()
    for name, p in plist.items():
        dest = root / name
        if running_from(dest):
            print("probe %r is running, skipped" % name)
            continue
        if spots_only:
            if dest.exists() and not dry:
                (dest / "spots.txt").write_text(table, encoding="utf-8")
            continue
        exe_dir = p["build"] if (p["build"] / "Driver_Recompiled.exe").exists() else DEV
        copied = 0
        for f in RUNTIME_FILES:
            src = exe_dir / f if (exe_dir / f).exists() else DEV / f
            if src.exists():
                copied += copy_file(src, dest / f, dry)
        chi_pkg = DEV / "mods" / "packages" / "driver.chicago"
        for d in RUNTIME_DIRS:
            for src in (DEV / d).rglob("*"):
                if src.is_file() and chi_pkg not in src.parents:
                    copied += copy_file(src, dest / d / src.relative_to(DEV / d), dry)
        if exe_dir != DEV:      # the probe's build brings its own mod manifests (new features/options), not build-dev's
            pkgs = exe_dir / "mods" / "packages"
            for src in pkgs.rglob("*") if pkgs.exists() else ():
                if src.is_file() and "driver.chicago" not in src.relative_to(pkgs).parts:
                    copied += copy_file(src, dest / "mods" / "packages" / src.relative_to(pkgs), dry)
        if not dry:
            active = dest / "mods" / "packages" / "driver.chicago"
            shutil.rmtree(active, ignore_errors=True)
            shutil.copytree(probe_package(p), active, dirs_exist_ok=True)
            st = dest / "mods" / "state.toml"
            t = st.read_text(encoding="utf-8").replace(     # old engine test (Miami copy), never for play
                'id = "test-bigmiami"\nenabled = true', 'id = "test-bigmiami"\nenabled = false')
            st.write_text(t, encoding="utf-8")
            force_off(st)
            if p.get("slot"):                               # Chicago in its own row: chicago-slot instead of chicago-la
                t = st.read_text(encoding="utf-8").replace(
                    'id = "chicago-la"\nenabled = true',
                    'id = "chicago-slot"\nenabled = true\n[feature.values]\ncity = "la"')
                assert 'id = "chicago-slot"' in t, "chicago-la feature block not found in state.toml"
                st.write_text(t, encoding="utf-8")   # row 3 = original LA, row 5 = Chicago
        for src in DISC_SRC:
            copied += copy_file(src, root / "_disc" / src.name, dry)
        copied += copy_file(BIOS, dest / "bios" / BIOS.name, dry)
        for src in DEVTOOLS:
            copied += copy_file(src, dest / "devtools" / src.name, dry)
        if not (dest / "saves").exists():                  # own saves, started from the PC's; never copied back
            for src in (APP / "saves").glob("*.mcd"):
                copied += copy_file(src, dest / "saves" / src.name, dry)
        if not dry:
            if p["discs"] == 3:
                three_disc_game_toml(dest / "game.toml")
            (dest / "fixpaths.ps1").write_text(PROBE3_FIXPATHS_PS1 if p["discs"] == 3 else PROBE_FIXPATHS_PS1,
                                               encoding="utf-8")
            (dest / "spot.ps1").write_text(SPOT_PS1, encoding="utf-8")
            (dest / "spots.txt").write_text(table, encoding="utf-8")
            (dest / "devtools").mkdir(exist_ok=True)
            (dest / "CLAUDE.md").write_text(LAPTOP_CHAT, encoding="utf-8")
            title = "PROBE '%s' (%s)" % (name, p["what"][:80])
            (dest / "Play probe.bat").write_text(PROBE_PLAY_BAT.replace("{name}", name).replace("\n", "\r\n"),
                                                 encoding="ascii", errors="replace")
            (dest / "Play probe at spot.bat").write_text(
                PROBE_SPOT_BAT.replace("{title}", title).replace("\n", "\r\n"), encoding="ascii", errors="replace")
            exe_t = datetime.datetime.fromtimestamp((dest / "Driver_Recompiled.exe").stat().st_mtime)
            (dest / "VERSION.txt").write_text(
                "PROBE '%s' published %s\nwhat: %s\ngame exe: %s (from %s, frozen at publish time)\nlevel: %s\n\n"
                "Start: 'Play probe.bat' (downtown) or 'Play probe at spot.bat' (pick a test spot; then Take a Ride ->"
                " Los Angeles = Chicago). F9 snapshots go to dev\\dumps here. Own saves, separate from the dev client.\n"
                % (name, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), p["what"],
                   exe_t.strftime("%Y-%m-%d %H:%M"), exe_dir.name, p["lev"].name), encoding="utf-8")
        print("probe %r -> %s (%s exe): %.1f MB %s" % (name, dest, exe_dir.name, copied / 1e6,
                                                      "to copy" if dry else "copied"))
    if not dry and not spots_only and root.exists():
        for old in root.iterdir():                          # probes no longer in probes.json
            if old.is_dir() and old.name not in plist and old.name != "_disc" and not running_from(old):
                dumps = old / "dev" / "dumps"                # the user's snapshots survive the probe
                for snap in (dumps.iterdir() if dumps.exists() else []):
                    keep = APP / "dev" / "dumps" / ("probe_%s_%s" % (old.name.replace(" ", "_"), snap.name))
                    if snap.is_dir() and not keep.exists():
                        shutil.copytree(snap, keep)
                        print("kept user snapshot:", keep.name)
                shutil.rmtree(old, ignore_errors=True)
                for dp, dns, fns in os.walk(old, topdown=False):   # OneDrive can leave empty dirs behind
                    if not fns:
                        try:
                            os.rmdir(dp)
                        except OSError:
                            pass
                print("removed outdated probe folder:", old.name)
        slugs = {p["slug"] for p in plist.values()}
        for st in (PROBE_PKG_BUILD.iterdir() if PROBE_PKG_BUILD.exists() else []):   # lean disk: stale package builds
            if st.is_dir() and st.name not in slugs:
                shutil.rmtree(st, ignore_errors=True)
                print("removed stale probe package build:", st.name)
        (root / "README.txt").write_text(
            "Probe tests: test levels / test builds that are NOT in the dev client yet. One folder per probe,\n"
            "each self-contained (own exe, own saves). Use 'Play probe at spot.bat' inside a folder.\n\n" +
            "".join("- %s: %s\n" % (n, p["what"]) for n, p in plist.items()), encoding="utf-8")


def main():
    dry = "--dry-run" in sys.argv
    auto = "--if-changed" in sys.argv
    if "--probes" in sys.argv:
        publish_probes(dry, spots_only=False)
        return
    if auto:
        publish_probes(dry, spots_only=True)
    dest = desktop() / NAME
    if auto:
        stamp, newest = source_stamp()
        old = (dest / STAMP_NAME).read_text(encoding="utf-8") if (dest / STAMP_NAME).exists() else ""
        if stamp == old or datetime.datetime.now().timestamp() - newest < STABLE_S or running_from(dest):
            return                                          # unchanged, still being written, or in use
    if running_from(dest):
        raise SystemExit("The playable copy is running (%s). Close the game first." % dest)
    copied = 0
    for f in RUNTIME_FILES:
        if (DEV / f).exists():
            copied += copy_file(DEV / f, dest / f, dry)
    chi_pkg = DEV / "mods" / "packages" / "driver.chicago"
    for d in RUNTIME_DIRS:
        for src in (DEV / d).rglob("*"):
            if src.is_file() and chi_pkg not in src.parents:      # the Chicago package goes via packages_store
                copied += copy_file(src, dest / d / src.relative_to(DEV / d), dry)
    store = dest / "packages_store"
    copied += copy_tree(chi_pkg, store / "dev" / "driver.chicago", dry)
    plist = probes()
    for name, p in plist.items():                           # one complete package per current probe
        built = PROBE_PKG_BUILD / p["slug"] / "driver.chicago" / "0.1.0"
        lev_out = built / "assets" / "chicago.lev"
        if not dry and (not lev_out.exists() or lev_out.stat().st_mtime < p["lev"].stat().st_mtime):
            sys.path.insert(0, str(APP / "driver_personal" / "chicago" / "devtools"))
            import dt
            shutil.rmtree(built.parent, ignore_errors=True)
            dt.build_package(lev=p["lev"], pkg_dir=built)
        if built.parent.exists():
            copied += copy_tree(built.parent, store / p["slug"] / "driver.chicago", dry)
    if not dry:
        for old in store.glob("probe_*"):                   # probes no longer in probes.json
            if old.name not in {p["slug"] for p in plist.values()}:
                shutil.rmtree(old, ignore_errors=True)
        for old in dest.glob("Play probe - *.bat"):
            if old.stem[len("Play probe - "):-len(" at spot")] not in plist:
                old.unlink()
    for src in DISC_SRC:
        copied += copy_file(src, dest / "disc" / src.name, dry)
    copied += copy_file(BIOS, dest / "bios" / BIOS.name, dry)
    for src in DEVTOOLS:
        copied += copy_file(src, dest / "devtools" / src.name, dry)
    if not (dest / "saves").exists():                      # first publish only: start from the PC's saves
        for src in (APP / "saves").glob("*.mcd"):
            copied += copy_file(src, dest / "saves" / src.name, dry)
    table = spot_table()
    if not dry:
        force_off(dest / "mods" / "state.toml")
        (dest / "fixpaths.ps1").write_text(FIXPATHS_PS1, encoding="utf-8")
        (dest / "spot.ps1").write_text(SPOT_PS1, encoding="utf-8")
        (dest / "spots.txt").write_text(table, encoding="utf-8")
        (dest / "devtools").mkdir(exist_ok=True)
        (dest / "CLAUDE.md").write_text(LAPTOP_CHAT, encoding="utf-8")
        (dest / "Play Driver.bat").write_text(PLAY_BAT.replace("\n", "\r\n"), encoding="ascii")
        (dest / "Play at spot.bat").write_text(SPOT_BAT.replace("\n", "\r\n"), encoding="ascii")
        for name, p in plist.items():
            bat = SPOT_BAT_T.replace("{title}", "PROBE '%s' (%s)" % (name, p["what"][:80])).replace("{slug}", p["slug"])
            (dest / ("Play probe - %s at spot.bat" % name)).write_text(bat.replace("\n", "\r\n"), encoding="ascii",
                                                                      errors="replace")
        # leave the dev client's package active by default
        active = dest / "mods" / "packages" / "driver.chicago"
        shutil.rmtree(active, ignore_errors=True)            # may be held by OneDrive: then overwrite in place
        shutil.copytree(store / "dev" / "driver.chicago", active, dirs_exist_ok=True)
        exe_t = datetime.datetime.fromtimestamp((DEV / "Driver_Recompiled.exe").stat().st_mtime)
        lev = DEV / "mods/packages/driver.chicago/0.1.0/assets/chicago.lev"
        lev_t = datetime.datetime.fromtimestamp(lev.stat().st_mtime).strftime("%Y-%m-%d %H:%M") if lev.exists() else "?"
        (dest / "VERSION.txt").write_text(
            "Published %s from build-dev (the dev client)\ngame exe: %s\nChicago level: %s\n\n"
            "Start: 'Play Driver.bat' (downtown) or 'Play at spot.bat' (pick a test spot; then Take a Ride -> Los Angeles = Chicago).\n"
            "Probes (test levels that are not in the dev client yet): 'Play probe - NAME at spot.bat'. Current: %s.\n"
            "Dev mode is on: F9 / L3+R3 snapshots and logs go to the dev folder here and sync back to the PC.\n"
            "Don't run it on two PCs at the same time (shared saves).\n"
            % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), exe_t.strftime("%Y-%m-%d %H:%M"), lev_t,
               ", ".join("%s (%s)" % (n, p["what"]) for n, p in plist.items()) or "none"),
            encoding="utf-8")
        (dest / STAMP_NAME).write_text(source_stamp()[0], encoding="utf-8")
        if auto:
            with open(APP / "driver_personal" / "WORKLOG.md", "a", encoding="utf-8") as w:
                w.write("%s | publish (auto) | playable | build-dev mirrored to the OneDrive desktop copy '%s' "
                        "(%.1f MB changed) for the laptop | publish_playable.py\n"
                        % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), NAME, copied / 1e6))
    print("%s %s: %.1f MB %s, %d spots" % ("would update" if dry else "published to", dest, copied / 1e6,
                                          "to copy" if dry else "copied", table.count("\n") - 1))


if __name__ == "__main__":
    main()
