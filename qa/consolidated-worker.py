#!/usr/bin/env python3
"""Queued forum-only packaging/QA worker. Cleans every container/server it starts."""
import json,os,pathlib,subprocess,sys,time,urllib.request,hashlib
root=pathlib.Path(__file__).resolve().parents[1];os.chdir(root)
sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip() if (root/'.git').exists() else (root/'SOURCE_SHA').read_text().strip()
image='wizard-search:'+sha+'-amd64';out=root/'evidence';out.mkdir(exist_ok=True)
env=os.environ.copy();env.update(QA_EVIDENCE=str(out),QA_BASE='http://127.0.0.1:19771',QA_PRIVATE_PROOF=str(root/'private-proxy-proof.json'),PLAYWRIGHT_MODULE='/srv/work/opaque-music-build/node_modules/playwright',QA_APP_CLIENT=str(root/'shell-web/core/app-client.js'))
def run(argv,**kw):return subprocess.run(argv,check=True,**kw)
project='search-consolidated-'+sha[:10]
override=root/'qa-runtime.yml'
override.write_text('services:\n  wizard-search:\n    image: '+image+'\n    ports: ["127.0.0.1:19772:9288"]\n    environment:\n      TINFOIL_PROXY_URL: ""\n      WIZARD_SEARCH_TINFOIL_APP: ""\n')
compose=['docker','compose','--project-directory',str(root),'-p',project,'-f','runtipi/docker-compose.yml','-f',str(override)]
server=None
try:
 with (out/'unit.log').open('w') as f:run([sys.executable,'-m','unittest','discover','-s','tests','-v'],stdout=f,stderr=subprocess.STDOUT)
 run(['node','--check','web/app.js']);run([sys.executable,'tools/check_view.py'])
 run(['docker','build','--build-arg','REVISION='+sha,'-f','app/Dockerfile','-t',image,'.'])
 archive=root/('wizard-search-'+sha+'-amd64.tar')
 run(['docker','save','-o',str(archive),image])
 image_id=subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}}'],text=True).strip()
 manifest={'source_sha':sha,'image':image,'image_id':image_id,'image_archive':archive.name,'image_archive_sha256':hashlib.file_digest(archive.open('rb'),'sha256').hexdigest(),'tests':'pending','production_activated':False}
 (root/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 run(['docker','pull','docker.io/searxng/searxng@sha256:64936ab0847aae6494d37edf688ce792b262e8467d48ad844c0bf3f899a45249'])
 run(compose+['up','-d','--no-build','--pull','never'])
 cid=subprocess.check_output(compose+['ps','-q','wizard-search'],text=True).strip()
 networks=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]['NetworkSettings']['Networks']
 gateway=next(v['Gateway'] for v in networks.values() if v.get('Gateway'))
 run([sys.executable,'qa/bridge-proof.py','--bind',gateway,'--out',str(out/'bridge-proof.json')])
 for i in range(40):
  try:
   urllib.request.urlopen('http://127.0.0.1:19772/api/health',timeout=2).read();break
  except OSError:
   if i==39:raise
   time.sleep(.5)
 server=subprocess.Popen([sys.executable,'qa/consolidated-host.py','--shell',str(root/'shell-web')],stdout=(out/'host.log').open('w'),stderr=subprocess.STDOUT)
 for i in range(40):
  try:urllib.request.urlopen('http://127.0.0.1:19771/wizard/v1/apps',timeout=2).read();break
  except OSError:
   if i==39:raise
   time.sleep(.25)
 # Focused actual packaged web/image queries; no mock provider here.
 live={}
 for kind,q in [('web','Python programming language official documentation'),('images','Python programming language logo')]:
  import urllib.parse
  live[kind]=json.load(urllib.request.urlopen('http://127.0.0.1:19772/api/'+kind+'?q='+urllib.parse.quote(q),timeout=90))
  assert live[kind].get('source')=='searxng' and live[kind].get('results' if kind=='web' else 'images')
 (out/'packaged-live-search.json').write_text(json.dumps(live,indent=2))
 # Existing voice fixture tests the frozen admission seam; real shared resources are tested below.
 run(['node','qa/voice-browser.cjs'],env={**env,'WIZARD_APP_CLIENT':str(root/'shell-web/core/app-client.js')})
 run(['node','qa/consolidated-browser.cjs'],env=env)
 archive=root/('wizard-search-'+sha+'-amd64.tar')
 run(['docker','save','-o',str(archive),image])
 image_id=subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}}'],text=True).strip()
 manifest={'source_sha':sha,'image':image,'image_id':image_id,'image_archive':archive.name,'image_archive_sha256':hashlib.file_digest(archive.open('rb'),'sha256').hexdigest(),'tests':'passed','production_activated':False,'shell_visual_review':'required','live_private_provider_proof':'private-proxy-proof.json (separate real network proof, 699 ms first delta; replay only for browser AI UI)'}
 (root/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))
finally:
 if server:server.terminate();server.wait(timeout=10)
 subprocess.run(compose+['down','--volumes','--remove-orphans'],check=False)
