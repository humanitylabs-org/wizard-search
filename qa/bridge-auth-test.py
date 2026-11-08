#!/usr/bin/env python3
"""Small stdlib regressions: synthetic credentials and ephemeral loopback only.
No Docker, installed services, real credentials, provider calls or private homes.
"""
import contextlib
import argparse
import ast
import importlib.util
import io
import json
import os
import runpy
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from typing import Any
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bridge', ROOT / 'ops/private-proxy-bridge.py')
assert spec is not None and spec.loader is not None
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
CALLER = 'synthetic-caller-' + 'a' * 40
UPSTREAM = 'synthetic-upstream-' + 'b' * 40
BODY = json.dumps({'model': 'gpt-oss-120b', 'messages': [{'role': 'user', 'content': 'fixture only'}]}).encode()


class TokenFiles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.caller = self.directory / 'caller'
        self.caller.write_text(CALLER)
        self.caller.chmod(0o600)
        self.upstream = self.directory / 'upstream'
        self.upstream.write_text(UPSTREAM + '\n')
        self.upstream.chmod(0o600)

    def argv(self):
        return ['bridge', '--bind', '10.128.40.1', '--port', '0',
                '--token-file', str(self.caller), '--upstream-token-file', str(self.upstream),
                '--upstream', 'http://127.0.0.1:1/v1/chat/completions']

    def rejected_before_listen(self, argv=None):
        stderr = io.StringIO()
        with patch.object(sys, 'argv', argv or self.argv()), patch.object(bridge, 'ThreadingHTTPServer') as server:
            with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as result:
                bridge.main()
            self.assertEqual(result.exception.code, 2)
            server.assert_not_called()
        self.assertNotIn(CALLER, stderr.getvalue())
        self.assertNotIn(UPSTREAM, stderr.getvalue())

    def test_valid_protected_file(self):
        self.assertEqual(bridge.read_upstream_token(self.upstream), UPSTREAM)

    def test_missing_file(self):
        self.upstream.unlink()
        self.rejected_before_listen()

    def test_required_argument(self):
        argv = self.argv()
        i = argv.index('--upstream-token-file')
        del argv[i:i+2]
        self.rejected_before_listen(argv)

    def test_permission_modes(self):
        for mode in (0o644, 0o640, 0o660, 0o400, 0o700):
            with self.subTest(mode=oct(mode)):
                self.upstream.chmod(mode)
                self.rejected_before_listen()

    def test_symlink(self):
        target = self.upstream.with_name('target')
        self.upstream.rename(target)
        self.upstream.symlink_to(target)
        self.rejected_before_listen()

    def test_directory(self):
        self.upstream.unlink()
        self.upstream.mkdir(mode=0o600)
        self.rejected_before_listen()

    def test_fifo_does_not_block(self):
        self.upstream.unlink()
        os.mkfifo(self.upstream, 0o600)
        result = subprocess.run([sys.executable, str(ROOT / 'ops/private-proxy-bridge.py'), *self.argv()[1:]],
                                capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(UPSTREAM.encode(), result.stderr)

    def test_invalid_contents(self):
        for raw in (b'', b' \n', b'x' * 8193, b'one\ntwo', b'one two', b'one\x00two', b'\xff'):
            with self.subTest(length=len(raw)):
                self.upstream.write_bytes(raw)
                self.rejected_before_listen()

    def test_identical_credentials_rejected(self):
        self.upstream.write_text(CALLER)
        self.rejected_before_listen()

    def parent_preflight(self, path):
        source = (ROOT / 'ops/parent-release.py').read_text()
        block = source[source.index(' # Validate the explicit credential'):source.index(' manifest=json.loads(')]
        self.assertLess(source.index(block), source.index(' backup.mkdir('))
        code = compile(ast.parse('if True:\n' + block), '<actual package preflight>', 'exec')
        values = {'a': SimpleNamespace(upstream_token_file=path), 'p': argparse.ArgumentParser(),
                  'runpy': runpy, 'root': ROOT}
        exec(code, values)
        return values['upstream_token']

    def test_parent_package_preflight_rejects_missing_or_unsafe_file(self):
        for path in (None, self.directory / 'missing', self.upstream):
            if path == self.upstream:
                self.upstream.chmod(0o644)
            before = sorted(self.directory.iterdir())
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
                self.parent_preflight(path)
            self.assertEqual(sorted(self.directory.iterdir()), before)
            self.assertNotIn(UPSTREAM, stderr.getvalue())

    def test_parent_package_preflight_accepts_explicit_file(self):
        self.assertEqual(self.parent_preflight(self.upstream), UPSTREAM)


class Protocol(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        directory = Path(self.temp.name)
        caller, upstream = directory / 'caller', directory / 'upstream'
        caller.write_text(CALLER)
        upstream.write_text(UPSTREAM)
        caller.chmod(0o600)
        upstream.chmod(0o600)
        self.seen = []
        self.mode = 'json'
        test = self

        class Fixture(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                test.seen.append((dict(self.headers), body, self.path))
                if test.mode == 'redirect':
                    self.send_response(302)
                    self.send_header('Location', f'http://127.0.0.1:{test.up.server_port}/must-not-follow')
                    self.end_headers()
                    return
                if test.mode == 'error':
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(UPSTREAM.encode())
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream' if test.mode == 'stream' else 'application/json')
                self.end_headers()
                self.wfile.write(b'data: {"fixture":true}\n\ndata: [DONE]\n\n' if test.mode == 'stream' else b'{"fixture":true}')

        self.up = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
        threading.Thread(target=self.up.serve_forever, daemon=True).start()
        self.addCleanup(self.close_server, self.up)
        argv = ['bridge', '--bind', '10.128.40.1', '--port', '0', '--token-file', str(caller),
                '--upstream-token-file', str(upstream), '--upstream',
                f'http://127.0.0.1:{self.up.server_port}/v1/chat/completions']
        # Capture the real production handler after main's validation, without a
        # Docker gateway/listener. Serve that handler on a disposable loopback port.
        with patch.object(sys, 'argv', argv), patch.object(bridge, 'ThreadingHTTPServer') as server:
            bridge.main()
            handler = server.call_args.args[1]
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.close_server, self.server)
        self.client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @staticmethod
    def close_server(server):
        server.shutdown()
        server.server_close()

    def request(self, token: str | None = CALLER, body=BODY, path='/v1/chat/completions', extra=None):
        headers = {'Content-Type': 'application/json', **(extra or {})}
        if token is not None:
            headers['Authorization'] = 'Bearer ' + token
        request = urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}{path}', data=body, headers=headers)
        try:
            with self.client.open(request, timeout=3) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            with error:
                return error.code, error.read()

    def test_separate_upstream_authorization_and_exact_body(self):
        status, body = self.request(extra={'X-Api-Key': 'do-not-forward', 'Cookie': 'do-not-forward'})
        self.assertEqual((status, body), (200, b'{"fixture":true}'))
        self.assertEqual(len(self.seen), 1)
        headers, forwarded, path = self.seen[0]
        self.assertEqual(headers['Authorization'], 'Bearer ' + UPSTREAM)
        self.assertNotEqual(headers['Authorization'], 'Bearer ' + CALLER)
        self.assertNotIn('X-Api-Key', headers)
        self.assertNotIn('Cookie', headers)
        self.assertEqual((forwarded, path), (BODY, '/v1/chat/completions'))

    def test_stream_retains_auth(self):
        self.mode = 'stream'
        value = json.loads(BODY)
        value['stream'] = True
        status, body = self.request(body=json.dumps(value).encode())
        self.assertEqual(status, 200)
        self.assertIn(b'data: [DONE]', body)
        self.assertEqual(self.seen[0][0]['Authorization'], 'Bearer ' + UPSTREAM)

    def test_existing_vision_model_retains_auth(self):
        value = json.loads(BODY)
        value['model'] = 'gemma4-31b'
        self.assertEqual(self.request(body=json.dumps(value).encode())[0], 200)
        self.assertEqual(self.seen[0][0]['Authorization'], 'Bearer ' + UPSTREAM)

    def test_deepseek_translation_model_retains_auth(self):
        value = json.loads(BODY)
        value['model'] = 'deepseek-v4-1-flash'
        self.assertEqual(self.request(body=json.dumps(value).encode())[0], 200)
        self.assertEqual(self.seen[0][0]['Authorization'], 'Bearer ' + UPSTREAM)

    def test_wrong_missing_or_upstream_caller_credential_never_forwarded(self):
        for token in ('wrong', None, UPSTREAM):
            with self.subTest(token_kind='missing' if token is None else 'incorrect'):
                self.assertEqual(self.request(token=token)[0], 401)
        self.assertEqual(self.seen, [])

    def test_origin_and_path_rejected_before_upstream(self):
        cases: list[dict[str, Any]] = [{'extra': {'Origin': 'https://elsewhere.invalid'}},
                                      {'extra': {'Sec-Fetch-Site': 'cross-site'}}, {'path': '/elsewhere'}]
        for kwargs in cases:
            self.assertEqual(self.request(**kwargs)[0], 403)
        self.assertEqual(self.seen, [])

    def test_other_model_rejected_before_upstream(self):
        value = json.loads(BODY)
        value['model'] = 'other-provider-model'
        self.assertEqual(self.request(body=json.dumps(value).encode())[0], 400)
        self.assertEqual(self.seen, [])

    def test_upstream_errors_are_generic_and_tokens_not_logged(self):
        self.mode = 'error'
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            status, body = self.request()
        self.assertEqual((status, body), (502, b'{"error":"private_proxy_unavailable"}'))
        self.assertNotIn(UPSTREAM.encode(), body)
        self.assertNotIn(CALLER, stderr.getvalue())
        self.assertNotIn(UPSTREAM, stderr.getvalue())
        self.assertEqual(len(self.seen), 1)

    def test_redirect_never_forwards_upstream_credential(self):
        self.mode = 'redirect'
        self.assertEqual(self.request()[0], 502)
        self.assertEqual(len(self.seen), 1)
        self.assertEqual(self.seen[0][2], '/v1/chat/completions')


if __name__ == '__main__':
    unittest.main(verbosity=2)
