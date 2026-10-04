/* Renders the common Python SVG embedded in exported layout JSON. No server API. */
export class TransitMap extends HTMLElement {
  static observedAttributes = ['src'];
  constructor() {
    super(); this._attached=false; this.attachShadow({mode:'open'}); this.pointers=new Map(); this.zoom=1;
    this.shadowRoot.innerHTML=`<style>:host{display:block;min-height:300px;position:relative}svg{width:100%;height:100%;position:absolute;touch-action:none;user-select:none}.transit-station,.transit-line{cursor:pointer}.transit-station:focus{stroke:#0077ff}.muted{opacity:.15}.hidden{display:none}.error{padding:1em;color:#a00}</style><div class="viewport"></div>`;
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
    this.svg.addEventListener('click',e=>{if(!this.dragged)this.interaction(e,'click',this.pressTarget||e.target);this.pressTarget=null;});
    this.svg.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();this.interaction(e,'click');}});
    this.svg.addEventListener('pointerover',e=>{this.interaction(e,'hover'); const id=e.target.closest('[data-line-id]')?.dataset.lineId;if(id)this.highlight(id);});
    this.svg.addEventListener('pointerout',()=>this.highlight(null));
    this.updateLabels(); this.dispatchEvent(new CustomEvent('map-load',{detail:layout,bubbles:true,composed:true}));
  }
  point(x,y) { const point=new DOMPoint(x,y); return point.matrixTransform(this.svg.getScreenCTM().inverse()); }
  scale(factor,x,y) {
    const next=Math.min(this.options.max_zoom,Math.max(this.options.min_zoom,this.zoom*factor)); factor=next/this.zoom;
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
  highlight(id) {for(const line of this.svg.querySelectorAll('.transit-line'))line.classList.toggle('muted',id!==null && line.dataset.lineId!==id);}
  interaction(event,action,origin=event.target) {
    const target=origin.closest('[data-station-id],[data-line-id]');if(!target)return;
    const station=target.dataset.stationId;const type=station?'station':'line';const id=station||target.dataset.lineId;
    const item=(station?this.layout.nodes:this.layout.lines).find(item=>item.id===id);
    this.dispatchEvent(new CustomEvent(`${type}-${action}`,{detail:{id,[type]:item,originalEvent:event},bubbles:true,composed:true}));
  }
  reset() {const v=this.svg?.viewBox.baseVal;if(!v)return;[v.x,v.y,v.width,v.height]=this.initial;this.zoom=1;this.updateLabels();}
}
if(!customElements.get('transit-map'))customElements.define('transit-map',TransitMap);
