# Schematic Transit Map Generator — Algorithm Specification

Audience: coding agents implementing the system. Status: v0.1 (design). All numeric defaults are starting points and must live in a config file, not in code.

---

## 1. Goal

Given a graph of train stations and lines (with geographic coordinates), produce a **schematic (subway-style) map**:

- Stations get new 2D coordinates; edges become **polylines** with a small number of bends.
- Edges use only octilinear directions (0°, 45°, 90°, ...), with a tolerance for diagonals (see §5).
- The result should still **resemble geography** (relative positions, neighbour order), but need not match it.
- Two renderings are produced from the same JSON output:
  1. a static **PNG** with colored lines and labeled stations;
  2. an interactive **web component** (pan and zoom).

Primary deliverable of the algorithm: a **JSON layout** (§3). Rendering (§9) consumes only that JSON.

Non-goals (v0.1): automatic line-color assignment, timetable data, real-time data, 3D, curved (Bezier) route optimization (corner rounding is cosmetic only).

---

## 2. Input

### 2.1 Schema

```json
{
  "directed": false,
  "multigraph": false,
  "nodes": [
    {
      "id": "THK01",
      "name": "東京",
      "coordinates": [139.76694, 35.68083],
      "schematic": [24.0, 0.0]
    }
  ],
  "edges": [
    {
      "source": "THK01",
      "target": "THK02",
      "distance": 3.6,
      "lines": ["THK_line"]
    }
  ],
  "lines": [
    { "id": "THK_line", "name": "東北新幹線", "color": "#980ef2" }
  ]
}
```

| Field | Meaning |
|---|---|
| `nodes[].id` | Unique string. |
| `nodes[].name` | Display label (any Unicode; CJK must render). |
| `nodes[].coordinates` | `[longitude, latitude]` in degrees (WGS84). |
| `nodes[].schematic` | **Optional hint** (see 2.3). |
| `edges[].source/target` | Node ids. Undirected, no duplicates (a pair appears once; shared by several lines via `lines`). |
| `edges[].distance` | Geographic length in **km** (assumed). If missing, compute with haversine from `coordinates`. |
| `edges[].lines` | Non-empty list of line ids that run on this edge. |
| `lines[].id/name/color` | Line identity and hex color. **Color lives only on lines**, not on nodes or edges. |

Removed relative to earlier drafts: `nodes[].num_lines` and `edges[].color`. Both are **derived** (§2.2).

### 2.2 Derived data (compute during preprocessing)

- `node.lines`: union of `lines` of incident edges.
- `node.degree`: number of incident edges.
- `node.is_interchange`: `len(node.lines) >= 2`.
- `node.kind`: `terminal` (degree 1), `through` (degree 2 and all incident edges share the same line set), `junction` (degree ≥ 3, or degree 2 with differing line sets). Terminals, junctions, and interchanges are **key nodes**.
- `edge.color`: if `len(edge.lines) == 1`, that line's color; otherwise draw each line separately (§8).
- `edge.distance` if missing.

### 2.3 The `schematic` field

Interpretation: a **coarse, pre-existing layout hint** (in the sample, `x` looks like a line slot and `y` like the station sequence index). Treat it as optional:

- If present for all nodes, it may be used as an alternative **initial layout** (config `init.mode = "hint"`).
- Default is `init.mode = "geo"` (ignore the hint).
- The output always overwrites `schematic` with the computed layout.
- Never assume it is octilinear or collision-free.

### 2.4 Validation (fail fast with clear errors)

- Unique node ids; edges reference existing nodes; no self loops; no duplicate undirected pairs.
- Every `edges[].lines` entry exists in `lines`.
- Coordinates in valid ranges; warn on two nodes with identical coordinates (nudge by ε in preprocessing, keep both).
- Node degree > 8: error (cannot be drawn with 8 ports); suggest merging.
- Disconnected graph: allowed. Lay out each connected component independently, then pack components (§6, Stage 0).

---

## 3. Output

```json
{
  "meta": {
    "version": "0.1",
    "seed": 42,
    "units": "grid_units",
    "bounds": [xmin, ymin, xmax, ymax],
    "y_axis": "up"
  },
  "transform": { "rotation_deg": -15.0, "aspect": 1.1, "origin_lonlat": [139.7, 35.7] },
  "nodes": [
    {
      "id": "THK01",
      "name": "東京",
      "coordinates": [139.76694, 35.68083],
      "schematic": [24.0, 0.0],
      "lines": ["THK_line"],
      "degree": 1,
      "kind": "terminal",
      "marker": "dot",
      "label": { "anchor": "east", "offset": [0.3, 0.0], "rotation_deg": 0 }
    }
  ],
  "edges": [
    {
      "source": "THK01",
      "target": "THK02",
      "lines": ["THK_line"],
      "line_offsets": { "THK_line": 0.0 },
      "path": [[24.0, 0.0], [24.0, 0.6], [24.4, 1.0], [24.4, 1.0]],
      "length": 1.2
    }
  ],
  "lines": [ { "id": "THK_line", "name": "東北新幹線", "color": "#980ef2" } ],
  "metrics": { }
}
```

Rules:

- `path` is a polyline in schematic coordinates; **first point = source `schematic`, last point = target `schematic`**; intermediate points are bends (not stations). At most 2 bends, i.e. at most 4 points.
- `lines` is ordered by drawing order across the bundle (left to right when traveling source → target). `line_offsets[id]` is the signed perpendicular offset in units of line width (symmetric around 0).
- Coordinates use a **y-up** system (north ≈ +y after un-rotation); the renderer flips y for screen output.
- `transform` records the global rotation θ and aspect s used (§6, Stage 1). Geographic coordinates are kept on nodes for traceability.
- Output must be deterministic given `meta.seed` and the input.
- Include `metrics` (§10).

---

## 4. Terminology

- **Octilinear direction**: one of 8 directions at multiples of 45°.
- **Port**: one of the 8 directions at which an edge may leave a node. A node can use each port at most once.
- **Chain**: maximal path of `through` nodes between two key nodes. The unit for spacing and straightening.
- **Bend**: interior vertex of an edge's polyline. Turn angle between consecutive segments must be 45° or 90°.
- **Bundle**: an edge carrying more than one line.
- **Grid unit**: the layout unit; minimum station spacing `d_min = 1.0` grid unit.

---

## 5. Constraints and Penalties (Energy Function)

Total energy:

```
E(layout) = Σ_hard  W_∞ · violation  +  Σ_soft  w_k · term_k(layout)
```

Hard terms use a very large weight (barrier / penalty) rather than rejecting states, so that simulated annealing can traverse infeasible regions early on. The final layout **must** have zero hard violations; if not reachable, report which constraints failed.

### 5.1 Hard constraints

| ID | Constraint | Definition |
|---|---|---|
| H1 | Minimum station spacing | Euclidean distance between any two nodes ≥ `d_min` (default 1.0). Also, length of every edge path ≥ `d_min`. |
| H2 | Bend limit | Each edge path has ≤ 2 bends. |
| H3 | Bend angle | Each bend turns by exactly 45° or 90° (never 135° or reversal). |
| H4 | Segment directions | Axis-aligned segments are **exactly** horizontal or vertical. Diagonal segments have angle within **±15° of 45°** (i.e. 30°–60° from the x axis in any quadrant). Nothing else is allowed. |
| H5 | Node clearance | An edge must not pass within `r_clear` (default 0.35) of any node that is not one of its endpoints. `r_clear` includes marker radius plus half the line-bundle width. |
| H6 | Port uniqueness and separation | Two edges at one node must leave at directions differing by ≥ 45° (by construction at most one per octant). |
| H7 | Circular order | The cyclic (clockwise) order of incident edges around each node must equal the cyclic order in the transformed geographic layout. |

H4 note: the diagonal tolerance is used by the router so that the endpoints of a straight diagonal edge don't need exact 45° offsets. Segments within tolerance are rendered as drawn (they are **not** snapped).

### 5.2 Soft terms

All terms are pluggable (§11). Default weights are guidance only.

| ID | Term | Definition | Default w |
|---|---|---|---|
| S1 | Crossings | Count of proper crossings between edge paths (excluding shared endpoints). Very steep; a planar result is the target. Allowed only if the data forces it. | 1000 per crossing |
| S2 | Edge-length uniformity | For each edge: `((len − L_target)/L_target)²`, with `L_target = max(d_min, a + b·ln(1 + d_geo/d0))`. Defaults: `a=1.0`, `b=0.3`, `d0=5 km`. Compresses long rural edges and expands dense urban ones, but keeps monotonic order. | 5 |
| S3 | Angle deviation | Squared outside-zone deviation plus linear diagonal `dev/tolerance` inside H4’s feasibility zone. Axes and exact diagonals cost zero. | 2 |
| S4 | Bend count | Penalty per bend (2-bend edges cost more than proportionally). | 3 per bend, 8 for the second |
| S5 | Collinearity | For each station/line with two incident edges, `abs(180° − tangent_separation)/45°`. Uses outward routed tangents. | 2 |
| S6 | Relative direction | Smoothed open-chain key-to-key chord deviation: `max(0, delta − 45°)/45°`. No through-station or closed-chain chord costs. | 10 |
| S7 | Geographic displacement | Mean squared centered displacement at key nodes only. | 0.05 |
| S8 | Edge-length vs. stations on chain | Sum of population variances of routed edge lengths divided by their chain mean. | 10 |
| S9 | Total length / compactness | Weak term on layout bounding-box area, to prevent runaway expansion. | 0.1 |
| S10 | Label clearance | Computed in Stage 5 only (not during node optimization). | — |
| S11 | Line turns | Count changes ≥45° along concatenated routed lines, including station turns and loop seams. | 6 |
| S12 | Zigzags | Count consecutive opposite-sign thresholded turns separated by less than 3 units of arc length. | 12 |
| S13 | Minimum straight run | Sum `((1.5 − run)/1.5)²` for runs shorter than 1.5, excluding terminal-ending runs. | 5 |
| S14 | Relative order | Optional count of flipped x/y orders among deduplicated k-nearest geographic key pairs; k=4. | 5; disabled |

---

## 6. Pipeline

```
load → validate → preprocess → [per component]
  Stage 1: global transform (θ, s)
  Stage 2: initial layout
  Stage 3: optimize node positions (with approximate routing)
  Stage 4: final routing + local refinement
  Stage 5: bundle ordering and label placement
→ pack components → output JSON → render PNG / web
```

### Stage 0 — Preprocess

1. Project lon/lat to local planar km. Use an equirectangular projection about the centroid: `x = (lon − lon0)·cos(lat0)·111.32`, `y = (lat − lat0)·110.57`. (For very large extents like all of Japan, consider a Lambert conformal conic or UTM-like projection; keep it behind an interface.)
2. Build the graph, derived fields (§2.2), and chains.
3. Components: handle each separately. Pack final components left-to-right (or by projected centroid) with a margin of ≥ 3 grid units.

### Stage 1 — Global rotation θ and aspect s

Simplify each projected geographic chain (RDP, 5 km tolerance), resample at its
original arc fractions, and low-pass smooth four times with alpha 0.5. Preserve
all key endpoints. `reference.enabled` can disable smoothing.

Transform `T(p) = S(s) · R(θ) · (p − centroid)`.

- Search θ in ±45° at 1° increments and aspect in [0.7, 1.4] at 0.05 increments.
- Use smoothed open-chain chord bearings, weighted by smoothed chain length
  times prominence (2 for flagged primary lines or the line with most stations,
  otherwise 1). `transform.chain_bearings: false` restores edge bearings.
- Objective: weighted squared nearest-octilinear angular deviations,
  `lambda_theta × theta² + lambda_s × ln(aspect)²`; angles here are radians.
  Defaults: `lambda_theta=0.0001`, `lambda_s=1`.
- Add the length-weighted PCA primary-line rotation-to-y candidate. Choose the
  largest flagged primary line, else the line with most stations, ID tie-break.
  Eligible primaries are flagged or originally within 45° of vertical.
  Eligible candidates must align within 5°, and also pay the configured
  squared primary-axis objective (default weight 50 times primary length).
  Flagged PCA candidates may exceed the ordinary rotation limit.
- Refine the grid result locally by golden-section search; store θ, aspect,
  primary ID and eligibility in `transform`.
- Scale each connected component independently into grid units using the median
  positive reference edge length and median target length.
- Joint transform annealing remains unimplemented; `optimize_transform: true`
  raises an explicit configuration error.

All numeric thresholds and switches live in `config/default.yaml`. Degenerate
or isotropic primary covariance has no usable PCA axis.

### Stage 2 — Skeleton initialization and station expansion

Default `init.mode: skeleton` builds keys (terminals, junctions and interchanges)
and one coarse edge per maximal chain. Internal parallel edges are retained.
Route each chain with at most four octilinear segments and length at least
`n_edges × d_min × spacing_factor` (default factor 1.5). Optimize coarse
H1/H3–H7, S1/S3/S6 and S11–S14; the configured skeleton term list controls
which enabled terms participate. H7 retains the original geographic incident
edge order at keys. Internal routing also penalizes closely overlapping
unrelated chain corridors. Closed chains are expanded using a loop route.

Expand each coarse chain by placing through stations at equal arc-length
spacing. Slice that route at stations into final edge paths, discard redundant
collinear vertices, and refine the full graph. Final H2 remains two bends per
edge; the internal four-segment allowance never relaxes the output constraints.

`init.mode: geo` keeps the flat geographic/stress pipeline with overlap
resolution and fine-grid snapping; `hint` starts from supplied schematic
coordinates. `skeleton.enabled: false` bypasses the coarse optimization.

### Stage 3 — Optimize node positions

Algorithm: **simulated annealing** over grid-snapped node positions (multi-resolution: coarse g=1.0, then fine g=0.25).

- State: node positions. Edge routes are **derived** (best candidate per edge, §7).
- Moves (pick randomly with weights):
  1. shift one node by ±1..k grid steps in 8 directions;
  2. shift an entire chain's interior nodes by the same vector;
  3. shift a branch (the subtree hanging off a junction) by a vector;
  4. snap a through-node onto the line between its two neighbours (collinearity move);
  5. reflect a short branch about its junction axis (try, accept only if H7 holds);
  6. re-space a chain's nodes evenly between its endpoints;
  7. rotate an entire chain by ±45°;
  8. rotate a junction branch by ±45°.
- `anneal.rotation_moves` enables the last two move types. `multistart` alternates
  preserved skeleton and geographic starts; at least two restarts are needed.
- Archive/restart selection defaults to lexicographic `(hard violation count,
  crossings, zigzags, energy)`. Annealing acceptance still uses the weighted
  energy. `feasibility_priority` and `zigzag_priority` control this safeguard.
- Cost evaluation is **incremental**: on moving node v, re-route only the incident edges, re-evaluate only terms touching v, its neighbours, and (via a spatial grid index) nearby nodes/edges for H1, H5, S1.
- Schedule: T0 so that ~60% of uphill moves are accepted, geometric cooling (×0.995–0.999 per sweep), stop when no improvement in N sweeps or when a fixed budget is hit. Run `R` restarts (default 8, in parallel) and keep the best.
- Finish with a **greedy descent** (accept only improving moves) at the fine grid.
- Determinism: all randomness from a seeded PRNG; restart `i` uses `seed + i`.

### Stage 4 — Final routing and refinement

- Re-route every edge with the full candidate set (more samples for 3-segment routes).
- Local search tries incident-star routing orders and node moves at configured
  fine-grid step scales for hard violations, crossings and nearby zigzags.
  Acceptance improves the archive rank; hard constraints are always measured.
- Verify all hard constraints; produce a violation report (also in `metrics`).

### Stage 5 — Bundle order and labels

**Bundle ordering.** For each bundle, choose the order of lines (and `line_offsets`) to minimize line crossings at the bundle ends. Approach: local ordering by the direction in which each line leaves the bundle at each end (cf. Metro-line crossing minimization); small bundles (≤ 6 lines) can use exhaustive search. Ensure that lines which continue straight through a junction keep their relative side.

**Labels.** Candidate positions for each node: 8 anchors (N, NE, E, SE, S, SW, W, NW), optionally rotated 45° text for dense areas. Cost: overlap with edges (high), overlap with other labels (high), overlap with nodes (high), preference order E > W > N > S > diagonals, and label close to its marker. Solve with greedy + local swaps, or an ILP/graph-coloring approach if conflicts remain. Text width estimates must account for CJK glyph widths (full-width ≈ 1 em).

---

## 7. Edge Routing: Candidate Polylines

Given endpoints P → Q with offset `(dx, dy)`, enumerate candidate paths with ≤ 3 segments (≤ 2 bends) from the 8 directions:

1. **Straight**: valid if the direction is axis-aligned exactly, or the bearing is within 15° of a diagonal.
2. **One bend** (2 segments): directions `d1, d2` with turn 45° or 90° such that `a·d1 + b·d2 = (dx, dy)`, `a, b > 0` (solve the 2×2 linear system; reject if singular or negative). Both orders (d1 first or d2 first) are candidates, so the dogleg can be placed at either end.
3. **Two bends** (3 segments): directions `d1, d2, d3` with each consecutive turn of 45° or 90°; one free length parameter sampled at a few values (e.g. 25%, 50%, 75% of the middle segment), others solved.
4. The first segment direction at P is the **port** at P and must obey H6; likewise the last segment at Q.
5. Each segment length must satisfy a minimum (default 0.3) to avoid tiny jogs.

Candidate score = `w_len·(len − L_target)² + w_bend·bends + w_ang·angle_penalty + w_cross·crossings + clearance penalties`. Cache candidates per (dx, dy, port constraints). Preference order for ties: straight > 1 bend (diagonal then axis) > 2 bends. Prefer the axis-aligned segment next to the *interchange or key node* and the diagonal next to the through node (a common cartographic convention).

---

## 8. Parallel Lines (Bundles)

- Edges with `len(lines) > 1` are drawn as parallel strokes offset perpendicular to the path by `line_offsets` (spacing = line width + gap).
- At bends, offset polylines use miter or round joins with a miter limit; at junctions where bundles split, strokes separate smoothly (short diagonal transition of length ≈ 0.5 grid units, cosmetic).
- Bundle width is included in H5 clearance and in the S1 crossing logic (a crossing between bundles counts once).

---

## 9. Rendering

Both outputs must be generated from the JSON only.

1. **Common SVG generator** (single source of truth): lines drawn as stroked polylines with round caps; corners rounded with radius ≈ 0.3 grid units (cosmetic; do not alter topology). Stations: dot (through/terminal), white circle with black outline (interchange), and capsule/pill for adjacent interchange nodes (optional). Labels use `label.anchor`.
2. **PNG**: SVG → PNG via `resvg` or `cairosvg`; configurable DPI and padding; bundle a CJK-capable font (e.g. Noto Sans CJK), no reliance on system fonts.
3. **Interactive component**: a web component (`<transit-map src="...">`) rendering the same SVG, with pan/zoom (d3-zoom or equivalent), pinch/touch support, level-of-detail labels (hide through-station labels at low zoom), hover/click events on stations and lines, highlight-line-on-hover. No dependency on a server.
4. Use the line color from `lines[].color`; if two adjacent colors have low contrast with the background, add a thin outline (config).

---

## 10. Metrics and Acceptance

`metrics` is written to the output and used for regression tests and tuning:

| Metric | Target |
|---|---|
| `hard_violations` (H1–H7) | 0 |
| `crossings` | 0 for planar-capable inputs |
| `bends_total`, `bends_per_edge_mean` | minimize; mean < 0.5 typical |
| `angle_dev_mean` / `max` (outside zero-penalty zone) | 0 |
| `edge_len_cv` (coefficient of variation within chains) | < 0.25 |
| `min_station_distance` | ≥ `d_min` |
| `collinearity_dev_mean` (deg) | < 5° |
| `geo_direction_dev_mean` (deg) | < 25° |
| `geo_displacement_rms` | report only |
| `circular_order_violations` | 0 |
| `label_overlaps` | 0 |
| `runtime_s` | report |
| `turns_per_line` | minimize; includes station turns |
| `zigzag_count` | 0 on single-line and Shinkansen fixtures |
| `mean_straight_run` | report, grid units |
| `long_run_fraction_per_line` | ≥0.8 of length in runs spanning ≥3 stations, outside dense cores |
| `primary_axis_angle_error_deg` | ≤5° when primary eligible; null for isotropic/degenerate PCA |
| `key_node_spearman` (x, y) | ≥0.6 against transformed, unpacked geography |
| `key_node_spearman_by_component` | report component-local correlations to diagnose packing |

---

## 11. Software Architecture

Language: Python 3.11+ for the layout engine (numpy; optional numba for the inner loop, shapely or a custom spatial grid index). Rendering is separate (JS for the web component).

Suggested layout:

```
schematic_map/
  io/            load.py, validate.py, export.py
  graph/         build.py, chains.py, derived.py
  geo/           projection.py
  layout/
    transform.py        # Stage 1
    init.py             # Flat Stage 2
    skeleton.py         # Coarse keys/chains and arc-length expansion
    reference.py        # Smoothed geographic chains
    line_geometry.py    # Line turns, zigzags and straight runs
    primary.py          # Primary-line selection and PCA measurements
    anneal.py           # Stage 3
    moves.py
    routing.py          # §7 candidates
    refine.py           # Stage 4
    bundles.py          # Stage 5a
    labels.py           # Stage 5b
    energy/
      base.py           # Term interface
      hard.py, soft.py  # H*, S* terms
  render/        svg.py, png.py
  web/           transit-map.js
  metrics.py
  config/default.yaml
  tests/
```

**Term interface** (pluggable; terms can be added or removed from config without code changes elsewhere):

```python
class Term:
    name: str
    kind: Literal["hard", "soft"]
    weight: float          # from config
    def full(self, layout) -> float: ...
    def delta(self, layout, move) -> float:   # incremental; may fall back to full()
        ...
```

Config (YAML) lists enabled terms, weights, and parameters:

```yaml
seed: 42
grid: {d_min: 1.0, pitch_coarse: 1.0, pitch_fine: 0.25}
transform: {theta_max_deg: 30, aspect_range: [0.7, 1.4], lambda_theta: 0.01, lambda_s: 1.0}
terms:
  H1_min_spacing: {enabled: true}
  S1_crossings: {enabled: true, weight: 1000}
  S2_edge_length: {enabled: true, weight: 5, a: 1.0, b: 0.3, d0_km: 5}
  S5_collinearity: {enabled: true, weight: 2, linear: true}
anneal: {restarts: 8, cooling: 0.997, max_sweeps: 5000}
```

Engineering rules:

- Pure functions where possible; layout state is a small immutable-friendly structure (positions array + cached routes).
- Every term has unit tests with hand-computed values.
- Layout JSON is validated against a JSON Schema in CI.
- Same seed + input + config ⇒ identical output.

---

## 12. Test Plan

Test fixtures (in order of difficulty):

1. Single straight line (5 stations) — must come out straight, evenly spaced.
2. Single line with a 90° geographic turn — one bend or a diagonal; check bend count.
3. Y-junction (three branches) — circular order preserved, no shared ports.
4. Two lines sharing a trunk (bundle) — correct `line_offsets`, no crossings.
5. Grid-like network with an interchange crossing — correct crossing handling at nodes.
6. Loop line (Yamanote-like) with spurs — hardest; expected result is octagon-like.
7. The Shinkansen sample, scaled up (long edge vs short edge: Tokyo–Ueno 3.6 km vs Ueno–Omiya 27.7 km).
8. Disconnected components.
9. Dense urban core (many stations < 2 km apart) — checks H1 and label placement.

Property tests: random planar graphs ⇒ zero hard violations; rotating the input by arbitrary φ ⇒ Stage 1 recovers θ ≈ −φ (within regularization); scaling coordinates by a constant ⇒ same layout.

Visual regression: render PNGs and compare using a perceptual diff with tolerance; store goldens.

---

## 13. Milestones

1. **M1**: IO, validation, derived fields, projection, JSON Schema; render raw geographic map to SVG/PNG (sanity check).
2. **M2**: Stage 1 transform; Stage 2 init; renderer with straight edges.
3. **M3**: Routing candidates (§7) and energy terms H1–H6, S1–S5, S2; Stage 3 annealing; fixtures 1–5 pass.
4. **M4**: S6–S9, H7; Stage 4 refinement; metrics output.
5. **M5**: Bundles and labels (Stage 5); fixtures 6–9.
6. **M6**: Web component with pan/zoom and level-of-detail.
7. **M7**: Performance tuning (numba/parallel restarts), config documentation.

---

## 14. Open Questions / Assumptions to Confirm

- `distance` assumed to be in km along the track (not straight-line); confirm.
- `schematic` field semantics (§2.3) — currently treated as an optional hint.
- Expected network size (stations/lines) determines whether annealing is fast enough or a grid-routing (LOOM-style) alternative is needed. The alternative is to build an octilinear grid graph and route edges as shortest paths with bend/occupancy costs; it guarantees octilinearity but conflicts with the ±15° diagonal tolerance.
- Whether lines with different geographic positions but the same shared track should be bundled when the input lists them as separate edges (current rule: input is non-multigraph; bundle = one edge with several `lines`).
- Treatment of very long edges (e.g. Shinkansen between distant cities): a "break" or compressed-edge symbol may be desired (not in v0.1).
- Target output canvas sizes and font choices for the PNG.
## Smoothing implementation and validation notes

The exact implemented formulas, weighting conventions, label objective and
Stage 1 objective are documented in [CONSTRAINTS.md](CONSTRAINTS.md). The node
energy is the sum of all enabled weighted H/S terms. S10 is separate label
placement. Disabled hard terms still appear in final verification.

Every new term has a hand-computed unit test. Seeded restarts and stable tie
breaking preserve reproducibility; `runtime_s` is null unless requested.

The acceptance criteria are quality targets, not a claim that finite-weight
annealing proves feasibility. The staged results and remaining failures are in
[reports/smoothing-progress.md](reports/smoothing-progress.md). Current supplied
large fixtures are JRE and JRW, not identified Tokyo-only or whole-Japan inputs.
The comparison runner stores JSON, PNG and exact configuration under
`output/comparisons/<stage>/`; its bounded budgets differ from default search
budgets. Measurement-only stages retain the saved geometry and PNGs and record
that provenance explicitly.
