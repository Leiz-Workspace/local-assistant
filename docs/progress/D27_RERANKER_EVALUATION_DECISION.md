# D27 — Local reranker evaluation decision

**Purpose:** Close the measured local evaluation with an explicit conservative decision, preserving original models, failures and actual evidence limitations.

**Date:** 2026-10-19
**Decision:** Retain the approved dense retrieval path; defer production reranker adoption. Qwen3-Reranker-0.6B remains the original registry nomination and measured candidate. No model replacement, production routing or configuration change.

## Evidence and rationale

Original24-document/36-query authored diagnostic: original CPU BF16 batch4 candidate improves R@3 .972222→1, MRR .949074→1 and nDCG .961613→1 across three stable actual rounds. The descriptive nDCG-gain interval includes0; batch1 CPU attempts remain FAILED/INCOMPLETE. This is a small authored diagnostic, not independent human evidence.

The owner explicitly delegated manual relevance work to the assistant. ADR-042 records that change without fabricating human labels. Original v1 review exposes8 answerable/0 absent cases: doc-d supports a negative answer to the quarterly-approval question, so its minimum-one-absent coverage FAILS before inference. Separately frozen v2 corrects only that ambiguous query before scores, retains original source bytes/seven queries/thresholds and has7 answerable/1 absent assistant judgments. Three actual source/HTTP/model paired rounds complete with stable source/point/generation identity and ranks. **Dense and candidate R@3/R@5/R@10/MRR/nDCG all1 on answerable cases; new diagnostic gain0.** The descriptive gain interval is[0,0], not population significance. Absent support metrics remain null; no calibrated abstention is established. Same-agent authorship/review remains an explicit limitation.

Actual authenticated ASGI complete-response trial and bounded real CORE traffic pass owner/source/lifecycle gates. Full-checkpoint raw evidence retains every sample, model logits/token counts and per-child resource. Focused ten-candidate dense requests average5.616s versus11.593s for fresh-child reranking; concurrent drill averages10.935s with101 overlapping CORE requests. Tiny samples, ordered phases and cache state prohibit causal speedup/SLO claims. New v2 reranker child peak1542.746MiB RAM, verified CPU-only allocation0; not whole-application RAM or CORE VRAM.

Real ephemeral Uvicorn/TCP trial also passes: observed dense5.606043s, two-candidate reranking8.896878s, dense-after-disable5.634908s. Authentication/Origin/foreign-owner fences hold and exact source/point identities are retained. Same fixture event loop/resources are used; this is real loopback TCP, not separate-process/multiworker/load certification. Temporary server, workers and owned fixtures are joined/cleaned.

There is no demonstrated new diagnostic quality advantage to justify enabling this fresh-child ranking path now. Broader independent quality and persistent-runtime performance remain unmeasured. Retaining dense is an evaluation decision that preserves agreed state; it does not silently replace/discard a registry model or require candidate adoption approval. The original positive diagnostic evidence remains available for a future approved integration or runtime optimization.

## Acceptance and rollback

All amended local evaluation gates are measured: original paired diagnostic/failures retained, autonomous AI judgments transparently versioned before inference, three new actual paired rounds, source/owner/delivery/cancel/shutdown checks, ASGI/CORE and real TCP measurements, exact disable-to-dense behavior and clean post-audit. No automatic adoption, confidence calibration or broad production quality PASS.

Verification comprises **1234-test full regression PASS/787.47s**, then **16 new AI-focused PASS/448.97s** and **1 new TCP PASS/40.93s**, each0 SKIP and exit0. This covers1251 unique tests across unchanged frozen source checkpoints; **there was no single1251-test full invocation**. Earlier46/31 focused cases are subsets of1234 and are not added twice. No application source changes occurred between these runs. The additional17 tests/modules are isolated and all fixtures/resources were independently audited clean.

D27 is **PASS for local evaluation/decision**; candidate is **not adopted/deployed**. D28 grounded generation/citations can proceed using the unchanged approved dense retrieval and CORE model. General/human-independent quality, persistent-model optimization, multiworker/off-host DR and deployment load/SLOs remain future evidence, not claimed complete. Any future agreed-model/routing change still requires owner approval and benchmark/performance/resources/migration/rollback.

No production migration executed. Ranking preserves embedding fingerprint, source/point/generation identity and needs no reindex. Test-only enablement is undone by restoring dense service composition and draining/joining its child. Future production rollback must likewise disable/drain without deleting models, sources, journal obligations, collections or existing data.
