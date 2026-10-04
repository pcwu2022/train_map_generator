import numpy as np
from .routing import Router
from .geometry import DIRECTIONS
from .energy.base import Layout, energy, configured_terms


def refine(layout):
    graph,config=layout.graph,layout.config
    router=Router(graph,layout.targets,layout.anchor,config)
    terms=configured_terms(config)
    routes=router.route_all(layout.positions,full=True,previous=layout.routes)
    candidate=Layout(graph,layout.positions,routes,layout.anchor,layout.targets,config)
    if energy(candidate,terms)<energy(layout,terms): layout=candidate
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
        if not nodes: break
        improved=False
        for node in sorted(nodes):
            for delta in DIRECTIONS*config['grid']['pitch_fine']:
                if limit is not None and attempts>=limit: return layout
                attempts+=1
                points=layout.positions.copy(); points[node]+=np.round(delta/config['grid']['pitch_fine'])*config['grid']['pitch_fine']
                affected={e for _,e in graph.adjacency[node]}
                candidate=Layout(graph,points,router.route_all(points,True,layout.routes,affected),layout.anchor,layout.targets,config,previous=layout,changed=(node,))
                candidate_cost=energy(candidate,terms)
                if candidate_cost<cost-1e-8: layout,cost=candidate,candidate_cost; improved=True
        if not improved: break
    return layout
