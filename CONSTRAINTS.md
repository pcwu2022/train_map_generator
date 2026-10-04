# Constraints and cost function

This guide describes the **current implementation** of the schematic-map layout
engine. The design specification is [SPEC.md](SPEC.md), especially §5. Tunable
thresholds, enabled terms, and weights live in
[default.yaml](schematic_map/config/default.yaml); a user YAML file can override
them.

## Notation

- `p_v`: schematic position of station `v`, in grid units.
- `a_v`: transformed and scaled geographic reference position of that station.
- `P_e`: polyline connecting the endpoints of edge `e`.
- `l_e`: sum of the Euclidean lengths of the segments of `P_e`.
- `b_e`: number of interior vertices (bends) of `P_e`.
- `d_geo,e`: input track distance in kilometres, or haversine distance if omitted.
- `max(0, x)`: zero when `x` is negative, otherwise `x`.
- All angular deviations below are measured in **degrees**. Angle differences use
  the smaller circular difference, between 0° and 180°.

The implementation uses a small numerical epsilon for geometry comparisons.

## Hard constraints: H1–H7

These requirements determine whether the final layout is feasible. During
optimization they contribute large, **finite** penalties, allowing annealing to
visit infeasible intermediate states. Each hard term has a default weight of
**1,000,000**. The optimizer does not mathematically guarantee feasibility: every
final result is checked and any remaining violations are reported.

### H1 — Minimum station spacing (`H1_min_spacing`)

Every pair of stations must be at least `d_min` apart, and every edge's total
polyline length must be at least `d_min`. The default is **1.0 grid unit**.

The raw cost measures the normalized shortfall, rather than just counting failures:

```text
H1 = Σ_{unordered station pairs u,v} max(0, (d_min - ||p_u - p_v||) / d_min)
   + Σ_edges e max(0, (d_min - l_e) / d_min)
```

For example, two stations 0.75 units apart with `d_min = 1` contribute 0.25,
which becomes a cost of 250,000 after weighting. Violation reports count each
failing pair or edge separately.

### H2 — Bend limit (`H2_bend_limit`)

Each edge may have at most **two bends**, hence at most three segments or four
polyline points.

```text
H2 = number of edges for which b_e > 2
```

Candidate generation normally enforces this limit before energy evaluation.

### H3 — Bend angle (`H3_bend_angle`)

The direction change at every bend must be exactly **45° or 90°**, within
numerical tolerance. Turns of 0°, 135°, or 180° are invalid.

```text
H3 = number of bends with a turn other than 45° or 90°
```

This uses the actual consecutive segment directions, not the chord joining the
edge's stations.

### H4 — Segment directions (`H4_segment_direction`)

Horizontal and vertical segments must be axis-aligned. Diagonal segments may
deviate from their nearest 45° diagonal by up to **15°**, allowing bearings
30°–60° in each quadrant. Other directions are invalid. A zero-length segment
is also invalid.

```text
H4 = number of segments outside the permitted direction set
```

The diagonal tolerance does not relax H3: a bend still needs a 45° or 90° turn.
Allowed diagonal segments are drawn as computed, without snapping to exactly 45°.

### H5 — Clearance from unrelated stations (`H5_node_clearance`)

An edge must remain clear of every station other than its own endpoints. Measure
`distance(v, P_e)` as the minimum distance from station `v` to any segment of
that edge's path.

The effective clearance increases with the number of bundled lines:

```text
r_e = routing.clearance
    + (number_of_lines_on_e - 1) × (line_width + bundle_gap) / 2

H5 = Σ_edges e Σ_stations v not endpoints of e
     max(0, (r_e - distance(v, P_e)) / r_e)
```

The base clearance is **0.35 units**, line width **0.10**, and bundle gap **0.035**.
A two-line bundle therefore has clearance 0.4175 units. The base clearance already
represents the single-line/marker allowance; the extra term expands it for wider
bundles. The report counts each failing edge–station pair once.

### H6 — Unique and separated ports (`H6_ports`)

At a station, every incident edge's outward path tangent is assigned to its
nearest one of eight compass directions. No two incident edges may use the same
port, and their actual outward bearings must differ by at least **45°**.

```text
H6 = number of incident-edge pairs sharing a port
     or separated by less than 45°
```

Both conditions matter because diagonal tolerance can allow distinct nominal
ports whose actual bearings are too close. At a target endpoint the outward
vector points back along the last segment toward the previous polyline vertex.

### H7 — Circular neighbor order (`H7_circular_order`)

The cyclic order of incident edges around a station must match the order in the
transformed, unsmoothed geographic reference layout. Rotating the whole ordered list is
allowed; reversing it or swapping neighbors is not.

```text
H7 = number of stations whose incident-edge cyclic order differs
```

The implementation compares consistently ordered bearings of geographic chords
against routed endpoint tangents. Stations with fewer than three incident edges
cannot violate this cyclic-order comparison.

## Soft penalties: S1–S14

These terms trade off appearance and geographic fidelity. Their being nonzero
does not by itself make a layout infeasible.

| Term | Default weight | Raw term before weighting |
|---|---:|---|
| S1 `S1_crossings` | 1000 | Number of distinct edge pairs with proper path crossings |
| S2 `S2_edge_length` | 5 | Sum of squared relative deviations from target edge length |
| S3 `S3_angle` | 2 | Outside-zone squared deviation plus in-tolerance diagonal deviation / tolerance |
| S4 `S4_bends` | 3 for the first bend; 8 extra for the second | Special bend cost described below |
| S5 `S5_collinearity` | 2 | Sum of tangent deviations / 45° |
| S6 `S6_direction` | 10 | Sum of chain-chord deviations beyond 45°, divided by 45° |
| S7 `S7_displacement` | 0.05 | Mean squared centered displacement at key nodes |
| S8 `S8_chain_spacing` | 10 | Sum of normalized edge-length variances within chains |
| S9 `S9_compactness` | 0.1 | Area of the station-position bounding box |

### S1 — Crossings

Count each edge pair once if any of their segments cross properly. A shared
endpoint does not count as a crossing. Multiple intersections between the same
pair still count once, and a bundle is treated as one graph edge. This check uses
the centerline paths; it does not compute intersections of rendered stroke areas.
Collinear overlaps and endpoint touches are not proper crossings. Node clearance
and port checks cover some of those conflicts separately.

### S2 — Target edge lengths

Long geographic distances are compressed logarithmically while short edges keep
a minimum schematic length:

```text
L_target,e = max(d_min, a + b × ln(1 + d_geo,e / d0))
S2 = Σ_edges e ((l_e - L_target,e) / L_target,e)²
```

Defaults: `a = 1.0`, `b = 0.3`, `d0 = 5 km`. Scoring uses routed path length,
not endpoint-to-endpoint chord length.

### S3 — Segment angle deviation

For a nonzero segment, let `q` be its bearing modulo 90°. Axis-aligned segments
have zero deviation. Other segments use:

```text
deviation = max(0, |q - 45°| - diagonal_tolerance_deg)
S3 = Σ_segments deviation²
```

H4 still treats diagonals within ±15° as feasible. With
`S3_angle.exact_diagonal: true`, S3 additionally charges
`|q - 45°| / diagonal_tolerance_deg` on those feasible diagonals only.
Axes cost zero. At 50°, the raw cost is `5/15 = 1/3`, weighted cost `2/3`.
At 20°, outside-zone deviation is 10°, so raw cost is 100 and weighted
cost is 200; no in-tolerance term is added. Zero-length segments get a
180° outside-zone deviation. `exact_diagonal: false` restores the older form.

### S4 — Bend count

For feasible routes, the **weighted contribution** per edge is:

```text
0 bends:  0
1 bend:   weight
2 bends:  weight + second_bend
```

Defaults therefore give costs **0, 3, and 11**. `second_bend = 8` is an additional
absolute cost, not another factor multiplied by `weight = 3`.

To fit the common weighted-term interface, the raw implementation is:

```text
S4 = Σ_edges min(b_e, 1)
   + number_of_edges_with_b_e_above_1 × second_bend / weight
```

A zero S4 weight disables the entire bend contribution. Paths with more than two
bends are invalid under H2; S4 does not add further bend charges beyond the second.

### S5 — Collinearity along a line

For each station and line with exactly two incident edges carrying that line,
compare the two **outward routed tangents**. Straight continuation has an angle
of 180°:

```text
S5 = Σ_eligible station–line pairs |180° - tangent_separation| / 45°
```

Eligibility is per line, including a junction with exactly two incident
edges carrying that line. A 45° turn contributes raw 1, weighted 2; a
90° turn contributes raw 2, weighted 4. The linear form avoids favoring
many small turns over one decisive turn. `linear: false` restores the square.

### S6 — Preserve chain direction

Smooth the projected geographic chain with Ramer–Douglas–Peucker simplification
(default tolerance 5 km), resample at the original stations' arc fractions,
and apply four low-pass iterations with alpha 0.5. Key endpoints remain fixed.
Compare only each open chain's key-to-key geographic and schematic chords:

```text
S6 = Σ_open chains max(0, angular_difference - tolerance_deg) / 45°
```

Tolerance defaults to 45°. Through-station geography is absent from this term;
closed chains have no endpoint chord and are skipped. A 90° difference costs
raw 1, weighted 10. `chain_only: false` restores the per-edge quadratic form.
`reference.enabled: false` bypasses reference smoothing.

### S7 — Geographic displacement at key nodes

Keys are terminals, junctions, or interchange stations. Center the two key
point clouds before comparison:

```text
S7 = mean_over_keys ||(p_v - mean_key(p)) - (a_v - mean_key(a))||²
```

Weight is 0.05. The reference is already transformed and scaled to grid units;
through stations contribute nothing. Empty key sets cost zero.
`key_only: false` restores the all-station displacement term. S6/S7 can also
be disabled individually with their `enabled` flags.

### S8 — Even spacing along chains

A chain is a maximal path between key stations, possibly a closed loop. For each
chain with at least two edges and positive mean length:

```text
S8 = Σ_chains variance(edge_lengths / mean_chain_edge_length)
```

Dividing by the chain's mean length makes this a relative spacing penalty.
The variance uses the population convention, dividing by the number of edges.
Terminals, junctions, and interchanges delimit chains.

### S9 — Compactness

```text
S9 = (max_station_x - min_station_x)
   × (max_station_y - min_station_y)
```

This discourages excessive expansion. The implementation uses station positions;
it does not include route bends or label extents in this cost.

### S11 — Turns along complete lines

For each line, build deterministic edge-disjoint walks, splitting at stations
whose degree on that line differs from two. Orient and concatenate the routed
paths, then count direction changes of at least 45° (configurable via
`line_geometry.turn_threshold_deg`). Turns at stations and the seam of a loop
count. Each shared path is counted separately for each line using it.

```text
S11 = sum(turns_per_line.values())
```

Weight is 6. Branches have no ambiguous through-pairing: each branch walk
ends at the fork; S5 still measures a line with two incident edges there.

### S12 — Nearby opposite turns (zigzags)

Consecutive thresholded turns form a zigzag when their signed turns have
opposite signs and their arc-length separation is strictly less than
`zigzag_window = 3.0`. Include the wraparound pair on a closed walk.

```text
S12 = number of qualifying consecutive opposite-turn pairs
```

Weight is 12. Exactly three units apart does not qualify. Distance is routed
arc length, not Euclidean distance between turns.

### S13 — Minimum straight runs

Split each walk into maximal constant-direction runs, merging equal directions
across a loop's seam. Ignore runs ending at a terminal of that line (line degree
one); branch boundaries alone are not terminals.

```text
S13 = Σ_nonterminal runs with length < run_min
      ((run_min - length) / run_min)²
```

`run_min = 1.5`, weight 5. A nonterminal one-unit run has raw cost 1/9.
For `(0,0) → (1,0) → (1,1) → (2,1)`, S11=2, S12=1 and S13=1/9;
their total weighted contribution is `24 + 5/9`.

### S14 — Geographic relative order (optional)

Within each connected component, select each key's `k = 4` nearest geographic
keys. Deduplicate unordered pairs. For each selected pair and each coordinate
axis, charge one if its schematic order reverses its geographic order.
Geographic ties and schematic ties are not flips.

```text
S14 = Σ_selected unordered pairs Σ_axes
      indicator(reference_difference × schematic_difference < 0)
```

Default weight 5, disabled by default. Pair selection uses transformed geographic
references and never compares keys in disconnected components.

## Label clearance: S10, a separate placement stage

Labels are placed **after** node optimization. S10 is a design objective, not a
registered term in the node-layout energy. Each station has eight anchor directions at each configured offset scale
(defaults 1, 1.5, 2); optional rotated candidates can also be enabled.

The label placement score is:

```text
label_score = labels.overlap_weight × number_of_conflicts
            + anchor_preference_rank
            + labels.distance_weight × (offset_scale - 1)
```

A conflict is an overlapping label, an overlapping station-marker rectangle, or
an edge whose path intersects the candidate label rectangle. Each edge counts
once. The default overlap weight is **1000**. The preference ranks are:

```text
E = 0, W = 1, N = 2, S = 3, NE = 4, NW = 5, SE = 6, SW = 7
```

Candidates use a configured offset (default **0.5 units**) and Unicode-aware text
width estimates. Greedy placement, repeated local updates, and pair swaps try to
reduce conflicts. Remaining conflicts are reported in `metrics.label_overlaps`.
They do not contribute to `meta.feasible` or the node-layout energy.

## Final layout cost function

For a layout `L`, the implementation evaluates every **enabled** term and sums
its weighted value:

```text
E(L) = Σ_enabled terms t weight_t × t.full(L)
```

With the default configuration and feasible routes of at most two bends:

```text
E = 1,000,000 × (H1 + H2 + H3 + H4 + H5 + H6 + H7)
  + 1000 × S1
  +    5 × S2
  +    2 × S3
  +    3 × number_of_edges_with_at_least_one_bend
  +    8 × number_of_edges_with_two_bends
  +    2 × S5
  +   10 × S6
  + 0.05 × S7
  +   10 × S8
  +  0.1 × S9
  +    6 × S11 + 12 × S12 + 5 × S13
  +    5 × S14   # only when explicitly enabled
```

**Lower cost is better.** The finite hard weights are barriers, not a
lexicographic guarantee that every hard constraint outweighs all possible soft
costs. Disabled terms contribute nothing to optimization, but final hard
verification still checks all H1–H7 constraints. Custom registered terms can add
other contributions through the same interface.

During annealing, a proposal has `delta_E = E(new) - E(current)`. Improving moves
are accepted; uphill moves are accepted with probability
`exp(-delta_E / temperature)`. Cooling gradually reduces acceptance of uphill
moves. The default archive and restart selection use lexicographic ranking
`(hard violation count, crossing count, zigzag count, E)`. Greedy descent
requires both lower E and improved rank; refinement accepts improved rank,
even at higher E. Annealing still accepts proposals by the energy rule above.
These safeguards do not redefine H1–H7 or guarantee that a feasible state
will be discovered. Disable `feasibility_priority` to select purely by energy,
or `zigzag_priority` to omit zigzags from the rank. Moving a
station reroutes its incident edges; incremental scoring reuses cached facts
where possible and falls back to full term evaluation otherwise.

### Feasibility is checked separately from cost

`metrics.hard_violations` counts violation records; it is **not** the weighted
hard energy. In particular, H1 and H5 energy measure shortfall magnitude while
their reports count failing pairs.

```text
meta.feasible = (metrics.hard_violations == 0)
```

A finite or relatively low energy does not establish feasibility. Crossings,
label overlaps, bend means, and geographic quality metrics are additional
acceptance/tuning targets. The CLI writes diagnostic output and exits with code
2 when hard violations remain, unless `--allow-infeasible` is supplied.

## Other checks and objectives

These rules are separate from the final node-layout energy:

- **Input validation:** unique IDs, known endpoints and lines, valid coordinates,
  nonnegative distances, no self-loops or duplicate undirected edges, and station
  degree at most eight. Invalid inputs fail before optimization. Duplicate
  geographic coordinates produce warnings and deterministic projection nudges.
- **Router minimum segment length:** candidate segments normally must be at least
  **0.8 units**, preventing tiny jogs. If no candidate exists, an explicitly scored
  infeasible straight fallback can be returned for diagnosis.
- **Router candidate score:** a local selection heuristic uses length, bends,
  clearance, ports, circular order, collinearity, and crossing penalties. It is
  not the complete `E(L)` above; the resulting full layout is scored afterward.
- **Global transform search:** use smoothed open-chain chords weighted by
  smoothed chain length times prominence (2 for flagged lines or the line with
  most stations; otherwise 1). The objective is the weighted sum of squared
  nearest-octilinear angular deviations plus `lambda_theta × theta²` and
  `lambda_s × ln(aspect)²`. Angles here use radians, unlike node-layout terms.
  Defaults are ±45° search and `lambda_theta = 0.0001`. A length-weighted PCA
  candidate aligns the primary line to y. Eligible lines are flagged, or have
  an original smoothed PCA axis within 45° of vertical. Eligible transform
  candidates beyond 5° of vertical are excluded; others additionally pay
  `primary_axis.weight × primary_length × error_radians²` (default weight 50).
  Flagged lines may use a PCA candidate outside the normal rotation cap.
  This is a Stage 1 objective, not a final-layout constraint: later stages can
  alter the axis, so final metrics measure it again. Degenerate/isotropic PCA
  has no axis and is reported as null.
- **Skeleton:** keys and chains form a coarse graph. Internal routes may have
  four segments and must be at least `n_edges × d_min × spacing_factor`
  (default factor 1.5). This internal H2 limit never relaxes final-edge H2.
  H7 uses original key incident-edge directions, not smoothed chain chords.
  A local corridor clearance heuristic discourages unrelated chains from
  overlapping. Uniform arc-length expansion places through stations, then
  the final graph is refined and all H1–H7 are checked again. Select
  `init.mode: geo` for the flat stress initialization, or `hint` for supplied
  schematic coordinates; `skeleton.enabled: false` bypasses the coarse stage.
- **Restarts and refinement:** rotate chains or junction branches by ±45°
  (`rotation_moves`), alternate skeleton and geographic starts (`multistart`),
  and retain the best rank. Local repair tries incident-edge routing orders
  (`star_orders`), multiple fine-grid step sizes, and nearby zigzag stations
  (`smoothness`). All flags and budgets live in YAML. Set at least two restarts
  to exercise both initializations.
- **Bundle ordering:** local line-order choices minimize ordering inversions and
  prioritize continuity across previously ordered, near-straight bundles. This
  happens after node optimization and is not a registered energy term.
- **Component packing:** disconnected components are optimized independently,
  then packed with a gap of at least **3 units**, accounting for provisional label
  extents. The packing gap is not an energy term.
- **Output integrity:** schema validation checks the exported structure, and
  semantic checks require path endpoints to equal station positions and bundle
  line IDs to match their offset keys.

## Where the implementation lives

| Responsibility | File |
|---|---|
| Default thresholds and weights | [default.yaml](schematic_map/config/default.yaml) |
| Geometry checks and cached raw measurements | [energy/base.py](schematic_map/layout/energy/base.py), `Layout.facts()` |
| Hard-term adapters | [energy/hard.py](schematic_map/layout/energy/hard.py) |
| Soft-term formulas | [energy/soft.py](schematic_map/layout/energy/soft.py) |
| Enabled-term loading and weighted sum | [energy/base.py](schematic_map/layout/energy/base.py), `configured_terms()` and `energy()` |
| Route candidates and local route scoring | [routing.py](schematic_map/layout/routing.py) |
| Label placement score | [labels.py](schematic_map/layout/labels.py) |
| Global transform objective and target lengths | [transform.py](schematic_map/layout/transform.py) |
| Final metrics and violation reporting | [metrics.py](schematic_map/metrics.py) |

## Diagnostic metrics and current validation

`turns_per_line` and `zigzag_count` use the S11/S12 definitions.
`mean_straight_run` is the unweighted mean routed run length in grid units.
`long_run_fraction_per_line` divides length in runs spanning at least three
stations by total line length; stations on the run boundaries count. The
implementation reports every line, without silently exempting dense cores.

`primary_axis_angle_error_deg` uses length-weighted covariance of the routed
primary line (Gaussian quadrature along each segment), modulo 180° relative to
y. The selected primary is the largest flagged line, otherwise the line with
most stations, with ID tie-breaking.

`key_node_spearman` compares average tie ranks on each axis against transformed,
unpacked geography. Key positions are fixed during smoothing. The global score
includes any effects of component packing; `key_node_spearman_by_component`
provides translation-independent diagnostics for each component. Fewer than two
keys or a constant axis produces null, never a fabricated perfect score.

[reports/smoothing-progress.md](reports/smoothing-progress.md) records staged
metrics and remaining acceptance failures. PNGs, saved configurations and JSON
are in `output/comparisons/`; those generated artifacts are ignored by Git.

## Weight changes and their purpose

| Setting | Previous → current | Purpose |
|---|---|---|
| S3 weight | 20 → 2 | Prefer exact diagonals with a mild linear cost while retaining H4 feasibility |
| S5 weight and formula | 8 squared degrees → 2 linear /45° | Avoid rewarding many small turns over one larger turn |
| S6 tolerance/formula | 22.5° quadratic edges → 45° linear chain chords | Preserve broad direction without reproducing noisy track geometry |
| S7 weight/domain | 0.5 all stations → 0.05 keys | Allow through-station redistribution |
| S8 weight | 3 → 10 | Strengthen even chain spacing |
| S11 / S12 / S13 | new: 6 / 12 / 5 | Charge line turns, nearby reversals and short runs |
| S14 | new: 5, disabled | Optional local geographic order protection |
| S2 logarithmic b | 0.6 → 0.3 | Compress long rural distances more strongly |
| Minimum routed segment | 0.3 → 0.8 | Reduce tiny routing jogs |
| Rotation cap / regularizer | 30° / 0.01 → 45° / 0.0001 | Permit meaningful primary-line alignment |
| Primary-axis objective | new: weight 50 | Prefer vertical eligible primary axes in Stage 1 |

The former rotation regularizer is recorded in the legacy YAML; the new
rotation search uses radians. Acceptance thresholds are configured separately
under `acceptance`; they do not secretly add penalties to final energy.
