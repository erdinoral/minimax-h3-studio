const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { test } = require('node:test');

test('film scene cards follow EN/TR without changing the saved scene text', () => {
  const handlers = {};
  const host = { innerHTML: '', contains: () => false, querySelector: () => null };
  const document = {
    activeElement: null,
    addEventListener: (name, handler) => { handlers[name] = handler; },
    getElementById: id => id === 'film-workspace' ? host : null,
  };
  const window = {};
  const context = { document, window, localStorage: { getItem: () => 'en' } };
  vm.runInNewContext(fs.readFileSync('studio/static/i18n.js', 'utf8'), context);
  let lang = 'en';
  window.t = key => window.H3_I18N[lang][key] || key;
  window.h3Lang = () => lang;
  vm.runInNewContext(fs.readFileSync('studio/static/film-workspace.js', 'utf8'), context);

  const film = {
    film_id: 'film-1',
    shots: [{ id: 'shot-1', chapter: 'Bölüm 1', scene: '', text: 'A woman opens the door.', mode: 't2v', bindings: [], review: 'draft' }],
    characters: [], creatures: [], locations: [],
  };
  const workspace = window.createFilmWorkspace({
    get: () => film,
    jobs: () => [],
    saveStatus: () => 'Saved',
    filter: () => {},
  });

  workspace.render();
  assert.match(host.innerHTML, /Shot 1/);
  assert.match(host.innerHTML, /Draft/);
  assert.match(host.innerHTML, /Section 1/);
  assert.match(host.innerHTML, /A woman opens the door/);
  assert.doesNotMatch(host.innerHTML, /Çekim 1|Taslak|Bölümü üret/);

  lang = 'tr';
  handlers['h3-lang']();
  assert.match(host.innerHTML, /Çekim 1/);
  assert.match(host.innerHTML, /Taslak/);
  assert.match(host.innerHTML, /A woman opens the door/);
});
