// C129 phase 2: the Driver 2 civ-AI core (d2civ.cpp + compat.cpp, the same sources as the mipsel build) inside the
// driver.chicago plugin, host-side (Strategy 30.10.: no ~50 KB free guest RAM in D2 Take a Ride; M8 host-only list).
// Wrapped in a namespace so the core's globals (car_data, CameraCnt ...) cannot clash with the runtime / generated code.
// The plugin (driver_chicago.c) owns every guest read / write; this file only works in Driver 2 coordinates:
//   c129_roads_load()  the city's road blob ("D2RD", export_roads.py layout) + libgte's rcossin table (from guest RAM)
//   c129_attach()      put AI slot i on the nearest D2 lane point that runs along its heading (PingIn-like placement)
//   c129_step()        one frame of kinematic follow: CivSteerAngle (node upkeep) + CivFindStation + CivFindPointOnPath
//                      at station + speed, heading from the path 256 ahead (= route.h, the host / mipsel reference)
//   c129_detach()      slot free again
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

namespace c129 {
#include "compat.cpp"
#include "d2civ.cpp"
}
using namespace c129;

#define C129_SLOTS 22                           // Driver 1 AI records 0..21 -> car_data[0..21]

static char* s_roads;
static short s_tab[4096 * 2];
static int s_ready;
static uint8_t s_on[C129_SLOTS];

extern "C" int c129_roads_load(const void* blob, uint32_t size, const int16_t* rcossin) {
    s_ready = 0;
    free(s_roads); s_roads = NULL;
    if (!blob || size < 16 || memcmp(blob, "D2RD", 4) != 0) return 0;
    const int* h = (const int*)((const char*)blob + 4);
    if (h[0] <= 0 || h[1] < 0 || h[2] < 0 || 16u + 28u * (uint32_t)(h[0] + h[1]) + 12u * (uint32_t)h[2] > size) return 0;
    s_roads = (char*)malloc(size);
    if (!s_roads) return 0;
    memcpy(s_roads, blob, size);
    memcpy(s_tab, rcossin, sizeof s_tab);
    if (s_tab[0] != 0 || s_tab[1] != 4096 || s_tab[2048] != 4096 || s_tab[2049] != 0) { free(s_roads); s_roads = NULL; return 0; }
    rcossin_tbl = s_tab;
    NumDriver2Straights = h[0]; NumDriver2Curves = h[1]; NumDriver2Junctions = h[2];
    char* p = s_roads + 16;
    Driver2StraightsPtr = (DRIVER2_STRAIGHT*)p; p += 28 * NumDriver2Straights;
    Driver2CurvesPtr = (DRIVER2_CURVE*)p; p += 28 * NumDriver2Curves;
    Driver2JunctionsPtr = (DRIVER2_JUNCTION*)p;
    static CAR_COSMETICS cos = { { 120, 0, 280, 0 } };
    ClearMem((char*)car_data, sizeof car_data);
    for (int i = 0; i < MAX_CARS + 2; i++) { car_data[i].ap.carCos = &cos; car_data[i].id = (u_char)i; }
    memset(s_on, 0, sizeof s_on);
    CameraCnt = 0; frameStart = 0;
    s_ready = 1;
    return 1;
}

extern "C" void c129_reset(void) {
    memset(s_on, 0, sizeof s_on);
    for (int i = 0; i < MAX_CARS + 2; i++) car_data[i].controlType = CONTROL_TYPE_NONE;
}

extern "C" void c129_frame(void) { CameraCnt++; }

static int heading_ok(int lane_dir, int heading) { return ABS(DIFF_ANGLES(lane_dir, heading)) < 1024; }

// Nearest AI lane point (not parking) whose travel direction is within 90 degrees of heading, within maxd. Returns 1 and
// the road / lane / distance along it.
static int find_lane(int x, int z, int heading, int maxd, int* oroad, int* olane, int* odist, int* opx, int* opz) {
    long long best = (long long)maxd * maxd + 1;
    int found = 0;
    for (int i = 0; i < NumDriver2Straights; i++) {
        DRIVER2_STRAIGHT* st = Driver2StraightsPtr + i;
        int dx = x - st->Midx, dz = z - st->Midz;
        if (ABS(dx) > st->length + 8192 || ABS(dz) > st->length + 8192) continue;
        int along = FIXEDH(dx * RSIN(st->angle) + dz * RCOS(st->angle)) + st->length / 2;
        if (along < 64 || along > (int)st->length - 64) continue;
        int lanes = ROAD_WIDTH_IN_LANES(st);
        for (int l = 0; l < lanes; l++) {
            if (!ROAD_IS_AI_LANE(st, l) || ROAD_IS_PARKING_ALLOWED_AT(st, l)) continue;
            int ldir = ROAD_LANE_DIR(st, l) ? (st->angle + 2048) & 4095 : st->angle;
            if (!heading_ok(ldir, heading)) continue;
            int px, pz;
            GetNodePos(st, NULL, NULL, along, NULL, &px, &pz, l);
            long long d = (long long)(px - x) * (px - x) + (long long)(pz - z) * (pz - z);
            if (d < best) { best = d; found = 1; *oroad = i; *olane = l; *odist = along; *opx = px; *opz = pz; }
        }
    }
    for (int i = 0; i < NumDriver2Curves; i++) {
        DRIVER2_CURVE* cv = Driver2CurvesPtr + i;
        int dx = x - cv->Midx, dz = z - cv->Midz;
        int outer = (cv->inside + (cv->NumLanes & 15)) * 1024 + 4096;
        if (ABS(dx) > outer || ABS(dz) > outer) continue;
        int span = (cv->end - cv->start) & 4095;
        int dist = (ratan2(dx, dz) - cv->start) & 4095;
        if (dist > span) continue;
        int lanes = ROAD_WIDTH_IN_LANES(cv);
        for (int l = 0; l < lanes; l++) {
            if (!ROAD_IS_AI_LANE(cv, l) || ROAD_IS_PARKING_ALLOWED_AT(cv, l)) continue;
            int ldir = ROAD_LANE_DIR(cv, l) == 0 ? (dist + cv->start + 1024) & 4095 : (dist + cv->start - 1024) & 4095;
            if (!heading_ok(ldir, heading)) continue;
            int px, pz;
            GetNodePos(NULL, NULL, cv, dist, NULL, &px, &pz, l);
            long long d = (long long)(px - x) * (px - x) + (long long)(pz - z) * (pz - z);
            if (d < best) { best = d; found = 1; *oroad = 0x4000 | i; *olane = l; *odist = dist; *opx = px; *opz = pz; }
        }
    }
    return found;
}

// Attach AI slot `slot` near (x, z) heading `heading` (D2 units / 4096 angle). Out: the lane point and its heading.
extern "C" int c129_attach(int slot, int x, int z, int heading, int maxd, int* ox, int* oz, int* odir, int* oroad, int* olane) {
    if (!s_ready || slot < 0 || slot >= C129_SLOTS) return 0;
    int road, lane, dist, px, pz;
    if (!find_lane(x, z, heading & 4095, maxd, &road, &lane, &dist, &px, &pz)) return 0;
    CAR_DATA* cp = &car_data[slot];
    CAR_COSMETICS* cos = cp->ap.carCos;
    ClearMem((char*)&cp->ai.c, sizeof cp->ai.c);
    cp->ap.carCos = cos;
    cp->controlType = 2;
    cp->ai.c.currentRoad = road;
    cp->hd.where.t[0] = px; cp->hd.where.t[2] = pz;
    cp->hd.oBox.location.vx = px; cp->hd.oBox.location.vz = pz;
    cp->ai.c.currentLane = (u_char)lane;
    cp->ai.c.ctrlState = CIV_AI_CTRL_DRIVE;
    cp->ai.c.turnNode = -1;
    cp->ai.c.ctrlNode = NULL;
    InitNodeList(cp, NULL);
    cp->ai.c.currentLane = (u_char)lane;
    cp->ai.c.pnode = cp->ai.c.targetRoute;
    cp->ai.c.currentNode = 0;
    cp->hd.direction = cp->ai.c.targetRoute[0].dir & 4095;
    s_on[slot] = 1;
    *ox = px; *oz = pz; *odir = cp->hd.direction; *oroad = road; *olane = lane;
    return 1;
}

extern "C" void c129_detach(int slot) {
    if (slot < 0 || slot >= C129_SLOTS) return;
    s_on[slot] = 0;
    car_data[slot].controlType = CONTROL_TYPE_NONE;
}

// One frame: advance `speed` D2 units along the path. Returns 0 when the car is confused (no road ahead: detach it).
extern "C" int c129_step(int slot, int speed, int* ox, int* oz, int* odir, int* oroad, int* olane, int* octrl) {
    if (!s_ready || slot < 0 || slot >= C129_SLOTS || !s_on[slot]) return 0;
    CAR_DATA* cp = &car_data[slot];
    cp->hd.wheel_speed = speed << 12;
    CivSteerAngle(cp);
    if (cp->ai.c.ctrlState == CIV_AI_CTRL_EMPTY) return 0;
    int station = CivFindStation(cp);
    VECTOR pt = { 0, 0, 0, 0 }, ahead = { 0, 0, 0, 0 };
    CivFindPointOnPath(cp, station + speed, &pt);
    CivFindPointOnPath(cp, station + speed + 256, &ahead);
    int dx = ahead.vx - pt.vx, dz = ahead.vz - pt.vz;
    if (dx || dz) cp->hd.direction = ratan2(dx, dz);
    cp->hd.where.t[0] = pt.vx; cp->hd.where.t[2] = pt.vz;
    cp->hd.oBox.location.vx = pt.vx; cp->hd.oBox.location.vz = pt.vz;
    *ox = pt.vx; *oz = pt.vz; *odir = cp->hd.direction; *oroad = cp->ai.c.currentRoad; *olane = cp->ai.c.currentLane;
    *octrl = cp->ai.c.ctrlState;
    return 1;
}

// The road's speed class limit (D2 speedLimits 56 / 97 / 138 units per frame) of the slot's current road.
extern "C" int c129_speed_limit(int slot) {
    if (slot < 0 || slot >= C129_SLOTS || !s_on[slot]) return 0;
    DRIVER2_ROAD_INFO ri;
    if (!GetSurfaceRoadInfo(&ri, car_data[slot].ai.c.currentRoad)) return speedLimits[1];
    return speedLimits[ROAD_SPEED_LIMIT(&ri) < 3 ? ROAD_SPEED_LIMIT(&ri) : 2];
}
