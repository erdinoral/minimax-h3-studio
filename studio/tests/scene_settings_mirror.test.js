const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {test} = require('node:test');
const script = fs.readFileSync('studio/static/scene-settings.js', 'utf8');

function setup() {
  const events = [], clicks = [], handlers = {};
  const input = attr => ({value:'0.6', disabled:false, checked:true, dataset:{acceleration:'spectrum'},
    hasAttribute:key => key === attr,
    closest() {return this;},
    dispatchEvent(event) {
      events.push({attr, type:event.type, value:this.value, checked:this.checked});
      if (attr === 'data-spectrum-range' && event.type === 'input') originals['data-spectrum-weight'].value = this.value;
      if (attr === 'data-spectrum-weight' && event.type === 'input') originals['data-spectrum-range'].value = this.value;
    }});
  const attrs = ['data-spectrum-range','data-spectrum-weight','data-acceleration'];
  const originals = Object.fromEntries(attrs.map(attr => [attr,input(attr)]));
  const mirrors = Object.fromEntries(attrs.map(attr => [attr,input(attr)]));
  const select = collection => selector => collection[attrs.find(attr => selector.includes(attr))];
  const button = {dataset:{spectrumPreset:'light'}, click:() => clicks.push('light')};
  const source = {innerHTML:'controls', querySelectorAll:() => [button], querySelector:select(originals)};
  const target = {innerHTML:'', querySelectorAll:() => [], querySelector:select(mirrors), addEventListener:(type,fn) => handlers[type]=fn};
  vm.runInNewContext(script, {
    document:{getElementById:id => ({'h3-engine-control':source,'scene-engine-settings':target})[id]},
    MutationObserver:class {observe() {}}, Event:class {constructor(type) {this.type=type;}}
  });
  return {handlers, originals, mirrors, clicks, events, button};
}

test('Scene Spectrum preset clicks reach the original settings handler', () => {
  const s=setup();
  s.handlers.click({target:{closest:() => s.button}});
  assert.deepEqual(s.clicks,['light']);
});

test('Scene slider forwards live input, synchronizes its number and commits on change', () => {
  const s=setup(), slider=s.mirrors['data-spectrum-range'];
  slider.value='0.37';
  s.handlers.input({type:'input',target:slider});
  assert.equal(s.originals['data-spectrum-range'].value,'0.37');
  assert.equal(s.mirrors['data-spectrum-weight'].value,'0.37');
  s.handlers.change({type:'change',target:slider});
  assert.deepEqual(s.events.map(e=>e.type),['input','change']);
});

test('Scene manual value and toggle changes reach their original controls', () => {
  const s=setup(), number=s.mirrors['data-spectrum-weight'];
  number.value='0.43';
  s.handlers.input({type:'input',target:number});
  assert.equal(s.mirrors['data-spectrum-range'].value,'0.43');
  s.handlers.change({type:'change',target:number});
  const toggle=s.mirrors['data-acceleration']; toggle.checked=false;
  s.handlers.change({type:'change',target:toggle});
  assert.equal(s.events[1].value,'0.43');
  assert.equal(s.events[2].checked,false);
});

test('Disabled original Spectrum controls cannot be changed through the mirror', () => {
  const s=setup();
  s.originals['data-spectrum-range'].disabled=true;
  s.handlers.change({type:'change',target:s.mirrors['data-spectrum-range']});
  assert.equal(s.events.length,0);
});
