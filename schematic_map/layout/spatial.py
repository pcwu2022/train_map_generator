"""Deterministic uniform-grid broad phase for node and edge geometry."""
from collections import defaultdict
import math


class SpatialGrid:
    def __init__(self,cell_size):
        self.cell_size=cell_size
        self.cells=defaultdict(set)
        self.members={}

    def keys(self,bounds):
        xmin,ymin,xmax,ymax=bounds
        for x in range(math.floor(xmin/self.cell_size),math.floor(xmax/self.cell_size)+1):
            for y in range(math.floor(ymin/self.cell_size),math.floor(ymax/self.cell_size)+1):
                yield x,y

    def put(self,ident,bounds):
        for key in self.members.pop(ident,()): self.cells[key].discard(ident)
        keys=tuple(self.keys(bounds)); self.members[ident]=keys
        for key in keys: self.cells[key].add(ident)

    def query(self,bounds):
        result=set()
        for key in self.keys(bounds): result.update(self.cells.get(key,()))
        return sorted(result)
