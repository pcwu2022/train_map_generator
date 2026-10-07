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


def generate_layout(data,config=None,record_runtime=False,progress=None,live_callback=None):
    started=time.perf_counter(); config=load_config(overrides=config)
    validate_graph(data); graph=build_graph(data,config)
    anchor,transform=find_transform(graph,config)
    graph.topology_reference=apply_transform(graph.geo,transform['rotation_deg'],transform['aspect'])
    
    # Calculate inherent crossings from straight geographic lines
    from .layout.geometry import intersection_pairs
    geo_routes = [np.array([anchor[u], anchor[v]]) for u, v in graph.endpoints]
    allowed = intersection_pairs(geo_routes, None, None, config['routing']['intersection_block_size'])
    graph.allowed_crossings = { (min(u, v), max(u, v)) for u, v in allowed }
    
    # Calculate close station pairs for proximity hard constraint
    d_min = config['grid']['d_min']
    close_threshold = d_min * 1.5 # arbitrary threshold mapped to ~400m
    
    # Vectorized O(N^2) distance calculation
    dist_matrix = np.linalg.norm(anchor[:, None, :] - anchor[None, :, :], axis=2)
    u_idx, v_idx = np.where(np.triu(dist_matrix < close_threshold, 1))
    graph.close_pairs_u = u_idx
    graph.close_pairs_v = v_idx
    
    targets=target_lengths(graph,config)
    positions=initial_layout(graph,anchor,targets,config); routes=[None]*len(graph.edges)
    
    def make_component_callback(component, edge_ids, component_index):
        def callback(sub_positions, sub_routes, progress_text, component_percent=0.0):
            overall_percent = (component_index + component_percent) / len(graph.components)
            if progress:
                bar_len = 30
                filled_len = int(round(bar_len * overall_percent))
                bar = '=' * filled_len + '-' * (bar_len - filled_len)
                try:
                    progress(f'\r[{bar}] {overall_percent*100:5.1f}% | C{component_index+1}/{len(graph.components)}: {progress_text}'.ljust(80), end='', flush=True)
                except TypeError:
                    progress(f'\r[{bar}] {overall_percent*100:5.1f}% | C{component_index+1}/{len(graph.components)}: {progress_text}'.ljust(80), end='')
            if not live_callback: return
            positions[component] = sub_positions
            for local, global_id in enumerate(edge_ids):
                if sub_routes is not None and local < len(sub_routes): routes[global_id] = sub_routes[local]
            nodes = []
            for i, node in enumerate(graph.nodes):
                item = deepcopy(node); item['schematic'] = positions[i].tolist()
                item['marker'] = 'station'
                item['label'] = {'offset': [0,0], 'anchor': 'center', 'rotation_deg': 0}
                nodes.append(item)
            edges = []
            for i, edge in enumerate(graph.edges):
                item = deepcopy(edge)
                item['lines'] = edge['lines']; item['line_offsets'] = {line_id: 0 for line_id in edge['lines']}
                if routes[i] is not None: item['path'] = routes[i].tolist()
                else:
                    u, v = graph.endpoints[i]
                    item['path'] = [positions[u].tolist(), positions[v].tolist()]
                edges.append(item)
            clouds = [positions] + [r for r in routes if r is not None]
            cloud = np.concatenate(clouds) if clouds else np.zeros((1,2))
            bounds = [*cloud.min(axis=0), *cloud.max(axis=0)]
            overall_percent = (component_index + component_percent) / len(graph.components)
            meta = {'version':'0.1', 'bounds':bounds, 'feasible':False, 'progress': progress_text, 'percent': overall_percent}
            live_callback({'meta':meta, 'nodes':nodes, 'edges':edges, 'lines':graph.lines, 'render':deepcopy(config['render']), 'label_style':deepcopy(config['labels']), 'web':deepcopy(config['web'])})
        return callback

    # --- [PHASE 1: SPACE WARPING] ---
    from .layout.space_warp import apply_space_warp
    anchor = apply_space_warp(anchor, config)
    positions = anchor.copy()
    
    component_label_boxes = [[] for _ in graph.components]
    for number,component in enumerate(graph.components):
        node_ids={graph.nodes[i]['id'] for i in component}
        edge_ids=[i for i,e in enumerate(graph.edges) if e['source'] in node_ids]
        
        comp_callback = make_component_callback(component, edge_ids, number)
        comp_callback(positions[component], None, "Initializing component...", 0.0)

        subdata={'nodes':[deepcopy(graph.nodes[i]) for i in component], 'edges':[deepcopy(graph.edges[i]) for i in edge_ids],'lines':graph.lines}
        subgraph=build_graph(subdata,config)
        subgraph.geo=graph.geo[component]; subgraph.origin=graph.origin
        subgraph.topology_reference=graph.topology_reference[component]
        
        # --- [PHASE 2: MACRO LAYOUT (SKELETON)] ---
        from .layout.skeleton import skeleton_layout
        def skeleton_cb(p, r, text, pct):
            comp_callback(p, r, text, pct)
            
        # Run our new geometric skeleton layout
        sublayout = skeleton_layout(subgraph, positions[component], anchor[component], targets[edge_ids], config, callback=skeleton_cb)
        
        # --- [PHASE 3: MICRO REFINEMENT] ---
        from .layout.refine_micro import optimize_micro
        # --- [PHASE 4: STRAIGHTEN BRANCHES (Run BEFORE Micro-refinement!)] ---
        from .layout.straighten_branches import apply_straightening
        
        if False:
            comp_callback(sublayout.positions, sublayout.routes, "Straightening branches...", 0.35)
            sub_p, sub_r = apply_straightening(subgraph, sublayout.positions, sublayout.routes, config)
            sublayout.positions = sub_p
            sublayout.routes = sub_r

            # --- [PHASE 3: RESOLVE OVERLAPS & MICRO-REFINE] ---
            def micro_cb(p, r, text, pct):
                comp_callback(p, r, text, pct)
            sublayout = optimize_micro(subgraph, sublayout.positions, sublayout.routes, anchor[component], targets[edge_ids], config, callback=micro_cb)
        
        positions[component] = sublayout.positions
        
        # Since we skip label placement for now, just use empty boxes
        component_label_boxes.append([])
        for local,global_id in enumerate(edge_ids): 
            routes[global_id] = sublayout.routes[local]
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
    if progress: progress() # Print a newline at the end of progress bar
    return {'meta':meta,'transform':transform,'nodes':nodes,'edges':edges,'lines':graph.lines,'metrics':metrics,'render':deepcopy(config['render']),'label_style':deepcopy(config['labels']),'web':deepcopy(config['web'])}
