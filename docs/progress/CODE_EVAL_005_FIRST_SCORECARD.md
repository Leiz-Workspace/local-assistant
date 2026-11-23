# CODE-EVAL-005 first scorecard

Purpose: retain the original twelve first results before any review-policy correction.

Date: 2026-11-02. Snapshot: `be08b57`, 745 application files. Native mode: `coding_reasoning_v2`, original CORE, 1536 reasoning/2048 total tokens. Exactly twelve first generations, no feedback or retry; all twelve protocol measurements completed.

**First functional result: 11/12; unchanged 12/12 criterion FAIL.** `ce005-split-final-component` was rejected as `unreviewed_call` because the candidate uses `str.rfind`, absent from the fixture review vocabulary. It received no patch/check approval and no native functional result. Its source appears consistent with the issue; that observation is not a functional PASS. All other eleven cases passed visible and held-out native tests with exact API/import/audit preservation.

[Immutable first result](../evidence/ce005-first-result.json) and [exact first inputs](../evidence/ce005-review-correction-inputs.json) bind every request/reply/native wire/measurement. Later review-policy maintenance must preserve this result and candidate bytes, use no new inference and report separately. Original CE0049/12, CE0034/6, CE0027/12 and D46first7/10 remain unchanged. The targeted same-agent-authored cohort does not establish broad independent coding quality.

Corrected WEB004 separately completed the unchanged three-claim workflow with one CORE assessment, one native DOCX/PDF batch, archive reopening after proof revocation, and actual visual inspection of all three pages. The intermediate full collected5830items and was interrupted before the first completed-test log line to address this discovered reviewer false negative; it is not software acceptance. Owned CORE exited0/reaped/guardNone and the exact original native0/15-container inventory was restored. A final current-source full and read-only audit remain required.


2026-11-02 correction: absence of a completed test line did not mean the first fixture had not started. The intermediate run had created one142-byte test file/index job before group SIGTERM bypassed teardown. This caused the later complete5836PASS/1FAIL/0ERROR/0SKIP full to reject the global40-byte quota test. [ADR142](../ADR/142-owned-interrupted-fixture-recovery-and-graceful-retirement.md) records independent owner/namespace/content/time proof, exact owned cleanup and graceful descendant-pytest teardown. The original October18zero-usage owner was preserved. Actual post-recovery fingerprints/security/runtime match the original baseline with only quota updated_at drift; no original row is reset to force acceptance. The earlier interrupted/failed fulls remain unsuccessful. A new clean-preflight full is required.
