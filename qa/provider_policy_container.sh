#!/usr/bin/env bash
# Forum-only container acceptance. Fake keys; no real vendor requests. See qa/README.md.
set -euo pipefail
cd "$(dirname "$0")/.."
REV=$(git rev-parse HEAD)
P="wsp-$(date +%s)-$$"
OUT=${OUT:-"$PWD/qa-out/$P"}
export POLICY_QA_IMAGE="wizard-search-policy-qa:$P"
mkdir -p "$OUT"
exec > >(tee "$OUT/run.log") 2>&1
DC=(docker compose -p "$P" --project-directory . -f runtipi/docker-compose.yml -f qa/policy.override.yml)
cleanup() {
  "${DC[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  # Only our unique app image, never shared base/SearXNG images or other jobs' cache.
  docker image rm "$POLICY_QA_IMAGE" >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
echo "revision $REV project $P out $OUT"

# Prove the shipped-UI notice tests really execute (the pinned Python image has no Node).
command -v node
python3 -m unittest discover -s tests -p test_setup_notice.py -v

echo "== 1 unit tests in pinned python:3.12-slim"
docker run --rm --network none -v "$PWD:/src:ro" -w /src -e PYTHONDONTWRITEBYTECODE=1 \
  python:3.12-slim@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2 \
  sh -c 'python3 -m unittest discover -s tests -v && python3 tools/check_view.py'

# Each response is fully drained into a file BEFORE inspecting it; never pipe api to head.
api() {
  local target=$1 file=$2
  "${DC[@]}" exec -T wizard-search curl -sS -o /tmp/r -w '%{http_code}\n' --max-time 40 "http://127.0.0.1:9288$target" > "$file"
  "${DC[@]}" exec -T wizard-search cat /tmp/r >> "$file"
}
count() { "${DC[@]}" exec -T paid-sink python -c 'import urllib.request;print(urllib.request.urlopen("http://127.0.0.1:8080/count").read().decode())'; }
assert_zero() { local c; c=$(count); echo "paid sink: $c"; python3 qa/policy_checks.py counter "$c"; }
preflight() {
  local a s x n
  a=$("${DC[@]}" ps -q wizard-search); s=$("${DC[@]}" ps -q paid-sink); x=$("${DC[@]}" ps --all -q wizard-search-searxng)
  docker inspect "$a" > "$OUT/app-inspect.json"
  docker inspect "$s" > "$OUT/sink-inspect.json"
  docker inspect "$x" > "$OUT/searx-inspect.json"
  # Every network of this compose project (including the Search-only internal network).
  n=$(docker network ls -q --filter "label=com.docker.compose.project=$P")
  # Docker network IDs have no whitespace.
  read -r -d '' -a networks <<< "$n" || true
  docker network inspect "${networks[@]}" > "$OUT/networks-inspect.json"
  local expected
  expected=$(python3 qa/policy_checks.py topology "$OUT")
  # DNS must match the exact sink IP set; this runs before config, health, search or sink HTTP.
  "${DC[@]}" exec -T wizard-search python3 - "$expected" < qa/policy_preflight.py
}
up() {
  "${DC[@]}" up -d --no-deps --no-build --force-recreate wizard-search >/dev/null
  preflight
  for i in $(seq 30); do
    if api /api/health "$OUT/health.json" && python3 -c 'import sys;assert open(sys.argv[1]).readline().strip()=="200"' "$OUT/health.json"; then return; fi
    sleep 1
  done
  echo "search not healthy"; exit 1
}
real_results() {
  local kind=$1 query=$2
  # Upstream engines may rate-limit or start slowly: at most 3 attempts per capability.
  # Never replace a real response with fixtures, and retain every attempt.
  for i in 1 2 3; do
    local file="$OUT/$kind-free-$i.json"
    if api "$query" "$file" && python3 qa/policy_checks.py "$kind" "$file"; then
      cp "$file" "$OUT/$kind-free.json"; return
    fi
    assert_zero
    if [ "$i" != 3 ]; then sleep 3; fi
  done
  echo "real SearXNG $kind exhausted 3 attempts"; return 1
}

echo "== build + start (free-only default, stale fake keys)"
export WIZARD_SEARCH_PROVIDER_POLICY=
"${DC[@]}" build --build-arg REVISION="$REV" wizard-search
"${DC[@]}" up -d --no-build paid-sink wizard-search-searxng
up
api /api/config "$OUT/config-free.json"
python3 qa/policy_checks.py config "$OUT/config-free.json"
for i in $(seq 20); do
  if "${DC[@]}" exec -T wizard-search curl -sf -o /dev/null http://wizard-search-searxng:8080/healthz; then break; fi
  if [ "$i" = 20 ]; then echo 'SearXNG not healthy'; exit 1; fi
  sleep 2
done

echo "== 2 real SearXNG web + images, free-only"
real_results web '/api/web?q=Python+programming+language+official+documentation'
real_results images '/api/images?q=lighthouse'
assert_zero

echo "== 3 SearXNG stopped, free-only: actual 502 RuntimeError, zero paid"
"${DC[@]}" stop wizard-search-searxng >/dev/null
api '/api/web?q=searxng+stopped+policy+check' "$OUT/web-down-free.json"
python3 qa/policy_checks.py down "$OUT/web-down-free.json"
sleep 8; assert_zero

echo "== 4 invalid policy fails closed"
export WIZARD_SEARCH_PROVIDER_POLICY=paid-please
up
api /api/config "$OUT/config-invalid.json"
python3 qa/policy_checks.py invalid "$OUT/config-invalid.json"
api '/api/web?q=invalid+policy+check' "$OUT/web-invalid.json"
python3 qa/policy_checks.py down "$OUT/web-invalid.json"
sleep 8; assert_zero

echo "== 5 legacy-race explicit: HTTP and TLS counters must INDEPENDENTLY increase"
export WIZARD_SEARCH_PROVIDER_POLICY=legacy-race
up
api '/api/web?q=legacy+race+policy+check' "$OUT/web-legacy.json"
# Background futures can finish after the winning router result. Bounded drain only.
for i in $(seq 10); do
  c=$(count); echo "paid sink: $c"
  if python3 qa/policy_checks.py counter "$c" positive; then break; fi
  if [ "$i" = 10 ]; then echo 'counter positive control failed'; exit 1; fi
  sleep 1
done
echo "ALL PROVIDER-POLICY CONTAINER CHECKS PASSED revision $REV"
