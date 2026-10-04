import numpy as np
import pytest
from schematic_map import load_config
from schematic_map.graph.build import build_graph
from schematic_map.layout.energy.base import Layout,configured_terms
from schematic_map.layout.transform import target_lengths
from schematic_map.layout.line_geometry import line_facts


def layout_for(points,closed=False):
    config=load_config()
    nodes=[{'id':str(i),'name':str(i),'coordinates':[139+x*.01,35+y*.01]} for i,(x,y) in enumerate(points)]
    pairs=[(i,i+1) for i in range(len(points)-1)]
    if closed:pairs.append((len(points)-1,0))
    data={'nodes':nodes,'edges':[{'source':str(u),'target':str(v),'distance':5,'lines':['a']} for u,v in pairs],'lines':[{'id':'a','name':'A','color':'#123456'}]}
    graph=build_graph(data,config);positions=np.array(points,dtype=float)
    return Layout(graph,positions,[positions[[u,v]] for u,v in pairs],positions.copy(),target_lengths(graph,config),config)


def test_new_terms_hand_computed():
    layout=layout_for([(0,0),(1,0),(1,1),(2,1)])
    terms={term.name:term for term in configured_terms(layout.config)}
    assert terms['S11_line_turns'].full(layout)==2
    assert terms['S12_zigzag'].full(layout)==1
    assert terms['S13_min_run'].full(layout)==pytest.approx(1/9)
    assert sum(terms[name].weight*terms[name].full(layout) for name in ['S11_line_turns','S12_zigzag','S13_min_run'])==pytest.approx(24+5/9)


def test_reverse_edges_and_loop():
    layout=layout_for([(0,0),(2,0),(2,2),(0,2)],closed=True)
    expected=line_facts(layout.graph,layout.routes,layout.config)
    assert expected['turns_per_line']=={'a':4}
    assert expected['zigzag_count']==0
    layout.graph.endpoints[1]=layout.graph.endpoints[1,::-1];layout.routes[1]=layout.routes[1][::-1]
    assert line_facts(layout.graph,layout.routes,layout.config)==expected


def test_short_terminal_runs_exempt_and_window_strict():
    layout=layout_for([(0,0),(.5,0),(.5,3),(1,3)])
    facts=line_facts(layout.graph,layout.routes,layout.config)
    assert facts['zigzag_count']==0
    terms={term.name:term for term in configured_terms(layout.config)}
    assert terms['S13_min_run'].full(layout)==0


def test_linear_station_turn_and_diagonal_preference():
    layout=layout_for([(0,0),(1,0),(1,1)])
    terms={term.name:term for term in configured_terms(layout.config)}
    assert terms['S5_collinearity'].full(layout)==2  # One decisive 90-degree turn.
    layout=layout_for([(0,0),(1,np.tan(np.radians(50)))])
    terms={term.name:term for term in configured_terms(layout.config)}
    assert terms['S3_angle'].full(layout)==pytest.approx(5/15)
    assert layout.facts()['hard']['H4_segment_direction']==[]
