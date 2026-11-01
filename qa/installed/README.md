# Installed Search acceptance adapter (preparation, not acceptance)

Target Search bytes: `679be8ce8eea6ba13bf031104ea991202b5c373a`.
Base box: published **0.3.73**, explicitly selected, never today's mutable Stable.
No installed, visual, model-driven, ARM64 or release PASS is implied by these files.

## Reuse boundary

- **REUSE:** the existing fresh-box Lima acceptance runner; its public install, installed readback and owned-VM stop. Pass its paths and SHA-256 values in a private stage config. Do not reuse a mutable retained guest or the owner's staging instance.
- **REUSE:** shipped WAM `release_pins.configure_manager`, its read-only pin-index adapter, `wam install`, normal Runtipi packaging, the generated registry and existing agent-link wiring.
- **REUSE:** the installed shell's `?open=` URL and public `WizCore.deeplink.route` after `appsLoaded()` and `refreshApps({afterPending:true})`, existing app frame, shared app client and installed skin API. Explicit `?shell=desktop|phone` selects each shell; viewport width does not. No replacement shell, bridge, grant file, router or credentials.
- **NEW, QA only:** this bounded orchestration adapter and assertions. It invokes existing implementations; it implements no product capability.

## Run

The outcome owner's private stage config names the exact copied positional fresh helper (no base runner), Playwright installation, one-use work path/VM, source/dependency hashes and Search runtime-file hashes derived from the tested commit. Do not commit machine-specific stage paths or an owner's state. Preflight is read-only; execution must be submitted by the parent through the normal durable Linux worker:

```
FRESH_LAUNCH_HELPER=/path/to/pinned/fresh_launch.py python3 qa/installed/test_prep.py -v
node --check qa/installed/browser.cjs
python3 qa/installed/runner.py /path/to/private-stage-config.json
# Parent's durable job only, never the control-plane machine:
python3 qa/installed/runner.py /path/to/private-stage-config.json --execute
```

The full `fixtures/fresh_launch.py.txt` is a non-executed, byte-identical snapshot of the actual copied helper (SHA-256 `a78a1b08b0bea0ddd96b359e59645ad554be2e17443684f042998454e0d3ac7b`). Tests parse only its positional argv assignments and `l4-` assertion, then compare the runner-built argv; `FRESH_LAUNCH_HELPER` also compares a staged helper's bytes. Read-only preflight repeats that contract check against the configured, manifest-pinned helper, not just the snapshot.

Preflight refuses changed/symlinked dependencies, reused work, non-worker paths, missing KVM/tools, the wrong base release/Search SHA and less than **300 GiB** free. Never lower another rig's reserve or delete another owner's data to pass admission. The parent must read current storage/active owners again before submitting.

## Candidate host CLI (optional)

A private config may add `"wam_candidate": {"repo": "humanitylabs-org/wizard-app-manager", "commit": "<40 lowercase hex SHA>"}`. Missing/null leaves the baseline untouched; branches, tags, abbreviated SHAs, other repos and extra fields fail preflight. Pin `wam_candidate.py` in `files` alongside the runner and guest.

After the successful fresh 0.3.73 baseline/readback and before importing WAM in the Search phase, the guest parses the installed launcher, requires its checkout clean, fetches **only** that SHA without credentials/hooks, verifies `FETCH_HEAD`, checks out detached and verifies HEAD and the imported module path. This reuses `install.sh:102-109`: the launcher executes Python `-m wam` from the checkout, not a pip-installed package. It never runs `install.sh`, rewrites the launcher, restarts the host API or changes the baseline manager image. The later existing pin-index setup still selects the manager image from 0.3.73.

`wam-candidate.json` and the parent receipt retain requested/actual/baseline commits, source/interpreter/module paths and unchanged launcher/manager-compose hashes. Search independently verifies the candidate receipt and loaded module before `wam install`. A candidate failure remains failure; the existing finally-stop, credential stripping and no-inference guards are unchanged. This is candidate acceptance, not acceptance of unmodified published 0.3.73.

## Intended execution (not yet run)

1. Create a new guest through the existing fresh runner and install/read back 0.3.73. No owner homes, accounts or histories are imported. The helper takes `EVIDENCE_ROOT LIMA_HOME VM_NAME RELEASE`, requires `l4-`, creates the `after-install` snapshot, and stops its VM. Restart only this new guest after its successful phase receipts. It reserves host 18796 → guest 8796; the adapter uses a separate ephemeral SSH port → the raw shell port from `view.local` **if present**, otherwise `view.url` (8796). A fresh unpaired registry has no `view.local` or top-level `port`; never use a published HTTPS view port.
2. Copy the installed release pins into a separate local QA candidate snapshot and append Search at the tested SHA. Reconfigure only that guest's **existing WAM pin-index adapter** and manager. CLI-only pins are insufficient: manager lookup could otherwise replace the candidate with the current catalog. No published manifest is edited and no default is promoted.
3. Actual `wam install wizard-search`, immutable installed source readback, running image ID and hashes of runtime files. WAM retains its normal setup, recipe safety and dependency handling; failures are not bypassed.
4. In that guest's installed stock Hermes engine, discover the configured `wizard` MCP gateway and invoke its discovered Search status/web tools through `model_tools.handle_function_call`. No synthetic model, direct-app RPC replacement, account sign-in or chat/session is used. Discovery/call failure remains failure. This is **dispatcher proof**, not evidence a model selected a tool or composed a cited answer.
5. Open Search in the installed shell; verify the shared appearance handshake, real results and hidden fresh-install pause notice. Capture phone and desktop in two contrasting installed skins. Then seed **fake** paused keys via WAM's user-config helper in this guest, restart only Search, and capture the real notice under the same skins. The notice phase does not request search or inference. No response interception or HTML fixture is used.
6. Stop/reap the private SSH forward and stop the exact owned VM in `finally`; preserve logs, registry/running-byte readback, dispatcher JSON, browser receipts and screenshots. A successful script still says **pending screenshot review**. Parent visually inspects screenshots and retains small evidence durably; VM/container disks stay scratch.

## Pinned shell opening contract (0.3.73)

Source pin: `humanitylabs-org/wizard-ux@db361987f795fbbd1489ded7e19e7b66d102eeaa`.

- **Both full shells honour `?open=<id>`**, not a hash: `web/core/deeplink.js:35,65,85-90` parses, dispatches and exposes `WizCore.deeplink.route`; `web/app.js:3936-3947` and `web/desktop/desktop.js:2321-2330` register app handlers and consume the URL. The handlers retry after `appsLoaded()` on a cold registry. `?app-session=` is the separate single-app/mobile presentation (`web/install.js:11-17`, `web/core/single-app-session.js:84-94`), not the full desktop/phone acceptance surface.
- **Wait for the actual app registry, not just WosSkin.** `web/core/apps.js:83-89,115-124` loads on startup/focus, exposes `appsLoaded()`/`refreshApps()`, and accepts the Store's same-origin `wizard:apps-changed` message. An external `wam install` does not itself notify an already-open page; the launcher explicitly calls `refreshApps({afterPending:true})` (`web/app.js:1848`, `web/desktop/desktop.js:1254-1262`). This test refreshes then re-routes the public app link; it never fabricates a tile or calls private shell `openApp` functions.
- **The iframe src is the registry URL, not a fixed proxy/port pattern.** Both renderers use `WosOwnViews.frameUrl` then `w.url`/`app.url` and stamp `data-own-app` (`web/app.js:1503-1505`, `web/desktop/desktop.js:409-410`). Own screens may use `/wizard/views/<id>/`; otherwise the registered URL is retained (`web/core/own-views.js:7,13-15`). Select `iframe[data-own-app="wizard-search"]`, not an assumed substring of src. `?app-session=` wraps the presentation; it is not appended to a full-shell app iframe.
- **`type: service` does not hide a declared view.** The remote list keeps any entry with a URL and converts it to `kind: wizard`, carrying the declared service type as metadata (`web/core/apps.js:50-67,105-111`); desktop opens any such URL (`web/desktop/desktop.js:331-334`). Backend-only entries have no URL. Search's `wizard.md` declares view port 9288, path `/`; the shell uses the projected registry URL, not that container port directly.
- **A narrow headless desktop is not a phone.** `web/core/shell.js:8-11,17-36` selects by device/pointer or the supported `?shell=` override. The two viewport checks explicitly select desktop/phone and assert which shell loaded.

The previous skin-only wait and src-substring timeout saved no page state, so its exact failing page/registry cannot be recovered from that log. A fresh unpaired box also has a separate **unresolved platform risk**: Agent Service `3773ca0c:server/wizard-os-settings.mjs:245,264-269` rejects raw `http://127.0.0.1:<port>/` view URLs; candidate WAM `77078ce6:wam/links.py:244-253,371-383` publishes/replaces those with browser URLs only when Tailscale is connected. Refreshing cannot create a missing published view. The browser now fails explicitly if Search has no launchable same-origin registry URL and captures the evidence; this QA repair must not inject a registry override, add a replacement proxy, or claim installed acceptance before the remote run.

Any browser failure attempts a full-page `*-failure-<width>-<skin|boot>.png` and writes a matching small JSON before rethrowing and closing Chromium: actual href, iframe srcs, visible app IDs, registry/backend IDs, shell and deep-link log. Screenshot/evaluation failures are recorded separately rather than masking the original error. Launch failures with no page can only produce JSON. Existing successful screenshots, policy checks, two skins and shared-token checks are unchanged.

## Limits and likely seams

Only syntax and preparation-guard tests can run on the control plane. Full installation/browser execution belongs to the admitted remote job. The installed launcher's interpreter/pin layout, engine Python command, shared frame/skin selectors and actual generated gateway visibility are deliberately asserted rather than patched around. If these have changed, retain the failing phase and classify the installed/platform seam. Do not silently fall back to a custom bridge or a public provider.

The wrapper pins and copies the old fresh helper rather than rebuilding its rig. Its existing public-installer fetch is still mutable transport; it explicitly requests 0.3.73 and independently reads back installed pins. This proves requested installed versions if it passes, not byte-exact certification of today's installer.

Out of scope: a real-model answer (requires the owner-approved model), Browser reading/egress hardening, provider connector extraction, alongside and ARM64 admission, merging, publication and any live/global deployment.
