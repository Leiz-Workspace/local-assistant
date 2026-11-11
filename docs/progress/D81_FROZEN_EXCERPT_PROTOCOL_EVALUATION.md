# D81-FMT-002 — First frozen bilingual excerpt protocol evaluation

**Purpose:** Record first actual existing-CORE results, preserve failed observations and distinguish format admission from answer correctness.

**Date:** 2026-10-24 (Asia/Ho_Chi_Minh). **Status:** Six-case observations COMPLETE; quality **FAIL (1/6 accepted)**. No production prompt integration or model change. [ADR 126](../ADR/126-frozen-core-excerpt-protocol-evaluation.md).

## Fixed protocol and actual outcome

The new runner/corpus were committed before inference; corrected execution snapshot `440ae44`. Three EN and three VI authored cases each provide file/code/web text, separate host-only exact values and minimal excerpt oracles. The request supplies fact keys and a fixed unrelated formatting example, without oracle values/excerpts/offsets. Existing D80 system template/gateway/Fast512 and original CORE process remain unchanged. This is a small same-agent-authored protocol evaluation, not independent human or broad model-quality certification.

| Case | Exact fact object | Literal unique quotes | Exact excerpt quotes | Guard admitted | Full contract |
|---|---|---|---|---|---|
| excerpt-en-01 | PASS |3/3|3/3|Yes|PASS|
| excerpt-en-02 | FAIL |3/3|2/3|No|FAIL|
| excerpt-en-03 | FAIL |3/3|3/3|Yes|FAIL|
| excerpt-vi-01 | FAIL |3/3|3/3|Yes|FAIL|
| excerpt-vi-02 | FAIL |3/3|2/3|No|FAIL|
| excerpt-vi-03 | FAIL |3/3|3/3|Yes|FAIL|

Total: **1/6 full contracts, 1/6 exact fact objects, 18/18 literal unique quotes, 16/18 exact excerpts, 4/6 guard admissions**. Every case received exactly one model response, all retained. Each case took2.149–2.590seconds including composition/gateway/artifact overhead; this is not model-only latency or an SLO benchmark. CLI exit2 honestly reports complete observations with failed quality.

Case02 returned a source instruction as the retention fact and citation instead of19days. Other failures include copying whole supporting sentences/assignments instead of extracting their values, changing a requested fact key and substituting source IDs for fact keys. Case05 also added the neighboring VAT sentence to its quote. No source instruction was executed: this text-only composition has no tool/action capability. Literal occurrence alone is not evidence that a statement is a valid requested fact. In particular, the excerpt guard admits four correctly quoted replies while three of them still fail fact-object checks; its documented lack of semantic certification remains material.

## Retained first failures and integrity

The first startup directory `data/backups/d81-fmt002-first` is empty because manifest serialization failed before any model request. The corresponding log is preserved. Only the new artifact serializer was corrected and covered by an actual712-file manifest regression; existing16KiB MCP/request limits remain unchanged. This was not a retry of a model response.

First actual inference is exclusively under `data/backups/d81-fmt002-first-inference`: frozen protocol/712source hashes, private attempt records, native request and decoded native-response payload bytes, HTTP completeness receipts, unchanged gateway/profile outputs, separate scores and final result. Transport retains incomplete/error payloads before gateway rejection; no output trimming/normalization/repair/tuning or neural retry occurred. [Digest/count verification](../evidence/d81-fmt002-first-verification.json).

Same original CORE PID37256/start63900/command/context, text recovery PASS. Final point measurement: RSS RAM8,842,544KiB and NVIDIA process allocation VRAM9386MiB, separately labeled; not model-only/peak/minimum requirements. No model load/download/fallback/replacement/default, context change, endpoint activation or database/infrastructure mutation by this evaluation. Original D81 first response, original1/3format/3/3grounding and D70actual-listening labels remain unchanged.

## Decisions and remaining work

**Do not adopt this per-request protocol as a validated product contract.** Keep D81 model adherence OPEN and the original profile templates unchanged. The deterministic guard component remains verified within its narrower scope; it cannot fill semantic fields from host oracles or silently substitute an answer. Any future remediation must declare a protocol/source-authorized product design, independent factual/schema checks and fresh frozen cases before measuring; keep this1/6 result immutable. No replacement model is proposed.

Corrected preparation:36new controls within132related PASS/0FAIL/0SKIP/0.66s, Ruff PASS. Fresh full software regression is a separate current712-file freeze,5507tests collected; read its terminal receipt before declaring PASS. Owner-deferred hearing/device tests, voice/model/license decisions, originalD14quality and final release acceptance remain open.

**Full-run follow-up:** First execution ended5505PASS/2FAIL/0SKIP because the caller's0077umask changed two intended public-permission fixtures toprivate. Controlled0022reproduction passes both unchanged tests; no production/source repair. Separate completecorrected run is active, with identical712source bytes. [Exact environment diagnosis and subsequent evidence](D90_ARTIFACT_PROVENANCE_SNAPSHOT.md). This does not change the model's1/6quality failure.
