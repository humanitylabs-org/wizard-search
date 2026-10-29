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

## Private release archive installation

This test release distributes architecture-specific Docker archives through the private GitHub
release `v0.1.0-test.1` in `humanitylabs-org/wizard-search`. Repository read access is required;
the GHCR-shaped image name is a **local imported tag**, not a published registry image.
Download `search-linux-arm64.tar.gz` or `search-linux-amd64.tar.gz` for the recipient host,
plus `SHA256SUMS` and `search-package.tar.gz`, using authenticated GitHub release downloads.
Verify the downloaded files against SHA256SUMS, then `docker load -i search-linux-<arch>.tar.gz`.
Both architecture archives load `ghcr.io/humanitylabs-org/wizard-search:0.1.0-test.1`; load only
the matching architecture on a recipient host. The shipped Compose uses `pull_policy: never`.
Check the loaded image ID, architecture and revision against `search-store-manifest.json`.
Extract the source/setup package for the App Manager integration; never replace its native
Dockerfile/Compose with a generic inline template. No registry login or provider credentials
are needed to import the image. Provider configuration is a separate, required next step.
The platform owner registers the private Store entry and authenticated gateway; this archive
receipt does not claim that recipient Store access or installation has already been verified.
For archive upgrades and rollback, pin the verified archive SHA256 and loaded image ID instead
of assuming a registry manifest digest exists.

## Default provider (free, nothing to configure)

The Compose file starts `wizard-search-searxng`, an unmodified upstream SearXNG image pinned by digest,
and sets `SEARXNG_URL=http://wizard-search-searxng:8080`. It has no published port, no limiter (single
owner behind the gateway), JSON output enabled and a random secret generated at each start. It fans
each query out to several public engines (Brave, Google, DuckDuckGo, Bing, Wikipedia, ...), so one engine
challenging the box does not stop results. It enables web AND image results with no account or key.
Clear `SEARXNG_URL` to disable it; point it at another SearXNG `/search`-capable origin to replace it.

## Provider policy: free-only by default

`WIZARD_SEARCH_PROVIDER_POLICY` decides which lanes may run. A configured key or URL is **never**
consent to spend or to send queries to another provider.

- `free-only` (default, also used when unset): only the bundled SearXNG and an operator SOCKS egress run.
  Firecrawl Cloud, Bright Data and the Firecrawl router never run, even if their keys/URLs are still set.
  If all free lanes fail, time out or return no results, HTTP web search returns
  502 `{"error":"RuntimeError"}` (the existing server error shape), while MCP `web_search` reports
  `provider_unavailable`; it never falls back to a paid lane. With no free lane configured, search returns 503 `setup_required` naming the configured but
  unapproved lanes.
- `approved-upgrades`: free lanes plus exactly the lanes named in `WIZARD_SEARCH_APPROVED_UPGRADES`
  (comma list of `firecrawl_cloud`, `brightdata`, `firecrawl_router`). Free lanes keep their head start.
- `legacy-race`: explicit opt-in to Search 0.3.1 behaviour (every configured lane may race). Lanes already
  started keep running after another lane wins, so they can spend credits.

Invalid values (unknown mode, unknown lane, `approved-upgrades` with an empty list) fail closed to
`free-only` and report `policy.error`. `GET /api/config` and MCP `search_status` show the effective policy,
`usable` lanes and `blocked_configured` (names only, never values). Lane classes: SearXNG and SOCKS are
`free`; Firecrawl Cloud and Bright Data are `paid`; the Firecrawl router is `operator`.

**Upgrading from 0.3.1 is a rollout gate:** an install with paid keys previously raced them automatically.
Without an explicit compatible policy setting, this version pauses those fallbacks. The existing Search
setup/readiness notice stays visible even when free search is configured. It names the paused providers,
says the keys are kept, and gives the exact settings to restore them; a key alone is still not consent.
No new dashboard, automatic opt-in, environment rewrite or live migration is performed.

Use the existing app settings (runtipi form or private environment), then recreate Search:
- Keep `WIZARD_SEARCH_PROVIDER_POLICY=free-only` to leave paid/operator lanes paused.
- To retain previously approved fallbacks, select `WIZARD_SEARCH_PROVIDER_POLICY=approved-upgrades` and
  put their exact lane names in `WIZARD_SEARCH_APPROVED_UPGRADES`, e.g. `firecrawl_cloud,brightdata`.
  The notice includes any currently approved lanes in its suggested list, so they are not dropped.
- To deliberately retain the complete old race, select `WIZARD_SEARCH_PROVIDER_POLICY=legacy-race`.

Preserve already explicit compatible settings verbatim. This is not a request to reapprove all existing
providers or re-collect their keys: carry forward a documented existing choice only with an authorised
compatible migration, otherwise keep the pause visible and do not roll the change out silently.
Nothing is deleted: keys remain private and `blocked_configured` reports lane names only.

AI overviews, translation and screenshot reading are a separate owner switch (below); this policy does
not turn them on or off, and turning them on does not approve paid search lanes.

## Optional extra lanes (existing paid routes only)

Set any of these in private runtime environment, approve them in the provider policy, then recreate
the container:
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

Web races the free lanes first (SearXNG, plus DDG when SOCKS is set). When approved, Firecrawl Cloud joins
only after a 3 s head start (1.2 s without SearXNG), then approved Bright Data/local-router fallbacks.
Images try SearXNG, then Bing through SOCKS, then (if approved) Bright Data unlocker.

## Optional AI overviews with the Tinfoil app (owner switch, no setup)

When the Tinfoil app is installed and connected on the same box, the Search start screen shows an
"AI overviews" switch. Turn on asks Tinfoil (same-origin owner page, `POST ../wizard-tinfoil/api/app-tokens`)
for a Search-only box token, and Search keeps it 0600 in its `search-data` volume. Search never sees the
Tinfoil API key. Turn off (or Remove on the Tinfoil page) revokes it. Boxes without Tinfoil see no switch.
`WIZARD_SEARCH_TINFOIL_APP` (default `http://wizard-tinfoil:18804`) names the peer. Overviews spend the
owner's Tinfoil credit. An operator `TINFOIL_PROXY_URL` (below) takes precedence over the switch.

## Optional inference (operator proxy)

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

Expected fresh install with the bundled sidecar: state=configured, web and images true, overview false
(the overview box stays hidden). With `SEARXNG_URL` cleared and nothing else set: state=setup_required;
search returns 503 with error=setup_required and the screen displays setup instructions. After configuration:
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
