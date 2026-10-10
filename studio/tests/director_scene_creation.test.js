const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {test} = require('node:test');
const source = fs.readFileSync('studio/static/app.js', 'utf8');
const html = fs.readFileSync('studio/static/index.html', 'utf8');
test('Director exposes scene and chapter creation in the main toolbar', () => {
  const toolbar = html.match(/<div class="cinema-workspace-actions">([\s\S]*?)<\/div>/)[1];
  for (const id of ['btn-cinema-add-scene', 'btn-cinema-add-t2v']) {
    assert.ok(toolbar.includes(`id="${id}"`));
    assert.ok(!toolbar.match(new RegExp(`<button[^>]*id="${id}"[^>]*(?:disabled|hidden)`)));
  }
});
test('Scene creation button opens a new-scene editor without needing existing shots', () => {
  const calls = [];
  const context = {openCinemaSceneModal: (...args) => calls.push(args)};
  vm.createContext(context);
  const start = source.indexOf('  function addCinemaShot(mode) {');
  vm.runInContext(source.slice(start, source.indexOf('/** New empty chapter', start)), context);
  const handler = source.match(/\$\("btn-cinema-add-scene"\)\?\.addEventListener\("click", (\(\) => addCinemaShot\("t2v"\))\);/);
  assert.ok(handler);
  vm.runInContext(`(${handler[1]})()`, context);
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0], [null, 't2v']);
});