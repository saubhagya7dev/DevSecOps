const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const app = fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
const code = app.slice(app.indexOf('const Sunrise ='),app.indexOf('// Landing-only role emphasis;'));
const scene = vm.runInNewContext(code+'\nSunrise;');
test('sun remains attached to the same symmetric curved planetary horizon',()=>{
  const center=scene.horizonAt(500,1000,700);
  assert.ok(scene.horizonAt(160,1000,700)>center);
  assert.equal(scene.horizonAt(160,1000,700),scene.horizonAt(840,1000,700));
  // The renderer uses a quadratic with the same endpoints and control point.
  for(const t of [0,.16,.5,.84,1]) {
    const bezier=(1-t)**2*(.87*700)+2*(1-t)*t*(.64*700)+t*t*(.87*700);
    assert.ok(Math.abs(scene.horizonAt(t*1000,1000,700)-bezier)<1e-9);
  }
});
test('star texture is deterministic, irregular, bounded, and varies brightness',()=>{
  const stars=scene.starsFor(1000,700);
  assert.equal(JSON.stringify(stars),JSON.stringify(scene.starsFor(1000,700)));
  assert.ok(stars.length>200&&stars.length<300);
  assert.ok(stars.every(s=>s.x>=0&&s.x<1000&&s.y>=0&&s.y<700&&s.radius<1.4));
  assert.ok(stars.some(s=>s.alpha>.25)&&stars.some(s=>s.alpha<.1));
  assert.ok(new Set(stars.map(s=>s.color)).size>=4);
  assert.ok(stars.filter(s=>s.glowing).length<stars.length*.3);
  assert.ok(stars.some(s=>s.radius>1)&&stars.some(s=>s.radius<.3));
  assert.equal(scene.starsFor(10000,10000).length,700);
});
function harness(reduced=false) {
  const frames=[],translations=[];let time=0,draws=0;
  const gradient=()=>({addColorStop(){}});
  const base={setTransform(){},fillRect(){},beginPath(){},arc(){},fill(){},save(){},restore(){},
    scale(){},moveTo(){},lineTo(){},closePath(){},quadraticCurveTo(){},stroke(){},clip(){},
    createLinearGradient:gradient,createRadialGradient:gradient,translate(){},drawImage(){}};
  const ctx={...base,translate:(x,y)=>translations.push([x,y]),drawImage:()=>draws++};
  const canvas={getContext:()=>ctx,getBoundingClientRect:()=>({width:1000,height:700})};
  const motion={matches:reduced,addEventListener(){}};
  let visibility;
  const sandbox={matchMedia:()=>motion,devicePixelRatio:1,
    requestAnimationFrame:fn=>{frames.push(fn);return frames.length;},
    ResizeObserver:class {observe(){}},
    IntersectionObserver:class {constructor(fn){visibility=fn;}observe(){}},
    window:{addEventListener(){}},
    document:{hidden:false,addEventListener(){},createElement:()=>({getContext:()=>({...base})})}};
  const api=vm.runInNewContext(code+'\nSunrise;',sandbox).create(canvas);
  function flush(){let count=0;while(frames.length){if(++count>500)throw Error('Animation did not settle');frames.shift()(time+=16);}return count;}
  flush();
  return {api,flush,frames,translations,motion,get draws(){return draws;},visibility:(value)=>visibility([{isIntersecting:value}])};
}
test('role transition follows the curve, settles, and leaves no idle animation',()=>{
  const h=harness();h.api.focus(.16);assert.ok(h.flush()>1);
  const [x,y]=h.translations.at(-1);
  assert.ok(Math.abs(x-160)<.001);
  assert.ok(Math.abs(y-(scene.horizonAt(160,1000,700)-1))<.001);
  assert.equal(h.frames.length,0);
});
test('reduced motion snaps in one frame and offscreen scenes do not redraw',()=>{
  const h=harness(true);h.api.focus(.84);assert.equal(h.flush(),1);
  assert.equal(h.translations.at(-1)[0],840);
  h.visibility(false);const before=h.draws;h.api.focus(.16);
  assert.equal(h.flush(),0);assert.equal(h.draws,before);
  h.visibility(true);assert.equal(h.flush(),1);assert.equal(h.translations.at(-1)[0],160);
});

test('star hover has a bounded soft falloff and clears without an idle loop',()=>{
  const star={x:100,y:100};
  assert.equal(scene.starInfluence(star,null),0);
  assert.equal(scene.starInfluence(star,{x:100,y:100}),1);
  assert.equal(scene.starInfluence(star,{x:175,y:100}),0);
  assert.equal(scene.starInfluence(star,{x:137.5,y:100}),.25);
  const h=harness();h.api.hover({x:100,y:100});assert.equal(h.flush(),1);
  h.api.hover(null);assert.equal(h.flush(),1);assert.equal(h.frames.length,0);
});


test('only three eligible sky stars can receive strong pointer illumination',()=>{
  const stars=Array.from({length:10},(_,i)=>({x:100+i,y:100,glowing:true,hoverRange:50}));
  stars.push({x:100,y:100,glowing:false,hoverRange:100});
  stars.push({x:100,y:690,glowing:true,hoverRange:1000});
  const selected=scene.nearbyStars(stars,{x:100,y:100},1000,700);
  assert.equal(selected.length,3);assert.equal(selected[0].x,100);
  assert.ok(selected.every(s=>s.glowing&&s.y===100));
  assert.equal(scene.starInfluence({...stars[0],hoverRange:32},{x:145,y:100}),0);
  assert.ok(scene.starInfluence({...stars[0],hoverRange:80},{x:145,y:100})>0);
});
