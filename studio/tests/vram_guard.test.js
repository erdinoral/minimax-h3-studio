const test = require("node:test");
const assert = require("node:assert");
const { plan } = require("../static/vram-guard.js");

const SIZES = {
  1088: [1920, 1088],
  768: [1344, 768],
  736: [1280, 736],
  608: [1056, 608],
  480: [864, 480],
  352: [608, 352],
};
const sizeOf = (q) => SIZES[q];
const req = (quality, duration, extra = {}) => ({ quality, duration, refImages: 0, ...extra });

test("settings that rendered on a 16 GB card pass silently", () => {
  assert.strictEqual(plan(req("1088", 5), sizeOf, 16), null);
  assert.strictEqual(plan(req("768", 10), sizeOf, 16), null);
  assert.strictEqual(plan(req("736", 10), sizeOf, 16), null);
  assert.strictEqual(plan(req("608", 15), sizeOf, 16), null);
  assert.strictEqual(plan(req("1088", 5, { refImages: 3 }), sizeOf, 16), null);
  assert.strictEqual(plan(req("768", 10, { refImages: 3 }), sizeOf, 16), null);
});

test("settings that ran out of memory on a 16 GB card warn", () => {
  for (const [q, d] of [["1088", 6], ["1088", 10], ["1088", 15], ["768", 15], ["736", 15]]) {
    assert.ok(plan(req(q, d), sizeOf, 16), `${q}p ${d}s should warn`);
  }
  assert.ok(plan(req("1088", 10, { refImages: 3 }), sizeOf, 16));
});

test("unknown VRAM skips the check", () => {
  assert.strictEqual(plan(req("1088", 15), sizeOf, null), null);
});

test("options shorten, lower resolution, and split into Continuum parts", () => {
  const result = plan(req("1088", 10, { canSplit: true }), sizeOf, 16);
  assert.deepStrictEqual(result.options, [
    { kind: "shorter", duration: 5 },
    { kind: "lower", quality: "768" },
    { kind: "split", duration: 4, chunks: 3 },
  ]);
});

test("split is only offered when Continuum is available and not already on", () => {
  assert.ok(!plan(req("1088", 10), sizeOf, 16).options.some((o) => o.kind === "split"));
  assert.ok(!plan(req("1088", 10, { canSplit: true, continuum: true }), sizeOf, 16).options.some((o) => o.kind === "split"));
});

test("motion transfer parts are fixed at 5 s, so only resolution can change", () => {
  const result = plan(req("1088", 15, { motion: true, canSplit: true }), sizeOf, 16);
  assert.deepStrictEqual(result.options, [{ kind: "lower", quality: "768" }]);
  assert.strictEqual(plan(req("768", 15, { motion: true }), sizeOf, 16), null);
});

test("a larger card scales the budget", () => {
  assert.strictEqual(plan(req("1088", 10), sizeOf, 32), null);
});
