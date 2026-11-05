#!/usr/bin/env python3
"""Queued Forum-only QA. Reuse immutable image inputs; diagnose before cleanup."""
import argparse, hashlib, json, os, pathlib, signal, subprocess, sys, time
from packaged_readiness import request_json, wait_search

root=pathlib.Path(__file__).resolve().parents[1]
os.chdir(root)
p=argparse.ArgumentParser()
p.add_argument('--reuse-from',type=pathlib.Path,help='Prior stage containing artifact-manifest.json and original image archive')
a=p.parse_args()
sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip() if (root/'.git').exists() else (root/'SOURCE_SHA').read_text().strip()
out=root/'evidence';out.mkdir(exist_ok=True)
env=os.environ.copy();env.update(QA_EVIDENCE=str(out),QA_BASE='http://127.0.0.1:19771',QA_PRIVATE_PROOF=str(root/'private-proxy-proof.json'),PLAYWRIGHT_MODULE='/srv/work/opaque-music-build/node_modules/playwright',QA_APP_CLIENT=str(root/'shell-web/core/app-client.js'))
def run(argv,**kw):return subprocess.run(argv,check=True,**kw)
def digest(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
project='search-consolidated-'+sha[:10]
image='wizard-search:'+sha+'-amd64';image_sha=sha
archive=root/('wizard-search-'+sha+'-amd64.tar')
reuse=None
if a.reuse_from:
 old=json.loads((a.reuse_from/'artifact-manifest.json').read_text())
 # This receipt is generated from the original pushed git tree, never from
 # possibly modified files in the old scratch stage. Includes every COPY input,
 # Dockerfile/.dockerignore and the runtime compose recipe.
 reuse=json.loads((root/'image-reuse.json').read_text())
 assert reuse['runtime_source_sha']==old['source_sha']
 assert reuse['image_id']==old['image_id']
 paths=set(reuse['runtime_file_sha256'])
 expected={'app/Dockerfile','.dockerignore','server.py','setup.json','openapi.json','SETUP.md','runtipi/docker-compose.yml'}|{str(f.relative_to(root)) for f in (root/'web').rglob('*') if f.is_file()}
 assert paths==expected,'Runtime input inventory changed; rebuild required'
 assert all(digest(root/name)==value for name,value in reuse['runtime_file_sha256'].items()),'Runtime bytes changed; rebuild required'
 image=old['image'];image_sha=old['source_sha'];archive=a.reuse_from/old['image_archive']
 assert digest(archive)==old['image_archive_sha256'],'Prior image archive changed'
 actual=json.loads(subprocess.check_output(['docker','image','inspect',image]))[0]
 assert actual['Id']==old['image_id'] and actual['Config']['Labels']['org.opencontainers.image.revision']==image_sha
 (out/'image-reuse.json').write_text(json.dumps({**reuse,'candidate_source_sha':sha,'archive_sha256':old['image_archive_sha256'],'verified':True},indent=2)+'\n')
override=root/'qa-runtime.yml'
override.write_text('services:\n  wizard-search:\n    image: '+image+'\n    ports: ["127.0.0.1:19772:9288"]\n    environment:\n      TINFOIL_PROXY_URL: ""\n      WIZARD_SEARCH_TINFOIL_APP: ""\n      WIZARD_SEARCH_SOCKS: ""\n      FIRECRAWL_CLOUD_API_KEY: ""\n      FIRECRAWL_ROUTER_URL: ""\n      BRIGHTDATA_API_TOKEN: ""\n')
compose=['docker','compose','--project-directory',str(root),'-p',project,'-f','runtipi/docker-compose.yml','-f',str(override)]
server=None;started=False;manifest={}
# Diagnostics run inside only this job's Search container and query only its
# bundled sidecar. No container env, private app, owner API or mounts are read.
probe='''import json,urllib.request,urllib.error,urllib.parse
base='http://wizard-search-searxng:8080'
for category in ['general','images']:
 url=base+'/search?'+urllib.parse.urlencode({'q':'Python programming language','format':'json','categories':category,'language':'en','safesearch':1})
 try:
  with urllib.request.urlopen(url,timeout=12) as r:
   d=json.load(r); rows=d.get('results') or []
   print(json.dumps({'category':category,'status':r.status,'result_count':len(rows),'unresponsive_engines':d.get('unresponsive_engines'),'sample':[{k:x.get(k) for k in ['title','url','img_src']} for x in rows[:5]]}))
 except urllib.error.HTTPError as e: print(json.dumps({'category':category,'status':e.code,'body_excerpt':e.read(4096).decode('utf8','replace')}))
 except Exception as e: print(json.dumps({'category':category,'error':type(e).__name__,'detail':str(e)[:512]}))
'''
def diagnostics():
 for name,args in [('compose-state.txt',['ps','--all']),('compose-provider.log',['logs','--no-color','--tail','120','wizard-search-searxng','wizard-search'])]:
  try:
   result=subprocess.run(compose+args,capture_output=True,text=True,timeout=15)
   (out/name).write_text(result.stdout+result.stderr)
  except Exception as error:(out/name).write_text(type(error).__name__+': '+str(error))
 try:
  result=subprocess.run(compose+['exec','-T','wizard-search','python3','-c',probe],capture_output=True,text=True,timeout=30)
  (out/'sidecar-query-diagnostic.jsonl').write_text(result.stdout+result.stderr)
 except Exception as error:(out/'sidecar-query-diagnostic.jsonl').write_text(type(error).__name__+': '+str(error))
def expired(*_):raise TimeoutError('650s worker budget exhausted; preserving diagnostics and cleaning up')
signal.signal(signal.SIGALRM,expired)
signal.alarm(650)
try:
 with (out/'unit.log').open('w') as f:run([sys.executable,'-m','unittest','discover','-s','tests','-v'],stdout=f,stderr=subprocess.STDOUT)
 run(['node','--check','web/app.js']);run([sys.executable,'tools/check_view.py'])
 if not reuse:
  run(['docker','build','--build-arg','REVISION='+sha,'-f','app/Dockerfile','-t',image,'.'])
  run(['docker','save','-o',str(archive),image])
 image_id=subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}}'],text=True).strip()
 manifest={'source_sha':sha,'image_source_sha':image_sha,'runtime_bytes_identical':bool(reuse),'runtime_file_sha256':reuse['runtime_file_sha256'] if reuse else {},'image':image,'image_id':image_id,'image_archive':archive.name,'image_archive_sha256':digest(archive),'tests':'pending','production_activated':False}
 (root/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 # Pinned provider already pulled by the first admitted job. No blind pull/build.
 run(['docker','image','inspect','docker.io/searxng/searxng@sha256:64936ab0847aae6494d37edf688ce792b262e8467d48ad844c0bf3f899a45249'],stdout=subprocess.DEVNULL)
 started=True;run(compose+['up','-d','--no-build','--pull','never'])
 cid=subprocess.check_output(compose+['ps','-q','wizard-search'],text=True).strip()
 networks=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]['NetworkSettings']['Networks']
 gateway=next(v['Gateway'] for v in networks.values() if v.get('Gateway'))
 run([sys.executable,'qa/bridge-proof.py','--bind',gateway,'--out',str(out/'bridge-proof.json')])
 # App /health reports settings only. Readiness must include the real sidecar.
 readiness=[];deadline=time.monotonic()+60
 while time.monotonic()<deadline:
  app=request_json('http://127.0.0.1:19772/api/health',timeout=2)
  check=subprocess.run(compose+['exec','-T','wizard-search','python3','-c',"import urllib.request; r=urllib.request.urlopen('http://wizard-search-searxng:8080/',timeout=2); assert r.status==200; print(r.status)"],capture_output=True,text=True,timeout=8)
  readiness.append({'app':app,'sidecar_exit':check.returncode,'sidecar_output':(check.stdout+check.stderr)[-4096:]})
  (out/'startup-readiness.json').write_text(json.dumps(readiness,indent=2)+'\n')
  if app['status']==200 and check.returncode==0:break
  time.sleep(2)
 else:raise RuntimeError('Bundled sidecar did not become ready within 60s')
 wait_search('http://127.0.0.1:19772',out)
 server=subprocess.Popen([sys.executable,'qa/consolidated-host.py','--shell',str(root/'shell-web')],stdout=(out/'host.log').open('w'),stderr=subprocess.STDOUT)
 for i in range(40):
  if request_json('http://127.0.0.1:19771/wizard/v1/apps',timeout=2)['status']==200:break
  if i==39:raise RuntimeError('Synthetic QA host did not become ready')
  time.sleep(.25)
 run(['node','qa/voice-browser.cjs'],env={**env,'WIZARD_APP_CLIENT':str(root/'shell-web/core/app-client.js')})
 run(['node','qa/consolidated-browser.cjs'],env=env)
 manifest.update(tests='passed',shell_visual_review='required',browser_host='copied public shell, synthetic registry; not production',live_private_provider_proof='private-proxy-proof.json (separate network proof; replay only for browser AI UI)')
 (root/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))
except BaseException as error:
 (out/'worker-failure.json').write_text(json.dumps({'source_sha':sha,'type':type(error).__name__,'error':str(error)[:2000],'tests':'failed','production_activated':False},indent=2)+'\n')
 raise
finally:
 signal.alarm(0)
 # Preserve decisive HTTP errors/provider state BEFORE teardown on every path.
 if started:diagnostics()
 if server:
  server.terminate()
  try:server.wait(timeout=10)
  except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
 if started:subprocess.run(compose+['down','--volumes','--remove-orphans'],check=False,timeout=40)
