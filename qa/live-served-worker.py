#!/usr/bin/env python3
"""Forum light job. Pin public serving bytes, then bounded actual-shell browser acceptance.

No tunnel, auth/header substitution, fixture Search API, Docker build, or owner writes.
--pin-only is read-only HTTP preparation, not browser acceptance or a job submission.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--base',default='https://wizard.tailc0f369.ts.net')
    p.add_argument('--app-path',default='/wizard-search/preview/')
    p.add_argument('--app-id',default='search-preview')
    p.add_argument('--pins',type=Path,required=True)
    p.add_argument('--runtime-manifest',type=Path,required=True)
    p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--pin-only',action='store_true')
    a=p.parse_args();a.evidence.mkdir(parents=True,exist_ok=True)
    def fetch(path):
        with urllib.request.urlopen(a.base+path,timeout=20) as r:
            assert r.status==200
            return r.read()
    def obj(path):return json.loads(fetch(path))
    paths=['/wizard-os-home/','/wizard-os-home/desktop.html','/wizard-os-home/core/app-client.js']
    paths += [a.app_path+n for n in ('','app.js','app.css','voice-input.js','standalone-tokens.css')]
    current={path:hashlib.sha256(fetch(path)).hexdigest() for path in paths}
    runtime=json.loads(a.runtime_manifest.read_text())
    assert runtime['image_source_sha']=='7fac0ebc6ce22ff951b5fc6738a41b7d40a9456b'
    for name in ('index.html','app.js','app.css','voice-input.js','standalone-tokens.css'):
        assert current[a.app_path+('' if name=='index.html' else name)]==runtime['runtime_file_sha256']['web/'+name], 'Actual Search runtime bytes differ: '+name
    health=obj(a.app_path+'api/health');cfg=obj(a.app_path+'api/config');provider=obj(a.app_path+'api/overview-provider')
    # Actual installed public app metadata, then discard every unrelated record.
    apps=obj('/wizard/v1/apps')['apps'];candidate=[r for r in apps if r.get('id')==a.app_id]
    assert len(candidate)==1 and candidate[0]['url']==a.app_path and candidate[0]['name']=='Search'
    if a.pin_only:
        assert not a.pins.exists(),'Pin-only refuses overwrite; retain drift evidence'
        value={'base':a.base,'app_path':a.app_path,'app_id':a.app_id,
               'source_sha':(ROOT/'SOURCE_SHA').read_text().strip(),'public_sha256':current,
               'health':health,'registry':candidate[0],'configuration':cfg,'overview_provider':provider,
               'scope':'actual canonical public static and Search-only installed metadata; not acceptance'}
        a.pins.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value,indent=2));return
    pinned=json.loads(a.pins.read_text())
    preflight={'public_static_exact':current==pinned['public_sha256'],'current_public_sha256':current,
               'registry':candidate[0],'health':health,'configuration':cfg,'overview_provider':provider}
    (a.evidence/'live-preflight.json').write_text(json.dumps(preflight,indent=2)+'\n')
    assert preflight['public_static_exact'],'Actual public serving bytes drifted since parent-reviewed pins'
    assert health['revision']=='7fac0ebc6ce22ff951b5fc6738a41b7d40a9456b' and health['ok'] is True
    assert candidate[0].get('receives_voice_input') is True,'Live voice admission remains false; parent must fix independent writer first'
    assert cfg['providers']=={'searxng':True,'socks':False,'firecrawl_cloud':False,'brightdata':False,'firecrawl_router':False,'tinfoil':True}
    assert provider['mode']=='proxy' and provider['model']=='gpt-oss-120b'
    env={**os.environ,'QA_BASE':a.base,'QA_APP_PATH':a.app_path,'QA_APP_ID':a.app_id,
         'QA_LIVE_PINS':str(a.pins.resolve()),'QA_EVIDENCE':str(a.evidence.resolve()),
         'PLAYWRIGHT_MODULE':'/srv/work/opaque-music-build/node_modules/playwright'}
    subprocess.run(['node','qa/live-served-browser.cjs'],cwd=ROOT,env=env,check=True,timeout=330)

if __name__=='__main__':main()
