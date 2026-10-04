from pathlib import Path
from PIL import Image,ImageChops,ImageFilter,ImageStat
from schematic_map import generate_layout,load_config
from schematic_map.render.png import render_png


def test_straight_visual_regression(fixtures,fast_config,tmp_path):
    config=load_config(Path(__file__).parent/'config/legacy.yaml')
    config['anneal'].update(fast_config['anneal']);config['refine'].update(fast_config['refine'])
    layout=generate_layout(fixtures['straight'],config)
    actual=tmp_path/'actual.png';render_png(layout,actual)
    golden=Image.open(Path(__file__).parent/'goldens/straight.png').convert('RGB')
    rendered=Image.open(actual).convert('RGB')
    assert rendered.size==golden.size
    # Blur removes platform antialiasing noise; RMS still catches moved/missing features.
    diff=ImageChops.difference(golden.filter(ImageFilter.GaussianBlur(1)),rendered.filter(ImageFilter.GaussianBlur(1)))
    assert max(ImageStat.Stat(diff).rms)<3
