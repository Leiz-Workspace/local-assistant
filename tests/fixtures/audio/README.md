# Public speech fixture provenance

**Purpose:** Identify the public speech input and exact retained source/license artifacts used by D66 explicit supplied-transcript/frame composition.

`jfk.flac` is copied unchanged from `openai/whisper` commit `86098128c0b4f24f0e2aa2994de830614b474227`, source `tests/jfk.flac`. `provenance.json` contains original URLs, retrieval UTC, byte counts and exact SHA256. `WHISPER_LICENSE.txt` is the complete unchanged upstream license; `whisper-test-transcribe.source.txt` retains the upstream test as evidence data, never executed by this application. Its selected phrase/timing assertions do not establish a new independent full transcript or local ASR benchmark.

The D66 composite contains this real speech normalized by the isolated native worker and separate authored visual stages. Its full reference text is explicitly supplied/same-agent/unverified; no speech recognizer or model is downloaded/selected/deployed. No microphone/private recording or original historic video claim. Run the authored composite generator with `uv run --no-sync python -m scripts.generate_transcript_video_golden`; no raw speech codec is decoded on the host by that generator.
