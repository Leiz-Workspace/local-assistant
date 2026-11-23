# D90 — Current artifact snapshot and remaining P1 gates

**Purpose:** Close the existing artifact-inventory and backend tool-policy cleanup items using measured bytes and explicit tests, without approving models or release.

**Date:** 2026-10-24 (Asia/Ho_Chi_Minh). **Status:** ARTIFACT SNAPSHOT / LOCAL TOOL POLICY VERIFIED; model quality, manual/product acceptance and release remain OPEN.

## Actual read-only snapshot

The private operator streamed both existing configured GGUFs and both projectors in1MiB blocks, checked complete file identity/size/mtime/ctime before and after, and compared model hashes with unchanged `configs/models.yaml`. It did not load either model for inference, copy weights, download artifacts, select a profile or change current CORE. Symlink substitution/mid-read modification/size bounds and versioned runtime-library selection have six deterministic controls. [Measured inventory](../evidence/d90-candidate-model-runtime-snapshot.json), [verification/source/log digests](../evidence/d90-artifact-snapshot-verification.json).

| Profile | GGUF bytes | Projector bytes | Model SHA matches configured value |
|---|---:|---:|---|
| CORE |7,958,818,848|921,704,896|Yes|
| UNRESTRICTED |7,359,259,008|921,704,448|Yes; no runtime profile switch|

The companion snapshot includes exact projector hashes, the actual loaded CORE executable and eight loaded project runtime libraries, including versioned sonames. Runtime Git commit remains `5c8854fd88319125125dc4b836c98b1b215b0f23`. Projector hashes describe observed current bytes; they are not a newly verified upstream license/provenance chain. A Git commit plus binary hashes is an inventory, not a reproducible-build attestation or full OS/CUDA SBOM.

The original `releases/v0.1/release-manifest.json` matches its Git bytes and is unchanged. This new companion artifact is explicitly NOT_RELEASED, with no new model/default/profile deployment or approval. P1's request to record model/projector/runtime hashes is fulfilled; the original weighted quality scorecard and model decisions are separate gates.

## Explicit backend UNRESTRICTED tool denial

The fixed CORE-only D77/D79 backend guards reject `profile="unrestricted"` before invoking a handler. Existing text/profile prompts grant no tools, and existing workspace/coding inference services select CORE explicitly. The actual `test_profile_requires_explicit_host_core[unrestricted]` and `test_untrusted_scope_cannot_reach_policy_or_handler[profile-unrestricted]` controls PASS in the first full log. The overall first full still FAILED on two unrelated umask-sensitive fixtures; individual policy evidence is not an overall full PASS. No actual UNRESTRICTED model load/quality measurement or additional permission is inferred.

## Full regression execution diagnosis

First current712-file full run: **5505PASS/2FAIL/0ERROR/0SKIP/1756.41s**, source bytes unchanged. The caller incorrectly launched pytest with umask0077. A directory requested as0755 and a file requested as0644 therefore became0700/0600, so the negative tests did not receive their intended public-permission fixtures. Original production security checks correctly accept private files; changing those checks or tests would hide the invocation mistake.

Controlled isolated subprocess reproduction: the same two original tests fail under0077 and both pass under0022. [Exact diagnosis](../evidence/d90-permission-fixture-umask-reproduction.json). No source/security-policy change. A fresh complete rerun uses the original0022 fixture environment; supervisor/log/metadata remain explicitly0600 and roots0700. Both results are retained. Corrected full completed5507PASS/0FAIL/0ERROR/0SKIP/1762.43s; [terminal/qualified audit](../evidence/d90-corrected-full-acceptance.json).

## Production-only reference follow-up

The retained D88fresh offline CPython3.12.3environment imports the new components and validates three fixture excerpts. Actual ASGI health200 and missing-auth503 at `/api/v1/chat/completions`; pytest remains absent, isolated mode enabled, native socket connections blocked, model calls/database connections0. [Actual receipt](../evidence/d90-reference-followup-smoke.json). This adds no dependency/install or physical-device/owner acceptance.

First smoke caller incorrectly used `/api/v1/chat` and received404. Keep its log/executed test; correct only the private smoke route to the existing endpoint and retain the subsequent PASS. Existing application routes/source stay unchanged. The25private operator policy controls and this reference smoke are separate evidence, not additions to the5507full-suite count.


After the structured compiler fix, the retained production-only environment also verifies all6positive/2refusal fixture contracts, exact source Unicode, ASGIhealth/auth and imports with no native sockets/model/database calls. [Separate actual smoke](../evidence/d90-reference-structured-smoke.json). This does not reinstall dependencies, rerun model evaluation, or create listening/product approval.

## Current paired-profile follow-up, preserving historical inventory claims

The snapshot above did not load UNRESTRICTED. A later explicitly authorized [MQ002trial](MODEL_QUALITY_002_UNRESTRICTED_SCORECARD.md) did: existing exactGGUF/temporaryCPUonly/32K,30first replies/20correct/45of70textpoints; whole-childpeakRSS RAM7.68GiB,zeroGPUoffload,12GiBAS, exited0/reaped. COREretained23/30/52.5of70. No original artifact/config/default/privilege/model selection changes; no provenance/license/overallquality certification from this limited trial. Current728sourcefiles/full5674and backend authority denial remain verified.
