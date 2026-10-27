const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const script = fs.readFileSync('app/static/presentation.js', 'utf8');
function setup() {
  const nodes = new Map(), timers = new Map(); let timerId = 0;
  class Element {
    constructor() { this.listeners = {}; this.open = false; this.value = '0.5'; this.src = ''; this.paused = true; this.textContent = ''; }
    addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener); }
    async fire(type, event = {}) { for (const fn of this.listeners[type] || []) await fn(event); }
    showModal() { this.open = true; }
    close() { this.open = false; this.fire('close'); }
    focus() {}
    pause() { this.paused = true; }
    play() { this.paused = false; return Promise.resolve(); }
    load() {}
    removeAttribute(name) { this[name] = ''; }
    getAttribute(name) { return this[name]; }
  }
  const element = id => { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); };
  const slides = Array.from({length:3}, (_, n) => ({number:n+1,title:`Slide ${n+1}`,image_url:`/${n}.png`, audio_ready:n<2,audio_url:`/${n}.wav`}));
  const context = {window:{},element, state:{project:{slides},slide:0}, action: op => op(), saveScript: async () => {}, render: () => {},
    document:{body:{classList:{add(){},remove(){}}},documentElement:{},addEventListener(){},fullscreenElement:null},
    setTimeout: fn => { timers.set(++timerId, fn); return timerId; },clearTimeout: id => timers.delete(id)};
  vm.runInNewContext(script, context);
  return {element, context, timers, slides};
}
test('presentation shows image, counter and navigation without narration', async () => {
  const {element} = setup();
  await element('present-slides').fire('click');
  assert.equal(element('presentation').open, true);
  assert.equal(element('presentation-counter').textContent, '1 / 3');
  assert.equal(element('presentation-prev').disabled, true);
  await element('presentation-next').fire('click');
  assert.equal(element('presentation-image').src, '/1.png');
  await element('presentation-next').fire('click');
  assert.equal(element('presentation-next').disabled, true);
  assert.equal(element('presentation-play').disabled, true);
});
test('space controls playback even while the Exit button has focus', async () => {
  const {element} = setup();
  await element('present-slides').fire('click');
  let prevented = false;
  await element('presentation').fire('keydown',{key:' ',code:'Space',target:{tagName:'BUTTON'},preventDefault(){prevented=true;}});
  assert.equal(prevented,true);
  assert.equal(element('presentation-audio').paused,false);
  await element('presentation-play').fire('click');
  assert.equal(element('presentation-audio').paused,true);
});
test('narration advances after its pause; missing audio switches to manual navigation', async () => {
  const {element,timers} = setup();
  await element('present-slides').fire('click');
  await element('presentation-play').fire('click');
  await element('presentation-audio').fire('ended');
  assert.equal(element('presentation-counter').textContent,'1 / 3');
  [...timers.values()].at(-1)();
  assert.equal(element('presentation-counter').textContent,'2 / 3');
  await element('presentation-audio').fire('ended');
  [...timers.values()].at(-1)();
  assert.equal(element('presentation-counter').textContent,'3 / 3');
  assert.equal(element('presentation-play').disabled,true);
  assert.match(element('presentation-status').textContent,/no narration/);
});
test('closing cancels narration and delayed slide advance and returns to selected slide', async () => {
  const {element,context,timers} = setup();
  await element('present-slides').fire('click');
  await element('presentation-next').fire('click');
  await element('presentation-play').fire('click');
  await element('presentation-audio').fire('ended');
  const delayed = [...timers.values()].at(-1);
  await element('presentation-close').fire('click');
  delayed();
  assert.equal(context.state.slide,1);
  assert.equal(element('presentation').open,false);
  assert.equal(element('presentation-audio').paused,true);
  assert.equal(timers.size,0);
  assert.equal(element('presentation-counter').textContent,'2 / 3');
});
test('Home and End navigate and native WebViews have a fullscreen fallback', async () => {
  const {element} = setup();
  await element('present-slides').fire('click');
  for (const [key,expected] of [['End','3 / 3'],['Home','1 / 3']]) {
    await element('presentation').fire('keydown',{key,preventDefault(){}});
    assert.equal(element('presentation-counter').textContent,expected);
  }
  await element('presentation-fullscreen').fire('click');
  assert.match(element('presentation-status').textContent,/window’s full-screen control/);
});

test('native desktop fullscreen uses its window bridge', async () => {
  const {element,context} = setup();
  let calls = 0;
  context.window.pywebview = {api:{toggle_fullscreen: async () => { calls++; return true; }}};
  await element('presentation-fullscreen').fire('click');
  assert.equal(calls,1);
  assert.equal(element('presentation-fullscreen').textContent,'Leave full screen');
});
