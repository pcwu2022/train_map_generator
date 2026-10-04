import numpy as np
import pytest
from schematic_map.layout.primary import primary_line,primary_axis_error
from schematic_map.layout.transform import find_transform
from test_line_geometry import layout_for


def test_primary_axis_recovers_large_tilt():
    theta=np.radians(40);points=[(-np.sin(theta)*i,np.cos(theta)*i) for i in range(5)]
    layout=layout_for(points);layout.graph.geo=layout.positions.copy();layout.graph.lines[0]['primary']=True
    anchor,transform=find_transform(layout.graph,layout.config)
    assert transform['rotation_deg']==pytest.approx(-40,abs=1)
    _,error=primary_axis_error(layout.graph,anchor,[anchor[[u,v]] for u,v in layout.graph.endpoints],layout.config)
    assert error<5


def test_primary_selection_and_isotropic_axis():
    layout=layout_for([(0,0),(1,0),(1,1),(0,1)],closed=True)
    assert primary_line(layout.graph)['id']=='a'
    assert primary_axis_error(layout.graph,layout.positions,layout.routes,layout.config)[1] is None


def test_refinement_targets_zigzag_after_feasibility():
    from schematic_map.layout.refine import refine
    from schematic_map.metrics import measure
    layout=layout_for([(0,0),(2,0),(2,1),(4,1)])
    layout.config['refine'].update(sweeps=2,max_trials=64)
    before=measure(layout)
    after=measure(refine(layout))
    assert before['hard_violations']==0
    assert after['hard_violations']==0
    assert after['crossings']<=before['crossings']
    assert after['zigzag_count']==0
