const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {test} = require('node:test');
const source = fs.readFileSync('studio/static/app.js', 'utf8');

async function setup() {
  const initial = {spectrum_enabled:false, spectrum_installed:true, spectrum_preset:'balanced', spectrum_blend_weight:0.5};
  const requests = [], errors = [];
  let reply = initial, ok = true;
  const controls = [];
  const panel = {querySelectorAll:() => controls, querySelector:() => ({value:'0.5'})};
  const host = {isConnected:true};
  const context = {
    window:{h3Lang:() => 'tr'}, document:{getElementById:() => panel},
    toast:error => errors.push(error), errDetail:data => data.detail,
    fetch:async (url, options) => {
      if (options) requests.push(JSON.parse(options.body));
      return {ok, json:async () => reply};
    },
  };
  vm.createContext(context);
  const start = source.indexOf('  async function renderH3Acceleration(host) {');
  const end = source.indexOf('  let optionalModelTimer;', start);
  vm.runInContext(source.slice(start, end), context);
  await context.renderH3Acceleration(host);
  return {panel, requests, errors, reply:(value, success=true) => {reply=value; ok=success;}, initial};
}

test('manual Spectrum blend sends only its own settings and renders confirmed custom state', async () => {
  const s = await setup();
  s.reply({...s.initial, spectrum_preset:'custom', spectrum_blend_weight:0.37});
  await s.panel.onchange({target:{value:'0.37', validity:{valid:true}, matches:selector => selector.includes('data-spectrum-weight')}});
  assert.deepEqual(s.requests, [{spectrum_preset:'custom', spectrum_blend_weight:0.37}]);
  assert.match(s.panel.innerHTML, /data-spectrum-preset="custom" aria-pressed="true"/);
  assert.match(s.panel.innerHTML, /value="0.37" data-spectrum-weight/);
});

test('invalid manual input is rejected before saving', async () => {
  const s = await setup();
  await s.panel.onchange({target:{value:'1.5', validity:{valid:false}, matches:selector => selector.includes('data-spectrum-weight')}});
  assert.equal(s.requests.length, 0);
  assert.equal(s.errors.length, 1);
  assert.match(s.panel.innerHTML, /value="0.5" data-spectrum-weight/);
});

test('toggle and preset controls send partial updates without resetting manual fields', async () => {
  const s = await setup();
  s.reply({...s.initial, spectrum_enabled:true});
  await s.panel.onchange({target:{checked:true, matches:selector => selector === '[data-acceleration]'}});
  assert.deepEqual(s.requests[0], {spectrum_enabled:true});
  s.reply({...s.initial, spectrum_enabled:true, spectrum_preset:'strong', spectrum_blend_weight:0.75});
  s.panel.onclick({target:{closest:() => ({disabled:false, dataset:{spectrumPreset:'strong'}})}});
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(s.requests[1], {spectrum_preset:'strong'});
  assert.match(s.panel.innerHTML, /data-spectrum-preset="strong" aria-pressed="true"/);
});

test('failed save restores the confirmed selection', async () => {
  const s = await setup();
  s.reply({detail:'save failed'}, false);
  await s.panel.onchange({target:{value:'0.8', validity:{valid:true}, matches:selector => selector.includes('data-spectrum-weight')}});
  assert.deepEqual(s.errors, ['save failed']);
  assert.match(s.panel.innerHTML, /data-spectrum-preset="balanced" aria-pressed="true"/);
  assert.match(s.panel.innerHTML, /value="0.5" data-spectrum-weight/);
});
