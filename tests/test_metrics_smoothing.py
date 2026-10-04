import numpy as np
import pytest
from schematic_map.metrics import measure,spearman,average_ranks
from test_line_geometry import layout_for


def test_rank_correlation_hand_computed_and_ties():
    assert spearman([1,2,3],[1,3,2])==pytest.approx(.5)
    assert spearman([1,2,3],[3,2,1])==pytest.approx(-1)
    assert np.array_equal(average_ranks([3,1,1,4]),[3,1.5,1.5,4])
    assert spearman([1,1,1],[1,2,3]) is None
    assert spearman([1],[1]) is None


def test_smoothing_metrics_hand_computed():
    layout=layout_for([(0,0),(1,0),(2,0),(2,1),(3,1)])
    result=measure(layout)
    assert result['turns_per_line']=={'a':2}
    assert result['zigzag_count']==1
    assert result['mean_straight_run']==pytest.approx(4/3)
    assert result['long_run_fraction_per_line']=={'a':.5}
    assert result['key_node_spearman']==pytest.approx({'x':1.,'y':1.})
    assert result['primary_axis_angle_error_deg'] is not None


def test_vertical_primary_axis_and_unpacked_reference():
    layout=layout_for([(0,0),(0,1),(0,2)])
    result=measure(layout)
    assert result['primary_axis_angle_error_deg']==pytest.approx(0)
    assert result['key_node_spearman']['x'] is None
    assert result['key_node_spearman']['y']==pytest.approx(1)
    layout.graph.topology_reference=layout.anchor.copy()
    layout.positions=-layout.positions
    assert measure(layout)['key_node_spearman']['y']==pytest.approx(-1)


def test_new_metric_schema_bounds(fixtures,fast_config):
    from schematic_map import generate_layout
    from schematic_map.io.export import validate_layout
    result=generate_layout(fixtures['straight'],fast_config)
    validate_layout(result)
    result['metrics']['zigzag_count']=-1
    from jsonschema import ValidationError
    with pytest.raises(ValidationError):validate_layout(result)
