# Artistic pre-review of the pending probes (Design, 2026-10-14)

Scope (Strategy's brief): art only, no bug hunting. Own captures on devtest/design (build-test exe, the probe
packages from devtest/_probe_pkgs, port 4490, native 15-bit screenshots), compared with Driver 2's own data:
the SKY0.RAW panoramas (day/night), the D2 Chicago texture pages (DriverLevelTool export of d2_CHICAGO.LEV) and
Driver 2's menu/city artwork from the D2 disc. Driver 2 in-game reference shots were not available; D2 knowledge
is from REDRIVER2 (sky.c, draw.c) and the originals' data.

## 1. "sky d2" (C46 data-only sky) vs today's sky

| | today (city selector, b16b) | "sky d2" (mirror + top 42) | Driver 2 itself |
|---|---|---|---|
| skyline height | squeezed: the towers end well below the cloud band, the city reads as a low grey strip | towers ~1/3 taller, Sears/Hancock stand out, horizon cleaner | tall towers, the skyline band is the dominant element of the dome |
| sky above | large cloud field, correct colours | slightly less cloud, the band starts higher | similar |
| below the horizon | flat ground colour | D2's mirrored rows at half brightness (only visible from elevated spots / over water) | mirror rows (sky.c y3/y4) |
| night | skyline nearly invisible, a faint grey band; the lit windows of D2's night panorama are lost | windows readable as a sparkle band, moon/halo glow visible over the horizon | lit windows + moon |

**Verdict: "sky d2" = clearly closer to Driver 2, keep it as the default.** Day: the only thing a player
sees is a taller, more present skyline (good). Night: the gain is bigger (the city is visible at all).
What would make it more like D2 (in order of payoff):
1. The exact dome order (research_sky.md proposal): D2 alternates two skyline bands around the dome (models
   0/2 vs 1/3); today the same 256-px panorama repeats every 90 degrees, so a player turning on the spot sees
   the same towers four times. This is the one remaining visible difference by day; engine work, so a later step.
2. Sun / moon sprites and the lens flare (D2 DisplaySun/DisplayMoon/DrawLensFlare): small, but they are what
   makes D2's sky "alive". D1 has its own sun flare code (0x80047030) that could take a Chicago position.
3. Dusk/dawn/rain variants: D2 ships 5 skies per city; we ship day/night/rain. Fine for now.
Things the user should look at: (a) turn 360 degrees downtown by day: is the repeating skyline acceptable?
(b) night: do the lit windows read as a city or as noise? (c) the Lake Shore / water spots: mirror rows visible?

## 2. "d2 cars" (C42 mix3): the look of D2's traffic and police

Evidence: D2's car pages (PAGE 50/58/65 of d2_CHICAGO.LEV: 256x256, each car side ~200 px long) vs the
probe's car pages (PAGE 5/6: the same textures at half size, ~100 px per car side); the Polish findings
images (c42_mix3_traffic_frame / d2_cop_traffic); own captures (the traffic was parked out of view at the
default start, so no fresh close-ups: the findings frames are the reference).

- **Texture halving:** at Driver 1's normal viewing distance (chase cam, car 2-3 car lengths ahead) the
  halved textures are acceptable: Driver 1's own cars use ~128-px sides, so D2's halved cars match the
  D1 cars' texel density and don't stand out next to the player's Miami car. Up close (cop ramming, replay
  cameras) the "CHICAGO POLICE" door lettering and the grille turn soft. Verdict: **acceptable, not
  authentic**. More D2-like: keep the cop (the car players look at most) at full size and halve only the
  civilian traffic; or keep the door/hood textures full and halve roofs/undersides (the parts never seen
  close). That is a page-budget decision for Polish/Infrastructure, not a style one.
- **Wheels ~40 % too big:** this is the thing that hurts. In the findings frame the cop's front wheel is a
  black disc larger than the wheel arch and sits outside the body; it reads as a toy / a glitch, and it is
  the first thing a Driver 2 player notices (D2's Chicago cop is a long, low sedan with small wheels).
  Verdict: **visibly wrong until the wheel tables are mapped**; the halved textures are secondary to it.
- **Colour / palette:** the D2 palettes survive (blue-white cop, the beige/brown civilian set): good.
- **Music:** D2's Chicago day/night tracks in Chicago only, D1's elsewhere: right choice for the "two games
  in one" feel (not judged further; out of the art brief).
User checks: (1) a cop chase at speed: do the wheels distract? (2) stop next to a parked civilian car in
the chase cam: is the texture softness noticeable? (3) does the Miami player car look out of place among
D2 traffic (it does to me a little: brighter, more saturated paint; a later "player car = D2 car" step fixes it).

## 3. Texture look of Chicago (city selector b16b) vs Driver 2 (C7 downscaling)

- Facades, road, kerbs and the L structures are D2's textures with the box-filtered halving where an area
  exceeds the 16-slot page budget. Downtown (dense areas) the ground-floor shopfronts and the window grids
  are visibly softer than D2's; the big glass towers and the brick blocks look right because their textures
  tile and halving hides well. Mid-town and the lakeshore look like D2.
- Driver 1's own cities use coarser textures than D2 did, so Chicago still looks **richer than LA/Miami**
  in the same engine: for a Driver 1 player the city looks like an upgrade, for a Driver 2 player like a
  slightly soft Chicago. Verdict: **acceptable**; authentic enough that nothing looks "wrong", just soft.
- More D2-like (data side): spend the halving on what the camera never sees close (roofs, high storeys,
  undersides of the L) and keep street-level textures (shopfronts, signs, kerb lines) at full size; the
  current cost-ordered choice already goes that way, a "street-level first" weight would finish it.
- Day lighting: Chicago day uses Miami's ambient (0x282828 path) and Miami's cars; D2's Chicago day is
  colder/greyer (overcast). A slightly cooler fog/sky tint for Chicago day would read more D2 (small, exe
  colour words; later).

## 4. What matters most for the player (art view)
1. **Wheel size on D2 cars** (C42): breaks the car's silhouette; fix before the D2 cars ship.
2. **Sky dome order**: the repeating skyline is the one thing a D2 fan notices in the sky; "sky d2" as is
   already fixes the squeeze and the night.
3. **C2 near stretch**: not an art issue (geometry); visually it is Driver 1 behaviour at D2's polygon sizes;
   a player sees it on every overpass, so it stays high on the gameplay list, not on mine.
4. Texture softness (C7): lowest; acceptable.

## Captures (scratchpad, not kept): city_selector day/night, cs_overpass, sky_day/night (8 headings each),
cars_day/watch/tele, D2 panoramas, D2 car pages 50/58/65 vs probe pages 5/6.
