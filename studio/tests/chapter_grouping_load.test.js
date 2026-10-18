const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const {test}=require('node:test');
const source=fs.readFileSync('studio/static/app.js','utf8');
const load=source.slice(source.indexOf('  async function loadCinema()'),source.indexOf('  function flushCinemaFields()'));

test('loading a film retains chapter grouping, with old projects defaulting to cut boundaries',async()=>{
  for (const value of ['chapter',undefined]) {
    const state={};
    const ctx={state,fetch:async()=>({json:async()=>({film_id:'f',continuum_grouping:value})}),
      emptyCinema:()=>({setup:{},audio:{}}),normalizeQuality:x=>x,
      normalizeCinemaImageProvider:x=>x,cinemaChapterList(){},setCinemaStudioMode(){},
      ensureCinema:()=>state.cinema,renderCinema(){},fillLoraSelect(){},fillCinemaFilms(){},
      refreshCinemaPreview(){},syncFilmModeSummary(){},syncFilmStillsWarn(){}};
    vm.createContext(ctx);vm.runInContext(load,ctx);
    await ctx.loadCinema();
    assert.equal(state.cinema.continuum_grouping,value || 'cuts');
  }
});

test('saving chapter grouping sends the choice and retains it after the server response',async()=>{
  const requests=[];
  const state={cinemaLoaded:true,cinema:{film_id:'f',shots:[{text:'first action'}],continuum_grouping:'chapter'}};
  const ctx={state,AbortController,flushCinemaFields:()=>state.cinema,$:()=>null,
    cinemaChapterList:()=>['A'],normalizeQuality:String,normalizeCinemaImageProvider:String,
    cinemaStudioMode:()=> 'seamless',emptyCinema:()=>({setup:{},audio:{}}),
    ensureCinema:()=>state.cinema,cinemaTypingIn:()=>false,cinemaTypingShots:()=>false,
    tt:String,toast:()=>{},errDetail:String,
    fetch:async(url,options)=>{
      const data=options?JSON.parse(options.body):state.cinema;
      if(options)requests.push(data);
      return {ok:true,json:async()=>data};
    }};
  vm.createContext(ctx);
  vm.runInContext(source.slice(source.indexOf('  function cinemaPayload()'),source.indexOf('  const LORA_CATEGORIES')),ctx);
  assert.equal(await ctx.saveCinema(true),true);
  assert.equal(requests[0].continuum_grouping,'chapter');
  assert.equal(state.cinema.continuum_grouping,'chapter');
  state.cinema.continuum_grouping='cuts';
  assert.equal(await ctx.saveCinema(true),true);
  assert.equal(requests[1].continuum_grouping,'cuts');
  assert.equal(state.cinema.continuum_grouping,'cuts');
});
