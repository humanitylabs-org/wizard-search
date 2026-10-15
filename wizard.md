---
wizard: 0.2
id: wizard-search
name: Search
type: service
category: app
version: 0.1.0-test.1
summary: Web and image search with optional cited Tinfoil overviews; operator-configured providers.
license: LicenseRef-Proprietary
source: .
icon: web/icon.png
runtime:
  kind: runtipi
  config: runtipi/config.json
  compose: runtipi/docker-compose.yml
api:
  port: 9288
  path: /api
  spec: openapi.json
mcp:
  port: 9288
  path: /mcp
  transport: streamable-http
skill: skill/SKILL.md
view:
  port: 9288
  path: /
  source:
    path: web
    build: python3 tools/check_view.py
    dist: web
provides: [web-search, image-search]
system: false
uses: []
needs: []
health: /api/health
---

# Search — private test release

No credentials or history are bundled. Start empty, then configure existing providers with
SETUP.md and setup.json. Wizard gateway supplies the shared app client and authenticated
routing. This is not a new Connections implementation. Runtime dependencies are explicit
operator settings rather than fictitious installable Wizard app IDs.
