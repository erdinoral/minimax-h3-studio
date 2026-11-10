const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const STATIC = "studio/static";
const source = fs.readFileSync(path.join(STATIC, "i18n.js"), "utf8");

function boot({ stored = null, browser = [] } = {}) {
  const handlers = {};
  const window = {};
  const saved = {};
  const context = {
    window,
    navigator: { languages: browser, language: browser[0] },
    document: { addEventListener: (name, fn) => { handlers[name] = fn; }, querySelectorAll: () => [], querySelector: () => null, getElementById: () => null, documentElement: {}, dispatchEvent() {} },
    localStorage: { getItem: () => stored, setItem: (k, v) => { saved[k] = v; } },
    CustomEvent: function CustomEvent() {},
  };
  vm.runInNewContext(source, context);
  return { window, saved };
}

const holes = (s) => (String(s).match(/\{\w+\}/g) || []).sort().join(",");

test("French, Spanish and German packs cover every English key with the same placeholders", () => {
  const { en } = boot().window.H3_I18N;
  for (const lang of ["fr", "es", "de"]) {
    const pack = JSON.parse(fs.readFileSync(path.join(STATIC, "i18n", `${lang}.json`), "utf8"));
    assert.deepEqual(Object.keys(pack).sort(), Object.keys(en).sort(), lang);
    for (const [key, value] of Object.entries(en)) assert.equal(holes(pack[key]), holes(value), `${lang}: ${key}`);
  }
});

test("language choice comes from storage, then the browser, then English", () => {
  assert.equal(boot({ stored: "fr" }).window.h3Lang(), "fr");
  assert.equal(boot({ browser: ["de-DE", "en"] }).window.h3Lang(), "de");
  assert.equal(boot({ browser: ["it-IT"] }).window.h3Lang(), "en");
  const { window, saved } = boot({ stored: "tr" });
  window.setH3Lang("es");
  assert.equal(window.h3Lang(), "es");
  assert.equal(saved["h3-lang"], "es");
  window.setH3Lang("xx");
  assert.equal(window.h3Lang(), "en");
});

test("a language pack that is still loading falls back to English text", () => {
  const { window } = boot({ stored: "es" });
  assert.equal(window.t("prod.ready"), window.H3_I18N.en["prod.ready"]);
  window.H3_I18N.es = { "prod.ready": "Listo" };
  assert.equal(window.t("prod.ready"), "Listo");
  assert.equal(window.t("sec"), window.H3_I18N.en.sec);
});

test("language menu opens from the toggle and closes after a choice or an outside click", () => {
  const classes = (initial = []) => {
    const set = new Set(initial);
    return { contains: (c) => set.has(c), toggle: (c, on) => (on ? set.add(c) : set.delete(c)) };
  };
  const attrs = {};
  const toggle = { focus() {}, setAttribute: (k, v) => { attrs[k] = v; }, closest: (s) => (s === "#lang-toggle" ? toggle : null) };
  const option = { dataset: { lang: "de" }, classList: classes(["lang-option"]), setAttribute() {}, focus() {}, closest: (s) => (s === "[data-lang]" ? option : null) };
  const listeners = {};
  const box = {
    classList: classes(),
    contains: (el) => el === toggle || el === option,
    querySelector: () => null,
    querySelectorAll: () => [option],
    addEventListener: (name, fn) => { listeners[name] = fn; },
  };
  const docHandlers = {};
  const byId = { "lang-switch": box, "lang-toggle": toggle };
  const window = {};
  const document = {
    addEventListener: (name, fn) => { (docHandlers[name] ||= []).push(fn); },
    querySelectorAll: (sel) => (sel.includes("lang-switch") ? [option] : []),
    querySelector: () => null,
    getElementById: (id) => byId[id] || null,
    documentElement: {},
    dispatchEvent() {},
  };
  vm.runInNewContext(source, {
    window, document, navigator: { languages: [] },
    localStorage: { getItem: () => "tr", setItem() {} },
    CustomEvent: function CustomEvent() {},
  });
  docHandlers.DOMContentLoaded.forEach((fn) => fn());
  listeners.click({ target: toggle });
  assert.equal(box.classList.contains("open"), true);
  assert.equal(attrs["aria-expanded"], "true");
  listeners.click({ target: option });
  assert.equal(window.h3Lang(), "de");
  assert.equal(box.classList.contains("open"), false);
  listeners.click({ target: toggle });
  docHandlers.click.forEach((fn) => fn({ target: {} }));
  assert.equal(box.classList.contains("open"), false);
});

test("every language has a switch chip and inline checks treat non-Turkish as English", () => {
  const html = fs.readFileSync(path.join(STATIC, "index.html"), "utf8");
  for (const lang of ["en", "tr", "fr", "es", "de"]) assert.match(html, new RegExp(`data-lang="${lang}"`));
  for (const file of fs.readdirSync(STATIC).filter((f) => f.endsWith(".js"))) {
    const code = fs.readFileSync(path.join(STATIC, file), "utf8");
    assert.doesNotMatch(code, /(h3Lang\?\.\(\)|h3Lang\(\)|uiLang\(\)|documentElement\.lang)\s*[!=]==\s*["']en["']/, file);
  }
});
