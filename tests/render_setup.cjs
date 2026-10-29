// Run the shipped app, not a copy of the notice logic. Minimal DOM; no browser/network.
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const cfg = JSON.parse(fs.readFileSync(0, 'utf8'));
const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
const nodes = new Map();
for (const [, id] of html.matchAll(/id="([^"]+)"/g)) {
  nodes.set('#' + id, { hidden: false, textContent: '', addEventListener() {}, setAttribute() {}, focus() {} });
}
const document = {
  querySelector(s) { if (s === '.tabs') return { addEventListener() {} }; if (!nodes.has(s)) throw Error('missing real DOM element: ' + s); return nodes.get(s); },
  addEventListener() {},
};
const requests = [];
const WizardApp = { ready() {}, back: { register() {} }, hosted: true };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8'), {
  document, window: { WizardApp }, WizardApp, URL, URLSearchParams,
  location: new URL('https://wizard.example/apps/wizard-search/'),
  fetch(url) {
    requests.push(url);
    if (url.endsWith('api/config')) return Promise.resolve({ ok: true, json: async () => cfg });
    if (url.endsWith('api/overview-provider')) return Promise.resolve({ ok: true, json: async () => ({ mode: 'off' }) });
    throw Error('unexpected request: ' + url);
  },
  setTimeout() {},
});
setImmediate(() => process.stdout.write(JSON.stringify({
  setupHidden: nodes.get('#setup').hidden,
  status: nodes.get('#setup-status').textContent,
  notice: nodes.get('#policy-notice')?.textContent,
  noticeHidden: nodes.get('#policy-notice')?.hidden,
  requests,
})));
