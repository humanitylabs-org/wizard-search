# Actual installed Search checks and final small visual job

This follow-up changes operator/QA code only; Search runtime inputs remain byte-identical to image source `7fac0ebc6ce22ff951b5fc6738a41b7d40a9456b`. Do **not** rerun `parent-release.py package`: its snapshot, image load, recipe, token and one lifecycle update were already completed manually by parent. Existing lifecycle request ID: `c5c3f8fb-d01f-4edb-8574-209e30a6f348`. Original package source is `11a86e0a9029ee1fd95499d33a1be4fdf030c8d6`; retained full fixture QA source is `09f472aab630ee06eaf0cd265b811c364af00e32`.

## What is actually proven

`qa/live-api-proof.py` calls only actual installed Search HTTP endpoints. Evidence is under the original release's `evidence/installed-live-api*.json`, using harmless Python documentation/logo queries and a generated `SEARCH QA 4827` PNG. Initial and bounded repeat both give real SearXNG web results (10), images (60), and actual full-proxy PNG bytes. The private SSE emits sources then HTTPError with **zero deltas**, and translation/OCR return HTTP 502. Provider configuration correctly advertises only SearXNG and approved Tinfoil proxy mode `gpt-oss-120b`; that is not a reachability pass. No fallback/provider changes were made, no agent data or voice bytes used. Do not accept or cut over based on this partial proof.

`qa/verify-installed-package.py` validates the exact archive content graph + loaded identity, samples only the Search container's public image/revision/running fields, checks all 14 runtime file hashes, computes the original immutable source hash from a scratch `git archive`, checks installed source metadata and the actual HTTP health/providers, then samples exact identity again before writing the explicit receipt. It never submits lifecycle operations. The phase marker is labelled manual-completion recovery and is **not** app/provider/visual acceptance.

## Correct lifecycle helper (future parent use only)

`ops/release_lifecycle.py` uses real installed `rt.req` and `rt.wait_status`. Both update and update-config are PATCH endpoints verified in pinned backend Swagger. The helper persists a protected journal before submission and persists requestId before waiting; existing journals forbid resubmission. Old-running is insufficient: exact immutable image/revision plus running and HTTP health are required. A transient missing container is retried within a bounded readback, not by another mutation. Tests use the pinned Runtipi AST and cover old-running/missing/expected recreation, verification timeout and ambiguous submission. Parent's manual update is not replayed by these tests.

## Voice blocker

The host agent runtime imports its own old WAM source root, independent of patched API/CLI. See the separately pushed WAM branch `fix/agent-runtime-registry-voice-20261105`, source `4f729e9f0ee68fbf62d0ec7682feda80f7ce34ff`, and its `docs/AGENT-RUNTIME-REGISTRY-VOICE.md`. Its immutable staged delivery is under `wam-agent-runtime-writer/<sha>` in this consolidation release. Exactly one of 38 WAM files changes, by one boolean projection line. The old runtime source is **888a61c9…**, not the newer `9309…` baseline. Parent alone activates it; no live registry edits were made. Actual Search shell admission remains false until parent repairs and verifies the writer.

## Forum job, parent submission only

Canonical HTTPS is directly reachable from Forum at `https://wizard.tailc0f369.ts.net`; no tunnel/auth changes are needed. `https://telos.tailc0f369.ts.net/wizard-os-home/` is the wrong gateway (404). Forum's SSH route back to Telos fails host-key verification and is not used or modified.

The staged job uses `qa/live-served-worker.py` and `qa/live-served-browser.cjs`, reusing `qa/shell-frame.cjs`. Preparation with `--pin-only` fetches only actual public shell HTML, app-client and candidate static + actual Search health/provider config + installed public registry, filtering to Search before persistence. It binds Search bytes to the reviewed runtime manifest. It is not a browser job or acceptance.

The parent submission receipt (`live-job-submit.json` next to the staged job) supplies `host=forum,lane=light`, 420s bound. Run it only after private HTTP inference and voice admission are fixed. The worker refuses static-byte drift and false voice admission. It uses actual installed ID `search-preview` and same-origin `/wizard-search/preview/`; after parent cutover, prepare a distinct pin set with the resulting real ID and root path instead of relabelling preview evidence.

Browser scope: actual live public shell; real installed Search registry (other app metadata discarded); harmless actual Search web/images and fresh private SSE requests. All unrelated owner history, agents, accounts, bootstrap settings and preferences are intercepted with synthetic empty bodies; all owner writes and foreign origins are blocked. No fabricated identity headers, auth replacements, Search API substitutions, recorded SSE replay or owner preference writes. Settings/bootstrap values are explicitly synthetic; this is not owner-personalization QA.

Matrix: phone 390×844 and desktop 1440×1000 using real shell overrides; each uses ephemeral `WosSkin.preview` for installed `nebula` and `obsidian-light`. Four screenshots plus actual served response-body hashes, current registry, native SSE events/first-delta/model/citations and blocked endpoint paths are retained. The browser selects a committed actionable iframe by candidate route and visibility using the prior geometry helper. It does not replay the full already-passed fixture behavior matrix or build any images.

The parent must inspect the screenshots and retain the completed job artifacts off Forum scratch. No acceptance marker, cutover, service stop/disable, retirement, registry mutation or public publication was performed here.
