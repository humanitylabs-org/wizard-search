/* Fast open (issue #42): time to first paint and to a ready screen, switch off vs on, over a slow link.
 * Runs the REAL server.py (from a temp copy, so the update test can change a file) behind a small gateway that adds
 * a fixed delay to every request (a phone on a slow tailnet) and serves the REAL shared client from a wizard-ux
 * checkout. Checks: on paints from the device on the second open, opens with no network, picks up a new release on
 * the next open, and turning the switch off removes the worker and caches.
 * Usage: WIZARD_UX_WEB=<ux>/web PLAYWRIGHT_MODULE=<path>/playwright [QA_DELAY_MS=400] node qa/fast-open-browser.cjs */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const http = require('node:http'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { spawn } = require('node:child_process'), assert = require('node:assert/strict');
const repo = path.resolve(__dirname, '..'), ux = path.resolve(process.env.WIZARD_UX_WEB || '../wizard-ux/web');
const evidence = process.env.QA_EVIDENCE || path.join(repo, 'evidence');
const DELAY = Number(process.env.QA_DELAY_MS || 400);
fs.mkdirSync(evidence, { recursive: true });
const tmp = fs.mkdtempSync(path.join(process.env.TMPDIR || os.tmpdir(), 'search42-'));
for (const f of ['server.py', 'setup.json', 'openapi.json', 'SETUP.md']) fs.copyFileSync(path.join(repo, f), path.join(tmp, f));
fs.cpSync(path.join(repo, 'web'), path.join(tmp, 'web'), { recursive: true });
fs.mkdirSync(path.join(tmp, 'data'));
const setSwitch = on => fs.writeFileSync(path.join(tmp, 'data', 'switches.json'), JSON.stringify({ 'fast-open': on }));
const port = 20000 + Math.floor(Math.random() * 20000);
const py = spawn('python3', ['server.py'], { cwd: tmp, stdio: 'ignore', env: { ...process.env, WIZARD_SEARCH_PORT: String(port),
  WIZARD_SEARCH_DATA: path.join(tmp, 'data'), WIZARD_SWITCHES_DIR: path.join(tmp, 'data'), SEARXNG_URL: 'http://searx.invalid:8080' } });
let offline = false;
const types = { '.js': 'text/javascript', '.css': 'text/css' };
const gateway = http.createServer((req, res) => {
  if (offline) return req.socket.destroy();
  setTimeout(() => {
    const u = new URL(req.url, 'http://x');
    if (u.pathname.startsWith('/wizard-os-home/')) {
      const f = path.join(ux, u.pathname.slice('/wizard-os-home/'.length));
      if (!f.startsWith(ux) || !fs.existsSync(f)) { res.writeHead(404); return res.end(); }
      res.writeHead(200, { 'Content-Type': types[path.extname(f)] || 'text/plain', 'Cache-Control': 'no-cache' }); return res.end(fs.readFileSync(f));
    }
    if (u.pathname === '/wizard/v1/bootstrap') { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end('{"bootstrap":1,"settings":{},"capabilities":{}}'); }
    if (u.pathname === '/wizard-search/api/web') { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end(JSON.stringify({ results: [{ title: 'Fixture result: ' + u.searchParams.get('q'), host: 'example.test', url: 'https://example.test/r', snippet: 'Fixture web result' }] })); }
    const p = http.request({ host: '127.0.0.1', port, path: req.url, method: req.method, headers: req.headers }, r => { res.writeHead(r.statusCode, r.headers); r.pipe(res); });
    p.on('error', () => { res.writeHead(502); res.end(); }); req.pipe(p);
  }, DELAY);
});
const READY = `(() => { const t0 = performance.now(); const tick = () => {
  const s = document.querySelector('#setup-status');
  if (window.WizardSearch && s && !/Checking provider/.test(s.textContent)) window.__ready = performance.now(); else requestAnimationFrame(tick); };
  requestAnimationFrame(tick); })();`;
async function open(ctx, base, label, q = '') {
  const page = await ctx.newPage(); const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto(base + '/wizard-search/' + q, { waitUntil: 'commit' });
  await page.waitForFunction(() => window.__ready && performance.getEntriesByName('first-contentful-paint').length, null, { timeout: 30000 });
  const m = await page.evaluate(() => ({ fcp: Math.round(performance.getEntriesByName('first-contentful-paint')[0]?.startTime || -1), ready: Math.round(window.__ready),
    fast: document.documentElement.hasAttribute('data-fast-open'), controlled: !!navigator.serviceWorker.controller, setupShown: getComputedStyle(document.querySelector('#setup')).display !== 'none' && !document.querySelector('#setup').hidden,
    status: document.querySelector('#setup-status').textContent, build: window.__build || '' }));
  m.errors = errors; console.log(label.padEnd(34), JSON.stringify(m));
  return { page, m };
}
(async () => {
  await new Promise(r => gateway.listen(0, '127.0.0.1', r));
  const base = 'http://127.0.0.1:' + gateway.address().port;
  for (let i = 0; i < 50; i++) { try { await fetch(`http://127.0.0.1:${port}/wizard-search/api/health`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  const browser = await chromium.launch();
  const results = {};
  try {
    console.log(`every request delayed ${DELAY} ms`);
    setSwitch(false);
    let ctx = await browser.newContext({ viewport: { width: 390, height: 760 } });
    await ctx.addInitScript(READY);
    let r = await open(ctx, base, 'off: first open'); results.off1 = r.m; await r.page.close();
    r = await open(ctx, base, 'off: next open'); results.off2 = r.m;
    assert.equal(r.m.fast, false); assert.equal(r.m.controlled, false);
    await r.page.screenshot({ path: path.join(evidence, 'fast-open-off-390.png') }); await r.page.close();
    offline = true; const offPage = await ctx.newPage();
    const offErr = await offPage.goto(base + '/wizard-search/').then(() => '', e => e.message.split('\n')[0]);
    console.log('off: open with no network'.padEnd(34), offErr || 'loaded'); results.offOffline = offErr || 'loaded'; offline = false; await offPage.close();
    await ctx.close();

    setSwitch(true);
    ctx = await browser.newContext({ viewport: { width: 390, height: 760 } });
    await ctx.addInitScript(READY);
    r = await open(ctx, base, 'on: first open (installs worker)'); results.on1 = r.m;
    assert.equal(r.m.fast, true); assert.equal(r.m.setupShown, false);
    await r.page.evaluate(() => navigator.serviceWorker.ready); await r.page.waitForTimeout(Math.max(1500, DELAY * 4)); await r.page.close();
    r = await open(ctx, base, 'on: next open'); results.on2 = r.m; assert.equal(r.m.controlled, true); await r.page.close();
    r = await open(ctx, base, 'on: open again'); results.on3 = r.m;
    await r.page.screenshot({ path: path.join(evidence, 'fast-open-on-390.png') });
    await r.page.locator('#q').click(); await r.page.locator('#q').fill('hiking trails'); await r.page.locator('#q').press('Enter');
    await r.page.waitForSelector('#web li .t'); results.search = await r.page.locator('#web li .t').first().textContent();
    await r.page.goBack(); await r.page.waitForTimeout(800);
    results.backClears = await r.page.evaluate(() => WizardSearch.state().q === '' && !document.querySelector('#empty').hidden);
    assert.equal(results.backClears, true); await r.page.close();
    offline = true;
    r = await open(ctx, base, 'on: open with no network'); results.onOffline = r.m; offline = false;
    assert.equal(r.m.setupShown, false); await r.page.close();
    // A new release: the next open still shows the saved copy and fetches the new one; the open after uses it.
    fs.appendFileSync(path.join(tmp, 'web', 'app.js'), '\nwindow.__build = "new-release";\n');
    r = await open(ctx, base, 'on: open right after a release'); results.rel1 = r.m; await r.page.waitForTimeout(Math.max(1500, DELAY * 4)); await r.page.close();
    r = await open(ctx, base, 'on: the open after that'); results.rel2 = r.m; await r.page.close();
    assert.equal(results.rel2.build, 'new-release');
    // Desktop look with the switch on.
    const desk = await browser.newContext({ viewport: { width: 1440, height: 900 } }); await desk.addInitScript(READY);
    r = await open(desk, base, 'on: desktop'); await r.page.screenshot({ path: path.join(evidence, 'fast-open-on-1440.png') }); await desk.close();
    // Switch off again: the next open drops the worker and caches; the one after is the plain page.
    setSwitch(false);
    r = await open(ctx, base, 'switched off: next open'); await r.page.waitForTimeout(Math.max(1500, DELAY * 4)); await r.page.close();
    r = await open(ctx, base, 'switched off: open after');
    results.afterOff = { ...r.m, caches: await r.page.evaluate(() => caches.keys()), registration: await r.page.evaluate(() => navigator.serviceWorker.getRegistration('/wizard-search/').then(x => !!x)) };
    console.log('switched off: leftovers'.padEnd(34), JSON.stringify({ caches: results.afterOff.caches, registration: results.afterOff.registration }));
    assert.equal(r.m.fast, false); assert.equal(r.m.controlled, false); assert.deepEqual(results.afterOff.caches, []); assert.equal(results.afterOff.registration, false);
    for (const [k, v] of Object.entries(results)) if (v?.errors?.length) throw new Error(k + ': ' + v.errors.join('; '));
    fs.writeFileSync(path.join(evidence, 'fast-open-results.json'), JSON.stringify({ delayMs: DELAY, ...results }, null, 2));
    console.log('PASS');
  } finally { await browser.close(); gateway.close(); py.kill(); fs.rmSync(tmp, { recursive: true, force: true }); }
})().catch(e => { console.error(e); process.exit(1); });
