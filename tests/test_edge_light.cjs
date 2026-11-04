const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../web/app.js'), 'utf8');
const lighting = source.slice(source.indexOf('// Paint only existing rectangular borders'));
function harness() {
  const transforms = [], lines = [], listeners = {}, frames = [];
  const box = {left:0, top:0, width:985, height:800};
  const context = {
    setTransform: (...args) => transforms.push(args), clearRect() {},
    createRadialGradient: () => ({addColorStop() {}}), beginPath() {},
    moveTo: (...args) => lines.push(['move', ...args]),
    lineTo: (...args) => lines.push(['line', ...args]), stroke() {},
  };
  const canvas = {width:300, height:150, setAttribute() {}, getContext:() => context, getBoundingClientRect:() => box};
  const style = {borderTopWidth:'1px',borderRightWidth:'1px',borderBottomWidth:'1px',borderLeftWidth:'1px',visibility:'visible',display:'block'};
  const surface = {getBoundingClientRect:() => ({left:800,right:980,top:100,bottom:140,width:180,height:40})};
  const sandbox = {
    innerWidth:1000,innerHeight:800,devicePixelRatio:1.25,
    matchMedia:() => ({matches:true,addEventListener() {}}),
    requestAnimationFrame: callback => {frames.push(callback); return frames.length;},
    getComputedStyle:() => style,
    document:{hidden:false,createElement:() => canvas,body:{append() {}},
      documentElement:{addEventListener() {}},
      addEventListener:(name,fn) => {listeners[name]=fn;},querySelectorAll:() => [surface]},
    window:{addEventListener() {}},
  };
  vm.runInNewContext(lighting, sandbox);
  function flush() {while(frames.length) frames.shift()();}
  function move(x=970,y=120) {listeners.pointermove({pointerType:'mouse',clientX:x,clientY:y});flush();}
  flush();
  return {sandbox,canvas,box,transforms,lines,style,move};
}
test('edge overlay uses its CSS box, not viewport width including scrollbar', () => {
  const h=harness();h.move();
  assert.equal(h.canvas.width,Math.round(985*1.25));
  const transform=h.transforms.at(-1);
  assert.equal(transform[0],h.canvas.width/985);
  // A viewport point must map back to the identical CSS location after drawing.
  assert.ok(Math.abs(980*transform[0]/h.canvas.width*985-980)<1e-9);
});
test('edge overlay remaps after fractional resize and DPR changes without reload', () => {
  const h=harness();h.box.width=782.4;h.box.left=4;h.sandbox.devicePixelRatio=2;h.move();
  assert.equal(h.canvas.width,1565);
  const transform=h.transforms.at(-1);
  assert.equal(transform[0],1565/782.4);
  assert.equal(transform[4],-4*transform[0]);
});
test('border strokes follow border centers and skip missing edges', () => {
  const h=harness();h.style.borderLeftWidth='0px';h.move();
  assert.deepEqual(h.lines[0],['move',800,100.5]);
  assert.deepEqual(h.lines[1],['line',979.5,100.5]);
  assert.equal(h.lines.length,6);
});

