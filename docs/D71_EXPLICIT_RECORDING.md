# D71 — Explicit local recording and stop controls

**Purpose:** Document the implemented recording lifecycle, actual tests, privacy boundaries and optional user-device check.

**Status:** PASS for the local browser recording scope. The owner authorized D71 while deferring D70 listening under [ADR-111](ADR/111-owner-deferred-tts-listening-and-explicit-recording.md). No TTS naturalness or production voice/model-selection claim.

## Use

From `ai/`, start the optional read-only surface with:

```sh
uv run --no-sync uvicorn apps.voice.main:app --host 127.0.0.1 --port 8091 --no-proxy-headers
```

Open `http://127.0.0.1:8091` in a browser **on the machine where you want to use the microphone**. For a remote server, use your normal SSH local port forwarding and open the forwarded loopback URL on your own machine. The server never reads its microphone. Loading the page requests no microphone. Click “Bắt đầu ghi” and accept the browser permission. Click “Dừng và nghe lại” to release capture and expose a local WAV preview; click “Hủy / xóa audio” or Escape to discard. A new recording always needs another explicit action.

The browser emits mono16k PCM, maximum480000samples/30seconds, through its native AudioWorklet. PCM is encoded into an ordinary PCM16 WAV after stopping tracks. The graph produces no live microphone feedback. A permission dialog has a10second application deadline; a later stream is stopped without starting capture. Hidden page, page exit, track loss, worklet error, invalid PCM, permission failure and explicit cancellation release capture. Stop and failure handlers do not automatically retry. No audio POST, model call, automatic download, persistent browser storage or server audio retention exists in D71.

The static surface is separate from the passed API and has no upload endpoint. It allows fixed resources only, loopback peer/Host, same-origin requests, no proxy-derived identity, no frames, no-store and a microphone permission policy. Native input remains untrusted for future D72 processing. In-memory discard does not promise secure erasure of browser/OS-managed copies or revoke the browser's remembered site permission.

## Actual validation

- **271 related Python tests PASS /15.46s /0FAIL /0SKIP**, covering the new surface plus existing normalizer/video/timeline/ASR/VAD contracts and health API. The Node suite is invoked by one Python control; do not add its11cases to271as independent coverage.
- **11 Node lifecycle/PCM/worklet tests PASS /0FAIL /0SKIP**: no device on construction, pending/late permission, duplicate start, stop/cancel, deadline, context initialization cancellation, denied permission, bad sample rate/frame, track loss, processor error, stale frame rejection, preview failure/revocation, PCM bounds and exact worklet downmix.
- **Real Brave154.0.8037.58**, using only its fake microphone: four acquired streams all end, valid mono16k WAV23852bytes after first stop, Escape/hidden-page cancellation, and native stream arriving after cancellation is stopped. No page errors or upload/external requests observed. Headless fake-device validation is not a physical-microphone or subjective listening test.
- Ruff and diff whitespace checks PASS. Readonly hash audit preserves661prior source files,917protected files,176original inputs and the original24pending listening labels. No production API/runtime/config/model/database/Vault change.

Keep first failures: the first browser probe tried `fetch(blob:)`, which CSP correctly blocked; the test now inspects its observed Blob without loosening CSP. An added permission-race scenario initially asserted the wrong stream count/order; the test was corrected and its failure retained. Neither was a neural/audio-quality retry. Raw logs and the final acceptance receipt are under `data/backups/d71-*` and [evidence](evidence/d71-explicit-recording-acceptance.json). The temporary test UI process and browser were stopped.

## Optional physical-device acceptance

On your own machine, check no microphone indicator on initial load; start requires your click; stop/cancel removes the active capture indicator; Escape/tab hiding stops capture; deny permission and verify a visible finite error; wait beyond30seconds and verify capture ends. A browser may continue showing a remembered permission icon after tracks stop; distinguish that from active capture. Check playback yourself and record browser/OS/device, date and observations. This user-device check has **not been executed by the agent** and does not supply the deferred D70 review.

## Next milestone

D72 owns bounded ASR→LLM→TTS orchestration, original sample clocks, cancellation/error handling, and the separately assessed VAD/ASR comparison/model gates. This D71 surface does not select, expose or deploy any model. Deferred D70 listening and voice licenses remain gates before voice acceptance/model selection/release.
