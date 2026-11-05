const assert=require('node:assert/strict'),crypto=require('node:crypto');
const {policy}=require('./live-served-browser.cjs');
const base='https://wizard.tailc0f369.ts.net',p='/wizard-os-home/core/app-client.js';
const bytes=Buffer.from('actual upstream static bytes');
const sha=crypto.createHash('sha256').update(bytes).digest('hex');
function fixture(path=p){
 const calls=[];const response={status:()=>200,body:async()=>bytes};
 return {calls,response,route:{request:()=>({url:()=>base+path,method:()=> 'GET',resourceType:()=> 'script'}),fetch:async()=>{calls.push('fetch');return response;},fulfill:async x=>{calls.push(x);},continue:async()=>calls.push('continue'),abort:async()=>calls.push('abort')}};
}
(async()=>{
 const report={blocked:[],static:[]},f=fixture();await policy(f.route,report,{public_sha256:{[p]:sha}});
 assert.equal(f.calls[0],'fetch');assert.equal(f.calls[1].response,f.response);assert.equal(f.calls[1].body,bytes);assert.equal(report.static[0].sha256,sha);
 const bad=fixture();await assert.rejects(policy(bad.route,{blocked:[],static:[]},{public_sha256:{[p]:'0'.repeat(64)}}),/drift/);assert.equal(bad.calls.length,1);
 const history=fixture('/wizard/hermes/api/sessions');await policy(history.route,{blocked:[],static:[]},{public_sha256:{}});assert(!history.calls.includes('fetch'));assert.deepEqual(history.calls[0].json,{});
 console.log('PASS: exact actual bytes fulfilled; drift rejected; unrelated owner history never fetched');
})().catch(e=>{console.error(e);process.exitCode=1;});
