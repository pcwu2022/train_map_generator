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
second station's `km` minus the first station's `km`.

Shared undirected edges are merged, with all line IDs in `lines`. Colors are
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
