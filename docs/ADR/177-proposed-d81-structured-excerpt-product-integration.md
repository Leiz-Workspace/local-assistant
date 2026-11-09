# ADR 177 — Proposed default-off structured excerpt extraction over grounded sources

**Purpose:** Define one owner-reviewable path that moves the locally verified D81 structured-excerpt adapter from evaluation scripts into an authenticated, default-off product mode, without changing models, templates, defaults or any historical score.

**Status:** ACCEPTED (option A) — 2026-11-09. The owner wrote "Tiếp theo làm D81, D87 đi" and, asked "D81 theo ADR177 ... Bạn chọn phương án nào?", answered "A: code + test (Recommended)": implementation and software gates only, default-off, zero native calls. Option B (A plus the native v4 evaluation budget) was not chosen, and option C (defer) was not chosen. This acceptance does not activate the feature, select a model or default, authorize any native request, or close D81, D89 or D90. The implementation is recorded in [Implementation (option A, 2026-11-09)](#implementation-option-a-2026-11-09); the proposal sections before it keep their pre-decision text (written 2026-11-06, last revised 2026-11-07); only the chosen/not-chosen markers on the options and the decision line after them were added.

Earlier status (history): PROPOSED — 2026-11-06. Prepared as the D81 item of step 2 in [OPEN_DAYS_20261105](../OPEN_DAYS_20261105.md) at the owner's request of 2026-11-06 for a concrete proposal to review before any code (owner 2026-11-06, operator record); no approval or decision is recorded yet. This document changes no source, configuration, route, model, service or data.

## Context and evidence

Passed, within stated scope:

- Deterministic admission: [strict excerpt guard](../D81_STRICT_EXCERPT_GUARD.md) under [ADR125](125-host-pinned-profile-excerpt-validation.md), 66 new tests within 227 related tests PASS (0 FAIL, 0 SKIP) with zero model calls. The first CORE reply is rejected, not rewritten.
- Source-string grammar: [ADR128](128-source-derived-string-vocabulary.md) fresh v3 arm 6/6 positives, 18/18 exact minimal quotes and 2/2 explicit refusals ([receipt](../evidence/d81-literal-source-first-verification.json); receipt `executed_commit` 76c4ea2, a pre-rewrite hash not resolvable in current history).
- Original three-domain fixture: after the integer quote-domain fix (current commit 07ebf3b; receipt `executed_commit` d040108, a pre-rewrite hash not resolvable in current history), one first native request of the unchanged file/code/authored-web workflow through `StructuredExcerptAdapter` accepted **3/3 exact fact/quote pairs** (G-17/128/45). Eight retained v3 outputs revalidated offline, zero retries ([report](../D81_INTEGER_QUOTE_REGRESSION.md), [receipt](../evidence/d81-integer-quote-native-verification.json)). The [roadmap](../LOCAL_ASSISTANT_MASTER_ROADMAP.md) D81 row reads LOCAL ORIGINAL WORKFLOW VERIFIED; PRODUCT INTEGRATION OPEN, matching [open days](../OPEN_DAYS_20261105.md).
- Software: the 719-file full run including these additions was 5596 PASS / 0 FAIL / 0 ERROR / 0 SKIP ([receipt](../evidence/d90-structured-full-acceptance.json)). Later full runs are separate historical scopes.

Failed and retained unchanged:

- First cross-domain native run: 1/3 quotes in the requested fact-only form, 3/3 grounding by replay ([report](../D81_CROSS_DOMAIN_ORCHESTRATION.md)).
- Fresh six-case prompt protocol: **1/6 full contracts**, 1/6 exact fact objects, 16/18 exact excerpts. The guard admitted 4/6, and three of those still failed fact checks ([D81-FMT-002](../D81_FROZEN_EXCERPT_PROTOCOL_EVALUATION.md), [ADR126](126-frozen-core-excerpt-protocol-evaluation.md)).
- Structured v1: baseline 6/6, schema 5/6, refusals 1/2 ([ADR127](127-opt-in-source-derived-structured-extraction.md)). v2: 5/6 in both modes after the wire-order fix ([D81-FMT-004](../D81_STRUCTURED_ORDER_FOLLOWUP_PROTOCOL.md)). v3: original workflow FAIL on a nonnumeric quota quote, so the campaign is NOT QUALIFIED.

Limits on what this evidence supports:

- The original workflow `REQUEST` in [tests/cross_domain_scenario.py](../../tests/cross_domain_scenario.py) names the three target values. Its PASS is a fixture regression of quote/format adherence, not open-ended extraction.
- Fresh cases are small texts authored by the same agent, not retrieval chunks from owner files. Literal consistency is not semantic correctness: FMT-002 case 02 returned a source instruction as a fact.
- The fresh v3 arm ran before the integer quote-eligibility change. After it, only the original workflow ran natively; the fresh outputs were revalidated offline, not regenerated.

Wired today (read in code):

- [`StructuredExcerptAdapter`](../../src/infrastructure/inference/structured_excerpt_adapter.py) is constructed only by [scripts/structured_excerpt_evaluation.py](../../scripts/structured_excerpt_evaluation.py) and tests. No route or service uses it. Its only application reference is the ADR175 guard list `TARGETS` in [apps/api/voice_admission.py](../../apps/api/voice_admission.py).
- Adapter contract:
  - Single use, with exactly `profile="core"`, `preset="fast"`, `max_tokens=512` and `temperature=0`.
  - Model `qwen3.5-9b-core` at `http://127.0.0.1:8080`, taken from `get_model_profile("core")`. `httpx.Timeout(20, connect=5)` (each connect at most 5 s; each read/write/pool wait at most 20 s) across four sequential HTTP requests (`/v1/models`, `/apply-template`, `/tokenize`, `/v1/chat/completions`); there is no end-to-end bound inside the adapter.
  - Messages are exactly system `TEMPLATES["core"]` plus a user `PromptInput` JSON, with one declared field per source.
  - 1–8 fields, typed `string` (at most 24 codepoints) or signed 32-bit `integer`.
  - Each source is 1–4096 characters, split into 1–32 unique units of at most 512 characters. At most 512 literal choices per source. Schema and request frames are at most 32768 bytes.
  - An explicit refusal raises `InferenceFailure` `structured_insufficient_evidence` (422). Every other rejection becomes `structured_<phase>` (503), with phase `invalid_request`, `backend_failed`, `invalid_reply` or `model_mismatch`; internal reasons are not exposed. Cancellation propagates as `CancelledError`.
  - `StructuredProvenance` (prompt, schema, native-request and content digests plus the two flags) is set only after the output validates; after a refusal or rejection it is `None`.
- [`StructuredProfileAdapter`](../../src/infrastructure/inference/structured_profile.py) is the D14 host-schema path ([ADR133](133-opt-in-host-schema-profile-decoding.md)). Its `compile_schema` admits only `type` and `maxLength` on strings, so it cannot carry source-derived quote enums and is not the D81 path.
- [apps/api/main.py](../../apps/api/main.py) registers `/api/v1/grounded/answer` ([route](../../apps/api/routes/grounded.py)) behind `require_local_client` (loopback only, no Origin, no proxy headers) and bearer `Principal`. [`GroundedService`](../../apps/api/services/grounded.py) ([ADR043](043-source-held-grounded-generation.md)):
  - is default-off via `ASSISTANT_GROUNDED_ENABLED` ([startup](../../apps/api/storage/grounded.py)) and holds owner-authorized retrieval sources;
  - refuses overlap with 429 `grounded_busy` and runs CORE fast/512/temperature 0 under a 60-second model-only deadline (`model_timeout`);
  - validates sources before and after inference, and `RetrievalResponse` validates again before sending headers.
- `GroundedService.operation` hard-codes `build_messages`/`parse_answer`, `complete` always calls the constructor-bound `self.inference`, and `shutdown` joins only tasks registered in `self.operations`. Its `SYSTEM` prompt and payload differ from the adapter's required template and input. Injected as its inference port, the adapter would reject the call in `prepare()` (internal reason `structured_prompt_scope`) as `InferenceFailure` `structured_invalid_request` (503), which `/grounded/answer` maps to 503 `grounded_model_unavailable`; being single use, a shared instance would also fail from the second call.
- `/api/v1/chat/completions` accepts caller-chosen profile, preset, temperature and messages, and has no source fence. Conversation routes manage stored history. Neither fits source-bound extraction.

## Decision proposed

Add one opt-in route, **proposed** `POST /api/v1/grounded/extract`, next to the unchanged `/grounded/answer`, calling `StructuredExcerptAdapter` unchanged. Reuse needs one additive method in `apps/api/services/grounded.py` (**proposed** `GroundedService.extraction`): it takes the same `self.admission`, registers its task in `self.operations`, honours `closing`, and awaits the per-request adapter under `model_timeout` with the shield/cancel/join pattern of `complete`. Existing `operation`, `complete` and `shutdown` stay unchanged. Following ADR175, an additive factory (**proposed** `apps.api.grounded_extract:create_app`) composes the route and returns the exact `apps.api.main.app` when disabled. `main.py` and existing route modules stay byte-identical.

**Request contract** (strict, extra fields forbidden):

- `query`: 1–4096 UTF-8 bytes, used only as retrieval search text.
- `fields`: 1–3 objects `{name, type, file_id}`. Names are distinct identifiers other than `citations`, `type` is `string` or `integer`, and file UUIDs are distinct.
- No profile, model, preset, schema, enum, expected value, source text, owner or citation field is accepted.

**Server composition:**

1. Authenticate with the existing dependencies. The principal comes only from bearer authentication.
2. Inside `GroundedService.extraction`, open `retrieval.operation(owner, query, top_k=len(fields), file_ids=[...])`. Require exactly one hit per declared file, a plain `chunk_text` span (no table or cell structure) and text inside the adapter bounds. Otherwise refuse before inference, with zero model calls.
3. Build the prompt from system `TEMPLATES["core"]` and a canonical `PromptInput`:
   - `request` is the evaluated `INSTRUCTION` text plus the field map, moved byte-identical from the evaluation script into a production module.
   - Source IDs are assigned by the server, with `facts_key="facts"` and fixed `sentences` units (the boundary regex also splits on newlines). v3 used `sentences` for file/web sources and `lines` for code sources, so only the file/web part of the measured mode mix applies.
   - Flags are `schema_enabled=True` and `literal_strings=True`, the combination used in the v3 candidate arm. The current integer-eligibility grammar was natively exercised only on the original workflow, so v4 below would be the first native measurement of this exact configuration.
   - The free-text query is not added to the model prompt. Adding it would be a new protocol that needs its own evaluation.
4. Create one new adapter per request and await it as the method's owned work, joined on timeout or cancellation.
5. Validate sources again and map each citation back to its hit. Compute codepoint `quote_span` and `source_span` through the existing `evidence_units` mapping, as `parse_answer` does, and deliver through `RetrievalResponse`.

**Response (200):**

- `status`: `extracted`, `insufficient_evidence` or `no_sources`.
- `facts`: an object, or null.
- `citations`: `[{field, quote, quote_span, file_id, chunk_id, source_sha256, generation, source_span}]`.
- `answer_trust="model_generated"` and `content_trust="untrusted"`.
- `extraction`: only for `extracted`, `{protocol, schema_sha256, prompt_sha256}`. `protocol` is a server constant naming the frozen instruction/unit/flag set; the digests come from `StructuredProvenance`. For `insufficient_evidence` and `no_sources` it is null. The digests are provenance only, not approval or proof of correctness.

**Refusal behaviour:**

- Explicit model refusal: `insufficient_evidence` with `facts=null`, `citations=[]` and `extraction=null`. No partial facts are returned.
- No hits: `no_sources`, with no inference.
- Contract or source-shape failure: 422 `extract_contract_invalid`, `extract_source_mismatch` or `extract_source_unsupported`.
- Adapter rejection: 503 `extract_model_unavailable`. Timeout: the existing 504 `grounded_model_timeout`.
- Inherited refusals: 429 `grounded_busy` (lock shared with `/grounded/answer`), 429 `retrieval_busy` (lock shared with `/api/v1/retrieval/search`) and the pre-header delivery fence 409 `retrieval_source_changed`.
- GPU residency: 409 `gpu_busy`, a forward guard only (see below); clients distinguish it from the fence by code.
- No retry, no repair, and no fallback to `/grounded/answer` or plain text.
- The route needs its own error mapping. The existing grounded dependency turns every `InferenceFailure` other than `context_overflow` into 503, so the 422 refusal would become `grounded_model_unavailable`, and it catches `RuntimeError`, which would hide `AdmissionBusy`, a `RuntimeError` subclass, as `grounded_unavailable`.

**GPU admission (ADR175):**

- Extraction-only process, the only first-scope configuration: `ManagedGPUCalls` never starts, so no `guard_gpu` wrappers exist (ADR175: disabled applications have no wrappers). CORE overlap is limited only by the grounded lock and the CORE slot, exactly as for `/grounded/answer` today. This is not a host-wide lock.
- Forward guard: `StructuredExcerptAdapter.complete` is already a declared voice target. In a later combined voice+extraction composition, extraction during voice residency would get `AdmissionBusy`, never borrow the voice lease, and a cancelled unborrowed call would quarantine admission for that process. The first scope maps `AdmissionBusy` to 409 `gpu_busy` and tests it by binding a `GPUAdmission` directly; this is not first-scope runtime behaviour.
- `apps.api.voice:create_app` builds from `apps.api.main.app` and would not include this route. The first scope therefore refuses startup when `ASSISTANT_VOICE_ENABLED=1`; a combined composition needs its own tests.
- [ADR176](176-bounded-foreign-gpu-tolerance-and-b3-preflight.md) (ACCEPTED 2026-11-06) tolerates foreign GPU processes up to 1 GiB total in `src/infrastructure/voice/ipc.py` and allowed exactly one replacement B3 panel after preflight. It does not change in-process `GPUAdmission`.
- That panel ran on 2026-11-06 and ended NOT_PASS (`main_voice_call_budget_or_cleanup`); its result is recorded in [D74_MAIN_VOICE_B3_RESULT.md](../D74_MAIN_VOICE_B3_RESULT.md) with a [public receipt](../evidence/d74-main-voice-b3-adr176-result.json); private artifacts stay in `data/backups/d74-main-integration-adr176`. No retry followed, and that result is not relabelled. On a new owner decision (2026-11-06), [ADR178](178-graceful-sigterm-exit-in-b3-acceptance.md) (ACCEPTED 2026-11-07) changed only the B3 runner (`benchmarks/scripts/main_voice_integration.py`) and its tests, and allowed exactly one new panel. That panel ran on 2026-11-07 and is PASS ([public receipt](../evidence/d74-main-voice-b3-adr178-result.json); private artifacts stay in `data/backups/d74-main-integration-adr178`). ADR178 does not change in-process `GPUAdmission` either. Extraction native work never shares a window with a voice panel.

**Configuration:** **proposed** `ASSISTANT_GROUNDED_EXTRACT_ENABLED`.

- Absent or `0`: the exact original app and OpenAPI.
- `1`: requires live retrieval and grounded services created by the existing lifespan, which needs the whole chain: `DATABASE_URL`, `ASSISTANT_FILES_ENABLED=1`, `ASSISTANT_INGESTION_ENABLED=1` with `ASSISTANT_INGESTION_CONFIG_FILE`, `ASSISTANT_RETRIEVAL_ENABLED=1` (with the owned ingestion collection), `ASSISTANT_GROUNDED_ENABLED=1`, and `ASSISTANT_AUTH_FILE` (required by file storage and bearer authentication).
- Any other value, a missing prerequisite, or the voice combination: startup `RuntimeError`.
- No production manifest and no default enablement.

**Audit events** (finite codes and counts, no content):

- New events: `grounded_extract_disabled`, `grounded_extract_composed`, `grounded_extract_admitted fields=%d`, `grounded_extract_source_refused code=%s`, `grounded_extract_published fields=%d citations=%d`, `grounded_extract_insufficient_evidence`, `grounded_extract_failed code=%s`, `grounded_extract_gpu_busy`.
- The adapter's existing `structured_excerpt_*`, `structured_literal_values_bound` and `structured_quote_eligibility` events (counts only) are kept.
- Logs never contain the query, field names, values, quotes, source text, file/chunk/principal identifiers or content digests.

## Non-goals

- No change to model, default, template, preset, budget, context or grammar policy. `TEMPLATES["core"]`, the grounded `SYSTEM`, the `/grounded/answer` contract and both adapters keep their current behaviour.
- No new model, weights, SDK or dependency, and no downloads.
- No activation: no default enablement, production manifest, UI, chat/conversation mode, memory write or tool/action authority.
- No workspace-code or web sources; the D78/D79/web-fetch composition stays evaluation-only. No multi-worker or cross-process coordination.
- `ProfileExcerptGuard` is not used because it needs excerpt spans the host already knows, which a product request does not have.
- No rescoring of retained failures and no general claim about extraction quality.

## Validation plan

Software gates are fixture-only and make no model calls. They reuse the `Port`/`Retrieval` fakes in [tests/test_grounded_service.py](../../tests/test_grounded_service.py):

- `tests/test_grounded_extract_contract.py`:
  - strict request model, forbidden overrides, name/type/file rules;
  - byte-identical `INSTRUCTION` and a prompt digest equal to the `ProfilePromptRun` composition;
  - fixed unit mode and adapter flags; `extraction` present only for `extracted`.
- `tests/test_grounded_extract_service.py`:
  - one-hit-per-file binding;
  - mismatched, table/cell and oversized sources refused with zero transport calls, and `no_sources` without inference;
  - a refusal publishes nothing, and failure codes map as specified;
  - source changes before and after inference are fenced, and delivery returns 409 `retrieval_source_changed`;
  - 429 `grounded_busy` is shared with `/answer` and 429 `retrieval_busy` with `/retrieval/search`;
  - cancellation and timeout are joined, each adapter is used once, and extraction tasks are registered in `GroundedService.operations` and joined by `shutdown`.
- `tests/test_grounded_extract_startup.py`:
  - default-off returns the same app object and OpenAPI;
  - invalid flag values, missing prerequisites and the voice combination are refused;
  - loopback, no-Origin and bearer rules apply;
  - `file_ids` owned by another principal match nothing under the owner-scoped retrieval filter, giving `no_sources` (or `extract_source_mismatch` when only some files resolve) with zero model calls;
  - audit records contain no content.
- `tests/test_grounded_extract_gpu_admission.py` (forward guard):
  - with a directly bound `GPUAdmission` holding residency and a wrapped adapter, extraction returns 409 `gpu_busy`, not `grounded_unavailable`;
  - quarantine refuses requests, and an extraction-only app installs no wrappers.

These unchanged related suites must also pass, plus Ruff on changed files:

- `tests/test_structured_excerpt_adapter.py`, `tests/test_structured_excerpt_evaluation.py`
- `tests/test_grounded_answer.py`, `tests/test_grounded_service.py`, `tests/test_grounded_source_groups.py`, `tests/test_grounded_startup.py`
- `tests/test_main_voice_admission.py`, `tests/test_profile_prompts.py`
- `tests/test_cross_domain_scenario.py`, `tests/test_cross_domain_retained_grounding.py`

None of them appears in the hosted exclusion or quarantine lists under `.github/ci/`, so they run in the main [CI](../../.github/workflows/ci.yml) job. Branch protection and rulesets are unavailable for this private Free-plan repository (API 403, operator 2026-11-06), so CI is not an enforced merge gate; the PR records the CI run and the exact local commands and counts. A software PASS is not model quality. The owner-run D87 full regression (runbook `docs/D87_FULL_REGRESSION_20261106_RUNBOOK.md`, owner 2026-11-06, operator record) is a separate software scope and covers only code present in its snapshot.

**Native evaluation budget (needs separate owner approval):**

- Corpus: create and freeze `tests/fixtures/harness/d81-grounded-extract-v4.json` only after approval and before any inference. It would hold 6 fresh positives (3 EN / 3 VI) as authored single-chunk files and 2 negatives (missing value, instruction-only).
- Environment: an isolated, disposable evaluation database/collection and a RAM-backed test principal, both created and removed by the operator. Ingestion embeddings run through the existing configured worker and are counted separately. CORE is an operator-owned instance with attested identity, as in ADR174 B3; a shared instance is never reset.
- Requests: exactly one first request per case through real loopback HTTP. At most 8 CORE generations plus 1 ordinary recovery, Fast512 at temperature 0, no retry. Each case's model call is bounded by the existing 60-second grounded model deadline (retrieval and delivery are outside it), inside which the adapter's per-operation HTTP timeouts apply.
- Runner: the frozen protocol states its web-process shutdown criterion before inference. The ADR176 replacement B3 required exit code 0, while the locked uvicorn 0.54.0 re-raises the captured SIGTERM after a complete graceful shutdown (exit -15), so its later borrowed-CORE liveness check was never evaluated (operator 2026-11-06); that result stays NOT_PASS and is not reinterpreted here. [ADR178](178-graceful-sigterm-exit-in-b3-acceptance.md) then replaced the exit-0 criterion with a verified graceful-shutdown criterion: exit 0 or -15 is accepted only when the audit contains the five ordered voice lifespan shutdown events exactly once and no quarantine, Traceback, ERROR or CRITICAL line. Its single panel on 2026-11-07 passed with web exit -15 proven graceful, and the borrowed-CORE liveness check was evaluated for the first time (CORE alive).
- Acceptance: 6/6 exact fact objects with exact source-unit quotes, 2/2 explicit refusals that publish nothing, all fences pass, and source bytes and CORE identity are unchanged.
- Any failure is retained, and no rerun follows automatically.

## Migration and rollback

No data, schema, collection or index migration is needed. Default-off keeps routes, OpenAPI and startup identical.

Rollback either unsets the flag or starts the original entry point, after `GroundedService.shutdown` joins owned operations. That join covers extraction only because its tasks are registered in `GroundedService.operations`, which the service tests verify. If a native request cannot be proven complete, rollback is not claimed (ADR175 rule). Every evidence file, fixture and failure is retained.

## Risks

- Literal is not correct: a quoted, literally consistent value can still be the wrong fact (FMT-002 case 02). Responses keep the `model_generated`/`untrusted` labels and make no verification claim.
- Evidence transfer: authored fixtures and an original question that names the values do not predict behaviour on real owner chunks. v4 would be the first measurement on that path.
- Availability: the 4096-character, 32-unit, 512-choice and 32 KiB bounds, plus the one-hit-per-file rule, will refuse many real chunks and multi-chunk files. Refusal is preferred to truncation.
- Prompt injection inside owner files: the route has no tool authority and output is restricted to source units, but instruction text can still be quoted as a value.
- GPU/CORE contention: an extraction-only process has no coordinator or wrappers, and separate API processes are not coordinated. Quarantine applies only to a future combined voice composition.
- Overfitting: the fixed `INSTRUCTION` and the small corpora. Changing either needs a new frozen protocol.

Sequencing follows step 2 of [open days](../OPEN_DAYS_20261105.md). The first two step-1 B3 panels ran and ended NOT_PASS: the ADR175 panel of 2026-11-05 (`main_voice_prepare_fault`, recorded in ADR176) and the ADR176 replacement of 2026-11-06 (`main_voice_call_budget_or_cleanup`, [result](../D74_MAIN_VOICE_B3_RESULT.md)); both results are kept unchanged. After the owner decision of 2026-11-06, the single [ADR178](178-graceful-sigterm-exit-in-b3-acceptance.md) panel of 2026-11-07 passed ([public receipt](../evidence/d74-main-voice-b3-adr178-result.json)), so B3 has now passed for the default-off `/voice` path and no longer keeps step 1 open. Physical first-audible (B4), short/quiet/room speech, product activation and any model, voice or default decision remain separate open gates. When this proposal was written, starting step-2 D81 work before step 1 closed was part of the owner decision below; that ordering question no longer applies, and option A still does not depend on any voice panel.

**Owner decision pending:**

- A: approve implementation and software gates only (default-off, zero native calls). **Chosen on 2026-11-09.**
- B: A plus the native budget above, run once after the software gates pass and never during a voice panel. Not chosen.
- C: defer. The adapter stays evaluation-only and D81 product integration stays OPEN. Not chosen.

None of these options activates the feature, selects a model or default, or closes D81, D89 or D90.

**Owner decision recorded (2026-11-09):** A, from the owner's answer "A: code + test (Recommended)". The option text above is kept as it was proposed on 2026-11-06; only the chosen/not-chosen markers were added. The native budget of option B stays unapproved; running it needs a separate owner decision.

## Implementation (option A, 2026-11-09)

Scope: option A only. Code and fixture-only software gates, default-off, zero native calls. Work branch `feat/d81-grounded-extract`, cut from `develop` `385f4c6`. The names marked **proposed** above are used unchanged.

**Files:**

- New `apps/api/routes/grounded_extract.py`: `POST /api/v1/grounded/extract` with its own error mapping, behind the existing `require_local_client` guard (loopback only, no Origin, no proxy headers) and bearer `Principal`.
- New `apps/api/grounded_extract.py`: the factory `create_app()` (see below).
- New `src/application/services/grounded_extract.py`: a pure protocol module holding the frozen `INSTRUCTION` (moved byte-identical), the protocol constant `d81-grounded-extract-v1`, field validation, one-hit-per-file source binding and publication of citations with `quote_span`/`source_span` through the existing `evidence_units` mapping.
- Changed `apps/api/services/grounded.py`: additive methods only. `extraction` is an async context manager that shares `self.admission` with `/grounded/answer`, registers its task in `self.operations` and honours `closing`; `extract_sources` binds and fences the sources; `complete_extraction` awaits one new `StructuredExcerptAdapter` per request with shield/cancel/join under `model_timeout`. `operation`, `complete` and `shutdown` are unchanged.
- Changed `scripts/structured_excerpt_evaluation.py`: imports `INSTRUCTION` from the protocol module instead of defining it.
- New suites `tests/test_grounded_extract_contract.py`, `tests/test_grounded_extract_service.py`, `tests/test_grounded_extract_startup.py`, `tests/test_grounded_extract_gpu_admission.py`, plus the shared fixture helper `tests/grounded_extract_cases.py` (not a suite).
- Unchanged, checked with `git diff` against `origin/develop`: `apps/api/main.py`, `apps/api/routes/grounded.py`, `apps/api/routes/retrieval.py`, `apps/api/voice.py`, `src/infrastructure/inference/structured_excerpt_adapter.py` and `src/application/services/gpu_admission.py`.
- Audit events are the eight new events listed under **Audit events** above (codes and counts only); no-hit requests log `grounded_extract_source_refused code=no_sources`.

**Running the factory:** `apps.api.main:app` never reads `ASSISTANT_GROUNDED_EXTRACT_ENABLED` and never serves the route. Only the separate entry point does, started like the main API with `DATABASE_URL` supplied through the environment:

```bash
ASSISTANT_GROUNDED_EXTRACT_ENABLED=1 \
ASSISTANT_FILES_ENABLED=1 ASSISTANT_INGESTION_ENABLED=1 \
ASSISTANT_RETRIEVAL_ENABLED=1 ASSISTANT_GROUNDED_ENABLED=1 \
ASSISTANT_INGESTION_CONFIG_FILE=<ingestion config> ASSISTANT_AUTH_FILE=<principal file> \
uv run --no-sync uvicorn apps.api.grounded_extract:create_app --factory \
  --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

- Flag absent or `0`: logs `grounded_extract_disabled` and returns the exact `apps.api.main.app` object, so routes and OpenAPI are unchanged.
- Flag `1`: `DATABASE_URL`, `ASSISTANT_INGESTION_CONFIG_FILE` and `ASSISTANT_AUTH_FILE` must be present, `ASSISTANT_FILES_ENABLED`, `ASSISTANT_INGESTION_ENABLED`, `ASSISTANT_RETRIEVAL_ENABLED` and `ASSISTANT_GROUNDED_ENABLED` must be `1`, and `ASSISTANT_VOICE_ENABLED` must be absent or `0`. The factory then builds a new app from the original routes plus the extract route (the pattern of `apps/api/voice.py`) and logs `grounded_extract_composed`.
- Any other flag value, a missing prerequisite or voice enabled: startup `RuntimeError` (`grounded_extract_flag_invalid`, `grounded_extract_prerequisites_required`, `grounded_extract_voice_unsupported`).
- The composed lifespan runs the unchanged base lifespan and then refuses to start (`grounded_extract_requires_grounded_retrieval`) unless live retrieval and grounded services exist and the grounded service is linked to that retrieval service.
- Ingestion creates a real Qdrant collection and needs owner approval first ([README](../../README.md)). No production manifest, default enablement or UI was added.

**Software validation (local, 2026-11-09):**

- The four new suites: **169 passed, 0 failed, 0 skipped**, fixture-only with zero model calls.
- The ten unchanged related suites listed in the validation plan: **206 passed, 0 failed, 0 skipped**. Total 375.
- Ruff check (`E4,E7,E9,F`) and `ruff format --check` on the 10 changed or new `.py` files: clean.
- Internal review with three lenses (contract, concurrency/lifecycle, security/test quality) found 5 low-severity items, all applied: the `no_sources` trust label set to the literal Response section, the quarantine forward guard, oversized and NaN test cases made meaningful, and the audit test scope.

```bash
uv run --no-sync python -m pytest -q tests/test_grounded_extract_contract.py \
  tests/test_grounded_extract_service.py tests/test_grounded_extract_startup.py \
  tests/test_grounded_extract_gpu_admission.py
uv run --no-sync python -m pytest -q tests/test_structured_excerpt_adapter.py \
  tests/test_structured_excerpt_evaluation.py tests/test_grounded_answer.py \
  tests/test_grounded_service.py tests/test_grounded_source_groups.py \
  tests/test_grounded_startup.py tests/test_main_voice_admission.py \
  tests/test_profile_prompts.py tests/test_cross_domain_scenario.py \
  tests/test_cross_domain_retained_grounding.py
```

A software PASS is not a model-quality measurement. The CI run belongs to the PR record.

**Implementation decisions and interpretations:**

- `no_sources` returns `answer_trust="model_generated"`, following the literal Response section above (every 200 response), although no model runs. `/grounded/answer` uses `not_generated` for its own no-sources answer. Changing this label needs an amendment of this ADR.
- Two bounds that the adapter checks only after backend calls are enforced before inference: the canonical messages at most 16384 bytes and the native request frame at most 32768 bytes. Both refuse with 422 `extract_source_unsupported` and zero transport calls.
- "No table or cell structure" is read strictly: any non-empty `provenance.structure` is refused as `extract_source_unsupported`. A plain chunk must also be non-blank, at most 4096 characters and at most 8192 UTF-8 bytes.
- Corrupted span or text data inside `evidence_units` keeps the existing 503 codes `grounded_sources_invalid` and `grounded_source_span_invalid`.
- The request body is parsed by hand (exactly one `application/json` content type, at most 16384 bytes), so duplicate keys and NaN get the exact 422 `extract_contract_invalid` and nothing is echoed. The OpenAPI request schema is still published.
- Forward guard: when the adapter's inner guarded call fails while a bound `GPUAdmission` is quarantined, the service maps it to 409 `gpu_busy` by reading `src.application.services.gpu_admission._coordinator` (module unchanged). The first-scope extraction-only app binds no coordinator, so this path is test-only today.
- Logs: the new extraction events carry no content. The shared bearer dependency still logs `conversation_principal_authenticated principal_id=…`, and the existing retrieval rehydration logs file identifiers (`blob_reader_opened file_id=…`, `ingestion_plan_prepared file_id=…`), as for every authenticated route. The rule "logs never contain … identifiers" above holds for the new extraction events, not for those shared pre-existing events.
- Moving `INSTRUCTION` changes the file sha256 of `scripts/structured_excerpt_evaluation.py`. Historical freeze receipts recorded the old value (for example [d81-literal-source-first-verification.json](../evidence/d81-literal-source-first-verification.json)) and are not rewritten; the instruction text itself is byte-identical.
- The shared fixture helper `tests/grounded_extract_cases.py` was added; it holds fixtures only and is not a suite.

**Side effect on the B3/B4 voice evidence source scope:** `source_snapshot()` in `benchmarks/scripts/main_voice_integration.py` (`apps/**/*.py`, `src/**/*.py` and the other listed voice, test, configuration and ADR files) grows from 307 to 310 files with the three new modules, and `apps/api/services/grounded.py` changes. Voice code paths are unchanged, but `apps.api.voice:create_app` builds on `apps.api.main.app`, whose import chain now also loads the extraction modules. The B3 PASS and the [B4 owner acceptance](../D74_B4_OWNER_ACCEPTANCE.md) stay as recorded for their snapshots. A future `/voice` session needs a manifest with the recomputed source map: the B4 launch procedure's drift check, which expected only `src/infrastructure/ocr_worker.py` to differ, would now stop at `unexpected_source_drift`. This ADR file is not in that scope.

**Still open after option A:**

- Not activated: no default enablement, no production manifest and no UI. With the flag absent or `0`, the app and OpenAPI are identical to the original.
- The native v4 evaluation of option B was not run, and its corpus `tests/fixtures/harness/d81-grounded-extract-v4.json` was not created. Extraction quality on owner chunks is unmeasured, and no quality claim is made.
- D81 stays OPEN: the product integration code is implemented default-off, but full-flow acceptance for a chosen scope (and any native measurement) remains.
- D87 follows the owner's answer "Sau D81 + promote (Recommended)": merge D81 into `develop`, promote `develop` → `staging` → `production` (no tag, no deploy), then run D87 on that commit. None of these steps is recorded as done here.
- D89 and D90 stay OPEN, D60 stays deferred, voice stays default-off, and there is no tag, release or deployment. The release state is unchanged.
