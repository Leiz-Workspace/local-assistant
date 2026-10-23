# ADR 106 Proposed controlled SpeechJudge runtime remediation

**Purpose:** Prepare a concrete, source-bound provider patch after the failed ADR-105 request, without changing production models, resource caps, old observations or D70 acceptance.

**Date:** 2026-10-23. **Status: OFFLINE IMPLEMENTATION AND VERIFICATION COMPLETE; NO OWNER SPACE/ACCOUNT AVAILABLE, DEPLOYMENT UNSCHEDULED.** The owner requested continued work after the context diagnostic, then explicitly answered **“Chưa có Space riêng”** and **“Chưa có tài khoản Hugging Face”**. Local source review, patch generation, tests and documentation are complete. No third-party Space write access, new account, paid resources or consumed inference scope is inferred. Readonly inspection of14Vault records plus standard local credential locations found no matching HF configuration; no values were retained or used for external authentication. Retain this patch for a future controlled endpoint; [ADR-107](107-proposed-isolated-voxtral-evaluator-preparation.md) assesses a separate local preparation route without any new weights yet.

## Problem and evidence

The author-linked Space still reports RUNTIME_ERROR. The community Space still reports the same repository/deployed revision `e16fd85d230ac043091476eb78faa6c2e24c5c66`; RUNNING is frontend metadata, not recovered inference. The only approved actual request retains `GPU task aborted` and no quality score. Its cause remains unconfirmed; neither local VRAM headroom nor the complete-event envelope proves anything about remote memory or successful generation. [First outcome](../evidence/d70-specialist-campaign-first.json), [context/resource diagnostic](../D70_CONTEXT_RESOURCE_DIAGNOSTIC.md).

The [official ZeroGPU documentation](https://huggingface.co/docs/hub/spaces-zerogpu) recommends placing models on CUDA during module startup, outside the GPU-decorated request. The retained app instead moves the model inside a30-second request allocation and then permits up to1024generated tokens. The utility also downloads an unpinned repository revision. These are concrete lifecycle, budget and provenance issues that can be addressed in source; they are not established causes of the observed abort.

## Reviewable proposal

The offline helper `scripts/tts_speechjudge_source_remediation.py` accepts exactly two original source hashes, parses without importing/executing them, and publishes an exclusive local candidate:

1. Move the existing model's `.to("cuda")` into `load_model_globally`, which the unchanged entry point calls before serving requests. Remove only the request-time transfer. Keep BF16, SDPA and model construction unchanged.
2. Change `@spaces.GPU(duration=30)` to120seconds. This changes a future provider request budget, not local RAM/VRAM/context. Actual availability, quota and permitted duration must be checked for the eventual account; no quota bypass, automatic credits or billing is authorized.
3. Add the already inspected model revision `8d4ce4ddf54c5e7ac0b457fc7b561cec1bd784c1` to the original `snapshot_download` call. This declares the intended research checkpoint; it does not attest the old community worker's unknown bytes or download anything locally.
4. Add English descriptions and startup/comparison logging to the changed code. The full candidate retains the original public API and source attribution through the source-bound manifest/diff.

Preserve `MODEL.generate` arguments byte-equivalently at AST level: sampling,1024output-token cap and no audio output remain. Preserve the original four-parameter `gradio_handler`, rubric, complete audio conditioning and all other input/scoring functions. Do not reduce context, trim audio, alter control expectations, fix raw answers or select a model. Model/revision pinning here is limited to the proposed research evaluator, never the agreed production lineup.

Run `uv run --no-sync python -m scripts.tts_speechjudge_source_remediation` only to construct local artifacts. The first candidate already exists at `data/backups/d70-speechjudge-remediation-first/`: full `app.py`, full `infer/utils.py`, unified `remediation.patch`, and first `manifest.json`. The helper refuses source drift, candidate drift, symlink outputs and existing output directories. It has no deployment, login, download or inference operation. Do not execute the generated app on this local server.

## Verification and practical limit

Eleven new authored-fixture controls PASS0.20s;366TTSrelated PASS19.36s/0FAIL/0SKIP/Ruff PASS. Tests apply the patch using actual Git in a temporary authored source tree, compare complete candidate bytes, enforce provenance/permissions/exclusivity, and reject source/candidate drift. An independent offline check also applies the actual retained-source patch and verifies exact candidate bytes. Only app functions `load_model_globally`/`compare_wavs` and utility `download_speechjudge_grm` change their AST; other function bodies, decoder call and API signature are preserved.

No candidate is imported, executed, hosted or GPU-tested. Software/static success is not ZeroGPU compatibility, a proven abort fix, naturalness qualification or a model benchmark. The new source count647 includes only this helper and its tests; all645prior sources remain byte-identical. Protected917/original176inputs/two SDKs/16artifacts/old D70 evidence/24pending labels and original services/security/database/vector/CORE remain unchanged. Two ordinary CORE text checks verify recovery; no new auditory evaluator request occurred.

## Dependencies, effort, risk, migration and rollback

Existing P1 `AUDIO-EVAL-REVIEWER-RELIABILITY-001`: offline remediation milestone complete; one future controlled deployment/startup audit plus one conditional evaluation milestone remains. Dependencies are an explicitly identified owner-managed endpoint, hosting permissions and resource/quota constraints, its exact SDK/build identity and model/provenance receipts. No Space or account has been created. The original dependency declaration is retained for review; no packages or weights are installed here.

The pinned upstream `requirements.txt` is only73bytes and leaves transformers, accelerate, qwen-omni-utils, gradio, torch and torchvision unversioned; vllm is commented out. A new build cannot be called reproducible merely by pinning app/model source. Preserve this declaration as evidence and audit/freeze the eventual supported provider SDK/build before any qualified campaign. No dependency versions, CUDA build or provider capacity are invented from the existing local CPU SDK.

Risks: documentation/provider version mismatch, emulated CUDA startup failure, insufficient real provider resources, queue/duration limits, checkpoint pin changing unknown historical bytes, source licensing, external retention, stochastic tie/order bias and unsupported Vietnamese quality. A120-second budget does not guarantee success and is not a memory cap or resource measurement. No related production component or database/index/source/audio migration is needed.

Do not change the old Den4ikAI endpoint or reopen its execution flag. Any eventual new endpoint must have its own explicit recipient/protocol/source freeze and one finite18-control/conditional24-comparison scope, exact first local inputs and original strict gate. Preserve first errors in a separate namespace; no outcome-dependent prompt/label/threshold changes, alternate seeds, favourable retries or automatic D70 acceptance. Actual inference is unscheduled while ownership/endpoint and scope remain unspecified.

Rollback of the current offline work affects only new artifacts. If a future deployment is approved, stop only that owned evaluator, retire its exact client scope and retain source/build/model/response receipts; do not touch CORE, the old Space, production models, Vault/Docker/database or original audio. No remote deletion/cancellation guarantee is implied.

**D70 IN PROGRESS/NATURALNESS OPEN; D71 NOT STARTED.** ADR-105 remains a completed failed service campaign, not a passed or retried one.
