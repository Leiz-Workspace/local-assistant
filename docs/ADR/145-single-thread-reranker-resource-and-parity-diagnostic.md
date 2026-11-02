# ADR 145 - Single-thread reranker resource and parity diagnostic

Purpose: evaluate a truthful separate CPU-thread profile after two passive two-thread trials missed the unchanged headroom criterion.

Date: 2026-11-02. Status: Accepted for one isolated diagnostic under the owner's current verification request; no model/default adoption.

Normal-affinity passive completed three rounds/original gates at473.229childCPU seconds; preferred physical cores1,3 completed at482.273seconds. Both exceed450 and remain NOT ELIGIBLE. Do not increase the ceiling, repeat these configurations or declare affinity a stable remedy.

P1, dependency retained first measurements and joined clean runtime. Effort a separately frozen private one-thread profile/runtime/worker/comparison and parity controls. Risk is slower wall latency, numeric differences between thread layouts, profile mislabeling and a larger source graph. No model replacement, weights/SDK download or production activation is authorized.

Copy the original runtime/worker/comparison into a distinct diagnostic namespace. Change only the declared intra-op thread count2→1, exact corresponding request/contract fingerprints and source paths, plus the previously assessed passive-wait environment. Preserve batch4, interop1, model/revision/artifact hashes, BF16/SDPA, complete prefix/query/document/suffix tokens,512-token refusal, all36queries/3rounds/forward calls, reference-logit parity and every original quality/resource assertion. Keep original files/configs/manifests byte-identical. A separate profile must truthfully state1thread; never rewrite a1thread result as the original2thread contract.

Snapshot the existing actual successful two-thread comparison before inference and pin its complete raw rounds. It supplies only a post-execution parity oracle, never worker inputs or cached forward scores. Preregister identical document rank order per query and maximum absolute score delta1e-6 across all three rounds. Verify those conditions independently after actual one-thread inference.

One normal-affinity CPU-only/offline attempt; unchanged CPU480/481seconds, AS8GiB, RSS4096MiB, query60seconds, wall600seconds. Additional child-CPU450-second eligibility remains mandatory alongside original gates and cross-thread parity. No automatic retry. Retain all outputs/failures and actual thread/model identities. Only a qualifying diagnostic may justify a versioned opt-in public evaluation path, followed by current-source full and read-only audit. Production model choices, schemas, vectors and original CE005/D60 observations stay unchanged; rollback omits the new runtime variant.
