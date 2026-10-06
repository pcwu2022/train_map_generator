import numpy as np
from .base import Term, register


class SoftTerm(Term): kind='soft'


@register
class Crossings(SoftTerm):
    name='S1_crossings'
    def full(self,layout):
        facts = layout.facts()
        return float(len(facts.get('crossings', [])) + len(facts.get('missing_crossings', [])))


@register
class EdgeLength(SoftTerm):
    name='S2_edge_length'
    def full(self,layout):
        ratios = layout.facts()['lengths'] / layout.targets
        lower_dev = np.maximum(0, 0.8 - ratios)
        upper_dev = np.maximum(0, ratios - 1.2)
        penalty = (lower_dev + upper_dev)**2
        
        if not hasattr(self, 'terminal_edges'):
            self.terminal_edges = []
            for chain_nodes, chain_edges in layout.graph.chains:
                u, v = chain_nodes[0], chain_nodes[-1]
                if len(layout.graph.adjacency[u]) == 1 or len(layout.graph.adjacency[v]) == 1:
                    self.terminal_edges.extend(chain_edges)
                    
        for ei in self.terminal_edges:
            penalty[ei] += 10.0 * ((ratios[ei] - 1.0)**2)
            
        return float(np.sum(penalty))


@register
class Angle(SoftTerm):
    name='S3_angle'
    def full(self,layout):
        value=float(np.sum(np.array(layout.facts()['angles'])**2))
        if self.parameters.get('exact_diagonal',False):
            from ..geometry import diagonal_soft_deviation
            tolerance=layout.config['routing']['diagonal_tolerance_deg']
            value+=sum(diagonal_soft_deviation(vector,tolerance) for path in layout.routes for vector in np.diff(path,axis=0))
        return value


@register
class Bends(SoftTerm):
    name='S4_bends'
    def full(self,layout):
        if not self.weight: return 0.
        bends=layout.facts()['bends']
        base_penalty=np.minimum(bends,1)+(bends>1)*self.parameters['second_bend']/self.weight
        multiplier = np.ones(len(bends))
        d_min = layout.config['grid']['d_min']
        lengths = layout.facts()['lengths']
        for i, edge in enumerate(layout.graph.edges):
            line_factor = 1.0 + 0.5 * (len(edge.get('lines', [])) - 1)
            length_factor = max(1.0, lengths[i] / (3.0 * d_min))
            multiplier[i] = line_factor * length_factor
        return float(np.sum(base_penalty * multiplier))


@register
class Collinearity(SoftTerm):
    name='S5_collinearity'
    def full(self,layout):
        deviations=np.array(layout.facts()['collinear'])
        return float(np.sum(deviations/45 if self.parameters.get('linear',False) else deviations**2))


@register
class Direction(SoftTerm):
    name='S6_direction'
    def full(self,layout):
        if self.parameters.get('chain_only',False):
            from ..reference import chain_direction_cost
            return chain_direction_cost(layout,self.parameters['tolerance_deg'])
        return float(np.sum(np.maximum(0,np.array(layout.facts()['geo_deviations'])-self.parameters['tolerance_deg'])**2))


@register
class Displacement(SoftTerm):
    name='S7_displacement'
    def full(self,layout):
        if self.parameters.get('key_only',False):
            from ..reference import key_nodes
            keys=key_nodes(layout.graph)
            if not keys:return 0.
            p,a=layout.positions[keys],layout.anchor[keys]
            d=(p-p.mean(axis=0))-(a-a.mean(axis=0))
        else:d=layout.facts()['displacement']
        return float(np.mean(np.sum(d*d,axis=1))) if len(d) else 0.


@register
class ChainSpacing(SoftTerm):
    name='S8_chain_spacing'
    def full(self,layout): return float(np.sum(layout.facts()['chain_variances']))


@register
class Compactness(SoftTerm):
    name='S9_compactness'
    def full(self,layout): return layout.facts()['area']


def line_statistics(layout):
    from ..line_geometry import line_facts
    facts=layout.facts()
    if 'line_geometry' not in facts:
        facts['line_geometry']=line_facts(layout.graph,layout.routes,layout.config)
    return facts['line_geometry']


@register
class LineTurns(SoftTerm):
    name='S11_line_turns'
    def full(self,layout):return float(sum(line_statistics(layout)['turns_per_line'].values()))


@register
class Zigzag(SoftTerm):
    name='S12_zigzag'
    def full(self,layout):return float(line_statistics(layout)['zigzag_count'])


@register
class MinimumRun(SoftTerm):
    name='S13_min_run'
    def full(self,layout):
        minimum = 3.0 * layout.config['grid']['d_min']
        return sum(((minimum-run['length'])/minimum)**2 for run in line_statistics(layout)['runs']
                   if run['length']<minimum and not run['terminal'])


@register
class RelativeOrder(SoftTerm):
    name='S14_relative_order'
    def full(self,layout):
        from ..reference import relative_order_cost
        return relative_order_cost(layout,self.parameters['k'])


@register
class ChainAngleVariance(SoftTerm):
    name='S15_chain_angle_variance'
    def full(self,layout):
        total_var = 0.0
        facts = layout.facts()
        for chain_nodes, chain_edges in layout.graph.chains:
            deviations = []
            for e in chain_edges:
                deviations.extend(facts['edge_deviations'][e])
            if len(deviations) > 1:
                total_var += float(np.var(deviations))
        return total_var

@register
class ChainTurns(SoftTerm):
    name='S18_chain_turns'
    def full(self,layout):
        penalty = 0.0
        facts = layout.facts()
        for chain_nodes, chain_edges in layout.graph.chains:
            turns = sum(facts['bends'][e] for e in chain_edges)
            for node in chain_nodes[1:-1]:
                turns += facts['node_internal_turns'].get(node, 0)
            if turns > 2:
                penalty += (turns - 2)**2
        return float(penalty)


@register
class TransferOrthogonality(SoftTerm):
    name='S16_transfer_orthogonality'
    def full(self,layout):
        penalty = 0.0
        for node in range(len(layout.graph.nodes)):
            is_transfer = len(layout.graph.adjacency[node]) > 2 or len(layout.graph.nodes[node].get('lines', [])) > 1
            if is_transfer:
                from ..geometry import node_tangents, bearing
                tangents = node_tangents(layout.graph, layout.routes, node)
                for edge, vec in tangents:
                    b = bearing(vec)
                    dist_90 = b % 90
                    dist_90 = min(dist_90, 90 - dist_90)
                    if dist_90 > 5:
                        penalty += 1.0
        return penalty


@register
class RadialGravity(SoftTerm):
    name='S17_radial_gravity'
    def full(self,layout):
        if not hasattr(self, 'center_node'):
            anchors = layout.anchor
            median = np.median(anchors, axis=0)
            distances = np.linalg.norm(anchors - median, axis=1)
            self.center_node = np.argmin(distances)
            
        center_pos = layout.positions[self.center_node]
        distances = np.linalg.norm(layout.positions - center_pos, axis=1)
        return float(np.mean(distances))
