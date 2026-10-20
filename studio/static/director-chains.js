(function (root) {
  'use strict';
  function orderJobs(selected, all = selected) {
    const byId = new Map(all.map(j => [j.id, j]));
    const included = new Map(selected.map(j => [j.id, j]));
    for (const job of selected) {
      const parent = byId.get(job.director_parent_id);
      if (parent && parent.film_id === job.film_id) included.set(parent.id, parent);
    }
    const children = new Map();
    for (const job of included.values()) {
      if (job.director_parent_id && included.has(job.director_parent_id) && job.director_parent_id !== job.id) {
        const rows = children.get(job.director_parent_id) || [];
        rows.push(job);
        children.set(job.director_parent_id, rows);
      }
    }
    const result = [], visited = new Set();
    function visit(job) {
      if (visited.has(job.id)) return;
      visited.add(job.id);
      result.push(job);
      (children.get(job.id) || []).sort((a, b) =>
        (Number(a.shot_index) || 0) - (Number(b.shot_index) || 0) ||
        (Number(a.created_at) || 0) - (Number(b.created_at) || 0)).forEach(visit);
    }
    for (const job of selected) visit(included.get(job.director_parent_id) || job);
    for (const job of included.values()) visit(job);
    return result;
  }
  function sceneParents(shots) {
    const parents = new Map();
    let parent = null, chapter = null;
    for (const shot of shots) {
      const nextChapter = shot.chapter || 'Bölüm 1';
      if (nextChapter !== chapter) parent = null;
      chapter = nextChapter;
      if (shot.mode !== 'continue') parent = shot.id;
      else if (parent) parents.set(shot.id, parent);
    }
    return parents;
  }
  const api = {orderJobs, sceneParents};
  if (typeof module !== 'undefined') module.exports = api;
  root.H3DirectorChains = api;
})(globalThis);
