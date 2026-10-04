"""Geometry predicates shared by routing, energy, labels and metrics."""
import math
import numpy as np

EPS = 1e-8
DIRECTIONS = np.array([(math.cos(i*math.pi/4),math.sin(i*math.pi/4)) for i in range(8)])
DIRECTIONS[np.abs(DIRECTIONS)<EPS] = 0


def bearing(vector):
    return math.degrees(math.atan2(vector[1],vector[0])) % 360


def angle_difference(a,b):
    return abs((a-b+180)%360-180)


def port(vector):
    return int(math.floor((bearing(vector)+22.5)/45)) % 8


def direction_deviation(vector, tolerance):
    if np.linalg.norm(vector) < EPS: return 180.
    angle = bearing(vector) % 90
    if angle < EPS or 90-angle < EPS: return 0.
    return max(0., abs(angle-45)-tolerance)


def path_length(path):
    return float(np.linalg.norm(np.diff(path,axis=0),axis=1).sum())


def point_segment_distances(points, start, end):
    delta = end-start
    t = np.clip((points-start) @ delta/max(float(delta @ delta), EPS**2),0,1)
    return np.linalg.norm(points-start-t[:,None]*delta,axis=1)


def cross(a,b):
    return a[...,0]*b[...,1]-a[...,1]*b[...,0]


def proper_crossing(a,b,c,d):
    return bool(cross(b-a,c-a)*cross(b-a,d-a)<-EPS and cross(d-c,a-c)*cross(d-c,b-c)<-EPS)


def intersection_pairs(routes, affected=None, previous=None, block_size=256):
    """Proper crossings count once per edge pair; updates touch changed edges only."""
    segments, owners = [], []
    for ei,path in enumerate(routes):
        for a,b in zip(path,path[1:]): segments.append((a,b)); owners.append(ei)
    if not segments: return set()
    array = np.asarray(segments); a,b = array[:,0],array[:,1]
    selected=np.arange(len(segments)) if affected is None else np.array([i for i,edge in enumerate(owners) if edge in affected],dtype=int)
    result=set() if previous is None else {pair for pair in previous if not any(edge in affected for edge in pair)}
    if not len(selected): return result
    for offset in range(0,len(selected),block_size):
        subset=selected[offset:offset+block_size]; c,d=a[subset],b[subset]
        first=cross((d-c)[:,None,:],a[None,:,:]-c[:,None,:])
        second=cross((d-c)[:,None,:],b[None,:,:]-c[:,None,:])
        third=cross((b-a)[None,:,:],c[:,None,:]-a[None,:,:])
        fourth=cross((b-a)[None,:,:],d[:,None,:]-a[None,:,:])
        hits=np.argwhere((first*second < -EPS) & (third*fourth < -EPS))
        result.update((min(owners[subset[i]],owners[j]),max(owners[subset[i]],owners[j])) for i,j in hits if owners[subset[i]]!=owners[j])
    return result


def cyclic_equal(a,b):
    if len(a) != len(b): return False
    if len(a) < 3: return True
    offset = b.index(a[0])
    return all(a[i] == b[(i+offset)%len(b)] for i in range(len(a)))


def tangent(path, at_source):
    return path[1]-path[0] if at_source else path[-2]-path[-1]


def node_tangents(graph, routes, node):
    return [(edge,tangent(routes[edge],graph.endpoints[edge,0]==node)) for _,edge in graph.adjacency[node]]


def circular_order(graph, positions, node):
    return [edge for _,edge in sorted(graph.adjacency[node],key=lambda item: (bearing(positions[item[0]]-positions[node]),item[1]))]


def rectangle_overlap(a,b):
    return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))


def segment_rectangle(a,b,rect):
    # Liang-Barsky clipping, including touches.
    lo,hi = 0.,1.
    delta = b-a
    for axis in range(2):
        if abs(delta[axis])<EPS:
            if a[axis]<rect[axis] or a[axis]>rect[axis+2]: return False
        else:
            first,second = (rect[axis]-a[axis])/delta[axis],(rect[axis+2]-a[axis])/delta[axis]
            lo,hi = max(lo,min(first,second)),min(hi,max(first,second))
            if lo>hi: return False
    return True
