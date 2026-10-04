# train_map_generator
An automation tool that generates railway diagrams

Generate graph JSON files from matching filenames in `data/geo_raw` and
`data/topology_raw` (Python standard library only):

```sh
python3 generate_graphs.py
```

Results are written to `data/graphs`. Override directories with `--geo-dir`,
`--topology-dir`, and `--output-dir`.

Nodes include `id`, `name`, geographic `coordinates` (longitude,
latitude), and `schematic` coordinates when available. `schematic_bends` is
ignored. Consecutive stations in each segment define edges; `distance` is the
absolute difference between the stations' `km` values, so decreasing kilometre
markers also yield nonnegative track lengths.

Shared undirected edges are merged, with all line IDs in `lines`. Conflicting
distances fail by default. For rounded source data, pass
`--distance-tolerance-km 0.05`: differences within that explicit tolerance retain
the first distance and emit a warning; larger conflicts still fail. Colors are
stored only on lines. Missing line colors are generated deterministically and uniquely
within each output graph, avoiding supplied colors. Supplied colors are preserved.
Line metadata appears only in the top-level `lines` field.
`directed` and `multigraph` are both retained as `false`. Node line counts can
be derived from the distinct line IDs on incident edges; lines containing only
one station have no edges, so their station membership is not stored.

Load the result with NetworkX:

```python
import json
import networkx as nx

with open("data/graphs/jre_shinkansen.json", encoding="utf-8") as file:
    data = json.load(file)
graph = nx.node_link_graph(data, edges="edges")
lines = data["lines"]
```

For older NetworkX versions that use the `link` parameter, use
`nx.node_link_graph(data, link="edges")` instead.

Sample output (a subset of `jre_shinkansen.json` showing two stations and one edge):

```json
{
  "directed": false,
  "multigraph": false,
  "nodes": [
    {
      "id": "THK01",
      "name": "東京",
      "coordinates": [
        139.76694,
        35.68083
      ],
      "schematic": [
        24.0,
        0.0
      ]
    },
    {
      "id": "THK02",
      "name": "上野",
      "coordinates": [
        139.77672,
        35.71343
      ],
      "schematic": [
        24.0,
        1.0
      ]
    }
  ],
  "edges": [
    {
      "source": "THK01",
      "target": "THK02",
      "distance": 3.6,
      "lines": [
        "THK_line"
      ]
    }
  ],
  "lines": [
    {
      "id": "THK_line",
      "name": "東北新幹線",
      "color": "#980ef2"
    }
  ]
}
```

## Generate schematic maps

The layout engine implements the pipeline in `SPEC.md`. It accepts the graph
JSON produced above and writes `layout.json`, `map.svg`, `map.png`, and a static
HTML viewer with an interactive `<transit-map>` component.

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m schematic_map data/graphs/jre_shinkansen.json -o output/shinkansen
python3 -m http.server 8000 --directory output/shinkansen
```

Open `http://localhost:8000`. The HTTP server only serves files; the component
needs no application server. Browsers generally block `fetch` from `file://`.
Pan by dragging, zoom with the wheel, and pinch with two touch pointers. Through
station labels appear on zoom. Stations support keyboard selection, and hovering
a line highlights it. The component dispatches `station-click`, `station-hover`,
`line-click`, `line-hover`, `map-load`, and `map-error` DOM events. Selection events
include the ID and station/line metadata in `event.detail`.

```html
<script type="module" src="transit-map.js"></script>
<transit-map src="layout.json" style="height: 600px"></transit-map>
```

The component displays the SVG embedded by the JSON exporter. This keeps Python,
PNG, and browser rendering on the same implementation. `setLayout(layout)` and
`reset()` are also available. The exporter renders from JSON only, including
render settings, offsets and labels. A bundled, SIL OFL licensed Noto Sans CJK
Japanese font is converted to glyph outlines so CJK works in Cairo and browsers
without installed fonts, external font requests, or font fallback differences.

### Configuration and API

All configurable defaults are in `schematic_map/config/default.yaml`; `--config`
accepts a YAML file with partial overrides. Useful examples:

```yaml
seed: 42
init: {mode: geo}  # hint requires schematic coordinates on every input station
anneal: {restarts: 8, workers: 4, max_sweeps: 8}
render: {pixels_per_unit: 45, dpi: 144, padding: 1.0}
```

Distances are nonnegative track kilometres; missing distances use haversine.
Geographic coordinates are preserved, and duplicate locations get distinct
projected positions. The default projection is local equirectangular kilometres;
wide networks can substitute another projection behind `geo/projection.py`.
A shared rotation/aspect search provides the output's global transform. Stress
initialization, annealing and refinement run independently per component, then
components are packed with at least three units of separation. Nodes and paths
use y-up coordinates; renderers flip y. Angles in energy terms are measured in
degrees, with squared deviations outside the allowed tolerance.

The default search budget is deliberately bounded for interactive use. Increase
`max_sweeps`, `restarts`, `patience`, and `refine.sweeps` when tuning difficult
networks. Restarts use `seed + restart_index`; process results are collected in
restart order for reproducible ties. Routing caches translation-invariant
candidates, prunes with a nonnegative score bound, uses a uniform spatial grid
for obstacle checks, and reroutes incident edges for proposed moves. Energy
updates reuse unchanged edge lengths, clearance reports and crossing pairs;
custom terms may fall back to a full evaluation.

```python
from schematic_map import generate_layout, load_config
from schematic_map.io.load import load_graph
from schematic_map.io.export import export_layout

layout = generate_layout(load_graph("data/graphs/jre_shinkansen.json"), load_config())
export_layout(layout, "layout.json")
```

The same input, seed and config produce identical JSON. `runtime_s` is `null`
by default because elapsed time cannot be deterministic; `--runtime` or
`record_runtime=True` records it. Render an existing layout with:

```sh
schematic-map output/shinkansen/layout.json --render-only -o output/rerendered
```

`--no-png` skips PNG export. Generated files are ignored by Git.

### Constraint reports and extension points

Every output contains H1–H7 counts and detailed violation records, crossings,
bends, angle deviations, chain length variation, minimum spacing, geographic
fidelity, label overlap counts, and per-term energy values. `meta.feasible`
means all hard constraints passed. The CLI writes the diagnostic result and exits
with status 2 if hard constraints remain; `--allow-infeasible` overrides this
exit status. Crossings and labels are soft objectives, reported separately.

This is a heuristic search: it can report failures on difficult or impossible
inputs rather than guaranteeing a planar solution for every planar graph.
Automatic acceptance targets such as geographic deviation below 25 degrees and
collinearity below 5 degrees are tuning goals, not universal guarantees.
Bundles use local exhaustive ordering up to six lines; global metro-line crossing
minimization and optional cosmetic split transitions remain extensions. Joint
annealing of the transform is an optional spec feature and is currently rejected
if enabled; the Stage 1 search is implemented. Corner rounding is cosmetic.

Built-in terms are registered in `layout/energy/`. To add a term, subclass `Term`,
provide `name`, `kind`, `full(layout)`, and optionally `delta(layout, proposed)`.
Use its fully qualified class name as a key under YAML `terms`, with `enabled`,
`weight`, and parameters. Unknown terms fail clearly; disable any existing term
with `enabled: false`. Hard verification always runs, even when optimization
terms are disabled.

### Verification

```sh
.venv/bin/pip install pytest
.venv/bin/pytest -q
node --check schematic_map/web/transit-map.js
```

Tests cover all nine specification fixtures, input validation, each energy term,
route geometry, incremental/full equivalence, deterministic serial/parallel
restarts, schema and endpoint integrity, geographic transform properties, CJK
PNG output, and a perceptual PNG regression. CI runs on Python 3.11. Optional
browser integration checks live in `tests/test_browser.py` and use Playwright:

```sh
.venv/bin/pip install playwright
.venv/bin/playwright install chromium
.venv/bin/pytest tests/test_browser.py -q
```

The included 68-station Shinkansen graph was also run with the default search
budget: zero H1–H7 violations, crossings and label overlaps; minimum spacing
1.03 units; chain length CV 0.185; mean geographic direction deviation 19.4°;
mean collinearity deviation approximately zero. The run took about 46 seconds
on the development machine. Its mean bend count was 1.07 per edge, above the
specification's typical 0.5 target: the current weights strongly favor tangent
collinearity and geographic fidelity, sometimes introducing extra doglegs.


### JRE and JRW large-network smoke tests

These two raw datasets require the explicit shared-distance rounding tolerance:

```sh
python3 generate_graphs.py --distance-tolerance-km 0.05
.venv/bin/python -m schematic_map data/graphs/jre.json --config tests/config/large_network.yaml -o output/jre --runtime
.venv/bin/python -m schematic_map data/graphs/jrw.json --config tests/config/large_network.yaml -o output/jrw --runtime
```

The checked-in smoke-test config uses geographic initialization with five stress
iterations, one restart, 25 annealing proposals, and 16 local refinement trials
per component. It also reduces candidate samples and raster scale. These are
bounded end-to-end tests, not runs of the default quality-search configuration.
`anneal.max_moves` bounds search proposals (calibration is separately configured);
`refine.max_trials` bounds node-move refinement attempts. Both default to `null`.
Spatial indexes accelerate overlap resolution and label placement; crossing
checks run in configurable blocks to avoid quadratic peak memory.

| Dataset | Stations | Edges | Layout runtime | Hard violations | Crossings | Label overlaps |
|---|---:|---:|---:|---:|---:|---:|
| JRE | 1,646 | 1,703 | 39.7 s | 11 | 28 | 84 |
| JRW | 1,143 | 1,167 | 21.3 s | 4 | 8 | 17 |

Both results pass schema, endpoint integrity, PNG decoding, and browser rendering
checks. Browser zoom and keyboard station selection work with the full datasets.
They **fail map-quality acceptance**: the remaining hard failures are H5 node
clearance, H6 port separation, and H7 circular order. Both CLIs correctly exit 2
while preserving JSON, SVG, PNG, and viewer files for diagnosis. Full violation
records are in each `layout.json`. The test report is saved to
`output/large-network-test-report.json`.

## Layout algorithm and constraints

The default engine smooths geographic chains, aligns the primary line, routes a
key-station skeleton, then spaces through stations along its routes and refines
the full graph. See [ALGORITHM.md](ALGORITHM.md) for a brief explanation and
[CONSTRAINTS.md](CONSTRAINTS.md) for every constraint and the final cost function.
Staged fixture results and remaining quality failures are recorded in
[reports/smoothing-progress.md](reports/smoothing-progress.md).
