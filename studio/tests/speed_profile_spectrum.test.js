const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {test} = require('node:test');

const source = fs.readFileSync('studio/static/app.js', 'utf8');

function setup(initialSettings = {spectrum_enabled: false, spectrum_preset: 'balanced', spectrum_blend_weight: 0.5}) {
  const requests = [];
  const values = {steps: {value: '20'}};
  const context = {
    fetch: async (url, options) => {
      if (!options) {
        requests.push({url, method: 'GET'});
        return {ok: true, json: async () => ({...initialSettings})};
      }
      const body = JSON.parse(options.body);
      requests.push({url, method: 'POST', body});
      if (body.spectrum_enabled !== undefined) initialSettings.spectrum_enabled = body.spectrum_enabled;
      if (body.spectrum_preset === 'strong') {
        initialSettings.spectrum_preset = 'strong';
        initialSettings.spectrum_blend_weight = 0.75;
      } else if (body.spectrum_preset === 'balanced') {
        initialSettings.spectrum_preset = 'balanced';
        initialSettings.spectrum_blend_weight = 0.5;
      }
      return {ok: true, json: async () => ({...initialSettings})};
    },
    errDetail: result => result.detail,
    toast: message => { throw Error(message); },
    $: id => values[id] || null,
    setDuration: value => { values.duration = value; },
    setQuality: value => { values.quality = value; },
    applyCinemaSpeed: value => { values.cinemaSpeed = value; },
    prepareDraftLora: value => { values.draftLora = value; },
    document: {querySelectorAll: () => []},
  };
  vm.createContext(context);

  const saveStart = source.indexOf('  let h3AccelerationSaveQueue = Promise.resolve();');
  const saveEnd = source.indexOf('  const CHROME_FIT_KEY', saveStart);
  vm.runInContext(source.slice(saveStart, saveEnd), context);
  context.prepareDraftLora = value => { values.draftLora = value; };

  const speedStart = source.indexOf('  function applySpeedProfile(kind) {');
  const speedEnd = source.indexOf('  $("btn-generate").onclick', speedStart);
  vm.runInContext(source.slice(speedStart, speedEnd), context);
  return {context, requests, values};
}

test('Taslak enables the default 50% Spectrum setting without replacing its blend value', async () => {
  const {context, requests, values} = setup();
  context.applySpeedProfile('draft');
  const applied = await vm.runInContext('pendingSpeedSpectrumApply', context);
  assert.equal(applied, true);
  assert.equal(values.duration, 5);
  assert.equal(values.quality, '480');
  assert.equal(values.steps.value, '4');
  assert.equal(values.draftLora, 'draft');
  assert.deepEqual(requests, [
    {url: '/api/h3-acceleration', method: 'GET'},
    {
    url: '/api/h3-acceleration',
    method: 'POST',
    body: {spectrum_enabled: true},
    },
  ]);
});

test('Taslak preserves a manually selected 75% Spectrum value', async () => {
  const initial = {spectrum_enabled: true, spectrum_preset: 'strong', spectrum_blend_weight: 0.75};
  const {context, requests, values} = setup(initial);
  context.applySpeedProfile('draft');
  const applied = await vm.runInContext('pendingSpeedSpectrumApply', context);
  await vm.runInContext('h3AccelerationSaveQueue', context);
  assert.equal(applied, true);
  assert.equal(values.duration, 5);
  assert.equal(values.quality, '480');
  assert.equal(values.steps.value, '4');
  assert.deepEqual(requests, [{url: '/api/h3-acceleration', method: 'GET'}]);
  assert.equal(initial.spectrum_blend_weight, 0.75);
});

test('manual Spectrum update after Taslak remains the active value', async () => {
  const {context, requests} = setup();
  context.applySpeedProfile('draft');
  await vm.runInContext('pendingSpeedSpectrumApply', context);
  await context.saveH3AccelerationSettings({spectrum_preset: 'strong'});
  await vm.runInContext('h3AccelerationSaveQueue', context);
  assert.deepEqual(requests, [
    {url: '/api/h3-acceleration', method: 'GET'},
    {url: '/api/h3-acceleration', method: 'POST', body: {spectrum_enabled: true}},
    {url: '/api/h3-acceleration', method: 'POST', body: {spectrum_preset: 'strong'}},
  ]);
});
