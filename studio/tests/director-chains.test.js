const {test} = require('node:test');
const assert = require('node:assert/strict');
const {orderJobs, sceneParents} = require('../static/director-chains.js');
const {sequenceGroups} = require('../static/director-chains.js');
test('each New owns only its ordered continuation prompt sections', () => {
  const shots = [
    {id:'a', mode:'t2v', text:'A'}, {id:'b', mode:'continue', text:'B'},
    {id:'c', mode:'continue', text:'C'}, {id:'d', mode:'t2v', text:'D'},
    {id:'e', mode:'continue', text:'E'}
  ];
  assert.deepEqual(sequenceGroups(shots).map(g => [g.root, g.shots.map(s => s.text)]),
    [['a',['A','B','C']], ['d',['D','E']]]);
  assert.equal(sequenceGroups([{id:'orphan',mode:'continue'}])[0].root, null);
});

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
