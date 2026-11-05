// Harness-only real-media admission. Never supplies bytes to the native viewer.
const assert=require('node:assert/strict');
function fullCandidates(tiles,base){
 const origin=new URL(base).origin;
 return tiles.slice(0,6).map(t=>{
  const u=new URL(t.thumb,base);
  assert.equal(u.origin,origin,'Image candidate must use the packaged same-origin proxy');
  assert.match(u.pathname,/^\/wizard-search\/thumb\/[^/]+\.jpg$/);
  u.pathname=u.pathname.replace('/thumb/','/img/');u.search='';
  return {...t,url:u.href};
 });
}
function firstDecoded(attempts){return attempts.find(a=>a.status===200 && a.decoded && a.width>0 && a.height>0) || null;}
async function probeFullImages({candidates,budgetMs}){
 // Runs in the actual app frame. Fetch AND decode full proxy bytes, not thumbnails.
 const started=performance.now(),controller=new AbortController();let rejectDeadline;
 const deadline=new Promise((_,reject)=>{rejectDeadline=reject;});deadline.catch(()=>{});
 const timer=setTimeout(()=>{controller.abort();rejectDeadline(Error('45s full-image selection deadline'));},budgetMs);
 const base64=bytes=>{let s='';for(let i=0;i<bytes.length;i+=16384)s+=String.fromCharCode(...bytes.subarray(i,i+16384));return btoa(s);};
 const rows=await Promise.all(candidates.map(async candidate=>{
  const start=performance.now();let image,objectURL,bytes;
  const row={...candidate,status:null,contentType:null,decoded:false};
  try{
   const response=await fetch(candidate.url,{signal:controller.signal,credentials:'same-origin'});
   row.status=response.status;row.responseURL=response.url;row.contentType=response.headers.get('content-type');row.headersMs=performance.now()-start;
   if(new URL(response.url).origin!==location.origin)throw Error('Full-image proxy redirected outside the copied host');
   bytes=new Uint8Array(await response.arrayBuffer());
   row.bytes=bytes.length;row.sha256=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
   if(response.status!==200){row.bodyBase64=base64(bytes);row.bodyTruncated=false;throw Error('Full-image HTTP '+response.status);}
   if(bytes.length>32*1024*1024)throw Error('Full image exceeds bounded 32 MiB diagnostic allowance');
   objectURL=URL.createObjectURL(new Blob([bytes],{type:row.contentType || ''}));image=new Image();image.src=objectURL;
   await Promise.race([image.decode(),deadline]);
   row.width=image.naturalWidth;row.height=image.naturalHeight;row.decoded=!!(image.complete && row.width && row.height);
   if(!row.decoded)throw Error('Full proxy bytes did not decode to nonzero dimensions');
   row.fullBase64=base64(bytes);
  }catch(error){row.error=String(error);if(bytes){row.bodyBase64=base64(bytes);row.bodyTruncated=false;}}
  finally{if(image)image.src='';if(objectURL)URL.revokeObjectURL(objectURL);row.elapsedMs=performance.now()-start;}
  return row;
 }));
 clearTimeout(timer);
 // Bound browser-to-runner output: preserve only the first real decodable full file.
 const selected=rows.find(r=>r.decoded && r.status===200);
 for(const row of rows)if(row!==selected)delete row.fullBase64;
 return {budgetMs,elapsedMs:performance.now()-started,attempts:rows};
}
async function waitViewerImage(page,selected){
 await page.waitForFunction(url=>{
  const image=document.querySelector('.mviewer:not([hidden]) .mv-stage img');
  return window.WosChat?.viewer.isOpen() && image?.complete && image.naturalWidth>0 && image.naturalHeight>0 && image.currentSrc===url;
 },selected.url,{timeout:10000});
 const loaded=await page.evaluate(async()=>{
  const image=document.querySelector('.mviewer:not([hidden]) .mv-stage img');
  let timer;try{await Promise.race([image.decode(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Native viewer decode deadline')),5000);})]);}
  finally{clearTimeout(timer);}
  const r=image.getBoundingClientRect();
  return {src:image.currentSrc,complete:image.complete,width:image.naturalWidth,height:image.naturalHeight,bounds:{x:r.x,y:r.y,width:r.width,height:r.height}};
 });
 assert.equal(loaded.width,selected.width);assert.equal(loaded.height,selected.height);
 assert(loaded.bounds.width>0 && loaded.bounds.height>0,'Decoded image must have a rendered box');
 return loaded;
}
async function outsideViewer(page,selected,touch){
 // Never infer letterbox geometry from an open but pending/broken image.
 await waitViewerImage(page,selected);
 const point=await page.evaluate(()=>{
  const v=document.querySelector('.mviewer:not([hidden])'),stage=v?.querySelector('.mv-stage'),image=stage?.querySelector('img');
  if(!image?.complete || !image.naturalWidth || !image.naturalHeight)return null;
  const r=stage.getBoundingClientRect(),points=[];
  for(const f of [.02,.1,.25,.5,.75,.9,.98])points.push([r.left+3,r.top+r.height*f],[r.right-3,r.top+r.height*f],[r.left+r.width*f,r.top+3],[r.left+r.width*f,r.bottom-3]);
  for(const [x,y] of points){
   const target=document.elementFromPoint(x,y);
   if(target===v || target===stage)return {x,y,kind:'bare-stage'};
   if(target===image){const b=image.getBoundingClientRect(),fit=Math.min(b.width/image.naturalWidth,b.height/image.naturalHeight),w=image.naturalWidth*fit,h=image.naturalHeight*fit;
    if(x<b.left+(b.width-w)/2 || x>b.right-(b.width-w)/2 || y<b.top+(b.height-h)/2 || y>b.bottom-(b.height-h)/2)return {x,y,kind:'decoded-image-letterbox'};}
  }return null;
 });
 assert(point,'No native outside-viewer hit target after real full-image decode; never force-click');
 if(touch)await page.touchscreen.tap(point.x,point.y);else await page.mouse.click(point.x,point.y);
 await page.waitForFunction(()=>!WosChat.viewer.isOpen(),null,{timeout:5000});return point;
}
module.exports={fullCandidates,firstDecoded,probeFullImages,waitViewerImage,outsideViewer};
