# D70 Voxtral first auditory campaign

> **Trạng thái hiện tại — 2026-10-24:** D70 đã hoàn tất đo máy; nghe thực tế **0/24, chủ dự án để test sau**. [ADR-111](ADR/111-owner-deferred-tts-listening-and-explicit-recording.md) đã cho phép tiếp tục; D71–D73 đã kiểm chứng phạm vi local, D74 còn nghiệm thu sản phẩm. Các dòng “D71 NOT STARTED” ở lịch sử bên dưới mô tả thời điểm trước quyết định này. Các guard research vẫn đóng; xem phê duyệt và lượt chạy theo đúng ngày của từng thí nghiệm. Không mở lại evaluator campaign hoặc sửa điểm/nhãn cũ. Xem [trạng thái dự án hiện tại](RELEASE_CANDIDATE_STATUS.md), [hướng dẫn nghe](D70_MANUAL_LISTENING_TEST.md).

**Historical actual checkpoint2026-10-23:** Approved ADR110 completed; eager/SDPA first answers unchanged on4historical presence cases, full-vector differences retained/audited. Scope consumed/guardFalse, no backend/model selection. D70 naturalness OPEN/D71 NOT STARTED. [Actual result](D70_VOXTRAL_ATTENTION_DIAGNOSTIC.md).

**Purpose:** Record the approved ADR-109 first observations, strict qualification failure, resource measurements and remaining D70 gate without changing models or acceptance criteria.

**Date:** 2026-10-23. **Status: FAIL — 4/12 controls. D70 NATURALNESS OPEN; D71 NOT STARTED.** [Immutable first evidence](evidence/d70-voxtral-auditory-first.json), [explicit approval/source freeze](evidence/d70-voxtral-auditory-approved-freeze.json), [ADR-109](ADR/109-proposed-voxtral-auditory-qualification-and-conditional-review.md).

## Approved and executed scope

The owner explicitly approved “Duyệt campaign ADR-109” for commit `2348566`. One original-weight CPU worker processed the twelve frozen blind controls. One separate no-weights worker replayed their native conditioning. There was no retry, new artifact/package download, GPU evaluator, resource increase, external upload or model selection. The conditional twenty-four-audio phase was authorized only if every existing gate passed; its condition failed, so neither its packet nor its worker was created.

The retained checkpoint, revision, SDK, native BF16/FP32 payloads, source signals and native decoder were used exactly as frozen. All 762 tensor receipts matched the accepted ADR-108 first load; SDPA switching preserved native payloads and storage. All twelve first outputs ended with native EOS and parsed under the preregistered rules. Independent no-weights replay matched every original conditioning receipt, including full source prefixes, native zero padding, input IDs and FP32/BF16 features. These checks establish the recorded execution's integrity, not auditory competence.

## First control results

| Control | Source or authored transformation | Expected | First answer | Match |
|---|---|---|---|---|
| clip-01 | EN speech presence | YES | NO | No |
| clip-02 | EN language | ENGLISH | ENGLISH | Yes |
| clip-03 | Identical EN pair | EQUAL | SECOND | No |
| clip-04 | EN middle-half gap, second | SECOND | SECOND | Yes |
| clip-05 | Exact silence presence | NO | YES | No |
| clip-06 | Seeded noise presence | NO | NO | Yes |
| clip-07 | VI clipping, second | SECOND | SECOND | Yes |
| clip-08 | VI speech presence | YES | NO | No |
| clip-09 | Identical VI pair | EQUAL | SECOND | No |
| clip-10 | VI language | VIETNAMESE | ENGLISH | No |
| clip-11 | EN clipping, first | FIRST | UNCERTAIN | No |
| clip-12 | VI middle-half gap, first | FIRST | SECOND | No |

Presence **1/4**, language **1/2**, comparisons **2/6**: **4/12**, below the unchanged requirement **12/12**. `UNCERTAIN` remains an honest retained response and fails its factual control. The identical pairs have equal source and native padded waveform hashes. Ten distinct FP32 and BF16 feature hashes across the twelve cases show that a single constant feature was not reused for all cases; this does not independently validate every semantic aspect of the native implementation. No response, label, prompt or threshold was repaired after observation.

These observations disqualify this exact checkpoint/SDK/CPU-SDPA/prompt combination for the proposed reviewer role. They do not isolate a causal defect, establish universal Voxtral quality, demonstrate naturalness competence or provide human MOS. Payload fidelity, successful parsing and feature replay cannot by themselves exclude all implementation/numerical/prompt issues. A source-only investigation may continue without running a new trial; a revised neural experiment needs a preregistered proposal and the owner's approval under the existing model rule.

## Measured resources and closure

Original worker wall **238.164530s**, exit0/no timeout; no-weights replay **5.379030s**, exit0/no timeout. Both owned workers were reaped. Process exit0 describes complete observations, **not a qualification PASS**.

Whole original worker peak **RSS RAM 9,886,292KiB = 9.428303GiB**; virtual **VmPeak 10,736,124KiB = 10.238766GiB**, below the retained **12GiB address-space cap**. This peak includes SDK imports, loading, tensor audits, SDPA switch, processor and twelve controls; it is not model-only incremental RAM or VRAM. Sampled MemAvailable immediately before launch was **21,663,969,280bytes**, above the retained **14GiB** host guard; it was not reserved. CPU2/inter-op1/affinity0,1 and offline isolation were retained. No evaluator GPU allocation was measured or requested.

The original CORE stayed loaded: PID37256/start63900/same command hash, context32768 and9386MiB NVIDIA process allocation; literal text recovery passed. No restart, context reduction, Docker/Vault/database/config/default/model change. Final readonly audit verified656source files, all655other final source bytes unchanged,917protected files,176original inputs,38prior D70 evidence files,23,475original TTS SDK entries,23,382old reviewer SDK entries/16artifacts and19,561Voxtral SDK entries/all9artifacts, original services/data/security/collections and the same CORE. The only final source extension is an explicit permission-switch unit test.

The auditory guard was restored to its exact reviewed closed bytes only after independently checking the executed source and first raw gate. Full executed sources and approved ADR bytes are retained. All24original pending human-listening fields remain null/unlistened; no common benchmark output was sent to Voxtral. Earlier Qwen failures, public service errors, preparation evidence and load-only PASS remain unchanged.

Final **432 TTS-related tests PASS in40.13s, 0FAIL/0SKIP; Ruff PASS**. Preflight431PASS40.96s; the updated auditory test file27PASS10.78s, including one new positive permission-switch regression without original model inference. One existing deliberate duplicate-archive-fixture warning. This is related software coverage, not a full656-source regression or a successful auditory benchmark.

## Remaining work

`AUDIO-EVAL-VOXTRAL-QUAL-004` is executed and closed **FAIL**, with its one-campaign scope consumed. D70's naturalness criterion remains unmet; D71 remains gated by the owner's unchanged AC and rejected ADR-097 sequencing waiver. The reviewer-reliability parent stays open. A [source-only comparison](evidence/d70-voxtral-auditory-source-triage.json) of the pinned native conditioning, forward/cache, decoder and model-card path is now complete, with no demonstrated causal fix. No model is approved for replacement and no new neural trial is scheduled. Any proposed experiment must retain first failures and define independent controls, resources, migration/rollback implications and approval before execution.

## 2026-10-23 further synthetic diagnosis complete; ADR-110 prepared, original execution closed

[Investigation and limits](D70_VOXTRAL_SYNTHETIC_DIAGNOSTICS.md), [prepared source/test/audit evidence](evidence/d70-voxtral-attention-protocol-prepared.json), [concrete ADR-110](ADR/110-proposed-voxtral-paired-attention-diagnostic.md). Standard versus pread loading preserves nonpersistent FP32 RoPE buffers and exact logits on a7,116parameter fixture; eager/SDPA cache routing is correct on tiny random inputs. A random1280width/20head/1500position attention block preserves bidirectionality, with maximum difference0.000244140625 within declared tolerance. Four authored mel inputs match independent Mistral-filter/STFT math exactly. These tests establish no causal fix or original-weight quality.

New paired controller/runtime retain both backend first responses and full131072-element FP32 logit vectors; the parent independently recomputes hashes/argmax/differences/RMS and source-bound no-weights replay. Actual native paired forwarding/generation is tested only on a random2,114,232parameter fixture with authored silence; its random invalid labels/non-EOS responses remain unmodified and are not qualification evidence. Final **470TTSrelated PASS64.37s/0FAIL/0SKIP/Ruff PASS**,38new tests, one existing deliberate duplicate-archive warning; not full661-source regression. Fresh audit661source/all656prior bytes/917protected/176inputs/52immutableD70JSON/threeSDKs/all prior artifacts/originalservices/data/security/sameCORE/24pending human labels preserved.

AUDIO-EVAL-VOXTRAL-DIAG-005 now has protocol/code/tests/local4signal/6file packet complete. **Execution NOT APPROVED/NOT RUN; guardFalse.** Proposed one original-weight worker compares eager then SDPA on four historical presence signals,8explicit forwards+8first responses, then one no-weights replay. Retain12GiBAS/14GiBhostguard/CPU2/offline/COREloaded/20GiBroot; worker900swall/retained1200sCPU, replay120swall. No new weights/packages, retry, model/backend selection, fresh qualification or24audio review. Original eager fit is unmeasured and must fail inside the unchanged cap if insufficient. P1 dependency of reviewer reliability; effort one bounded diagnostic/audit, risks original-scale numeric differences/memory/time/order/selection bias, production migration none, rollback closes the research guard and retains first evidence. Previous explicit ADR109 one-campaign approval is consumed; a new original worker awaits its own exact approval. Original4/12FAIL and all prior results remain unchanged. **D70 naturalness OPEN; D71 NOT STARTED.**

## 2026-10-23 approved ADR-110 diagnostic complete: numerical differences, unchanged answers

[Actual report](D70_VOXTRAL_ATTENTION_DIAGNOSTIC.md), [immutable first observations/full-vector/audit receipts](evidence/d70-voxtral-attention-first.json). The owner explicitly approved “Duyệt một lượt ADR-110” for commita950539. Exactly one original-weight worker performed8explicit forwards+8first generations on4historical presence cases, followed by one no-weights replay. Both eager and SDPA returned **NO/YES/NO/NO**, all8raw answers matching ADR109 and all8nativeEOS/schema valid. Full logit vectors differ (maximum absolute difference0.25–0.53125), but first-token argmax agrees on all4cases. Parent independently recomputes all8full131072-elementFP32 vectors/metrics and reconciles both backend/historical/replay features plus762native tensor receipts. Switching to eager did not fix these four answers; this is not fresh qualification or a universal root-cause exclusion. Original4/12FAIL remains unchanged.

Worker217.312967s/replay5.337580s, exit0/no timeout/reaped; whole-worker peak **RSS RAM9.565887GiB**, **virtualVmPeak10.237831GiB**, retaining12GiBAS/14GiBsampledheadroom/CPU2/offline/originalCOREloaded. No evaluator VRAM/new weights/packages/retry/context change. After verifying full executed-source bindings, the guard was restored to exact reviewedFalsebytes; all661canonical sources match the reviewed baseline. Final **470TTSrelated PASS64.25s/0FAIL/0SKIP/Ruff PASS**, not full661-source or reviewer-quality PASS. Fresh audit917protected/176inputs/53prior immutableD70JSON/allthreeSDKs/allpriorartifacts/originalservices/data/security/sameCORE/24pending humanlabels preserved. DIAG-005 bounded counterfactual COMPLETE/no causalfix; scope consumed/guardFalse/workers0. No backend/model selection, qualification rerun,24audio review or next trial scheduled. Reviewer-reliability parent remains open. **D70 NATURALNESS OPEN; D71 NOT STARTED.**
