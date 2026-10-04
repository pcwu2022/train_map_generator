from copy import deepcopy
import math
import numpy as np
import pytest
from schematic_map import generate_layout
from schematic_map.graph.build import build_graph
from schematic_map.layout.transform import find_transform


@pytest.mark.parametrize('angle',[-25,-15,15,25])
def test_rotation_recovered(fixtures,fast_config,angle):
    data=deepcopy(fixtures['straight'])
    theta=math.radians(angle)
    for i,node in enumerate(data['nodes']):
        y=(i-2)*2; x=-math.sin(theta)*y; y=math.cos(theta)*y
        node['coordinates']=[139+x/(111.32*math.cos(math.radians(35))),35+y/110.57]
    _,transform=find_transform(build_graph(data,fast_config),fast_config)
    assert (transform['rotation_deg']+angle+22.5)%45-22.5==pytest.approx(0,abs=1)


def test_geographic_scale_invariance(fixtures,fast_config):
    data=deepcopy(fixtures['junction']);center=np.mean([n['coordinates'] for n in data['nodes']],axis=0)
    # Centering at the same latitude preserves the local projection scale.
    scaled=deepcopy(data)
    for node in scaled['nodes']:node['coordinates']=(center+3*(np.array(node['coordinates'])-center)).tolist()
    a=generate_layout(data,fast_config); b=generate_layout(scaled,fast_config)
    assert [n['schematic'] for n in a['nodes']]==[n['schematic'] for n in b['nodes']]
    assert [e['path'] for e in a['edges']]==[e['path'] for e in b['edges']]


@pytest.mark.parametrize('seed',range(4))
def test_random_planar_stars(seed,fixtures,fast_config):
    rng=np.random.default_rng(seed);data=deepcopy(fixtures['junction']); fast_config['init']['mode']='hint'
    rotation=int(rng.integers(8))*math.pi/4
    matrix=np.array([[math.cos(rotation),-math.sin(rotation)],[math.sin(rotation),math.cos(rotation)]])
    for node in data['nodes']:
        point=(np.array(node['schematic']) @ matrix.T)*float(rng.integers(2,5))
        node['schematic']=np.round(point,8).tolist()
        node['coordinates']=[139+point[0]/(111.32*math.cos(math.radians(35))),35+point[1]/110.57]
    output=generate_layout(data,fast_config)
    assert output['metrics']['hard_violations']==0
    assert output['metrics']['crossings']==0
