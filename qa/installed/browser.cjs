// Existing installed shell, its app frame and shared appearance client. No mocked responses.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const [pw, base, out, mode] = process.argv.slice(2);
const { chromium } = require(pw);
// Best effort per artifact: a crashed page must not hide the original failure or
// prevent the JSON being written when screenshot/evaluation is unavailable.
async function captureFailure(page, details, error) {
  const stem = `${mode}-failure-${details.viewport?.width || 'launch'}-${details.skin || 'boot'}`;
  const state = {...details,error:String(error.stack || error),href:page?.url() || null,iframeSrcs:[],visibleAppIds:[]};
  if (page) {
    try {
      await page.screenshot({path:path.join(out,`${stem}.png`),fullPage:true,timeout:10000});
      state.screenshot = `${stem}.png`;
    } catch (e) { state.screenshotError = String(e); }
    try {
      Object.assign(state,await page.evaluate(() => {
        const visible = el => !!(el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden');
        return {
          href:location.href,
          iframeSrcs:[...document.querySelectorAll('iframe')].map(f => f.src).slice(0,100),
          visibleAppIds:[...new Set([...document.querySelectorAll('[data-app],[data-own-app]')].filter(visible).map(el => el.dataset.app || el.dataset.ownApp))].slice(0,100),
          registeredApps:(window.__installedSearchRegistry?.APPS || []).map(a => ({id:a.id,url:a.url,type:a.type})).slice(0,100),
          backendAppIds:(window.WizCore?.backendApps?.() || []).map(a => a.id).slice(0,100),
          shell:window.WIZ_SHELL,
          deeplinkLog:window.WizCore?.deeplink?.log,
        };
      }));
    } catch (e) { state.pageStateError = String(e); }
  }
  fs.writeFileSync(path.join(out,`${stem}.json`),JSON.stringify(state,null,2) + '\n');
}
(async () => {
  fs.mkdirSync(out,{recursive:true});
  let browser, page;
  const details = {mode,viewport:null,skin:null};
  const receipts = [];
  try {
    browser = await chromium.launch({headless:true, args:['--no-sandbox','--disable-dev-shm-usage']});
    for (const size of [{width:1365,height:900}, {width:390,height:844}]) {
      details.viewport = size; details.skin = null; page = null;
      const shell = size.width > 600 ? 'desktop' : 'phone';
      const ctx = await browser.newContext({viewport:size});
      await ctx.addInitScript(() => {localStorage.setItem('wos.coached','true');localStorage.setItem('wos.tour.done','1');});
      page = await ctx.newPage();
      const failed = [];
      page.on('requestfailed', r => {if (!r.url().startsWith('https://')) failed.push({url:r.url(),failure:r.failure()});});
      // 0.3.73 core/deeplink.js supports ?open= in BOTH shells. Width alone
      // does not select phone (core/shell.js); use its public sticky override.
      await page.goto(base + '/wizard-os-home/' + (shell === 'desktop' ? 'desktop.html' : '') + `?shell=${shell}&open=wizard-search`, {waitUntil:'domcontentloaded',timeout:60000});
      await page.waitForFunction(() => window.WosSkin?.list?.length > 0 && window.WizCore?.deeplink?.log?.includes('open:wizard-search'), undefined, {timeout:60000});
      const opened = await page.evaluate(async shell => {
        await window.WizCore.appsLoaded();
        // Re-read after any pending startup snapshot, as the owner's launcher does.
        await window.WizCore.refreshApps({afterPending:true});
        const registry = window.__installedSearchRegistry = window.WizCore.apps(shell === 'phone' ? 'mobile' : 'desktop');
        const app = registry.APP['wizard-search'];
        if (!app?.url) throw Error('Installed Search has no launchable URL in the shell registry');
        if (new URL(app.url,location.href).origin !== location.origin) throw Error('Installed Search view is not on the shell origin: ' + app.url);
        // Same public route used by a tapped shell app link; do not call private openApp.
        return {shell:window.WIZ_SHELL,url:app.url,routed:window.WizCore.deeplink.route(location.pathname + '?open=wizard-search')};
      },shell);
      assert.equal(opened.shell,shell);
      assert.equal(opened.routed,true);
      // Both shell renderers stamp the stable app ID; URL prefixes/ports and
      // own-view routing need not contain the ID in the iframe src.
      const element = await page.waitForSelector('iframe[data-own-app="wizard-search"]', {state:'visible',timeout:60000});
      const frame = await element.contentFrame();
      assert.ok(frame,'Installed Search frame unavailable');
      const look = await page.evaluate(() => {
        const s=window.WosSkin.list;
        const dark=s.find(x => x.id === 'nebula');
        const light=s.find(x => x.id === 'obsidian-light');
        if (!dark || !light || dark.family === light.family) throw Error('Pinned Nebula and Light skins unavailable');
        return [dark.id,light.id];
      });
      for (const skin of look) {
        details.skin = skin;
        // The public skin API is the same operation used by the installed Settings page.
        assert.equal(await page.evaluate(id => window.WosSkin.set(id), skin),skin);
        await frame.waitForSelector('#q', {timeout:60000});
        await frame.waitForFunction(() => document.documentElement.hasAttribute('data-wz-hosted'), undefined, {timeout:15000});
        await frame.waitForFunction(() => !document.querySelector('#setup-status').textContent.includes('Checking'), undefined, {timeout:30000});
        assert.equal(await page.evaluate(() => window.WosSkin.current),skin);
        if (mode === 'fresh') {
          assert.equal(await frame.locator('#policy-notice').isVisible(),false);
          await frame.locator('#q').fill('Python programming language official documentation');
          await frame.locator('#q').press('Enter');
          await frame.waitForSelector('#web li a[href^="http"]', {timeout:90000});
        } else {
          await frame.waitForSelector('#policy-notice', {state:'visible',timeout:30000});
          const text = await frame.locator('#policy-notice').innerText();
          for (const required of ['Firecrawl Cloud','Bright Data','Firecrawl router','WIZARD_SEARCH_PROVIDER_POLICY=approved-upgrades','legacy-race','No provider is enabled automatically']) assert.ok(text.includes(required),required);
          assert.ok(!text.includes('qa-not-a-real-key'));
          await frame.locator('#setup').evaluate(el => el.scrollIntoView({block:'start'}));
          assert.equal(await frame.locator('#setup').isVisible(),true);
        }
        await page.waitForTimeout(1200);
        const file = `${mode}-${skin}-${size.width}.png`;
        await page.screenshot({path:path.join(out,file),fullPage:true});
        const tokens = await frame.evaluate(() => ({hosted:document.documentElement.dataset.wzHosted,canvas:getComputedStyle(document.documentElement).getPropertyValue('--wz-canvas').trim(),text:getComputedStyle(document.body).color,scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth}));
        assert.ok(tokens.canvas,'Shared appearance tokens missing');
        assert.ok(tokens.scrollWidth <= tokens.clientWidth + 1,'Horizontal overflow');
        receipts.push({mode,skin,viewport:size,file,tokens});
      }
      assert.equal(failed.length,0,JSON.stringify(failed));
      await ctx.close();
      page = null;
    }
    fs.writeFileSync(path.join(out,`${mode}-browser.json`),JSON.stringify({kind:'installed shell browser; no model',receipts,needs_human_visual_review:true},null,2));
  } catch (error) {
    try { await captureFailure(page,details,error); }
    catch (captureError) { console.error('Failure capture:',captureError.stack); }
    throw error;
  } finally { await browser?.close(); }
})().catch(e=>{console.error(e.stack);process.exitCode=1});
