# D88 — Model provenance and acceptance scorecard

**Purpose:** Reconcile the historical registry, current approved configuration and actual benchmark evidence without selecting or changing models.

**Status:** Documentation reconciliation only; model/voice/license/product/release gates remain open. The original [MODEL_REGISTRY](MODEL_REGISTRY.md) preserves the2026-10-18lineup and D24reconciliation context; the current roadmap, approved later ADRs and exact configs record subsequent authorized decisions. Historical “planned”/unchecked entries are not evidence that later tests never happened, nor authority to download models.

| Role | Original strategy and current explicit state | Evidence / remaining gate |
|---|---|---|
| CORE | Original Qwen3.5-9B/bartowskiQ6_K/compatible projector,32K; existing loaded model retained | configs/models.yaml; D61–D67native media and D80/D83text/timing evidence. These functional checks do not close original D14weighted quality scorecard |
| UNRESTRICTED | Original HauhauCSQwen3.5-9B Q6_K isolated text profile; no automatic tools/privileges | Same config, isolated loading strategy; D80profile/identity tests use deterministic ports. Not loaded/switched during this work, no new runtime-quality claim |
| Embedding | Qwen3-Embedding-0.6B was the original candidate. Later owner explicitly approved selected CPU BF16/1024config after fair comparison; current config says selected_not_deployed | configs/embedding-selected.json, ADR032and model-eval-001approval/comparison. No new choice/cutover in D71–D88 |
| D24rollback | multilingual-e5-base int8/768at a88584b remains intact as historical accepted implementation/rollback | configs/embedding-e5-rollback.json and ADR031. D24itself did not compare Qwen; later MODEL-EVAL-001did. Never mix768/1024spaces or erase original results |
| Reranker | Qwen3-Reranker-0.6B original nominee; isolated experiments only, dense production ordering retained | D27evidence and configs/reranker-qwen-evaluation.json. Assistant-authored labels are not independent human review/adoption. Full regression may exercise the existing isolated diagnostic, not overwrite first results or grant selection |
| Vision/OCR | COREnative vision plus existing projector; native PDF/DOCX/XLSXparsing first, explicit bounded fallback | D61–D67source/frame/field evidence. No extraOCR/VLMdefault or specialist model selected |
| ASR | Original Qwen3-ASR-0.6B versus Whisper/faster-whisper candidates, CPU evaluation only | D68actual accuracy/RAM observations and D72held-out replay. No product default. No-speech hallucinations and short/quiet speech policy remain gates |
| VAD | Original SileroVADv5candidate | D69actual presence/clock replay; D72naive concatenation worsens ASRWER, stays disabled. No word-retention/real-mic robustness certification |
| TTS | Original Qwen3-TTS-0.6B versus PiperEN/VIinstances, CPU evaluation only | D70machine outputs/measurements retained; actual listening0/24owner-deferred. Explicit QwenVIunsupported/refusals kept; PiperVIengine/weights/dataset/output license chain not fully approved |
| Voice product | D71recording/D72explicit offline matrix/D73retention components prepared | Six actual compatible buffered paths do not select a default voice or approve production API/microphone workflow; D74product gate open |
| Research reviewers | Owner-authorized QwenOmni/Voxtral/public demos were research tools, not product roles | Failed controls/exhausted scopes/first outputs retained. No reviewer qualification or naturalness approval is inferred; no additional download or trial here |
| Coding/web/video | Original CORE plus deterministic source/Git/patch/check/search/fetch/browser/FFmpegtools | Existing guarded/owned tool chains and D75–D85prepared components. No specialist coder, web model or standalone video model selected |

Licenses listed in candidate manifests are upstream declarations, not legal clearance of every engine/weight/voice/dataset/output use. Frozen artifacts/revisions/hashes remain in existing manifests and reports. Dataset repetition/training-overlap, warm-versus-cold/runtime/dtype differences, sampled-versus-peak RAM/VRAM and source-quality limits remain part of the evidence; do not generalize small tests into universal superiority.

Any future replacement still requires measured benchmark, performance/resources, compatibility, migration, rollback and explicit owner approval under ADR031and the registry policy. This scorecard does not authorize a model/default/config/service/data change. Final acceptance still needs actual owner listening/manual checks and explicit model/voice/license/release decisions; software PASS is not model-quality PASS.

## Historical D14files independently reconciled

Read-only inspection of the actual day14-core-gate/day14-unrestricted-gate reports finds9/9checks per profile, covering YAML/profile/runtime/artifact/Docker/API identity gates. The day13scorecard explicitly declares day13_provisional, small smoke datasets, basic math reasoning and unscored performance/multimodal/VRAM/context/provenance dimensions; it explicitly disclaims an overall model-capability percentage. These real files therefore support historical runtime readiness, not closure of the complete weighted30–50case quality acceptance. No original result was edited or model rerun. [Exact metadata/hashes](evidence/d88-historical-scorecard-reconciliation.json).


## Later original-quality follow-up — 2026-10-24

[MODEL-QUALITY-001first COREtext baseline](MODEL_QUALITY_001_CORE_TEXT_SCORECARD.md) now supplies30fresh authored first attempts under the same historical weights:23/30exact,52.5of70text points,overall100point scorenull. Other30points/UNRESTRICTEDprofile comparison/actual broadquality and owner/model/product signoff remainunmeasured/open. Same retained CORE/D80template/fast512; no model/default/context/resource change. Original day13/day14reports and their provisional/runtime-only classifications remain unchanged. This later result adds bounded evidence without converting it into completeD14acceptance.
