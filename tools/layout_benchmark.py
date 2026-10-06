"""Run reproducible, bounded comparisons; keep JSON, PNG and provenance per stage."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from schematic_map import generate_layout,load_config
from schematic_map.graph.build import build_graph
from schematic_map.layout.line_geometry import line_facts
from schematic_map.io.export import export_layout
from schematic_map.render.png import render_png


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage',required=True)
    parser.add_argument('--config',default='tests/config/large_network.yaml')
    parser.add_argument('--inputs',nargs='+',default=['data/graphs/jre_shinkansen.json','data/graphs/jre.json','data/graphs/jrw.json','data/graphs/jrw_kansai.json'])
    args=parser.parse_args();config=load_config(args.config)
    directory=Path('output/comparisons')/args.stage;directory.mkdir(parents=True,exist_ok=True)
    (directory/'config.json').write_text(json.dumps(config,indent=2)+'\n')
    summary={}
    for path in args.inputs:
        data=json.loads(Path(path).read_text());name=Path(path).stem
        result=generate_layout(data,config,record_runtime=True,progress=lambda s:print(name,s,flush=True))
        graph=build_graph(data,config);routes=[np.asarray(e['path']) for e in result['edges']]
        extra=line_facts(graph,routes,config);extra.pop('runs')
        result['metrics'].update(extra);export_layout(result,directory/f'{name}.json');render_png(result,directory/f'{name}.png')
        summary[name]=result['metrics'];print(name,{k:summary[name][k] for k in ['hard_violations','crossings','zigzag_count','bends_total']},flush=True)
    (directory/'metrics.json').write_text(json.dumps(summary,indent=2)+'\n')
    base=Path('output/comparisons/baseline/metrics.json')
    if base.exists():
        baseline=json.loads(base.read_text())
        rows=['| Fixture | Hard before → after | Crossings before → after | Zigzags before → after | Bends before → after |','|---|---:|---:|---:|---:|']
        for name,metrics in summary.items():
            rows.append('| '+name+' | '+' | '.join(f"{baseline[name][key]} → {metrics[key]}" for key in ['hard_violations','crossings','zigzag_count','bends_total'])+' |')
        (directory/'comparison.md').write_text('\n'.join(rows)+'\n')
        print('\n'.join(rows),flush=True)


if __name__=='__main__':main()
