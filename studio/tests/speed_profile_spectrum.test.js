const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {test} = require('node:test');

const source = fs.readFileSync('studio/static/app.js', 'utf8');

function setup(initialSettings = {spectrum_enabled: false, spectrum_preset: 'balanced', spectrum_blend_weight: 0.5, sparse_enabled: false}) {
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
      if (body.sparse_enabled !== undefined) initialSettings.sparse_enabled = body.sparse_enabled;
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
    tToast: () => {},
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

const enableAll = {url: '/api/h3-acceleration', method: 'POST', body: {spectrum_enabled: true, sparse_enabled: true}};

test('Taslak: 480p, 8 steps and every accelerator without replacing the blend value', async () => {
  const {context, requests, values} = setup();
  context.applySpeedProfile('draft');
  const applied = await vm.runInContext('pendingSpeedSpectrumApply', context);
  assert.equal(applied, true);
  assert.equal(values.duration, 5);
  assert.equal(values.quality, '480');
  assert.equal(values.steps.value, '8');
  assert.equal(values.draftLora, 'draft');
  assert.deepEqual(requests, [{url: '/api/h3-acceleration', method: 'GET'}, enableAll]);
});

test('Orta: 736p, 8 steps and every accelerator', async () => {
  const {context, requests, values} = setup();
  context.applySpeedProfile('quick');
  await vm.runInContext('pendingSpeedSpectrumApply', context);
  assert.equal(values.duration, 5);
  assert.equal(values.quality, '736');
  assert.equal(values.steps.value, '8');
  assert.equal(values.draftLora, 'quick');
  assert.deepEqual(requests, [{url: '/api/h3-acceleration', method: 'GET'}, enableAll]);
});

test('Kalite: 1088p, 18 steps, every accelerator and no speed adapter profile', async () => {
  const {context, requests, values} = setup();
  context.applySpeedProfile('quality');
  await vm.runInContext('pendingSpeedSpectrumApply', context);
  assert.equal(values.quality, '1088');
  assert.equal(values.steps.value, '18');
  assert.equal(values.draftLora, 'quality');
  assert.equal(values.duration, undefined);
  assert.deepEqual(requests, [{url: '/api/h3-acceleration', method: 'GET'}, enableAll]);
});

test('Taslak only switches on what is missing and keeps a manual 75% Spectrum value', async () => {
  const initial = {spectrum_enabled: true, spectrum_preset: 'strong', spectrum_blend_weight: 0.75, sparse_enabled: false};
  const {context, requests} = setup(initial);
  context.applySpeedProfile('draft');
  const applied = await vm.runInContext('pendingSpeedSpectrumApply', context);
  await vm.runInContext('h3AccelerationSaveQueue', context);
  assert.equal(applied, true);
  assert.deepEqual(requests, [
    {url: '/api/h3-acceleration', method: 'GET'},
    {url: '/api/h3-acceleration', method: 'POST', body: {sparse_enabled: true}},
  ]);
  assert.equal(initial.spectrum_blend_weight, 0.75);
});

test('no save request when every accelerator is already on', async () => {
  const initial = {spectrum_enabled: true, spectrum_preset: 'balanced', spectrum_blend_weight: 0.5, sparse_enabled: true};
  const {context, requests} = setup(initial);
  context.applySpeedProfile('quality');
  await vm.runInContext('pendingSpeedSpectrumApply', context);
  assert.deepEqual(requests, [{url: '/api/h3-acceleration', method: 'GET'}]);
});

test('manual Spectrum update after Taslak remains the active value', async () => {
  const {context, requests} = setup();
  context.applySpeedProfile('draft');
  await vm.runInContext('pendingSpeedSpectrumApply', context);
  await context.saveH3AccelerationSettings({spectrum_preset: 'strong'});
  await vm.runInContext('h3AccelerationSaveQueue', context);
  assert.deepEqual(requests, [
    {url: '/api/h3-acceleration', method: 'GET'},
    enableAll,
    {url: '/api/h3-acceleration', method: 'POST', body: {spectrum_preset: 'strong'}},
  ]);
});
