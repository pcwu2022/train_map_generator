from pathlib import Path
from PIL import Image,ImageChops,ImageFilter,ImageStat
from schematic_map import generate_layout
from schematic_map.render.png import render_png


def test_straight_visual_regression(fixtures,fast_config,tmp_path):
    layout=generate_layout(fixtures['straight'],fast_config)
    actual=tmp_path/'actual.png';render_png(layout,actual)
    golden=Image.open(Path(__file__).parent/'goldens/straight.png').convert('RGB')
    rendered=Image.open(actual).convert('RGB')
    assert rendered.size==golden.size
    # Blur removes platform antialiasing noise; RMS still catches moved/missing features.
    diff=ImageChops.difference(golden.filter(ImageFilter.GaussianBlur(1)),rendered.filter(ImageFilter.GaussianBlur(1)))
    assert max(ImageStat.Stat(diff).rms)<3
