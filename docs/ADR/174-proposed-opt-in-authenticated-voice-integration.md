# ADR 174 — Proposed opt-in authenticated voice integration

**Purpose:** Define a concrete owner-reviewable path from the qualified local voice trial into the main application, preserving model choices, existing API security and measured runtime contracts.

**Status:** PROPOSED / READY FOR OWNER REVIEW. The current request authorizes this design and rights review. It does not approve production activation, a model/default change or a new native campaign. Nothing below is enabled by writing this ADR.

## Context and evidence

- The trial at 8092 has 766related Python / 20 JS PASS, real browser session/Origin controls, four exact ASR/CORE/playback outputs with 1.972–3.250 second HTTP roundtrips, and two correct no-speech refusals. Prepare took43.843 seconds. These are bounded warm-ready integration results, not a universal or physical first-audible SLO.
- Owner feedback is exactly “Ổn rồi”. No measured speaker timing or product/model approval is inferred.
- `apps/api/main.py` is the main API. `apps/web/` exists but is empty. Building the main voice view is additional UI composition, not attaching a button to an existing main web app.
- Existing `require_local_client` rejects any Origin and proxy headers; `authenticate_principal` requires a protected digest-to-principal file and bearer credential. The trial cookie issued to a local page visitor and its fresh per-turn owner UUID cannot be adopted as product identity.
- There is no identified global GPU-residency coordinator across application inference paths. Conversation leases and D85 bounded fixture admission do not establish that capability.
- [Rights review](../D74_VOICE_RIGHTS_REVIEW.md) supports proposing personal-local source integration, with separate bundle/distribution obligations. Preserve all candidate roles and earlier failed results.

## Decision proposed: A — personal-local, disabled by default

Use the exact existing research lane as the proposed binding: Silero v5 whole-clip detector peak-copy, original ASR PCM/clock, Qwen3-ASR-0.6B CUDA FP32/eager/TF32off, CORE Qwen3.5-9B Q6_K 32K/Fast512, and the existing Trúc Ly CPU8/FP32 reading policy/reference hashes. No new artifact, quantization, voice, automatic fallback, context reduction, source trimming or pronunciation tuning.

Implement the feature behind an explicit enable flag and owner-reviewed artifact manifest. Default-off must preserve current routes, auth, OpenAPI surface and startup behavior, with no model/SDK import/load or background preparation. Configuration names such as `ASSISTANT_VOICE_ENABLED` and an approval-manifest path are **proposed**, not files/settings changed in this task. Evaluation-only test manifests must not masquerade as production approvals.

The first product scope is one local owner, Vietnamese independent turns, canonical mono 16k PCM16 inputs 1–20 seconds, complete buffered answers and explicit Prepare/Send. Preserve 24 total attempts / 3 preparations per process, 8 minute ready-group lifetime and current turn/resource guards until separately measured and approved. Extra languages, conversation-history persistence, RAG/tool authority, public hosting, multiple API workers and unbounded throughput are not included.

## Identity and browser composition

1. Add a main voice view under a **proposed** `/voice` URL and a small in-process backend-for-frontend under a distinct `/ui/voice` prefix. The existing8092 research surface stays unchanged. The proposed main URL is not running yet.
2. Main machine API routes under a proposed `/api/v1/voice` prefix use existing loopback/bearer authentication **before reading upload bodies**. Principal comes only from authentication, never a UUID/profile/model in the body. Preserve the current no-Origin policy on existing APIs.
3. A bearer-authenticated local operator endpoint can mint a single-use, short-lived pairing code bound to that principal and credential digest. Owner enters this temporary code in the main local UI; it is not a permanent API key and must never be placed in URLs/logs. No account or external identity service is needed for this initial scope.
4. Redeeming a valid code creates an opaque HttpOnly/SameSiteStrict UI session with bounded TTL and same-origin CSRF protection. Store its principal/digest binding only in process memory. Every privileged UI action rechecks the protected principal mapping; missing/revoked/changed identity fails closed. Grant replay and cross-principal access/cancel must fail.
5. The BFF resolves the session and calls the same owner-scoped application service as the machine API. Do not invoke route handlers with fabricated requests, remove Origin restrictions, forward caller-controlled identity headers, or put bearer tokens in JavaScript. BFF, route and service shutdown/revocation preserve active-work ownership until joined.

## Runtime, CORE ownership and resource admission

Extract qualified native adapters/worker protocol from research composition into `src/infrastructure/voice/` and a pure manifest/config boundary; production code must not depend on `data/backups` paths or import benchmark operators/corpora. Retain exact decoder/renderer numerical behavior and artifact/reference hashes. Reuse `VoicePipeline`, source/owner clocks, whole-clip admission and accepted reading mapping rather than rewriting passed domain logic.

**Borrow the existing approved CORE endpoint; do not start, stop, reset or adopt a foreign/transient CORE from a voice request.** Verify its approved alias/context/runtime/artifact attestation and resource-accounting identity. A trial-owned CORE that can expire is not a product backend. Absent/unverified backend means `core_not_ready`; no automatic model/server replacement. Voice owns only its VAD/ASR/TTS workers and ephemeral files.

Introduce application-managed GPU **residency** admission, not merely a per-turn lock. The ASR GPU allocation persists while ready. For the initial conservative mode, one voice group holds the residency lease across Prepare→ready→turns→joined retirement; other managed GPU inference requests return explicit busy instead of queuing or overlapping. Include chat, conversation and direct context/gateway paths; a check of `/slots` alone is not an atomic lease. Health/static endpoints remain available. The UI must offer explicit Close voice session to release the GPU promptly instead of requiring an 8 minute wait.

One API worker is the initial supported deployment. Before activation, inventory and cover every application-managed native inference path; detect unsafe other model/runtime overlap and fail closed. This is not a host-wide lock over unrelated GPU software. Existing free-memory/resource guards continue to protect against external contention. Do not claim multi-process/distributed coordination until separately implemented and tested.

Keep pre-load MemAvailable 14 GiB, sampled worker+attestedCORE RSS 8 GiB / TTS 2 GiB, current VAD/TTS CPU/virtual caps, Qwen 64 GiB **virtual address** mapping / 4 GiB allocator / 4.5 GiB owned VRAM / free 1.25 GiB / pre-load 6 GiB, thread profiles and deadlines. Main/BFF memory and other components need separate accounting; old peaks do not prove whole-system capacity. Lack of reliable borrowed-CORE accounting blocks activation rather than weakening guards.

Cancellation aborts/join owned workers and stops client playback immediately. For a borrowed CORE request, close transport and require bounded verified quiescence under the exclusive lease before releasing it. Do not kill the shared server or infer native cancellation from HTTP disconnect alone. Unknown completion/retirement keeps admission closed and exposes a finite error. All content publication must reject stale/cancelled/revoked operations.

## Data handling and lifecycle

Authenticate before body admission; validate exact content type/size/clock; keep the original full ASR PCM and a separate detector view. One nonqueued turn per principal plus residency admission, unique operation IDs, no retry refund, bounded tombstones and owner-bound cancel/status. Model output remains untrusted text, with no tool privileges.

Preserve RAM-backed temporary inputs/native output/diagnostics, per-turn joined deletion, 5 minute browser-result TTL, no persistent audio/transcript/answer logs or automatic conversation/database writes. Native SDK buffers may remain until group retirement; no secure memory wiping claim. No weights, vendor libraries or third-party binary bundles in this source-only promotion.

API lifespan creates the optional service outside the database-required branch, after trusted configuration/auth/admission are available. Shutdown closes admission, cancels and joins voice operations, retires owned workers, releases the residency lease, and leaves borrowed CORE and existing database/service shutdown ordering intact. No new schema or data migration.

## Proposed changes and acceptance gates

| Phase / priority | Concrete deliverable | Dependencies / effort estimate | Required evidence / risks |
|---|---|---|---|
| B1 P1 | Default-off voice contracts/routes; owner-scoped service; main UI/BFF pairing/session/revocation | Approval of this ADR; existing principal store; about 1–2 engineering days | Mock tests for auth-before-body, Origin/proxy policy, cross-owner denial, grant replay, missing auth, default-off/no-load and stable legacy routes. Risk: mistakenly promoting anonymous trial auth. |
| B2 P1 | Qualified adapter extraction, approved artifact manifest, borrowed-CORE identity, residency coordinator and UI Close session | B1 and existing pins; about 2–3 days | Byte/phone/clock parity, lazy imports, cancellation/drain, busy/expiry/cleanup, all managed caller inventory, no shared-CORE stop. Risk: resident GPU contention and incomplete legacy-path coverage. |
| B3 P1 | One conditional native qualification through isolated new main UI/API composition | B1/B2 software/rights/provenance/resource gates PASS; about 0.5–1 day | Fixed 4 retained VI speech / 2 negative inputs; first outputs exact, every complete HTTP response ≤4 seconds, negatives before downstream inference, verified cleanup. Reused source panel is integration evidence, not new broad quality. |
| B4 P1 before activation | Declared real-device/room/short-quiet-ASR and physical first-audible acceptance, final model/voice/default decision | B3 plus owner/device/reference availability; effort not yet fixed | Physical ≤4 seconds measured separately; retain every missing/failed case. Do not infer it from “Ổn rồi”, replay scheduling or synthetic browser tests. |
| D1 P2 only if distributing | Shipping SBOM/notices/project-license/vendor/denoiser lineage review | Actual package contents and owner distribution scope; initially 1–2 days, remaining review uncertain | Installed inventory is not shipping clearance. No new license or redistribution decision is made automatically. |

Estimates are planning ranges, not calendar commitments or acceptance. Do not advance development-day labels merely because implementation exists. Broader fresh latency/ASR workloads require their own declared labels/protocol; do not select only fast cases or reopen stopped pronunciation cycles.

### Concrete conditional native budget for requested approval

The owner-review packet asks for **one implementation campaign covering B1–B3 conditionally**, not activation. After software and source gates actually pass, preregister the same four speech and two negative IDs/PCM hashes from `d74-voice-browser-trial-first/http-execution-freeze.json`; no relabel/new source selection. At most 6 VAD / 4 ASR / 4 CORE / 4 TTS plus one declared 1 second zero ASR readiness, no retries or extra model.

Use an isolated evaluation configuration, RAM-backed temporary auth/principal credentials, a clean free test slot and one operator-owned original CORE for the test. The application borrows that **explicitly attested evaluation CORE**; the operator retires it only after application/workers join. Do not contact/reset a preexisting shared CORE or change production auth/config. Stop on first unexpected software/resource/provenance fault and preserve all rows, including unattempted ones. Do not automatically run the old model-calling full suite outside this fixed budget; select appropriate software regressions and disclose their scope.

Native qualification is not enabled by this proposed ADR alone. No new checkpoint/SDK download, benchmark threshold reduction, default/model adoption, database/Vault write, external audio upload or production deployment is in the requested campaign.

## Migration, rollback and owner decision

No existing data or index migration is required. Additive optional routes and UI; original recorder, 8092 trial, model registry, E5/Qwen embedding records, Qdrant and D24 history stay unchanged. Changes to main entry/lifespan/gateway admission are narrowly justified by opt-in composition and tested in disabled and enabled modes; avoid unrelated cleanup of passed code.

Rollback turns off new admission/feature, rejects late output, joins owned operations/workers, releases only verified leases and removes UI pairing/session state. Borrowed CORE, existing model/config/data/auth files and prior evidence are retained. If a native request cannot be proven quiescent, do not claim complete rollback or release unsafe admission.

**Owner decision pending:** A = implement B1/B2 with the feature default-off, then one B3 campaign only when all stated gates pass. This does not approve product activation, a new model/default/voice or D90 release. B = retain research-only mode and defer main integration. The requested preparation task is complete when these documents/evidence are reviewable; no decision is silently recorded as approved.
