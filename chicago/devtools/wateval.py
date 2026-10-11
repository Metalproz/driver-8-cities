"""wateval.py [SINCE] [SPOTS..] - latest lab captures/soaks per spot: one line each + one sheet.

SINCE = job id prefix time (MMDDHHMMSS) to ignore older results (default: all).
"""
import glob, json, sys
from pathlib import Path
import dt

RES = dt.TEST / "_lab" / "results"
since = sys.argv[1] if len(sys.argv) > 1 else "0"
spots = sys.argv[2:] or ["riverbridge", "bridge", "quay", "inwater", "beach_s", "beach_n",
                         "park", "overpass_s", "north", "blackroofs", "missingbld"]
imgs, labels = [], []
for s in spots:
    for kind in ("capture", "soak"):
        ds = [d for d in glob.glob(str(RES / ("*_%s_%s_*" % (kind, s)))) if Path(d).name.split("_")[1] >= since]
        if not ds:
            continue
        d = Path(max(ds, key=lambda p: Path(p).name.split("_")[1]))
        j = json.loads((d / "job.json").read_text()) if (d / "job.json").exists() else {}
        r = j.get("result", {})
        bad = [k for k in ("fatal", "hang", "error") if r.get(k)]
        if kind == "capture":
            print("%-11s cap  pos %-24s end %-24s area %s->%s %s" % (
                s, r.get("pos"), r.get("end_pos"), r.get("area"), r.get("end_area"), " ".join("%s=%s" % (k, str(r[k])[:50]) for k in bad)))
            for f in ("start", "drive2", "drive4"):
                imgs.append(d / (f + ".png")); labels.append("%s %s" % (s, f))
        else:
            a = r.get("areas", [])
            print("%-11s soak steps %s dist %s switches %d last %s %s" % (
                s, r.get("steps_done"), r.get("dist"), max(0, len(a) - 1), r.get("last_pos"),
                " ".join("%s=%s" % (k, str(r[k])[:50]) for k in bad)))
out = RES / "wateval.png"
dt.sheet(imgs, out, labels)
print("sheet", out)
