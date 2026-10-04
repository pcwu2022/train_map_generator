from pathlib import Path
from .svg import render_svg


def render_png(layout,path,dpi=None):
    import cairosvg
    config=layout['render']; dpi=config['dpi'] if dpi is None else dpi
    if dpi<=0: raise ValueError('DPI must be positive')
    cairosvg.svg2png(bytestring=render_svg(layout).encode(),write_to=str(Path(path)),dpi=dpi,scale=dpi/config['dpi'])
