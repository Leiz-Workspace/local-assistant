# D30-T03 — Explicit message memory selection and retention

**Purpose:** Describe implemented opt-in source-literal memory extraction, owner export and bounded expiry cleanup with honest acceptance limits.

**Status:** D30 PASS locally. Focused147 PASS/6.91s,0 SKIP; final full1570 PASS/1357.69s (22:37),0 SKIP, exit0. Clean [post-audit](../evidence/d30-final-post-audit.json) and [acceptance](../evidence/d30-memory-acceptance.json). [ADR-047](../ADR/047-explicit-message-memory-selection-and-retention.md), [export ADR-048](../ADR/048-owner-memory-export.md). D30 remains open.

## Explicit extraction

The existing operator flag `ASSISTANT_MEMORY_ENABLED=1` exposes local authenticated memory controls. It defaults off. Each owner must separately enable memory and extraction and grant a current receipt with `allow_extraction=true`. No automatic transcript/file scan or model call occurs on startup. Only one nonqueued extraction is admitted per app instance.

POST `/api/v1/memory/extractions` accepts only `consent_id`, `conversation_id`, `message_id`. The source must be one actual user message in an active conversation owned by the authenticated principal; assistant/system, legacy unowned, foreign or deleted conversations are refused before model inference. Session receipts must name that same conversation. Source text is complete and at most8192 UTF-8 bytes; no truncation. File-evidence schemas are structural future contracts; file-to-memory is assessed in [backlog](MEMORY_BACKLOG.md).

Existing CORE/fast, temperature0, output512 and a60-second client model deadline select one unique literal source quote, or return explicit insufficiency. Output is strict JSON, at most8192 UTF-8 bytes; selected quote at most2048. Duplicate/extra keys, nonfinite values, ambiguous/normalized/absent quotes and incomplete completions are refused. Source text and model output remain untrusted. A literal quote establishes provenance, not factual truth, correct memory classification or permission to follow its instructions.

The server stores the quote itself, actual producer ID, source IDs/hash and exact Unicode code-point offsets. SQL rechecks current source ownership/content and receipt/settings/expiry before capture, then rechecks source/consent/record version immediately before response headers. No SQL locks remain held during model inference. Disable/revoke commits before cancelling/joining matching live requests. Source changes after the final authorization point are ordered after it; socket delivery is not a distributed transaction.

A successful response reports `captured` and a bounded record, or `insufficient_evidence` and null record. Both carry `content_trust=untrusted`. Final drift returns409 without the selected quote. Busy429, oversized source413, missing/foreign source404, disabled extraction403, stale consent409, model deadline504 and sanitized unavailable/invalid output503. Private/no-store/nosniff headers apply. Source failure is not silently converted into a manual memory or a different model.

Owned SQL/model child work is shielded and joined even under repeated parent cancellation. Response ownership lasts through ASGI delivery; shutdown joins extraction/retention/manual work before the shared pool closes. This does not certify immediate cancellation or cache erasure inside the existing shared CORE server.

## Owner export and expiry

GET `/api/v1/memory/export` explicitly downloads `memory-export.json`: format `local-assistant-memory-v1`, observation time, own settings, all retained receipts and full records. It remains available while the owner is disabled or consent is inactive. A read-only repeatable-read snapshot prevents mixed multi-query states. Missing settings stay inert revision0; no implicit consent or model call. Owner caps1000 receipts/1000 records and12MiB encoded UTF-8 JSON; overflow refuses rather than truncates. Export includes retained provenance, not original transcripts/files/vectors/keys. Already delivered exports cannot be recalled.

Enabled startup owns one periodic retention worker on the existing app pool. Each cycle visits at most10 owners, deletes at most100 expired records and100 orphan inactive receipts per owner, then advances a UUID cursor; empty page resets cursor. Default interval30 seconds. Expiry applies while owner use is disabled. Referenced unexpired records/receipts, source/history and vectors are retained. The worker joins its SQL child during cancellation/shutdown. Bounded eventual cleanup does not guarantee expiry-to-purge latency under downtime/load; expiry already denies use/write even before physical purge.

## Recorded checks and remaining gates

Focused147 PASS/6.91s,0 SKIP includes exact Unicode/JSON/budget/strictness, controlled model cancellation/timeout and delivery faults, actual SQL source/consent races and worker cleanup, authenticated owner controls/export, actual CORE English/Vietnamese selection and greeting insufficiency, foreign refusal before model and real ephemeral TCP. Four actual CORE calls use same-agent synthetic sources. Controlled ports are explicitly distinguished from actual inference; no independent human/model-wide quality, production load or privacy certification is implied.

Initial JSONB UUID strict-decoding failure was corrected only at the tagged database codec boundary, with five regression cases; applied V005 is unchanged. Initial live2 FAIL/10 setup errors were retained: restarted environment had sealed Vault/loading CORE and standalone fixture discovery was missing. Existing Vault keys/runtime recovered without rotation/new model/config changes; fixture import fixed. Export6 PASS/1 FAIL was an oracle comparing equivalent UTC spellings, corrected to compare aware instants. Original failure logs remain protected.

Final full1570 PASS/0 SKIP and clean post-audit establish D30 local acceptance. Old owners/ACLs, applied V005 and protected models/config/dependencies remain unchanged; source/memory/quota/probe/vector/worker/lock inventories0. D31 independently verifies injection, source deletion and export/purge propagation; no memory-to-prompt or vector-memory feature exists. Disable/drain the operator feature for rollback while retaining journal/data; never downgrade populated memory tables. Preserve original model choices, approved embedding and exact E5 rollback.


## D31 source privacy checkpoint

[Transactional source repair](D31_PRIVACY_AND_DELETION.md) is now locally accepted under ADR-049/V006:271 final related plus140 source-system PASS/0 SKIP and clean audit. Enabled memory now requires0006; files/ingestion admit reviewed0006 while keeping existing grant checks. Applied V005 and prior acceptance entries remain historical/unchanged. Source deletion/edit removes dependent extracted records atomically; independent explicit manual preferences remain. D31-T02 and final full-day acceptance remain open.
