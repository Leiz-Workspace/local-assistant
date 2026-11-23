# D81-FMT-004 — Declared schema order follow-up

**Purpose:** Verify the concrete schema wire-order bug fix on fresh frozen data without retrying or replacing failed v1 observations.

**Date:** 2026-10-24 (Asia/Ho_Chi_Minh). **Status:** EXECUTED/CLOSED/NOT QUALIFIED. Both positive modes5/6; explicit refusals2/2. Historical workflow NOT_RUN; raw Unicode mismatch retained.

P2 existing D81remediation; depends on the red wire-order reproducer, primary pinned runtime parser/grammar source and unchanged established CORE. Effort one bug-fix/measurement milestone. Risks: treating JSON canonicalization as grammar-neutral, overfitting old cases, changing scalar/quote/refusal criteria after observing errors, masking an unknown semantic failure and confusing a small protocol with general model quality.

The native API parser keeps object member order, and its grammar emits properties in that order. The old serializer reordered schema into citations-first while the request/example asks facts-first. Preserve host declaration order in request/schema bytes; use the old canonical representation only for prompt provenance hashing. Exact native/schema byte hashes remain order-sensitive. New positive unit checks actual transmitted property order; first red test and original model failures remain retained. Existing model, system template, source-unit rules, local scalar/quote/usage guards and refusal criteria remain unchanged.

Freeze `tests/fixtures/harness/d81-typed-paired-v2.json`: six new EN/VIpositive cases and two new missing/instruction-only negatives before inference. Compare baseline and schema once each on the same positive messages; only `response_format` differs. Two negatives schema-only. Require all six schema fact objects/18exact excerpts and both explicit negative refusals with no answer publication. Only then run one original native file/code/authored-web fixture with the original question/oracle, excluded from fresh scores. No postprocessing, feedback/regeneration or score normalization.

Maximum16requests including ordinary recovery, Fast512/temperature0/20seconds each, campaign360seconds plus recovery30seconds, same original CORE identity/resource configuration. No new weights/SDK/models, default/API activation, service/config/database/collection changes. Fresh exclusive private directory; capture every first payload before gateway/local validation. Explicit `--corpus` path and its hash bind the version. Earlier v1raw data/oracles/criteria/source commit remain immutable; fixing this implementation does not relabel v1asPASS.

Prepared67new controls within199related PASS/0FAIL/0SKIP/0.79s, RuffPASS. Existing full5507passed on its712-file foundation; these additive components have scoped tests and native verification separately. Acceptance and remaining model/manual/product/release gates follow ADR127. This is one finite fresh follow-up, not an automatic until-pass loop or model replacement authorization.

```sh
uv run --no-sync python -m scripts.structured_excerpt_evaluation data/backups/d81-structured-order-first --corpus tests/fixtures/harness/d81-typed-paired-v2.json
```

Actual snapshot7599624 kept718source bytes unchanged,14posts plus one recovery, same original CORE. Both modes dropped the combining accent from scalar `cafe\u0301-z`; schema quote preserved it while the scalar became `cafe-z`. Both unsupported scalars were withheld; neither raw output nor source was normalized to accept it. [First observations/executed source](../evidence/d81-structured-order-first-verification.json). This finite scope is consumed. The [separate source-spelling follow-up](../ADR/128-source-derived-string-vocabulary.md) addresses the identified scalar-domain gap on fresh data; it does not change this FAIL.
