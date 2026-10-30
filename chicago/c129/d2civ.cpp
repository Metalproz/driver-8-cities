// C129: Driver 2 civ-AI road following, cut from REDRIVER2 src_rebuild/Game/C/civ_ai.c lines 242-1494 (verbatim)
// plus GetSurfaceRoadInfo (dr2roads.c). Built for the host (reference) and mipsel (guest overlay). See NOTES "C129 plan".
#include "compat.h"

int GetLeftBoundLane(DRIVER2_ROAD_INFO& roadInfo, int oppDir)
{
	int i, laneCount, laneNo;

	laneCount = ROAD_WIDTH_IN_LANES(&roadInfo);
	laneNo = laneCount;

	for (i = laneNo - 1; i >= 0; i--)
	{
		if (ROAD_IS_AI_LANE(&roadInfo, i) && !ROAD_IS_PARKING_ALLOWED_AT(&roadInfo, i))
		{
			test42 = ROAD_LANE_DIR(&roadInfo, i) ^ 1;
			laneNo = i;

			if (test42 == 0)
			{
				if (oppDir != 0)
					break;
			}
			else
			{
				if (oppDir == 0)
					break;
			}
		}
	}

	return laneNo;
};

int GetRightBoundLane(DRIVER2_ROAD_INFO& roadInfo, int oppDir)
{
	int i, laneCount, laneNo;

	laneCount = ROAD_WIDTH_IN_LANES(&roadInfo);
	laneNo = ROAD_IS_LEFTMOST_LANE_PARKING(&roadInfo);

	for (i = laneNo; i < laneCount; i++)
	{
		if (ROAD_IS_AI_LANE(&roadInfo, i) && !ROAD_IS_PARKING_ALLOWED_AT(&roadInfo, i))
		{
			test555 = ROAD_LANE_DIR(&roadInfo, i) ^ 1;
			laneNo = i;

			if (test555 == 0)
			{
				if (oppDir != 0)
					break;
			}
			else
			{
				if (oppDir == 0)
					break;
			}
		}
	}

	return laneNo;
}

// [D] [T]
int GetNextRoadInfo(CAR_DATA* cp, int randomExit, int* turnAngle, int* startDist, CIV_ROUTE_ENTRY* oldNode)
{
	u_int junctionFlags;
	DRIVER2_JUNCTION* jn;

	DRIVER2_ROAD_INFO currentRoadInfo;
	DRIVER2_ROAD_INFO roadInfo;

	int tmpNewRoad[2];
	int tmpNewLane[2];
	int laneFit[2];
	short validExitIdx[4];

	int newRoad, newLane, newExit, numExits;
	int currentRoadId, leftLane, rightLane;

	int oppDir, oldOppDir;
	int turnDir, currentLaneDir;

	currentRoadId = cp->ai.c.currentRoad;

	if (GetSurfaceRoadInfo(&currentRoadInfo, currentRoadId))
	{
		int laneNo;

		currentLaneDir = ROAD_LANE_DIR(&currentRoadInfo, cp->ai.c.currentLane);

		if (currentRoadInfo.straight)
		{
			oldOppDir = (currentRoadInfo.straight->angle - oldNode->dir) + 1024U & 2048;
		}
		else
		{
			int dx, dz;
			dx = oldNode->x - currentRoadInfo.curve->Midx;
			dz = oldNode->z - currentRoadInfo.curve->Midz;

			oldOppDir = DIFF_ANGLES(ratan2(dx, dz), oldNode->dir);
			oldOppDir = (oldOppDir < 1) * 2048;
		}

		// first road is picked from road direction
		tmpNewRoad[0] = currentRoadInfo.ConnectIdx[(oldOppDir > 0) * 2];

		// and second picked from lane direction
		tmpNewRoad[1] = currentRoadInfo.ConnectIdx[(currentLaneDir > 0) ? 3 : 1];
		laneNo = GetLeftBoundLane(currentRoadInfo, currentLaneDir);

		if (oldOppDir == 0)
			leftLane = laneNo;
		else
			rightLane = laneNo;

		laneNo = GetRightBoundLane(currentRoadInfo, currentLaneDir);

		if (oldOppDir != 0)
			leftLane = laneNo;
		else
			rightLane = laneNo;
	}

	newLane = -1;
	
	if (IS_JUNCTION_SURFACE(tmpNewRoad[0]))
	{
		int exitFrom, exitCnt, bestExit;
		int rnd;
		
		cp->ai.c.changeLaneCount = 0;
		jn = GET_JUNCTION(tmpNewRoad[0]);

		exitFrom = -1;	// best exit id

		// check if road is valid for this junction
		// by determining connection with junction
		for(exitCnt = 0; exitCnt < 4; exitCnt++)
		{
			if(jn->ExitIdx[exitCnt] == currentRoadId)
			{
				exitFrom = exitCnt;
				break;
			}
		}

		if (exitFrom == -1)
		{
			CIV_STATE_SET_CONFUSED(cp);
			return 0;
		}

		// check directions of exits
		numExits = 0;

		// only need 3 cycles because we don't want make U-turns
		for (exitCnt = 0; exitCnt < 3; exitCnt++)
		{
			int exitSurfId, exitIdx, valid;

			exitIdx = (exitFrom + exitCnt + 1) % 4;
			
			valid = 0;
			exitSurfId = jn->ExitIdx[exitIdx];
			
			if (exitSurfId != -1)
			{
				int turnAng;
				int exitDir;
				exitDir = ((exitIdx + 4) - exitFrom) % 4;

				if (exitDir == 1)
					turnAng = -1024;	// left
				else if (exitDir == 2)
					turnAng = 0;		// forward
				else if (exitDir == 3)
					turnAng = 1024;	// right
				else
					turnAng = 0;		// forward again?

				test123 = 666;
				test555 = 666;
				test42 = 666;

				// current node direction and new direction
				turnDir = oldNode->dir + turnAng;

				if (GetSurfaceRoadInfo(&roadInfo, exitSurfId))
				{
					int dx, dz;
					int numLanes;

					numLanes = ROAD_WIDTH_IN_LANES(&roadInfo);

					if(roadInfo.straight)
					{
						oppDir = (roadInfo.straight->angle - turnDir) + 1024U & 2048;
					}
					else
					{
						dx = oldNode->x - roadInfo.curve->Midx;
						dz = oldNode->z - roadInfo.curve->Midz;

						oppDir = DIFF_ANGLES(ratan2(dx, dz), turnDir);
						oppDir = (oppDir < 1) * 2048;
					}
			
					if (turnAng == 0) // going forward
					{
						if (oppDir != oldOppDir) // next road is flipped
							newLane = numLanes - (cp->ai.c.currentLane + 1);
						else
							newLane = cp->ai.c.currentLane;
					}
					else if (turnAng == -1024) // going left
					{
						newLane = GetRightBoundLane(roadInfo, oppDir);
					}
					else if (turnAng == 1024)
					{
						newLane = GetLeftBoundLane(roadInfo, oppDir);
					}

					// validate lane
					if (newLane >= 0 && newLane < numLanes)
					{
						valid = ROAD_IS_AI_LANE(&roadInfo, newLane) && !ROAD_IS_PARKING_ALLOWED_AT(&roadInfo, newLane);
					}

					if (oppDir != oldOppDir)
					{
						if (currentLaneDir == ROAD_LANE_DIR(&roadInfo, newLane))
							valid = 0;
					}
					else
					{
						if (currentLaneDir != ROAD_LANE_DIR(&roadInfo, newLane))
							valid = 0;
					}
				}
			}

			if (valid)
			{
				validExitIdx[exitCnt] = exitIdx;
				numExits++;
			}
			else
			{
				validExitIdx[exitCnt] = 42;
			}
		}

		if (leftLane != rightLane && numExits != 1 && ROAD_LANES_COUNT(&currentRoadInfo) > 1)
		{
			if (cp->ai.c.currentLane == leftLane)
			{
				if (validExitIdx[2] != 42)
					numExits--;
				
				validExitIdx[2] = 42;
			}
			else if (cp->ai.c.currentLane == rightLane)
			{
				if (validExitIdx[0] != 42)
					numExits--;
				
				validExitIdx[0] = 42;
			}
			else if (validExitIdx[1] != 42)
			{
				if (validExitIdx[0] != 42)
					numExits--;
				
				if (validExitIdx[2] != 42)
					numExits--;
				
				validExitIdx[2] = 42;
				validExitIdx[0] = 42;
			}
		}

		if (numExits == 0)
		{
			CIV_STATE_SET_CONFUSED(cp);
			return 0;
		}
		
		// randomize exit selection
		rnd = Random2(0) % 3;

		do
		{
			bestExit = validExitIdx[rnd % 3];
			rnd++;
		} while (bestExit == 42);
		
		newRoad = jn->ExitIdx[bestExit];

		{
			int invExit;
			invExit = (bestExit + 4 - exitFrom) % 4;

			if (invExit == 1)
				*turnAngle = -1024;
			else if (invExit > 1 && invExit != 2 && invExit == 3)
				*turnAngle = 1024;
			else
				*turnAngle = 0;

			test42 = exitFrom;
			test555 = bestExit;
		}

		junctionFlags = jn->flags;

		// manage states
		if (cp->ai.c.ctrlState != CIV_AI_CTRL_STOP_AT_NODE)
		{
			if (junctionFlags & 1)
			{
				// wait for traffic light
				cp->ai.c.trafficLightPhaseId = (exitFrom & 1);
				cp->ai.c.ctrlState = CIV_AI_CTRL_WAIT_TRAFFIC_LIGHT;

				if (junctionLightsPhase[exitFrom & 1] == 3)
				{
					if (*turnAngle != 0)
						cp->ai.c.ctrlNode = oldNode;
					else
						cp->ai.c.ctrlState = CIV_AI_CTRL_YIELD_STRAIGHT;
				}
				else
					cp->ai.c.ctrlNode = oldNode;
			}
			else
			{
				int yield = 0;

				if (exitFrom == 0 || exitFrom == 2)
					yield = 1;

				if (junctionFlags & 2)
				{
					if (yield || *turnAngle != 0)
					{
						cp->ai.c.ctrlNode = oldNode;
						cp->ai.c.ctrlState = CIV_AI_CTRL_YIELD_TURN;
					}
					else
						cp->ai.c.ctrlState = CIV_AI_CTRL_YIELD_STRAIGHT;
				}
				else
				{
					if (!yield || *turnAngle != 0)
					{
						cp->ai.c.ctrlNode = oldNode;
						cp->ai.c.ctrlState = CIV_AI_CTRL_YIELD_TURN;
					}
					else
						cp->ai.c.ctrlState = CIV_AI_CTRL_YIELD_STRAIGHT;
				}
			}
		}

		if(!GetSurfaceRoadInfo(&roadInfo, newRoad))
		{
			CIV_STATE_SET_CONFUSED(cp);
			return 0;
		}

		turnDir = oldNode->dir + *turnAngle;

		// determine the new lane on the new road
		{
			int numLanes, turnAng;

			numLanes = ROAD_WIDTH_IN_LANES(&roadInfo);
			turnAng = *turnAngle;

			if (roadInfo.straight)
			{
				oppDir = (turnDir - roadInfo.straight->angle) + 1024 & 2048;
			}
			else
			{
				int dx, dz;
				dx = oldNode->x - roadInfo.curve->Midx;
				dz = oldNode->z - roadInfo.curve->Midz;

				oppDir = DIFF_ANGLES(ratan2(dx, dz), turnDir);
				oppDir = (oppDir < 1) * 2048;
			}

			if (turnAng == 0)
			{
				//printWarning("car %d check forward lane\n", cp->id);
				
				if (oppDir == oldOppDir)
					newLane = cp->ai.c.currentLane;
				else
					newLane = numLanes - (cp->ai.c.currentLane + 1);

				if (ROAD_LANE_DIR(&roadInfo, newLane))
				{
					if (oppDir == 0)
						newLane = -1;
				}
				else
				{
					if (oppDir != 0)
						newLane = -1;
				}

				if (!ROAD_IS_AI_LANE(&roadInfo, newLane))
					newLane = -1;
			}
			else if (turnAng == -1024)
			{
				newLane = GetRightBoundLane(roadInfo, oppDir);
			}
			else if (turnAng == 1024)
			{
				newLane = GetLeftBoundLane(roadInfo, oppDir);
			}


			if (*turnAngle != 0)
			{
				if (numLanes - 1 == newLane)
				{
					// [A] might be incorrect
					if (ROAD_LANE_DIR(&roadInfo, newLane) == ROAD_LANE_DIR(&roadInfo, newLane - 1))
						newLane = newLane - 1;
				}
				else if (newLane == 0)
				{
					// [A] might be incorrect
					if (ROAD_LANE_DIR(&roadInfo, 0) == ROAD_LANE_DIR(&roadInfo, newLane + 1))
						newLane = newLane + 1;
				}
			}
		}
	}
	else
	{
		// road continuation using connections
		int roadCnt;
		
		if (turnAngle == NULL)
		{
			CIV_STATE_SET_CONFUSED(cp);
			return 0;
		}

		*turnAngle = 0;
		newExit = -1;
		numExits = 0;
		
		if (tmpNewRoad[0] != -1)
			numExits++;
		
		if (tmpNewRoad[1] != -1)
			numExits++;

		// check the connections
		// determine new lanes on possible new roads based on the old node position
		for (roadCnt = 0; roadCnt < 2; roadCnt++)
		{
			if (tmpNewRoad[roadCnt] != -1)
			{
				int px, pz;
				int dx, dz;
				int numLanes;

				numLanes = 0;

				// [A] fix lane changingg issues
				if(cp->ai.c.changeLaneCount > 0)
				{
					GetNodePos(currentRoadInfo.straight, NULL, currentRoadInfo.curve, oldNode->distAlongSegment, NULL, &px, &pz, cp->ai.c.currentLane);
				}
				else
				{
					px = oldNode->x;
					pz = oldNode->z;
				}

				if (GetSurfaceRoadInfo(&roadInfo, tmpNewRoad[roadCnt]))
				{
					numLanes = ROAD_WIDTH_IN_LANES(&roadInfo);

					// determine new lane by old node position
					if(roadInfo.straight)
					{
						dx = (px - roadInfo.straight->Midx);
						dz = (pz - roadInfo.straight->Midz);

						tmpNewLane[roadCnt] = ROAD_LANES_COUNT(&roadInfo)
											- (FIXEDH(dx * RCOS(roadInfo.straight->angle) - dz * RSIN(roadInfo.straight->angle)) + 512 >> 9);

					}
					else
					{
						dx = px - roadInfo.curve->Midx;
						dz = pz - roadInfo.curve->Midz;

						tmpNewLane[roadCnt] = (SquareRoot0(dx * dx + dz * dz) >> 9) - roadInfo.curve->inside * 2;
					}
				}

				// [A] if there are more than one connections we check the bounds strictly
				if(numExits > 1)
				{
					if (tmpNewLane[roadCnt] < 0 || tmpNewLane[roadCnt] >= numLanes)
					{
						laneFit[roadCnt] = 666;
						numExits--;	// there has to be one exit
						continue;
					}
				}

				// fit new lane
				newLane = tmpNewLane[roadCnt];

				if (newLane < 0)
					laneFit[roadCnt] = 0;
				else if (newLane <= numLanes - 1)
					laneFit[roadCnt] = 0;
				else
					laneFit[roadCnt] = newLane - numLanes - 1;

				// clamp lane
				if (tmpNewLane[roadCnt] >= numLanes - 1)
					tmpNewLane[roadCnt] = numLanes - 1;

				if (tmpNewLane[roadCnt] < 0)
					tmpNewLane[roadCnt] = 0;
				
				// set this a s correct exit
				newExit = roadCnt;
			}
			else
			{
				laneFit[roadCnt] = 666;
			}
		}

		if (newExit == -1 || laneFit[newExit] == 666)
		{
			CIV_STATE_SET_CONFUSED(cp);
			return 0;
		}

		newExit = (ABS(laneFit[0]) < ABS(laneFit[1])) ^ 1;
	
		newRoad = tmpNewRoad[newExit];
		newLane = tmpNewLane[newExit];
		
		if (cp->ai.c.ctrlState != CIV_AI_CTRL_EMPTY)
		{
			// [A] removed old lane fitting code
			
			if (laneFit[newExit] != 0)
			{
				cp->ai.c.turnNode = GET_NODE_ID(cp, GET_NEXT_NODE(cp, oldNode));
				cp->ai.c.turnDir = ROAD_LANE_DIR(&roadInfo, laneFit[newExit]);				
			}
		}
	}

	if (newLane < 0)
	{
		CIV_STATE_SET_CONFUSED(cp);
		return 0;
	}

	// determine distance and speed limit
	if (startDist != NULL)
	{
		if (GetSurfaceRoadInfo(&roadInfo, newRoad))
		{
			if(roadInfo.straight)
			{
				if (ROAD_LANE_DIR(&roadInfo, newLane))
					*startDist = roadInfo.straight->length;
				else
					*startDist = 0;
			}
			else
			{
				if (ROAD_LANE_DIR(&roadInfo, newLane))
					*startDist = roadInfo.curve->end - roadInfo.curve->start & 0xfff;
				else
					*startDist = 0;
			}

			cp->ai.c.maxSpeed = speedLimits[ROAD_SPEED_LIMIT(&roadInfo)];
		}
	}

	if (newRoad < 0)
	{
		CIV_STATE_SET_CONFUSED(cp);
		return 0;
	}

	cp->ai.c.currentLane = newLane;

	return newRoad;
}

// [D] [T]
void InitNodeList(CAR_DATA* cp, EXTRA_CIV_DATA* extraData)
{
	int dx; // $s1
	int dz; // $s2
	int i;
	DRIVER2_CURVE* curve;
	DRIVER2_STRAIGHT* straight;
	int surfInd;

	CIV_ROUTE_ENTRY* cr;
	cr = cp->ai.c.targetRoute;

	for (i = 0; i < 13; i++)
	{
		cr->pathType = 127;
		cr->x = 0;
		cr->z = 0;
		cr++;
	}

	cr = &cp->ai.c.targetRoute[0];

	cr->pathType = 1;
	cr->x = cp->hd.where.t[0];
	cr->z = cp->hd.where.t[2];

	surfInd = cp->ai.c.currentRoad;

	if (IS_STRAIGHT_SURFACE(surfInd))
	{
		int theta; // $s0
		int laneDist; // $s1

		straight = GET_STRAIGHT(surfInd);

		dx = cp->hd.where.t[0] - straight->Midx;
		dz = cp->hd.where.t[2] - straight->Midz;

		theta = straight->angle - ratan2(dx, dz);
		cr->distAlongSegment = (straight->length / 2) + FIXEDH(RCOS(theta) * SquareRoot0(dx * dx + dz * dz));

		laneDist = ROAD_LANES_COUNT(straight) * 512 + FIXEDH(-dx * RCOS(straight->angle) + dz * RSIN(straight->angle));
		cp->ai.c.currentLane = laneDist / 512;

		// calc all dirs
		if (ROAD_LANE_DIR(straight, cp->ai.c.currentLane))
			cr->dir = straight->angle + 2048U & 0xfff;
		else
			cr->dir = straight->angle;
	}
	else if (IS_CURVED_SURFACE(surfInd))
	{
		if (extraData == NULL)
		{
			curve = GET_CURVE(surfInd);

			cr->distAlongSegment = (ratan2(cr->x - curve->Midx, cr->z - curve->Midz) & 0xfff) - curve->start;

			if (curve->inside < 10)
				cr->distAlongSegment &= 0xf80;
			else if (curve->inside < 20)
				cr->distAlongSegment &= 0xfc0;
			else
				cr->distAlongSegment &= 0xfe0;

			if (ROAD_LANE_DIR(curve, cp->ai.c.currentLane) == 0)
				cr->dir = (cr->distAlongSegment + curve->start) + 1024;
			else
				cr->dir = (cr->distAlongSegment + curve->start) - 1024;
		}
		else
		{
			cr->distAlongSegment = extraData->distAlongSegment;
			cr->dir = extraData->angle;
		}
	}

	if (extraData != NULL)
		cr->distAlongSegment = extraData->distAlongSegment;
}

// [A] bug fixes the incorrect lane changes
void RemapLaneChange(CAR_DATA* cp)
{
	CIV_ROUTE_ENTRY* currentNode;
	DRIVER2_ROAD_INFO roadInfo;
	int numLanes, dx, dz;
	int newLane;

	if (!GetSurfaceRoadInfo(&roadInfo, cp->ai.c.currentRoad))
		return;

	currentNode = &cp->ai.c.targetRoute[cp->ai.c.currentNode];
	numLanes = ROAD_WIDTH_IN_LANES(&roadInfo);

	// determine lane on new road by old node position
	if (roadInfo.straight)
	{
		dx = (currentNode->x - roadInfo.straight->Midx);
		dz = (currentNode->z - roadInfo.straight->Midz);

		newLane = ROAD_LANES_COUNT(&roadInfo)
			- (FIXEDH(dx * RCOS(roadInfo.straight->angle) - dz * RSIN(roadInfo.straight->angle)) + 512 >> 9);
	}
	else
	{
		dx = currentNode->x - roadInfo.curve->Midx;
		dz = currentNode->z - roadInfo.curve->Midz;

		newLane = (SquareRoot0(dx * dx + dz * dz) >> 9) - roadInfo.curve->inside * 2;
	}

	cp->ai.c.currentLane = newLane;
}

// [D] [T]
int GetNodePos(DRIVER2_STRAIGHT* straight, DRIVER2_JUNCTION* junction, DRIVER2_CURVE* curve, int distAlongPath, CAR_DATA* cp, int* x, int* z, int laneNo)
{
	u_char oldLane, changeLaneCount;
	int angle;
	int distFromCentre;
	int sideShift;
	int radius;

	if (cp)
	{
		oldLane = cp->ai.c.oldLane;
		changeLaneCount = cp->ai.c.changeLaneCount;
	}
	else
	{
		oldLane = 0;
		changeLaneCount = 0;
	}

	if (straight)
	{
		angle = straight->angle;
		distFromCentre = distAlongPath - (straight->length / 2);

		if (angle < 2048)
		{
			if (laneNo <= oldLane)
				test42 = -changeLaneCount * 128;
			else
				test42 = changeLaneCount * 128;

			sideShift = (ROAD_LANES_COUNT(straight) * 512 - (laneNo * 512 + 256)) + test42;

			*x = straight->Midx + FIXEDH(distFromCentre * RSIN(angle)) +
								  FIXEDH(sideShift * RCOS(angle));

			*z = straight->Midz + FIXEDH(distFromCentre * RCOS(angle)) -
								  FIXEDH(sideShift * RSIN(angle));
		}
		else if (cp)
		{
			CIV_STATE_SET_CONFUSED(cp);
			return 0;
		}
	}
	else if (curve)
	{
		angle = distAlongPath + curve->start;

		if (oldLane <= laneNo)
			test42 = -changeLaneCount * 128;
		else
			test42 = changeLaneCount * 128;

		radius = curve->inside * 1024 + laneNo * 512 + 256 + test42;

		*x = curve->Midx + FIXEDH(radius * RSIN(angle));
		*z = curve->Midz + FIXEDH(radius * RCOS(angle));
	}
	else if (junction)
	{
		// do nothing really
	}
	else if (cp)
	{
		CIV_STATE_SET_CONFUSED(cp);
		return 0;
	}

	if (cp && changeLaneCount > 0)
		cp->ai.c.changeLaneCount--;

	return 0;
}

// [D] [T]
int CheckChangeLanes(DRIVER2_STRAIGHT* straight, DRIVER2_CURVE* curve, int distAlongSegment, CAR_DATA* cp, int tryToPark)
{
	int oldLane, newLane, currentLane;
	int trials;
	CAR_COSMETICS* car_cos;
	int dx, dz;
	u_int theta;
	int length;
	CAR_DATA* lcp;

	int oldLaneDir;
	VECTOR pos;
	u_char canProceed;
	u_char turnRight;
	CDATA2D cd[2];

	canProceed = 0;
	oldLane = cp->ai.c.currentLane;
	currentLane = oldLane;

	if (cp->ai.c.ctrlState != CIV_AI_CTRL_STOP_AT_NODE && cp->ai.c.changeLaneIndicateCount == 0)
	{
		int roadWidthInLanes;
		int segLen;

		if (straight == NULL)
		{
			roadWidthInLanes = ROAD_WIDTH_IN_LANES(curve);
			segLen = curve->end - curve->start & 0xfff;
		}
		else
		{
			roadWidthInLanes = ROAD_WIDTH_IN_LANES(straight);
			segLen = straight->length;
		}

		newLane = currentLane + (Random2(0 /* C129: was (int)straight, unused by Random2; 64-bit host */) >> 7 & 2U) + 0xff & 0xff;
		
		if (tryToPark)
		{
			if (oldLane == 1)
				newLane = 0;
			else if (roadWidthInLanes - 2 == currentLane)
				newLane = roadWidthInLanes - 1;

			// [A] don't park near the road ends
			if(distAlongSegment < 1024 && distAlongSegment > segLen - 1024)
				return currentLane;
		}

		for (trials = 0; trials < 2; trials++)
		{
			if (trials == 1)
				newLane = currentLane * 2 - newLane & 0xff;

			if (newLane == 0xff || roadWidthInLanes <= newLane)
				continue;

			//travelAlongRoad = (currentLane ^ 1) & 1;
			
			if (gCurrentMissionNumber == 33 && makeLimoPullOver)
			{
				// bypass checks
			}
			else if (tryToPark)
			{
				int allowedToDrive;
				allowedToDrive = straight && ROAD_IS_AI_LANE(straight, newLane) || curve && ROAD_IS_AI_LANE(curve, newLane);

				if (!allowedToDrive)
					continue;
			}
			else
			{
				int allowedToPark;
				int allowedToDrive;

				// collect the lanes.
				allowedToPark = straight && ROAD_IS_PARKING_ALLOWED_AT(straight, newLane) || curve && ROAD_IS_PARKING_ALLOWED_AT(curve, newLane);
				allowedToDrive = straight && ROAD_IS_AI_LANE(straight, newLane) || curve && ROAD_IS_AI_LANE(curve, newLane);

				if (!allowedToDrive || allowedToPark)
					continue;
			}

			// don't allow to change lane which in wrong direction
			if (straight != NULL) 
			{
				oldLaneDir = ROAD_LANE_DIR(straight, oldLane);
				if (oldLaneDir != ROAD_LANE_DIR(straight, newLane))
					continue;
			}
			else if (curve != NULL) 
			{
				oldLaneDir = ROAD_LANE_DIR(curve, oldLane);
				if (oldLaneDir != ROAD_LANE_DIR(curve, newLane))
					continue;
			}

			if (cp->ai.c.ctrlNode == NULL && cp->ai.c.turnNode == -1) 
			{
				canProceed = true;
				turnRight = oldLaneDir == 0;

				if (currentLane < newLane)
					turnRight = !turnRight;

				if (turnRight)
					theta = cp->hd.direction + 1024;
				else
					theta = cp->hd.direction - 1024;

				cd[0].x.vx = cp->hd.oBox.location.vx + FIXEDH(RSIN(theta) * 512);
				cd[0].x.vz = cp->hd.oBox.location.vz + FIXEDH(RCOS(theta) * 512);
				cd[0].length[0] = cp->ap.carCos->colBox.vz + 93;
				cd[0].length[1] = cp->ap.carCos->colBox.vx;
				cd[0].theta = cp->hd.direction;

				lcp = &car_data[MAX_CARS-1];

				while (lcp >= car_data)
				{
					if (lcp != cp && lcp->controlType != CONTROL_TYPE_NONE)
					{
						car_cos = lcp->ap.carCos;

						cd[1].length[0] = car_cos->colBox.vz + 93;
						cd[1].length[1] = car_cos->colBox.vx;
						cd[1].x.vx = lcp->hd.oBox.location.vx;
						cd[1].x.vz = lcp->hd.oBox.location.vz;
						cd[1].theta = lcp->hd.direction;

						length = ((cd[0].length[0] + cd[1].length[0]) * 3) / 2;

						dx = cd[0].x.vx - cd[1].x.vx;
						dz = cd[0].x.vz - cd[1].x.vz;

						if (ABS(dx) < length && ABS(dz) < length) 
						{
							if (bcollided2d(cd))
							{
								canProceed = false;
								break;
							}
						}
					}
					lcp--;
				}

				if (canProceed)
					break;
			}
		}

		if (canProceed)
		{
			cp->ai.c.changeLaneIndicateCount = 161;
			cp->ai.c.oldLane = oldLane;
			cp->ai.c.changeLaneCount = 4;
			cp->ai.c.changeLane = turnRight;
			currentLane = newLane;
		}
	}

	return currentLane;
}

int makeNextNodeCtrlNode = -1;

// [D] [T]
int CreateNewNode(CAR_DATA * cp)
{
	CIV_ROUTE_ENTRY* start;
	CIV_ROUTE_ENTRY* newNode;
	CIV_ROUTE_ENTRY* retNode;
	int oldRoad;
	int cr;
	DRIVER2_ROAD_INFO roadInfo;
	CIV_ROUTE_ENTRY tempNode;
	int turnAngle;
	int startDist;
	int travelDir;
	int segmentEnd;
	int cornerAngle;

	start = cp->ai.c.pnode;
	turnAngle = 0;

	// validate two next nodes
	if (IS_NODE_VALID(cp, GET_NEXT_NODE(cp, start)) &&
		IS_NODE_VALID(cp, GET_NEXT_NODE(cp, start + 1)))
	{
		do {
			newNode = retNode = GET_NEXT_NODE(cp, start);

			if (retNode->pathType == 127)
			{
				oldRoad = cp->ai.c.currentRoad;

				if (cp->id == makeNextNodeCtrlNode)
				{
					cp->ai.c.ctrlNode = newNode;
					makeNextNodeCtrlNode = -1;
				}

				// stop, dammmm
				if (!GetSurfaceRoadInfo(&roadInfo, oldRoad))
					break;

				if (ROAD_LANE_DIR(&roadInfo, cp->ai.c.currentLane) == 0)
					travelDir = 1;
				else
					travelDir = -1;
				
				if (roadInfo.straight)
				{
					segmentEnd = roadInfo.straight->length;

					newNode->distAlongSegment = start->distAlongSegment + travelDir * 1024;
					newNode->dir = start->dir;
				}
				else
				{
					int dist;

					segmentEnd = roadInfo.curve->end - roadInfo.curve->start & 0xfff;

					if (roadInfo.curve->inside < 10)
						dist = travelDir << 7;
					else if (roadInfo.curve->inside < 20)
						dist = travelDir << 6;
					else
						dist = travelDir << 5;

					newNode->distAlongSegment = start->distAlongSegment + dist;
					newNode->dir = newNode->distAlongSegment + roadInfo.curve->start + travelDir * 1024 & 0xfff;
				}

				// check travelling direction and position on segment
				// advance road if needed
				if ((travelDir > 0 && segmentEnd < newNode->distAlongSegment) ||
					(travelDir < 0 && newNode->distAlongSegment < 0))
				{
					if ((travelDir > 0 && segmentEnd <= start->distAlongSegment) ||
						(travelDir < 0 && start->distAlongSegment < 1))
					{
						cp->ai.c.currentRoad = GetNextRoadInfo(cp, 1, &turnAngle, &startDist, start);
						
						newNode->dir = start->dir + turnAngle & 0xfff;
						newNode->distAlongSegment = startDist;

						if (cp->ai.c.currentRoad == -1)
							break;
					}
					else
					{
						if (travelDir < 1)
							newNode->distAlongSegment = 0;
						else
							newNode->distAlongSegment = segmentEnd;
					}
				}

				cr = cp->ai.c.currentRoad;
				
				if (GetSurfaceRoadInfo(&roadInfo, cr))
				{
					// this node is unused
					tempNode.dir = newNode->dir;
					tempNode.pathType = newNode->pathType;
					tempNode.distAlongSegment = newNode->distAlongSegment;
					tempNode.x = newNode->x;
					tempNode.z = newNode->z;

					if (oldRoad != cr && turnAngle == 0)
					{
						if (ROAD_LANE_DIR(&roadInfo, cp->ai.c.currentLane) == 0)
							travelDir = 1;
						else
							travelDir = -1;
						
						if (roadInfo.curve)
						{
							int dist;

							if (roadInfo.curve->inside < 10)
								dist = travelDir << 7;
							else if (roadInfo.curve->inside < 20)
								dist = travelDir << 6;
							else
								dist = travelDir << 5;

							newNode->distAlongSegment = newNode->distAlongSegment + dist;
						}
						else
						{
							newNode->distAlongSegment = newNode->distAlongSegment + travelDir * 1024;
						}
					}

					// Caine's Cash limo can be stopped by player in police car
					if (gCurrentMissionNumber == 33 && cp->ap.model == SPECIAL_CAR_SLOT)
					{
						int dx, dz;
						CAR_DATA* playerCar = &car_data[MainPlayer.playerCarId];

						dx = playerCar->hd.where.t[0] - cp->hd.where.t[0];
						dz = playerCar->hd.where.t[1] - cp->hd.where.t[1];

						// check if siren is on and we near the car
						if (CarHasSiren(playerCar->ap.model) && MainPlayer.horn.on &&
							dx * dx + dz * dz < 16000000)
						{
							makeLimoPullOver = 1;
						}
					}

					// try parking it
					if ((Random2(0) + cp->id * 32 & 0xf1) == 0xf1 || makeLimoPullOver)
					{
						int tryToPark;
						int newLane;

						tryToPark = 0;

						if (numParkedCars < maxParkedCars)
							tryToPark = (Random2(0) & 2U) != 0;

						// apply our Caine's Cash logic
						if (gCurrentMissionNumber == 33 && cp->ap.model == SPECIAL_CAR_SLOT && limoId == cp->id) // [A] limoId was skipped, bringing it back.
						{
							tryToPark = makeLimoPullOver;
						}

						newLane = CheckChangeLanes(roadInfo.straight, roadInfo.curve, newNode->distAlongSegment, cp, tryToPark);

						// try change lanes or park
						if (newLane != cp->ai.c.currentLane)
						{
							cp->ai.c.currentLane = newLane;

							if (tryToPark)
							{
								if (makeLimoPullOver || cp->ai.c.ctrlState == CIV_AI_CTRL_DRIVE && ROAD_IS_PARKING_ALLOWED_AT(&roadInfo, newLane))
								{
									makeNextNodeCtrlNode = cp->id;

									cp->ai.c.ctrlState = CIV_AI_CTRL_STOP_AT_NODE;
									cp->ai.c.ctrlNode = newNode; // [A]
									cp->ai.c.changeLaneCount = 0;
								}
							}
						}
					}		

					tempNode.x = newNode->x;
					tempNode.z = newNode->z;

					tempNode.dir = newNode->dir;
					tempNode.pathType = newNode->pathType;
					tempNode.distAlongSegment = newNode->distAlongSegment;

					GetNodePos(roadInfo.straight, NULL, roadInfo.curve, newNode->distAlongSegment, cp, &tempNode.x, &tempNode.z, cp->ai.c.currentLane);

					if (turnAngle == -1024)
					{
						int cornerAngle;
						int segLength;
						int tmp;
						int dx;
						int dz;

						dx = tempNode.x - start->x;
						dz = tempNode.z - start->z;

						segLength = (SquareRoot0(dx * dx + dz * dz) - (cp->hd.wheel_speed / 170));
						cornerAngle = DIFF_ANGLES(start->dir, ratan2(dx, dz)); //((ratan2(dx, dz) - start->dir) + 2048U & 0xfff) - 2048;

						tmp = FIXEDH(segLength * RCOS(cornerAngle));

						retNode = newNode;
						if (tmp > 0)
						{
							newNode->x = start->x + FIXEDH(tmp * RSIN(start->dir));
							newNode->z = start->z + FIXEDH(tmp * RCOS(start->dir));

							newNode->pathType = 1;
							newNode->dir = start->dir;

							retNode = GET_NEXT_NODE(cp, newNode);
						}

						tmp = FIXEDH(segLength * RSIN(cornerAngle));

						newNode = retNode;

						if (tmp < 0)
						{
							retNode->x = tempNode.x + FIXEDH(tmp * RSIN(tempNode.dir));
							retNode->z = tempNode.z + FIXEDH(tmp * RCOS(tempNode.dir));

							retNode->pathType = 1;
							retNode->dir = tempNode.dir;

							newNode = GET_NEXT_NODE(cp, retNode);
						}
					}

					// push into empty node
					if (newNode->pathType == 127)
					{
						newNode->x = tempNode.x;
						newNode->z = tempNode.z;

						newNode->dir = tempNode.dir;
						newNode->pathType = tempNode.pathType;
						newNode->distAlongSegment = tempNode.distAlongSegment;

						if (ABS(tempNode.x) < 600000)
						{
							if (turnAngle)
							{
								cp->ai.c.turnNode = GET_NODE_ID(cp, newNode);
								cp->ai.c.turnDir = (turnAngle == 1024);
							}

							newNode->pathType = 1;

							return 1;
						}
					}
				}
				
				break;
			}

			//if (newNode >= end) // [A] i don't think that's ever needed now, probably have done better macro than OG devs
			//	newNode = start - 12;

			start = newNode;

		} while (newNode != cp->ai.c.pnode);
	}

	CIV_STATE_SET_CONFUSED(cp);
	return 0;
}

// [D] [T]

// --- civ_ai.c lines 3032-3274 (verbatim): CivFindStation, CivFindPointOnPath, CivSteerAngle ---
int CivFindStation(CAR_DATA * cp)
{

	int loop;
	int square;
	CIV_ROUTE_ENTRY* currentNode;
	CIV_ROUTE_ENTRY* retNode;
	CIV_ROUTE_ENTRY* rep;
	int dz;
	int dx;

	int sz;
	int sx;

	int cx;
	int cz;
	int stepsize;
	int i;

	cx = cp->hd.where.t[0];
	cz = cp->hd.where.t[2];

	loop = cp->ai.c.currentNode - 1;

	currentNode = cp->ai.c.targetRoute;
	rep = currentNode;
	while (loop >= 0)
	{
		currentNode = rep = GET_NEXT_NODE(cp, rep);
		loop--;
	}

	do {
		retNode = GET_NEXT_NODE(cp, currentNode);

		if (retNode == NULL)
			break;

		sx = currentNode->x;
		sz = currentNode->z;

		dx = retNode->x - sx;
		dz = retNode->z - sz;

		square = dx * dx + dz * dz;

		if (square < 0)
			break;

		square = SquareRoot0(square);
		if (square > 0)
		{
			stepsize = ((cx - sx) * dx + (cz - sz) * dz) / square;

			if (stepsize < square)
			{
				cp->ai.c.pnode = currentNode;
				return stepsize;
			}
		}

		currentNode = retNode;
		cp->ai.c.currentNode = GET_NODE_ID(cp, currentNode);

		i = 1;
		do
		{
			if (GET_NEXT_NODE(cp, retNode + i)->pathType == 127)
				CreateNewNode(cp);

			i++;
		} while (i < 4);
	} while (true);

	CIV_STATE_SET_CONFUSED(cp);

	return 0;
}

// [D] [T]
int CivFindPointOnPath(CAR_DATA * cp, int station, VECTOR * ppoint)
{
	int stepSize;
	CIV_ROUTE_ENTRY* start;
	CIV_ROUTE_ENTRY* currentNode;
	CIV_ROUTE_ENTRY* retNode;
	int dx, dz;
	int sx, sz;

	start = cp->ai.c.pnode;

	if (start)
	{
		currentNode = start;

		do {
			retNode = currentNode + 1;

			if (cp->ai.c.targetRoute + 13 <= retNode)	// [A] there was reflections bug?
				retNode = currentNode - 12;

			if (retNode == NULL || retNode && retNode->pathType == 127)
			{
				ppoint->vx = currentNode->x;
				ppoint->vz = currentNode->z;

				return 1;
			}

			sx = currentNode->x;
			sz = currentNode->z;

			dx = retNode->x - sx;
			dz = retNode->z - sz;
			stepSize = SquareRoot0(dx * dx + dz * dz);

			// advance
			if (station < stepSize)
			{
				if (station < 0)
					station = 0;

				if (stepSize < 4096)
				{
					ppoint->vx = sx + (dx * station) / stepSize;
					ppoint->vz = sz + (dz * station) / stepSize;
				}
				else
				{
					stepSize /= 16;

					ppoint->vx = sx + FIXEDH(((dx * 256) / stepSize) * station);
					ppoint->vz = sz + FIXEDH(((dz * 256) / stepSize) * station);
				}

				return 1;
			}

			station -= stepSize;
			currentNode = retNode;

		} while (retNode != start);
	}

	CIV_STATE_SET_CONFUSED(cp);

	return 0;
}

const int checkFrames = 20;
const int maxSteer = 512;

// [D] [T] [A] - removed copying of car. Still works okay
int CivSteerAngle(CAR_DATA* cp)
{
	CIV_ROUTE_ENTRY* startNode;
	short lbody;
	CIV_ROUTE_ENTRY* retNode;
	CIV_ROUTE_ENTRY* crLoc;
	VECTOR locPath;
	VECTOR pathPoint;
	int i;

	pathPoint.vx = 0;
	pathPoint.vy = 0;
	pathPoint.vz = 0;

	startNode = cp->ai.c.pnode;

	lbody = cp->ap.carCos->colBox.vz;

	// we need 3 nodes, try making them in each different frame
	i = 0;
	do
	{
		if (GET_NEXT_NODE(cp, startNode + i)->pathType == 127)
		{
			if (CreateNewNode(cp) == 0)
			{
				CIV_STATE_SET_CONFUSED(cp);
				return 0;
			}
		}
		i++;
	} while (i < 4);

	if (startNode->pathType != 127)
	{
		retNode = GET_NEXT_NODE(cp, cp->ai.c.pnode);

		if (retNode->pathType != 127)
		{
			int station;
			station = CivFindStation(cp);

			crLoc = cp->ai.c.pnode;

			if (crLoc->pathType != 127)
			{
				retNode = GET_NEXT_NODE(cp, cp->ai.c.pnode);

				if (retNode->pathType != 127)
				{
					CIV_ROUTE_ENTRY* cr;

					int ret;
					int dx, dz;
					CivFindPointOnPath(cp, station + FIXEDH(cp->hd.wheel_speed) * checkFrames + lbody, &pathPoint);

					dx = pathPoint.vx - cp->hd.where.t[0];
					dz = pathPoint.vz - cp->hd.where.t[2];

					ret = DIFF_ANGLES(cp->hd.direction, ratan2(dx, dz)); // ((ratan2(dx, dz) - cp->hd.direction) + 2048U & 0xfff) - 2048;

					if (ret < -maxSteer)
						ret = -maxSteer;
					else if (ret > maxSteer)
						ret = maxSteer;

					// invalidate old nodes
					cr = startNode;
					while (cr != cp->ai.c.pnode)
					{
						cr->pathType = 127;

						// invalidate current turn node
						if (cp->ai.c.turnNode == GET_NODE_ID(cp, cr))
							cp->ai.c.turnNode = -1;

						cr = GET_NEXT_NODE(cp, cr);
					}

					return ret;
				}
			}
		}
	}

	CIV_STATE_SET_CONFUSED(cp);
	return 0;
}

// [D] [T]
