"""probe_tiles.py SPOT - trace the ground-tile draw functions for one frame."""
import sys, json, time, collections, struct
import dt
spot = sys.argv[1]
dt.prepare("probe", dt.spots()[spot]["d2"])
p, d = dt.launch("probe", 4420)
try:
    dt.to_take_a_ride(d)
    d.cmd("fn_filter", lo="0x80026000", hi="0x8002A000")
    d.cmd("fn_clear")
    time.sleep(0.5)
    st = d.cmd("fn_stats")
    hi = st["entry_total"]
    r = d.cmd("fn_entry_dump", count=60000, seq_lo=max(0, hi - 60000), seq_hi=hi)
    ents = r.get("entries", [])
    frames = collections.Counter(e["frame"] for e in ents)
    f = sorted(frames)[-2] if len(frames) > 1 else sorted(frames)[-1]
    fe = [e for e in ents if e["frame"] == f]
    out = dt.run_dir("probe-" + spot)
    json.dump(fe, open(out / "fn.json", "w"))
    (out / "ram.bin").write_bytes(d.ram_all()); (out / "mod.bin").write_bytes(d.mod_all())
    d.shot(out / "screen.png")
    c = collections.Counter(e["func"] for e in fe)
    print("frame", f, "calls", len(fe), "by function:", c.most_common(14))
    print("out", out)
finally:
    p.kill()
