import importlib.util
import json
import os
import tempfile
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
        with patch.object(s, 'FC_CLOUD_KEY', 'dummy-secret'):
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

    def test_searxng_long_question_not_rejected(self):
        # wizard-os#616: a full question has many content words; SearXNG results only mention a few of them.
        fake = {'results': [
            {'url': 'https://example.org/mb', 'title': 'Markov blanket - Wikipedia', 'content': 'A Markov blanket separates a system from its environment.'},
            {'url': 'https://example.org/fep', 'title': 'Free energy principle', 'content': 'Simple systems such as cells have a Markov blanket.'},
            {'url': 'https://example.org/c', 'title': 'Do bacteria have Markov blankets?', 'content': 'Single cells as the simplest case.'}]}

        class R:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps(fake).encode()
        real_open = urllib.request.urlopen
        def fake_open(req, timeout=0):
            url = getattr(req, 'full_url', req)
            if urllib.parse.urlsplit(str(url)).hostname != 'searx.invalid':
                return real_open(req, timeout=timeout)
            return R()
        q = 'What are the most primitive systems that exert or exhibit a Markov blanket?'
        self.assertFalse(s._relevant(q, [{'title': x['title'], 'snippet': x['content'], 'url': x['url']} for x in fake['results']]))
        with patch.object(s, 'SEARXNG_URL', 'http://searx.invalid:8080'), patch.object(s.urllib.request, 'urlopen', fake_open):
            code, data = self.request('/api/web?' + urllib.parse.urlencode({'q': q}))
            self.assertEqual((code, data.get('source')), (200, 'searxng'), data)
            self.assertEqual(len(data['results']), 3)

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

    def test_search_bar_mic_is_on_for_everyone_and_its_switch_is_gone(self):
        # Issue #29 approved: no search-bar-mic switch any more, and a saved value for it is cleared at start.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'WIZARD_SWITCHES_DIR': tmp}):
            self.assertNotIn('search-bar-mic', [x['id'] for x in s.switches_doc()['switches']])
            self.assertNotIn('search-bar-mic', self.request('/api/config')[1]['switches'])
            f = os.path.join(tmp, 'switches.json')
            with open(f, 'w') as fh:
                json.dump({'search-bar-mic': False, 'other': True}, fh)
            s._sw_forget_retired()
            with open(f) as fh:
                self.assertEqual(json.load(fh), {'other': True})
            s._sw_forget_retired()  # nothing left to clear: no error, file unchanged
            with open(f) as fh:
                self.assertEqual(json.load(fh), {'other': True})

    def test_fast_open_is_on_for_everyone_and_its_switch_is_gone(self):
        # Issue #42 approved: no fast-open switch any more, and a saved value for it is cleared at start.
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'WIZARD_SWITCHES_DIR': tmp}):
            self.assertNotIn('fast-open', [x['id'] for x in s.switches_doc()['switches']])
            self.assertNotIn('fast-open', self.request('/api/config')[1]['switches'])
            f = os.path.join(tmp, 'switches.json')
            with open(f, 'w') as fh:
                json.dump({'fast-open': False, 'other': True}, fh)
            s._sw_forget_retired()
            with open(f) as fh:
                self.assertEqual(json.load(fh), {'other': True})
            with urllib.request.urlopen(self.base + '/') as r:  # a saved "off" never brings the plain page back
                self.assertIn('src="app.js?v=%s"' % s.asset_tag('app.js'), r.read().decode())
        app = (ROOT / 'web/app.js').read_text()
        self.assertNotIn('fast-open', app); self.assertNotIn('FAST', app); self.assertNotIn('unregister', app)
        self.assertNotIn('data-fast-open', (ROOT / 'web/app.css').read_text())

    def test_fast_open_page_versioned_assets_and_worker(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'WIZARD_SWITCHES_DIR': tmp}):
            with urllib.request.urlopen(self.base + '/?q=x') as r:
                page = r.read().decode(); self.assertEqual(r.headers['Cache-Control'], 'no-cache')
            self.assertIn('<link rel="manifest" href="manifest.webmanifest">', page)
            tag = s.asset_tag('app.js')
            self.assertRegex(tag, r'^[0-9a-f]{12}$')
            self.assertIn('src="app.js?v=%s"' % tag, page)
            self.assertIn('href="app.css?v=%s"' % s.asset_tag('app.css'), page)
            # The shared client stays where the gateway serves it, still first in <head> (skins paint as before).
            self.assertLess(page.index('/wizard-os-home/core/app-client.js'), page.index('<meta charset'))
            with urllib.request.urlopen(self.base + '/app.js?v=' + tag) as r:
                self.assertEqual(r.headers['Cache-Control'], 'private, max-age=31536000, immutable')
            with urllib.request.urlopen(self.base + '/app.js?v=000000000000') as r:  # a stale tag is never kept for good
                self.assertEqual(r.headers['Cache-Control'], 'no-cache')
            with urllib.request.urlopen(self.base + '/sw.js?v=0.3.15') as r:
                self.assertEqual(r.headers['Cache-Control'], 'no-cache')
                worker = r.read().decode()
            with urllib.request.urlopen(self.base + '/manifest.webmanifest') as r:
                man = json.loads(r.read()); self.assertEqual(r.headers['Content-Type'], 'application/manifest+json')
            self.assertEqual(man['background_color'], '#0b0b14'); self.assertEqual(man['scope'], './')
            # Worker: own cache prefix and scope only; searches, images and settings stay network-only.
            self.assertIn("PREFIX = 'wizard-search-shell-'", worker)
            self.assertIn('api\\/|thumb\\/|img\\/', worker)
            app = (ROOT / 'web/app.js').read_text()
            self.assertIn("sw.register(`${BASE}sw.js?v=${SEARCH_VERSION}`", app)
            # The worker's cache follows the release: its version is the one Search reports.
            reported = app.split("WizardApp.ready({ name: 'Search', version: '")[1].split("'")[0]
            self.assertIn("const SEARCH_VERSION = '%s'" % reported, app)

    def test_bottom_search_bar_is_on_for_everyone_and_its_switch_is_gone(self):
        # Issue #51 approved: no bottom-search-bar switch any more, a saved value for it is cleared at start, and a
        # saved "off" never brings the field back to the top: the phone layout is plain CSS, with no page mark.
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'WIZARD_SWITCHES_DIR': tmp}):
            self.assertNotIn('bottom-search-bar', [x['id'] for x in s.switches_doc()['switches']])
            self.assertNotIn('bottom-search-bar', self.request('/api/config')[1]['switches'])
            f = os.path.join(tmp, 'switches.json')
            with open(f, 'w') as fh:
                json.dump({'bottom-search-bar': False, 'other': True}, fh)
            s._sw_forget_retired()
            with open(f) as fh:
                self.assertEqual(json.load(fh), {'other': True})
            with urllib.request.urlopen(self.base + '/') as r:
                page = r.read().decode()
            self.assertIn('<html lang="en" data-app="wizard-search">', page)
            self.assertIn('src="app.js?v=%s"' % s.asset_tag('app.js'), page)
        app = (ROOT / 'web/app.js').read_text()
        css = (ROOT / 'web/app.css').read_text()
        self.assertNotIn('bottom-search-bar', app); self.assertNotIn('data-bottom-bar', app)
        self.assertNotIn('data-bottom-bar', css); self.assertNotIn('bottom_bar_page', (ROOT / 'server.py').read_text())
        phone = css.split('@media (max-width:820px){', 1)[1].split('\n}', 1)[0]
        self.assertIn('.bar{position:fixed', phone)
        self.assertIn('env(safe-area-inset-bottom', phone)

    def test_search_bar_mic_uses_shared_capture_and_system_speech(self):
        mic = (ROOT / 'web/search-mic.js').read_text()
        app = (ROOT / 'web/app.js').read_text()
        page = (ROOT / 'web/index.html').read_text()
        self.assertIn('id="mic"', page)
        self.assertIn('hidden><svg', page)  # hidden until the shared capture is ready
        self.assertIn('<script src="search-mic.js"></script>', page)
        self.assertNotIn('search-bar-mic', app)
        self.assertIn("mic = window.SearchMic?.register(", app)
        self.assertIn('WizardApp.capture.start', mic)
        self.assertIn('WizardApp.voice.transcribe', mic)
        self.assertIn('WizConfig.transcribe', mic)
        for forbidden in ('SpeechRecognition', 'getUserMedia', 'MediaRecorder'):
            self.assertNotIn(forbidden, mic)

    def test_provider_failure_not_empty_success(self):
        with patch.object(s, 'FIRECRAWL_URL', 'http://127.0.0.1:1/v2/search'):
            code, data = self.request('/api/web?q=provider-failure-test')
            self.assertEqual(code, 502)
            self.assertIn('error', data)

    def test_mcp(self):
        code, data = self.request('/mcp', {'jsonrpc':'2.0','id':1,'method':'initialize'})
        self.assertEqual(code, 200)
        self.assertEqual(data['result']['serverInfo']['name'], 'wizard-search')
        _, data = self.request('/mcp', {'jsonrpc':'2.0','id':2,'method':'tools/list'})
        self.assertEqual(len(data['result']['tools']), 4)
        _, data = self.request('/mcp', {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'search_web','arguments':{'q':'test'}}})
        self.assertTrue(data['result']['isError'])
        self.assertEqual(json.loads(data['result']['content'][0]['text'])['error'], 'setup_required')

    def test_no_public_source_files(self):
        for path in ['/server.py','/.git/config','/.env','/../server.py','/%2e%2e/server.py','/tests/test_search.py']:
            self.assertEqual(self.request(path)[0], 404, path)
        for path in ['/SETUP.md','/setup.json','/openapi.json']:
            self.assertEqual(self.request(path)[0], 200, path)

    def raw(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def test_static_serves_web_files_byte_identical(self):
        # Issue #46: the allowlist rewrite must serve every web/ file exactly as before.
        # index.html is the one file the server rewrites (fast-open asset URLs, issue #42): compare it as rewritten.
        with patch.object(s, 'switch_on', lambda _id: False):
            page = s.fast_open_page((ROOT / 'web' / 'index.html').read_bytes())
            for f in sorted((ROOT / 'web').iterdir()):
                if f.is_file():
                    self.assertEqual(self.raw('/' + f.name), (200, page if f.name == 'index.html' else f.read_bytes()), f.name)
            self.assertEqual(self.raw('/'), (200, page))
            self.assertEqual(self.raw('/x/../app.js'), (200, (ROOT / 'web' / 'app.js').read_bytes()))

    def test_static_blocks_traversal_and_symlink_escape(self):
        # Issue #46: nothing outside web/ is ever read, also not through a symlink inside web/.
        with tempfile.TemporaryDirectory() as tmp:
            web, outside = Path(tmp, 'web'), Path(tmp, 'secret.txt')
            (web / 'sub').mkdir(parents=True)
            outside.write_text('secret')
            (web / 'ok.js').write_text('ok')
            (web / 'sub' / 'deep.css').write_text('deep')
            os.symlink(outside, web / 'leak.txt')
            os.symlink(Path(tmp), web / 'up')
            os.symlink(web / 'ok.js', web / 'alias.js')
            with patch.object(s, 'WEB_ROOT', os.path.realpath(web)), patch.object(s, 'switch_on', lambda _id: False):
                self.assertEqual(self.raw('/ok.js'), (200, b'ok'))
                self.assertEqual(self.raw('/sub/deep.css'), (200, b'deep'))
                self.assertEqual(self.raw('/alias.js'), (200, b'ok'))
                for path in ['/leak.txt', '/up/secret.txt', '/../secret.txt', '/%2e%2e/secret.txt', '/sub/../../secret.txt',
                             '/sub', '/missing.js', '//etc/passwd', '/sub/%2f..%2f..%2fsecret.txt']:
                    code, body = self.raw(path)
                    self.assertEqual(code, 404, path)
                    self.assertNotIn(b'secret', body, path)

    def test_cross_origin_rejected(self):
        self.assertEqual(self.request('/mcp', {'id':1,'method':'tools/list'}, {'Origin':'https://untrusted.example'})[0], 403)

    def test_parser_fixture_is_not_live_evidence(self):
        rows = s.parse_bing_images('<a m="{&quot;murl&quot;:&quot;https://example.org/a.png&quot;,&quot;t&quot;:&quot;A&quot;}"></a>')
        self.assertEqual(rows[0]['full'], 'https://example.org/a.png')
        self.assertFalse(s.public_host('http://127.0.0.1/test'))


if __name__ == '__main__':
    unittest.main()
