const {test} = require('node:test');
const assert = require('node:assert/strict');
const {orderJobs, sceneParents} = require('../static/director-chains.js');

test('active child keeps its finished root above it and siblings in story order', () => {
  const root = {id:'root', film_id:'film'};
  const a = {id:'a', film_id:'film', director_parent_id:'root', shot_index:2};
  const b = {id:'b', film_id:'film', director_parent_id:'root', shot_index:3};
  const other = {id:'other'};
  assert.deepEqual(orderJobs([b, other, a], [root, a, b, other]).map(j => j.id), ['root','a','b','other']);
});
test('missing parents and cycles never hide a job or duplicate rows', () => {
  const jobs = [{id:'a',director_parent_id:'b'},{id:'b',director_parent_id:'a'},{id:'orphan',director_parent_id:'gone'}];
  assert.equal(new Set(orderJobs(jobs).map(j => j.id)).size, 3);
});
test('scene cards follow the most recent New within their chapter', () => {
  const parents = sceneParents([
    {id:'new',mode:'t2v'},{id:'a',mode:'continue'},{id:'b',mode:'continue'},
    {id:'cut',mode:'t2v'},{id:'c',mode:'continue'},{id:'next',mode:'continue',chapter:'Other'}
  ]);
  assert.deepEqual([...parents], [['a','new'],['b','new'],['c','cut']]);
});
