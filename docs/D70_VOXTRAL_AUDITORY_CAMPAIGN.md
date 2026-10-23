# D70 Voxtral first auditory campaign

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
