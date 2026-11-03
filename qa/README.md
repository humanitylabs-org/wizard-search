# Provider policy acceptance (forum only)

`bash qa/provider_policy_container.sh` is a bounded container/internet check, not a unit test or a
live install. Run it only through the authorised forum worker with an exact clean Git SHA and an
empty process environment (except PATH, scratch HOME and OUT). Requires Docker Compose v2, Python 3
and Node on that host. Do not use an owner's `.env`, credentials, networks or volumes.

## Safety and evidence

- The app and counting sink join **one Docker `internal: true` network only**. The real bundled
  SearXNG joins that network plus a separate outbound `free-upstream` network. Search has no external
  route; DNS shadowing is not the sole egress guard. No ports are published.
- After every app recreation, before scripted HTTP checks, inspect actual container/network state,
  require those memberships/internal flags, then resolve **each** paid destination
  (`api.firecrawl.dev`, `api.brightdata.com`, `paid-sink`) from inside Search. Every resolved address
  must equal an actual sink address. A mixed public/private DNS answer fails closed.
- Also require direct IPv4 and IPv6 TCP canaries to fail from Search. They send no HTTP or vendor
  traffic. Explicitly empty proxy/SOCKS/AI variables prevent accidental inherited routes. The free
  SearXNG sidecar alone deliberately contacts public search engines with public test queries.
- Fake stale keys are literal QA-only values in the overlay. No vendor secrets are loaded. A single
  sink accepts router HTTP on 8080 and counts closed TLS connections on 443 for both vendor aliases.
- Free-only success, free-only stopped SearXNG, and invalid policy must each leave **both** counters
  zero. The legacy positive control requires `http > 0` **and independently `tls > 0`**; HTTP alone
  cannot validate the paid-vendor DNS/TLS path. Wait at most ten seconds for background futures.
- Fully consume responses into evidence files before parsing them. Never use `api | head -1` under
  `pipefail`: that can SIGPIPE the producer and hide the actual result. An unavailable HTTP web
  provider currently returns `502 {"error":"RuntimeError"}`, not `provider_unavailable`.
- Retry real-engine results at most three times for web and three for images, retaining every
  response. Exhaustion is a genuine failed acceptance run, never replaced with fixture results.
- EXIT/INT/TERM cleanup removes this run's containers, network and volume and **only** its unique app
  image tag. Shared pinned Python/SearXNG base images and other jobs' build caches are not pruned.

`OUT/run.log`, response files and Docker topology inspections are the retained evidence. Success must
end with `ALL PROVIDER-POLICY CONTAINER CHECKS PASSED revision <exact SHA>`. This does not prove an
installed release, Browser security, real-model MCP use, or permission/grant admission.

## Lightweight repair regressions

`python3 -m unittest discover -s tests -v` includes:
- real `server.configuration()` -> shipped `web/app.js` execution -> actual setup DOM IDs (Node VM,
  no browser). Stale keys/default, no free lane, partial approvals, complete explicit approvals,
  legacy, invalid policy and a clean keyless install; only reads, no config writes;
- runner assertion tests rejecting HTTP-only positive controls, mixed DNS, an external app network,
  an externally routed sink and literal-IP connectivity; a >1 MiB error exercises the actual shell
  `api()` function and catches the old SIGPIPE failure mode.

Without Node the Python-only image explicitly skips the six UI tests; the runner first requires Node
and executes them on the forum host, so a container run cannot silently omit notice coverage.
No local Docker/browser run is needed for these focused unit checks. DOM logic proof is not a visual
skin/screenshot claim; two-skin browser/installed acceptance remains a later release gate.
