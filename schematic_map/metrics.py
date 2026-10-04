import math
import numpy as np
from .layout.energy.base import configured_terms


def measure(layout,label_overlaps=0):
    facts=layout.facts(); angles=facts['angles']; bends=facts['bends']
    mean=lambda values: float(np.mean(values)) if len(values) else 0.
    hard={name:len(reports) for name,reports in facts['hard'].items()}
    return {
        'hard_violations':int(sum(hard.values())), 'hard_violations_by_constraint':hard,
        'violation_report':facts['hard'], 'crossings':len(facts['crossings']),
        'bends_total':int(sum(bends)), 'bends_per_edge_mean':mean(bends),
        'angle_dev_mean':mean(angles), 'angle_dev_max':max(angles,default=0.),
        'edge_len_cv':mean(facts['chain_cvs']), 'min_station_distance':facts['min_distance'],
        'collinearity_dev_mean':mean(facts['collinear']), 'geo_direction_dev_mean':mean(facts['geo_deviations']),
        'geo_displacement_rms':math.sqrt(mean(np.sum(facts['displacement']**2,axis=1))),
        'circular_order_violations':hard['H7_circular_order'],'label_overlaps':label_overlaps,
        'energy_terms':{term.name:float(term.full(layout)) for term in configured_terms(layout.config)},
    }
