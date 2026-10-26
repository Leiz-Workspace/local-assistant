# D14 — Structured-output fix and functional quality gate

**Purpose:** Report the implemented format fix, actual fresh model outcomes and the quality gate's explicit refusal to promote incorrect answers.

Date:2026-10-26. **Format integration VERIFIED; functional quality gate FAIL.** [Preregistered criteria](D14_STRUCTURED_QUALITY_GATE_PROTOCOL.md), [ADR133](ADR/133-opt-in-host-schema-profile-decoding.md), [exact independent first/wire verification](evidence/d14-structured-quality-gate-first-result.json).

## Changes and first actual results

Added an opt-in `StructuredProfileAdapter` for the existing agreed profiles. It sends structural JSONgrammar to the pinned native runtime and validates exact first native output. The schema has no expected answer enum/const/default/description or semantic restrictions. It cannot certify factual correctness, fill answers or repair output. Existing default/API/gateway/vision/excerpt behavior and profile templates stay unchanged; no model, tool permission, runtime configuration or data selection changes.

| Actual cohort | Format | Functional exact answers | Interpretation |
|---|---:|---:|---|
| First CORE42questions with initial parser |39/42|28/42| Three streaming results were rejected by a native role-null compatibility bug; all first failures stay unchanged |
| Same retained COREwire, corrected parser, offline revalidation |42/42|31/42| Revalidation of original bytes, not new answers or overwritten first scores |
| First UNRESTRICTED42questions with corrected parser |42/42|30/42| Fresh complete actual evaluation; wrong typed answers still fail |
| Three additional fresh COREstream compatibility questions |3/3|3/3| End-to-end corrected native streaming, different sequences, no repeated first question |

The local functional criterion declared before inference is **42/42correct per profile**, plus lifecycle/provenance/baseline checks. It remainsFAIL. The gate command exitsnonzero when those requirements are unmet; complete execution or schema success cannot make itPASS. Original D14localcomposites66.5/52and every previous first result remain immutable.

Examples of remaining actual factual errors: COREreturns58for90−36+8(expected62),13foranexistingdictionarykeywhosevalueis0, and[1,3,5]instead oftheodd-value squares[1,9,25]. It also sometimes returns a question or a whole source sentence instead of the requested exact label. These are content/request-interpretation failures, not repaired by grammar. Every failure is linked in the machine receipt; no dropped cases, answer coercion, Markdown extraction or lower threshold.

## Technical faults corrected without rerunning old cases

1. NativeSSEopens with `role:assistant, content:null`. Accept that first role-only metadata frame, preserve all actual string chunks, and continue to reject a null after answer emission or a foreign role/model. The first three failed rows remain failed; raw-wire replay and three different fresh live questions separately verify the parser fix.
2. The original nativeportprobe used a plainbind, which can reject a retired port inTIME_WAIT even though the nativeSO_REUSEADDRlistener can safely rebind. FirstUNRESTRICTEDpreflight had sufficientRAM/VRAM but stopped withOSErrorbefore creating any modelprocess/request. Correct only the evaluator's probe to mirror the native bind semantics; real loopback tests prove it still refuses an active listener and accepts a retiredconnection. No unrelated process is stopped and no resource guard is lowered.

The failed launcher using direct script invocation stopped at import before any generation. Use `uv run --no-sync python -m benchmarks.scripts.d14_structured_gate` for module execution. First controller's42COREanswers and partialresult remain retained. A separately frozen suffix admits only the never-loaded UNRESTRICTEDprofile, checks priorhash/completeCOREaccounting/settledlifecycle and permits no native artifacts beyond its old preflight. It also declares only three new COREcompatibility questions. No old question is regenerated.

## Verification and resource boundaries

**394scoped tests PASS /0FAIL/0SKIP,2.15s; RuffPASS.** Includes host-schema/gold-leak denials, wrong-shaped and wrong-factual outputs, nativeSSEidentity/role/null/DONE/usage, first-byte preservation, single-use/no-fallback behavior, repeated cancellation/HTTPclose joins, independentmath/Pythonreferences, full84-dispatch mock-controller/qualityFAIL controls, realPOSIXchild and TCPport retirement, actualwire replay and cumulative-delivery allowlists. Mock tests are implementation controls, never substituted for actual model results.

Actual generation accounting:84first scored requests +2planned nativecancel streams +3fresh compatibility requests = **89**, zero automatic retry/oldcase regeneration. Both profiles use the same existing32K/GPU99/projector/thread2/batch512/ubatch128/reasoningoff/offline settings in sequential owned loopback18080processes. All three ownedGPUservers exit0/reaped, nativecancel probes return slotsidle, original boot/container/no-native baseline restored. RAM/VRAMguards stay as ADR132; nativewait4whole-processRAM and sampledVRAM remain separately recorded, not a claimed hard CUDAaddress-space cap or model-only cost.

Current application snapshot has730files: the previous728passed application/source/config/test files are byte-identical plus the new adapter and its tests. The completed5674full remains the historical728-file result; **no new730-file full is claimed**. The new opt-in component is covered by scoped controls and real native gate evidence. No production route/default registration, database/Vault/schema/Qdrant access, Docker change, model download/replacement, release or deployment.

Read-only posttrial verification checks all frozenartifact hashes, current730source and every prior728file,916of917olderprotectedreferences plus the disclosed previously authorizedMODEL_REGISTRYdocumentationdelta, and all176originalinputs. Original pendinglisteninglabels are unaffected; no human audio judgment is inferred. No oldbootdata/ACLaudit is relabeled as a new databaseaudit.

## Remaining disposition

The requested formatting/stream integration fix and executable quality gate are implemented and tested. The gate correctly blocks the remaining factual errors. Do not mark general D14qualityPASS or select/replace a model based on format results. Next P1semantic remediation needs an assessed mechanism, independent references and fresh preregistered evaluation; expected values must not enter grammar or hidden feedback. Existing model choices, first scores and owner/manual/voice/license/product/release gates remain binding.
