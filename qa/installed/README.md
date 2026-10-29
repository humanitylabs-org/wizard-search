# Installed Search acceptance adapter (preparation, not acceptance)

Target Search bytes: `679be8ce8eea6ba13bf031104ea991202b5c373a`.
Base box: published **0.3.73**, explicitly selected, never today's mutable Stable.
No installed, visual, model-driven, ARM64 or release PASS is implied by these files.

## Reuse boundary

- **REUSE:** the existing fresh-box Lima acceptance runner; its public install, installed readback and owned-VM stop. Pass its paths and SHA-256 values in a private stage config. Do not reuse a mutable retained guest or the owner's staging instance.
- **REUSE:** shipped WAM `release_pins.configure_manager`, its read-only pin-index adapter, `wam install`, normal Runtipi packaging, the generated registry and existing agent-link wiring.
- **REUSE:** the installed shell's `?open=` path, existing app frame, shared app client and installed skin API. No replacement shell, bridge, grant file, router or credentials.
- **NEW, QA only:** this bounded orchestration adapter and assertions. It invokes existing implementations; it implements no product capability.

## Run

The outcome owner's private stage config names the exact copied fresh helper/base runner, Playwright installation, one-use work path/VM, source/dependency hashes and Search runtime-file hashes derived from the tested commit. Do not commit machine-specific stage paths or an owner's state. Preflight is read-only; execution must be submitted by the parent through the normal durable Linux worker:

```
python3 qa/installed/test_prep.py -v
node --check qa/installed/browser.cjs
python3 qa/installed/runner.py /path/to/private-stage-config.json
# Parent's durable job only, never the control-plane machine:
python3 qa/installed/runner.py /path/to/private-stage-config.json --execute
```

Preflight refuses changed/symlinked dependencies, reused work, non-worker paths, missing KVM/tools, the wrong base release/Search SHA and less than **300 GiB** free. Never lower another rig's reserve or delete another owner's data to pass admission. The parent must read current storage/active owners again before submitting.

## Intended execution (not yet run)

1. Create a new guest through the existing fresh runner and install/read back 0.3.73. No owner homes, accounts or histories are imported. Restart only this new guest.
2. Copy the installed release pins into a separate local QA candidate snapshot and append Search at the tested SHA. Reconfigure only that guest's **existing WAM pin-index adapter** and manager. CLI-only pins are insufficient: manager lookup could otherwise replace the candidate with the current catalog. No published manifest is edited and no default is promoted.
3. Actual `wam install wizard-search`, immutable installed source readback, running image ID and hashes of runtime files. WAM retains its normal setup, recipe safety and dependency handling; failures are not bypassed.
4. In that guest's installed stock Hermes engine, discover the configured `wizard` MCP gateway and invoke its discovered Search status/web tools through `model_tools.handle_function_call`. No synthetic model, direct-app RPC replacement, account sign-in or chat/session is used. Discovery/call failure remains failure. This is **dispatcher proof**, not evidence a model selected a tool or composed a cited answer.
5. Open Search in the installed shell; verify the shared appearance handshake, real results and hidden fresh-install pause notice. Capture phone and desktop in two contrasting installed skins. Then seed **fake** paused keys via WAM's user-config helper in this guest, restart only Search, and capture the real notice under the same skins. The notice phase does not request search or inference. No response interception or HTML fixture is used.
6. Stop/reap the private SSH forward and stop the exact owned VM in `finally`; preserve logs, registry/running-byte readback, dispatcher JSON, browser receipts and screenshots. A successful script still says **pending screenshot review**. Parent visually inspects screenshots and retains small evidence durably; VM/container disks stay scratch.

## Limits and likely seams

Only syntax and preparation-guard tests can run on the control plane. Full installation/browser execution belongs to the admitted remote job. The installed launcher's interpreter/pin layout, engine Python command, shared frame/skin selectors and actual generated gateway visibility are deliberately asserted rather than patched around. If these have changed, retain the failing phase and classify the installed/platform seam. Do not silently fall back to a custom bridge or a public provider.

The wrapper pins and copies the old fresh helper rather than rebuilding its rig. Its existing public-installer fetch is still mutable transport; it explicitly requests 0.3.73 and independently reads back installed pins. This proves requested installed versions if it passes, not byte-exact certification of today's installer.

Out of scope: a real-model answer (requires the owner-approved model), Browser reading/egress hardening, provider connector extraction, alongside and ARM64 admission, merging, publication and any live/global deployment.
