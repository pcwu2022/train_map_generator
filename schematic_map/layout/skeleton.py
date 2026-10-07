"""Route key-node chains, then expand through stations by equal arc length."""
from copy import deepcopy
import numpy as np
from ..graph.build import build_graph
from .reference import key_nodes,sample_polyline
from .geometry import EPS,bearing,path_length
from .energy.base import Layout


def slice_polyline(path,start,end):
    arc=np.concatenate(([0.],np.cumsum(np.linalg.norm(np.diff(path,axis=0),axis=1))))
    endpoints=sample_polyline(path,[start,end])
    middle=path[(arc>start+EPS)&(arc<end-EPS)]
    result=np.concatenate((endpoints[:1],middle,endpoints[1:]))
    # Remove redundant collinear vertices without changing geometry.
    cleaned=[result[0]]
    for i in range(1,len(result)-1):
        a=result[i]-cleaned[-1];b=result[i+1]-result[i]
        if np.linalg.norm(a)<EPS:continue
        if abs(a[0]*b[1]-a[1]*b[0])<EPS and a @ b>0:continue
        cleaned.append(result[i])
    cleaned.append(result[-1]);return np.asarray(cleaned)


def skeleton_layout(graph,initial,anchor,targets,config,callback=None):
    from .reference import key_nodes, sample_polyline
    from .octolinear import generate_octolinear_candidates, generate_ring_template
    from .energy.base import Layout
    
    keys = key_nodes(graph)
    chains = [(nodes, edges) for nodes, edges in graph.chains if nodes[0] != nodes[-1]]
    keys = sorted(set(keys) | {node for nodes, _ in chains for node in (nodes[0], nodes[-1])})
    
    positions = initial.copy()
    routes = [None] * len(graph.edges)
    
    # Phase 2: Macro-Layout (Routing the skeleton geometrically)
    paths = []
    
    if callback:
        callback(positions, routes, "Generating Macro-Layout...", 0.3)
        
    # --- [Make Primary Line Straight] ---
    from .primary import primary_line
    primary = primary_line(graph)
    if primary:
        primary_id = primary['id']
        # Find all nodes belonging to the primary line
        primary_nodes = set()
        for i, edge in enumerate(graph.edges):
            if primary_id in edge['lines']:
                primary_nodes.update(graph.endpoints[i])
                
        if primary_nodes:
            primary_nodes_list = list(primary_nodes)
            p_coords = positions[primary_nodes_list]
            
            # Determine if it's more horizontal or vertical
            dx = np.max(p_coords[:, 0]) - np.min(p_coords[:, 0])
            dy = np.max(p_coords[:, 1]) - np.min(p_coords[:, 1])
            
            if dx > dy:
                # Mostly horizontal, force all Y coordinates to the median Y
                median_y = np.median(p_coords[:, 1])
                positions[primary_nodes_list, 1] = median_y
            else:
                # Mostly vertical, force all X coordinates to the median X
                median_x = np.median(p_coords[:, 0])
                positions[primary_nodes_list, 0] = median_x
    # ------------------------------------
    
    # Generate octolinear paths for chains between key nodes
    for nodes, chain_edges in chains:
        u, v = nodes[0], nodes[-1]
        p1, p2 = positions[u], positions[v]
        
        candidates = generate_octolinear_candidates(p1, p2)
        
        # For now, pick Candidate 0 (Horizontal/Vertical first).
        # In a full implementation with backtracking, we'd try Candidate 1 if 0 fails in Phase 3.
        path = candidates[0]
        paths.append(path)
        
    # Handle Circular lines (Rings)
    for nodes, chain_edges in graph.chains:
        if nodes[0] != nodes[-1]: continue
        
        # Approximate radius based on perimeter targets
        minimum = config['grid']['d_min']
        factor = config['skeleton']['spacing_factor']
        perimeter = max(sum(targets[chain_edges]), len(chain_edges) * minimum * factor)
        radius = perimeter / (2 * np.pi)
        
        center = positions[nodes[0]]
        path = generate_ring_template(center, radius, len(nodes))
        
        paths.append(path)
        chains.append((nodes, chain_edges))
        
    if callback:
        callback(positions, routes, "Interpolating stations...", 0.6)
        
    # Interpolate through stations along the generated paths
    for (nodes, chain_edges), path in zip(chains, paths):
        length = path_length(path)
        if length < EPS:
            distances = np.zeros(len(nodes))
        else:
            distances = np.linspace(0, length, len(nodes))
            
        stations = sample_polyline(path, distances)
        
        # Skeleton endpoints are shared exactly between incident chains.
        stations[0] = positions[nodes[0]]
        stations[-1] = positions[nodes[-1]]
        positions[nodes[1:-1]] = stations[1:-1]
        
        for i, edge in enumerate(chain_edges):
            route = slice_polyline(path, distances[i], distances[i+1])
            route[0] = stations[i]
            route[-1] = stations[i+1]
            routes[edge] = route if graph.endpoints[edge, 0] == nodes[i] else route[::-1].copy()
            
    if callback:
        callback(positions, routes, "Phase 2 Complete", 1.0)
        
    return Layout(graph, positions, routes, anchor, targets, config)
