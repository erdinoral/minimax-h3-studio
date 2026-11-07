const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const { test } = require("node:test");

const app = fs.readFileSync("studio/static/app.js", "utf8");
const html = fs.readFileSync("studio/static/index.html", "utf8");
const i18n = fs.readFileSync("studio/static/i18n.js", "utf8");
const start = app.indexOf("  // Gallery select all.");
const end = app.indexOf("  // End gallery select all.", start);
assert.ok(start >= 0 && end > start, "select-all helper should exist");
const context = {};
vm.runInNewContext(`${app.slice(start, end)}\nthis.next = gallerySelectAllNext;`, context);
const pick = (all, picked) => JSON.parse(JSON.stringify(context.next(all, picked)));

test("Select all picks every listed item, then clears", () => {
  assert.deepEqual(pick(["a", "b", "c"], ["b"]), { full: false, next: ["a", "b", "c"] });
  assert.deepEqual(pick(["a", "b"], ["b", "a"]), { full: true, next: [] });
});

test("stale picks of deleted items do not count as a full selection", () => {
  assert.deepEqual(pick(["a", "b"], ["a", "gone"]), { full: false, next: ["a", "b"] });
  assert.deepEqual(pick([], ["gone"]), { full: false, next: [] });
});

test("the button is wired for videos and photos and has both languages", () => {
  assert.match(html, /id="btn-gallery-select-all"/);
  assert.match(app, /\$\("btn-gallery-select-all"\)\?\.addEventListener\("click", toggleGallerySelectAll\);/);
  assert.match(app, /state\.galleryPhotoPickNames = next;\s*patchGalleryPhotoSelection\(\);/);
  assert.match(app, /state\.galleryVideoPickIds = next;\s*patchGalleryVideoSelection\(\);/);
  assert.match(app, /event\.target\.closest\?\.\("input, textarea, select, \[contenteditable='true'\]"\)/, "Ctrl+A still selects text in fields");
  for (const key of ["gallery.selectAll", "gallery.selectNone", "gallery.selectAllTitle"]) {
    assert.equal(i18n.split(`"${key}":`).length - 1, 2, key);
  }
});
