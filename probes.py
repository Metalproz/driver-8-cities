"""probes.py - keep the user's probe shortcuts in sync with probes.json.

    python driver_personal/probes.py sync     desktop: create "Driver (probe - NAME)" for every probe in
                                              probes.json, remove every other "Driver (probe - *)" shortcut
    python driver_personal/probes.py list     show the current probes

A probe = the dev client's exe + a test level, started at a chosen spot (spotplay.py --lev).
The laptop copy gets the same probes from publish_playable.py (it reads probes.json too).
"""
from __future__ import annotations

import json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
CHI = HERE / "chicago"
PROBES = HERE / "probes.json"
PREFIX = "Driver (probe - "

BAT = ('@echo off\r\nrem PROBE "{name}": {what}\r\nrem = dev-client exe + {lev}. Separate test copy; the dev client is untouched.\r\n'
       'cd /d "%~dp0driver_personal\\chicago\\devtools"\r\n'
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
        bat = APP / (PREFIX + name + ").bat")
        bat.write_text(BAT.format(name=name, what=p.get("what", ""), lev=p["lev"]), encoding="ascii", newline="")
        make_lnk(desk / (PREFIX + name + ").lnk"), bat)
        print("probe ok:", name, "->", p["lev"])
    for f in list(APP.glob(PREFIX + "*).bat")) + list(desk.glob(PREFIX + "*).lnk")):
        if f.stem not in want:
            f.unlink()
            print("removed outdated:", f.name)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "sync":
        sync()
    else:
        for name, p in load().items():
            print("%-14s %s  (%s)" % (name, p["lev"], p.get("what", "")))
