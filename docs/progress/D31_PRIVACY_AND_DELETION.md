# D31 — Privacy, injection, export and deletion

**Purpose:** Track actual local privacy acceptance and distinguish source-derived data removal from independent records and retained recovery copies.

**Status:** PASS for documented local privacy scope. Full1608 PASS/1361.93s (22:41),0 SKIP completed2026-10-19; frozen252 files match and fresh2026-10-20 audit passes after external restart. [Final acceptance](../evidence/d31-privacy-acceptance.json), [post-audit](../evidence/d31-final-post-audit.json). Initial failures retained; no full rerun after reboot claimed.

## Source privacy repair

[V006 rollout](../evidence/d31-t01-v006-rollout.json) adds two invoker-security trigger functions, two triggers and partial provenance lookup indexes. No old migration or data rewrite, new app authority, model/configuration/dependency/credential change. All11 old data-table fingerprints and schema/table/column ACLs match before/after; a fresh protected restore verifies exact function/trigger definitions and permissions. Populated memory inventory refuses rollout pending a separate audited plan. Current local memory was empty before application.

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

D31 local negative injection/export/privacy composition, actual file DB/vector/blob removal and full regression/post-audit gates are accepted. Preserve agreed models and historical failed evaluations; no user labeling or model replacement is required.

## Final measured privacy composition

Focused9 PASS/20.90s and full1608 PASS/1361.93s,0 SKIP. Existing CORE/fast returned explicit insufficiency for the frozen malicious source, with no foreign canary/marker file; this is one structural/source isolation case, not general semantic safety. Actual Qwen/file/Qdrant flow leaves the deleted source inactive with text-free tombstone/cleanup acknowledgement, zero scoped vectors, absent blob and released quota, while another principal retains its blob and one vector. Per-record memory deletion physically removes its row and keeps its separate source. All252 code/test/config bytes match the execution freeze. New2026-10-20 audit: V006, memory/source/quota/restore probes/vector collections/workers/advisory locks0; original ACLs/narrow app grants and invoker-only source functions preserved. D32 knowledge gate NEXT.
