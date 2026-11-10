const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const STATIC = "studio/static";
const source = fs.readFileSync(path.join(STATIC, "video-labels.js"), "utf8");
const html = fs.readFileSync(path.join(STATIC, "index.html"), "utf8");
const app = fs.readFileSync(path.join(STATIC, "app.js"), "utf8");

test("preview layout matches the server placement rule", () => {
  const body = source.match(/function layout\([\s\S]*?\r?\n  }\r?\n/)[0];
  const layout = vm.runInNewContext(`(${body.replace("function layout", "function")})`);
  assert.deepEqual([...layout({ x: 0.5, y: 0.5, pointer: false }, 1000, 500, 200, 40)], [400, 230]);
  const [left, top] = layout({ x: 1, y: 1, pointer: false }, 1000, 500, 200, 40);
  assert.ok(left + 200 <= 985 && top + 40 <= 485);
  const [pl, pt] = layout({ x: 0.2, y: 0.2, pointer: true }, 1000, 500, 200, 40);
  assert.ok(pl > 200 && pt > 100);
});

test("labels button follows the open player clip", () => {
  const handlers = {};
  const button = { disabled: true, title: "" };
  const document = {
    readyState: "complete",
    getElementById: (id) => (id === "btn-video-labels" ? button : null),
    addEventListener: (name, fn) => { handlers[name] = fn; },
  };
  vm.runInNewContext(source, { document, window: { t: (k) => k } });
  assert.equal(button.disabled, true);
  assert.equal(typeof button.onclick, "function");
  handlers["h3-player-clip"]({ detail: { id: "abc", width: 640, height: 360 } });
  assert.equal(button.disabled, false);
  assert.equal(button.title, "labels.hint");
  handlers["h3-player-clip"]({ detail: null });
  assert.equal(button.disabled, true);
});

test("player, purpose chips and look presets expose the explainer workflow", () => {
  assert.match(html, /id="btn-video-labels" data-i18n="labels\.open"/);
  assert.match(html, /<script src="\/static\/video-labels\.js\?v=\d+"><\/script>/);
  assert.equal((html.match(/data-purpose="explainer"/g) || []).length, 2);
  assert.match(html, /<option value="explainer">/);
  assert.match(app, /const CINEMA_PURPOSE_KEYS = \[[^\]]*"explainer"/);
  assert.match(app, /explainer: \["technical_cutaway", "xray", "blueprint"/);
  for (const look of ["technical_cutaway", "xray", "blueprint"]) {
    assert.match(app, new RegExp(`\\n    ${look}: \\{\\r?\\n      camera:`), look);
    assert.match(app, new RegExp(`\\["${look}", "`), look);
  }
});
