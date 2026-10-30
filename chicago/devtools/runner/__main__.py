"""python -m runner (cwd devtools): scripted game tests on test copies (Q42).

    python -m runner list                          the tests in runner/tests
    python -m runner run NAME [NAME ...] [--port 4468] [--copy runner] [--build build-test]
    python -m runner report RUN_DIR                rebuild a run's report.html

A test is runner/tests/<name>.py with SESSION = {...Session kwargs...} and run(s). Each run writes
devtest/_out/runner/<time>-<name>/ (steps.jsonl, result.json, report.html, screenshots, WAVs, game.log); the console
shows <= 60 step lines + one verdict line per test.
"""
from __future__ import annotations

import importlib.util, json, sys, time, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from runner.session import Session, StepFailed, RUNS  # noqa: E402
from runner import report  # noqa: E402

TESTS = HERE / "tests"


def load(name):
    path = TESTS / (name if name.endswith(".py") else name + ".py")
    spec = importlib.util.spec_from_file_location("runner_test_" + path.stem, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def run_one(name, overrides):
    mod = load(name)
    kw = dict(getattr(mod, "SESSION", {})); kw.update(overrides)
    s = Session(Path(name).stem, **kw)
    verdict, err = "pass", ""
    try:
        with s:
            mod.run(s)
    except StepFailed as e:
        verdict, err = "fail", str(e)
    except Exception as e:                         # a broken test or tool, not a game result
        verdict, err = "error", "%s: %s" % (type(e).__name__, e)
        (s.dir / "traceback.txt").write_text(traceback.format_exc())
    if verdict == "pass" and any(not c["ok"] for c in s.checks):
        verdict = "fail"
    if verdict == "pass" and (getattr(s, "new_dumps", None) or any(e["step"] == "crash" for e in s.steps)):
        verdict = "fail"
    res = {"test": s.test, "verdict": verdict, "error": err, "secs": round(time.time() - s.t0, 1),
           "checks": s.checks, "dumps": getattr(s, "new_dumps", []), "dir": str(s.dir)}
    (s.dir / "result.json").write_text(json.dumps(res, indent=1))
    report.write(s.dir)
    print("%s %-24s %5.0fs  checks %d/%d  %s  %s" % (verdict.upper(), s.test, res["secs"],
          sum(c["ok"] for c in s.checks), len(s.checks), err[:80], s.dir), flush=True)
    return verdict


def main(argv):
    if not argv or argv[0] == "list":
        for p in sorted(TESTS.glob("*.py")):
            if p.stem != "__init__":
                doc = (load(p.stem).__doc__ or "").strip().splitlines()
                print("%-24s %s" % (p.stem, doc[0] if doc else ""))
        return 0
    if argv[0] == "report":
        report.write(Path(argv[1])); return 0
    if argv[0] == "run":
        names, ov, i = [], {}, 1
        while i < len(argv):
            a = argv[i]
            if a in ("--port", "--copy", "--build", "--day", "--night"):   # --day / --night: Chicago's levels (work/ names)
                ov[a[2:]] = int(argv[i + 1]) if a == "--port" else argv[i + 1]; i += 2
            elif a == "--reuse":
                ov["reuse"] = True; i += 1
            else:
                names.append(a); i += 1
        bad = [n for n in names if run_one(n, ov) != "pass"]
        return 1 if bad else 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
