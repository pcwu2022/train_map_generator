import numpy as np
from .base import Term, register


class SoftTerm(Term): kind='soft'


@register
class Crossings(SoftTerm):
    name='S1_crossings'
    def full(self,layout): return float(len(layout.facts()['crossings']))


@register
class EdgeLength(SoftTerm):
    name='S2_edge_length'
    def full(self,layout): return float(np.sum(((layout.facts()['lengths']-layout.targets)/layout.targets)**2))


@register
class Angle(SoftTerm):
    name='S3_angle'
    def full(self,layout): return float(np.sum(np.array(layout.facts()['angles'])**2))


@register
class Bends(SoftTerm):
    name='S4_bends'
    def full(self,layout):
        bends=layout.facts()['bends']
        return float(np.sum(np.minimum(bends,1))+np.sum(bends>1)*self.parameters['second_bend']/self.weight) if self.weight else 0.


@register
class Collinearity(SoftTerm):
    name='S5_collinearity'
    def full(self,layout): return float(np.sum(np.array(layout.facts()['collinear'])**2))


@register
class Direction(SoftTerm):
    name='S6_direction'
    def full(self,layout):
        return float(np.sum(np.maximum(0,np.array(layout.facts()['geo_deviations'])-self.parameters['tolerance_deg'])**2))


@register
class Displacement(SoftTerm):
    name='S7_displacement'
    def full(self,layout):
        d=layout.facts()['displacement']; return float(np.mean(np.sum(d*d,axis=1))) if len(d) else 0.


@register
class ChainSpacing(SoftTerm):
    name='S8_chain_spacing'
    def full(self,layout): return float(np.sum(layout.facts()['chain_variances']))


@register
class Compactness(SoftTerm):
    name='S9_compactness'
    def full(self,layout): return layout.facts()['area']
