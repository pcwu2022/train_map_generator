"""Seeded multi-resolution annealing with incident-edge rerouting."""
from concurrent.futures import ProcessPoolExecutor
import math
import numpy as np
from .routing import Router
from .moves import propose,branches
from .energy.base import Layout,configured_terms,energy


def optimize_restart(args):
    graph,initial,anchor,targets,config,restart,initial_routes=args
    rng=np.random.default_rng(config['seed']+restart)
    router=Router(graph,targets,anchor,config); terms=configured_terms(config)
    current=Layout(graph,initial.copy(),router.route_all(initial) if initial_routes is None else [path.copy() for path in initial_routes],anchor,targets,config)
    cost=energy(current,terms); best,best_cost=current,cost
    def rank(state,value):
        if not config['anneal']['feasibility_priority']:return (value,)
        facts=state.facts()
        from .energy.soft import line_statistics
        zigzags=line_statistics(state)['zigzag_count'] if config['anneal']['zigzag_priority'] else 0
        return (sum(len(reports) for reports in facts['hard'].values()),len(facts['crossings']),zigzags,value)
    best_rank=rank(best,best_cost)
    branch_list=branches(graph)
    def trial(state,pitch):
        points,changed=propose(graph,state.positions,rng,pitch,config,branch_list)
        if not changed: return None
        affected={edge for node in changed for _,edge in graph.adjacency[node]}
        routes=router.route_all(points,previous=state.routes,affected=affected)
        proposed=Layout(graph,points,routes,anchor,targets,config,previous=state,changed=tuple(changed))
        # Terms with specialized deltas use cached local facts; others fall back to full scoring.
        delta=sum(term.weight*term.delta(state,proposed) for term in terms)
        return proposed,delta
    uphill=[]
    for _ in range(config['anneal']['calibration_moves']):
        candidate=trial(current,config['grid']['pitch_coarse'])
        if candidate and candidate[1]>0: uphill.append(candidate[1])
    temperature=float(np.median(uphill))/-math.log(config['anneal']['uphill_acceptance']) if uphill else 1.
    attempts=0
    limit=config['anneal']['max_moves']
    for pitch in (config['grid']['pitch_coarse'],config['grid']['pitch_fine']):
        stale=0
        for _ in range(config['anneal']['max_sweeps']):
            improved=False
            for _ in range(max(1,len(graph.nodes))):
                if limit is not None and attempts>=limit: break
                attempts+=1
                candidate=trial(current,pitch)
                if candidate is None: continue
                proposed,delta=candidate
                if delta<=0 or rng.random()<math.exp(-min(delta/max(temperature,1e-12),700)):
                    current=proposed; cost+=delta
                    candidate_rank=rank(current,cost)
                    if candidate_rank<best_rank: best,best_cost,best_rank=current,cost,candidate_rank; improved=True
            temperature*=config['anneal']['cooling']
            stale=0 if improved else stale+1
            if stale>=config['anneal']['patience'] or (limit is not None and attempts>=limit): break
        current,cost=best,best_cost
    for _ in range(config['anneal']['greedy_sweeps']*max(1,len(graph.nodes))):
        if limit is not None and attempts>=limit: break
        attempts+=1
        candidate=trial(current,config['grid']['pitch_fine'])
        if candidate and candidate[1]<-1e-8 and rank(candidate[0],cost+candidate[1])<rank(current,cost):
            current=candidate[0]; cost+=candidate[1]
    # Deterministic chain descent complements random proposals: every chain gets
    # a chance to become straight and evenly spaced before the restart finishes.
    for _ in range(config['anneal']['greedy_sweeps']):
        improved=False
        for chain,_ in graph.chains:
            if limit is not None and attempts>=limit: break
            attempts+=1
            ids=chain[1:-1]
            if not ids or chain[0]==chain[-1]: continue
            points=current.positions.copy()
            pitch=config['grid']['pitch_fine']
            points[ids]=np.round(np.linspace(points[chain[0]],points[chain[-1]],len(chain))[1:-1]/pitch)*pitch
            changed=np.flatnonzero(np.any(abs(points-current.positions)>1e-8,axis=1)).tolist()
            if not changed: continue
            affected={edge for node in changed for _,edge in graph.adjacency[node]}
            routes=router.route_all(points,previous=current.routes,affected=affected)
            candidate=Layout(graph,points,routes,anchor,targets,config,previous=current,changed=tuple(changed))
            candidate_cost=energy(candidate,terms)
            if candidate_cost<cost-1e-8 and rank(candidate,candidate_cost)<rank(current,cost):current,cost=candidate,candidate_cost;improved=True
        if not improved: break
    return current.positions,current.routes,float(cost)


def optimize(graph,initial,anchor,targets,config,initial_routes=None,alternate=None):
    args=[]
    for i in range(config['anneal']['restarts']):
        other=alternate is not None and config['anneal']['multistart'] and i%2==1
        args.append((graph,alternate if other else initial,anchor,targets,config,i,None if other else initial_routes))
    if config['anneal']['workers']>1 and len(args)>1:
        with ProcessPoolExecutor(max_workers=config['anneal']['workers']) as pool: results=list(pool.map(optimize_restart,args))
    else: results=[optimize_restart(arg) for arg in args]
    # map order provides deterministic tie-breaking independent of scheduling.
    def result_rank(result):
        if not config['anneal']['feasibility_priority']:return (result[2],)
        state=Layout(graph,result[0],result[1],anchor,targets,config);facts=state.facts()
        from .energy.soft import line_statistics
        zigzags=line_statistics(state)['zigzag_count'] if config['anneal']['zigzag_priority'] else 0
        return (sum(len(reports) for reports in facts['hard'].values()),len(facts['crossings']),zigzags,result[2])
    points,routes,_=min(results,key=result_rank)
    return Layout(graph,points,routes,anchor,targets,config)
