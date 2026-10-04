"""Primary-line selection and length-weighted principal-axis measurements."""
import math
import numpy as np
from .geometry import EPS,bearing


def primary_line(graph,prefer_flagged=True):
    counts={line['id']:set() for line in graph.lines}
    for edge,(u,v) in enumerate(graph.endpoints):
        for line in graph.edges[edge]['lines']:counts[line].update((int(u),int(v)))
    available=[line for line in graph.lines if len(counts[line['id']])>=2]
    flagged=[line for line in available if line.get('primary',False)]
    candidates=(flagged or available) if prefer_flagged else available
    return min(candidates,key=lambda line:(-len(counts[line['id']]),line['id'])) if candidates else None


def primary_covariance(graph,points,config,routes=None):
    line=primary_line(graph)
    if line is None:return None,None
    if routes is None:
        weights=np.zeros(len(points))
        for edge,(u,v) in enumerate(graph.endpoints):
            if line['id'] in graph.edges[edge]['lines']:
                length=np.linalg.norm(points[v]-points[u]);weights[u]+=length/2;weights[v]+=length/2
        selected=weights>EPS;cloud=points[selected];weights=weights[selected]
    else:
        cloud=[];weights=[]
        for edge,path in enumerate(routes):
            if line['id'] not in graph.edges[edge]['lines']:continue
            for a,b in zip(path,path[1:]):
                # Gaussian quadrature integrates a straight segment's covariance exactly.
                length=np.linalg.norm(b-a)
                for fraction,weight in zip(config['primary_axis']['quadrature_points'],config['primary_axis']['quadrature_weights']):
                    cloud.append(a+fraction*(b-a));weights.append(length*weight)
        cloud=np.asarray(cloud);weights=np.asarray(weights)
    if not len(weights) or weights.sum()<EPS:return line,None
    centered=cloud-np.average(cloud,axis=0,weights=weights)
    covariance=(centered.T*weights) @ centered/weights.sum()
    return line,covariance


def covariance_axis(covariance,anisotropy):
    if covariance is None:return None
    values,vectors=np.linalg.eigh(covariance)
    if values[-1]<EPS or values[-1]/max(values[0],EPS)<anisotropy:return None
    return vectors[:,-1]


def primary_axis_error(graph,positions,routes,config):
    line,covariance=primary_covariance(graph,positions,config,routes)
    axis=covariance_axis(covariance,config['primary_axis']['min_anisotropy'])
    return (line['id'] if line else None,abs((bearing(axis)-90+90)%180-90) if axis is not None else None)
