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
    from .anneal import optimize
    keys=key_nodes(graph)
    chains=[(nodes,edges) for nodes,edges in graph.chains if nodes[0]!=nodes[-1]]
    keys=sorted(set(keys)|{node for nodes,_ in chains for node in (nodes[0],nodes[-1])})
    lookup={node:i for i,node in enumerate(keys)}
    positions=initial.copy();routes=[None]*len(graph.edges)
    factor=config['skeleton']['spacing_factor'];minimum=config['grid']['d_min']
    if chains:
        edges=[]
        for nodes,chain_edges in chains:
            ids=graph.edges[chain_edges[0]]['lines']
            edges.append({'source':graph.nodes[nodes[0]]['id'],'target':graph.nodes[nodes[-1]]['id'],
                          'lines':ids,'distance':sum(graph.edges[e]['distance'] for e in chain_edges),
                          'min_path_length':len(chain_edges)*minimum*factor})
        coarse=build_graph({'nodes':[graph.nodes[node] for node in keys],'edges':edges,'lines':graph.lines},config)
        coarse.skeleton=True;coarse.geo=graph.geo[keys];coarse.topology_reference=graph.topology_reference[keys] if graph.topology_reference is not None else anchor[keys]
        # Preserve the original first/last incident-edge ordering, not skeleton chord order.
        original_reference=graph.topology_reference if graph.topology_reference is not None else anchor
        coarse.topology_orders=[]
        for node in keys:
            outgoing=[]
            for edge,(nodes,chain_edges) in enumerate(chains):
                if nodes[0]==node:outgoing.append((edge,bearing(original_reference[nodes[1]]-original_reference[node])))
                if nodes[-1]==node:outgoing.append((edge,bearing(original_reference[nodes[-2]]-original_reference[node])))
            coarse.topology_orders.append([edge for edge,angle in sorted(outgoing,key=lambda item:(item[1],item[0]))])
        coarse_config=deepcopy(config)
        coarse_config['routing']['passes']=config['skeleton']['routing_passes']
        coarse_config['anneal']['max_sweeps'] = config['skeleton'].get('anneal_sweeps', min(3, config['anneal']['max_sweeps']))
        coarse_config['anneal']['greedy_sweeps'] = config['skeleton'].get('greedy_sweeps', min(1, config['anneal']['greedy_sweeps']))
        for name,term in coarse_config['terms'].items():term['enabled']=term['enabled'] and name in config['skeleton']['terms']
        coarse_targets=np.array([max(sum(targets[chain_edges]),edge['min_path_length']) for (_,chain_edges),edge in zip(chains,edges)])
        coarse_points=initial[keys].copy()
        ratios=[edge['min_path_length']/max(float(np.linalg.norm(coarse_points[v]-coarse_points[u])),EPS) for edge,(u,v) in zip(edges,coarse.endpoints)]
        scale=min(config['skeleton']['max_initial_scale'],max([1.]+ratios))
        center=coarse_points.mean(axis=0);coarse_points=center+(coarse_points-center)*scale
        def coarse_callback(p, r, text, percent):
            if callback:
                current_pos = initial.copy()
                current_pos[keys] = p
                callback(current_pos, None, f'Skeleton {text}', percent)
        state=optimize(coarse,coarse_points,anchor[keys],coarse_targets,coarse_config,callback=coarse_callback if callback else None)
        positions[keys]=state.positions
        paths=state.routes
    else:paths=[]
    # Closed chains need a closed polygon rather than the zero chord of a self-loop.
    for nodes,chain_edges in graph.chains:
        if nodes[0]!=nodes[-1]:continue
        perimeter=max(sum(targets[chain_edges]),len(chain_edges)*minimum*factor)
        aspect=config['skeleton']['loop_aspect'];width=perimeter/(2*(1+aspect));height=width*aspect
        origin=positions[nodes[0]]
        paths.append(origin+np.array([[0,0],[width,0],[width,height],[0,height],[0,0]]))
        chains.append((nodes,chain_edges))
    for (nodes,chain_edges),path in zip(chains,paths):
        length=path_length(path);distances=np.linspace(0,length,len(nodes))
        stations=sample_polyline(path,distances)
        # Skeleton endpoints are shared exactly between incident chains.
        stations[0]=positions[nodes[0]];stations[-1]=positions[nodes[-1]]
        positions[nodes[1:-1]]=stations[1:-1]
        for i,edge in enumerate(chain_edges):
            route=slice_polyline(path,distances[i],distances[i+1])
            route[0]=stations[i];route[-1]=stations[i+1]
            routes[edge]=route if graph.endpoints[edge,0]==nodes[i] else route[::-1].copy()
    return Layout(graph,positions,routes,anchor,targets,config)
