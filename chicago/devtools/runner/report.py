"""runner.report - one self-contained HTML page per run (steps, checks, screenshots, WAV players)."""
from __future__ import annotations

import html, json
from pathlib import Path


def write(run_dir: Path):
    run_dir = Path(run_dir)
    res = json.loads((run_dir / "result.json").read_text()) if (run_dir / "result.json").exists() else {}
    steps = [json.loads(l) for l in (run_dir / "steps.jsonl").read_text().splitlines() if l.strip()] \
        if (run_dir / "steps.jsonl").exists() else []
    v = res.get("verdict", "?")
    col = {"pass": "#1a7f37", "fail": "#cf222e", "error": "#9a6700"}.get(v, "#555")
    rows = "".join("<tr class='%s'><td>%.1f</td><td>%s</td><td>%s</td></tr>" % (
        "" if e.get("ok", True) else "bad", e["t"], html.escape(e["step"]), html.escape(str(e.get("detail", ""))))
        for e in steps)
    checks = "".join("<li class='%s'>%s %s: %s</li>" % ("" if c["ok"] else "bad", "&#10003;" if c["ok"] else "&#10007;",
                     html.escape(c["name"]), html.escape(c["detail"])) for c in res.get("checks", []))
    media = "".join("<figure><img src='%s'><figcaption>%s</figcaption></figure>" % (p.name, p.stem)
                    for p in sorted(run_dir.glob("*.png")))
    media += "".join("<figure><audio controls src='%s'></audio><figcaption>%s</figcaption></figure>" % (p.name, p.stem)
                     for p in sorted(run_dir.glob("*.wav")))
    page = """<!doctype html><meta charset="utf-8"><title>%(t)s</title>
<style>body{font:14px system-ui,sans-serif;margin:16px;background:#fff;color:#111}h1{font-size:18px}
.v{color:#fff;background:%(c)s;padding:2px 8px;border-radius:4px}table{border-collapse:collapse;width:100%%}
td{border-bottom:1px solid #ddd;padding:2px 6px;vertical-align:top}.bad{color:#cf222e}
figure{display:inline-block;margin:6px}img{max-width:512px;border:1px solid #ccc}
@media (prefers-color-scheme:dark){body{background:#111;color:#ddd}td{border-color:#333}}</style>
<h1>%(t)s <span class="v">%(v)s</span></h1><p>%(e)s %(s)s s, dumps: %(d)s</p><h2>Checks</h2><ul>%(ch)s</ul>
<h2>Media</h2>%(m)s<h2>Steps</h2><table>%(r)s</table>""" % {
        "t": html.escape(res.get("test", run_dir.name)), "c": col, "v": v, "e": html.escape(res.get("error", "")),
        "s": res.get("secs", "?"), "d": html.escape(" ".join(res.get("dumps", [])) or "none"), "ch": checks,
        "m": media, "r": rows}
    (run_dir / "report.html").write_text(page, encoding="utf-8")
