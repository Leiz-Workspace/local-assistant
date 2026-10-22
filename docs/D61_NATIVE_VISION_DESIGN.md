# D61 native CORE image chat design preparation

**Purpose:** Record the inspected dependencies and proposed D61 acceptance before implementation, without advancing past unfinished D60 gates.

**Date:** 2026-10-22. **Status:** Design preparation only; D60 full4120/final audit must complete before D61 implementation or acceptance. No image chat inference or source change is authorized by this document alone.

## Existing foundations

The selected CORE remains Qwen3.5-9B Q6_K with the original BF16 mmproj, loopback8080,32K context and parallel1. `configs/models.yaml` and `MODEL_REGISTRY.md` remain unchanged. D21 already has explicit sanitized image transcription through `apps/api/services/vision_ocr.py`; its structured OCR/table-only prompt is intentionally preserved. The text `InferencePort` and `LlamaInferenceAdapter` accept text messages and remain unchanged.

`src/infrastructure/page_ocr.py::prepare_page` and `ocr_worker.py` already provide a credential-free readonly native namespace, inherited source FD, type verification, EXIF orientation/RGB normalization, metadata removal, thumbnail to2000px/4million pixels and at most4MiB PNG. The worker has512MiB address space,8/9CPU seconds,32FDs and parent25s wall. Explicit `mode=vlm` returns normalized raster data without OCR/model work. Reuse this boundary instead of decoding untrusted images in the API process or adding a new codec/runtime/model.

D21's existing OCR endpoint owns ready-file/hash/namespace locks through response delivery; it must retain its semantics. D61's initial adapter can be unwired/local and accept explicit current-operation image bytes supplied by trusted composition. It must not claim authenticated stored-file/HTTP/UI integration that has not been implemented or tested. Future API adoption needs owner-bound file capabilities and delivery/cancellation integration, separately assessed before scheduling.

## Proposed bounded operation

One explicit owner UUID, source bytes, supported image suffix and question; no caller-selected file path, URL, profile/model/projector, backend endpoint, system prompt or tool. Native normalization runs from an anonymous source FD and is joined through cancellation before releasing ownership. PNG envelope/hash/dimensions/metadata policy is checked before any model disclosure. Retain original and normalized fingerprints and pixel dimensions; do not persist images/questions/model replies automatically or log raw content.

One existing CORE image completion after bounded model-alias verification, environment proxies/redirects disabled, fixed host template, temperature0/thinkingoff, no history/tools or external image URLs. The image is a host-generated inline data URI only. A structured complete answer/uncertainty schema, response/output-token bounds and finite status errors apply. Set prompt-cache reuse off where the existing native protocol supports it; do not equate that with verified GPU-memory erasure or certified cancellation of remote model computation. Source/image/question/output remain untrusted; answers are unverified and cannot authorize actions or masquerade as cited source proofs.

Reuse existing nonqueued admission, bounded quota/no-refund, fixed CPU/model/total budgets, complete-result validation and shielded joined cancellation/shutdown patterns. Final values and native protocol fields require a dedicated ADR and frozen tests before actual measurement. Backend/shared model lifetimes stay external; no model/service/config/database/Vault/dependency mutation or download.

## Proposed acceptance and priority

P1/existing D61 after D60 acceptance; depends on original CORE/mmproj availability and D21 native image isolation. Effort one additive port/policy/service/normalizer/model-adapter milestone plus controlled/native/actual sample gates. Risks: untrusted image codec work on host, EXIF/metadata or image/question leakage, oversized raster/context/memory use, coercive model output, source/model identity mismatch, cancellation releasing while native work remains and overclaiming answer correctness from visible fixtures.

Predeclare representative authored public images/questions and expected visible facts before inference. Verify normalization/orientation/size/hash/metadata, denial before I/O, no URL/path/profile authority, wrong model/finish/schema/oversize refusal, owner/quota/busy/deadline/repeated-cancel/shutdown cleanup, native isolation/timeout and existing text/vision OCR regression. Measure actual local image chat once per frozen sample using the same CORE and preserve every first failure. Do not label model self-evaluation as independent human accuracy. Verify ordinary text inference remains functional after media work; broader quality/resource benchmarking belongs to D62/D63/D67.

Rollback drains only the new operation and removes unwired adapters; accepted OCR/text/source/model configuration, stored blobs/rows, current collections and all historical artifacts remain intact. D61 does not select an alternate OCR/VLM model. Original registry candidates remain subject to the user's benchmark and approval rule.

## Inspected public fixture facts for a future frozen sample

Both existing authored OCR PNGs were visually inspected during design preparation, without a model call. `clean.png` visibly says Invoice2048 and Total42USD; `table-vie.png` has Bút3/Vở5 and headers Tên hàng/Số lượng. The invoice image has no customer name. This design note is not a D61 measurement or final oracle freeze; freeze exact implementation/model/output/boundary oracles before later inference.

```json
[
  {
    "fixture": "tests/fixtures/ocr/clean.png",
    "question": "What invoice number and total currency amount are visible in this image?",
    "visible_facts": [
      "2048",
      "42",
      "USD"
    ],
    "fixture_sha256": "b6c6c432b50ffd56737d1883aaee6a7226f443aced25993c7f350de95f9d2495"
  },
  {
    "fixture": "tests/fixtures/ocr/table-vie.png",
    "question": "Trong ảnh, số lượng Bút và Vở lần lượt là bao nhiêu?",
    "visible_facts": [
      "Bút",
      "3",
      "Vở",
      "5"
    ],
    "fixture_sha256": "b3c4b9fbe86c6f35ea68274b113eafb834983c3c41848048317cdee73669917f"
  },
  {
    "fixture": "tests/fixtures/ocr/clean.png",
    "question": "What is the customer name on this invoice?",
    "expected": "State that the customer name is not visible; do not invent a name.",
    "fixture_sha256": "b6c6c432b50ffd56737d1883aaee6a7226f443aced25993c7f350de95f9d2495"
  }
]
```

Existing native verification also refuses animated/multiframe images and bounds original decoded rasters to20million pixels before the2000px/4million-pixel normalization. Preserve those checks. Any additional PNG integrity checking on the host must parse only bounded container metadata without decoding image pixels or following embedded links.

## Existing native protocol inspected during preparation

Local `runtimes/llama.cpp/tools/server/README.md` documents schema-constrained chat, inline `image_url` data, `cache_prompt` and `/v1/models` architecture modalities. Two bounded readonly model-info requests confirmed the existing alias `qwen3.5-9b-core` advertises `architecture.input_modalities=[text,image,video]` and `output_modalities=[text]`; no image, question or completion was sent. This is capability advertisement, not a D61 image-chat result or video-quality acceptance. Future adapter admission should require exactly the configured alias and an advertised image input before any raster disclosure, rather than inferring image support from the model name.

The native server accepts remote URLs/local file paths as image inputs, so the new host adapter must construct a validated inline PNG data URI itself and expose no caller-controlled `image_url`. Native `cache_prompt=false` means no reuse of a previous prompt's KV prefix; its documentation does not establish secure erasure or server-side computation abortion. Preserve that distinction in privacy/cancellation evidence.
