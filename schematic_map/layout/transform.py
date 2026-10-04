import math
import numpy as np


def apply_transform(points, theta, aspect):
    angle = math.radians(theta)
    rotation = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    return (points @ rotation.T) * [1, aspect]


def target_lengths(graph, config):
    term = config['terms']['S2_edge_length']
    return np.array([max(config['grid']['d_min'], term['a']+term['b']*math.log1p(e['distance']/term['d0_km'])) for e in graph.edges])


def golden(function, lo, hi, iterations):
    ratio = (math.sqrt(5)-1)/2
    x, y = hi-ratio*(hi-lo), lo+ratio*(hi-lo)
    fx, fy = function(x), function(y)
    for _ in range(iterations):
        if fx < fy:
            hi, y, fy = y, x, fx; x = hi-ratio*(hi-lo); fx = function(x)
        else:
            lo, x, fx = x, y, fy; y = lo+ratio*(hi-lo); fy = function(y)
    return (lo+hi)/2


def find_transform(graph, config):
    cfg = config['transform']
    vectors = graph.geo[graph.endpoints[:,1]] - graph.geo[graph.endpoints[:,0]]
    weights = np.linalg.norm(vectors, axis=1)
    def score(theta, aspect):
        transformed = apply_transform(vectors, theta, aspect)
        angles = np.arctan2(transformed[:,1], transformed[:,0])
        deviations = (angles + math.pi/8) % (math.pi/4)-math.pi/8
        return float(np.sum(weights * deviations**2)) + cfg['lambda_theta']*math.radians(theta)**2 + cfg['lambda_s']*math.log(aspect)**2
    candidates = [(score(t,s), float(t), float(s)) for t in np.arange(-cfg['theta_max_deg'],cfg['theta_max_deg']+1e-8,cfg['theta_step_deg']) for s in np.arange(cfg['aspect_range'][0],cfg['aspect_range'][1]+1e-8,cfg['aspect_step'])]
    _, theta, aspect = min(candidates)
    for _ in range(2):
        theta = golden(lambda t:score(t,aspect), max(-cfg['theta_max_deg'],theta-cfg['theta_step_deg']), min(cfg['theta_max_deg'],theta+cfg['theta_step_deg']),cfg['refine_iterations'])
        aspect = golden(lambda s:score(theta,s), max(cfg['aspect_range'][0],aspect-cfg['aspect_step']),min(cfg['aspect_range'][1],aspect+cfg['aspect_step']),cfg['refine_iterations'])
    anchor = apply_transform(graph.geo, theta, aspect)
    targets = target_lengths(graph, config)
    # Independent scale per component prevents distant isolated components shrinking a network.
    for component in graph.components:
        ids = set(component)
        ei = [i for i,(u,v) in enumerate(graph.endpoints) if u in ids and v in ids]
        points = anchor[component]
        anchor[component] -= points.mean(axis=0)
        lengths = np.linalg.norm(anchor[graph.endpoints[ei,1]]-anchor[graph.endpoints[ei,0]],axis=1)
        positive = lengths[lengths > 1e-12]
        if len(positive): anchor[component] *= float(np.median(targets[ei])/np.median(positive))
    return anchor, {'rotation_deg':theta, 'aspect':aspect,'origin_lonlat':graph.origin}
