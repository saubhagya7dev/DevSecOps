/* Deterministic repository graph: containment and citation links, never invented imports. */
(function (root) {
  'use strict';
  const colors = ['#ef9d43','#ec797c','#90a9ff','#bf96ee','#8bdca7','#e88cc1'];
  const hash = value => [...value].reduce((n,c) => ((n * 31 + c.charCodeAt(0)) >>> 0), 17);
  function build(artifacts = {}, events = []) {
    const repo = artifacts.repository || {}, read = new Set((repo.files || []).map(f => f.path));
    const discovered = events.filter(e => e.title === 'Read repository file').map(e => e.detail);
    discovered.forEach(p => read.add(p));
    const paths = [...new Set([...read, ...(repo.tree_paths || [])])].filter(p => typeof p === 'string').slice(0, 160);
    const groups = [...new Set(paths.map(p => p.includes('/') ? p.split('/')[0] : 'Root files'))];
    const nodes = [], edges = [], byId = new Map();
    function add(node) { if (!byId.has(node.id)) { nodes.push(node); byId.set(node.id,node); } return byId.get(node.id); }
    if(paths.length) add({id:'repository',label:repo.name?.split('/').pop()||'Repository',type:'repository',group:0,inspected:true});
    groups.forEach((group, i) => {add({id:'dir:'+group,label:group,type:'directory',group:i,inspected:true});edges.push({from:'repository',to:'dir:'+group,kind:'structure'});});
    paths.forEach(path => {
      const group = groups.indexOf(path.includes('/') ? path.split('/')[0] : 'Root files');
      add({id:'file:'+path,label:path.split('/').pop(),path,type:'file',group,inspected:read.has(path)});
      edges.push({from:'dir:'+groups[group],to:'file:'+path,kind:'structure'});
    });
    (artifacts.profile?.observations || []).forEach(o => {
      const file = byId.get('file:'+o.path); if (!file) return;
      add({id:'obs:'+o.id,label:o.id,type:'observation',observation:o,group:file.group,inspected:true});
      edges.push({from:file.id,to:'obs:'+o.id,kind:'evidence'});
    });
    if ((artifacts.profile?.technologies || []).length) add({id:'tech-group',label:'Dependencies',type:'directory',group:groups.length,inspected:true});
    (artifacts.profile?.technologies || []).slice(0,16).forEach((t,i) => {
      const id='tech:'+i; add({id,label:t.name,type:'technology',technology:t,group:groups.length,inspected:true});
      edges.push({from:'tech-group',to:id,kind:'group'});
      (t.evidence_ids || []).forEach(e => {if (byId.has('obs:'+e)) edges.push({from:'obs:'+e,to:id,kind:'evidence'});});
    });
    const sourceById = new Map((artifacts.research?.sources || []).map(s => [s.id,s]));
    (artifacts.research?.incidents || []).slice(0,8).forEach((incident,i) => {
      const source=sourceById.get(incident.source_id); if (!source) return;
      add({id:'source:'+incident.id,label:source.id,type:'source',source,incident,group:groups.length+((artifacts.profile?.technologies||[]).length?1:0),inspected:true});
      (artifacts.review?.findings || []).filter(f => f.incident_ids.includes(incident.id)).forEach(f => f.evidence_ids.forEach(e => {
        if (byId.has('obs:'+e)) edges.push({from:'obs:'+e,to:'source:'+incident.id,kind:'evidence',finding:f});
      }));
    });
    if ((artifacts.profile?.technologies || []).length) groups.push('Dependencies');
    if (nodes.some(n=>n.type==='source')) groups.push('External evidence');
    const advisoryGroup=groups.length;
    (artifacts.research?.advisories||[]).slice(0,24).forEach((advisory,i)=>{
      const id='advisory:'+i;
      add({id,label:advisory.identifiers?.find(x=>x.startsWith('CVE-'))||advisory.id,type:'advisory',advisory,group:advisoryGroup,inspected:true,cvss:validScore(advisory.cvss_score)});
      nodes.filter(n=>n.type==='technology'&&normalizePackage(n.label)===normalizePackage(advisory.package?.name||'')).forEach(n=>edges.push({from:n.id,to:id,kind:'advisory'}));
    });
    if(nodes.some(n=>n.type==='advisory'))groups.push('Advisories');
    const components=artifacts.profile?.components||[];
    nodes.forEach(n=>{
      const evidence=n.observation?[n.observation.id]:n.technology?.evidence_ids||
        (n.type==='file'?(artifacts.profile?.observations||[]).filter(o=>o.path===n.path).map(o=>o.id):[]);
      const cited=components.filter(c=>(c.evidence_ids||[]).some(id=>evidence.includes(id))).map(c=>c.name);
      n.layer=cited.length?cited.join(' + '):n.type==='advisory'?'External advisories':n.type==='source'?'External evidence':n.type==='repository'?'Repository':'Unmapped';
    });
    const hubs = new Map();
    groups.forEach((g,i) => {const angle = i * 2.39996 - 1.3, radius=groups.length===1?0:130+Math.min(i,6)*15; hubs.set(i,{x:465+Math.cos(angle)*radius*1.25,y:258+Math.sin(angle)*radius*.8});});
    nodes.forEach(n => {
      const h=hubs.get(n.group)||{x:780,y:360}, seed=hash(n.id), a=(seed%6283)/1000, r=24+(seed%95);
      n.x=h.x+(['directory','repository'].includes(n.type)?0:Math.cos(a)*r); n.y=h.y+(['directory','repository'].includes(n.type)?0:Math.sin(a)*r*.8);
      n.color=colors[n.group%colors.length]; n.radius=n.type==='repository'?16:n.type==='directory'?13:['technology','advisory'].includes(n.type)?6:n.type==='file'?(n.inspected?4.6:3.2):5;
    });
    // Settle overlapping circles without animating or suggesting unobserved activity.
    for(let step=0;step<65;step++) for(let i=0;i<nodes.length;i++) for(let j=i+1;j<nodes.length;j++) {
      const a=nodes[i],b=nodes[j],dx=b.x-a.x||.1,dy=b.y-a.y||.1,d=Math.hypot(dx,dy),min=a.radius+b.radius+9;
      if(d<min){const push=(min-d)*.22;a.x-=dx/d*push;a.y-=dy/d*push;b.x+=dx/d*push;b.y+=dy/d*push;}
    }
    if(nodes.length){const minX=Math.min(...nodes.map(n=>n.x)),maxX=Math.max(...nodes.map(n=>n.x)),minY=Math.min(...nodes.map(n=>n.y)),maxY=Math.max(...nodes.map(n=>n.y));
    nodes.forEach(n=>{n.x=45+(n.x-minX)*825/Math.max(1,maxX-minX);n.y=25+(n.y-minY)*340/Math.max(1,maxY-minY);});}
    return {nodes,edges,groups,omitted:[...new Set(repo.tree_paths||[])].filter(p=>!paths.includes(p)).length,read:read.size};
  }
  const validScore=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=10?value:null;
  const layerColor=name=>colors[hash(name||'Unmapped')%colors.length];
  const normalizePackage=value=>value.toLowerCase().replace(/[-_. ]/g,'');
  const severity=value=>value===null||value===undefined?'Unscored':value>=9?'Critical':value>=7?'High':value>=4?'Medium':value>0?'Low':'Clean';
  const heat={Critical:'#f36478',High:'#f29b60',Medium:'#e5c46b',Low:'#90a9ff',Clean:'#8bdca7',Unscored:'#a3a3ad'};
  function filter(model,settings={}){
    const query=(settings.query||'').toLowerCase();
    let nodes=model.nodes.filter(n=>
      (settings.mode==='evidence'||!['observation','source'].includes(n.type))&&
      (!settings.inspected||n.inspected||n.type==='directory')&&
      (!query||[n.label,n.path,n.layer,model.groups[n.group],...(n.advisory?.identifiers||[]),...(n.incident?.identifiers||[])].filter(Boolean).join(' ').toLowerCase().includes(query))&&
      (!settings.severities||settings.severities.includes(severity(validScore(n.cvss))))&&
      (!(settings.minScore>0)||(validScore(n.cvss)!==null&&n.cvss>=settings.minScore)));
    let ids=new Set(nodes.map(n=>n.id));
    let edges=model.edges.filter(e=>ids.has(e.from)&&ids.has(e.to));
    if(settings.orphans===false){const connected=new Set(edges.flatMap(e=>[e.from,e.to]));nodes=nodes.filter(n=>connected.has(n.id));ids=new Set(nodes.map(n=>n.id));edges=edges.filter(e=>ids.has(e.from)&&ids.has(e.to));}
    return {nodes,edges,groups:model.groups};
  }
  function spotlight(model,id){
    const ids=new Set(id?[id]:[]);
    model.edges.filter(e=>e.from===id||e.to===id).forEach(e=>{ids.add(e.from);ids.add(e.to);});
    const paths=new Set(model.edges.filter(e=>e.finding&&(ids.has(e.from)||ids.has(e.to))).map(e=>e.finding.id));
    model.edges.filter(e=>e.finding&&paths.has(e.finding.id)).forEach(e=>{ids.add(e.from);ids.add(e.to);});
    model.edges.filter(e=>e.kind==='evidence'&&(ids.has(e.from)||ids.has(e.to))).forEach(e=>{ids.add(e.from);ids.add(e.to);});
    return ids;
  }
  function step(model,options={},alpha=1){
    const charge=options.charge??5000,gravity=options.gravity??.007,distance=options.distance??90,damping=options.damping??.82;
    const nodes=model.nodes,byId=new Map(nodes.map(n=>[n.id,n]));
    nodes.forEach(n=>{n.vx=(n.vx||0)+(480-n.x)*gravity*alpha;n.vy=(n.vy||0)+(200-n.y)*gravity*alpha;});
    for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
      const a=nodes[i],b=nodes[j],dx=b.x-a.x||.01,dy=b.y-a.y||.01,r2=Math.max(225,dx*dx+dy*dy);
      const force=charge*alpha/(r2*Math.sqrt(r2)),fx=dx*force,fy=dy*force;
      a.vx-=fx;a.vy-=fy;b.vx+=fx;b.vy+=fy;
    }
    model.edges.forEach(e=>{const a=byId.get(e.from),b=byId.get(e.to);if(!a||!b)return;
      const dx=b.x-a.x,dy=b.y-a.y,r=Math.max(.1,Math.hypot(dx,dy)),f=(r-distance)*.016*alpha/r;
      a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f;
    });
    let energy=0;
    nodes.forEach(n=>{n.vx=Math.max(-12,Math.min(12,n.vx*damping));n.vy=Math.max(-12,Math.min(12,n.vy*damping));
      if(n.fx!==undefined){n.x=n.fx;n.y=n.fy;n.vx=n.vy=0;}else{n.x+=n.vx;n.y+=n.vy;}
      energy+=n.vx*n.vx+n.vy*n.vy;
    });
    return energy/Math.max(1,nodes.length);
  }
  class CanvasView {
    constructor(canvas,onSelect,onHover){
      this.canvas=canvas;this.ctx=canvas.getContext('2d');this.onSelect=onSelect;this.onHover=onHover;
      this.model={nodes:[],edges:[],groups:[]};this.settings={charge:5000,gravity:.007,distance:90,damping:.82,nodeScale:1,linkWidth:1,labels:'all',colorMode:'architecture',pulses:false};
      this.camera={x:0,y:0,z:1};this.pointers=new Map();this.hover=null;this.selected=null;this.alpha=0;this.frame=0;this.visible=true;this.autoFit=true;
      this.motion=matchMedia('(prefers-reduced-motion: reduce)');
      this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(canvas);window.addEventListener('resize',()=>this.resize());
      this.intersectionObserver=new IntersectionObserver(entries=>{this.visible=entries[0].isIntersecting;if(this.visible)this.wake();});this.intersectionObserver.observe(canvas);
      document.addEventListener('visibilitychange',()=>{if(!document.hidden)this.wake();});
      this.motion.addEventListener('change',()=>this.wake());
      canvas.addEventListener('wheel',e=>{e.preventDefault();this.zoom(Math.exp(-e.deltaY*.0015),this.point(e));},{passive:false});
      canvas.addEventListener('pointerdown',e=>this.down(e));
      canvas.addEventListener('pointermove',e=>this.move(e));
      canvas.addEventListener('pointerup',e=>this.up(e));
      canvas.addEventListener('pointercancel',e=>this.up(e,true));
      canvas.addEventListener('lostpointercapture',e=>{if(this.pointers.has(e.pointerId))this.up(e,true);});
      canvas.addEventListener('pointerleave',()=>{if(!this.pointers.size){this.hover=null;this.onHover(null);this.draw();}});
      canvas.addEventListener('keydown',e=>{
        if(['+','=','-','0','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){
          e.preventDefault();if(e.key==='0')this.fit();else if(['+','=','-'].includes(e.key))this.zoom(e.key==='-'?.8:1.25);
          else{this.autoFit=false;this.camera.x+=e.key==='ArrowLeft'?30:e.key==='ArrowRight'?-30:0;this.camera.y+=e.key==='ArrowUp'?30:e.key==='ArrowDown'?-30:0;this.draw();}
        }
      });
    }
    point(e){const r=this.canvas.getBoundingClientRect();return{x:e.clientX-r.left,y:e.clientY-r.top};}
    world(p){return{x:(p.x-this.camera.x)/this.camera.z,y:(p.y-this.camera.y)/this.camera.z};}
    resize(){
      const r=this.canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;
      if(this.fitted){this.camera.x+=(r.width-this.width)/2;this.camera.y+=(r.height-this.height)/2;}
      this.width=r.width;this.height=r.height;this.dpr=dpr;
      this.canvas.width=Math.round(r.width*dpr);this.canvas.height=Math.round(r.height*dpr);
      this.canvas.dataset.dpr=String(dpr);if((!this.fitted||this.autoFit)&&this.model.nodes.length)this.fit();else this.draw();
    }
    setModel(model){
      const previous=new Map(this.model.nodes.map(n=>[n.id,n]));
      model.nodes=model.nodes.map(n=>{const old=previous.get(n.id);if(old&&old!==n)Object.assign(n,{x:old.x,y:old.y,vx:old.vx||0,vy:old.vy||0,...(old.fx!==undefined?{fx:old.fx,fy:old.fy}:{})});return n;});
      this.pointers.forEach(p=>{if(p.node)p.node=model.nodes.find(n=>n.id===p.node.id)||null;});
      this.model=model;if(this.hover&&!model.nodes.some(n=>n.id===this.hover)){this.hover=null;this.onHover(null);this.canvas.classList.remove('over-node');}this.reheat();if(!this.fitted&&model.nodes.length)this.fit();
    }
    reset(){this.model={nodes:[],edges:[],groups:[]};this.fitted=false;this.pointers.clear();this.pinch=null;this.hover=null;this.selected=null;this.alpha=0;this.autoFit=true;this.draw();}
    update(settings,selected){this.settings={...this.settings,...settings};this.selected=selected;this.draw();}
    fit(smooth=false){
      const nodes=this.model.nodes;if(!nodes.length||!this.width)return;
      const minX=Math.min(...nodes.map(n=>n.x-n.radius*2)),maxX=Math.max(...nodes.map(n=>n.x+n.radius*2));
      const minY=Math.min(...nodes.map(n=>n.y-n.radius*2)),maxY=Math.max(...nodes.map(n=>n.y+n.radius*2));
      const z=Math.max(.1,Math.min(2.5,Math.min((this.width-70)/Math.max(120,maxX-minX),(this.height-65)/Math.max(100,maxY-minY))));
      const next={z,x:this.width/2-(minX+maxX)/2*z,y:this.height/2-(minY+maxY)/2*z};
      if(smooth){for(const k of ['x','y','z'])this.camera[k]+=(next[k]-this.camera[k])*.25;}else{this.camera=next;this.autoFit=true;}
      this.fitted=true;this.draw();
    }
    zoom(factor,p={x:this.width/2,y:this.height/2}){
      this.autoFit=false;const anchor=this.world(p),z=Math.max(.08,Math.min(6,this.camera.z*factor));
      this.camera={z,x:p.x-anchor.x*z,y:p.y-anchor.y*z};this.draw();
    }
    hit(point){const p=this.world(point);return [...this.model.nodes].reverse().find(n=>Math.hypot(n.x-p.x,n.y-p.y)<n.radius*this.settings.nodeScale+6/this.camera.z);}
    down(e){
      if(e.button!==0&&e.pointerType==='mouse')return;
      this.autoFit=false;this.canvas.focus({preventScroll:true});const p=this.point(e),node=this.hit(p);
      this.pointers.set(e.pointerId,{...p,start:p,node,pan:{...this.camera},moved:false});this.canvas.setPointerCapture(e.pointerId);
      if(this.pointers.size===2){
        this.pointers.forEach(v=>{if(v.node){delete v.node.fx;delete v.node.fy;}v.node=null;});
        const [a,b]=[...this.pointers.values()],middle={x:(a.x+b.x)/2,y:(a.y+b.y)/2};
        this.pinch={distance:Math.max(1,Math.hypot(a.x-b.x,a.y-b.y)),z:this.camera.z,anchor:this.world(middle)};
      }else if(node){const w=this.world(p);this.pointers.get(e.pointerId).offset={x:node.x-w.x,y:node.y-w.y};node.fx=node.x;node.fy=node.y;this.onSelect(node.id);this.reheat();}
      this.canvas.dataset.gesture=node?'node-drag':'pan';
    }
    move(e){
      const p=this.point(e),pointer=this.pointers.get(e.pointerId);
      if(!pointer){const n=this.hit(p);if(this.hover!==(n?.id||null)){this.hover=n?.id||null;this.canvas.classList.toggle('over-node',Boolean(n));this.onHover(n||null);this.draw();}return;}
      pointer.x=p.x;pointer.y=p.y;pointer.moved ||= Math.hypot(p.x-pointer.start.x,p.y-pointer.start.y)>3;
      if(this.pointers.size>=2&&this.pinch){
        const [a,b]=[...this.pointers.values()],middle={x:(a.x+b.x)/2,y:(a.y+b.y)/2};
        const z=Math.max(.08,Math.min(6,this.pinch.z*Math.hypot(a.x-b.x,a.y-b.y)/this.pinch.distance));
        this.camera={z,x:middle.x-this.pinch.anchor.x*z,y:middle.y-this.pinch.anchor.y*z};this.canvas.dataset.gesture='pinch';
      }else if(pointer.node){const w=this.world(p);pointer.node.fx=w.x+(pointer.offset?.x||0);pointer.node.fy=w.y+(pointer.offset?.y||0);pointer.node.x=pointer.node.fx;pointer.node.y=pointer.node.fy;this.reheat();}
      else{this.camera.x=pointer.pan.x+p.x-pointer.start.x;this.camera.y=pointer.pan.y+p.y-pointer.start.y;}
      this.draw();
    }
    up(e,cancelled=false){
      const pointer=this.pointers.get(e.pointerId);if(!pointer)return;
      if(pointer.node){delete pointer.node.fx;delete pointer.node.fy;this.reheat();}
      this.pointers.delete(e.pointerId);this.pinch=null;
      if(this.canvas.hasPointerCapture(e.pointerId))this.canvas.releasePointerCapture(e.pointerId);
      this.pointers.forEach(v=>{v.start={x:v.x,y:v.y};v.pan={...this.camera};});
      this.canvas.dataset.gesture='idle';this.draw();
    }
    reheat(){this.alpha=this.model.nodes.length ? .8 : 0;this.ticks=0;this.wake();}
    wake(){if(!this.frame&&this.visible&&!document.hidden)this.frame=requestAnimationFrame(t=>this.tick(t));}
    tick(time){
      this.frame=0;if(!this.visible||document.hidden)return;
      const dragging=[...this.pointers.values()].some(p=>p.node);
      if(this.alpha>.002&&this.model.nodes.length){
        const energy=step(this.model,this.settings,this.alpha);this.alpha*=.975;this.ticks++;
        if(!dragging&&(this.ticks>420||(energy<.0004&&this.ticks>45)))this.alpha=0;
      }
      if(this.autoFit&&this.ticks%6===0&&this.alpha>.002)this.fit(true);
      this.draw(time);this.canvas.dataset.simulation=this.alpha>.002?'settling':'idle';
      const pulses=this.settings.pulses&&!this.motion.matches&&this.model.edges.some(e=>e.finding);
      if(this.alpha>.002||dragging||pulses)this.wake();
    }
    draw(time=performance.now()){
      const ctx=this.ctx;if(!this.width||!ctx)return;
      ctx.setTransform(this.dpr,0,0,this.dpr,0,0);ctx.clearRect(0,0,this.width,this.height);
      ctx.translate(this.camera.x,this.camera.y);ctx.scale(this.camera.z,this.camera.z);
      const byId=new Map(this.model.nodes.map(n=>[n.id,n]));
      const active=this.hover?spotlight(this.model,this.hover):null;
      this.model.edges.forEach((e,i)=>{
        const a=byId.get(e.from),b=byId.get(e.to);if(!a||!b)return;
        const highlighted=active&&active.has(a.id)&&active.has(b.id);
        ctx.globalAlpha=active?(highlighted ? .8 : .055):e.kind==='structure'||e.kind==='group' ? .26 : .42;
        ctx.strokeStyle=highlighted?'#d0c3eb':e.finding?'#d9a2cc':e.kind==='advisory'?'#b49dcd':'#777780';
        ctx.lineWidth=this.settings.linkWidth/this.camera.z;ctx.setLineDash(['evidence','advisory'].includes(e.kind)?[4/this.camera.z,5/this.camera.z]:[]);
        ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();ctx.setLineDash([]);
        if(e.finding&&this.settings.pulses&&!this.motion.matches){
          const t=(time/2200+i*.17)%1;ctx.globalAlpha=active&&!highlighted ? .08 : .9;ctx.fillStyle='#e5c6f3';
          ctx.beginPath();ctx.arc(a.x+(b.x-a.x)*t,a.y+(b.y-a.y)*t,2/this.camera.z,0,Math.PI*2);ctx.fill();
        }
      });
      this.model.nodes.forEach(n=>{
        const focused=n.id===this.hover,selected=n.id===this.selected,r=n.radius*this.settings.nodeScale;
        const color=this.settings.colorMode==='heatmap'?heat[severity(validScore(n.cvss))]:this.settings.colorMode==='layers'?layerColor(n.layer):n.color;
        ctx.globalAlpha=active&&!active.has(n.id) ? .13 : n.inspected ? 1 : .45;
        const halo=ctx.createRadialGradient(n.x,n.y,0,n.x,n.y,r*3.4);
        halo.addColorStop(0,color+'80');halo.addColorStop(.45,color+'27');halo.addColorStop(1,color+'00');
        ctx.fillStyle=halo;ctx.beginPath();ctx.arc(n.x,n.y,r*3.4,0,Math.PI*2);ctx.fill();
        ctx.fillStyle=color;ctx.strokeStyle=selected||focused?'#f0edf5':color;ctx.lineWidth=1/this.camera.z;
        ctx.beginPath();ctx.arc(n.x,n.y,r,0,Math.PI*2);ctx.fill();ctx.stroke();
        if(selected){ctx.strokeStyle='#eee';ctx.lineWidth=1/this.camera.z;ctx.beginPath();ctx.arc(n.x,n.y,r+4/this.camera.z,0,Math.PI*2);ctx.stroke();}
        const label=this.settings.labels==='all'||focused||selected||(this.settings.labels==='large'&&n.radius>=10);
        if(label){
          ctx.font=`${11/this.camera.z}px "Segoe UI",sans-serif`;ctx.fillStyle='#e0dce6';ctx.strokeStyle='#0b0b0b';ctx.lineWidth=3/this.camera.z;
          const text=n.label.length>32?n.label.slice(0,30)+'…':n.label;const x=n.x+r+6/this.camera.z,y=n.y+4/this.camera.z;
          ctx.strokeText(text,x,y);ctx.fillText(text,x,y);
        }
      });
      ctx.globalAlpha=1;this.canvas.dataset.zoom=this.camera.z.toFixed(3);
    }
  }
  root.RepoGraph = {build,colors,validScore,severity,heat,filter,spotlight,step,layerColor,CanvasView};
  if (typeof module !== 'undefined') module.exports = root.RepoGraph;
})(typeof window !== 'undefined' ? window : globalThis);
