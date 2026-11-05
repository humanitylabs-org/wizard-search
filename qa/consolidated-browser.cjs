// Exact copied public shell; synthetic empty owner contract; recorded private-inference UI replay.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const {appFrame}=require('./shell-frame.cjs');
const {fullCandidates,firstDecoded,probeFullImages,waitViewerImage,outsideViewer}=require('./media-readiness.cjs');
const settled=()=>document.fonts.status==='loaded' && document.getAnimations().every(a=>a.playState!=='running' || !Number.isFinite(a.effect?.getComputedTiming().endTime));
async function settle(page,frame){await page.waitForFunction(settled,null,{timeout:15000});if(frame)await frame.waitForFunction(settled,null,{timeout:15000});}
async function diagnostic(page){
 const state=await page.evaluate(()=>({
  shell:document.documentElement.dataset.shell,phone:!!window.__wos,desktop:window.__wux?.shell,
  bootstrap:{bootstrap:window.WizConfig?.raw?.bootstrap,appsEndpoint:window.WizConfig?.endpoint('apps')},
  registries:['mobile','desktop'].map(s=>({shell:s,apps:window.WizCore?.apps?.(s)?.APPS?.map(a=>({id:a.id,source:a.source,url:a.url,view:a.view}))})),
  services:window.WizAppServices?.inspect(),appearance:window.WizAppearance?.inspect(),
  viewer:{open:!!window.WosChat?.viewer?.isOpen(),images:[...document.querySelectorAll('.mv-stage img')].map(i=>({src:i.currentSrc || i.src,complete:i.complete,width:i.naturalWidth,height:i.naturalHeight}))},
  iframes:[...document.querySelectorAll('iframe')].map(f=>{const r=f.getBoundingClientRect();return {src:f.getAttribute('src'),url:(()=>{try{return f.contentWindow.location.href;}catch{return 'cross-origin';}})(),bounds:{x:r.x,y:r.y,width:r.width,height:r.height},display:getComputedStyle(f).display,visibility:getComputedStyle(f).visibility};})
 })).catch(e=>({diagnosticError:String(e)}));
 return {...state,frames:page.frames().map(f=>({url:f.url(),parent:f.parentFrame()?.url()}))};
}
(async()=>{
 const out=process.env.QA_EVIDENCE,base=process.env.QA_BASE;fs.mkdirSync(out,{recursive:true});
 const proof=JSON.parse(fs.readFileSync(process.env.QA_PRIVATE_PROOF));
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});const results=[];
 const save=()=>fs.writeFileSync(path.join(out,'shell-browser.json'),JSON.stringify({results,expected_shell_cases:4,source:'exact copied public shell; explicit synthetic empty owner APIs',needs_visual_review:true},null,2));
 try {for(const viewport of [{width:390,height:844},{width:1440,height:900}])for(const skin of ['nebula','obsidian-light']){
  // A fresh shell per case: a failed photo/provider/overlay cannot poison the next skin or viewport.
  const shell=viewport.width>600?'desktop':'phone',id=`${skin}-${viewport.width}`;
  const ctx=await browser.newContext({viewport,isMobile:shell==='phone',hasTouch:shell==='phone'});
  await ctx.addInitScript(()=>{localStorage.setItem('wos.coached','true');localStorage.setItem('wos.tour.done','1');window.__qaAcks=[];addEventListener('message',e=>{if(e.origin===location.origin && e.data?.type==='wizard:appearance:ack')window.__qaAcks.push({revision:e.data.revision,src:[...document.querySelectorAll('iframe')].find(f=>f.contentWindow===e.source)?.getAttribute('src')});});});
  const page=await ctx.newPage();page.setDefaultTimeout(15000);
  const detail={viewport,shell,skin,status:'running',checks:{},failures:[],skin_method:'ephemeral WosSkin.preview; not Settings interaction',ai_ui:'recorded private proof replay; NOT fresh live inference'};
  results.push(detail);save();const logs=[],network=[],mediaNetwork=[],imageResults=[];
  page.on('console',m=>{if(['warning','error'].includes(m.type()))logs.push({type:m.type(),text:m.text()});});
  page.on('pageerror',e=>logs.push({type:'pageerror',text:String(e.stack)}));
  page.on('requestfailed',r=>logs.push({type:'requestfailed',url:r.url(),error:r.failure()}));
  page.on('response',r=>{const p=new URL(r.url()).pathname;if(['/wizard/v1/bootstrap','/wizard/v1/apps'].includes(p))network.push({url:r.url(),status:r.status()});if(p.startsWith('/wizard-search/img/'))mediaNetwork.push({url:r.url(),status:r.status(),contentType:r.headers()['content-type'],timing:r.request().timing()});if(p==='/wizard-search/api/images')r.json().then(j=>imageResults.push(...(j.images||[]).map(({id,title,host,full,page})=>({id,title,host,full,page})))).catch(e=>logs.push({type:'image-results-diagnostic',error:String(e)}));});
  await page.route('**/*',async route=>{const u=new URL(route.request().url());if(u.origin!==new URL(base).origin && !['data:','blob:'].includes(u.protocol))return route.abort();return route.continue();});
  await page.route('**/wizard-search/api/config',async route=>{const r=await route.fetch();const j=await r.json();j.capabilities.overview=true;return route.fulfill({json:j});});
  await page.route('**/wizard-search/api/overview-provider',route=>route.fulfill({json:{mode:'proxy',model:'gpt-oss-120b',tinfoil:{installed:true,connected:true}}}));
  await page.route('**/wizard-search/api/overview-stream?*',route=>route.fulfill({headers:{'Content-Type':'text/event-stream'},body:proof.stream.map(e=>`event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`).join('')}));
  const check=async(name,fn)=>{
   try{detail.checks[name]={status:'passed',value:await fn()};}
   catch(e){const file=`FAIL-${id}-${name}.png`;await page.screenshot({path:path.join(out,file),timeout:5000}).catch(()=>{});detail.checks[name]={status:'failed',error:String(e.stack),file};detail.failures.push(name);fs.writeFileSync(path.join(out,`failure-${id}-${name}.json`),JSON.stringify({error:String(e.stack),url:page.url(),state:await diagnostic(page)},null,2));}
   save();return detail.checks[name].status==='passed';
  };
  try {
   await page.goto(base+'/wizard-os-home/'+(shell==='desktop'?'desktop.html':'')+`?shell=${shell}&open=wizard-search`,{waitUntil:'domcontentloaded'});
   await page.waitForFunction(()=>window.WosSkin?.list?.length && window.WizCore?.appsLoaded,{timeout:45000});
   await page.evaluate(async()=>{await WizCore.appsLoaded();await WizCore.refreshApps({afterPending:true});WizCore.deeplink.route(location.pathname+'?open=wizard-search');});
   assert.equal(await page.evaluate(()=>document.documentElement.dataset.shell),shell);
   assert(await page.evaluate(s=>s==='phone'?!!window.__wos:window.__wux?.shell==='desktop',shell),'Actual requested shell runtime must be mounted');
   const {frame,el}=await appFrame(page,base);detail.frame=frame.url();
   await frame.waitForFunction(()=>document.documentElement.hasAttribute('data-wz-hosted'));
   await page.waitForFunction(f=>WizAppServices.authorized(f),el,{timeout:20000});
   await page.evaluate(id=>{if(!WosSkin.list.some(x=>x.id===id))throw Error('missing '+id);WosSkin.preview(WosSkin.index(id));},skin);
   await check('appearance',async()=>{
    await el.evaluate((f,id)=>new Promise((resolve,reject)=>{
     const end=Date.now()+20000;const poll=()=>{
      const c=WizAppearance.get(f),d=f.contentDocument?.documentElement,st=WizAppearance.inspect().find(a=>a.src===f.getAttribute('src'));
      const ack=(window.__qaAcks||[]).some(a=>a.src===f.getAttribute('src') && a.revision===st?.revision);
      if(c?.skin===id && d?.dataset.skin===id && d?.dataset.colorScheme===c.colorScheme && ack && st?.acked)return resolve();
      if(Date.now()>end)return reject(Error('Current-revision Appearance ACK / scheme / skin did not settle'));setTimeout(poll,50);
     };poll();
    }),skin);
    return el.evaluate(f=>({context:WizAppearance.get(f),acks:window.__qaAcks,services:WizAppServices.inspect()}));
   });
   await check('web',async()=>{
    await frame.locator('#q').fill('Python programming language official documentation');await frame.locator('#q').press('Enter');
    await frame.waitForSelector('#web li a.t',{timeout:90000});await frame.waitForSelector('#ov .cite',{timeout:20000});await settle(page,frame);
    detail.file=`shell-${id}.png`;await page.screenshot({path:path.join(out,detail.file),fullPage:true,timeout:5000});
    const tokens=await frame.evaluate(()=>({text:getComputedStyle(document.body).color,base:getComputedStyle(document.documentElement).getPropertyValue('--wz-base').trim(),panel:getComputedStyle(document.documentElement).getPropertyValue('--wz-panel').trim(),skin:document.documentElement.dataset.skin,scheme:document.documentElement.dataset.colorScheme,overflow:document.documentElement.scrollWidth>innerWidth}));
    detail.tokens=tokens;assert(!tokens.overflow);assert.equal(tokens.skin,skin);
    const appearance=await el.evaluate(f=>WizAppearance.get(f));assert.equal(tokens.base,appearance.tokens.base);assert.equal(tokens.scheme,skin==='obsidian-light'?'light':'dark');return tokens;
   });
   let selected;
   await check('full_image_selection',async()=>{
    await frame.locator('[data-t="images"]').click();await frame.waitForSelector('#grid [data-i]',{timeout:90000});
    const tiles=await frame.locator('#grid [data-i]').evaluateAll(nodes=>nodes.slice(0,6).map(n=>({index:Number(n.dataset.i),title:n.textContent.trim(),thumb:n.querySelector('img').src})));
    const candidates=fullCandidates(tiles,base).map(c=>({...c,result:imageResults.find(r=>new URL(c.url).pathname===`/wizard-search/img/${r.id}.jpg`) || null}));
    const probe=await frame.evaluate(probeFullImages,{candidates,budgetMs:45000});
    selected=firstDecoded(probe.attempts);
    for(const attempt of probe.attempts){
     if(attempt.bodyBase64){const file=`media-${id}-${attempt.index}-error.bin`;fs.writeFileSync(path.join(out,file),Buffer.from(attempt.bodyBase64,'base64'));attempt.bodyFile=file;delete attempt.bodyBase64;}
     if(attempt.fullBase64){const file=`media-${id}-${attempt.index}-full.bin`;const bytes=Buffer.from(attempt.fullBase64,'base64');assert.equal(bytes.length,attempt.bytes);assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),attempt.sha256);fs.writeFileSync(path.join(out,file),bytes);attempt.fullFile=file;delete attempt.fullBase64;}
    }
    detail.media={...probe,selected:selected?{...selected}:null};fs.writeFileSync(path.join(out,`media-${id}.json`),JSON.stringify(detail.media,null,2));save();
    assert(selected,'None of the first six actual full proxy results decoded within 45s; upstream failures retained, viewer acceptance remains failed');return detail.media;
   });
   const open=async()=>{
    await frame.locator(`#grid [data-i="${selected.index}"]`).click();await page.waitForFunction(()=>WosChat.viewer.isOpen(),null,{timeout:10000});
    assert.equal(await frame.locator('#lb').isVisible(),false);return waitViewerImage(page,selected);
   };
   let viewerReady=false;
   if(selected){
    viewerReady=await check('shared_viewer',async()=>{
     const loaded=await open();await settle(page,frame);detail.viewerFile=`viewer-${id}.png`;
     await page.screenshot({path:path.join(out,detail.viewerFile),fullPage:true,timeout:5000});return loaded;
    });
    if(viewerReady)await check('outside',()=>outsideViewer(page,selected,shell==='phone'));
    else detail.checks.outside={status:'skipped',reason:'No decoded native viewer image; no outside assertion or tap admitted'};
    // A failed outside tap must not prevent native close or Back diagnostics.
    await check('viewer_close',async()=>{
     if(!await page.evaluate(()=>WosChat.viewer.isOpen()))await open();
     await page.locator('.mviewer:not([hidden]) [data-mv="close"]').click();await page.waitForFunction(()=>!WosChat.viewer.isOpen(),null,{timeout:5000});return true;
    });
   }else for(const name of ['shared_viewer','outside','viewer_close'])detail.checks[name]={status:'skipped',reason:'No real decodable full proxy result; not accepted'};
   await check('nested_back',async()=>{
    assert(!await page.evaluate(()=>WosChat.viewer.isOpen()),'Viewer still open; app Back geometry is not valid');
    const nested=await el.evaluate(f=>WizAppServices.back(f));assert.equal(nested,'handled');
    await frame.waitForFunction(()=>document.querySelector('[data-t="all"]').getAttribute('aria-selected')==='true');return nested;
   });
   await check('root_back',async()=>{
    const root=await el.evaluate(f=>WizAppServices.back(f));assert.equal(root,'atRoot');assert(page.url().includes('/wizard-os-home/'));assert(frame.url().startsWith(base+'/wizard-search/'));return {root,root_stayed_in_shell:true};
   });
   await check('app_errors',async()=>{assert.deepEqual(logs.filter(x=>x.type==='pageerror' && x.text.includes('/wizard-search/')),[]);return true;});
  } catch(e){
   detail.failures.push('setup');detail.error=String(e.stack);await page.screenshot({path:path.join(out,`FAIL-${id}-setup.png`),timeout:5000}).catch(()=>{});
  } finally {
   detail.status=detail.failures.length?'failed':'passed';
   fs.writeFileSync(path.join(out,`shell-diagnostics-${id}.json`),JSON.stringify({network,mediaNetwork,imageResults,logs,state:await diagnostic(page)},null,2));save();await ctx.close();
  }
 }
 // Standalone remains independent of all four shell cases, including failures.
 const standalone={standalone:true,status:'running'};results.push(standalone);save();
 const ctx=await browser.newContext({viewport:{width:390,height:844},colorScheme:'dark'});const page=await ctx.newPage();
 await page.route('**/*',r=>new URL(r.request().url()).origin===new URL(base).origin?r.continue():r.abort());
 try{await page.goto(base+'/wizard-search/',{waitUntil:'domcontentloaded'});await page.locator('#q').fill('Python programming language official documentation');await page.locator('#q').press('Enter');await page.waitForSelector('#web li a.t',{timeout:90000});await settle(page);
  const paint=await page.evaluate(()=>({hosted:document.documentElement.hasAttribute('data-wz-hosted'),scheme:getComputedStyle(document.documentElement).colorScheme,background:getComputedStyle(document.body).backgroundColor,text:getComputedStyle(document.body).color}));assert.equal(paint.hosted,false);assert(paint.scheme.includes('dark'));await page.screenshot({path:path.join(out,'standalone-dark-390.png'),fullPage:true,timeout:5000});Object.assign(standalone,{status:'passed',paint,file:'standalone-dark-390.png'});
 }catch(e){standalone.status='failed';standalone.error=String(e.stack);await page.screenshot({path:path.join(out,'FAIL-standalone.png'),timeout:5000}).catch(()=>{});}
 finally{save();await ctx.close();}
 const cases=results.filter(r=>!r.standalone);assert.equal(cases.length,4);assert.equal(new Set(cases.map(r=>`${r.shell}/${r.skin}`)).size,4);
 assert(results.every(r=>r.status==='passed'),'Independent matrix completed with failures; inspect per-case receipts (acceptance NOT weakened)');
 }finally{save();await browser.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
