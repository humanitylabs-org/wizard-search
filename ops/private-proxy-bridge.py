#!/usr/bin/env python3
"""Narrow optional host bridge for an already-approved loopback PRIVATE proxy.

No Docker socket, agent mounts, account lookup or endpoint discovery.
Bind ONLY the installed Search bridge gateway, never 0.0.0.0. Explicit protected
files supply separate caller and approved upstream credentials; only the existing
chat-completions path is forwarded. No credential values belong in argv or logs.
"""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import stat
import urllib.error
import urllib.parse
import urllib.request


def read_upstream_token(path):
    """Read one explicit, regular mode-0600 file; never disclose its contents."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= 8192:
                raise ValueError
            raw = stream.read(8193)
        if len(raw) > 8192:
            raise ValueError
        token = raw.decode('ascii').strip()
        if not token or any(not 33 <= ord(c) <= 126 for c in token):
            raise ValueError
        return token
    except (OSError, ValueError):
        raise ValueError('Upstream token requires a readable regular mode-0600 file containing one nonempty ASCII token (max 8192 bytes).') from None


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bind', required=True)
    p.add_argument('--port', type=int, default=19332)
    p.add_argument('--token-file', type=Path, required=True)
    p.add_argument('--upstream-token-file', type=Path, required=True)
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
    try:
        upstream_token = read_upstream_token(a.upstream_token_file)
    except ValueError as error:
        p.error(str(error))
    if hmac.compare_digest(token, upstream_token):
        p.error('Caller and upstream tokens must be separate credentials.')

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None  # Never carry the upstream credential to another endpoint.
    upstream_opener = urllib.request.build_opener(NoRedirect)

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
                request = urllib.request.Request(a.upstream, data=body, headers={
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + upstream_token,
                })
                with upstream_opener.open(request, timeout=120) as response:
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
            except (OSError, ValueError, urllib.error.URLError) as error:
                if isinstance(error, urllib.error.HTTPError):
                    error.close()
                # A failed connection never invokes another provider.
                if response_started:
                    self.close_connection = True
                else:
                    self.fail(502)
    ThreadingHTTPServer((a.bind, a.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
