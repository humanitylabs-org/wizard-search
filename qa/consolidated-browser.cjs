// Real public shell + shared client/resources; isolated synthetic owner APIs and recorded AI UI stream.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const out=process.env.QA_EVIDENCE,base=process.env.QA_BASE;fs.mkdirSync(out,{recursive:true});
 const proof=JSON.parse(fs.readFileSync(process.env.QA_PRIVATE_PROOF));
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});const results=[];
 try {for(const viewport of [{width:390,height:844},{width:1440,height:900}]){
  const ctx=await browser.newContext({viewport});
  await ctx.addInitScript(()=>{localStorage.setItem('wos.coached','true');localStorage.setItem('wos.tour.done','1');});
  const page=await ctx.newPage();let detail={viewport};
  // No remote shell/backend access, including accidental absolute API bases.
  await page.route('**/*',async route=>{const u=new URL(route.request().url());if(u.origin!==new URL(base).origin && !['data:','blob:'].includes(u.protocol))return route.abort();return route.continue();});
  await page.route('**/wizard-search/api/config',async route=>{const r=await route.fetch();const j=await r.json();j.capabilities.overview=true;return route.fulfill({json:j});});
  await page.route('**/wizard-search/api/overview-provider',route=>route.fulfill({json:{mode:'proxy',model:'gpt-oss-120b',tinfoil:{installed:true,connected:true}}}));
  await page.route('**/wizard-search/api/overview-stream?*',route=>route.fulfill({headers:{'Content-Type':'text/event-stream'},body:proof.stream.map(e=>`event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`).join('')}));
  try {
   const shell=viewport.width>600?'desktop':'phone';
   await page.goto(base+'/wizard-os-home/'+(shell==='desktop'?'desktop.html':'')+`?shell=${shell}&open=wizard-search`,{waitUntil:'domcontentloaded'});
   await page.waitForFunction(()=>window.WosSkin?.list?.length && window.WizCore?.appsLoaded,{timeout:45000});
   await page.evaluate(async()=>{await WizCore.appsLoaded();await WizCore.refreshApps({afterPending:true});WizCore.deeplink.route(location.pathname+'?open=wizard-search');});
   const el=await page.waitForSelector('iframe[data-own-app="wizard-search"]',{state:'visible',timeout:45000});const frame=await el.contentFrame();assert(frame);
   const errors=[];frame.page().on('pageerror',e=>{if(String(e.stack).includes('/wizard-search/'))errors.push(String(e));});
   const skins=await page.evaluate(()=>{const s=WosSkin.list;return ['nebula','obsidian-light'].map(id=>{const found=s.find(x=>x.id===id);if(!found)throw Error('missing '+id);return id;});});
   for(const skin of skins){detail={viewport,skin};await page.evaluate(id=>WosSkin.set(id),skin);
    await frame.waitForFunction(()=>document.documentElement.hasAttribute('data-wz-hosted'));
    await frame.locator('#q').fill('Python programming language official documentation');await frame.locator('#q').press('Enter');
    await frame.waitForSelector('#web li a.t',{timeout:90000});await frame.waitForSelector('#ov .cite',{timeout:20000});
    const file=`shell-${skin}-${viewport.width}.png`;await page.screenshot({path:path.join(out,file),fullPage:true});
    const tokens=await frame.evaluate(()=>({text:getComputedStyle(document.body).color,base:getComputedStyle(document.documentElement).getPropertyValue('--wz-base').trim(),skin:document.documentElement.dataset.skin,overflow:document.documentElement.scrollWidth>innerWidth}));assert(!tokens.overflow);
    await frame.locator('[data-t="images"]').click();await frame.waitForSelector('#grid [data-i]',{timeout:90000});
    await frame.locator('#grid [data-i]').first().click();await page.waitForSelector('.mviewer:not([hidden])',{timeout:20000});assert.equal(await frame.locator('#lb').isVisible(),false);
    await page.screenshot({path:path.join(out,`viewer-${skin}-${viewport.width}.png`),fullPage:true});
    // Outside tap and shared Back are exercised in the parent shell's real media viewer.
    await page.locator('.mviewer').click({position:{x:3,y:3},force:true});await page.waitForFunction(()=>!WosChat.viewer.isOpen());
    await frame.locator('#grid [data-i]').first().click();await page.waitForFunction(()=>WosChat.viewer.isOpen());await page.goBack();await page.waitForFunction(()=>!WosChat.viewer.isOpen());
    await page.goBack();await frame.waitForFunction(()=>document.querySelector('[data-t="all"]').getAttribute('aria-selected')==='true');
    await page.goBack();assert(page.url().includes('/wizard-os-home/'));
    assert.deepEqual(errors,[]);results.push({viewport,skin,file,tokens,shared_viewer:true,outside_tap:true,nested_back:true,root_stayed_in_shell:true,ai_ui:'recorded private proof replay; NOT fresh live inference'});
   }
  } catch(e){await page.screenshot({path:path.join(out,`FAIL-${viewport.width}.png`)}).catch(()=>{});fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify({...detail,error:String(e.stack),url:page.url()},null,2));throw e;}
  await ctx.close();
 }}finally{await browser.close();fs.writeFileSync(path.join(out,'shell-browser.json'),JSON.stringify({results,source:'exact live public shell static files; synthetic empty owner APIs',needs_visual_review:true},null,2));}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
