# PS1 graphics and presentation reference for the port (Design, 2026-10-14)

Purpose: the facts the Design chat judges visuals against. "Authentic" = what the PS1 hardware and
Driver 1 / Driver 2 do themselves; only departures from that are bugs (FAN's rule). Sources: psx-spx
(nocash) GPU docs, REDRIVER2 source (refs/REDRIVER2), psxrecomp docs (ENHANCEMENTS.md G1, WIDESCREEN.md,
GL_RENDERER_HANDOFF.md), chicago/NOTES.md, research_fps.md, research_sky.md.

## 1. PS1 GPU facts that explain what we see
| fact | visible effect | relevance here |
|---|---|---|
| No Z-buffer; draw order = submission order via an Ordering Table (OT) sorted by GTE average Z | polygons pop through each other at similar depth, flicker frame to frame when their sort bucket flips | D1 per-object renderer: unsorted groups in one per-model OT bucket (z/2 + 0x1000), sorted groups per polygon at OT z (NOTES, C31). Facade flicker and building swaps are OT effects, not texture bugs |
| Affine (screen-space linear) UV interpolation, no 1/z | textures swim/warp on large near polygons; lane lines kink at polygon edges | C2. The only fix on hardware is subdivision (D2: makeMesh 5x5 on near polys, draw.c); the runtime also has an opt-in host fix (section 3) |
| GTE projects to integer pixels (SXY), fraction dropped | vertex wobble ("jitter") on slow motion | authentic; the runtime's geometry_correction is withdrawn (cracks meshes) |
| No near-plane clipping in the GPU; polygons are clipped by the drawing area, vertex coords -1024..1023, max polygon size 1023x511 | very near polygons stretch across the screen or vanish when a vertex projects behind the camera | C2 overpasses; D1 relies on polygon flags 0x20/0x40 near-subdivision (< 6000 / 9000 units, 0x80030B08) and on culling; D2 subdivides more aggressively |
| 15-bit colour (5:5:5), 4x4 ordered dither applied only to Gouraud or modulated polygons, never to rectangles | banding in dark gradients, visible dither on shaded surfaces at night | night Chicago dimming (palette x0.17 water etc.) must be judged in 15-bit: steps of 8/255 |
| VRAM 1024x512 halfwords (1 MB): framebuffers + texture pages 256x256 (4-bit 32 KB, 8-bit 64 KB), CLUT 16x1 / 256x1 strips | texture page budget is the hard limit on detail per area | D1: 16 page slots at x 512..1023 (NOTES), area pages stream into slots; C7 downscaling is pixel-bound |
| Colour 0000h in a texture = transparent; bit 15 = semi-transparent flag; 4 blend modes (B/2+F/2, B+F, B-F, B+F/4) | glows and smoke are additive (B+F) quads; a wrong CLUT entry makes a window or shopfront magenta/cyan | C32 purple shopfronts, C18 square light glows (sprite record lookup, not blending) |
| Texture window (GP0 E2h) repeats a power-of-two sub-rect across the page | tiling of road/ground textures without extra polygons | converter must keep textures at power-of-two sizes when D1 used windows |
| Display 256/320/368/512/640 x 240 (480 interlaced) | D1 and D2 run 320x240-class, 24 bit for FMV only | widescreen in the runtime is a GTE X-squash plus per-prim fixes (section 3) |

## 2. Driver 1 vs Driver 2 presentation (what differs and why it matters for the port)
- **Draw distance / culling:** D2 uses a 21x21 cell PVS window (map.h PVS_CELL_COUNT, "do not modify") and
  VIEW_DRAW_DISTANCE 16000/22000 (camera.h, platform dependent); D1 uses a 19x19 window of 3000-unit cells and a
  far tile range of ~9000 units (C19 water cut-off). Chicago in D1 therefore shows slightly less than in D2; this is
  authentic D1 behaviour, not a bug, unless geometry vanishes inside D1's range.
- **Subdivision:** D2 subdivides near building polygons NxN (PlotBuildingModelSubdivNxN, draw.c 781) and road/ground
  5x5 meshes; D1 subdivides only polygons flagged 0x20/0x40 at two fixed levels. Converter default "light"
  (CHI_POLISH_SUBDIV) maps all flagged polygons to D1's light level: +4 FPS, slight extra warping near walls.
  Judgement rule: warping within what LA shows at the same distance = OK.
- **Sky:** D1 = 12 BMPs 64x42 (256x126 panorama, horizon at v~105), 3 bands (research_sky.md); D2 = 512x252 dome in
  5 variants (day, night, rain, dawn, dusk) with sun, moon, lens flare, TunnelSkyFade (sky.c). Chicago ships D2's
  skyline squeezed into D1's layout (sky 13/14/15). The missing parts vs D2 are sun/moon sprites, lens flare and the
  tunnel fade: authentic-to-D1 loss, candidates for a later polish round (C46 is the dome-order follow-up).
- **Lighting at night:** D1 night = per-city dimmed palettes + headlight halos + lamp glows on named models
  (0x800A663C list); D2 night = same idea plus per-vertex lighting on cars and more light sprites. Chicago night
  uses LA's night code path on D2's night LEV; no double dimming (NOTES).
- **Fog / depth cue:** D1 fades far polygons to the fog colour set per CITY (0x800298D8 compares); D2 uses per-area
  sky/fog colour. For Chicago day, CITY 3 colours are replaced by the plugin's day words.
- **Minimap:** D2's overlay map turned a quarter and re-scaled (x1.32) into D1's lump 24 (polish_map); D1 draws
  it with LA's per-city table replaced while Chicago is loaded.
- **Cars:** D1 car textures must sit on pages >= 5; glows, hubcaps, smoke, flares are by-name sprites in the
  texture page COUNT table (0x800BE2F8); getting those tables wrong gives dark squares (C18 family).

## 3. Runtime (psxrecomp) presentation knobs, state of the dev client
settings.toml of build-dev: renderer opengl, supersampling 2, antialiasing on, texture_filtering nearest,
geometry_correction off, perspective_texturing off, crt_filter raw, aspect 4:3, frame_interpolation off.
- `perspective_texturing = true` is the one safe, shippable enhancement (G1.8: no cracks, UVs only). It would hide
  part of C2's lane-line kinks and road swim on the host only; it is NOT a PS1 path (Milestone 8), so it is a
  "nice on PC" option, never a fix for a converter issue. The runtime trial on C2 (NOTES) showed no change because
  the stretching is geometric (no near clipping), not UV.
- `geometry_correction` is withdrawn by the framework (cracks meshes at partial coverage): do not propose it.
- `texture_filtering = bilinear` exists (GL/SW parity) but changes the look away from the PS1; keep nearest as the
  default and only offer bilinear as a player option.
- Widescreen (`aspect_ratio = 16:9`) is a GTE X-squash plus per-game sprite tagging; Driver has no [widescreen]
  block yet. Side effects to expect: world-space culling pop-in at the wide edges, HUD anchoring heuristics.
  Not on the roadmap; mention only if the user asks.
- Frame-level tools: app/psxrecomp/tools/gpu_frame_*.py (which guest function drew which primitive, per-function
  layers, frame diffs) are the right instrument for any "what is drawn here" question; prefer them over screenshots.

## 4. Open visual issues sorted by what a PS1 player would notice (Design view, 2026-10-14)
Big (break the illusion): C2 near stretching of overpasses and lane kinks; C30 black faces / building swaps
while an area loads; C1 ground strip holes near the car. Medium: C10/C46 sky (done except dome order), C18 square
light glows, C32 purple shopfronts (not reproduced), C31 facade flicker (OT bucket; LA has the same mechanism),
C24 white debris shards. Small: C7 downscaling in dense areas (pixel-bound, already filtered), C13 damaged wheels
(not reproduced), minimap/loading bar (data ready).
Authentic, not bugs: D1's shorter draw distance than D2, affine swim at D1's level, 15-bit banding, vertex wobble,
pop-in at D1's far tile range, OT flicker at the level LA shows.

## 5. Judging method
1. Compare against the same situation in an original D1 city (LA/Miami) and in D2 Chicago (DriverLevelTool viewer
   or the D2 disc in an emulator if needed): same mechanism visible there = authentic.
2. For a suspected rendering bug, take a frame dump and attribute the primitives with gpu_frame tools before
   proposing a converter or engine change.
3. Keep PS1 limits (VRAM pages, OT size, polygon size 1023x511, 2 MB RAM) in every proposal (Milestone 8).
