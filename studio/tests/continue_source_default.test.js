const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { test } = require("node:test");

const source = fs.readFileSync("studio/static/app.js", "utf8");
const start = source.indexOf("  async function fillContinueSource() {");
const end = source.indexOf("  function clearPlayer(", start);
assert.ok(start >= 0 && end > start, "continue source function should exist");

test("continue source defaults to the first visible video and preserves manual picks", async () => {
  const sel = {
    options: [],
    value: "",
    replaceChildren() { this.options = []; },
    appendChild(option) { this.options.push(option); },
  };
  const state = {
    jobs: [
      { id: "older", status: "done", created_at: 1, prompt: "older" },
      { id: "first", status: "queued", created_at: 3, prompt: "first" },
      { id: "second", status: "running", created_at: 2, prompt: "second" },
    ],
    galleryItems: [],
    continueFrom: null,
    continueSourceManual: false,
    produceMode: "continue",
  };
  const selected = [];
  const context = {
    state,
    $: () => sel,
    document: { activeElement: null, createElement: () => ({}) },
    fetch: async () => ({ json: async () => ({ items: [] }) }),
    tt: (key) => key,
    tf: (_key, values) => `${values.i}. ${values.label}`,
    setContinueMode: async (id) => { selected.push(id); },
    clearContinueMode: () => { state.continueFrom = null; },
  };
  vm.runInNewContext(source.slice(start, end), context);

  await context.fillContinueSource();
  assert.deepEqual(sel.options.map((option) => option.value), ["first", "second", "older"]);
  assert.equal(sel.value, "first");
  assert.equal(state.continueFrom, "first");

  state.continueSourceManual = true;
  state.continueFrom = "second";
  sel.value = "second";
  state.jobs.push({ id: "newest", status: "queued", created_at: 4, prompt: "newest" });
  await context.fillContinueSource();
  assert.equal(sel.value, "second", "manual choice must not jump to a new queue item");

  state.continueSourceManual = false;
  await context.fillContinueSource();
  assert.equal(sel.value, "newest", "default should track the first visible item");
  assert.equal(state.continueFrom, "newest");
  assert.deepEqual(selected, ["first", "newest"]);
});
