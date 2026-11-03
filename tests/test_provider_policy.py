"""Provider policy: free-only by default, paid lanes only when explicitly approved.

Every outbound request is intercepted. Paid/operator fakes return *valid winning results*, so a paid lane that
ran would visibly win; the assertions therefore prove absence of paid calls, not merely absence of paid results.
Fixtures only: no real provider, key or network is used.
"""
import importlib.util
import json
import socket
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('search_policy', ROOT / 'server.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)

REAL_URLOPEN = urllib.request.urlopen
PAID_HOSTS = {'api.firecrawl.dev', 'api.brightdata.com', 'router.invalid'}
STALE = dict(FC_CLOUD_KEY='stale-fc-not-real', BD_TOKEN='stale-bd-not-real',
             FIRECRAWL_URL='http://router.invalid/v2/search', FC_CLOUD_URL='https://api.firecrawl.dev')
ROWS = [{'url': 'https://example.org/%s' % n, 'title': 'policy test result %s' % n,
         'description': 'policy test result', 'content': 'policy test result',
         'img_src': 'https://img.example.org/%s.jpg' % n} for n in 'ab']


class Resp:
    def __init__(self, obj):
        self.body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.body

    def __iter__(self):
        return iter(self.body.splitlines(True))


class Net:
    """Fake urlopen: records every destination host; searx behaviour is configurable."""

    def __init__(self, searx='ok'):
        self.searx, self.calls, self.lock = searx, [], threading.Lock()

    def paid(self):
        return [h for h in self.calls if h in PAID_HOSTS]

    def __call__(self, req, timeout=0):
        url = getattr(req, 'full_url', req)
        host = urllib.parse.urlsplit(str(url)).hostname
        if host == '127.0.0.1':  # the test's own calls to the Search server under test
            return REAL_URLOPEN(req, timeout=timeout)
        with self.lock:
            self.calls.append(host)
        if host == 'searx.invalid':
            if self.searx == 'fail':
                raise urllib.error.URLError('searx down')
            if self.searx == 'timeout':
                time.sleep(0.3)
                raise socket.timeout('timed out')
            if self.searx == 'empty':
                return Resp({'results': []})
            return Resp({'results': ROWS})
        if host == 'api.firecrawl.dev' or host == 'router.invalid':
            return Resp({'data': {'web': ROWS}})
        if host == 'api.brightdata.com':
            body = json.loads(req.data)
            if body.get('data_format') == 'parsed_light':
                return Resp({'organic': [{'link': r['url'], 'title': r['title'], 'description': 'x'} for r in ROWS]})
            return Resp(b'<a m="{&quot;murl&quot;:&quot;https://img.example.org/bd.jpg&quot;,&quot;t&quot;:&quot;BD&quot;}"></a>')
        if host == 'llm.invalid':
            return Resp({'choices': [{'message': {'content': 'Answer [1].'}}]})
        raise AssertionError('unexpected network destination: %s' % host)


class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = patch.multiple(s, SEARXNG_URL='', SOCKS='', LLM_URL='', TINFOIL_KEY='', BD_TOKEN='', FC_CLOUD_KEY='',
                                 FIRECRAWL_URL='', PREFIX='', POLICY_MODE='', POLICY_APPROVED='')
        cls.env.start()
        cls.server = s.ThreadingHTTPServer(('127.0.0.1', 0), s.H)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = 'http://127.0.0.1:%d' % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.env.stop()

    def setUp(self):
        for c in (s.WEB_CACHE, s.IMG_CACHE, s.OVR_CACHE):
            with c.lock:
                c.d.clear()
        s.DDG_COOLDOWN['until'] = 0.0

    def get(self, path):
        try:
            r = urllib.request.urlopen(self.base + path, timeout=20)
        except urllib.error.HTTPError as e:
            r = e
        with r:
            return r.status, json.loads(r.read())

    def mcp(self, name, args=None):
        req = urllib.request.Request(self.base + '/mcp', data=json.dumps(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': args or {}}}).encode())
        with urllib.request.urlopen(req, timeout=20) as r:
            res = json.loads(r.read())['result']
        return res['isError'], json.loads(res['content'][0]['text'])

    def run_with(self, net, policy='', approved='', searx=True, **extra):
        env = dict(STALE, SEARXNG_URL='http://searx.invalid:8080' if searx else '', POLICY_MODE=policy,
                   POLICY_APPROVED=approved, **extra)
        return patch.multiple(s, **env), patch.object(s.urllib.request, 'urlopen', net)

    # ---- policy parsing ---------------------------------------------------------------
    def test_default_and_invalid_policies_fail_closed(self):
        cases = [('', '', 'free-only', [], None),
                 ('free-only', '', 'free-only', [], None),
                 ('FREE-ONLY ', '', 'free-only', [], None),
                 ('free-only', 'brightdata', 'free-only', [], 'approved_upgrades_ignored_in_free_only'),
                 ('paid', '', 'free-only', [], 'invalid_policy'),
                 ('legacy', '', 'free-only', [], 'invalid_policy'),
                 ('approved-upgrades', '', 'free-only', [], 'invalid_policy'),
                 ('approved-upgrades', 'brightdata,stripe', 'free-only', [], 'invalid_policy'),
                 ('approved-upgrades', 'searxng', 'free-only', [], 'invalid_policy'),
                 ('approved-upgrades', 'brightdata, firecrawl_cloud,brightdata', 'approved-upgrades',
                  ['brightdata', 'firecrawl_cloud'], None),
                 ('legacy-race', '', 'legacy-race', list(s.UPGRADE_LANES), None)]
        for mode, approved, want_mode, want_lanes, want_err in cases:
            with self.subTest(mode=mode, approved=approved), \
                    patch.multiple(s, POLICY_MODE=mode, POLICY_APPROVED=approved):
                pol = s.provider_policy()
                self.assertEqual((pol['mode'], pol['approved_upgrades'], pol['schema']), (want_mode, want_lanes, 1))
                if want_err:
                    self.assertTrue(pol['error'] and pol['error'].startswith(want_err), pol['error'])
                else:
                    self.assertIsNone(pol['error'])

    def test_every_lane_is_classified_and_free_lanes_are_keyless(self):
        self.assertEqual(set(s.LANES), {'searxng', 'socks', 'firecrawl_cloud', 'brightdata', 'firecrawl_router'})
        self.assertEqual(set(s.UPGRADE_LANES), {'firecrawl_cloud', 'brightdata', 'firecrawl_router'})

    # ---- stale keys in free-only ------------------------------------------------------
    def test_stale_keys_free_only_web_uses_searxng_only(self):
        net = Net('ok')
        a, b = self.run_with(net)
        with a, b:
            code, d = self.get('/api/web?q=policy+test+result')
            self.assertEqual((code, d['source'], d['policy']), (200, 'searxng', 'free-only'))
            _, cfg = self.get('/api/config')
        self.assertEqual(net.paid(), [])
        self.assertEqual(sorted(cfg['policy']['blocked_configured']), ['brightdata', 'firecrawl_cloud', 'firecrawl_router'])
        self.assertFalse(any(cfg['usable'][k] for k in s.UPGRADE_LANES))
        for secret in ('stale-fc-not-real', 'stale-bd-not-real'):
            self.assertNotIn(secret, json.dumps(cfg))

    def test_free_provider_failure_timeout_empty_never_falls_back_to_paid(self):
        for mode in ('fail', 'timeout', 'empty'):
            with self.subTest(searx=mode):
                self.setUp()
                net = Net(mode)
                a, b = self.run_with(net)
                with a, b:
                    code, d = self.get('/api/web?q=policy+test+' + mode)
                    time.sleep(0.4)  # any late-starting lane would have been submitted by now
                self.assertEqual(code, 502)
                self.assertIn('error', d)
                self.assertEqual(net.paid(), [], net.calls)

    def test_free_only_mcp_failure_reports_unavailable_without_paid(self):
        net = Net('fail')
        a, b = self.run_with(net)
        with a, b:
            err, d = self.mcp('search_web', {'q': 'policy mcp failure'})
            self.assertEqual((err, d['error']), (True, 'provider_unavailable'))
            err, st = self.mcp('search_status')
            self.assertEqual((err, st['policy']['mode']), (False, 'free-only'))
        self.assertEqual(net.paid(), [])

    def test_free_only_without_free_lane_is_setup_required_and_names_blocked_lanes(self):
        net = Net()
        a, b = self.run_with(net, searx=False)
        with a, b:
            for route in ('web', 'images', 'overview', 'overview-stream'):
                code, d = self.get('/api/%s?q=policy+setup' % route)
                self.assertEqual((code, d['error']), (503, 'setup_required'), route)
            self.assertIn('not approved', d['message'])
            err, d = self.mcp('search_web', {'q': 'policy setup'})
            self.assertEqual((err, d['error']), (True, 'setup_required'))
        self.assertEqual(net.calls, [])

    def test_free_only_images_never_use_brightdata_unlocker(self):
        net = Net('fail')
        a, b = self.run_with(net)
        with a, b:
            code, d = self.get('/api/images?q=policy+images')
        self.assertEqual(code, 502)
        self.assertEqual(net.paid(), [])

    def test_policy_invalid_input_behaves_as_free_only(self):
        for mode, approved in (('approved-upgrades', 'brightdat'), ('legacy', ''), ('approved-upgrades', '')):
            with self.subTest(mode=mode, approved=approved):
                self.setUp()
                net = Net('fail')
                a, b = self.run_with(net, policy=mode, approved=approved)
                with a, b:
                    code, _ = self.get('/api/web?q=policy+invalid+' + mode)
                    _, cfg = self.get('/api/config')
                self.assertEqual(code, 502)
                self.assertEqual((cfg['policy']['mode'], bool(cfg['policy']['error'])), ('free-only', True))
                self.assertEqual(net.paid(), [])

    def test_upgrade_request_functions_refuse_before_network(self):
        net = Net()
        a, b = self.run_with(net)
        with a, b:
            for fn, arg in ((s._cloud, 'q'), (s._serp, 'q'), (s._local, 'q'),
                            (lambda p: s.bd_request(p), {'zone': 'z', 'url': 'https://example.org'})):
                with self.assertRaises(s.PolicyBlocked):
                    fn(arg)
        self.assertEqual(net.calls, [])

    # ---- explicit upgrades and legacy --------------------------------------------------
    def test_approved_upgrades_only_runs_named_lanes(self):
        net = Net('fail')
        a, b = self.run_with(net, policy='approved-upgrades', approved='firecrawl_cloud')
        with a, b:
            code, d = self.get('/api/web?q=policy+test+result+approved')
            time.sleep(0.4)
        self.assertEqual((code, d['source'], d['policy']), (200, 'cloud', 'approved-upgrades'))
        self.assertIn('api.firecrawl.dev', net.calls)
        self.assertNotIn('api.brightdata.com', net.calls)
        self.assertNotIn('router.invalid', net.calls)

    def test_approved_paid_lane_does_not_race_a_fast_free_answer(self):
        net = Net('ok')
        a, b = self.run_with(net, policy='approved-upgrades', approved='firecrawl_cloud,brightdata,firecrawl_router')
        with a, b:
            code, d = self.get('/api/web?q=policy+test+result+race')
            time.sleep(0.4)
        self.assertEqual((code, d['source']), (200, 'searxng'))
        self.assertEqual(net.paid(), [])

    def test_approved_brightdata_images_fallback(self):
        net = Net('fail')
        a, b = self.run_with(net, policy='approved-upgrades', approved='brightdata')
        with a, b:
            code, d = self.get('/api/images?q=policy+images+approved')
        self.assertEqual((code, d['source']), (200, 'bing via unlocker'))
        self.assertIn('api.brightdata.com', net.calls)

    def test_legacy_race_explicit_mode_keeps_old_fallbacks(self):
        net = Net('fail')
        a, b = self.run_with(net, policy='legacy-race')
        with a, b:
            code, d = self.get('/api/web?q=policy+test+result+legacy')
            _, cfg = self.get('/api/config')
        self.assertEqual((code, d['source'], d['policy']), (200, 'cloud', 'legacy-race'))
        self.assertEqual(cfg['policy']['blocked_configured'], [])

    # ---- overview inference stays a separate consent ---------------------------------
    def test_overview_inference_is_separate_from_search_spend(self):
        net = Net('ok')
        a, b = self.run_with(net, LLM_URL='http://llm.invalid/v1/chat/completions')
        with a, b:
            _, cfg = self.get('/api/config')
            self.assertTrue(cfg['capabilities']['overview'])
            self.assertEqual(cfg['policy']['mode'], 'free-only')
            code, d = self.get('/api/overview?q=policy+test+result+overview')
        self.assertEqual((code, d['answer']), (200, 'Answer [1].'))
        self.assertIn('llm.invalid', net.calls)
        self.assertEqual(net.paid(), [])
        # Turning the policy to legacy does not create overview consent either.
        with patch.multiple(s, POLICY_MODE='legacy-race', LLM_URL='', SEARXNG_URL='http://searx.invalid:8080'):
            self.assertFalse(s.configuration()['capabilities']['overview'])


if __name__ == '__main__':
    unittest.main()
