const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { test } = require("node:test");

const source = fs.readFileSync("studio/static/app.js", "utf8");
const start = source.indexOf("  // Motion player view.");
const end = source.indexOf("  function bindMotionView()", start);
assert.ok(start >= 0 && end > start, "Motion view controller should exist");

function classList(initial = []) {
  const set = new Set(initial);
  return {
    contains: (name) => set.has(name),
    toggle(name, on) { if (on ?? !set.has(name)) set.add(name); else set.delete(name); },
    add: (name) => set.add(name),
    remove: (name) => set.delete(name),
  };
}

function harness({ motion = true, jobs = [] } = {}) {
  const events = [];
  const tabs = ["workspace", "result"].map((view) => ({
    dataset: { motionView: view },
    classList: classList(),
    attrs: {},
    tabIndex: 0,
    setAttribute(name, value) { this.attrs[name] = value; },
    focus() { this.focused = true; },
  }));
  const els = {
    "motion-view": { dataset: {} },
    "motion-view-result": { dataset: {}, title: "" },
    "motion-view-badge": { textContent: "" },
    "motion-view-live": { textContent: "" },
    "mv-result-empty-body": { textContent: "" },
    player: { paused: 0, pause() { this.paused += 1; } },
  };
  const body = { classList: classList(motion ? ["ws-motion"] : []) };
  const state = { jobs, v2vVideos: [], pendingMotionLongId: null };
  const context = {
    state,
    window: {},
    document: {
      body,
      querySelectorAll: () => tabs,
      dispatchEvent: (event) => events.push(event.detail),
    },
    CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init?.detail; } },
    $: (id) => els[id] || null,
    tt: (key) => key,
    tf: (key, map) => `${key}:${JSON.stringify(map)}`,
    jobLane: (job) => job.lane || "scene",
  };
  vm.runInNewContext(source.slice(start, end), context);
  return { context, state, els, tabs, body, events };
}

test("Motion lane status reports progress of the running job and ignores other lanes", () => {
  const { context } = harness();
  assert.deepEqual({ ...context.motionResultStatus([
    { lane: "scene", status: "running", progress: 90 },
    { lane: "motion", status: "queued" },
    { lane: "motion", status: "running", progress: 41.6 },
  ]) }, { state: "busy", pct: 42 });
  assert.equal(context.motionResultStatus([{ lane: "motion", status: "queued" }]).state, "queued");
  assert.equal(context.motionResultStatus([{ lane: "scene", status: "running" }]).state, "idle");
});

test("a finished Motion video marks Result as Ready without switching the view", () => {
  const job = { id: "a", lane: "motion", status: "done", output: { url: "/clip/a" } };
  const { context, state, els, body } = harness({ jobs: [job] });
  context.noteMotionResults({ a: "running" });
  assert.equal(state.motionResultUnseen, true);
  assert.equal(state.motionView, "workspace");
  assert.equal(body.classList.contains("mv-result"), false);
  context.syncMotionResultBadge();
  assert.equal(els["motion-view-result"].dataset.state, "ready");
  assert.equal(els["motion-view-badge"].textContent, "motion.resultReady");
  assert.equal(els["motion-view-live"].textContent, "motion.resultReadyTitle");
});

test("Ready is not raised for frames, other lanes or a Result already on screen", () => {
  const frame = { id: "f", lane: "motion", status: "done", mode: "sketch_frame" };
  const scene = { id: "s", lane: "scene", status: "done", output: { url: "/clip/s" } };
  const { context, state } = harness({ jobs: [frame, scene] });
  context.noteMotionResults({ f: "running", s: "running" });
  assert.equal(state.motionResultUnseen, false);

  const clip = { id: "m", lane: "motion", status: "done", output: { url: "/clip/m" } };
  const viewing = harness({ jobs: [clip] });
  viewing.context.setMotionView("result");
  viewing.context.noteMotionResults({ m: "running" });
  assert.equal(viewing.state.motionResultUnseen, false);
});

test("switching views updates tabs, clears Ready on Result and pauses the result video on leave", () => {
  const { context, state, els, tabs, body, events } = harness();
  state.motionResultUnseen = true;
  context.setMotionView("result");
  assert.equal(body.classList.contains("mv-result"), true);
  assert.equal(els["motion-view"].dataset.view, "result");
  assert.deepEqual(tabs.map((tab) => tab.attrs["aria-selected"]), ["false", "true"]);
  assert.deepEqual(tabs.map((tab) => tab.tabIndex), [-1, 0]);
  assert.equal(state.motionResultUnseen, false);
  const paused = els.player.paused;
  context.setMotionView("workspace", { focus: true });
  assert.equal(els.player.paused, paused + 1);
  assert.equal(tabs[0].focused, true);
  assert.deepEqual(events, ["result", "workspace"]);
  context.setMotionView("workspace");
  assert.deepEqual(events, ["result", "workspace"], "no event when the view does not change");
});

test("an explicit Play reveals Result only inside the Motion tab", () => {
  const motion = harness();
  motion.context.showMotionResult();
  assert.equal(motion.state.motionView, "result");
  const scene = harness({ motion: false });
  scene.context.showMotionResult();
  assert.equal(scene.state.motionView, "workspace");
  assert.match(source, /selectJob\(j\);\s*showMotionResult\(\);/, "job list Play reveals Result");
});

test("the view switch is an accessible tab list bound to the player stage", () => {
  const html = fs.readFileSync("studio/static/index.html", "utf8");
  const block = html.slice(html.indexOf('id="motion-view"') - 60, html.indexOf('id="player-stage"') + 20);
  assert.match(block, /role="tablist"/);
  assert.equal((block.match(/role="tab"/g) || []).length, 2);
  assert.equal((block.match(/aria-controls="player-stage"/g) || []).length, 2);
  assert.match(block, /data-i18n-aria-label="motion\.viewAria"/);
  assert.match(html, /<div class="player-stage" id="player-stage">/);
  assert.match(html, /id="mv-ref-stage"/);
  assert.match(html, /id="mv-result-empty"/);
});

test("workspace layers fade out instead of unmounting and respect reduced motion", () => {
  const css = fs.readFileSync("studio/static/app.css", "utf8");
  const off = css.match(/body\.ws-motion\.mv-result \.mb-stage \{([^}]*)\}/);
  assert.ok(off, "Result must have a rule for workspace layers");
  assert.match(off[1], /visibility: hidden/);
  assert.match(off[1], /pointer-events: none/);
  assert.doesNotMatch(off[1], /display:\s*none/);
  const reduced = css.match(/@media \(prefers-reduced-motion: reduce\) \{\s*\.motion-view-switch::before[\s\S]{0,600}/);
  assert.ok(reduced, "reduced-motion block for the view switch");
  assert.match(reduced[0], /transition: none/);
  assert.match(reduced[0], /animation: none/);
});

test("robot and sketch stages stay mounted per source and only run while the Workspace is shown", () => {
  const robot = fs.readFileSync("studio/static/motion-robot.js", "utf8");
  assert.match(robot, /const active = \(\) => present\(\) && \(window\.h3MotionView\?\.\(\) \|\| "workspace"\) === "workspace";/);
  assert.match(robot, /\$\("mb-stage"\)\?\.classList\.toggle\("hidden", !present\(\)\);/);
  assert.match(robot, /if \(!active\(\) && !recording\) \{ looping = false; return; \}/, "a take keeps the loop alive");
  assert.match(robot, /addEventListener\("h3-motion-view", sync\)/);
  const sketch = fs.readFileSync("studio/static/motion-sketch.js", "utf8");
  assert.match(sketch, /const visible = \(\) => present\(\) && \(window\.h3MotionView\?\.\(\) \|\| "workspace"\) === "workspace";/);
  assert.match(sketch, /\$\("sk-stage"\)\?\.classList\.toggle\("hidden", !present\(\)\);/);
  assert.match(sketch, /addEventListener\("h3-motion-view", sync\)/);
});
