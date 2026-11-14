const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "../../static/src/js/app/appearance.js"), "utf8"
);

function harness(initialTheme = "system") {
  const listeners = { document: {}, body: {}, window: {} };
  const storage = new Map();
  const media = { matches: false, addEventListener(_name, callback) { this.onChange = callback; } };
  const inner = {
    dataset: { theme: initialTheme, fontScale: "md" },
    contains() { return true; },
  };
  const outer = {
    dataset: { theme: initialTheme, fontScale: "md", appearanceUser: "7" },
    querySelector() { return inner; },
    appendChild() {},
    contains() { return true; },
  };
  const chart = {
    canvas: {}, options: {
      plugins: { legend: { labels: {} }, tooltip: {} },
      scales: { x: { ticks: {}, grid: {}, title: {} } },
    },
    update() { this.updates = (this.updates || 0) + 1; },
  };
  const document = {
    readyState: "complete",
    documentElement: { dataset: {}, style: {} },
    body: { addEventListener(name, callback) { listeners.body[name] = callback; } },
    querySelector() { return outer; },
    querySelectorAll() { return [outer, inner]; },
    createElement() { return { style: {}, remove() {} }; },
    addEventListener(name, callback) { listeners.document[name] = callback; },
  };
  const window = {
    Chart: { instances: { 1: chart } },
    matchMedia() { return media; },
    addEventListener(name, callback) { listeners.window[name] = callback; },
    dispatchEvent() {},
    requestAnimationFrame(callback) { callback(); },
  };
  const localStorage = {
    setItem(key, value) { storage.set(key, value); },
    getItem(key) { return storage.get(key) || null; },
  };
  vm.runInNewContext(source, {
    document, window, localStorage,
    getComputedStyle(element) {
      return {
        color: "rgb(230, 240, 250)",
        backgroundColor: element === inner ? "rgb(16, 25, 35)" : "transparent",
      };
    },
    CustomEvent: class { constructor(name, options) { this.type = name; this.detail = options.detail; } },
  });
  return { outer, inner, media, storage, listeners, chart, document };
}

test("server theme wins at startup and HTMX changes both shell roots", () => {
  const app = harness("light");
  assert.equal(app.storage.get("ufhob.appearance.7"), '{"theme":"light","font_scale":"md"}');
  app.listeners.document["account:preferences-updated"]({
    detail: { theme: "DARK", font_scale: "XL" },
  });
  assert.equal(app.outer.dataset.theme, "dark");
  assert.equal(app.inner.dataset.fontScale, "xl");
  assert.equal(app.document.documentElement.dataset.appBootTheme, "dark");
  assert.ok(app.chart.updates >= 2);
});

test("system mode follows OS changes and ignores them in forced light", () => {
  const app = harness("system");
  assert.equal(app.outer.dataset.resolvedTheme, "light");
  app.media.matches = true;
  app.media.onChange();
  assert.equal(app.outer.dataset.resolvedTheme, "dark");
  app.listeners.document["account:preferences-updated"]({
    detail: { theme: "LIGHT", font_scale: "SM" },
  });
  app.media.matches = false;
  app.media.onChange();
  assert.equal(app.outer.dataset.resolvedTheme, "light");
  assert.equal(app.outer.dataset.theme, "light");
});

test("another tab's saved preference synchronizes this tab", () => {
  const app = harness("light");
  app.listeners.window.storage({
    key: "ufhob.appearance.7",
    newValue: '{"theme":"dark","font_scale":"lg"}',
  });
  assert.equal(app.outer.dataset.theme, "dark");
  assert.equal(app.inner.dataset.fontScale, "lg");
});
