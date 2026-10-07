import numpy as np

def apply_space_warp(anchor, config):
    """
    Apply a radial density-based space warp.
    Local scale factor smoothly transitions from 3.0x at the center to 0.3x at the edge.
    """
    if len(anchor) == 0:
        return anchor
        
    warped_anchor = anchor.copy()
    
    # 1. Find the center of mass
    center = np.mean(warped_anchor, axis=0)
    
    # 2. Calculate distances from center
    vectors = warped_anchor - center
    distances = np.linalg.norm(vectors, axis=1)
    max_dist = np.max(distances)
    
    if max_dist < 1e-6:
        return warped_anchor
        
    # 3. Apply exact scale integration
    # Local scale S(r) = 3.0 - 2.7 * (r / max_dist)
    # Warped distance r' = Integral of S(r) dr = 3.0 * r - 1.35 * (r^2 / max_dist)
    warped_dist = 3.0 * distances - 1.35 * (distances**2 / max_dist)
    
    # 4. Calculate new positions
    warp_ratio = np.where(distances > 1e-6, warped_dist / distances, 3.0)
    warped_anchor = center + vectors * warp_ratio[:, np.newaxis]
    
    return warped_anchor
