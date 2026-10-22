# ADR 099 — Bounded official public audio-review qualification

**Purpose:** Test an already available audio-input service against synthetic controls before considering its source-bound AI observations for the unresolved D70 auditory criterion.

**Date:** 2026-10-22. **Status:** Accepted for bounded qualification under the owner's continuing D70 evaluation instruction; neither qualified review evidence nor D70 acceptance exists yet. ADR-097 remains REJECTED; D71 remains unstarted. ADR-098's proposed local model download is not approved or executed.

## Decision and scope

Use the ordinary published anonymous API of the [official Qwen demo](https://huggingface.co/spaces/Qwen/Qwen2.5-Omni-7B-Demo) as an evaluation tool. This provisions no neural model, replaces no agreed project model and deploys no service. Inputs are only existing generated neutral test speech and authored synthetic controls; no user recordings, credentials, source database, documents or account data. This is a declared online AI reviewer, not an offline/local reviewer or an assertion that the orchestrating assistant can hear.

The available service exposes Gradio5.23.1 `/chat_predict` with audio/text inputs and fresh per-request state. Public application revision`c5fae1cb2829e3b2075a248cd50f6fd1dc4f4863`, sourceSHA256`ad9fb4df3712b95c8df293c7fef1b96d52b6ab6d1a4650d565ef561045d72e3a`, routes to the **`qwen-omni-turbo` API alias**. Despite the demo's7B title, its exact serving checkpoint, decoder settings and backend revision cannot be pinned or independently verified. Never report it as the downloaded original3B/7B model. [Public interface metadata](../../data/backups/d70-audio-reviewer-planning/public-demo-source-interface.json).

The [Gradio API documentation](https://gradio.app/4.44.1/guides/querying-gradio-apps-with-curl) describes ordinary public prediction/event streaming; the actual5.23.1 endpoint schema has been retained before use. No login, billing, paid account creation, API key, gated access, rate-limit bypass or private endpoint is authorized. If normal access fails or rate limits occur, preserve the first failure and stop; do not evade limits. Public-provider availability/retention are not production guarantees.

## Frozen qualification before any reviewed common output

Five predeclared opaque controls: existing separate Qwen English smoke; existing separate Piper Vietnamese smoke; authored5second silence; seed7 authored5second noise; and a severely clipped copy of the English smoke. Keep originals unchanged. Store exact raw/WAV hashes and retain full input duration; opaque upload filenames and a fixed English prompt withhold the expected class, text, candidate names and all ASR/latency scores.

Require speech/English, speech/Vietnamese, silence/no-speech, non-speech-noise and an acknowledged audible distortion on the clipped speech, respectively. All factual/control conditions must be met from the **first** raw audio-conditioned responses; uncertain or unsupported Vietnamese does not count as qualification. This is a capability/control check, not a calibrated human naturalness benchmark. No outcome-driven prompt, label, audio or decoder tuning; preserve transport/protocol failures separately.

If qualification passes, freeze its result, source and protocol before reviewing the24existing first TTS outputs once. Use the same opaque IDs/fixed prompt and full-timeline PCM16 inspection copies, fresh history per request, full original/native/transmitted hashes and a parent-only identity mapping. Conversion rounds float32×32767 to PCM16 without gain, clipping or trimming; refuse native peaks above1 instead of repairing them. Original native samples remain authoritative and unchanged. Native outputs and prior first scores remain untouched. Keep every failure/uncertainty/capped/partial response and actual service identity. Return qualitative speech presence, language, prosody/artifacts and naturalness confidence; never independent human MOS or supported-Vietnamese certification. D70 may close only when the actual review evidence is adequate under its original AC; receiving text alone is not success.

## Bounds, tests and audit

New additive source/tests only; preserve all624prior source files/environments/model/data/config/CORE and previously frozen176artifacts. Use existing uv runtime, no dependency installation. Fixed HTTPS origin only, no redirects/authentication/cookies, exact upload/prediction/event endpoints, max2MiB input, max2MiB response/64KiB lines, total240seconds per request and bounded60KiB extracted review. Explicitly reject symlinks/special files, wrong source/WAV hashes, foreign origins/paths, duplicate identities, unexpected response shapes and fabricated listening flags. Publish private0600 exclusive first evidence, no raw/signed URL logging.

Only one remote request at a time. A timeout is an incomplete remote operation, not proof the provider stopped; retain that limitation and stop further work. Normal complete events establish response completion only. Do not claim deletion or provider-side process draining/retention guarantees. No generated service audio is downloaded or treated as TTS benchmark data. Test request authority, streaming/error bounds, extraction and coverage before the first qualification call.

## Priority, dependency, effort and risk

P1/D70 blocker; qualification plus one24-case review milestone if viable. Depends on genuine anonymous availability and successful controls. Risks: alias drift, family bias, weak Vietnamese hearing, hallucinated descriptions, uncalibrated naturalness, public cache/retention, rate limits and incomplete remote cancellation. Input minimization, blind controls, strict bounds, first-result retention and uncertainty accounting constrain these risks; they do not certify the service.

This online option preserves actual audio inspection atD70 and avoids an unapproved local weight download. No model/default/config/database migration occurs. Rollback closes owned client connections and stops further requests; retain private evidence and untouched originals. No claim that already submitted provider data can be revoked. Failure leaves D70 open and D71 unstarted. Any later local model provisioning or product model/provider adoption requires its own approval; neither ADR-098 nor this qualification grants it.
