"""probes.py - keep the user's probe shortcuts in sync with probes.json.

    python driver_personal/probes.py sync     desktop: create "Driver (probe - NAME)" for every probe in
                                              probes.json, remove every other "Driver (probe - *)" shortcut
    python driver_personal/probes.py list     show the current probes

A probe = the dev client's exe + a test level, started at a chosen spot (spotplay.py --lev).
The laptop copy gets the same probes from publish_playable.py (it reads probes.json too).
Optional "build": run that build's exe instead (e.g. "build-test" for an exe/plugin fix not yet
in build-dev); desktop only, the laptop copy mirrors build-dev and skips such probes.
"""
from __future__ import annotations

import json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
CHI = HERE / "chicago"
PROBES = HERE / "probes.json"
PREFIX = "Driver (probe - "

BAT = ('@echo off\r\nrem PROBE "{name}": {what}\r\nrem = {exe} exe + {lev}. Separate test copy; the dev client is untouched.\r\n'
       'cd /d "%~dp0driver_personal\\chicago\\devtools"\r\n{env}'
       'if "%~1"=="" (python spotplay.py --lev {lev}) else (python spotplay.py %1 --lev {lev})\r\npause\r\n')


def load() -> dict:
    data = json.loads(PROBES.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def desktop() -> Path:
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                         capture_output=True, text=True).stdout.strip()
    return Path(out)


def make_lnk(lnk: Path, target: Path):
    ps = ("$ws = New-Object -ComObject WScript.Shell; $l = $ws.CreateShortcut('%s'); $l.TargetPath = '%s'; "
          "$l.WorkingDirectory = '%s'; $l.IconLocation = '%s,0'; $l.Save()"
          % (lnk, target, APP, APP / "build-dev" / "Driver_Recompiled.exe"))
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)


def sync():
    probes, desk = load(), desktop()
    want = {PREFIX + name + ")" for name in probes}
    for name, p in probes.items():
        if not (CHI / p["lev"]).exists():
            print("MISSING level for probe %r: %s (skipped)" % (name, p["lev"]))
            continue
        build = p.get("build", "build-dev")
        if not (APP / build / "Driver_Recompiled.exe").exists():
            print("MISSING exe for probe %r: %s (skipped)" % (name, build))
            continue
        env = "" if build == "build-dev" else "set CHI_TEST_BUILD=%s\r\n" % build
        bat = APP / (PREFIX + name + ").bat")
        bat.write_text(BAT.format(name=name, what=p.get("what", ""), lev=p["lev"], exe=build, env=env),
                       encoding="ascii", newline="")
        print("probe ok:", name, "->", p["lev"], "" if build == "build-dev" else "(%s exe)" % build)
    for f in list(APP.glob(PREFIX + "*).bat")) + list(desk.glob(PREFIX + "*).lnk")):
        if f.stem not in want or f.suffix == ".lnk":    # the desktop gets the "Driver Probe Tests" folder instead
            f.unlink()
            print("removed:", f.name)
    # user 2026-10-12: every probe as a self-contained copy in <Desktop>/Driver Probe Tests (OneDrive -> laptop)
    subprocess.run([sys.executable, str(HERE / "publish_playable.py"), "--probes"], check=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "sync":
        sync()
    else:
        for name, p in load().items():
            print("%-14s %s%s  (%s)" % (name, p["lev"], " [%s]" % p["build"] if "build" in p else "", p.get("what", "")))
