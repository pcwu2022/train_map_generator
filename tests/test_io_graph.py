from copy import deepcopy
import pytest
from schematic_map.io.validate import validate_graph
from schematic_map.graph.build import build_graph
from schematic_map.geo.projection import haversine


@pytest.mark.parametrize('mutation,match',[
    (lambda g:g['nodes'].append(g['nodes'][0]),'duplicate node'),
    (lambda g:g['edges'].append(dict(g['edges'][0],source='missing')),'unknown endpoint'),
    (lambda g:g['edges'].append(dict(g['edges'][0],source='1',target='0')),'Duplicate undirected'),
    (lambda g:g['edges'][0].update(target='0'),'self loop'),
    (lambda g:g['edges'][0].update(lines=['missing']),'known IDs'),
    (lambda g:g['nodes'][0].update(coordinates=[181,35]),'invalid longitude'),
    (lambda g:g['edges'][0].update(distance=-1),'nonnegative'),
    (lambda g:g['lines'].append(g['lines'][0]),'duplicate line')])
def test_validation(fixtures,mutation,match):
    graph=deepcopy(fixtures['straight']); mutation(graph)
    with pytest.raises(ValueError,match=match): validate_graph(graph)


def test_duplicate_coordinate_nudge(fixtures,fast_config):
    data=deepcopy(fixtures['straight']); data['nodes'][1]['coordinates']=data['nodes'][0]['coordinates']
    with pytest.warns(UserWarning,match='identical'): validate_graph(data)
    graph=build_graph(data,fast_config)
    assert graph.geo[0].tolist()!=graph.geo[1].tolist()
    assert graph.nodes[0]['coordinates']==graph.nodes[1]['coordinates']


def test_derived_fields_and_chains(fixtures,fast_config):
    graph=build_graph(fixtures['bundle'],fast_config)
    assert graph.nodes[1]['lines']==['a','b']
    assert graph.nodes[1]['degree']==2
    assert graph.nodes[1]['is_interchange']
    assert graph.nodes[2]['kind']=='junction'
    edges=[e for _,chain in graph.chains for e in chain]
    assert sorted(edges)==list(range(len(graph.edges)))
    loop=build_graph(fixtures['loop'],fast_config)
    assert len({e for _,chain in loop.chains for e in chain})==len(loop.edges)


def test_missing_distance(fixtures,fast_config):
    data=deepcopy(fixtures['straight']); del data['edges'][0]['distance']
    graph=build_graph(data,fast_config)
    assert graph.edges[0]['distance']==pytest.approx(haversine(data['nodes'][0]['coordinates'],data['nodes'][1]['coordinates']))
    assert haversine([0,0],[0,1])==pytest.approx(111.19508,rel=1e-6)


def test_too_many_ports(fixtures):
    data=deepcopy(fixtures['straight']); data['edges']=[]
    for i in range(1,10):
        if i>=len(data['nodes']): data['nodes'].append(dict(data['nodes'][0],id=str(i),coordinates=[139+i*.01,35]))
        data['edges'].append({'source':'0','target':str(i),'lines':['a']})
    with pytest.raises(ValueError,match='8 ports'):validate_graph(data)


@pytest.mark.parametrize('overrides',[
    {'seed':-1},{'anneal':{'restarts':0}},{'grid':{'d_min':0}},
    {'terms':{'S1_crossings':{'weight':-1}}},{'transform':{'aspect_range':[0,1]}},
    {'init':{'mode':'unknown'}},{'transform':{'optimize_transform':True}}])
def test_invalid_configuration(overrides):
    from schematic_map.config import load_config
    with pytest.raises(ValueError):load_config(overrides=overrides)
