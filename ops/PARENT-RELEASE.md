# Parent-controlled Search release (NOT executed by the builder)

`parent-release.py` is executable control-plane material, not proof that production has changed. It never uninstalls anything, never edits `apps.json`, and changes state only with `--execute`. Retain the protected backup folder. Do not run package until the queued image/browser job passes and screenshots have been inspected.

## Prerequisites / exact route

1. Copy the worker's `artifact-manifest.json` and the named image tar (verify its SHA256) into the durable release directory. Use the **clean pushed candidate checkout** for the operator script, not a worker directory containing synthetic fixtures.
2. The WAM registry projection omits `receives_voice_input`. The exact-source review and minimal activation/rollback route are now in `WAM-VOICE-REVIEW.md`, with pushed host/runtime-source branches and repeated-regeneration regressions. Both executable host copies (API source and the managed CLI builder bundle) must preserve the bool. The queued repair job tests both source baselines and a one-file-only managed builder distribution in isolated homes. Do not patch `apps.json` or mutate a sealed release. Regenerate through both entrypoints and read `/wizard/v1/apps` back after parent activation; this remains a real platform gate, not a waiver.
3. The fast approved private proxy at loopback `3301` must still work. The bridge now requires **two distinct credentials**: the existing Search-only caller token and an explicitly supplied upstream provider token file, regular mode 0600, at most 8192 bytes. The parent provisions that file from the already-approved main legacy Search provider configuration; neither helper discovers accounts, reads environment files, or inspects private agents/containers. Caller Authorization is never forwarded. Redirects fail closed so the provider credential cannot follow another endpoint. No provider/model substitution is permitted. See `BRIDGE-AUTH-REPAIR.md` for a bridge-only repair of an already packaged release; do not rerun package for that case.
4. Set these control-plane variables from the recorded live discovery (all paths are operator inputs; no personal keys/machines are packaged):

```sh
SOURCE=/path/to/clean/pushed/candidate
RELEASE=/path/to/durable/consolidated-search-release
WAM_SOURCE=/path/to/reviewed/voice-projection-capable/wam/source
ROUTES=/path/to/the/serving/private-routes.json
UPSTREAM_TOKEN_FILE=/path/to/protected/approved-upstream-token
/usr/bin/python3 "$SOURCE/ops/parent-release.py" package --release "$RELEASE" --wam-root "$WAM_SOURCE" --routes "$ROUTES" --upstream-token-file "$UPSTREAM_TOKEN_FILE"
# Above is a DRY RUN. Only the parent adds --execute.
```

The real lifecycle interfaces were checked against installed App Manager revision `9309d85767203983aa18917e53660d2c968bd2aa`: authenticated `GET /apps/search-preview:wizardapps`, `PATCH /app-lifecycle/.../update` with `{performBackup:true}`, `PATCH .../update-config` with complete preserved form flags, and request receipt waiting. The existing package uses loopback `19289`, service `search-preview`, a Search-only `search-data` named volume, and a bundled SearXNG sidecar. These identities are deliberately retained, avoiding a needless app-ID/data migration. Source app name is simply **Search**; its legacy technical install ID is not shown to the owner.

## Package (parent only)

```sh
/usr/bin/python3 "$SOURCE/ops/parent-release.py" package --execute --release "$RELEASE" --wam-root "$WAM_SOURCE" --routes "$ROUTES" --upstream-token-file "$UPSTREAM_TOKEN_FILE"
```

This snapshots both installed/store recipes and pins, Search-only lifecycle row/config, Search's `/data`, owner route/launcher source metadata and any previous bridge unit into `parent-backup` mode 0700. Sensitive state stays in that local protected folder, never source/images. It loads the exact built image (no VPS build), retains existing service/volume identities, starts a narrowly authenticated bridge bound only to Search's existing Docker gateway, then uses WAM lifecycle update and regenerates the registry. The legacy root and service are still intact. No source of credentials is read from a private agent.

Package validates the explicit upstream file before its first production write, then saves a mode-0600 copy as `parent-backup/upstream-token`; only this file path is placed in the bridge unit. The app container receives only the Search caller token, never the upstream credential. Existing source/image binding gates remain unchanged.

Verify the candidate at the old preview URL through the actual gateway on phone/desktop/two skins, real web/images, real private cited stream, shared media Back/root/outside tap, voice routing/retries, translation and read-image failures. Check actual image revision, model `gpt-oss-120b`, low reasoning request evidence and first-token timing. Read back `/wizard/v1/apps`; manifest declaration alone is insufficient. Only after those checks create `parent-acceptance.json` containing exactly `{"verified":true,"sha":"<manifest source_sha>"}` in RELEASE.

## Cutover, then retirement (parent only)

```sh
/usr/bin/python3 "$SOURCE/ops/parent-release.py" cutover --execute --release "$RELEASE" --wam-root "$WAM_SOURCE" --routes "$ROUTES"
# Verify the one remaining Search on James's desktop and phone, then:
/usr/bin/python3 "$SOURCE/ops/parent-release.py" retire-legacy --execute --release "$RELEASE" --wam-root "$WAM_SOURCE" --routes "$ROUTES"
```

Cutover updates the supported owner routes source and serving private route adapter, keeps `/wizard-search/` canonical and `/wizard-search/preview/` compatible, regenerates the WAM registry, verifies the surviving packaged Search voice flag/name, then removes only the obsolete `wizard-search` legacy launcher link. This is **not** an app uninstall. Retirement merely stops the old user service after a verified cutover receipt. Old checkout, original image and data remain for rollback. No merge, public catalog publication, external message, or unrelated app change is part of this route.

## One-command rollback

```sh
/usr/bin/python3 "$SOURCE/ops/parent-release.py" rollback --execute --release "$RELEASE" --wam-root "$WAM_SOURCE" --routes "$ROUTES"
```

This stops the bridge, restores the exact saved recipes/pins/routes/launcher and prior lifecycle configuration through `update-config`, regenerates the registry, restarts the route adapter and legacy service, and checks the original packaged revision plus legacy-root health. Search's browser site data is never cleared. The protected `search-data.tar` is retained as an additional model-blind recovery copy; the normal rollback does not overwrite newer owner settings unnecessarily.

**Current status:** the builder did not execute any of these production actions. The WAM voice fix, image/browser receipt, visual inspection and parent-owned deployed-device verification are mandatory gates. The helper is syntax/dry-run tested, not a production rehearsal claim.

## Static review of the parent helper

- **Reused-image binding is already explicit:** `source_sha` is the pushed QA/operator candidate; `image_source_sha` remains `7fac0ebc6ce22ff951b5fc6738a41b7d40a9456b`. When they differ, package requires `runtime_bytes_identical`, the complete current runtime-input inventory and every SHA256; Docker ID and actual OCI revision are checked independently. No relabel/rebuild is needed for this oracle-only repair. `qa/operator-contract-test.py` executes this actual binding block against the recorded map and rejects changed/missing/extra bytes.
- Registry regeneration explicitly selects the provided WAM source, owner OS home and Runtipi root through its subprocess environment; it cannot accidentally inherit another `PYTHONPATH`/home. Retirement requires an exact candidate-bound cutover receipt and the package receipt's verified effective image ID, rather than any stale `verified:true` receipt.
- **Cross-Docker identity is content-bound, not label-only:** `ops/image_archive_identity.py` verifies the archive SHA256, unique exact Docker-save tag and matching OCI tagged descriptor, manifest/config blob digests and sizes, tested config ID, linux/amd64 platform, source revision, ordered layer descriptors and actual layer bytes against config rootfs diff IDs. This deliberately supports the reviewed dual Docker-save/OCI archive with uncompressed layers; other layouts fail closed. Docker may report either that verified config ID or its verified OCI image-manifest ID. Loaded platform/rootfs and every archived image-config field must also match. Package records both identities plus the actual effective ID; retirement revalidates the graph and running image against that exact receipt. `qa/image-archive-identity-test.py` exercises both representations and corrupt/incorrect graph, tag, config, platform, layer and stale-receipt cases using tiny stdlib tar fixtures, without Docker or production writes.
- **A failed partial snapshot is immutable rollback material:** never delete or reuse its `parent-backup`. After checking original serving revision and saved recipe/routes/launcher targets still match, prepare a fresh durable release directory with a new operator `source_sha`, retained `qa_source_sha`/`image_source_sha`, the unchanged complete runtime hash map, and checksum-identical image/evidence. The image tar may be hardlinked, not rebuilt or relabeled. The operator takes a new backup when the parent executes package. Retained QA proves the earlier app bytes only; focused operator tests prove this control-plane delta, not a full QA rerun.
- `ops/wam-voice-activate.py` and the commands in `WAM-VOICE-REVIEW.md` provide the narrow host API + managed CLI activation/rollback route. They do not replace the Node App Manager image, touch an agent or declare deployed registry success.
- **Rollback constraints still require operator review before package:** the Search helper snapshots/restores entire route/launcher files and Search recipe directories. Do not run it across concurrent unrelated edits; compare those files before restoring, or merge only Search-owned entries. A pre-existing bridge unit/token is not an exercised case: rollback disables the bridge and removes `/data/private-proxy-token` rather than restoring its previous operational state/content. If either exists, stop and extend the exact restore handling before package. The protected full Search data tar is a recovery copy, not proof that this case is automated.
- The hard-coded old package revision, port/service/volume identities and loopback private proxy remain live-drift prerequisites, not newly revalidated facts. Partial package/cutover failure leaves protected recovery material; it is not automatic transactional rollback. No activation or rollback was rehearsed here.
