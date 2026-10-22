# ADR 101 — Proposed original-tensor loading within the retained12GiB cap

**Purpose:** Prepare a concrete memory-loading investigation without resuming the paused evaluator, changing agreed models or claiming that loading repairs its quality failures.

**Date:** 2026-10-22. **Status: PROPOSED — NOT IMPLEMENTED, NOT EXECUTED.** ADR-100 remains REJECTED; cap12GiB and execution-disabled policy remain unchanged. The owner's generic request to continue does not resume the evaluator.

## Findings from source and headers only

The installed safetensors0.8.0 exposes `safe_open(..., backend="pread")`. Its [official source](https://github.com/safetensors/safetensors/blob/v0.8.0/bindings/python/py_src/safetensors/torch.py) documents the storage backend. The installed [Transformers4.57.3 loader](https://github.com/huggingface/transformers/blob/v4.57.3/src/transformers/modeling_utils.py) calls `safe_open` without forwarding this option; its old `low_cpu_mem_usage` and `offload_state_dict` arguments are popped unused. Adding those arguments alone is not a demonstrated remedy.

Readonly original headers contain1442Thinker tensors, allBF16, totalling9,406,928,896bytes; largest tensor622,329,856bytes. These are serialized tensor bytes, not measured RSS or a proven address-space requirement. This inspection read bounded JSON headers and SDK text only: no tensor data, neural SDK import, allocation, model load or inference. [Feasibility evidence](../evidence/d70-12g-pread-feasibility.json).

## Proposed experiment, only after explicit resume

Use native safetensors `pread` to read only the exact original `thinker.*` tensors, retaining the original shards and their complete hash checks. Pass these unmodified tensors to the genuine Thinker `from_pretrained(None, config=original_thinker_config, state_dict=...)` interface. Preserve the original parameter names and original BF16 bytes; no tensor slicing/repacking/quantization, SDK monkeypatch or new model/download. The loader's coverage/missing/mismatch/storage/device/dtype accounting must reject partial or substituted state. Keep the tested original EOS/padding boundary handling.

Keep cap12GiB, CPU-only/two threads/affinity0,1, existing CORE loaded, no credentials/network/GPU, private bounded output/tmpfs and existing600second qualification bound. First validate publication/provenance and failure controls with authored tiny fixtures; then a separately frozen native load-only trial could measure whether the original tensors actually fit. Capture RSS/VmSize/VmPeak on success/failure. Stop on cap/headroom/native-loader failure; no automatic cap increase, CORE unload, second model or patched checkpoint. The currently installed SDK versions and original model/config/data stay unchanged.

The protocol must independently verify exact bytes and complete parameter accounting, not infer fidelity from successful construction. If native loading copies or allocates too much, this proposed path may still fail12GiB. No fit, speed, peak RAM, production or quality claim is made from the source/header study.

## Quality gate remains separate

The previous evaluator's first-turn outputs called silence/noise speech and severe clipping natural, and failed strictJSON. A loading change does not address those observed quality defects. This proposal is **not permission to rerun semantic controls until a favourable result appears**, soften labels, repair responses into PASS or review the24common outputs. Any later control run needs a justified protocol and retained first failures; the existing reviewer remains NOT QUALIFIED. D70 stays open and D71 unstarted under the unchanged owner AC/order. No human MOS or reliable Vietnamese quality claim follows from a memory fix.

## Priority, dependencies, effort and risk

**AUDIO-EVAL-LOAD-12G-001: P2, assessed but not scheduled for execution.** One loader investigation milestone; depends on explicit owner resume, unchanged artifacts/SDK, tiny-fixture tests and actual native-load evidence within12GiB. The **P1 D70 dependency remains a reviewer that passes factual/quality controls**. This P2 work cannot replace that dependency or justify advancing the roadmap.

Risks: native CPU tensor copies exceed the virtual cap; hidden storage/dtype/key changes; unwanted model components loaded; memory progress mistaken for auditory reliability; repeating controls to pick favourable output. Keep full originals, independent complete-byte checks, first-result retention and strict separation of memory and quality conclusions.

Rollback stops/joins only the owned trial if later authorized; retain its logs and original artifacts. Current state needs no migration or cleanup: evaluator execution stays disabled, cap12GiB, rejected16GiB decision and all historical results preserved. No application/service/database/Vault/Docker/registry change is authorized by this proposal.
