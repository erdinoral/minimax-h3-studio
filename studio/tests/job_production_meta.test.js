const fs=require('node:fs'),vm=require('node:vm'),test=require('node:test'),assert=require('node:assert/strict');
test('Prompt details display effective adapter weights and recorded model, not current settings',()=>{
  const source=fs.readFileSync('studio/static/app.js','utf8');
  const ctx=vm.createContext({window:{h3Lang:()=> 'en'},tt:()=> 's'});
  vm.runInContext(source.slice(source.indexOf('  function jobVideoSeconds('),source.indexOf('  function setClipPrompt(')),ctx);
  const meta=ctx.jobProductionMeta({duration:5,width:864,height:480,h3_models:{unet:'recorded-model'},lora_name:'wrong.safetensors',effective_lora_name:'mara.safetensors|detail.safetensors',effective_lora_strength:{'mara.safetensors':1.05,'detail.safetensors':0},character_manifest:[{name:'Mara'}]});
  assert.match(meta,/recorded-model/);assert.match(meta,/mara \(1.05\)/);assert.match(meta,/detail \(0\)/);assert.doesNotMatch(meta,/wrong/);assert.match(meta,/Cast: Mara/);
  assert.match(ctx.jobProductionMeta({lora_name:'wrong',effective_lora_name:''}),/LoRA: none/);
});

test('Continuum metadata separates native chunks from last-frame handoff',()=>{
  const source=fs.readFileSync('studio/static/app.js','utf8');
  const ctx=vm.createContext({window:{h3Lang:()=> 'en'},tt:()=> 's'});
  vm.runInContext(source.slice(source.indexOf('  function jobVideoSeconds('),source.indexOf('  function setClipPrompt(')),ctx);
  const meta=ctx.jobProductionMeta({mode:'continuum',duration:5,continuum_prompts:['one','two'],continue_from:'previous',continuum_reference_size:'Match Output'});
  assert.match(meta,/Native sequence: 2 × 5s/);
  assert.match(meta,/Between jobs: previous last frame/);
  assert.match(meta,/Reference size: Match Output/);
  const resumed=ctx.jobProductionMeta({mode:'continuum',duration:5,continue_from:'previous',continuum_resume:true});
  assert.match(resumed,/saved native context/);
  assert.doesNotMatch(resumed,/previous last frame/);
  assert.match(ctx.jobProductionMeta({effective_spectrum:{enabled:true,video_blend_weight:0.6}}),/Spectrum: 60%/);
  assert.match(ctx.jobProductionMeta({effective_spectrum:{enabled:false}}),/Spectrum: off/);
});

test('Continuum duration is total sequence length before and after completion',()=>{
  const source=fs.readFileSync('studio/static/app.js','utf8');
  const ctx=vm.createContext({window:{h3Lang:()=> 'en'},tt:()=> 's'});
  vm.runInContext(source.slice(source.indexOf('  function jobVideoSeconds('),source.indexOf('  function setClipPrompt(')),ctx);
  const job={mode:'continuum',duration:5,continuum_chunk_seconds:5,continuum_prompts:['a','b','c','d','e','f']};
  assert.equal(ctx.jobVideoSeconds(job),30);
  assert.match(ctx.jobProductionMeta(job),/^30s/);
  assert.equal(ctx.jobVideoSeconds({...job,duration:30,status:'done'}),30);
  assert.equal(ctx.jobVideoSeconds({mode:'t2v',duration:5}),5);
});
