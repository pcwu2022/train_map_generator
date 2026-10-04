import json
from pathlib import Path
from jsonschema import Draft202012Validator


def validate_layout(layout):
    schema=json.loads((Path(__file__).parent/'layout.schema.json').read_text())
    Draft202012Validator(schema).validate(layout)
    nodes={n['id']:n for n in layout['nodes']}
    lines={line['id'] for line in layout['lines']}
    if len(nodes)!=len(layout['nodes']) or len(lines)!=len(layout['lines']): raise ValueError('Duplicate output identifiers')
    for edge in layout['edges']:
        if edge['path'][0]!=nodes[edge['source']]['schematic'] or edge['path'][-1]!=nodes[edge['target']]['schematic']:
            raise ValueError('Route endpoints must equal station schematic coordinates')
        if set(edge['lines'])!=set(edge['line_offsets']) or not set(edge['lines'])<=lines:
            raise ValueError('Invalid bundle offsets or line references')
    return layout


def export_layout(layout,path,embed_svg=True):
    data=dict(layout)
    if embed_svg:
        from ..render.svg import render_svg
        data['svg']=render_svg(layout)
    validate_layout(data)
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
