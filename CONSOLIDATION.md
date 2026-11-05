# Consolidated Search — feature union / implementation inventory

## Exact live baselines

- Legacy source: `a9cfc284fc93087b27dee2d401baacfdfec650a9` (clean live user service, not the repository default).
- Packaged source: `e429987349b87d0c6d4973fb482c604765e2434b` (actual serving image revision; fetched `index.html`, `app.js`, `app.css`, `voice-input.js` bytes matched that commit).
- Candidate branches from the packaged source and preserves/retests the legacy feature union. Exact `git archive` parity reports must pass against **both**, with no waivers, before promotion.

## REUSE / EXTEND / NEW

**REUSE**: SearXNG sidecar and its pinned image/free default; web/image APIs and MCP; streaming cited Tinfoil overview (`gpt-oss-120b`, low reasoning); private translation (`gemma4-31b`, existing private `gpt-oss-120b` retry); read-image API and errors; image proxy, strip/grid, download/Save; setup docs and existing optional operator integrations; voice frozen context, IndexedDB request identity, conflict/retry/reload admission; shared `WizardApp.voiceInput`, `WizardApp.back`, `WizardApp.media.view`, `WizardApp.theme`; shared live kit/client resources.

**EXTEND**: recover sibling Tinfoil discovery when old install forms contain an empty endpoint; fix nested preview Tinfoil page path; restore the shared image viewer previously disabled by the package port; preserve standalone lightbox/Save and outside-tap dismissal; map existing app visuals to Appearance v1 roles with canonical dark standalone tokens, opaque text-bearing overlays, no redesign; paint query state before waiting for configuration; close stale streams; optional box-local credential-file support for existing operator-private-proxy configuration (missing file fails closed).

**NEW, deployment-only**: parent-controlled release/rollback script, an authenticated Search-only bridge to the **already approved loopback private proxy**, regression tests, isolated real-shell QA host/worker. This bridge does not inspect any private agent/container, source any personal provider key, discover providers, or choose a fallback. It only forwards `/v1/chat/completions` to an explicitly supplied loopback endpoint, allows the two established private models and never logs requests. No subscription or non-private model/provider/policy/UI has been introduced.

## Privacy and measured provider evidence

Real synthetic SearXNG web/images and real cited private streaming proof are stored outside the source checkout, not invented fixtures. On this box the approved private proxy produced its first token in **699 ms**, completion in **1994 ms**, 86 delta events; actual translation and read-image calls succeeded (the synthetic icon correctly contained no text). The installed Tinfoil app is connected and enclave-verification metadata reports its official SDK; its current `/v1` compatibility endpoint buffers output: first delta **10517 ms**, done **10518 ms**. Therefore the fast approved private proxy is retained through a narrow authenticated bridge, rather than silently switching the user onto the slower endpoint. The app-owned connection path remains supported for portable installs.

Provider credentials stayed in process memory only during the installed-app probe; none are in commits, images or evidence. No sealed agent filesystem, environment, accounts, requests, Messenger, recordings or owner query history was read.

## Union acceptance

- Web, image, cited streaming overview; unchanged private-only inference.
- Legacy voice file/database naming remains unchanged. Canonical `/wizard-search/` origin/path stays unchanged. The old preview URL remains a compatibility proxy (not a forced redirect) so its browser storage scope is not erased or silently rekeyed.
- Translation/read-image success, failures and private retry covered by focused regression tests; real provider smoke separated from mocks.
- Packaged SearXNG real web/images; voice fixture admission/retries; actual public shell/client/media/Back and phone/desktop live skin switches at Nebula and Light; standalone dark fallback. Browser AI rendering explicitly replays the separately measured real private stream, rather than claiming fixture inference is live.
- The worker must produce exact source/image/archive hashes and all screenshots. Screenshots require actual visual inspection after the worker returns.

## Known parent gate

The currently serving WAM `9309d85767203983aa18917e53660d2c968bd2aa` drops `receives_voice_input` in `wam/registry.py`, even though the installed Search manifest declares it. Do not fake `apps.json` or accept the manifest as routing evidence. `ops/registry-voice.patch` is an exact-source, non-applied correction; ship/review it in the owning WAM source/runtime and test registry regeneration durability before cutover. Parent release refuses its package step unless the supplied WAM source carries this projection. The installed runtime's registry writer must also preserve the field.
