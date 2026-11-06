# ADR 085 Native CORE image chat with isolated normalization

**Purpose:** Implement D61 request normalization, bounded image sizing and private local image chat through the existing CORE/mmproj without changing accepted OCR/text inference.

**Date:** 2026-10-22. **Status:** Accepted for additive unwired implementation after D60 commit45ab011/full4120/final readonly audit; code alone is not acceptance.

## Dependency and scope

P1/existing D61, depends on D60 measured local closure, D21 isolated page preparation and the already loaded original Qwen3.5-9B Q6_K/BF16 mmproj. Estimate one port/policy/service/native-normalizer/model-adapter milestone plus controlled/native/actual acceptance. Risks: host image decoding, metadata/private image leakage, oversized raster/context, misleading model confidence, source/model mismatch and releasing ownership before a native thread or HTTP cancellation retires. No new model/package/image/service/config/schema/Vault/dependency or permanent API change.

Use a separate vision port and operation; preserve the text InferencePort/LlamaInferenceAdapter and existing OCR endpoint/transcription prompt. Trusted local composition supplies the current authenticated owner UUID and explicit current-operation bytes; no path/file UUID/source URL/history lookup exists in this initial unwired interface. This does not claim stored-file HTTP/UI integration. Output owner/hash association is provenance only, never a signed citation, approval or semantic truth certificate.

## Input and normalization

Require immutable bytes1–8MiB and png/jpg/jpeg/webp, one explicit question1–2048UTF8 bytes with bounded NFC/control policy and original whole-input bounds before normalization. Refuse remote/data-URI strings, caller-selected model/profile/projector/backend/prompt/tools and malformed types before admission. No automatic OCR escalation or image retention.

Run the unchanged `prepare_page`/`ocr_worker` with page1/modevlm from an anonymous descriptor inside its existing readonly/networkless/credential-free namespace. Original type/full-image/multiframe/20million-pixel verification, EXIF transpose/RGB/metadata removal and thumbnail2000px/4million-pixel/4MiB PNG remain. Original worker512MiB/8–9CPU/32FD and parent25s bounds apply. Host checks only the complete bounded PNG container/CRC/RGB IHDR/dimensions/chunk ordering/hash, never decodes image pixels. Only IHDR/IDAT/IEND are admitted, so ancillary EXIF/text/profile or active metadata cannot reach inference. Original bytes and normalized PNG have separate fingerprints.

Normalization runs in one owned shielded thread task. Cancellation/deadline must join that task without cancelling its future and losing the underlying thread. Native source/output descriptors remain owned until original worker cleanup finishes. No unsandboxed fallback or image reencoding/retry to rescue rejected data.

## Fixed local model contract

Use the configured existing CORE only, fixed loopback endpoint resolved by original model configuration. One bounded16KiB `/v1/models` response must contain exactly that alias and architecture advertising image input/text output before any raster is sent. Native documentation and readonly current metadata already confirm this shape; that is readiness, not a quality result.

Construct a fixed system frame and neutral JSON question with escaped role-looking delimiters plus one host-generated inline normalized PNG data URI. No caller image_url/path/HTTP headers, ambient proxy/auth, redirects, tools/history or remote images. One nonstreamed completion/temperature0/seed7/thinkingoff/max1024; JSON schema has exactly answer and uncertainties. Use `cache_prompt=false`, which disables prefix reuse but does not certify memory erasure. Bound the complete uncompressed JSON reply64KiB and validate alias/assistant role/single stop choice/no tool calls/content, strict duplicate-free complete answer schema, output-token cap and finite UTF8/control limits. No retry, smaller-image fallback or alternate model.

Questions/images/model replies remain ephemeral and untrusted, no raw logs/persistence. Replies retain owner, question/source/normalized hashes, dimensions/processor/model/UTC and explicit unverified semantics/no calibrated confidence. Existing shared model/OS/backend memory is trusted; network cancellation does not certify server-side compute abortion or secure GPU erasure.

## Ownership and acceptance

One nonqueued operation per service, original process-local four-owner/sixteen-global/60s quota primitive with no refund; the counters are a new independent image-chat quota, not a shared search route. Proposed total75s/native27s/model45s, complete-stage timeout rechecks and admission retained through cleanup. Shutdown cancels/joins only owned callers; shared normalizer/model lifetimes remain external. No caller budget/model controls.

Controlled tests must cover complete input/PNG/source/model/reply validation, privacy/redaction, quota/busy/deadlines, repeated cancellation, late-result suppression, source FD lifetime and shutdown isolation. Native tests prove original namespace/type/metadata/size/orientation/multiframe behavior and joined cancellation. Freeze exact authored public fixture questions/facts and actual options before inference; one attempt per sample, every first failure retained. Use existing clean invoice2048/42USD, Vietnamese Bút3/Vở5 table and absent customer-name question, then verify ordinary text inference still works. This is a small visible functionality sample, not independent-human or broad VLM/OCR quality. D62/D63/D67 retain broader quality/resource tasks.

Appropriate existing OCR/text/native/lifecycle regressions, final model/data/source/runtime readonly audit and complete-file archive required before D61 PASS. Rollback drains/removes only new unwired components, preserving all545 accepted source/config bytes, models/projector/config/data/collections/old artifacts. Production integration is a separately assessed backlog dependency, not silently enabled by this local adapter.
