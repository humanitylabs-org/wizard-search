/* Opaque search bar and tabs (issue #71): no result text shows through the bar, the All / Images tabs, or the bottom
 * panel, in the tokens the real shell pushes (appearance-host.js: canvas "transparent", base = the skin's --bg,
 * surface = 6% ink over transparent), dark default and a light skin, phone and wide window.
 * Check: each panel region is screenshotted with the results visible and again with them hidden; any pixel that
 * changes is bleed-through. Also: the last result ends above the bar (keyboard closed and open).
 * Runs the REAL server.py behind a small gateway that serves the REAL shared client from a wizard-ux checkout and
 * answers web/images with fixtures. Screenshots go to $QA_EVIDENCE (default evidence/).
 * Usage: WIZARD_UX_WEB=<ux>/web PLAYWRIGHT_MODULE=<path>/playwright node qa/opaque-bar-browser.cjs */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const http = require('node:http'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { spawn } = require('node:child_process');
const repo = path.resolve(__dirname, '..'), ux = path.resolve(process.env.WIZARD_UX_WEB || '../wizard-ux/web');
const evidence = process.env.QA_EVIDENCE || path.join(repo, 'evidence');
fs.mkdirSync(evidence, { recursive: true });
const data = fs.mkdtempSync(path.join(process.env.TMPDIR || os.tmpdir(), 'search71-'));
const port = 20000 + Math.floor(Math.random() * 20000);
const py = spawn('python3', ['server.py'], { cwd: repo, stdio: 'ignore', env: { ...process.env, WIZARD_SEARCH_PORT: String(port),
  WIZARD_SEARCH_DATA: data, WIZARD_SWITCHES_DIR: data, SEARXNG_URL: 'http://searx.invalid:8080' } });
const types = { '.js': 'text/javascript', '.css': 'text/css' };
const json = (res, o) => { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(o)); };
const hues = ['#e4572e', '#29335c', '#f3a712', '#a8c686', '#669bbc', '#7d5ba6'];
const gateway = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x');
  if (u.pathname.startsWith('/wizard-os-home/')) {
    const f = path.join(ux, u.pathname.slice('/wizard-os-home/'.length));
    if (!f.startsWith(ux) || !fs.existsSync(f)) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': types[path.extname(f)] || 'text/plain' }); return res.end(fs.readFileSync(f));
  }
  if (u.pathname === '/wizard/v1/bootstrap') return json(res, { bootstrap: 1, settings: {}, capabilities: {} });
  if (u.pathname === '/wizard-search/api/web') return json(res, { results: Array.from({ length: 14 }, (_, i) => ({ title: `Apply for PAN Card Online in India | PAN ${i + 1}`, host: 'example.test', url: 'https://example.test/' + i, snippet: 'A fixture web result with a line or two of snippet text so the list scrolls like a real one.' })) });
  if (u.pathname === '/wizard-search/api/images') return json(res, { images: Array.from({ length: 24 }, (_, i) => ({ id: 'im' + i, title: 'Fixture image ' + i, host: 'example.test', url: 'https://example.test/i' + i, page: 'https://example.test/p' + i, width: 300, height: 200 + (i % 3) * 80 })) });
  const m = u.pathname.match(/^\/wizard-search\/thumb\/im(\d+)\.jpg$/);
  if (m) { const h = 200 + (m[1] % 3) * 80; res.writeHead(200, { 'Content-Type': 'image/svg+xml' });
    return res.end(`<svg xmlns="http://www.w3.org/2000/svg" width="300" height="${h}"><rect width="300" height="${h}" fill="${hues[m[1] % hues.length]}"/><text x="20" y="60" font-size="44" fill="#fff">IMAGE ${m[1]}</text></svg>`); }
  const p = http.request({ host: '127.0.0.1', port, path: req.url, method: req.method, headers: req.headers }, r => { res.writeHead(r.statusCode, r.headers); r.pipe(res); });
  p.on('error', () => { res.writeHead(502); res.end(); }); req.pipe(p);
});
// What appearance-host.js tokens() pushes to a hosted app, for the default dark skin and a light skin.
const skin = (bg, ink, ink2, ink3, line, accent, win, light) => ({ win, light, tokens: { canvas: 'transparent', base: bg, chrome: win,
  surface: `color-mix(in srgb, ${ink} 6%, transparent)`, 'surface-raised': `color-mix(in srgb, ${ink} 10%, transparent)`,
  text: ink, 'text-secondary': ink2, 'text-muted': ink3, border: line, accent } });
const SKINS = {
  dark: skin('#05030c', '#f3efff', '#b9b0d8', '#7d74a3', 'rgba(205,190,255,.24)', '#b99bff', 'rgba(12,8,26,.82)', false),
  light: skin('#f6f3ec', '#1d1b17', '#4a463c', '#7b766a', 'rgba(29,27,23,.16)', '#5b3fd6', 'rgba(246,243,236,.86)', true),
};
const applySkin = (page, s) => page.evaluate(s => {
  const r = document.documentElement; r.setAttribute('data-wz-hosted', '');
  for (const [k, v] of Object.entries(s.tokens)) r.style.setProperty('--wz-' + k, v);
  r.style.colorScheme = s.light ? 'light' : 'dark';
  // The window behind a hosted app (canvas is transparent): its material over the skin's base.
  document.body.style.background = `linear-gradient(${s.win},${s.win}),${s.tokens.base}`;
}, s);
// A loud backdrop instead, so any see-through panel shows in the pixel check.
const loud = page => page.evaluate(() => { document.body.style.background = 'repeating-linear-gradient(45deg,#ff00aa 0 12px,#00ffcc 12px 24px)'; });
(async () => {
  await new Promise(r => gateway.listen(0, '127.0.0.1', r));
  const base = 'http://127.0.0.1:' + gateway.address().port + '/wizard-search/';
  for (let i = 0; i < 50; i++) { try { await fetch(`http://127.0.0.1:${port}/wizard-search/api/health`); break; } catch { await new Promise(r => setTimeout(r, 100)); } }
  const browser = await chromium.launch();
  const fails = [], errors = [], tag = process.env.QA_PHASE || 'run';
  const check = (ok, what) => { console.log((ok ? 'ok   ' : 'FAIL ') + what); if (!ok) fails.push(what); };
  try {
    for (const [vw, vh, mobile] of [[412, 860, true], [1280, 800, false]]) {
      const ctx = await browser.newContext({ viewport: { width: vw, height: vh }, deviceScaleFactor: 1, isMobile: mobile, hasTouch: mobile });
      for (const [name, s] of Object.entries(SKINS)) for (const t of ['all', 'images']) {
        const page = await ctx.newPage(); page.on('pageerror', e => errors.push(e.message));
        await page.goto(base + '?q=Yoneda+lemma' + (t === 'images' ? '&tab=images' : ''));
        await page.waitForSelector(t === 'images' ? '#grid .tile img' : '#web li');
        await page.evaluate(() => { for (const i of document.images) i.loading = 'eager'; return Promise.race([new Promise(r => setTimeout(r, 3000)),
          Promise.all([...document.images].map(i => i.complete ? 0 : new Promise(r => { i.addEventListener('load', r); i.addEventListener('error', r); })))]); });
        await applySkin(page, s);
        // Scroll so results sit right behind the tabs and the bar.
        await page.evaluate(() => window.scrollTo(0, 260)); await page.waitForTimeout(150);
        const where = `${vw}px ${name} ${t}`;
        const regions = await page.evaluate(() => {
          const out = {}, r = el => { const b = el.getBoundingClientRect(); return { x: Math.max(0, b.left), y: Math.max(0, b.top), width: Math.min(innerWidth, b.right) - Math.max(0, b.left), height: b.height }; };
          out.bar = r(document.querySelector('#f')); out.tabs = r(document.querySelector('.tabs')); out.header = r(document.querySelector('.top'));
          const after = getComputedStyle(document.querySelector('.top'), '::after');
          if (after.content !== 'none' && after.position === 'fixed') { const h = parseFloat(after.height); out.panel = { x: 0, y: innerHeight - h, width: innerWidth, height: h }; }
          return out;
        });
        await page.screenshot({ path: path.join(evidence, `opaque-${tag}-${vw}-${name}-${t}.png`) });
        await loud(page);
        const shot = clip => page.screenshot({ clip, animations: 'disabled', caret: 'hide' });
        const withResults = {}; for (const [k, c] of Object.entries(regions)) withResults[k] = await shot(c);
        await page.evaluate(() => { document.querySelector('main').style.visibility = 'hidden'; document.body.style.background = 'none'; });
        for (const [k, c] of Object.entries(regions)) check((await shot(c)).equals(withResults[k]), `${where}: nothing shows through ${k}`);
        await page.evaluate(() => { document.querySelector('main').style.visibility = ''; });
        if (mobile && t === 'all') {
          for (const kb of [0, 300]) {
            await page.evaluate(kb => document.documentElement.style.setProperty('--kb', kb + 'px'), kb);
            await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight)); await page.waitForTimeout(150);
            const end = await page.evaluate(() => ({ last: document.querySelector('#web li:last-child').getBoundingClientRect().bottom, bar: document.querySelector('#f').getBoundingClientRect().top }));
            check(end.last <= end.bar, `${where}: last result ends above the bar with a ${kb}px keyboard (${Math.round(end.last)} <= ${Math.round(end.bar)})`);
          }
        }
        await page.close();
      }
      await ctx.close();
    }
    check(errors.length === 0, 'no page errors ' + JSON.stringify(errors));
    console.log(fails.length ? `FAIL (${fails.length})` : 'PASS');
    process.exitCode = fails.length ? 1 : 0;
  } finally { await browser.close(); gateway.close(); py.kill(); }
})().catch(e => { console.error(e); py.kill(); process.exit(1); });
