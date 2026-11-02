# ADR 149 - Fixed-system-prefix cache parity campaign

Purpose: evaluate reuse of constant system-prefix activations while preserving original model choices, every actual candidate pair and strict score/resource criteria.

Date: 2026-11-02. Status: Accepted for one conditional isolated diagnostic; no runtime/default/model adoption.

## Evidence and assessment

ADR148's complete original-runtime full retained5836PASS/1FAIL/0ERROR/0SKIP in2147.54seconds. The exact original two-thread worker inherited CPU3, but CPU exit152 terminated it after two rounds. All worker thread masks and480/481CPU limits were observed read-only. CORE exited0/reaped, original native0/container inventory restored; independent original DB/security/vector preservation verified with only quota updated_at drift. Scheduling alone is not established as a reliable correction.

P1 dependency is that retained failure and inspected pinned SDK cache/forward implementation. Effort one private prefix prototype, ownership/isolation tests and conditional micro/full measurement. Risks are BF16 shape-dependent numeric drift, mask/position drift, mutable cached tensors, RAM growth, cold overhead and mistaking activation reuse for cached answers. No original source/config/model/weights/SDK/provider/database changes are authorized.

## Separate evaluation contract

A distinct profile truthfully declares conditional prefix KV use, reference-only uncached computation and unchanged two threads/batch4/BF16/SDPA. Retain only the fixed `PREFIX` token window, including its exact original left-padding IDs/masks. Validate every prefix token against the constant system text; no query/document token, score, ranking, oracle or answer is cached. Cache keys include batch shape, all prefix IDs and all prefix masks. Keep at most32entries/1GiB retained KV tensors within unchanged overall AS8GiB/RSS4096MiB guards. At capacity, use the original complete uncached forward without eviction. Clone every retained layer state before continuation so SDK updates cannot mutate stored state. Continue with every remaining original token and the complete original attention mask; let the pinned SDK derive the original absolute positions from the exact prefix length. The cache is process-local and disappears on exit.

The three-query micro probe compares actual original, cold-prefix and warm-prefix paths against the independently pinned old observations, retaining original tokens/ordering. Count actual backbone calls, including prefix prefill and the two unchanged reference-logit controls. Require warm/cold observations exactly equal, every score within1e-6 of both actual old paths, identical rankings and truthful full runtime/profile identity. If any check fails, stop with0full dispatches. No retry.

Only after micro PASS run one36-query/3-round/1080-pair diagnostic with original CPU480/481seconds, AS8GiB, RSS4096MiB, query60seconds and wall600seconds, plus unchanged total child CPU450seconds, all1080score differences at most1e-6 and identical rankings. No criterion is relaxed after observing results. All scores still require real continuation forwards; no cached score may enter inference. The original uncached all-position/last-position reference remains exact.

## Promotion and rollback

Keep all original frozen graphs byte-identical. Any qualifying result requires a separately versioned optional evaluation path, focused controls, a fresh current-source full and read-only preservation review before use. A failed candidate is not promoted. No model replacement, production route/default change, download, host policy/shared-service change or historical score rewrite. Rollback omits the private variant and its process-local cache.
