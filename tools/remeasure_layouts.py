"""Add new diagnostics to saved layouts without changing their geometry or energy."""
import argparse
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from schematic_map import load_config
from schematic_map.graph.build import build_graph
from schematic_map.layout.energy.base import Layout
from schematic_map.layout.transform import apply_transform,target_lengths
from schematic_map.metrics import smoothing_metrics
from schematic_map.io.export import export_layout
from schematic_map.io.export import validate_layout


def remeasure(source,destination):
    config=load_config(overrides=json.loads((source/'config.json').read_text()))
    destination.mkdir(parents=True,exist_ok=True)
    summary={}
    for path in sorted(source.glob('*.json')):
        if path.stem in ('metrics','config','provenance'):continue
        result=json.loads(path.read_text())
        graph=build_graph(result,config)
        transform=result['transform']
        graph.topology_reference=apply_transform(graph.geo,transform['rotation_deg'],transform['aspect'])
        positions=np.array([node['schematic'] for node in result['nodes']]);routes=[np.array(edge['path']) for edge in result['edges']]
        layout=Layout(graph,positions,routes,graph.topology_reference,target_lengths(graph,config),config)
        result['metrics'].update(smoothing_metrics(layout));validate_layout(result)
        export_layout(result,destination/path.name)
        summary[path.stem]=result['metrics']
        if source!=destination:shutil.copyfile(source/f'{path.stem}.png',destination/f'{path.stem}.png')
    if source!=destination:shutil.copyfile(source/'config.json',destination/'config.json')
    (destination/'metrics.json').write_text(json.dumps(summary,indent=2)+'\n')
    (destination/'provenance.json').write_text(json.dumps({'geometry_source':str(source),'operation':'Remeasure unchanged routed geometry; retain original energy, runtime and PNG'},indent=2)+'\n')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('destination',nargs='?')
    args=parser.parse_args();source=Path(args.source)
    remeasure(source,Path(args.destination) if args.destination else source)
