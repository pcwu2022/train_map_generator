"""Pluggable energy terms. A term may supply an incremental delta implementation."""
from dataclasses import dataclass, field
import importlib
import numpy as np
from ..geometry import (path_length, direction_deviation, bearing, angle_difference,
    node_tangents, port, cyclic_equal, circular_order, point_segment_distances, intersection_pairs, EPS)


@dataclass
class Layout:
    graph: object
    positions: np.ndarray
    routes: list
    anchor: np.ndarray
    targets: np.ndarray
    config: dict
    cache: dict = field(default_factory=dict)
    previous: object = None
    changed: tuple = ()

    def facts(self):
        if self.cache: return self.cache
        g,p,c = self.graph,self.positions,self.config
        n = len(p)
        distances = np.linalg.norm(p[:,None,:]-p[None,:,:],axis=2)
        old=self.previous.facts() if self.previous is not None else None
        affected={edge for node in self.changed for _,edge in g.adjacency[node]} if old else None
        lengths = old['lengths'].copy() if old else np.empty(len(self.routes))
        for edge,path in enumerate(self.routes):
            if affected is None or edge in affected: lengths[edge]=path_length(path)
        bends = np.array([len(path)-2 for path in self.routes])
        hard = {name:[] for name in ('H1_min_spacing','H2_bend_limit','H3_bend_angle','H4_segment_direction','H5_node_clearance','H6_ports','H7_circular_order')}
        spacing_penalty = 0.
        for u,v in np.argwhere(np.triu(distances<c['grid']['d_min']-EPS,1)):
            hard['H1_min_spacing'].append({'nodes':[g.nodes[u]['id'],g.nodes[v]['id']], 'distance':float(distances[u,v])})
            spacing_penalty += (c['grid']['d_min']-distances[u,v])/c['grid']['d_min']
        angles,clearance_penalty = [],0.
        for ei,path in enumerate(self.routes):
            u,v = g.endpoints[ei]
            if lengths[ei]<c['grid']['d_min']-EPS:
                hard['H1_min_spacing'].append({'edge':ei,'length':float(lengths[ei])}); spacing_penalty += (c['grid']['d_min']-lengths[ei])/c['grid']['d_min']
            if bends[ei]>2: hard['H2_bend_limit'].append({'edge':ei})
            vectors = np.diff(path,axis=0)
            for a,b in zip(vectors,vectors[1:]):
                turn = angle_difference(bearing(a),bearing(b))
                if min(abs(turn-45),abs(turn-90))>EPS: hard['H3_bend_angle'].append({'edge':ei,'turn_deg':turn})
            for segment,d in enumerate(vectors):
                deviation = direction_deviation(d,c['routing']['diagonal_tolerance_deg']); angles.append(deviation)
                if deviation>EPS: hard['H4_segment_direction'].append({'edge':ei,'segment':segment,'deviation_deg':deviation})
            clearance=c['routing']['clearance']+max(0,len(g.edges[ei]['lines'])-1)*(c['render']['line_width']+c['render']['bundle_gap'])/2
            if old is not None and ei not in affected:
                changed_ids={g.nodes[node]['id'] for node in self.changed}
                reports=[report for report in old['hard']['H5_node_clearance'] if report['edge']==ei and report['node'] not in changed_ids]
                test_nodes=np.array([node for node in self.changed if node not in (u,v)],dtype=int)
            else:
                reports=[]
                test_nodes=np.array([node for node in range(n) if node not in (u,v)],dtype=int)
            minimum=np.full(len(test_nodes),np.inf)
            for a,b in zip(path,path[1:]): minimum=np.minimum(minimum,point_segment_distances(p[test_nodes],a,b))
            for local in np.flatnonzero(minimum<clearance-EPS):
                reports.append({'edge':ei,'node':g.nodes[test_nodes[local]]['id'],'distance':float(minimum[local])})
            hard['H5_node_clearance'].extend(reports)
            clearance_penalty += sum((clearance-report['distance'])/clearance for report in reports)
        collinear=[]
        for node in range(n):
            tangents = node_tangents(g,self.routes,node)
            for i,(edge,a) in enumerate(tangents):
                for other,b in tangents[:i]:
                    separation=angle_difference(bearing(a),bearing(b))
                    if port(a)==port(b) or separation<45-EPS:
                        hard['H6_ports'].append({'node':g.nodes[node]['id'],'edges':[edge,other]})
            order=[e for e,d in sorted(tangents,key=lambda item:(bearing(item[1]),item[0]))]
            if not cyclic_equal(circular_order(g,g.topology_reference if g.topology_reference is not None else self.anchor,node),order): hard['H7_circular_order'].append({'node':g.nodes[node]['id']})
            for line in g.nodes[node]['lines']:
                incident=[d for edge,d in tangents if line in g.edges[edge]['lines']]
                if len(incident)==2: collinear.append(180-angle_difference(bearing(incident[0]),bearing(incident[1])))
        geo_deviations=[]
        for u,v in g.endpoints:
            geo_deviations.append(angle_difference(bearing(self.anchor[v]-self.anchor[u]),bearing(p[v]-p[u])))
        chain_variances, cvs = [],[]
        for _,edges in g.chains:
            values=lengths[edges]
            if len(values)>1 and values.mean()>EPS:
                cvs.append(float(values.std()/values.mean())); chain_variances.append(float(np.var(values/values.mean())))
        # Center before displacement so packed translations do not change the metric.
        displacement = p-p.mean(axis=0) - (self.anchor-self.anchor.mean(axis=0)) if n else p
        area=float(np.prod(np.ptp(p,axis=0))) if n else 0.
        self.cache.update(hard=hard,spacing_penalty=float(spacing_penalty),clearance_penalty=float(clearance_penalty),
            lengths=lengths,bends=bends,angles=angles,crossings=intersection_pairs(self.routes,affected,old['crossings'] if old else None,c['routing']['intersection_block_size']),collinear=collinear,
            geo_deviations=geo_deviations,chain_variances=chain_variances,chain_cvs=cvs,displacement=displacement,
            area=area,min_distance=float(distances[np.triu_indices(n,1)].min()) if n>1 else None)
        self.previous=None
        return self.cache


class Term:
    name: str
    kind: str
    def __init__(self, weight, parameters=None):
        self.weight = weight
        self.parameters = parameters or {}
    def full(self, layout):
        raise NotImplementedError
    def delta(self, layout, move):
        """move is the proposed Layout; custom terms can reuse either state's caches."""
        return self.full(move)-self.full(layout)


REGISTRY = {}


def register(cls):
    REGISTRY[cls.name]=cls
    return cls


def configured_terms(config):
    from . import hard, soft  # noqa: F401: register built-ins
    result=[]
    for name,params in config['terms'].items():
        if not params.get('enabled', True): continue
        cls=REGISTRY.get(name)
        if cls is None and '.' in name:
            module,attribute=name.rsplit('.',1); cls=getattr(importlib.import_module(module),attribute)
        if cls is None: raise ValueError(f'Unknown energy term {name}')
        result.append(cls(params.get('weight',1),params))
    return result


def energy(layout, terms):
    return sum(term.weight*term.full(layout) for term in terms)
