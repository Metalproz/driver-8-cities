"""run.py - quiet runner: full output goes to a log file, only a capped head/tail is printed.

    python run.py [--head N] [--tail N] [--grep REGEX] [--name TAG] -- CMD ARGS...

Defaults: head 15, tail 25 lines. Log: <app>/devtest/_out/logs/<time>-<tag>.log.
Exit code = the command's exit code. Use this for the converter, package builds,
exports, soaks and probes so chat context stays small.
"""
from __future__ import annotations

import argparse, os, re, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent.parent.parent
LOGS = APP / "devtest" / "_out" / "logs"


def main():
    try:
        sys.stdout.reconfigure(errors="replace")   # generator output carries non-cp1252 characters
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--head", type=int, default=15)
    ap.add_argument("--tail", type=int, default=25)
    ap.add_argument("--grep", help="also print every line matching this regex (max 40)")
    ap.add_argument("--name", help="tag for the log file name")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    if not cmd:
        ap.error("no command")
    LOGS.mkdir(parents=True, exist_ok=True)
    tag = a.name or re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(cmd[-1] if cmd[0].lower().startswith("python") and len(cmd) > 1 else cmd[0]).stem)[:40]
    log = LOGS / (time.strftime("%m%d-%H%M%S") + "-" + tag + ".log")
    t0 = time.time()
    lines = []
    with open(log, "w", encoding="utf-8", errors="replace") as f:
        f.write("$ " + " ".join(cmd) + "\n")
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace", cwd=os.getcwd())
        for line in p.stdout:
            f.write(line)
            lines.append(line.rstrip("\n"))
        rc = p.wait()
    n = len(lines)
    print(f"log: {log}  ({n} lines, {time.time() - t0:.0f}s, exit {rc})")
    if n <= a.head + a.tail:
        print("\n".join(lines))
    else:
        print("\n".join(lines[:a.head]))
        print(f"... ({n - a.head - a.tail} lines omitted) ...")
        print("\n".join(lines[-a.tail:]))
    if a.grep:
        rx = re.compile(a.grep, re.I)
        hits = [l for l in lines if rx.search(l)]
        if hits:
            print(f"-- {len(hits)} lines match /{a.grep}/:")
            print("\n".join(hits[:40]))
    sys.exit(rc)


if __name__ == "__main__":
    main()
