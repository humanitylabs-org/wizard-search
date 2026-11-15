// Drives web/app.js's WizardApp.back contract with a tiny fake DOM (no browser needed).
// Used by tests/test_back.py. Prints one JSON line with the observed states.
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const els = {};
function el(sel) {
  if (!els[sel]) {
    const listeners = {};
    els[sel] = {
      sel, hidden: sel === '#lb', value: '', innerHTML: '', textContent: '', disabled: false, dataset: {},
      style: {}, classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
      addEventListener(k, f) { (listeners[k] ||= []).push(f); }, listeners,
      setAttribute(k, v) { this[k] = v; }, getAttribute(k) { return this[k]; },
      focus() {}, blur() {}, closest: () => null, querySelector: () => el(sel + ' *'), querySelectorAll: () => [],
    };
  }
  return els[sel];
}
let href = 'https://box.example/wizard-search/';
let backHandler = null;
const document = {
  title: 'Search', documentElement: el('html'), body: el('body'),
  querySelector: el, querySelectorAll: () => [], addEventListener() {}, getElementById: id => el('#' + id),
  createElement: t => el('new-' + t + Math.random()),
};
const config = { state: 'ready', capabilities: { web: true, images: true, overview: false }, switches: {} };
const ctx = {
  document, console, URL, URLSearchParams, setTimeout, clearTimeout, Promise, JSON,
  location: { get href() { return href; }, get pathname() { return new URL(href).pathname; }, get search() { return new URL(href).search; } },
  history: { state: { __wizardAppGuard: true }, replaceState(s, _t, u) { this.state = s; href = String(u); }, pushState() {} },
  fetch: async url => ({ ok: true, json: async () => (String(url).includes('api/config') ? config : String(url).includes('api/images') ? { images: [] } : { results: [] }) }),
  EventSource: function () { this.close = () => {}; this.addEventListener = () => {}; },
  scrollTo() {}, addEventListener() {}, innerWidth: 390,
  WizardApp: { hosted: true, ready() {}, back: { register(h) { backHandler = h; return () => {}; } } },
};
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'web', 'app.js'), 'utf8'), ctx);

const snap = () => ({
  q: ctx.WizardSearch.state().q, tab: ctx.WizardSearch.state().tab, box: el('#q').value,
  empty_shown: !el('#empty').hidden, results_shown: !el('#all').hidden, images_shown: !el('#images').hidden,
  url_has_q: new URL(href).searchParams.has('q'), title: document.title,
});
(async () => {
  const out = {};
  out.start_can = backHandler.canGoBack();
  await ctx.WizardSearch.run('python docs');
  out.results = snap();
  out.results_can = backHandler.canGoBack();
  out.results_back = backHandler.back();
  out.after_back = snap();
  out.after_can = backHandler.canGoBack();
  out.after_back_again = backHandler.back();
  await ctx.WizardSearch.run('python docs');
  ctx.WizardSearch.tab('images');
  out.images_back = backHandler.back();
  out.images_after = snap();
  out.images_back2 = backHandler.back();
  out.images_after2 = snap();
  console.log(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
