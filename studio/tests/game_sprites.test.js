const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { test } = require("node:test");

const gameSource = fs.readFileSync("studio/static/game-sprites.js", "utf8");
const helpersStart = gameSource.indexOf("  // Game sprite helpers.");
const helpersEnd = gameSource.indexOf("  // End game sprite helpers.");
assert.ok(helpersStart >= 0 && helpersEnd > helpersStart, "game sprite helpers should be marked");

function helpers() {
  const context = {};
  vm.runInNewContext(
    `${gameSource.slice(helpersStart, helpersEnd)}
    this.api = { GAME_ANIMATIONS, GAME_CELLS, gameSets, gameJobState, spriteSettingsPayload, fitZoom, seamFrames };`,
    context,
  );
  return context.api;
}

const appSource = fs.readFileSync("studio/static/app.js", "utf8");
const viewStart = appSource.indexOf("  // Motion player view.");
const viewEnd = appSource.indexOf("  function bindMotionView()", viewStart);

function classList(initial = []) {
  const set = new Set(initial);
  return {
    contains: (name) => set.has(name),
    toggle(name, on) { if (on ?? !set.has(name)) set.add(name); else set.delete(name); },
    add: (name) => set.add(name),
    remove: (name) => set.delete(name),
  };
}

function viewHarness(tab, jobs) {
  const els = {
    "motion-view": { dataset: {} },
    "motion-view-result": { dataset: {}, title: "" },
    "motion-view-badge": { textContent: "" },
    "motion-view-live": { textContent: "" },
    "mv-result-empty-body": { textContent: "" },
    player: { pause() {} },
  };
  const state = { jobs, v2vVideos: [], pendingMotionLongId: null };
  const context = {
    state,
    window: {},
    document: { body: { classList: classList([tab]) }, querySelectorAll: () => [], dispatchEvent() {} },
    CustomEvent: class { constructor(type, init) { this.detail = init?.detail; } },
    $: (id) => els[id] || null,
    tt: (key) => key,
    tf: (key) => key,
    jobLane: (job) => job.lane || "scene",
  };
  vm.runInNewContext(appSource.slice(viewStart, viewEnd), context);
  return { context, state, els };
}

test("game jobs group by set, newest set first, animations in preset order", () => {
  const { gameSets } = helpers();
  const job = (id, set, animation, created) => ({ id, created_at: created, game: { set_id: set, animation } });
  const sets = gameSets([
    job("a", "old", "run", 10),
    job("b", "new", "jump", 30),
    job("c", "new", "idle", 31),
    job("d", "old", "idle", 11),
    { id: "scene", created_at: 99 },
  ]);
  assert.deepEqual([...sets.map((s) => s.id)], ["new", "old"]);
  assert.deepEqual([...sets[0].jobs.map((j) => j.game.animation)], ["idle", "jump"]);
  assert.deepEqual([...sets[1].jobs.map((j) => j.game.animation)], ["idle", "run"]);
});

test("a broken or empty mask is never reported as a finished sprite", () => {
  const { gameJobState } = helpers();
  const done = (result) => ({ status: "done", game: { result } });
  assert.equal(gameJobState({ status: "queued", game: {} }), "queued");
  assert.equal(gameJobState({ status: "running", game: {} }), "running");
  assert.equal(gameJobState({ status: "error", game: {} }), "error");
  assert.equal(gameJobState({ status: "cancelled", game: {} }), "error");
  assert.equal(gameJobState(done(null)), "ready");
  assert.equal(gameJobState(done({ ok: false, status: "failed" })), "failed");
  assert.equal(gameJobState(done({ ok: false, status: "ok" })), "failed");
  assert.equal(gameJobState(done({ ok: true, status: "warn" })), "warn");
  assert.equal(gameJobState(done({ ok: true, status: "ok" })), "ok");
});

test("sprite settings map to the API names and blank fields fall back to presets", () => {
  const { spriteSettingsPayload } = helpers();
  const base = { cell: 64, frames: "", fps: "", palette: 0, tolerance: 30, hole: 18, edge: 1, detail: "balanced", loopStart: "", loopEnd: "" };
  assert.deepEqual({ ...spriteSettingsPayload(base) }, {
    cell: 64, palette: 0, tolerance: 30, hole_tolerance: 18, edge_clean: 1, detail: "balanced",
  });
  const custom = spriteSettingsPayload({ ...base, cell: "128", frames: "12", fps: "15", palette: "16", loopStart: "0.5", loopEnd: "1.75" });
  assert.equal(custom.cell, 128);
  assert.equal(custom.frames, 12);
  assert.equal(custom.fps, 15);
  assert.equal(custom.palette, 16);
  assert.equal(custom.loop_start, 0.5);
  assert.equal(custom.loop_end, 1.75);
  assert.equal(spriteSettingsPayload({ ...base, cell: 48 }).cell, 64, "unknown cells fall back to 64");
  assert.equal("frames" in spriteSettingsPayload({ ...base, frames: "abc" }), false);
});

test("pixel zoom stays a whole number and the seam view shows last frames before the first", () => {
  const { fitZoom, seamFrames } = helpers();
  assert.equal(fitZoom(64, 64, 300, 200), 3);
  assert.equal(fitZoom(64, 64, 40, 40), 1);
  assert.equal(fitZoom(0, 64, 300, 300), 1);
  assert.deepEqual([...seamFrames(8)], [6, 7, 0, 1]);
  assert.deepEqual([...seamFrames(3)], [2, 0]);
  assert.deepEqual([...seamFrames(1)], []);
});

test("presets offer the requested cells and loop rules", () => {
  const { GAME_ANIMATIONS, GAME_CELLS } = helpers();
  assert.deepEqual([...GAME_CELLS], [32, 64, 128]);
  const loops = Object.fromEntries(GAME_ANIMATIONS.map((a) => [a.id, a.loop]));
  assert.equal(loops.idle, true);
  assert.equal(loops.walk, true);
  assert.equal(loops.run, true);
  assert.equal(loops.jump, false);
  assert.equal(loops.attack, false);
  const py = fs.readFileSync("studio/lib/game_sprites.py", "utf8");
  for (const anim of GAME_ANIMATIONS) assert.match(py, new RegExp(`"${anim.id}": \\{"loop": ${anim.loop ? "True" : "False"},`), `${anim.id} loop matches backend`);
});

test("the Game tab reuses Workspace / Result with its own Ready mark", () => {
  const sprite = { id: "g", lane: "game", status: "done", output: { url: "/clip/g" } };
  const motion = { id: "m", lane: "motion", status: "running", progress: 40 };
  const { context, state, els } = viewHarness("ws-game", [sprite, motion]);
  context.noteMotionResults({ g: "running" });
  assert.equal(state.gameResultUnseen, true);
  assert.equal(state.motionResultUnseen, false, "a sprite clip does not light the Motion badge");
  context.syncMotionResultBadge();
  assert.equal(els["motion-view-result"].dataset.state, "ready");
  context.setMotionView("result");
  assert.equal(state.gameResultUnseen, false);
  assert.equal(context.motionResultStatus(state.jobs).state, "idle", "Motion jobs do not count in the Game lane");
  context.showMotionResult();
  assert.equal(state.motionView, "result");
  assert.equal(els["mv-result-empty-body"].textContent, "game.resultEmptyBody");
});

test("the Game tab, panel, stage and results exist for every element the module uses", () => {
  const html = fs.readFileSync("studio/static/index.html", "utf8");
  assert.match(html, /<button type="button" class="chip" data-ws="game" id="ws-game" role="tab"/);
  assert.match(html, /<div id="panel-workspace-game" class="game-panel hidden">/);
  assert.match(html, /class="mb-stage gs-stage hidden" id="gs-stage"/);
  assert.match(html, /id="prod-lane-game"/);
  assert.match(html, /<script src="\/static\/game-sprites\.js\?v=\d+"><\/script>/);
  const stage = html.slice(html.indexOf('id="player-stage"'), html.indexOf('class="player-actions"'));
  assert.ok(stage.includes('id="gs-stage"'), "sprite preview lives inside the player stage");
  const prompt = html.slice(html.indexOf('class="zone zone-prompt'), html.indexOf('class="zone zone-lora'));
  assert.ok(prompt.includes('id="game-results"'), "results live in the prompt zone");
  const ids = new Set([...gameSource.matchAll(/\$\("([a-z0-9-]+)"\)/g)].map((m) => m[1]));
  for (const id of ids) assert.ok(html.includes(`id="${id}"`), `index.html has #${id}`);
  assert.match(html, /data-i18n="game\.identityNote"/, "identity preservation is described as not guaranteed");
});

test("Motion controls stay out of the Game tab and the sprite preview stays pixel sharp", () => {
  const css = fs.readFileSync("studio/static/app.css", "utf8");
  assert.match(css, /body\.ws-game \.zone-prompt > :not\(#game-results\),/);
  assert.match(css, /body:not\(\.ws-game\) #game-results,/);
  assert.match(css, /body\.ws-game\.mv-result \.mb-stage,\s*body\.ws-motion\.mv-result \.mb-stage \{/);
  assert.match(css, /\.gs-view canvas,\s*\.gs-view img \{[^}]*image-rendering: pixelated;/);
  const robot = fs.readFileSync("studio/static/motion-robot.js", "utf8");
  assert.match(robot, /classList\.contains\("ws-motion"\)/, "robot stage only mounts in Motion");
  assert.match(appSource, /\$\("panel-workspace-scene"\)\?\.classList\.toggle\("hidden", next === "director" \|\| next === "game"\);/);
  assert.match(appSource, /const PROD_LANES = \[[^\]]*"game"/);
});

test("job lists refresh the module without a second poll and unknown 404s explain the restart", () => {
  assert.match(appSource, /dispatchEvent\(new CustomEvent\("h3-jobs", \{ detail: \{ jobs: state\.jobs \} \}\)\)/);
  assert.doesNotMatch(gameSource, /setInterval\(/, "the module must not poll on its own");
  assert.match(gameSource, /addEventListener\("h3-jobs"/);
  assert.match(gameSource, /game\.backendOld/);
});
