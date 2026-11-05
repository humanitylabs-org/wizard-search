# First Forum run: bounded repair handoff

The admitted job `heavy_b41c6a41d90848b8ae3718eabe55d593` built the Search image and passed units, view syntax and bridge fixture, then failed on the first real packaged search HTTP 502. It did not retain that HTTP error body or sidecar logs. Therefore the provider failure's exact cause is **not yet proven**. `/api/health` only reports present settings, not reachable providers; treating it as readiness was a definite QA flaw.

This repair does not change `server.py`, any web asset, Docker inputs or the runtime compose recipe. It does not disable the failing real check, replace the provider or add AI fallbacks.

## Executable changes

- Wait up to 60s for both app health and the actual bundled SearXNG HTTP root, then require useful real web and image results. Each synthetic query has at most three attempts inside one 100s budget; all attempts persist status, elapsed time, body/error and projected results before another attempt or exception. Nonempty but invalid/unrelated arrays fail.
- Before every compose teardown, collect only this job's compose status, bounded app/sidecar logs, and direct synthetic sidecar queries with result counts, engine failures and five sample rows. Distinguish boot/crash, 403/format, empty engine results and app relevance/projection errors from the evidence. No credentials, private agent env/mounts/content or owner history are read.
- Reuse the existing exact image and tar only when its manifest digest, actual Docker ID/revision, and every build/runtime input hash match the original pushed source. Do not retag/relabel the old image as a new commit. `source_sha` identifies the repaired QA/operator source; `image_source_sha` remains the original runtime source. The parent helper verifies the byte map before accepting that distinction.
- Run new diagnostic regression tests, both exact WAM source regressions and an isolated managed one-file builder update, then existing Search units, bridge fixture, real provider checks, voice fixture and copied-public-shell browser matrix. Browser shell/registry APIs remain synthetic, not live owner acceptance. Private AI rendering remains a replay of the separate real provider proof.

## Immutable reused runtime

- Runtime source: `7fac0ebc6ce22ff951b5fc6738a41b7d40a9456b`.
- Image: `wizard-search:7fac0ebc6ce22ff951b5fc6738a41b7d40a9456b-amd64`.
- Image ID: `sha256:4e1ec215f2a3c8a7acb2f1aff6448271c6cb6305b41413af44cdaa4b29e2f532`.
- Archive retained in `/srv/work/search-consolidated-7fac0ebc6ce2/` as `wizard-search-7fac0ebc6ce22ff951b5fc6738a41b7d40a9456b-amd64.tar`; SHA256 `0dfec19c294e4355c98b975705573c2a0d0010bf56a33865bd118e3fe4dceeb0`.

## Parent collection / remaining gates

The new stage and exact submit payload are in the durable `repair-job.json`; parent submits via exposed `wizard_heavy_submit`, Forum/light, 900s. This helper does not submit or run a heavy job directly. The worker has an internal 650s alarm so diagnostics/cleanup run before the outer deadline. Its source `SOURCE_SHA`, archive hashes and input manifests are included in `repair-preparation.json`.

Collect `evidence/{packaged-readiness.json,packaged-live-search.json,startup-readiness.json,compose-state.txt,compose-provider.log,sidecar-query-diagnostic.jsonl,worker-failure.json}` (the last only on failure), all WAM logs/receipts, browser artifacts and `artifact-manifest.json`. Copy the **original** named image archive from the prior stage, rather than looking for a needlessly regenerated tar in the repaired stage.

No real search, WAM regression, browser or visual success is claimed for this repair until that admitted job returns. If real search still fails, the new diagnostic evidence is the result, not permission to skip the check. Parent still owns screenshot inspection, voice-registry activation/readback, live source re-resolution and deployed desktop/phone verification. No production action was executed.
