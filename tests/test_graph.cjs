const {test} = require('node:test');
const assert = require('node:assert/strict');
const {build} = require('../web/graph.js');

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
