// Drives web/app.js's AI overview box with a tiny fake DOM and a fake EventSource (wizard-search#58).
// Used by tests/test_overview.py. Prints one JSON line: what the #ov box shows for each scripted stream.
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const els = {};
function el(sel) {
  if (!els[sel]) {
    els[sel] = {
      sel, hidden: sel === '#lb', value: '', innerHTML: '', textContent: '', disabled: false, dataset: {},
      style: {}, classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
      addEventListener() {}, setAttribute(k, v) { this[k] = v; }, getAttribute(k) { return this[k]; },
      toggleAttribute() {}, focus() {}, blur() {}, closest: () => null, querySelector: () => el(sel + ' *'), querySelectorAll: () => [],
    };
  }
  return els[sel];
}
let href = 'https://box.example/wizard-search/';
const document = {
  title: 'Search', documentElement: el('html'), body: el('body'),
  querySelector: el, querySelectorAll: () => [], addEventListener() {}, getElementById: id => el('#' + id),
  createElement: t => el('new-' + t + Math.random()),
};
const config = { state: 'ready', capabilities: { web: true, images: true, overview: true }, switches: {} };
let script = [];
function FakeES() {
  const ls = {};
  this.close = () => {};
  this.addEventListener = (k, f) => { (ls[k] ||= []).push(f); };
  const events = script;
  setTimeout(() => { for (const [k, d] of events) (ls[k] || []).forEach(f => f({ data: JSON.stringify(d) })); }, 0);
}
const ctx = {
  document, console, URL, URLSearchParams, setTimeout, clearTimeout, Promise, JSON,
  location: { get href() { return href; }, get pathname() { return new URL(href).pathname; }, get search() { return new URL(href).search; } },
  history: { state: { __wizardAppGuard: true }, replaceState(s, _t, u) { this.state = s; href = String(u); }, pushState() {} },
  fetch: async url => ({ ok: true, json: async () => (String(url).includes('api/config') ? config : String(url).includes('api/images') ? { images: [] } : { results: [] }) }),
  EventSource: FakeES, requestAnimationFrame: f => setTimeout(f, 0),
  scrollTo() {}, addEventListener() {}, innerWidth: 390,
  WizardApp: { hosted: true, ready() {}, back: { register() { return () => {}; } } },
};
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'web', 'app.js'), 'utf8'), ctx);

const tick = () => new Promise(r => setTimeout(r, 20));
const box = () => ({ hidden: !!el('#ov').hidden, html: el('#ov').innerHTML });
const SRC = [{ n: 1, url: 'https://ex.example/a', title: 'A', host: 'ex.example' }];
(async () => {
  const out = {};
  script = [['sources', { sources: SRC }], ['done', { model: 'm', answer: '', error: 'no answer' }]];
  await ctx.WizardSearch.run('asdkjh qwe'); await tick(); out.no_answer = box();
  script = [['sources', { sources: SRC }], ['delta', { t: 'That feeling is called anemoia.' }], ['done', { model: 'm', answer: 'That feeling is called anemoia.' }]];
  await ctx.WizardSearch.run('word for nostalgia for a time you never lived'); await tick(); out.ungrounded = box();
  script = [['sources', { sources: SRC }], ['delta', { t: 'Use hum to search [1].' }], ['done', { model: 'm', answer: 'Use hum to search [1].' }]];
  await ctx.WizardSearch.run('find a song by humming'); await tick(); out.grounded = box();
  console.log(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
