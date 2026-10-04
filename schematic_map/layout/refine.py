import numpy as np
from .routing import Router
from .geometry import DIRECTIONS,EPS
from .energy.base import Layout, energy, configured_terms


def refine(layout):
    graph,config=layout.graph,layout.config
    router=Router(graph,layout.targets,layout.anchor,config)
    terms=configured_terms(config)
    def rank(state):
        facts=state.facts();value=energy(state,terms)
        if not config['anneal']['feasibility_priority']:return (value,)
        from .energy.soft import line_statistics
        zigzags=line_statistics(state)['zigzag_count'] if config['anneal']['zigzag_priority'] else 0
        return (sum(len(reports) for reports in facts['hard'].values()),len(facts['crossings']),zigzags,value)
    routes=router.route_all(layout.positions,full=True,previous=layout.routes)
    candidate=Layout(graph,layout.positions,routes,layout.anchor,layout.targets,config)
    if rank(candidate)<rank(layout): layout=candidate
    cost=energy(layout,terms)
    attempts=0
    limit=config['refine']['max_trials']
    for _ in range(config['refine']['sweeps']):
        facts=layout.facts(); nodes=set()
        for reports in facts['hard'].values():
            for report in reports:
                if 'edge' in report: nodes.update(graph.endpoints[report['edge']])
                if 'edges' in report:
                    for edge in report['edges']: nodes.update(graph.endpoints[edge])
                ids=report.get('nodes',[])+([report['node']] if 'node' in report else [])
                nodes.update(i for i,n in enumerate(graph.nodes) if n['id'] in ids)
        for a,b in facts['crossings']: nodes.update(graph.endpoints[a]); nodes.update(graph.endpoints[b])
        smooth_nodes=set()
        if config['refine']['smoothness']:
            from .line_geometry import line_walks,walk_geometry
            for walk in line_walks(graph):
                geometry=walk_geometry(graph,layout.routes,walk)
                if geometry is None:continue
                turns=[item for item in geometry['turns'] if abs(item[0])+EPS>=config['line_geometry']['turn_threshold_deg']]
                arcs=np.concatenate(([0.],np.cumsum([facts['lengths'][edge] for edge in walk[2]])))
                for a,b in zip(turns,turns[1:]):
                    if a[0]*b[0]<0 and b[1]-a[1]<config['terms']['S12_zigzag']['zigzag_window']:
                        indices=np.argsort(abs(arcs-(a[1]+b[1])/2),kind='stable')[:config['refine']['smooth_neighbors']]
                        smooth_nodes.update(walk[1][i] for i in indices)
            nodes.update(smooth_nodes)
        if not nodes: break
        improved=False
        # Hard failures get the budget before purely cosmetic crossings.
        hard_nodes=set()
        by_id={node['id']:i for i,node in enumerate(graph.nodes)}
        for reports in facts['hard'].values():
            for report in reports:
                if 'edge' in report:hard_nodes.update(graph.endpoints[report['edge']])
                for edge in report.get('edges',[]):hard_nodes.update(graph.endpoints[edge])
                hard_nodes.update(by_id[node] for node in report.get('nodes',[]))
                if 'node' in report:hard_nodes.add(by_id[report['node']])
        for node in sorted(nodes,key=lambda node:(node not in hard_nodes,node not in smooth_nodes,node)):
            affected=sorted({e for _,e in graph.adjacency[node]})
            if config['refine']['star_orders'] and node in hard_nodes and len(affected)>1:
                for shift in range(len(affected)):
                    if limit is not None and attempts>=limit:return layout
                    attempts+=1;order=affected[shift:]+affected[:shift]
                    rerouted=router.route_all(layout.positions,True,layout.routes,affected,order)
                    candidate=Layout(graph,layout.positions,rerouted,layout.anchor,layout.targets,config)
                    if rank(candidate)<rank(layout):layout=candidate;cost=energy(layout,terms);improved=True
            for scale in config['refine']['step_scales']:
                for delta in DIRECTIONS*config['grid']['pitch_fine']*scale:
                    if limit is not None and attempts>=limit:return layout
                    attempts+=1
                    points=layout.positions.copy();points[node]+=np.round(delta/config['grid']['pitch_fine'])*config['grid']['pitch_fine']
                    candidate=Layout(graph,points,router.route_all(points,True,layout.routes,affected),layout.anchor,layout.targets,config,previous=layout,changed=(node,))
                    candidate_cost=energy(candidate,terms)
                    if rank(candidate)<rank(layout):layout,cost=candidate,candidate_cost;improved=True
        if not improved: break
    return layout
