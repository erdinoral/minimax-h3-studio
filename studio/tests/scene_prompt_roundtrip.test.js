const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
test('Scene editor separates cast, compositions and dialogue in compiled prompts', () => {
  const src = fs.readFileSync('studio/static/app.js', 'utf8');
  const ctx = vm.createContext({emptyCinemaStructured:()=>({})});
  vm.runInContext(src.slice(src.indexOf('  function parseH3Prompt('),src.indexOf('  function cinemaShotStructured(')),ctx);
  const text='integrated_multimodal_description: [Shot 1] Live-action Location: Hall Main character: Ainz Opening composition: Ainz sits. Action: He nods. Chronological action beats: 0s: sitting. Camera: Close-up. End composition: He stops. Ainz (S1) says: <d>[Turkish] Merhaba Albedo.</d> Constraints: Keep his face. overall_soundscape: Room tone. non_diegetic_music: N/A';
  const out=ctx.parseH3Prompt(text);
  assert.equal(out.character,'Ainz');
  assert.equal(out.opening_frame,'Ainz sits.');
  assert.equal(out.ending_frame,'He stops.');
  assert.equal(out.action,'He nods.');
  assert.equal(out.dialogue,'Merhaba Albedo.');
  assert.equal(out.camera,'Close-up.');
});
