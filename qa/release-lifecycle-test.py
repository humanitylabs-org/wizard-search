#!/usr/bin/env python3
"""No mutation: bind release methods to pinned Runtipi AST and exercise recreate races."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_lifecycle', ROOT/'ops/release_lifecycle.py')
assert spec and spec.loader
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
PINNED = Path(os.environ.get('QA_RUNTIPI_SOURCE', '/home/telos/.local/share/wizard-search-releases/consolidated-20261105/wam-api-v2/975fcbd37a84f0a79bd593db317f27b500a2cac6/wam/runtipi.py'))
IMAGE = 'sha256:'+'a'*64
REV = 'b'*40

class Contracts(unittest.TestCase):
    def test_only_real_methods_and_signatures(self):
        tree = ast.parse(PINNED.read_text())
        methods = {n.name:n for c in tree.body if isinstance(c,ast.ClassDef) and c.name=='Runtipi'
                   for n in c.body if isinstance(n,ast.FunctionDef)}
        calls = [n for path in [ROOT/'ops/parent-release.py',ROOT/'ops/release_lifecycle.py']
                 for n in ast.walk(ast.parse(path.read_text())) if isinstance(n,ast.Call)
                 and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name)
                 and n.func.value.id=='rt']
        self.assertTrue(calls)
        for call in calls:
            self.assertIn(call.func.attr,methods)
            args = methods[call.func.attr].args
            names = [a.arg for a in args.args[1:]]
            self.assertTrue({k.arg for k in call.keywords} <= set(names))
            self.assertLessEqual(len(call.args),len(names))
        self.assertNotIn('call',methods); self.assertNotIn('wait',methods)
        swagger = json.loads((PINNED.parents[1]/'packages/backend/src/swagger.json').read_text())
        for action in ['update','update-config']:
            self.assertIn('patch',swagger['paths']['/api/app-lifecycle/{urn}/'+action])
        fields = swagger['components']['schemas']['AppFormBody']['properties']
        self.assertTrue({'port','skipEnv','skipRun','skipPull','maxBackups'} <= fields.keys())

    def exercise(self, mode):
        with tempfile.TemporaryDirectory() as td:
            receipt=Path(td)/'receipt.json'; now=[0]; calls=[]; observations=[0]
            class RT:
                def req(self, method, path, body, timeout):
                    calls.append((method,path,body)); assert json.loads(receipt.read_text())['state']=='submission_started'
                    if mode=='ambiguous': raise OSError('connection lost after submit')
                    return {'requestId':'synthetic-request'}
                def wait_status(self, urn, statuses, timeout):
                    assert json.loads(receipt.read_text())['requestId']=='synthetic-request'
                    return 'running'  # Deliberately reports old running before recreate.
            def inspect(_):
                observations[0]+=1
                if observations[0]==1:
                    return {'Image':'sha256:'+'c'*64,'State':{'Running':True},'Config':{'Labels':{'org.opencontainers.image.revision':REV}}}
                if observations[0]==2: raise subprocess.CalledProcessError(1,['docker','inspect'])
                return {'Image':IMAGE,'State':{'Running':True},'Config':{'Labels':{'org.opencontainers.image.revision':REV}}}
            kwargs=dict(rt=RT(),urn='search-preview:wizardapps',action='update',body={'performBackup':True},
                        receipt=receipt,expected_image=IMAGE,expected_revision=REV,container='synthetic',health_url='http://synthetic',
                        timeout=4,inspect=inspect,health=lambda _: {'ok':mode!='timeout'},clock=lambda:now[0],sleep=lambda n:now.__setitem__(0,now[0]+n))
            if mode=='ambiguous':
                with self.assertRaises(OSError):m.submit_and_verify(**kwargs)
            elif mode=='timeout':
                with self.assertRaises(TimeoutError):m.submit_and_verify(**kwargs)
                self.assertEqual(json.loads(receipt.read_text())['state'],'verification_timeout')
            else:
                result=m.submit_and_verify(**kwargs)
                self.assertEqual(result['state'],'verified');self.assertGreaterEqual(observations[0],3)
            self.assertEqual(len(calls),1)
            self.assertEqual(receipt.stat().st_mode & 0o777,0o600)
            with self.assertRaises(FileExistsError):m.submit_and_verify(**kwargs)
            self.assertEqual(len(calls),1)

    def test_old_running_then_missing_then_expected(self):self.exercise('success')
    def test_timeout_never_resubmits(self):self.exercise('timeout')
    def test_ambiguous_submit_never_resubmits(self):self.exercise('ambiguous')

if __name__=='__main__':unittest.main()
