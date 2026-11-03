"""Runner safety regressions: no Docker, browser, engine or real network access."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'qa' / (name + '.py'))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checks = load('policy_checks')
preflight = load('policy_preflight')


class RunnerSafetyTests(unittest.TestCase):
    def test_tls_positive_control_cannot_be_satisfied_by_http(self):
        for d in ({'http': 4, 'tls': 0}, {'http': 0, 'tls': 4}, {'http': -1, 'tls': 1}):
            with self.subTest(d=d), self.assertRaises(AssertionError):
                checks.counter(d, positive=True)
        checks.counter({'http': 1, 'tls': 1}, positive=True)
        checks.counter({'http': 0, 'tls': 0})
        with self.assertRaises(AssertionError):
            checks.counter({'http': 0, 'tls': 1})

    def test_dns_requires_each_host_to_be_only_the_exact_sink(self):
        calls = []
        def resolve(host, *a, **kw):
            calls.append(host)
            return [(None, None, None, None, ('172.30.0.5', 443))]
        preflight.check_dns(resolve, ['172.30.0.5'])
        self.assertEqual(calls, ['api.firecrawl.dev', 'api.brightdata.com', 'paid-sink'])
        def mixed(host, *a, **kw):
            rows = resolve(host)
            if host == 'api.brightdata.com':
                rows.append((None, None, None, None, ('203.0.113.1', 443)))
            return rows
        with self.assertRaises(AssertionError):
            preflight.check_dns(mixed, ['172.30.0.5'])

    def test_literal_ip_external_route_must_be_blocked(self):
        def blocked(*a, **kw):
            raise OSError('no route')
        preflight.check_no_route(blocked)
        class OpenConnection:
            def close(self): pass
        with self.assertRaises(AssertionError):
            preflight.check_no_route(lambda *a, **kw: OpenConnection())

    def test_internal_app_and_sink_only_separate_egress_for_free_sidecar(self):
        def box(names):
            return {'NetworkSettings': {'Networks': {n: {'IPAddress': '172.30.0.5'} for n in names}}}
        a, sink, sx = box(['internal']), box(['internal']), box(['internal', 'upstream'])
        networks = [{'Name': 'internal', 'Internal': True}, {'Name': 'upstream', 'Internal': False}]
        self.assertEqual(checks.topology(a, sink, sx, networks), ['172.30.0.5'])
        with self.assertRaises(AssertionError):
            checks.topology(box(['internal', 'upstream']), sink, sx, networks)
        with self.assertRaises(AssertionError):
            checks.topology(a, sink, sx, [{'Name': 'internal', 'Internal': False}])
        with self.assertRaises(AssertionError):
            checks.topology(a, box(['internal', 'upstream']), sx, networks)

    def test_real_api_function_drains_large_error_without_sigpipe(self):
        script = (ROOT / 'qa/provider_policy_container.sh').read_text()
        api = script[script.index('api() {'):].split('\n}', 1)[0] + '\n}'
        # Simulates docker exec, not HTTP. A large valid JSON body used to close the
        # producer's pipe while api | head -1 returned a misleading SIGPIPE (141).
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / 'response.json'
            program = '''set -euo pipefail
fake_docker() {
  if [[ "$*" == *"cat /tmp/r"* ]]; then
    python3 -c 'print(" " * 1048576 + "{\\\"error\\\":\\\"RuntimeError\\\"}")'
  else
    printf '502\\n'
  fi
}
DC=(fake_docker)
''' + api + '\napi /api/web "$1"\n'
            subprocess.run(['bash', '-c', program, 'qa-api-regression', str(output)], check=True, timeout=5)
            checks.response(output, 'down')
            self.assertGreater(output.stat().st_size, 1048576)

    def test_guard_order_retries_and_own_image_cleanup_remain_in_runner(self):
        script = (ROOT / 'qa/provider_policy_container.sh').read_text()
        up = script.split('\nup() {', 1)[1].split('\n}', 1)[0]
        self.assertLess(up.index('preflight'), up.index('api /api/health'))
        self.assertNotIn('| head', '\n'.join(line for line in script.splitlines() if not line.startswith('#')))
        self.assertIn('for i in 1 2 3', script)
        self.assertIn('docker image rm "$POLICY_QA_IMAGE"', script)
        self.assertNotIn('docker image prune', script)
