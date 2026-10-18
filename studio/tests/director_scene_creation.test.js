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

test('Empty chapter offers scene creation and disables chapter production', () => {
  const context = {
    cinemaChapterOpen: () => true,
    htmlEsc: String, tt: x => x, tf: x => x,
    cinemaChapterDisplayName: String,
  };
  vm.createContext(context);
  const start = source.indexOf('  function cinemaChapterHtml(');
  const end = source.indexOf('  let cinemaSceneEditId', start);
  vm.runInContext(source.slice(start, end), context);
  const rendered = context.cinemaChapterHtml('Chapter 2', [], 0);
  assert.match(rendered, /cinema-chapter-add-scene/);
  assert.match(rendered, /cinema-chapter-produce[^>]* disabled/);
});

test('Scene created from a chapter is assigned to that chapter', () => {
  const start = source.indexOf('    const chapterAdd = e.target.closest(');
  const end = source.indexOf('    const chapterProduce', start);
  const calls = [];
  const context = {
    cinemaSceneEditChapter: null,
    openCinemaSceneModal: (...args) => calls.push(args),
    e: {preventDefault() {}, target: {closest: () => ({closest: () => ({dataset: {chapter: 'Chapter 2'}})})}},
  };
  vm.createContext(context);
  vm.runInContext('(function(){' + source.slice(start, end) + '})()', context);
  assert.equal(context.cinemaSceneEditChapter, 'Chapter 2');
  assert.deepEqual(calls[0], [null, 't2v']);
});

test('Produce all queues both chapters; chapter production queues only its chapter', async () => {
  const cinema = {shots: [
    {id: 'a', text: 'First scene', chapter: 'A'},
    {id: 'b', text: 'Second scene', chapter: 'B'},
    {id: 'empty', text: '', chapter: 'B'},
    {id: 'disabled', text: 'Disabled scene', chapter: 'B', enabled: false},
  ]};
  const requests = [], errors = [];
  const noop = () => {};
  const context = {
    $: () => null, ensureCinema: () => cinema, state: {},
    flushCinemaFields: noop, saveCinema: async () => {},
    cinemaActiveChapter: () => 'A', cinemaChapterOf: s => s.chapter,
    cinemaStudioMode: () => 'assets', cinemaAudio: () => ({mode: 'silent'}),
    numOr: () => -1, normalizeQuality: String,
    normalizeCinemaImageProvider: String, collectLoraPayload: () => ({}),
    fetch: async (url, options) => {
      requests.push(JSON.parse(options.body));
      return {ok: true, json: async () => ({phase: 'sheets', sheets_queued: []})};
    },
    tt: String, tf: String, toast: x => errors.push(x),
    setProdLane: noop, refreshJobs: async () => {},
    stopImageStudioQueuePoll: noop,
  };
  vm.createContext(context);
  const start = source.indexOf('  async function produceCinema(opts)');
  const end = source.indexOf('  async function regenerateCinemaAsset', start);
  vm.runInContext(source.slice(start, end), context);
  await context.produceCinema({all: true});
  await context.produceCinema({chapter: 'B'});
  assert.equal(requests.length, 2, errors.join('\n'));
  assert.deepEqual(requests[0].shots.map(s => s.id), ['a', 'b']);
  assert.deepEqual(requests[1].shots.map(s => s.id), ['b']);
  context.cinemaStudioMode = () => 'seamless';
  context.state.multishot = true;
  cinema.shots[0].take_index = 1;
  cinema.shots[0].structured = {ending_frame: 'At the foot of the mountain'};
  cinema.shots[1].mode = 't2v';
  cinema.shots[1].take_index = 2;
  await context.produceCinema({all:true});
  assert.equal(requests[2].shots[0].structured.ending_frame,'At the foot of the mountain');
  assert.equal(requests[2].shots[1].take_index,2);
  assert.equal(requests[2].shots[1].mode,'t2v');
});
