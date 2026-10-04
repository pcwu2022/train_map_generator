"""Chain-level geographic references; topology bearings remain unsmoothed for H7."""
import numpy as np
from .geometry import EPS,point_segment_distances


def key_nodes(graph):
    return [i for i,node in enumerate(graph.nodes) if node['kind']!='through' or node['is_interchange']]


def simplify(points,tolerance):
    if len(points)<=2:return points.copy()
    distances=point_segment_distances(points[1:-1],points[0],points[-1])
    pivot=int(np.argmax(distances))+1
    if distances[pivot-1]<=tolerance:return points[[0,-1]].copy()
    return np.concatenate((simplify(points[:pivot+1],tolerance)[:-1],simplify(points[pivot:],tolerance)))


def sample_polyline(points,distances):
    lengths=np.linalg.norm(np.diff(points,axis=0),axis=1)
    arc=np.concatenate(([0.],np.cumsum(lengths)))
    if arc[-1]<EPS:return np.repeat(points[:1],len(distances),axis=0)
    query=np.clip(distances,0,arc[-1])
    return np.column_stack([np.interp(query,arc,points[:,axis]) for axis in range(2)])


def smooth_reference(graph,config):
    result=graph.geo.copy();cfg=config['reference']
    if not cfg['enabled']:return result
    for nodes,_ in graph.chains:
        if len(nodes)<=2:continue
        points=graph.geo[nodes];simple=simplify(points,cfg['simplify_tolerance_km'])
        original=np.concatenate(([0.],np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))))
        total=float(np.linalg.norm(np.diff(simple,axis=0),axis=1).sum())
        fractions=original/original[-1] if original[-1]>EPS else np.linspace(0,1,len(nodes))
        smoothed=sample_polyline(simple,fractions*total)
        alpha=cfg['low_pass_alpha']
        for _ in range(cfg['low_pass_iterations']):
            updated=smoothed.copy();updated[1:-1]=(1-alpha)*smoothed[1:-1]+alpha*(smoothed[:-2]+smoothed[2:])/2
            smoothed=updated
        # Shared keys retain the same coordinates for every incident chain.
        result[nodes[1:-1]]=smoothed[1:-1]
    return result


def chain_direction_cost(layout,tolerance):
    from .geometry import bearing,angle_difference
    cost=0.
    for nodes,_ in layout.graph.chains:
        if nodes[0]==nodes[-1]:continue
        u,v=nodes[0],nodes[-1]
        deviation=angle_difference(bearing(layout.anchor[v]-layout.anchor[u]),bearing(layout.positions[v]-layout.positions[u]))
        cost+=max(0,deviation-tolerance)/45
    return cost


def relative_order_cost(layout,k):
    keys=key_nodes(layout.graph);cost=0;seen=set()
    for component in layout.graph.components:
        local=[node for node in keys if node in component]
        for u in local:
            nearest=sorted((v for v in local if v!=u),key=lambda v:(float(np.linalg.norm(layout.anchor[v]-layout.anchor[u])),v))[:k]
            for v in nearest:
                pair=tuple(sorted((u,v)))
                if pair in seen:continue
                seen.add(pair)
                geographic=layout.anchor[v]-layout.anchor[u];schematic=layout.positions[v]-layout.positions[u]
                cost+=sum(abs(a)>EPS and a*b<0 for a,b in zip(geographic,schematic))
    return float(cost)
