const {test} = require('node:test');
const assert = require('node:assert/strict');
const {build, step, filter, spotlight, severity, validScore, CanvasView} = require('../web/graph.js');

const repo = {name:'owner/repo', tree_paths:['api/main.py','lib/client.py','README.md'],
  files:[{path:'api/main.py',content:'import client'}]};
const profile = {observations:[{id:'E1',path:'api/main.py',claim:'Uses an HTTP client'}],
  technologies:[{name:'HTTP client',evidence_ids:['E1']}]};

test('structure comes from file paths, never guessed imports', () => {
  const graph = build({repository:repo});
  assert(graph.edges.some(e=>e.from==='dir:api' && e.to==='file:api/main.py'));
  assert(!graph.edges.some(e=>e.from==='file:api/main.py' && e.to==='file:lib/client.py'));
  assert.equal(graph.nodes.find(n=>n.path==='lib/client.py').inspected,false);
});

test('actual preparation events reveal inspected files before artifacts arrive', () => {
  const graph=build({},[{title:'Read repository file',detail:'api/main.py'},
    {title:'Searching primary sources',detail:'not-a-file'}]);
  assert.equal(graph.read,1);
  assert(graph.nodes.some(n=>n.path==='api/main.py' && n.inspected));
  assert(!graph.nodes.some(n=>n.path==='not-a-file'));
});

test('technology associations require existing cited observations', () => {
  const graph=build({repository:repo,profile:{...profile,
    technologies:[{name:'Client',evidence_ids:['E1','E999']} ]}});
  assert(graph.edges.some(e=>e.from==='obs:E1'&&e.to==='tech:0'&&e.kind==='evidence'));
  assert(!graph.edges.some(e=>e.from==='obs:E999'));
});

test('external reports do not imply a match to repository files', () => {
  const graph=build({repository:repo,profile,research:{sources:[{id:'S1',title:'Report'}],
    incidents:[{id:'I1',source_id:'S1'}]}});
  assert(graph.nodes.some(n=>n.id==='source:I1'));
  assert(!graph.edges.some(e=>e.to==='source:I1'));
});

test('accepted findings connect only their cited observation and incident', () => {
  const graph=build({repository:repo,profile,research:{sources:[{id:'S1'}],
    incidents:[{id:'I1',source_id:'S1'}]},review:{findings:[{
      id:'F1',incident_ids:['I1'],evidence_ids:['E1','E999']}]}});
  assert(graph.edges.some(e=>e.from==='obs:E1' && e.to==='source:I1' && e.finding.id==='F1'));
  const ids=new Set(graph.nodes.map(n=>n.id));
  assert(graph.edges.every(e=>ids.has(e.from)&&ids.has(e.to)));
});

test('large trees are bounded while inspected files take priority', () => {
  const graph=build({repository:{...repo,tree_paths:Array.from({length:300},(_,i)=>'dir/'+i+'.py')}});
  assert.equal(graph.nodes.filter(n=>n.type==='file').length,160);
  assert(graph.nodes.some(n=>n.path==='api/main.py'));
  assert(graph.omitted>0);
});

test('empty and populated layouts are stable and finite, including source-only evidence', () => {
  assert.deepEqual(build().nodes,[]);
  const artifacts={repository:repo,profile,research:{sources:[{id:'S1'}],incidents:[{id:'I1',source_id:'S1'}]}};
  const graph=build(artifacts);
  assert.deepEqual(graph,build(artifacts));
  assert(graph.nodes.every(n=>Number.isFinite(n.x)&&Number.isFinite(n.y)&&n.color));
  const external=build({research:artifacts.research});
  assert.equal(external.groups[external.nodes[0].group],'External evidence');
});


test('CVSS boundaries preserve zero and never classify absent scores as clean', () => {
  assert.deepEqual([null,0,.1,3.9,4,6.9,7,8.9,9,10].map(severity),
    ['Unscored','Clean','Low','Low','Medium','Medium','High','High','Critical','Critical']);
  for(const value of [undefined,null,'9.8','CVSS:3.1/AV:N',true,NaN,Infinity,-1,11]) assert.equal(validScore(value),null);
});

test('CVEs are searchable and minimum scores exclude unscored nodes', () => {
  const model=build({repository:repo,research:{advisories:[{id:'G1',identifiers:['CVE-2026-12345'],cvss_score:9.8,package:{name:'client'}}]}});
  const matches=filter(model,{query:'cve-2026-12345',minScore:9});
  assert.equal(matches.nodes.length,1);assert.equal(matches.nodes[0].type,'advisory');
  assert(filter(model,{minScore:9}).nodes.every(n=>n.cvss>=9));
  assert.equal(filter(model,{severities:['Clean']}).nodes.length,0);
});

test('orphan filtering and disabled severity groups remove corresponding nodes', () => {
  const model={nodes:[{id:'a',label:'A',type:'file'},{id:'b',label:'B',type:'file'},{id:'orphan',label:'C',type:'file',cvss:9.8}],edges:[{from:'a',to:'b'}],groups:[]};
  assert.deepEqual(filter(model,{orphans:false}).nodes.map(n=>n.id),['a','b']);
  assert.deepEqual(filter(model,{severities:['Critical']}).nodes.map(n=>n.id),['orphan']);
});

test('hover spotlight includes direct neighbors and reviewer evidence chain only', () => {
  const model={edges:[{from:'file',to:'E1',kind:'evidence'},{from:'E1',to:'I1',kind:'evidence',finding:{id:'F1'}},{from:'unrelated',to:'other',kind:'structure'}]};
  assert.deepEqual([...spotlight(model,'file')].sort(),['E1','I1','file']);
});

test('repulsion is symmetric, fixed drag anchors stay put, and springs tug neighbors', () => {
  const pair={nodes:[{id:'a',x:100,y:100},{id:'b',x:120,y:100}],edges:[]};
  step(pair,{gravity:0,charge:5000,damping:1});
  assert(pair.nodes[0].x<100&&pair.nodes[1].x>120);
  assert(Math.abs(pair.nodes[0].vx+pair.nodes[1].vx)<1e-9);
  const linked={nodes:[{id:'a',x:100,y:100,fx:100,fy:100},{id:'b',x:400,y:100}],edges:[{from:'a',to:'b'}]};
  step(linked,{gravity:0,charge:0,distance:90});
  assert.equal(linked.nodes[0].x,100);assert(linked.nodes[1].x<400);
});

test('simulation settles and stays finite under strong forces and coincident nodes', () => {
  const model=build({repository:repo,profile});
  model.nodes[0].x=model.nodes[1].x;model.nodes[0].y=model.nodes[1].y;
  let energy;
  for(let i=0;i<500;i++)energy=step(model,{charge:15000,gravity:.04,distance:20,damping:.95},.8*Math.pow(.975,i));
  assert(model.nodes.every(n=>[n.x,n.y,n.vx,n.vy].every(Number.isFinite)));
  assert(energy<.05);
});

test('cursor zoom keeps the world point beneath the cursor anchored', () => {
  const view=Object.create(CanvasView.prototype);
  Object.assign(view,{camera:{x:10,y:20,z:1.5},width:800,height:400,draw(){}});
  const cursor={x:230,y:150},before=view.world(cursor);
  view.zoom(1.8,cursor);
  assert(Math.abs(view.world(cursor).x-before.x)<1e-9);
  assert(Math.abs(view.world(cursor).y-before.y)<1e-9);
});

test('two touch pointers scale around their midpoint and cancel without stuck pointers', () => {
  const view=Object.create(CanvasView.prototype),captured=new Set();
  Object.assign(view,{camera:{x:0,y:0,z:1},pointers:new Map(),canvas:{focus(){},dataset:{},setPointerCapture(id){captured.add(id);},hasPointerCapture(id){return captured.has(id);},releasePointerCapture(id){captured.delete(id);}},
    point(e){return{x:e.clientX,y:e.clientY};},hit(){return null;},draw(){},reheat(){}});
  view.down({pointerId:1,pointerType:'touch',clientX:100,clientY:100});
  view.down({pointerId:2,pointerType:'touch',clientX:200,clientY:100});
  const anchor=view.world({x:150,y:100});
  view.move({pointerId:2,clientX:300,clientY:100});
  assert.equal(view.camera.z,2);assert.deepEqual(view.world({x:200,y:100}),anchor);
  view.up({pointerId:1},true);view.up({pointerId:2},true);
  assert.equal(view.pointers.size,0);assert.equal(captured.size,0);assert.equal(view.pinch,null);
});


test('node dragging preserves grab offset, selects the node, and frees anchors on cancellation', () => {
  const view=Object.create(CanvasView.prototype),captured=new Set();
  const node={id:'drag',x:100,y:100,radius:8};let selected;
  Object.assign(view,{camera:{x:0,y:0,z:1},settings:{nodeScale:1},model:{nodes:[node]},pointers:new Map(),
    canvas:{focus(){},dataset:{},setPointerCapture(id){captured.add(id);},hasPointerCapture(id){return captured.has(id);},releasePointerCapture(id){captured.delete(id);}},
    point(e){return{x:e.clientX,y:e.clientY};},draw(){},reheat(){},onSelect(id){selected=id;}});
  view.down({pointerId:1,pointerType:'mouse',button:0,clientX:104,clientY:100});
  assert.equal(selected,'drag');assert.equal(node.x,100);
  view.move({pointerId:1,clientX:144,clientY:125});
  assert.equal(node.x,140);assert.equal(node.y,125);assert.equal(node.fx,140);
  view.up({pointerId:1},true);
  assert.equal(node.fx,undefined);assert.equal(node.fy,undefined);assert.equal(captured.size,0);
});


test('an empty or fully filtered graph does not keep the physics loop hot', () => {
  const view=Object.create(CanvasView.prototype);
  Object.assign(view,{model:{nodes:[]},alpha:1,wake(){}});
  view.reheat();assert.equal(view.alpha,0);
});


test('high-DPI resizing allocates a two-times backing store without changing CSS dimensions', () => {
  const previous=globalThis.window;
  try {
    globalThis.window={devicePixelRatio:2};
    const view=Object.create(CanvasView.prototype);
    Object.assign(view,{canvas:{getBoundingClientRect(){return{width:200,height:100};},dataset:{}},model:{nodes:[]},draw(){}});
    view.resize();
    assert.equal(view.canvas.width,400);assert.equal(view.canvas.height,200);
    assert.equal(view.width,200);assert.equal(view.height,100);assert.equal(view.dpr,2);
  } finally {if(previous===undefined)delete globalThis.window;else globalThis.window=previous;}
});


test('service layers and service-name searches require cited component associations', () => {
  const model=build({repository:repo,profile:{...profile,components:[{name:'API service',evidence_ids:['E1']}]}});
  assert.equal(model.nodes.find(n=>n.path==='api/main.py').layer,'API service');
  assert.equal(model.nodes.find(n=>n.path==='lib/client.py').layer,'Unmapped');
  const matches=filter(model,{query:'API service'});
  assert(matches.nodes.some(n=>n.path==='api/main.py'));
  assert(!matches.nodes.some(n=>n.path==='lib/client.py'));
});

test('auto-fit follows moving bounds every frame and renders only once per frame', () => {
  const originalDocument=globalThis.document;
  try {
    globalThis.document={hidden:false};
    const view=Object.create(CanvasView.prototype);let draws=0,wakes=0;
    Object.assign(view,{camera:{x:0,y:0,z:1},width:800,height:400,autoFit:true,
      model:{nodes:[{id:'a',x:400,y:200,radius:8}],edges:[]},settings:{pulses:false},
      motion:{matches:false},visible:true,pointers:new Map(),alpha:0,ticks:1,canvas:{dataset:{}},
      draw(){draws++;},wake(){wakes++;}});
    const positions=[];
    for(let i=0;i<5;i++){view.tick(16*(i+1));positions.push(view.camera.x);}
    assert.equal(draws,5);
    assert.equal(wakes,5);
    assert(positions.every((x,i)=>i===0||x!==positions[i-1]),'No six-frame camera plateaus');
    // Zoom/pan ownership remains respected while physics continues.
    view.autoFit=false;const camera={...view.camera};view.tick(96);
    assert.deepEqual(view.camera,camera);
  } finally {if(originalDocument===undefined)delete globalThis.document;else globalThis.document=originalDocument;}
});

test('metadata refreshes preserve cooling and positions; topology changes reheat', () => {
  const view=Object.create(CanvasView.prototype);let reheats=0;
  Object.assign(view,{model:{nodes:[],edges:[]},pointers:new Map(),fitted:true,hover:null,
    reheat(){reheats++;this.alpha=.8;this.ticks=0;},draw(){}});
  view.setModel({nodes:[{id:'a',x:100,y:200,radius:8}],edges:[]});
  view.alpha=.12;view.ticks=85;view.model.nodes[0].vx=.7;
  view.setModel({nodes:[{id:'a',x:900,y:900,radius:8,label:'New metadata'}],edges:[]});
  assert.equal(reheats,1);assert.equal(view.alpha,.12);assert.equal(view.ticks,85);
  assert.equal(view.model.nodes[0].x,100);assert.equal(view.model.nodes[0].vx,.7);
  view.setModel({nodes:[{id:'a'},{id:'b',x:300,y:200,radius:6}],edges:[{from:'a',to:'b',kind:'structure'}]});
  assert.equal(reheats,2);assert.equal(view.alpha,.8);
});
