# Wizard Search

Private web and image search that works on install. The Compose file runs an unmodified, digest-pinned
SearXNG metasearch sidecar (AGPL-3.0, https://github.com/searxng/searxng) on the app network only; it
needs no account or key and gets a fresh random secret on every start. Packaged without owner keys,
history or automatic home-directory configuration.
See [SETUP.md](SETUP.md) for operator setup, [setup.json](setup.json) for machine-readable
requirements, [openapi.json](openapi.json) and [skill/SKILL.md](skill/SKILL.md) for agent use.
Python 3.12+ standard library and curl; no Python packages. Wizard supplies the shared client,
authenticated proxy and Back/Appearance. Use `app/Dockerfile` with repository-root context.
`runtime.package: build` lets App Manager build that pinned source on either CPU architecture;
curl and CA certificates come from the distro packages in the digest-pinned Python base.
Image binds 9288 internally; never publish it on a public interface. The service is single-owner,
not an Internet multi-tenant API. API health is liveness, not paid-provider readiness.

Build: `docker build --build-arg REVISION=$(git rev-parse HEAD) -f app/Dockerfile -t wizard-search:test .`
Tests: `python3 -m unittest discover -s tests -v`; `python3 tools/check_view.py`.
Run API-only: `docker run --rm --read-only -p 127.0.0.1:19288:9288 wizard-search:test`.
A bare app port without Wizard's shared resource is intentionally not a complete browser preview.
No volume is required: caches are memory-only and reset on restart. No seed or owner data ships.
Runtime environment belongs to the operator's private store, and must be retained when upgrading.
