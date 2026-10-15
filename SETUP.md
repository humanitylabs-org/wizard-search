# Search setup for Oscar / the installing agent

## Install boundary

This private test package keeps the existing providers: DuckDuckGo HTML and Bing images through
an operator-supplied SOCKS egress, Firecrawl Cloud, Bright Data SERP/unlocker, an optional existing
Firecrawl-compatible router, and optional Tinfoil inference. Do not substitute vendors or create
paid accounts. Use Miguel's approved credentials/services, not the publisher's.

The image listens on 9288 at `/` (WIZARD_SEARCH_BASE is empty). Proxy its entire path from the
Wizard app route, stripping the gateway prefix. Preserve query strings, Host and Origin; disable
response buffering for `/api/overview-stream`. Serve the installed Wizard shared resource at
`/wizard-os-home/core/app-client.js` on the browser origin. App Manager's usual installed app
mount is `/apps/wizard-search/`; inspect the actual installed registry rather than guessing.
A legacy standalone service may set WIZARD_SEARCH_BASE=/wizard-search instead. Do not combine
a stripped path proxy with that setting. Gateway authentication is REQUIRED; bind direct published
ports only to loopback. No app-owned public auth/rate-limiting is supplied.

## Minimum useful configuration (choose an existing route)

Set **one** of these in private runtime environment, then recreate the container:
- `FIRECRAWL_CLOUD_API_KEY`: existing Firecrawl Cloud key. Optional `FIRECRAWL_CLOUD_URL`
  defaults to `https://api.firecrawl.dev`. Server calls POST /v2/search with Bearer auth;
  response must contain data.web[{url,title,description}]. Enables web results only.
- `FIRECRAWL_ROUTER_URL`: complete private router search endpoint, including /v2/search.
  Existing router contract: POST {query,limit:8}, same response shape, no auth header.
  Keep this router on the private container network. No router is bundled.
- `WIZARD_SEARCH_SOCKS`: reachable `socks5h://host:port`. Enables DuckDuckGo HTML web results
  and Bing image scraping. Must be provided/approved by the operator; no residential tunnel
  or credentials are bundled. Challenges cause a temporary cooldown and fallback.
- `BRIGHTDATA_API_TOKEN`: existing Bright Data API token with approved zones.
  `BRIGHTDATA_SERP_ZONE` defaults `serp_api1`; `BRIGHTDATA_UNLOCK_ZONE` defaults `mcp_unlocker`.
  Verify these exact zone names in the recipient account and override if different. Enables
  Google SERP and Bing images via unlocker; uses https://api.brightdata.com/request.

Web races the original fast routes (DDG gets 1.2s head start before Firecrawl Cloud), then
Bright Data/local-router fallbacks. Multiple configured lanes may incur more than one request.
Images try Bing through SOCKS, then Bright Data unlocker. No silent vendor replacement.

## Optional inference

`TINFOIL_PROXY_URL` is the COMPLETE reachable Tinfoil proxy chat endpoint ending in
`/v1/chat/completions`; optional `TINFOIL_API_KEY` is sent as Bearer auth. Use the recipient's
existing Tinfoil proxy, not a guessed public API or another vendor. Overview needs web search
AND this endpoint; translations/OCR also use it. Models: `WIZARD_SEARCH_MODEL=gpt-oss-120b`,
`WIZARD_TRANSLATE_MODEL=gemma4-31b`, `WIZARD_TRANSLATE_FALLBACK=gpt-oss-120b`,
`WIZARD_VISION_MODEL=gemma4-31b`. Operator must verify those models on their proxy.
Do not copy an old host's loopback URLs: 127.0.0.1 inside the app container means this app,
not another container or the physical host. Prefer same-network service DNS; use an explicitly
configured host gateway only where the host actually exposes that dependency safely.

## Secret custody and upgrade

Use App Manager password fields or a protected environment file (0600) referenced by the
runtime, never source/build arguments/image layers, browser storage or chat. No automatic
reading of ~/.hermes/.env or other owner files. Restart/recreate after environment changes.
Keep the same environment across image updates. There is no persistent query database or
required volume. Results and image IDs deliberately expire/restart empty. Browser URL history
and upstream providers can still retain queries. Result favicons contact icons.duckduckgo.com;
opening source links contacts their publishers. This is not an anonymity guarantee.

## Acceptance commands (against the installed app base)

Set BASE to the authenticated installed app URL, or a loopback API test port. Then:

```sh
curl -fsS "$BASE/api/health"
curl -fsS "$BASE/api/config"
curl -fsS --get --data-urlencode 'q=Python programming language official documentation' "$BASE/api/web"
curl -fsS "$BASE/mcp" -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Expected fresh install: health ok=true, state=setup_required; search returns 503 with
error=setup_required, and the screen displays setup instructions. After configuration:
state=configured means SETTINGS PRESENT only. Require a real query with nonempty results,
public URLs and source lane; open a returned source. For images run /api/images?q=... and fetch
an issued /thumb/<id>.jpg. For overview run /api/overview?q=... and require answer + sources.
No provider fixture counts as real search proof. A 502 means providers failed/challenged or
returned unusable results; inspect account limits/zone names/network and retry without dumping
secrets. Missing optional images/overview must not stop web results.

Restart and repeat health/config/search. Check configured providers survive because the operator's
runtime environment survives, not because keys are written by Search. On upgrade pin the released
image digest; rollback to the previous digest with the same private environment. No data migration.

Browser: test phone/desktop, enter query, view results, switch Images and Back to All, open an
image then Back closes it, root Back stays. No backend mutation or search history delete exists.
