import math
import numpy as np
from .reference import smooth_reference
from .primary import primary_line,primary_covariance,covariance_axis
from .geometry import EPS,bearing


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
    reference=smooth_reference(graph,config)
    primary=primary_line(graph)
    largest=primary_line(graph,prefer_flagged=False)
    if cfg['chain_bearings']:
        vectors=[];weights=[]
        for nodes,edges in graph.chains:
            if nodes[0]==nodes[-1]:continue
            vectors.append(reference[nodes[-1]]-reference[nodes[0]])
            length=float(np.linalg.norm(np.diff(reference[nodes],axis=0),axis=1).sum())
            prominent=any(line.get('primary',False) or (largest and line['id']==largest['id']) for line in graph.lines if line['id'] in graph.edges[edges[0]]['lines'])
            weights.append(length*(cfg['primary_prominence'] if prominent else 1))
        vectors=np.asarray(vectors).reshape((-1,2));weights=np.asarray(weights)
    else:
        vectors=graph.geo[graph.endpoints[:,1]]-graph.geo[graph.endpoints[:,0]]
        weights=np.linalg.norm(vectors,axis=1)
    _,covariance=primary_covariance(graph,reference,config)
    axis=covariance_axis(covariance,config['primary_axis']['min_anisotropy'])
    pca_theta=(90-bearing(axis)+90)%180-90 if axis is not None else None
    eligible=bool(config['primary_axis']['enabled'] and axis is not None and
                  (primary.get('primary',False) or abs(pca_theta)<=config['primary_axis']['eligible_angle_deg']))
    primary_length=sum(float(np.linalg.norm(reference[v]-reference[u])) for edge,(u,v) in enumerate(graph.endpoints) if primary and primary['id'] in graph.edges[edge]['lines'])
    rotation_limit=cfg['theta_max_deg']
    if eligible and primary.get('primary',False) and config['primary_axis']['allow_out_of_range_flagged']:
        rotation_limit=max(rotation_limit,abs(pca_theta))
    def score(theta, aspect):
        transformed = apply_transform(vectors, theta, aspect)
        angles = np.arctan2(transformed[:,1], transformed[:,0])
        deviations = (angles + math.pi/8) % (math.pi/4)-math.pi/8
        result=float(np.sum(weights * deviations**2)) + cfg['lambda_theta']*math.radians(theta)**2 + cfg['lambda_s']*math.log(aspect)**2
        if eligible:
            matrix=apply_transform(np.eye(2),theta,aspect).T
            rotated=matrix @ covariance @ matrix.T
            transformed_axis=covariance_axis(rotated,1)
            error=abs((bearing(transformed_axis)-90+90)%180-90)
            if error>config['primary_axis']['max_error_deg']+EPS:return float('inf')
            result+=config['primary_axis']['weight']*primary_length*math.radians(error)**2
        return result
    candidates = [(score(t,s), float(t), float(s)) for t in np.arange(-cfg['theta_max_deg'],cfg['theta_max_deg']+1e-8,cfg['theta_step_deg']) for s in np.arange(cfg['aspect_range'][0],cfg['aspect_range'][1]+1e-8,cfg['aspect_step'])]
    if eligible and abs(pca_theta)<=rotation_limit+EPS:
        for aspect_candidate in np.arange(cfg['aspect_range'][0],cfg['aspect_range'][1]+EPS,cfg['aspect_step']):
            candidates.append((score(pca_theta,float(aspect_candidate)),float(pca_theta),float(aspect_candidate)))
    _, theta, aspect = min(candidates)
    for _ in range(2):
        theta = golden(lambda t:score(t,aspect), max(-rotation_limit,theta-cfg['theta_step_deg']), min(rotation_limit,theta+cfg['theta_step_deg']),cfg['refine_iterations'])
        aspect = golden(lambda s:score(theta,s), max(cfg['aspect_range'][0],aspect-cfg['aspect_step']),min(cfg['aspect_range'][1],aspect+cfg['aspect_step']),cfg['refine_iterations'])
    anchor = apply_transform(reference, theta, aspect)
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
    return anchor, {'rotation_deg':theta, 'aspect':aspect,'origin_lonlat':graph.origin,'primary_line_id':primary['id'] if primary else None,'primary_axis_eligible':eligible}
