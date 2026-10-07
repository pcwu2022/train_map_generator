/* Renders the common Python SVG embedded in exported layout JSON. No server API. */
export class TransitMap extends HTMLElement {
  static observedAttributes = ['src'];
  constructor() {
    super(); this._attached=false; this.attachShadow({mode:'open'}); this.pointers=new Map(); this.zoom=1;
    this.shadowRoot.innerHTML=`<style>:host{display:block;min-height:300px;position:relative}svg{width:100%;height:100%;position:absolute;touch-action:none;user-select:none}.transit-station,.transit-line{cursor:pointer;transition:opacity 0.2s}.transit-station:focus{stroke:#0077ff;outline:none}.muted{opacity:.15}.hidden{display:none}.error{padding:1em;color:#a00} #info-panel{position:absolute;bottom:20px;left:50%;transform:translateX(-50%);background:rgba(255,255,255,0.95);padding:12px 24px;border-radius:12px;box-shadow:0 6px 16px rgba(0,0,0,0.15);font-family:sans-serif;pointer-events:none;z-index:100;text-align:center;min-width:200px;transition:opacity 0.2s;} #info-title{font-weight:bold;margin-bottom:6px;font-size:18px;} #info-desc{font-size:14px;color:#555;}</style><div class="viewport"></div><div id="info-panel" class="hidden"><div id="info-title"></div><div id="info-desc"></div></div>`;
  }
  connectedCallback() { this._attached=true; if(this.hasAttribute('src')) this.load(); }
  disconnectedCallback() { this._attached=false; this.controller?.abort(); }
  attributeChangedCallback(name,oldValue,newValue) { if(oldValue!==newValue && this.isConnected && this._attached) this.load(); }
  async load() {
    this.controller?.abort(); const controller=this.controller=new AbortController();
    try {
      const response=await fetch(this.getAttribute('src'),{signal:controller.signal});
      if(!response.ok) throw new Error(`HTTP ${response.status}`);
      const layout=await response.json(); this.setLayout(layout);
    } catch(error) {
      if(error.name==='AbortError') return;
      this.shadowRoot.querySelector('.viewport').textContent=`Unable to load map: ${error.message}`;
      this.dispatchEvent(new CustomEvent('map-error',{detail:error,bubbles:true,composed:true}));
    }
  }
  setLayout(layout) {
    if(typeof layout.svg!=='string') throw new Error('Layout must contain the common SVG; export with embed_svg=True');
    // Parse SVG into a detached document, allowing only the renderer's inert primitives.
    const doc=new DOMParser().parseFromString(layout.svg,'image/svg+xml'); const root=doc.documentElement;
    if(root.localName!=='svg' || doc.querySelector('parsererror')) throw new Error('Invalid SVG');
    const allowed=new Set(['svg','g','path','circle','rect','title']);
    const attributes=new Set(['xmlns','viewBox','width','height','role','aria-label','class','fill','stroke','stroke-width','stroke-linecap','stroke-linejoin','d','transform','x','y','cx','cy','r','tabindex','data-kind','data-line-id','data-station-id']);
    for(const element of [root,...root.querySelectorAll('*')]) {
      if(!allowed.has(element.localName)) { element.remove(); continue; }
      for(const attr of [...element.attributes]) if(!attributes.has(attr.name)) element.removeAttribute(attr.name);
    }
    this.shadowRoot.querySelector('.viewport').replaceChildren(document.importNode(root,true));
    this.svg=this.shadowRoot.querySelector('svg'); this.layout=layout; this.options=layout.web;
    this.base=this.svg.viewBox.baseVal; this.initial=[this.base.x,this.base.y,this.base.width,this.base.height]; this.zoom=1; this.pointers.clear();
    this.svg.addEventListener('wheel',e=>{ e.preventDefault(); this.scale(Math.exp(-e.deltaY*this.options.wheel_sensitivity),e.clientX,e.clientY); },{passive:false});
    this.svg.addEventListener('pointerdown',e=>{this.svg.setPointerCapture(e.pointerId);this.pointers.set(e.pointerId,[e.clientX,e.clientY]);this.pressTarget=e.target;this.gestureStart=[e.clientX,e.clientY];this.dragged=false;});
    this.svg.addEventListener('pointermove',e=>this.move(e));
    for(const name of ['pointerup','pointercancel','lostpointercapture']) this.svg.addEventListener(name,e=>this.pointers.delete(e.pointerId));
    this.svg.addEventListener('click',e=>{
      if(!this.dragged) {
        const target = (this.pressTarget||e.target).closest('[data-station-id],[data-line-id]');
        if(!target) {
          this.activeLines = null;
          this.highlight(null);
          if(this.hideInfo) this.hideInfo();
        } else {
          this.interaction(e,'click',this.pressTarget||e.target);
        }
      }
      this.pressTarget=null;
    });
    this.svg.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();this.interaction(e,'click');}});
    this.svg.addEventListener('pointerover',e=>{
      this.interaction(e,'hover');
    });
    this.svg.addEventListener('pointerout',()=>{
      if(this.activeLines) return;
      if(this.hideInfo) this.hideInfo();
    });
    this.updateLabels(); this.dispatchEvent(new CustomEvent('map-load',{detail:layout,bubbles:true,composed:true}));
  }
  point(x,y) { const point=new DOMPoint(x,y); return point.matrixTransform(this.svg.getScreenCTM().inverse()); }
  scale(factor,x,y) {
    const next=Math.min(this.options.max_zoom * 5,Math.max(this.options.min_zoom,this.zoom*factor)); factor=next/this.zoom;
    const p=this.point(x,y),v=this.svg.viewBox.baseVal; v.x=p.x+(v.x-p.x)/factor;v.y=p.y+(v.y-p.y)/factor;v.width/=factor;v.height/=factor;this.zoom=next;this.updateLabels();
  }
  move(event) {
    if(!this.pointers.has(event.pointerId))return;
    if(Math.hypot(event.clientX-this.gestureStart[0],event.clientY-this.gestureStart[1])>4)this.dragged=true;
    const old=[...this.pointers.values()]; const previous=this.pointers.get(event.pointerId); const a=this.point(...previous),b=this.point(event.clientX,event.clientY);
    this.pointers.set(event.pointerId,[event.clientX,event.clientY]); const current=[...this.pointers.values()];
    this.svg.viewBox.baseVal.x+=a.x-b.x;this.svg.viewBox.baseVal.y+=a.y-b.y;
    if(current.length===2) {const distance=p=>Math.hypot(p[1][0]-p[0][0],p[1][1]-p[0][1]);if(distance(old)>0)this.scale(distance(current)/distance(old),(current[0][0]+current[1][0])/2,(current[0][1]+current[1][1])/2);}
  }
  updateLabels() {for(const label of this.svg.querySelectorAll('.station-label'))label.classList.toggle('hidden',label.dataset.kind==='through' && this.zoom<this.options.label_zoom);}
  highlight(ids) {
    if(ids !== null && !Array.isArray(ids)) ids = [ids];
    for(const line of this.svg.querySelectorAll('.transit-line')) {
      line.classList.toggle('muted', ids !== null && !ids.includes(line.dataset.lineId));
    }
  }
  interaction(event,action,origin=event.target) {
    const target=origin.closest('[data-station-id],[data-line-id]');if(!target)return;
    const station=target.dataset.stationId;const type=station?'station':'line';const id=station||target.dataset.lineId;
    const item=(station?this.layout.nodes:this.layout.lines).find(item=>item.id===id);
    
    if(action === 'click') {
      if(station) {
        this.activeLines = item.lines || [];
        this.highlight(this.activeLines);
        this.showStationInfo(item);
      } else {
        this.activeLines = [id];
        this.highlight(this.activeLines);
        this.showLineInfo(item);
      }
    } else if(action === 'hover' && !this.activeLines) {
      if(station) this.showStationInfo(item);
      else this.showLineInfo(item);
    }
    
    this.dispatchEvent(new CustomEvent(`${type}-${action}`,{detail:{id,[type]:item,originalEvent:event},bubbles:true,composed:true}));
  }
  getLineEndpoints(lineId) {
    const lineEdges = this.layout.edges.filter(e => e.lines.includes(lineId));
    const nodeCounts = new Map();
    for(const edge of lineEdges) {
      nodeCounts.set(edge.source, (nodeCounts.get(edge.source)||0) + 1);
      nodeCounts.set(edge.target, (nodeCounts.get(edge.target)||0) + 1);
    }
    const endpoints = [];
    for(const [nodeId, count] of nodeCounts.entries()) {
      if (count === 1) {
        const node = this.layout.nodes.find(n => n.id === nodeId);
        if(node) endpoints.push(node.name);
      }
    }
    return endpoints;
  }
  showInfo(title, desc, color) {
    const panel = this.shadowRoot.getElementById('info-panel');
    const titleEl = this.shadowRoot.getElementById('info-title');
    const descEl = this.shadowRoot.getElementById('info-desc');
    titleEl.textContent = title;
    titleEl.style.color = color || '#333';
    descEl.textContent = desc;
    panel.classList.remove('hidden');
  }
  hideInfo() {
    this.shadowRoot.getElementById('info-panel').classList.add('hidden');
  }
  showStationInfo(node) {
    const lineNames = (node.lines||[]).map(lid => {
      const l = this.layout.lines.find(x=>x.id===lid);
      return l ? l.name : lid;
    });
    this.showInfo(node.name, `經過路線: ${lineNames.join(', ')}`, '#333');
  }
  showLineInfo(line) {
    const eps = this.getLineEndpoints(line.id);
    let desc = '';
    if(eps.length === 2) desc = `起終點: ${eps[0]} - ${eps[1]}`;
    else if(eps.length === 0) desc = `環狀線`;
    else desc = `起終點: ${eps.join(', ')}`;
    this.showInfo(line.name, desc, line.color);
  }
  reset() {const v=this.svg?.viewBox.baseVal;if(!v)return;[v.x,v.y,v.width,v.height]=this.initial;this.zoom=1;this.updateLabels();}
}
if(!customElements.get('transit-map'))customElements.define('transit-map',TransitMap);
