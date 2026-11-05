#!/usr/bin/env python3
"""Read-only installed package checks; writes only the explicitly requested local receipt.

This is phase recovery, NOT lifecycle execution and NOT app/visual acceptance.
"""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ops'))
from image_archive_identity import archive_identity, loaded_identity
from release_lifecycle import protected_write


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--release',type=Path,required=True)
    p.add_argument('--wam-root',type=Path,required=True)
    p.add_argument('--lifecycle-request-id',required=True)
    p.add_argument('--receipt',type=Path,required=True)
    a=p.parse_args();release=a.release.resolve()
    assert not a.receipt.exists(),'Refuse replacing an existing phase receipt'
    manifest=json.loads((release/'artifact-manifest.json').read_text())
    graph=archive_identity(release/manifest['image_archive'],manifest)
    def call(argv):return subprocess.check_output(argv,timeout=30).decode().strip()
    image=json.loads(call(['docker','image','inspect',manifest['image']]))[0]
    identity=loaded_identity(graph,image)
    container='search-preview_wizardapps-search-preview-1'
    # No container environment/mount inspection; public image/revision/lifecycle fields only.
    public=json.loads(call(['docker','inspect','--format',
        '{"image":{{json .Image}},"running":{{json .State.Running}},"revision":{{json (index .Config.Labels "org.opencontainers.image.revision")}}}',container]))
    assert public=={'image':identity['effective_image_id'],'running':True,'revision':manifest['image_source_sha']}
    expected=manifest['runtime_file_sha256']
    assert expected and all(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==sha for path,sha in expected.items())
    # Materialize EXACT original package source in scratch, not the dirty operator tree.
    source_bytes=subprocess.check_output(['git','-C',str(ROOT),'archive',manifest['source_sha']],timeout=30)
    sys.path.insert(0,str(a.wam_root))
    from wam.builder import source_hash
    with tempfile.TemporaryDirectory() as td:
        with tarfile.open(fileobj=io.BytesIO(source_bytes)) as tar:tar.extractall(td,filter='data')
        exact_source_hash=source_hash(Path(td))
    installed=Path('/home/telos/runtipi/apps/wizardapps/search-preview')
    metadata=json.loads((installed/'.wizard-source').read_text())
    assert metadata['upstream_commit']==manifest['source_sha']
    assert metadata['source_hash']==exact_source_hash
    def obj(path):
        with urllib.request.urlopen('http://127.0.0.1:19289'+path,timeout=10) as r:return json.load(r)
    health=obj('/api/health');cfg=obj('/api/config');provider=obj('/api/overview-provider')
    assert health['ok'] is True and health['revision']==manifest['image_source_sha']
    assert cfg['providers']=={'searxng':True,'socks':False,'firecrawl_cloud':False,'brightdata':False,'firecrawl_router':False,'tinfoil':True}
    assert all(cfg['capabilities'][k] is True for k in ('web','images','overview'))
    assert provider=={'mode':'proxy','model':'gpt-oss-120b','tinfoil':{'installed':True,'connected':True}}
    # Last exact-image sample immediately before the phase marker; never claim app acceptance.
    assert json.loads(call(['docker','inspect','--format',
        '{"image":{{json .Image}},"running":{{json .State.Running}},"revision":{{json (index .Config.Labels "org.opencontainers.image.revision")}}}',container]))==public
    result={'sha':manifest['source_sha'],'operator_sha':call(['git','-C',str(ROOT),'rev-parse','HEAD']),
            'qa_source_sha':manifest['qa_source_sha'],'image_source_sha':manifest['image_source_sha'],
            'phase':'package manually completed by parent; independently read back',
            'lifecycle_request_id':a.lifecycle_request_id,'lifecycle_mutations_by_this_verifier':0,
            'candidate_port':19289,'cutover':False,'image_identity':identity,'running_candidate':public,
            'source_hash':exact_source_hash,'runtime_file_count':len(expected),
            'configuration':cfg,'overview_provider':provider,
            'provider_reachability':'See evidence/installed-live-api.json; configuration is NOT inference proof',
            'acceptance':False,'visual_acceptance':False,'voice_admission':'not verified; known live registry false'}
    protected_write(a.receipt,result)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
