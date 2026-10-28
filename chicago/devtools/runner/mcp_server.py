"""runner.mcp_server - the Q42 runner as an MCP server (stdio, JSON-RPC 2.0, no extra packages).

    python driver_personal/chicago/devtools/runner/mcp_server.py      (register as a stdio MCP server)

One game session at a time on a test copy (default devtest/runner, port 4468, build-test); never build-dev. Every tool
returns compact JSON (paths, numbers); screenshots / WAVs / logs stay on disk. stdout carries only protocol messages
(everything the tools print goes to stderr).
"""
from __future__ import annotations

import contextlib, json, math, sys, time, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from runner.session import Session, StepFailed, CITY, AREA, VSYNC, LOADING  # noqa: E402
from runner import __main__ as cli  # noqa: E402

OUT = sys.stdout
S: Session | None = None


def _num(v):
    return int(v, 0) if isinstance(v, str) else int(v)


def t_launch(a):
    global S
    if S is not None:
        return {"error": "a session is running; call stop first", "dir": str(S.dir)}
    kw = {k: a[k] for k in ("day", "night", "s4", "port", "copy", "build", "dev_mode") if k in a}
    S = Session(a.get("name", "mcp"), quiet=True, **kw)
    S.start()
    return {"ok": True, "dir": str(S.dir), "pid": S.p.pid, "port": S.port}


def t_stop(a):
    global S
    if S is None:
        return {"ok": True, "note": "no session"}
    S.stop(); d = S.dir; dumps = getattr(S, "new_dumps", []); S = None
    return {"ok": True, "dir": str(d), "hang_dumps": dumps}


def need():
    if S is None:
        raise StepFailed("no session: call launch first")
    return S


def t_status(a):
    s = need()
    x, y, z, h, dmg = s.car(0)
    return {"pos": [x, y, z], "heading_deg": round(math.degrees(h)), "damage": dmg, "city": s.word(CITY),
            "area": s.word(AREA), "loading": s.word(LOADING), "vsync": s.word(VSYNC), "frame": s.d.frame()}


def t_menu(a):
    need().menu(a["path"]); return t_status(a)


def t_pose(a):
    need().pose(_num(a["x"]), _num(a["z"]), math.radians(float(a.get("heading_deg", 0)))); return t_status(a)


def t_press(a):
    need().press(*a["buttons"], hold=float(a.get("hold", 0.12)), gap=float(a.get("gap", 0.5))); return {"ok": True}


def t_hold(a):
    s = need(); s.hold(*a["buttons"]); time.sleep(float(a.get("secs", 1.0))); s.release(); return t_status(a)


def t_drive(a):
    s = need(); h = a.get("heading_deg")
    s.drive(float(a.get("secs", 5)), None if h is None else math.radians(float(h))); return t_status(a)


def t_read_ram(a):
    s = need(); n = min(_num(a.get("len", 4)), 256)
    return {"addr": "%08x" % _num(a["addr"]), "hex": s.ram(_num(a["addr"]), n).hex()}


def t_write_word(a):
    need().poke32(_num(a["addr"]), _num(a["value"])); return {"ok": True}


def t_wait_word(a):
    s = need(); addr, want = _num(a["addr"]), _num(a["value"])
    ok = s.wait_for(lambda: s.word(addr) == want, float(a.get("timeout", 30)), "word %08x == %x" % (addr, want), fail=False)
    return {"ok": ok, "value": "%x" % s.word(addr)}


def t_screenshot(a):
    s = need(); p = s.screenshot(a.get("name", "shot%d" % int(time.time())), a.get("baseline"), float(a.get("tol", 12)))
    res = {"path": str(p)}
    if a.get("baseline"):
        res["check"] = s.checks[-1]
    return res


def t_audio(a):
    p, m = need().audio(a.get("name", "audio%d" % int(time.time())), float(a.get("secs", 5)), int(a.get("tap", 0)))
    return {"path": str(p), "metrics": m}


def t_list_tests(a):
    return {"tests": sorted(p.stem for p in cli.TESTS.glob("*.py") if p.stem != "__init__")}


def t_run_test(a):
    if S is not None:
        return {"error": "stop the interactive session first (same copy / port)"}
    v = cli.run_one(a["name"], {k: a[k] for k in ("port", "copy", "build") if k in a})
    runs = sorted(Path(cli.RUNS).glob("*-" + a["name"]), key=lambda p: p.stat().st_mtime)
    res = json.loads((runs[-1] / "result.json").read_text()) if runs else {}
    return {"verdict": v, "dir": res.get("dir"), "checks": res.get("checks", []), "error": res.get("error", "")}


S_OBJ = {"type": "object"}
TOOLS = {
    "launch": (t_launch, "Start a game session on a test copy (build-test by default; never build-dev).",
               {"type": "object", "properties": {"name": {"type": "string"}, "day": {"type": "string"}, "night": {"type": "string"},
                "s4": {"type": "boolean"}, "port": {"type": "integer"}, "copy": {"type": "string"}, "build": {"type": "string"}}}),
    "stop": (t_stop, "Stop the session (kills its own PID) and list real hang dumps.", S_OBJ),
    "status": (t_status, "Player position / heading / damage, city, area, loading flag, VSync and frame counters.", S_OBJ),
    "menu": (t_menu, "Navigate from the title: take_a_ride/<miami|frisco|la|ny|newtown|interview|desert|chicago>[/night] "
                     "or undercover/new_game; waits until in level.",
             {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}),
    "pose": (t_pose, "TELEPORT the player (Chicago / LA; Driver 1 x, z, heading in degrees): holds the car until the world there "
                     "is loaded and drawn (area load done, region stable, no CD reads for 1.5 s; fails loudly otherwise), "
                     "then releases it and re-poses at the ground height if it was off. Not 'start at spot': for a level start "
                     "at a position use launch with a package start (dt.prepare start / CHI_START).",
             {"type": "object", "properties": {"x": {"type": "integer"}, "z": {"type": "integer"}, "heading_deg": {"type": "number"}},
              "required": ["x", "z"]}),
    "press": (t_press, "Tap buttons (cross, square, circle, triangle, up, down, left, right, l1, r1, l2, r2, start, select).",
              {"type": "object", "properties": {"buttons": {"type": "array", "items": {"type": "string"}}, "hold": {"type": "number"}},
               "required": ["buttons"]}),
    "hold": (t_hold, "Hold buttons for secs, then release.",
             {"type": "object", "properties": {"buttons": {"type": "array", "items": {"type": "string"}}, "secs": {"type": "number"}},
              "required": ["buttons"]}),
    "drive": (t_drive, "Throttle for secs; optional heading_deg to hold (reverses when stuck).",
              {"type": "object", "properties": {"secs": {"type": "number"}, "heading_deg": {"type": "number"}}}),
    "read_ram": (t_read_ram, "Read up to 256 bytes of guest RAM (hex).",
                 {"type": "object", "properties": {"addr": {"type": "string"}, "len": {"type": "integer"}}, "required": ["addr"]}),
    "write_word": (t_write_word, "Write one 32-bit word of guest RAM (test copies only).",
                   {"type": "object", "properties": {"addr": {"type": "string"}, "value": {"type": "string"}}, "required": ["addr", "value"]}),
    "wait_word": (t_wait_word, "Wait until a RAM word equals value (timeout s).",
                  {"type": "object", "properties": {"addr": {"type": "string"}, "value": {"type": "string"}, "timeout": {"type": "number"}},
                   "required": ["addr", "value"]}),
    "screenshot": (t_screenshot, "Save a screenshot (path); with baseline: mean-abs-diff check against that PNG.",
                   {"type": "object", "properties": {"name": {"type": "string"}, "baseline": {"type": "string"}, "tol": {"type": "number"}}}),
    "audio_capture": (t_audio, "Capture the last secs of game audio to WAV (tap 0 SPU out, 3 voices) + metrics (rms, clicks, silences).",
                      {"type": "object", "properties": {"name": {"type": "string"}, "secs": {"type": "number"}, "tap": {"type": "integer"}}}),
    "list_tests": (t_list_tests, "List the scripted tests (runner/tests).", S_OBJ),
    "run_test": (t_run_test, "Run one scripted test end to end; returns verdict, checks and the run dir.",
                 {"type": "object", "properties": {"name": {"type": "string"}, "port": {"type": "integer"}}, "required": ["name"]}),
}


def send(msg):
    OUT.write(json.dumps(msg) + "\n"); OUT.flush()


def handle(req):
    m, rid = req.get("method"), req.get("id")
    if m == "initialize":
        return {"protocolVersion": req.get("params", {}).get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}}, "serverInfo": {"name": "driver-runner", "version": "0.1"}}
    if m == "tools/list":
        return {"tools": [{"name": n, "description": d, "inputSchema": sch} for n, (_, d, sch) in TOOLS.items()]}
    if m == "tools/call":
        p = req.get("params", {}); fn = TOOLS.get(p.get("name"), (None,))[0]
        if fn is None:
            return {"content": [{"type": "text", "text": "unknown tool %s" % p.get("name")}], "isError": True}
        try:
            with contextlib.redirect_stdout(sys.stderr):
                res = fn(p.get("arguments") or {})
            return {"content": [{"type": "text", "text": json.dumps(res)}], "isError": "error" in res}
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            return {"content": [{"type": "text", "text": "%s: %s" % (type(e).__name__, e)}], "isError": True}
    if m == "ping":
        return {}
    if rid is None:
        return None                                   # notifications (initialized, cancelled)
    raise KeyError(m)


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        try:
            res = handle(req)
            if req.get("id") is not None and res is not None:
                send({"jsonrpc": "2.0", "id": req["id"], "result": res})
        except KeyError as e:
            send({"jsonrpc": "2.0", "id": req.get("id"), "error": {"code": -32601, "message": "method not found: %s" % e}})
    if S is not None:
        S.stop()


if __name__ == "__main__":
    main()
