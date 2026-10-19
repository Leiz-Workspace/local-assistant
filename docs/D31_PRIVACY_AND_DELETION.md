# D31 — Privacy, injection, export and deletion

**Purpose:** Track actual local privacy acceptance and distinguish source-derived data removal from independent records and retained recovery copies.

**Status:** D31 IN PROGRESS; T01 source repair PASS locally. Final271 related PASS/11.00s and140 source-system PASS/216.58s,0 SKIP; [acceptance](evidence/d31-t01-source-acceptance.json), [clean audit](evidence/d31-t01-final-post-audit.json). Initial3 source failures retained. D31-T02 injection/export/purge and final full regression pending; no1599-case full run claimed.

## Source privacy repair

[V006 rollout](evidence/d31-t01-v006-rollout.json) adds two invoker-security trigger functions, two triggers and partial provenance lookup indexes. No old migration or data rewrite, new app authority, model/configuration/dependency/credential change. All11 old data-table fingerprints and schema/table/column ACLs match before/after; a fresh protected restore verifies exact function/trigger definitions and permissions. Populated memory inventory refuses rollout pending a separate audited plan. Current local memory was empty before application.

| Operation | Source and dependent memory behavior |
|---|---|
| Conversation soft-delete, hard-delete or owner change | In the same transaction remove its exact message-provenance memory, session-scoped records and now-orphan session receipts |
| Message delete or content/role/conversation/id change | In the same transaction remove only exact previous message/conversation provenance |
| No-op content, ordering/title change or archive alone | Keep independent explicit memory; existing active-source checks still deny new extraction from archived conversations |
| Explicit PATCH of a preference to manual content | Creates manual provenance/no model ID; this independent owner decision survives later source deletion |
| Independent manual record or another conversation/principal | Retain it; source mutation does not grant authority to delete unrelated storage |
| Disabled owner or memory runtime | Database source triggers remain active; they do not depend on an extraction worker or owner flag |

Source updates and their dependent removal either commit together or both roll back. Capture retains the accepted global/owner/receipt/conversation/message ordering; triggers do not acquire new owner/global locks afterward. A real concurrency test observes PostgreSQL `Lock` before releasing capture, then verifies that the later source change removes the just-committed copy. SQL failure/deadlock cannot acknowledge a partially committed privacy operation. Controlled inference is explicitly a persistence/lifecycle fixture, not actual model-quality evidence.

The app cannot directly EXECUTE these trigger functions; they are invoker-only, use fixed search_path/qualified tables and no dynamic SQL or definer privilege. Server logs contain only source kind/counts. Runtime files/ingestion admit reviewed0006 with existing immutable-grant checks; enabled memory requires0006 and rejects known0005 gaps/unknown later revisions. Default features remain off.

## Deletion domains and remaining work

D15 conversation DELETE remains **soft-delete**: hidden transcript rows are retained according to that accepted API; V006 does not promise secure erasure of original history. D30 per-record memory DELETE is a physical record deletion, separate from the original source. Consent revocation/owner disable deny use and new capture; explicit retained-data inspection/export/delete remain available. Mandatory expiry cleanup is eventual and bounded.

Memory export is a read-only repeatable-read owner snapshot. A snapshot ordered before concurrent deletion can contain earlier retained data; already-delivered owner exports cannot be recalled. File deletion has separate journal/tombstone, vector cleanup and physical private blob gates; D31 must verify their actual composition rather than infer it from a successful HTTP status. There is no file-to-memory adapter or memory-vector collection to claim purged.

Protected backups/WAL, already-delivered exports, shared model context/KV cache and forensic disk erasure are distinct retention domains. No SQL DELETE test certifies their erasure. Any permanent transcript purge/backup lifecycle expansion must be separately assessed and scheduled; it is not silently added to the accepted soft-delete endpoint.

D31 remains open for negative injection/export/privacy composition, actual file DB/vector/blob removal and final full regression/post-audit. Preserve agreed models and historical failed evaluations; no user labeling or model replacement is required.
