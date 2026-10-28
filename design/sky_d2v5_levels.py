"""Design (R31): Chicago DAY sky d2v5 levels, applied to the 256x126 day panorama (RGB float array) AFTER the d2v4 mapping and
BEFORE the 4-bit quantisation. Night untouched.  Measured against the user's D2 references (background sky 1..4)."""
import numpy as np
K_SKY = 0.58                                   # contrast compression toward white for the sky rows
BAND_MIX = 0.38; BAND_TINT = (160, 168, 180)   # skyline rows: c' = (1-MIX)*c + MIX*TINT  (lifts the floor, softens the towers)
BLEND = (62, 92)                               # v range of the smoothstep from sky formula to band formula
def d2v5_day(pano):
    a = np.asarray(pano, float); h = a.shape[0]; v = np.arange(h)[:, None, None].astype(float)
    t = np.clip((v - BLEND[0]) / (BLEND[1] - BLEND[0]), 0, 1); t = t * t * (3 - 2 * t)
    sky = 255 - (255 - a) * K_SKY
    band = (1 - BAND_MIX) * a + BAND_MIX * np.array(BAND_TINT, float)
    return np.clip(sky * (1 - t) + band * t, 0, 255)
