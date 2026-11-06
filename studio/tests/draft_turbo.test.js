const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {test} = require('node:test');
const source = fs.readFileSync('studio/static/app.js', 'utf8');
const id = 'lightx2v-hybrid-r48';

function setup(download = async spec => spec) {
  const elements = {steps:{value:'20'}, 'cinema-steps':{value:'20'}};
  const cinema = {};
  const selected = ['actor', 'old-speed'];
  const messages = [];
  const state = {cinemaLoaded:true, loraCatalog:[
    {id, file:'turbo.safetensors', ready:true, preset:true, preserve_manual_steps:true},
    {id:'actor', file:'actor.safetensors', category:'character'},
    {id:'old-speed', file:'other.safetensors', preset:true}
  ]};
  const context = {state, $:key=>elements[key], ensureCinema:()=>cinema,
    loadLoras:async()=>{}, downloadCatalogLora:download,
    selectedLoraIds:()=>[...selected], syncLoraSelection:ids=>selected.splice(0,selected.length,...ids),
    saveCinema:async()=>{}, toast:text=>messages.push(text)};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  let pendingDraftLoraApply'),
    source.indexOf('  function saveH3AccelerationSettings')), context);
  return {context, elements, selected, messages};
}

test('draft selects the exact Turbo, keeps the character and respects a later manual step edit', async()=>{
  const {context, elements, selected} = setup();
  context.prepareDraftLora('draft');
  assert.equal(elements.steps.value, '8');
  elements.steps.value = '10';
  await context.waitForDraftLora();
  assert.deepEqual(selected, ['actor',id]);
  assert.equal(elements.steps.value, '10');
});

test('generation waits for the missing adapter and fails closed on download error', async()=>{
  let rejectDownload;
  const {context, messages} = setup(()=>new Promise((_,reject)=>{rejectDownload=reject;}));
  context.prepareDraftLora('draft');
  const waiting = context.waitForDraftLora();
  rejectDownload(Error('download failed'));
  await assert.rejects(waiting, /LoRA/);
  assert.equal(messages[0], 'download failed');
});

test('quality drops every speed adapter, including the old 4-step drafts', async()=>{
  const {context, selected} = setup();
  selected.push('erosmax-beta1-fl2v-4step', 'lightx2v-fl2v-4step-v12');
  context.prepareDraftLora('quality');
  assert.deepEqual(selected, ['actor']);
});

test('medium preset uses the same 8-step adapter as draft', async()=>{
  const {context, elements, selected} = setup();
  context.prepareDraftLora('quick');
  assert.equal(elements.steps.value, '8');
  await context.waitForDraftLora();
  assert.deepEqual(selected, ['actor', id]);
});

test('switching to quality during a download cannot activate the draft adapter later', async()=>{
  let resolveDownload;
  const {context, selected} = setup(()=>new Promise(resolve=>{resolveDownload=resolve;}));
  context.prepareDraftLora('draft');
  context.prepareDraftLora('quality');
  resolveDownload({id,ready:true});
  await new Promise(resolve=>setImmediate(resolve));
  await context.waitForDraftLora();
  assert.equal(selected.includes(id), false);
});
