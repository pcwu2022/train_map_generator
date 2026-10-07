import numpy as np
from .energy.base import Layout
from .geometry import EPS, path_length
from .reference import sample_polyline
from .skeleton import slice_polyline
from .octolinear import generate_octolinear_candidates

def check_station_overlap(positions, cand, clearance, nodes_set):
    cand_min = np.min(cand, axis=0) - clearance
    cand_max = np.max(cand, axis=0) + clearance
    
    mask = (positions[:, 0] >= cand_min[0]) & (positions[:, 0] <= cand_max[0]) & \
           (positions[:, 1] >= cand_min[1]) & (positions[:, 1] <= cand_max[1])
           
    for n in nodes_set:
        mask[n] = False
        
    pts = positions[mask]
    if len(pts) == 0:
        return False
        
    for i in range(len(cand) - 1):
        a = cand[i]
        b = cand[i+1]
        v = b - a
        if np.linalg.norm(v) < EPS: continue
        w = pts - a
        c1 = np.sum(w * v, axis=1)
        c2 = np.dot(v, v)
        
        d = np.zeros(len(pts))
        m1 = c1 <= 0
        if np.any(m1): d[m1] = np.linalg.norm(pts[m1] - a, axis=1)
        
        m2 = (c1 > 0) & (c2 <= c1)
        if np.any(m2): d[m2] = np.linalg.norm(pts[m2] - b, axis=1)
        
        m3 = ~(m1 | m2)
        if np.any(m3):
            proj = a + (c1[m3] / c2)[:, None] * v
            d[m3] = np.linalg.norm(pts[m3] - proj, axis=1)
            
        if np.min(d) < clearance:
            return True
            
    return False
    
def get_turn_penalties(path):
    penalty = 0
    turns = []
    for i in range(len(path) - 2):
        v1 = path[i+1] - path[i]
        v2 = path[i+2] - path[i+1]
        len1 = np.linalg.norm(v1)
        len2 = np.linalg.norm(v2)
        if len1 < EPS or len2 < EPS: continue
        v1 = v1 / len1
        v2 = v2 / len2
        
        # Turn sequence for C-shapes
        cp = v1[0]*v2[1] - v1[1]*v2[0]
        if abs(cp) > 1e-2:
            turns.append(np.sign(cp))
            
        # Angle penalty
        dot = np.dot(v1, v2)
        if dot < -1e-2:
            penalty += 100000  # Forbidden acute angle (< 90 deg)
        else:
            penalty += (1.0 - dot)  # Prefer straight (dot=1) over 45 (0.7) over 90 (0)
            
    c_shapes = 0
    for i in range(len(turns) - 1):
        if turns[i] * turns[i+1] > 0:
            c_shapes += 1
            
    return penalty + c_shapes * 1000

def generate_shifted_candidates(p1, p2, nodes, initial_positions, max_shift=20, d_min=1.0):
    """
    Generate base octolinear candidates, plus laterally shifted versions 
    to avoid overlaps.
    """
    base_candidates = generate_octolinear_candidates(p1, p2)
    all_candidates = []
    
    # 0 shift
    for c in base_candidates:
        all_candidates.append(c)
        
    # generate shifted candidates (up to max_shift)
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    
    # Determine the primary perpendicular direction
    if abs(dx) > abs(dy):
        perp = np.array([0.0, 1.0])
    else:
        perp = np.array([1.0, 0.0])
        
    preferred_sign = 1
    if len(nodes) > 2:
        avg_pos = np.mean(initial_positions[nodes[1:-1]], axis=0)
        if np.dot(avg_pos - p1, perp) < 0:
            preferred_sign = -1
            
    shifts = []
    for shift in range(1, max_shift + 1):
        shifts.append(preferred_sign * shift * 0.3)
    for shift in range(1, max_shift + 1):
        shifts.append(-preferred_sign * shift * 0.3)
        
    for shift_val in shifts:
        offset = perp * shift_val * d_min
        p1_shifted = p1 + offset
        p2_shifted = p2 + offset
        shifted_bases = generate_octolinear_candidates(p1_shifted, p2_shifted)
        for c in shifted_bases:
            shifted_path = np.vstack(([p1], c, [p2]))
            cleaned = [shifted_path[0]]
            for i in range(1, len(shifted_path)-1):
                a = shifted_path[i] - cleaned[-1]
                b = shifted_path[i+1] - shifted_path[i]
                if np.linalg.norm(a) < EPS: continue
                if abs(a[0]*b[1] - a[1]*b[0]) < EPS and a @ b > 0: continue
                cleaned.append(shifted_path[i])
            cleaned.append(shifted_path[-1])
            all_candidates.append(np.asarray(cleaned))
                
    return all_candidates

def segments_overlap(path1, path2, clearance):
    """Check if any segment in path1 is parallel and too close to any segment in path2."""
    for i in range(len(path1) - 1):
        A = path1[i]
        B = path1[i+1]
        v1 = B - A
        len1 = np.linalg.norm(v1)
        if len1 < EPS: continue
        v1_dir = v1 / len1
        n = np.array([-v1_dir[1], v1_dir[0]])
        
        for j in range(len(path2) - 1):
            C = path2[j]
            D = path2[j+1]
            
            # Simple bounding box check first
            if (min(A[0], B[0]) > max(C[0], D[0]) + clearance or
                max(A[0], B[0]) < min(C[0], D[0]) - clearance or
                min(A[1], B[1]) > max(C[1], D[1]) + clearance or
                max(A[1], B[1]) < min(C[1], D[1]) - clearance):
                continue
                
            v2 = D - C
            len2 = np.linalg.norm(v2)
            if len2 < EPS: continue
            v2_dir = v2 / len2
            
            # Check if they are parallel (or anti-parallel)
            if abs(np.abs(np.dot(v1_dir, v2_dir)) - 1.0) > 1e-2:
                continue # They cross at an angle, allow it!
                
            # BYPASS: Allow short terminal connecting segments (fanning out of stations) to overlap
            is_term1 = (i == 0 or i == len(path1) - 2)
            is_term2 = (j == 0 or j == len(path2) - 2)
            if is_term1 and is_term2 and (len(path1) > 2 or len(path2) > 2):
                # Check if they share a common endpoint
                p1_eps = [path1[0], path1[-1]]
                p2_eps = [path2[0], path2[-1]]
                shared_ep = False
                for p1_e in p1_eps:
                    for p2_e in p2_eps:
                        if np.linalg.norm(p1_e - p2_e) < EPS:
                            shared_ep = True
                            break
                            
                if shared_ep:
                    # ONLY bypass if BOTH segments are connecting segments.
                    # A connecting segment is roughly perpendicular to the chain's overall displacement.
                    main_vec1 = path1[-1] - path1[0]
                    main_vec2 = path2[-1] - path2[0]
                    
                    if np.linalg.norm(main_vec1) > EPS and np.linalg.norm(main_vec2) > EPS:
                        dot1 = np.dot(v1_dir, main_vec1 / np.linalg.norm(main_vec1))
                        dot2 = np.dot(v2_dir, main_vec2 / np.linalg.norm(main_vec2))
                        
                        # If abs(dot) < 0.85, it is perpendicular or 45-deg to the main direction
                        if abs(dot1) < 0.85 and abs(dot2) < 0.85:
                            continue # Ignore overlap for terminal connecting segments
                
            # They are parallel. Check lateral distance.
            dist = abs(np.dot(C - A, n))
            if dist > clearance:
                continue # Parallel but far enough apart
                
            # Check longitudinal overlap
            pA = 0
            pB = len1
            pC = np.dot(C - A, v1_dir)
            pD = np.dot(D - A, v1_dir)
            
            min_C_D = min(pC, pD)
            max_C_D = max(pC, pD)
            
            overlap_start = max(min(pA, pB), min_C_D)
            overlap_end = min(max(pA, pB), max_C_D)
            
            # Require a significant longitudinal overlap to trigger (e.g. at least 10% of clearance)
            # This ignores endpoints that just barely touch.
            if overlap_end - overlap_start > clearance * 0.1:
                return True
                
    return False

def optimize_micro(graph, initial_positions, routes, anchor, targets, config, callback=None):
    """
    Phase 3: Priority-based Yielding and Shifting.
    """
    positions = initial_positions.copy()
    
    if callback:
        callback(positions, routes, "Phase 3: Prioritizing chains...", 0.1)
        
    # 1. Identify chains
    chains = [(nodes, edges) for nodes, edges in graph.chains if nodes[0] != nodes[-1]]
    
    # 2. Score chains
    from .primary import primary_line
    primary = primary_line(graph)
    primary_id = primary['id'] if primary else None

    # Calculate line-level scores
    line_scores = {}
    for line in graph.lines:
        line_id = line['id']
        line_nodes = [n for n in graph.nodes if line_id in n['lines']]
        line_length = len(line_nodes)
        line_interchanges = sum(1 for n in line_nodes if n['is_interchange'])
        line_scores[line_id] = line_length * 10 + line_interchanges * 50

    chain_scores = []
    for idx, (nodes, chain_edges) in enumerate(chains):
        lines_on_chain = graph.edges[chain_edges[0]]['lines']
        
        # Score is based on the most important line that runs on this chain
        score = max((line_scores.get(l, 0) for l in lines_on_chain), default=0)
        
        if primary_id in lines_on_chain:
            score += 1000000  # Absolute priority for primary line
            
        # Add chain length as a tie-breaker
        score += len(nodes)
        
        chain_scores.append((score, idx, nodes, chain_edges))
        
    # Sort descending by score
    chain_scores.sort(key=lambda x: x[0], reverse=True)
    
    if callback:
        callback(positions, routes, "Phase 3: Resolving overlaps...", 0.4)
        
    # Calculate standard station distance
    edge_lengths = []
    for u, v in graph.endpoints:
        edge_lengths.append(np.linalg.norm(positions[u] - positions[v]))
    std_dist = np.mean(edge_lengths) if edge_lengths else config['grid']['d_min'] * 5.0
    
    clearance = std_dist * 0.4
    
    occupied_paths = []
    final_paths = {}
    
    # Primary line nodes shouldn't be shifted if they were straightened in Phase 2
    # But this logic naturally handles it if the primary line is processed first (it has the highest score)
    
    # 3. Place chains and resolve overlaps
    total_chains = len(chain_scores)
    for i, (score, idx, nodes, chain_edges) in enumerate(chain_scores):
        if callback and i % 5 == 0:
            lines_on_chain = graph.edges[chain_edges[0]]['lines']
            line_names = [l for l in lines_on_chain]
            callback(positions, routes, f"Phase 3: Resolving overlaps for line(s) {','.join(line_names)}...", 0.4 + 0.4 * (i / max(1, total_chains)))
            
        u, v = nodes[0], nodes[-1]
        p1, p2 = positions[u], positions[v]
        
        # Shift by standard station distance
        candidates = generate_shifted_candidates(p1, p2, nodes, initial_positions, max_shift=20, d_min=std_dist)
        
        valid_candidates = []
        for cand_idx, cand in enumerate(candidates):
            overlap = False
            for occ in occupied_paths:
                if segments_overlap(cand, occ, clearance):
                    overlap = True
                    break
            if not overlap:
                valid_candidates.append((cand_idx, cand))
                
        if not valid_candidates:
            # Fallback
            lines_on_chain = graph.edges[chain_edges[0]]['lines']
            print(f"DEBUG: All candidates overlapped for lines {lines_on_chain}! Falling back to shift 0.")
            valid_candidates = [(0, candidates[0])]
            
        best_cand = None
        best_cost = float('inf')
        
        for cand_idx, cand in valid_candidates:
            cost = cand_idx  # Base penalty for shifting further away
            
            # Check C-shapes along lines running on this chain
            lines = graph.edges[chain_edges[0]]['lines']
            for line_id in lines:
                # Concatenate paths for this line
                # Look at node u
                path_before = []
                for placed_c_idx in final_paths:
                    placed_nodes = chains[placed_c_idx][0]
                    placed_lines = graph.edges[chains[placed_c_idx][1][0]]['lines']
                    if line_id in placed_lines:
                        if placed_nodes[-1] == u:
                            path_before = final_paths[placed_c_idx][:-1]
                        elif placed_nodes[0] == u:
                            path_before = final_paths[placed_c_idx][::-1][:-1]
                            
                path_after = []
                for placed_c_idx in final_paths:
                    placed_nodes = chains[placed_c_idx][0]
                    placed_lines = graph.edges[chains[placed_c_idx][1][0]]['lines']
                    if line_id in placed_lines:
                        if placed_nodes[0] == v:
                            path_after = final_paths[placed_c_idx][1:]
                        elif placed_nodes[-1] == v:
                            path_after = final_paths[placed_c_idx][::-1][1:]
                            
                full_path = cand
                if len(path_before) > 0:
                    if np.linalg.norm(path_before[-1] - full_path[0]) > EPS:
                        full_path = np.vstack((path_before, full_path))
                if len(path_after) > 0:
                    if np.linalg.norm(full_path[-1] - path_after[0]) > EPS:
                        full_path = np.vstack((full_path, path_after))
                        
                cost += get_turn_penalties(full_path)
                
            # Add penalty for passing too close to unrelated stations
            nodes_set = set(nodes)
            if check_station_overlap(positions, cand, clearance, nodes_set):
                cost += 50000  # huge penalty for slicing through unrelated stations
                
            if cost < best_cost:
                best_cost = cost
                best_cand = cand
                
        final_paths[idx] = best_cand
        occupied_paths.append(best_cand)
        
    # 4. Interpolate stations and update routes
    if callback:
        callback(positions, routes, "Phase 3: Finalizing positions...", 0.8)
        
    for _, idx, nodes, chain_edges in chain_scores:
        path = final_paths[idx]
        length = path_length(path)
        if length < EPS:
            distances = np.zeros(len(nodes))
        else:
            distances = np.linspace(0, length, len(nodes))
            
        stations = sample_polyline(path, distances)
        
        stations[0] = positions[nodes[0]]
        stations[-1] = positions[nodes[-1]]
        positions[nodes[1:-1]] = stations[1:-1]
        
        for i, edge in enumerate(chain_edges):
            route = slice_polyline(path, distances[i], distances[i+1])
            route[0] = stations[i]
            route[-1] = stations[i+1]
            routes[edge] = route if graph.endpoints[edge, 0] == nodes[i] else route[::-1].copy()
            
    if callback:
        callback(positions, routes, "Phase 3 Complete", 1.0)
        
    return Layout(graph, positions, routes, anchor, targets, config)
