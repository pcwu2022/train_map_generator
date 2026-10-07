import numpy as np

def generate_octolinear_candidates(p1, p2):
    """
    Generate deterministic octolinear paths between two points p1 and p2.
    Returns a list of candidate paths (each path is a list of 2 or 3 numpy points).
    """
    p1 = np.asarray(p1)
    p2 = np.asarray(p2)
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    
    # Very close points, just return a straight line
    if np.linalg.norm([dx, dy]) < 1e-6:
        return [np.array([p1, p2])]
        
    candidates = []
    
    if abs(abs(dx) - abs(dy)) < 1e-6 or abs(dx) < 1e-6 or abs(dy) < 1e-6:
        # Already octolinear (pure diagonal, pure vertical, or pure horizontal)
        candidates.append(np.array([p1, p2]))
    elif abs(dx) > abs(dy):
        # Needs Horizontal and Diagonal
        h_len = abs(dx) - abs(dy)
        d_len = abs(dy)
        sign_x = np.sign(dx)
        sign_y = np.sign(dy)
        
        # Candidate 1: Horizontal then Diagonal
        pmid1 = p1 + np.array([sign_x * h_len, 0])
        candidates.append(np.array([p1, pmid1, p2]))
        
        # Candidate 2: Diagonal then Horizontal
        pmid2 = p1 + np.array([sign_x * d_len, sign_y * d_len])
        candidates.append(np.array([p1, pmid2, p2]))
        
        # Candidate 3: S-curve (Diag - Horiz - Diag) or (Horiz - Diag - Horiz)
        # Let's do Horiz(half) - Diag - Horiz(half)
        pmid3a = p1 + np.array([sign_x * (h_len / 2), 0])
        pmid3b = pmid3a + np.array([sign_x * d_len, sign_y * d_len])
        candidates.append(np.array([p1, pmid3a, pmid3b, p2]))
        
    else:
        # Needs Vertical and Diagonal
        v_len = abs(dy) - abs(dx)
        d_len = abs(dx)
        sign_x = np.sign(dx)
        sign_y = np.sign(dy)
        
        # Candidate 1: Vertical then Diagonal
        pmid1 = p1 + np.array([0, sign_y * v_len])
        candidates.append(np.array([p1, pmid1, p2]))
        
        # Candidate 2: Diagonal then Vertical
        pmid2 = p1 + np.array([sign_x * d_len, sign_y * d_len])
        candidates.append(np.array([p1, pmid2, p2]))
        
        # Candidate 3: Vert(half) - Diag - Vert(half)
        pmid3a = p1 + np.array([0, sign_y * (v_len / 2)])
        pmid3b = pmid3a + np.array([sign_x * d_len, sign_y * d_len])
        candidates.append(np.array([p1, pmid3a, pmid3b, p2]))

    return candidates

def generate_ring_template(center, radius, num_stations):
    """
    Generate an octagonal ring template for circular lines.
    Returns a polyline that forms an octagon.
    """
    # Standard octagon vertices
    angles = np.linspace(0, 2 * np.pi, 9)[:-1] # 8 points
    # Rotate by 22.5 degrees (pi/8) so edges are horizontal/vertical/diagonal
    angles += np.pi / 8
    
    octagon = np.array([
        [np.cos(a), np.sin(a)] for a in angles
    ]) * radius
    
    # Close the loop
    octagon = np.vstack((octagon, octagon[0]))
    return center + octagon
