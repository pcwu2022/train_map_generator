import math
import numpy as np
from .layout.energy.base import configured_terms
from .layout.energy.soft import line_statistics
from .layout.reference import key_nodes
from .layout.primary import primary_axis_error


def average_ranks(values):
    """One-based average ranks; stable sorting makes ties deterministic."""
    values=np.asarray(values)
    order=np.argsort(values,kind='stable');ranks=np.empty(len(values),dtype=float)
    start=0
    while start<len(values):
        end=start+1
        while end<len(values) and values[order[end]]==values[order[start]]:end+=1
        ranks[order[start:end]]=(start+1+end)/2
        start=end
    return ranks


def spearman(reference,positions):
    if len(reference)<2:return None
    a=average_ranks(reference);b=average_ranks(positions)
    a-=a.mean();b-=b.mean();denominator=np.linalg.norm(a)*np.linalg.norm(b)
    return float(np.clip(np.dot(a,b)/denominator,-1,1)) if denominator>0 else None


def key_correlations(layout):
    keys=key_nodes(layout.graph)
    # H7's reference is the transformed, unpacked geography. Smoothing fixes keys.
    reference=layout.graph.topology_reference
    if reference is None:reference=layout.anchor
    def axes(nodes):
        return {axis:spearman(reference[nodes,column],layout.positions[nodes,column])
                for column,axis in enumerate(('x','y'))}
    return axes(keys),[{'component':i,'key_nodes':len(nodes),**axes(nodes)}
                        for i,component in enumerate(layout.graph.components)
                        for nodes in [[node for node in keys if node in component]]]


def measure(layout,label_overlaps=0):
    facts=layout.facts(); angles=facts['angles']; bends=facts['bends']
    mean=lambda values: float(np.mean(values)) if len(values) else 0.
    hard={name:len(reports) for name,reports in facts['hard'].items()}
    return {**smoothing_metrics(layout),
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


def smoothing_metrics(layout):
    lines=line_statistics(layout);correlations,components=key_correlations(layout)
    primary,error=primary_axis_error(layout.graph,layout.positions,layout.routes,layout.config)
    mean=lambda values:float(np.mean(values)) if values else 0.
    return {
        'turns_per_line':lines['turns_per_line'], 'zigzag_count':lines['zigzag_count'],
        'mean_straight_run':mean([run['length'] for run in lines['runs']]),
        'long_run_fraction_per_line':lines['long_run_fraction_per_line'],
        'primary_line_id':primary,'primary_axis_angle_error_deg':error,
        'key_node_spearman':correlations,'key_node_spearman_by_component':components,
    }
