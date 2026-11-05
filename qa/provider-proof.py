#!/usr/bin/env python3
"""Synthetic live-provider proof. No owner queries/history, no credential output or persistence."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument('--evidence', type=Path, required=True)
p.add_argument('--tinfoil-container')
a = p.parse_args()
spec = importlib.util.spec_from_file_location('search_proof', Path(__file__).resolve().parents[1] / 'server.py')
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
if a.tinfoil_container:
    # Read ONLY the installed provider app's documented internal API credential, not its connection/API key.
    # Keep the pipe in process memory; never echo or persist it.
    raw = subprocess.check_output(['docker', 'exec', a.tinfoil_container, 'python3', '-c',
                                  'import json,os;from pathlib import Path;print(json.loads((Path(os.environ.get("DATA_DIR","/data"))/"gateway-token.json").read_text())["token"])'])
    m.TINFOIL_KEY = raw.decode().strip()
q = 'Python programming language official documentation'
evidence = {'synthetic_query': q, 'searxng': m.SEARXNG_URL, 'provider': 'Tinfoil',
            'model': m.LLM_MODEL, 'reasoning_effort': 'low', 'fallback_added': False,
            'transport': 'installed-tinfoil-app' if a.tinfoil_container else 'approved-private-proxy'}
evidence['web'] = m.web_search(q)
evidence['images'] = m.image_search('Python programming language logo')
assert evidence['web']['results'] and evidence['web']['source'] == 'searxng'
assert evidence['images']['images'] and evidence['images']['source'] == 'searxng'
m.WEB_CACHE.put(q.lower(), evidence['web'])
started = time.monotonic()
events = []
def emit(kind, value):
    events.append({'event': kind, 'elapsed_ms': round((time.monotonic()-started)*1000), 'data': value})
m.overview_stream(q, emit)
assert events[-1]['event'] == 'done'
answer = ''.join(e['data'].get('t', '') for e in events if e['event'] == 'delta')
assert answer and '[' in answer and events[-1]['data']['model'] == 'gpt-oss-120b'
evidence['stream'] = events
evidence['delta_count'] = sum(e['event'] == 'delta' for e in events)
evidence['first_delta_ms'] = next(e['elapsed_ms'] for e in events if e['event'] == 'delta')
evidence['total_ms'] = events[-1]['elapsed_ms']
evidence['translation'] = m.translate_items(['Bonjour le monde', 'Documentation officielle'])
assert len(evidence['translation']['items']) == 2
# Source icon is a public synthetic image, not an owner attachment or screenshot.
try:
    evidence['vision'] = m.read_image((Path(__file__).resolve().parents[1] / 'web/icon.png').read_bytes(), 'image/png')
except Exception as ex:
    evidence['vision'] = {'error': type(ex).__name__, 'note': 'Real provider failed; failure parity covered separately, not a success claim.'}
a.evidence.parent.mkdir(parents=True, exist_ok=True)
a.evidence.write_text(json.dumps(evidence, indent=2)+'\n')
print(json.dumps({k:evidence[k] for k in ['provider','transport','model','reasoning_effort','delta_count','first_delta_ms','total_ms','translation','vision']}, indent=2))
