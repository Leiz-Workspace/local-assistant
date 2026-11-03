# D72 — Held-out VAD and ASR comparison

**Purpose:** Report actual original-candidate gated/ungated observations separately from production activation, word-boundary certification and TTS listening.

**Status:** Bounded offline comparison COMPLETE; VAD concatenation NOT APPROVED for product activation. D72 application/native wiring remains separately tracked.

## Corpus and protocol

Original retained FLEURS artifacts,20new utterance/sentence identities per language outside D68/D69, five authored negatives and two padded repeats. Exactly40independent speech utterances; the two composites repeat one utterance per language and are reported separately from the primary40. No new download or result-dependent selection. All references stay outside worker mounts. Source/configuration hashes and raw receipts are in [evidence](evidence/d72-vad-asr-comparison-first.json).

Original Silero5 processed47inputs in forward/reverse order:94first observations, exact source/span/probability replay. Gating concatenates original integer-sample spans without gain repair; removed gaps remain explicit in the mapping. Five empty gates skip ASR. Each original ASR candidate processes89reference-free requests, interleaved ungated then gated per source, once each. Very short nonempty inputs would receive recorded trailing zero padding to meet the unchanged one-second worker minimum. Independent sample-level word/quiet-speech labels do not exist, so this cannot certify word preservation or word alignment.

## Primary results:20independent utterances per language

| Candidate | Language | Ungated WER | Gated WER | Ungated CER | Gated CER |
|---|---|---:|---:|---:|---:|
| qwen3-asr-0.6b | vi_vn | 7.614% | 8.968% | 4.990% | 5.998% |
| qwen3-asr-0.6b | en_us | 5.652% | 11.522% | 4.122% | 9.961% |
| whisper-small-ct2 | vi_vn | 20.474% | 19.966% | 12.500% | 11.542% |
| whisper-small-ct2 | en_us | 6.087% | 11.739% | 3.925% | 9.470% |

Both variants have complete40/40primary coverage. Raw outputs and all47case metrics, including padded repeats and failed lexical predictions, are retained; no semantic transcript correction or retry.

| Candidate | Ungated nonempty outputs on5negatives | Gated nonempty outputs | Whole worker wall | Whole worker peak RSS RAM |
|---|---:|---:|---:|---:|
| qwen3-asr-0.6b | 4/5 | 0/5 | 421.091s | 5.6359GiB |
| whisper-small-ct2 | 5/5 | 0/5 | 186.009s | 0.9170GiB |

Gating suppresses all five authored no-speech signals, but Qwen speech WER worsens in both languages and Whisper English WER also worsens. The small Whisper Vietnamese improvement is not evidence of safe universal gating. Keep the product gate disabled; do not silently choose a model or repair/retry the failed words.

Worker wall includes import/load and both variants sharing one model process; it is not cold-load latency, streaming TTFA, a per-variant isolated latency experiment or minimum RAM/VRAM. Qwen uses original CPUfloat32/eager; Whisper uses its original CPUint8 request/native int8_float32 execution. Do not attribute differences solely to model architecture.

Original VAD3GiB/ASR8GiB virtual limits, CPU2/offline namespaces and14GiBsampled host preflight were retained; no GPU evaluator. All workers exit0/no timeout/reaped. CORE PID37256/start63900/command/context32K unchanged and literal text recovery passed. Native model artifacts/configurations, databases, source collections and earlier scores are unchanged.

## Remaining product gates

Do not claim fine-grained short/quiet-word retention or enable VAD from this comparison. Any further gating proposal needs explicit source-clock/coverage evidence for its intended policy. Buffered application/native voice composition has its own acceptance evidence. Product ASR/TTS choices and voice license approval remain explicit owner decisions. Owner D70listening24/24is now recorded with quality limitations; [D74voice/model/rights/no-speech/device acceptance](D74_VOICE_DECISION_BRIEF.md) remains pending. These ASR metrics are not naturalness.
