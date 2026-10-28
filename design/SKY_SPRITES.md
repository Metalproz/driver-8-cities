# Sun, moon and lens flare for Chicago's sky (Design, 2026-10-14)

## What Driver 2 has (REDRIVER2 sky.c, debris.c)
- Textures by name from the level: `SKYSUN` (24x24, 12 colours, a white disc with a blue rim) and `SKYMOON`
  (32x32, 16 colours, a grey moon with craters). Chicago: both on D2 page 2 (SKYMOON at 224,0; SKYSUN at 224,32).
- `DrawLensFlare` (every frame, except rain/fog and dawn/dusk): projects `sun_position[level]` = (-32000,-11000,-5000)
  (same for all 4 cities), samples the framebuffer around the sun to see how much of it is uncovered, draws
  `DisplaySun` (semi-transparent quad, col 254 by day) and then 8 flare sprites from `flare_info` along the line to
  the screen centre (colours {0,0,90},{80,40,4},{90,0,0},{0,90,0},{0,0,90},{90,90,0},{90,0,0},{0,0,90}; sizes 16..64).
  At night: col 128, `DisplayMoon` at `moon_position` (-32000,-11500,-18000) plus a flipped second moon at
  `moon_shadow_position` (the reflection on the water for Chicago/Havana/Vegas; Rio's y differs).
- `TunnelSkyFade`: the sky darkens inside the three tunnels (tunnelPos table).

## What Driver 1 already has (exe 0x80046E44, the D2 `DrawLensFlare` ancestor)
- Same design, same numbers: sun vector 0x80096C24 = (-32000,-11000,-5000) exactly D2's; an 8-entry flare table at
  0x8008A878 byte-identical to D2's `flare_info`; framebuffer sampling for occlusion (FUN_00074464 + the 10x? loop);
  the big glare halo (FUN_000473F0 / FUN_000493CC) by day when not blocked (0x8009789C != 3).
- Night (night_flag set): the SAME `SKYSUN` sprite drawn dimmed (0x60) at the night vector 0x80096C2C =
  (-32000,-6000,-5000) with flares at half strength. That is Driver 1's "moon": a soft white disc. There is no
  SKYMOON texture and no moon code in Driver 1.
- The by-name sprite list (0x80052240) knows `SKYSUN` and `FLARE1`; our converted Chicago LEVs carry D2's SKYSUN
  (so the day sun in Chicago IS Driver 2's sun; seen in the captures: disc + flare chain) and drop SKYMOON.
- Chicago night runs LA's night path with the D1 night flag 0x80096850 unset (NOTES: no double dimming), so the
  flare routine takes its DAY branch at night: full-brightness SKYSUN at the day vector. In the night captures that
  shows as a bright round glow high in the sky (sky_night turn 2): acceptable as a moon stand-in, but it is the sun.

## Design
1. **Day: nothing to change.** Chicago day shows Driver 2's own sun sprite with Driver 2's own flare table through
   Driver 1's identical code: authentic.
2. **Night: a real moon, data-only.** Day and night are separate LEV files, so the night LEV can carry Driver 2's
   SKYMOON pixels in the `SKYSUN` slot: the converter (night run only, switch `CHI_NIGHT_MOON=1`) replaces the SKYSUN
   texture by `out/SKYMOON_24.png` (D2's 32x32 moon resampled to the 24x24 slot; or keep 32x32 if texrepack allows a
   larger by-name texture: the sprite quad scales with the texture width in the routine, so 32 gives D2's size).
   The routine then draws the moon disc at full brightness (day branch) with the flare chain: D2 draws its night
   flares at col 128, so if the chain is too strong at night, the plugin can write the night brightness (0x60) into
   the routine's colour byte for Chicago night (one immediate) or leave it: a moon with a faint flare is what D2 shows.
3. **Moon position (plugin, 3 halfwords):** while Chicago night is loaded, write 0x80096C24 := D2's moon_position
   (-32000,-11500,-18000) and restore the sun vector for day, so the moon stands where D2 puts it (further south-west,
   lower). Without this it stays at the sun's place: fine for a first version.
4. **Moon reflection** (D2's flipped second moon on the lake): skip; D1 has no second draw and the lake is rarely
   under the moon.
5. **Tunnel sky fade:** skip for now (Chicago's tunnels are short; D1 has no equivalent); revisit if the sky showing
   through tunnel mouths bothers the user.
6. **Rain sky (15):** D2 draws no sun in rain. The plugin could zero the sun's brightness in the rain variant
   (the routine checks a rain byte at 0x80096AA8 already for the colour scaling; if the sun still shows in rain, a
   one-byte gate there). Low priority.

Assets in `out/`: `SKYMOON_32.png` (D2 original), `SKYMOON_24.png` (slot-sized), `SKYSUN_24.png` (D2 sun, already in
our LEV), `sun_moon_8x.png` (preview). PS1 path: pure texture/CLUT data in the LEV, no RAM cost (Milestone 8 ok).
