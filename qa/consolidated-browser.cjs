// Exact copied public shell; synthetic empty owner contract; recorded private-inference UI replay.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const {appFrame}=require('./shell-frame.cjs');
const settled=()=>document.fonts.status==='loaded' && document.getAnimations().every(a=>a.playState!=='running' || !Number.isFinite(a.effect?.getComputedTiming().endTime));
async function settle(page,frame){await page.waitForFunction(settled,null,{timeout:15000});if(frame)await frame.waitForFunction(settled,null,{timeout:15000});}
async function diagnostic(page){
 const state=await page.evaluate(()=>({
  shell:document.documentElement.dataset.shell,phone:!!window.__wos,desktop:window.__wux?.shell,
  bootstrap:{bootstrap:window.WizConfig?.raw?.bootstrap,appsEndpoint:window.WizConfig?.endpoint('apps')},
  registries:['mobile','desktop'].map(s=>({shell:s,apps:window.WizCore?.apps?.(s)?.APPS?.map(a=>({id:a.id,source:a.source,url:a.url,view:a.view}))})),
  services:window.WizAppServices?.inspect(),appearance:window.WizAppearance?.inspect(),
  iframes:[...document.querySelectorAll('iframe')].map(f=>{const r=f.getBoundingClientRect();return {src:f.getAttribute('src'),url:(()=>{try{return f.contentWindow.location.href;}catch{return 'cross-origin';}})(),bounds:{x:r.x,y:r.y,width:r.width,height:r.height},display:getComputedStyle(f).display,visibility:getComputedStyle(f).visibility};})
 })).catch(e=>({diagnosticError:String(e)}));
 return {...state,frames:page.frames().map(f=>({url:f.url(),parent:f.parentFrame()?.url()}))};
}
async function outsideViewer(page){
 // Source-defined bare backdrop, or the photo's actual object-fit letterbox; never force a covered tap.
 const point=await page.evaluate(()=>{
  const v=document.querySelector('.mviewer:not([hidden])'),stage=v?.querySelector('.mv-stage');if(!stage)return null;
  const r=stage.getBoundingClientRect();
  for(const [x,y] of [[r.left+3,r.top+3],[r.right-3,r.top+3],[r.left+3,r.bottom-3],[r.right-3,r.bottom-3]]){
   const target=document.elementFromPoint(x,y);
   if(target===v || target===stage)return {x,y};
   if(target?.matches('.mv-stage img') && target.naturalWidth){const b=target.getBoundingClientRect(),fit=Math.min(b.width/target.naturalWidth,b.height/target.naturalHeight),w=target.naturalWidth*fit,h=target.naturalHeight*fit;
    if(x<b.left+(b.width-w)/2 || x>b.right-(b.width-w)/2 || y<b.top+(b.height-h)/2 || y>b.bottom-(b.height-h)/2)return {x,y};}
  }return null;
 });
 assert(point,'No native outside-viewer hit target; retain diagnostics instead of force-click');
 await page.mouse.click(point.x,point.y);await page.waitForFunction(()=>!WosChat.viewer.isOpen());
 return point;
}
(async()=>{
 const out=process.env.QA_EVIDENCE,base=process.env.QA_BASE;fs.mkdirSync(out,{recursive:true});
 const proof=JSON.parse(fs.readFileSync(process.env.QA_PRIVATE_PROOF));
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});const results=[];
 try {for(const viewport of [{width:390,height:844},{width:1440,height:900}]){
  const shell=viewport.width>600?'desktop':'phone';
  const ctx=await browser.newContext({viewport,isMobile:shell==='phone',hasTouch:shell==='phone'});
  await ctx.addInitScript(()=>{localStorage.setItem('wos.coached','true');localStorage.setItem('wos.tour.done','1');window.__qaAcks=[];addEventListener('message',e=>{if(e.origin===location.origin && e.data?.type==='wizard:appearance:ack')window.__qaAcks.push({revision:e.data.revision,src:[...document.querySelectorAll('iframe')].find(f=>f.contentWindow===e.source)?.getAttribute('src')});});});
  const page=await ctx.newPage();let detail={viewport,shell};const logs=[],network=[];
  page.on('console',m=>{if(['warning','error'].includes(m.type()))logs.push({type:m.type(),text:m.text()});});
  page.on('pageerror',e=>logs.push({type:'pageerror',text:String(e.stack)}));
  page.on('requestfailed',r=>logs.push({type:'requestfailed',url:r.url(),error:r.failure()}));
  page.on('response',r=>{const p=new URL(r.url()).pathname;if(['/wizard/v1/bootstrap','/wizard/v1/apps'].includes(p))network.push({url:r.url(),status:r.status()});});
  await page.route('**/*',async route=>{const u=new URL(route.request().url());if(u.origin!==new URL(base).origin && !['data:','blob:'].includes(u.protocol))return route.abort();return route.continue();});
  await page.route('**/wizard-search/api/config',async route=>{const r=await route.fetch();const j=await r.json();j.capabilities.overview=true;return route.fulfill({json:j});});
  await page.route('**/wizard-search/api/overview-provider',route=>route.fulfill({json:{mode:'proxy',model:'gpt-oss-120b',tinfoil:{installed:true,connected:true}}}));
  await page.route('**/wizard-search/api/overview-stream?*',route=>route.fulfill({headers:{'Content-Type':'text/event-stream'},body:proof.stream.map(e=>`event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`).join('')}));
  try {
   await page.goto(base+'/wizard-os-home/'+(shell==='desktop'?'desktop.html':'')+`?shell=${shell}&open=wizard-search`,{waitUntil:'domcontentloaded'});
   await page.waitForFunction(()=>window.WosSkin?.list?.length && window.WizCore?.appsLoaded,{timeout:45000});
   await page.evaluate(async()=>{await WizCore.appsLoaded();await WizCore.refreshApps({afterPending:true});WizCore.deeplink.route(location.pathname+'?open=wizard-search');});
   assert.equal(await page.evaluate(()=>document.documentElement.dataset.shell),shell);
   assert(await page.evaluate(s=>s==='phone'?!!window.__wos:window.__wux?.shell==='desktop',shell),'Actual requested shell runtime must be mounted');
   const {frame,el}=await appFrame(page,base);
   await frame.waitForFunction(()=>document.documentElement.hasAttribute('data-wz-hosted'));
   await page.waitForFunction(f=>WizAppServices.authorized(f),el,{timeout:20000});
   const skins=await page.evaluate(()=>['nebula','obsidian-light'].map(id=>{if(!WosSkin.list.some(x=>x.id===id))throw Error('missing '+id);return id;}));
   for(const skin of skins){
    detail={viewport,shell,skin,frame:frame.url()};
    // Ephemeral resource preview, NOT Settings control coverage or persisted owner preferences.
    await page.evaluate(id=>WosSkin.preview(WosSkin.index(id)),skin);
    await el.evaluate((f,id)=>new Promise((resolve,reject)=>{
     const end=Date.now()+20000;const poll=()=>{
      const c=WizAppearance.get(f),d=f.contentDocument?.documentElement,st=WizAppearance.inspect().find(a=>a.src===f.getAttribute('src'));
      const ack=(window.__qaAcks||[]).some(a=>a.src===f.getAttribute('src') && a.revision===st?.revision);
      if(c?.skin===id && d?.dataset.skin===id && d?.dataset.colorScheme===c.colorScheme && ack && st?.acked)return resolve();
      if(Date.now()>end)return reject(Error('Current-revision Appearance ACK / scheme / skin did not settle'));setTimeout(poll,50);
     };poll();
    }),skin);
    await frame.locator('#q').fill('Python programming language official documentation');await frame.locator('#q').press('Enter');
    await frame.waitForSelector('#web li a.t',{timeout:90000});await frame.waitForSelector('#ov .cite',{timeout:20000});
    await settle(page,frame);
    const file=`shell-${skin}-${viewport.width}.png`;await page.screenshot({path:path.join(out,file),fullPage:true});
    const tokens=await frame.evaluate(()=>({text:getComputedStyle(document.body).color,base:getComputedStyle(document.documentElement).getPropertyValue('--wz-base').trim(),panel:getComputedStyle(document.documentElement).getPropertyValue('--wz-panel').trim(),skin:document.documentElement.dataset.skin,scheme:document.documentElement.dataset.colorScheme,overflow:document.documentElement.scrollWidth>innerWidth}));assert(!tokens.overflow);assert.equal(tokens.skin,skin);
    const appearance=await el.evaluate(f=>({context:WizAppearance.get(f),acks:window.__qaAcks,services:WizAppServices.inspect()}));
    assert.equal(tokens.base,appearance.context.tokens.base);assert.equal(tokens.scheme,skin==='obsidian-light'?'light':'dark');
    await frame.locator('[data-t="images"]').click();await frame.waitForSelector('#grid [data-i]',{timeout:90000});
    const open=async()=>{await frame.locator('#grid [data-i]').first().click();await page.waitForFunction(()=>WosChat.viewer.isOpen());assert.equal(await frame.locator('#lb').isVisible(),false);};
    await open();await settle(page,frame);
    await page.screenshot({path:path.join(out,`viewer-${skin}-${viewport.width}.png`),fullPage:true});
    const outside=await outsideViewer(page);
    await open();await page.locator('.mviewer:not([hidden]) [data-mv="close"]').click();await page.waitForFunction(()=>!WosChat.viewer.isOpen());
    const nested=await el.evaluate(f=>WizAppServices.back(f));assert.equal(nested,'handled');
    await frame.waitForFunction(()=>document.querySelector('[data-t="all"]').getAttribute('aria-selected')==='true');
    const root=await el.evaluate(f=>WizAppServices.back(f));assert.equal(root,'atRoot');assert(page.url().includes('/wizard-os-home/'));assert.equal(frame.url().startsWith(base+'/wizard-search/'),true);
    assert.deepEqual(logs.filter(x=>x.type==='pageerror' && x.text.includes('/wizard-search/')),[]);
    results.push({viewport,shell,skin,file,tokens,appearance,shared_viewer:true,outside,viewer_close:true,nested_back:nested,root_back:root,root_stayed_in_shell:true,skin_method:'ephemeral WosSkin.preview; not Settings interaction',ai_ui:'recorded private proof replay; NOT fresh live inference'});
   }
  } catch(e){await page.screenshot({path:path.join(out,`FAIL-${viewport.width}.png`)}).catch(()=>{});fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify({...detail,error:String(e.stack),url:page.url(),network,logs,state:await diagnostic(page)},null,2));throw e;}
  finally{fs.writeFileSync(path.join(out,`shell-diagnostics-${viewport.width}.json`),JSON.stringify({network,logs,state:await diagnostic(page)},null,2));await ctx.close();}
 }
 const ctx=await browser.newContext({viewport:{width:390,height:844},colorScheme:'dark'});const page=await ctx.newPage();
 await page.route('**/*',r=>new URL(r.request().url()).origin===new URL(base).origin?r.continue():r.abort());
 try{await page.goto(base+'/wizard-search/',{waitUntil:'domcontentloaded'});await page.locator('#q').fill('Python programming language official documentation');await page.locator('#q').press('Enter');await page.waitForSelector('#web li a.t',{timeout:90000});await settle(page);
  const paint=await page.evaluate(()=>({hosted:document.documentElement.hasAttribute('data-wz-hosted'),scheme:getComputedStyle(document.documentElement).colorScheme,background:getComputedStyle(document.body).backgroundColor,text:getComputedStyle(document.body).color}));assert.equal(paint.hosted,false);assert(paint.scheme.includes('dark'));await page.screenshot({path:path.join(out,'standalone-dark-390.png'),fullPage:true});results.push({standalone:true,paint,file:'standalone-dark-390.png'});
 }finally{await ctx.close();}
 }finally{await browser.close();fs.writeFileSync(path.join(out,'shell-browser.json'),JSON.stringify({results,source:'exact copied public shell; explicit synthetic empty owner APIs',needs_visual_review:true},null,2));}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
