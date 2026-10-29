"""Small fail-closed assertions shared by the QA runner and lightweight regressions."""
import json
from pathlib import Path
import sys


def topology(app, sink, searx, networks):
    a, s, x = (v['NetworkSettings']['Networks'] for v in (app, sink, searx))
    assert len(a) == 1 and set(a) == set(s), 'app and sink must share ONLY one internal network'
    private = next(iter(a))
    by_name = {n['Name']: n for n in networks}
    assert by_name[private]['Internal'] is True, 'Search network permits external egress'
    assert set(x) > set(a) and len(x) == 2, 'only SearXNG may also join the upstream network'
    upstream = next(iter(set(x) - set(a)))
    assert by_name[upstream]['Internal'] is False, 'SearXNG needs a separate outbound network'
    addresses = {s[private].get(k) for k in ('IPAddress', 'GlobalIPv6Address')} - {'', None}
    assert addresses, 'sink has no addresses'
    return sorted(addresses)


def counter(d, positive=False):
    assert set(d) == {'http', 'tls'} and all(type(n) is int and n >= 0 for n in d.values()), d
    if positive:
        # HTTP success must never mask a broken TLS hostname/counter path.
        assert d['http'] > 0, 'HTTP counter saw no paid router request'
        assert d['tls'] > 0, 'TLS counter saw no paid vendor connection'
    else:
        assert d == {'http': 0, 'tls': 0}, 'PAID REQUESTS SEEN: ' + str(d)


def response(path, kind):
    code, raw = Path(path).read_text().split('\n', 1)
    d = json.loads(raw)
    if kind in ('web', 'images'):
        field = 'results' if kind == 'web' else 'images'
        assert code == '200' and d['source'] == 'searxng' and d['policy'] == 'free-only' and d[field], (code, raw[:300])
        print(kind, 'OK:', len(d[field]))
    elif kind == 'down':
        assert code == '502' and d == {'error': 'RuntimeError'}, (code, raw[:300])
    elif kind in ('config', 'invalid'):
        assert code == '200' and d['policy']['mode'] == 'free-only', (code, raw[:300])
        assert sorted(d['policy']['blocked_configured']) == ['brightdata', 'firecrawl_cloud', 'firecrawl_router'], d['policy']
        assert 'fake-stale' not in raw
        if kind == 'invalid':
            assert d['policy']['error'], d['policy']
    else:
        raise AssertionError('unknown response assertion: ' + kind)


if __name__ == '__main__':
    action, *args = sys.argv[1:]
    if action == 'topology':
        p = Path(args[0])
        app, sink, searx, networks = (json.loads((p / f'{n}-inspect.json').read_text()) for n in ('app', 'sink', 'searx', 'networks'))
        print(json.dumps(topology(app[0], sink[0], searx[0], networks)))
    elif action == 'counter':
        counter(json.loads(args[0]), positive=len(args) > 1 and args[1] == 'positive')
    else:
        response(args[0], action)
