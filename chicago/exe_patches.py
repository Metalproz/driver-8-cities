"""exe_patches.py — generate guarded main_exe patches that move Driver 1's
model pointer table (800 entries at 0x800A0E20) to expansion memory.

Every reference is a `lui rX, 0x000A` followed (before rX is redefined) by
addiu/lw/sw rY, 0x0E20+k(rX). Both instructions are retargeted to NEW_BASE.
The scan is exhaustive over the EXE text and refuses any lui whose register
is used for anything else before it is redefined (or a call clobbers it).
"""
from __future__ import annotations

import os, struct

OLD_BASE, OLD_END = 0x000A0E20, 0x000A1AA0     # 800 x 4 bytes
NEW_BASE = 0x9F000000                          # first psx_mod_alloc_guest_memory block
NEW_ENTRIES = 2048

MEMOPS = {0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x28, 0x29, 0x2A, 0x2B, 0x2E}
CALL_CLOBBERS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 24, 25, 31}


def load_exe(path):
    data = open(path, "rb").read()
    assert data[:8] == b"PS-X EXE"
    t_addr, t_size = struct.unpack_from("<II", data, 0x18)
    return data[0x800:0x800 + t_size], 0x80000000 | (t_addr & 0x1FFFFFFF)


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def reads(w, r):
    op, rs, rt = w >> 26, (w >> 21) & 31, (w >> 16) & 31
    if op == 0:
        return r in (rs, rt)
    if op in (0x04, 0x05) or op in (0x28, 0x29, 0x2A, 0x2B, 0x2E):
        return r in (rs, rt)
    if op in (0x02, 0x03, 0x0F):
        return False
    return rs == r


def writes(w, r):
    op = w >> 26
    if op == 0:
        funct = w & 0x3F
        if funct in (0x08, 0x18, 0x19, 0x1A, 0x1B, 0x11, 0x13, 0x0C, 0x0D):
            return False
        return ((w >> 11) & 31) == r
    if op == 0x03:
        return r in CALL_CLOBBERS
    if op in (0x01, 0x02, 0x04, 0x05, 0x06, 0x07) or op in (0x28, 0x29, 0x2A, 0x2B, 0x2E):
        return False
    return ((w >> 16) & 31) == r


def find_sites(exe_path, window=48):
    img, base = load_exe(exe_path)
    n = len(img) // 4
    words = struct.unpack_from("<%dI" % n, img)
    sites = []
    for i, x in enumerate(words):
        if x >> 26 != 0x0F:
            continue
        r = (x >> 16) & 31
        hi = (x & 0xFFFF) << 16
        uses, bad = [], False
        j = i + 1
        while j < min(n, i + window):
            y = words[j]
            op = y >> 26
            if reads(y, r):
                if (op == 0x09 or op in MEMOPS) and ((y >> 21) & 31) == r:
                    uses.append((j, (hi + s16(y & 0xFFFF)) & 0x1FFFFFFF))
                else:
                    uses.append((j, None))
            # a jal's delay slot executes before the call clobbers registers
            if op == 0x03 and j + 1 < n and reads(words[j + 1], r):
                y2 = words[j + 1]
                if ((y2 >> 26) == 0x09 or (y2 >> 26) in MEMOPS) and ((y2 >> 21) & 31) == r:
                    uses.append((j + 1, (hi + s16(y2 & 0xFFFF)) & 0x1FFFFFFF))
                j += 1
            if writes(y, r) or op in (0x02,) or (op == 0 and (y & 0x3F) == 0x08):
                break
            j += 1
        hits = [(k, ea) for k, ea in uses if ea is not None and OLD_BASE <= ea < OLD_END]
        if not hits:
            continue
        others = [(k, ea) for k, ea in uses if ea is None or not (OLD_BASE <= ea < OLD_END)]
        sites.append({"lui": (base + 4 * i, x), "uses": [(base + 4 * k, words[k], ea) for k, ea in hits],
                      "conflicts": [(base + 4 * k, ea) for k, ea in others]})
    return sites


def patches(exe_path):
    out = []
    new_hi = (NEW_BASE + 0x8000) >> 16
    for site in find_sites(exe_path):
        if site["conflicts"]:
            raise RuntimeError("lui at %08X shares its register: %r" % (site["lui"][0], site["conflicts"]))
        pc, word = site["lui"]
        out.append((pc, word, (word & 0xFFFF0000) | new_hi, "lui -> 0x%04X" % new_hi))
        for upc, uword, ea in site["uses"]:
            new_ea = NEW_BASE + (ea - OLD_BASE)
            lo = (new_ea - (new_hi << 16)) & 0xFFFF
            out.append((upc, uword, (uword & 0xFFFF0000) | lo, "imm 0x%04X -> 0x%04X (entry %d)"
                        % (uword & 0xFFFF, lo, (ea - OLD_BASE) // 4)))
    return out


# --- cell objects buffer -> mod memory ---------------------------------------
# InitCellData (0x80039748) carves cell pointers, cell objects and cell data from
# the heap. Chicago's cell objects (~290 KB) do not fit in the 2 MB RAM, so the
# objects buffer is placed in mod memory (CD DMA can target it: local runtime
# change in dma.c) and its size is no longer taken from the heap.
CELL_OBJECTS_ADDR = 0x9F002000                 # after the 8 KB model table
CELL_OBJECTS_BYTES = 512 * 1024

CELL_PATCH = [
    # (address, original word, new word, note)
    (0x800397CC, 0x3C010009, 0x3C039F00, "lui at,9 -> lui v1,0x9F00"),
    (0x800397D0, 0xAC257108, 0x34632000, "sw a1,0x7108(at) -> ori v1,v1,0x2000"),
    (0x800397D4, 0x00A32821, 0x3C010009, "addu a1,a1,v1 -> lui at,9 (objects no longer on the heap)"),
    (0x800397D8, 0x3C010009, 0xAC237108, "lui at,9 -> sw v1,0x7108(at) (cell_objects = 0x9F002000)"),
]


def cell_patches(exe_path):
    img, base = load_exe(exe_path)
    out = []
    for pc, old, new, note in CELL_PATCH:
        cur = struct.unpack_from("<I", img, pc - base)[0]
        if cur != old:
            raise RuntimeError("unexpected word at %08X: %08X" % (pc, cur))
        out.append((pc, old, new, note))
    return out


# --- primitive buffer guard ----------------------------------------------------
# Each frame's GPU primitives go to a fixed 0x1E000-byte buffer; when a frame
# overflows it, 0x800513D4 prints a message and parks in a `break` loop (that
# block is now skipped, see SPOOL_RESET), so an overflow silently overwrites
# what follows: buffer A runs into buffer B, buffer B into the road map tables
# at 0x80117220 (cars fell through the street; quay, 2026-10-10). Per frame the
# ground tiles are drawn first (TILE_LIMIT, tile guard), then every collected
# map object in one batch (0x80030ED0, called from 0x8002D664; Chicago peaked at
# 0x235A4 bytes). The batch loop now stops once the frame has used OBJ_LIMIT,
# leaving room for cars, skid marks (0x8002A084), effects and the HUD. The
# check lives in the overflow handler's dead printf/break block.
OBJ_LIMIT = 0x16800           # measured: cars, skid marks, effects and HUD after the objects need ~0x5A00
CAVE = 0x80051460
BATCH_NEXT, BATCH_LOOP, BATCH_EXIT = 0x80030F20, 0x80030F0C, 0x80030F2C
AT, V0, V1, T8, SP = 1, 2, 3, 24, 29


def _j(target):
    return (2 << 26) | ((target >> 2) & 0x3FFFFFF)


def _lw(rt, off, rs):
    return (0x23 << 26) | (rs << 21) | (rt << 16) | (off & 0xFFFF)


def _bne(rs, rt, pc, target):
    return (5 << 26) | (rs << 21) | (rt << 16) | (((target - pc - 4) >> 2) & 0xFFFF)


OBJ_GUARD_CODE = [
    "lw t0, 0xdc0(gp)",            # current draw buffer (0x80097530)
    "lui at, %#x" % (OBJ_LIMIT >> 16),
    "lw t0, 8(t0)",                # buffer start
    "ori at, at, %#x" % (OBJ_LIMIT & 0xFFFF),
    "subu t0, a1, t0",             # a1 = primitive pointer after this object
    "sltu t0, t0, at",
    "beq t0, zero, OUT",
    "addiu s0, s0, 4",             # (moved from the loop) next list entry
    "blez s1, OUT",
    "nop",
    "j %#x" % BATCH_LOOP,          # next object
    "nop",
    "OUT:",
    "j %#x" % BATCH_EXIT,          # list done or frame full
    "nop",
]


def prim_guard_patches(exe_path):
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    if [word(BATCH_NEXT + 4 * k) for k in range(3)] != [0x00402821, 0x1E20FFF9, 0x22100004]:
        raise RuntimeError("unexpected object batch loop at %08X" % BATCH_NEXT)
    code = asm(CAVE, OBJ_GUARD_CODE, 0x8005149C)
    out = [(BATCH_NEXT, word(BATCH_NEXT), _j(CAVE), "move a1,v0 -> j object guard"),
           (BATCH_NEXT + 4, word(BATCH_NEXT + 4), 0x00402821, "bgtz s1 -> move a1,v0 (delay slot of the jump)")]
    for k, new in enumerate(code):
        if word(CAVE + 4 * k) != new:
            out.append((CAVE + 4 * k, word(CAVE + 4 * k), new, "object guard %d" % k))
    return out


# --- tiny assembler for rewritten routines -------------------------------------------
REG = {n: k for k, n in enumerate("zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 "
                                    "s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra".split())}
_IOP = {"addiu": 9, "slti": 10, "sltiu": 11, "andi": 12, "ori": 13, "lw": 0x23, "lbu": 0x24, "lhu": 0x25, "sw": 0x2B,
        "lh": 0x21, "sh": 0x29}
_RFN = {"addu": 0x21, "subu": 0x23, "slt": 0x2A, "sltu": 0x2B, "xor": 0x26, "and": 0x24, "or": 0x25}


def asm(base, lines, end=None):
    """MIPS words for `lines` ("op args", "NAME:" labels; branch targets are
    labels or hex addresses), padded with nops up to `end`."""
    labels, prog, pc = {}, [], base
    for ln in lines:
        if ln.endswith(":"):
            labels[ln[:-1]] = pc
        else:
            prog.append((pc, ln)); pc += 4
    out = []
    for pc, ln in prog:
        op, _, rest = ln.partition(" ")
        a = [x.strip() for x in rest.split(",")] if rest else []
        r = REG.__getitem__
        if op == "nop":
            w = 0
        elif op == "move":
            w = (r(a[1]) << 21) | (r(a[0]) << 11) | 0x21
        elif op in _RFN:
            w = (r(a[1]) << 21) | (r(a[2]) << 16) | (r(a[0]) << 11) | _RFN[op]
        elif op in ("sll", "srl", "sra"):
            w = (r(a[1]) << 16) | (r(a[0]) << 11) | (int(a[2], 0) << 6) | {"sll": 0, "srl": 2, "sra": 3}[op]
        elif op == "mult":
            w = (r(a[0]) << 21) | (r(a[1]) << 16) | 0x18
        elif op == "mflo":
            w = (r(a[0]) << 11) | 0x12
        elif op in ("bgez", "bltz", "bgtz"):
            t = labels[a[-1]] if a[-1] in labels else int(a[-1], 16)
            off = (t - pc - 4) >> 2
            assert -0x8000 <= off < 0x8000
            w = ((1 << 26) | (r(a[0]) << 21) | ((1 if op == "bgez" else 0) << 16) | (off & 0xFFFF)) if op != "bgtz" \
                else ((7 << 26) | (r(a[0]) << 21) | (off & 0xFFFF))
        elif op == "jal":
            t = labels[a[0]] if a[0] in labels else int(a[0], 16)
            w = (3 << 26) | ((t >> 2) & 0x3FFFFFF)
        elif op == "jr":
            w = (r(a[0]) << 21) | 8
        elif op == "lui":
            w = (15 << 26) | (r(a[0]) << 16) | (int(a[1], 0) & 0xFFFF)
        elif op in ("lw", "lbu", "lhu", "sw", "lh", "sh"):
            off, _, rb = a[1].partition("(")
            w = (_IOP[op] << 26) | (r(rb[:-1]) << 21) | (r(a[0]) << 16) | (int(off, 0) & 0xFFFF)
        elif op in _IOP:
            w = (_IOP[op] << 26) | (r(a[1]) << 21) | (r(a[0]) << 16) | (int(a[2], 0) & 0xFFFF)
        elif op in ("beq", "bne", "blez"):
            t = labels[a[-1]] if a[-1] in labels else int(a[-1], 16)
            off = (t - pc - 4) >> 2
            assert -0x8000 <= off < 0x8000
            rt = r(a[1]) if op != "blez" else 0
            w = ({"beq": 4, "bne": 5, "blez": 6}[op] << 26) | (r(a[0]) << 21) | (rt << 16) | (off & 0xFFFF)
        elif op == "j":
            t = labels[a[0]] if a[0] in labels else int(a[0], 16)
            w = (2 << 26) | ((t >> 2) & 0x3FFFFFF)
        else:
            raise ValueError(ln)
        out.append(w)
    if end is not None:
        assert base + 4 * len(out) <= end, "routine too long"
        out += [0] * ((end - base) // 4 - len(out))
    return out


def rewrite(exe_path, base, words, note):
    """Patches for the words of a rewritten range that differ from the original."""
    img, b0 = load_exe(exe_path)
    out = []
    for k, w in enumerate(words):
        old = struct.unpack_from("<I", img, base + 4 * k - b0)[0]
        if old != w:
            out.append((base + 4 * k, old, w, "%s %d" % (note, k)))
    return out


# --- area switching ------------------------------------------------------------
# Driver 1 switches the loaded area (0x80033F9C) only in regions with switch
# entries (area, direction): an entry fires when the camera's cell inside the
# region passes 30 - t towards its direction or drops below t on the way back;
# t = 13 if *0x80096884 else 15. With 15 the band without switching is one cell,
# so driving along a region's middle switched areas back and forth (constant CD
# loads; soaks: 42 of 77 switches went straight back). The entry loop and the
# no-switch path (0x8003401C-0x80034134) are rewritten: t is always 13 (a 5-cell
# band, hysteresis), and in Chicago (city 3) a region whose two entries do not
# name the loaded area (or with none loaded yet: a start inside the band kept
# area -1, untextured/missing buildings) loads its own area (second entry), so a stale area cannot
# be carried through the band into regions it does not cover (convert.py
# simulates this rule to build the area sets). Other cities behave as before.
AREA_LOAD, AREA_RET = 0x8003413C, 0x800341F4
AREA_SWITCH_CODE = [
    "lw t4, 0xbcc(gp)",            # region size (0x8009733C)
    "lw t5, 0xb50(gp)",            # loaded area (0x800972C0)
    "addiu t4, t4, -13",           # cell > size - 13 fires towards +z / +x
    "beq t2, zero, NOMATCH",
    "move a2, zero",
    "LOOP:",
    "addu v0, t0, a2",
    "lbu v1, 2(v0)",
    "nop",
    "andi v0, v1, 0x3f",           # entry area
    "beq v0, t5, NEXT",
    "srl v1, v1, 6",               # entry direction: 0 +z, 1 +x, 2 -z, 3 -x
    "sw v1, 0xac0(gp)",
    "andi at, v1, 1",
    "beq at, zero, AXIS",
    "move t3, a1",                 # z cell
    "move t3, a0",                 # x cell
    "AXIS:",
    "sltiu at, v1, 2",
    "beq at, zero, CHECK",
    "slti t1, t3, 13",             # back: cell < 13
    "slt t1, t4, t3",              # towards: cell > size - 13
    "CHECK:",
    "bne t1, zero, %#x" % AREA_LOAD,
    "nop",
    "NEXT:",
    "addiu a2, a2, 1",
    "slt at, a2, t2",
    "bne at, zero, LOOP",
    "nop",
    "NOMATCH:",
    "lw at, 0xc4(gp)",             # city (0x80096834)
    "addiu v0, zero, 3",
    "beq at, v0, OWN",             # Chicago: also when nothing is loaded yet (-1)
    "addiu at, zero, -1",
    "bne t5, at, %#x" % AREA_RET,  # other cities as before: only when nothing is loaded,
    "nop",
    "lw v0, 0xbd4(gp)",            # the default area (0x80097344)
    "nop",
    "bne v0, at, %#x" % AREA_LOAD,
    "nop",
    "beq zero, zero, %#x" % AREA_RET,
    "nop",
    "OWN:",
    "addiu v0, zero, 2",
    "bne t2, v0, %#x" % AREA_RET,
    "lbu v0, 2(t0)",
    "nop",
    "andi v0, v0, 0x3f",
    "beq v0, t5, %#x" % AREA_RET,
    "lbu v0, 3(t0)",
    "nop",
    "andi v0, v0, 0x3f",
    "bne v0, t5, %#x" % AREA_LOAD,  # loaded area is not one of this region's: load its own
    "nop",
    "beq zero, zero, %#x" % AREA_RET,
    "nop",
]


def area_switch_patches(exe_path):
    return rewrite(exe_path, 0x8003401C, asm(0x8003401C, AREA_SWITCH_CODE, 0x80034138), "area switch")


# --- road map decoder ----------------------------------------------------------------
# A region's road map arrives run-length coded (u32 count, u32 value) and is
# unpacked into 3600 cells (0x800354D8, CD callback) until the count reaches
# exactly 0. A buffer that is stale or not loaded yet (restart race) never sums
# to 3600 or holds zero counts: the callback loops forever and the game hangs
# (0x80035538, after Play Again). Rewritten: a run that is empty or longer than
# the cells left fills the rest, so it always ends after 3600 cells.
ROAD_DECODER_CODE = [
    "lw a0, 0xb4c(gp)",            # spool entry index (0x800972BC)
    "lui v1, 0xa",
    "sll v0, a0, 2",
    "addu v0, v0, a0",
    "sll v0, v0, 2",
    "addu v0, v0, v1",             # 0xA0000 + 20 * index (entries at +0x7EA4)
    "lhu v1, 0x7ea6(v0)",
    "lw v0, 0x7eb4(v0)",           # source data
    "sll v1, v1, 2",
    "addu v1, v1, gp",
    "lw v1, 0x7184(v1)",           # destination (table at 0x8009D8F4)
    "sw zero, 0xb38(gp)",
    "sw v0, 0xb5c(gp)",
    "sw v1, 0xb58(gp)",
    "addiu a2, zero, 3600",
    "RUN:",
    "lw a0, 0(v0)",
    "lw a1, 4(v0)",
    "addiu t0, a0, -1",
    "sltu t0, t0, a2",             # 1 <= count <= cells left
    "bne t0, zero, FILLS",
    "addiu v0, v0, 8",
    "move a0, a2",
    "FILLS:",
    "subu a2, a2, a0",
    "FILL:",
    "sw a1, 0(v1)",
    "addiu a0, a0, -1",
    "bne a0, zero, FILL",
    "addiu v1, v1, 4",
    "bne a2, zero, RUN",
    "nop",
    "jr ra",
    "nop",
]


def road_decoder_patches(exe_path):
    return rewrite(exe_path, 0x800354D8, asm(0x800354D8, ROAD_DECODER_CODE, 0x80035558), "road decoder")


# The model renderer (0x800307FC) traps bad polygon group data in an endless
# `j self` loop at 0x80030B00 (the game freezes, interrupts and music go on).
# It now leaves the model instead (0x80030BCC: OT write-back + return).
RENDER_TRAP = [
    (0x80030B00, 0x0800C2C0, 0x0800C2F3, "j self -> j 0x80030BCC: skip a model with bad group data"),
    (0x80030B04, 0x0001000D, 0x00000000, "break 1 (delay slot) -> nop"),
]


# Spool reader (CD sector callback 0x80034C74): after each queue entry it chains
# into the next one while its "sectors left" total (0x800971F8) is non-zero. A
# load cut off by a restart (wreck -> Play Again) leaves that total too high, so
# the next session's reader runs past the last entry into an empty one
# (destination 0, count 0) and streams sectors over the kernel at address 0
# (BIOS tables gone -> fatal dispatch). An empty entry now ends the read like a
# finished queue (0x80034D10), and every queue-drained reset also clears the
# total.
SPOOL_CHAIN = [
    (0x80034CF8, 0x8C620008, 0x94620002, "lw v0,8(v1) -> lhu v0,2(v1) (sector count)"),
    (0x80034CFC, 0x94630002, 0x8C630008, "lhu v1,2(v1) -> lw v1,8(v1) (destination)"),
    (0x80034D00, 0xAF820A80, 0x10400003, "sw v0,dest -> beqz v0,0x80034D10 (empty entry: stop)"),
    (0x80034D04, 0xAF830A8C, 0xAF820A8C, "sw v1,count -> sw v0,count"),
    (0x80034D0C, 0x00000000, 0xAF830A80, "nop (delay slot of j) -> sw v1,dest"),
]
SPOOL_DRAIN_SITES = (0x80034ACC, 0x80034E98, 0x80034FF8, 0x80035288)
SPOOL_DRAIN_OLD = [0xAF800B40, 0x8F820B40, 0x00000000, 0xAF820280, 0x8F820280,
                   0x00000000, 0xAF82027C, 0x8F82027C, 0x00000000, 0xAF820B64]
SPOOL_DRAIN_NEW = [0xAF800B40, 0xAF800280, 0xAF80027C, 0xAF800B64, 0xAF800A88,
                   0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x00000000]


# Spool reset (0x800337D4, run on level start and restart) clears the queue but
# not the reader: a CD read still in flight keeps its sector callback, index
# (0x800969EC / 0x800969F0) and count, and since the reset also clears the
# "reading" flag the main loop starts a second read from the stale index with a
# whole-region count. The read then chains into entries that are not contiguous
# on disc (restart: wrong texture pages, map data) or past the queue (crash).
# The reset now also zeroes both indices and the area loading flag and detaches
# the sector callback (CdReadyCallback(0), 0x8007A12C). The code goes into the overflow check before
# 0x8005149C, dead since the primitive guard (a branch skips it).
SPOOL_RESET = [
    (0x80051438, 0x3C060001, 0x00000000, "lui a2,1 -> nop (dead overflow check)"),
    (0x8005143C, 0x8F820DC0, 0xAF800540, "lw v0,0xdc0(gp) -> sw zero,0x540(gp) (moved up, still on both paths)"),
    (0x80051440, 0x34C6E000, 0x10000016, "ori a2,a2,0xe000 -> b 0x8005149C (rest of the dead overflow check)"),
    (0x80051444, 0xAF800540, 0x00000000, "sw zero,0x540(gp) -> nop (delay slot)"),
    (0x80051448, 0x8C430008, 0xAF80027C, "spool reset: sw zero,reader index"),
    (0x8005144C, 0x8C450000, 0xAF800280, "spool reset: sw zero,read index"),
    (0x80051450, 0x00661021, 0xAF800278, "spool reset: sw zero,area loading flag (an abandoned load must not block switches)"),
    (0x80051454, 0x0045102B, 0x0801E84B, "spool reset: j CdReadyCallback (tail call)"),
    (0x80051458, 0x10400010, 0x00002021, "spool reset: move a0,zero (callback = none)"),
    (0x8005145C, 0x00A62823, 0x00000000, "nop"),
    (0x8003381C, 0x8F820AC4, 0x0C014512, "lw v0,0xac4(gp) -> jal spool reset (0x80051448)"),
    (0x80033850, 0xAF820B40, 0xAF800B40, "sw v0,write index -> sw zero,write index"),
]


def spool_patches():
    out = list(SPOOL_CHAIN) + SPOOL_RESET
    for site in SPOOL_DRAIN_SITES:
        for k, (old, new) in enumerate(zip(SPOOL_DRAIN_OLD, SPOOL_DRAIN_NEW)):
            if old != new:
                out.append((site + 4 * k, old, new, "queue drained: zero indices and sectors-left total"))
    return out


# Driver 1 starts an area switch (0x80033F9C, called from 0x80039FE8) even while
# the previous area is still loading. The model fix-up 0x80033E54 then installs
# the first area's models under the second area's id list (*0x800972D0): whole
# streets drawn with one wrong model, floating fragments. Driver 1's own 5-cell
# switch band made this rare; Chicago's 1-cell band (AREA_THRESHOLD) does not.
# The call is now skipped while the loading flag 0x800969E8 is set; the check
# runs every frame, so the switch happens as soon as the load is installed.
AREA_SWITCH_WAIT = [
    (0x80039FCC, 0x00000000, 0x8F840278, "nop -> lw a0,0x278(gp) (area loading flag)"),
    (0x80039FE0, 0x8F840BB0, 0x14800003, "lw a0,0xbb0(gp) -> bnez a0,0x80039FF0 (loading: no new switch)"),
    (0x80039FEC, 0x00000000, 0x8F840BB0, "nop (delay slot of jal) -> lw a0,0xbb0(gp)"),
]


# Ground tiles are drawn after the map-object loop (tile list, 0x800270D4) and
# were not limited: a dense view overflowed the 0x1E000 primitive buffer into the
# other frame's buffer while the GPU read it (fatal "GP0 unknown command").
# The tile loop now stops once a frame has used TILE_LIMIT bytes, leaving
# 0x1E000 - TILE_LIMIT for cars, effects and the HUD. The check lives in the
# "LevEdit cellsize" error block (0x8002E1A0), unreachable for Chicago's 3000
# cell size once its branch is made unconditional.
TILE_LIMIT = 0x12000         # ground tiles (drawn first); then map objects up to OBJ_LIMIT
CAVE2 = 0x8002E1A0
TILE_LOOP, TILE_LOOP_ALT, TILE_LOOP_NEXT, TILE_LOOP_EXIT = 0x80027264, 0x8002727C, 0x8002726C, 0x800275F0
S1, S7, ZERO = 17, 23, 0


def _beqz(rs, pc, target):
    return (4 << 26) | (rs << 21) | (((target - pc - 4) >> 2) & 0xFFFF)


def tile_guard_code():
    c = CAVE2
    return [
        (0xF << 26) | (V1 << 16) | 0x8009,               # lui  v1, 0x8009
        _lw(V1, 0x7530, V1),                             # lw   v1, 0x7530(v1)   current draw buffer
        (0xF << 26) | (AT << 16) | (TILE_LIMIT >> 16),   # lui  at, hi(limit)
        _lw(V0, 0, V1),                                  # lw   v0, 0(v1)        primitive pointer
        _lw(V1, 8, V1),                                  # lw   v1, 8(v1)        buffer start
        (0xD << 26) | (AT << 21) | (AT << 16) | (TILE_LIMIT & 0xFFFF),  # ori at, at, lo(limit)
        (V0 << 21) | (V1 << 16) | (V0 << 11) | 0x23,     # subu v0, v0, v1
        (V0 << 21) | (AT << 16) | (V0 << 11) | 0x2B,     # sltu v0, v0, at
        _beqz(V0, c + 32, TILE_LOOP_EXIT),               # beqz v0, leave the tile loop
        (0xA << 26) | (S1 << 21) | (V0 << 16) | 0x80,    # slti v0, s1, 0x80     (replaced test)
        _beqz(V0, c + 40, TILE_LOOP_ALT),                # beqz v0, 0x8002727C   (replaced branch)
        (S1 << 16) | (V0 << 11) | (2 << 6),              # sll  v0, s1, 2        (its delay slot)
        _j(TILE_LOOP_NEXT),                              # j    back into the loop
        0,
    ]


# The map-object loop appends ground tiles to a list without a bound: 128 on the
# stack, then a 0x800-byte heap buffer (*0x8009715C, 512 entries); beyond 640
# tiles it overwrites the next per-frame list (*0x8009719C) and the heap. Tiles
# past 640 are now skipped. The append goes through the cave's last 5 words.
TILE_CAP = 640
TILE_APPEND = 0x8002D0E0
TILE_APPEND_DONE, CELL_OBJ_NEXT = 0x8002D0F4, 0x8002D250
CAVE2_APPEND = CAVE2 + 4 * 14
S0 = 16


def _bnez(rs, pc, target):
    return (5 << 26) | (rs << 21) | (((target - pc - 4) >> 2) & 0xFFFF)


def tile_cap_code():
    return [
        _lw(V1, 0x715C, V1),                             # lw   v1, 0x715c(v1)  tile buffer
        0,
        (V0 << 21) | (V1 << 16) | (V0 << 11) | 0x21,     # addu v0, v0, v1
        _j(TILE_APPEND_DONE),                            # j    0x8002D0F4      (j next object; s6++)
        (0x2B << 26) | (V0 << 21) | (S0 << 16) | (0xFE00),  # sw s0, -0x200(v0)
    ]


def tile_guard_patches(exe_path):
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    if word(0x8002E198) != 0x10620014:
        raise RuntimeError("unexpected cellsize check at 8002E198: %08X" % word(0x8002E198))
    out = [(0x8002E198, 0x10620014, 0x10000014, "beq v1,v0 -> b 0x8002E1EC: cellsize error block unused (3000)")]
    if word(TILE_LOOP) != _beqz(V0, TILE_LOOP, TILE_LOOP_ALT):
        raise RuntimeError("unexpected tile loop at %08X: %08X" % (TILE_LOOP, word(TILE_LOOP)))
    out.append((TILE_LOOP, word(TILE_LOOP), _j(CAVE2), "beqz v0,0x8002727C -> j tile guard"))
    for k, new in enumerate(tile_guard_code()):
        out.append((CAVE2 + 4 * k, word(CAVE2 + 4 * k), new, "tile guard %d" % k))
    # tile list bound
    S6 = 22
    old = [word(TILE_APPEND + 4 * k) for k in range(5)]
    if old != [0x3C030009, 0x8C63715C, 0x00000000, 0x00431021, 0xAC50FE00]:
        raise RuntimeError("unexpected tile append at %08X: %s" % (TILE_APPEND, [hex(w) for w in old]))
    new = [
        (0xA << 26) | (S6 << 21) | (V1 << 16) | TILE_CAP,    # slti v1, s6, 640
        _bnez(V1, TILE_APPEND + 4, CAVE2_APPEND),            # bnez v1, append in the cave
        (0xF << 26) | (V1 << 16) | 0x0009,                   # lui  v1, 9          (delay slot)
        _j(CELL_OBJ_NEXT),                                   # j    next object (list full)
        0,
    ]
    for k in range(5):
        out.append((TILE_APPEND + 4 * k, old[k], new[k], "tile list bound %d" % k))
    for k, w in enumerate(tile_cap_code()):
        out.append((CAVE2_APPEND + 4 * k, word(CAVE2_APPEND + 4 * k), w, "tile list append %d" % k))
    return out


def area_patches(exe_path):
    img, base = load_exe(exe_path)
    out = []
    for pc, old, new, note in RENDER_TRAP + AREA_SWITCH_WAIT + spool_patches():
        cur = struct.unpack_from("<I", img, pc - base)[0]
        if cur != old:
            raise RuntimeError("unexpected word at %08X: %08X (expected %08X)" % (pc, cur, old))
        out.append((pc, old, new, note))
    return out


# Height-aware road surface selection (C16/C17) is NOT an exe patch any more: the exe has
# no spare words (the "unreferenced" function 0x8006C078 is reached via 0x8006C964 -> C22
# crash) and the recomp fail-fasts on code outside its image. driver_chicago.c reorders the
# marked ROADSURF planes around the player every vblank instead (see NOTES.md).


def all_patches(exe_path):
    return (patches(exe_path) + cell_patches(exe_path) + prim_guard_patches(exe_path) + area_patches(exe_path)
            + tile_guard_patches(exe_path) + area_switch_patches(exe_path) + road_decoder_patches(exe_path))


def apply(exe_in, exe_out):
    """Write the patched executable that `generate` compiles natively."""
    data = bytearray(open(exe_in, "rb").read())
    img, base = load_exe(exe_in)
    for pc, old, new, _note in all_patches(exe_in):
        off = 0x800 + pc - base
        assert struct.unpack_from("<I", data, off)[0] == old
        struct.pack_into("<I", data, off, new)
    open(exe_out, "wb").write(bytes(data))


def toml(exe_path, feature):
    lines = []
    for pc, old, new, note in all_patches(exe_path):
        b = lambda v: " ".join("%02x" % c for c in struct.pack("<I", v))
        lines += ["[[patch]]", 'feature = "%s"' % feature, 'target = "main_exe"',
                  "address = 0x%08X" % pc, 'expected = "%s"' % b(old), 'replace = "%s"   # %s' % (b(new), note), ""]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    exe = sys.argv[1]
    sites = find_sites(exe)
    print("# %d lui sites, %d uses, %d with conflicts" % (
        len(sites), sum(len(s["uses"]) for s in sites), sum(1 for s in sites if s["conflicts"])))
    for s in sites:
        if s["conflicts"]:
            print("# CONFLICT", hex(s["lui"][0]), s["conflicts"])
    if len(sys.argv) > 3 and sys.argv[2] == "--apply":
        apply(exe, sys.argv[3])
        print("# wrote patched executable", sys.argv[3])
    elif len(sys.argv) > 2:
        open(sys.argv[2], "w", newline="\n").write(toml(exe, "model-table") + "\n")
        print("# wrote", sys.argv[2])
