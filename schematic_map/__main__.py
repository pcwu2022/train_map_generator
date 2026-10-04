import argparse
import json
from pathlib import Path
import shutil
from jsonschema.exceptions import ValidationError
from .config import load_config
from .io.load import load_graph
from .io.export import export_layout, validate_layout
from .pipeline import generate_layout


def main(argv=None):
    parser=argparse.ArgumentParser(description='Generate schematic JSON, SVG, PNG and a pan/zoom viewer')
    parser.add_argument('input',type=Path)
    parser.add_argument('-o','--output-dir',type=Path,default=Path('output'))
    parser.add_argument('--config',type=Path)
    parser.add_argument('--seed',type=int)
    parser.add_argument('--render-only',action='store_true',help='Input is existing layout JSON')
    parser.add_argument('--runtime',action='store_true',help='Include elapsed runtime (otherwise deterministic null)')
    parser.add_argument('--allow-infeasible',action='store_true',help='Exit successfully even if hard constraints remain')
    parser.add_argument('--no-png',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.render_only:
            layout=json.loads(args.input.read_text()); validate_layout(layout)
        else:
            config=load_config(args.config,{'seed':args.seed} if args.seed is not None else None)
            layout=generate_layout(load_graph(args.input),config,record_runtime=args.runtime,progress=print)
        args.output_dir.mkdir(parents=True,exist_ok=True)
        export_layout(layout,args.output_dir/'layout.json')
        from .render.svg import render_svg
        (args.output_dir/'map.svg').write_text(render_svg(layout),encoding='utf-8')
        if not args.no_png:
            from .render.png import render_png
            render_png(layout,args.output_dir/'map.png')
        shutil.copyfile(Path(__file__).parent/'web/transit-map.js',args.output_dir/'transit-map.js')
        (args.output_dir/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Transit map</title><style>html,body{margin:0;height:100%;font-family:sans-serif}transit-map{height:100vh}</style><script type="module" src="transit-map.js"></script><transit-map src="layout.json"></transit-map></html>')
        m=layout['metrics']; print(f'Wrote {args.output_dir}: {m["hard_violations"]} hard violations, {m["crossings"]} crossings, {m["label_overlaps"]} label overlaps')
        if m['hard_violations'] and not args.allow_infeasible: return 2
        return 0
    except (ValueError, OSError, ValidationError) as error:
        parser.error(str(error))


if __name__=='__main__':
    raise SystemExit(main())
