/* Search bar mic (issue #29) in a standalone page: the REAL shared client, capture resource and config from a
 * wizard-ux checkout (WIZARD_UX_WEB=<wizard-ux>/web), Chromium's fake microphone, and a fixture system transcriber.
 * Usage: WIZARD_UX_WEB=../wizard-ux/web PLAYWRIGHT_MODULE=<path>/playwright node qa/mic-browser.cjs [on|off] */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const http = require('node:http'), fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../web'), ux = path.resolve(process.env.WIZARD_UX_WEB || '../wizard-ux/web');
const evidence = process.env.QA_EVIDENCE || path.resolve(__dirname, '../evidence');
const on = process.argv[2] !== 'off';
fs.mkdirSync(evidence, { recursive: true });
const calls = [];
const types = { '.js': 'text/javascript', '.html': 'text/html', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png' };
const json = (res, code, obj) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(obj)); };
const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://localhost');
  calls.push(req.method + ' ' + u.pathname + u.search);
  if (u.pathname.startsWith('/wizard-os-home/')) {
    const f = path.join(ux, u.pathname.slice('/wizard-os-home/'.length));
    if (!f.startsWith(ux) || !fs.existsSync(f)) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': types[path.extname(f)] || 'text/plain' }); return res.end(fs.readFileSync(f));
  }
  if (u.pathname === '/wizard/v1/bootstrap') return json(res, 200, { bootstrap: 1, settings: { agent: { name: 'Wizard' }, voice: { vocabulary: [] } }, capabilities: { voice: true }, endpoints: { transcribe: '/wizard/v1/voice/transcribe' } });
  if (u.pathname === '/wizard/v1/voice/transcribe') {
    let bytes = 0; for await (const c of req) bytes += c.length;
    calls.push('audio-bytes ' + bytes + ' ' + req.headers['content-type']);
    return json(res, 200, { text: 'best hiking trails near Ljubljana', model: 'fixture-stt' });
  }
  if (u.pathname === '/wizard-search/api/config') return json(res, 200, { state: 'configured', capabilities: { web: true, images: true, overview: false }, switches: { 'search-bar-mic': on } });
  if (u.pathname === '/wizard-search/api/overview-provider') return json(res, 200, { mode: 'off', tinfoil: {} });
  if (u.pathname === '/wizard-search/api/web') return json(res, 200, { results: [{ title: 'Fixture result: ' + u.searchParams.get('q'), host: 'example.test', url: 'https://example.test/r', snippet: 'Fixture web result' }] });
  if (u.pathname === '/wizard-search/api/images') return json(res, 200, { images: [] });
  if (u.pathname.startsWith('/wizard-search/')) {
    const f = path.join(root, u.pathname.slice('/wizard-search/'.length) || 'index.html');
    if (f.startsWith(root) && fs.existsSync(f) && fs.statSync(f).isFile()) { res.writeHead(200, { 'Content-Type': types[path.extname(f)] || 'text/plain' }); return res.end(fs.readFileSync(f)); }
  }
  res.writeHead(404); res.end();
});
(async () => {
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const base = 'http://127.0.0.1:' + server.address().port;
  const browser = await chromium.launch({ args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 760 }, permissions: ['microphone'] });
  const page = await ctx.newPage();
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto(base + '/wizard-search/');
  await page.waitForTimeout(800);
  const mic = page.locator('#mic');
  if (!on) {
    assert.equal(await mic.isHidden(), true, 'mic stays hidden with the switch off');
    assert.ok(!calls.some(c => c.includes('app-capture.js')), 'switch off loads no capture code');
    await page.screenshot({ path: path.join(evidence, 'mic-off.png') });
    console.log('OFF: mic hidden, no capture code loaded');
  } else {
    await mic.waitFor({ state: 'visible' });
    await page.screenshot({ path: path.join(evidence, 'mic-idle.png') });
    await mic.click();
    await page.waitForFunction(() => document.querySelector('#mic').dataset.phase === 'listening', null, { timeout: 8000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(evidence, 'mic-listening.png') });
    console.log('status while listening:', await page.textContent('#voice-status'));
    await mic.click();
    await page.waitForFunction(() => document.querySelector('#web li'), null, { timeout: 10000 });
    assert.equal(await page.inputValue('#q'), 'best hiking trails near Ljubljana');
    assert.match(await page.textContent('#web'), /Fixture result: best hiking trails near Ljubljana/);
    assert.ok(calls.some(c => /^audio-bytes [1-9]\d* audio\//.test(c)), 'audio reached the system transcriber');
    await page.screenshot({ path: path.join(evidence, 'mic-searched.png') });
    // Back while listening cancels the take and stays in Search.
    await mic.click();
    await page.waitForFunction(() => document.querySelector('#mic').dataset.phase === 'listening', null, { timeout: 8000 });
    await page.goBack().catch(() => {});
    await page.waitForTimeout(500);
    console.log('after Back:', page.url(), '|', await page.textContent('#voice-status'), '| phase', await mic.getAttribute('data-phase'));
    console.log('ON: tap, speak, tap ran the search; calls:', calls.filter(c => /transcribe|audio-bytes|api\/web/.test(c)).join(' ; '));
  }
  assert.deepEqual(errors, []);
  await browser.close(); server.close();
})().catch(e => { console.error(e); process.exit(1); });
