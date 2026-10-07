# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Two stages:
1. `generate_graphs.py` (stdlib only) merges `data/geo_raw/<name>.json` + `data/topology_raw/<name>.json` into NetworkX node-link graphs in `data/graphs/` (edges key is `edges`, colors live only on `lines`).
2. The `schematic_map` package turns a graph JSON into an octilinear schematic layout: `layout.json`, `map.svg`, `map.png`, and a static `index.html` viewer using the `<transit-map>` web component (`schematic_map/web/transit-map.js`).

`SPEC.md` is the design spec; `ALGORITHM.md` summarizes the implemented algorithm; `CONSTRAINTS.md` documents every hard/soft term and the cost function (keep it in sync when changing terms or weights). `reports/smoothing-progress.md` records staged fixture results and known acceptance failures.

## Commands

On this Windows machine the venv executables are under `.venv/Scripts/` (README shows POSIX `.venv/bin/`). Run pytest with `PYTHONUTF8=1`: tests use `read_text()` without an encoding and fail under the cp950 default. cairosvg is not installed here, so PNG/visual tests fail locally; use `--no-png`.

```sh
pip install -e . pytest
python generate_graphs.py --distance-tolerance-km 0.05   # JRE/JRW raw data needs the tolerance
python -m schematic_map data/graphs/jre_shinkansen.json -o output/shinkansen [--config X.yaml] [--seed N] [--live] [--no-png]
python -m schematic_map output/shinkansen/layout.json --render-only -o output/rerendered
python -m http.server 8000 --directory output/shinkansen  # viewer needs HTTP, not file://

pytest -q                                   # full suite (CI: Python 3.11, needs libcairo)
pytest tests/test_skeleton.py -q            # single file
pytest tests/test_pipeline.py -k straight   # single test
node --check schematic_map/web/transit-map.js
```

- CLI exits **2** when hard constraints (H1–H7) remain; `--allow-infeasible` overrides. Outputs are still written for diagnosis.
- Large networks (JRE ~1.6k stations, JRW): use `--config tests/config/large_network.yaml`. `fast_preview.yaml` is a reduced-budget config for `--live` previews on huge networks.
- `tests/test_browser.py` needs Playwright + Chromium and skips otherwise. `tests/test_visual.py` compares against `tests/goldens/`.
- `tools/layout_benchmark.py --stage <name>` runs bounded comparisons into `output/comparisons/<stage>/`; `tools/layout_report.py` / `tools/remeasure_layouts.py` report acceptance against `acceptance:` criteria in config.
- `output/` is gitignored.

## Architecture

Entry point `schematic_map/pipeline.py::generate_layout` orchestrates everything:

1. `io/validate.py` + `graph/build.py` → internal graph (nodes, `endpoints`, chains, `components`), `geo/projection.py` projects lon/lat to km.
2. `layout/transform.py` searches a global rotation/aspect (with a PCA candidate from `layout/primary.py` aligning the primary line vertically) → `anchor` positions; `layout/reference.py` smooths geographic chains. Allowed crossings (inherent in straight geographic lines) and close station pairs are precomputed here and stored on the graph.
3. **Per connected component** (components never interact during optimization):
   - default `init.mode: lp` → `layout/lp.py`, ported from `../TRA_Visualization/tools/schematic_layout.py`: chains between degree≠2 key nodes, order-preserving octilinear port assignment, 1–3 piece chain shapes, one scipy HiGHS LP minimizing total length with soft relative-position constraints, re-solved with separation constraints for crossing pieces; stations evenly spaced along each chain. Skips annealing and refine. Goal: clean metro-map style (few bends) over geographic fidelity. Parameters under `lp:` in config.
   - `init.mode: skeleton` → `layout/skeleton.py` routes a key-station skeleton, places through stations at equal arc length; then `layout/anneal.py::optimize` (simulated annealing with seeded restarts, `seed + restart_index`, alternating skeleton and geographic starts; parallel via `anneal.workers`).
   - `init.mode: geo` → `layout/init.py` stress init then anneal.
   - `layout/refine.py` local repair of spacing/clearance/ports/circular order and zigzags.
4. Components are packed left-to-right with ≥3 units gap; `layout/bundles.py` orders parallel lines; `layout/labels.py` places labels; `metrics.py` measures everything; result dict is exported by `io/export.py` (validated against `io/layout.schema.json`) and rendered by `render/svg.py` (PNG via cairosvg in `render/png.py`; the JSON embeds the SVG so browser/PNG share one renderer; CJK glyphs come from the bundled Noto font converted to outlines).

Energy system (`layout/energy/`): `base.py` holds `Layout` (positions, routes, cached facts) and `Term`. Hard terms `H1`–`H7` in `hard.py` (weight 1e6, finite so annealing can pass through infeasible states); soft terms `S1…` in `soft.py`. Terms implement `full(layout)` and optionally incremental `delta(layout, proposed)` — incremental and full evaluation must agree (tested). Terms are enabled/weighted by name under `terms:` in config; custom terms are referenced by fully-qualified class name. Selection order of retained states: hard violation count, crossings, zigzags, then weighted energy.

Routing (`layout/routing.py`, `geometry.py`, `spatial.py`) generates octilinear polylines per edge with cached translation-invariant candidates and a uniform grid for obstacle checks; moves (`layout/moves.py`) reroute only incident edges.

Config: all defaults in `schematic_map/config/default.yaml`; `load_config(path, overrides)` deep-merges partial overrides. Tests use the `fast_config` fixture (tiny anneal budget) and fixture graphs in `tests/fixtures/`.

## Invariants

- Determinism: same input + seed + config must produce byte-identical JSON (serial and parallel restarts). `runtime_s` is `null` unless `--runtime`/`record_runtime=True`. Don't introduce unseeded randomness or order-dependent set iteration in outputs.
- Coordinates are y-up; renderers flip y. Angles in energy terms are degrees.
- The repo tracks both `CONSTRAINTS.md` (real guide) and `constraints.md` (stub pointing to it); on case-insensitive Windows checkouts they collide on one path, so be careful editing/committing either.
