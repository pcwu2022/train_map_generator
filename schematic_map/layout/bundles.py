"""Order bundled lines by the side on which their continuations depart."""
from itertools import permutations
from .geometry import cross, tangent, angle_difference, bearing


def order_bundles(graph,routes,config):
    orders,offsets=[],[]
    for edge,(u,v) in enumerate(graph.endpoints):
        ids=sorted(graph.edges[edge]['lines'])
        desired=[]
        for node,source in ((u,True),(v,False)):
            forward=tangent(routes[edge],source)
            ranks={}
            for line in ids:
                turns=[]
                for _,other in graph.adjacency[node]:
                    if other!=edge and line in graph.edges[other]['lines']:
                        outgoing=tangent(routes[other],graph.endpoints[other,0]==node)
                        turns.append(float(cross(forward,outgoing))*(1 if source else -1))
                ranks[line]=sum(turns)/len(turns) if turns else 0
            # First line is leftmost; positive offsets point to the left of source -> target.
            desired.append(sorted(ids,key=lambda line:(-ranks[line],line)))
        continuations=[]
        for node,source in ((u,True),(v,False)):
            for _,other in graph.adjacency[node]:
                if other>=edge or len(orders[other])<2: continue
                common=set(ids)&set(orders[other])
                if len(common)<2: continue
                other_source=graph.endpoints[other,0]==node
                turn=angle_difference(bearing(tangent(routes[edge],source)),bearing(tangent(routes[other],other_source)))
                if turn<135: continue
                expected=[line for line in orders[other] if line in common]
                if other_source: expected.reverse()  # Opposing outward tangents invert sides.
                if not source: expected.reverse()
                continuations.append(expected)
        def cost(order):
            rank={line:i for i,line in enumerate(order)}
            local=sum(rank[a]>rank[b] for expected in desired for i,a in enumerate(expected) for b in expected[i+1:])
            continuity=sum(rank[a]>rank[b] for expected in continuations for i,a in enumerate(expected) for b in expected[i+1:])
            return continuity,local
        chosen=min(permutations(ids),key=lambda order:(cost(order),order)) if len(ids)<=6 else tuple(desired[0])
        orders.append(list(chosen))
        spacing=(config['render']['line_width']+config['render']['bundle_gap'])/config['render']['line_width']
        offsets.append({line:((len(chosen)-1)/2-i)*spacing for i,line in enumerate(chosen)})
    return orders,offsets
