---
wizard: 0.2
id: wizard-search
name: Search
type: service
category: app
version: 1
summary: Private web and image search using configured providers.
source: .
receives_voice_input: true
view:
  port: 9288
  path: /wizard-search/
provides: [web-search, image-search]
system: false
uses: []
needs: []
health: /wizard-search/api/health
---

# Search — Receives voice input

The shared Wizard client delivers a transcript to Search, not Chats. The frozen
recipient includes query, tab, and up to five bounded result references. Spoken
text becomes a new literal query in that tab (300 characters maximum); there is
no extra intent model or implicit follow-up rewriting. Voice requests use only
the existing web or images API; type a query for the existing full overview flow.

Browser IndexedDB durably stores admission identity, query/context and results.
Same-ID/same-payload retries do not search again, including after reload and
between same-origin frames. Conflicting payloads and unavailable storage reject
admission so the shell retains the input. An accepted request interrupted by a
reload is shown as interrupted, never automatically retried: type a new query
to try again. Browser site-data deletion clears these receipts; this is not a
cross-device server ledger. Receipts are not automatically evicted.

This manifest describes the existing local serving layout, not the portable
package. When porting onto the private package candidate, retain its full
manifest and add only `receives_voice_input: true`.
