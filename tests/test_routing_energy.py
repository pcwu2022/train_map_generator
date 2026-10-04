from copy import deepcopy
import numpy as np
import pytest
from schematic_map.graph.build import build_graph
from schematic_map.layout.transform import target_lengths
from schematic_map.layout.routing import Router
from schematic_map.layout.geometry import path_length, direction_deviation, angle_difference, bearing, intersection_pairs
from schematic_map.layout.energy.base import Layout,configured_terms


def make_layout(fixtures,config,name='straight'):
    graph=build_graph(fixtures[name],config)
    points=np.array([n['schematic'] for n in graph.nodes],dtype=float)
    routes=[points[[u,v]] for u,v in graph.endpoints]
    return Layout(graph,points,routes,points.copy(),target_lengths(graph,config),config)


@pytest.mark.parametrize('delta',[(0,3),(3,0),(2,2),(3,2),(3,1),(-1,3),(-2,-3)])
def test_candidate_geometry(delta,fixtures,fast_config):
    layout=make_layout(fixtures,fast_config); router=Router(layout.graph,layout.targets,layout.anchor,fast_config)
    candidates=router.candidates(np.array(delta,dtype=float),full=True)
    assert candidates
    for path in candidates:
        assert np.allclose(path[0],[0,0]) and np.allclose(path[-1],delta)
        assert 2<=len(path)<=4
        vectors=np.diff(path,axis=0)
        assert all(np.linalg.norm(v)>=fast_config['routing']['min_segment']-1e-8 for v in vectors)
        assert all(direction_deviation(v,15)==0 for v in vectors)
        assert all(min(abs(angle_difference(bearing(a),bearing(b))-45),abs(angle_difference(bearing(a),bearing(b))-90))<1e-8 for a,b in zip(vectors,vectors[1:]))


def test_diagonal_tolerance():
    assert direction_deviation(np.array([2,1.5]),15)==0
    assert direction_deviation(np.array([2,0]),15)==0
    assert direction_deviation(np.array([2,.1]),15)>0


def test_crossing_excludes_endpoints():
    routes=[np.array([[0,0],[2,2]]),np.array([[0,2],[2,0]]),np.array([[2,2],[3,2]])]
    assert intersection_pairs(routes)=={(0,1)}


def test_every_term_hand_computed(fixtures,fast_config):
    layout=make_layout(fixtures,fast_config)
    terms={term.name:term for term in configured_terms(fast_config)}
    # Four vertical edges of length 2, no bends, exact reference positions.
    for name in terms:
        if name not in ('S2_edge_length',): assert terms[name].full(layout)==pytest.approx(0)
    target=fast_config['terms']['S2_edge_length']['a']+fast_config['terms']['S2_edge_length']['b']*np.log(2)
    assert terms['S2_edge_length'].full(layout)==pytest.approx(4*((2-target)/target)**2)
    assert terms['S2_edge_length'].delta(layout,layout)==0


@pytest.mark.parametrize('name', ['H1_min_spacing','H2_bend_limit','H3_bend_angle','H4_segment_direction','H5_node_clearance','H6_ports','H7_circular_order','S1_crossings','S3_angle','S4_bends','S5_collinearity','S6_direction','S7_displacement','S8_chain_spacing','S9_compactness'])
def test_term_detects_violation(name,fixtures,fast_config):
    layout=make_layout(fixtures,fast_config,'grid' if name in ('H6_ports','H7_circular_order') else 'straight')
    if name=='H1_min_spacing': layout.positions[1]=layout.positions[0]+[0,.5]
    elif name=='H2_bend_limit': layout.routes[0]=np.array([[0,0],[1,0],[2,1],[2,2],[0,2]])
    elif name=='H3_bend_angle': layout.routes[0]=np.array([[0,0],[1,0],[0,2]])
    elif name in ('H4_segment_direction','S3_angle'): layout.routes[0]=np.array([[0,0],[3,.1]])
    elif name=='H5_node_clearance': layout.routes[0]=np.array([[0,0],[0,5]])
    elif name=='H6_ports': layout.routes[0]=np.array([[0,0],[2,0]])
    elif name=='H7_circular_order': layout.routes[0],layout.routes[1]=layout.routes[1],layout.routes[0]
    elif name=='S1_crossings': layout.routes[0]=np.array([[0,0],[2,2]]);layout.routes[1]=np.array([[0,2],[2,0]])
    elif name=='S4_bends': layout.routes[0]=np.array([[0,0],[1,1],[1,2]])
    elif name=='S5_collinearity': layout.routes[0]=np.array([[0,0],[2,2]])
    elif name=='S6_direction': layout.positions[1]=layout.positions[0]+[2,0]
    elif name=='S7_displacement': layout.positions[1]+=[2,0]
    elif name=='S8_chain_spacing': layout.routes[0]=np.array([[0,0],[0,3]])
    elif name=='S9_compactness': layout.positions[1]+=[2,0]
    terms={term.name:term for term in configured_terms(fast_config)}
    value=terms[name].full(layout)
    assert value>0
    expected={
        'H1_min_spacing':.5, 'H2_bend_limit':1, 'H3_bend_angle':1,
        'H4_segment_direction':1, 'H5_node_clearance':1, 'H6_ports':1,
        'H7_circular_order':1, 'S1_crossings':1, 'S4_bends':1,
        'S5_collinearity':1, 'S7_displacement':.64,
        'S8_chain_spacing':1/27, 'S9_compactness':16,
        'S3_angle':(30-np.degrees(np.arctan(1/30)))**2,
        'S6_direction':67.5**2+(np.degrees(np.arctan(.5))-22.5)**2,
    }
    assert value==pytest.approx(expected[name])


def test_incremental_facts_match_full(fixtures,fast_config):
    from schematic_map.layout.anneal import optimize
    from schematic_map.layout.spatial import SpatialGrid
    layout=make_layout(fixtures,fast_config,'loop')
    router=Router(layout.graph,layout.targets,layout.anchor,fast_config)
    layout.routes=router.route_all(layout.positions)
    points=layout.positions.copy();points[1]+=[.25,.5]
    affected={e for _,e in layout.graph.adjacency[1]}
    routes=router.route_all(points,previous=layout.routes,affected=affected)
    incremental=Layout(layout.graph,points,routes,layout.anchor,layout.targets,fast_config,previous=layout,changed=(1,))
    full=Layout(layout.graph,points,routes,layout.anchor,layout.targets,fast_config)
    for term in configured_terms(fast_config):
        assert term.full(incremental)==pytest.approx(term.full(full)),term.name
        assert term.delta(layout,incremental)==pytest.approx(term.delta(layout,full)),term.name
    assert incremental.facts()['crossings']==full.facts()['crossings']
    grid=SpatialGrid(2);grid.put('station',[0,0,1,1]);assert grid.query([.5,.5,3,3])==['station']
    grid.put('station',[10,10,11,11]);assert grid.query([0,0,1,1])==[]


def test_crossing_blocks_preserve_results():
    routes=[np.array([[0,0],[2,2]]),np.array([[0,2],[2,0]]),np.array([[2,2],[3,2]])]
    assert intersection_pairs(routes,block_size=1)==intersection_pairs(routes,block_size=256)
