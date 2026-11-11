const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
const code=source.slice(source.indexOf('const LuminousType ='),source.indexOf('LuminousType.mount();'));
const effects=vm.runInNewContext(code+'\nLuminousType;');
test('text spotlight follows smoothly and afterglow settles completely',()=>{
  const state={x:0,y:0,targetX:100,targetY:30,strength:0,targetStrength:1};
  assert.equal(effects.follow(state,16,false),true);
  assert.ok(state.x>0&&state.x<100);assert.ok(state.strength>0&&state.strength<1);
  state.targetStrength=0;
  for(let i=0;i<120;i++)effects.follow(state,16,false);
  assert.equal(state.strength,0);assert.equal(effects.follow(state,16,false),false);
});
test('reduced motion updates the text light immediately',()=>{
  const state={x:0,y:0,targetX:100,targetY:30,strength:0,targetStrength:1};
  assert.equal(effects.follow(state,16,true),false);
  assert.equal(state.x,100);assert.equal(state.y,30);assert.equal(state.strength,1);
});
test('spotlight uses existing text without duplicates and restores styles on exit',()=>{
  const frames=[],events={},properties=new Map(),classes=new Set();let time=0;
  const element={isConnected:true,style:{setProperty:(k,v)=>properties.set(k,v),removeProperty:k=>properties.delete(k)},
    classList:{add:k=>classes.add(k),remove:k=>classes.delete(k)},
    querySelector:()=>null,getBoundingClientRect:()=>({left:10,top:20}),
    get textContent(){return 'Original readable text';},set textContent(value){throw Error('Do not rewrite text');}};
  const document={hidden:false,documentElement:{addEventListener:(k,v)=>events[k]=v},addEventListener:(k,v)=>events[k]=v};
  const sandbox={CSS:{supports:()=>true},matchMedia:()=>({matches:false,addEventListener(){}}),
    getComputedStyle:()=>({color:'rgb(170, 170, 170)'}),document,window:{addEventListener(){}},
    requestAnimationFrame:fn=>{frames.push(fn);return frames.length;}};
  vm.runInNewContext(code+'\nLuminousType.mount();',sandbox);
  const flush=()=>{let count=0;while(frames.length){if(++count>150)throw Error('Idle loop');frames.shift()(time+=16);}};
  events.pointermove({pointerType:'mouse',clientX:30,clientY:40,target:{closest:()=>element}});flush();
  assert.equal(element.textContent,'Original readable text');assert.equal(properties.get('--type-base'),'rgb(170, 170, 170)');
  assert.equal(properties.get('--type-strength'),'100.00%');assert.ok(classes.has('luminous-text'));
  events.pointerleave();flush();assert.equal(classes.size,0);assert.equal(properties.size,0);
});
