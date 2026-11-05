# Parent-controlled Search release (NOT executed by the builder)

`parent-release.py` is executable control-plane material, not proof that production has changed. It never uninstalls anything, never edits `apps.json`, and changes state only with `--execute`. Retain the protected backup folder. Do not run package until the queued image/browser job passes and screenshots have been inspected.

## Prerequisites / exact route

1. Copy the worker's `artifact-manifest.json` and the named image tar (verify its SHA256) into the durable release directory. Use the **clean pushed candidate checkout** for the operator script, not a worker directory containing synthetic fixtures.
2. The current WAM registry projection omits `receives_voice_input`. Review `registry-voice.patch` against the exact WAM source and ship the narrow projection in **both** the active host registry writer and installed App Manager/runtime writer; a manual `apps.json` patch is not a fix. Test regeneration and read `/wizard/v1/apps` back. This is a real outstanding platform gate, not a waiver.
3. The fast approved private proxy at loopback `3301` must still work. No inspection of its owning private agent/container is needed or permitted. The release helper only reaches its previously authorized HTTP inference interface. The installed Tinfoil app alternative was verified but buffers output for roughly ten seconds, so it is not silently substituted.
4. Set these control-plane variables from the recorded live discovery (all paths are operator inputs; no personal keys/machines are packaged):

```sh
SOURCE=/path/to/clean/pushed/candidate
RELEASE=/path/to/durable/consolidated-search-release
WAM_SOURCE=/path/to/reviewed/voice-projection-capable/wam/source
ROUTES=/path/to/the/serving/private-routes.json
/usr/bin/python3 "$SOURCE/ops/parent-release.py" package --release "$RELEASE" --wam-root "$WAM_SOURCE" --routes "$ROUTES"
# Above is a DRY RUN. Only the parent adds --execute.
```

The real lifecycle interfaces were checked against installed App Manager revision `9309d85767203983aa18917e53660d2c968bd2aa`: authenticated `GET /apps/search-preview:wizardapps`, `PATCH /app-lifecycle/.../update` with `{performBackup:true}`, `PATCH .../update-config` with complete preserved form flags, and request receipt waiting. The existing package uses loopback `19289`, service `search-preview`, a Search-only `search-data` named volume, and a bundled SearXNG sidecar. These identities are deliberately retained, avoiding a needless app-ID/data migration. Source app name is simply **Search**; its legacy technical install ID is not shown to the owner.

## Package (parent only)

```sh
/usr/bin/python3 "$SOURCE/ops/parent-release.py" package --execute --release "$RELEASE" --wam-root "$WAM_SOURCE" --routes "$ROUTES"
```

This snapshots both installed/store recipes and pins, Search-only lifecycle row/config, Search's `/data`, owner route/launcher source metadata and any previous bridge unit into `parent-backup` mode 0700. Sensitive state stays in that local protected folder, never source/images. It loads the exact built image (no VPS build), retains existing service/volume identities, starts a narrowly authenticated bridge bound only to Search's existing Docker gateway, then uses WAM lifecycle update and regenerates the registry. The legacy root and service are still intact. No source of credentials is read from a private agent.

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
