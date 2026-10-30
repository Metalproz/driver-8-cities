// C129: one reference route (kinematic follow along the D2 lanes) for the host harness (host_main.cpp) and the mipsel
// harness (mips_main.cpp): the SAME code in both builds, so "host == mipsel" compares the two compilers / CPUs on the core.
// emit(kind, v[7]): kind 0 = header (road, lane, lanes, dir, x, z, heading), 1 = sample (frame, x, z, dir, road, lane,
// ctrl), 2 = confused (frame, road, lane), 3 = error (code, road).
#ifndef C129_ROUTE_H
#define C129_ROUTE_H
#include "compat.h"

typedef void (*c129_emit_fn)(int kind, const int* v);

static inline void c129_bind_roads(const char* blob, const short* tab) {
    rcossin_tbl = tab;
    const int* h = (const int*)(blob + 4);
    NumDriver2Straights = h[0]; NumDriver2Curves = h[1]; NumDriver2Junctions = h[2];
    const char* p = blob + 16;
    Driver2StraightsPtr = (DRIVER2_STRAIGHT*)p; p += 28 * NumDriver2Straights;
    Driver2CurvesPtr = (DRIVER2_CURVE*)p; p += 28 * NumDriver2Curves;
    Driver2JunctionsPtr = (DRIVER2_JUNCTION*)p;
}

static inline int c129_run_route(int road, int frames, int speed, int every, int want_lane, c129_emit_fn emit) {
    static CAR_COSMETICS cos = { { 120, 0, 280, 0 } };
    int v[7];
    CameraCnt = 0; frameStart = 0;
    ClearMem((char*)car_data, sizeof car_data);
    for (int i = 0; i < MAX_CARS + 2; i++) { car_data[i].ap.carCos = &cos; car_data[i].id = (u_char)i; }
    CAR_DATA* cp = &car_data[1];
    cp->controlType = 2;
    cp->ai.c.currentRoad = road;
    DRIVER2_ROAD_INFO ri;
    if (!GetSurfaceRoadInfo(&ri, road)) { v[0] = 1; v[1] = road; emit(3, v); return 1; }
    int lanes = ROAD_WIDTH_IN_LANES(&ri), lane = -1;
    for (int l = 0; l < lanes && lane < 0; l++)
        if ((want_lane < 0 || l == want_lane) && ROAD_IS_AI_LANE(&ri, l) && !ROAD_IS_PARKING_ALLOWED_AT(&ri, l)) lane = l;
    if (lane < 0) { v[0] = 2; v[1] = road; emit(3, v); return 1; }
    int dir = ROAD_LANE_DIR(&ri, lane);        // 0: along the road's angle / curve start -> end
    int x = 0, z = 0, start;
    if (ri.straight) start = dir ? ri.straight->length - 200 : 200;
    else start = dir ? ((ri.curve->end - ri.curve->start) & 0xfff) - 64 : 64;
    GetNodePos(ri.straight, NULL, ri.curve, start, NULL, &x, &z, lane);
    cp->hd.where.t[0] = x; cp->hd.where.t[2] = z;
    cp->hd.oBox.location.vx = x; cp->hd.oBox.location.vz = z;
    cp->ai.c.currentLane = (u_char)lane;
    cp->ai.c.ctrlState = CIV_AI_CTRL_DRIVE;
    cp->ai.c.turnNode = -1;
    cp->ai.c.ctrlNode = NULL;
    InitNodeList(cp, NULL);
    cp->ai.c.currentLane = (u_char)lane;        // InitNodeList recomputes it from the position on straights
    cp->ai.c.pnode = cp->ai.c.targetRoute;
    cp->ai.c.currentNode = 0;
    cp->hd.direction = cp->ai.c.targetRoute[0].dir;
    v[0] = road; v[1] = lane; v[2] = lanes; v[3] = dir; v[4] = x; v[5] = z; v[6] = cp->hd.direction;
    emit(0, v);
    for (int f = 0; f < frames; f++) {
        CameraCnt++;
        cp->hd.wheel_speed = speed << 12;
        CivSteerAngle(cp);
        if (cp->ai.c.ctrlState == CIV_AI_CTRL_EMPTY) {
            v[0] = f; v[1] = cp->ai.c.currentRoad; v[2] = cp->ai.c.currentLane; emit(2, v); break;
        }
        int station = CivFindStation(cp);
        VECTOR pt = { 0, 0, 0, 0 }, ahead = { 0, 0, 0, 0 };
        CivFindPointOnPath(cp, station + speed, &pt);
        CivFindPointOnPath(cp, station + speed + 256, &ahead);
        int dx = ahead.vx - pt.vx, dz = ahead.vz - pt.vz;
        if (dx || dz) cp->hd.direction = ratan2(dx, dz);
        cp->hd.where.t[0] = pt.vx; cp->hd.where.t[2] = pt.vz;
        cp->hd.oBox.location.vx = pt.vx; cp->hd.oBox.location.vz = pt.vz;
        if (f % every == 0) {
            v[0] = f; v[1] = pt.vx; v[2] = pt.vz; v[3] = cp->hd.direction; v[4] = cp->ai.c.currentRoad;
            v[5] = cp->ai.c.currentLane; v[6] = cp->ai.c.ctrlState;
            emit(1, v);
        }
    }
    return 0;
}
#endif
