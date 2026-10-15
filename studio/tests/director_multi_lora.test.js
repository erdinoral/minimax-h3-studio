const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const test = require('node:test');
const source = fs.readFileSync('studio/static/app.js', 'utf8');

test('film-specific weights override another film and preserve zero', () => {
  const context=vm.createContext({state:{cinema:{lora_weights:{'a.safetensors':0}}},localStorage:{getItem:()=>'{"a.safetensors":0.9}'}});
  vm.runInContext(source.slice(source.indexOf('  function loraWeight('),source.indexOf('  function selectedLoraIds(')),context);
  assert.equal(vm.runInContext('loraWeight({file:"a.safetensors",strength:0.8})',context),0);
  context.state.cinema={lora_weights:{'a.safetensors':0.4}};
  assert.equal(vm.runInContext('loraWeight({file:"a.safetensors",strength:0.8})',context),0.4);
});

test('Director keeps five picks, disables the sixth and sends the full stack', () => {
  const catalog = ['a', 'b', 'c', 'd', 'e', 'f'].map(id => ({id, file: `${id}.safetensors`, ready: true, strength: .8}));
  const elements = {};
  for (const id of ['lora-select', 'cinema-lora-select']) {
    const options = catalog.map(s => ({value: s.id, selected: false}));
    elements[id] = {options, get selectedOptions() {return options.filter(o => o.selected);}};
  }
  for (const id of ['lora-check-list', 'cinema-lora-check-list']) {
    const boxes = catalog.map(s => ({value: s.id, checked: false, disabled: false}));
    elements[id] = {boxes, querySelectorAll: () => boxes};
  }
  elements['view-cinema'] = {classList: {contains: () => false}};
  const context = vm.createContext({$: id => elements[id], state: {loraCatalog: catalog}, updateLoraHint() {}, loraWeight: spec => spec.id === "b" ? 0 : spec.strength, appliedLoraSpec: () => null});
  const start = source.indexOf('  function selectedLoraIds(');
  const end = source.indexOf('  function collectGenerateKnobs()', start);
  vm.runInContext(source.slice(start, end), context);
  vm.runInContext('syncLoraSelection(["a", "b", "c", "d", "e"]);', context);
  assert.equal(elements['cinema-lora-check-list'].boxes[5].disabled, true);
  assert.equal(vm.runInContext('collectLoraPayload().lora_name', context), 'a.safetensors|b.safetensors|c.safetensors|d.safetensors|e.safetensors');
  assert.equal(vm.runInContext('collectLoraPayload().lora_strengths["b.safetensors"]', context), 0);
  vm.runInContext('syncLoraSelection(["a", "b", "c", "d", "e", "f"]);', context);
  assert.equal(elements['cinema-lora-select'].selectedOptions.length, 5);
  assert.ok(source.includes('syncLoraSelection(pickedIds.length ? pickedIds : [ready.id])'));
});
