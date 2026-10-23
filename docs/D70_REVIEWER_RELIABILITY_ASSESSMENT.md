# D70 auditory reviewer reliability assessment

**Purpose:** Record the completed investigation after ADR-104, separate measured local failures from external research and interface availability, and identify a concrete next evaluation route without changing project models or D70 acceptance.

**Date:** 2026-10-23. **Status:** Owner-approved ADR-105 campaign completed with first-request upstream GPU failure; no usable auditory score, scope consumed and execution closed. [Actual evidence](evidence/d70-specialist-campaign-first.json). [ADR-105 protocol and outcome](ADR/105-proposed-specialist-public-auditory-review.md). [Evidence](evidence/d70-specialist-review-proposal.json).

## What the retained failure establishes

ADR-104 retains12first responses,12genuine EOS and strict8of12matches. The capitalized EN label is one format failure; three pairwise comparisons are semantically wrong under the preregistered controls. Correcting case would not remove those comparison failures, and no historical label/parser/result is changed. Five of six pair responses chose second; the original experiment does not by itself establish a causal positional bias. New comparisons must test both orientations.

Independent original feature-hash/mask/token replay and full1442tensor byte verification found no mismatch. The installed native SDK explicitly iterates audio segments and merges their embeddings; no evidence was found for a blanket “only one audio supported” explanation. These checks do not prove good audio reasoning or Vietnamese naturalness judgement. Memory was sufficient for the actual12cases; another cap increase does not address their wrong answers.

The [SpeechJudge study](https://arxiv.org/abs/2511.07931) distinguishes naturalness judgement from general audio understanding and develops a specifically trained evaluator. This motivates investigating a specialist rather than repeatedly tuning prompts on our failed held-out cases. Its [released model](https://huggingface.co/RMSnow/SpeechJudge-GRM) declares EN/ZH, CC-BY-NC-4.0 and Qwen2.5-Omni-7B lineage. This is not Vietnamese qualification or a local project benchmark.

## Routes checked

| Route | Current evidence | Decision for this continuation |
|---|---|---|
| Existing local3B, unchanged protocol | Failed original controls and ADR-104; all first failures retained | No rerun or promotion |
| Native BF16 specialist locally | Analytic and native meta-only count agree:7,615,616,512text parameters,15,231,233,024BF16bytes≈14.185GiB before modalities/runtime | Excluded under12GiB cap; no weights downloaded, no cap/precision change |
| Author-linked SpeechJudge demo | Metadata reports RUNTIME_ERROR | Unavailable at this observation; no prediction attempted |
| Community SpeechJudge demo | RUNNING metadata; live exact public API/schema/source check passes | Approved first request failed with GPU task aborted; no quality result or qualification |
| Earlier official Qwen demos | Frontend metadata still RUNNING; prior real model calls failed/timed out | Frontend state does not reverse retained failures; no retry made |
| ASR/acoustic/MOS proxies | Existing intelligibility/acoustic diagnostics retained | Cannot replace actual per-output naturalness evidence |

The native lower bound is an architecture calculation, independently checked using **meta tensors** in the existing SDK; no checkpoint parameters were loaded and no model response generated. It is not measured RAM/VRAM. The candidate model index declares22,362,553,472serialized bytes for the full checkpoint, a different quantity. Native loading, quantization and offload were not attempted.

The inspected community copy is [Den4ikAI/SpeechJudge-GRM](https://huggingface.co/spaces/Den4ikAI/SpeechJudge-GRM), Space revision`e16fd85d230ac043091476eb78faa6c2e24c5c66`, Gradio6.26.0. It is not author-owned or controlled by this project. Its utility downloads the model repository without a pinned revision. Code identity and a public model-card revision do not attest remotely loaded weights, settings or resource consumption. No account, key, billing or local installation was used for metadata reads.

## Implementation and proposal-stage boundary (historical)

New standalone script/test files leave all642prior source bytes unchanged. External execution defaults disabled for provider constructors and retained-object media calls; reversible local control preparation is allowed and benchmark copies still require successful qualification. Tests cover full PCM16 provenance, mirrored/tie controls, schema/path/endpoint bounds, exact one-generation requests, raw/frontend score agreement, first-failure retention, gate recomputation, conditional24output pairing, order disagreements, metadata drift and policy refusal. Native meta-only counting separately checks the resource exclusion. Live metadata checking transmits no audio.

The proposed campaign has18neutral-smoke control comparisons, then only if all pass24mirrored comparisons covering all24existing benchmark outputs. It uses the specialist's source-defined1to10rubric and required neutral reference text; those model scores are not human MOS. Maximum42comparisons/84audio uploads, one generation each, no retries or averaging away disagreements. Independent readonly checks confirm that all24retained signals form12same-text EN/VI pairs and still match native/diagnostic hashes; the real local control packet is prepared and frozen; the common review packet remains uncreated.

At the proposal checkpoint, approval was needed for **sending neutral test audio and authored text to this new community recipient**; that permission has now been granted and the one campaign consumed. Prior local ADR-104 scope was consumed and previous public trials addressed different endpoints. No approval is requested for metadata investigation, reversible implementation or tests. One concrete ADR-105 approval would cover both conditional stages; it would not select/deploy a production model, waive AC or authorize further failed-campaign retries.

All original models, datasets, first observations,24pending listening labels and CORE are retained. D70 remains IN PROGRESS/NATURALNESS OPEN; D71 remains NOT STARTED. If the candidate fails controls or cannot produce adequate VI/EN descriptions, those outcomes stay failures and D70 stays open.


## 2026-10-23 first-evidence gate follow-up

[Binding and correction evidence](evidence/d70-specialist-first-evidence-binding.json). While external consent remains pending, the standalone gate now verifies exactly56first-control artifacts, all hashes, fixed-origin unique event receipts and exact result/observation/SSE/parsed-judgement agreement. Two regressions reproduced against6e9f6ab; after repair41specialist/346TTSrelated PASS0.53s/18.40s,0FAIL/0SKIP/Ruff PASS. Authored full18control+24review flow and partial-stream failure tests require no real upload/model. Execution remains disabled and original ADR-1048of12 unchanged.

Audit correction:6e9f6ab's917preserved claim used a pre-edit audit; a later redundant agent note changed protected AUDIO_BACKLOG.md, leaving916of917unchanged at that commit. Only that append is now removed and the exact protected baseline restored, while current progress stays in canonical roadmap/devlog/backlogs. First failed audit/removed-note version and prior evidence retained; fresh917protected/runtime/model/SDK/data/sameCORE audit passes. No historical result is relabelled. All642pre-specialist source bytes remain unchanged/current645; only specialist helper/test changed. No media, weights or predictions added. D70 OPEN/D71 NOT STARTED.


## 2026-10-23 real local control packet ready; external consent remains pending

[Local preparation evidence](evidence/d70-specialist-local-control-preparation.json). Removed the unnecessary consent barrier around reversible local copies while retaining EXECUTION_ALLOWEDFalse for every provider client/upload/inference. Actual18control/36WAV/38file packet is now prepared privately and its first manifest verified; later execution must reuse/check those exact bytes. Common benchmark inputs still require complete18control qualification and are not prepared. No media sent, no prediction or new weights.

A first local CLI attempt exposed missing owned-root initialization before any file publication; fixed0700creation/symlink rejection and tested a previously nonexistent root, preserving the failed log.348TTSrelated PASS18.38s/0FAIL/0SKIP/Ruff PASS, including2new preparation/changed-packet cases after the binding follow-up. All642pre-specialist source bytes and34priorD70JSON preserved/current645,917protected/176inputs/23475+23382SDK/16artifacts/original system/sameCORE audit passes;24pending judgements unchanged. Local preparation was authorized continuation work; only transmission to the new community recipient awaits explicit permission. D70 OPEN/D71 NOT STARTED.

## 2026-10-23 ADR-105 approved campaign: upstream GPU failure, no auditory scores

Owner explicitly approved **“Cho phép gửi audio theo ADR-105”**. [Approved freeze](evidence/d70-specialist-approved-freeze.json), [actual first evidence](evidence/d70-specialist-campaign-first.json), [protocol and outcome](ADR/105-proposed-specialist-public-auditory-review.md). Reused the hash-bound first local packet; exact source/runtime/schema preflight passed. Two neutral WAV uploads and one accepted prediction request reached the community endpoint. At the first identical EN control, four heartbeats ended in `System Error: 'GPU task aborted'` / `ZeroGPU worker error`, without a score or rationale. The unchanged parser rejected it as `specialist_first_generation`; this is **service failure, not measured wrong audio judgement**. One control attempted/17unattempted/0usable comparisons, no retry or conditional24benchmark packet/upload. Remote completion/resources/root cause/deletion remain unverified.

Command elapsed78.37s; local-client maximumRSS43276KiB, not provider RAM/VRAM. Exit0 means handled failure recorded, not PASS. Gate restoredFalse/scope consumed; original local policy remains imports/load-only. **350preflight/355finalTTSrelated PASS19.04s/19.30s,0FAIL/0SKIP/Ruff PASS**,7new regression cases since348; no full645-source or auditory benchmark claim. All642pre-specialist source bytes preserved/current645,917protected/35priorD70JSON/176inputs/23475+23382SDK/16artifacts/original system/security/model/data/sameCORE audit PASS. First audit-launch import-root error retained and corrected without an inference retry.24original pending naturalness labels remain null/unlistened. **D70 naturalness OPEN; D71 NOT STARTED.** No model/default/provider deployment, weights/package download, AC waiver or new campaign scheduled.
