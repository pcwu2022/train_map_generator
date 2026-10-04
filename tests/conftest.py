import json
from pathlib import Path
import pytest
from schematic_map.config import load_config


@pytest.fixture
def fast_config():
    return load_config(overrides={'anneal':{'restarts':1,'max_sweeps':2,'calibration_moves':2,'greedy_sweeps':1,'patience':2},'refine':{'sweeps':2}})


@pytest.fixture
def fixtures():
    return {p.stem:json.loads(p.read_text()) for p in (Path(__file__).parent/'fixtures').glob('*.json')}
