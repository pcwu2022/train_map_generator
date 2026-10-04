# Schematic smoothing comparisons

Fixtures: `data/graphs/jre_shinkansen.json` (68 stations), `jre.json`
(1,646 stations), and `jrw.json` (1,143 stations). No separate Tokyo-only or
whole-Japan fixture was identified; these labels refer to the actual inputs.

The baseline was captured from the pre-A engine (`a902eda`) with bounded
large-network smoke budgets. A–C used the flat initialization; D–E used the
skeleton at the same outer budgets. Skeleton routing has its own configured
coarse passes, so its total routing work is greater. F/G measure frozen E
geometry; they do not claim a fresh optimization or changed rendering.
Each folder under `output/comparisons/` contains JSON, PNG, metrics and the
saved configuration. Generated artifacts are ignored by Git.

## A — line turns, zigzags and short runs

| Fixture | Hard before → after | Crossings before → after | Zigzags before → after | Bends before → after |
|---|---:|---:|---:|---:|
| jre_shinkansen | 0 → 0 | 0 → 0 | 36 → 35 | 69 → 69 |
| jre | 11 → 11 | 28 → 28 | 1421 → 1421 | 1770 → 1770 |
| jrw | 4 → 4 | 8 → 8 | 978 → 978 | 1209 → 1209 |

## B — linear costs and longer segments

| Fixture | Hard before → after | Crossings before → after | Zigzags before → after | Bends before → after |
|---|---:|---:|---:|---:|
| jre_shinkansen | 0 → 0 | 0 → 0 | 36 → 36 | 69 → 51 |
| jre | 11 → 78 | 28 → 211 | 1421 → 1228 | 1770 → 1835 |
| jrw | 4 → 24 | 8 → 74 | 978 → 835 | 1209 → 1229 |

## C — smoothed references and key-only geography

| Fixture | Hard before → after | Crossings before → after | Zigzags before → after | Bends before → after |
|---|---:|---:|---:|---:|
| jre_shinkansen | 0 → 0 | 0 → 0 | 36 → 35 | 69 → 44 |
| jre | 11 → 82 | 28 → 244 | 1421 → 1222 | 1770 → 1920 |
| jrw | 4 → 18 | 8 → 62 | 978 → 745 | 1209 → 1082 |

## D — key-node skeleton and corridor routing

| Fixture | Hard before → after | Crossings before → after | Zigzags before → after | Bends before → after |
|---|---:|---:|---:|---:|
| jre_shinkansen | 0 → 0 | 0 → 0 | 36 → 1 | 69 → 7 |
| jre | 11 → 20 | 28 → 52 | 1421 → 65 | 1770 → 258 |
| jrw | 4 → 3 | 8 → 16 | 978 → 33 | 1209 → 122 |

## E — primary alignment, rotation moves and geographic/skeleton restarts

The same bounded smoke budgets were retained. One restart in this comparison
exercises the skeleton start; the separate longer run uses two restarts to
exercise both starting layouts. Refinement now targets hard failures first,
then residual zigzags, with configurable star-order and step-scale proposals.

| Fixture | Hard before → after | Crossings before → after | Zigzags before → after | Bends before → after |
|---|---:|---:|---:|---:|
| jre_shinkansen | 0 → 0 | 0 → 0 | 36 → 2 | 69 → 13 |
| jre | 11 → 21 | 28 → 93 | 1421 → 77 | 1770 → 267 |
| jrw | 4 → 7 | 8 → 14 | 978 → 34 | 1209 → 123 |

## F — final line and geography diagnostics

Geometry is unchanged from E. Metrics were recomputed from saved routes and
the original graph; PNGs were copied unchanged. Baseline diagnostics were
backfilled using the same metric definitions. JSON and provenance are stored
under `output/comparisons/F/`.

| Fixture | Turns before → after | Mean run before → after | Axis error ° before → after | Spearman x before → after | Spearman y before → after |
|---|---:|---:|---:|---:|---:|
| jre | 1861 → 623 | 1.614 → 13.859 | 18.492 → 1.418 | 0.984 → 0.923 | 0.865 → 0.877 |
| jre_shinkansen | 69 → 15 | 2.320 → 10.462 | 36.527 → 2.758 | 0.952 → 0.998 | 0.991 → 1.000 |
| jrw | 1233 → 303 | 1.649 → 17.747 | 74.822 → 35.962 | 0.876 → 0.860 | 0.407 → 0.437 |

## G — configuration, constraints and final audit

Geometry and PNGs are unchanged from F; the same measurement definitions and
schema checks were applied. The hard/crossing/zigzag/bend comparison is:

| Fixture | Hard before → after | Crossings before → after | Zigzags before → after | Bends before → after |
|---|---:|---:|---:|---:|
| jre_shinkansen | 0 → 0 | 0 → 0 | 36 → 2 | 69 → 13 |
| jre | 11 → 21 | 28 → 93 | 1421 → 77 | 1770 → 267 |
| jrw | 4 → 7 | 8 → 14 | 978 → 34 | 1209 → 123 |

| Fixture | Hard | Crossings (baseline) | Zigzags | Primary axis ° | Key Spearman x / y | Lines meeting straight-run target |
|---|---:|---:|---:|---:|---|---:|
| jre | 21 | 93 (28) | 77 | 1.418 | 0.923 / 0.877 | 55/100 |
| jre_shinkansen | 0 | 0 (0) | 2 | 2.758 | 0.998 / 1.000 | 3/6 |
| jrw | 7 | 14 (8) | 34 | 35.962 | 0.860 / 0.437 | 37/57 |

Every line is reported; no dense-core exemption was inferred. Undefined PCA
axes and correlations are recorded as null. Primary alignment applies only
when the transform reports an eligible primary; zero zigzags is a target
for single-line/Shinkansen inputs. This report does not infer fixture classes.
Exact failures and configured thresholds are in `acceptance.json`.

All H1–H7 definitions and final verification remain active. The engine reports
infeasible results rather than declaring them valid. The bounded run does
**not** meet all requested acceptance criteria. In particular, hard failures,
crossing regressions, short-run fractions and JRW y correlation remain.
No dense-core exception has been automatically applied. Seven JRE lines and
four JRW lines contain only two stations, so those lines cannot meet a target
requiring runs spanning three stations without an explicit exception.

Changed weights and their rationale are listed in
[CONSTRAINTS.md](../CONSTRAINTS.md). The core algorithm is described briefly in
[ALGORITHM.md](../ALGORITHM.md). The complete suite currently has 105 passing
tests, including hand-computed new costs, deterministic serial/parallel
restarts, legacy rendering, schema validation and real browser interaction.

To reproduce a new bounded comparison and audit it:

```sh
.venv/bin/python tools/layout_benchmark.py --stage current --config tests/config/smoothing.yaml
.venv/bin/python tools/layout_report.py output/comparisons/current
```

The separate longer comparison uses `tests/config/smoothing_quality.yaml`
(two restarts, 200 annealing proposals, 256 refinement trials per component).
It uses a larger budget and is reported separately from A–G.

## Longer two-start comparison

| Fixture | Hard | Crossings (baseline) | Zigzags | Primary axis ° | Key Spearman x / y | Lines meeting straight-run target |
|---|---:|---:|---:|---:|---|---:|
| jre | 4 | 61 (28) | 91 | 1.307 | 0.921 / 0.877 | 38/100 |
| jre_shinkansen | 0 | 0 (0) | 0 | 0.903 | 0.936 / 1.000 | 3/6 |
| jrw | 1 | 16 (8) | 62 | 34.173 | 0.859 / 0.436 | 23/57 |

Every line is reported; no dense-core exemption was inferred. Undefined PCA
axes and correlations are recorded as null. Primary alignment applies only
when the transform reports an eligible primary; zero zigzags is a target
for single-line/Shinkansen inputs. This report does not infer fixture classes.
Exact failures and configured thresholds are in `acceptance.json`.

This run exercises skeleton/geographic restarts and longer local repair. It is
not the unrestricted default search. JSON, PNG, configuration and exact
per-line acceptance failures are in `output/comparisons/quality/`.

Shinkansen meets hard/crossing/zigzag, primary-axis and rank-correlation targets;
three branch lines remain below 80% straight-run coverage. JRE has one H6 port
conflict at `JRE_TOH_010` and three H7 order conflicts (`JRE_TOH_001`,
`JRE_TOH_003`, `JRE_SKY_006`). JRW has an H7 conflict at `JRW_Sanyo_19`.
Large-network crossings still exceed baseline, and JRW global y correlation is
below 0.6. Longer repair improved feasibility while increasing turns and
reducing straight-run coverage relative to the bounded E run; both outcomes
are retained so this tradeoff is visible.

Full acceptance remains unmet. No mathematical feasibility guarantee, automatic
dense-core exemption, or whole-Japan/Tokyo fixture identity is claimed.
