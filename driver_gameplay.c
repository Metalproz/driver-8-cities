/* driver_gameplay.c — "unlock-all" for Driver (USA v1.1,
 * SLUS-00842). Addresses come from the retail executable; the game addresses
 * them through KUSEG (lui 0x0009 / $gp = 0x00096770).
 *
 * unlock-all mirrors what the game itself does when the Undercover story is
 * finished (frontend code at 0x80024E7C): every entry of the cheat-code table
 * gets -2 in its first slot, which is the game's own "cheat unlocked" marker.
 * The Undercover script raises the unlocked-city count with max(cities, n)
 * (0x8006EC04); we raise it to all four. Mission progress (0x800967F8) is not
 * touched, so Undercover saves keep their real position.
 *
 * skip-intro is declarative (main_exe patches in the package manifest). */

#include "driver_personal.h"

#include <stdint.h>

#include "mod_plugins.h"

/* ---- unlock-all -------------------------------------------------------- */

#define CHEAT_TABLE      0x0008671Cu  /* 13 L/R-button steps + terminator each */
#define CHEAT_STRIDE     0x38u
#define CHEAT_COUNT      0x000967D8u  /* $gp+0x68, 8 on retail */
#define CHEAT_MAX        8u
#define CHEAT_UNLOCKED   0xFFFFFFFEu  /* -2 */
#define CITIES_UNLOCKED  0x000967E0u  /* $gp+0x70, 2 on a new game */
#define CITIES_ALL       4u

static void unlock_all_vblank(void) {
    if (!psx_mod_game_started())
        return;
    uint32_t n = psx_mod_read_word(CHEAT_COUNT);
    if (n > CHEAT_MAX)
        n = CHEAT_MAX;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t slot = CHEAT_TABLE + i * CHEAT_STRIDE;
        if (psx_mod_read_word(slot) != CHEAT_UNLOCKED)
            psx_mod_write_word(slot, CHEAT_UNLOCKED);
    }
    if ((int32_t)psx_mod_read_word(CITIES_UNLOCKED) < (int32_t)CITIES_ALL)
        psx_mod_write_word(CITIES_UNLOCKED, CITIES_ALL);
}

PSX_MOD_CONSTRUCTOR(driver_gameplay_register) {
    psx_mod_register_vblank_plugin("driver.unlock-all", unlock_all_vblank);
}
