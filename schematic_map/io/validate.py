"""Fail-fast input checks without altering user data."""
import math
import re
import warnings


def validate_graph(data):
    if not isinstance(data,dict):
        raise ValueError('Input graph must be an object')
    if data.get('directed', False) is not False or data.get('multigraph', False) is not False:
        raise ValueError('Input must be an undirected, non-multigraph')
    for key in ('nodes', 'edges', 'lines'):
        if not isinstance(data.get(key), list):
            raise ValueError(f'{key} must be an array')
    nodes, lines, pairs, coordinates = {}, set(), set(), {}
    for line in data['lines']:
        if not isinstance(line,dict): raise ValueError('Each line must be an object')
        ident = line.get('id')
        if not isinstance(ident, str) or not ident or ident in lines:
            raise ValueError(f'Invalid or duplicate line ID: {ident!r}')
        if not isinstance(line.get('name'), str) or (not isinstance(line.get('color'),str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', line['color'])):
            raise ValueError(f'Line {ident}: name and #RRGGBB color are required')
        if 'primary' in line and not isinstance(line['primary'],bool):
            raise ValueError(f'Line {ident}: primary must be boolean')
        lines.add(ident)
    for node in data['nodes']:
        if not isinstance(node,dict): raise ValueError('Each node must be an object')
        ident = node.get('id')
        if not isinstance(ident, str) or not ident or ident in nodes:
            raise ValueError(f'Invalid or duplicate node ID: {ident!r}')
        if not isinstance(node.get('name'), str):
            raise ValueError(f'Node {ident}: name must be a string')
        point = node.get('coordinates')
        if not valid_point(point) or not (-180 <= point[0] <= 180 and -90 <= point[1] <= 90):
            raise ValueError(f'Node {ident}: invalid longitude/latitude coordinates')
        if 'schematic' in node and not valid_point(node['schematic']):
            raise ValueError(f'Node {ident}: invalid schematic hint')
        pair = tuple(point)
        if pair in coordinates:
            warnings.warn(f'Nodes {coordinates[pair]} and {ident} have identical coordinates; nudging projection', stacklevel=2)
        coordinates[pair] = ident
        nodes[ident] = 0
    for edge in data['edges']:
        if not isinstance(edge,dict): raise ValueError('Each edge must be an object')
        u, v = edge.get('source'), edge.get('target')
        if not isinstance(u,str) or not isinstance(v,str) or u not in nodes or v not in nodes:
            raise ValueError(f'Edge {u}--{v}: unknown endpoint')
        if u == v:
            raise ValueError(f'Edge {u}: self loop')
        pair = tuple(sorted((u, v)))
        if pair in pairs:
            raise ValueError(f'Duplicate undirected edge {u}--{v}')
        pairs.add(pair)
        ids = edge.get('lines')
        if not isinstance(ids, list) or not ids or any(not isinstance(x, str) or x not in lines for x in ids) or len(ids) != len(set(ids)):
            raise ValueError(f'Edge {u}--{v}: lines must be nonempty, unique, known IDs')
        distance = edge.get('distance')
        if distance is not None and (not isinstance(distance, (float, int)) or isinstance(distance,bool) or not math.isfinite(distance) or distance < 0):
            raise ValueError(f'Edge {u}--{v}: distance must be finite and nonnegative km')
        nodes[u] += 1
        nodes[v] += 1
    for ident, degree in nodes.items():
        if degree > 8:
            raise ValueError(f'Node {ident} has degree {degree} > 8 ports; merge stations or split the junction')
    return data


def valid_point(point):
    return isinstance(point, (list, tuple)) and len(point) == 2 and all(isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x) for x in point)
