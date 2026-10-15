/* Thales browser harness. Shared client + providers are fixtures unless --real is used. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const http = require('node:http'), fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../web'), evidence = process.env.QA_EVIDENCE || path.resolve(__dirname, '../evidence');
fs.mkdirSync(evidence, { recursive: true });
const calls = [], checks = [], real = process.argv.includes('--real');
const client = `window.WizardApp={ready(){},back:{useHistory(){},register(x){window.backReceiver=x}},voiceInput:{register(x){window.voiceReceiver=x}}};`;
const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://localhost');
  if (u.pathname.startsWith('/wizard-os-home/')) { res.setHeader('Content-Type', 'text/javascript'); return res.end(u.pathname.endsWith('app-client.js') ? client : ''); }
  if (u.pathname.includes('/api/')) {
    calls.push(u.pathname + u.search);
    if (u.pathname.endsWith('/config')) { res.setHeader('Content-Type', 'application/json'); return res.end(JSON.stringify({ capabilities: {web:true, images:true, overview:false}, state:'ready' })); }
    const q = u.searchParams.get('q');
    if (real && q === 'Python documentation' && u.pathname.endsWith('/web')) {
      try {
        const upstream = await fetch(process.env.REAL_SEARCH_URL + '?q=' + encodeURIComponent(q));
        const body = await upstream.text();
        fs.writeFileSync(path.join(evidence, 'real-search.json'), body);
        res.writeHead(upstream.status, {'Content-Type':'application/json'}); return res.end(body);
      } catch (e) { res.writeHead(502); return res.end(JSON.stringify({error:e.message})); }
    }
    if (q === 'slow fixture') await new Promise(r => setTimeout(r, 400));
    else await new Promise(r => setTimeout(r, 80));
    res.setHeader('Content-Type', 'application/json');
    if (q === 'error fixture') { res.statusCode = 503; return res.end(JSON.stringify({error:'fixture provider offline'})); }
    if (u.pathname.endsWith('/images')) return res.end(JSON.stringify({images:[{id:'01234567890123456789',title:'Fixture image',host:'example.test',page:'https://example.test/image',full:'https://example.test/image.png'}]}));
    return res.end(JSON.stringify({results:[{title:'Fixture result: '+q,host:'example.test',url:'https://example.test/result',snippet:'Clearly labelled fixture search data'}]}));
  }
  if (u.pathname.startsWith('/thumb/') || u.pathname.startsWith('/img/')) { res.writeHead(404); return res.end(); }
  const file = path.join(root, u.pathname === '/' ? 'index.html' : u.pathname.slice(1));
  if (!file.startsWith(root + '/') || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
  res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
  res.end(fs.readFileSync(file));
});
(async () => {
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const base = 'http://127.0.0.1:' + server.address().port;
  const browser = await chromium.launch({headless:true});
  const ctx = await browser.newContext();
  await ctx.route('https://**', r => r.abort());
  const errors = [];
  const page = await ctx.newPage(); page.on('pageerror', e => errors.push(String(e)));
  await page.goto(base); await page.waitForFunction(() => !!window.voiceReceiver);
  const target = await page.evaluate(() => voiceReceiver.snapshot());
  assert.equal(target.tab, 'all');
  assert(await page.evaluate(() => { const t=voiceReceiver.snapshot(); return Object.isFrozen(t)&&Object.isFrozen(t.results); }));
  checks.push('bounded frozen target');
  const send = (p, message, allowed = true) => p.evaluate(({message,allowed}) => voiceReceiver.receive(message, () => { if (!allowed) throw new Error('fixture revoked'); }), {message,allowed});
  const m = {request_id:'search_test_0001',text:'voice fixture',target};
  const receipts = await Promise.all([send(page,m),send(page,m)]);
  assert(receipts.every(x=>x.accepted));
  await page.waitForFunction(() => document.querySelector('#voice-status').textContent === 'Voice query complete.');
  assert.equal(calls.filter(x=>x.includes('q=voice%20fixture')).length,1);
  assert.match(await page.locator('#web').innerText(), /Fixture result/);
  checks.push('concurrent retry admits once, visible result');
  const bounded = await page.evaluate(() => voiceReceiver.snapshot());
  assert.equal(bounded.results.length,1);
  await assert.rejects(send(page,{...m,text:'conflicting query'}),/different query/);
  await assert.rejects(send(page,{...m,request_id:'search_denied_01'},false),/revoked/);
  await assert.rejects(send(page,{...m,request_id:'search_long_0001',text:'x'.repeat(301)}),/300/);
  await assert.rejects(send(page,{...m,request_id:'search_file_0001',files:[{}]}),/text query/);
  checks.push('conflict, authorization, bounds and attachment rejection');
  const beforeReload = calls.length;
  await page.reload(); await page.waitForFunction(() => !!window.voiceReceiver);
  await page.waitForFunction(() => document.querySelector('#voice-status').textContent === 'Voice query complete.');
  await send(page,m); assert.equal(calls.filter(x=>!x.includes('/config')).length, calls.slice(0,beforeReload).filter(x=>!x.includes('/config')).length);
  checks.push('reload restores durable results without duplicate search');
  const p2 = await ctx.newPage(); await p2.goto(base); await p2.waitForFunction(() => !!window.voiceReceiver);
  const cross={...m,request_id:'search_cross_001',text:'cross frame fixture'};
  await Promise.all([send(page,cross),send(p2,cross)]);
  await page.waitForTimeout(200);
  assert.equal(calls.filter(x=>x.includes('q=cross%20frame%20fixture')).length,1);
  checks.push('two-frame durable admission serialization');
  await p2.close();
  const images={...m,request_id:'search_images_01',text:'image fixture',target:{...target,tab:'images',label:'Search · Images'}};
  await page.evaluate(() => WizardSearch.tab('all'));
  await send(page,images); await page.waitForFunction(() => document.querySelector('#voice-status').textContent === 'Voice query complete.');
  assert.equal(await page.evaluate(() => WizardSearch.state().tab),'images');
  assert.equal(calls.filter(x=>x.includes('q=image%20fixture')).length,1);
  assert.equal(await page.locator('#grid .tile').count(),1);
  checks.push('frozen images tab uses existing images endpoint');
  await send(page,{...m,request_id:'search_error_001',text:'error fixture'});
  await page.waitForFunction(() => document.querySelector('#voice-status').textContent.includes('fixture provider offline'));
  assert(!/Finding/.test(await page.locator('#web').innerText()));
  checks.push('provider failure visible, loading clears');
  await send(page,{...m,request_id:'search_slow_0001',text:'slow fixture'});
  await send(page,{...m,request_id:'search_fast_0001',text:'newest fixture'});
  await page.waitForTimeout(600);
  assert.equal(await page.locator('#q').inputValue(),'newest fixture');
  assert.match(await page.locator('#web').innerText(),/newest fixture/);
  checks.push('late completion cannot replace newer search');
  const blocked = await ctx.newPage();
  await blocked.addInitScript(() => Object.defineProperty(window, 'indexedDB', {value:{open(){throw new Error('fixture storage denied')}}}));
  await blocked.goto(base); await blocked.waitForFunction(() => !!window.voiceReceiver);
  const beforeBlocked = calls.length;
  await assert.rejects(send(blocked,{...m,request_id:'search_storage_1'}),/storage denied/);
  assert.equal(calls.length,beforeBlocked);
  await blocked.close(); checks.push('storage failure rejects before search');
  if (real) {
    await send(page,{...m,request_id:'search_real_0001',text:'Python documentation'});
    await page.waitForFunction(() => document.querySelector('#voice-status').textContent === 'Voice query complete.', null, {timeout:90000});
    assert((await page.locator('#web a.t').count())>0);
    assert((await page.locator('#web a.t').evaluateAll(links=>links.map(x=>x.href))).some(u=>new URL(u).hostname.endsWith('python.org')));
    checks.push('real existing Search web provider returns Python documentation');
  }
  for (const viewport of [{width:390,height:844},{width:1440,height:900}]) {
    await page.setViewportSize(viewport);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({path:path.join(evidence,`search-voice-${viewport.width}.png`),fullPage:true});
  }
  assert.equal(calls.filter(x=>/chat|overview|translate|read-image/.test(x)).length,0);
  assert.deepEqual(errors,[]);
  checks.push('phone/desktop layout, no Chats/inference calls, no page errors');
  const result={passed:checks.length,checks,provider_mode:real?'one real query; remaining fixtures':'fixtures only',shared_client:'fixture implementing frozen API seam',calls,page_errors:errors};
  fs.writeFileSync(path.join(evidence,'voice-browser.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result,null,2));
  await browser.close(); server.close();
})().catch(e=>{console.error(e);process.exit(1)});
