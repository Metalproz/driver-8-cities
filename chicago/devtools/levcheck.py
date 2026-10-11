"""levcheck.py - independent check of a LEV with OpenDriver2Tools' DriverLevelTool.

    python levcheck.py LEV [--world] [--vs OTHER.LEV] [--keep]

Copies the LEV to <app>/devtest/_out/levcheck/<name>/, runs DriverLevelTool
(textures always, world OBJ with --world), and prints a compact summary:
loader warnings/errors, texture pages written, and with --world the OBJ
object/vertex/face counts plus the 12 most common object-name prefixes.
--vs runs the same on a second LEV and prints the deltas (e.g. converted
Chicago vs the Driver 2 original, or vs LA). The OBJ (100-250 MB) is deleted
unless --keep. Takes ~1-3 min per LEV with --world.
"""
from __future__ import annotations

import argparse, collections, re, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent.parent.parent
TOOL = Path("D:/recomps/refs/OpenDriver2Tools-bin/DriverLevelTool_Release/DriverLevelTool.exe")
OUT = APP / "devtest" / "_out" / "levcheck"
BAD = re.compile(r"error|warn|bad|fail|invalid|unknown|overflow|corrupt", re.I)


def check(lev: Path, world: bool, keep: bool) -> dict:
    name = re.sub(r"[^A-Za-z0-9_]+", "_", lev.stem).upper()
    d = OUT / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    src = d / (name + ".LEV")
    shutil.copyfile(lev, src)
    args = [str(TOOL), src.name, "-textures", "1"] + (["-world", "1"] if world else [])
    t0 = time.time()
    p = subprocess.run(args, cwd=d, capture_output=True, text=True, errors="replace", timeout=1800)
    log = p.stdout + p.stderr
    (d / "tool.log").write_text(log, encoding="utf-8")
    r = {"name": name, "exit": p.returncode, "secs": round(time.time() - t0),
         "bad": [l.strip() for l in log.splitlines() if BAD.search(l) and "Writing texture" not in l],
         "pages": len(list((d / (name + "_textures")).glob("PAGE_*.tga"))) if (d / (name + "_textures")).exists() else 0}
    obj = d / (name + "_LEVELMODEL.obj")
    if world and obj.exists():
        o = v = f = 0
        pre = collections.Counter()
        with open(obj, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("v "):
                    v += 1
                elif line.startswith("f "):
                    f += 1
                elif line.startswith("o "):
                    o += 1
                    pre[re.sub(r"[\d_]+$", "", line[2:].strip().split("_")[0])] += 1
        r.update(objects=o, verts=v, faces=f, obj_mb=round(obj.stat().st_size / 1e6), prefixes=pre.most_common(12))
        if not keep:
            obj.unlink()
    src.unlink()
    return r


def show(r):
    print(f"{r['name']}: exit {r['exit']}, {r['secs']}s, texture pages {r['pages']}, "
          f"suspicious log lines {len(r['bad'])}")
    for l in r["bad"][:8]:
        print("   ", l[:160])
    if "objects" in r:
        print(f"    OBJ: objects {r['objects']}, verts {r['verts']}, faces {r['faces']} ({r['obj_mb']} MB)")
        print("    names:", ", ".join(f"{k} {n}" for k, n in r["prefixes"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lev")
    ap.add_argument("--world", action="store_true")
    ap.add_argument("--vs")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    if not TOOL.exists():
        sys.exit(f"missing {TOOL} (unzip DriverLevelTool_Release.zip from OpenDriver2Tools 1.10)")
    r1 = check(Path(a.lev), a.world, a.keep)
    show(r1)
    if a.vs:
        r2 = check(Path(a.vs), a.world, a.keep)
        show(r2)
        if "objects" in r1 and "objects" in r2:
            print("delta (first - second): " + ", ".join(
                f"{k} {r1[k] - r2[k]:+d}" for k in ("objects", "verts", "faces", "pages")))


if __name__ == "__main__":
    main()
