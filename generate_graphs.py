#!/usr/bin/env python3
"""Combine matching geography/topology JSON files into node-link graphs."""

import argparse
import hashlib
import json
import math
import warnings
from decimal import Decimal
from pathlib import Path


def build_graph(geo, topology, *, distance_tolerance_km=0.0):
    """Return an undirected NetworkX node-link graph with an `edges` key.

    Shared edges list all their line IDs; colors are stored only on lines.
    Coordinates retain the input order: [longitude, latitude].
    """
    if not math.isfinite(distance_tolerance_km) or distance_tolerance_km < 0:
        raise ValueError("Distance tolerance must be finite and nonnegative")
    segments = topology["segments"]
    used_colors = {
        segment["color"].lower()
        for segment in segments
        if "color" in segment
    }
    lines = {}
    nodes = {}
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
                    "coordinates": geo["stations"][station_id],
                }
                if station_id in geo.get("schematic", {}):
                    nodes[station_id]["schematic"] = geo["schematic"][station_id]

        for first, second in zip(stations, stations[1:]):
            source, target = first["id"], second["id"]
            key = tuple(sorted((source, target)))
            # Decimal avoids artifacts such as 27.700000000000003.
            distance = float(abs(Decimal(str(second["km"])) - Decimal(str(first["km"]))))
            if key not in edges:
                edges[key] = {
                    "source": source,
                    "target": target,
                    "distance": distance,
                    "lines": [],
                }
            elif edges[key]["distance"] != distance:
                discrepancy = abs(Decimal(str(edges[key]["distance"])) - Decimal(str(distance)))
                if discrepancy > Decimal(str(distance_tolerance_km)):
                    raise ValueError(f"Conflicting distances for edge {source}--{target}: "
                                     f"{edges[key]['distance']} vs {distance} km")
                warnings.warn(f"Shared edge {source}--{target}: retaining "
                              f"{edges[key]['distance']} km instead of {distance} km "
                              f"(within {distance_tolerance_km} km tolerance)", stacklevel=2)
            if line_id not in edges[key]["lines"]:
                edges[key]["lines"].append(line_id)

    line_list = list(lines.values())
    return {
        "directed": False,
        "multigraph": False,
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
    parser.add_argument("--distance-tolerance-km", type=float, default=0.0,
                        help="Allow shared-edge rounding differences; keep first distance (default: strict)")
    args = parser.parse_args()
    if not math.isfinite(args.distance_tolerance_km) or args.distance_tolerance_km < 0:
        parser.error("--distance-tolerance-km must be finite and nonnegative")
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
        graph = build_graph(geo, topology, distance_tolerance_km=args.distance_tolerance_km)
        output = args.output_dir / name
        output.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {output}: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")


if __name__ == "__main__":
    main()
