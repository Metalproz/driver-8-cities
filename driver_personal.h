/* driver_personal.h — shared bits of the local-only Driver plugins. */
#pragma once

#define DP_PACKAGE_ID "driver.personal"

/* <app>/ folder (exe folder without a trailing build-* component). */
const char* dp_app_dir(void);
/* 1 when a boolean option of this package's feature is true. */
int dp_option_enabled(const char* feature, const char* option);
