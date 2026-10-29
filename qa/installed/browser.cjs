// Existing installed shell, its app frame and shared appearance client. No mocked responses.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const [pw, base, out, mode] = process.argv.slice(2);
const { chromium } = require(pw);
(async () => {
  const browser = await chromium.launch({headless:true, args:['--no-sandbox','--disable-dev-shm-usage']});
  const receipts = [];
  try {
    for (const size of [{width:1365,height:900}, {width:390,height:844}]) {
      const ctx = await browser.newContext({viewport:size});
      await ctx.addInitScript(() => {localStorage.setItem('wos.coached','true');localStorage.setItem('wos.tour.done','1');});
      const page = await ctx.newPage();
      const failed = [];
      page.on('requestfailed', r => {if (!r.url().startsWith('https://')) failed.push({url:r.url(),failure:r.failure()});});
      await page.goto(base + '/wizard-os-home/' + (size.width > 600 ? 'desktop.html' : '') + '?open=wizard-search', {waitUntil:'domcontentloaded',timeout:60000});
      await page.waitForFunction(() => window.WosSkin?.list?.length > 0, undefined, {timeout:60000});
      const look = await page.evaluate(() => {
        const s=window.WosSkin.list;
        const dark=s.find(x => x.id === 'nebula');
        const light=s.find(x => x.id === 'obsidian-light');
        if (!dark || !light || dark.family === light.family) throw Error('Pinned Nebula and Light skins unavailable');
        return [dark.id,light.id];
      });
      for (const skin of look) {
        // The public skin API is the same operation used by the installed Settings page.
        assert.equal(await page.evaluate(id => window.WosSkin.set(id), skin),skin);
        const element = await page.waitForSelector('iframe[src*="wizard-search"]', {timeout:60000});
        const frame = await element.contentFrame();
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
    }
    fs.writeFileSync(path.join(out,`${mode}-browser.json`),JSON.stringify({kind:'installed shell browser; no model',receipts,needs_human_visual_review:true},null,2));
  } finally { await browser.close(); }
})().catch(e=>{console.error(e.stack);process.exitCode=1});
