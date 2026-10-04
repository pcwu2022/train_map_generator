import math
import unicodedata
import numpy as np
from .geometry import rectangle_overlap,segment_rectangle
from .spatial import SpatialGrid

ANCHORS=('east','west','north','south','northeast','northwest','southeast','southwest')
VECTORS={'east':(1,0),'west':(-1,0),'north':(0,1),'south':(0,-1),'northeast':(1,1),'northwest':(-1,1),'southeast':(1,-1),'southwest':(-1,-1)}


def text_width(text,font_size):
    return sum(0 if unicodedata.combining(c) else (1 if unicodedata.east_asian_width(c) in ('W','F') else 0.6) for c in text)*font_size


def label_box(position,name,label,config):
    size=config['labels']['font_size']; width=text_width(name,size); height=size
    x,y=np.asarray(position)+label['offset']; anchor=label['anchor']
    if 'east' in anchor: xmin=x
    elif 'west' in anchor: xmin=x-width
    else: xmin=x-width/2
    if 'north' in anchor: ymin=y
    elif 'south' in anchor: ymin=y-height
    else: ymin=y-height/2
    rotation=math.radians(label.get('rotation_deg',0))
    if rotation:
        width,height=abs(width*math.cos(rotation))+abs(height*math.sin(rotation)),abs(width*math.sin(rotation))+abs(height*math.cos(rotation))
    pad=config['labels']['padding']
    return [xmin-pad,ymin-pad,xmin+width+pad,ymin+height+pad]


def place_labels(graph,positions,routes,config):
    choices=[]
    for node in graph.nodes:
        labels=[]
        for anchor,scale in ((anchor,scale) for anchor in ANCHORS for scale in config['labels']['offset_scales']):
            x,y=VECTORS[anchor]
            labels.append({'anchor':anchor,'offset':[x*config['labels']['offset']*scale,y*config['labels']['offset']*scale],'rotation_deg':0})
            if x and y and config['labels']['rotate_diagonal']:
                labels.append({'anchor':anchor,'offset':[x*config['labels']['offset']*scale,y*config['labels']['offset']*scale],'rotation_deg':45})
        choices.append(labels)
    selected=[None]*len(positions); boxes=[None]*len(positions)
    radii=[config['render']['interchange_radius'] if node['is_interchange'] else config['render']['marker_radius'] for node in graph.nodes]
    node_boxes=[[p[0]-r,p[1]-r,p[0]+r,p[1]+r] for p,r in zip(positions,radii)]
    cell=config['routing']['spatial_cell_size']
    node_index,edge_index,label_index=SpatialGrid(cell),SpatialGrid(cell),SpatialGrid(cell)
    for node,box in enumerate(node_boxes):node_index.put(node,box)
    for edge,path in enumerate(routes):edge_index.put(edge,[*path.min(axis=0),*path.max(axis=0)])
    static={}
    def cost(node,label):
        key=(node,label['anchor'],label['rotation_deg'],tuple(label['offset']))
        if key not in static:
            box=label_box(positions[node],graph.nodes[node]['name'],label,config)
            conflicts=sum(rectangle_overlap(box,node_boxes[i])>0 for i in node_index.query(box))
            conflicts+=sum(any(segment_rectangle(a,b,box) for a,b in zip(routes[i],routes[i][1:])) for i in edge_index.query(box))
            static[key]=(box,conflicts)
        box,conflicts=static[key]
        conflicts+=sum(rectangle_overlap(box,boxes[i])>0 for i in label_index.query(box) if i!=node)
        distance=max(abs(value) for value in label['offset'])/config['labels']['offset']-1
        return conflicts*config['labels']['overlap_weight']+ANCHORS.index(label['anchor'])+config['labels']['distance_weight']*distance,box
    order=sorted(range(len(positions)),key=lambda i:(not graph.nodes[i]['is_interchange'],-graph.nodes[i]['degree'],i))
    for _ in range(config['labels']['local_passes']+1):
        for i in order:
            choice=min(choices[i],key=lambda label:cost(i,label)[0]); selected[i]=choice; boxes[i]=cost(i,choice)[1]
            label_index.put(i,boxes[i])
    # Local pair swaps when both stations could benefit; deterministic bounded search.
    order_rank={node:rank for rank,node in enumerate(order)}
    for i in order:
        for j in sorted(label_index.query(boxes[i]),key=lambda node:order_rank[node]):
            if j<=i or rectangle_overlap(boxes[i],boxes[j])==0: continue
            old_i,old_j=selected[i],selected[j]
            old_cost=cost(i,old_i)[0]+cost(j,old_j)[0]
            best=(old_cost,old_i,old_j)
            for a in choices[i]:
                boxes[i]=label_box(positions[i],graph.nodes[i]['name'],a,config); label_index.put(i,boxes[i])
                for b in choices[j]:
                    boxes[j]=label_box(positions[j],graph.nodes[j]['name'],b,config); label_index.put(j,boxes[j])
                    value=cost(i,a)[0]+cost(j,b)[0]
                    if value<best[0]: best=(value,a,b)
            _,selected[i],selected[j]=best
            boxes[i]=label_box(positions[i],graph.nodes[i]['name'],selected[i],config)
            boxes[j]=label_box(positions[j],graph.nodes[j]['name'],selected[j],config)
            label_index.put(i,boxes[i]); label_index.put(j,boxes[j])
    overlaps=sum(rectangle_overlap(box,boxes[j])>0 for i,box in enumerate(boxes) for j in label_index.query(box) if j<i)
    overlaps+=sum(rectangle_overlap(box,node_boxes[j])>0 for box in boxes for j in node_index.query(box))
    overlaps+=sum(any(segment_rectangle(a,b,box) for a,b in zip(routes[j],routes[j][1:])) for box in boxes for j in edge_index.query(box))
    return selected,boxes,int(overlaps)
