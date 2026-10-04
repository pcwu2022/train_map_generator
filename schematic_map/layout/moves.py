import numpy as np


def branches(graph):
    result=[]
    for junction,adjacent in enumerate(graph.adjacency):
        if len(adjacent)<3: continue
        for root,_ in adjacent:
            seen={junction}; stack=[root]; branch=[]
            while stack:
                u=stack.pop()
                if u in seen: continue
                seen.add(u); branch.append(u)
                stack.extend(v for v,_ in graph.adjacency[u] if v not in seen)
            # Only true hanging branches: a cycle cannot reconnect to the junction.
            if sum(v==junction for u in branch for v,_ in graph.adjacency[u])==1:
                result.append((junction,root,branch))
    return result


def propose(graph, positions, rng, pitch, config, branch_list):
    result=positions.copy(); n=len(result)
    if not n: return result,[]
    node=int(rng.integers(n))
    weights=config['anneal']['move_weights']+(config['anneal']['rotation_weights'] if config['anneal']['rotation_moves'] else [])
    move=int(rng.choice(len(weights),p=np.array(weights)/sum(weights)))
    shift=rng.integers(-config['anneal']['max_step'],config['anneal']['max_step']+1,size=2)*pitch
    ids=[node]
    if move in (6,7):
        angle=np.radians(config['anneal']['rotation_angle_deg']*rng.choice([-1,1]))
        rotation=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
        if move==6 and graph.chains:
            chain,_=graph.chains[int(rng.integers(len(graph.chains)))];ids=sorted(set(chain))
            center=positions[ids].mean(axis=0);result[ids]=center+(positions[ids]-center) @ rotation.T
        elif branch_list:
            junction,_,ids=branch_list[int(rng.integers(len(branch_list)))];center=positions[junction]
            result[ids]=center+(positions[ids]-center) @ rotation.T
    elif move==1 and graph.chains:
        chain,_=graph.chains[int(rng.integers(len(graph.chains)))]; ids=chain[1:-1] or [node]
        result[ids]+=shift
    elif move in (2,4) and branch_list:
        junction,root,ids=branch_list[int(rng.integers(len(branch_list)))]
        if move==2: result[ids]+=shift
        else:
            axis=positions[root]-positions[junction]; norm=np.linalg.norm(axis)
            if norm>1e-8:
                axis/=norm; relative=positions[ids]-positions[junction]
                result[ids]=positions[junction]+2*(relative @ axis)[:,None]*axis-relative
    elif move==3 and len(graph.adjacency[node])==2:
        a,b=[v for v,_ in graph.adjacency[node]]; delta=positions[b]-positions[a]
        ratio=np.clip((positions[node]-positions[a]) @ delta/max(delta @ delta,1e-8),0,1)
        result[node]=positions[a]+ratio*delta
    elif move==5 and graph.chains:
        chain,_=graph.chains[int(rng.integers(len(graph.chains)))]; ids=chain[1:-1]
        if ids: result[ids]=np.linspace(positions[chain[0]],positions[chain[-1]],len(chain))[1:-1]
    else: result[node]+=shift
    result[ids]=np.round(result[ids]/pitch)*pitch
    changed=np.flatnonzero(np.any(abs(result-positions)>1e-8,axis=1)).tolist()
    return result,changed
