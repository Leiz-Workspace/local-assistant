# D70 Voxtral first paired attention diagnostic

**Purpose:** Record the explicitly approved original-weight eager/SDPA comparison, complete numerical evidence and remaining D70 gate without changing historical qualification or selecting a backend/model.

**Date:** 2026-10-23. **Status: DIAGNOSTIC COMPLETE; ANSWERS UNCHANGED; REVIEWER NOT QUALIFIED. D70 NATURALNESS OPEN; D71 NOT STARTED.** [Immutable first result](evidence/d70-voxtral-attention-first.json), [approval/executed-source freeze](evidence/d70-voxtral-attention-approved-freeze.json), [ADR-110](ADR/110-proposed-voxtral-paired-attention-diagnostic.md).

## Actual execution and first observations

The owner explicitly replied **“Duyệt một lượt ADR-110”** for commit `a950539`. Exactly one original-weight worker performed8explicit uncached diagnostic forwards and8first generations on4historical presence inputs, in fixed eager-then-SDPA order. One no-weights worker replayed the native conditioning. No retry, new download/package, alternate prompt, generation repair, qualification rerun or common24audio review.

| Historical input | Expected presence | Eager raw answer | SDPA raw answer | Maximum absolute logit difference | RMS logit difference |
|---|---|---|---|---:|---:|
| EN speech, old clip-01 | YES | NO | NO |0.53125 |0.208502114 |
| Exact silence, old clip-05 | NO | YES | YES |0.25 |0.049059987 |
| Seeded noise, old clip-06 | NO | NO | NO |0.375 |0.068581313 |
| VI speech, old clip-08 | YES | NO | NO |0.375 |0.113380045 |

All8raw answers match the historical ADR109 answers. All8have native EOS2 and valid preregistered schema. Each backend matches1/4historical expectations descriptively; these reused diagnostic inputs are **not a new qualification benchmark**. The original twelve-control **4/12FAIL remains unchanged**.

All4full logit vectors differ between backends, while all4argmax choices agree. Each generated first token also matches its explicit uncached forward argmax. For noise, SDPA's NO and YES logits both equal26.375 and native argmax selects NO; the tie is retained. These logits are not calibrated confidence scores or naturalness evidence. Backend changes produce real numerical differences, but switching to eager does **not** fix these four answers. This does not exclude every numerical/prompt/runtime cause or establish intrinsic universal model quality; language/comparison controls were not rerun.

## Independent numerical and fidelity audit

All8complete131072-element FP32 little-endian vectors are retained in the original worker stderr: **4,194,304raw vector bytes**, base64 encoded within the existing8MiBstderr limit. Parent independently decodes and verifies exact hashes, finite values, argmax, maximum difference, RMS and exact-byte equality, rather than trusting summary metrics. Original stderr/stdout, first result/freeze and all hashes remain preserved.

Both backend conditioning receipts exactly match the historical full-source prefix/native zero-padding/input-ID/FP32/BF16 features and the independent no-weights replay. All762native tensor receipts match ADR108. Post-comparison payload hashes and storage pointers remain unchanged. The approved executing source was fully archived and independently checked before retiring the permission switch. All661canonical source files now match the exact reviewed pre-run bytes; no permanent source change was needed.

## Measured resources and preserved state

Worker wall **217.312967s**, replay **5.337580s**, both exit0/no timeout/owned processes reaped. Whole-worker peak **RSS RAM10,030,560KiB =9.565887GiB**; virtual **VmPeak10,735,144KiB =10.237831GiB**, below the retained12GiBaddress-space cap. These include loading, integrity hashes, both attention backends, processor, forwards, generation, vectors and post-audit; they are not model-only incremental RAM or VRAM. This establishes fit for this exact diagnostic, not arbitrary longer eager inputs or minimum required host RAM.

Sampled MemAvailable immediately before launch **21,721,317,376bytes**, above the retained14GiBhost guard; no reservation. CPU2/inter-op1/affinity0,1/offline; no evaluator GPU. Original CORE stayed loaded with PID37256/start63900/same command hash/context32768 and9386MiB NVIDIA process allocation; literal text recovery passed. No context reduction, restart, cap change, model/default/registry/Docker/Vault/database/config/collection migration.

Final integrity audit verifies661source/all661reviewed bytes restored,917protected files,176original inputs,53prior immutable D70 evidence files,23,475original TTS SDK entries,23,382old reviewer SDK entries/16artifacts,19,561Voxtral SDK entries/all9artifacts, original services/data/security/quota/vector state and same CORE.24pending human-listening fields remain null/unlistened; all prior failures and D24/a88584b/E5 rollback remain untouched.

Final **470TTS-related tests PASS64.25s, 0FAIL/0SKIP; Ruff PASS**. One existing deliberate duplicate-archive-fixture warning. No full661-source regression or auditory qualification PASS is claimed.

## Closure and next dependency

The one ADR110 diagnostic is complete and its scope consumed. `EXECUTION_ALLOWED=False` is restored to the exact reviewed worker bytes; original model worker count remaining0. No backend/model is selected, no naturalness label/MOS is created and no24audio review follows. The backend-only repair hypothesis is unsupported by these four unchanged answers; the broader root cause remains unresolved.

`AUDIO-EVAL-VOXTRAL-DIAG-005` closes this bounded investigation with **no demonstrated causal fix**. Reviewer-reliability remains open: D70 needs an evaluator with valid independent auditory qualification and actual naturalness assessment under unchanged AC. No additional original-weight experiment, model download/replacement, prompt retuning or resource expansion is scheduled. D71 remains gated by D70, consistent with the owner's rejected ADR097 sequencing waiver.
