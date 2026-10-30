// C129 mipsel harness: the same routes as host_main (route.h) compiled for the PS1 CPU (GCC mipsel, R3000 flags) and
// run by mipsrun (a MIPS I interpreter) -> out/*_mips_paths.txt must equal the host's paths byte for byte.
// Fixed guest memory (mipsrun fills / reads it): 0x80100000 params {count, then count x (road, frames, speed, every,
// lane)}, 0x80110000 rcossin (16 KB), 0x80120000 roads blob, 0x80180000 output {n, then n x 8 ints (kind, v[7])}.
#include "route.h"

#define PARAMS ((const int*)0x80100000)
#define TAB ((const short*)0x80110000)
#define ROADS ((const char*)0x80120000)
#define OUT ((int*)0x80180000)

static void emit(int kind, const int* v) {
    int n = OUT[0];
    if (n >= 60000) return;
    int* r = OUT + 1 + 8 * n;
    r[0] = kind;
    for (int i = 0; i < 7; i++) r[1 + i] = v[i];
    OUT[0] = n + 1;
}

extern "C" int mips_main(void) {
    OUT[0] = 0;
    c129_bind_roads(ROADS, TAB);
    int n = PARAMS[0];
    for (int i = 0; i < n; i++) {
        const int* p = PARAMS + 1 + 5 * i;
        c129_run_route(p[0], p[1], p[2], p[3], p[4], emit);
    }
    return n;
}
