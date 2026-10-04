from .base import Term, register


class HardTerm(Term):
    kind='hard'
    def full(self,layout):
        return float(len(layout.facts()['hard'][self.name]))


@register
class MinSpacing(HardTerm):
    name='H1_min_spacing'
    def full(self,layout): return layout.facts()['spacing_penalty']


@register
class BendLimit(HardTerm): name='H2_bend_limit'


@register
class BendAngle(HardTerm): name='H3_bend_angle'


@register
class SegmentDirection(HardTerm): name='H4_segment_direction'


@register
class NodeClearance(HardTerm):
    name='H5_node_clearance'
    def full(self,layout): return layout.facts()['clearance_penalty']


@register
class Ports(HardTerm): name='H6_ports'


@register
class CircularOrder(HardTerm): name='H7_circular_order'
