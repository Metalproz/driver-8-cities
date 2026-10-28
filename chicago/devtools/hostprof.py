"""Host sampling profiler for a running Driver_Recompiled.exe (Windows, no admin): suspends each thread every
--interval ms, reads RIP, resumes; maps RIP to module (+ symbol from an lld /MAP file for the exe). Read-only.

  python hostprof.py PID [--secs 10] [--interval 1] [--map build-wip/Driver_Recompiled.map] [--top 40]
"""
import argparse, bisect, collections, ctypes, ctypes.wintypes as W, re, sys, time

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
TH32CS_SNAPTHREAD = 0x4
THREAD_ALL = 0x0002 | 0x0008 | 0x0010 | 0x0040   # suspend/resume, get context, query info
PROCESS_QUERY_VM = 0x0400 | 0x0010
CONTEXT_AMD64, CONTEXT_CONTROL = 0x100000, 0x100001


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ThreadID", W.DWORD), ("th32OwnerProcessID", W.DWORD),
                ("tpBasePri", W.LONG), ("tpDeltaPri", W.LONG), ("dwFlags", W.DWORD)]


class MODULEINFO(ctypes.Structure):
    _fields_ = [("lpBaseOfDll", ctypes.c_void_p), ("SizeOfImage", W.DWORD), ("EntryPoint", ctypes.c_void_p)]


CTX_SIZE = 1232
RIP_OFF = 0xF8


def threads(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    te = THREADENTRY32(); te.dwSize = ctypes.sizeof(te)
    out = []
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            out.append(te.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    return out


def modules(pid):
    h = k32.OpenProcess(PROCESS_QUERY_VM, False, pid)
    arr = (ctypes.c_void_p * 1024)(); need = W.DWORD()
    psapi.EnumProcessModulesEx(h, arr, ctypes.sizeof(arr), ctypes.byref(need), 3)
    mods = []
    for i in range(need.value // ctypes.sizeof(ctypes.c_void_p)):
        name = ctypes.create_unicode_buffer(260)
        psapi.GetModuleBaseNameW(h, ctypes.c_void_p(arr[i]), name, 260)
        mi = MODULEINFO()
        psapi.GetModuleInformation(h, ctypes.c_void_p(arr[i]), ctypes.byref(mi), ctypes.sizeof(mi))
        mods.append((mi.lpBaseOfDll, mi.lpBaseOfDll + mi.SizeOfImage, name.value))
    k32.CloseHandle(h)
    return sorted(mods)


def load_map(path):
    """llvm-nm --defined-only -n output ('addr t name') or an lld /MAP file -> sorted (rva, name)"""
    syms = []
    try:
        for ln in open(path, errors="ignore"):
            m = re.match(r"([0-9a-fA-F]{8,16}) [tT] (\S+)$", ln.strip())
            if m: syms.append((int(m.group(1), 16) - 0x140000000, m.group(2)))
    except OSError:
        pass
    if syms:
        syms.sort(); return syms
    return load_lld_map(path)


def load_lld_map(path):
    """lld-link /MAP: lines '  Address  Size  Align  Out  In  Symbol' -> (rva, name)"""
    syms = []
    base = 0x140000000
    try:
        for ln in open(path, errors="ignore"):
            m = re.match(r"\s*([0-9a-fA-F]{8,16})\s+([0-9a-fA-F]+)\s+\d+\s+(\S+)$", ln)
            if m and not m.group(3).startswith(("<", ".")):
                syms.append((int(m.group(1), 16) - base, m.group(3)))
    except OSError:
        pass
    syms.sort()
    return syms


def pe_exports(path):
    """(rva, name) of a DLL's exports, sorted (minimal PE parser)."""
    import struct as st
    try:
        b = open(path, "rb").read()
    except OSError:
        return []
    pe = st.unpack_from("<I", b, 0x3C)[0]
    nsec = st.unpack_from("<H", b, pe + 6)[0]; opt = pe + 24
    exp_rva = st.unpack_from("<I", b, opt + 112)[0]
    secs = [st.unpack_from("<8sIIII", b, opt + st.unpack_from("<H", b, pe + 20)[0] + 40 * i) for i in range(nsec)]
    def off(rva):
        for _, vs, va, rs, rp in secs:
            if va <= rva < va + max(vs, rs): return rva - va + rp
        return None
    e = off(exp_rva)
    if e is None: return []
    nn, af, an, ao = st.unpack_from("<I", b, e + 24)[0], *st.unpack_from("<III", b, e + 28)
    funcs, names, ords = off(af), off(an), off(ao)
    out = []
    for i in range(nn):
        nm_off = off(st.unpack_from("<I", b, names + 4 * i)[0]); o = st.unpack_from("<H", b, ords + 2 * i)[0]
        rva = st.unpack_from("<I", b, funcs + 4 * o)[0]
        out.append((rva, b[nm_off:b.index(bytes(1), nm_off)].decode(errors="ignore")))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pid", type=int)
    ap.add_argument("--secs", type=float, default=10)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--map", default=None)
    ap.add_argument("--top", type=int, default=40)
    a = ap.parse_args()
    mods = modules(a.pid)
    exe = next((m for m in mods if m[2].lower().endswith(".exe")), None)
    syms = load_map(a.map) if a.map else []
    keys = [s[0] for s in syms]
    hs = {}
    exports = {}
    for tid in threads(a.pid):
        h = k32.OpenThread(THREAD_ALL, False, tid)
        if h: hs[tid] = h
    ctx = (ctypes.c_byte * (CTX_SIZE + 16))()
    addr = (ctypes.addressof(ctx) + 15) & ~15
    per_thread = collections.Counter(); per_sym = collections.Counter(); per_mod = collections.Counter()
    t_end = time.time() + a.secs; n = 0
    while time.time() < t_end:
        for tid, h in hs.items():
            if k32.SuspendThread(h) == 0xFFFFFFFF: continue
            ctypes.memset(addr, 0, CTX_SIZE)
            ctypes.c_uint32.from_address(addr + 0x30).value = CONTEXT_CONTROL
            ok = k32.GetThreadContext(h, ctypes.c_void_p(addr))
            k32.ResumeThread(h)
            if not ok: continue
            rip = ctypes.c_uint64.from_address(addr + RIP_OFF).value
            mod = next((m for m in mods if m[0] <= rip < m[1]), None)
            mname = mod[2] if mod else "?"
            per_mod[(tid, mname)] += 1
            if mod is exe and syms:
                i = bisect.bisect_right(keys, rip - exe[0]) - 1
                per_sym[(tid, syms[i][1] if i >= 0 else "?")] += 1
            elif mod is exe:
                per_sym[(tid, "exe+%06X" % ((rip - exe[0]) >> 12 << 12))] += 1
            elif mname.lower() in ("ntdll.dll", "kernelbase.dll", "win32u.dll"):
                ex = exports.setdefault(mname, pe_exports("C:/Windows/System32/" + mname))
                ks = [x[0] for x in ex]
                j = bisect.bisect_right(ks, rip - mod[0]) - 1
                per_sym[(tid, mname + "!" + (ex[j][1] if j >= 0 else "?"))] += 1
            else:
                per_sym[(tid, mname)] += 1
            per_thread[tid] += 1
        n += 1
        time.sleep(a.interval / 1000.0)
    tot = sum(per_thread.values()) or 1
    print("samples %d rounds, threads %s" % (n, dict(per_thread.most_common(6))))
    exe_name = exe[2] if exe else ""
    busy = collections.Counter({t: v for (t, m), v in per_mod.items() if m == exe_name})
    print("exe samples per thread: %s" % dict(busy.most_common(6)))
    busiest = busy.most_common(1)[0][0] if busy else (per_thread.most_common(1)[0][0] if per_thread else None)
    WAIT = ("ntdll.dll", "win32u.dll", "KERNELBASE.dll")
    print("per-thread busy (samples outside %s):" % (WAIT,))
    for t in per_thread:
        tot_t = sum(v for (tt, m), v in per_mod.items() if tt == t) or 1
        busy_t = sum(v for (tt, m), v in per_mod.items() if tt == t and m not in WAIT)
        mods = sorted(((v, m) for (tt, m), v in per_mod.items() if tt == t and m not in WAIT), reverse=True)[:4]
        print("  thread %6d: %5.1f %% busy  %s" % (t, 100.0 * busy_t / tot_t, ", ".join("%s %.1f%%" % (m, 100.0 * v / tot_t) for v, m in mods)))
    print("per-thread top symbols:")
    for t in per_thread:
        tot_t = per_thread[t] or 1
        top = sorted(((v, sy) for (tt, sy), v in per_sym.items() if tt == t), reverse=True)[:5]
        print("  thread %6d: %s" % (t, ", ".join("%s %.0f%%" % (sy, 100.0 * v / tot_t) for v, sy in top)))
    print("modules (busiest thread %s):" % busiest)
    bt = sum(v for (t, _), v in per_mod.items() if t == busiest) or 1
    for (t, m), v in per_mod.most_common():
        if t == busiest: print("  %5.1f %%  %s" % (100.0 * v / bt, m))
    print("top symbols (busiest thread):")
    k = 0
    for (t, s), v in per_sym.most_common():
        if t != busiest: continue
        print("  %5.1f %%  %s" % (100.0 * v / bt, s)); k += 1
        if k >= a.top: break


if __name__ == "__main__":
    main()
