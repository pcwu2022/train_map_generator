"""Configuration is merged recursively; every tunable default lives in YAML."""
from copy import deepcopy
import math
from pathlib import Path
import yaml


def merge(base, update):
    result = deepcopy(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_config(path=None, overrides=None):
    config = yaml.safe_load((Path(__file__).parent / 'config/default.yaml').read_text())
    if path:
        config = merge(config, yaml.safe_load(Path(path).read_text()) or {})
    config = merge(config, overrides or {})
    if config['grid']['d_min'] <= 0 or config['grid']['pitch_fine'] <= 0:
        raise ValueError('Grid spacing and pitch must be positive')
    if config['init']['mode'] not in ('geo', 'hint'):
        raise ValueError('init.mode must be geo or hint')
    if config['anneal']['restarts'] < 1:
        raise ValueError('anneal.restarts must be positive')
    if config['transform']['optimize_transform']:
        raise ValueError('Joint transform optimization is not implemented; use Stage 1 search')
    if not isinstance(config['seed'],int) or config['seed']<0:
        raise ValueError('seed must be a nonnegative integer')
    for name,term in config['terms'].items():
        weight=term.get('weight',1)
        if not isinstance(weight,(int,float)) or not math.isfinite(weight) or weight<0:
            raise ValueError(f'{name}: weights must be finite and nonnegative')
    if config['terms']['S2_edge_length']['d0_km']<=0:
        raise ValueError('S2_edge_length.d0_km must be positive')
    if not 0<config['anneal']['uphill_acceptance']<1 or not 0<config['anneal']['cooling']<=1:
        raise ValueError('Invalid annealing acceptance or cooling')
    if config['anneal']['workers']<1 or config['anneal']['max_sweeps']<0:
        raise ValueError('Annealing workers must be positive and sweeps nonnegative')
    if config['init']['anchor_weight']<=0 or config['routing']['spatial_cell_size']<=0:
        raise ValueError('Anchor weight and spatial cell size must be positive')
    if config['transform']['theta_step_deg']<=0 or config['transform']['aspect_step']<=0:
        raise ValueError('Transform search steps must be positive')
    low,high=config['transform']['aspect_range']
    if not 0<low<=high:
        raise ValueError('Invalid positive aspect range')
    if config['render']['pixels_per_unit']<=0 or config['render']['dpi']<=0 or config['render']['line_width']<=0:
        raise ValueError('Render scale, DPI and line width must be positive')
    if not isinstance(config['routing']['intersection_block_size'],int) or config['routing']['intersection_block_size']<=0:
        raise ValueError('Intersection block size must be a positive integer')
    for value in (config['anneal']['max_moves'],config['refine']['max_trials']):
        if value is not None and (not isinstance(value,int) or value<0):
            raise ValueError('Move and refinement budgets must be nonnegative integers or null')
    if not 0<config['line_geometry']['turn_threshold_deg']<=180:
        raise ValueError('Line turn threshold must be in (0, 180]')
    if config['terms']['S12_zigzag']['zigzag_window']<=0 or config['terms']['S13_min_run']['run_min']<=0:
        raise ValueError('Zigzag window and minimum run must be positive')
    if config['reference']['simplify_tolerance_km']<0 or not 0<=config['reference']['low_pass_alpha']<=1 or config['reference']['low_pass_iterations']<0:
        raise ValueError('Invalid reference smoothing parameters')
    if config['terms']['S14_relative_order']['k']<1:
        raise ValueError('Relative-order k must be positive')
    return config
