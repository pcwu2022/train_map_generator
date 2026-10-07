"""Deterministic line walks and arc-length runs, including reversed edges and loops."""
import math
import numpy as np
from .geometry import EPS, bearing


def line_walks(graph):
    walks=[]
    for line in graph.lines:
        adjacency=[[] for _ in graph.nodes]
        for edge,(u,v) in enumerate(graph.endpoints):
            if line['id'] in graph.edges[edge]['lines']:
                adjacency[u].append((v,edge)); adjacency[v].append((u,edge))
        used=set()
        starts=[i for i,items in enumerate(adjacency) if items and len(items)!=2]
        starts += [i for i,items in enumerate(adjacency) if len(items)==2]
        for start in starts:
            for following,edge in adjacency[start]:
                if edge in used: continue
                nodes,edges=[start],[]; current=start
                while edge not in used:
                    used.add(edge);edges.append(edge);nodes.append(following)
                    current=following
                    if current==start or len(adjacency[current])!=2:break
                    choices=[item for item in adjacency[current] if item[1] not in used]
                    if not choices:break
                    following,edge=choices[0]
                walks.append((line['id'],nodes,edges,len(adjacency[start])==1,len(adjacency[current])==1))
    return walks


def walk_geometry(graph,routes,walk):
    _,nodes,edges,start_terminal,end_terminal=walk
    points=[]; station_positions=[]
    for i,edge in enumerate(edges):
        path=routes[edge] if graph.endpoints[edge,0]==nodes[i] else routes[edge][::-1]
        station_positions.append(len(points)-1 if points else 0)
        points.extend(path if not points else path[1:])
    if not points:return None
    station_positions.append(len(points)-1)
    points=np.asarray(points); vectors=np.diff(points,axis=0); lengths=np.linalg.norm(vectors,axis=1)
    arc=np.concatenate(([0.],np.cumsum(lengths)))
    angles=np.array([bearing(v) for v in vectors]); turns=[]; cuts=[0]
    for i in range(1,len(vectors)):
        turn=(angles[i]-angles[i-1]+180)%360-180
        if abs(turn)>EPS:
            turns.append((float(turn),float(arc[i]))); cuts.append(i)
    cuts.append(len(vectors))
    runs=[]
    for a,b in zip(cuts,cuts[1:]):
        count=sum(a<=vertex<=b for vertex in station_positions)
        runs.append({'length':float(arc[b]-arc[a]),'stations':count,
                     'terminal':(a==0 and start_terminal) or (b==len(vectors) and end_terminal)})
    closed=nodes[0]==nodes[-1]
    if closed and len(vectors):
        turn=(angles[0]-angles[-1]+180)%360-180
        if abs(turn)>EPS:turns.append((float(turn),float(arc[-1])))
        elif len(runs)>1:
            first,last=runs[0],runs[-1]
            runs=[{'length':first['length']+last['length'],'stations':first['stations']+last['stations']-1,'terminal':False}]+runs[1:-1]
    return {'turns':turns,'runs':runs,'length':float(arc[-1]),'closed':closed}


def line_facts(graph,routes,config):
    cfg=config['line_geometry']; threshold=cfg['turn_threshold_deg']
    counts={line['id']:0 for line in graph.lines}; zigzags=0; runs=[]; fractions={line['id']:[0.,0.] for line in graph.lines}
    for walk in line_walks(graph):
        geometry=walk_geometry(graph,routes,walk)
        if geometry is None:continue
        turns=[item for item in geometry['turns'] if abs(item[0])+EPS>=threshold]
        counts[walk[0]]+=len(turns)
        pairs=list(zip(turns,turns[1:]))
        if geometry['closed'] and len(turns)>1:
            pairs.append((turns[-1],(turns[0][0],turns[0][1]+geometry['length'])))
        zigzags+=sum(a[0]*b[0]<0 and b[1]-a[1]<config['terms']['S12_zigzag']['zigzag_window']-EPS for a,b in pairs)
        runs.extend(geometry['runs'])
        fractions[walk[0]][0]+=sum(run['length'] for run in geometry['runs'] if run['stations']>=cfg['long_run_stations'])
        fractions[walk[0]][1]+=geometry['length']
    return {'turns_per_line':counts,'zigzag_count':int(zigzags),'runs':runs,
            'long_run_fraction_per_line':{line:(min(1.0, max(0.0, float(length/total))) if total>EPS else None) for line,(length,total) in fractions.items()}}
