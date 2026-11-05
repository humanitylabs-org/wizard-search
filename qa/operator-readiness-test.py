"""The real operator retries only bounded metadata connection refusals."""
import ast, io, json, pathlib, types, unittest, urllib.error
from unittest.mock import Mock
source=pathlib.Path(__file__).resolve().parents[1]/'ops/parent-release.py'
node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='obj')
code=compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec')
def load(effects):
    request=types.SimpleNamespace(urlopen=Mock(side_effect=effects))
    sleep=Mock();ns={'json':json,'urllib':types.SimpleNamespace(request=request,error=urllib.error),'time':types.SimpleNamespace(sleep=sleep)}
    exec(code,ns);return ns['obj'],request.urlopen,sleep
class Readiness(unittest.TestCase):
    def test_listener_binds_after_restart(self):
        f,request,sleep=load([urllib.error.URLError(ConnectionRefusedError()),urllib.error.URLError(ConnectionRefusedError()),io.StringIO('{"ok":true}')])
        self.assertEqual(f('http://local/metadata'),{'ok':True});self.assertEqual(request.call_count,3);self.assertEqual(sleep.call_count,2)
    def test_bound(self):
        f,request,sleep=load([urllib.error.URLError(ConnectionRefusedError())]*30)
        with self.assertRaises(urllib.error.URLError):f('http://local/metadata')
        self.assertEqual(request.call_count,30);self.assertEqual(sleep.call_count,29)
    def test_http_and_dns_fail_without_retry(self):
        for exc in [urllib.error.HTTPError('http://local',401,'unauthorized',{},None),urllib.error.URLError('DNS failure')]:
            f,request,sleep=load([exc])
            with self.assertRaises(urllib.error.URLError):f('http://local/metadata')
            self.assertEqual(request.call_count,1);sleep.assert_not_called()
if __name__=='__main__':unittest.main()
