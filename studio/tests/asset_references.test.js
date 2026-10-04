const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('studio/static/asset-references.js','utf8');

async function setup(saved=null) {
  const events={}, storage=new Map(saved?[['h3-scene-assets',JSON.stringify(saved)]]:[]);
  const host={innerHTML:'',addEventListener:(name,fn)=>events[name]=fn};
  const film={film_id:'f',title:'Film',vehicles:[{id:'car',name:'<script>bad()</script>',images:[{file:'front.png',name:'front'},{file:'rear.png',name:'rear'}]}]};
  const context={window:{h3Lang:()=> 'tr'},localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
    document:{getElementById:()=>host,addEventListener(){}},
    fetch:async()=>({ok:true,json:async()=>film})};
  vm.createContext(context);vm.runInContext(source,context);
  const picker=context.window.createSceneAssetReferences({context:()=>({prompt:'Drive'}),toast:msg=>{throw Error(msg)}});
  await new Promise(setImmediate);
  return {picker,events,host,storage};
}

test('Scene selections send exact owner and files; clearing is explicit',async()=>{
  const {picker,events}=await setup();
  assert.equal(JSON.stringify(picker.payload().asset_bindings),'[]');
  events.change({target:{dataset:{owner:'car',file:'rear.png'},checked:true}});
  assert.equal(JSON.stringify(picker.payload().asset_bindings),'[{"asset_id":"car","files":["rear.png"]}]');
  events.change({target:{dataset:{owner:'car',file:'rear.png'},checked:false}});
  assert.equal(JSON.stringify(picker.payload().asset_bindings),'[]');
  await events.click({target:{dataset:{action:'auto'}}});
  assert.equal(picker.payload().asset_bindings,null);
  assert.equal(picker.payload().asset_auto_match,true);
});

test('Scene selection restores only for the matching film and escapes card labels',async()=>{
  const saved={asset_film_id:'f',asset_bindings:[{asset_id:'car',files:['front.png']}]};
  const {picker,host}=await setup(saved);
  assert.equal(picker.payload().asset_bindings[0].files[0],'front.png');
  assert.ok(host.innerHTML.includes('&lt;script&gt;bad()&lt;/script&gt;'));
  assert.ok(!host.innerHTML.includes('<script>bad()'));
  const changed=await setup({...saved,asset_film_id:'another'});
  assert.equal(JSON.stringify(changed.picker.payload().asset_bindings),'[]');
});
