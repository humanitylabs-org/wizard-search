#!/usr/bin/env python3
"""Single queued bounded repair job; source fixtures only, no production writes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

parser=argparse.ArgumentParser()
parser.add_argument('--reuse-from',type=Path,required=True)
a=parser.parse_args()
root=Path(__file__).resolve().parents[1]
evidence=root/'evidence';evidence.mkdir(exist_ok=True)
receipt={}
for label in ('host','runtime'):
    source=root/('wam-'+label+'-source')
    sha=(source/'SOURCE_SHA').read_text().strip()
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','WIZARD_OS_HOME':str(root/'isolated-wam-home')}
    with (evidence/('wam-'+label+'-regeneration.log')).open('w') as stream:
        result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_registry_voice_input.py','-v'],cwd=source,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=20)
    receipt[label]={'source_sha':sha,'exit_code':result.returncode,'fixture_only':True}
    (evidence/'wam-regeneration.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if result.returncode:raise SystemExit(result.returncode)
# Exercise the managed CLI distribution without touching the owner's builder,
# skill discovery, registry, routes, agent runtime, or service units.
builder=root/'wam-builder-source'
identity=json.loads((root/'builder-reuse.json').read_text())
program='''import json,hashlib,pathlib,sys
from wam.builder_bundle import install
root=pathlib.Path(sys.argv[1]); identity=json.loads((root/'builder-reuse.json').read_text())
source=root/'wam-builder-source'
old=identity['baseline_file_sha256']
new={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file() and p.name!='bundle.json' and '__pycache__' not in p.parts and p.suffix!='.pyc'}
assert set(old)==set(new)
assert [k for k in new if old[k]!=new[k]]==['wam/registry.py']
result=install(root/'isolated-wam-home',source=source)
path=root/'isolated-wam-home/builder/current/wam/registry.py'
assert hashlib.sha256(path.read_bytes()).hexdigest()==new['wam/registry.py']
(root/'evidence/wam-builder-install.json').write_text(json.dumps({'fixture_only':True,'result':result,'changed_files':['wam/registry.py'],'registry_sha256':new['wam/registry.py']},indent=2)+'\\n')
'''
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(root/'wam-host-source'),'WIZARD_OS_HOME':str(root/'isolated-wam-home')}
subprocess.run([sys.executable,'-c',program,str(root)],cwd=root,env=env,check=True,timeout=20)
env['PYTHONPATH']=str(root/'isolated-wam-home/builder/current')
with (evidence/'wam-builder-regeneration.log').open('w') as stream:
    subprocess.run([sys.executable,str(root/'wam-host-source/tests/test_registry_voice_input.py'),'-v'],cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=20)
subprocess.run([sys.executable,'qa/consolidated-worker.py','--reuse-from',str(a.reuse_from.resolve())],cwd=root,check=True,timeout=780)
