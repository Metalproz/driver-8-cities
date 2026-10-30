// C129: globals + helpers for d2civ.cpp (host + mipsel; no libc). REDRIVER2 sources: convert.c (Random2), bcollide.c
// (bcollided2d, overlap part dropped: civ_ai calls it with one argument), dr2roads.c (GetSurfaceRoadInfo).
// ratan2 / SquareRoot0 (libgte on the PS1) are integer versions over the same rcossin table, identical in both builds.
#include "compat.h"

const short* rcossin_tbl;
DRIVER2_STRAIGHT* Driver2StraightsPtr;
DRIVER2_CURVE* Driver2CurvesPtr;
DRIVER2_JUNCTION* Driver2JunctionsPtr;
int NumDriver2Straights, NumDriver2Curves, NumDriver2Junctions;
CAR_DATA car_data[MAX_CARS + 2];
PLAYER_SHELL MainPlayer;
int CameraCnt, frameStart;
int gCurrentMissionNumber = -1, numParkedCars, maxParkedCars;
char makeLimoPullOver, limoId, junctionLightsPhase[2];
// makeNextNodeCtrlNode: defined in d2civ.cpp (civ_ai.c)
int test42, test123, test555;
const u_char speedLimits[3] = { 56, 97, 138 };

int Random2(int step) {
    (void)step;
    return RAND((CameraCnt - frameStart) * (CameraCnt - frameStart)) >> 8 & 65535;
}

int SquareRoot0(int x) {                       // floor(sqrt(x)), x >= 0
    if (x <= 0) return 0;
    unsigned int v = (unsigned int)x, r = 0, b = 1u << 30;
    while (b > v) b >>= 2;
    while (b) {
        if (v >= r + b) { v -= r + b; r = (r >> 1) + b; }
        else r >>= 1;
        b >>= 2;
    }
    return (int)r;
}

int ratan2(int y, int x) {                     // angle a (4096 = full turn) with sin(a) ~ y, cos(a) ~ x
    if (x == 0 && y == 0) return 0;
    unsigned int ax = (unsigned int)(x < 0 ? -x : x), ay = (unsigned int)(y < 0 ? -y : y);
    while (ax >= (1u << 19) || ay >= (1u << 19)) { ax >>= 1; ay >>= 1; }
    int lo = 0, hi = 1024;                     // first quadrant: largest t with ay * cos(t) >= ax * sin(t)
    while (lo < hi) {
        int mid = (lo + hi + 1) >> 1;
        if ((int)ay * RCOS(mid) >= (int)ax * RSIN(mid)) lo = mid;
        else hi = mid - 1;
    }
    int t = lo;                                // largest t with tan(t) <= ay / ax: sin(t) ~ ay, cos(t) ~ ax
    int a;
    if (x >= 0 && y >= 0) a = t;
    else if (x < 0 && y >= 0) a = 2048 - t;
    else if (x < 0) a = 2048 + t;
    else a = 4096 - t;
    return a & 4095;
}

int CarHasSiren(int model) { return model == 3; }   // only the Caine's Cash limo branch asks (mission 33: never here)

void ClearMem(char* mem, int length) { for (int i = 0; i < length; i++) mem[i] = 0; }

int bcollided2d(CDATA2D* body, int* boxOverlap) {
    (void)boxOverlap;
    int dtheta, ac, as, i, j, k;
    VECTOR delta;
    dtheta = body[1].theta - body[0].theta;
    for (i = 0; i < 2; i++) {
        as = RSIN(body[i].theta);
        ac = RCOS(body[i].theta);
        body[i].axis[0].vx = as;
        body[i].axis[0].vz = ac;
        body[i].axis[1].vz = -as;
        body[i].axis[1].vx = ac;
    }
    as = RSIN(dtheta & 2047);
    ac = RSIN(dtheta + 1024 & 2047);
    delta.vx = body[0].x.vx - body[1].x.vx;
    delta.vz = body[0].x.vz - body[1].x.vz;
    k = 0;
    i = 1;
    do {
        j = 1;
        do {
            body[i].dist[j] = FIXEDH(body[i].axis[j].vx * delta.vx + body[i].axis[j].vz * delta.vz);
            body[i].limit[j] = body[i].length[j] + FIXEDH(body[k].length[j] * ac + body[k].length[1 - j] * as);
            if (body[i].dist[j] < -body[i].limit[j] || body[i].dist[j] > body[i].limit[j])
                return 0;
            j--;
        } while (j >= 0);
        k++;
        i--;
    } while (i >= 0);
    return 1;
}

int GetSurfaceRoadInfo(DRIVER2_ROAD_INFO* outRoadInfo, int surfId) {
    DRIVER2_CURVE* curve;
    DRIVER2_STRAIGHT* straight;
    DRIVER2_JUNCTION* junction;
    ClearMem((char*)outRoadInfo, sizeof(DRIVER2_ROAD_INFO));
    outRoadInfo->surfId = surfId;
    if (IS_CURVED_SURFACE(surfId)) {
        outRoadInfo->curve = curve = GET_CURVE(surfId);
        outRoadInfo->ConnectIdx = curve->ConnectIdx;
        outRoadInfo->NumLanes = curve->NumLanes;
        outRoadInfo->LaneDirs = curve->LaneDirs;
        outRoadInfo->AILanes = curve->AILanes;
        return 1;
    } else if (IS_STRAIGHT_SURFACE(surfId)) {
        outRoadInfo->straight = straight = GET_STRAIGHT(surfId);
        outRoadInfo->ConnectIdx = straight->ConnectIdx;
        outRoadInfo->NumLanes = straight->NumLanes;
        outRoadInfo->LaneDirs = straight->LaneDirs;
        outRoadInfo->AILanes = straight->AILanes;
        return 1;
    } else if (IS_JUNCTION_SURFACE(surfId)) {
        junction = GET_JUNCTION(surfId);
        outRoadInfo->ConnectIdx = junction->ExitIdx;
    }
    return 0;
}
