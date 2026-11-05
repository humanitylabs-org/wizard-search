"""Bounded real-provider readiness; synthetic queries only, no mock success."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

QUERIES = [('web', 'Python programming language official documentation'),
           ('images', 'Python programming language logo')]


def request_json(url, timeout=15):
    start = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(2_000_000)
            status = response.status
        try:
            data = json.loads(body)
        except ValueError:
            data = None
        return {'status': status, 'elapsed_ms': round((time.monotonic()-start)*1000),
                'data': data, 'body_excerpt': body[:4096].decode('utf8', 'replace') if data is None else None}
    except urllib.error.HTTPError as error:
        return {'status': error.code, 'elapsed_ms': round((time.monotonic()-start)*1000),
                'body_excerpt': error.read(4096).decode('utf8', 'replace')}
    except (OSError, TimeoutError) as error:
        return {'status': None, 'elapsed_ms': round((time.monotonic()-start)*1000),
                'error': type(error).__name__, 'detail': str(error)[:512]}


def useful(kind, data):
    if not isinstance(data, dict) or data.get('source') != 'searxng':
        return False
    rows = data.get('results' if kind == 'web' else 'images')
    if not isinstance(rows, list) or not rows:
        return False
    valid_url = lambda value: isinstance(value, str) and urllib.parse.urlsplit(value).scheme in ('http', 'https') and bool(urllib.parse.urlsplit(value).hostname)
    valid = [row for row in rows if isinstance(row, dict) and row.get('title') and
             valid_url(row.get('url' if kind == 'web' else 'full')) and
             (kind == 'web' or valid_url(row.get('page')))]
    # A nonempty array alone can be a broken projection. Retain the exact actual
    # results for parent usefulness review, and require at least one Python hit.
    return bool(valid) and any('python' in json.dumps(row).lower() for row in valid)


def wait_search(base, evidence, timeout=100, request=request_json, sleep=time.sleep, clock=time.monotonic):
    deadline = clock() + timeout
    attempts, live = [], {}
    def persist():
        (evidence/'packaged-readiness.json').write_text(json.dumps({'synthetic_queries': True, 'real_provider': True,
            'timeout_seconds': timeout, 'attempts': attempts, 'passed_kinds': sorted(live)}, indent=2)+'\n')
    for kind, query in QUERIES:
        for attempt in range(1, 4):
            remaining = deadline-clock()
            if remaining <= 0:
                break
            result = request(base+'/api/'+kind+'?q='+urllib.parse.quote(query), timeout=min(15, remaining))
            data = result.pop('data', None)
            passed = useful(kind, data)
            attempts.append({'kind': kind, 'attempt': attempt, 'query': query, **result, 'useful': passed,
                             'response': data})
            if passed:
                live[kind] = data
            persist()  # includes 502 bodies even if a later attempt passes
            if passed:
                break
            if attempt < 3:
                sleep(min(3, max(0, deadline-clock())))
        if kind not in live:
            raise RuntimeError('Real packaged '+kind+' unavailable; see packaged-readiness.json and compose/provider diagnostics')
    (evidence/'packaged-live-search.json').write_text(json.dumps(live, indent=2)+'\n')
    return live
