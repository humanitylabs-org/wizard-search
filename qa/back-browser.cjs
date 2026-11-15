/* Phone Back on results (issue #38) in a standalone page with the REAL shared client from a wizard-ux checkout.
 * Search, press browser Back: the search clears to the empty start screen and Search stays open; Back again leaves.
 * Usage: WIZARD_UX_WEB=../wizard-ux/web PLAYWRIGHT_MODULE=<path>/playwright node qa/back-browser.cjs [before|after] */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const http = require('node:http'), fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../web'), ux = path.resolve(process.env.WIZARD_UX_WEB || '../wizard-ux/web');
const evidence = process.env.QA_EVIDENCE || path.resolve(__dirname, '../evidence');
const on = false, label = process.argv[2] || 'after';
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
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 390, height: 760 } })).newPage();
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  try {
    await page.goto(base + '/wizard-search/');
    await page.waitForTimeout(800);
    await page.locator('#q').click(); await page.locator('#q').fill('hiking trails'); await page.locator('#q').press('Enter');
    await page.waitForSelector('#web li .t');
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(evidence, `back-${label}-1-results.png`) });
    await page.goBack(); await page.waitForTimeout(1200);
    const after = await page.evaluate(() => ({ q: WizardSearch.state().q, box: document.querySelector('#q').value, empty: !document.querySelector('#empty').hidden, results: !document.querySelector('#all').hidden, exitNotice: !!document.querySelector('#wizard-app-back-notice'), url: location.href }));
    await page.screenshot({ path: path.join(evidence, `back-${label}-2-after-back.png`) });
    console.log(label, 'after one Back:', JSON.stringify(after));
    if (label === 'after') {
      assert.deepEqual([after.q, after.box, after.empty, after.results, after.exitNotice], ['', '', true, false, false]);
      assert.ok(after.url.includes('/wizard-search/') && !after.url.includes('q='));
      await page.waitForTimeout(2200);
      await page.goBack(); await page.waitForFunction(() => document.querySelector('#wizard-app-back-notice'));
      console.log('second Back on the empty start screen: leaves Search as before');
    }
    assert.deepEqual(errors, []);
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });
