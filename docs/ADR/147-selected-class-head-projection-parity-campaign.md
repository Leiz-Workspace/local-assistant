# ADR 147 - Selected-class head projection parity campaign

Purpose: remove unused vocabulary projection while retaining original batch shapes, both declared CPU threads and the exact binary scorer semantics.

Date: 2026-11-02. Status: Accepted for one conditional micro/full diagnostic; no model/default adoption.

ADR146 micro failed: maximum score delta0.000164073 and rank changes exceeded the unchanged1e-6criterion, so full dispatch remained0. Keep that failure and do not use batch10. All original-position batching changes are excluded from this proposal.

P1 dependency complete failed batching experiment and inspected pinned SDK implementation. Effort one isolated selected-head prototype, tensor/weight integrity tests and conditional measurement. Risks are numeric differences from projection kernel shapes, SDK wrapper behavior and overestimating memory/dispatch savings. No weights, tokenizer, model/revision, source data or stored vector/schema changes are authorized.

The installed Transformers Qwen3ForCausalLM forward executes its unchanged backbone, selects last hidden positions and applies a bias-free full-vocabulary `lm_head`. Current runtime retains only the last position but still computes every vocabulary output, then uses only original `no`/`yes` rows. Pin this exact SDK source hash. Evaluate selecting those two unchanged original weight rows for `functional.linear` on the identical final backbone hidden state. Keep the original full head/weights resident for verification; do not change `vocab_size`, learned parameters, token IDs, precision, masks, position IDs, batch4, two threads, interop1 or KV-cache policy. Truthfully declare the projection policy in a distinct profile/fingerprint.

Default candidate scoring uses the two-row projection; an explicit verification-only switch retains the old full-vocabulary last-position head. The original all-position/full-head versus optimized reference control must still report exact logits. A three-query micro probe compares both actual live paths and pinned prior scores/ranks before any complete trial. If it fails1e-6/rank/runtime identity, stop. If it passes, execute one full36query/3round/1080pair diagnostic with original CPU480/481seconds, AS8GiB, RSS4096MiB, query60seconds and wall600seconds. Preserve additional child-CPU450 and all1080score/rank parity criteria. No automatic retries or post-observation threshold changes.

Keep original source/config/manifest graphs byte-identical. Only a qualifying complete trial may justify a versioned opt-in evaluation path and a fresh current-source full/audit. Rollback omits the new projection variant. Existing model choices, production routes, historical failed scores, provider and hearing gates remain unchanged.
