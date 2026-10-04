const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { test } = require("node:test");

const source = fs.readFileSync("studio/static/app.js", "utf8");
const start = source.indexOf("  function playerVideoItems() {");
const end = source.indexOf("  function appendDirectorMsg(", start);
assert.ok(start >= 0 && end > start, "player navigation functions should exist");

test("gallery hydration enables arrows and excludes deleted jobs", async () => {
  const next = { classList: { toggle(_name, hidden) { this.hidden = hidden; } }, disabled: false };
  const prev = { classList: { toggle(_name, hidden) { this.hidden = hidden; } }, disabled: false };
  const state = {
    selectedJobId: "middle",
    galleryItems: [],
    galleryLoaded: false,
    jobs: [{ id: "middle", status: "done", output: { url: "/clip/middle" } }],
  };
  const context = {
    state,
    $: (id) => id === "btn-player-next" ? next : prev,
    fetch: async () => ({ ok: true, json: async () => ({ items: [
      { id: "newest", url: "/g/newest", done_at: 3 },
      { id: "middle", url: "/g/middle", done_at: 2 },
      { id: "oldest", url: "/g/oldest", done_at: 1 },
    ] }) }),
    showPlayerVideo() {},
    setClipPrompt() {},
    tt: () => "s",
  };
  vm.runInNewContext(source.slice(start, end), context);
  context.syncPlayerNavigation();
  assert.equal(next.disabled, true);
  assert.equal(prev.disabled, true);
  await context.refreshPlayerNavigation("middle");
  assert.equal(next.disabled, false);
  assert.equal(prev.disabled, false);
  assert.equal(next.classList.hidden, false);
  assert.equal(prev.classList.hidden, false);

  state.galleryItems = state.galleryItems.filter((item) => item.id !== "middle");
  assert.deepEqual(Array.from(context.playerVideoItems(), (item) => item.id), ["newest", "oldest"]);
});

test("deletion picks older video, falling back to newer at the end", () => {
  const context = { state: {}, $: () => null };
  vm.runInNewContext(source.slice(start, end), context);
  const items = ["newest", "middle", "oldest"].map((id) => ({ id }));
  assert.equal(context.adjacentVideoAfterDeletion(items, "middle", ["middle"]).id, "oldest");
  assert.equal(context.adjacentVideoAfterDeletion(items, "oldest", ["oldest"]).id, "middle");
  assert.equal(context.adjacentVideoAfterDeletion(items, "middle", ["middle", "oldest"]).id, "newest");
});

test("left arrow opens newer and right arrow opens older", async () => {
  const shown = [];
  const state = { selectedJobId: "middle", galleryItems: [], galleryLoaded: false, jobs: [] };
  const context = {
    state,
    $: () => null,
    fetch: async () => ({ ok: true, json: async () => ({ items: [
      { id: "newest", url: "/g/newest", done_at: 3 },
      { id: "middle", url: "/g/middle", done_at: 2 },
      { id: "oldest", url: "/g/oldest", done_at: 1 },
    ] }) }),
    showPlayerVideo(_url, id) { shown.push(id); state.selectedJobId = id; },
    setClipPrompt() {},
    tt: () => "s",
  };
  vm.runInNewContext(source.slice(start, end), context);
  await context.navigatePlayerVideo("next");
  assert.equal(shown.at(-1), "newest");
  state.selectedJobId = "middle";
  await context.navigatePlayerVideo("previous");
  assert.equal(shown.at(-1), "oldest");
});
