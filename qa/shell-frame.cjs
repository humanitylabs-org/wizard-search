// Pure geometry oracle shared with browser-free regression; no shell-specific class names.
function visibleBounds(r, viewport) {
 return r.width>0 && r.height>0 && r.right>0 && r.bottom>0 && r.left<viewport.width && r.top<viewport.height;
}
async function appFrame(page, base, timeout=45000) {
 const deadline=Date.now()+timeout;
 while(Date.now()<deadline) {
  for(const frame of page.frames()) {
   const url=new URL(frame.url(),base);
   if(url.origin!==new URL(base).origin || !url.pathname.startsWith('/wizard-search/'))continue;
   const el=await frame.frameElement();
   const state=await el.evaluate(f=>{
    const r=f.getBoundingClientRect(),s=getComputedStyle(f);
    return {r:{left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height},
     viewport:{width:innerWidth,height:innerHeight},display:s.display,visibility:s.visibility};
   }).catch(()=>null);
   if(state && state.display!=='none' && state.visibility==='visible' && visibleBounds(state.r,state.viewport)) {
    await frame.waitForURL(u=>u.origin===new URL(base).origin && u.pathname.startsWith('/wizard-search/'),{timeout:Math.max(1,deadline-Date.now())});
    await frame.locator('#q').waitFor({state:'visible',timeout:Math.max(1,deadline-Date.now())});
    // Native actionability, not force-click: a covered or clipped retained frame is not the app in front.
    await frame.locator('#q').click({trial:true,timeout:Math.max(1,deadline-Date.now())});
    return {frame,el};
   }
   await el.dispose();
  }
  await new Promise(resolve=>setTimeout(resolve,100));
 }
 throw Error('No committed, intersecting, actionable Search frame in actual frame tree');
}
module.exports={visibleBounds,appFrame};
