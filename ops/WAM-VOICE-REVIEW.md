# Narrow WAM voice-projection source review (not activated)

## Identities re-resolved, control-only

- Active `wizard-app-manager-api.service` executes `/usr/bin/python3 -m wam serve` from immutable source `319650ad9976644c63790d505e06ce923a84b3f6`, not the earlier `c4b6f84...` snapshot.
- Host `wam` CLI executes the managed builder bundle `0934bfcb8dcbe6868e49aa618d002fc3e3e11a3b7d0f731ebc02161e564a5f78`. Its `wam/registry.py` SHA256 is `3a5b8335f6adf6864fc43253195e30684ecb46853515e2b572392bbb014eca38`, exactly the API source registry file. **Both executable host copies must move.** Updating just the API working directory leaves CLI regeneration broken.
- Installed `runtipi` App Manager image labels still identify source `9309d85767203983aa18917e53660d2c968bd2aa`. Its source `wam/registry.py` is identical at these baselines. The Node `WizardStorage.writeGrants` mirror writer preserves the entire parsed registry via object spread and changes only grants; it does not reconstruct the app capability fields. This source inspection is not a claim of deployed voice acceptance.
- Current upstream `main` (`58eb02d70d79087f2599b99e98a9204125b6d295` at review) still lacks the Python projection. No broad main upgrade is needed or proposed.

## Reviewed named changes

Repository `humanitylabs-org/wizard-app-manager`:

- API/host base 319650a: `fix/registry-voice-projection-20261105`, SHA `975fcbd37a84f0a79bd593db317f27b500a2cac6`.
- Installed image's source base 9309d85, without the four unrelated host-only source changes: `fix/runtime-registry-voice-20261105`, SHA `9cc81b082c396c25db4863b49888d916c4c6d791`.

Both contain exactly the same one-line production change in `wam/registry.py`, plus `tests/test_registry_voice_input.py`. Literal YAML boolean true alone grants admission (`is True`); false, absent, string true, integer 1 and null do not. The regression exercises build, public projection, two complete on-disk regenerations, and removal of the declaration to reject stale true. Tests run only against throwaway installed-app/home fixtures. The queued repair job runs against both source baselines and a minimally patched builder distribution. No manual `apps.json` patch.

## Minimal parent route / rollback (instructions only)

After the queued WAM tests pass:

1. Preserve current systemd drop-in, API working directory and builder/current target. Re-resolve them again; stop on drift.
2. Extract the exact reviewed **host** source archive into a new immutable release directory named with its SHA. Do not edit `319650a...` or another sealed active release.
3. Point a new narrow API service drop-in at the new release; reload/restart only `wizard-app-manager-api.service` when the parent authorizes activation. Keep the old drop-in for rollback.
4. For the CLI, use the existing managed `wam.builder_bundle.install` with `source=<staged wam-builder-source>` from the reviewed host source. That staged source is a copy of the current public builder distribution with **only** `wam/registry.py` replaced by the reviewed file. The job exercises installation in an isolated home and asserts exact one-file distribution delta. Do not call `fresh`, pass a Hermes home, inspect agent runtime mounts, or restart an agent. Do not replace a sealed bundle file in place.
5. Regenerate using the reviewed source through the supported WAM API/CLI; read back only the Search row of `/wizard/v1/apps`, requiring literal boolean true. Repeat regeneration from both executable host entrypoints and the normal lifecycle/mirror path. This remains a parent acceptance gate. The Node image need not be replaced merely to apply the host projection; if the parent finds a separate reconstructing runtime writer, stop and identify it rather than assuming the prepared source branch is deployed.
6. Rollback: restore the API drop-in, daemon-reload/restart the same service; invoke managed `builder-bundle rollback --revision 0934bfcb8dcbe6868e49aa618d002fc3e3e11a3b7d0f731ebc02161e564a5f78`; regenerate and read back. Retain both immutable releases.

No activation, route mutation, service retirement, registry regeneration, agent inspection or merge was performed while preparing this change. Static scope review is complete; queued execution/readback are not yet claimed.
