# ADR 104 Proposed held-out auditory controls and conditional blind review

**Purpose:** Preregister one complete research campaign that can test a fixed auditory protocol and, conditionally, inspect the retained D70 outputs without repeated scope requests, model replacement or acceptance changes.

**Date:** 2026-10-23. **Status: OWNER-APPROVED CAMPAIGN COMPLETED; FIRST CONTROLS FAILED; CONDITIONAL REVIEW BLOCKED; SCOPE CONSUMED.** Owner explicitly replied **“Duyệt campaign ADR-104”** after reviewing commit `4906fa0`. One twelve-control worker ran under the exact limits below; its first8of12 strict matches fail the gate, so the conditional review was not prepared or run. Four campaign modes have been closed; imports/load-only policy restored. Original qualification/review and consumed ADR-103 diagnostic remain blocked. Proposal/preparation and approved source snapshots are retained unchanged; actual outcome is appended below.

## Decision and dependencies

P1 `AUDIO-EVAL-QUALITY-PROTOCOL-001`, one preparation/test milestone plus one conditional research campaign. Dependencies: original weights/SDK and full tensor fidelity from ADR-101/102; pure worker namespace correction from ADR-103; all original failures and 24 native outputs; source/model/runtime/parent-label freeze; explicit approval of this entire campaign. No new model, package, service, credential, synthesis or provider. Do not reopen the original nine-control qualification or rewrite its outcomes.

Keep original Qwen/Qwen2.5-Omni-3B revision `f75b40e3da2003cdd6e1829b1f420ca70797c34e`, native Thinker BF16 CPU/pread loader, original processor, system text, EOS151645/pad151643, greedy seed7, two threads/inter-op1/affinity0,1. Keep 12GiB process address space, 14GiB sampled host MemAvailable preflight before preparation and again before launch, CORE loaded, no GPU/network/credentials, readonly mounts and 128MiB private tmpfs. Host headroom is not reserved memory. Prior four-case inference fit does not establish two-audio or 24-output memory feasibility. Any resource, source, namespace or response failure is retained; no automatic cap/headroom change, retry, prompt repair or new model.

## Fixed twelve observations, before common candidate inputs

Two existing complete FLEURS signals not previously sent to this evaluator are preregistered. Held-out means held out from these local reviewer runs; unknown model training exposure is not claimed absent:

| Existing signal | Samples at 16kHz | Full float32 SHA256 |
|---|---:|---|
| en_us-0002 | 94080 | `5666c569fbad40208b387286b812cfc2161f604532023dabd30fc9adad79db1c` |
| vi_vn-0002 | 138240 | `933ee308dcc8a81cb74687643d99183066e15f79d2051c8c45d05d9a6d017536` |

1. Four presence tasks: those two signals (yes), exact zeros (no), Gaussian noise (no). Authored zero/noise are 64000 samples; noise NumPy default_rng104, mean0/std0.05, stored unchanged float32. Exact question: “Does this audio contain any intelligible human speech? Answer exactly yes, no, or uncertain.”
2. Two language tasks: complete EN/VI signals, expected english/vietnamese. Exact question: “Which language is spoken in this audio? Answer exactly english, vietnamese, other, or uncertain.”
3. Six pair tasks: for each language, original versus `clip(40*x,-1,1)`, original versus a separate copy whose middle half is exact zeros, and original versus an identical copy. Both signals keep identical complete duration/sample rate; no resampling, trimming, gain repair or source mutation. Predeclare two damaged-first, two damaged-second and two identical/equal pairs. EN clipped first/gap second; VI clipped second/gap first. Exact question: “Which audio has more audible distortion or unnatural interruptions? Answer exactly first, second, equal, or uncertain.”

All tasks use at most16newtokens; each has a fresh conversation without previous answers. Shuffle all twelve tasks with order seed104. Opaque `clip-NN` observations and `clip-NN-a/b` signals expose only task, count and hash; no source name, transcript, candidate identity, transform or expected label. Accept only exact declared lowercase labels with surrounding whitespace removed; no punctuation/case/JSON/prose repair. Retain all raw text/token IDs, EOS, actual input hashes, feature shape/hash, per-audio mask lengths and audio-token count. An uncertain answer is preserved and fails a known control.

Gate: every one of twelve predeclared answers must match, all complete provenance/termination checks must pass and namespace isolation must have been verified before launch. Qualification wall600s/CPU1200s; one exclusive `quality-104-controls-first` run only. On failure, retain outcome and close inference scope; do not prepare common candidate inputs. The new control gate does **not** turn the historical nine failures into successes or certify general reviewer qualification.

## Conditional single review of the original 24 outputs

Only if that exact first gate passes, prepare 48 fixed observations: one naturalness label and one audible explanation per original output. Bit-copy the complete already-retained 16k diagnostic signals with their original hash/sample/resampling/gain provenance. No new synthesis, resampling, trimming or native-audio modification. Keep all 24 pending original human-listening labels intact; publish new model-review evidence separately.

Shuffle all48 observations with seed104 and opaque identities. Each receives the actual signal, the unchanged system text and one fixed task only, without transcript, synthesis engine, nominal language, expected answer, other task's answer or control feedback:

- Naturalness, maximum16tokens: “Does the actual speech sound natural in pronunciation, rhythm, pauses and continuity? Answer exactly natural, unnatural, uncertain, or not_applicable. Use uncertain when unable to assess, and not_applicable only for no speech.”
- Notes, maximum96tokens: “Describe only audible pronunciation, rhythm, pauses, continuity or distortion in at most forty English words. State uncertainty where necessary. Do not invent a transcript, score or human listening claim.”

Review wall7200s/CPU14400s, same12GiB/14GiB resource policy, one exclusive `quality-104-review-first` run. Record every first response, parse failure, EOS, features, elapsed time and RAM/virtual-memory counters. No per-output retry or selective reporting. Before common preparation and again before execution, recompute first controls and verify frozen source, SDK inventory, parent expectations, request and signal hashes. The controller also verifies actual model/SDK bytes on each run and original CORE identity/text recovery before/after.

## Isolation, meaning and acceptance

Parent preparation code `tts_local_review_quality.py`, source identities and expectations stay outside the worker. Mount only pure `tts_local_review_quality_runtime.py`, unchanged native loader, worker, original model/SDK and opaque signal files. A genuine bwrap processor-only test checks the actual mount layout and native two-audio feature/token order with authored signals; it loads no model weights and generates no neural response. This verifies the input path, not pairwise judgement capability. Prior ADR-103 namespace deviation and its four raw matches remain unchanged.

Language/presence/severe corruption/tie controls test a narrow task scope. They do not establish subtle Vietnamese pronunciation/prosody competence, absolute naturalness accuracy, preference independence or equivalence to human listening. New short prompts are an explicitly different research protocol, not an outcome-based repair of old failed responses. No human MOS, independent human review or generalized quality certification may be claimed. A passing control gate permits only the preregistered research review; the code always leaves D70_complete=False, D71_started=False and reviewer_qualification_passed=False.

Evaluate retained per-output observations against **unchanged ADR-096 AC** after the campaign, including actual conditioning/provenance, uncertainty, adequacy of qualitative descriptions and unresolved evaluator limitations. Missing or unusable naturalness evidence leaves D70 open. Do not assume a successful control run or 48 syntactically valid answers automatically closes D70. The original Vietnamese refusals/Auto-only coverage, latency/resources, compatibility/migration/rollback and voice-license caveats remain. Owner approval remains mandatory before selecting/deploying any model or voice; D71 cannot advance while D70 AC is incomplete. ADR-097 remains rejected.

## Rollback and approval boundary

Rollback closes the four new modes, joins only owned workers, preserves all inputs/first failures/results and changes no production model/default/data/service. No automatic new research campaign follows failure. Scope approval, if granted, covers preparation, one twelve-observation control worker and the single conditional 48-observation worker together; it does not require another permission between those stages. It grants no model substitution, installation, cap increase, headroom reduction, acceptance waiver, source/data migration or cleanup.

Implementation verification and actual approvals/results are recorded in `d70-quality-protocol-proposal.json` and the devlog. The following section records the completed approved campaign; original preregistered questions, controls, limits and acceptance remain unchanged.


## Actual first campaign: 2026-10-23

[Approval/source freeze](../evidence/d70-quality-campaign-approved-freeze.json), [complete first observations and audit](../evidence/d70-quality-campaign-first.json). Preflight300TTSrelated PASS12.38s/Ruff PASS, full source/packet/parent metadata freeze before inference. Real packet12controls/18opaque signals/20files; only signals mounted, no parent preparation module or labels.

First original-weight worker completed93.437s/exit0/no timeout/joined, all12genuine EOS responses. Exactly11canonical labels, **8of12strict matches**, so the unchanged gate **FAILS**:

| Task | Strict matches | Observed limitation |
|---|---:|---|
| Speech presence | 4/4 | Narrow success on these four controls only |
| Language | 1/2 | EN returned raw `English`, not preregistered `english`; retained parse failure |
| Pair distortion/interruptions | 3/6 | EN identical pair called second; EN clipped-first and VI gap-first both called second |

Five of six pair responses were `second`; VI identical pair returned `equal`. This is a limited observed response pattern, not a proved causal explanation or general quality score. No case conversion, expected-label change, parser repair, per-case retry or second model worker. Process completion is distinct from the runtime observation-validity flag, which is false because one raw label is invalid.

Independent post-run **processor-only** replay reproduced all12exact original feature hashes/shapes/per-audio masks/audio-token counts. Both identical waveform pairs produce identical feature rows; all four damaged pairs produce distinct feature rows. No model weights loaded or neural answer generated by that replay. Parent also independently rehashed all1442original tensor payloads/9,406,928,896bytes from the actual worker's fidelity receipt. No source/conditioning mismatch found by these checks; do not use the failure to tune this held-out protocol into a pass.

Measured lifetime peak RSS10,195,540KiB≈9.723GiB **RAM**; kernel VmPeak10,928,692KiB≈10.422GiB **virtual address space**; CPU156.821s. Sampled prelaunch MemAvailable18,870,910,976bytes. Actual twelve-case/two-audio inference fit under12GiB was observed; no VRAM, minimum-RAM or generalized capacity/quality claim.

Conditional common packet/worker: **0**. All24pending original judgements remain null/unlistened; no new naturalness label, MOS, model selection or D70 acceptance. Permission retirement tests and retained scoped-approval fixtures: **304TTSrelated PASS12.63s/0FAIL/0SKIP/Ruff PASS**. Final642source/640approved bytes unchanged; only permission restoration and associated tests differ from approved source snapshots. All30priorD70JSON,917protected hashes,176original audit inputs,23475originalSDK/23382reviewerSDK/16artifacts and original system/data/security/sameCORE audit preserved. No worker remains.

`AUDIO-EVAL-QUALITY-PROTOCOL-001` campaign milestone is complete with a failed control gate. D70 naturalness dependency remains OPEN/D71 NOT STARTED. Next P1 assessment `AUDIO-EVAL-REVIEWER-RELIABILITY-001` must identify a defensible auditory-review route before scheduling more inference; no replacement model/provider, download, new campaign, AC waiver or deployment is authorized by this consumed scope.
