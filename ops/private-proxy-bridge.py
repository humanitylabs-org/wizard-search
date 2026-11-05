#!/usr/bin/env python3
"""Narrow optional host bridge for an already-approved loopback PRIVATE proxy.

No Docker socket, provider keys, agent mounts, account lookup or endpoint discovery.
Bind ONLY the installed Search bridge gateway, never 0.0.0.0. The caller supplies
an app-only random token; only the existing chat-completions path is forwarded.
"""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bind', required=True)
    p.add_argument('--port', type=int, default=19332)
    p.add_argument('--token-file', type=Path, required=True)
    p.add_argument('--upstream', required=True)
    a = p.parse_args()
    addr = ipaddress.ip_address(a.bind)
    if not addr.is_private or addr.is_unspecified or addr.is_loopback:
        p.error('Bind must be the Search Docker bridge gateway, not a public/wildcard address.')
    u = urllib.parse.urlsplit(a.upstream)
    if u.scheme != 'http' or u.hostname not in ('127.0.0.1', 'localhost') or u.path != '/v1/chat/completions' or u.query or u.fragment or u.username:
        p.error('Only an explicitly approved loopback /v1/chat/completions upstream is supported.')
    token = a.token_file.read_text().strip()
    if len(token) < 32:
        p.error('Use a dedicated app-only random token of at least 32 characters.')

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'
        def log_message(self, *args):
            pass  # Never log intent, bodies, headers or credentials.
        def fail(self, code):
            b = b'{"error":"private_proxy_unavailable"}'
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        def do_POST(self):
            response_started = False
            if self.path != '/v1/chat/completions' or self.headers.get('Origin') or self.headers.get('Sec-Fetch-Site') == 'cross-site':
                return self.fail(403)
            if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                return self.fail(401)
            try:
                n = int(self.headers.get('Content-Length', '0'))
                if not 0 < n <= 8 * 1024 * 1024:
                    return self.fail(413)
                body = self.rfile.read(n)
                value = json.loads(body)
                # The app's established private overview/translation/vision models only.
                if not isinstance(value, dict) or value.get('model') not in ('gpt-oss-120b', 'gemma4-31b') or not isinstance(value.get('messages'), list):
                    return self.fail(400)
                request = urllib.request.Request(a.upstream, data=body, headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(request, timeout=120) as response:
                    response_started = True
                    self.send_response(response.status)
                    self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('X-Accel-Buffering', 'no')
                    self.end_headers()
                    if value.get('stream'):
                        for line in response:
                            self.wfile.write(line)
                            self.wfile.flush()
                    else:
                        self.wfile.write(response.read())
            except (BrokenPipeError, ConnectionResetError):
                pass
            except (OSError, ValueError, urllib.error.URLError):
                # A failed connection never invokes another provider.
                if response_started:
                    self.close_connection = True
                else:
                    self.fail(502)
    ThreadingHTTPServer((a.bind, a.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
