#!/usr/bin/env python3
"""Browser-free actual HTTP/bootstrap + pinned shell JS regression. No owner API access."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import threading
from http.server import ThreadingHTTPServer
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fixture', ROOT / 'qa/consolidated-host.py')
assert spec is not None and spec.loader is not None
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)

# Execute unchanged public core/config.js and core/apps.js, not a reimplementation
# of endpoint('apps') or readRemote(). Minimal browser globals only, no browser.
PROGRAM = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const [base,shell]=process.argv.slice(1);
const {visibleBounds}=require(process.cwd()+'/qa/shell-frame.cjs');
assert(visibleBounds({left:0,top:0,right:100,bottom:100,width:100,height:100},{width:390,height:844}));
for(const r of [
 {left:0,top:0,right:100,bottom:0,width:100,height:0},
 {left:390,top:0,right:780,bottom:844,width:390,height:844},
 {left:-390,top:0,right:0,bottom:844,width:390,height:844},
 {left:0,top:844,right:390,bottom:1688,width:390,height:844}
])assert(!visibleBounds(r,{width:390,height:844}));
async function exercise(mode) {
 const calls=[],store=new Map(),events=[];
 const sandbox={console,URL,Intl,Date,Map,Set,Promise,AbortSignal,
  location:new URL(base),document:{hidden:false,addEventListener(){}},
  localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)},
  CustomEvent:class{constructor(type,options){this.type=type;this.detail=options?.detail;}},
  addEventListener(){},dispatchEvent:e=>events.push(e.type),
  WizCore:{norm:s=>String(s).toLowerCase()},
  fetch:async url=>{calls.push(url);const r=await fetch(new URL(url,base));let data=await r.json();
   if(mode==='broken-bootstrap' && url==='/wizard/v1/bootstrap')data={apps:[]};
   if(mode==='missing-endpoint' && url==='/wizard/v1/bootstrap')data={...data,endpoints:{}};
   if(mode==='untrusted-source' && url==='/wizard/v1/apps')data={...data,apps:data.apps.map(a=>({...a,source:'synthetic-QA-registry'}))};
   return {ok:r.ok,json:async()=>data};}
 };
 sandbox.window=sandbox;vm.createContext(sandbox);
 for(const file of ['config.js','apps.js'])vm.runInContext(fs.readFileSync(shell+'/core/'+file,'utf8'),sandbox,{filename:file});
 await sandbox.WizConfig.ready;await sandbox.WizCore.appsLoaded();
 const regs=['mobile','desktop'].map(s=>sandbox.WizCore.apps(s));
 const result={mode,bootstrap:sandbox.WizConfig.raw.bootstrap,endpoint:sandbox.WizConfig.endpoint('apps'),calls,
  apps:regs.map(r=>r.APPS.filter(a=>a.id==='wizard-search').map(a=>({id:a.id,source:a.source,view:a.view,voice:a.receives_voice_input}))) };
 if(mode==='valid'){
  assert.equal(result.bootstrap,1);assert.equal(result.endpoint,'/wizard/v1/apps');assert(calls.includes('/wizard/v1/apps'));
  for(const apps of result.apps){assert.equal(apps.length,1);assert.equal(apps[0].source,'apps.json');assert.equal(apps[0].view.mode,'original');assert.equal(apps[0].voice,true);}
 }else if(mode==='untrusted-source')for(const apps of result.apps)assert.notEqual(apps[0].source,'apps.json');
 else {assert(!calls.includes('/wizard/v1/apps'));assert(result.apps.every(a=>a.length===0));}
 return result;
}
(async()=>{const results=[];for(const mode of ['valid','broken-bootstrap','missing-endpoint','untrusted-source'])results.push(await exercise(mode));console.log(JSON.stringify({passed:true,geometry_negatives:4,results},null,2));})().catch(e=>{console.error(e.stack);process.exitCode=1;});
'''


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--shell', type=Path, required=True)
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    with tempfile.TemporaryDirectory() as td:
        server = ThreadingHTTPServer(('127.0.0.1', 0), fixture.handler(Path(td), 'http://127.0.0.1:1'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        try:
            def read(path):
                with urllib.request.urlopen(base + path, timeout=3) as r:
                    return json.load(r)
            bootstrap = read('/wizard/v1/bootstrap')
            assert isinstance(bootstrap['bootstrap'], int) and bootstrap['bootstrap']
            assert bootstrap['capabilities'] == {} and bootstrap['endpoints'] == {'apps': '/wizard/v1/apps'}
            assert read(bootstrap['endpoints']['apps']) == {'apps': [fixture.APP], 'in_development': []}
            assert read('/wizard/v1/settings')['settings']['owner']['name'] == 'Synthetic QA owner'
            for route, method, status in [('/wizard/v1/unknown', 'GET', 404),
                                          ('/wizard/v1/settings', 'PUT', 403),
                                          ('/wizard/v1/ui-preferences/seed', 'POST', 403)]:
                try:
                    urllib.request.urlopen(urllib.request.Request(base + route, method=method), timeout=3)
                except urllib.error.HTTPError as e:
                    assert e.code == status
                else:
                    raise AssertionError('Unknown routes/writes must fail closed')
            result = subprocess.run(['node', '-e', PROGRAM, base, str(a.shell.resolve())],
                                    cwd=ROOT, check=True, capture_output=True, text=True, timeout=15)
            if a.out:
                a.out.write_text(result.stdout)
            print(result.stdout)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == '__main__':
    main()
