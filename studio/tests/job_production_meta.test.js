const fs=require('node:fs'),vm=require('node:vm'),test=require('node:test'),assert=require('node:assert/strict');
test('Prompt details display effective adapter weights and recorded model, not current settings',()=>{
  const source=fs.readFileSync('studio/static/app.js','utf8');
  const ctx=vm.createContext({window:{h3Lang:()=> 'en'},tt:()=> 's'});
  vm.runInContext(source.slice(source.indexOf('  function jobProductionMeta('),source.indexOf('  function setClipPrompt(')),ctx);
  const meta=ctx.jobProductionMeta({duration:5,width:864,height:480,h3_models:{unet:'recorded-model'},lora_name:'wrong.safetensors',effective_lora_name:'mara.safetensors|detail.safetensors',effective_lora_strength:{'mara.safetensors':1.05,'detail.safetensors':0},character_manifest:[{name:'Mara'}]});
  assert.match(meta,/recorded-model/);assert.match(meta,/mara \(1.05\)/);assert.match(meta,/detail \(0\)/);assert.doesNotMatch(meta,/wrong/);assert.match(meta,/Cast: Mara/);
  assert.match(ctx.jobProductionMeta({lora_name:'wrong',effective_lora_name:''}),/LoRA: none/);
});
