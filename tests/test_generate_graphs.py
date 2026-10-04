from copy import deepcopy
import pytest
from generate_graphs import build_graph


def input_data():
    geo={'stations':{'a':[139,35],'b':[139,35.01]}}
    topology={'segments':[{'id':'line1','name':'First','stations':[{'id':'a','name':'A','km':0},{'id':'b','name':'B','km':1.62}]}]}
    return geo,topology


def test_decreasing_kilometre_markers():
    geo,topology=input_data()
    topology['segments'][0]['stations'][0]['km']=3.24
    assert build_graph(geo,topology)['edges'][0]['distance']==1.62


def test_shared_track_tolerance_is_explicit():
    geo,topology=input_data()
    segment=deepcopy(topology['segments'][0]);segment.update(id='line2',name='Second')
    segment['stations'][1]['km']=1.6;topology['segments'].append(segment)
    with pytest.raises(ValueError,match='Conflicting distances'):build_graph(geo,topology)
    with pytest.warns(UserWarning,match='retaining 1.62'):
        graph=build_graph(geo,topology,distance_tolerance_km=.02)
    assert graph['edges'][0]['distance']==1.62
    assert graph['edges'][0]['lines']==['line1','line2']
    with pytest.raises(ValueError,match='Conflicting distances'):
        build_graph(geo,topology,distance_tolerance_km=.01)


@pytest.mark.parametrize('tolerance',[-1,float('nan'),float('inf')])
def test_invalid_tolerance(tolerance):
    with pytest.raises(ValueError,match='finite and nonnegative'):
        build_graph(*input_data(),distance_tolerance_km=tolerance)
