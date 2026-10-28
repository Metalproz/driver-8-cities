# Quay artefact (EXP, 2026-10-16, partial)
- Snapshot 20261016-003253-v3839 (D2 -179784,-101211; D1 -79591,-220697, hdg 233, area 11, reg 135). ram.bin + screen.png in the probe folder.
- Run 1 (devtest/exp_work/quay/run1_log.txt, cellprobe CP_PTS at the point, CP_R=2, var_polish_quay2_day.lev, port 4450, start 300 back not used: started at the snapshot D2 point, car spawned at D1 -79591,164,-220698):
  - Road-map cells around the point: sid 754 at the centre (height/plane entries), water cells 683 (1080 W) around it (the quay side is water).
  - Surface 754: 2 planes: foot (-750,-750)-(750,750) a 0 d 0 nv 4 sw -32768; foot same extent d -1640 nv 4 sw 1334. The second plane (d -1640) is the candidate for the slanted grey plane; sw 1334 vs -32768 differs (flag/weight).
- Not done: model ids of the vertical slab and the slanted plane (needs the object list at that cell or a GPU capture; not in this run), TESS/SHOREFIX check (not compared), second run (not needed for the data above).
- Causes are unverified. Candidates: (a) surface 754 plane d -1640 (a second plane with sw 1334) taken as a height plane over the quay; (b) the water/quay cell pair (754 next to 683 W) is the shore edge that SHOREFIX rewrites but this surface id is not covered.

## Run 2: GP0 capture at the pose (EXP, 2026-10-16)
- Start: D2 (-180084,-101211), 300 units back; the car reached 396 units from the snapshot point (D1 -79987,-220698) and then drove on (cross held). One capture at 396 units: devtest/exp_work/quay/frames/quay0.{json,png,summary.json}.
- Frame 11041: 859 packets (840 drawing); ops PolyFT4 552, PolyFT3 102, PolyFT4+semi 50, PolyFT3+semi 97, Sprite+semi 12, Rect1 2; modes B+F 143, 0.5B+0.5F 31. Attribution: ONE guest function (0x1FC02B80, 859 packets), so the layer tool does not separate the slab from the rest.
- Picture (quay0.png): a dark translucent slab above the water in the upper middle (blue-grey, additive), building faces on the left, the quay wall edge across the middle.
- Not done: model ids (the cell object list was not read; the attribution gives no per-model split), polygon extents after TESS, placement height. The translucent slab is drawn with semi-transparent polygons (B+F), so it is a textured model or sprite group, not the collision plane.

## Offline cell-object lookup (EXP, 2026-10-16) — work/var_polish_quay2_day.lev and var_roads_b16b_day.lev
- Method: d1cells.extract() + unique_objects() (CellObject x, y, z, yang, model), all objects within 4000 units of D1 (-79591,-220697). Output: devtest/exp_work/quay/near_objs.json.
- 24 objects, identical in quay2 and b16b (same positions, same ids): TESS/SHOREFIX change geometry, not the object placement.
  - model 683 x 4: nearest (-79500, y 1084, -220500), 217 units from the point, 1084 above the street (y 0 at the road). No model name in the MODELNAMES list (ids above the name list). Candidate (a) for the translucent slab: an object 1084 high right at the quay, additive or semi model (not checked: no polygon data read yet).
  - model 53 (LOW_BIGGRASS) x 12 at y 0: grass, not the slab/plane.
  - model 149 (LOW_TLIGHT02) x 6 at y 0: traffic light, not the plane.
  - model 1215 x 2: not listed (within range).
- Model 1115 (the quay wall candidate in NOTES) is NOT within 4000 units of the point in either level: the slanted plane is not a cell object here (candidate (b) not found among objects; likely the terrain/road surface or a ROADSURF/shore plane, not a model).
- Open: polygon extents, semi-transparency flags and the largest edge of model 683 (needs the model table parse, models.Model.parse on the 683 entry), and the surface that makes the slanted plane (terrain height vs quay).
