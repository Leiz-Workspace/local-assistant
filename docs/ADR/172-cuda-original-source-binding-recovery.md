# ADR 172 — Recover the original-PCM CUDA native binding

**Purpose:** Correct a newly introduced research-runner mount defect after ADR171 quality completed. Preserve all first observations and every original application/model/default.

**Status:** Necessary implementation repair within the owner’s ongoing “Làm cho nó pass đi” request. No cap, model, voice, quality or acceptance relaxation.

## Evidence and cause

ADR171 completed80first GPU quality predictions. Qwen matches all40raw CPUtexts exactly, including both language WER/CER. Whisper fails the declared noninferiority gate: VI CER253/1984 versus248/1984; it remains excluded even though English improves. No additional quality run is authorized by this repair.

The first native Qwen turn dispatched one request, but the immutable source digest rejected a wrongly mounted detector-normalized copy before transcription. No native ASR result/CORE/TTS call completed. The runner had replaced `/samples` indiscriminately: quality needs its original standalone corpus; native needs the existing original-volume normalized PCM, while only VAD uses the new peak-view directory. The rejection is a software/provenance failure, not an OOM or inference-quality result. Retain the entire first root, original source snapshot, logs,80predictions,3explicit readiness calls and partial native result.

## Repair and bounded recovery

Require an explicit phase at the CUDA command builder. Native mounts the original source directory irrespective of the offered detector path; quality/probe keep their separately scoped inputs. Test the actual original loader with differing source/view bytes and both namespace paths. Keep the already qualified CUDA worker and all model/runtime/decoder settings byte-identical.

After software tests, verify the complete first root, its frozen40source identities/hashes, exact worker hash, unchanged original checkpoints/runtime/application, first quality pass and baseline restoration. Reuse that qualified Qwen result; do not rerun80quality predictions or admit failed Whisper. Freeze one separate recovery root and six original native sources:4speech and2negative,6VAD/4ASR/4CORE/4TTS maximum, one explicit1secondzero readiness inference, zero retry. The rejected prior dispatch is never erased or counted as a success. Count the new5actual ASR calls separately from prior83actual quality/readiness inferences and one rejected native dispatch.

Use the same ADR171 CUDA SDK,64GiB virtual-address mapping/4GiB allocator/4.5GiB owned VRAM/1.25GiB free/6GiB pre-load GPUfree; all existing host/worker/CORE guards and14GiB pre-load headroom remain unchanged. CPUVAD2/TTS8, fixed Trúc Ly/reference, CORE32K/Fast512, original PCM/full clock, no new weights or shared-service action. Recovery wall≤900seconds, per-turn180seconds, private root≤8GiB. Stop on first fault and join exact owned processes; no automatic retry or cap escalation.

## Gates and limits

Require full4speech/2negative coverage, retained40/40quality parity, model/provenance/cleanup guards, and every complete-PCM speech time≤4seconds. A pass applies only to the fixed warm-resident buffered compute experiment; physical first-audible endpoint/browser/device/rights/product/default/release gates remain separate. Do not omit failed first roots or imply Whisper qualification, model adoption, streaming, new pronunciation quality, or whole-D74 PASS.

Priority P1 VOICE-LATENCY-AC-001; dependency retained first qualification and tested mount repair; effort one repair plus one bounded native milestone. Risks: repeating the mount mistake, weak evidence reuse, co-memory and confusing a compute proxy with speaker acceptance. Rollback removes this optional research runner; no migration or data/default change.

## Post-audit guard-root correction and one confirmation

The first six-turn recovery already passed (2.146–3.543seconds,6/6); preserve its entire root/source/first delivery. Audit then found the inherited Worker default made polling disk budgets examine the old campaign root. The completed new roots are actually well below8GiB, and the workflow separately checked its own root after each turn, so the measurements remain valid; the continuous guard attribution still needs correction. This is a control repair, not a new inference algorithm, cap or acceptance criterion.

Pass the explicit current campaign root into resident/CUDA worker constructors, quality and native factories, with regression tests. Keep both inference-worker implementations, SDK/model/reference and every decoder/voice method unchanged. The retained-evidence verifier permits only these two orchestration files and their tests to differ from the first snapshot; it still requires identical inference-worker sources and every frozen input/model artifact.

Authorize one finite confirmation in a distinct `d74-cuda-root-guard-confirmation-first` root under the owner’s continuing repair request: same4speech/2negative sources,6VAD/4ASR/4CORE/4TTS and one explicit zero-input readiness, no quality repeat or retries. Keep all ADR171/172 resource/deadline/provenance/cleanup/maximum gates. Stop on the first fault, do not change a result or automatically repeat. Record all six new observations separately, not as replacements for the earlier successful recovery or failed original native scope.
