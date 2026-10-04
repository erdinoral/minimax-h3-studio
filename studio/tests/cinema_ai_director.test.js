const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{test}=require('node:test');
const source=fs.readFileSync('studio/static/app.js','utf8');
function harness(planOk=true){
 const film={film_id:'f1',duration:5};const elements={};
 for(const id of ['cinema-ai-story','cinema-ai-status','cinema-duration','cinema-ai-total','director-model','btn-cinema-ai-generate','btn-cinema-ai-close','cinema-ai-modal','btn-cinema-plan','cinema-prod-hint'])elements[id]={value:'',disabled:false,textContent:'',classList:{add(){},remove(){}},setAttribute(){},focus(){}};
 elements['cinema-ai-story'].value='NEA enters the station.';elements['cinema-ai-total'].value='60';elements['cinema-duration'].value='5';
 const calls=[],applied=[];const context={$:id=>elements[id],ensureCinema:()=>film,saveCinema:async()=>true,window:{h3Lang:()=> 'en'},tt:k=>k,tf:(k,args)=>k+':'+args.count,errDetail:d=>d.detail,
 fetch:async(url,opts)=>{calls.push({url,body:JSON.parse(opts.body)});return url.endsWith('/ai-plan')?{ok:planOk,json:async()=>planOk?{payload:{schema:'h3-cinema/v1',sections:[]},chapter:'Bölüm 2',shot_count:12}:{detail:'aiDirector.incompleteScenes'}}:{ok:true,json:async()=>({cinema:film})}},applyCinemaJsonResult:async result=>applied.push(result)};
 vm.createContext(context);const start=source.indexOf('  let cinemaAiBusy = false;'),end=source.indexOf('function cinemaKindMeta(',start);vm.runInContext(source.slice(start,end),context);return {context,calls,applied,elements};
}
test('AI Director applies its package through the importer without starting generation',async()=>{
 const h=harness();await h.context.generateCinemaAiPlan();assert.equal(h.calls.length,2);assert.equal(h.calls[0].body.shot_count,12);assert.equal(h.calls[1].url,'/api/cinema/import-json');assert.equal(h.calls[1].body.expected_film_id,'f1');assert.equal(h.calls[1].body.generate_sheets,false);assert.equal(h.calls[1].body.new_film,false);assert.equal(h.calls[1].body.keep_stills,true);assert.equal(h.applied.length,1);assert.equal(h.elements['btn-cinema-ai-generate'].disabled,false);
});
test('invalid planner reply is shown and never imported',async()=>{const h=harness(false);await h.context.generateCinemaAiPlan();assert.equal(h.calls.length,1);assert.equal(h.applied.length,0);assert.equal(h.elements['cinema-ai-status'].textContent,'aiDirector.incompleteScenes');assert.equal(h.elements['cinema-ai-story'].value,'NEA enters the station.');});
