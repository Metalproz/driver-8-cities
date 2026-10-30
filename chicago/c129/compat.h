// C129: the minimal Driver 2 environment for d2civ.cpp (REDRIVER2 civ_ai.c road following), host + mipsel.
// Types / macros as in REDRIVER2 (dr2types.h, dr2roads.h, dr2math.h, civ_ai.c); CAR_DATA reduced to the fields the
// slice uses. Guest: the adapter (overlay entry) mirrors Driver 1's cars into these shells every frame.
#ifndef C129_COMPAT_H
#define C129_COMPAT_H

typedef unsigned char u_char;
typedef unsigned short u_short;
typedef unsigned int u_int;

#ifndef NULL
#define NULL 0
#endif
#define MAX_CARS 20
#define SPECIAL_CAR_SLOT 4
#define CONTROL_TYPE_NONE 0

struct VECTOR { int vx, vy, vz, pad; };
struct SVECTOR { short vx, vy, vz, pad; };

struct DRIVER2_CURVE {
    int Midx;
    int Midz;
    short start;
    short end;
    short ConnectIdx[4];
    short gradient;
    short height;
    char NumLanes;
    char LaneDirs;
    char inside;
    char AILanes;
};

struct DRIVER2_STRAIGHT {
    int Midx;
    int Midz;
    u_short length;
    short bing;
    short angle;
    short ConnectIdx[4];
    char NumLanes;
    char LaneDirs;
    char AILanes;
    char packing;
};

struct DRIVER2_JUNCTION {
    short ExitIdx[4];
    u_int flags;
};

struct DRIVER2_ROAD_INFO {
    int surfId;
    short* ConnectIdx;
    char NumLanes;
    char LaneDirs;
    char AILanes;
    DRIVER2_STRAIGHT* straight;
    DRIVER2_CURVE* curve;
};

struct CIV_ROUTE_ENTRY {
    short dir;
    u_short pathType;
    int distAlongSegment;
    int x;
    int z;
};

struct CIV_STATE {
    int currentRoad;
    int currentNode;
    CIV_ROUTE_ENTRY* ctrlNode;
    u_char ctrlState;
    u_char trafficLightPhaseId;
    u_char changeLane;
    u_char turnDir;
    char brakeLight;
    u_char oldLane;
    u_char changeLaneCount;
    u_char pad3;
    int turnNode;
    int changeLaneIndicateCount;
    int carPauseCnt;
    int velRatio;
    CIV_ROUTE_ENTRY targetRoute[13];
    CIV_ROUTE_ENTRY* pnode;
    u_char maxSpeed;
    u_char thrustState;
    u_char carMustDie;
    u_char currentLane;
};

enum {
    CIV_AI_CTRL_DRIVE = 0, CIV_AI_CTRL_WAIT_TRAFFIC_LIGHT = 1, CIV_AI_CTRL_YIELD_TURN = 4, CIV_AI_CTRL_PARKED = 5,
    CIV_AI_CTRL_YIELD_STRAIGHT = 6, CIV_AI_CTRL_EMPTY = 7, CIV_AI_CTRL_STOP_AT_NODE = 8, CIV_AI_CTRL_DIED_WITH_MUSIC = 9
};
enum { CIV_AI_THRUST_ACCELERATE = 0, CIV_AI_THRUST_STOP_AT_NODE = 1, CIV_AI_THRUST_STOP = 3, CIV_AI_THRUST_YIELD = 6 };

struct CAR_COSMETICS { SVECTOR colBox; };

struct EXTRA_CIV_DATA {                // only what InitNodeList reads
    int surfInd;
    int distAlongSegment;
    short angle;
    u_short ctrlState;
    int thrustState;
    u_char palette;
    u_char controlFlags;
};

struct CAR_DATA {
    struct {
        struct { int t[3]; } where;
        int direction;
        int wheel_speed;
        struct { VECTOR location; } oBox;
    } hd;
    struct {
        int model;
        CAR_COSMETICS* carCos;
    } ap;
    struct { CIV_STATE c; } ai;
    u_char id;
    u_char controlType;
};

struct CDATA2D {
    VECTOR x;
    VECTOR axis[2];
    VECTOR vel;
    int theta;
    int length[2];
    int dist[2];
    int limit[2];
    int avel;
    int isCameraOrTanner;
};

struct PLAYER_SHELL { int playerCarId; struct { int on; } horn; };

// --- macros (REDRIVER2) -------------------------------------------------------------------------------------------
#define FixHalfRound(x, bits)   (((x) + (1 << (bits - 1))) >> bits)
#define FIXEDH(a)               FixHalfRound(a, 12)
#define RSIN(a)                 (rcossin_tbl[((a) & 4095) * 2])
#define RCOS(a)                 (rcossin_tbl[((a) & 4095) * 2 + 1])
#define RAND(seed)              ((seed) * 0x19660D + 0x3C6EF35F)
#define DIFF_ANGLES_R(A, B, RANGE) (((((B) - (A)) + (RANGE >> 1)) & RANGE - 1) - (RANGE >> 1))
#define DIFF_ANGLES(A, B)       DIFF_ANGLES_R(A, B, 4096)
#define ABS(a)                  fst_abs(a)
static inline int fst_abs(int x) { return x < 0 ? -x : x; }

#define IS_STRAIGHT_SURFACE(surfid) (((surfid) > -1) && ((surfid) & 0xFFFFE000) == 0 && ((surfid) & 0x1FFF) < NumDriver2Straights)
#define IS_CURVED_SURFACE(surfid)   (((surfid) > -1) && ((surfid) & 0xFFFFE000) == 0x4000 && ((surfid) & 0x1FFF) < NumDriver2Curves)
#define IS_JUNCTION_SURFACE(surfid) (((surfid) > -1) && ((surfid) & 0xFFFFE000) == 0x2000 && ((surfid) & 0x1FFF) < NumDriver2Junctions)
#define GET_STRAIGHT(surfid)        (Driver2StraightsPtr + ((surfid) & 0x1FFF))
#define GET_CURVE(surfid)           (Driver2CurvesPtr + ((surfid) & 0x1FFF))
#define GET_JUNCTION(surfid)        (Driver2JunctionsPtr + ((surfid) & 0x1FFF))
#define ROAD_IS_AI_LANE(rd, lane)            ((u_char)(rd)->AILanes >> ((lane) / 2) & 1U)
#define ROAD_LANE_DIRECTION_BIT(rd, lane)    ((u_char)(rd)->LaneDirs >> ((lane) / 2) & 1U)
#define ROAD_LANES_COUNT(rd)                 ((u_int)(rd)->NumLanes & 15)
#define ROAD_WIDTH_IN_LANES(rd)              (ROAD_LANES_COUNT(rd) * 2)
#define ROAD_IS_LEFTMOST_LANE_PARKING(rd)    (((u_char)(rd)->NumLanes & 0x40) != 0)
#define ROAD_IS_RIGHTMOST_LANE_PARKING(rd)   (((u_char)(rd)->NumLanes & 0x80) != 0)
#define ROAD_SPEED_LIMIT(rd)                 (((u_char)(rd)->NumLanes >> 4) & 3)
#define ROAD_LANE_DIR(rd, lane) \
    (((u_char)(rd)->LaneDirs == 0xFF && (rd)->NumLanes == 1) ? ((lane) & 1) : ROAD_LANE_DIRECTION_BIT(rd, lane))
#define ROAD_IS_PARKING_ALLOWED_AT(rd, lane) \
    ((ROAD_IS_LEFTMOST_LANE_PARKING(rd) && (lane) == 0) || (ROAD_IS_RIGHTMOST_LANE_PARKING(rd) && (lane) == ROAD_WIDTH_IN_LANES(rd) - 1))

#define IS_NODE_VALID(cp, node) ((node) >= cp->ai.c.targetRoute && (node) <= cp->ai.c.targetRoute + 12)
#define GET_NEXT_NODE(cp, relNode) (relNode + 1 > cp->ai.c.targetRoute + 12 ? relNode - 12 : relNode + 1)
#define GET_NODE_ID(cp, node) int((node) - cp->ai.c.targetRoute)
#define CIV_STATE_SET_CONFUSED(cp) \
    cp->ai.c.thrustState = CIV_AI_THRUST_STOP; cp->ai.c.ctrlState = CIV_AI_CTRL_EMPTY;

// --- globals (compat.cpp; the guest adapter fills them) ------------------------------------------------------------
extern const short* rcossin_tbl;                // 4096 x (sin, cos), libgte's table (Driver 1's exe holds the same one)
extern DRIVER2_STRAIGHT* Driver2StraightsPtr;
extern DRIVER2_CURVE* Driver2CurvesPtr;
extern DRIVER2_JUNCTION* Driver2JunctionsPtr;
extern int NumDriver2Straights, NumDriver2Curves, NumDriver2Junctions;
extern CAR_DATA car_data[MAX_CARS + 2];
extern PLAYER_SHELL MainPlayer;
extern int CameraCnt, frameStart;
extern int gCurrentMissionNumber, numParkedCars, maxParkedCars;
extern char makeLimoPullOver, limoId, junctionLightsPhase[2];
extern int makeNextNodeCtrlNode;
extern int test42, test123, test555;
extern const u_char speedLimits[3];

int Random2(int step);
int SquareRoot0(int x);
int ratan2(int y, int x);
int CarHasSiren(int model);
void ClearMem(char* mem, int length);
int bcollided2d(CDATA2D* body, int* boxOverlap = 0);
int GetSurfaceRoadInfo(DRIVER2_ROAD_INFO* outRoadInfo, int surfId);

// d2civ.cpp
int GetLeftBoundLane(DRIVER2_ROAD_INFO& roadInfo, int oppDir);
int GetRightBoundLane(DRIVER2_ROAD_INFO& roadInfo, int oppDir);
int GetNextRoadInfo(CAR_DATA* cp, int randomExit, int* turnAngle, int* startDist, CIV_ROUTE_ENTRY* oldNode);
void InitNodeList(CAR_DATA* cp, EXTRA_CIV_DATA* extraData);
void RemapLaneChange(CAR_DATA* cp);
int GetNodePos(DRIVER2_STRAIGHT* straight, DRIVER2_JUNCTION* junction, DRIVER2_CURVE* curve, int distAlongPath,
               CAR_DATA* cp, int* x, int* z, int laneNo);
int CheckChangeLanes(DRIVER2_STRAIGHT* straight, DRIVER2_CURVE* curve, int distAlongSegment, CAR_DATA* cp, int tryToPark);
int CreateNewNode(CAR_DATA* cp);
int CivFindStation(CAR_DATA* cp);
int CivFindPointOnPath(CAR_DATA* cp, int station, VECTOR* ppoint);
int CivSteerAngle(CAR_DATA* cp);

#endif
