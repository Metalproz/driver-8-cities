/* driver_personal.h — shared bits of the local-only Driver plugins. */
#pragma once
#include <stdint.h>

#define DP_PACKAGE_ID "driver.personal"

/* <app>/ folder (exe folder without a trailing build-* component). */
const char* dp_app_dir(void);
/* 1 when a boolean option of this package's feature is true. */
int dp_option_enabled(const char* feature, const char* option);
/* FPS / EMU measurement (the overlay's numbers + the stats block for test tools), once per
 * VBlank: called by every always-on vblank plugin with its own id; the first caller owns it. */
void driver_personal_fps_tick(int caller);
void driver_personal_sel_debug(const uint32_t w[6]);   /* SEL1 record (C17 test tools) */
