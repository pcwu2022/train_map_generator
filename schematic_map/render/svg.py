"""The common SVG renderer, entirely driven by layout JSON.

Labels are outlined using the bundled CJK font so Cairo and browsers render
identical glyphs without installed system fonts or remote font services.
"""
from functools import lru_cache
from html import escape
from pathlib import Path
import math
import numpy as np
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen


def number(x): return format(float(x),'.8g')


@lru_cache(maxsize=1)
def font():
    return TTFont(Path(__file__).resolve().parents[1]/'fonts/NotoSansCJKjp-Regular.otf')


@lru_cache(maxsize=4096)
def glyph(character):
    f=font(); name=f.getBestCmap().get(ord(character),'.notdef')
    pen=SVGPathPen(f.getGlyphSet()); f.getGlyphSet()[name].draw(pen)
    return pen.getCommands(),f['hmtx'][name][0],f['head'].unitsPerEm


def offset_path(path,offset,miter_limit):
    points=np.asarray(path,dtype=float)
    if offset==0: return points
    delta=np.diff(points,axis=0); lengths=np.linalg.norm(delta,axis=1)
    normals=np.column_stack((-delta[:,1],delta[:,0]))/np.maximum(lengths[:,None],1e-12)
    result=[points[0]+offset*normals[0]]
    for i in range(1,len(points)-1):
        miter=normals[i-1]+normals[i]; norm=np.linalg.norm(miter)
        if norm<1e-12: result.append(points[i]+offset*normals[i]); continue
        miter/=norm; projection=float(miter @ normals[i])
        distance=offset/max(projection,1e-12)
        distance=math.copysign(min(abs(distance),abs(offset)*miter_limit),distance)
        result.append(points[i]+miter*distance)
    result.append(points[-1]+offset*normals[-1]); return np.asarray(result)


def rounded_path(points,radius):
    commands=[f'M {number(points[0,0])} {number(-points[0,1])}']
    for i in range(1,len(points)-1):
        before,after=points[i-1]-points[i],points[i+1]-points[i]
        la,lb=np.linalg.norm(before),np.linalg.norm(after)
        trim=min(radius,la/2,lb/2)
        a,b=points[i]+before/max(la,1e-12)*trim,points[i]+after/max(lb,1e-12)*trim
        commands.append(f'L {number(a[0])} {number(-a[1])} Q {number(points[i,0])} {number(-points[i,1])} {number(b[0])} {number(-b[1])}')
    commands.append(f'L {number(points[-1,0])} {number(-points[-1,1])}')
    return ' '.join(commands)


def luminance(color):
    values=[int(color[i:i+2],16)/255 for i in (1,3,5)]
    values=[v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4 for v in values]
    return sum(v*w for v,w in zip(values,(0.2126,0.7152,0.0722)))


def render_svg(layout):
    cfg=layout['render']; labels=layout['label_style']; bounds=layout['meta']['bounds']; pad=cfg['padding']
    xmin,ymin,xmax,ymax=bounds; width=max(xmax-xmin+2*pad,2*pad); height=max(ymax-ymin+2*pad,2*pad)
    viewbox=f'{number(xmin-pad)} {number(-ymax-pad)} {number(width)} {number(height)}'
    content=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" width="{number(width*cfg["pixels_per_unit"])}" height="{number(height*cfg["pixels_per_unit"])}" role="img" aria-label="Transit map">',
        f'<rect x="{number(xmin-pad)}" y="{number(-ymax-pad)}" width="{number(width)}" height="{number(height)}" fill="{escape(cfg["background"],quote=True)}"/>',
        '<g class="routes" fill="none" stroke-linecap="round" stroke-linejoin="round">']
    lines={line['id']:line for line in layout['lines']}
    for edge in layout['edges']:
        for line_id in edge['lines']:
            line=lines[line_id]; path=offset_path(edge['path'],edge['line_offsets'][line_id]*cfg['line_width'],cfg['miter_limit'])
            commands=rounded_path(path,cfg['corner_radius']); color=line['color']
            contrast=(max(luminance(color),luminance(cfg['background']))+0.05)/(min(luminance(color),luminance(cfg['background']))+0.05)
            if cfg['outline_low_contrast'] and contrast<cfg['contrast_threshold']:
                content.append(f'<path class="transit-line" data-line-id="{escape(line_id,quote=True)}" d="{commands}" stroke="#333333" stroke-width="{number(cfg["line_width"]*1.4)}"/>')
            content.append(f'<path class="transit-line" data-line-id="{escape(line_id,quote=True)}" d="{commands}" stroke="{color}" stroke-width="{number(cfg["line_width"])}"><title>{escape(line["name"])}</title></path>')
    content.append('</g><g class="stations">')
    for node in layout['nodes']:
        x,y=node['schematic']; interchange=node['marker']=='interchange'; radius=cfg['interchange_radius'] if interchange else cfg['marker_radius']
        content.append(f'<circle class="transit-station" data-station-id="{escape(node["id"],quote=True)}" tabindex="0" role="button" aria-label="{escape(node["name"],quote=True)}" cx="{number(x)}" cy="{number(-y)}" r="{number(radius)}" fill="white" stroke="black" stroke-width="{number(cfg["line_width"]/2)}"><title>{escape(node["name"])}</title></circle>')
    content.append('</g><g class="labels" fill="#111111">')
    for node in layout['nodes']:
        label=node['label']; anchor=label['anchor']; size=labels['font_size']; x,y=np.array(node['schematic'])+label['offset']
        glyphs=[glyph(c) for c in node['name']]; units=font()['head'].unitsPerEm; scale=size/units; width=sum(g[1] for g in glyphs)*scale
        if 'west' in anchor: x-=width
        elif 'east' not in anchor: x-=width/2
        if 'north' in anchor: y+=size*0.15
        elif 'south' in anchor: y-=size*0.85
        else: y-=size*0.35
        content.append(f'<g class="station-label" data-kind="{node["kind"]}" data-station-id="{escape(node["id"],quote=True)}" aria-label="{escape(node["name"],quote=True)}" transform="translate({number(x)} {number(-y)}) rotate({number(-label["rotation_deg"])}) scale({number(scale)} {number(-scale)})">')
        cursor=0
        for commands,advance,_ in glyphs:
            if commands: content.append(f'<path transform="translate({cursor} 0)" d="{commands}"/>')
            cursor+=advance
        content.append('</g>')
    content.append('</g></svg>'); return '\n'.join(content)
