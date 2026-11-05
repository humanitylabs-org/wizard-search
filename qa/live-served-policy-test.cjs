const {test}=require('node:test'),assert=require('node:assert/strict');
const {policy}=require('./live-served-browser.cjs');
function fake(url,method='GET',json={}){
 const calls=[];return {calls,request:()=>({url:()=>url,method:()=>method}),continue:()=>calls.push('continue'),abort:()=>calls.push('abort'),
 fulfill:value=>calls.push(['fulfill',value]),fetch:async()=>{calls.push('fetch');return{status:()=>200,json:async()=>json};}};
}
const base='https://wizard.tailc0f369.ts.net';
test('owner histories, agents, accounts, unknown JSON and every unrelated write never reach network',async()=>{
 for(const [path,method] of [['/wizard/v1/agents','GET'],['/wizard/v1/accounts','GET'],['/wizard/v1/history','GET'],['/wizard-os-home/store-data/private.json','GET'],['/wizard/v1/settings','PATCH'],['/wizard-search/preview/api/overview-provider','POST']]){
  const route=fake(base+path,method),report={blocked:[]};await policy(route,report);
  assert(!route.calls.includes('fetch'));assert(!route.calls.includes('continue'));
 }
});
test('only actual Search registry record enters shell, other installed metadata is discarded',async()=>{
 const app={id:'search-preview',name:'Search',url:'/wizard-search/preview/',receives_voice_input:true};
 const route=fake(base+'/wizard/v1/apps','GET',{apps:[{id:'unrelated-owner-app'},app]});
 const report={blocked:[]};await policy(route,report);assert.deepEqual(report.registry,app);
 assert.deepEqual(route.calls.at(-1)[1].json,{apps:[app],in_development:[]});
});
test('actual Search APIs and public shell scripts are not substituted; foreign origins blocked',async()=>{
 for(const path of ['/wizard-search/preview/api/overview-stream?q=synthetic','/wizard-search/preview/api/images?q=synthetic','/wizard-search/preview/app.js','/wizard-os-home/core/app-client.js']){
  const route=fake(base+path);await policy(route,{blocked:[]});assert.deepEqual(route.calls,['continue']);
 }
 const route=fake('https://foreign.invalid/track');await policy(route,{blocked:[]});assert.deepEqual(route.calls,['abort']);
});
