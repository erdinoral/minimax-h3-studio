const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {test}=require('node:test');

function setup() {
  const handlers={},messages=[],requests=[];
  const film={film_id:'f',shots:[{id:'a',text:'A opens a door.',review:'approved'},{id:'b',text:'A opens a door.',review:'draft'}]};
  const host={innerHTML:'',parentElement:{querySelector:()=>null},addEventListener:(name,fn)=>handlers[name]=fn};
  const document={getElementById:()=>host,addEventListener:()=>{}};
  const window={t:k=>k,h3Lang:()=> 'en'};
  const context={window,document,Set,fetch:async(url,options)=>{
    requests.push({url,body:JSON.parse(options.body)});
    const data=url.endsWith('/draft')?{patches:{b:'A steps inside.'}}:url.endsWith('/apply')?{cinema:{...film,shots:[film.shots[0],{...film.shots[1],text:'A steps inside.'}]}}:
      {checkpoint:'review1',issues:[{shot_id:'b',message:'duplicate',evidence:'<img src=x onerror=alert(1)>',repairable:true}]};
    return {ok:true,json:async()=>data};
  }};
  vm.runInNewContext(fs.readFileSync('studio/static/plan-review.js','utf8'),context);
  const widget=window.createPlanReview({get:()=>film,save:async()=>{},replace:data=>Object.assign(film,data),toast:msg=>messages.push(msg)});
  const click=action=>handlers.click({target:{closest:()=>({dataset:{review:action}})}});
  return {film,host,widget,click,messages,requests};
}
test('repair preview is escaped and remains read-only until apply',async()=>{
  const s=setup();await s.click('basic');
  assert.match(s.host.innerHTML,/&lt;img/);assert.doesNotMatch(s.host.innerHTML,/<img src=x/);
  await s.click('draft');assert.equal(s.film.shots[1].text,'A opens a door.');
  assert.equal(s.requests.filter(r=>r.url.endsWith('/apply')).length,0);
  await s.click('apply');assert.equal(s.film.shots[1].text,'A steps inside.');
  assert.equal(s.film.shots[0].review,'approved');
});
test('local edit invalidates preview before an apply request',async()=>{
  const s=setup();await s.click('basic');await s.click('draft');s.film.shots[0].text='Edited';
  await s.click('apply');assert.equal(s.requests.filter(r=>r.url.endsWith('/apply')).length,0);
  assert.match(s.messages[0],/stale/);
});
test('discarding preview never sends a persistence request',async()=>{
  const s=setup();await s.click('basic');await s.click('draft');await s.click('discard');await s.click('apply');
  assert.equal(s.requests.filter(r=>r.url.endsWith('/apply')).length,0);
});
