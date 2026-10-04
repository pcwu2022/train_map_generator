# train_map_generator
An automation tool that generates railway diagrams

Generate graph JSON files from matching filenames in `data/geo_raw` and
`data/topology_raw` (Python standard library only):

```sh
python3 generate_graphs.py
```

Results are written to `data/graphs`. Override directories with `--geo-dir`,
`--topology-dir`, and `--output-dir`.

Nodes include `id`, `name`, `num_lines`, geographic `coordinates` (longitude,
latitude), and `schematic` coordinates when available. `schematic_bends` is
ignored. Consecutive stations in each segment define edges; `distance` is the
second station's `km` minus the first station's `km`.

Shared undirected edges are merged, with all line IDs in `lines` and the first
line's color. Missing line colors are generated deterministically and uniquely
within each output graph, avoiding supplied colors. Supplied colors are preserved.
Line metadata appears at the top level and in graph metadata so NetworkX retains it.

Load the result with NetworkX:

```python
import json
import networkx as nx

with open("data/graphs/jre_shinkansen.json", encoding="utf-8") as file:
    data = json.load(file)
graph = nx.node_link_graph(data, edges="edges")
lines = graph.graph["lines"]
```

For older NetworkX versions that use the `link` parameter, use
`nx.node_link_graph(data, link="edges")` instead.
