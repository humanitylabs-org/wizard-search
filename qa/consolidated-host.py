#!/usr/bin/env python3
"""Copied public shell; explicit synthetic read-only owner contract, never owner data."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import urllib.parse
import urllib.request
import urllib.error
import mimetypes

APP = {'id': 'wizard-search', 'name': 'Search', 'url': '/wizard-search/',
       'view': {'mode': 'original', 'url': '/wizard-search/'}, 'source': 'apps.json',
       'receives_voice_input': True, 'provides': ['web-search', 'image-search'], 'type': 'service'}
SETTINGS = {'owner': {'name': 'Synthetic QA owner', 'place': ''}, 'agent': {'name': 'Wizard'},
            'clock': {'timezone': 'UTC', 'day_starts_at': '00:00'},
            'voice': {'language': '', 'vocabulary': []}}
# This is a fixture projection of apps.json, NOT a claim about any installed owner registry.
ROUTES = {
    '/wizard/v1/bootstrap': {'bootstrap': 1, 'endpoints': {'apps': '/wizard/v1/apps'},
                             'settings': SETTINGS, 'capabilities': {}},
    '/wizard/v1/settings': {'settings': SETTINGS},
    '/wizard/v1/apps': {'apps': [APP], 'in_development': []},
    '/wizard/v1/ui-preferences': {'launcher': {'links': [], 'nativeLinks': []},
                                  'migrations': {'launcher-seed-v1': True}},
    '/wizard/v1/agents': {'agents': []},
    '/wizard/v1/agent-options': {'agents': []},
    '/wizard/v1/app-bindings': {'bindings': {}},
    '/wizard/v1/pages': {'pages': []},
    '/wizard-os-home/store-data/wizard/v1/app-logos': {'logos': {}},
}


def handler(shell, app_url):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def send(self, code, data, ctype='application/json'):
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            if path in ROUTES:
                return self.send(200, json.dumps(ROUTES[path]).encode())
            if path.startswith('/wizard-search/'):
                try:
                    with urllib.request.urlopen(app_url + self.path[len('/wizard-search'):], timeout=90) as r:
                        return self.send(r.status, r.read(), r.headers.get('Content-Type', 'application/json'))
                except urllib.error.HTTPError as e:
                    return self.send(e.code, e.read())
            if path.startswith('/wizard-os-home/'):
                rel = urllib.parse.unquote(path[len('/wizard-os-home/'):]) or 'index.html'
                f = (shell / rel).resolve()
                if f.is_relative_to(shell.resolve()) and f.is_file():
                    return self.send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or 'application/octet-stream')
            return self.send(404, b'{"error":"synthetic_route_not_defined"}')

        def do_POST(self):
            return self.send(403, b'{"error":"synthetic_shell_read_only"}')

        do_PUT = do_POST
        do_PATCH = do_POST
        do_DELETE = do_POST
    return Handler


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--shell', type=Path, required=True)
    p.add_argument('--port', type=int, default=19771)
    p.add_argument('--app', default='http://127.0.0.1:19772')
    a = p.parse_args()
    ThreadingHTTPServer(('127.0.0.1', a.port), handler(a.shell, a.app)).serve_forever()
