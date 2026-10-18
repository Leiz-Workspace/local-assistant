# File storage — authenticated local operation

**Purpose:** Operate the accepted D17 file feature, preserve ownership/namespace and run its protected paired recovery drill.

## Runtime and access

Use the existing PostgreSQL/Vault and one API worker bound directly to `127.0.0.1`. Follow the credential delivery in [conversation runbook](CONVERSATION_API_LOCAL_RUNBOOK.md): runtime receives app `DATABASE_URL` and protected digest-only `ASSISTANT_AUTH_FILE`, never an operator Vault token. Current app/API credentials already exist in Vault under `secret/server/local-assistant/postgresql` and `secret/server/local-assistant/api`; migration identity is separate. Token rotation must preserve principal UUIDs.

File resources initialize only with `ASSISTANT_FILES_ENABLED=1`, revision V002 and matching principal/root bindings. `ASSISTANT_FILES_ROOT` defaults to `ai/data/files`; keep it dedicated, 0700, with private 0600 payloads/namespace marker. Changing to another empty root while these principals have allocations fails startup. Do not delete/replace `.storage-namespace` or persistent resource-lock directories.

After secure app-credential delivery, from `ai/`:

```sh
ASSISTANT_FILES_ENABLED=1 \
ASSISTANT_AUTH_FILE="$PWD/data/auth/principals.json" \
ASSISTANT_FILES_ROOT="$PWD/data/files" \
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Default feature flag is off; setting it does not create another infrastructure service. Bubblewrap `/usr/bin/bwrap`, working unprivileged namespaces and the uv-locked runtime are required; missing isolation rejects verification without fallback. Browser Origin/proxy headers are rejected by the existing loopback boundary.

## HTTP contract

| Operation | Request/result |
|---|---|
| Reserve | POST `/api/v1/files`, JSON `filename`, `size_bytes`, `sha256`, optional `request_key`; 201 |
| Upload | PUT `/{id}/content`, raw bytes; use application/octet-stream; 200 only after verification/durable publication |
| List/detail | GET collection or `/{id}`; owner-scoped metadata, bounded pagination |
| Download | GET `/{id}/content`; ready only, attachment/nosniff, full size/hash check before headers |
| Delete | DELETE `/{id}`; 204 after physical purge or 202/purging while cleanup remains pending |

Always send the existing bearer credential. IDs/owner/key/lease/path fields are assigned by the service. Same-key/same-declaration POST replays the existing live reservation/ready record without charging twice; changed declarations and failed/terminal keys return conflict. A ready PUT is immutable/conflicts; use GET to recover an acknowledged/uncertain result. New intentional retries after terminal failure require a new request key.

Limits and supported format subsets are defined in [design](FILE_STORAGE_DESIGN.md) and ADR-022: 25 MiB/file, 1 GiB/owner, 10 GiB/global, bounded counts/upload slots/free space, 8 KiB metadata, UTF-8 text, verified raster/PDF/OOXML. Encrypted/active/macro/ZIP64/external-linked/animated or oversized structures may be rejected by conservative V1 bounds. Verification does not grant semantic trust, execute content, attach to conversations or start extraction automatically.

## Recovery and maintenance

Startup and a five-second loop reconcile bounded known journal batches. Expired lease alone never releases allocation: the old writer/reader must release its inode/resource lock and physical purge must complete. A paused process retains quota; a dead process releases locks. Busy cleanup is retried fairly; redundant known ready staging links are removed only after same-inode/hash proof. Unknown/colliding/corrupt files remain quarantined for operator review; no glob-delete or silent adoption occurs.

Inspect safe stable-code logs such as `file_purge_pending`, `file_ready_reconciliation_pending`, `file_storage_root_namespace_mismatch` and pool metrics. Keep unresolved quota charged. Stop admission and drain before filesystem/database repair; do not reset counters or markers to hide a fault.

## Paired backup/restore drill

Stop API consumers first; resolve active/purging uploads and run a verified nonempty fixture if this is an acceptance drill. Deliver the existing app DB credential securely, then use a **new** backup directory:

```sh
uv run python -m scripts.file_storage_recovery_acceptance \
  --source-root data/files \
  --auth-file data/auth/principals.json \
  --backup-directory data/backups/CHOOSE_A_NEW_PRIVATE_DIRECTORY
```

The operator CLI needs existing local Docker PostgreSQL administrative access for dump/probe restore. It reuses the instance; no shared restart or production restore/overwrite occurs. Artifacts include DB archive/verification, blobs, an independent restored blob root, namespace identity, digest-only principal bindings and a success manifest. All remain protected/ignored; never commit/package them with source. Retention/encryption/off-host procedures require a separate operational plan.

Accepted retained evidence: `data/backups/d17-paired-20261018/manifest.json` has paired/database/security/identity verification true, one 53-byte fixture, seven restored tables, matching hashes/permissions and no remaining DB probe. The actual API process drill stopped both owned workers and removed only its test resource; final allocation is zero and existing conversation rows/ACLs are unchanged.

For real recovery, verify the complete paired set in isolated targets first, preserve namespace/principal UUIDs and current credential-revocation policy, then review activation while the old deployment is drained. Existing DB-only Day 15 backups are insufficient once blobs exist. Rollback disables admission and preserves tables/bytes; never downgrade populated V002 as a code rollback.

## Native PDF extraction (D18)

**Purpose:** Operate the owner-scoped, on-demand PDF text API defined by ADR-026.

With the existing file feature enabled, upload a verified PDF through the reservation/content endpoints, then send authenticated `POST /api/v1/files/{file_id}/extract`. There is no request payload. The response contains `file_id`, source `sha256`, versioned `extractor`, `content_trust: untrusted`, and `pages`. Each page has one-based `page_number`, `text`, `locator: file:<uuid>#page=<number>` and `status` (`native_text` or `no_native_text`). Empty pages remain in position. `no_native_text` is not visual blankness or an OCR result. Response uses `Cache-Control: private, no-store`.

The API rechecks owner/namespace/ready state and source size/hash before parsing, then checks integrity/owned ready state again before responding. No text cache, DB migration, ingestion, conversation attachment or model invocation occurs. Runtime audit records UUID/count/version/errors, never page text. Keep source text untrusted in all downstream consumers.

Two extractions may run concurrently in the supported one-worker deployment; excess returns429 without queueing. Each sandbox has 512 MiB address space, 5/6s CPU, 10s wall, 32 FDs, zero core and 8 MiB bounded stdout. Reject rather than truncate above1000 pages,128 KiB UTF-8/page or1 MiB UTF-8/document. Parser reuses D17's structure/stream and active-content restrictions. Cancellation/shutdown joins in-flight I/O before releasing shared blob locks; delete can return202 while extraction owns a reader. Retry delete/recovery after the reader closes.

Expected failures:401 anonymous;404 missing/foreign/deleted/wrong namespace;409 not ready;415 non-PDF/invalid PDF;413 text/resource limit or wall timeout;429 parser capacity;503 storage/sandbox unavailable or integrity mismatch. Error details contain stable codes only. Repeated extraction computes from the verified bytes each time. A scan without native text needs the separately planned D21 OCR/VLM workflow. Native font mappings and plain-mode reading order have finite coverage; this milestone does not certify arbitrary visual layout or table reconstruction.

Rollback drains requests and removes the extraction route/code; retain V002/root namespace/auth/blobs. Existing backup and paired restore procedures are unchanged because no extraction artifacts are persisted.

## DOCX read and rewrite (D19)

**Purpose:** Operate the bounded main-body DOCX workflow from ADR-027.

After uploading a verified DOCX, authenticated `POST /api/v1/files/{file_id}/docx/read` returns source UUID/SHA-256, processor version, `content_trust: untrusted`, ordered `paragraphs`, `tables` and declared `styles`. Paragraphs include one-based IDs, text, explicit style ID, editability and direct runs with text/bold/italic/underline/style references. Table cells refer to paragraph IDs and retain gridSpan/vertical-merge metadata. `column` is the physical XML cell ordinal within a row, not a projected Word grid coordinate. Locators use `file:<uuid>#paragraph=<id>` or `#table=<id>`; DOCX has no stable rendered-page locator at this stage.

To replace existing plain-run text, send authenticated JSON to `POST /api/v1/files/{file_id}/docx/rewrite`:

```json
{
  "source_sha256": "<source sha256 from read response>",
  "edits": [
    {"paragraph_id": 2, "run_index": 1, "text": "Updated text\twith tab\nand newline"}
  ]
}
```

The real request requires 64 lowercase hexadecimal SHA characters.1–100 unique run targets; strict JSON at most 64 KiB; no extra fields/duplicate keys, XML controls or carriage returns (use `\n`). One-based indices target existing direct runs. A stale source hash gives 409; unsupported non-plain paragraphs, signed packages or missing targets give 422. Fields/drawings/hyperlinks/bookmarks/tracked changes and page/column breaks are refused for editing. Empty existing runs can receive text; this API does not create new paragraphs/tables or accept arbitrary XML. Style inheritance and layout are not computed. Headers/footers/other parts are preserved, not extracted.

Response is a DOCX attachment with `Cache-Control: private, no-store`, `nosniff`, `X-Source-File-ID`, `X-Source-SHA256`, `X-Docx-Processor` and `X-Content-SHA256`. Downloaded bytes are reverified in the sandbox; source hash/ready ownership is checked again before the response. Source remains unchanged. Output is not persisted or charged as a stored file; use the normal reserve/upload path if it should enter the file journal. Unedited package-member bytes stay unchanged; only document.xml is serialized for run edits. Source text and edit text remain untrusted data, never model instructions.

Two DOCX operations/responses per service are admitted without a queue; excess 429. The slot, source lock and active-task tracking remain held until response delivery completes or is cancelled, including slow clients. PDF retains its existing separate two-parser gate. Cancellation/shutdown joins worker threads before closing FDs. Concurrent delete can return202 until the DOCX response releases its shared lock. Original allocation remains charged until physical cleanup.

Runtime lxml 6.1.3 is uv-locked; dev-only python-docx 1.2.0 and installed LibreOffice provide independent trusted golden opening checks. Untrusted production parsing only uses Bubblewrap: source stdin FD, bounded anonymous edit-plan FD mounted read-only at `/request.json`, cleared environment/read-only code/runtime, no credential/root mounts/network. Worker 512 MiB RAM,5/6s CPU,10s wall,32FD,zero core,25 MiB stdout/file; read JSON8 MiB, extracted text1 MiB, run64 KiB, main XML2 MiB,10000 paragraphs/cells,20000 runs,1000 styles. Existing D17 archive/relationship/DTD/active-content bounds apply before lxml and again to generated packages. Exceeded budgets 413; wrong format 415; unavailable sandbox/integrity failure 503. Logs exclude document/edit text.

Rollback drains requests and removes DOCX endpoints/modules, retaining source journal/root/auth/blobs. There is no migration or generated-output cache to reverse. No arbitrary Word layout, active-content safety certificate, cloud upload or model execution is introduced.

## XLSX inspection and literal rewrite (D20)

**Purpose:** Operate the bounded formula-preserving workbook contract from ADR-028.

Upload a verified XLSX, then authenticated `POST /api/v1/files/{id}/xlsx/read` returns source UUID/SHA, processor version, `content_trust: untrusted`, `formula_cache_status: preserved_not_recalculated`, style count and native sheets/cells. Each cell exposes canonical A1 address, storage kind, lexical value, formula source/attributes, cached value, style index and editability. Sheet/cell locators use `file:<uuid>#sheet=<native-sheet-id>` and `&cell=<A1>`. Merged ranges retain their native references. Styles are preserved/referenced, not rendered.

Authenticated `POST /api/v1/files/{id}/xlsx/rewrite` accepts strict bounded JSON:

```json
{
  "source_sha256": "<64 lowercase hexadecimal source SHA characters>",
  "edits": [
    {"sheet_id": 1, "cell": "A2", "kind": "number", "value": "99.5"},
    {"sheet_id": 1, "cell": "A1", "kind": "string", "value": "=literal text"},
    {"sheet_id": 1, "cell": "A3", "kind": "boolean", "value": false}
  ]
}
```

Numeric values are lexical strings with finite representable decimal values, never JSON float coercion. Boolean values are strict JSON booleans. Strings are explicitly inlineStr, including leading `=`; no formula input/evaluation occurs. Text must be XML-valid, at most64 KiB UTF-8/32767 UTF-16 units per cell; use newline, not carriage return. Plans are at most64 KiB with1–100 unique sheet/cell targets. Only existing literal cells are editable; formula, merged-range, rich-text, metadata/unsupported cells and signed packages are refused. Missing targets/unsupported edits422, stale source409, wrong format415, exceeded budget413, capacity429, unavailable sandbox/integrity failure503. Read JSON limit8 MiB includes locators.

Output is an ephemeral XLSX attachment with private/no-store/nosniff, `X-Source-File-ID`, `X-Source-SHA256`, `X-Xlsx-Processor`, `X-Content-SHA256`, and `X-Formula-Cache-Status: preserved_not_recalculated`. Formula source/attributes/cache remain unchanged even if edited inputs make caches stale. The service never calculates formulas, runs macros or fetches remote content. An application opening the download has its own calculation policy. Persist output explicitly with normal reserve/upload if needed; original bytes/quota are unchanged.

Two XLSX operation/response slots per service, no waiting queue; slot/active task/source SH FD remain held through delivery or cancellation. Owner/namespace/ready/size/hash are checked before parsing and hash/ready after parsing; thread work is joined before close. Concurrent delete may return202 until the response closes. Existing PDF/DOCX gates remain unchanged, scoped to one API worker.

Runtime uses existing lxml with entities/DTD/network/huge-tree disabled after D17 verifier. Read-only anonymous metadata mount keeps text out of argv/env; source stdin FD, no private host mounts/network. Worker512 MiB RAM,5/6s CPU,10s wall,32FD,zero core,25 MiB output; lexical text1 MiB,100 sheets,50000 cells,100000 shared strings,10000 styles and existing2 MiB/XML part/archive bounds. openpyxl3.1.5/et-xmlfile2.0.0 are uv-locked dev-only independent reopen tools, not runtime parsers.

D17's existing conservative OOXML subset is unchanged: absolute package-root relationship targets, external relationships, macro/nested/DTD content remain rejected. No automatic source repair or arbitrary Excel fidelity is claimed. Rollback drains XLSX operations and removes endpoints/modules; no schema/root/auth/cache or source rollback is needed.
