# CODE-EVAL-002 — Fresh paired coding-quality protocol

**Purpose:** Measure the existing CORE on fresh authored utility repairs and explicit issue wording while preserving first D46 failures, strict source reviews and action budgets.

Date: 2026-10-24, Asia/Ho_Chi_Minh. Status: EXECUTED/CLOSED; protocol completed, broader promotion NOT QUALIFIED. The preparation below was committed before inference. This is the next independent P1 task in the assessed coding backlog; no model/default/provider or production behavior changes.

## Scope, dependencies and risk

D46 measured 7/10 first repairs. Token masking and negative retry arithmetic failed; one six-step plan was rejected by the unchanged one-to-five contract. CODE-EVAL-002 addresses format and edge-case evidence on fresh data, rather than regenerating the old cases into a better score. Dependencies: D43/D44 reviewed finite workflow, D42 native unittest runtime, original CORE and immutable D46 evidence. Effort: one corpus/oracle/paired-measurement/failure-analysis milestone. Risks: repeated-case overfitting, leaking reference answers, changing expected behavior after seeing replies, treating experiment execution as successful repairs, automatically granting model actions and accidentally activating a prompt/model choice.

Freeze 12 new utilities spanning suffix/prefix masking, retry delay/capacity, EN/VI boolean labels, zero-length slicing, last-separator splitting, stable uniqueness, clamped indices, ceiling division and mapping precedence. Two visible and five held-out examples per case. These are same-agent authored deterministic tasks; they are not independent human evaluation, an unseen public benchmark or general coding safety certification. Closely related failure families are deliberate targeted diagnostics, not claimed novel domains.

29 corpus/paired-isolation controls PASS. Before inference all 12 buggy/reference pairs run in existing native capsules: buggy must fail at least one complete suite and reference must pass both; actual 12 oracle tests PASS, 24 capsules, 9.13 seconds, zero model calls. The two private capture controls PASS and prove a six-step reply is saved unchanged and a missing transport body is never fabricated. [Pre-inference receipt](evidence/ce002-pre-inference-freeze.json).

## Fixed comparison and actions

Pair the existing workflow issue with the same issue plus one fixed concise-plan/requirement-check hint. Full source, visible tests, hidden oracles, system prompt, response parser, pure fixture review, native runner and action scopes stay identical. Counterbalance arm order by case index. The hint requests exactly one concise plan entry and internal checking of applicable empty/zero/negative/boundary requirements; it supplies no held-out examples, expected outputs, reference source or new tools. Never trim six steps, relax the schema, repair model output or retry a failed reply. This is explicit experimental issue wording, not a shared/default prompt change.

Exactly one existing CORE attempt per case per arm: at most 24, fast/temperature0/requested max_tokens2048 under the unchanged preset enforcement/original 60-second generation budget. A fresh fixture per measurement, exact separately typed patch/visible-check/held-out-check approvals from the trusted test operator only. Existing review may reject a proposal and grant no actions. Model text cannot approve itself; candidates never execute on the host. All actual work runs through the existing authenticated local TCP/CLI/native workflow. No production database, Vault write, collection, infrastructure, model loading/download, context or resource-cap change.

Capture the exact application-port request and any complete first reply before original response-contract validation. If the existing adapter rejects the transport before returning a body, report that absence explicitly. Preserve every outcome and native exit independently. A protocol PASS means complete bounded measurement; functional repair requires admitted candidate, known exact edit and both actual native suites passing with immutable tests/canary. Generic native quality_evaluated remains false.

Exclusive private campaign: `data/backups/ce002-first`, source/corpus/arm/CORE identity frozen before inference. Existing D46 runner writes only new UUID-indexed case directories, never old first evidence. Supervisor limit 1800 seconds, SIGINT and up to 120 seconds joined retirement; timeout/interruption is retained as a campaign failure, never retried. One ordinary CORE recovery after joined completion. All 719 files from the prior 5596-test snapshot must remain identical; additions have their own focused/native evidence and cannot inherit that full-run claim.

## Acceptance and rollback

Require all 24 first measurements, all 12 independently prevalidated source/oracle pairs, raw replies or explicit transport absence, exact source/CORE identity, no implicit retries, unchanged tests/canaries and joined native cleanup. Publish both functional scores and every failure. No improvement, broad promotion or model/default adoption is implied even if a small arm scores perfectly. Historical D46 7/10 and all D81 failures remain unchanged. Removing the experimental hint/operator returns to the original behavior; no data migration or production rollback is needed.

No architecture change or shared prompt/security modification is introduced, so this milestone needs its explicit protocol rather than a new architecture ADR. Future production adoption or feedback/planner changes require their own architecture review, tests and applicable approval. D70 listening/device/product/model/license/release decisions remain separate.


## Terminal result

All24first measurements complete,111.69s/24protocol testsPASS/0FAIL/0SKIP; functional scores **baseline7/12 and concise7/12**. The hint is not adopted. All12concise replies still contain2–5plan entries rather than the requested1. Existing native/source guards reject3proposals;21admitted candidates receive63distinct fixture approvals/42native capsules.116affected regression testsPASS/0FAIL/0SKIP/26.74s.723source bytes/original719files/COREidentity retained, joined qualified read-only audit complete; listening remains0/24. Original D46score untouched. [First scorecard and every failure](CODE_EVAL_002_FIRST_SCORECARD.md). The campaign scope is consumed; no further same-case model generation is scheduled.
