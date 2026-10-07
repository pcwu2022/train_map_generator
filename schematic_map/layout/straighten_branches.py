import numpy as np
from .geometry import DIRECTIONS

def apply_straightening(graph, positions, routes, config):
    """
    Phase 4: Straighten branches (blind gut lines).
    Finds terminal branches, flattens them to a single octolinear axis,
    locks them, and works upwards layer by layer.
    """
    positions = positions.copy()
    routes = [r.copy() if r is not None else None for r in routes]
    active_edges = set(range(len(graph.edges)))
    subtrees = {i: {i} for i in range(len(graph.nodes))}
    
    d_min = config['grid']['d_min']
    
    while True:
        degrees = [0] * len(graph.nodes)
        for u in range(len(graph.nodes)):
            for v, e in graph.adjacency[u]:
                if e in active_edges:
                    degrees[u] += 1
                    
        leaves = [u for u, d in enumerate(degrees) if d == 1]
        
        chains = []
        for leaf in leaves:
            active_leaf_edges = [e for v, e in graph.adjacency[leaf] if e in active_edges]
            if len(active_leaf_edges) != 1:
                continue
                
            chain_nodes = [leaf]
            chain_edges = []
            curr = leaf
            
            while True:
                nxt, nxt_e = None, None
                for v, e in graph.adjacency[curr]:
                    if e in active_edges and e not in chain_edges:
                        nxt, nxt_e = v, e
                        break
                
                if nxt is None:
                    break
                    
                chain_nodes.append(nxt)
                chain_edges.append(nxt_e)
                
                if degrees[nxt] > 2 or degrees[nxt] == 1:
                    break
                    
                curr = nxt
                
            chains.append((chain_nodes, chain_edges))
            for e in chain_edges:
                active_edges.discard(e)
                
        if not chains:
            break
            
        for chain_nodes, chain_edges in chains:
            root = chain_nodes[-1]
            vec = positions[chain_nodes[0]] - positions[root]
            norm = np.linalg.norm(vec)
            
            if norm < 1e-5:
                best_dirs = DIRECTIONS
            else:
                vec = vec / norm
                dots = [np.dot(vec, d) for d in DIRECTIONS]
                best_dirs = [DIRECTIONS[i] for i in np.argsort(dots)[::-1]]
                
            placed = False
            for d in best_dirs:
                new_p = positions.copy()
                new_r = [r.copy() if r is not None else None for r in routes]
                curr_p = positions[root].copy()
                
                overlap = False
                moved_nodes = set()
                
                for i in range(len(chain_nodes)-2, -1, -1):
                    node = chain_nodes[i]
                    parent = chain_nodes[i+1]
                    dist = np.linalg.norm(positions[node] - positions[parent])
                    if dist < 1e-5: dist = d_min
                    
                    curr_p = curr_p + dist * d
                    delta = curr_p - positions[node]
                    
                    for sub_node in subtrees[node]:
                        new_p[sub_node] += delta
                        moved_nodes.add(sub_node)
                        
                        for v, e in graph.adjacency[sub_node]:
                            if v in subtrees[node] and v > sub_node:
                                if new_r[e] is not None:
                                    new_r[e] += delta
                                    
                unmoved_nodes = set(range(len(graph.nodes))) - moved_nodes
                
                if unmoved_nodes and moved_nodes:
                    m_pts = new_p[list(moved_nodes)]
                    u_pts = new_p[list(unmoved_nodes)]
                    # Simple bounding box / distance check to avoid heavy computation
                    for pt in m_pts:
                        dists = np.linalg.norm(u_pts - pt, axis=1)
                        if np.any(dists < d_min * 0.8):
                            overlap = True
                            break
                            
                if not overlap:
                    positions = new_p
                    routes = new_r
                    placed = True
                    break
                    
            if not placed:
                d = best_dirs[0]
                curr_p = positions[root].copy()
                for i in range(len(chain_nodes)-2, -1, -1):
                    node = chain_nodes[i]
                    parent = chain_nodes[i+1]
                    dist = np.linalg.norm(positions[node] - positions[parent])
                    if dist < 1e-5: dist = d_min
                    curr_p = curr_p + dist * d
                    delta = curr_p - positions[node]
                    
                    for sub_node in subtrees[node]:
                        positions[sub_node] += delta
                        for v, e in graph.adjacency[sub_node]:
                            if v in subtrees[node] and v > sub_node:
                                if routes[e] is not None:
                                    routes[e] += delta
                                    
            for i in range(len(chain_nodes)-1):
                subtrees[root].update(subtrees[chain_nodes[i]])
                
            for e in chain_edges:
                u, v = graph.endpoints[e]
                routes[e] = np.array([positions[u], positions[v]])
                
    return positions, routes
