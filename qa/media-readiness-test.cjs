// Browser-free oracle regressions only. No provider/media evidence is synthesized.
const test=require('node:test'),assert=require('node:assert/strict');
const {fullCandidates,firstDecoded,waitViewerImage,outsideViewer}=require('./media-readiness.cjs');
const base='http://127.0.0.1:19771';
test('full admission uses at most six real tile proxy identifiers, never thumbnail URLs',()=>{
 const tiles=Array.from({length:9},(_,index)=>({index,title:`tile ${index}`,thumb:`${base}/wizard-search/thumb/real-id-${index}.jpg`}));
 const candidates=fullCandidates(tiles,base);assert.equal(candidates.length,6);assert.equal(candidates[0].url,base+'/wizard-search/img/real-id-0.jpg');assert.equal(candidates[5].index,5);
});
test('external origins and non-proxy candidates fail closed',()=>{
 assert.throws(()=>fullCandidates([{thumb:'https://example.invalid/wizard-search/thumb/id.jpg'}],base));
 assert.throws(()=>fullCandidates([{thumb:base+'/wizard-search/image/id.jpg'}],base));
});
test('HTTP success or an open viewer alone cannot admit an undecoded image',()=>{
 assert.equal(firstDecoded([{status:200,decoded:false,width:0,height:0}]),null);
 assert.equal(firstDecoded([{status:500,decoded:true,width:100,height:100}]),null);
 const good={index:2,status:200,decoded:true,width:640,height:480};
 assert.equal(firstDecoded([{index:0,status:502},{index:1,status:200,decoded:false},good,{index:3,status:200,decoded:true,width:800,height:600}]),good);
});
test('native viewer gate rejects pending/broken/wrong-src images before geometry, even if viewer is open',async()=>{
 const oldDocument=global.document,oldWindow=global.window;
 const image={complete:false,naturalWidth:0,naturalHeight:0,currentSrc:base+'/wizard-search/img/id.jpg'};
 global.document={querySelector:()=>image};global.window={WosChat:{viewer:{isOpen:()=>true}}};
 try{
  const page={waitForFunction:async(fn,url)=>{assert.equal(fn(url),false);throw Error('readiness rejected');},evaluate:async()=>{throw Error('geometry must not execute');}};
  const selected={url:image.currentSrc,width:640,height:480};
  await assert.rejects(waitViewerImage(page,selected),/readiness rejected/);
  let clicked=false;page.mouse={click:async()=>{clicked=true;}};
  await assert.rejects(outsideViewer(page,selected,false),/readiness rejected/);assert.equal(clicked,false);
  image.complete=true;await assert.rejects(waitViewerImage(page,selected),/readiness rejected/);
  image.naturalWidth=640;image.naturalHeight=480;image.currentSrc=base+'/wizard-search/img/different.jpg';await assert.rejects(waitViewerImage(page,selected),/readiness rejected/);
 }finally{global.document=oldDocument;global.window=oldWindow;}
});
