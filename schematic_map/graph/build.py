from copy import deepcopy
from dataclasses import dataclass
import numpy as np
from ..geo.projection import project, haversine


@dataclass
class Graph:
    nodes: list
    edges: list
    lines: list
    endpoints: np.ndarray
    adjacency: list
    components: list
    chains: list
    geo: np.ndarray
    origin: list
    topology_reference: object = None
    topology_orders: object = None
    skeleton: bool = False


def build_graph(data, config):
    nodes, edges = deepcopy(data['nodes']), deepcopy(data['edges'])
    index = {node['id']: i for i, node in enumerate(nodes)}
    endpoints = np.array([(index[e['source']], index[e['target']]) for e in edges], dtype=int).reshape((-1, 2))
    adjacency = [[] for _ in nodes]
    for ei, (u, v) in enumerate(endpoints):
        adjacency[u].append((v, ei)); adjacency[v].append((u, ei))
        edges[ei].setdefault('distance', haversine(nodes[u]['coordinates'], nodes[v]['coordinates']))
    for i, node in enumerate(nodes):
        sets = [set(edges[e]['lines']) for _, e in adjacency[i]]
        node['lines'] = sorted(set().union(*sets))
        node['degree'] = len(sets)
        
        # A station is a through station if it has exactly degree 2 and both edges carry the exact same lines.
        if len(sets) == 2 and sets[0] == sets[1]:
            node['kind'] = 'through'
            node['is_interchange'] = False
        else:
            node['kind'] = 'terminal' if len(sets) == 1 else 'junction'
            # It's considered an interchange if it's a junction (or if it just happens to have multiple lines, 
            # though true interchanges usually have degree > 2 or changing line sets)
            node['is_interchange'] = len(node['lines']) >= 2
            
        node['marker'] = 'interchange' if node['is_interchange'] else 'dot'
    components, seen = [], set()
    for i in range(len(nodes)):
        if i in seen: continue
        stack, component = [i], []
        seen.add(i)
        while stack:
            u = stack.pop(); component.append(u)
            for v, _ in adjacency[u]:
                if v not in seen: seen.add(v); stack.append(v)
        components.append(sorted(component))
    # Edge-disjoint maximal chains, including closed loops with no key node.
    used, chains = set(), []
    keys = [i for i,n in enumerate(nodes) if n['kind'] != 'through' or n['is_interchange']]
    for start in keys + [i for i in range(len(nodes)) if i not in keys]:
        for nxt, edge in adjacency[start]:
            if edge in used: continue
            chain, chain_edges = [start], []
            current, eid = nxt, edge
            while eid not in used:
                used.add(eid); chain_edges.append(eid); chain.append(current)
                if current in keys or current == start: break
                choices = [(v,e) for v,e in adjacency[current] if e not in used]
                if not choices: break
                current, eid = choices[0]
            chains.append((chain, chain_edges))
    geo, origin = project([n['coordinates'] for n in nodes], config['projection'])
    return Graph(nodes, edges, deepcopy(data['lines']), endpoints, adjacency, components, chains, geo, origin)
