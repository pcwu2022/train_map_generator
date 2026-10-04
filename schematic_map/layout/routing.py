"""Cached translation-invariant 0/1/2-bend route enumeration."""
from collections import OrderedDict
from .spatial import SpatialGrid
from itertools import product
import numpy as np
from .geometry import (DIRECTIONS, EPS, direction_deviation, path_length, port,
                       angle_difference, bearing, point_segment_distances, cross, diagonal_soft_deviation, segment_distance,
                       cyclic_equal, circular_order, node_tangents, proper_crossing)


class Router:
    def __init__(self, graph, targets, anchor, config):
        self.graph, self.targets, self.anchor, self.config = graph, targets, anchor, config
        self.cache = OrderedDict()
        self.rank_cache = OrderedDict()
        self.pairs = [(a,b) for a,b in product(range(8),repeat=2) if min((a-b)%8,(b-a)%8) in (1,2)]
        self.triples = [(a,b,c) for a,b in self.pairs for c in range(8) if min((b-c)%8,(c-b)%8) in (1,2)]
        self.orders = graph.topology_orders if graph.topology_orders is not None else [circular_order(graph,graph.topology_reference if graph.topology_reference is not None else anchor,i) for i in range(len(graph.nodes))]
        # Precompute inverse direction matrices; solving tiny systems repeatedly is expensive.
        self.inverses = {(a,b):np.linalg.inv(np.column_stack((DIRECTIONS[a],DIRECTIONS[b]))) for a,b in self.pairs}

    def candidates(self, delta, full=False, min_length=None):
        key = (round(float(delta[0]),8),round(float(delta[1]),8),full,min_length)
        if key in self.cache:
            self.cache.move_to_end(key); return self.cache[key]
        cfg = self.config['routing']; minimum = cfg['min_segment']
        result = []
        origin = np.zeros(2)
        exact=(not self.graph.skeleton or not self.config['skeleton']['exact_octilinear'] or abs((bearing(delta)+22.5)%45-22.5)<EPS)
        if exact and np.linalg.norm(delta)>=minimum and direction_deviation(delta,cfg['diagonal_tolerance_deg'])==0:
            result.append(np.array([origin,delta]))
        for a,b in self.pairs:
            lengths = self.inverses[a,b] @ delta
            if min(lengths)>=minimum-EPS:
                result.append(np.array([origin,lengths[0]*DIRECTIONS[a],delta]))
        samples = cfg['final_samples'] if full else cfg['samples']
        # Sample first segment; solve the other two. This parameterization also covers d1=d3.
        radius = max(np.linalg.norm(delta),minimum*3,min_length or 0)
        for a,b,c in self.triples:
            inverse = self.inverses[b,c]
            # Feasible interval for first length from positivity of the solved remaining lengths.
            initial, slope = inverse @ delta, -(inverse @ DIRECTIONS[a])
            lo,hi = minimum, radius*2
            for value,rate in zip(initial,slope):
                if abs(rate)<EPS:
                    if value<minimum-EPS: hi=-1; break
                elif rate>0: lo=max(lo,(minimum-value)/rate)
                else: hi=min(hi,(minimum-value)/rate)
            if hi<lo-EPS: continue
            for fraction in samples:
                first = lo+(hi-lo)*fraction
                second,third = initial+slope*first
                if min(second,third)<minimum-EPS: continue
                result.append(np.array([origin,first*DIRECTIONS[a],first*DIRECTIONS[a]+second*DIRECTIONS[b],delta]))
        if self.graph.skeleton:
            for a,b,c in self.triples:
                for d in range(8):
                    if (c,d) not in self.inverses:continue
                    inverse=self.inverses[c,d]
                    for first_fraction,second_fraction in product(self.config['skeleton']['four_segment_samples'],repeat=2):
                        first=max(minimum,radius*first_fraction);second=max(minimum,radius*second_fraction)
                        third,fourth=inverse @ (delta-first*DIRECTIONS[a]-second*DIRECTIONS[b])
                        if min(third,fourth)<minimum-EPS:continue
                        one=first*DIRECTIONS[a];two=one+second*DIRECTIONS[b];three=two+third*DIRECTIONS[c]
                        result.append(np.array([origin,one,two,three,delta]))
        # Canonical ties favour shorter routes; preserve deterministic enumeration.
        result.sort(key=lambda p:(len(p),path_length(p), port(p[1]-p[0])%2))
        if self.graph.skeleton:
            quota=self.config['skeleton']['candidates_per_ports'];counts={};selected=[]
            for path in result:
                if min_length is not None and path_length(path)<min_length-EPS:continue
                group=(len(path),port(path[1]-path[0]),port(path[-2]-path[-1]))
                if counts.get(group,0)>=quota:continue
                counts[group]=counts.get(group,0)+1;selected.append(path)
            result=selected
        if not result: result = [np.array([origin,delta])]  # An explicitly scored infeasible fallback.
        self.cache[key] = result
        if len(self.cache)>cfg['cache_size']: self.cache.popitem(last=False)
        return result

    def score(self, path, edge, positions, routes):
        graph,cfg = self.graph,self.config
        u,v = graph.endpoints[edge]; terms = cfg['terms']
        def weight(name): return terms[name]['weight'] if terms[name]['enabled'] else 0
        length = path_length(path); bends = len(path)-2
        result = weight('S2_edge_length')*((length-self.targets[edge])/self.targets[edge])**2
        result += weight('S11_line_turns')*bends*len(graph.edges[edge]['lines'])
        result += weight('S4_bends')*min(1,bends)+(terms['S4_bends']['second_bend'] if terms['S4_bends']['enabled'] and bends>1 else 0)
        if terms['S3_angle'].get('exact_diagonal',False):
            result+=weight('S3_angle')*sum(diagonal_soft_deviation(d,cfg['routing']['diagonal_tolerance_deg']) for d in np.diff(path,axis=0))
        result += weight('H4_segment_direction')*sum(direction_deviation(d,cfg['routing']['diagonal_tolerance_deg'])>EPS for d in np.diff(path,axis=0))
        clearance = cfg['routing']['clearance']+max(0,len(graph.edges[edge]['lines'])-1)*(cfg['render']['line_width']+cfg['render']['bundle_gap'])/2
        lower=path.min(axis=0)-clearance; upper=path.max(axis=0)+clearance
        nearby=self.node_index.query([*lower,*upper]) if hasattr(self,'node_index') else range(len(positions))
        others=np.array([node for node in nearby if node not in (u,v)],dtype=int)
        for a,b in zip(path,path[1:]):
            distances = point_segment_distances(positions[others],a,b)
            result += weight('H5_node_clearance')*float(np.sum(np.maximum(0,clearance-distances)/clearance))
        for node,is_source in ((u,True),(v,False)):
            own = path[1]-path[0] if is_source else path[-2]-path[-1]
            known = [(edge,own)]
            for _,other in graph.adjacency[node]:
                if other==edge or routes[other] is None: continue
                other_path=routes[other]
                out = other_path[1]-other_path[0] if graph.endpoints[other,0]==node else other_path[-2]-other_path[-1]
                result += weight('H6_ports')*(port(own)==port(out) or angle_difference(bearing(own),bearing(out))<45-EPS)
                common = set(graph.edges[edge]['lines']) & set(graph.edges[other]['lines'])
                for line in common:
                    incident = [e for _,e in graph.adjacency[node] if line in graph.edges[e]['lines']]
                    if len(incident)==2:
                        deviation=180-angle_difference(bearing(own),bearing(out))
                        result += weight('S5_collinearity')*(deviation/45 if terms['S5_collinearity'].get('linear',False) else deviation**2)
                known.append((other,out))
            if len(known)==len(graph.adjacency[node]):
                order = [e for e,d in sorted(known,key=lambda item:(bearing(item[1]),item[0]))]
                result += weight('H7_circular_order')*(not cyclic_equal(self.orders[node],order))
        padding=cfg['grid']['d_min']*cfg['skeleton']['corridor_spacing_factor'] if graph.skeleton else 0
        nearby_edges=self.edge_index.query([*(path.min(axis=0)-padding),*(path.max(axis=0)+padding)]) if hasattr(self,'edge_index') else range(len(routes))
        obstacles=[(a,b,other) for other in nearby_edges if other!=edge and routes[other] is not None for a,b in zip(routes[other],routes[other][1:])]
        if obstacles:
            a=np.array([item[0] for item in obstacles]); b=np.array([item[1] for item in obstacles]); hits=set()
            for start,end in zip(path,path[1:]):
                first=cross(end-start,a-start)*cross(end-start,b-start)
                second=cross(b-a,start-a)*cross(b-a,end-a)
                hits.update(obstacles[i][2] for i in np.flatnonzero((first < -EPS) & (second < -EPS)))
            result+=weight('S1_crossings')*len(hits)
        if graph.skeleton and obstacles:
            owners=np.array([item[2] for item in obstacles],dtype=int)
            valid=np.array([not (set(graph.endpoints[edge]) & set(graph.endpoints[other])) for other in owners])
            starts,ends=a[valid],b[valid];owners=owners[valid]
            nearest=np.full(len(graph.edges),np.inf)
            vectors=ends-starts;denominators=np.maximum(np.sum(vectors*vectors,axis=1),EPS**2)
            for start,end in zip(path,path[1:]):
                t=np.clip(np.sum((start-starts)*vectors,axis=1)/denominators,0,1)
                first=np.linalg.norm(start-starts-t[:,None]*vectors,axis=1)
                t=np.clip(np.sum((end-starts)*vectors,axis=1)/denominators,0,1)
                second=np.linalg.norm(end-starts-t[:,None]*vectors,axis=1)
                distances=np.minimum(np.minimum(first,second),np.minimum(point_segment_distances(starts,start,end),point_segment_distances(ends,start,end)))
                hits=(cross(end-start,starts-start)*cross(end-start,ends-start)<-EPS)&(cross(vectors,start-starts)*cross(vectors,end-starts)<-EPS)
                distances[hits]=0;np.minimum.at(nearest,owners,distances)
            result+=cfg['skeleton']['corridor_weight']*float(np.maximum(0,(padding-nearest)/padding).sum())
        # Cartographic tie-break: an axis segment at a key node.
        preference = 0
        for node,vec in ((u,path[1]-path[0]),(v,path[-2]-path[-1])):
            if graph.nodes[node]['kind']!='through' or graph.nodes[node]['is_interchange']:
                preference += port(vec)%2
        return result, bends, preference, length

    def best(self, edge, positions, routes, full=False):
        u,v = self.graph.endpoints[edge]
        candidates = self.candidates(positions[v]-positions[u],full,self.graph.edges[edge]['min_path_length'] if self.graph.skeleton else None)
        if self.graph.skeleton:
            required=self.graph.edges[edge]['min_path_length']
            candidates=[path for path in candidates if path_length(path)>=required-EPS] or candidates[-1:]
        terms = self.config['terms']
        def lower(path):
            bends = len(path)-2
            value = terms['S2_edge_length']['weight']*((path_length(path)-self.targets[edge])/self.targets[edge])**2 if terms['S2_edge_length']['enabled'] else 0.
            if terms['S4_bends']['enabled']:
                value += terms['S4_bends']['weight']*min(bends,1)+(terms['S4_bends']['second_bend'] if bends>1 else 0)
            if terms['S11_line_turns']['enabled']:value+=terms['S11_line_turns']['weight']*bends*len(self.graph.edges[edge]['lines'])
            return value
        rank_key=(round(float(positions[v,0]-positions[u,0]),8),round(float(positions[v,1]-positions[u,1]),8),float(self.targets[edge]),full)
        ranked=self.rank_cache.get(rank_key)
        if ranked is None:
            ranked = sorted(((lower(p),i,p) for i,p in enumerate(candidates)),key=lambda item:(item[0],item[1]))
            self.rank_cache[rank_key]=ranked
            if len(self.rank_cache)>self.config['routing']['cache_size']: self.rank_cache.popitem(last=False)
        best_path,best_score = None,None
        for bound,_,relative in ranked:
            if best_score is not None and bound > best_score[0]+EPS: break
            path = relative+positions[u]
            path[0]=positions[u]; path[-1]=positions[v]
            score = self.score(path,edge,positions,routes)
            if best_score is None or score<best_score: best_path,best_score=path,score
        return best_path.copy()

    def route_all(self, positions, full=False, previous=None, affected=None):
        routes = [None]*len(self.graph.edges) if previous is None else [p.copy() for p in previous]
        indices = list(range(len(routes))) if affected is None else sorted(affected)
        if previous is not None:
            for edge in indices: routes[edge]=None
        self.node_index=SpatialGrid(self.config['routing']['spatial_cell_size'])
        self.edge_index=SpatialGrid(self.config['routing']['spatial_cell_size'])
        for node,point in enumerate(positions): self.node_index.put(node,[*point,*point])
        for edge,path in enumerate(routes):
            if path is not None: self.edge_index.put(edge,[*path.min(axis=0),*path.max(axis=0)])
        for edge in indices:
            routes[edge]=self.best(edge,positions,routes,full)
            self.edge_index.put(edge,[*routes[edge].min(axis=0),*routes[edge].max(axis=0)])
        for _ in range(self.config['routing']['passes']-1 if affected is None else 0):
            for edge in indices:
                routes[edge]=self.best(edge,positions,routes,full)
                self.edge_index.put(edge,[*routes[edge].min(axis=0),*routes[edge].max(axis=0)])
        return routes
