"""Report acceptance honestly, including per-line failures and undefined axes."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from schematic_map import load_config


def report(directory,baseline):
    config=load_config(overrides=json.loads((directory/'config.json').read_text()))
    criteria=config['acceptance'];minimum=criteria['min_long_run_fraction']
    base=json.loads((baseline/'metrics.json').read_text());results=json.loads((directory/'metrics.json').read_text())
    rows=['| Fixture | Hard | Crossings (baseline) | Zigzags | Primary axis ° | Key Spearman x / y | Lines meeting straight-run target |','|---|---:|---:|---:|---:|---|---:|']
    details={}
    for name,metrics in results.items():
        output=json.loads((directory/f'{name}.json').read_text())
        fractions=metrics['long_run_fraction_per_line']
        failures={line:fraction for line,fraction in fractions.items() if fraction is not None and fraction<minimum}
        correlations=metrics['key_node_spearman'];error=metrics['primary_axis_angle_error_deg']
        eligible=output['transform'].get('primary_axis_eligible',False)
        details[name]={
            'hard_zero':metrics['hard_violations']==0,
            'crossings_no_worse_than_baseline':metrics['crossings']<=base[name]['crossings'],
            'zigzag_zero':metrics['zigzag_count']==0,
            'primary_axis_eligible':eligible,
            'primary_axis_pass':None if not eligible or error is None else error<=config['primary_axis']['max_error_deg'],
            'key_spearman_pass':{axis:None if value is None else value>=criteria['min_key_spearman'] for axis,value in correlations.items()},
            'short_run_lines':failures,
            'dense_core_exemptions_applied':False,
        }
        fmt=lambda value:'undefined' if value is None else f'{value:.3f}'
        rows.append(f"| {name} | {metrics['hard_violations']} | {metrics['crossings']} ({base[name]['crossings']}) | {metrics['zigzag_count']} | {fmt(error)} | {fmt(correlations['x'])} / {fmt(correlations['y'])} | {sum(v is not None and v>=minimum for v in fractions.values())}/{sum(v is not None for v in fractions.values())} |")
    rows.extend(['', 'Every line is reported; no dense-core exemption was inferred. Undefined PCA', 'axes and correlations are recorded as null. Primary alignment applies only', 'when the transform reports an eligible primary; zero zigzags is a target', 'for single-line/Shinkansen inputs. This report does not infer fixture classes.', 'Exact failures and configured thresholds are in `acceptance.json`.'])
    (directory/'acceptance.json').write_text(json.dumps({'criteria':criteria,'primary_axis_max_error_deg':config['primary_axis']['max_error_deg'],'fixtures':details},indent=2)+'\n')
    (directory/'acceptance.md').write_text('\n'.join(rows)+'\n')
    print('\n'.join(rows))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory');parser.add_argument('--baseline',default='output/comparisons/baseline')
    args=parser.parse_args();report(Path(args.directory),Path(args.baseline))
