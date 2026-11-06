# ADR 146 - Query-batch consolidation with original-position parity

Purpose: assess actual redundant forward overhead rather than raising resource limits or accepting an insufficient-headroom trial.

Date: 2026-11-02. Status: Accepted for one conditional micro-parity/full diagnostic campaign; no model/default adoption.

The one-thread batch4 trial completed original gates and matched all1080two-thread scores exactly, but CPU465.299seconds exceeded450. It remains NOT ELIGIBLE. Tokenizer-only measurement found39792real versus41444padded tokens; length grouping saves only2.302%. Retain the first tokenizer import failure, corrected zero-forward measurement and all trial results.

P1 dependency measured one-thread parity and padding work; effort one separately named batching prototype, independent mask/position tests and conditional measurement. Risks are numeric changes from batching, incorrect RoPE positions, more activation memory and misleading fewer-forward accounting. Model/revision/weights/SDK and source text remain unchanged; no migration of stored vectors/data or production activation is authorized.

Consolidate each query's10complete pairs into one batch instead of4+4+2. This still computes all1080pairs over36queries/3rounds; it removes repeated dispatch/weight-streaming passes rather than dropping pairs or using cached scores. Static token count becomes42490padded tokens,2.52% above the batch4baseline, so performance must be measured. Declare batch10 truthfully in a separate profile and fingerprint, retaining one intra-op/one inter-op thread, BF16/SDPA and all original limits.

Preserve every real token's original batch4 absolute position by explicitly passing per-row position IDs; additional left padding remains masked. Original-width values are computed solely from the unchanged tokenizer/input, never reference scores. Default batch4 scoring must retain its old path. Bound each width/offset and preserve original document order/count,512-token rejection and complete prefixes/suffixes. Validate matrices against independent authored position/mask examples.

One campaign: first load the existing model in an isolated guarded worker and compare old4+4+2 versus consolidated10 on three query IDs frozen from token-length statistics (minimum/median/maximum padding increase). Require rank equality and score delta≤1e-6 against both actual old-path scores and the pinned earlier reference. This probe uses no cached values for inference. If any gate fails, stop without full trial. If all pass, run one complete36query/3round comparison in a new worker with fresh original CPU480/481seconds/AS8GiB/RSS4096MiB/query60seconds/wall600seconds. Additional total-child-CPU450 and all1080cross-thread score/rank parity criteria remain unchanged. Keep every first outcome; no automatic retry or post-result criterion change.

Only a qualifying complete campaign may justify a versioned opt-in public evaluation variant and fresh full software/data/runtime verification. Original batch4 one/two-thread paths and failed fulls remain auditable. Rollback omits the new variant; no model replacement, provider request, schema/ACL change or hearing label is implied.
