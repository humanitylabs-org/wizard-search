#!/usr/bin/env bash
# Provider-policy container acceptance for Search. Linux/amd64 heavy host only (needs Docker + Internet).
# Builds this checkout, runs the real bundled SearXNG plus a counting sink that impersonates every
# paid/operator destination, then proves:
#   1. unit tests pass inside the pinned Python 3.12 image
#   2. free-only + stale fake keys: real SearXNG web+image results, zero paid requests
#   3. free-only + SearXNG stopped: honest 502, zero paid requests
#   4. invalid policy fails closed to free-only, zero paid requests
#   5. legacy-race (explicit) + SearXNG stopped: paid lane runs (proves the counter can see paid calls)
# Keys are fake literals; real vendor hosts are shadowed on the private app network. Cleans up on exit.
set -euo pipefail
cd "$(dirname "$0")/.."
REV=$(git rev-parse HEAD)
P="wsp-$(date +%s)-$$"
OUT=${OUT:-"$PWD/qa-out/$P"}
mkdir -p "$OUT"
exec > >(tee "$OUT/run.log") 2>&1
DC=(docker compose -p "$P" --project-directory . -f runtipi/docker-compose.yml -f qa/policy.override.yml)
cleanup() { "${DC[@]}" down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT
echo "revision $REV project $P out $OUT"

echo "== 1 unit tests in pinned python:3.12-slim"
docker run --rm -v "$PWD:/src:ro" -w /src -e PYTHONDONTWRITEBYTECODE=1 \
  python:3.12-slim@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2 \
  sh -c 'python3 -m unittest discover -s tests -v && python3 tools/check_view.py'

export FIRECRAWL_CLOUD_API_KEY=fake-stale-firecrawl-key BRIGHTDATA_API_TOKEN=fake-stale-brightdata-token
export FIRECRAWL_CLOUD_URL=https://api.firecrawl.dev
api() { "${DC[@]}" exec -T wizard-search curl -s -o /tmp/r -w '%{http_code}' --max-time 40 "http://127.0.0.1:9288$1" && echo && "${DC[@]}" exec -T wizard-search cat /tmp/r; }
count() { "${DC[@]}" exec -T paid-sink python -c 'import urllib.request;print(urllib.request.urlopen("http://127.0.0.1:8080/count").read().decode())'; }
up() { "${DC[@]}" up -d --no-deps --force-recreate wizard-search >/dev/null; for i in $(seq 60); do api /api/health >/dev/null 2>&1 && return; sleep 2; done; echo "search not healthy"; exit 1; }
assert_zero() { c=$(count); echo "paid sink: $c"; python3 -c "import json,sys;d=json.loads(sys.argv[1]);sys.exit(0 if d=={'http':0,'tls':0} else 'PAID REQUESTS SEEN')" "$c"; }

echo "== build + start (free-only default, stale fake keys)"
export WIZARD_SEARCH_PROVIDER_POLICY=
"${DC[@]}" build --build-arg REVISION="$REV" wizard-search
"${DC[@]}" up -d
up
api /api/config | tee "$OUT/config-free.json"; echo
python3 - "$OUT/config-free.json" <<'PY'
import json,sys
raw=open(sys.argv[1]).read().split("\n",1)[1]; d=json.loads(raw)
assert d["policy"]["mode"]=="free-only", d["policy"]
assert sorted(d["policy"]["blocked_configured"])==["brightdata","firecrawl_cloud","firecrawl_router"], d["policy"]
assert "fake-stale" not in raw
print("config OK")
PY
for i in $(seq 20); do "${DC[@]}" exec -T wizard-search curl -sf -o /dev/null http://wizard-search-searxng:8080/healthz && break; sleep 3; done

echo "== 2 real SearXNG web + images, free-only"
api '/api/web?q=Python+programming+language+official+documentation' | tee "$OUT/web-free.json"; echo
python3 - "$OUT/web-free.json" <<'PY'
import json,sys
code,raw=open(sys.argv[1]).read().split("\n",1); d=json.loads(raw)
assert code=="200" and d["source"]=="searxng" and d["policy"]=="free-only" and d["results"], (code, raw[:300])
print("web OK:", len(d["results"]), "results; first", d["results"][0]["url"])
PY
api '/api/images?q=lighthouse' > "$OUT/images-free.json"
python3 -c "import json,sys;c,r=open(sys.argv[1]).read().split('\n',1);d=json.loads(r);assert c=='200' and d['source']=='searxng' and d['images'],(c,r[:200]);print('images OK:',len(d['images']))" "$OUT/images-free.json"
assert_zero

echo "== 3 SearXNG stopped, free-only: honest failure, zero paid"
"${DC[@]}" stop wizard-search-searxng >/dev/null
api '/api/web?q=searxng+stopped+policy+check' | tee "$OUT/web-down-free.json"; echo
head -1 "$OUT/web-down-free.json" | grep -qx 502
sleep 8; assert_zero

echo "== 4 invalid policy fails closed"
export WIZARD_SEARCH_PROVIDER_POLICY=paid-please
up
api /api/config | sed -n 2p | python3 -c "import json,sys;d=json.load(sys.stdin)['policy'];assert d['mode']=='free-only' and d['error'],d;print('invalid policy ->',d['mode'],d['error'])"
api '/api/web?q=invalid+policy+check' | head -1 | grep -qx 502
sleep 8; assert_zero

echo "== 5 legacy-race explicit: counter observes paid lane"
export WIZARD_SEARCH_PROVIDER_POLICY=legacy-race
up
api '/api/web?q=legacy+race+policy+check' | tee "$OUT/web-legacy.json"; echo
c=$(count); echo "paid sink: $c"
python3 -c "import json,sys;d=json.loads(sys.argv[1]);sys.exit(0 if d['http']+d['tls']>0 else 'counter saw nothing; zero-paid results above are not meaningful')" "$c"
echo "ALL PROVIDER-POLICY CONTAINER CHECKS PASSED revision $REV"
