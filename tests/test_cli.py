from copy import deepcopy
import json
from schematic_map.__main__ import main


def test_infeasible_result_is_reported_and_exported(fixtures,tmp_path):
    data=deepcopy(fixtures['straight'])
    for node in data['nodes']:node['schematic']=[0,0]
    source=tmp_path/'input.json';source.write_text(json.dumps(data))
    config=tmp_path/'config.yaml';config.write_text('init: {mode: hint}\ngrid: {overlap_iterations: 0}\nanneal: {restarts: 1, max_sweeps: 0, calibration_moves: 0, greedy_sweeps: 0}\nrefine: {sweeps: 0}\n')
    output=tmp_path/'output'
    assert main([str(source),'--config',str(config),'-o',str(output),'--no-png'])==2
    layout=json.loads((output/'layout.json').read_text())
    assert not layout['meta']['feasible']
    assert layout['metrics']['hard_violations']>0
    assert layout['metrics']['violation_report']['H1_min_spacing']
    assert main([str(output/'layout.json'),'--render-only','--allow-infeasible','--no-png','-o',str(tmp_path/'rerendered')])==0
