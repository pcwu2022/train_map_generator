"""Public graph -> layout API. Elapsed runtime is optional for byte reproducibility."""
from copy import deepcopy
import time
import numpy as np
from .config import load_config
from .io.validate import validate_graph
from .graph.build import build_graph
from .layout.transform import find_transform,target_lengths,apply_transform
from .layout.init import initial_layout
from .layout.anneal import optimize
from .layout.refine import refine
from .layout.bundles import order_bundles
from .layout.labels import place_labels
from .layout.energy.base import Layout
from .metrics import measure


def generate_layout(data,config=None,record_runtime=False,progress=None):
    started=time.perf_counter(); config=load_config(overrides=config)
    validate_graph(data); graph=build_graph(data,config)
    anchor,transform=find_transform(graph,config)
    graph.topology_reference=apply_transform(graph.geo,transform['rotation_deg'],transform['aspect'])
    targets=target_lengths(graph,config)
    positions=initial_layout(graph,anchor,targets,config); routes=[None]*len(graph.edges)
    component_label_boxes=[]
    # Optimize each component separately; neither obstacles nor annealing cross components.
    for number,component in enumerate(graph.components):
        if progress: progress(f'Layout component {number+1}/{len(graph.components)} ({len(component)} stations)')
        node_ids={graph.nodes[i]['id'] for i in component}
        edge_ids=[i for i,e in enumerate(graph.edges) if e['source'] in node_ids]
        subdata={'nodes':[deepcopy(graph.nodes[i]) for i in component], 'edges':[deepcopy(graph.edges[i]) for i in edge_ids],'lines':graph.lines}
        subgraph=build_graph(subdata,config)
        subgraph.geo=graph.geo[component]; subgraph.origin=graph.origin
        subgraph.topology_reference=graph.topology_reference[component]
        if config['init']['mode']=='skeleton' and config['skeleton']['enabled']:
            from .layout.skeleton import skeleton_layout
            sublayout=skeleton_layout(subgraph,positions[component],anchor[component],targets[edge_ids],config)
            if config['anneal']['multistart']:
                geographic_config=deepcopy(config);geographic_config['init']['mode']='geo'
                geographic=initial_layout(subgraph,anchor[component],targets[edge_ids],geographic_config)
                sublayout=optimize(subgraph,sublayout.positions,anchor[component],targets[edge_ids],config,initial_routes=sublayout.routes,alternate=geographic)
        else:
            sublayout=optimize(subgraph,positions[component],anchor[component],targets[edge_ids],config)
        sublayout=refine(sublayout)
        positions[component]=sublayout.positions
        _,label_boxes,_=place_labels(subgraph,sublayout.positions,sublayout.routes,config)
        component_label_boxes.append(label_boxes)
        for local,global_id in enumerate(edge_ids): routes[global_id]=sublayout.routes[local]
    # Pack complete component extents, including bends and provisional labels.
    cursor=0.
    for component,label_boxes in zip(graph.components,component_label_boxes):
        ids=set(component); edge_ids=[i for i,(u,v) in enumerate(graph.endpoints) if u in ids]
        clouds=[positions[component]]+[routes[e] for e in edge_ids]
        for box in label_boxes: clouds.append(np.array([[box[0],box[1]],[box[2],box[3]]]))
        cloud=np.concatenate(clouds); low,high=cloud.min(axis=0),cloud.max(axis=0)
        shift=np.array([cursor-low[0],-low[1]])
        positions[component]+=shift; anchor[component]+=shift
        for edge in edge_ids: routes[edge]+=shift
        # Preserve at least the configured gap between complete component extents.
        cursor+=high[0]-low[0]+max(3.,config['components']['margin'])
    layout=Layout(graph,positions,routes,anchor,targets,config)
    orders,offsets=order_bundles(graph,routes,config)
    labels,boxes,label_overlaps=place_labels(graph,positions,routes,config)
    nodes=[]
    for i,node in enumerate(graph.nodes):
        item=deepcopy(node); item['schematic']=positions[i].tolist(); item['label']=labels[i]; nodes.append(item)
    edges=[]
    for i,edge in enumerate(graph.edges):
        item=deepcopy(edge); item.update(lines=orders[i],line_offsets=offsets[i],path=routes[i].tolist(),length=layout.facts()['lengths'][i].item()); edges.append(item)
    clouds=[positions]+routes
    cloud=np.concatenate(clouds) if len(positions) else np.zeros((1,2))
    bounds=[*cloud.min(axis=0),*cloud.max(axis=0)]
    for box in boxes:
        bounds=[min(bounds[0],box[0]),min(bounds[1],box[1]),max(bounds[2],box[2]),max(bounds[3],box[3])]
    metrics=measure(layout,label_overlaps); metrics['runtime_s']=time.perf_counter()-started if record_runtime else None
    meta={'version':'0.1','seed':config['seed'],'units':'grid_units','bounds':bounds,'y_axis':'up','feasible':metrics['hard_violations']==0}
    return {'meta':meta,'transform':transform,'nodes':nodes,'edges':edges,'lines':graph.lines,'metrics':metrics,'render':deepcopy(config['render']),'label_style':deepcopy(config['labels']),'web':deepcopy(config['web'])}
