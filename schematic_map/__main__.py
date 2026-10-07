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
    parser.add_argument('--live',action='store_true',help='Live update in browser during layout generation')
    args=parser.parse_args(argv)
    try:
        if args.render_only:
            layout=json.loads(args.input.read_text()); validate_layout(layout)
        else:
            config=load_config(args.config,{'seed':args.seed} if args.seed is not None else None)
            if args.live:
                config['anneal']['workers'] = 1
                config['anneal']['restarts'] = 1
            args.output_dir.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(Path(__file__).parent/'web/transit-map.js',args.output_dir/'transit-map.js')
            (args.output_dir/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Transit map</title><style>html,body{margin:0;height:100%;font-family:sans-serif}transit-map{height:100vh} #progress-container{position:absolute;bottom:20px;left:50%;transform:translateX(-50%);width:60%;max-width:600px;background:rgba(255,255,255,0.95);padding:10px 20px;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,0.15);font-family:sans-serif;z-index:999;display:flex;flex-direction:column;gap:8px;} #progress-bar{width:100%;height:8px;background:#eee;border-radius:4px;overflow:hidden;} #progress-fill{height:100%;background:#0077ff;width:0%;transition:width 0.3s;} #progress-text{font-size:14px;font-weight:bold;color:#333;text-align:center;}</style><script type="module" src="transit-map.js"></script><div id="progress-container" style="display:none;"><div id="progress-text">Waiting for data...</div><div id="progress-bar"><div id="progress-fill"></div></div></div><transit-map src="layout.json"></transit-map>' + ('<script>document.getElementById("progress-container").style.display="flex";let lz=null,lb=null,last_id=null,startTime=null;setInterval(()=>{fetch("layout.json?t="+Date.now()).then(r=>r.json()).then(data=>{if(data.meta.update_id===last_id)return;last_id=data.meta.update_id;if(startTime===null&&data.meta.percent!==undefined&&data.meta.percent<1.0)startTime=Date.now();const tm=document.querySelector("transit-map");lz=tm.zoom;if(tm.svg?.viewBox?.baseVal)lb={x:tm.svg.viewBox.baseVal.x,y:tm.svg.viewBox.baseVal.y,w:tm.svg.viewBox.baseVal.width,h:tm.svg.viewBox.baseVal.height};tm.setLayout(data);if(lb){tm.zoom=lz;tm.svg.viewBox.baseVal.x=lb.x;tm.svg.viewBox.baseVal.y=lb.y;tm.svg.viewBox.baseVal.width=lb.w;tm.svg.viewBox.baseVal.height=lb.h;tm.updateLabels();}let timeText="";if(startTime!==null){let elapsed=(Date.now()-startTime)/1000;let ft=(s)=>{let m=Math.floor(s/60);let ss=Math.floor(s%60);return(m>0?m+"m ":"")+ss+"s"};let rem="--";if(data.meta.percent>0){let total=elapsed/data.meta.percent;rem=ft(Math.max(0,total-elapsed));}timeText=` (經過: ${ft(elapsed)} | 剩餘: ${rem})`;}if(data.meta.percent!==undefined)document.getElementById("progress-fill").style.width=(data.meta.percent*100)+"%";document.getElementById("progress-text").innerText=(data.meta.progress||"")+timeText;}).catch(()=>{})}, 500);</script>' if args.live else '') + '</html>', encoding='utf-8')

            import time
            last_write = [0]
            update_counter = [0]
            def live_callback(layout_data):
                if time.time() - last_write[0] < 1.0: return
                last_write[0] = time.time()
                update_counter[0] += 1
                layout_data['meta']['update_id'] = update_counter[0]
                try:
                    from .render.svg import render_svg
                    layout_data['svg'] = render_svg(layout_data)
                    (args.output_dir/'layout.json').write_text(json.dumps(layout_data), encoding='utf-8')
                except Exception as e:
                    print(f"Live preview error: {e}")

            import time
            start_time_total = time.perf_counter()
            layout=generate_layout(load_graph(args.input),config,record_runtime=args.runtime,progress=print,live_callback=live_callback if args.live else None)
            
        export_layout(layout,args.output_dir/'layout.json')
        from .render.svg import render_svg
        (args.output_dir/'map.svg').write_text(render_svg(layout),encoding='utf-8')
        if not args.no_png:
            from .render.png import render_png
            render_png(layout,args.output_dir/'map.png')
            
        m=layout['metrics']
        if args.render_only:
            print(f'Wrote {args.output_dir}: {m["hard_violations"]} hard violations, {m["crossings"]} crossings, {m["label_overlaps"]} label overlaps')
        else:
            elapsed_total = time.perf_counter() - start_time_total
            print(f'Wrote {args.output_dir}: {m["hard_violations"]} hard violations, {m["crossings"]} crossings, {m["label_overlaps"]} label overlaps. (Total time: {elapsed_total:.2f}s)')
            
        if m['hard_violations'] and not args.allow_infeasible: return 2
        return 0
    except (ValueError, OSError, ValidationError) as error:
        parser.error(str(error))


if __name__=='__main__':
    raise SystemExit(main())
