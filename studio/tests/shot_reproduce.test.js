const fs = require('node:fs'), vm = require('node:vm');
const assert = require('node:assert/strict'), test = require('node:test');
const app = fs.readFileSync('studio/static/app.js', 'utf8');

test('scene header orders disable, duplicate, reproduce, delete', () => {
  const start = app.indexOf('  function cinemaShotHtml(');
  const end = app.indexOf('  function cinemaChapterDisplayName(', start);
  const context = {
    cinemaStudioMode: () => 'seamless', ensureCinema: () => ({shots: [], duration: 5}),
    cinemaShotCalls: () => [], cinemaShotJobMeta: () => ({cls: '', label: ''}),
    cinemaJobForShot: () => ({id: 'old', status: 'done'}),
    cinemaShotStructured: () => ({}), cinemaShotSummary: () => 'scene',
    htmlEsc: s => s, tt: s => s, tf: s => s,
  };
  vm.createContext(context); vm.runInContext(app.slice(start, end), context);
  const html = context.cinemaShotHtml({id: 'shot', mode: 'continue'}, 0, 0);
  const classes = ['cinema-shot-toggle', 'cinema-shot-duplicate', 'cinema-shot-reproduce', 'cinema-shot-del'];
  const positions = classes.map(c => html.indexOf(c));
  assert.ok(positions.every((p, i) => p >= 0 && (!i || p > positions[i - 1])));
});

test('reproduce sends historical identity, never saves current controls or produces a batch', async () => {
  const start = app.indexOf('  async function reproduceCinemaOne(');
  const end = app.indexOf('  async function produceCinemaOne(', start);
  const calls = [];
  const context = {
    ensureCinema: () => ({film_id: 'film', shots: [{id: 'shot'}]}),
    cinemaJobForShot: () => ({id: 'old'}),
    fetch: async (url, opts) => {
      calls.push([url, JSON.parse(opts.body)]);
      return {ok: true, json: async () => ({job: {id: 'new'}})};
    },
    toast() {}, tt: s => s, setProdLane() {}, refreshJobs: async () => {}, renderCinemaShots() {},
  };
  vm.createContext(context); vm.runInContext(app.slice(start, end), context);
  await context.reproduceCinemaOne('shot', {disabled: false, isConnected: true});
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], '/api/cinema/reproduce-one');
  assert.deepEqual(calls[0][1], {shot_id: 'shot', expected_film_id: 'film', source_job_id: 'old'});
});
