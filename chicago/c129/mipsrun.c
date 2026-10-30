/* C129 mipsrun: a small MIPS I (R3000, little endian) interpreter for the mipsel harness (mips_main.cpp + the core).
 * Runs the flat image at 0x80010000 from its first word until 'break', then prints the harness output exactly like
 * host_main does, so the two outputs can be compared with cmp / diff.
 *   mipsrun IMAGE.bin ROADS.bin RCOSSIN.bin ROAD[:FRAMES:SPEED:EVERY:LANE] ...
 * Branch delay slots are executed; load delays are not modelled (GCC -march=r3000 schedules around them, NOTES
 * "C129 toolchain"). 2 MB of RAM (KSEG0 / KUSEG mirrors). Host-side test tool only. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RAM_SIZE (2u << 20)
static uint8_t ram[RAM_SIZE];
static uint32_t R[32], HI, LO, PC, NPC;
static unsigned long long icount;

static uint32_t phys(uint32_t a) {
    uint32_t p = a & 0x1FFFFFFFu;
    if (p >= RAM_SIZE) { fprintf(stderr, "mipsrun: access %08X out of RAM (pc %08X)\n", a, PC); exit(3); }
    return p;
}
static uint32_t rd32(uint32_t a) { if (a & 3) { fprintf(stderr, "mipsrun: unaligned lw %08X pc %08X\n", a, PC); exit(3); } uint32_t v; memcpy(&v, ram + phys(a), 4); return v; }
static uint16_t rd16(uint32_t a) { if (a & 1) { fprintf(stderr, "mipsrun: unaligned lh %08X pc %08X\n", a, PC); exit(3); } uint16_t v; memcpy(&v, ram + phys(a), 2); return v; }
static uint8_t rd8(uint32_t a) { return ram[phys(a)]; }
static void wr32(uint32_t a, uint32_t v) { if (a & 3) { fprintf(stderr, "mipsrun: unaligned sw %08X pc %08X\n", a, PC); exit(3); } memcpy(ram + phys(a), &v, 4); }
static void wr16(uint32_t a, uint16_t v) { if (a & 1) { fprintf(stderr, "mipsrun: unaligned sh %08X pc %08X\n", a, PC); exit(3); } memcpy(ram + phys(a), &v, 2); }
static void wr8(uint32_t a, uint8_t v) { ram[phys(a)] = v; }

static long loadf(const char* p, uint32_t at, uint32_t max) {
    FILE* f = fopen(p, "rb");
    if (!f) { fprintf(stderr, "mipsrun: cannot open %s\n", p); exit(2); }
    long n = (long)fread(ram + phys(at), 1, max, f);
    fclose(f);
    return n;
}

static int run(void) {
    PC = 0x80010000u; NPC = PC + 4;
    for (;;) {
        uint32_t ins = rd32(PC), pc = PC;
        PC = NPC; NPC = PC + 4;
        icount++;
        uint32_t op = ins >> 26, rs = (ins >> 21) & 31, rt = (ins >> 16) & 31, rdn = (ins >> 11) & 31, sa = (ins >> 6) & 31;
        int32_t simm = (int16_t)(ins & 0xFFFF); uint32_t imm = ins & 0xFFFF;
        uint32_t s = R[rs], t = R[rt], ea = s + (uint32_t)simm, btgt = pc + 4 + ((uint32_t)simm << 2);
        switch (op) {
        case 0x00:
            switch (ins & 63) {
            case 0x00: R[rdn] = t << sa; break;
            case 0x02: R[rdn] = t >> sa; break;
            case 0x03: R[rdn] = (uint32_t)((int32_t)t >> sa); break;
            case 0x04: R[rdn] = t << (s & 31); break;
            case 0x06: R[rdn] = t >> (s & 31); break;
            case 0x07: R[rdn] = (uint32_t)((int32_t)t >> (s & 31)); break;
            case 0x08: NPC = s; break;
            case 0x09: R[rdn] = pc + 8; NPC = s; break;
            case 0x0C: fprintf(stderr, "mipsrun: syscall at %08X\n", pc); return -1;
            case 0x0D: { uint32_t code = (ins >> 6) & 0xFFFFF; if (code) { fprintf(stderr, "mipsrun: break %u at %08X\n", code, pc); return -1; } return (int)R[2]; }
            case 0x10: R[rdn] = HI; break;
            case 0x11: HI = s; break;
            case 0x12: R[rdn] = LO; break;
            case 0x13: LO = s; break;
            case 0x18: { int64_t p = (int64_t)(int32_t)s * (int32_t)t; LO = (uint32_t)p; HI = (uint32_t)((uint64_t)p >> 32); break; }
            case 0x19: { uint64_t p = (uint64_t)s * t; LO = (uint32_t)p; HI = (uint32_t)(p >> 32); break; }
            case 0x1A:
                if (t == 0) { HI = s; LO = (int32_t)s < 0 ? 1u : 0xFFFFFFFFu; }
                else if (s == 0x80000000u && t == 0xFFFFFFFFu) { LO = s; HI = 0; }
                else { LO = (uint32_t)((int32_t)s / (int32_t)t); HI = (uint32_t)((int32_t)s % (int32_t)t); }
                break;
            case 0x1B: if (t == 0) { HI = s; LO = 0xFFFFFFFFu; } else { LO = s / t; HI = s % t; } break;
            case 0x20: case 0x21: R[rdn] = s + t; break;
            case 0x22: case 0x23: R[rdn] = s - t; break;
            case 0x24: R[rdn] = s & t; break;
            case 0x25: R[rdn] = s | t; break;
            case 0x26: R[rdn] = s ^ t; break;
            case 0x27: R[rdn] = ~(s | t); break;
            case 0x2A: R[rdn] = (int32_t)s < (int32_t)t; break;
            case 0x2B: R[rdn] = s < t; break;
            case 0x34: if (s == t) { fprintf(stderr, "mipsrun: teq trap at %08X\n", pc); return -1; } break;
            default: fprintf(stderr, "mipsrun: SPECIAL %02X at %08X\n", ins & 63, pc); return -1;
            }
            break;
        case 0x01:
            switch (rt) {
            case 0x00: if ((int32_t)s < 0) NPC = btgt; break;
            case 0x01: if ((int32_t)s >= 0) NPC = btgt; break;
            case 0x10: R[31] = pc + 8; if ((int32_t)s < 0) NPC = btgt; break;
            case 0x11: R[31] = pc + 8; if ((int32_t)s >= 0) NPC = btgt; break;
            default: fprintf(stderr, "mipsrun: REGIMM %02X at %08X\n", rt, pc); return -1;
            }
            break;
        case 0x02: NPC = (PC & 0xF0000000u) | ((ins & 0x3FFFFFF) << 2); break;
        case 0x03: R[31] = pc + 8; NPC = (PC & 0xF0000000u) | ((ins & 0x3FFFFFF) << 2); break;
        case 0x04: if (s == t) NPC = btgt; break;
        case 0x05: if (s != t) NPC = btgt; break;
        case 0x06: if ((int32_t)s <= 0) NPC = btgt; break;
        case 0x07: if ((int32_t)s > 0) NPC = btgt; break;
        case 0x08: case 0x09: R[rt] = s + (uint32_t)simm; break;
        case 0x0A: R[rt] = (int32_t)s < simm; break;
        case 0x0B: R[rt] = s < (uint32_t)simm; break;
        case 0x0C: R[rt] = s & imm; break;
        case 0x0D: R[rt] = s | imm; break;
        case 0x0E: R[rt] = s ^ imm; break;
        case 0x0F: R[rt] = imm << 16; break;
        case 0x20: R[rt] = (uint32_t)(int8_t)rd8(ea); break;
        case 0x21: R[rt] = (uint32_t)(int16_t)rd16(ea); break;
        case 0x22: { uint32_t w = rd32(ea & ~3u), sh = (ea & 3) * 8; R[rt] = (t & (0x00FFFFFFu >> sh)) | (w << (24 - sh)); break; }   /* lwl */
        case 0x23: R[rt] = rd32(ea); break;
        case 0x24: R[rt] = rd8(ea); break;
        case 0x25: R[rt] = rd16(ea); break;
        case 0x26: { uint32_t w = rd32(ea & ~3u), sh = (ea & 3) * 8; R[rt] = (t & ~(0xFFFFFFFFu >> sh)) | (w >> sh); break; }        /* lwr */
        case 0x28: wr8(ea, (uint8_t)t); break;
        case 0x29: wr16(ea, (uint16_t)t); break;
        case 0x2A: { uint32_t a = ea & ~3u, w = rd32(a), sh = (ea & 3) * 8; wr32(a, (w & ~(0xFFFFFFFFu >> (24 - sh))) | (t >> (24 - sh))); break; }   /* swl */
        case 0x2B: wr32(ea, t); break;
        case 0x2E: { uint32_t a = ea & ~3u, w = rd32(a), sh = (ea & 3) * 8; wr32(a, (w & ~(0xFFFFFFFFu << sh)) | (t << sh)); break; }               /* swr */
        default: fprintf(stderr, "mipsrun: opcode %02X at %08X\n", op, pc); return -1;
        }
        R[0] = 0;
    }
}

int main(int argc, char** argv) {
    if (argc < 5) { fprintf(stderr, "usage: mipsrun IMAGE ROADS RCOSSIN ROAD[:FRAMES:SPEED:EVERY:LANE] ...\n"); return 2; }
    loadf(argv[1], 0x80010000u, 0xF0000u);
    loadf(argv[3], 0x80110000u, 0x10000u);
    loadf(argv[2], 0x80120000u, 0x60000u);
    int n = argc - 4;
    wr32(0x80100000u, (uint32_t)n);
    for (int i = 0; i < n; i++) {
        int v[5] = { 0, 1800, 40, 15, -1 }, k = 0;
        char* p = argv[4 + i];
        while (k < 5 && *p) { v[k++] = (int)strtol(p, &p, 0); if (*p == ':') p++; }
        for (int j = 0; j < 5; j++) wr32(0x80100000u + 4u * (1 + 5 * i + j), (uint32_t)v[j]);
    }
    int r = run();
    if (r < 0) return 3;
    uint32_t cnt = rd32(0x80180000u);
    for (uint32_t i = 0; i < cnt; i++) {
        int v[8];
        for (int j = 0; j < 8; j++) v[j] = (int)rd32(0x80180004u + 32u * i + 4u * j);
        if (v[0] == 0) printf("# road %#x lane %d/%d dir %d start (%d, %d) heading %d\n", v[1], v[2], v[3], v[4], v[5], v[6], v[7]);
        else if (v[0] == 1) printf("%d %d %d %d %#x %d %d\n", v[1], v[2], v[3], v[4], v[5], v[6], v[7]);
        else if (v[0] == 2) printf("%d CONFUSED road %#x lane %d\n", v[1], v[2], v[3]);
        else fprintf(stderr, v[1] == 1 ? "not a road: %#x\n" : "no AI lane on %#x\n", v[2]);
    }
    fprintf(stderr, "mipsrun: %d routes, %u records, %llu instructions\n", r, cnt, icount);
    return 0;
}
