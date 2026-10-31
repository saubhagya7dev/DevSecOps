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
    const hubs = new Map();
    groups.forEach((g,i) => {const angle = i * 2.39996 - 1.3, radius=groups.length===1?0:130+Math.min(i,6)*15; hubs.set(i,{x:465+Math.cos(angle)*radius*1.25,y:258+Math.sin(angle)*radius*.8});});
    nodes.forEach(n => {
      const h=hubs.get(n.group)||{x:780,y:360}, seed=hash(n.id), a=(seed%6283)/1000, r=24+(seed%95);
      n.x=h.x+(['directory','repository'].includes(n.type)?0:Math.cos(a)*r); n.y=h.y+(['directory','repository'].includes(n.type)?0:Math.sin(a)*r*.8);
      n.color=colors[n.group%colors.length]; n.radius=n.type==='repository'?16:n.type==='directory'?13:n.type==='technology'?6:n.type==='file'?(n.inspected?4.6:3.2):5;
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
  root.RepoGraph = {build,colors};
  if (typeof module !== 'undefined') module.exports = root.RepoGraph;
})(typeof window !== 'undefined' ? window : globalThis);
