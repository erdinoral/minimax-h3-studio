const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('studio/static/app.js', 'utf8');
const refresh = source.slice(source.indexOf('  async function refreshJobs()'), source.indexOf('  function numOr(', source.indexOf('  async function refreshJobs()')));

function fixture(status = 'done') {
  const card = {id:'ada', images:[]};
  const ctx = {
    card, loads:0, typing:false,
    state:{jobStatusSnapshot:{sheet:status}},
    fetch:async()=>({json:async()=>({jobs:[{id:'sheet',status:'done',sheet_attached:true,sheet_asset_id:'ada',sheet_still_urls:['/api/refs/deleted.png']}]})}),
    loadCinema:async()=>{ctx.loads++;card.images=[];},
    cinemaAssetCardsTyping:()=>ctx.typing,
    // A regression to the old history hydrator would resurrect this file.
    applySheetStillsFromJobs:()=>{card.images=[{file:'deleted.png'}];return true;},
    renderCinemaAssetCards(){}, renderJobs(){}, autoPlayNewestFinished(){},
    fillContinueSource(){},syncMergeToolbar(){},pollFilmPlan(){},
    $:()=>({classList:{contains:()=>true}}),
  };
  vm.createContext(ctx);vm.runInContext(refresh,ctx);return ctx;
}

test('repeated job polling cannot resurrect a deleted sheet image',async()=>{
  const ctx=fixture();
  await ctx.refreshJobs();await ctx.refreshJobs();
  assert.deepEqual(ctx.card.images,[]);assert.equal(ctx.loads,0);
});

test('a new completed sheet reloads saved assets once and waits while the user types',async()=>{
  const ctx=fixture('running');ctx.typing=true;
  await ctx.refreshJobs();assert.equal(ctx.loads,0);
  assert.equal(ctx.state.cinemaSheetReloadPending,true);
  ctx.typing=false;
  await ctx.refreshJobs();assert.equal(ctx.loads,1);
  await ctx.refreshJobs();assert.equal(ctx.loads,1);
  assert.deepEqual(ctx.card.images,[]);
});
