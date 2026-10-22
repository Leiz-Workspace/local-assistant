# D68 offline registry ASR comparison

**Purpose:** Record the controlled bilingual comparison of the two nominated ASR families, including exact scope, failures and resource evidence without selecting or deploying a default.

**Status: PASS local offline comparison; no selected or deployed ASR.** Both first candidate runs completed44/44 requests without retries, timeout, cap errors or missing outputs. ADR-094 governs this evaluation. D67's original599 source files remain unchanged; its actual4495-test run is historical coverage of that source snapshot, not a full-run claim for the new D68 scripts. Current467 related tests, including87 new D68 controls, and32 private auditor controls pass. Readonly final audit verifies608 source files, original model/configuration/data/runtime and unchanged CORE identity/text recovery.

## Candidates and isolation

| Role | Artifact | Evaluation runtime |
| --- | --- | --- |
| Original nominated ASR | Qwen/Qwen3-ASR-0.6B, revision `5eb144179a02acc5e5ba31e748d22b0cf3e303b0` | Exact official qwen-asr0.0.6 Transformers backend; CPU float32, greedy, two threads, batch one |
| Whisper-family reference | Systran/faster-whisper-small, revision `536b0662742c02347bc0e980a01041f333bce120` | Unchanged official faster-whisper1.2.1 Python sources; CTranslate2 4.6.0 CPU int8, beam five, two threads, one worker |

Model licenses declared by the upstream cards are Apache2.0 and MIT respectively. Weight storage sizes are 1,876,091,704 and 483,546,902 bytes; these are **disk sizes**, not RAM or VRAM requirements. Actual model artifacts have pinned LFS SHA256 and ordinary files have Git blob hashes in `configs/asr-evaluation-candidates.json`.

These are different practical precision/engine/decoding configurations on the same machine, not a controlled model-only efficiency comparison. Original CORE remains running. Each candidate runs alone in a fresh credential-free/network-free PID namespace, with readonly model/source/sample mounts, two-logical-CPU affinity, 8GiB address-space/1200CPU-second/900wall-second budgets and bounded private 128MiB tmpfs. No reference manifest enters the worker filesystem. No microphone, external transcription, GPU execution, server, default routing, production model/configuration, Vault, database or Docker changes.

The Qwen root initializer eagerly imports an unused forced aligner/Japanese neural tokenizer. Instead retain unchanged official backend modules as ordinary namespace packages and use the original processor/template/generation/decode protocol directly. No fake imports or model logic substitution. The complete original wheel and source hashes/licenses remain in the ignored evidence directory. Qwen primary scored output is raw decoding without its optional repetition-repair helper.

The faster-whisper wheel bundles unused VADv6 weights. Use the pinned official Python sources at tree `65882eee9f5cdbeeb2d877f1131d48cf241b327d`, omitting that asset, with VAD false. This does not install/evaluate a VAD model. Whisper's declared no-speech0.6/logprob-1.0/compression2.4 suppression remains enabled, temperature is a single zero, timestamps and previous-text conditioning are disabled. Fully consume lazy segments before stopping timing. A generation ceiling hit is an error with raw partial output retained.

## Fixed corpus and scoring

Public Google FLEURS, CC-BY4.0, revision `70bb2e84b976b7e960aa89f1c648e09c59f894dd`; original pinned test archives/TSVs acquired and verified. The viewer's501 scan-limit refusal is retained as planning evidence. Historical upstream loader schema `2de94963bc53758e33898d0b8fa3c2c71939cdef` establishes the literal seven-tab-column format; no remote dataset code is executed.

Select the first20 eligible original-order test recordings per language before predictions, each1–20seconds. Vietnamese:219.24seconds/20recordings/9distinct sentence IDs; English:198.88seconds/20recordings/10distinct sentence IDs. Keep all excluded rows/reasons. These are repeated public human-labelled sentences, not40 independent sentence texts. Training overlap is unknown; no general user-accuracy or official full-FLEURS claim.

Actual source is uncompressed mono16k IEEEfloat32 WAV. The isolated bounded RIFF reader preserves the original float32 data bits, with source/waveform SHA256, exact sample counts and upstream references. No resampling, clipping, quantization, source text repair or widening of accepted production media policies. Add silence and seed7 low-amplitude Gaussian noise,5seconds each, with English and Vietnamese hints: **four requests, two unique control waveforms**. Total requested audio438.12seconds, including repeated controls.

Freeze exact code, tests, metrics, runtime versions/source, labels, common waveforms and language hints before either candidate's scored predictions. One actual prediction per case, no outcome-driven retries, label changes or selective output trimming. Primary normalization is NFC/casefold, Unicode punctuation to space, whitespace collapse, preserving accents and digits. WER uses whitespace tokens (Vietnamese orthographic syllable-like units); CER removes whitespace. Micro-aggregate edits/reference units per language; do not average case rates or bound rates at one. No-speech false positives are normalized nonempty predictions and have no speech-WER denominator. Missing/failed/capped outputs retain incomplete coverage and cannot support a winner.

## Qualification and failures retained

The first Qwen import failed on missing namespace UID mapping before loading any model. An owned synthetic passwd/group entry fixes SDK lookup without mounting host accounts. Corrected import passed. Load-only qualification passed for both candidates within8GiB address space: Qwen5894164KiB peak lifetime process RSS and Whisper823188KiB. These include imports/load/mapped/shared pages, not unique RAM, a minimum hardware requirement or candidate VRAM. Downloaded/cache-warm files mean the timing is not a cold-storage benchmark.

The separate existing public JFK fixture is used only for SDK input/output qualification, never as a scored FLEURS example or independent accuracy reference. Qwen smoke first failed because the evaluation wrapper duplicated `return_dict_in_generate`, which the official backend already sets internally. First and diagnostic results remain unchanged; a dedicated regression test now forbids that duplicate. Corrected smoke returned one complete27-token observation without hitting the cap. No common-corpus predictions were made during qualification. Ordinary CORE echo/process identity recovered before and after each qualification.

## First actual paired observations

| Observation | Qwen3-ASR-0.6B CPU float32 | Whisper-small CT2 actual int8_float32 |
| --- | ---: | ---: |
| Completed requests |44/44 |44/44 |
| Vietnamese WER |27/549 =4.918% |105/549 =19.126% |
| Vietnamese CER |74/1916 =3.862% |211/1916 =11.013% |
| English WER |21/428 =4.907% |28/428 =6.542% |
| English CER |80/2254 =3.549% |91/2254 =4.037% |
| No-speech nonempty outputs |3/4 requests |4/4 requests |
| Import / load wall seconds |5.335 /1.163 |2.979 /0.542 |
| Total inference-call seconds |195.148 |86.767 |
| Whole worker wall seconds |202.365 |90.687 |
| All44 call latency min / median / max seconds |0.791 /4.547 /8.195 |1.473 /1.920 /2.701 |
| Duration-weighted RTF, all44 calls |0.44542 |0.19804 |
| Median per-call RTF |0.47089 |0.20829 |
| Lifetime process peak RSS KiB |5903892 |957248 |
| Lifetime process peak RSS GiB |5.630 |0.913 |
| Process CPU seconds |370.058 |164.077 |

RSS is process RAM including imports/loading/mapped/shared pages; it is not unique memory, address-space size, all-process memory or a minimum hardware requirement. These candidates executed on CPU, with no visible GPU device; existing CORE NVIDIA allocation is recorded separately, not attributed to ASR. Two inference threads and two-logical-CPU affinity do not mean exactly two kernel threads. The owned evaluation root uses about4.5GiB apparent disk storage including runtime, corpus and candidates, below the declared6GB planning budget; this is neither RAM nor an isolated cache accounting.

All438.12requested audio seconds and44call latencies are included. Each measured process is fresh and has no separate inference warmup: the first call includes lazy initialization (Qwen4.587s/Whisper2.168s), while files/kernel caches may be warm from provisioning/qualification. Therefore these are complete post-load call observations, **not uniformly warmed calls or cold-storage load measurements**. No slow-case trimming, p95 SLO, streaming first-token or decoding throughput claim. Keep the original ADR's planned warm-per-case wording as history; actual evidence/reporting uses this narrower measured scope.

On this small repeated-sentence corpus, Qwen has lower observed WER/CER in both languages; Whisper's tested configuration uses less RAM and finishes faster. Architecture/precision/beam/suppression differ, so neither result isolates model architecture or predicts general production speed/accuracy. Both fail the known no-speech controls: Qwen emits text for both silence language hints and Vietnamese noise; Whisper emits text for all four requests. Do not enable automatic audio transcription merely because speech WER is low. No timestamps, extra forced aligner, streaming recognition or approved default were evaluated. D69 evaluates the originally nominated SileroVADv5 boundary separately; VAD effectiveness and combined ASR improvement are not inferred from D68.

Raw predictions, both references, exact waveforms, source/SDK versions, first failures and complete stdout/stderr are retained under ignored `data/backups/d68-*` paths. The qualified paired freeze precedes both scored runs. The earlier prelint/import/metadata qualification snapshots remain unchanged and were never used for scored model selection. Public audit recomputes all edits/RTF/coverage from original observations and retains every control output, rather than adjusting thresholds after seeing results.

Evidence: [qualified paired freeze](evidence/d68-offline-asr-qualified-freeze.json), [audit code/control/result freeze](evidence/d68-offline-asr-audit-freeze.json), [readonly final audit](evidence/d68-offline-asr-readonly-audit.json), [acceptance](evidence/d68-offline-asr-acceptance.json). Source implementation commit`d967148`; no application model routing or source changes. A later documentation-only audio-backlog closure transition preserves its exact audited preclosure bytes and binds the accepted Git revision without rewriting old freezes.

## Compatibility, approval and rollback

Both candidates operate on private explicit float32 buffers and language hints; neither is wired to product upload/auth/session/cancellation APIs. Generation formats, timestamp behavior, precision and no-speech filtering differ. A future role choice needs actual quality/performance/resource evidence and owner approval before any registry/default/deployment edit. Keep existing CORE, embedding/reranker, all source data/collections and the D24 E5 rollback intact. A separate implementation ADR must cover API contract, warm-worker ownership/admission/cancellation and compatibility before production integration.

Recommendation for review: retain original Qwen as the accuracy-oriented candidate and Whisper-small as the lower-resource reference; select neither now. D69/no-speech segmentation, user-representative independent audio and approved resource/admission/timestamp requirements remain dependencies before proposing a production choice. Any owner-approved future deployment must be additive/default-off first, preserve current audio/source ownership contracts and every existing model role, avoid data/index migrations, then provide a separately tested disable-and-drain rollback. There is no authorization to replace models through this report.

Rollback for this evaluation retires only its owned namespace; retained source/models/corpus/results remain in ignored private directories until separately authorized cleanup. No production data/index/schema migration or existing model replacement has occurred.
