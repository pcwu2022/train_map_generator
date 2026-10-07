import numpy as np
import pytest
from schematic_map.config import load_config
from schematic_map.graph.build import build_graph
from schematic_map.layout.lp import lp_layout
from schematic_map.pipeline import generate_layout


@pytest.mark.parametrize('name', ['straight', 'turn', 'junction', 'loop', 'grid'])
def test_lp_routes_are_octilinear_and_anchored(fixtures, name):
    config = load_config()
    graph = build_graph(fixtures[name], config)
    positions, routes = lp_layout(graph, config)
    for (u, v), path in zip(graph.endpoints, routes):
        assert np.allclose(path[0], positions[u]) and np.allclose(path[-1], positions[v])
        for a, b in zip(path, path[1:]):
            dx, dy = np.abs(b - a)
            assert dx < 1e-6 or dy < 1e-6 or abs(dx - dy) < 1e-6


def test_lp_spaces_chain_stations_evenly(fixtures):
    layout = generate_layout(fixtures['straight'], load_config())
    lengths = [edge['length'] for edge in layout['edges']]
    assert max(lengths) - min(lengths) < 1e-6 and min(lengths) >= 1 - 1e-6
    assert layout['metrics']['crossings'] == 0


def test_lp_is_deterministic(fixtures):
    first = generate_layout(fixtures['junction'], load_config())
    second = generate_layout(fixtures['junction'], load_config())
    assert first == second
