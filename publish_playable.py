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

import datetime, json, shutil, struct, subprocess, sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
DEV = APP / "build-dev"
NAME = "Driver Chicago (playable)"
DEFAULT_START_D2 = (9216, 106496)          # build_package.py's default CHICAGO_START_D2

RUNTIME_FILES = ["Driver_Recompiled.exe", "game.toml", "game_options.toml", "input.ini", "keybinds.ini",
                 "settings.toml", "psx_game_version.txt", "psxrecomp_exe_name-psx-runtime.txt"]
RUNTIME_DIRS = ["assets", "bios", "mods"]
DISC_FILES = ["disc1.bin", "disc1.cue", "SLUS_008.42", "SYSTEM.CNF"]
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
Set-Content -Path (Join-Path $here 'disc.cfg') -Value "$fw/disc/disc1.bin" -Encoding ascii
$st = Join-Path $here 'settings.toml'
if (Test-Path $st) {
  $t = Get-Content $st -Raw
  $t = $t -replace '(?m)^path = ".*SCPH1001\.BIN"', ('path = "' + $fw + '/bios/SCPH1001.BIN"')
  $t = $t -replace '(?m)^path = ".*disc1\.bin"', ('path = "' + $fw + '/disc/disc1.bin"')
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
Write-Host "start set to: $name  (Take a Ride -> Los Angeles = Chicago)"
'''

PLAY_BAT = r'''@echo off
rem Driver with Chicago (dev client copy): normal downtown start. Dev mode: F9 snapshots -> dev\dumps
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0spot.ps1" default
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fixpaths.ps1"
start "" "%~dp0Driver_Recompiled.exe" --memcard-dir "%~dp0saves"
'''

SPOT_BAT = r'''@echo off
rem Driver with Chicago (dev client copy): pick a test spot as the Take a Ride start, then play.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0spot.ps1" %*
if errorlevel 1 (pause & exit /b 1)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fixpaths.ps1"
start "" "%~dp0Driver_Recompiled.exe" --memcard-dir "%~dp0saves"
'''


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
    files = [DEV / "Driver_Recompiled.exe", DEV / "mods/state.toml", SPOTS,
             *sorted((DEV / "mods/packages").rglob("manifest.toml")),
             *sorted((DEV / "mods/packages").rglob("*.lev"))]
    files = [f for f in files if f.exists()]
    stamp = "\n".join("%s %d %d" % (f.relative_to(APP), f.stat().st_size, int(f.stat().st_mtime)) for f in files)
    return stamp, max(f.stat().st_mtime for f in files)


def main():
    dry = "--dry-run" in sys.argv
    auto = "--if-changed" in sys.argv
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
    for d in RUNTIME_DIRS:
        for src in (DEV / d).rglob("*"):
            if src.is_file():
                copied += copy_file(src, dest / d / src.relative_to(DEV / d), dry)
    for f in DISC_FILES:
        copied += copy_file(APP / "disc" / f, dest / "disc" / f, dry)
    copied += copy_file(BIOS, dest / "bios" / BIOS.name, dry)
    for src in DEVTOOLS:
        copied += copy_file(src, dest / "devtools" / src.name, dry)
    if not (dest / "saves").exists():                      # first publish only: start from the PC's saves
        for src in (APP / "saves").glob("*.mcd"):
            copied += copy_file(src, dest / "saves" / src.name, dry)
    table = spot_table()
    if not dry:
        (dest / "fixpaths.ps1").write_text(FIXPATHS_PS1, encoding="utf-8")
        (dest / "spot.ps1").write_text(SPOT_PS1, encoding="utf-8")
        (dest / "spots.txt").write_text(table, encoding="utf-8")
        (dest / "devtools").mkdir(exist_ok=True)
        (dest / "CLAUDE.md").write_text(LAPTOP_CHAT, encoding="utf-8")
        (dest / "Play Driver.bat").write_text(PLAY_BAT.replace("\n", "\r\n"), encoding="ascii")
        (dest / "Play at spot.bat").write_text(SPOT_BAT.replace("\n", "\r\n"), encoding="ascii")
        exe_t = datetime.datetime.fromtimestamp((DEV / "Driver_Recompiled.exe").stat().st_mtime)
        lev = DEV / "mods/packages/driver.chicago/0.1.0/assets/chicago.lev"
        lev_t = datetime.datetime.fromtimestamp(lev.stat().st_mtime).strftime("%Y-%m-%d %H:%M") if lev.exists() else "?"
        (dest / "VERSION.txt").write_text(
            "Published %s from build-dev (the dev client)\ngame exe: %s\nChicago level: %s\n\n"
            "Start: 'Play Driver.bat' (downtown) or 'Play at spot.bat' (pick a test spot; then Take a Ride -> Los Angeles = Chicago).\n"
            "Dev mode is on: F9 / L3+R3 snapshots and logs go to the dev folder here and sync back to the PC.\n"
            "Don't run it on two PCs at the same time (shared saves).\n"
            % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), exe_t.strftime("%Y-%m-%d %H:%M"), lev_t),
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
