# ADR-131 — Isolated observed publisher-link evaluation

**Purpose:** Record why a separately frozen evaluation may follow an actual official publisher anchor without rewriting a failed direct-result qualification.

Date: 2026-10-24. Status: Accepted for one isolated evaluation under the owner's request to complete outstanding work; no production activation.

The current Brave check succeeded. The subsequent first end-to-end cohort made three accepted searches, then failed `live_missing_primary_sources`: its actual RFC result was the publisher's `/info/rfc9111/` landing, whereas the unchanged direct-result oracle requires full text. That FAILED cohort and source-family policy remain unchanged.

One follow-up uses exactly the acknowledged original discovery archive, validated against its pinned owner/run journal and byte hash. Only the summary's known datetime representations are normalized for equality; original archive bytes/timestamps/queries/source IDs remain retained. This archive supplies source locations, never a live proof. There are zero new Brave queries or planner calls.

Fetch the actually returned official landing through existing DNS/public-IP/peer/TLS/body/timeout guards. Parse bounded UTF-8 HTML, reject base/duplicate attributes and ambiguous targets, and follow only a present anchor to the exact official RFC9111 HTML path. Never fabricate a child search hit. Acquire new source proofs for that child and the actually returned SearXNG document, then one CORE assessment and one native DOCX/PDF batch. Preserve original three claims/status/evidence/25-word quote oracles and 30-second source/90-second publication budgets. Reopen complete archives after issuer revocation and inspect every rendered PDF page. Original application/source/config files remain unchanged.

This adds an isolated evaluation variant, not an API/architecture/default change or automatic retry. Risks: publisher representation/link changes, additional source latency, SSRF/redirect ambiguity, archive-to-live confusion and overclaiming broad coverage. Controls restrict the publisher/path/hop/body counts, bind observed anchors to complete parent SHA, retain first failures, and distinguish this variant from direct-result qualification. Full parent HTML remains private and excluded from delivery; anchor metadata/hash binds the observation. No model, provider, collection, database or release decision changes. Missing source or incorrect assessment ends the one phase; no fallback, retry or extra campaign is scheduled.

45 isolated parser/archive controls PASS before freeze, including ownership/hash/payload tamper denial. Earlier preflight failures are retained. [Exact freeze](../evidence/web003-linked-publication-pre-inference-freeze.json). Any future product integration requires its own reviewed implementation, tests and ADR impact assessment; this experiment does not imply that integration is accepted.
