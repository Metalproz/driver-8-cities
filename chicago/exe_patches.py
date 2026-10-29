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
NEW_BASE = 0x80115600                          # S4a (20.10.): main RAM, 8 KB above Driver 1's heap start (the heap now
                                               # starts at 0x80117600, s4_patches); was 0x9F000000 (mod memory)
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
    # (address, original word, new word, note) -- S4a (20.10.): the cave S4C decides per level: with the S4 flag
    # (gp+0x1120 = 0x80097890, plugin CHI_S4=1) and objects + cell data ending below 0x801F5000 (the replay tape starts at 0x801FABBC; ~12-24 KB of later level allocations) the objects stay on the heap as in
    # Driver 1 (every D1 city), otherwise they go to the mod buffer 0x9F002000 (Chicago until its data diet)
    (0x800397CC, 0x3C010009, 0x03E0C021, "lui at,9 -> move t8, ra (InitCellData is a leaf)"),
    (0x800397D0, 0xAC257108, None, "sw a1,0x7108(at) -> jal S4C (cell objects: heap or mod buffer)"),
    (0x800397D4, 0x00A32821, 0x00000000, "addu a1,a1,v1 -> nop (S4C moves a1 past the objects on the heap path)"),
    (0x800397D8, 0x3C010009, 0x0300F821, "lui at,9 -> move ra, t8 (S4C returns at = 0x90000)"),
]


def cell_patches(exe_path):
    img, base = load_exe(exe_path)
    out = []
    for pc, old, new, note in CELL_PATCH:
        cur = struct.unpack_from("<I", img, pc - base)[0]
        if cur != old:
            raise RuntimeError("unexpected word at %08X: %08X" % (pc, cur))
        if new is None:
            new = asm(pc, ["jal 0x%08x" % _s1_labels()["S4C"]])[0]
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
    "lw at, -0x3358(gp)",          # C94: OBJ limit word XOBJ 0x80093418 (default OBJ_LIMIT, image data)
    "lw t0, 8(t0)",                # buffer start
    "nop",
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
_IOP = {"addiu": 9, "slti": 10, "sltiu": 11, "andi": 12, "ori": 13, "xori": 14, "lw": 0x23, "lbu": 0x24, "lhu": 0x25, "sw": 0x2B,
        "lh": 0x21, "sh": 0x29, "sb": 0x28, "lb": 0x20}
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
        elif op == ".word":                          # raw word (GTE ops: lwc2 / mfc2 / cop2 commands)
            w = int(a[0], 0)
        elif op == "move":
            w = (r(a[1]) << 21) | (r(a[0]) << 11) | 0x21
        elif op in _RFN:
            w = (r(a[1]) << 21) | (r(a[2]) << 16) | (r(a[0]) << 11) | _RFN[op]
        elif op == "sllv":                           # sllv rd, rt, rs
            w = (r(a[2]) << 21) | (r(a[1]) << 16) | (r(a[0]) << 11) | 4
        elif op in ("sll", "srl", "sra"):
            w = (r(a[1]) << 16) | (r(a[0]) << 11) | (int(a[2], 0) << 6) | {"sll": 0, "srl": 2, "sra": 3}[op]
        elif op == "mult":
            w = (r(a[0]) << 21) | (r(a[1]) << 16) | 0x18
        elif op == "div":                            # div rs, rt (LO = quotient)
            w = (r(a[0]) << 21) | (r(a[1]) << 16) | 0x1A
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
        elif op in ("lw", "lbu", "lhu", "sw", "lh", "sh", "sb", "lb"):
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
    "lui at, 0x8009",              # Chicago active (plugin flag at CHICAGO_FLAG_ADDR 0x8009788C: Chicago may
    "lw at, 0x788c(at)",           # share LA's city index 3 with the original LA since its own Take a Ride slot)
    "nop",
    "bne at, zero, OWN",           # Chicago: also when nothing is loaded yet (-1)
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
    return rewrite(exe_path, 0x800354D8, asm(0x800354D8, ROAD_DECODER_CODE, 0x80035558), "road decoder") \
        + road16_decoder_patches(exe_path)


# C48 (14.10., investigator): the 16-bit road-id map decoder (0x8003542C, CD callback, 3600 s16 cells into
# *(0x8009E724 + slot*4)) read run lengths as signed and never clamped them: a negative count grew the
# remaining total, a long one wrote past the table (seen: 0x801DA000..0x801FBFFE, the draw-buffer struct
# 0x800BE024 filled with 0x2F512F51 -> misaligned dispatch / B0 / PC 0 at load, more often with more roads).
# Rewritten like the 32-bit decoder: a run must be 1..cells left, else it fills the rest and decoding ends.
ROAD16_DECODER_CODE = [                # MIPS I: one instruction between a load and the use of its result
    "lui v1, 0xa",
    "lw a0, 0xb4c(gp)",            # spool entry index (0x800972BC)
    "addiu v1, v1, 0x7ea4",
    "sw zero, 0xb34(gp)",
    "sll v0, a0, 2",
    "addu v0, v0, a0",
    "sll v0, v0, 2",
    "addu v0, v0, v1",             # entry (20 B) at 0x800A7EA4
    "lhu v1, 2(v0)",
    "lw a1, 0xc(v0)",              # source data
    "sll v1, v1, 2",
    "addu v1, v1, gp",
    "lw a0, 0x7fb4(v1)",           # destination: table 0x8009E724 (= gp + 0x7FB4)
    "sw a1, 0xaec(gp)",            # 0x8009725C
    "addiu a2, zero, 3600",
    "sw a0, 0xae8(gp)",
    "lw v1, 0(a1)",
    "addiu v0, zero, -1",
    "bne v1, v0, RUN",
    "nop",
    "move v1, v0",                 # whole region without roads: one run of 3600 x -1
    "beq zero, zero, OK",
    "move v0, a2",
    "RUN:",
    "lh v0, 0(a1)",                # count
    "lh v1, 2(a1)",                # value
    "addiu t0, v0, -1",
    "sltu t0, t0, a2",             # 1 <= count <= cells left
    "bne t0, zero, OK",
    "addiu a1, a1, 4",
    "move v0, a2",                 # bad run: fill the rest with its value, then end
    "OK:",
    "subu a2, a2, v0",
    "FILL:",
    "sh v1, 0(a0)",
    "addiu v0, v0, -1",
    "bne v0, zero, FILL",
    "addiu a0, a0, 2",
    "bne a2, zero, RUN",
    "nop",
    "jr ra",
    "nop",
]


def road16_decoder_patches(exe_path):
    if os.environ.get("CHI_ROAD16_FIX") == "0":      # default since the C48 change (14.10.)
        return []
    return rewrite(exe_path, 0x8003542C, asm(0x8003542C, ROAD16_DECODER_CODE, 0x800354D8), "road16 decoder")


# C48 (14.10.): Driver 1 accepts at most 422 roads (ROADS / ROADBOUNDS loaders: slti 0x1A7, else a
# "MAX_ROADS ... guess what you gotta do" break loop) and builds a 20-byte row per road from 0x8009E744.
# The rows may now grow up to 0x800A0D00 (483 rows; 0x800A0D00.. is C50's script area): the 16-byte
# variable that followed the 422 rows (0x800A083C, two sites) moves to 0x800A0CF0 (unused), and the limit
# becomes 483. Original cities have at most 410 roads, so nothing changes for them. All guest code.
MAX_ROADS = 483
ROAD_LIMIT = [
    (0x8003950C, 0x28C201A7, 0x28C20000 | (MAX_ROADS + 1), "C48: ROADS loader limit 422 -> %d" % MAX_ROADS),
    (0x80039604, 0x28C201A7, 0x28C20000 | (MAX_ROADS + 1), "C48: ROADBOUNDS loader limit 422 -> %d" % MAX_ROADS),
    (0x80024C88, 0x8C64083C, 0x8C640CF0, "C48: variable after the road rows 0x800A083C -> 0x800A0CF0"),
    (0x80024C98, 0x2465083C, 0x24650CF0, "C48: its address (a1)"),
]


def road_limit_patches(exe_path):
    img, base = load_exe(exe_path)
    for pc, old, _new, _n in ROAD_LIMIT:
        if struct.unpack_from("<I", img, pc - base)[0] != old:
            raise RuntimeError("unexpected word at %08X" % pc)
    return list(ROAD_LIMIT)


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
# The sector callbacks end a read when the "sectors left" total reaches exactly 0;
# a total gone negative (seen after a teleport during a load, -170) kept them
# chaining into stale queue slots (PC=0 / dispatch 0xB0 crashes) and kept the
# plugin's surface selection idle. They now treat a total <= 0 as done (same
# offsets, only the branch opcode: beqz -> blez, bnez -> bgtz).
SPOOL_END = [
    (0x80034CE0, 0x1060000B, 0x1860000B, "beqz v1 -> blez v1 (main reader: total <= 0 = done)"),
    (0x80034BA8, 0x10A0000A, 0x18A0000A, "beqz a1 -> blez a1 (region reader: total <= 0 = done)"),
    (0x800350CC, 0x14A00009, 0x1CA00009, "bnez a1 -> bgtz a1 (sector reader: go on only while total > 0)"),
    (0x8003531C, 0x14600018, 0x1C600018, "bnez v1 -> bgtz v1 (sector reader: go on only while total > 0)"),
]
# Sea level (C35): for a water cell whose model is "sea" (flags 0x80) the ground query
# 0x8001EEB4 ignores the cell height: ground = wave table value around y 0 (LA's
# harbour at street level) minus a sink term. Chicago's water is drawn 1084 below the
# street, so cars floated ~1000 above it. The same 10 words now also add a sea level
# offset read from mod memory (SEA_LEVEL_ADDR, written by driver_chicago.c: -1084 in
# Chicago, 0 elsewhere = unchanged): the redundant `lui v0,9` and the table base
# `addiu` move into the load (lw/lhu offsets), the load-delay nop loads its address.
SEA_LEVEL_ADDR = 0x80097888       # S4a: main RAM word gp+0x1118 (no exe xrefs; was 0x9F082100 in mod memory)
CHICAGO_FLAG_ADDR = 0x8009788C    # gp+0x111C: 1 while Chicago is the loaded city (plugin; was 0x9F082104)
SEA_LEVEL_OLD = [(0x8001F0C8, "nop"), (0x8001F0D8, "lui v0, 9"), (0x8001F0DC, "lw v0, 0x70fc(v0)"),
                 (0x8001F0E0, "addiu v1, v1, -0x1558"), (0x8001F0E4, "andi v0, v0, 0xfff"),
                 (0x8001F0E8, "sll v0, v0, 2"), (0x8001F0EC, "addu v0, v0, v1"), (0x8001F0F0, "lhu v0, 0(v0)"),
                 (0x8001F0F4, "lw v1, 0x894(gp)"), (0x8001F0F8, "sll v0, v0, 0x10"), (0x8001F0FC, "sra a0, v0, 0x17")]
SEA_LEVEL_NEW = [(0x8001F0C8, "lui at, 0x%X" % (SEA_LEVEL_ADDR >> 16)), (0x8001F0D8, "lw v0, 0x70fc(v1)"),
                 (0x8001F0DC, "lw at, 0x%X(at)" % (SEA_LEVEL_ADDR & 0xFFFF)), (0x8001F0E0, "andi v0, v0, 0xfff"),
                 (0x8001F0E4, "sll v0, v0, 2"), (0x8001F0E8, "addu v0, v0, v1"), (0x8001F0EC, "lhu v0, -0x1558(v0)"),
                 (0x8001F0F0, "lw v1, 0x894(gp)"), (0x8001F0F4, "sll v0, v0, 0x10"), (0x8001F0F8, "sra a0, v0, 0x17"),
                 (0x8001F0FC, "addu a0, a0, at")]


# Model table, a use the lui/use pairing missed (C36, user freeze 2026-10-12 21:11):
# 0x8004B5A4 `lui t7,0xA` (moved to 0x9F00) sits in the delay slot of a branch to
# 0x8004B7A0, whose `addiu t7,t7,0xE20` 0x20C bytes later still added the OLD table's
# offset: the read took entry index + 904, so a model index >= 1144 (Chicago's far
# water 1214 / shore walls 1215) read past the 2048 entries -> garbage model pointer
# -> address error at 0x8004B7CC (lhu flags2) -> the game stopped in the BIOS handler.
MODEL_TABLE_LATE = [
    (0x8004B7B0, 0x25EF0E20, 0x25EF0000 | ((NEW_BASE - (((NEW_BASE + 0x8000) >> 16) << 16)) & 0xFFFF),
     "addiu t7,t7,0xE20 -> addiu t7,t7,lo(NEW_BASE) (t7 = new table base's high half from 0x8004B5A4)"),
    # same class (found 21.10. by a branch-following scan, probe "optimisation 1" hang): 0x8002CED4 `beqz v0, 0x8002CF48`
    # has `lui t7, 0xA` (patched) in its delay slot; the far-object block at 0x8002CF48 adds 0xE20 itself. With the table
    # at 0x9F000000 it read entry index + 904 (wrong far models since the table move); at 0x80115600 it read below the
    # table (garbage pointer -> AdEL at 0x8002CF60 on every map).
    (0x8002CF4C, 0x25EF0E20, 0x25EF0000 | ((NEW_BASE - (((NEW_BASE + 0x8000) >> 16) << 16)) & 0xFFFF),
     "addiu t7,t7,0xE20 -> addiu t7,t7,lo(NEW_BASE) (t7 from the delay-slot lui at 0x8002CED8)"),
]


def sea_level_patches():
    return [(pc, asm(pc, [o])[0], asm(pc, [n])[0], "sea level: " + n)
            for (pc, o), (_, n) in zip(SEA_LEVEL_OLD, SEA_LEVEL_NEW)]


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
    # C38 root fix (14.10.): a restart left the drive streaming the old read (only the callback was
    # dropped); the new level's reads then met a stuck CD interrupt (spool-done wait 0x80033AF8 forever).
    # Now the queue is emptied and the spool's own end-of-queue path 0x80032DEC runs: CdReadyCallback(0)
    # + CdControl(CdlPause), as when a queue ends normally.
    (0x80051454, 0x0045102B, 0xAF800B40, "spool reset: sw zero,write index (queue empty)"),
    (0x80051458, 0x10400010, 0x0800CB7B, "spool reset: j 0x80032DEC (empty queue -> callback none + CdlPause)"),
    (0x8005145C, 0x00A62823, 0xAF800A88, "spool reset: sw zero,stream sectors left (delay slot)"),
    (0x8003381C, 0x8F820AC4, 0x0C014512, "lw v0,0xac4(gp) -> jal spool reset (0x80051448)"),
    (0x80033850, 0xAF820B40, 0xAF800B40, "sw v0,write index -> sw zero,write index"),
]


def spool_patches():
    out = list(SPOOL_CHAIN) + SPOOL_RESET + SPOOL_END
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
        _lw(AT, -0x3354 & 0xFFFF, 28),                   # lw   at, XTILE(gp)    C94: limit word (default TILE_LIMIT)
        _lw(V0, 0, V1),                                  # lw   v0, 0(v1)        primitive pointer
        _lw(V1, 8, V1),                                  # lw   v1, 8(v1)        buffer start
        0,                                               # nop
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
    skip = set(os.environ.get("CHI_EXCLUDE_PATCHES", "").split(","))   # bisection: spool_end, sea, mtlate
    groups = (RENDER_TRAP + AREA_SWITCH_WAIT
              + [q for q in spool_patches() if "spool_end" not in skip or q not in SPOOL_END]
              + (sea_level_patches() if "sea" not in skip else [])
              + (MODEL_TABLE_LATE if "mtlate" not in skip else []))
    for pc, old, new, note in groups:
        cur = struct.unpack_from("<I", img, pc - base)[0]
        if cur != old:
            raise RuntimeError("unexpected word at %08X: %08X (expected %08X)" % (pc, cur, old))
        out.append((pc, old, new, note))
    return out


# Height-aware road surface selection (C16/C17) is NOT an exe patch any more: the exe has
# no spare words (the "unreferenced" function 0x8006C078 is reached via 0x8006C964 -> C22
# crash) and the recomp fail-fasts on code outside its image. driver_chicago.c reorders the
# marked ROADSURF planes around the player every vblank instead (see NOTES.md).


# --- C45 part 3: skip resident stable pages at an area switch (opt-in: CHI_C45_SKIP=1) ---------
# The area loader 0x80033B10 queues a 17-sector read for every page of the new area, resident or not
# (residency 0x800BE278 only picks the slot). Pages below STABLE_END (main RAM word gp+0x2174,
# written by the plugin from the level's stable-page list; 0 = no skipping, every original city)
# have identical content in every area that lists them (Polish, CHI_POLISH_SHAREDPAGES): when such
# a page is resident it keeps its slot and gets no queue entry and no slot/page pair; only its disc
# offset advances. The page loop 0x80033BD4..0x80033D00 is rewritten (the per-page CITY table
# lookup of the sector base is hoisted out, which makes room). P2: the page stream countdown
# (0x80032EC0, = all queued pages) becomes 1, so after every page 0x80032DEC takes the next entry,
# compares the drive position and seeks after a skipped page (contiguous pages stream on).
STABLE_END_GP = 0x2174          # 0x800988E4, unused by the exe (zero in all dumps)
C45_LOOP, C45_LOOP_END = 0x80033BD4, 0x80033D00
C45_SKIP_CODE = [               # MIPS I: one instruction between a load and the use of its result
    "lw v1, 0xb24(gp)",
    "sll v0, t4, 4",
    "addu v0, v0, v1",
    "lhu t6, 0(v0)",               # the area's first page sector (relative to the spooled section)
    "lw v0, 0xc4(gp)",             # CITY
    "beq t2, zero, %#x" % C45_LOOP_END,
    "move a2, zero",
    "sll v0, v0, 5",
    "lui v1, 0xc",
    "addiu v1, v1, -0x1f5c",       # 0x800BE0A4 level location table
    "addu v0, v0, v1",
    "lw a1, 0x18(v0)",             # spooled section, byte position (>= 0)
    "lui v0, 0xc",
    "addiu s2, v0, -0x1d88",       # 0x800BE278 residency (slot + 1)
    "sra a1, a1, 11",
    "addu t6, t6, a1",             # absolute sector of the area's first page
    "lui v0, 0xa",
    "addiu s1, v0, 0x7ba4",        # 0x800A7BA4 spool queue
    "addiu t7, v0, 0x7f54",        # pair table: slot
    "addiu t9, v0, 0x7f50",        # pair table: page
    "sll v0, a3, 2",
    "addu t4, v0, sp",             # free slots (stack)
    "addiu t5, zero, 0x11",
    "lui t3, 3",
    "addiu t3, t3, 0x3870",        # page callback 0x80033870
    "addiu t0, zero, 1",
    "LOOP:",
    "lbu v0, 0(t1)",               # page
    "lw at, %#x(gp)" % STABLE_END_GP,
    "addu a0, v0, s2",
    "lbu v1, 0(a0)",
    "slt at, v0, at",              # stable page?
    "beq v1, zero, FREE",
    "addiu v1, v1, -1",            # (delay) resident: its slot
    "bne at, zero, SKIP",          # resident and stable: nothing to read
    "lw v0, 0xb44(gp)",            # (delay)
    "beq zero, zero, PAIR",
    "nop",
    "FREE:",
    "blez a3, %#x" % C45_LOOP_END,
    "addiu t4, t4, -4",
    "lw v1, 0(t4)",                # a free slot
    "lw v0, 0xb44(gp)",
    "addiu a3, a3, -1",
    "PAIR:",
    "lw a1, 0xb40(gp)",            # queue write index
    "sll a0, v0, 3",
    "addu a0, a0, t7",
    "sw v1, 0(a0)",                # pair: slot
    "addiu v1, v0, 1",
    "sw v1, 0xb44(gp)",
    "sll a0, v0, 3",
    "addu a0, a0, t9",
    "lbu v1, 0(t1)",
    "sll v0, a1, 4",
    "sw v1, 0(a0)",                # pair: page
    "addu a0, v0, s1",
    "addiu a1, a1, 1",
    "sw a1, 0xb40(gp)",
    "sb t0, 0(a0)",                # entry: type 1 (page)
    "sb zero, 1(a0)",
    "sh t5, 2(a0)",                # 17 sectors
    "sw t6, 4(a0)",                # disc sector
    "sw t8, 8(a0)",                # destination
    "sw t3, 0xc(a0)",              # callback
    "SKIP:",
    "addiu t6, t6, 0x11",
    "addiu a2, a2, 1",
    "slt v0, a2, t2",
    "bne v0, zero, LOOP",
    "addiu t1, t1, 1",             # (delay)
]
C45_COUNTDOWN = 0x80032EC0      # lw a1, 0xb44(gp) -> addiu a1, zero, 1


def c45_skip_patches(exe_path):
    if os.environ.get("CHI_C45_SKIP") != "1":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    if word(C45_COUNTDOWN) != 0x8F850B44 or word(0x80033C18) != 0x91220000:
        raise RuntimeError("unexpected area page loader")
    out = rewrite(exe_path, C45_LOOP, asm(C45_LOOP, C45_SKIP_CODE, C45_LOOP_END), "C45 page loop")
    out.append((C45_COUNTDOWN, 0x8F850B44, 0x24050001, "C45: page stream countdown 1 (seek after a skipped page)"))
    return out


# --- C47/C39: static "look CITY" instead of RAM code-word switches (opt-in: CHI_LOOK_CITY=1) -------
# The plugin used to rewrite code words in RAM for Chicago by day (CITY 3 = LA's night-only branches);
# every rewritten function then ran in the slow dirty-RAM interpreter (C47: +13-15 % host time in dense
# Chicago, mostly the per-car headlight code 0x8004B000). Now these sites read main-RAM words kept by
# the plugin (M8: a PS1 build sets them in guest code): LOOK_CITY = CITY, or 0x7F for Chicago by day
# (at the CITY loads whose value only feeds "== 3" / "== 5" / "== 1" compares), and C3 = 3, or 0x7F
# (the compare constant at 0x800298D8, whose CITY value is tested "< 4" afterwards; the instruction
# after the load does not use v0, so the load delay holds). C38: the region decoder's error path
# (printf from the CD interrupt) becomes the empty-region path, all cities.
LOOK_CITY_GP, C3_GP = 0x112C, 0x1128     # 0x8009789C / 0x80097898, unused by the exe (zero in all dumps)
# 0x8003B1A4 is NOT redirected: with CITY != 3 it calls 0x80079AF0(0x1F800308) (stack to the
# scratchpad), and Chicago's draw then crashed at level start (PC 0, 14.10. bisection); Chicago by day
# keeps LA's path there (no call), as LA always did.
LOOK_CITY_SITES = [0x80023634, 0x80023794, 0x80023CD0, 0x8003A6B0, 0x8003C970, 0x800437DC,
                   0x8004702C, 0x8004B250]
LOOK_CITY_SITES = [a for a in LOOK_CITY_SITES
                   if "%08X" % a not in os.environ.get("CHI_LOOK_SKIP", "").upper().split(",")]   # bisection


def look_city_patches(exe_path):
    if os.environ.get("CHI_LOOK_CITY") == "0":       # default since 14.10. (C47); 0 = old exe for A/B
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    out = []
    for a in LOOK_CITY_SITES:
        w = word(a)
        rs, imm = (w >> 21) & 31, w & 0xFFFF
        if w >> 26 != 0x23 or not ((rs == 28 and imm == 0xC4) or imm == 0x6834):
            raise RuntimeError("no CITY load at %08X" % a)
        new = (w & 0xFFFF0000) | (LOOK_CITY_GP if rs == 28 else 0x7898 + (LOOK_CITY_GP - 0x1128))
        if a == 0x8004702C and os.environ.get("CHI_MOON_GATE") != "0":   # C55: the sky sun test reads SUN_CITY
            out.append((a, w, (w & 0xFFFF0000) | 0x7884, "C47 + C55: CITY load -> SUN_CITY word (0x80097884)"))
            continue
        out.append((a, w, new, "C47: CITY load -> look CITY word"))
    # C51: the car damage zone tables (0x8003E5A8: CITY indexes 0x8008A6BC/DC/FC/1C) follow the loaded car set
    if word(0x8003E5A8) != 0x8C636834:
        raise RuntimeError("unexpected 0x8003E5A8")
    out.append((0x8003E5A8, 0x8C636834, 0x8C6378A0, "C51: damage zone tables by CARSET_CITY (0x800978A0)"))
    if word(0x800298D8) != 0x24020003:
        raise RuntimeError("unexpected 0x800298D8")
    out.append((0x800298D8, 0x24020003, (0x23 << 26) | (28 << 21) | (2 << 16) | C3_GP, "C47: li v0,3 -> lw v0,C3(gp)"))
    if word(0x80035670) != 0x14A20026:
        raise RuntimeError("unexpected 0x80035670")
    out.append((0x80035670, 0x14A20026, 0x14A2FFCD, "C38: decoder error path -> empty region"))
    return out


# --- C42 step 1: Driver 2 traffic/cop cars get Driver 2's damage zone tables -------------------------
# Driver 1 loads ONE set of damage zone tables for every city at boot (DRIVER/DTL.BIN, 6484 B, to
# 0x801F8BC0); the four per-CITY pointer tables 0x8008A6BC/DC/FC/1C hold the same address in all 8
# entries. Entry 4 (FLAT, not used any more) of the civ verts / civ polys tables now points at
# 0x800A0E20 / 0x800A11A4 (the old model-table area, unused since the model table moved): the plugin
# writes Driver 2's civ tables there (Polish's damage blob) and sets CARSET_CITY (0x800978A0, read at
# 0x8003E5A8) to 4 while Chicago with Driver 2 traffic cars is loaded. Player entries stay DTL's.
# C42 engine step (Infrastructure 17.10.): DentCar indexes the civ rows by the AI car's RESIDENT model (AI record
# +0x10 = 1..3 = lump slots 0..2; resident 0 = the player's car), so the entries point one row (300 / 420 B) below
# the blob: row 1 (cop, slot 0) lands at 0x800A0E20 / 0x800A11A4. Before, slot 1 dented with slot 2's row and slot 2
# read the polygon table (the "no dents on Driver 2 cars" of the d2 cars probe).
C42_TABLES = [
    (0x8008A6EC, 0x001F919C, 0x000A0CF4, "C42: civ verts table, entry 4 -> 0x800A0E20 - 300 (rows by resident model 1..3)"),
    (0x8008A72C, 0x001F9E80, 0x000A1050, "C42: civ polys table, entry 4 -> 0x800A11A4 - 420"),
]


def c42_table_patches(exe_path):
    if os.environ.get("CHI_C42_TABLES") == "0":      # default since 14.10. (applied with the disc exe)
        return []
    img, base = load_exe(exe_path)
    for pc, old, _new, _n in C42_TABLES:
        if struct.unpack_from("<I", img, pc - base)[0] != old:
            raise RuntimeError("unexpected word at %08X" % pc)
    return list(C42_TABLES)



# --- C53 / C42: car cosmetics (wheel and light positions) by car set -----------------------------------
# LoadCosmetics 0x80052620 copies the player's row (base + model) and the cop/civ rows (base + 5..7) of
# the table 0x800853D8 (100-B rows, 8 per city) by a jump-table switch on CITY (0x80010A20: bases 0, 8,
# 0x10, 0x18, -, 0x20, -, 0x28). It now reads CARSET_CITY (0x800978A0, the plugin's car-set word, as the
# damage tables since C51): Chicago by day with Miami's cars gets Miami's rows (C53; it had LA's). The
# jump table becomes a table of bases (lw a0 instead of jr); entry 4 (FLAT, unused) = 0x482 points at
# 0x800A16A0 (old model-table area, free behind the C42 damage tables), where the plugin writes the
# Chicago rows of a level with Driver 2 cars (Polish: Miami / LA rows 0-4 + D2 cop, civ0, civ1 in 5-7).
COSMETICS_ROWS = 0x800A16A0
COSMETICS = [
    (0x80052624, 0x8C636834, 0x8C6378A0, "C53: LoadCosmetics reads CARSET_CITY 0x800978A0 instead of CITY"),
    (0x80052648, 0x8C620000, 0x8C640000, "C53: lw a0, (v1): the base from the table"),
    (0x8005264C, 0x00000000, 0x080149A1, "C53: j 0x80052684 (instead of jr v0)"),
    (0x80052650, 0x00400008, 0x00000000, "C53: nop (delay slot)"),
] + [(0x80010A20 + 4 * i, old, new, "C53: base table entry %d" % i) for i, (old, new) in enumerate([
    (0x00052658, 0x00), (0x00052660, 0x08), (0x00052668, 0x10), (0x00052670, 0x18),
    (0x00052658, (COSMETICS_ROWS - 0x800853D8) // 100), (0x00052678, 0x20), (0x00052658, 0x00), (0x00052680, 0x28)])]


def cosmetics_patches(exe_path):
    if os.environ.get("CHI_COSMETICS") == "0":       # default since 14.10. (applied with the disc exe)
        return []
    img, base = load_exe(exe_path)
    for pc, old, _new, _n in COSMETICS:
        if struct.unpack_from("<I", img, pc - base)[0] != old:
            raise RuntimeError("unexpected word at %08X" % pc)
    return list(COSMETICS)



# --- C17: drowning at a water edge in Driver 2 cities (default; CHI_DROWN_EDGE=0 off; needs COSMETICS) --------
# Drowning (FUN_0003A698, general path 0x8003ADC4) tests the car CENTRE's cell (model flag 0x80) and y < 0xDC,
# but FindSurfaceD2 gives every WHEEL sea ground (wave + sea offset, -1084 in Chicago): a car straddling a
# street / water edge sank on its water wheels while its centre stayed on a street cell, no countdown,
# stuck ~1000 below the street (FAN deckfall, hs_drop). Now: "centre not sea" goes through a cave that
# still takes the sea path when a wheel took FindSurfaceD2's sea path since the last check (0x800970F8,
# written only by FindSurfaceD2, read by nothing: its clear at 0x8001F158 goes, the cave clears it) and the
# car's y lies in [-1120, -500) (the water surface band; the 1352 trench floor is outside), with the band
# width from DROWN_RANGE (gp+0x1138 = 0x800978A8, unused: plugin 620 in Chicago, 0 = off, so the D1 cities
# keep their rule). Cave: the LoadCosmetics case blocks freed by COSMETICS (default block moved up a word).
DROWN_EDGE = [
    (0x80052630, 0x10400009, 0x10400008, "C17: LoadCosmetics default case -> 0x80052654 (moved up)"),
    (0x80052654, 0x00000000, 0x080149A1, "C17: default case: j 0x80052684"),
    (0x80052658, 0x080149A1, 0x00002021, "C17: default case: move a0, zero (delay)"),
    (0x8005265C, 0x00002021, 0x8F831138, "C17 cave: lw v1, 0x1138(gp) (DROWN_RANGE)"),
    (0x80052660, 0x080149A1, 0x8E2500CC, "C17 cave: lw a1, 0xcc(s1) (car y)"),
    (0x80052664, 0x24040008, 0x83820988, "C17 cave: lb v0, 0x988(gp) (a wheel took the sea path)"),
    (0x80052668, 0x080149A1, 0x24A50460, "C17 cave: addiu a1, a1, 1120"),
    (0x8005266C, 0x24040010, 0x00A3282B, "C17 cave: sltu a1, a1, v1 (-1120 <= y < -1120 + range)"),
    (0x80052670, 0x080149A1, 0x00451024, "C17 cave: and v0, v0, a1"),
    (0x80052674, 0x24040018, 0x1440A1D6, "C17 cave: bnez v0, 0x8003ADD0 (the sea path)"),
    (0x80052678, 0x080149A1, 0xA3800988, "C17 cave: sb zero, 0x988(gp) (delay: clear)"),
    (0x8005267C, 0x24040020, 0x0800EB9F, "C17 cave: j 0x8003AE7C (the reset path)"),
    (0x80052680, 0x24040028, 0x27A50088, "C17 cave: addiu a1, sp, 0x88 (delay: the reset path's first word)"),
    (0x8003ADC8, 0x1040002B, 0x10405E24, "C17: centre not sea -> the cave (delay move a0, s2 stays)"),
    (0x8001F158, 0xA02070F8, 0x00000000, "C17: FindSurfaceD2 keeps the sea-wheel flag set (the cave clears it)"),
]


# M3 (27.10., Havana harbour): the band started at Chicago's fixed -1120 (`addiu a1, a1, 1120`). The cave now jumps to a
# bigger one in the 0x8008A2A4..0x8008A464 padding (C113 / C114 share it) that adds BANDW (zero-block word 0x80093624,
# gp -0x314C) instead: the plugin writes the city's band start (Chicago 1120, Havana 2750 + 36); 0 with DROWN_RANGE 0
# in the D1 cities = the D1 rule as before. The old cave words after the jump stay (unreachable).
C17_BANDW, C17_BANDW_GP = 0x80093624, -0x314C
C17_CAVE, C17_CAVE_END = 0x8008A340, 0x8008A378         # (end tightened 28.10. for C133's cave behind it)


def drown_edge_patches(exe_path):
    if os.environ.get("CHI_DROWN_EDGE") == "0":      # default since 14.10. (applied with the disc exe)
        return []
    if not cosmetics_patches(exe_path):
        raise RuntimeError("CHI_DROWN_EDGE needs the COSMETICS group (its cave)")
    img, base = load_exe(exe_path)
    for pc, old, _new, _n in DROWN_EDGE:
        if struct.unpack_from("<I", img, pc - base)[0] != old:
            raise RuntimeError("unexpected word at %08X" % pc)
    out = list(DROWN_EDGE)
    if os.environ.get("CHI_DROWN_BANDW") == "0":     # the old fixed -1120 band (Chicago only)
        return out
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    if word(C17_BANDW) != 0:
        raise RuntimeError("C17: BANDW word not free")
    for a in range(C17_CAVE, C17_CAVE_END, 4):
        if word(a) != 0:
            raise RuntimeError("C17: cave word %08X not zero" % a)
    src = ["lw v1, 0x1138(gp)", "lw a1, 0xcc(s1)", "lb v0, 0x988(gp)", "lw at, %d(gp)" % C17_BANDW_GP, "nop",
           "addu a1, a1, at", "sltu a1, a1, v1", "and v0, v0, a1", "beq v0, zero, RST", "sb zero, 0x988(gp)",
           "j 0x8003add0", "nop", "RST:", "j 0x8003ae7c", "addiu a1, sp, 0x88"]
    cw = asm(C17_CAVE, src)
    assert C17_CAVE + 4 * len(cw) <= C17_CAVE_END
    out += [(C17_CAVE + 4 * i, 0, w, "C17 band cave %d (BANDW)" % i) for i, w in enumerate(cw) if w]
    j = asm(0x8005265C, ["j %#x" % C17_CAVE, "nop"])
    out = [(pc, o, (j[0] if pc == 0x8005265C else j[1] if pc == 0x80052660 else n), d) for pc, o, n, d in out]
    return out


# --- Chicago music (milestone 2): Chicago-gated song select ---------------------------------------------
# The mission loader stores the song (mission + 3) & 7 at 0x800687A8..B8 (sll/sra sign extension, addiu 3,
# andi 7, sw 0x1030(gp)); MUSIC.BIN's songs 0-7 belong to the D1 cities. The relocated MUSIC.BIN (Polish,
# built by build_package from the discs) adds 8 = D2 Chicago day, 9 = night. The sign extension is dropped
# (only the low 3 bits count) and a main-RAM word MUSIC_XOR (gp+0x217C = 0x800988EC, unused by the exe,
# zero in all dumps) is XORed in: 0 for every other city (unchanged song), song ^ ((mission + 3) & 7) for
# Chicago (the plugin sets it at the parser entry 0x80068928, which runs just before). PS1-native: guest
# instructions + one RAM word (the Chicago decision itself is the plugin's, host-only list). v1 is free here
# (the function returns right after; jr delay slot nop).
MUSIC_XOR_GP = 0x217C
MUSIC_SELECT = [
    (0x800687A8, 0x00101400, 0x8F83217C, "music: lw v1, 0x217C(gp) (MUSIC_XOR, 0 = unchanged)"),
    (0x800687AC, 0x00021403, 0x26020003, "music: addiu v0, s0, 3 (sign extension dropped: & 7 follows)"),
    (0x800687B0, 0x24420003, 0x30420007, "music: andi v0, v0, 7"),
    (0x800687B4, 0x30420007, 0x00431026, "music: xor v0, v0, v1 (then the original sw v0, 0x1030(gp))"),
]


def music_select_patches(exe_path):
    if os.environ.get("CHI_MUSIC_SELECT") == "0":    # default since 14.10. (applied with the disc exe)
        return []
    img, base = load_exe(exe_path)
    for pc, old, _new, _n in MUSIC_SELECT:
        if struct.unpack_from("<I", img, pc - base)[0] != old:
            raise RuntimeError("unexpected word at %08X" % pc)
    return list(MUSIC_SELECT)


# --- C12 minimap at Driver 2's zoom: the CLUT behind a larger tile table --------------------------------
# The overlay-map loader FUN_80054140 uploads the map CLUT from map + 0x148 (0x80054194 `addiu a1, a1, 0x148`,
# the jal delay slot); D1's lumps have 160 tile slots before it. Chicago at D2's own scale (polish_map F=1)
# needs 252 slots, its CLUT sits at 0x200. The heap-pointer update before the jal is rewritten gp-relative
# (two lui freed) to add MAP_CLUT_EXTRA (gp+0x1134 = 0x800978A4, no exe xrefs) to the CLUT address: 0 for every
# D1 city (unchanged), CLUT_AT - 0x148 for a Driver 2 map (the plugin sets it from the level's frame before the
# level loads). PS1-native: guest instructions + one RAM word.
MAP_CLUT_GP = 0x1134
MAP_CLUT = [
    (0x80054178, 0x3C020009, 0x8F820928, "C12: lw v0, 0x928(gp) (heap pointer 0x80097098)"),
    (0x8005417C, 0x8C427098, 0x8F881134, "C12: lw t0, 0x1134(gp) (MAP_CLUT_EXTRA)"),
    (0x80054180, 0x00000000, 0x00501021, "C12: addu v0, v0, s0"),
    (0x80054184, 0x00501021, 0xAF820928, "C12: sw v0, 0x928(gp)"),
    (0x80054188, 0x3C010009, 0x00A82821, "C12: addu a1, a1, t0 (CLUT = map + 0x148 + extra)"),
    (0x8005418C, 0xAC227098, 0x00000000, "C12: nop"),
]


def map_clut_patches(exe_path):
    if os.environ.get("CHI_MAP_CLUT") == "0":        # default since 16.10. (applied with the disc exe)
        return []
    img, base = load_exe(exe_path)
    for pc, old, _new, _n in MAP_CLUT:
        if struct.unpack_from("<I", img, pc - base)[0] != old:
            raise RuntimeError("unexpected word at %08X" % pc)
    return list(MAP_CLUT)


# --- C37: Driver 2's plane height (sdHeightOnPlane: -d - (a x + c z) / b) for Driver 2 cities --------------------
# MapHeight 0x8001F5B0 and FindSurfaceD2 0x8001EEB4 (the only readers of the surface planes) compute the height as
# ((x a + z c) >> 12) - d - cell height, so a unit normal makes a slope g only g / sqrt(1 + g^2) steep (45 deg ->
# 0.71). Both now divide by divisor = 4096 + ((b - 4096) & D2_PLANES): D2_PLANES (gp+0x1110 = 0x80097880, no exe
# xrefs) is 0 in every D1 city (divisor 4096: div truncates toward zero exactly like the original
# (sum + 0xFFF if negative) >> 12, so D1 heights stay bit-identical) and -1 in a Driver 2 city (the plugin), where
# the data writes Driver 2's unit normals (b > 0) and heights become exact. The blocks are rescheduled in place
# (a load moved into the preceding branch delay slot; HI/LO hazards kept at >= 2 instructions). PS1-native.
D2_PLANES_GP = 0x1110


def _div(rs, rt):
    return ".word 0x%08x" % ((REG[rs] << 21) | (REG[rt] << 16) | 0x1A)


# C86 (23.10.): MapHeight's block added -4096 to v0 one instruction after "lw v0, -8(s0)" (load delay: the divisor came
# from a = -0xc instead of b in Driver 2 cities -> wrong heights for everything MapHeight serves, e.g. the camera)
SLOPE_DIV_MAPHEIGHT = ["lw v0, -0xc(s0)", "lw a3, -4(s0)", "mult s3, v0", "lw v0, -8(s0)", "lw t0, 0x1110(gp)",
                       "mflo v1", "addiu v0, v0, -4096", "and v0, v0, t0", "mult s4, a3", "addiu v0, v0, 4096",
                       "mflo a3", "addu a3, v1, a3", "lw v1, 0(s0)", _div("a3", "v0"), "mflo v0", "subu a0, v0, v1"]
SLOPE_DIV_FINDSURF = ["lw a0, -0xc(s0)", "lw a1, -4(s0)", "mult s3, a0", "lw a3, -8(s0)", "lw t4, 0x1110(gp)",
                      "mflo v0", "addiu v1, a3, -4096", "and v1, v1, t4", "mult s4, a1", "addiu v1, v1, 4096",
                      "lw a2, 0(s0)", "mflo t4", "addu v0, v0, t4", "nop", _div("v0", "v1"), "mflo v0",
                      "subu a2, v0, a2"]


def slope_div_patches(exe_path):
    if os.environ.get("CHI_SLOPE_DIV") == "0":        # default since 16.10. (applied with the disc exe)
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    out = []
    for start, lines, first_old in ((0x8001F8A8, SLOPE_DIV_MAPHEIGHT, 0x00000000), (0x8001F2B4, SLOPE_DIV_FINDSURF, 0x00000000)):
        words = asm(start, lines)
        if word(start) != first_old or word(start - 4) & 0xFC000000 != 0x10000000:   # a nop in a beq delay slot
            raise RuntimeError("C37 slope div: unexpected code at %08X" % start)
        out += [(start + 4 * k, word(start + 4 * k), w, "C37 plane height / b: %s" % ln) for k, (w, ln) in enumerate(zip(words, lines))]
    return out


# --- C55: Chicago's night moon -------------------------------------------------------------------------------------
# The sky sun routine FUN_80046E44 draws the sun disc (0x800473F0) and its glare (0x800493CC) unless LOOK_CITY == 3
# (LA is a night-only city: no sun). Chicago night runs as CITY 3, so its moon (D2's SKYMOON in the SKYSUN slot) was
# never drawn. The test at 0x8004702C now reads its own word SUN_CITY (0x80097884, no exe xrefs; the plugin keeps it
# = LOOK_CITY, except Chicago: 0x7F by day, 0x7E by night), and the glare call goes through a stub that skips it for
# 0x7E (the moon has no glare). Stub in the unused MDEC debug strings 0x80011868.. (no references), seeded.
MOON_STUB = 0x80011868
# C55 follow-up (user reviews of probes "look" / "look 2", 16.10.): at NIGHT a Driver 2 city shows ONLY the moon sprite:
# the stub skips the full-screen glare tile for SUN_CITY 0x7E and clears s1, the caller's sun visibility count, so
# the lens-flare chain after it (0x800470C8: drawn only for s1 != 0) is skipped too (s1 is reassigned or restored
# later in FUN_00046E44). By DAY (0x7F) the sun keeps Driver 1's glare, flare and halo, as in the Driver 1 cities.
MOON_GATE_CODE = ["lw t0, 0x1114(gp)", "addiu t1, zero, 0x7e", "beq t0, t1, MRET", "nop",
                  "j 0x800493cc", "nop", "MRET:", "jr ra", "move s1, zero"]
# The disc itself (FUN_000473F0, block 0x800474A0..0x8004751C, 32 words) is rewritten in place without its load-delay
# nops: the same 24 x 20 quad, but for the night moon (SUN_CITY 0x7E) a bigger quad (CHI_MOON_HW / _HH half sizes) and
# a3 (the visibility count, the brightness of the rotating ray halo drawn next) = 0, so the additive halo adds nothing.
# t2 / t5..t9 are free here (t2, t5 are written before their next use; t6..t9 unused in the function).
MOON_HW = int(os.environ.get("CHI_MOON_HW", "18"))
MOON_HH = int(os.environ.get("CHI_MOON_HH", "15"))
DISC_BLOCK = 0x800474A0
DISC_CODE = ["lhu t7, 0(a0)", "lhu t8, 2(a0)", "lw t6, 0x1114(gp)", "addiu t5, zero, 12", "addiu t9, zero, 10",
             "addiu t2, zero, 0x7e", "bne t6, t2, DSZ", "lui v1, 0xc",
             "move a3, zero", "addiu t5, zero, %d" % MOON_HW, "addiu t9, zero, %d" % MOON_HH,
             "DSZ:", "subu v0, t7, t5", "sh v0, 8(a1)", "subu v0, t8, t9", "sh v0, 0xa(a1)",
             "addu v0, t7, t5", "sh v0, 0x10(a1)", "subu v0, t8, t9", "sh v0, 0x12(a1)",
             "subu v0, t7, t5", "sh v0, 0x18(a1)", "addu v0, t8, t9", "sh v0, 0x1a(a1)",
             "addu v0, t7, t5", "sh v0, 0x20(a1)", "addu v0, t8, t9", "sh v0, 0x22(a1)"] + ["nop"] * 5


def moon_gate_patches(exe_path):
    if os.environ.get("CHI_MOON_GATE") == "0":        # default since 16.10. (applied with the disc exe)
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    if img[MOON_STUB - base: MOON_STUB - base + 9] != b"MDEC_rest":
        raise RuntimeError("moon stub: unexpected bytes at %08X" % MOON_STUB)
    # (the load at 0x8004702C is rewritten to SUN_CITY by look_city_patches, which owns that word)
    out = [(0x80047068, 0x0C0124F3, asm(0x80047068, ["jal 0x%08x" % MOON_STUB])[0], "C55: glare via the night stub")]
    for pc, old, _new, _n in out:
        if word(pc) != old:
            raise RuntimeError("unexpected word at %08X" % pc)
    code = asm(MOON_STUB, MOON_GATE_CODE)
    assert MOON_STUB + 4 * len(code) <= CHASE_TAB
    out += [(MOON_STUB + 4 * k, word(MOON_STUB + 4 * k), w, "C55 moon stub %d" % k) for k, w in enumerate(code)]
    if os.environ.get("CHI_SUN_SPRITE") != "0":      # C55 follow-up: sprite only, bigger moon
        if word(DISC_BLOCK) != 0x94820000 or word(0x80047514) != 0x3C03000C or word(0x8004751C) != 0xA4A20022:
            raise RuntimeError("sun disc block: unexpected words")
        dcode = asm(DISC_BLOCK, DISC_CODE)
        assert len(dcode) == 32, len(dcode)
        out += [(DISC_BLOCK + 4 * k, word(DISC_BLOCK + 4 * k), w, "C55 disc block %d" % k) for k, w in enumerate(dcode)]
    return out


# --- C60 chase music: a 10-entry xm_coptrackpos (Infrastructure 16.10.) -------------------------------------------
# The chase switch in 0x8004CF50 (Driver 2's FunkUpDaBGMTunez) jumps to xm_coptrackpos[song] (lhu from table
# 0x8008AA04, 8 ints; base lui/addiu at 0x8004CF84/88, only reference 0x8004CFA4). Chicago's songs 8 / 9 (CHI_POLISH_MUSIC)
# read past its end (InitSound's SPU words) -> no chase music. The base now points at a 10-int copy in the unused MDEC
# debug strings after the C55 moon stub (0x8001188C..0x800118B3, no references, not code): Driver 1's 8 entries
# unchanged + Driver 2's Chicago chase positions (polish_music.coptrackpos_table: day 7, night 8). CHI_CHASE_TABLE=0 = off.
# C120 (probe havana 1: no chase music in Havana): Havana's songs 10 / 11 read past the 10 entries (the next stub's code,
# 0xFFF8 -> a bogus order position). The table is now 16 ints in the zero padding 0x8008A2A4..0x8008A300 (before the C114
# cave; margins kept): Driver 1's 8 + Driver 2's xm_coptrackpos_d2 for the songs of each D2 city in song-slot order
# (Chicago 8 / 9, Havana 10 / 11, Las Vegas 12 / 13, Rio 14 / 15; cityprofile songs -> chase_pos). The MDEC strings
# at 0x8001188C are no longer written. CHI_CHASE_TABLE16=0 = the 10-entry table.
CHASE_TAB = 0x8001188C
CHASE_TAB16 = 0x8008A2B0


def chase_table16() -> bytes:
    import cityprofile as cp
    import polish_music
    pos = list(polish_music.D1_COPTRACKPOS)
    for prof in (cp.CHICAGO, cp.HAVANA, cp.VEGAS, cp.RIO):     # song slots 8.. in this order (plugin s_song_base)
        assert len(prof.chase_pos) == 2, prof.name
        pos += list(prof.chase_pos)
    assert len(pos) == 16 and pos[8:10] == [polish_music.CHASE_POS[8], polish_music.CHASE_POS[9]]
    return struct.pack("<16i", *pos)


def chase_table_patches(exe_path):
    if os.environ.get("CHI_CHASE_TABLE") == "0":
        return []
    import polish_music
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    if img[0x80011884 - base: 0x80011884 - base + 12] != b"MDEC_in_sync":
        raise RuntimeError("chase table: unexpected bytes at %08X" % CHASE_TAB)
    t16 = os.environ.get("CHI_CHASE_TABLE16") != "0"
    tab = chase_table16() if t16 else polish_music.coptrackpos_table()
    at = CHASE_TAB16 if t16 else CHASE_TAB
    if tab[:32] != img[0x8008AA04 - base: 0x8008AA24 - base]:
        raise RuntimeError("chase table: Driver 1's xm_coptrackpos differs")
    if t16 and any(word(a) for a in range(0x8008A2A4, 0x8008A300, 4)):
        raise RuntimeError("chase table: padding 0x8008A2A4..0x8008A300 not zero")
    out = [(0x8004CF84, 0x3C020009, 0x3C020000 | (at + 0x8000) >> 16, "C60: xm_coptrackpos base hi"),
           (0x8004CF88, 0x2442AA04, 0x24420000 | (at & 0xFFFF), "C60: xm_coptrackpos base lo")]
    for pc, old, _new, _n in out:
        if word(pc) != old:
            raise RuntimeError("unexpected word at %08X" % pc)
    out += [(at + 4 * k, word(at + 4 * k), struct.unpack_from("<I", tab, 4 * k)[0],
             "C60 chase table %d" % k) for k in range(len(tab) // 4)]
    return out


# --- C68 hang in probe "look" (Infrastructure 16.10.; EXP research_hang_look.md) --------------------------------------
# FUN_0005F0EC (ambient objects on non-road cells, list from FUN_000143CC) calls FUN_000217C8(x, z, local_30) and
# ignores its result: FUN_000217C8 writes local_30[0] (the cell's model index) only when the road-map lookup
# FUN_00021690 finds a non-zero cell word. Chicago has empty cells (word 0) inside its 960 x 1260 grid (Driver 1's
# cities have none), so local_30[0] kept stale stack data (0x3640 = half a pointer), the model table read
# 0x9F000000 + 4 * 13888 gave garbage and "lhu 2(p)" at 0x8005F350 raised AdEL -> BIOS exception loop (the hang).
# The call now goes through a stub that clears local_30[0] first (no cell = model 0, the sky: never water, so the
# object gets the land type as for any dry cell) and also falls back to 0 when the table entry is null (model not
# resident). The index itself is the road map's 10-bit model id (< 900 by the converter), so no 11th bit is needed.
# Stub in the unused part of the libgpu "$Id: sys.c" string (only its address is printed by ResetGraph) and the pad
# before it, 0x800118B4..0x800118EF; seeded. All cities (a stale index can only be wrong). CHI_C68=0 = off.
C68_STUB = 0x800118B4
C68_CODE = ["addiu sp, sp, -8", "sw ra, 0(sp)", "jal 0x800217c8", "sh zero, 0(a2)",
            "lh t0, 0x38(sp)", "lui t1, 0x%x" % ((NEW_BASE + 0x8000) >> 16), "sll t0, t0, 2", "addu t0, t0, t1",
            "lw t0, %d(t0)" % (NEW_BASE - (((NEW_BASE + 0x8000) >> 16) << 16)), "lw ra, 0(sp)",
            "bne t0, zero, C68OK", "addiu sp, sp, 8", "sh zero, 0x30(sp)", "C68OK:", "jr ra", "nop"]


def c68_patches(exe_path):
    if os.environ.get("CHI_C68") == "0":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    if word(C68_STUB) != 0 or img[0x800118B8 - base: 0x800118B8 - base + 10] != b"$Id: sys.c" or \
            img[0x800118F0 - base: 0x800118F0 - base + 10] != b"ResetGraph":
        raise RuntimeError("C68 stub: unexpected bytes at %08X" % C68_STUB)
    if word(0x8005F334) not in (0x3C03000A, 0x3C039F00, 0x3C030000 | ((NEW_BASE + 0x8000) >> 16)):
        raise RuntimeError("C68: unexpected model table load at 8005F334")
    out = [(0x8005F318, 0x0C0085F2, asm(0x8005F318, ["jal 0x%08x" % C68_STUB])[0], "C68: cell model lookup via the stub")]
    if word(0x8005F318) != 0x0C0085F2:
        raise RuntimeError("unexpected word at 8005F318")
    code = asm(C68_STUB, C68_CODE)
    assert C68_STUB + 4 * len(code) <= 0x800118F0
    out += [(C68_STUB + 4 * k, word(C68_STUB + 4 * k), w, "C68 stub %d" % k) for k, w in enumerate(code)]
    return out


# --- C45 quay: near-only subdivision for Driver 2 cities (Driver 2's own rule, REDRIVER2 draw.c / tile.c) -------
# D1 subdivides a world quad only when its model flags it (0x20 / 0x40) and never a big ground/water tile in its mid
# band, so a large polygon passing the camera projects a vertex at/behind the camera plane (GTE overflow, x/y
# saturated) -> the stretched planes at the quay (GATE 1204, SHOREWALL 1215, water tile 683). Driver 2 subdivides
# whatever gets near and drops the too-near pieces. Gated by NEAR_SUB (gp+0x1124 = 0x80097894, no exe xrefs):
# bit 0 = world quads, bit 1 = tiles; the plugin sets 3 in a Driver 2 city (CHI_NEAR_SUB_BITS overrides for tests),
# 0 keeps every D1 map as before.
# 1. World quads: the polygon handler table entry for textured quads (scratchpad 0x8C, set at 0x8002D534/38,
#    originally 0x8003056C) points at WQ in the cave: with bit 0 set, a quad whose v0-v3 screen diagonal spans
#    >= NEAR_SUB_PX (64) pixels gets its 4 vertices' depth from the GTE (RTPT + RTPS with the object's matrix); if one
#    lies nearer than NEAR_SUB_Z (600) it goes to the 4x4 subdivision handler 0x80030F60, whose pieces pass
#    0x80030C20; every other quad runs a copy of the original handler inline (no extra call).
#    (A screen guard band missed walls whose near vertex projects inside the screen; gating by the object's near
#    level missed the shore walls (level 0 at the camera); all objects without the pre-filter cost 3 % FPS.)
# 2. Ground/water tiles: the near-band test (0x80027518, depth < 2000 -> 3x3 subdivided routine 0x800287A4) admits
#    depth < 2300 to the cave, which keeps depth < 2000 and adds depth < bounding radius (model +8) + 100 when bit 1
#    is set: only a big tile (water 683, radius 2120) whose edge reaches the camera qualifies.
# 3. Sub-pieces (0x80030C20): dropped when avg sz / 2 < 0x20 + NEAR_PIECE (gp+0x113C = 0x800978AC; plugin: 96 in a
#    Driver 2 city, D1 0 = its own 0x20), as Driver 2 drops its too-near pieces.
# Code cave: libgpu debug strings 0x80011924..0x80011AD7 (SetGraphDebug text: printed only for a level != 0, main
# passes 0; SetGrapQue .. PutDispEnv: GPU debug level >= 2 only; GPU-timeout text: only on a GPU timeout;
# 'LoadImage2': no reference); seeded in seeds/ghidra_funcs.txt (KSEG0: WQ, TCAVE) so the recompiler compiles it
# natively. PS1-native (guest code + two RAM words). Cost 16.10. at fps_drop_2: about -1.3 % (world -0.4, tiles
# -0.8: tiles at depth 2000..2300 pass the cave).
NEAR_SUB_GP = 0x1124
NEAR_SUB_CAVE = 0x80011924          # from the SetGraphDebug text (printed only for a level != 0; main sets 0)
NEAR_SUB_CAVE_END = 0x80011AD8      # + the GPU-timeout text and 'LoadImage2' (debug/error prints only)
NEAR_SUB_Z = int(os.environ.get("CHI_NEAR_SUB_Z", "600"))   # a quad with a vertex this near (SZ) is subdivided
NEAR_SUB_PX = int(os.environ.get("CHI_NEAR_SUB_PX", "64"))   # ... if its v0-v3 diagonal spans this many pixels
QUAD_HANDLER = 0x8003056C


def _near_sub_code(img, base):
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    plain = [word(QUAD_HANDLER + 4 * k) for k in range(25)]      # sw ra .. jr ra; sw t0,-0x24(v0) (no relative branches)
    assert plain[23] == 0x03E00008, "unexpected quad handler"
    c = NEAR_SUB_CAVE
    LW = lambda rt, off, base: ".word 0x%08x" % ((0x32 << 26) | (REG[base] << 21) | (rt << 16) | (off & 0xFFFF))   # lwc2
    MF = lambda rt, rd: ".word 0x%08x" % (0x48000000 | (REG[rt] << 16) | (rd << 11))                         # mfc2
    RTPT, RTPS = ".word 0x4a280030", ".word 0x4a180001"
    world = ["WQ:", "lw t0, 0x1124(gp)", "nop", "andi t0, t0, 1", "beq t0, zero, PLAIN", "nop",
             # cheap screen pre-filter: the diagonal v0-v3 spans >= NEAR_SUB_PX (|dx| + |dy|), else plain
             "sll t0, t1, 2", "andi t0, t0, 0x3fc", "addu t0, t0, v1", "lw s2, 0x1f0(t0)",
             "srl t0, t1, 22", "andi t0, t0, 0x3fc", "addu t0, t0, v1", "lw s3, 0x1f0(t0)",
             "sll t0, s2, 16", "sra t0, t0, 16", "sll t4, s3, 16", "sra t4, t4, 16", "subu t0, t4, t0",
             "sra t4, t0, 31", "xor t0, t0, t4", "subu t0, t0, t4",
             "sra s2, s2, 16", "sra s3, s3, 16", "subu s2, s3, s2", "sra t4, s2, 31", "xor s2, s2, t4", "subu s2, s2, t4",
             "addu t0, t0, s2", "sltiu t0, t0, %d" % NEAR_SUB_PX, "bne t0, zero, PLAIN", "lw t5, 0x74(v1)",
             # depth test: SZ of the 4 vertices (GTE, the object's matrix is loaded); any < NEAR_SUB_Z -> 4x4
             "sll t0, t1, 3", "andi t0, t0, 0x7f8", "addu t0, t0, t5", LW(0, 0, "t0"), LW(1, 4, "t0"),
             "srl t0, t1, 5", "andi t0, t0, 0x7f8", "addu t0, t0, t5", LW(2, 0, "t0"), LW(3, 4, "t0"),
             "srl t0, t1, 13", "andi t0, t0, 0x7f8", "addu t0, t0, t5", LW(4, 0, "t0"), LW(5, 4, "t0"),
             "srl t0, t1, 21", "andi t0, t0, 0x7f8", RTPT, "addu t0, t0, t5",
             MF("s2", 17), MF("s3", 18), MF("s4", 19), LW(0, 0, "t0"), LW(1, 4, "t0"), "nop", RTPS,
             "sltiu s2, s2, %d" % NEAR_SUB_Z, "sltiu s3, s3, %d" % NEAR_SUB_Z, MF("t4", 19),
             "sltiu s4, s4, %d" % NEAR_SUB_Z, "or s2, s2, s3", "sltiu t4, t4, %d" % NEAR_SUB_Z,
             "or s2, s2, s4", "or s2, s2, t4",
             "bne s2, zero, 0x80030f60", "nop",
             "PLAIN:"] + ["nop"] * 25
    if os.environ.get("CHI_NEAR_SUB_DBG") == "1":
        # TEST ONLY (isolated roots): no screen pre-filter; after the depth transform the 4 SZ values sit in
        # s2 s3 s4 t0 while a dummy store to 0x80011920 runs, so a RAM-write trace logs them with t1 / a1 per quad
        i0 = world.index("sll t0, t1, 2"); i1 = world.index("lw t5, 0x74(v1)")
        world[i0:i1 + 1] = ["lw t5, 0x74(v1)"]
        j0 = world.index("sltiu s2, s2, %d" % NEAR_SUB_Z); j1 = world.index("bne s2, zero, 0x80030f60")
        world[j0:j1] = [MF("s2", 16), MF("s3", 17), MF("s4", 18), MF("t0", 19), "lui t4, 0x8001", "sw t1, 0x1920(t4)",
                        "sltiu s2, s2, %d" % NEAR_SUB_Z, "sltiu s3, s3, %d" % NEAR_SUB_Z, "sltiu s4, s4, %d" % NEAR_SUB_Z,
                        "sltiu t0, t0, %d" % NEAR_SUB_Z, "or s2, s2, s3", "or s2, s2, s4", "or s2, s2, t0"]
        k = world.index(MF("s2", 17)); world[k:k + 3] = []       # the early SZ reads (the debug block reads all four)
    tile = ["TCAVE:", "slti v0, a3, 0x7d0", "bne v0, zero, TNEAR", "lw v1, 0x1124(gp)",
            "lhu v0, 8(a2)", "andi v1, v1, 2", "beq v1, zero, TMID", "addiu v0, v0, 100",
            "slt v0, a3, v0", "bne v0, zero, TNEAR",              # depth < radius + 100 (only big tiles reach it
            "TMID:", "lui a1, 9", "j 0x80027534", "lw a1, 0x7530(a1)",   # below the 2300 entry band); delay harmless
            "TNEAR:", "jal 0x800287a4", "move a1, a3", "j 0x8002757c", "addiu s1, s1, 1"]
    lines = world + tile
    words = asm(c, lines)
    labels, pc = {}, c
    for ln in lines:
        if ln.endswith(":"):
            labels[ln[:-1]] = pc
        else:
            pc += 4
    k0 = (labels["PLAIN"] - c) // 4
    words[k0:k0 + 25] = plain
    assert c + 4 * len(words) <= NEAR_SUB_CAVE_END, "cave overflow: %d words" % len(words)
    return words, labels


def near_sub_patches(exe_path):
    if os.environ.get("CHI_NEAR_SUB") != "1":        # C45 not accepted yet (16.10.): opt-in, isolated test roots only
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    words, lab = _near_sub_code(img, base)
    if img[NEAR_SUB_CAVE - base: NEAR_SUB_CAVE - base + 13] != b"SetGraphDebug" or img[0x80011A98 - base: 0x80011AA3 - base] != b"GPU timeout":
        raise RuntimeError("near-sub cave: unexpected bytes at %08X" % NEAR_SUB_CAVE)
    wq = lab["WQ"] & 0x1FFFFFFF                       # the table holds KUSEG addresses (0x0003056C)
    out = [(0x8002D534, 0x3C020003, asm(0x8002D534, ["lui v0, 0x%x" % (wq >> 16)])[0],
            "C45: quad handler table entry -> near-sub WQ (cave)"),
           (0x8002D538, 0x2442056C, asm(0x8002D538, ["addiu v0, v0, 0x%x" % (wq & 0xFFFF)])[0], "C45: (low half)"),
           (0x80027518, 0x28E207D0, asm(0x80027518, ["slti v0, a3, 0x8fc"])[0],
            "C45: tile near band: depth < 2300 goes to the cave"),
           (0x80027524, 0x0C00A1E9, asm(0x80027524, ["j 0x%08x" % lab["TCAVE"]])[0], "C45: tile near routine via the cave")]
    # 3. Sub-pieces (0x80030C20, every subdivided world quad): a piece is dropped when its avg sz / 2 < 0x20 + NEAR_PIECE
    #    (gp+0x113C = 0x800978AC, no exe xrefs; 0 = D1's 0x20, the plugin sets Driver 2's value), as Driver 2 drops
    #    its too-near pieces; the original lui at 0x80030CD4 becomes the branch delay slot.
    out += [(0x80030CC0, 0x001188C3, asm(0x80030CC0, ["lw at, 0x113c(gp)"])[0], "C45: piece near limit: lw at, NEAR_PIECE"),
            (0x80030CC4, 0x24010020, 0x001188C3, "C45: sra s1, s1, 3"),
            (0x80030CC8, 0x02210822, asm(0x80030CC8, ["addiu at, at, 0x20"])[0], "C45: addiu at, at, 0x20"),
            (0x80030CCC, 0x0420007B, 0x02210822, "C45: sub at, s1, at"),
            (0x80030CD0, 0x00000000, asm(0x80030CD0, ["bltz at, 0x80030ebc"])[0], "C45: bltz at, drop (delay: the lui)")]
    assert (wq & 0xFFFF) < 0x8000
    for pc, old, _new, _n in out:
        if word(pc) != old:
            raise RuntimeError("unexpected word at %08X" % pc)
    out += [(NEAR_SUB_CAVE + 4 * k, word(NEAR_SUB_CAVE + 4 * k), w, "C45 near-sub cave %d" % k) for k, w in enumerate(words)]
    return out


# --- C67 affine facade seams (Infrastructure 16.10.; Polish NOTES "C7 round 2 + C67") ---------------------------------
# Textured quads flagged 0x40 / 0x60 (Chicago's facades, C40 default) always take Driver 1's light handler
# (handler table entry 0x9C, set at 0x8002D564/68: 0x80030718), a fixed 2 x 2 split, so a tall facade near the camera
# shows the affine kink between the triangles of each piece, while far ones pay for a split they don't need. In a
# Driver 2 city (D2_PLANES gp+0x1110 != 0) the entry now goes to cave LQ, Driver 2's own rule (REDRIVER2 draw.c,
# n == 1): SZ of the 4 corners (GTE, the object's matrix is loaded); diff = max - min; diff * 4 <= minZ - C67_NEAR ->
# the plain handler 0x8003056C (no split); else minZ - C67_FINE < diff * 2 -> the 4 x 4 handler 0x80030F60, else the
# original 2 x 2. Driver 1 cities: straight to 0x80030718. Uses t0 t3 t4 t5 s2 s3 (free at a handler entry; t6 t8 t9
# s1 are the caller's and saved by the handlers). Cave: the libgpu debug strings 0x80011924.. (NEAR_SUB's cave; the
# two groups are exclusive, NEAR_SUB stays an opt-in experiment). CHI_C67=0 = off.
C67_NEAR = int(os.environ.get("CHI_C67_NEAR", "350"))
C67_PX = int(os.environ.get("CHI_C67_PX", "96"))          # round 2: a quad this big on screen is always split (0 = off)
C67_FINE = int(os.environ.get("CHI_C67_FINE", "0"))       # D2: 150; 0 keeps fps_drop_2 at its baseline (16.10.)


def _c67_code():
    LW = lambda rt, off, base: ".word 0x%08x" % ((0x32 << 26) | (REG[base] << 21) | (rt << 16) | (off & 0xFFFF))
    MF = lambda rt, rd: ".word 0x%08x" % (0x48000000 | (REG[rt] << 16) | (rd << 11))
    RTPT, RTPS, NCLIP = ".word 0x4a280030", ".word 0x4a180001", ".word 0x4b400006"
    return ["LQ:", "lw t0, 0x1110(gp)", "lw t5, 0x74(v1)", "beq t0, zero, 0x80030718", "sll t0, t1, 3",
            "andi t0, t0, 0x7f8", "addu t0, t0, t5", LW(0, 0, "t0"), LW(1, 4, "t0"),
            "srl t0, t1, 5", "andi t0, t0, 0x7f8", "addu t0, t0, t5", LW(2, 0, "t0"), LW(3, 4, "t0"),
            "srl t0, t1, 13", "andi t0, t0, 0x7f8", "addu t0, t0, t5", LW(4, 0, "t0"), LW(5, 4, "t0"),
            "srl t0, t1, 21", "andi t0, t0, 0x7f8", RTPT, "addu t0, t0, t5",
            MF("s2", 17), MF("s3", 18), MF("t4", 19), LW(0, 0, "t0"), LW(1, 4, "t0"),
            # C70: Driver 2 draws a quad only when it faces the camera (draw.c: NCLIP of the first three corners > 0);
            # Driver 1 only culls whole polygon groups, so back faces of the quay wall strips (below the road, facing
            # the water) were drawn over the road at the car. NCLIP <= C70_SIGN... -> return without drawing.
        ] + ([NCLIP, MF("t3", 24), "nop", "blez t3, LQBACK" if C70_CULL > 0 else "bgez t3, LQBACK", "nop"] if C70_CULL else []) + [
            # the projected corners go into the screen cache (v1 + 0x1F0 + 4 * index), so the plain handler draws
            # them right even for vertices the renderer did not transform (index >= tri_verts of a near object)
            MF("t3", 12), "sll t5, t1, 2", "andi t5, t5, 0x3fc", "addu t5, t5, v1", "sw t3, 0x1f0(t5)",
            MF("t3", 13), "srl t5, t1, 6", "andi t5, t5, 0x3fc", "addu t5, t5, v1", "sw t3, 0x1f0(t5)",
            MF("t3", 14), "srl t5, t1, 14", "andi t5, t5, 0x3fc", "addu t5, t5, v1", "sw t3, 0x1f0(t5)",
            RTPS, "srl t5, t1, 22", "andi t5, t5, 0x3fc", "addu t5, t5, v1", MF("t3", 14), "sw t3, 0x1f0(t5)",
            "move t0, s2",                                     # t0 = min, s2 = max over s2 s3 t4 t5
            "slt t3, s3, t0", "beq t3, zero, LQ1", "slt t3, s2, s3", "move t0, s3",
            "LQ1:", "beq t3, zero, LQ2", "nop", "move s2, s3",
            "LQ2:", MF("t5", 19), "slt t3, t4, t0", "beq t3, zero, LQ3", "slt t3, s2, t4", "move t0, t4",
            "LQ3:", "beq t3, zero, LQ4", "slt t3, t5, t0", "move s2, t4",
            "LQ4:", "beq t3, zero, LQ5", "slt t3, s2, t5", "move t0, t5",
            "LQ5:", "beq t3, zero, LQ6", "nop", "move s2, t5",
            "LQ6:", "subu s2, s2, t0", "sll s3, s2, 2", "addiu t3, t0, %d" % -C67_NEAR, "slt t3, t3, s3",
            "bne t3, zero, LQSUB", "sll s3, s2, 1"] + ([
            # C67 round 2: a quad big on screen is split even with a small depth spread (affine kinks on facades
            # that span ~100+ px): plain only when the v1-v3 diagonal |dx| + |dy| < C67_PX (GTE SXY0 / SXY2 after
            # the RTPS = corners 1 and 3)
            MF("t3", 12), MF("t5", 14), "nop",
            "sll s3, t3, 16", "sra s3, s3, 16", "sll t4, t5, 16", "sra t4, t4, 16", "subu s3, s3, t4",
            "sra t4, s3, 31", "xor s3, s3, t4", "subu s3, s3, t4",
            "sra t3, t3, 16", "sra t5, t5, 16", "subu t3, t3, t5", "sra t4, t3, 31", "xor t3, t3, t4", "subu t3, t3, t4",
            "addu s3, s3, t3", "sltiu t3, s3, %d" % C67_PX] if C67_PX else ["addiu t3, zero, 1"]) + [
            "bne t3, zero, LQPLAIN", "sll s3, s2, 1",
            "LQSUB:", "addiu t3, t0, %d" % -C67_FINE, "slt t3, t3, s3", "bne t3, zero, 0x80030f60", "nop",
            "j 0x80030718", "nop",
            "LQPLAIN:", "j 0x8003056c", "nop"] + (["LQBACK:", "jr ra", "nop"] if C70_CULL else [])


# --- C70 near-camera strips (Infrastructure 16.10.) -------------------------------------------------------------------
# The quay's long wall strips (models 1114/1115, 0x60, up to 9462 units) pass beside and behind the camera; through C67
# they take the 4 x 4 handler, but a piece with a corner behind the camera (GTE SZ clamped to 0) is still drawn, as a
# stretched grey face at/under the car. Driver 2 drops such sub-quads (draw.c: OTZ / nclip). The piece routine's drop
# test (0x80030CC0..D0: avg sz / 2 < 0x20 -> skip) now calls PCAVE (after LQ in the same cave): the same test, and in
# a Driver 2 city also "any of the piece's 4 grid corners has SZ < C70_NEAR" -> skip. ra is kept in s4 around the call
# (s4 is written before its next read in the routine). CHI_C70=0 = off.
C70_NEAR = int(os.environ.get("CHI_C70_NEAR", "32"))
C70_CULL = int(os.environ.get("CHI_C70_CULL", "0"))      # TEST ONLY (16.10.: culled railings): 1 = draw only NCLIP > 0 (Driver 2), -1 = only < 0, 0 = off


def _c70_code():
    return ["PCAVE:", "sra s1, s1, 3", "slti at, s1, 0x20", "bne at, zero, PRET", "lw t3, 0x1110(gp)", "nop",
            "beq t3, zero, PRET", "lw t3, -4(t1)", "addiu s1, zero, 0",
            "PL:", ".word 0x%08x" % ((17 << 21) | (11 << 16) | (1 << 11) | 6), "andi at, at, 0x3e", "sll at, at, 2", "addu at, at, v1", "lw at, 0xe8(at)",
            "addiu s1, s1, 5", "slti at, at, %d" % C70_NEAR, "bne at, zero, PRET", "nop",
            "slti at, s1, 20", "bne at, zero, PL", "nop",
            "PRET:", "jr ra", "nop"]


# --- C42 engine step: Driver 2 player cars (damage rule, damage rows, collision box) -------------------------
# (Infrastructure 17.10.; design in NOTES "C42 engine step".) All gated by main-RAM words the plugin writes only while
# a car set 4 level with Driver 2 player cars is loaded; 0 everywhere else = Driver 1's own behaviour.
#  - DentCar 0x8003E6A0, UV damage per polygon: the player's clamp (3) and shift (<< 6 per stage) come from
#    3 ^ PDMG and 6 ^ (PDMG >> 1) (PDMG = 0x80093380 = gp-0x33F0; 2 = Driver 2 player cars take the AI rule: one stage,
#    +128 = their damage twins; 0 = Driver 1's +64 x 3 stages).
#    Words: 0x80093380.. inside a 3144-byte zero block of the exe image (0x80093378..0x80093FC0: no xrefs, no pointer
#    formation into it, zero in all 71 RAM dumps). NOT free: 0x80097860..0x80097893 (a buffer, non-zero in 17 dumps) and
#    0x800988C8..0x80098977 (the felony event tables, FUN_00063C60 / FUN_000650E4: word k = event k's (counter, threshold);
#    the first C42E draft used events 2-5 there).
#  - player zone rows: entry 4 of the player verts / polys tables (0x8008A6CC / 0x8008A70C, data words) is set by the
#    plugin to its "car tables" block in mod memory (Driver 2 rows for choices 0..3, or Driver 1's copied from DTL for a
#    car set 4 level with Driver 1 player cars); no exe patch (0x9F082310 is the FPS overlay's block).
#  - collision box: Driver 1 uses one box for every car (car-car 0x80067C9C: half 186 x 90 x 520, 162 x 468 variant;
#    scenery 0x8003FF0C: 169 / 138 x 520; broad phase 0x8001FAFC: rotated 209 / 585 + 90). Driver 2 civilians x1.32
#    are within 8 % of that (170-183 x 110-115 x 495-523), its player cars are not (fire engine 263 x 236 x 891):
#    the player car (car index 0) takes half width / length PBX / PBZ (0x80093384 / 88) car-car (height stays 90) and
#    PBS / PBZ (0x8009338C low half) scenery when PBX / PBS != 0; the broad-phase margin is 90 + the high half of PBS
#    for all cars (the player's extra reach over Driver 1's 585 / 209; 0 for Driver 2 cars of Driver 1's size).
C42E_GP = {"PDMG": -0x33F0, "PBX": -0x33EC, "PBZ": -0x33E8, "PBS": -0x33E4}     # 0x80093380..0x8009338C


def c42e_patches(exe_path):
    if os.environ.get("CHI_C42E") == "0":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    g = C42E_GP
    expect = {0x8003EA1C: 0x11E00007, 0x8003EA88: 0x11E00004, 0x80067D60: 0x9063012E, 0x8001FBA8: 0x2468005A,
              0x8001FC0C: 0x2463005A, 0x8004006C: 0x24020208,
              0x8003FFAC: 0x8E420018, 0x80040020: 0x8E430040}
    for a, w in expect.items():
        if word(a) != w:
            raise RuntimeError("C42E: unexpected word %08X at %08X" % (word(a), a))
    out = []
    # (DentCar clamp / shift: c42d_patches since C42 r3)
    # car-car box (FUN_00067C9C loop body): copies without load-delay nops, then the original box choice, then the player box
    out += rewrite(exe_path, 0x80067CD0, asm(0x80067CD0, [
        "lh v0, 4(v1)", "lh t2, 0xa(v1)", "lh t3, 0x10(v1)", "lh t4, 6(v1)",
        "sw v0, 0(a1)", "sw t2, 4(a1)", "sw t3, 8(a1)", "sw t4, 0x20(a1)",
        "lh v0, 0xc(v1)", "lh t2, 0x12(v1)", "lh t3, 8(v1)", "lh t4, 0xe(v1)",
        "sw v0, 0x24(a1)", "sw t2, 0x28(a1)", "sw t3, 0x10(a1)", "sw t4, 0x14(a1)",
        "lh v0, 0x14(v1)", "lw t2, 0x18(v1)", "lw t3, 0x1c(v1)", "lw t4, 0x20(v1)",
        "sw v0, 0x18(a1)", "sw t2, 0x30(a1)", "sw t3, 0x34(a1)", "sw t4, 0x38(a1)",
        "move t5, v1",
        "lbu v1, 0x12e(v1)", "addiu v0, zero, 1", "bne v1, v0, PBA", "addiu v0, zero, 0xba",
        "lbu v0, 0(a2)", "nop", "beq v0, zero, PBA", "addiu v0, zero, 0xba",
        "lbu v0, 0x12e(a2)", "nop", "beq v0, v1, PBA0", "addiu v0, zero, 0xa2",
        "sw v0, 0x40(a1)", "j PZ", "addiu v0, zero, 0x1d4",
        "PBA0:", "addiu v0, zero, 0xba",
        "PBA:", "sw v0, 0x40(a1)", "addiu v0, zero, 0x208",
        "PZ:", "sw v0, 0x44(a1)", "addiu v0, zero, 0x5a", "sw v0, 0x48(a1)",
        # R33: the player / special box choice lives in BOXCAVE (c42m, LoadCosmetics' dead space)
        "j %#x" % C42B_CAVE, "nop"], 0x80067DB4), "C42E: car-car box")
    # broad phase margin 90 + PBS >> 16
    # C40 lever 1 (24.10.): the margin from each car's OWN matrix pad (car + 0x16 = -0xB6(a2), written by the plugin: the
    # player's / the special's reach, 0 = Driver 1) instead of PBS high half for every car (every traffic pair ran the SAT).
    # CHI_C40M=0: the old shared margin.
    bm = ["lh t2, -0xb6(a2)"] if os.environ.get("CHI_C40M", "1") != "0" else ["lh t2, %d(gp)" % (g["PBS"] + 2)]
    out += [(0x8001FB70, word(0x8001FB70), asm(0x8001FB70, bm)[0], "C42E: broad margin load (C40: per-car pad)"),
            (0x8001FB94, word(0x8001FB94), asm(0x8001FB94, ["addiu t2, t2, 0x5a"])[0], "C42E: broad margin + 90"),
            (0x8001FBA8, word(0x8001FBA8), asm(0x8001FBA8, ["addu t0, v1, t2"])[0], "C42E: broad x margin"),
            (0x8001FC0C, word(0x8001FC0C), asm(0x8001FC0C, ["addu v1, v1, t2"])[0], "C42E: broad z margin")]
    # scenery box (FUN_0003FF0C): shared path compacted (+ car index, PBS, PBZ), non-0x19 path with the player box
    out += rewrite(exe_path, 0x8003FFAC, asm(0x8003FFAC, [
        "lw v0, 0x18(s2)", "lui v1, 0xb", "sw v0, 0x20(sp)", "sw v0, 0x70c4(v1)",
        "lw v0, 0x20(s2)", "addiu a0, v1, 0x70c4", "sw v0, 0x28(sp)", "sw v0, 8(a0)",
        "lw v0, 0xf8(s2)", "lbu t4, 0(s2)", "sw v0, 0x40(a0)",
        "lh t5, %d(gp)" % g["PBS"], "lw t6, %d(gp)" % g["PBZ"], "sltu t4, zero, t4", "addiu t4, t4, -1"], 0x8003FFE8),
        "C42E: scenery shared")
    out += rewrite(exe_path, 0x80040020, asm(0x80040020, [
        "lw v1, 0x40(s2)", "lw v0, 0x48(s2)", "lw a1, 0x18(s2)",
        "addiu v1, v1, 0x800", "sra v1, v1, 12", "sw v1, 0x30(a0)", "addu a1, a1, v1", "sw a1, 0x18(s2)",
        "lw a1, 0x20(s2)", "addiu v0, v0, 0x800", "sra v0, v0, 12", "sw v0, 0x38(a0)", "addu a1, a1, v0", "sw a1, 0x20(s2)",
        "lbu v1, 0x12e(s2)", "and t5, t5, t4", "addiu v0, zero, 0x208", "xori v1, v1, 1",
        "bne v1, zero, S1", "addiu a1, zero, 0xa9", "addiu a1, zero, 0x8a",
        "S1:", "beq t5, zero, S2", "nop", "move a1, t5", "move v0, t6",
        "S2:", "sw v0, 0x44(a0)", "sw a1, 0x48(a0)"], 0x8004008C), "C42E: scenery box")
    return [o for o in out if o[1] != o[2]]


# --- C66: car polygons through the camera (Infrastructure 17.10.) -----------------------------------------------------
# A car right behind / under the chase camera (a cop ramming the player) had vertices behind the camera: RTPT saturates
# them and the car drawers (triangles 0x8003DF94, quads 0x8003E244) drew huge garbled polygons over the bottom of the
# screen (no near test in Driver 1's car code). Now the GTE FLAG of the RTPT (bit 31: SZ / divide / SX-SY saturation)
# rejects the polygon like a back face, masked by NEARCULL (0x80093390, plugin: 0x80000000 while Chicago is loaded,
# 0 = Driver 1's behaviour). The FLAG is read before NCLIP (which resets it); the quad drawer keeps the mask in fp
# (saved by its prologue), the triangle drawer loads it per polygon into the free load-delay slot.
NEARCULL_GP = -0x33E0


def c66_patches(exe_path):
    if os.environ.get("CHI_C66") == "0":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    expect = {0x8003E0A0: 0x4B400006, 0x8003E0A4: 0, 0x8003E0B0: 0, 0x8003E0C8: 0, 0x8003E0D8: 0, 0x8003E0E0: 0,
              0x8003E2C8: 0, 0x8003E35C: 0x4B400006, 0x8003E388: 0, 0x8003E394: 0, 0x8003E398: 0, 0x8003E39C: 0x4A180001}
    for a, w in expect.items():
        if word(a) != w:
            raise RuntimeError("C66: unexpected word %08X at %08X" % (word(a), a))
    W = lambda a: ".word %#x" % word(a)
    out = []
    tri = {0x8003E0A0: ".word 0x4841f800", 0x8003E0A4: ".word 0x4b400006", 0x8003E0B0: "lw v1, %d(gp)" % NEARCULL_GP,
           0x8003E0C8: "and at, at, v1", 0x8003E0D8: "bltz at, 0x8003e204", 0x8003E0DC: "nop", 0x8003E0E0: "bltz v0, 0x8003e204"}
    for a, ln in tri.items():
        out.append((a, word(a), asm(a, [ln])[0], "C66: car triangle near test"))
    out.append((0x8003E2C8, word(0x8003E2C8), asm(0x8003E2C8, ["lw fp, %d(gp)" % NEARCULL_GP])[0], "C66: car quads: mask in fp"))
    quad = asm(0x8003E35C, [
        ".word 0x4843f800",                       # cfc2 v1, FLAG (of the RTPT)
        ".word 0x4b400006",                       # NCLIP
        W(0x8003E360), W(0x8003E364), W(0x8003E368),   # swc2 SXY0..2 -> prim
        W(0x8003E36C),                            # mfc2 t7, MAC0
        "beq s1, zero, QA",
        W(0x8003E374),                            # addiu v0, t1, 0x28
        W(0x8003E378), W(0x8003E37C), W(0x8003E380),
        "QA:", "and v1, v1, fp",
        W(0x8003E38C), W(0x8003E390),             # lwc2 VXY0 / VZ0 of the 4th vertex
        "or t7, t7, v1",
        "bltz t7, 0x8003e500",
        ".word 0x4a180001"], 0x8003E3A0)          # RTPS (delay slot; harmless when skipped)
    for k, w in enumerate(quad):
        a = 0x8003E35C + 4 * k
        if word(a) != w:
            out.append((a, word(a), w, "C66: car quad near test %d" % k))
    return out


# --- C42 r3: wheel size per car (Infrastructure 17.10.) --------------------------------------------------------------
# DrawCarWheels (0x8003B208) rotates the shared wheel models' rim vertices at a fixed radius 101 (x 0x65 as shift-adds,
# 4 sites). The sites now multiply by 101 + WHEEL_RIM (0x80093394 = gp-0x33DC, zero block; the plugin's DrawCarWheels
# entry hook writes the car's rim - 101 together with the tread / hub vertices; 0 = Driver 1's 101).
WHEEL_RIM_GP = -0x33DC


def c42w_patches(exe_path):
    if os.environ.get("CHI_C42W") == "0":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    out = []
    for a, src, dst, first in ((0x8003B3CC, "a1", "t2", True), (0x8003B3E8, "v1", "t3", False),
                               (0x8003B488, "a2", "t2", True), (0x8003B4A4, "v1", "t3", False)):
        if word(a + 24) >> 16 != 0x0002 or word(a + 24) & 0x7FF != (0xC << 6) | 3:
            raise RuntimeError("C42W: unexpected rim site at %08X" % a)
        lines = (["lw t9, %d(gp)" % WHEEL_RIM_GP, "nop", "addiu t9, t9, 0x65"] if first else []) + \
                ["mult %s, t9" % src, "mflo v0", "sra %s, v0, 12" % dst]
        out += rewrite(exe_path, a, asm(a, lines, a + 28), "C42W: wheel rim radius")
    return out


# --- C42 r3: Driver 2's DentCar texture rule (Infrastructure 17.10.) -----------------------------------------------------
# D2 (denting.c): level = clamp(sum >> 10, 0, 2), offset = ((L^1) ^ ((L^1)|level)) * 64 with L = the polygon's damage kind
# (0 body: clean at level 1, its +128 twin at level 2; 1 lights: +64 / +128). Driver 1 shifted every damaged polygon of an
# AI car by +128 at level 1 (cap 1): Driver 2 bodies showed their wreck texture at the first scratch and polygons without a
# twin showed neighbours. RULEB (0x80093398) = 1 with a level table (plugin): AI cap 2, the shift loop calls DCAVE, which
# reads L from LTABC (AI rows by resident model, 0x8009339C) or LTABP (player rows by choice, 0x800933A0). RULEB 0 =
# Driver 1's caps / shifts (player cap 3 ^ PDMG, shift 6 ^ (PDMG >> 1), AI 1 / 7). DCAVE lives in the exe's zero block
# (two pieces in unreferenced library version strings, seeded: DCAVE1 = "$Id: intr.c ..." 0x80011BB8 (13 words), DCAVE2 =
# "$Id: bios.c ..." 0x800123E0 (14 words); the exe's zero block 0x80093378.. is cleared at boot, no code there).
# RULEB (0x80093398) = 1: AI cap 2 (player cap 3 ^ PDMG, PDMG 1); LTAB (0x8009339C) = the plugin's 1 KB table of (L ^ 1) per
# polygon, row 0 = the player's choice, rows 1..3 = AI resident models; 0 = Driver 1's shifts (AI 7, player 6).
RULEB_GP, LTAB_GP = -0x33D8, -0x33D4
DCAVE1, DCAVE2 = 0x80011BB8, 0x800123E0


def c42d_patches(exe_path):
    if os.environ.get("CHI_C42D") == "0":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    if img[DCAVE1 - base: DCAVE1 - base + 11] != b"$Id: intr.c" or img[DCAVE2 - base: DCAVE2 - base + 11] != b"$Id: bios.c":
        raise RuntimeError("C42D: unexpected bytes at the version-string caves")
    g = C42E_GP
    out = []
    out += rewrite(exe_path, 0x8003EA1C, asm(0x8003EA1C, [
        "sb v0, 0(v1)", "andi v0, v0, 0xff", "lw at, %d(gp)" % RULEB_GP, "bne t7, zero, L1", "addiu at, at, 1",
        "lw at, %d(gp)" % g["PDMG"], "nop", "xori at, at, 3",
        "L1:", "sltu v0, at, v0", "beq v0, zero, 0x8003ea50", "nop", "sb at, 0(v1)"], 0x8003EA50), "C42D: DentCar clamp")
    out += rewrite(exe_path, 0x8003EA88, asm(0x8003EA88, ["move t9, ra", "jal %#x" % DCAVE1, "lbu v0, 0(v1)",
                                                        "move ra, t9"], 0x8003EAA8),   # DentCar keeps ra in a register only
                   "C42D: DentCar shift via DCAVE")
    c1 = asm(DCAVE1, ["lw at, %d(gp)" % LTAB_GP, "sltu a1, zero, t7", "beq at, zero, D1", "addiu a2, a1, 6",
                      "j %#x" % DCAVE2, "nop", "D1:", "jr ra", "sllv v0, v0, a2"], DCAVE1 + 52)
    if os.environ.get("CHI_Q45B_EXE", "0") == "1":   # Q45 B +64 (23.10.; withdrawn: Polish packs D2's u+128 twins, normal rule)
        # Q45 B (user 23.10.): the special (AI row 5) keeps its damage copies 64 rows below the clean textures (split slot,
        # Polish SPECDMG) -> shift 5 instead of 6 for row 5 (+64 where Driver 2 has +128); rows 0-4 unchanged. Row 5 is all
        # 3 (no shift) unless the level ships .spd.bin rows (plugin spd_write_row5), so nothing changes without them.
        c2 = asm(DCAVE2, ["subu a1, zero, a1", "and a1, a1, s0", "sll a1, a1, 8", "xori a2, a1, 0x500", "sltiu a2, a2, 1",
                          "addu at, at, a1", "addu at, at, a0", "lbu a1, 0(at)", "subu a2, zero, a2", "addiu a2, a2, 6",
                          "or v0, a1, v0", "xor v0, a1, v0", "jr ra", "sllv v0, v0, a2"], DCAVE2 + 56)
    else:
        c2 = asm(DCAVE2, ["subu a1, zero, a1", "and a1, a1, s0", "sll a1, a1, 8", "addu at, at, a1", "addu at, at, a0",
                          "lbu a1, 0(at)", "addiu a2, zero, 6", "or v0, a1, v0", "xor v0, a1, v0", "jr ra",
                          "sllv v0, v0, a2"], DCAVE2 + 56)
    out += [(DCAVE1 + 4 * k, word(DCAVE1 + 4 * k), w, "C42D: DCAVE1 %d" % k) for k, w in enumerate(c1)]
    out += [(DCAVE2 + 4 * k, word(DCAVE2 + 4 * k), w, "C42D: DCAVE2 %d" % k) for k, w in enumerate(c2)]
    return [o for o in out if o[1] != o[2]]


def c42d_seeds():
    return [DCAVE1, DCAVE2]


# --- C42 r3 (b): six resident car models like Driver 2 (Infrastructure 17.10.) --------------------------------------------
# Driver 1 keeps 4 resident car models (0 player, 1 cop, 2-3 civilians; lump slots 5+choice, 0, 1, 2) in 4-entry tables:
# cosmetics 0x8009AF04 (4 x 100 B, then 0x8009B094 / the car array), damage / low model pointers 0x800A1AD0 / 0x800A1AE0
# (4 each: damage[4..5] = low[0..1]), polygon groups 0x800AF5B0 (4 x 0x3C, then the car matrices), low-model UV rows
# 0x800B6DBC (4 x 50 B, then the hubcap data); the car draw masks the model with & 3. Driver 2 (PSX) keeps 5 + the player.
# This group gives 6: 0 player, 1 cop, 2-4 civilians (lump slots 1-3), 5 the special (lump slot 4); the loader already
# loads lump slots 0..4 into entries 1..5 (Driver 1 levels leave slots 3-4 empty, so their models 4-5 stay null and
# nothing changes for them). The tables move to the old model-table area (free since the model table moved; same lui
# 0x800A as the cosmetics: only the low halves change): COS 0x800A0E20 (6 x 100), STRUCTS 0x800A1078 (6 x 0x3C),
# DAMG 0x800A11E0 / LOWM 0x800A11F8 (6 words each), LOWUV 0x800A1210 (6 x 50 + slack; stays zero: Driver 2 low models
# have up to 108 polygons, the draw reads past 50). Code: the group builder FUN_0003BBF8 builds 6 groups in a loop
# (flags as Driver 1: player a2 = 1 / stack 1; palettised a3 = 1 for models 2-3 only: models 4-5 draw their own CLUTs,
# Driver 2 gives model 0 / specials palette 0); FUN_0003BDC8's polygon buffer base and cap come from PCAVE ("Library
# Programs" copyright text 0x800932C8, seeded): PBUF / PCAP (0x800933A0 / A4, plugin) or Driver 1's 0x800AB728 / 666 when
# PBUF is 0; the cap sits in $at (unused by the builder). Low UV init FUN_0003E540: models 1..5, skips null low models,
# clears at most 50 bytes. LoadCosmetics: 6 rows (entry 0 = base + choice, entries 1..5 = base + 5..9; car set 4's 10
# rows at 0x800A16A0..0x800A1A88). Civilian spawn (5 sites, 2 + r % 2): model = SPAWN[r & 15] (16 bytes in the same
# copyright text, 0x800932B8, Driver 1's {2, 3} x 8; the plugin writes Driver 2's list for car set 4). The car draw masks
# with & 7. PS1-native (guest code + fixed RAM); the polygon buffer for 6 Driver 2 models (~900 entries) lives in mod
# memory on the PC (M8: needs 22 KB of PS1 RAM, host-only list).
C42M_COS, C42M_STRUCTS, C42M_DAMG, C42M_LOWM, C42M_LOWUV = 0x800A0E20, 0x800A1078, 0x800A11E0, 0x800A11F8, 0x800A1210
C42B_SPBX_GP, C42B_SPBZ_GP = -0x33C4, -0x33C0     # R33: 0x800933AC / B0, the special's car-car box (plugin)
C42B_SPBO_GP = -0x33BC                            # R34: 0x800933B4, the special's box offset along its z axis (plugin)
C42B_CAVE = 0x80052704                            # R33: BOXCAVE inside the rewritten LoadCosmetics (seeded)
C42M_SPAWN, C42M_PCAVE = 0x800932B8, 0x800932C8
C42M_PBUF_GP, C42M_PCAP_GP = -0x33D0, -0x33CC                     # 0x800933A0 / 0x800933A4 (intr stack bottom, plugin)
C42M_SPAWN_SITES = [(0x80015E5C, "v1", "v0", "v1"), (0x80015E84, "v0", "v1", "v0"), (0x800165AC, "v1", "v0", "v0"),
                    (0x80016988, "v1", "v0", "v0"), (0x800169F0, "v1", "v0", "v0")]      # (pc, r, scratch, model)
_MEMOPS = (0x20, 0x21, 0x23, 0x24, 0x25, 0x28, 0x29, 0x2B, 9)


def _lui_uses(img, base, lo, hi, skip=()):
    """(pc, target) of every instruction that forms an address in [lo, hi) from a preceding lui (same register, followed
    through addu index additions, up to 40 instructions); pcs inside `skip` ranges are left out."""
    n = len(img) // 4
    W = lambda i: struct.unpack_from("<I", img, 4 * i)[0]
    out = []
    for i in range(n):
        w = W(i)
        if w >> 26 != 15:
            continue
        rt, hi16 = (w >> 16) & 31, (w & 0xFFFF) << 16
        for j in range(1, 41):
            if i + j >= n:
                break
            v = W(i + j); op = v >> 26; rs = (v >> 21) & 31
            if rs == rt and op in _MEMOPS:
                a = (hi16 + ((v & 0xFFFF) ^ 0x8000) - 0x8000) & 0xFFFFFFFF
                if lo <= (a | 0x80000000) < hi:
                    pc = base + 4 * (i + j)
                    if not any(s0 <= pc < s1 for s0, s1 in skip):
                        out.append((pc, a | 0x80000000))
            dst = None
            if op == 0 and (v & 63) not in (8, 9, 0x18, 0x19, 0x1A, 0x1B, 0x11, 0x13):
                dst = (v >> 11) & 31
            elif op in (3,):
                dst = 31
            elif op in (9, 10, 11, 12, 13, 14, 15, 0x20, 0x21, 0x23, 0x24, 0x25):
                dst = (v >> 16) & 31
            if dst == rt and not (op == 0 and (v & 63) in (0x20, 0x21) and (rs == rt or (v >> 16) & 31 == rt)):
                break
            if op in (2, 3) or (op == 0 and (v & 63) == 8):   # j / jal / jr: its delay slot still counts
                v2 = W(i + j + 1)
                if (v2 >> 21) & 31 == rt and v2 >> 26 in _MEMOPS:
                    a = (hi16 + ((v2 & 0xFFFF) ^ 0x8000) - 0x8000) & 0xFFFFFFFF
                    pc = base + 4 * (i + j + 1)
                    if lo <= (a | 0x80000000) < hi and not any(s0 <= pc < s1 for s0, s1 in skip):
                        out.append((pc, a | 0x80000000))
                break
    return out


def _relo(img, base, pc, old_target, new_target, note):
    w = struct.unpack_from("<I", img, pc - base)[0]
    imm = ((w & 0xFFFF) ^ 0x8000) - 0x8000
    nimm = imm + (new_target - old_target)
    assert -0x8000 <= nimm < 0x8000, hex(pc)
    return (pc, w, (w & 0xFFFF0000) | (nimm & 0xFFFF), note)


def c42m_patches(exe_path):
    if os.environ.get("CHI_C42M") == "0":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    if img[C42M_SPAWN - base: C42M_SPAWN - base + 4] not in (b"Libr", b"ibra", b"brar", b"rary") and \
            b"Library Programs" not in img[C42M_SPAWN - base - 4: C42M_SPAWN - base + 20]:
        raise RuntimeError("C42M: unexpected bytes at the copyright text cave")
    out = []
    lcos = (0x80052684, 0x800527A4)                     # LoadCosmetics copy loops: rewritten below
    # 1. cosmetics: 4 x 100 B -> 6 x 100 B (lo halves only; 0x8009B094 stays)
    uses = _lui_uses(img, base, 0x8009AF04, 0x8009B094, skip=[lcos])
    if len(uses) != 32:
        raise RuntimeError("C42M: %d cosmetics sites (expected 32)" % len(uses))
    out += [_relo(img, base, pc, 0x8009AF04, C42M_COS, "C42M: cosmetics -> COS") for pc, a in uses]
    # 2. damage / low model pointers (the builder's and the low-UV init's sites are rewritten below)
    skip = [(0x8003BBF8, 0x8003BDC8), (0x8003E56C, 0x8003E66C)]
    for lo, new, name, cnt in ((0x800A1AD0, C42M_DAMG, "DAMG", 4), (0x800A1AE0, C42M_LOWM, "LOWM", 3)):
        uses = _lui_uses(img, base, lo, lo + 16, skip=skip)
        if len(uses) != cnt:
            raise RuntimeError("C42M: %d %s sites (expected %d)" % (len(uses), name, cnt))
        out += [_relo(img, base, pc, lo, new, "C42M: %s" % name) for pc, a in uses]
    out.append((0x8005281C, word(0x8005281C), asm(0x8005281C, ["slti v0, a2, 6"])[0], "C42M: loader clears 6 entries"))
    # 3. polygon group structs + low UV rows (hi 0x800B -> 0x800A): the two draw sites, the struct compare
    for pc, reg, tgt, new in ((0x8003A574, "v0", 0x800AF5B0, C42M_STRUCTS), (0x8003AF24, "v0", 0x800AF5B0, C42M_STRUCTS),
                              (0x8003AB64, "v1", 0x800B6DBC, C42M_LOWUV)):
        if word(pc) != asm(pc, ["lui %s, 0xb" % reg])[0] or word(pc + 4) & 0xFFFF != tgt & 0xFFFF:
            raise RuntimeError("C42M: unexpected word at %08X" % pc)
        out.append((pc, word(pc), asm(pc, ["lui %s, 0xa" % reg])[0], "C42M: table hi"))
        out.append((pc + 4, word(pc + 4), (word(pc + 4) & 0xFFFF0000) | (new & 0xFFFF), "C42M: table lo"))
    # 4. the car draw: model & 7
    for pc, old, new in ((0x8003A6A8, "andi s5, a1, 3", "andi s5, a1, 7"), (0x8003AF14, "andi v0, s3, 3", "andi v0, s3, 7")):
        if word(pc) != asm(pc, [old])[0]:
            raise RuntimeError("C42M: unexpected word at %08X" % pc)
        out.append((pc, word(pc), asm(pc, [new])[0], "C42M: car draw model mask"))
    # 5. group builder FUN_0003BBF8: 6 groups, palette halves, the SF cop offset (city 1)
    S, D = C42M_STRUCTS & 0xFFFF, C42M_DAMG & 0xFFFF
    sf_loop = [".word %#x" % word(a) for a in range(0x8003BD30, 0x8003BDA8, 4)]
    if word(0x8003BDA8) != 0x1C80FFE1:
        raise RuntimeError("C42M: unexpected SF loop end")
    lines = [
        "addiu sp, sp, -0x28", "sw s0, 0x18(sp)", "sw s1, 0x1c(sp)", "sw s2, 0x24(sp)", "sw ra, 0x20(sp)",
        "lui s0, 0xa", "addiu s0, s0, %#x" % S, "lui s1, 0xa", "addiu s1, s1, 0x1ab0", "move s2, zero",
        "B1:", "move a0, s0", "lw a1, 0(s1)", "sltiu a2, s2, 1", "addiu at, s2, -2", "sltiu a3, at, 3",
        "jal 0x8003bdc8", "sw a2, 0x10(sp)",
        "addiu s2, s2, 1", "addiu s0, s0, 0x3c", "slti v0, s2, 6", "bne v0, zero, B1", "addiu s1, s1, 4",
        "lui s0, 0xa", "addiu s0, s0, %#x" % S, "lw v0, 4(s0)", "lui a0, 0xffff", "lw v1, 8(v0)", "lw v0, 0xc(v0)",
        "and v1, v1, a0", "and t1, v0, a0", "addiu a3, zero, 6",
        "B2:", "lw v0, 0x30(s0)", "lw a0, 0x34(s0)", "blez v0, B4", "move a1, zero", "addiu a0, a0, 0xc",
        "B3:", "sw v1, -4(a0)", "sw t1, 0(a0)", "lw v0, 0x30(s0)", "addiu a1, a1, 1", "slt v0, a1, v0",
        "bne v0, zero, B3", "addiu a0, a0, 0x18",
        "B4:", "addiu a3, a3, -1", "bgtz a3, B2", "addiu s0, s0, 0x3c",
        "lui v1, 9", "lw v1, 0x6834(v1)", "addiu v0, zero, 1", "bne v1, v0, BEND", "lui v0, 0xa",
        "lw t1, %#x(v0)" % (S + 0x3C + 0x38), "lui v0, 0xa", "lw v0, 0x1ab4(v0)", "lui v1, 0xa", "lw v1, %#x(v1)" % (D + 4),
        "lhu a3, 0xc(v0)", "lw t0, 0x10(v1)", "move v0, a3", "blez v0, BEND", "addiu a3, a3, -1",
        "addiu a2, t0, 4", "addiu a1, t1, 4",
        "B5:"] + sf_loop + ["bgtz a0, B5", ".word %#x" % word(0x8003BDAC),
        "BEND:", "lw ra, 0x20(sp)", "lw s2, 0x24(sp)", "lw s1, 0x1c(sp)", "lw s0, 0x18(sp)", "jr ra", "addiu sp, sp, 0x28"]
    out += rewrite(exe_path, 0x8003BBF8, asm(0x8003BBF8, lines, 0x8003BDC8), "C42M: group builder")
    # 6. FUN_0003BDC8: buffer base + cap from PCAVE (ra kept in t9; t9 is set right after)
    for pc, old in ((0x8003BE34, "lui v0, 0xb"), (0x8003BE38, "addiu a3, v0, -0x48d8"), (0x8003BE40, "addiu t9, v0, 0x7030"),
                    (0x8003BE44, "lui v0, 8"), (0x8003BF60, "slti v0, t2, 0x29a"), (0x8003C5E0, "slti v0, t2, 0x29a")):
        if word(pc) != asm(pc, [old])[0]:
            raise RuntimeError("C42M: unexpected word at %08X" % pc)
    for pc, new in ((0x8003BE34, "move t9, ra"), (0x8003BE38, "jal %#x" % C42M_PCAVE), (0x8003BE40, "move ra, t9"),
                    (0x8003BE44, "addiu t9, v0, 0x7030"), (0x8003BF60, "slt v0, t2, at"), (0x8003C5E0, "slt v0, t2, at")):
        out.append((pc, word(pc), asm(pc, [new])[0], "C42M: polygon buffer via PCAVE"))
    cave = asm(C42M_PCAVE, ["lw a3, %d(gp)" % C42M_PBUF_GP, "lw at, %d(gp)" % C42M_PCAP_GP, "bne a3, zero, PX", "nop",
                            "lui a3, 0xb", "addiu a3, a3, -0x48d8", "addiu at, zero, 0x29a", "PX:", "jr ra", "nop"])
    out += [(C42M_PCAVE + 4 * k, word(C42M_PCAVE + 4 * k), w, "C42M: PCAVE %d" % k) for k, w in enumerate(cave)]
    # 7. low UV init FUN_0003E540 (models 1..5, null-safe, <= 50 bytes per row); the per-city pointer block
    #    0x8003E588..0x8003E5E4 stays in place (C51 patches 0x8003E5A8)
    out += rewrite(exe_path, 0x8003E56C, asm(0x8003E56C, [
        "lui s4, 0xa", "addiu s4, s4, %#x" % (C42M_LOWUV & 0xFFFF), "lui s0, 0xa", "addiu s0, s0, %#x" % (C42M_LOWM & 0xFFFF)],
        0x8003E588), "C42M: low UV init setup")
    lines = [
        "addiu s1, zero, 1", "addiu s3, s4, 0x32",
        "L1:", "sll v0, s1, 2", "addu v0, s0, v0", "lw v0, 0(v0)", "nop", "beq v0, zero, NX", "nop",
        "lhu a1, 0xe(v0)", "nop", "sltiu at, a1, 0x33", "bne at, zero, OK", "move v1, zero", "addiu a1, zero, 0x32",
        "OK:", "beq a1, zero, NX", "nop",
        "L2:", "addu v0, s3, v1", "addiu v1, v1, 1", "slt at, v1, a1", "bne at, zero, L2", "sb zero, 0(v0)",
        "NX:", "addiu s1, s1, 1", "slti at, s1, 6", "bne at, zero, L1", "addiu s3, s3, 0x32", "move a0, zero"]
    if word(0x8003E66C) != asm(0x8003E66C, ["jal 0x8003eb0c"])[0] or word(0x8003E5E4) != 0xAF830C64:
        raise RuntimeError("C42M: unexpected low UV init")
    out += rewrite(exe_path, 0x8003E5E8, asm(0x8003E5E8, lines, 0x8003E66C), "C42M: low UV init loop")
    # 8. LoadCosmetics: 6 rows (a0 = the car set's base row)
    if word(0x80052684) != asm(0x80052684, ["lui v0, 0xa"])[0] or word(0x800527A4) != asm(0x800527A4, ["jal 0x8001ba14"])[0]:
        raise RuntimeError("C42M: unexpected LoadCosmetics")
    lines = ["lui v0, 0xa", "addiu a2, v0, %#x" % (C42M_COS & 0xFFFF), "lui v1, 9", "lw v1, 0x683c(v1)", "move t0, zero",
             "L:", "bne t0, zero, AI", "addu t1, a0, v1", "beq zero, zero, ROW", "nop",
             "AI:", "addiu t1, a0, 4", "addu t1, t1, t0",
             "ROW:", "sll v0, t1, 1", "addu v0, v0, t1", "sll v0, v0, 3", "addu v0, v0, t1", "sll v0, v0, 2",
             "lui at, 8", "addiu at, at, 0x53d8", "addu a1, v0, at", "addiu t2, zero, 0x19",
             "C:", "lw v0, 0(a1)", "addiu a1, a1, 4", "addiu t2, t2, -1", "sw v0, 0(a2)", "bgtz t2, C", "addiu a2, a2, 4",
             "addiu t0, t0, 1", "slti at, t0, 6", "bne at, zero, L", "nop",
             # R33 BOXCAVE (C42B): the car-car box of the player (PBX / PBZ) or of the special, model 5 (SPBX / SPBZ:
             # Driver 2's colBox of the loaded special x 1.32, plugin; 0 = Driver 1's box); entered from c42e's box tail
             "j 0x800527a4", "nop",
             "BOX:", "lui t2, 0x800a", "addiu t2, t2, -0x4f5c", "bne t5, t2, NPB", "lw t3, %d(gp)" % C42E_GP["PBX"],
             "lw t4, %d(gp)" % C42E_GP["PBZ"], "beq zero, zero, SETB", "nop",
             "NPB:", "lbu v0, 2(t5)", "lw t3, %d(gp)" % C42B_SPBX_GP, "xori v0, v0, 5", "bne v0, zero, OUTB",
             "lw t4, %d(gp)" % C42B_SPBZ_GP,
             # R34: Driver 2 centres the box on the body (initOBox: where - R * cog = the drawn body's origin); our body
             # sits at +SPBO along the car's z axis (cog shift) -> box centre (+0x30 / +0x38) += column 2 (+0x10 / +0x18) x SPBO
             ] + ([   # R34 box offset (CHI_R34_BOXOFF=0: without)
             # C86 (23.10.): load-delay safe (v0 was tested / t2 multiplied one instruction after their loads)
             "lw v0, %d(gp)" % C42B_SPBO_GP, "lw t2, 0x10(a1)", "beq v0, zero, SETB", "lw at, 0x30(a1)",
             "mult t2, v0", "mflo t2", "sra t2, t2, 12", "addu at, at, t2", "sw at, 0x30(a1)",
             "lw t2, 0x18(a1)", "lw at, 0x38(a1)", "mult t2, v0", "mflo t2", "sra t2, t2, 12",
             "addu at, at, t2", "sw at, 0x38(a1)"] if os.environ.get("CHI_R34_BOXOFF", "1") != "0" else []) + [
             "SETB:", "beq t3, zero, OUTB", "nop", "sw t3, 0x40(a1)", "sw t4, 0x44(a1)",
             "OUTB:", "j 0x80067db4", "nop"]
    out += rewrite(exe_path, 0x80052684, asm(0x80052684, lines, 0x800527A4), "C42M: LoadCosmetics 6 rows")
    # 9. civilian spawn: model = SPAWN[r & 15]
    for pc, r, x, m in C42M_SPAWN_SITES:
        old = asm(pc, ["srl %s, %s, 31" % (x, r), "addu %s, %s, %s" % (x, r, x), "sra %s, %s, 1" % (x, x),
                       "sll %s, %s, 1" % (x, x), "subu %s, %s, %s" % (m, r, x), "addiu %s, %s, 2" % (m, m)])
        if [word(pc + 4 * k) for k in range(6)] != old:
            raise RuntimeError("C42M: unexpected spawn site %08X" % pc)
        new = asm(pc, ["andi %s, %s, 0xf" % (x, r), "lui at, 0x8009", "addu at, at, %s" % x,
                       "lbu %s, %#x(at)" % (m, C42M_SPAWN & 0xFFFF), "nop", "nop"])
        out += [(pc + 4 * k, old[k], new[k], "C42M: civ spawn model from SPAWN") for k in range(6)]
    out += [(C42M_SPAWN + 4 * k, word(C42M_SPAWN + 4 * k), 0x03020302, "C42M: SPAWN (Driver 1: 2, 3 x 8)") for k in range(4)]
    return [o for o in out if o[1] != o[2]]


def c42m_seeds():
    return [C42M_PCAVE, C42B_CAVE]


# --- R32 (user 'd2 cars 3'): cop light position + civilian palettes (Infrastructure 18.10.) --------------------------------
# Cop lights (FUN_00046000): Driver 1 draws its red / blue bar at fixed model-space spots x = +-"p`P@@P`p"[i] (table
# 0x8008A8D8), y -164, z 15 (its own cop's roof); on Driver 2's cop (lump model 0, roof bar top y -116, x +-33..66, z
# 30..63) that floated ~48 above the roof. COPW (0x800933A8, plugin): high half = y delta (0 = Driver 1), low byte = z
# (plugin: 15 = Driver 1); the plugin also writes the x table (Chicago: 50 at every step = Driver 2's fixed pair, D1's
# bytes elsewhere). Block 0x800460D4..0x800460FC rewritten with gp loads (night flag, CITY-free pause word) to make room.
# Civilian palettes: spawn palette = 1 + r % 4 at 4 sites -> PALT[r & 15] (16 bytes at 0x800932EC, copyright text after
# PCAVE; Driver 1 {1,2,3,4} x 4; the plugin writes 1..5 for car set 4 so Driver 2's 4 colour variants + the base paint
# are all used: palette 5 = CLUT table slot 3, as Driver 1's own city-5 special case).
C42L_COPW_GP = -0x33C8                     # 0x800933A8
C42P_PALT = 0x800932EC
C42P_SITES = [0x80015ED8, 0x800165C8, 0x800169A4, 0x80016A0C]


def c42l_patches(exe_path):
    if os.environ.get("CHI_C42L") == "0":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    old = ["lui v1, 9", "lw v1, 0x6850(v1)", "addiu v0, zero, -0xa4", "sh v0, 0x1a(sp)", "mflo t0", "beq v1, zero, 0x800460f4",
           "sh t0, 0x18(sp)", "addiu a0, zero, 0x32", "lui v0, 9", "lw v0, 0x687c(v0)", "nop"]
    if [word(0x800460D4 + 4 * k) for k in range(11)] != asm(0x800460D4, old):
        raise RuntimeError("C42L: unexpected cop light block")
    for a in (0x80046104, 0x8004611C):
        if word(a) != asm(a, ["addiu v0, zero, 0xf"])[0]:
            raise RuntimeError("C42L: unexpected z site %08X" % a)
    new = ["lw v1, 0xe0(gp)", "lw t1, %d(gp)" % C42L_COPW_GP, "mflo t0", "sra v0, t1, 16", "addiu v0, v0, -0xa4",
           "sh v0, 0x1a(sp)", "beq v1, zero, 0x800460f8", "sh t0, 0x18(sp)", "addiu a0, zero, 0x32", "lw v0, 0x10c(gp)", "nop"]
    out = rewrite(exe_path, 0x800460D4, asm(0x800460D4, new), "C42L: cop light y / z word")
    for a in (0x80046104, 0x8004611C):
        out.append((a, word(a), asm(a, ["andi v0, t1, 0xff"])[0], "C42L: cop light z from COPW"))
    return out


def c42p_patches(exe_path):
    if os.environ.get("CHI_C42P") == "0":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    if b"Entertainment" not in img[C42P_PALT - base - 8: C42P_PALT - base + 16]:
        raise RuntimeError("C42P: unexpected bytes at the PALT cave %r" % img[C42P_PALT - base: C42P_PALT - base + 8])
    out = []
    for pc in C42P_SITES:
        old = asm(pc, ["bgez v1, %#x" % (pc + 12), "move v0, v1", "addiu v0, v1, 3", "sra v0, v0, 2", "sll v0, v0, 2",
                       "subu v0, v1, v0", "addiu v0, v0, 1"])
        if [word(pc + 4 * k) for k in range(7)] != old:
            raise RuntimeError("C42P: unexpected palette site %08X" % pc)
        new = asm(pc, ["andi v0, v1, 0xf", "lui at, 0x8009", "addu at, at, v0", "lbu v0, %#x(at)" % (C42P_PALT & 0xFFFF),
                       "nop", "nop", "nop"])
        out += [(pc + 4 * k, old[k], new[k], "C42P: civ palette from PALT") for k in range(7)]
    out += [(C42P_PALT + 4 * k, word(C42P_PALT + 4 * k), 0x04030201, "C42P: PALT (Driver 1: 1..4 x 4)") for k in range(4)]
    return [o for o in out if o[1] != o[2]]


# --- R35 (user 'd2 cars 7': the player car is faster than in Driver 2) -------------------------------------------------
# Driver 1's pad handler FUN_0001FF24 (player + car 23) sets the thrust (car + 0xF0) to 7200 (0x1C20) when accelerating,
# -7000-ish when braking; Driver 2 (REDRIVER2 handling.c) FIXEDH(powerRatio * 4915) / FIXEDH(powerRatio * rws). Both
# games' wheel forces (thrust vs vel * 12 per wheel) have the same form, so the top speed scales with the thrust: Driver 1
# runs 1.465 x Driver 2 in world units, matching its cities (D2 x 1.38-1.46), but Chicago is D2 x 1.32 -> the player was
# ~11 % too fast for the city. The handler's last block (0x800204CC..0x8002051C: Miami choice 3 thrust x 19/16) becomes a
# general player scale: thrust = (thrust * THRS + 0x800) >> 12 when THRS (0x800933B8, plugin: Chicago's player choice
# = D2 powerRatio * 4915 * 1.32 / 7200, i.e. 3691 for powerRatio 4096) != 0, else the Miami rule as the same multiply
# (19/16 = 4864/4096, (x * 4864 + 0x800) >> 12 == (x * 19 + 8) >> 4 exactly). Brake thrust scales alike (D2 too).
C35T_THRS_GP = -0x33B8                    # 0x800933B8 (zero block)


def c35t_patches(exe_path):
    if os.environ.get("CHI_R35_THRUST", "1") == "0":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    old = asm(0x800204CC, ["bne s5, zero, 0x80020520", "addiu v0, zero, 3", "lui v1, 9", "lw v1, 0x683c(v1)", "nop",
                           "bne v1, v0, 0x80020520", "nop", "lui v0, 9", "lw v0, 0x6834(v0)", "nop",
                           "bne v0, zero, 0x80020520", "nop", "lw v1, 0xf0(s3)", "nop", "sll v0, v1, 2", "addu v0, v0, v1",
                           "sll v0, v0, 2", "subu v0, v0, v1", "addiu v0, v0, 8", "sra v0, v0, 4", "sw v0, 0xf0(s3)"])
    if [word(0x800204CC + 4 * k) for k in range(21)] != old:
        raise RuntimeError("C35T: unexpected thrust block at 0x800204CC")
    new = asm(0x800204CC, ["bne s5, zero, 0x80020520", "lw v1, %d(gp)" % C35T_THRS_GP, "lw v0, 0xf0(s3)",
                           "beq v1, zero, MIA", "nop",
                           "MUL:", "mult v0, v1", "mflo v0", "addiu v0, v0, 0x800", "sra v0, v0, 12",
                           "j 0x80020520", "sw v0, 0xf0(s3)",
                           "MIA:", "lui v1, 9", "lw at, 0x683c(v1)", "lw v1, 0x6834(v1)", "xori at, at, 3",
                           "or at, at, v1", "bne at, zero, 0x80020520", "addiu v1, zero, 4864", "j MUL", "nop"],
               0x80020520)
    return [(0x800204CC + 4 * k, old[k], new[k], "C35T: player thrust scale %d" % k) for k in range(21) if old[k] != new[k]]


# --- C76 (user: diagonal 'cut' lines in Chicago's sky) ---------------------------------------------------------------------
# The dome loop FUN_0004F7C8 draws each quad of a quadrant model through FUN_0004F34C(piece): UVs 0x800BDE40[piece * 8],
# CLUT 0x800BDD20[piece]. Chicago's domes (convert.sky_subdivide) have 48 sub-quads that carry 0x80 | parent piece in
# byte 1 and their own UVs in bytes 8..15. FUN_0004F34C writes the four screen points twice (0x8004F500..F5F8 and again
# 0x8004F604..F6E0, identical values); the redundant second copy is replaced in place by: a polygon with byte 1 bit 7
# takes its UVs from the polygon and the CLUT of piece byte1 & 0x7F (whatever the loop's map index), else the table as
# before. No cave; Driver 1's domes (byte 1 = their page index < 128) draw byte-identically.


def sky_dome_patches(exe_path):
    if os.environ.get("CHI_C76D", "1") == "0":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    # the duplicate: the second point block equals the first one word for word (except the 0x22 store through a0/v0)
    first = [word(0x8004F500 + 4 * k) for k in range(53)]
    second = [word(0x8004F604 + 4 * k) for k in range(53)]
    tail = asm(0x8004F6DC, ["sll v1, t0, 3", "sh v0, 0x22(a3)", "lui v0, 0xc", "addiu v0, v0, -0x21c0", "addu v1, v1, v0"])
    if first[:49] != second[:49] or [word(0x8004F6DC + 4 * k) for k in range(5)] != tail:
        raise RuntimeError("C76D: unexpected FUN_0004F34C")
    lines = ["lbu v0, 1(a1)", "sll v1, t0, 3", "andi at, v0, 0x80", "beq at, zero, TAB", "nop",
             "andi t0, v0, 0x7f", "beq zero, zero, DONE", "addiu v1, a1, 8",
             "TAB:", "lui at, 0xc", "addiu at, at, -0x21c0", "addu v1, v1, at", "DONE:"]
    return rewrite(exe_path, 0x8004F604, asm(0x8004F604, lines, 0x8004F6F0), "C76D: sky piece UV source")


def c67_patches(exe_path):
    if os.environ.get("CHI_C67") == "0":
        return []
    if os.environ.get("CHI_NEAR_SUB") == "1":
        raise RuntimeError("C67 and the NEAR_SUB experiment share the cave 0x80011924: set CHI_C67=0 for NEAR_SUB")
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    if img[NEAR_SUB_CAVE - base: NEAR_SUB_CAVE - base + 13] != b"SetGraphDebug":
        raise RuntimeError("C67 cave: unexpected bytes at %08X" % NEAR_SUB_CAVE)
    lines = _c67_code()
    c70 = os.environ.get("CHI_C70_DROP") == "1"           # PCAVE piece drop: experiment (the cull does the job)
    if c70:
        lines = lines + _c70_code()
        if img[0x80011A98 - base: 0x80011A98 - base + 11] != b"GPU timeout":
            raise RuntimeError("C70: unexpected bytes at 80011A98")
    words = asm(NEAR_SUB_CAVE, lines)
    # the cave may run into the GPU-timeout text (0x80011A98, printed only on a GPU timeout) and 'LoadImage2' (no
    # reference); 0x80011AD8 on are sprintf's digit tables
    if NEAR_SUB_CAVE + 4 * len(words) > 0x80011A98 and img[0x80011A98 - base: 0x80011A98 - base + 11] != b"GPU timeout":
        raise RuntimeError("C67: unexpected bytes at 80011A98")
    assert NEAR_SUB_CAVE + 4 * len(words) <= 0x80011AD8, len(words)
    lq = NEAR_SUB_CAVE & 0x1FFFFFFF                   # the table holds KUSEG addresses
    out = [(0x8002D564, 0x3C020003, asm(0x8002D564, ["lui v0, 0x%x" % (lq >> 16)])[0], "C67: light quad handler entry -> LQ"),
           (0x8002D568, 0x24420718, asm(0x8002D568, ["addiu v0, v0, 0x%x" % (lq & 0xFFFF)])[0], "C67: (low half)")]
    for pc, old, _new, _n in out:
        if word(pc) != old:
            raise RuntimeError("unexpected word at %08X" % pc)
    if c70:
        pc_ = _c67_labels(lines)["PCAVE"]
        inl = [(0x80030CC0, 0x001188C3, "move s4, ra"), (0x80030CC4, 0x24010020, "jal 0x%08x" % pc_),
               (0x80030CC8, 0x02210822, "nop"), (0x80030CCC, 0x0420007B, "bne at, zero, 0x80030ebc"),
               (0x80030CD0, 0x00000000, "move ra, s4")]
        for a, old, ins in inl:
            if word(a) != old:
                raise RuntimeError("C70: unexpected word at %08X" % a)
            out.append((a, old, asm(a, [ins])[0], "C70: piece drop via PCAVE (%s)" % ins))
    out += [(NEAR_SUB_CAVE + 4 * k, word(NEAR_SUB_CAVE + 4 * k), w, "C67 cave %d" % k) for k, w in enumerate(words)]
    return out


def _c67_labels(lines):
    labels, pc = {}, NEAR_SUB_CAVE
    for ln in lines:
        if ln.endswith(":"):
            labels[ln[:-1]] = pc
        else:
            pc += 4
    return labels


def c67_seeds():
    out = [NEAR_SUB_CAVE]
    if os.environ.get("CHI_C70_DROP") == "1":
        out.append(_c67_labels(_c67_code() + _c70_code())["PCAVE"])
    return out


def near_sub_seeds():
    """Cave entries the recompiler must compile natively (seeds/ghidra_funcs.txt, KSEG0 form)."""
    img, base = load_exe(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "disc", "SLUS_008.42.orig"))
    _w, lab = _near_sub_code(img, base)
    return [lab["WQ"], lab["TCAVE"]]


# --- S1 / S2: CLUTs out of VRAM slot 15 + a short permanent page in it (Infrastructure 20.10.) -------------------------
# Driver 1 keeps its CLUTs in the column x 960..1023, y 256..511 (page slot 15): the level-load allocator 0x80097550
# (perm / car / map / sky CLUTs, 4 per row from (960, 256)), then one 64 x 8 block per area slot (table 0x800BE1BC).
# Rows 427..502 hold D1's fixed HUD sprite block, row 426 the loading CLUT, (1008, 511) a fixed night CLUT, (320, 511)
# a fixed CLUT of 0x800508B0. Free in play AND during the level load (the loading screen draws 320 x 480 interlaced at
# x 0..319, y 0..479; in play the framebuffers are 512 x 240 at y 0 / 256): y 496..511 x 0..511, y 240..255 x 320..511,
# (rows 503..511 of the column are NOT free: the HUD block upload is 960, 459, 64 x 53). CLUT_STRIP v3 (20.10.):
#   allocator: region A = y 240..255 x 320..511 (12 per row): first CLUT + map at (320, 240) + the 64 x 3 reservation
#   (rows 240..242 = the sky CLUTs' own cursor 0x800974E0, as before rows 256..258), then region B = y 496..
#   x 0..511 (32 per row); one advance routine ADV
#   (cave) replaces the helper 0x800516AC and its two inline copies;
#   area slots: ONE 512-wide row each, slot s -> (0, 496 + s) (area loader 0x80033870: rect 512 x 1, CLUT words x += 64
#   per 4 instead of y += 1), so region B holds the permanent CLUTs only below row 496 + first area slot
#   Capacity: A 192 (rows 240..242 = the sky CLUT cursor 0x800974E0, up to 36) + B 32 x first area slot (Chicago
#   first 6: 384 positions; var_d2cars16 ends at (352, 501) = 374 used: 10 left).
# That frees x 960..1023, y 256..425 = a 256 x 170-texel page.
# SLOT15: a permanent page whose TEXTUREINFO flags have bit 0x80 ("short", converter CHI_POLISH_S1_SLOT15) is loaded into
# slot index 15 (outside the 0..14 range the area loops use) at (960, 256) with only 170 rows uploaded; the running page
# rect / slot counter / overflow flag are left as they were. Driver 1 levels have no 0x80 page: only the CLUT move applies.
S1_CAVE = 0x800106D0             # sound debug strings 'Error: Can't allocate SFX buffer' .. 'Bank: %d, Sample...' (no reference)
S1_CAVE_END = 0x80010898      # + 'Error: Can't allocate reverb', 'Channel status:', '-----' (no reference)


C82_SPTW_GP = -0x33B4                     # 0x800933BC (zero block): the special's yaw-kick factor (plugin; 0 = Driver 1's 0x37)


def _s1_cave_code():
    return ["SC:",
            "lw t0, 0xdf4(gp)", "sll t1, a2, 3", "addu t0, t0, t1", "lbu t0, 0(t0)",           # TEXPAGE_POS[page].flags
            "addiu sp, sp, -32", "sw ra, 24(sp)", "andi t0, t0, 0x80", "beq t0, zero, NORM",
            "lw t2, 0xe0c(gp)",                                                                   # (delay) overflow flag
            "nop", "sw t2, 28(sp)",                                                               # (load delay: nops)
            "lui t3, 0x100", "ori t3, t3, 0x3c0", "sw t3, 16(sp)",                               # rect x 960, y 256
            "lui t4, 0xaa", "ori t4, t4, 0x40", "sw t4, 20(sp)",                                 # w 64, h 170
            "addiu a0, sp, 16",
            "lui t5, 0xc", "addu t6, t5, a2", "addiu t7, zero, 15",
            "sb t7, -0x1d88(t6)",                                                                 # page -> slot 15
            "sb a2, -0x1af9(t5)",                                                                 # slot 15 -> page
            "sw t3, -0x18bc(t5)",                                                                 # slot 15 rect (960, 256)
            "lw t0, 0xdf0(gp)", "nop", "addiu t0, t0, -1",                                        # the caller adds 1 back
            "jal 0x800516e4", "sw t0, 0xdf0(gp)",
            "lw t2, 28(sp)", "nop", "sw t2, 0xe0c(gp)",
            "lw ra, 24(sp)", "nop", "jr ra", "addiu sp, sp, 32",
            "NORM:",
            "jal 0x800516e4", "nop",
            "lw ra, 24(sp)", "nop", "jr ra", "addiu sp, sp, 32",
            # ADV(a0 = &allocator {x, y}): the CLUT allocator's advance (v0, v1, at only, like the original helper)
            "ADV:",
            "lhu v0, 0(a0)", "lhu v1, 2(a0)", "addiu v0, v0, 16",
            "addiu at, zero, 0x200", "bne v0, at, STX", "slti at, v1, 255",
            "beq at, zero, B1", "nop",
            "addiu v0, zero, 320", "beq zero, zero, STY", "addiu v1, v1, 1",                      # region A next row
            "B1:", "slti at, v1, 256", "beq at, zero, B2", "move v0, zero",
            "beq zero, zero, STY", "addiu v1, zero, 496",                                          # A full -> region B
            "B2:", "addiu v1, v1, 1",                                                              # region B next row
            "STY:", "sh v1, 2(a0)",
            "STX:", "jr ra", "sh v0, 0(a0)",
            # S4C (InitCellData 0x800397CC, S4a): a1 = heap cursor for the cell objects, v1 = their bytes, v0 = cell
            # data bytes (kept); returns at = 0x90000 and a1 past the objects when they go on the heap
            "S4C:",
            "lw t0, 0x1120(gp)", "addu t1, a1, v1", "addu t2, t1, v0",
            "lui t3, 0x1f", "ori t3, t3, 0x5000", "sll t2, t2, 3", "srl t2, t2, 3",   # limit 0x1F5000: the replay tape
            # buffers start at 0x801FABBC (FUN_80058814) and the level allocates ~12-24 KB more after the cell data (C79)
            "beq t0, zero, S4MOD", "sltu t3, t2, t3",
            "beq t3, zero, S4MOD", "lui at, 9",
            "sw a1, 0x7108(at)", "jr ra", "move a1, t1",                                          # heap (Driver 1)
            "S4MOD:", "lui t3, 0x9f00", "ori t3, t3, 0x2000", "lui at, 9",
            "jr ra", "sw t3, 0x7108(at)",                                                          # mod buffer
            # ZT (level start 0x800228F0, S4a): clear the model table (main RAM, was frontend heap) before the level
            "ZT:",
            "addiu sp, sp, -8", "sw ra, 0(sp)",
            "lui t0, 0x%x" % ((NEW_BASE + 0x8000) >> 16), "addiu t0, t0, %d" % (NEW_BASE - (((NEW_BASE + 0x8000) >> 16) << 16)),
            "addiu t1, t0, 0x2000",
            "ZL:", "sw zero, 0(t0)", "addiu t0, t0, 4", "bne t0, t1, ZL", "nop",
            "jal 0x800505e0", "nop",
            "lw ra, 0(sp)", "nop", "jr ra", "addiu sp, sp, 8",
            # TW (C82, car-car response in GlobalTimeStep 0x8001CC44 / 0x8001CE9C): t1 = the yaw-kick factor of the car in t0
            # (Driver 1: 0x37 for every car; Driver 2: twistRateY / 2 per model) -> SPTW (plugin) for the special (model 5),
            # else 0x37; also does the call site's "lw v1, 0x98(sp)"
            "TW:",
            "lbu t0, 2(t0)", "lw v1, 0x98(sp)", "xori t0, t0, 5", "bne t0, zero, TWX", "addiu t1, zero, 0x37",
            "lw t0, %d(gp)" % C82_SPTW_GP, "nop", "beq t0, zero, TWX", "nop", "move t1, t0",
            "TWX:", "jr ra", "nop",
            # NOSES (C87, scenery hits in 0x8003FF0C: jal from 0x800407E8, its 'mflo t2' in the delay slot): the moved
            # 'sra v1, v0, 12', the car (s2) into t9, then C87's shared CORE (ready_cb cave)
            "NOSES:", "sra v1, v0, 12", "j %#x" % (C87_CAVE + 8), "move t9, s2",
            # C91 FEATHER (from the c88 car-car block): finish the id swap, then the tail in the pack-B string
            "FTHR1:", "xor t9, t9, v1", "j %#x" % (0x80010464 + 0x20), "sltu v0, zero, t8"]


def _s1_labels():
    labels, pc = {}, S1_CAVE
    for ln in _s1_cave_code():
        if ln.endswith(":"):
            labels[ln[:-1]] = pc
        else:
            pc += 4
    return labels


def s1_seeds():
    lab = _s1_labels()
    out = []
    if os.environ.get("CHI_S1_SLOT15", "1") != "0":
        out.append(lab["SC"])
    if os.environ.get("CHI_CLUT_STRIP", "1") != "0":
        out.append(lab["ADV"])
    out += [lab["S4C"], lab["ZT"]]
    if os.environ.get("CHI_C82", "1") != "0":
        out.append(lab["TW"])
    return out


def s1_clut_patches(exe_path):
    if os.environ.get("CHI_CLUT_STRIP", "1") == "0":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    adv = _s1_labels()["ADV"]
    edits = [  # (address, original instruction, new instruction)
        (0x80051B98, "addiu t1, zero, 0x3c0", "addiu t1, zero, 0x140"),            # allocator x start 320 (+ map x)
        (0x80051BA8, "addiu v0, zero, 0x3d0", "addiu v0, zero, 0x150"),            # x after the first CLUT
        (0x80051BB0, "lui at, 9", "addiu v1, zero, 0xf0"),                          # allocator y start 240
        (0x80051BB4, "sh a0, 0x7552(at)", "sh v1, 0xde2(gp)"),
        (0x80051C34, "sh a0, 0x75a2(at)", "sh v1, 0x75a2(at)"),                     # map CLUT rect y = 240
        # inline advance after the reservation -> ADV
        (0x80051C84, "addiu v0, v0, 0x10", "lui a0, 9"),
        (0x80051C88, "addiu v1, zero, 0x400", "jal 0x%08x" % adv),
        (0x80051C8C, "sh v0, 0xde0(gp)", "addiu a0, a0, 0x7550"),
        (0x80051C90, "sll v0, v0, 0x10", "nop"), (0x80051C94, "sra v0, v0, 0x10", "nop"),
        (0x80051C98, "bne v0, v1, 0x80051cb8", "nop"), (0x80051CA0, "lui v0, 9", "nop"),
        (0x80051CA4, "lhu v0, 0x7552(v0)", "nop"), (0x80051CA8, "sh t1, 0xde0(gp)", "nop"),
        (0x80051CAC, "addiu v0, v0, 1", "nop"), (0x80051CB0, "lui at, 9", "nop"), (0x80051CB4, "sh v0, 0x7552(at)", "nop"),
        # inline advance in the page palette loop (0x800516E4) -> ADV
        (0x80051758, "lhu v0, 0(s0)", "jal 0x%08x" % adv), (0x8005175C, "addiu v1, zero, 0x400", "move a0, s0"),
        (0x80051760, "addiu v0, v0, 0x10", "nop"), (0x80051764, "sh v0, 0(s0)", "nop"),
        (0x80051768, "sll v0, v0, 0x10", "nop"), (0x8005176C, "sra v0, v0, 0x10", "nop"),
        (0x80051770, "bne v0, v1, 0x80051788", "nop"), (0x80051774, "addiu v0, zero, 0x3c0", "nop"),
        (0x80051778, "lhu v1, 2(s0)", "nop"), (0x8005177C, "sh v0, 0(s0)", "nop"),
        (0x80051780, "addiu v1, v1, 1", "nop"), (0x80051784, "sh v1, 2(s0)", "nop"),
        # the helper's callers -> ADV
        (0x8004F03C, "jal 0x800516ac", "jal 0x%08x" % adv), (0x8005670C, "jal 0x800516ac", "jal 0x%08x" % adv),
        # no row align before the area slots
        (0x80052030, "beq v0, v1, 0x80052050", "beq zero, zero, 0x80052050"),
        # area slot CLUT row: (0, 496 + s); the allocator no longer moves per slot
        (0x800520A0, "lhu v0, 0xde0(gp)", "addiu v0, s2, 0x1f0"),
        (0x800520A4, "nop", "sh zero, 0(a0)"),
        (0x800520A8, "sh v0, 0(a0)", "nop"),
        (0x800520AC, "lui v0, 9", "nop"), (0x800520B0, "lhu v0, 0x7552(v0)", "nop"),
        (0x80052150, "addiu v0, v0, 8", "nop"),
        # area page loader: CLUTs as one row (512 x 1), words x += 64 per 4 palettes instead of y += 1
        (0x8003393C, "bgez s0, 0x80033948", "addiu s3, v0, 0x7030"),
        (0x80033940, "addiu s3, v0, 0x7030", "addiu v0, zero, 1"),
        (0x80033944, "addiu a0, s0, 3", "sh v0, 0x16(sp)"),
        (0x80033948, "sra v0, a0, 2", "addiu v0, zero, 0x200"),
        (0x8003394C, "addiu v0, v0, 1", "sh v0, 0x14(sp)"),
        (0x80033950, "sh v0, 0x16(sp)", "nop"),
        (0x800339E0, "lhu v0, 0x12(sp)", "lhu v0, 0x10(sp)"),
        (0x800339E8, "addiu v0, v0, 1", "addiu v0, v0, 0x40"),
        (0x800339EC, "sh v0, 0x12(sp)", "sh v0, 0x10(sp)"),
    ]
    out = []
    for pc, old_s, new_s in edits:
        old, new = asm(pc, [old_s])[0], asm(pc, [new_s])[0]
        if word(pc) != old:
            raise RuntimeError("CLUT strip: unexpected word at %08X (%08X, expected %s)" % (pc, word(pc), old_s))
        out.append((pc, old, new, "S1 CLUT strip: %s -> %s" % (old_s, new_s)))
    return out


def s1_slot15_patches(exe_path):
    if os.environ.get("CHI_S1_SLOT15", "1") == "0":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    if img[S1_CAVE - base: S1_CAVE - base + 33] != b"Error: Can't allocate SFX buffer\n" \
            or img[0x80010828 - base: 0x80010828 - base + 5] != b"Bank:":
        raise RuntimeError("S1 slot 15: unexpected bytes in the cave at %08X" % S1_CAVE)
    out = []
    for pc, old_s, new_s in [(0x800517B4, "lhu v0, 4(s4)", "lhu s0, 6(s4)"),                # upload height = rect h
                             (0x800517B8, "addiu s0, zero, 0x100", "lhu v0, 4(s4)"),        # (load delays respected)
                             (0x80051DF0, "jal 0x800516e4", "jal 0x%08x" % S1_CAVE)]:       # permanent pages via SC
        old, new = asm(pc, [old_s])[0], asm(pc, [new_s])[0]
        if word(pc) != old:
            raise RuntimeError("S1 slot 15: unexpected word at %08X" % pc)
        out.append((pc, old, new, "S1 slot 15: %s -> %s" % (old_s, new_s)))
    return out


def s1_cave_patches(exe_path):
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    if img[S1_CAVE - base: S1_CAVE - base + 33] != b"Error: Can't allocate SFX buffer\n" \
            or img[0x80010828 - base: 0x80010828 - base + 5] != b"Bank:":
        raise RuntimeError("S1 cave: unexpected bytes at %08X" % S1_CAVE)
    words = asm(S1_CAVE, _s1_cave_code())
    assert S1_CAVE + 4 * len(words) <= S1_CAVE_END, len(words)
    return [(S1_CAVE + 4 * k, word(S1_CAVE + 4 * k), w, "S1 cave %d" % k) for k, w in enumerate(words)]


# --- S4a (20.10.): the model table in main RAM: Driver 1's level heap starts 8 KB higher (0x80115600 -> 0x80117600,
# set at the level start 0x800228DC); the table (2048 entries) fills the gap; ZT clears it at the level start (the
# frontend used that RAM) before the level registers its models.
def s4_patches(exe_path):
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    assert NEW_BASE == 0x80115600
    out = []
    for pc, old_s, new_s in [(0x800228DC, "ori v1, v1, 0x5600", "ori v1, v1, 0x7600"),
                             (0x800228F0, "jal 0x800505e0", "jal 0x%08x" % _s1_labels()["ZT"])]:
        old, new = asm(pc, [old_s])[0], asm(pc, [new_s])[0]
        if word(pc) != old:
            raise RuntimeError("S4: unexpected word at %08X" % pc)
        out.append((pc, old, new, "S4a: %s -> %s" % (old_s, new_s)))
    return out


# --- C82 (23.10., user "optimisation 2": ramming the bus front throws / spins the car): Driver 1's car-car response
# (GlobalTimeStep) gives every car the same yaw kick (impulse x lever x 0x37); Driver 2 scales it per model (twistRateY / 2:
# cars 112, bus / fire engine 25, special 9 60), so a bus hit near its long nose spun the bus and its front swept the
# player away. TW (S1 cave) loads the special's factor (SPTW, plugin: 0x37 x D2 twistRateY / 224) for model 5.
# Plus the pair pre-check |d| < 1201 on the car ORIGINS (0x8001C4B4..EC): a bus box reaches 1024 behind its origin, so
# a pair was tested only after the boxes overlapped by up to ~330 -> window 2000 (Driver 1 boxes never touch beyond 1104:
# the exact box test decides, no change for Driver 1 cities).
def c82_patches(exe_path):
    if os.environ.get("CHI_C82", "1") == "0":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    tw = _s1_labels()["TW"]
    out = []
    for pc, old_s, new_s in [(0x8001C4B4, "addiu v0, v0, 0x4b0", "addiu v0, v0, 0x7d0"),
                             (0x8001C4B8, "sltiu v0, v0, 0x961", "sltiu v0, v0, 0xfa1"),
                             (0x8001C4D0, "slti v0, v1, 0x4b1", "slti v0, v1, 0x7d1"),
                             (0x8001C4D8, "slti v0, v1, -0x4b0", "slti v0, v1, -0x7d0"),
                             (0x8001C4E0, "slti v0, a0, 0x4b1", "slti v0, a0, 0x7d1"),
                             (0x8001C4E8, "slti v0, a0, -0x4b0", "slti v0, a0, -0x7d0"),
                             (0x8001CC44, "lw v1, 0x98(sp)", "jal 0x%08x" % tw), (0x8001CC48, "nop", "move t0, s7"),
                             (0x8001CE9C, "lw v1, 0x98(sp)", "jal 0x%08x" % tw), (0x8001CEA0, "nop", "move t0, s3")]:
        old, new = asm(pc, [old_s])[0], asm(pc, [new_s])[0]
        if word(pc) != old:
            raise RuntimeError("C82: unexpected word %08X at %08X" % (word(pc), pc))
        out.append((pc, old, new, "C82: %s -> %s" % (old_s, new_s)))
    return out


# --- C87 (48, 23.10.): Driver 2's damage zones for the special. DamageCar3D (D1 0x8003FC98 = D2 bcollide.c) picks the zone
# from nose / door of the lever with lbody = 0x104 for every car; Driver 2 uses colBox.vz / 2 per model and the drawn body's
# centre. A bus (half length 870, box centre 154 behind the origin) put side hits into the corner zones. NOSE (cave in the
# unreferenced 'ready_cb_*' strings 0x800104E0..0x8001052B, xrefs / immediates / pointer words checked) maps the nose of a
# model-5 car to Driver 1's scale: nose' = (nose - SPBO) x SPLB >> 12, SPLB = 260 x 4096 / (SPBZ / 2) (plugin, 0x800933C0;
# 0 = Driver 1). Entered by jal from 0x8003FD70 (the replaced 'addu v0, t1, a0' runs in the delay slot); NOSE does the
# moved 'mflo t0'. PS1-native.
C87_CAVE, C87_END = 0x800104E0, 0x8001052C
C87_SPLB_GP = -0x33B0                         # 0x800933C0 (zero block)


def c87_patches(exe_path):
    if os.environ.get("CHI_C87", "1") == "0":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    if img[C87_CAVE - base: C87_CAVE - base + 17] != b"ready_cb_textures" or img[C87_END - base: C87_END - base + 6] != b"Ulp!!!":
        raise RuntimeError("C87: unexpected bytes in the cave")
    cave = asm(C87_CAVE, ["mflo t0", "move t9, t2",                       # NOSE (car-car); CORE at +8 (t9 = the car)
                          "lbu t3, 2(t9)", "lw t4, %d(gp)" % C87_SPLB_GP, "xori t3, t3, 5", "bne t3, zero, NX",
                          "lw t3, %d(gp)" % C42B_SPBO_GP, "beq t4, zero, NX", "nop", "subu v1, v1, t3", "mult v1, t4",
                          "mflo v1", "sra v1, v1, 12", "NX:", "jr ra", "nop"], C87_END)
    out = [(C87_CAVE + 4 * k, word(C87_CAVE + 4 * k), w, "C87: NOSE %d" % k) for k, w in enumerate(cave)]
    for pc, old_s, new_s in [(0x8003FD70, "addu v0, t1, a0", "jal %#x" % C87_CAVE), (0x8003FD74, "mflo t0", "addu v0, t1, a0"),
                             (0x800407E8, "sra v1, v0, 12", "jal %#x" % _s1_labels()["NOSES"])]:   # scenery hits
        o, n = asm(pc, [old_s])[0], asm(pc, [new_s])[0]
        if word(pc) != o:
            raise RuntimeError("C87: unexpected word %08X at %08X" % (word(pc), pc))
        out.append((pc, o, n, "C87: %s -> %s" % (old_s, new_s)))
    return out


# --- C88 / C89 (user 24.10., Polish design_c88_cheats.md): new cheats + cheats in Survival ------------------------------
# Words (zero block, menu / plugin): INFM 0x800933C4 infinite mass, NGHT 0x800933C8 nightmare, SPD2 0x800933CC super
# speed (plugin: THRS x 2), 0x800933D0 = dummy target of C89's redirected resets; LOW GRAVITY = Driver 1's hidden word
# 0x8009D8E8. Every cheat off = Driver 1 unchanged.
C88_INFM_GP, C88_NGHT_GP, C88_SPD2_GP, C89_DUMMY_GP = -0x33AC, -0x33A8, -0x33A4, -0x33A0


def c88_patches(exe_path):
    if os.environ.get("CHI_C88", "1") == "0":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    out = []
    # LOW GRAVITY: StepOneCar 0x8001D7C4 uses -0xAAA (1/4 g) when 0x8009D8E8 != 0 -> -0x1555 (1/2 g, the cheat's value)
    o, n = asm(0x8001D7D4, ["addiu v0, zero, -0xaaa"])[0], asm(0x8001D7D4, ["addiu v0, zero, -0x1555"])[0]
    if word(0x8001D7D4) != o:
        raise RuntimeError("C88: unexpected gravity word")
    out.append((0x8001D7D4, o, n, "C88: low gravity 1/2 g"))
    # C89: Survival (type 0x13) / type 0x15 cleared Invincibility / Immunity at game start: the 3 stores go to a dummy word
    for pc, off in ((0x80024838, 0xb0), (0x8002483C, 0xac), (0x80024848, 0xb0)):
        o, n = asm(pc, ["sw zero, %d(gp)" % off])[0], asm(pc, ["sw zero, %d(gp)" % C89_DUMMY_GP])[0]
        if word(pc) != o:
            raise RuntimeError("C89: unexpected store at %08X" % pc)
        out.append((pc, o, n, "C89: cheat reset -> dummy (cheats stay on in Survival)"))
    # INFINITE MASS (needs C82's TW, which sets t1 itself): GlobalTimeStep's mission-rule block 0x8001C9FC..0x8001CA4C is
    # rewritten without nops / branches into flags: a2 / t2 (move car s7 / s3) &= mission rule (types 3 / 6: id < 0x17)
    # and, with INFM != 0, &= (car id != 0): the player is never moved by a car-car hit; the other car takes the impulse.
    if os.environ.get("CHI_C82", "1") != "0":
        old = [word(0x8001C9FC + 4 * k) for k in range(21)]
        if old[0] != asm(0x8001C9FC, ["lui v1, 9"])[0] or old[20] != asm(0x8001CA4C, ["move a2, zero"])[0]:
            raise RuntimeError("C88: unexpected mission-rule block")
        # C91: INFM word bit 0x20 = INFINITE MASS (the player is never moved), bit 0x100 = FEATHER (the OTHER car is never
        # moved when it meets the player: the ids are swapped before the same rule). Mission types 3 / 6 keep Driver 1's
        # mission rule only. Tail: S1 cave FTHR1 (3 words) + pack-B string tail (4 words).
        new = asm(0x8001C9FC, ["lbu v1, 0x128(gp)", "lw at, %d(gp)" % C88_INFM_GP, "sw v0, 0x58(sp)", "lbu t8, 0(s3)",
                               "lbu t9, 0(s7)", "addiu v0, v1, -3", "beq v0, zero, MR", "xori v1, v1, 6",
                               "bne v1, zero, INF", "srl v0, at, 8",
                               "MR:", "sltiu v0, t8, 0x17", "and t2, t2, v0", "sltiu v1, t9, 0x17",
                               "beq zero, zero, 0x8001ca50", "and a2, a2, v1",
                               "INF:", "beq at, zero, 0x8001ca50", "subu v0, zero, v0", "xor v1, t8, t9", "and v1, v1, v0",
                               "j %#x" % _s1_labels()["FTHR1"], "xor t8, t8, v1"], 0x8001CA50)
        assert len(new) == 21, len(new)
        out += [(0x8001C9FC + 4 * k, old[k], new[k], "C88: infinite mass / mission rule %d" % k) for k in range(21) if old[k] != new[k]]
    if os.environ.get("CHI_C88_REPLAY", "1") != "0":
        out += c88_replay_patches(img, base, word)
    # HIGH SCORES: FUN_8006C964 skips the record (0x80096F00 = 0 at 0x8006CA80) when 0x8009D8DC / E0 / E4 / E8 is set
    # (4 x lw / nop / bnez). The 15 words 0x8006C9FC..0x8006CA34 become one OR over those 4 + INFM / NGHT / SPD2 and one
    # bnez (same target, same delay slot 'addiu a0, sp, 0x10'); t0..t2 are dead here (t0 written before use, t1 / t2 unused).
    if os.environ.get("CHI_C88_SLOTS", "1") != "0":
        out += c88_slot_patches(word)
    if os.environ.get("CHI_C88_FLIP", "1") != "0":
        # INVINCIBILITY vs the flip wreck: FUN_800230B0 counts frames with the player's up vector y (0x8009B0B0) < 100
        # (0x80096920) and sets damage = max + 100 after 180; with Invincibility (0x8009681C) the counter is reset instead.
        old = ["nop", "lw v0, 0x1b0(gp)", "nop", "addiu v0, v0, 1", "sw v0, 0x1b0(gp)", "slti v0, v0, 0xb5",
               "bne v0, zero, 0x8002347c", "nop", "lui v0, 9"]
        new = ["nop", "lw v0, 0xac(gp)", "lw v1, 0x1b0(gp)", "bne v0, zero, 0x80023478", "addiu v1, v1, 1",
               "sw v1, 0x1b0(gp)", "slti v0, v1, 0xb5", "bne v0, zero, 0x8002347c", "lui v0, 9"]
        o, n = asm(0x80023440, old), asm(0x80023440, new)
        for k in range(len(o)):
            if word(0x80023440 + 4 * k) != o[k]:
                raise RuntimeError("C88 flip: unexpected word at %08X" % (0x80023440 + 4 * k))
        out += [(0x80023440 + 4 * k, o[k], n[k], "C88: no flip wreck with Invincibility %d" % k) for k in range(len(o)) if o[k] != n[k]]
    if os.environ.get("CHI_C88_SLOTS", "1") != "0":
        # route refresh in the pursuit handler: 'frame % 4 == slot - 1' -> '(frame & 3) == (slot - 1) & 3' so cops in
        # slots 5.. (Nightmare chasers) re-plan like Driver 1's (slots 1-4 unchanged for frame >= 0)
        old = ["bgez a0, 0x80066038", "sw a1, 0x2c(s0)", "addiu v1, a0, 3", "sra v1, v1, 2", "lw t2, 0x70(sp)",
               "sll v1, v1, 2", "lbu v0, 5(t2)", "subu v1, a0, v1", "addiu v0, v0, -1"]
        # mask = RMASK (0x800933E4, plugin; 0 = Driver 1) | 3: Nightmare may re-plan less often (CHI_C88_NM_REPLAN)
        new = ["sw a1, 0x2c(s0)", "lw t2, 0x70(sp)", "lw t3, %d(gp)" % C88_RMASK_GP, "lbu v0, 5(t2)", "ori t3, t3, 3",
               "addiu v0, v0, -1", "and v1, a0, t3", "and v0, v0, t3", "nop"]
        o, n = asm(0x8006602C, old), asm(0x8006602C, new)
        for k in range(len(o)):
            if word(0x8006602C + 4 * k) != o[k]:
                raise RuntimeError("C88 route refresh: unexpected word at %08X" % (0x8006602C + 4 * k))
        out += [(0x8006602C + 4 * k, o[k], n[k], "C88: route refresh for slots 5.. %d" % k) for k in range(len(o)) if o[k] != n[k]]
    if os.environ.get("CHI_C88_SCORES", "1") != "0":
        olds = [word(0x8006C9FC + 4 * k) for k in range(15)]
        if olds[0] != asm(0x8006C9FC, ["lw v1, -0x2724(v0)"])[0] or olds[14] != asm(0x8006CA34, ["bne v0, zero, 0x8006ca80"])[0] \
                or word(0x8006CA38) != asm(0x8006CA38, ["addiu a0, sp, 0x10"])[0]:
            raise RuntimeError("C88: unexpected high-score cheat check")
        new = asm(0x8006C9FC, ["lw v1, 0x716c(gp)", "lw t0, 0x7170(gp)", "lw t1, 0x7174(gp)", "lw t2, %d(gp)" % C88_LOWG_GP,
                               "or v1, v1, t0", "lw t0, %d(gp)" % C88_INFM_GP, "or v1, v1, t1", "lw t1, %d(gp)" % C88_NGHT_GP,
                               "or v1, v1, t2", "lw t2, %d(gp)" % C88_SPD2_GP, "or v1, v1, t0", "or v1, v1, t1",
                               "or v1, v1, t2", "nop", "bne v1, zero, 0x8006ca80"])
        out += [(0x8006C9FC + 4 * k, olds[k], new[k], "C88: high scores off with any cheat %d" % k)
                for k in range(15) if olds[k] != new[k]]
    return out


# C88 NIGHTMARE slots (user 63 B: every car chases): Driver 1's 4 cop slots (0x800C4E38 + k x 0x7A8: header, a route
# of <= 64 nodes x 0x1C at +0x58, state +0x758..0x7A8; record byte +5 = k + 1) move to a 24-slot array the plugin
# allocates; its address comes from 4 zero-block words (plugin, every vblank): SLOT0 = base, SLOT1 = base - 0x7A8
# (1-based sites 'lui 0xc / addiu 0x4690'), SLOTM = base - 0x4E38 (for a kept 'addiu x, 0x4e38 / 0x4690 / 0x6cd8'),
# SLOTE = base + 24 x 0x7A8. Loops over 24: level clear 0x80016D5C, FUN_8005474C's two (minimap), FUN_800635C0 (both),
# init FUN_80063C60, FUN_800641C0. Kept at 4: the allocators FUN_80063B14 / B74 and FUN_80063AA8 (Driver 1's director /
# missions get slots 1-4 only) and FUN_80064A64's drop loop (it counts empty slots) -> with no chaser Driver 1 behaves
# exactly as before. Chasers are given slots 5.. by the plugin (Nightmare, host; M8: the same from guest code, the array
# in RAM under the stack, NY sized 8).
C88_SLOT0_GP, C88_SLOT1_GP, C88_SLOTM_GP, C88_SLOTE_GP = -0x339C, -0x3398, -0x3394, -0x3390   # 0x800933D4..E0
C88_NSLOTS = 24
C88_RMASK_GP = -0x338C                     # 0x800933E4: route re-plan mask | 3 (plugin)


def c88_slot_patches(word):
    out = []
    def put(pc, old, new, note):
        o, n = asm(pc, [old])[0], asm(pc, [new])[0]
        if word(pc) != o:
            raise RuntimeError("C88 slots: %08X is %08X, expected %s" % (pc, word(pc), old))
        out.append((pc, o, n, "C88 slots: " + note))
    W = {0x4e38: C88_SLOT0_GP, 0x4690: C88_SLOT1_GP}
    adjacent = [(0x80017D00, "v0", "v0", 0x4690), (0x8001966C, "v0", "s5", 0x4690), (0x8001A070, "v0", "s6", 0x4690),
                (0x8001A61C, "v0", "v0", 0x4690), (0x80063F38, "v1", "v1", 0x4690), (0x80065478, "v1", "v1", 0x4690),
                (0x8001661C, "v0", "v0", 0x4e38), (0x800549D4, "v1", "s1", 0x4e38), (0x80063614, "v0", "s0", 0x4e38),
                (0x80063B18, "v0", "a0", 0x4e38), (0x80063B90, "v0", "a0", 0x4e38), (0x80063C08, "v1", "v1", 0x4e38),
                (0x80063C60, "v0", "a2", 0x4e38), (0x800642C8, "v0", "a2", 0x4e38)]
    for pc, rx, ry, imm in adjacent:
        put(pc, "lui %s, 0xc" % rx, "lw %s, %d(gp)" % (ry, W[imm]), "base")
        put(pc + 4, "addiu %s, %s, %#x" % (ry, rx, imm), "nop", "base (load delay)")
    for pc, rx in ((0x80019BEC, "t0"), (0x80065018, "a1")):            # lui / other / addiu: keep the addiu
        put(pc, "lui %s, 0xc" % rx, "lw %s, %d(gp)" % (rx, C88_SLOTM_GP), "base (kept addiu 0x4690)")
    # level clear (FUN_80016CE4): base + end, the end no longer an immediate
    put(0x80016D5C, "lui v0, 0xc", "lw v1, %d(gp)" % C88_SLOT0_GP, "clear base")
    put(0x80016D60, "addiu v1, v0, 0x4e38", "lw a1, %d(gp)" % C88_SLOTE_GP, "clear end")
    put(0x80016D6C, "addiu a1, v1, 0x1ea0", "nop", "clear end (was +4 slots)")
    # FUN_8005474C's two slot loops
    put(0x80054A08, "addiu v1, s1, 0x1ea0", "lw v1, %d(gp)" % C88_SLOTE_GP, "loop 1 end")
    put(0x80054AE4, "lui v0, 0xc", "lw s1, %d(gp)" % C88_SLOT0_GP, "loop 2 base")
    put(0x80054AE8, "addiu s1, v0, 0x4e38", "lw v1, %d(gp)" % C88_SLOTE_GP, "loop 2 end")
    put(0x80054AEC, "addiu v1, s1, 0x1ea0", "nop", "loop 2 end (load delay)")
    # FUN_800635C0 loop 2 (lost pursuit) and loop 1 (index)
    put(0x8006398C, "lui v0, 0xc", "lw s2, %d(gp)" % C88_SLOT0_GP, "lost-pursuit loop base")
    put(0x80063990, "addiu s2, v0, 0x4e38", "lw v1, %d(gp)" % C88_SLOTE_GP, "lost-pursuit loop end")
    put(0x80063994, "addiu v1, s2, 0x1ea0", "nop", "lost-pursuit loop end (load delay)")
    put(0x800638FC, "slti v0, s5, 4", "slti v0, s5, %d" % C88_NSLOTS, "seen loop count")
    put(0x80063D20, "slti v0, a1, 4", "slti v0, a1, %d" % C88_NSLOTS, "init loop count")
    put(0x80064320, "slti v0, a3, 4", "slti v0, a3, %d" % C88_NSLOTS, "spot loop count")
    # FUN_80064A64's drop loop stays on slots 1-4 (base + 0x1EA0 from SLOTM + 0x6cd8)
    put(0x80064BE4, "lui t3, 0xc", "lw v0, %d(gp)" % C88_SLOTM_GP, "drop loop end base")
    put(0x80064BE8, "lui v0, 0xc", "lw t3, %d(gp)" % C88_SLOTM_GP, "drop loop base")
    return out


# C94 "Extra draw distance" (driver.personal feature, 25.10.; design chicago/design_c94_drawdist.md). The map draw
# (cell loop FUN_8002C8FC) walks a 19 x 19 cell window (radius 9) against the camera cell's 19 x 19 PVS (decoded to
# 0x800A80C4). The window, its PVS buffer, the object list, the ground-tile bands and the primitive-buffer limits now
# come from words in the exe's zero block (image data = Driver 1's values, so nothing changes until the plugin writes
# the 1.5x set): window 27 x 27 (radius 13; corners trimmed 6 deep), the 19 x 19 PVS copied into the middle of a 27 x 27
# buffer whose ring stays 1 (no PVS data beyond radius 9: drawn when in the frustum), the plane start values moved 4
# cells out, a 4096-entry object list and bigger primitive buffers in host memory. Not changed: the AI ranges, the
# region / area streaming (2 x 2 regions cover 45000), the PVS used by the cops' line of sight (FUN_800397F4).
C94_WORDS = {   # name: (address, gp offset, Driver 1 value: the exact KUSEG values the original lui / ori built)
    "XB": (0x800933F0, -0x3380, 0x000A80C4), "XS": (0x800933F4, -0x337C, 19), "XW": (0x800933F8, -0x3378, 19),
    "XT": (0x800933FC, -0x3374, 4), "XL": (0x80093400, -0x3370, 18), "XR": (0x80093404, -0x336C, 9),
    "XDD": (0x80093408, -0x3368, 0), "XLIST": (0x8009340C, -0x3364, 0x000A76AC),
    "XTB1": (0x80093410, -0x3360, 7000), "XTB2": (0x80093414, -0x335C, 9000),
    "XOBJ": (0x80093418, -0x3358, OBJ_LIMIT), "XTILE": (0x8009341C, -0x3354, TILE_LIMIT),
    "XPB0": (0x80093420, -0x3350, 0x000D8600), "XPB1": (0x80093424, -0x334C, 0x000F6600),
    "XPBN": (0x80093428, -0x3348, -0x1E000 & 0xFFFFFFFF),   # C96: minus the primitive buffer size (car LOD budget)
}
C101_XPVS, C101_XPVS_GP = 0x80093430, -0x3340   # 0 = Driver 1 PVS (19 x 19); 729 = the level's PVS is 27 x 27 (_xd level)
C101_XTMP, C101_XTMP_GP = 0x80093434, -0x333C   # plugin buffer (729 B) for the cops' 19 x 19 view of a 27 x 27 stream
C101_CAVE, C101_CAVE_END = 0x80094640, 0x80094718  # zero run 0x80094634..0x800947C8 (zero in every dump, no xref)
C102_CAVE, C102_CAVE_END = 0x80094718, 0x800947C8  # same zero run (C102 shadow)
C102_SBUF, C102_SBUF_GP = 0x80093440, -0x3330      # 16 words: the shadow's corner block (copy of car +0x88..+0xC0)
C102_SHD, C102_SHD_GP = 0x80093480, -0x32F0        # 25 x 16 B: per car index 4 x (dx, dz) i16 added to the corners
C94_CAVE, C94_CAVE_END = 0x800947D0, 0x80094890   # a zero run 0x800947CC..0x800949CE (zero in every dump, no xref);
# not the zero block: plugin data words there made the page 'diverged' (code interpreted). 256 B after the end stay zero.
C95_OT_CAVE = 0x80094890   # 2 x 6 words right after the C94 cave (same zero run, ends 0x800948C0)
C97_CAVE, C97_CAVE_END = 0x800948C0, 0x80094910   # replay invincibility (same zero run)
C99_CAVE, C99_CAVE_END = 0x80094910, 0x800949CC   # HELL cheat (same zero run, ends 0x800949CC)
C99_HELL, C99_HELL_GP = 0x8009342C, -0x3344        # HELL word (zero block, plugin cheats menu)
C99_SEEDS = []
C106_PACKX, C106_UNPX, C106_DEMOX = 0x8009479C, 0x800947B4, 0x80094634   # HELL replay bit 9 / demo reset


def c94_all(exe_path):
    """always applied: the guards read XOBJ / XTILE, so the words (Driver 1 values) must exist; the rest is gated at
    run time by the words themselves"""
    img, base = load_exe(exe_path)
    return c94_patches(lambda a: struct.unpack_from("<I", img, a - base)[0])


def c94_patches(word):
    out = []
    for name, (addr, _gp, val) in C94_WORDS.items():
        if word(addr) != 0:
            raise RuntimeError("C94: zero-block word %s %08X not free" % (name, addr))
        # no image data: the zero block is cleared at boot (wtrace 25.10.: the words read 0 at the title although the
        # package wrote them); driver.chicago's vblank writes the Driver 1 values (C94_DEFAULTS) unless extra-draw is on
    g = {k: v[1] for k, v in C94_WORDS.items()}
    def put(pc, old, new, note):
        o, n = asm(pc, [old])[0], asm(pc, [new])[0]
        if word(pc) != o:
            raise RuntimeError("C94: %08X is %08X, expected %s" % (pc, word(pc), old))
        out.append((pc, o, n, "C94: " + note))
    # cave: plane start values 4 cells further out + the PVS copied into the 27 x 27 buffer (only with radius XR != 9;
    # XDD = 1 only marks that driver.personal owns the words)
    cave = asm(C94_CAVE, [
        "PRE:", "lw at, %d(gp)" % g["XR"], "nop", "addiu at, at, -9", "beq at, zero, PRET", "nop",   # radius 9 = Driver 1
        # value -= 4 * (column step + row step) for the three planes (sp of the cell loop: jal keeps sp)
        "lw t1, 0x5c(sp)", "lw t2, 0x60(sp)", "lw t3, 0x74(sp)", "addu t1, t1, t2", "sll t1, t1, 2", "subu t3, t3, t1",
        "sw t3, 0x74(sp)",
        "lw t1, 0x64(sp)", "lw t2, 0x68(sp)", "lw t3, 0x78(sp)", "addu t1, t1, t2", "sll t1, t1, 2", "subu t3, t3, t1",
        "sw t3, 0x78(sp)",
        "lw t1, 0x6c(sp)", "lw t2, 0x70(sp)", "lw t3, 0x7c(sp)", "addu t1, t1, t2", "sll t1, t1, 2", "subu t3, t3, t1",
        "sw t3, 0x7c(sp)",
        # PVS 19 x 19 (0x800A80C4) -> the middle of the 27 x 27 buffer XB (row 4, column 4); not with a native 27 x 27
        # PVS (C101 _xd level: decoded straight into XB)
        "lw at, %d(gp)" % C101_XPVS_GP, "nop", "bne at, zero, PRET",
        "lw t1, %d(gp)" % g["XB"], "lui t2, 0xb", "addiu t2, t2, -0x7f3c", "addiu t1, t1, 112", "addiu t3, zero, 19",
        "ROW:", "addiu at, zero, 19",
        "COL:", "lbu v0, 0(t2)", "addiu t2, t2, 1", "sb v0, 0(t1)", "addiu at, at, -1", "bne at, zero, COL",
        "addiu t1, t1, 1",
        "addiu t3, t3, -1", "bne t3, zero, ROW", "addiu t1, t1, 8",
        "PRET:", "jr ra", "nop"])
    assert C94_CAVE + 4 * len(cave) <= C94_CAVE_END
    out += [(C94_CAVE + 4 * k, word(C94_CAVE + 4 * k), w, "C94: cave %d" % k) for k, w in enumerate(cave)]
    # C95 OT index clamp: world_renderer (0x80030E64) and its subdivided path (0x800315D8) take the OT slot as
    # (sum of 4 vertex depths >> 3) & 0x3FFC: a polygon beyond avg depth ~32760 WRAPPED to a near slot and was drawn over
    # near geometry (cheats 5 'polygons popping at certain angles' with Extra draw distance; D1's corner cells reach it
    # too). Now clamped to the farthest slot 0x3FFC; in-range values are unchanged.
    for k, site in enumerate((0x80030E64, 0x800315D8)):   # andi s1, s1, 0x3ffc; add s4, s4, s1 -> j cave; nop
        cv = C95_OT_CAVE + 0x18 * k
        code = asm(cv, ["sltiu at, s1, 0x4000", "bne at, zero, %#x" % (cv + 16), "andi s1, s1, 0x3ffc",
                        "ori s1, zero, 0x3ffc", "j %#x" % (site + 8), "addu s4, s4, s1"])
        out += [(cv + 4 * i, word(cv + 4 * i), w, "C95: OT clamp cave %d word %d" % (k, i)) for i, w in enumerate(code)]
        put(site, "andi s1, s1, 0x3ffc", "j %#x" % cv, "OT slot clamp (C95) %d" % k)
        if word(site + 4) != 0x0291A020:                  # add s4, s4, s1 (asm() has no 'add'; addu in the cave)
            raise RuntimeError("C95: %08X is %08X" % (site + 4, word(site + 4)))
        out.append((site + 4, 0x0291A020, 0, "C95: OT slot clamp %d, add moved into the cave" % k))
    # C101 native 27 x 27 PVS (Polish's _xd level for Extra draw distance): XPVS = 729 -> the draw decode (FUN_8002D7C4's
    # call 0x8002D97C) runs with *0x800973A8 = 729 straight into XB; the cops' line-of-sight decode (FUN_8003A100's call
    # 0x8003A258) decodes 729 into XTMP and copies the middle 19 x 19 to its own buffer; *0x800973A8 back to 361 after.
    for w_ in (C101_XPVS, C101_XTMP):
        if word(w_) != 0:
            raise RuntimeError("C101: word %08X not free" % w_)
    cx = C101_CAVE
    # the draw decode also refreshes Driver 1's 19 x 19 buffer 0x800A80C4 (middle of the 27 x 27): FUN_800398B0 (car
    # visibility for the car draw list, FUN_80014A8C) reads it - without it cars were culled by a stale PVS (cheats 7
    # 'cars only very close' after NY -> Chicago)
    src = ["DRAW:", "lw at, %d(gp)" % C101_XPVS_GP, "nop", "beq at, zero, D1", "nop",
           "sw at, 0xc38(gp)", "lw a3, %d(gp)" % g["XB"], "addiu sp, sp, -16", "sw ra, 4(sp)",
           "jal 0x8003a270", "nop",
           "lw t1, %d(gp)" % g["XB"], "lui t2, 0xb", "addiu t2, t2, -0x7f3c", "addiu t1, t1, 112", "j CR",
           "addiu t3, zero, 19",
           "D1:", "j 0x8003a270", "nop",
           "COPS:", "lw at, %d(gp)" % C101_XPVS_GP, "nop", "beq at, zero, C1", "nop",
           "sw at, 0xc38(gp)", "addiu sp, sp, -16", "sw ra, 4(sp)", "sw a3, 8(sp)", "lw a3, %d(gp)" % C101_XTMP_GP,
           "jal 0x8003a270", "nop",
           "lw t1, %d(gp)" % C101_XTMP_GP, "lw t2, 8(sp)", "addiu t1, t1, 112", "addiu t3, zero, 19",
           "CR:", "addiu t4, zero, 19",
           "CC:", "lbu v0, 0(t1)", "addiu t1, t1, 1", "sb v0, 0(t2)", "addiu t4, t4, -1", "bne t4, zero, CC",
           "addiu t2, t2, 1",
           "addiu t3, t3, -1", "bne t3, zero, CR", "addiu t1, t1, 8",
           "lw ra, 4(sp)", "addiu sp, sp, 16", "addiu at, zero, 0x169", "jr ra", "sw at, 0xc38(gp)",
           "C1:", "j 0x8003a270", "nop"]
    code = asm(cx, src)
    assert cx + 4 * len(code) <= C101_CAVE_END, hex(cx + 4 * len(code))
    out += [(cx + 4 * i, word(cx + 4 * i), w, "C101: PVS cave %d" % i) for i, w in enumerate(code)]
    lab, k = {}, 0
    for ln in src:
        if ln.endswith(":"): lab[ln[:-1]] = cx + 4 * k
        else: k += 1
    c2 = lab["COPS"]
    put(0x8002D97C, "jal 0x8003a270", "jal %#x" % cx, "C101: draw PVS decode -> cave")
    put(0x8003A258, "jal 0x8003a270", "jal %#x" % c2, "C101: cops PVS decode -> cave")
    # C102 car shadow (FUN_8002ADEC: one PolyFT4 through the car's 4 corner points car +0x88 / 0x98 / 0xA8 / 0xB8, world
    # x, y, z ints, the same points the physics uses): the routine now reads a copy (SBUF) with per-car offsets added to
    # x / z: SHD[car] = 4 x (dx, dz) i16 in SBUF corner order (+0x88, +0x98, +0xA8, +0xB8); the plugin writes them for the
    # special (its .sps.bin quad minus its corner quad, in world axes) every vblank, 0 = Driver 1's quad.
    for w_ in range(C102_SBUF, C102_SHD + 16 * 25, 4):
        if word(w_) != 0:
            raise RuntimeError("C102: word %08X not free" % w_)
    sh = ["addiu v1, gp, %d" % C102_SBUF_GP, "addiu a0, t0, 0x88", "addiu a1, zero, 15", "move a2, v1",
          "CP:", "lw v0, 0(a0)", "addiu a0, a0, 4", "sw v0, 0(a2)", "addiu a1, a1, -1", "bne a1, zero, CP",
          "addiu a2, a2, 4",
          "sll a0, t1, 4", "addu a0, a0, gp", "addiu a0, a0, %d" % C102_SHD_GP, "addiu a1, zero, 4", "move a2, v1",
          "AD:", "lh v0, 0(a0)", "lw at, 0(a2)", "lh a3, 2(a0)", "addu at, at, v0", "sw at, 0(a2)", "lw at, 8(a2)",
          "addiu a0, a0, 4", "addu at, at, a3", "sw at, 8(a2)", "addiu a1, a1, -1", "bne a1, zero, AD",
          "addiu a2, a2, 0x10",
          "addiu t0, v1, -0x88", "lui v1, 9", "lhu v0, 0x88(t0)", "j 0x8002ae38", "nop"]
    shc = asm(C102_CAVE, sh)
    assert C102_CAVE + 4 * len(shc) <= C102_CAVE_END, hex(C102_CAVE + 4 * len(shc))
    out += [(C102_CAVE + 4 * i, word(C102_CAVE + 4 * i), w, "C102: shadow cave %d" % i) for i, w in enumerate(shc)]
    put(0x8002AE30, "lui v1, 9", "j %#x" % C102_CAVE, "C102: shadow corners -> cave (copy + offsets)")
    # cell loop (FUN_8002C8FC)
    put(0x8002CAC0, "nop", "jal %#x" % C94_CAVE, "planes + PVS ring (the 2 HI/LO spacer slots)")
    put(0x8002CAE4, "lui v0, 0xb", "lw v0, %d(gp)" % g["XB"], "PVS base")
    put(0x8002CAE8, "addiu v0, v0, -0x7f3c", "nop", "PVS base (load delay)")
    trim_old = ["lw t7, 0x38(sp)", "nop", "slti v0, t7, 4", "beq v0, zero, 0x8002cb74", "move a1, zero",
                "addiu v0, zero, 4", "j 0x8002cb90", "subu a1, v0, t7", "lw t8, 0x38(sp)", "addiu v0, zero, 0x12",
                "subu v0, v0, t8", "slti v0, v0, 4", "beq v0, zero, 0x8002cb90", "nop", "addiu a1, t8, -0xe"]
    trim_new = ["lw t7, 0x38(sp)", "lw v1, %d(gp)" % g["XT"], "lw t8, %d(gp)" % g["XL"], "subu a1, v1, t7",
                "bgtz a1, 0x8002cb90", "subu v0, t8, t7", "slt v0, v0, v1", "beq v0, zero, 0x8002cb90", "move a1, zero",
                "subu v0, t8, v1", "subu a1, t7, v0", "nop", "nop", "nop", "nop"]
    o, n = asm(0x8002CB54, trim_old), asm(0x8002CB54, trim_new)
    for k in range(len(o)):
        if word(0x8002CB54 + 4 * k) != o[k]:
            raise RuntimeError("C94: trim block %08X" % (0x8002CB54 + 4 * k))
    out += [(0x8002CB54 + 4 * k, o[k], n[k], "C94: corner trim from XT / XL %d" % k) for k in range(len(o)) if o[k] != n[k]]
    put(0x8002CC44, "move s7, a1", "lw v0, %d(gp)" % g["XW"], "window width (columns)")
    put(0x8002CC48, "addiu v0, zero, 0x13", "move s7, a1", "window width (moved)")
    put(0x8002D328, "lui v0, 9", "lw v0, %d(gp)" % g["XS"], "PVS row stride")
    put(0x8002D32C, "lw v0, 0x7364(v0)", "lw at, %d(gp)" % g["XW"], "window width (rows)")
    put(0x8002D344, "slti v0, t8, 0x13", "slt v0, t8, at", "rows")
    for pc in (0x8002D224, 0x8002D36C, 0x8002D400, 0x8002D62C):
        put(pc, "lui a0, 0xa", "lw a0, %d(gp)" % g["XLIST"], "object list base")
        put(pc + 4, "addiu a0, a0, 0x76ac", "nop", "object list base (load delay)")
    # window offset (FUN_8002D7C4): camera cell - radius
    put(0x8002D98C, "lui v0, 0xa", "lw t9, %d(gp)" % g["XR"], "radius (v0 still 0xA0000 from 0x8002D984)")
    put(0x8002D994, "addiu s0, s0, -9", "subu s0, s0, t9", "window x0")
    put(0x8002D9A0, "addiu s1, s1, -9", "subu s1, s1, t9", "window z0")
    # ground-tile LOD bands (written every frame by FUN_8002360C)
    put(0x80023A40, "addiu v0, zero, 0x1b58", "lw v0, %d(gp)" % g["XTB1"], "tile mid band")
    put(0x80023A4C, "addiu v0, zero, 0x2328", "lw v0, %d(gp)" % g["XTB2"], "tile far band")
    # primitive buffers (level setup 0x800515BC): bases from XPB0 / XPB1
    put(0x800515BC, "lui v1, 0xd", "lw v1, %d(gp)" % g["XPB0"], "primitive buffer 0")
    put(0x800515C0, "ori v1, v1, 0x8600", "nop", "primitive buffer 0 (load delay)")
    put(0x800515C4, "lui a1, 0xf", "lw a1, %d(gp)" % g["XPB1"], "primitive buffer 1")
    put(0x800515C8, "ori a1, a1, 0x6600", "nop", "primitive buffer 1 (load delay)")
    # C96 car LOD budget (FUN_80014A8C): free = start - 0x1E000 ... assumed Driver 1's buffer size; with bigger buffers
    # (Extra draw distance, Nightmare) the cars went low-detail / undrawn. Now minus the size from XPBN.
    put(0x80014C54, "lui a1, 0xfffe", "lw a1, %d(gp)" % g["XPBN"], "car budget: buffer size (C96)")
    put(0x80014C5C, "ori a1, a1, 0x2000", "nop", "car budget: buffer size (C96)")
    put(0x80014EF4, "lui a1, 0xfffe", "lw a1, %d(gp)" % g["XPBN"], "car budget: buffer size, loop reload (C96)")
    # C97 (cheats 5: 'Quick Replay ends early with cheats, the car takes damage'): while a replay plays (0x80096899, set
    # by the replay load path) Driver 1 skips the whole player block at 0x80025A38, including INVINCIBILITY's damage
    # reset: the replayed car took the damage the recorded one never kept and was wrecked (replay over), e.g. under
    # Nightmare's rams. In a replay the cave now does only the Invincibility reset (same stores), then skips as before.
    cv = C97_CAVE
    code = asm(cv, ["nop", "bne v0, zero, %#x" % (cv + 20), "nop", "j 0x80025a48", "nop",
                    "lw v0, 0xac(gp)", "lui at, 0xa", "beq v0, zero, %#x" % (cv + 64), "addiu at, at, -0x4f5c",
                    "sh zero, 0x17c(at)", "sw zero, 0x128(at)", "sw zero, 0x124(at)", "sw zero, 0x120(at)",
                    "sw zero, 0x11c(at)", "sw zero, 0x118(at)", "sw zero, 0x114(at)",
                    "j 0x80025b94", "nop"])
    assert cv + 4 * len(code) <= C97_CAVE_END
    out += [(cv + 4 * i, word(cv + 4 * i), w, "C97: replay invincibility cave %d" % i) for i, w in enumerate(code)]
    put(0x80025A38, "lbu v0, 0x129(gp)", "j %#x" % cv, "C97: replay check -> cave")
    put(0x80025A3C, "nop", "lbu v0, 0x129(gp)", "C97: replay flag (delay slot)")
    put(0x80025A40, "bne v0, zero, 0x80025b94", "nop", "C97: old replay branch (unreachable, load-delay checker)")
    # C99 HELL (user R60: Nightmare whose chasers drive at double speed and never wreck), word HELL 0x8009342C:
    # pursuit handler 0x80065424: the wreck check (damage car+0x17C >= 0x4651 frees the cop) sees a reset damage, and the
    # pursuit drive value car+0xF0 (written at 0x80065F8C..FD8) is doubled (thrust x 2, linear drag: top speed x 2).
    if word(C99_HELL) != 0:
        raise RuntimeError("C99: HELL word %08X not free" % C99_HELL)
    hv = C99_CAVE
    HG = "%d(gp)" % C99_HELL_GP
    src = ["WRK:", "lw v0, " + HG, "nop", "beq v0, zero, WRK1", "nop", "sh zero, 0x17c(s1)",       # never wreck
           "WRK1:", "lh v0, 0x17c(s1)", "j 0x800654a4", "nop",
           "SPD:", "lw v0, " + HG, "nop", "beq v0, zero, SPD1", "nop",                         # drive value x 2 (x 4
           "lw v0, 0xf0(s1)", "lbu at, 0x12e(s1)", "sll v0, v0, 1", "addiu at, at, -1",          #  when Driver 1 halved
           "bne at, zero, SPD0", "nop", "sll v0, v0, 1",                                         #  it: car +0x12E == 1)
           "SPD0:", "sw v0, 0xf0(s1)",
           "SPD1:", "lw v0, 0x20(s0)", "j 0x80065fe0", "nop",
           "TGT:", "lw v0, 0x24(s0)", "lw at, " + HG, "nop", "beq at, zero, TGT1", "nop",        # target speed x 2
           "sll v0, v0, 1",
           "TGT1:", "j 0x80065f00", "nop",
           "RBA:", "lw v0, 0x6f0(gp)", "lw at, " + HG, "nop", "beq at, zero, RBA1", "nop",       # no rubber band A
           "move v0, zero",
           "RBA1:", "j 0x80065d14", "nop",
           "RBB:", "lw v0, 0x6f8(gp)", "lw at, " + HG, "nop", "or v0, v0, at",                   # no rubber band B
           "j 0x80065e9c", "nop"]
    code = asm(hv, src)
    assert hv + 4 * len(code) <= C99_CAVE_END, hex(hv + 4 * len(code))
    out += [(hv + 4 * i, word(hv + 4 * i), w, "C99: HELL cave %d" % i) for i, w in enumerate(code)]
    lab, k = {}, 0
    for ln in src:                                         # label addresses (asm() takes labels, returns words only)
        if ln.endswith(":"): lab[ln[:-1]] = hv + 4 * k
        else: k += 1
    put(0x8006549C, "lh v0, 0x17c(s1)", "j %#x" % lab["WRK"], "C99: HELL wreck check -> cave")
    put(0x80065FDC, "lw v0, 0x20(s0)", "j %#x" % lab["SPD"], "C99: HELL drive value -> cave")
    put(0x80065EF8, "lw v0, 0x24(s0)", "j %#x" % lab["TGT"], "C99: HELL target speed -> cave")
    put(0x80065D0C, "lw v0, 0x6f0(gp)", "j %#x" % lab["RBA"], "C99: HELL rubber band A -> cave")
    put(0x80065E94, "lw v0, 0x6f8(gp)", "j %#x" % lab["RBB"], "C99: HELL rubber band B -> cave")
    C99_SEEDS[:] = [lab[x] for x in ("WRK", "SPD", "TGT", "RBA", "RBB")]
    return out


# C88 replay header: Driver 1 saves the cheats in the replay header word 0x80097644 bits 0-3 (MCARD.BIN's packer keeps
# the other bits of the old value) and the load path 0x80024868 restores them. New bits 4-7 = LOW GRAVITY 0x8009D8E8,
# INFM, NGHT, SPD2. PACK: every game start / replay start / demo start calls 0x80024F1C; its first word jumps to a pack
# stub (two dead printf strings: primbuf 0x80010954, its reference is gone under CAVE; cellsize 0x80010464, block
# skipped by the 3000 patch) that writes bits 4-7 from the words, then runs the moved prologue and returns. UNPACK: the
# load block 0x80024868..0x80024934 is rewritten gp-relative (same stores, same order) with 4 more stores (nonzero
# values, every reader tests != 0). DEMO: the attract reset 0x80024D0C..0x80024D48 also zeroes the 4 words.
C88_PACK_A, C88_PACK_A_END = 0x80010954, 0x8001098C     # 'you need to allocate at least %d bytes for primbuffers\n'
C88_PACK_B, C88_PACK_B_END = 0x80010464, 0x80010498     # 'Error LevEdit cellsize %d whilst PSX cellsize %d\n'
C88_LOWG_GP, C88_HDR_GP = 0x7178, 0xED4                 # 0x8009D8E8, 0x80097644


def c88_replay_patches(img, base, word):
    s = lambda a, n: bytes(img[a - base: a - base + n])
    if not s(C88_PACK_A, 8) == b"you need" or not s(C88_PACK_B, 8) == b"Error Le":
        raise RuntimeError("C88 replay: pack stub strings not found")
    if word(0x80024F1C) != asm(0x80024F1C, ["addiu sp, sp, -0x40"])[0] or word(0x80024F20) != asm(0x80024F20, ["sw s0, 0x18(sp)"])[0]:
        raise RuntimeError("C88 replay: unexpected 0x80024F1C prologue")
    # bits: 4 LOWG, 5 INFINITE MASS (INFM word bit 0x20), 6 NGHT, 7 SPD2, 8 FEATHER (INFM word bit 0x100)
    a = asm(C88_PACK_A, ["lw t0, %d(gp)" % C88_LOWG_GP, "lw t2, %d(gp)" % C88_NGHT_GP, "lw t3, %d(gp)" % C88_SPD2_GP,
                         "lw t1, %d(gp)" % C88_INFM_GP, "sltu t0, zero, t0", "sltu t2, zero, t2", "sltu t3, zero, t3",
                         "sll t2, t2, 2", "sll t3, t3, 3", "or t0, t0, t2", "or t0, t0, t3", "sll t0, t0, 4",
                         "j %#x" % C106_PACKX, "andi t1, t1, 0x120"])
    b = asm(C88_PACK_B, ["lw t4, %d(gp)" % C88_HDR_GP, "or t0, t0, t1", "andi t5, t4, 0x3f0", "xor t4, t4, t5",
                         "or t4, t4, t0", "sw t4, %d(gp)" % C88_HDR_GP, "j 0x80024f24", "sw s0, 0x18(sp)",
                         # C91 FEATHER tail of the car-car block (entered from S1 FTHR1)
                         "and t2, t2, v0", "sltu v1, zero, t9", "j 0x8001ca50", "and a2, a2, v1"])
    assert C88_PACK_B + 0x20 == 0x80010484
    assert C88_PACK_A + 4 * len(a) <= C88_PACK_A_END and C88_PACK_B + 4 * len(b) <= C88_PACK_B_END, (len(a), len(b))
    out = [(C88_PACK_A + 4 * k, word(C88_PACK_A + 4 * k), w, "C88 replay: pack A %d" % k) for k, w in enumerate(a)]
    out += [(C88_PACK_B + 4 * k, word(C88_PACK_B + 4 * k), w, "C88 replay: pack B %d" % k) for k, w in enumerate(b)]
    # C106 HELL = header bit 9 (pack A -> PACKX: | bit 9 into t1 -> pack B, whose mask now clears bits 4-9; unpack: the
    # load block's closing jal 0x80024F1C -> UNPX: HELL = header & 0x200, then the pack; demo reset: DEMOX zeroes HELL)
    px = asm(C106_PACKX, ["lw t6, %d(gp)" % C99_HELL_GP, "nop", "sltu t6, zero, t6", "sll t6, t6, 9",
                          "j %#x" % C88_PACK_B, "or t1, t1, t6"])
    ux = asm(C106_UNPX, ["lw v1, %d(gp)" % C88_HDR_GP, "nop", "andi v1, v1, 0x200", "j 0x80024f1c",
                         "sw v1, %d(gp)" % C99_HELL_GP])
    assert C106_UNPX + 4 * len(ux) <= 0x800947C8 and C106_PACKX + 4 * len(px) <= C106_UNPX
    for k, w_ in enumerate(px + ux):
        a_ = C106_PACKX + 4 * k
        if word(a_) != 0: raise RuntimeError("C106: %08X not free" % a_)
    out = [(C106_PACKX + 4 * k, 0, w_, "C106: HELL pack/unpack cave %d" % k) for k, w_ in enumerate(px + ux)] + out
    out += [(0x80024F1C, word(0x80024F1C), asm(0x80024F1C, ["j %#x" % C88_PACK_A])[0], "C88 replay: 0x80024F1C -> pack"),
            (0x80024F20, word(0x80024F20), asm(0x80024F20, ["addiu sp, sp, -0x40"])[0], "C88 replay: prologue (delay)")]
    # UNPACK (0x80024868..0x80024934, 52 words; the jal 0x80024F1C at 0x80024938 stays)
    if word(0x80024868) != asm(0x80024868, ["lui a0, 9"])[0] or word(0x80024938) != asm(0x80024938, ["jal 0x80024f1c"])[0]:
        raise RuntimeError("C88 replay: unexpected load block")
    un = ["lbu a0, 0xed0(gp)", "lbu a2, 0xed1(gp)", "lbu a1, 0xed2(gp)", "lw v1, 0xed0(gp)",
          "addiu v0, zero, 1", "sb v0, 0x129(gp)", "sw v0, 0x74(gp)",
          "srl v0, v1, 0x18", "andi v0, v0, 1", "sw v0, 0xe4(gp)",
          "srl v0, v1, 0x19", "andi v0, v0, 1", "sw v0, 0xe8(gp)",
          "srl v0, v1, 0x1c", "andi v0, v0, 3", "sw v0, 0x100(gp)",
          "srl v0, v1, 0x1a", "andi v0, v0, 3", "sw v0, 0x14(gp)",                 # 0x80096784
          "srl v0, v1, 0x1f", "srl v1, v1, 0x1e", "andi v1, v1, 1", "sw v1, 0xac(gp)",
          "lw v1, %d(gp)" % C88_HDR_GP, "sw a0, 0xc4(gp)", "sw a2, 0x84(gp)", "sw a1, 0x98(gp)", "sw v0, 0xb0(gp)",
          "andi v0, v1, 1", "sw v0, 0x716c(gp)",                                    # 0x8009D8DC
          "srl v0, v1, 1", "andi v0, v0, 1", "sw v0, 0x7170(gp)",
          "srl v0, v1, 2", "andi v0, v0, 1", "sw v0, 0x7174(gp)",
          "srl v0, v1, 3", "andi v0, v0, 1", "sw v0, 0x717c(gp)",                   # 0x8009D8EC
          "andi v0, v1, 0x10", "sw v0, %d(gp)" % C88_LOWG_GP,
          "andi v0, v1, 0x120", "sw v0, %d(gp)" % C88_INFM_GP,               # INFINITE MASS 0x20 / FEATHER 0x100
          "andi v0, v1, 0x40", "sw v0, %d(gp)" % C88_NGHT_GP,
          "andi v0, v1, 0x80", "sw v0, %d(gp)" % C88_SPD2_GP,
          "addiu v0, zero, 0x13", "bne a2, v0, 0x80024938", "nop",
          "addiu v0, zero, 2", "sw v0, 0x100(gp)"]
    un = asm(0x80024868, un)
    assert len(un) == 52, len(un)
    out += [(0x80024868 + 4 * k, word(0x80024868 + 4 * k), w, "C88 replay: unpack %d" % k)
            for k, w in enumerate(un) if word(0x80024868 + 4 * k) != w]
    out.append((0x80024938, word(0x80024938), asm(0x80024938, ["jal %#x" % C106_UNPX])[0], "C106: unpack -> HELL, then the pack"))
    # DEMO reset (0x80024D0C..0x80024D48, 16 words; v0 is dead after it)
    if word(0x80024D0C) != asm(0x80024D0C, ["lui v0, 0xa"])[0] or word(0x80024D48) != asm(0x80024D48, ["sw a0, 0x6de4(at)"])[0]:
        raise RuntimeError("C88 replay: unexpected demo reset")
    de = asm(0x80024D0C, ["sw zero, 0x716c(gp)", "sw v1, 0xd4(gp)", "sb v1, 0x125(gp)", "sb v1, 0x129(gp)",
                          "sw v1, 0x100(gp)", "sw v1, 0x14(gp)", "sw zero, 0xb0(gp)", "sw zero, 0xac(gp)",
                          "sw zero, 0x7170(gp)", "sw zero, 0x7174(gp)", "sw zero, 0x717c(gp)",
                          "sw zero, %d(gp)" % C88_INFM_GP, "sw zero, %d(gp)" % C88_NGHT_GP, "sw zero, %d(gp)" % C88_SPD2_GP,
                          "sw a0, 0x674(gp)", "sw zero, %d(gp)" % C88_LOWG_GP])     # 0x80096DE4
    dx = asm(C106_DEMOX, ["sw zero, 0x7170(gp)", "j %#x" % (0x80024D0C + 4 * 10), "sw zero, %d(gp)" % C99_HELL_GP])
    for k in range(3):
        if word(C106_DEMOX + 4 * k) != 0: raise RuntimeError("C106: demo cave %08X not free" % (C106_DEMOX + 4 * k))
    de[8] = asm(0x80024D0C + 4 * 8, ["j %#x" % C106_DEMOX])[0]             # was sw zero, 0x7170(gp) (now in the cave)
    out += [(C106_DEMOX + 4 * k, 0, w_, "C106: demo reset HELL %d" % k) for k, w_ in enumerate(dx)]
    out += [(0x80024D0C + 4 * k, word(0x80024D0C + 4 * k), w, "C88 replay: demo reset %d" % k)
            for k, w in enumerate(de) if word(0x80024D0C + 4 * k) != w]
    return out


# --- C113 shadow near-plane guard (Infrastructure 26.10.) -------------------------------------------------------------
# FUN_8002ADEC projects the car shadow's 4 corners (rtpt + rtps, SZ at sp+0x38/0x3C/0x40/0x44) and adds the quad with
# no near-plane test: a corner at / behind the camera plane (a car beside or under the camera) gives saturated, garbage
# screen coordinates = a big dark one-frame trapezoid. With SNEAR (zero-block word, 0 = Driver 1) the shadow is skipped
# when any corner's SZ < SNEAR. The plugin writes SNEAR (CHI_SHADOW_NEAR, default off). Cave in the zero padding after
# the 0xFFFF-terminated u16 list at 0x8008A2A0 (run 0x8008A2A4..0x8008A464, zero in every dump, no xref; margins kept).
C113_SNEAR, C113_SNEAR_GP = 0x80093438, -0x3338
C113_CAVE, C113_CAVE_END = 0x8008A3C0, 0x8008A440


def c113_patches(exe_path):
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    for a in range(0x8008A2A4, 0x8008A464, 4):
        if word(a) != 0:
            raise RuntimeError("C113: cave word %08X not zero" % a)
    if word(C113_SNEAR) != 0 or word(C113_SNEAR + 4) != 0:
        raise RuntimeError("C113: SNEAR word not free")
    src = ["lw at, %d(gp)" % C113_SNEAR_GP, "nop", "beq at, zero, GO", "nop"]
    for k, off in enumerate((0x38, 0x3C, 0x40, 0x44)):
        src += ["lw v0, %#x(sp)" % off, "nop", "slt v0, v0, at", "bne v0, zero, SKIP", "nop"]
    src += ["GO:", "lui v1, 9", "j 0x8002b058", "lw v1, 0x6834(v1)", "SKIP:", "j 0x8002b1fc", "nop"]
    cw = asm(C113_CAVE, src)
    assert C113_CAVE + 4 * len(cw) <= C113_CAVE_END, hex(C113_CAVE + 4 * len(cw))
    out = [(C113_CAVE + 4 * i, 0, w, "C113: shadow near guard %d" % i) for i, w in enumerate(cw) if w]
    old = asm(0x8002B050, ["lui v1, 9", "lw v1, 0x6834(v1)"])
    new = asm(0x8002B050, ["j %#x" % C113_CAVE, "nop"])
    for k in range(2):
        if word(0x8002B050 + 4 * k) != old[k]:
            raise RuntimeError("C113: shadow site %08X" % (0x8002B050 + 4 * k))
        out.append((0x8002B050 + 4 * k, old[k], new[k], "C113: shadow -> near guard cave %d" % k))
    return out


# --- C114 pursuer indicators (Infrastructure 27.10.) -------------------------------------------------------------------
# FUN_80055820 draws a red triangle on the bottom screen edge (FUN_800555F4) for every AI record in pursuit (state 4)
# with a cop slot (record +5 != 0) in a cone behind the player. Nightmare / Hell make every car a pursuer (slots 5..),
# so the edge fills with popping triangles. PIND (zero-block word, 0 = Driver 1 = every pursuer) limits it to slots
# 1..PIND; the plugin writes 4 (Driver 1's own cop slots) while Nightmare / Hell run if the user picks that.
C114_PIND, C114_PIND_GP = 0x8009343C, -0x3334
C114_CAVE, C114_CAVE_END = 0x8008A300, 0x8008A340


def c114_patches(exe_path):
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    if word(C114_PIND) != 0:
        raise RuntimeError("C114: PIND word not free")
    for a in range(C114_CAVE, C114_CAVE_END, 4):
        if word(a) != 0:
            raise RuntimeError("C114: cave word %08X not zero" % a)
    src = ["lbu v0, 0(s0)", "lw at, %d(gp)" % C114_PIND_GP, "beq v0, zero, SKIP", "nop", "beq at, zero, GO", "nop",
           "addiu v0, v0, -1", "sltu v0, v0, at", "beq v0, zero, SKIP", "nop",
           "GO:", "j 0x800558c0", "addu a0, s1, s5", "SKIP:", "j 0x800559e0", "addu a0, s1, s5"]
    cw = asm(C114_CAVE, src)
    assert C114_CAVE + 4 * len(cw) <= C114_CAVE_END, hex(C114_CAVE + 4 * len(cw))
    out = [(C114_CAVE + 4 * i, 0, w, "C114: pursuer indicator slot limit %d" % i) for i, w in enumerate(cw) if w]
    old = asm(0x800558B0, ["lbu v0, 0(s0)", "nop"])
    new = asm(0x800558B0, ["j %#x" % C114_CAVE, "nop"])
    for k in range(2):
        if word(0x800558B0 + 4 * k) != old[k]:
            raise RuntimeError("C114: site %08X" % (0x800558B0 + 4 * k))
        out.append((0x800558B0 + 4 * k, old[k], new[k], "C114: pursuer indicator -> cave %d" % k))
    return out


# --- C122 pause-menu map for the Driver 2 cities (Infrastructure 27.10.; Analyst study 'Minimap streaming (D2)') ----------
# Driver 1's full map 0x80057AE4 lays CITY 3 out for LA's 192 x 416 overlay (fixed origin, all tiles 1:1 on 512 x 240):
# Chicago (672 x 384) lands off screen, Havana (352 x 544) shows 41 %, and the marker uses LA's constants. With the
# plugin's flag MAPD2 (zero-block word, set while a D2 city with its own minimap frame runs; 0 = Driver 1 unchanged):
#  - cave MAPC (hook 0x80057C40, CITY 3's layout branch): the player's overlay pixel u = x_off + z / scale + K, q = y_off +
#    x / scale + K (table entry 3, as the HUD map 0x800563CC) is put at the screen centre (256, 120): x origin fp =
#    256 - q - sx clamped to [512 - h, 0] (centred when h <= 512), y term l50 = w + 32 - u - 120 + sy clamped to
#    [32, w - 208] (Driver 1's centring when w <= 240); the marker words (sp+0x18 / 0x1C, Driver 1 adds l50 / fp later)
#    get the same transform; d-pad held (0x8009752C: left 0x8000, right 0x2000, up 0x1000, down 0x4000) pans 8 px per
#    frame (MAPSX / MAPSY, reset when the map was not drawn for 60 vblanks; stored clamped). D2-faithful (overmap.c
#    DrawFullscreenMap, non-rotated).
#  - cave MAPW (0x80056310): LoadMapTile's 'CITY 3 skips the x < width test' (east-edge tiles wrap to the next row) only
#    when MAPD2 is 0.
#  - cave MAPK (0x8006C4E8): the map's 'any key closes' ignores the d-pad when MAPD2 is set (D1 cities: any key, as before).
# Caves in the zero run 0x8008A4D0..0x8008A6BC (after the 0xFFFF-terminated u16 list at 0x8008A464; no xrefs). PS1: pure exe
# + one data word (MAPD2 comes from the city's data block on PS1; host plugin today). CHI_C122=0 = off.
C122_MAPD2, C122_MAPD2_GP = 0x80093628, -0x3148
C122_MAPSX_GP, C122_MAPSY_GP, C122_MAPVB_GP = -0x3144, -0x3140, -0x313C
C122_CAVE, C122_CAVE_END = 0x8008A4D0, 0x8008A6A0         # MAPC (the zero run after the list ending 0x8008A4CE; C132 K4 behind it)
C122_MAPW = 0x8001188C                                    # 10 words: the MDEC strings the C60 table used before C120
C122_MAPK, C122_MAPK_END = 0x8008A440, 0x8008A464         # 9 words: zero padding after the C113 cave
C122_K = int(os.environ.get("CHI_C122_K", "49"))     # D1 0x80058278 (CITY 0/5) and D2 WorldToFullscreenMap: + 49


def c122_patches(exe_path):
    if os.environ.get("CHI_C122") == "0":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    for a in list(range(0x8008A4D0, C122_CAVE_END, 4)) + list(range(C122_MAPK, C122_MAPK_END, 4)):
        if word(a) != 0:
            raise RuntimeError("C122: cave word %08X not zero" % a)
    if img[C122_MAPW - 8 - base: C122_MAPW + 4 - base] != b"MDEC_in_sync":
        raise RuntimeError("C122: MAPW site is not the MDEC strings")
    for a in range(C122_MAPD2, C122_MAPD2 + 16, 4):
        if word(a) != 0:
            raise RuntimeError("C122: word %08X not free" % a)
    K = C122_K
    mapc = [
        "lw at, %d(gp)" % C122_MAPD2_GP, "nop", "bne at, zero, D2", "nop",
        # Driver 1's CITY 3 branch (0x80057C40..58), then its own 'sra fp, v0, 1' at 0x80057C5C
        "lw t3, 0x38(sp)", "nop", "subu v0, s1, t3", "lw t4, 0x3c(sp)", "sra v0, v0, 1", "sw v0, 0x40(sp)",
        "j 0x80057c5c", "subu v0, s2, t4",
        "D2:",
        # pan words: reset when the map was not drawn during the last 5 vblanks
        "lui t5, 9", "lw t5, 0x5250(t5)", "lw t6, %d(gp)" % C122_MAPVB_GP, "sw t5, %d(gp)" % C122_MAPVB_GP,
        "subu t6, t5, t6", "sltiu t6, t6, 60", "bne t6, zero, KEEP", "nop",   # a map frame can take several vblanks
        "sw zero, %d(gp)" % C122_MAPSX_GP, "sw zero, %d(gp)" % C122_MAPSY_GP,
        "KEEP:",
        "lui t7, 9", "lhu t7, 0x752c(t7)", "lw t8, %d(gp)" % C122_MAPSX_GP, "lw t9, %d(gp)" % C122_MAPSY_GP,
        "andi at, t7, 0x8000", "srl at, at, 12", "subu t8, t8, at",      # left: -8
        "andi at, t7, 0x2000", "srl at, at, 10", "addu t8, t8, at",      # right: +8
        "andi at, t7, 0x1000", "srl at, at, 9", "subu t9, t9, at",       # up: -8
        "andi at, t7, 0x4000", "srl at, at, 11", "addu t9, t9, at",      # down: +8
        # u = x_off + z / scale + K, q = y_off + x / scale + K (table entry 3 at 0x8008B0C8; player 0x8009B16C / 74)
        "lui v1, 0x8009", "addiu v1, v1, -0x4f38", "lw t3, 0x14(v1)", "lui t4, 0x800a", "lw t5, -0x4e8c(t4)",
        "lw t6, -0x4e94(t4)", "div t5, t3", "mflo t5", "nop", "nop", "div t6, t3", "lw t3, 0(v1)", "lw t4, 4(v1)",
        "mflo t6", "addu t5, t5, t3", "addiu t5, t5, %d" % K, "addu t6, t6, t4", "addiu t6, t6, %d" % K,
        # t5 = u, t6 = q; w, h
        "lw t3, 0x38(sp)", "lw t4, 0x3c(sp)",
        # x: fp = 256 - q - sx, clamped
        "addiu v0, zero, 0x100", "subu v0, v0, t6", "subu v0, v0, t8",
        "addiu at, t4, -0x201", "bgez at, XCL", "nop",
        "addiu v0, zero, 0x200", "subu v0, v0, t4", "j XOK", "sra v0, v0, 1",
        "XCL:", "bltz v0, XLO", "nop", "move v0, zero", "XLO:",
        "addiu at, zero, 0x200", "subu at, at, t4", "slt t7, v0, at", "beq t7, zero, XOK", "nop", "move v0, at",
        "XOK:",
        "addiu at, zero, 0x100", "subu at, at, t6", "subu at, at, v0", "sw at, %d(gp)" % C122_MAPSX_GP,
        # y: l50 = w + 32 - u - 120 + sy, clamped
        "addiu v1, t3, -88", "subu v1, v1, t5", "addu v1, v1, t9",
        "addiu at, t3, -0xf1", "bgez at, YCL", "nop",
        "addiu v1, zero, 0xf0", "subu v1, v1, t3", "j YOK", "sra v1, v1, 1",
        "YCL:", "slti t7, v1, 32", "beq t7, zero, YLO", "nop", "addiu v1, zero, 32", "YLO:",
        "addiu at, t3, -208", "slt t7, at, v1", "beq t7, zero, YOK", "nop", "move v1, at",
        "YOK:",
        "addiu at, t3, -88", "subu at, at, t5", "subu at, v1, at", "sw at, %d(gp)" % C122_MAPSY_GP,
        "sw v1, 0x40(sp)",
        # marker words: sp18 = q + fp - l50, sp1C = w + 32 - u - l50 - fp
        "addu at, t6, v0", "subu at, at, v1", "sw at, 0x18(sp)",
        "addiu at, t3, 32", "subu at, at, t5", "subu at, at, v1", "subu at, at, v0", "sw at, 0x1c(sp)",
        "j 0x80057c5c", "sll v0, v0, 1",
    ]
    mapw = ["lw at, %d(gp)" % C122_MAPD2_GP, "nop", "bne at, zero, TEST", "nop",
            "beq a0, v0, SKIP", "nop", "TEST:", "j 0x80056318", "nop", "SKIP:", "j 0x8005632c", "nop"]
    mapk = ["lui v0, 9", "lhu v0, 0x7538(v0)", "lw at, %d(gp)" % C122_MAPD2_GP, "nop", "beq at, zero, KR", "nop",
            "andi v0, v0, 0x0fff", "KR:", "jr ra", "nop"]
    out = []
    caves = {"MAPC": C122_CAVE, "MAPW": C122_MAPW, "MAPK": C122_MAPK}
    for name, src, end in (("MAPC", mapc, C122_CAVE_END), ("MAPW", mapw, C122_MAPW + 40), ("MAPK", mapk, C122_MAPK_END)):
        at = caves[name]
        cw = asm(at, src)
        assert at + 4 * len(cw) <= end, (name, hex(at + 4 * len(cw)))
        out += [(at + 4 * i, word(at + 4 * i), w, "C122: %s %d" % (name, i)) for i, w in enumerate(cw)
                if w != word(at + 4 * i)]
    sites = [(0x80057C40, ["lw t3, 0x38(sp)", "nop"], ["j %#x" % caves["MAPC"], "nop"], "full map layout"),
             (0x80056310, ["beq a0, v0, 0x8005632c", "nop"], ["j %#x" % caves["MAPW"], "nop"], "LoadMapTile width test"),
             (0x8006C4E8, ["lui v0, 9", "lh v0, 0x7538(v0)"], ["jal %#x" % caves["MAPK"], "nop"], "map close keys")]
    for pc, old_src, new_src, note in sites:
        old, new = asm(pc, old_src), asm(pc, new_src)
        for k in range(len(old)):
            if word(pc + 4 * k) != old[k]:
                raise RuntimeError("C122: site %08X" % (pc + 4 * k))
            out.append((pc + 4 * k, old[k], new[k], "C122: %s %d" % (note, k)))
    return out


# --- C133 pole traffic light glows (Infrastructure 28.10., vegas4: D2 TLIGHT02 = Driver 1's kind 1 TLIGHT01) ---------------
# Driver 1 draws kind 0 (TLIGHT00) and kind 1 (TLIGHT01) glows through ONE helper (0x80053764): only the x offset (a2 at the
# call sites 0x800530E4 / 0x800530F8, plugin glow words) differs, the lens heights (0x800537E4 / F8 / 0x8005380C) and z
# (0x80053814) are shared. LA / Chicago heads sit at one height; Las Vegas' pole light (vegas4) is ~660 lower than its arm
# heads. Cave LGTY (jal from the helper's draw call 0x80053810, a3 = z already set in the delay slot): an x argument
# a1 >= 0x2000 marks kind 1 with its own height (the plugin writes kind 1's x + 0x4000; real offsets stay below +-3000):
# a1 -= 0x4000, y (a2) += LGDY, z (a3) += LGDZ (zero-block words, plugin per city), then on to 0x8004343C. Unmarked x =
# Driver 1 unchanged. PS1: pure exe + 2 data words. CHI_C133=0 = off.
C133_DY, C133_DY_GP = 0x80093638, -0x3138
C133_DZ_GP = -0x3134
C133_CAVE, C133_CAVE_END = 0x8008A378, 0x8008A3C0


def c133_patches(exe_path):
    if os.environ.get("CHI_C133") == "0":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    for a in range(C133_CAVE, C133_CAVE_END, 4):
        if word(a) != 0:
            raise RuntimeError("C133: cave word %08X not zero" % a)
    for a in (C133_DY, C133_DY + 4):
        if word(a) != 0:
            raise RuntimeError("C133: word %08X not free" % a)
    src = ["slti at, a1, 0x2000", "bne at, zero, GO", "nop",
           "addiu a1, a1, -0x4000", "lw at, %d(gp)" % C133_DY_GP, "nop", "addu a2, a2, at",
           "lw at, %d(gp)" % C133_DZ_GP, "nop", "addu a3, a3, at",
           "GO:", "j 0x8004343c", "nop"]
    cw = asm(C133_CAVE, src)
    assert C133_CAVE + 4 * len(cw) <= C133_CAVE_END, hex(C133_CAVE + 4 * len(cw))
    out = [(C133_CAVE + 4 * i, 0, w, "C133: pole light glow height %d" % i) for i, w in enumerate(cw) if w]
    old, new = asm(0x80053810, ["jal 0x8004343c"])[0], asm(0x80053810, ["jal %#x" % C133_CAVE])[0]
    if word(0x80053810) != old:
        raise RuntimeError("C133: site 80053810")
    out.append((0x80053810, old, new, "C133: traffic light glow draw -> LGTY"))
    return out


# --- C132 (c) glow kind 4 = SLIGHT02 in CITY 3 (Infrastructure 28.10., user: the D2 night look) --------------------------
# CITY 3's glow table 0x8008AD7C already holds an unused 5th entry {4, 0, "SLIGHT02", 0} (count word 0x8008AE68 = 4); the
# plugin sets the count to 5 for a D2 city whose level keeps SLIGHT02 resident (Las Vegas), 4 elsewhere (an unresolved entry
# keeps model id 0). CITY 3's dispatch (0x800530C8..DC) knows kinds 0-3 only: its default 'j 0x80053254' now jumps to cave
# K4 (delay slot: at = 4): kind 4 draws ONE lamp glow like kind 2 (0x80053104: 5th arg v1, a0 = s1 set in the delay slot of
# 0x800530D0, a1 / a2 = x / y) at (LX4, LY4) (zero-block words, plugin per city), via 0x800531B0 (jal 0x80042EBC, a3 = 0).
# PS1: pure exe + 2 data words + the count word. CHI_C132=0 = off.
C132_LX4, C132_LX4_GP = 0x80093640, -0x3130
C132_LY4_GP = -0x312C
C132_CAVE, C132_CAVE_END = 0x8008A6A0, 0x8008A6BC


def c132_patches(exe_path):
    if os.environ.get("CHI_C132") == "0":
        return []
    img, base = load_exe(exe_path)
    word = lambda a: struct.unpack_from("<I", img, a - base)[0]
    for a in range(C132_CAVE, C132_CAVE_END, 4):
        if word(a) != 0:
            raise RuntimeError("C132: cave word %08X not zero" % a)
    for a in (C132_LX4, C132_LX4 + 4):
        if word(a) != 0:
            raise RuntimeError("C132: word %08X not free" % a)
    if img[0x8008ADBC - base: 0x8008ADCC - base] != struct.pack("<4I", 4, 0, 0x00010A58, 0) or \
            img[0x80010A58 - base: 0x80010A60 - base] != b"SLIGHT02":
        raise RuntimeError("C132: CITY 3's 5th glow entry is not SLIGHT02")
    src = ["beq a1, at, DO", "sw v1, 0x10(sp)", "j 0x80053254", "nop",
           "DO:", "lw a1, %d(gp)" % C132_LX4_GP, "j 0x800531b0", "lw a2, %d(gp)" % C132_LY4_GP]
    cw = asm(C132_CAVE, src)
    assert C132_CAVE + 4 * len(cw) <= C132_CAVE_END, hex(C132_CAVE + 4 * len(cw))
    out = [(C132_CAVE + 4 * i, 0, w, "C132: glow kind 4 (SLIGHT02) %d" % i) for i, w in enumerate(cw) if w]
    old = asm(0x800530D8, ["j 0x80053254", "nop"])
    new = asm(0x800530D8, ["j %#x" % C132_CAVE, "addiu at, zero, 4"])
    for k in range(2):
        if word(0x800530D8 + 4 * k) != old[k]:
            raise RuntimeError("C132: site %08X" % (0x800530D8 + 4 * k))
        out.append((0x800530D8 + 4 * k, old[k], new[k], "C132: CITY 3 glow dispatch default -> K4 %d" % k))
    return out


# --- C109 libgpu GPU-timeout limit (Infrastructure 27.10., Strategy go: A) ------------------------------------------------
# libgpu's wait helper FUN_764C4 ends a GPU wait after VSync(-1) passes the deadline (+240 vblanks) or after 0xF0000
# iterations. Inside the interrupt handler VSync does not advance, so a queued StoreImage whose 'ready to send VRAM'
# never came spun ~1M iterations (seconds) and the 4 s freeze watchdog ended the game. Normal play never iterates there
# (runner gpuwait: peak 1 iteration in 6000 samples, Miami / Chicago, Nightmare + Extra draw); 0x10000 = libgpu's own
# 'GPU timeout' recovery (queue + GPU command buffer reset, logged as tty: GPU timeout) after well under a second.
C109_TIMEOUT = [(0x80076508, 0x3C02000F, 0x3C020001, "C109: libgpu GPU-timeout iteration limit 0xF0000 -> 0x10000")]


def c109_patches(exe_path):
    img, base = load_exe(exe_path)
    for pc, old, _n, _d in C109_TIMEOUT:
        if struct.unpack_from("<I", img, pc - base)[0] != old:
            raise RuntimeError("C109: unexpected word at %08X" % pc)
    return list(C109_TIMEOUT)


def all_patches(exe_path):
    if "all" in os.environ.get("CHI_EXCLUDE_PATCHES", "").split(","):
        return []                                  # bisection: no engine patches at all
    return (patches(exe_path) + cell_patches(exe_path) + prim_guard_patches(exe_path) + area_patches(exe_path)
            + tile_guard_patches(exe_path) + area_switch_patches(exe_path) + road_decoder_patches(exe_path)
            + c45_skip_patches(exe_path) + look_city_patches(exe_path) + road_limit_patches(exe_path)
            + c42_table_patches(exe_path) + music_select_patches(exe_path) + cosmetics_patches(exe_path)
            + drown_edge_patches(exe_path) + map_clut_patches(exe_path) + near_sub_patches(exe_path)
            + slope_div_patches(exe_path) + moon_gate_patches(exe_path) + chase_table_patches(exe_path) + c68_patches(exe_path) + c67_patches(exe_path)
            + c42e_patches(exe_path) + c66_patches(exe_path) + c42w_patches(exe_path) + c42d_patches(exe_path)
            + c42m_patches(exe_path) + c42l_patches(exe_path) + c42p_patches(exe_path) + c35t_patches(exe_path)
            + sky_dome_patches(exe_path) + s1_clut_patches(exe_path) + s1_slot15_patches(exe_path)
            + s1_cave_patches(exe_path) + s4_patches(exe_path) + c82_patches(exe_path) + c87_patches(exe_path) + c88_patches(exe_path)
            + c94_all(exe_path) + c113_patches(exe_path) + c114_patches(exe_path) + c109_patches(exe_path) + c122_patches(exe_path) + c133_patches(exe_path) + c132_patches(exe_path))


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


def load_delay_hazards(exe_path):
    """C86 (23.10.): R3000 load delay - the instruction right after a load still sees the register's OLD value (the
    recompiler models it). Returns (pc, load word, next word) for every patched load whose next instruction reads it."""
    img, base = load_exe(exe_path)
    img = bytearray(img)
    pat = all_patches(exe_path)
    for a, _o, n, _d in pat:
        struct.pack_into("<I", img, a - base, n)
    W = lambda a: struct.unpack_from("<I", img, a - base)[0]

    def reads(w):
        op, rs, rt = w >> 26, (w >> 21) & 31, (w >> 16) & 31
        if op == 0:
            f = w & 63
            return {rt} if f in (0, 2, 3) else ({rs} if f in (8, 9) else (set() if f in (16, 18) else {rs, rt}))
        if op in (2, 3, 15):
            return set()
        if op in (4, 5, 0x28, 0x29, 0x2A, 0x2B, 0x2E):
            return {rs, rt}
        return {rs}
    out, addrs = [], {p[0] for p in pat}
    for a in sorted(addrs | {x - 4 for x in addrs}):
        w, n = W(a), W(a + 4)
        if w >> 26 in (0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26) and (w >> 16) & 31 and (w >> 16) & 31 in reads(n):
            out.append((a, w, n))
    return out


if __name__ == "__main__":
    import sys
    exe = sys.argv[1]
    hz = load_delay_hazards(exe)
    if hz:
        raise SystemExit("load-delay hazards in the patches (fix before applying): " +
                         ", ".join("%08X %08X->%08X" % h for h in hz))
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
