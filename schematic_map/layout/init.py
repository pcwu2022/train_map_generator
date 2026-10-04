import numpy as np
from .spatial import SpatialGrid


def separate(points, minimum, pitch, iterations):
    points = points.copy()
    for _ in range(iterations):
        changed = False
        index=SpatialGrid(minimum)
        for node,point in enumerate(points):index.put(node,[*point,*point])
        for u in range(len(points)):
            point=points[u]
            candidates=index.query([*(point-minimum),*(point+minimum)])
            for v in candidates:
                if v>=u: continue
                delta = points[u]-points[v]; length = np.linalg.norm(delta)
                if length+1e-9 < minimum:
                    direction = delta/length if length > 1e-12 else np.array([1.,0.])
                    shift = direction*(minimum-length+pitch)/2
                    points[u] += shift; points[v] -= shift; changed = True
                    index.put(u,[*points[u],*points[u]]);index.put(v,[*points[v],*points[v]])
        points = np.round(points/pitch)*pitch
        if not changed: break
    return points


def initial_layout(graph, anchor, targets, config):
    points = anchor.copy()
    if config['init']['mode'] == 'hint':
        if any('schematic' not in n for n in graph.nodes):
            raise ValueError('init.mode=hint requires schematic hints for every node')
        points = np.array([n['schematic'] for n in graph.nodes], dtype=float).reshape((-1,2))
    else:
        for component in graph.components:
            n = len(component)
            if n < 2: continue
            lookup = {v:i for i,v in enumerate(component)}
            distances = np.full((n,n), np.inf); np.fill_diagonal(distances,0)
            for ei,(u,v) in enumerate(graph.endpoints):
                if u in lookup and v in lookup: distances[lookup[u],lookup[v]] = distances[lookup[v],lookup[u]] = targets[ei]
            for k in range(n): distances = np.minimum(distances,distances[:,k,None]+distances[None,k,:])
            weights = np.zeros((n,n)); mask = distances>0; weights[mask] = 1/distances[mask]**2
            laplacian = np.diag(weights.sum(axis=1))-weights
            strength = config['init']['anchor_weight']
            inverse = np.linalg.inv(laplacian+strength*np.eye(n))
            current = points[component].copy()
            for _ in range(config['init']['stress_iterations']):
                lengths = np.linalg.norm(current[:,None,:]-current[None,:,:],axis=2)
                ratios = np.zeros_like(lengths); valid = lengths>1e-12
                ratios[valid] = -weights[valid]*distances[valid]/lengths[valid]
                np.fill_diagonal(ratios, -ratios.sum(axis=1))
                current = inverse @ (ratios @ current + strength*anchor[component])
            points[component] = current
    for component in graph.components:
        points[component] = separate(points[component],config['grid']['d_min'],config['grid']['pitch_fine'],config['grid']['overlap_iterations'])
    return points
