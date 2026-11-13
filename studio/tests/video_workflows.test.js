const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');
const source = fs.readFileSync('studio/static/video-workflows.js', 'utf8');

async function setup() {
  const elements = new Map();
  const listeners = {};
  const storage = new Map();
  function element() {
    return {
      value:'', checked:false, classList:{contains:()=>false, toggle(){}},
      closest:()=>({classList:{toggle(){}}}), querySelectorAll:()=>[],
      set innerHTML(value) {
        this.html = value;
        for (const match of value.matchAll(/id="([^"]+)"/g)) elements.set(match[1], element());
      }
    };
  }
  elements.set('video-workflow-controls', element());
  const window = {h3Lang:()=> 'en'};
  vm.runInNewContext(source, {window, document:{
    getElementById:id=>elements.get(id) || null,
    querySelector:()=>null,
    addEventListener:(name, callback)=>{listeners[name]=callback;}, dispatchEvent(){}
  }, localStorage:{removeItem:key=>storage.delete(key), getItem:key=>storage.get(key) ?? null, setItem:(key,value)=>storage.set(key,value)},
  fetch:async()=>({ok:true,json:async()=>({continuum_ready:true})}), Event:class{}});
  await new Promise(resolve=>setImmediate(resolve));
  return {window,elements,listeners,storage};
}

test('Continuum runs are extendable by default and the choice is remembered', async()=>{
  const app=await setup();
  assert.equal(app.window.getVideoWorkflowPayload().continuum_extendable,true);
  app.elements.get('h3-continuum-toggle').onchange({target:{checked:true}});
  assert.match(app.elements.get('video-workflow-controls').html,/id="continuum-extendable" type="checkbox" checked/);
  app.elements.get('continuum-extendable').onchange({target:{checked:false}});
  assert.equal(app.window.getVideoWorkflowPayload().continuum_extendable,false);
  assert.equal(app.storage.get('h3.continuumExtendable'),'0');
});

test('production payload no longer carries Refine fields', async()=>{
  const app=await setup();
  assert.equal('prepare_refine' in app.window.getVideoWorkflowPayload(),false);
});
