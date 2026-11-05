#!/usr/bin/python3
"""PARENT ONLY. Guarded package -> verify -> cutover -> retire; one-command rollback.
Run --help and read PARENT-RELEASE.md. No action runs without --execute. Never edits apps.json.
"""
import argparse,hashlib,json,os,pathlib,runpy,secrets,shutil,subprocess,sys,urllib.request,urllib.error,time
P=pathlib.Path
p=argparse.ArgumentParser()
p.add_argument('action',choices=['package','cutover','retire-legacy','rollback'])
p.add_argument('--execute',action='store_true');p.add_argument('--release',type=P,required=True)
p.add_argument('--wam-root',type=P,required=True);p.add_argument('--routes',type=P,required=True)
p.add_argument('--runtipi',type=P,default=P.home()/'runtipi')
p.add_argument('--os-home',type=P,default=P.home()/'.wizard-os')
p.add_argument('--upstream-token-file',type=P,help='Package only: explicit regular mode-0600 approved upstream credential file; no discovery.')
a=p.parse_args();root=P(__file__).resolve().parents[1];release=a.release.resolve();backup=release/'parent-backup'
if not a.execute:print('DRY RUN:',a.action,'Search only; read ops/PARENT-RELEASE.md; add --execute after reviewing evidence.');sys.exit()
import yaml  # All runtime prerequisites must resolve before the first production write.
from image_archive_identity import archive_identity, loaded_identity
# Both the active host CLI and App Manager must propagate the manifest voice field before release.
sys.path.insert(0,str(a.wam_root));from wam.runtipi import Runtipi
rt=Runtipi.from_install(a.runtipi)
urn='search-preview:wizardapps';container='search-preview_wizardapps-search-preview-1'
repo=a.runtipi/'repos/wizardapps/apps/search-preview';installed=a.runtipi/'apps/wizardapps/search-preview'
service=P.home()/'.config/systemd/user/wizard-search-private-proxy.service'
def run(argv,**kw):return subprocess.run(argv,check=True,**kw)
def call(argv,**kw):return subprocess.check_output(argv,**kw)
def obj(url):
 # A successful systemd restart can precede its listener. Retry only read-only
 # connection-refused observations, never lifecycle submissions or mutations.
 for attempt in range(30):
  try:return json.load(urllib.request.urlopen(url,timeout=120))
  except urllib.error.URLError as exc:
   if not isinstance(exc.reason,ConnectionRefusedError) or attempt==29:raise
   time.sleep(.1)
 raise AssertionError('Unreachable metadata retry exhaustion')
def write(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,indent=2)+'\n')
def refresh():
 env={**os.environ,'PYTHONPATH':str(a.wam_root),'PYTHONDONTWRITEBYTECODE':'1','WIZARD_OS_HOME':str(a.os_home),'RUNTIPI_ROOT':str(a.runtipi)}
 run(['/usr/bin/python3','-m','wam','apps','--json'],cwd=a.wam_root,env=env,stdout=subprocess.DEVNULL)
def lifecycle(action,body,expected_image,expected_revision):
 from release_lifecycle import submit_and_verify
 return submit_and_verify(rt,urn,action,body,release/('lifecycle-'+action+'.json'),
                          expected_image,expected_revision,container,'http://127.0.0.1:19289/api/health',timeout=90)
def form(row):
 cfg=row['config'];cfg=json.loads(cfg) if isinstance(cfg,str) else dict(cfg or {})
 for k in ['port','exposed','exposedLocal','openPort','domain','isVisibleOnGuestDashboard','enableAuth','localSubdomain','maxBackups']:
  if row.get(k) is not None:cfg[k]=row[k]
 cfg.update(skipEnv=False,skipPull=True,skipRun=False,forcePull=False)
 return cfg
if a.action=='package':
 # Validate the explicit credential before the first production write. No env/account discovery.
 if a.upstream_token_file is None:p.error('package requires --upstream-token-file')
 try:upstream_token=runpy.run_path(str(root/'ops/private-proxy-bridge.py'))['read_upstream_token'](a.upstream_token_file)
 except ValueError as error:p.error(str(error))
 manifest=json.loads((release/'artifact-manifest.json').read_text());sha=manifest['source_sha']
 assert call(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()==sha and not call(['git','-C',str(root),'status','--porcelain'],text=True).strip(),'Use the exact clean pushed source checkout.'
 assert manifest['tests']=='passed' and manifest['production_activated'] is False
 # Do not accept an inherited voice-routing regression merely because the UI admits voice.
 assert '"receives_voice_input": w.get("receives_voice_input") is True' in (a.wam_root/'wam/registry.py').read_text(), 'Parent must ship the reviewed registry voice projection patch first.'
 image_sha=manifest.get('image_source_sha',sha)
 if image_sha!=sha:
  assert manifest.get('runtime_bytes_identical') is True
  hashes=manifest['runtime_file_sha256']
  expected={'app/Dockerfile','.dockerignore','server.py','setup.json','openapi.json','SETUP.md','runtipi/docker-compose.yml'}|{str(f.relative_to(root)) for f in (root/'web').rglob('*') if f.is_file()}
  assert set(hashes)==expected and all(hashlib.sha256((root/name).read_bytes()).hexdigest()==value for name,value in hashes.items()),'Reused image runtime inputs differ from candidate'
 assert not backup.exists(),'Backup already exists; inspect it or use rollback. Never overwrite rollback material.'
 archive=release/manifest['image_archive'];graph=archive_identity(archive,manifest)
 live=json.loads(call(['docker','inspect',container]))[0]
 assert live['Config']['Labels']['org.opencontainers.image.revision']=='e429987349b87d0c6d4973fb482c604765e2434b','Serving package moved; rebase/reverify.'
 row=rt.app(urn)['app'];assert row['status']=='running'
 backup.mkdir(parents=True,mode=0o700);os.chmod(backup,0o700)
 write(backup/'lifecycle-row.json',row);os.chmod(backup/'lifecycle-row.json',0o600)
 paths=[repo,installed,a.os_home/'routes.json',a.os_home/'launcher.json',a.routes,a.runtipi/'app-data/wizardapps/search-preview/app.env',service,a.runtipi/'user-config/wizardapps/search-preview']
 table=[]
 for i,target in enumerate(paths):
  dest=backup/str(i);table.append({'target':str(target),'copy':str(dest),'exists':target.exists(),'directory':target.is_dir()})
  if target.is_dir():shutil.copytree(target,dest)
  elif target.exists():shutil.copy2(target,dest)
 write(backup/'files.json',table)
 with (backup/'search-data.tar').open('wb') as f:run(['docker','exec',container,'tar','-C','/data','-cf','-','.'],stdout=f)
 os.chmod(backup/'search-data.tar',0o600)
 run(['docker','load','-i',str(archive)],stdout=subprocess.DEVNULL)
 img=json.loads(call(['docker','image','inspect',manifest['image']]))[0]
 identity=loaded_identity(graph,img)
 gateway=next(v['Gateway'] for k,v in live['NetworkSettings']['Networks'].items() if 'search-preview' in k and v.get('Gateway'))
 token=secrets.token_urlsafe(48);tokenfile=backup/'proxy-token';tokenfile.write_text(token);os.chmod(tokenfile,0o600)
 upstream_tokenfile=backup/'upstream-token'
 with os.fdopen(os.open(upstream_tokenfile,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:f.write(upstream_token)
 shutil.copy2(root/'ops/private-proxy-bridge.py',backup/'private-proxy-bridge.py')
 # Search-only random token, not the Tinfoil API key or a private agent credential.
 run(['docker','exec','-i',container,'python3','-c','import sys,os;from pathlib import Path;p=Path("/data/private-proxy-token");p.write_bytes(sys.stdin.buffer.read());os.chmod(p,0o600)'],input=token.encode())
 service.parent.mkdir(parents=True,exist_ok=True)
 service.write_text('[Unit]\nDescription=Search-only bridge to approved private loopback inference\nAfter=network.target\n[Service]\nExecStart=/usr/bin/python3 '+str(backup/'private-proxy-bridge.py')+' --bind '+gateway+' --token-file '+str(tokenfile)+' --upstream-token-file '+str(upstream_tokenfile)+' --upstream http://127.0.0.1:3301/v1/chat/completions\nRestart=on-failure\nNoNewPrivileges=true\nPrivateTmp=true\nProtectSystem=strict\nProtectHome=read-only\n[Install]\nWantedBy=default.target\n')
 run(['systemctl','--user','daemon-reload']);run(['systemctl','--user','enable','--now',service.name])

 compose=yaml.safe_load((repo/'docker-compose.yml').read_text());svc=compose['services']['search-preview'];svc.pop('build',None);svc['image']=manifest['image'];svc['pull_policy']='never'
 svc['environment'].update(TINFOIL_PROXY_URL='http://'+gateway+':19332/v1/chat/completions',TINFOIL_API_KEY='',TINFOIL_API_KEY_FILE='/data/private-proxy-token',WIZARD_SEARCH_MODEL='gpt-oss-120b')
 # Preserve project/service names, existing Search data-volume binding, SearXNG sidecar and prior settings.
 (repo/'docker-compose.yml').write_text(yaml.safe_dump(compose,sort_keys=False))
 wizard=(root/'wizard.md').read_text().replace('id: wizard-search\n','id: search-preview\n');(repo/'wizard.md').write_text(wizard)
 config=json.loads((root/'runtipi/config.json').read_text());config['id']='search-preview';(repo/'config.json').write_text(json.dumps(config,indent=2)+'\n')
 from wam.builder import source_hash
 source=json.loads((repo/'.wizard-source').read_text());source.update(upstream_repo='humanitylabs-org/wizard-search',upstream_commit=sha,source_hash=source_hash(root));write(repo/'.wizard-source',source);(repo/'.wizard-commit').write_text(sha+'\n')
 lifecycle('update',{'performBackup':True},identity['effective_image_id'],image_sha);refresh()
 assert obj('http://127.0.0.1:19289/api/overview-provider')['model']=='gpt-oss-120b'
 provider=obj('http://127.0.0.1:19289/api/config');assert provider['capabilities']['overview'] and provider['capabilities']['web'] and provider['capabilities']['images']
 write(release/'parent-package-verification.json',{'sha':sha,'candidate_port':19289,'private_proxy_bridge':True,'model':'gpt-oss-120b','cutover':False,'image_identity':identity})
 print('Package updated, legacy root untouched. Verify real private stream plus phone/desktop/two-skin screenshots, then write parent-acceptance.json {"verified":true,"sha":"'+sha+'"}.')
elif a.action=='cutover':
 manifest=json.loads((release/'artifact-manifest.json').read_text());accept=json.loads((release/'parent-acceptance.json').read_text());assert accept=={'verified':True,'sha':manifest['source_sha']}
 assert backup.exists();assert obj('http://127.0.0.1:19289/api/config')['capabilities']['overview']
 # Update the supported owner routing source, then regenerate registry; never fake apps.json.
 routes=json.loads((a.os_home/'routes.json').read_text());routes['search-preview']={'view':'/wizard-search/'};write(a.os_home/'routes.json',routes)
 gateway=json.loads(a.routes.read_text());gateway['routes']['/wizard-search']={'target':'http://127.0.0.1:19289/','override':'Packaged Search; legacy backend retained for rollback'}
 gateway['routes']['/wizard-search/preview']={'target':'http://127.0.0.1:19289/','override':'Search compatibility alias; existing browser storage scope retained'};write(a.routes,gateway)
 refresh();run(['systemctl','--user','restart','private-app-route-adapter.service'])
 apps=obj('http://127.0.0.1:8923/wizard/v1/apps')['apps'];survivor=next(x for x in apps if x['id']=='search-preview');assert survivor['receives_voice_input'] is True and survivor['name']=='Search'
 launcher=json.loads((a.os_home/'launcher.json').read_text());launcher['links']=[x for x in launcher.get('links',[]) if x.get('id')!='wizard-search'];write(a.os_home/'launcher.json',launcher)
 apps=obj('http://127.0.0.1:8923/wizard/v1/apps')['apps'];assert len([x for x in apps if x.get('id') in ('wizard-search','search-preview')])==1
 assert obj('http://127.0.0.1:9191/wizard-search/api/overview-provider')['model']=='gpt-oss-120b'
 write(release/'parent-cutover.json',{'verified':True,'sha':manifest['source_sha']});print('One launcher Search verified. Legacy service remains available until retire-legacy.')
elif a.action=='retire-legacy':
 manifest=json.loads((release/'artifact-manifest.json').read_text())
 assert json.loads((release/'parent-cutover.json').read_text())=={'verified':True,'sha':manifest['source_sha']}
 package=json.loads((release/'parent-package-verification.json').read_text());assert package['sha']==manifest['source_sha']
 graph=archive_identity(release/manifest['image_archive'],manifest)
 running_id=json.loads(call(['docker','inspect',container]))[0]['Image']
 identity=loaded_identity(graph,json.loads(call(['docker','image','inspect',running_id]))[0])
 assert identity==package['image_identity'] and running_id==identity['effective_image_id']
 run(['systemctl','--user','stop','wizard-search.service']);assert subprocess.run(['systemctl','--user','is-active','wizard-search.service'],capture_output=True,text=True).stdout.strip()!='active'
else:
 assert backup.exists()
 subprocess.run(['systemctl','--user','disable','--now',service.name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
 for item in json.loads((backup/'files.json').read_text()):
  target=P(item['target']);src=P(item['copy'])
  if item['exists']:
   if item['directory']:
    if target.exists():shutil.rmtree(target)
    shutil.copytree(src,target)
   else:target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
  elif target.is_dir():shutil.rmtree(target)
  else:target.unlink(missing_ok=True)

 run(['systemctl','--user','daemon-reload'])
 old_compose=yaml.safe_load((repo/'docker-compose.yml').read_text())
 old_image=old_compose['services']['search-preview']['image']
 old_id=json.loads(call(['docker','image','inspect',old_image]))[0]['Id']
 lifecycle('update-config',form(json.loads((backup/'lifecycle-row.json').read_text())),old_id,'e429987349b87d0c6d4973fb482c604765e2434b')
 run(['docker','exec',container,'rm','-f','/data/private-proxy-token'])
 refresh();run(['systemctl','--user','restart','private-app-route-adapter.service']);run(['systemctl','--user','start','wizard-search.service'])
 actual=json.loads(call(['docker','inspect',container]))[0]['Config']['Labels']['org.opencontainers.image.revision'];assert actual=='e429987349b87d0c6d4973fb482c604765e2434b'
 assert obj('http://127.0.0.1:9191/wizard-search/api/health')['ok'] is True
 print('Original package, routes, launcher and legacy service restored. Search browser site data was never touched.')
