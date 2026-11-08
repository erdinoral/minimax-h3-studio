const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { test } = require("node:test");

const app = fs.readFileSync("studio/static/app.js", "utf8");
const sketch = fs.readFileSync("studio/static/motion-sketch.js", "utf8");
const robot = fs.readFileSync("studio/static/motion-robot.js", "utf8");
const html = fs.readFileSync("studio/static/index.html", "utf8");
const i18n = fs.readFileSync("studio/static/i18n.js", "utf8");

function section(source, startMark, endMark) {
  const start = source.indexOf(startMark);
  const end = source.indexOf(endMark, start);
  assert.ok(start >= 0 && end > start, `${startMark} section should exist`);
  return source.slice(start, end);
}

function load(source, startMark, endMark, names) {
  const context = {};
  vm.runInNewContext(`${section(source, startMark, endMark)}\nthis.out = { ${names.join(", ")} };`, context);
  return context.out;
}

const { createHistory } = load(sketch, "// Sketch history.", "// End sketch history.", ["createHistory"]);
const { motionLongGroups, motionLongSummary } = load(app, "// Long Motion card.", "// End long Motion card.",
  ["motionLongGroups", "motionLongSummary"]);
const { sketchReviewState, pickSketchReview } = load(app, "// Sketch frame review.", "// End sketch frame review.",
  ["sketchReviewState", "pickSketchReview"]);

const image = (width = 4, height = 3) => ({ width, height });

test("undoing Clear brings back the ink flag together with the pixels", () => {
  const history = createHistory(15);
  history.push(image(), false); // before the first stroke
  history.push(image(), true); // before Clear
  const cleared = history.pop(4, 3);
  assert.equal(cleared.ink, true, "undoing Clear makes the drawing sendable again");
  assert.equal(history.pop(4, 3).ink, false, "undoing the first stroke leaves an empty board");
  assert.equal(history.pop(4, 3), null);
  assert.match(sketch, /ctx\.putImageData\(last\.image, 0, 0\);\s*hasInk = last\.ink;/);
});

test("history keeps its limit and ignores steps from another canvas size", () => {
  const history = createHistory(2);
  history.push(image(), false);
  history.push(image(), true);
  history.push(image(), true);
  assert.equal(history.size, 2);
  history.push(image(8, 6), false);
  assert.equal(history.pop(4, 3), null, "an aspect change must not paint a wrong-sized step");
});

test("the drawing draft and its settings survive a reload", () => {
  assert.match(sketch, /store\.put\(DRAFT_KEY, \{ blob, width: canvas\.width, height: canvas\.height, aspect: aspectKey/);
  assert.match(sketch, /void restoreDraft\(\);/);
  assert.match(sketch, /if \(!draft\?\.blob \|\| touched \|\| hasInk\) return;/, "a fresh stroke wins over a late restore");
  assert.match(sketch, /localStorage\.setItem\(SETTINGS_KEY, JSON\.stringify\(\{ tool, size, color, method, fidelity: fidelity\(\) \}\)\)/);
  assert.match(sketch, /window\.addEventListener\("pagehide"/);
});

test("a missing Edit model falls back to img2img and says so", () => {
  assert.match(sketch, /return editMissing\?\.length \? "img2img" : method;/);
  assert.match(sketch, /t\("sketch\.editMissingNote", \{ files: editMissing\.join\(", "\) \}\)/);
  assert.match(app, /sketch_method: window\.h3SketchMethod\?\.\(\) \|\| "img2img"/);
  assert.match(app, /d\.code\.startsWith\("sketch\."\)/);
});

test("a failed robot upload keeps the take for retry and download", () => {
  const upload = section(robot, "async function upload(take)", "function keepTake");
  assert.match(upload, /dropTake\(\);\s*\} catch \(error\) \{\s*keepTake\(take\);/);
  assert.match(robot, /window\.h3MotionStore\?\.put\(TAKE_KEY, take\)/);
  assert.match(robot, /void restoreTake\(\);/);
  assert.match(robot, /link\.download = `robot_take_\$\{stamp\}\.mjpeg`;/);
  for (const id of ["mb-take-retry", "mb-take-upload", "mb-take-download", "mb-take-discard"]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
});

test("a sent robot take opens the review player and can be watched again", () => {
  const upload = section(robot, "async function upload(take)", "function keepTake");
  assert.match(upload, /\}\s*if \(ready\) \{ lastTake = ready; openReview\(\); \}/);
  assert.match(robot, /\$\("mb-watch"\)\?\.addEventListener\("click", openReview\)/);
  for (const id of ["mb-review", "mb-review-video", "mb-review-keep", "mb-review-retake", "mb-watch"]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
  assert.match(app, /video\.onclick = \(\) => \{ if \(video\.paused\)/);
});

function presetRunner() {
  const ui = { goal: null, run: false, goalRun: false };
  const sm = { isInteracting: false };
  const modes = [];
  const context = {
    script: null, running: false, gait: "linear_1d", GAITS: ["linear_1d"], renderGaits() {},
    mb: () => ({ ui, character: { sm }, setMode: (name) => modes.push(name) }),
  };
  vm.runInNewContext(`${section(robot, "  function presetTick()", "  async function until(")}
    this.presetTick = presetTick; this.endScript = endScript;
    this.start = (steps) => { script = { steps, index: 0 }; };
    this.state = () => ({ script, gait });`, context);
  return { ...context, ui, sm, modes };
}

test("a preset gives the next goal only after the last one is reached and interactions end", () => {
  const r = presetRunner();
  r.start([{ goal: [21.5, 0], run: true }, { goal: [19.3, 11] }]);
  r.presetTick();
  assert.deepEqual([...r.ui.goal], [21.5, 0]);
  assert.equal(r.ui.run, true);
  assert.deepEqual(r.modes, ["linear_1d"]);
  r.presetTick();
  assert.deepEqual([...r.ui.goal], [21.5, 0]);
  r.ui.goal = null;
  r.sm.isInteracting = true;
  r.presetTick();
  assert.equal(r.ui.goal, null);
  r.sm.isInteracting = false;
  r.presetTick();
  assert.deepEqual([...r.ui.goal], [19.3, 11]);
  assert.equal(r.ui.run, false);
  r.endScript();
  assert.equal(r.state().script, null);
  assert.equal(r.ui.goal, null);
});

test("a preset's walking style is applied and kept as the selected gait", () => {
  const r = presetRunner();
  r.start([{ mode: "zombie_1d", goal: [0, 0] }]);
  r.presetTick();
  assert.deepEqual(r.modes, ["zombie_1d"]);
  assert.equal(r.state().gait, "zombie_1d");
});

test("presets run on a fresh course layout and every preset has a label in both languages", () => {
  const run = section(robot, "async function runPreset(", "function setSeconds(");
  assert.match(run, /setLayout\("course", true\);/);
  assert.match(run, /if \(withRecording\) \{ setSeconds\(plan\.seconds\); await record\(\); \}/);
  const keys = section(robot, "const PRESETS = {", "const OBJECTS").match(/^\s{4}(\w+): \{/gm).map((line) => line.trim().split(":")[0]);
  assert.deepEqual(keys, ["vault", "parkour", "parkourSit", "zombie", "sneak", "vogue", "injured"]);
  const cams = ["behind", "side", "front", "tripod", "wide"].map((c) => `motion.cam.${c}`);
  const objects = ["MidJumpSP", "AvoidanceSP", "SmallJumpSP", "SitSP"].flatMap((o) =>
    ["obj", "objPh", "objDefault", "verb"].map((group) => `motion.${group}.${o}`));
  for (const key of [...keys.map((k) => `motion.preset.${k}`), ...cams, "motion.world.gym", "motion.world.course", ...objects,
    "motion.presets", "motion.presetTry", "motion.presetRecord", "motion.presetHint", "motion.presetTimeout", "motion.camera",
    "motion.worldLabel", "motion.objects", "motion.objectsHint", "motion.promptAdd", "motion.promptAdded", "motion.promptNone"]) {
    assert.equal(i18n.split(`"${key}":`).length - 1, 2, `${key} should be defined once per language`);
  }
});

test("a take records which object the robot used and when, and the prompt names them", () => {
  const rec = section(robot, "async function record()", "async function upload(take)");
  assert.match(rec, /events\.push\(\{ t: frames\.length \/ FPS, kind: active\.name \}\)/);
  assert.match(rec, /savedAt: Date\.now\(\), events \}\)/);
  const context = {
    objectNames: () => ({ MidJumpSP: "stone wall" }),
    t: (key, args = {}) => Object.entries(args).reduce((s, [k, v]) => s.replace(`{${k}}`, v), {
      "motion.verb.MidJumpSP": "At {t} s vaults over {obj}.", "motion.verb.SitSP": "At {t} s sits on {obj}.",
      "motion.objDefault.SitSP": "a bench",
    }[key] || key),
  };
  vm.runInNewContext(`${section(robot, "  function promptTimeline(", "  function addTimelineToPrompt(")}
    this.promptTimeline = promptTimeline;`, context);
  assert.equal(context.promptTimeline([{ t: 7.25, kind: "MidJumpSP" }, { t: 15, kind: "SitSP" }]),
    "At 7.3 s vaults over stone wall. At 15.0 s sits on a bench.");
});

test("the camera choice changes the framing and the tripod only pans", () => {
  assert.match(robot, /const \[back, side, height\] = CAMERAS\[cameraMode\];/);
  assert.match(section(robot, "function follow()", "function draw()"),
    /if \(cameraMode === "tripod"\) \{ controls\.target\.set\(ch\.pose\[0\], 0\.85, -ch\.pose\[1\]\); return; \}/);
  assert.match(robot, /`\/motionbricks\/index\.html\?capture=1\$\{layout === "course" \? "&scene=course" : ""\}`/);
  for (const id of ["mb-presets", "mb-preset-try", "mb-preset-record", "mb-cameras", "mb-layouts", "mb-objects", "mb-prompt-add", "mb-review-prompt"]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
});

function part(index, status, extra = {}) {
  return { id: `p${index}`, motion_long_id: "L", motion_long_index: index, motion_long_total: 3, status, ...extra };
}

function summary(jobs) {
  return { ...motionLongSummary(motionLongGroups(jobs).get("L")) };
}

test("long Motion parts collapse into one group with the final clip", () => {
  const groups = motionLongGroups([part(2, "done"), { id: "x" }, part(1, "done"), { id: "f", mode: "motion_long", motion_long_id: "L" }]);
  assert.equal(groups.size, 1);
  assert.deepEqual([...groups.get("L").parts.map((p) => p.id)], ["p1", "p2"]);
  assert.equal(groups.get("L").final.id, "f");
});

test("long Motion summary reports part progress, failures and merge state", () => {
  const running = summary([part(1, "done"), part(2, "running", { progress: 50 }), part(3, "queued")]);
  assert.equal(running.state, "running");
  assert.equal(running.index, 2);
  assert.equal(running.pct, 50);
  assert.equal(running.canStop, true);
  assert.equal(running.canDelete, false);

  const failed = summary([part(1, "done"), part(2, "error", { error: "OOM" }), part(3, "error", { error: "önceki" })]);
  assert.equal(failed.state, "failed");
  assert.equal(failed.index, 2);
  assert.equal(failed.error, "OOM", "the first failed part explains the chain");
  assert.equal(failed.canResume, true);

  const blocked = summary([part(1, "done"), part(2, "error"), part(3, "queued")]);
  assert.equal(blocked.canResume, false, "resume waits until nothing of this job is queued");

  const merging = summary([1, 2, 3].map((i) => part(i, "done", { motion_long_merge: "running" })));
  assert.equal(merging.state, "merging");
  assert.equal(merging.canMerge, false, "no second join while one runs");
  assert.equal(merging.canDelete, false);

  const mergeError = summary([1, 2, 3].map((i) => part(i, "done", { motion_long_merge: "error", motion_long_error: "ffmpeg" })));
  assert.equal(mergeError.state, "mergeError");
  assert.equal(mergeError.error, "ffmpeg");
  assert.equal(mergeError.canMerge, true);
  assert.equal(mergeError.canResume, false, "finished parts are never rendered again");

  const waiting = summary([1, 2, 3].map((i) => part(i, "done")));
  assert.equal(waiting.state, "waitingMerge");
  assert.equal(waiting.canMerge, true);

  const incomplete = summary([part(1, "done"), part(2, "done")]);
  assert.equal(incomplete.state, "incomplete", "a deleted part is not reported as a pending join");
  assert.equal(incomplete.canMerge, false);
  assert.equal(incomplete.canDelete, true);

  const done = summary([1, 2, 3].map((i) => part(i, "done")).concat({ id: "f", mode: "motion_long", motion_long_id: "L" }));
  assert.equal(done.state, "done");
  assert.equal(done.pct, 100);
});

test("the job list renders one long Motion card and wires resume and join retry", () => {
  assert.match(app, /const longGroup = longGroups\.get\(j\.motion_long_id\);/);
  assert.match(app, /\/api\/motion-transfer\/long\/\$\{group\.id\}\/resume/);
  assert.match(app, /\/api\/motion-transfer\/long\/\$\{group\.id\}\/assemble/);
});

test("sketch review states and the card it follows", () => {
  assert.equal(sketchReviewState(null), "empty");
  assert.equal(sketchReviewState({ status: "queued" }), "queued");
  assert.equal(sketchReviewState({ status: "running" }), "framing");
  assert.equal(sketchReviewState({ status: "done", frame_url: "/f.png" }), "awaiting");
  assert.equal(sketchReviewState({ status: "done", frame_url: "/f.png", video_job_id: "v" }), "approved");
  assert.equal(sketchReviewState({ status: "error" }), "error");

  const jobs = [
    { id: "old", mode: "sketch_frame", status: "done", frame_url: "/a", created_at: 1 },
    { id: "new", mode: "sketch_frame", status: "done", frame_url: "/b", video_job_id: "v", created_at: 3 },
    { id: "mid", mode: "sketch_frame", status: "running", created_at: 2 },
    { id: "clip", mode: "i2v", status: "done", created_at: 9 },
    { id: "dead", mode: "sketch_frame", status: "cancelled", created_at: 8 },
  ];
  assert.equal(pickSketchReview(jobs, "new").id, "new", "the stored card wins, even once approved");
  assert.equal(pickSketchReview(jobs, "dead").id, "dead", "the user's own failed card stays for a retry");
  assert.equal(pickSketchReview(jobs, "gone").id, "mid", "otherwise the newest frame still in progress or waiting");
  assert.equal(pickSketchReview([], ""), null);
});

test("approval goes through the animate endpoint and frames are never auto-rendered", () => {
  assert.match(app, /fetch\("\/api\/sketch\/frame"/);
  assert.doesNotMatch(app, /fetch\("\/api\/sketch\/video"/);
  assert.match(app, /sketchReviewPost\("animate"/);
  assert.match(app, /if \(!sketchReview\.id \|\| sketchReview\.busy\) return;/, "a double click sends one approval");
  assert.match(app, /\$\("sk-review-animate"\)\.disabled = sketchReview\.busy \|\| st !== "awaiting";/);
});

test("new Motion strings exist in Turkish and English", () => {
  const keys = [
    "sketch.makeFrame", "sketch.method", "sketch.methodEdit", "sketch.methodImg2img", "sketch.methodHint",
    "sketch.editMissing", "sketch.editMissingNote", "sketch.reviewTitle", "sketch.reviewText", "sketch.reviewTextPh",
    "sketch.regenerate", "sketch.animate", "sketch.stateQueued", "sketch.stateFraming", "sketch.stateAwaiting",
    "sketch.stateApproved", "sketch.stateError", "sketch.reviewEmpty", "sketch.frameReady", "sketch.animateQueued",
    "sketch.animateDuplicate", "sketch.regenQueued", "sketch.openFrame", "sketch.restored",
    "motion.uploadFailed", "motion.takePending", "motion.takeRetry", "motion.takeDownload", "motion.takeDiscard",
    "motion.takeDiscardConfirm", "mlong.title", "mlong.partStatus", "mlong.partMissing", "mlong.running", "mlong.queued", "mlong.failed",
    "mlong.merging", "mlong.mergeError", "mlong.waitingMerge", "mlong.incomplete", "mlong.done", "mlong.resume", "mlong.resumeTitle",
    "mlong.retryMerge", "mlong.resumed", "mlong.merged", "mlong.stopConfirm", "mlong.deleteConfirm",
    "motion.reviewTitle", "motion.reviewMsg", "motion.reviewKeep", "motion.reviewRetake", "motion.retakeHint",
    "motion.robotKeys", "pick.playPause",
  ];
  for (const key of keys) {
    const count = i18n.split(`"${key}":`).length - 1;
    assert.equal(count, 2, `${key} should be defined once per language`);
  }
});
