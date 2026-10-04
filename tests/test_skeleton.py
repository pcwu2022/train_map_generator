import numpy as np
from schematic_map import generate_layout
from schematic_map.io.export import validate_layout
from schematic_map.layout.skeleton import slice_polyline
from schematic_map.layout.geometry import path_length


def test_chain_stations_are_even_and_no_zigzag(fixtures,fast_config):
    config=fast_config.copy();config['init']=dict(config['init'],mode='skeleton');config['anneal']=dict(config['anneal'],multistart=False)
    result=generate_layout(fixtures['straight'],config);validate_layout(result)
    points=np.array([node['schematic'] for node in result['nodes']])
    distances=np.linalg.norm(np.diff(points,axis=0),axis=1)
    assert np.std(distances)<1e-8
    assert result['metrics']['hard_violations']==0
    assert result['metrics']['bends_total']==0


def test_arc_slicing_preserves_bends():
    path=np.array([[0.,0.],[2,0],[2,2],[4,2]])
    piece=slice_polyline(path,1,5)
    assert np.allclose(piece,[[1,0],[2,0],[2,2],[3,2]])
    assert path_length(piece)==4


def test_closed_chain_expansion(fixtures,fast_config):
    data=dict(fixtures['loop']);data['nodes']=data['nodes'][:8];data['edges']=data['edges'][:8]
    result=generate_layout(data,fast_config);validate_layout(result)
    assert result['metrics']['hard_violations']==0
