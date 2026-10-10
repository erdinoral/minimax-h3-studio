const fs = require('node:fs'), vm = require('node:vm');
const assert = require('node:assert/strict'), test = require('node:test');
const source = fs.readFileSync('studio/static/app.js', 'utf8');

test('selecting a reference only uploads and previews it; explicit generation queues once', async () => {
  const requests = [], queued = [];
  let resolveGeneration;
  const generation = new Promise(resolve => { resolveGeneration = resolve; });
  const context = {
    state:{cinemaLookRefs:{}}, ensureCinema:()=>({film_id:'film'}),
    FormData:class { append() {} },
    fetch:async url => { requests.push(url); return {ok:true,json:async()=>({name:'source.png',url:'/api/refs/source.png'})}; },
    flushCinemaFields:()=>{}, renderCinemaAssetCards:()=>{},
    regenerateCinemaAsset:async (...args)=>{ queued.push(args); return generation; },
  };
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  function cinemaLookReferenceKey('), source.indexOf('  function cinemaCardHtml(')), context);
  await context.stageCinemaLookReference('character','ada',{});
  assert.deepEqual(requests, ['/api/refs/upload']); assert.equal(queued.length,0);
  assert.equal(context.state.cinemaLookRefs['film:character:ada'].name,'source.png');
  const first = context.produceCinemaLookSheet('character','ada',null);
  await context.produceCinemaLookSheet('character','ada',null);
  assert.equal(queued.length,1);
  assert.equal(queued[0][3].ref_image,'source.png');
  resolveGeneration(true); await first;
  assert.equal(context.state.cinemaLookRefs['film:character:ada'],undefined);
});

test('failed sheet generation keeps the staged reference available for retry', async () => {
  const ref = {name:'source.png',url:'/api/refs/source.png'};
  const context = {
    state:{cinemaLookRefs:{'film:character:ada':ref}}, ensureCinema:()=>({film_id:'film'}),
    regenerateCinemaAsset:async ()=>false, flushCinemaFields:()=>{}, renderCinemaAssetCards:()=>{},
  };
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  function cinemaLookReferenceKey('), source.indexOf('  function cinemaCardHtml(')), context);
  await context.produceCinemaLookSheet('character','ada',null);
  assert.equal(context.state.cinemaLookRefs['film:character:ada'],ref);
  assert.equal(ref.busy,false);
});

test('asset request preserves the selected method and source on regeneration', async () => {
  const start = source.indexOf('  async function regenerateCinemaAsset(');
  const end = source.indexOf('  async function produceCinemaOne(', start);
  let request;
  const actor = {name:'Ada', notes:'navy jacket'};
  const context = {
    cinemaItem: () => actor, ensureCinema: () => ({image_provider:'image_studio', quality:'480', steps:20}),
    saveCinema: async () => {}, startImageStudioQueuePoll: () => {},
    stopImageStudioQueuePoll: () => {}, $: () => null, normalizeQuality: x => x, state:{aspect:'16:9'},
    fetch: async (url, options) => { request = JSON.parse(options.body); return {ok:true, json:async()=>({job:{id:'j'}})}; },
    toast: () => {}, tf: k => k, setProdLane: () => {}, refreshJobs: async () => {},
    normalizeCinemaImageProvider: value => value, cinemaImageProductionMethod: () => 'qwen',
  };
  vm.createContext(context); vm.runInContext(source.slice(start, end), context);
  await context.regenerateCinemaAsset('character', 'ada', null, {ref_images:['source.png'], ref_image:'source.png'});
  assert.equal(request.asset_id, 'ada'); assert.equal(request.name, 'Ada');
  assert.equal(request.production_method, 'qwen'); assert.deepEqual(request.ref_images, ['source.png']);
  actor.sheet_method = 'look_sheets'; actor.source_ref = 'source.png';
  await context.regenerateCinemaAsset('character', 'ada', null);
  assert.equal(request.production_method, 'qwen'); assert.deepEqual(request.ref_images, ['source.png']);
});
