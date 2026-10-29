import importlib.util
import json
import os
from pathlib import Path
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('search', ROOT / 'server.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class SearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = patch.multiple(s, SEARXNG_URL='', SOCKS='', LLM_URL='', TINFOIL_KEY='', BD_TOKEN='', FC_CLOUD_KEY='', FIRECRAWL_URL='', PREFIX='')
        cls.env.start()
        cls.server = s.ThreadingHTTPServer(('127.0.0.1', 0), s.H)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.env.stop()

    def request(self, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, headers=headers or {})
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            payload = response.read()
            return response.status, json.loads(payload) if payload and 'json' in response.headers.get('Content-Type', '') else payload

    def test_clean_install(self):
        code, data = self.request('/api/health')
        self.assertEqual(code, 200)
        self.assertEqual(data['state'], 'setup_required')
        self.assertFalse(any(data['capabilities'].values()))
        for route in ['web', 'images', 'overview', 'overview-stream']:
            code, data = self.request('/api/' + route + '?q=public+test')
            self.assertEqual((code, data['error']), (503, 'setup_required'))

    def test_configuration_no_secrets(self):
        # A paid key alone is not approval: free-only (default) keeps it unusable and says so.
        with patch.object(s, 'FC_CLOUD_KEY', 'dummy-secret'):
            code, data = self.request('/api/config')
            self.assertEqual(data['state'], 'setup_required')
            self.assertEqual(data['policy']['blocked_configured'], ['firecrawl_cloud'])
            self.assertNotIn('dummy-secret', json.dumps(data))
        with patch.object(s, 'FC_CLOUD_KEY', 'dummy-secret'), patch.object(s, 'POLICY_MODE', 'legacy-race'):
            code, data = self.request('/api/config')
            self.assertEqual(data['state'], 'configured')
            self.assertTrue(data['capabilities']['web'])
            self.assertFalse(data['capabilities']['images'])
            self.assertNotIn('dummy-secret', json.dumps(data))

    def test_searxng_default_web_and_images(self):
        fake = {'results': [
            {'url': 'https://example.org/a', 'title': 'Alpha receipt printer', 'content': 'receipt printer alpha',
             'img_src': 'https://img.example.org/a.jpg', 'thumbnail_src': '//img.example.org/a_t.jpg', 'resolution': '800 x 600'},
            {'url': 'https://example.org/b', 'title': 'Beta receipt printer', 'content': 'receipt printer beta',
             'img_src': 'https://img.example.org/b.jpg'},
            {'url': 'http:///videos/riverview/x', 'title': 'hostless'},
            {'url': 'javascript:alert(1)', 'title': 'bad'}]}

        class R:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps(fake).encode()
        seen = []
        real_open = urllib.request.urlopen
        def fake_open(req, timeout=0):
            url = getattr(req, 'full_url', req)
            if urllib.parse.urlsplit(str(url)).hostname != 'searx.invalid':
                return real_open(req, timeout=timeout)
            seen.append(url)
            return R()
        with patch.object(s, 'SEARXNG_URL', 'http://searx.invalid:8080'), patch.object(s.urllib.request, 'urlopen', fake_open):
            code, data = self.request('/api/config')
            self.assertEqual(data['state'], 'configured')
            self.assertTrue(data['capabilities']['web'] and data['capabilities']['images'])
            self.assertFalse(data['capabilities']['overview'])
            code, data = self.request('/api/web?q=receipt+printer+searx+test')
            self.assertEqual((code, data['source']), (200, 'searxng'))
            self.assertEqual([r['url'] for r in data['results']], ['https://example.org/a', 'https://example.org/b'])
            code, data = self.request('/api/images?q=receipt+printer+searx+images')
            self.assertEqual((code, data['source']), (200, 'searxng'))
            self.assertEqual(data['images'][0]['thumb'], 'https://img.example.org/a_t.jpg')
            self.assertEqual((data['images'][0]['w'], data['images'][0]['h']), (800, 600))
            self.assertTrue(seen)
            for u in seen:
                parts = urllib.parse.urlsplit(u)
                self.assertEqual((parts.hostname, parts.port, parts.path), ('searx.invalid', 8080, '/search'))
                self.assertEqual(urllib.parse.parse_qs(parts.query)['format'], ['json'])

    def test_tinfoil_app_overview_switch(self):
        import tempfile
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        good = 'x' * 40
        class Fake(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _j(self, code, obj):
                b = json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(b)
            def do_GET(self):
                if self.path == '/api/connection': return self._j(200, {'status': 'connected', 'credentialStored': True})
                if self.path == '/v1/models':
                    if self.headers.get('Authorization') != 'Bearer ' + good: return self._j(401, {'error': 'no'})
                    return self._j(200, {'data': [{'id': 'gpt-oss-120b'}, {'id': 'kimi-k3'}]})
                self._j(404, {})
        fake = ThreadingHTTPServer(('127.0.0.1', 0), Fake); threading.Thread(target=fake.serve_forever, daemon=True).start()
        tmp = tempfile.TemporaryDirectory()
        try:
            with patch.object(s, 'TINFOIL_APP', 'http://127.0.0.1:%d' % fake.server_port), patch.object(s, 'DATA_DIR', Path(tmp.name)), patch.object(s, 'SEARXNG_URL', 'http://searx.invalid:8080'):
                s.TINFOIL_PROBE['at'] = 0
                _, d = self.request('/api/overview-provider')
                self.assertEqual((d['mode'], d['tinfoil']), ('off', {'installed': True, 'connected': True}))
                self.assertFalse(self.request('/api/config')[1]['capabilities']['overview'])
                h = {'Content-Type': 'application/json', 'X-Wizard-Request': '1'}
                self.assertEqual(self.request('/api/overview-provider', {'provider': 'tinfoil', 'token': good}, {'Content-Type': 'application/json'})[0], 403)
                self.assertEqual(self.request('/api/overview-provider', {'provider': 'tinfoil', 'token': 'y' * 40}, h)[0], 502)
                code, d = self.request('/api/overview-provider', {'provider': 'tinfoil', 'token': good, 'models': ['kimi-k3', 'evil'], 'recommended': ['kimi-k3']}, h)
                self.assertEqual((code, d['mode'], d['model']), (200, 'tinfoil-app', 'kimi-k3'))
                self.assertEqual((Path(tmp.name) / s.LINK_FILE).stat().st_mode & 0o777, 0o600)
                self.assertTrue(self.request('/api/config')[1]['capabilities']['overview'])
                self.assertNotIn(good, json.dumps(self.request('/api/config')[1]))
                cfg = s.llm(); self.assertEqual(cfg['url'], 'http://127.0.0.1:%d/v1/chat/completions' % fake.server_port)
                code, d = self.request('/api/overview-provider', {'provider': 'off'}, h)
                self.assertEqual((code, d['mode']), (200, 'off'))
                self.assertIsNone(s.llm())
        finally:
            fake.shutdown(); fake.server_close(); tmp.cleanup(); s.TINFOIL_PROBE['at'] = 0

    def test_provider_failure_not_empty_success(self):
        with patch.object(s, 'FIRECRAWL_URL', 'http://127.0.0.1:1/v2/search'), \
                patch.object(s, 'POLICY_MODE', 'approved-upgrades'), patch.object(s, 'POLICY_APPROVED', 'firecrawl_router'):
            code, data = self.request('/api/web?q=provider-failure-test')
            self.assertEqual(code, 502)
            self.assertIn('error', data)

    def test_mcp(self):
        code, data = self.request('/mcp', {'jsonrpc':'2.0','id':1,'method':'initialize'})
        self.assertEqual(code, 200)
        self.assertEqual(data['result']['serverInfo']['name'], 'wizard-search')
        _, data = self.request('/mcp', {'jsonrpc':'2.0','id':2,'method':'tools/list'})
        self.assertEqual([t['name'] for t in data['result']['tools']], ['search_status', 'search_web', 'search_images', 'search_overview'])
        _, data = self.request('/mcp', {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'search_web','arguments':{'q':'test'}}})
        self.assertTrue(data['result']['isError'])
        self.assertEqual(json.loads(data['result']['content'][0]['text'])['error'], 'setup_required')

    def test_no_public_source_files(self):
        for path in ['/server.py','/.git/config','/.env','/../server.py','/%2e%2e/server.py','/tests/test_search.py']:
            self.assertEqual(self.request(path)[0], 404, path)
        for path in ['/SETUP.md','/setup.json','/openapi.json']:
            self.assertEqual(self.request(path)[0], 200, path)

    def test_cross_origin_rejected(self):
        self.assertEqual(self.request('/mcp', {'id':1,'method':'tools/list'}, {'Origin':'https://untrusted.example'})[0], 403)

    def test_parser_fixture_is_not_live_evidence(self):
        rows = s.parse_bing_images('<a m="{&quot;murl&quot;:&quot;https://example.org/a.png&quot;,&quot;t&quot;:&quot;A&quot;}"></a>')
        self.assertEqual(rows[0]['full'], 'https://example.org/a.png')
        self.assertFalse(s.public_host('http://127.0.0.1/test'))


if __name__ == '__main__':
    unittest.main()
