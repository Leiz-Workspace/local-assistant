# D27-T02 — Original Qwen reranker comparison

**Purpose:** Report isolated candidate execution, all attempted runtime variants and the remaining adoption boundary.

## Scope and protected baseline

The owner requested continuation after the concrete T02 plan. ADR-039 authorizes evaluation-only provisioning/inference of the original Qwen3-Reranker-0.6B candidate; it does not select/deploy the model. Approved Qwen embedding, E5 rollback, CORE/UNRESTRICTED, source/ACL/generation behavior and schema0004 remain unchanged. No candidate vector/source/DB/Vault/Docker writes or API integration are performed.

Use official revision e61197ed45024b0ed8a2d74b80b4d909f1255473, verified four artifact size/SHA256 identities and no/yes token IDs2152/9693. Weights live only under the separate ignored ID `models/embedding/qwen3-reranker-0.6b-bf16-cpu-eval`; the existing artifact helper cache path is not a selection or embedding collection. Separate frozen offline uv environment reuses reviewed CPU package versions without changing project/embedding dependencies. [Provisioning evidence](evidence/d27-t02-provisioning.json).

Source bindings, fixed top10 candidates,36 queries, binary labels, thresholds and baseline SHA are verified before launch. Relevance labels are not given to the worker. Complete official prefix/instruction/query/document/suffix input is counted before tensor creation;512 accepted/513 rejected, no silent truncation. Final-position no/yes logits use finite float32 softmax. Relative ranking probabilities are not calibrated confidence. Three actual score repetitions are required; no replayed score counts as a new measurement.

## Retained execution attempts

| Attempt | Runtime | Observed outcome |
|---|---|---|
| v1 | CPU BF16 batch1, full vocabulary head at every input position |41 tests PASS/1 FAIL in244.05s; incomplete worker failure near CPU limit, exact signal not logged; no accepted comparison metrics |
| v2 | CPU BF16 batch1, only final vocabulary-head position, exact original-reference probe |42 tests PASS/1 FAIL in242.76s; logged exit152=128+SIGXCPU24,2/3 rounds completed; frozen CPU budget failed, no complete metrics |
| v3 | Separate CPU BF16 batch4 runtime profile, candidates4+4+2 with left padding/masks, final-head optimization | **PASS local batch4 measurement**;44 focused PASS/234.51s, full1096 PASS/540.75s,0 SKIP; actual three rounds complete/stable |

[Initial failure](evidence/d27-t02-initial-failure.json), [confirmed v2 CPU failure](evidence/d27-t02-v2-failure.json), immutable v1/v2 manifests and protected initial source archives retain unsuccessful work. Do not represent the batch1 proposal as resource-qualified.

Pinned Transformers4.57.6 implements `logits_to_keep=1` by selecting final hidden positions before the vocabulary projection. Before accepting v2/v3, a real frozen singleton pair must produce exact final no/yes logits versus the original full-head computation. Batch4 additionally changes padding/matmul shape; those logits are not asserted bit-identical to batch1. Independent golden-array tests verify left-padding IDs, masks, counts, last-position selection and source/output alignment. [ADR-039](ADR/039-isolated-qwen-reranker-comparison.md), [ADR-040](ADR/040-reranker-batch4-evaluation-variant.md).

All attempts retain the same4GiB actual process RSS,8GiB virtual address ceiling,60s/query,480/481s child CPU and600s parent wall limits. GPU allocation0 is verified from CPU-only Torch/model devices, not host GPU inventory. Watchdogs kill their own worker; parent-death pidfd and cancellation/timeout kill/join prevent live model orphans. Actual peak RAM includes model load, the parity probe and measured rounds, not disk size or parent cumulative RSS. Fresh-process model initialization includes artifact verification, with filesystem cache uncontrolled. Ten-pair query timing excludes that initialization, embedding/retrieval and HTTP; it must not be relabeled as end-to-end application latency.

## Decision gates

The unchanged T01 plan requires no Recall@10 loss, macro R@3/MRR nonregression, per-group R@3 loss<=.05 and nDCG@10 gain>=.02, plus protocol/reproducibility/resources. Every repetition and failed check must remain visible. Candidate may only reorder identical fixed candidates; it cannot recover a source absent from that set. Same scores use stable document-ID ties. Query bootstrap deltas are descriptive because36 authored queries share12 intents; focused nDCG-delta95% interval[0,.094657] includes0. Independent human-reviewed quality is still unvalidated.

Current baseline R@3=.972222, MRR@10=.949074, nDCG@10=.961613, R@10=1 on the authored diagnostic corpus. Focused batch4 measurement: R@3/R@5/R@10/MRR@10/nDCG@10 all1.0; three rounds stable, all frozen quality/RSS/query/device gates met. Delta R@3+.027778, MRR+.050926, nDCG+.038387. Peak candidate RSS1594.512MiB (RAM), GPU allocation0 by CPU-only verification; cold load2.276442s, warm ten-pair query p50≈2120.184ms/p95≈2232.294ms/max≈2298.982ms over108 samples. Actual singleton full-head/final-head no/yes logits exactly[12.375,21.25]. Final full1096 PASS/540.75s,0 SKIP; original batch1 failures remain failures. No quality score was invented from an incomplete attempt.

D27 remains IN PROGRESS, D28 not started. T03 must review actual results, independent judgments, sustained resource/latency and an adoption decision. Even successful diagnostic gates do not authorize changing model/routing. Proposed integration would keep embedding/vector/source identity, add only an approved ranking stage behind a default-off control, retain owner/root/active-source checks through model delay and revalidate before delivery. Disable/drain would restore the original dense path without deleting sources/journals/ownership/collections. No integration or migration patch is implemented here.

## Final local acceptance — 2026-10-19

**Purpose:** Record the actual complete comparison without model adoption or erasing failed profiles.

T02 batch4 measurement accepted after1096 PASS in540.75s,0 SKIP.37 unit+7 actual cases; full/focused quality identical, three ranks stable, all frozen diagnostic gates met. Final peak process RSS1596.055MiB RAM/GPU allocation0; fresh model-session load2.300225s, ten-pair warm p50≈2120.524ms/p95≈2238.943ms/max≈2292.312ms over108 samples. Real singleton full-head/final-head no/yes logits exactly[12.375,21.25]. Goldens plus actual512/513 tokens, cancellation/timeout/parent SIGKILL and real RSS/query watchdog kills passed. No application/default model routing change.

[Complete comparison](evidence/d27-t02-reranker-comparison.json), [acceptance](evidence/d27-t02-acceptance.json), [post-audit](evidence/d27-t02-post-audit.json) and [T03 proposal](D27_RERANKER_ADOPTION_REVIEW.md). Post-audit schema0004 and original grants/owners/ACLs preserved; jobs/heads/files/quota/probe DBs/collections/model processes/advisory locks0. Batch1 remains FAILED/INCOMPLETE. D27 IN PROGRESS, T03 NEXT, D28 not started.
