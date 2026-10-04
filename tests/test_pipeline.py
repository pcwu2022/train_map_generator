from copy import deepcopy
import json
import numpy as np
import pytest
from schematic_map import generate_layout
from schematic_map.io.export import validate_layout,export_layout
from schematic_map.layout.geometry import cyclic_equal
from schematic_map.layout.labels import text_width
from schematic_map.render.svg import render_svg
from schematic_map.render.png import render_png


@pytest.mark.parametrize('name',['straight','turn','junction','bundle','grid','loop','disconnected','dense'])
def test_fixtures(name,fixtures,fast_config):
    config=deepcopy(fast_config)
    if name in ('loop','bundle','grid','turn','junction'): config['init']['mode']='hint'
    output=generate_layout(fixtures[name],config)
    validate_layout(output)
    assert output['metrics']['hard_violations']==0,output['metrics']['violation_report']
    assert output['metrics']['crossings']==0
    assert output['metrics']['label_overlaps']==0
    if name=='straight':
        assert output['metrics']['bends_total']==0
        assert output['metrics']['collinearity_dev_mean']<5
        assert output['metrics']['edge_len_cv']<.25
    if name=='bundle':
        for edge in output['edges']:
            assert sum(edge['line_offsets'].values())==pytest.approx(0)
            assert len(edge['line_offsets'])==len(edge['lines'])


def test_deterministic(fixtures,fast_config,tmp_path):
    first=generate_layout(fixtures['junction'],fast_config)
    second=generate_layout(fixtures['junction'],fast_config)
    assert first==second
    export_layout(first,tmp_path/'a.json'); export_layout(second,tmp_path/'b.json')
    assert (tmp_path/'a.json').read_bytes()==(tmp_path/'b.json').read_bytes()


def test_empty_and_isolated(fast_config):
    for nodes in ([],[{'id':'x','name':'東京','coordinates':[139,35]}]):
        output=generate_layout({'nodes':nodes,'edges':[],'lines':[]},fast_config)
        validate_layout(output)
        assert output['metrics']['hard_violations']==0


def test_hint_requires_all_nodes(fixtures,fast_config):
    data=deepcopy(fixtures['straight']); del data['nodes'][0]['schematic']; fast_config['init']['mode']='hint'
    with pytest.raises(ValueError,match='every node'): generate_layout(data,fast_config)


def test_cjk_render_and_json_only(fixtures,fast_config,tmp_path):
    layout=generate_layout(fixtures['straight'],fast_config)
    json_roundtrip=json.loads(json.dumps(layout))
    svg=render_svg(json_roundtrip)
    assert '<svg' in svg and '東京' in svg and 'station-label' in svg
    assert text_width('東京',1)==2
    path=tmp_path/'map.png'; render_png(json_roundtrip,path)
    from PIL import Image
    image=Image.open(path); assert image.width>0 and image.height>0


def test_cyclic_order():
    assert cyclic_equal([1,2,3],[2,3,1])
    assert not cyclic_equal([1,2,3],[1,3,2])


def test_parallel_restarts(fixtures,fast_config):
    fast_config['anneal']['restarts']=2
    serial=generate_layout(fixtures['junction'],fast_config)
    fast_config['anneal']['workers']=2
    parallel=generate_layout(fixtures['junction'],fast_config)
    assert serial==parallel


def test_shinkansen_fixture(fixtures,fast_config):
    config=deepcopy(fast_config)
    config['anneal'].update(max_sweeps=0,calibration_moves=0,greedy_sweeps=0)
    config['refine']['sweeps']=0
    output=generate_layout(fixtures['shinkansen'],config)
    validate_layout(output)
    assert output['metrics']['hard_violations']==0
    assert output['metrics']['crossings']==0
    assert output['metrics']['label_overlaps']==0
    from schematic_map.graph.build import build_graph
    from schematic_map.layout.transform import target_lengths
    targets=target_lengths(build_graph(fixtures['shinkansen'],config),config)
    distances=[e['distance'] for e in fixtures['shinkansen']['edges']]
    short=distances.index(3.6);long=distances.index(27.7)
    assert targets[short]<targets[long]
    assert targets[long]/targets[short]<27.7/3.6


def test_bundle_sides_survive_reversed_edges(fixtures,fast_config):
    from schematic_map.graph.build import build_graph
    from schematic_map.layout.bundles import order_bundles
    data=deepcopy(fixtures['bundle']);data['edges'][1].update(source='2',target='1')
    graph=build_graph(data,fast_config);points=np.array([n['schematic'] for n in graph.nodes],dtype=float)
    routes=[points[[u,v]] for u,v in graph.endpoints]
    _,offsets=order_bundles(graph,routes,fast_config)
    for line in ('a','b'):assert offsets[0][line]==-offsets[1][line]


def test_component_packing_includes_long_labels(fast_config):
    data={'nodes':[{'id':str(i),'name':'東京'*12,'coordinates':[139+i,35]} for i in range(2)],'edges':[],'lines':[]}
    result=generate_layout(data,fast_config)
    assert result['metrics']['label_overlaps']==0
    assert result['nodes'][1]['schematic'][0]-result['nodes'][0]['schematic'][0]>3


def test_zero_move_budget_skips_proposals(fixtures,fast_config):
    from unittest.mock import patch
    config=deepcopy(fast_config)
    config['anneal'].update(max_moves=0,calibration_moves=0)
    config['refine'].update(max_trials=0)
    with patch('schematic_map.layout.anneal.propose') as proposal:
        layout=generate_layout(fixtures['straight'],config)
    proposal.assert_not_called()
    assert layout['metrics']['hard_violations']==0
