#!/usr/bin/env python3
"""Real installed Search HTTP proof; synthetic inputs only; never imports server/env/keys."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base', default='http://127.0.0.1:19289')
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--ocr-image', type=Path, required=True)
    p.add_argument('--ocr-expect', default='SEARCH QA 4827')
    a = p.parse_args()
    base = a.base.rstrip('/')
    evidence = {'base': base, 'scope': 'actual installed HTTP API; harmless synthetic inputs; no replay',
                'checks': {}, 'started_at_unix': time.time()}
    a.evidence.parent.mkdir(parents=True, exist_ok=True)

    def save():
        a.evidence.write_text(json.dumps(evidence, indent=2) + '\n')

    def request(path, body=None, mime='application/json'):
        req = urllib.request.Request(base + path, data=body, headers={'Content-Type': mime} if body else {})
        with urllib.request.urlopen(req, timeout=100) as r:
            return r.status, r.headers.get('Content-Type', ''), r.read(), dict(r.headers)

    def obj(path, body=None):
        return json.loads(request(path, json.dumps(body).encode() if body else None)[2])

    def check(name, fn):
        started = time.monotonic()
        try:
            value = fn()
            evidence['checks'][name] = {'status': 'passed', 'value': value}
        except Exception as ex:
            error = {'type': type(ex).__name__, 'message': str(ex)}
            if isinstance(ex, urllib.error.HTTPError):
                error.update(http_status=ex.code, body=ex.read(8192).decode(errors='replace'))
            evidence['checks'][name] = {'status': 'failed', 'error': error}
        evidence['checks'][name]['elapsed_ms'] = round((time.monotonic() - started) * 1000)
        save()

    def config():
        cfg = obj('/api/config'); provider = obj('/api/overview-provider')
        evidence.update(configuration=cfg, overview_provider=provider)
        assert all(cfg['capabilities'].get(k) is True for k in ('web', 'images', 'overview'))
        assert cfg['providers'] == {'searxng': True, 'socks': False, 'firecrawl_cloud': False,
                                    'brightdata': False, 'firecrawl_router': False, 'tinfoil': True}
        assert provider == {'mode': 'proxy', 'model': 'gpt-oss-120b', 'tinfoil': {'installed': True, 'connected': True}}
        return {'private_inference': True, 'nonprivate_or_subscription_fallback_configured': False}
    check('configuration', config)
    # A distinct public question avoids overview cache; caches are not cleared or mutated by QA.
    query = 'Python pathlib Path official library documentation'
    def web():
        value = obj('/api/web?' + urllib.parse.urlencode({'q': query}))
        evidence['web'] = value
        assert value['source'] == 'searxng' and value['results']
        assert all(r['url'].startswith(('https://', 'http://')) for r in value['results'])
        return {'source': value['source'], 'result_count': len(value['results'])}
    check('web', web)

    def stream():
        started = time.monotonic(); events = []; event = None
        evidence['stream'] = events
        with urllib.request.urlopen(base + '/api/overview-stream?' + urllib.parse.urlencode({'q': query}), timeout=100) as r:
            assert r.headers.get_content_type() == 'text/event-stream'
            for raw in r:
                line = raw.decode().strip()
                if line.startswith('event: '):
                    event = line[7:]
                elif line.startswith('data: '):
                    events.append({'event': event, 'elapsed_ms': round((time.monotonic()-started)*1000), 'data': json.loads(line[6:])})
                    save()
        assert events and events[-1]['event'] == 'done'
        done = events[-1]['data']
        answer = ''.join(e['data'].get('t', '') for e in events if e['event'] == 'delta')
        sources = next(e['data'] for e in events if e['event'] == 'sources')
        citations = sorted(set(int(n) for n in re.findall(r'\[(\d+)\]', answer)))
        assert not done.get('cached') and not done.get('error'), done
        assert sources['source'] == 'searxng' and sources['sources']
        assert done['model'] == 'gpt-oss-120b' and answer and citations
        assert set(citations) <= {s['n'] for s in sources['sources']}
        return {'model': done['model'], 'fresh': True, 'first_delta_ms': next(e['elapsed_ms'] for e in events if e['event']=='delta'),
                'total_ms': events[-1]['elapsed_ms'], 'delta_count': sum(e['event']=='delta' for e in events),
                'citation_numbers': citations, 'source_count': len(sources['sources']), 'answer': answer}
    check('private_stream', stream)

    def images():
        value = obj('/api/images?' + urllib.parse.urlencode({'q': 'Python programming language logo'}))
        evidence['images'] = value
        assert value['source'] == 'searxng' and value['images']
        return {'source': value['source'], 'result_count': len(value['images'])}
    check('images', images)

    def full_image():
        attempts = []; evidence['full_image_attempts'] = attempts
        for row in evidence.get('images', {}).get('images', [])[:6]:
            path = '/img/' + row['id'] + '.jpg'
            try:
                status, mime, data, headers = request(path)
                attempt = {'id': row['id'], 'url': path, 'http_status': status, 'content_type': mime,
                           'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                attempts.append(attempt); save()
                assert mime.startswith('image/') and len(data) > 100
                signature = data.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff', b'GIF8', b'RIFF')) or data[4:12] in (b'ftypavif', b'ftypavis')
                assert signature, 'Unsupported/non-image signature'
                image_file = a.evidence.parent / 'live-full-image.bin'; image_file.write_bytes(data)
                return {**attempt, 'file': str(image_file), 'scope': 'real full proxy bytes; browser decode separate'}
            except Exception as ex:
                attempts.append({'id': row['id'], 'error': str(ex)}); save()
        raise AssertionError('No valid full proxy image in first six actual results')
    check('full_image', full_image)

    def translate():
        value = obj('/api/translate', {'items': ['Bonjour le monde', 'Documentation officielle'], 'to': 'English'})
        evidence['translation'] = value
        assert len(value['items']) == 2 and 'hello' in value['items'][0].lower() and 'world' in value['items'][0].lower()
        assert 'official' in value['items'][1].lower() and 'documentation' in value['items'][1].lower()
        return value
    check('translation', translate)

    def ocr():
        data = a.ocr_image.read_bytes()
        value = json.loads(request('/api/read-image', data, 'image/png')[2]); evidence['ocr'] = value
        normalize = lambda s: re.sub(r'[^A-Z0-9]', '', s.upper())
        assert normalize(a.ocr_expect) in normalize(' '.join(value['lines'])), value
        assert value['model'] == 'gemma4-31b'
        return {**value, 'synthetic_input_sha256': hashlib.sha256(data).hexdigest(), 'expected': a.ocr_expect}
    check('read_image', ocr)
    # Detect provider changes during proof without touching their settings.
    check('configuration_after', config)
    evidence['passed'] = all(c['status']=='passed' for c in evidence['checks'].values())
    save()
    print(json.dumps({'passed': evidence['passed'], 'checks': evidence['checks'], 'evidence': str(a.evidence)}, indent=2))
    return 0 if evidence['passed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
