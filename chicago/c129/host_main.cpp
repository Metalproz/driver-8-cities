// C129 host reference: drive one Driver 2 civ car along its lanes with the ported civ-AI core (kinematic follow) and
// print the path. Same core / data / route code (route.h) as the mipsel harness (mips_main.cpp) -> outputs must match.
//   host_main ROADS.bin RCOSSIN.bin ROAD_ID [FRAMES=1800] [SPEED=40] [EVERY=15] [LANE=-1 first AI lane]
// ROAD_ID: straight id, or 0x4000|curve. Output lines: frame x z dir road lane ctrl
#include "route.h"
#include <cstdio>
#include <cstdlib>
#include <vector>

static std::vector<char> load(const char* p) {
    std::vector<char> b;
    FILE* f = fopen(p, "rb");
    if (!f) { fprintf(stderr, "cannot open %s\n", p); exit(2); }
    fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
    b.resize(n);
    if (fread(b.data(), 1, n, f) != (size_t)n) exit(2);
    fclose(f);
    return b;
}

void c129_print(int kind, const int* v) {
    if (kind == 0) printf("# road %#x lane %d/%d dir %d start (%d, %d) heading %d\n", v[0], v[1], v[2], v[3], v[4], v[5], v[6]);
    else if (kind == 1) printf("%d %d %d %d %#x %d %d\n", v[0], v[1], v[2], v[3], v[4], v[5], v[6]);
    else if (kind == 2) printf("%d CONFUSED road %#x lane %d\n", v[0], v[1], v[2]);
    else fprintf(stderr, v[0] == 1 ? "not a road: %#x\n" : "no AI lane on %#x\n", v[1]);
}

int main(int argc, char** argv) {
    if (argc < 4) { fprintf(stderr, "usage: host_main ROADS RCOSSIN ROAD_ID [FRAMES] [SPEED] [EVERY] [LANE]\n"); return 2; }
    static std::vector<char> roads = load(argv[1]), tab = load(argv[2]);
    int road = (int)strtol(argv[3], 0, 0);
    int frames = argc > 4 ? atoi(argv[4]) : 1800, speed = argc > 5 ? atoi(argv[5]) : 40, every = argc > 6 ? atoi(argv[6]) : 15;
    int want_lane = argc > 7 ? atoi(argv[7]) : -1;
    c129_bind_roads(roads.data(), (const short*)tab.data());
    return c129_run_route(road, frames, speed, every, want_lane, c129_print);
}
