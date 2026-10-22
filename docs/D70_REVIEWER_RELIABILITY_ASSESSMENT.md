# D70 auditory reviewer reliability assessment

**Purpose:** Record the completed investigation after ADR-104, separate measured local failures from external research and interface availability, and identify a concrete next evaluation route without changing project models or D70 acceptance.

**Date:** 2026-10-23. **Status:** Investigation and gated implementation complete; new external audio evaluation is not approved or executed. [Proposed ADR-105](ADR/105-proposed-specialist-public-auditory-review.md). [Evidence](evidence/d70-specialist-review-proposal.json).

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
| Community SpeechJudge demo | RUNNING metadata; live exact public API/schema/source check passes | Candidate for one separately approved finite campaign, not qualified |
| Earlier official Qwen demos | Frontend metadata still RUNNING; prior real model calls failed/timed out | Frontend state does not reverse retained failures; no retry made |
| ASR/acoustic/MOS proxies | Existing intelligibility/acoustic diagnostics retained | Cannot replace actual per-output naturalness evidence |

The native lower bound is an architecture calculation, independently checked using **meta tensors** in the existing SDK; no checkpoint parameters were loaded and no model response generated. It is not measured RAM/VRAM. The candidate model index declares22,362,553,472serialized bytes for the full checkpoint, a different quantity. Native loading, quantization and offload were not attempted.

The inspected community copy is [Den4ikAI/SpeechJudge-GRM](https://huggingface.co/spaces/Den4ikAI/SpeechJudge-GRM), Space revision`e16fd85d230ac043091476eb78faa6c2e24c5c66`, Gradio6.26.0. It is not author-owned or controlled by this project. Its utility downloads the model repository without a pinned revision. Code identity and a public model-card revision do not attest remotely loaded weights, settings or resource consumption. No account, key, billing or local installation was used for metadata reads.

## Concrete implementation and remaining boundary

New standalone script/test files leave all642prior source bytes unchanged. The client defaults to execution disabled, including packet preparation, constructors and retained-object media calls. Tests cover full PCM16 provenance, mirrored/tie controls, schema/path/endpoint bounds, exact one-generation requests, raw/frontend score agreement, first-failure retention, gate recomputation, conditional24output pairing, order disagreements, metadata drift and policy refusal. Native meta-only counting separately checks the resource exclusion. Live metadata checking transmits no audio.

The proposed campaign has18neutral-smoke control comparisons, then only if all pass24mirrored comparisons covering all24existing benchmark outputs. It uses the specialist's source-defined1to10rubric and required neutral reference text; those model scores are not human MOS. Maximum42comparisons/84audio uploads, one generation each, no retries or averaging away disagreements. Independent readonly checks confirm that all24retained signals form12same-text EN/VI pairs and still match native/diagnostic hashes; real specialist packets remain uncreated.

Approval is needed for **sending neutral test audio and authored text to this new community recipient**. Prior local ADR-104 scope was consumed and previous public trials addressed different endpoints. No approval is requested for metadata investigation, reversible implementation or tests. One concrete ADR-105 approval would cover both conditional stages; it would not select/deploy a production model, waive AC or authorize further failed-campaign retries.

All original models, datasets, first observations,24pending listening labels and CORE are retained. D70 remains IN PROGRESS/NATURALNESS OPEN; D71 remains NOT STARTED. If the candidate fails controls or cannot produce adequate VI/EN descriptions, those outcomes stay failures and D70 stays open.
