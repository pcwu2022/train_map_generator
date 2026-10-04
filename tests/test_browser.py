"""Optional integration tests: pip install playwright; playwright install chromium."""
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import threading
import pytest
from schematic_map import generate_layout
from schematic_map.io.export import export_layout

playwright=pytest.importorskip('playwright.sync_api')


@pytest.fixture
def browser_page(tmp_path,fixtures,fast_config):
    layout=generate_layout(fixtures['bundle'],fast_config)
    export_layout(layout,tmp_path/'layout.json')
    (tmp_path/'transit-map.js').write_text((Path(__file__).parents[1]/'schematic_map/web/transit-map.js').read_text())
    (tmp_path/'index.html').write_text('<script type="module" src="transit-map.js"></script><transit-map src="layout.json" style="height:600px"></transit-map>')
    requests=[]
    class QuietHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            super().do_GET()
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(tmp_path)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with playwright.sync_playwright() as runtime:
            try: browser=runtime.chromium.launch(headless=True)
            except playwright.Error as error:
                if 'Executable' in str(error):pytest.skip('Playwright Chromium is not installed')
                raise
            page=browser.new_page(viewport={'width':900,'height':700},has_touch=True)
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.wait_for_function("document.querySelector('transit-map')?.shadowRoot.querySelector('svg')")
            assert requests.count('/layout.json')==1, 'Initial connection must fetch the layout once'
            yield page,layout,errors
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join()


def test_pan_zoom_events_and_lod(browser_page):
    page,layout,errors=browser_page
    host=page.locator('transit-map');svg=host.locator('svg')
    assert host.locator('.transit-station').count()==len(layout['nodes'])
    page.evaluate("""() => {window.mapEvents=[];for(const type of ['station-click','line-hover'])document.querySelector('transit-map').addEventListener(type,e=>mapEvents.push({type,id:e.detail.id}));}""")
    host.locator('.transit-station').first.click()
    assert page.evaluate('mapEvents.some(e=>e.type==="station-click")')
    point=host.locator('.transit-line').first.evaluate('el => {const p=el.getPointAtLength(el.getTotalLength()/2).matrixTransform(el.getScreenCTM());return {x:p.x,y:p.y}}')
    page.mouse.move(point['x'],point['y'])
    assert page.evaluate('mapEvents.some(e=>e.type==="line-hover")')
    assert host.locator('.muted').count()>0
    width=lambda:page.evaluate("document.querySelector('transit-map').shadowRoot.querySelector('svg').viewBox.baseVal.width")
    initial=width();page.mouse.move(450,300);page.mouse.wheel(0,-700)
    page.wait_for_function("document.querySelector('transit-map').zoom>1.2")
    assert width()<initial
    assert host.locator('.station-label.hidden').count()==0
    old_x=page.evaluate("document.querySelector('transit-map').svg.viewBox.baseVal.x")
    page.mouse.move(700,500);page.mouse.down();page.mouse.move(750,520);page.mouse.up()
    assert page.evaluate("document.querySelector('transit-map').svg.viewBox.baseVal.x")!=old_x
    page.evaluate("document.querySelector('transit-map').reset()")
    assert width()==pytest.approx(initial)
    assert not errors


def test_touch_pinch_and_sanitization(browser_page):
    page,layout,errors=browser_page
    session=page.context.new_cdp_session(page)
    session.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':400,'y':300,'id':1},{'x':500,'y':300,'id':2}]})
    session.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':350,'y':300,'id':1},{'x':550,'y':300,'id':2}]})
    session.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
    page.wait_for_function("document.querySelector('transit-map').zoom>1")
    page.evaluate("""() => {const map=document.querySelector('transit-map');const layout=structuredClone(map.layout);layout.svg=layout.svg.replace('</svg>','<script>window.injected=true</script><image href="invalid" onload="window.injected=true"/></svg>');map.setLayout(layout);}""")
    assert not page.evaluate('!!window.injected')
    assert page.locator('transit-map').locator('script,image').count()==0
    assert not errors
