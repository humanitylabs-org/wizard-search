/* Bottom search bar (issue #51, on for everyone): phone screen vs a wide window.
 * Runs the REAL server.py behind a small gateway that serves the REAL shared client from a wizard-ux checkout and
 * answers web/images with fixtures. Checks: phone = field fixed at the bottom on an opaque panel, tabs at the top, the
 * last result scrolls clear of the bar, the bar rides above a keyboard (--kb), a light skin's tokens paint the panel;
 * a wide window keeps the field on top. A saved "off" for the old switch changes nothing. Screenshots go to $QA_EVIDENCE (default evidence/).
 * Usage: WIZARD_UX_WEB=<ux>/web PLAYWRIGHT_MODULE=<path>/playwright node qa/bottom-bar-browser.cjs */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const http = require('node:http'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { spawn } = require('node:child_process'), assert = require('node:assert/strict');
const repo = path.resolve(__dirname, '..'), ux = path.resolve(process.env.WIZARD_UX_WEB || '../wizard-ux/web');
const evidence = process.env.QA_EVIDENCE || path.join(repo, 'evidence');
fs.mkdirSync(evidence, { recursive: true });
const data = fs.mkdtempSync(path.join(process.env.TMPDIR || os.tmpdir(), 'search51-'));
fs.writeFileSync(path.join(data, 'switches.json'), JSON.stringify({ 'bottom-search-bar': false })); // retired switch
const port = 20000 + Math.floor(Math.random() * 20000);
const py = spawn('python3', ['server.py'], { cwd: repo, stdio: 'ignore', env: { ...process.env, WIZARD_SEARCH_PORT: String(port),
  WIZARD_SEARCH_DATA: data, WIZARD_SWITCHES_DIR: data, SEARXNG_URL: 'http://searx.invalid:8080' } });
const types = { '.js': 'text/javascript', '.css': 'text/css' };
const json = (res, o) => { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(o)); };
const gateway = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x');
  if (u.pathname.startsWith('/wizard-os-home/')) {
    const f = path.join(ux, u.pathname.slice('/wizard-os-home/'.length));
    if (!f.startsWith(ux) || !fs.existsSync(f)) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': types[path.extname(f)] || 'text/plain' }); return res.end(fs.readFileSync(f));
  }
  if (u.pathname === '/wizard/v1/bootstrap') return json(res, { bootstrap: 1, settings: {}, capabilities: {} });
  if (u.pathname === '/wizard-search/api/web') return json(res, { results: Array.from({ length: 12 }, (_, i) => ({ title: `Result ${i + 1}: ${u.searchParams.get('q')}`, host: 'example.test', url: 'https://example.test/' + i, snippet: 'A fixture web result with a line or two of snippet text so the list scrolls like a real one.' })) });
  if (u.pathname === '/wizard-search/api/images') return json(res, { images: [] });
  const p = http.request({ host: '127.0.0.1', port, path: req.url, method: req.method, headers: req.headers }, r => { res.writeHead(r.statusCode, r.headers); r.pipe(res); });
  p.on('error', () => { res.writeHead(502); res.end(); }); req.pipe(p);
});
const measure = page => page.evaluate(() => {
  const r = s => { const b = document.querySelector(s).getBoundingClientRect(); return { top: Math.round(b.top), bottom: Math.round(b.bottom) }; };
  const panel = getComputedStyle(document.querySelector('.top'), '::after');
  return { vh: innerHeight, bar: r('#f'), tabs: r('.tabs'),
    mic: !document.querySelector('#mic').hidden, micInBar: document.querySelector('#f').contains(document.querySelector('#mic')),
    panel: panel.content !== 'none' ? panel.backgroundColor : null, hint: document.querySelector('#type-where').textContent };
});
(async () => {
  await new Promise(r => gateway.listen(0, '127.0.0.1', r));
  const base = 'http://127.0.0.1:' + gateway.address().port + '/wizard-search/';
  for (let i = 0; i < 50; i++) { try { await fetch(`http://127.0.0.1:${port}/wizard-search/api/health`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 390, height: 780 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const errors = [];
  const open = async q => { const page = await ctx.newPage(); page.on('pageerror', e => errors.push(e.message));
    await page.goto(base + (q ? '?q=' + q : '')); await page.waitForFunction(() => window.WizardSearch && !document.querySelector('#mic').hidden);
    if (q) await page.waitForSelector('#web li'); return page; };
  try {
    let page = await open('');
    const on = await measure(page); console.log('phone', JSON.stringify(on));
    assert.ok(on.bar.bottom > on.vh - 20 && on.bar.bottom <= on.vh, 'phone: field at the bottom');
    assert.ok(on.tabs.top < 40, 'phone: tabs at the top'); assert.ok(on.mic && on.micInBar, 'mic in the bottom bar');
    assert.equal(on.panel, 'rgb(11, 11, 20)', 'opaque dark fallback panel'); assert.equal(on.hint, 'below');
    await page.screenshot({ path: path.join(evidence, 'bottom-bar-on-empty.png') });
    await page.close();

    page = await open('pizza');
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight)); await page.waitForTimeout(200);
    const last = await page.evaluate(() => { const b = document.querySelector('#web li:last-child').getBoundingClientRect(), f = document.querySelector('#f').getBoundingClientRect(); return { lastBottom: Math.round(b.bottom), barTop: Math.round(f.top) }; });
    console.log('end  ', JSON.stringify(last)); assert.ok(last.lastBottom <= last.barTop, 'last result clear of the bar');
    await page.screenshot({ path: path.join(evidence, 'bottom-bar-on-results-end.png') });
    await page.evaluate(() => window.scrollTo(0, 0)); await page.waitForTimeout(100);
    await page.screenshot({ path: path.join(evidence, 'bottom-bar-on-results.png') });
    // A keyboard covering 300 px of the layout viewport (what visualViewport reports on iOS / Chrome): bar rides above.
    await page.evaluate(() => document.documentElement.style.setProperty('--kb', '300px'));
    const kb = await measure(page); console.log('kb   ', JSON.stringify(kb.bar)); assert.ok(Math.abs(kb.bar.bottom - (kb.vh - 300 - 11)) <= 1, 'bar above keyboard');
    await page.evaluate(() => document.documentElement.style.setProperty('--kb', '0px'));
    // A light skin: the panel takes the skin's canvas token, not a hard-coded dark.
    await page.evaluate(() => { const s = document.documentElement.style; document.documentElement.setAttribute('data-wz-hosted', '');
      s.setProperty('--wz-canvas', '#f6f4ee'); s.setProperty('--wz-surface', '#ffffff'); s.setProperty('--wz-border', '#d9d4c7'); s.setProperty('--wz-text', '#1d1b16'); s.setProperty('--wz-text-secondary', '#4a463c'); s.setProperty('--wz-text-muted', '#7b766a'); s.setProperty('--wz-accent', '#5b3fd6'); });
    const light = await measure(page); console.log('light', light.panel); assert.equal(light.panel, 'rgb(246, 244, 238)');
    await page.screenshot({ path: path.join(evidence, 'bottom-bar-on-light-skin.png') });
    errors.length = 0;
    await page.close();
    // A wide window keeps the field on top (the layout only applies at 820 px and narrower).
    page = await ctx.newPage(); await page.setViewportSize({ width: 1280, height: 800 });
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(base); await page.waitForFunction(() => window.WizardSearch && !document.querySelector('#mic').hidden);
    const wide = await measure(page); console.log('wide ', JSON.stringify(wide));
    assert.ok(wide.bar.top < 20, 'wide: field on top'); assert.equal(wide.panel, null); assert.equal(wide.hint, 'above');
    await page.close();
    assert.deepEqual(errors, []);
    console.log('PASS');
  } finally { await browser.close(); gateway.close(); py.kill(); }
})().catch(e => { console.error(e); py.kill(); process.exit(1); });
