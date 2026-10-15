const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs');
const path = require('path');
const assert = require('assert');
(async () => {
  const browser = await chromium.launch({headless:true});
  const base=process.env.QA_BASE, evidence=process.env.QA_EVIDENCE;
  fs.mkdirSync(evidence,{recursive:true});
  const results=[];
  try {
    for (const viewport of [{width:390,height:844},{width:1440,height:900}]) {
      const page = await browser.newPage({viewport});
      const errors=[]; page.on('pageerror', e=>errors.push(String(e)));
      await page.goto(base+'/clean/');
      await page.waitForFunction(()=>document.querySelector('#setup-status').textContent.includes('Setup required'));
      await page.screenshot({path:path.join(evidence,`clean-${viewport.width}.png`),fullPage:true});
      await page.locator('#q').fill('Python programming language official documentation');
      await page.locator('#q').press('Enter');
      await page.waitForFunction(()=>document.querySelector('#web').textContent.includes('Setup required'));
      await page.locator('[data-t="images"]').click();
      await page.goBack();
      await page.waitForFunction(()=>document.querySelector('[data-t="all"]').getAttribute('aria-selected')==='true');
      assert(page.url().includes('/clean/'));
      await page.waitForTimeout(2200);
      await page.goBack();
      await page.waitForFunction(()=>document.querySelector('#wizard-app-back-notice'));
      assert(page.url().includes('/clean/'));
      await page.goto(base+'/configured/');
      await page.waitForFunction(()=>document.querySelector('#setup-status').textContent.includes('Optional setup'));
      await page.locator('#q').fill('Python programming language official documentation');
      await page.locator('#q').press('Enter');
      await page.waitForSelector('#web li .t', {timeout:60000});
      const links=await page.locator('#web li .t').evaluateAll(es=>es.map(e=>({title:e.textContent,url:e.href})));
      assert(links.some(x=>x.url.startsWith('https://www.python.org/')));
      await page.screenshot({path:path.join(evidence,`configured-${viewport.width}.png`),fullPage:true});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth));
      // Exercise the actual domain viewer callback with an explicit synthetic UI fixture.
      // This verifies Back only and is NOT live image-search evidence.
      await page.route('**/api/images?*',r=>r.fulfill({json:{q:'back fixture',images:[{id:'fixture',title:'Back QA fixture',full:'https://www.python.org/static/img/python-logo.png',thumb:base+'/configured/icon.png',page:'https://www.python.org/'}]}}));
      await page.locator('#q').fill('viewer Back fixture'); await page.locator('#q').press('Enter');
      await page.waitForSelector('#strip [data-i]'); await page.locator('#strip [data-i]').first().click();
      assert(await page.locator('#lb').isVisible());
      await page.goBack(); await page.waitForFunction(()=>document.querySelector('#lb').hidden);
      assert(page.url().includes('/configured/'));
      assert.deepEqual(errors,[]);
      results.push({viewport,live_web_links:links,empty_setup:true,nested_back:true,root_back:true,viewer_back_fixture:true,page_errors:errors});
      await page.close();
    }
    fs.writeFileSync(path.join(evidence,'browser.json'),JSON.stringify({results},null,2));
    console.log(JSON.stringify({results},null,2));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
