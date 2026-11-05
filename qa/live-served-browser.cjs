/* Small actual-served acceptance: canonical TLS, real Search, synthetic unrelated owner surfaces. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {appFrame}=require('./shell-frame.cjs');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const base=process.env.QA_BASE||'https://wizard.tailc0f369.ts.net';
const appPath=process.env.QA_APP_PATH||'/wizard-search/preview/';
const appId=process.env.QA_APP_ID||'search-preview',out=process.env.QA_EVIDENCE;
const SETTINGS={owner:{name:'Synthetic QA owner',place:''},agent:{name:'Wizard'},clock:{timezone:'UTC',day_starts_at:'00:00'},voice:{language:'',vocabulary:[]}};
const synthetic={
 '/wizard/v1/bootstrap':{bootstrap:1,endpoints:{apps:'/wizard/v1/apps'},settings:SETTINGS,capabilities:{}},
 '/wizard/v1/settings':{settings:SETTINGS},'/wizard/v1/ui-preferences':{launcher:{links:[],nativeLinks:[],migrations:{'launcher-seed-v1':true}}},
 '/wizard/v1/agents':{agents:[]},'/wizard/v1/agent-options':{agents:[]},'/wizard/v1/app-bindings':{bindings:{}},'/wizard/v1/pages':{pages:[]},
 '/wizard-os-home/store-data/wizard/v1/app-logos':{logos:{}}
};
async function policy(route,report,pins){
 const req=route.request(),u=new URL(req.url());
 if(['data:','blob:'].includes(u.protocol))return route.continue();
 if(u.origin!==new URL(base).origin){report.blocked.push({path:u.origin+u.pathname,method:req.method()});return route.abort();}
 const p=u.pathname;
 if(p.startsWith(appPath)){
  const allowedGet=new Set(['api/config','api/health','api/overview-provider','api/web','api/images','api/overview-stream']);
  const rel=p.slice(appPath.length);
  const staticFile=/^(?:|app\.js|app\.css|voice-input\.js|standalone-tokens\.css|icon\.(?:png|svg))$/.test(rel);
  if(req.method()==='GET'&&(staticFile||allowedGet.has(rel)||/^img\/[a-f0-9]+\.jpg$/.test(rel)))return route.continue();
  report.blocked.push({path:p,method:req.method()});return route.abort();
 }
 if(p==='/wizard/v1/apps' && req.method()==='GET'){
  const response=await route.fetch();assert.equal(response.status(),200);
  const real=await response.json(),apps=real.apps.filter(a=>a.id===appId);
  assert.equal(apps.length,1,'Exactly one actual installed Search ID');
  assert.equal(apps[0].name,'Search');assert.equal(apps[0].url,appPath);
  report.registry=apps[0];
  return route.fulfill({json:{apps,in_development:[]}});
 }
 if(synthetic[p])return route.fulfill({json:synthetic[p]});
 // Static allowlist excludes ALL store-data and API paths, even .json lookalikes.
 if(req.method()==='GET'&&p.startsWith('/wizard-os-home/')&&!p.includes('/store-data/')&&!p.includes('/api/')&&
    (p==='/wizard-os-home/'||/\.(?:html|js|css|svg|png|webp|ico|woff2?|ttf|json)$/.test(p))){
  if(pins?.public_sha256[p]){
   const response=await route.fetch(),body=await response.body(),sha256=hash(body);
   assert.equal(response.status(),200);assert.equal(sha256,pins.public_sha256[p],p+' drift');
   report.static.push({path:p,status:response.status(),sha256,resourceType:req.resourceType(),proof:'unmodified actual upstream bytes fulfilled to this request'});
   return route.fulfill({response,body});
  }
  return route.continue();
 }
 report.blocked.push({path:p,method:req.method()});
 // Empty synthetic body, never fetch unrelated owner histories/accounts/agents.
 return route.fulfill({status:200,json:{}});
}
async function main(){
 const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
 const pins=JSON.parse(fs.readFileSync(process.env.QA_LIVE_PINS));
 fs.mkdirSync(out,{recursive:true});const results=[];
 const save=()=>fs.writeFileSync(path.join(out,'live-visual.json'),JSON.stringify({scope:'actual served shell + installed Search, unrelated owner surfaces synthetic, fresh inference; no replay',pins,results},null,2));
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 try{
  for(const [shell,viewport] of [['phone',{width:390,height:844}],['desktop',{width:1440,height:1000}]]){
   const context=await browser.newContext({viewport,isMobile:shell==='phone',hasTouch:shell==='phone',serviceWorkers:'block'});
   const report={shell,viewport,status:'running',blocked:[],static:[],skins:[],errors:[]};results.push(report);save();
   try{
    await context.route('**/*',async route=>{
     const req=route.request(),u=new URL(req.url());
     if(u.origin===new URL(base).origin&&req.method()==='GET'&&u.pathname.startsWith(appPath)&&pins.public_sha256[u.pathname]){
      const response=await route.fetch(),body=await response.body(),sha256=hash(body);
      assert.equal(response.status(),200);assert.equal(sha256,pins.public_sha256[u.pathname],u.pathname+' drift');
      report.static.push({path:u.pathname,status:response.status(),sha256,resourceType:req.resourceType(),proof:'unmodified actual upstream bytes fulfilled to this request'});
      return route.fulfill({response,body});
     }
     return policy(route,report,pins);
    });
    await context.addInitScript(()=>{localStorage.setItem('wos.coached','true');localStorage.setItem('wos.tour.done','1');});
    const page=await context.newPage();page.setDefaultTimeout(20000);

    const streamEvents=[];let streamStart=0;
    page.on('request',req=>{if(new URL(req.url()).pathname===appPath+'api/overview-stream')streamStart=Date.now();});
    // Observe native EventSource messages using page instrumentation, not response fulfillment/replay.
    await context.addInitScript(()=>{const Native=window.EventSource;window.__qaStream=[];window.EventSource=class extends Native{constructor(...args){super(...args);for(const kind of ['sources','delta','done','error'])this.addEventListener(kind,e=>{if(e.data)window.__qaStream.push({event:kind,at:Date.now(),data:JSON.parse(e.data)});});}};});
    await page.goto(base+'/wizard-os-home/'+(shell==='desktop'?'desktop.html':'')+`?shell=${shell}&open=${appId}`,{waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>window.WosSkin?.list?.length&&window.WizCore?.appsLoaded);
    await page.evaluate(async id=>{await WizCore.appsLoaded();await WizCore.refreshApps({afterPending:true});WizCore.deeplink.route(location.pathname+'?open='+id);},appId);
    assert.equal(await page.evaluate(()=>document.documentElement.dataset.shell),shell);
    const {frame,el}=await appFrame(page,base);assert(new URL(frame.url()).pathname.startsWith(appPath));
    await frame.waitForFunction(()=>document.documentElement.hasAttribute('data-wz-hosted'));
    await page.waitForFunction(f=>WizAppServices.authorized(f),el);
    report.frame=frame.url();report.voiceAdmission=report.registry.receives_voice_input===true;
    await frame.waitForFunction(()=>document.querySelector('#ai-sub')?.textContent.includes('set up by your server admin'));
    assert.equal(await frame.locator('#ai-btn').isVisible(),false,'No provider-setting mutations in QA');
    // New synthetic question per viewport/job; no cached-answer replay qualifies.
    const query=shell==='phone'?(process.env.QA_PHONE_QUERY||'Python json loads official library reference'):(process.env.QA_DESKTOP_QUERY||'Python itertools chain official library reference');
    await frame.locator('#q').fill(query);await frame.locator('#q').press('Enter');
    await frame.locator('#web li').first().waitFor({state:'visible',timeout:60000});
    await frame.waitForFunction(()=>window.__qaStream?.some(e=>e.event==='done'),null,{timeout:90000});
    streamEvents.push(...await frame.evaluate(()=>window.__qaStream));report.stream=streamEvents;
    const done=streamEvents.find(e=>e.event==='done');
    assert(done&&!done.data.error&&!done.data.cached,'Fresh successful private stream required');assert.equal(done.data.model,'gpt-oss-120b');
    const answer=streamEvents.filter(e=>e.event==='delta').map(e=>e.data.t||'').join('');
    assert(answer.length&&/\[\d+\]/.test(answer));report.firstDeltaMs=streamEvents.find(e=>e.event==='delta').at-streamStart;
    report.model=done.data.model;report.citationCount=(answer.match(/\[\d+\]/g)||[]).length;
    report.webCount=await frame.locator('#web li').count();
    const available=await page.evaluate(()=>WosSkin.list.map(s=>({id:s.id,scheme:s.scheme||s.colorScheme||''})));
    report.availableSkins=available;
    // Reuse retained QA skin IDs, no owner preference writes.
    const selected=['nebula','obsidian-light'];for(const id of selected)assert(available.some(s=>s.id===id),'Missing installed skin '+id);
    for(const id of selected){
     await page.evaluate(id=>WosSkin.preview(WosSkin.index(id)),id);
     await frame.waitForFunction(id=>document.documentElement.dataset.skin===id,id);
     await sleep(500);
     const appearance=await frame.evaluate(()=>({skin:document.documentElement.dataset.skin,scheme:getComputedStyle(document.documentElement).colorScheme,panel:getComputedStyle(document.querySelector('#ov')).backgroundColor,body:getComputedStyle(document.body).backgroundColor}));
     assert.equal(appearance.skin,id);
     const file=`actual-${shell}-${id}.png`;await page.screenshot({path:path.join(out,file)});report.skins.push({id,file,appearance});save();
    }
    assert.equal(report.errors.length,0,report.errors.join('\n'));
    const required=[shell==='desktop'?'/wizard-os-home/desktop.html':'/wizard-os-home/','/wizard-os-home/core/app-client.js',appPath,appPath+'app.js'];
    for(const p of required)assert(report.static.some(r=>r.path===p&&r.status===200),'Missing actual body proof '+p);
    report.status=report.voiceAdmission?'passed':'blocked_voice_admission';save();
   }catch(e){report.status='failed';report.errors.push(String(e.stack));const page=context.pages()[0];if(page)await page.screenshot({path:path.join(out,`FAIL-${shell}.png`)}).catch(()=>{});save();}
   finally{await context.close();}
  }
 }finally{await browser.close();save();}
 assert(results.every(r=>r.status==='passed'),'Live acceptance incomplete: inspect saved evidence');
}
if(require.main===module)main().catch(e=>{console.error(e);process.exitCode=1;});
module.exports={policy};
