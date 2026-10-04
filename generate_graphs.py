#!/usr/bin/env python3
"""Combine matching geography/topology JSON files into node-link graphs."""

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path


def build_graph(geo, topology):
    """Return an undirected NetworkX node-link graph with an `edges` key.

    Shared edges use the first line's color and list all their line IDs.
    Coordinates retain the input order: [longitude, latitude].
    """
    segments = topology["segments"]
    used_colors = {
        segment["color"].lower()
        for segment in segments
        if "color" in segment
    }
    lines = {}
    nodes = {}
    memberships = {}
    edges = {}

    for segment in segments:
        line_id = segment["id"]
        if line_id in lines:
            raise ValueError(f"Duplicate line ID: {line_id}")
        if "color" in segment:
            color = segment["color"]
        else:
            # Stable colors across runs; avoid supplied and generated colors.
            candidate = int(hashlib.sha256(line_id.encode()).hexdigest()[:6], 16)
            while f"#{candidate:06x}" in used_colors:
                candidate = (candidate + 1) % (1 << 24)
            color = f"#{candidate:06x}"
            used_colors.add(color)
        lines[line_id] = {"id": line_id, "name": segment["name"], "color": color}

        stations = segment["stations"]
        for station in stations:
            station_id = station["id"]
            if station_id not in nodes:
                nodes[station_id] = {
                    "id": station_id,
                    "name": station["name"],
                    "num_lines": 0,
                    "coordinates": geo["stations"][station_id],
                }
                if station_id in geo.get("schematic", {}):
                    nodes[station_id]["schematic"] = geo["schematic"][station_id]
                memberships[station_id] = set()
            memberships[station_id].add(line_id)

        for first, second in zip(stations, stations[1:]):
            source, target = first["id"], second["id"]
            key = tuple(sorted((source, target)))
            # Decimal avoids artifacts such as 27.700000000000003.
            distance = float(Decimal(str(second["km"])) - Decimal(str(first["km"])))
            if key not in edges:
                edges[key] = {
                    "source": source,
                    "target": target,
                    "color": color,
                    "distance": distance,
                    "lines": [],
                }
            elif abs(edges[key]["distance"]) != abs(distance):
                raise ValueError(f"Conflicting distances for edge {source}--{target}")
            if line_id not in edges[key]["lines"]:
                edges[key]["lines"].append(line_id)

    for station_id, node in nodes.items():
        node["num_lines"] = len(memberships[station_id])

    line_list = list(lines.values())
    return {
        "directed": False,
        "multigraph": False,
        # NetworkX preserves graph metadata here when importing node-link data.
        "graph": {"lines": line_list},
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "lines": line_list,
    }


def main():
    data_dir = Path(__file__).resolve().parent / "data"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geo-dir", type=Path, default=data_dir / "geo_raw")
    parser.add_argument("--topology-dir", type=Path, default=data_dir / "topology_raw")
    parser.add_argument("--output-dir", type=Path, default=data_dir / "graphs")
    args = parser.parse_args()
    for directory in (args.geo_dir, args.topology_dir):
        if not directory.is_dir():
            parser.error(f"Input directory does not exist: {directory}")

    geo_files = {path.name: path for path in args.geo_dir.glob("*.json")}
    topology_files = {path.name: path for path in args.topology_dir.glob("*.json")}
    for name in sorted(geo_files.keys() ^ topology_files.keys()):
        print(f"Skipping {name}: missing matching input file")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name in sorted(geo_files.keys() & topology_files.keys()):
        geo = json.loads(geo_files[name].read_text(encoding="utf-8"))
        topology = json.loads(topology_files[name].read_text(encoding="utf-8"))
        graph = build_graph(geo, topology)
        output = args.output_dir / name
        output.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {output}: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")


if __name__ == "__main__":
    main()
