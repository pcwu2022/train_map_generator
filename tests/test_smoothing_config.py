import pytest
from schematic_map import load_config


@pytest.mark.parametrize('override',[
    {'refine':{'step_scales':[]}},
    {'refine':{'smooth_neighbors':0}},
    {'reference':{'low_pass_iterations':1.5}},
    {'terms':{'S14_relative_order':{'k':1.5}}},
    {'routing':{'min_segment':0}},
    {'anneal':{'move_weights':[-1,2,1,2,1,2]}},
])
def test_invalid_smoothing_configuration(override):
    with pytest.raises(ValueError):load_config(overrides=override)
