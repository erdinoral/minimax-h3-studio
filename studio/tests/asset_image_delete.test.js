const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('studio/static/app.js', 'utf8');
const body = source.slice(source.indexOf('  async function removeCinemaImage('), source.indexOf('  async function ingestCinemaRole('));

function fixture(responses) {
  const film = {film_id:'film', vehicles:[{id:'car', images:[{file:'front.png'}]}, {id:'other', images:[]}]};
  const context = {film, cinemaPreviewTimer:0, cinemaSaveGen:0, cinemaAssetVersions:new Map(),
    clearTimeout(){}, abortCinemaSaves(){}, ensureCinema:()=>film,
    cinemaItem:(_k,id)=>film.vehicles.find(x=>x.id===id), cinemaKindMeta:()=>({key:'vehicles'}),
    nextCinemaAssetVersion(k,id){const v=(context.cinemaAssetVersions.get(`${k}:${id}`)||0)+1;context.cinemaAssetVersions.set(`${k}:${id}`,v);return v;},
    cinemaAssetImages:a=>a.images, renderCinemaAssetCards(){}, renderCinema(){}, toast(){}, tt:x=>x,
    errDetail:d=>d.detail, encodeURIComponent,
    fetch:async()=>{const r=responses.shift();return {ok:r.status===200,status:r.status,json:async()=>r.data};}};
  vm.createContext(context); vm.runInContext(body,context); return context;
}

test('already removed image refreshes stale vehicle card without changing other cards',async()=>{
  const ctx=fixture([{status:404,data:{detail:'missing'}},{status:200,data:{film_id:'film',vehicles:[{id:'car',images:[]}]}}]);
  const other=ctx.film.vehicles[1];
  await ctx.removeCinemaImage('vehicle','car','front.png');
  assert.equal(ctx.film.vehicles[0].images.length,0); assert.equal(ctx.film.vehicles[1],other);
});
test('successful deletion updates the card and invalidates older save responses',async()=>{
  const ctx=fixture([{status:200,data:{asset:{id:'car',images:[]}}}]);
  await ctx.removeCinemaImage('vehicle','car','front.png');
  assert.equal(ctx.film.vehicles[0].images.length,0); assert.equal(ctx.cinemaSaveGen,1);
});
test('real 404 error remains visible if the server still has the image',async()=>{
  const ctx=fixture([{status:404,data:{detail:'missing'}},{status:200,data:{film_id:'film',vehicles:[{id:'car',images:[{file:'front.png'}]}]}}]);
  await assert.rejects(ctx.removeCinemaImage('vehicle','car','front.png'),/missing/);
  assert.equal(ctx.film.vehicles[0].images.length,1);
});
