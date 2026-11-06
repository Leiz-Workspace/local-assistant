# ADR-134 — Shared D14 acceptance and retained request binding

**Purpose:** Record the acceptance-policy and evidence-trust corrections requested after the D14 code review.

Date: 2026-10-26. Status: Accepted within the owner's explicit “Sửa đi” request. No production architecture or model selection changes.

## Context and decision

The runner omitted the three declared compatibility results from final acceptance. The independent report omitted provenance from quality acceptance. Its request hash was supplied by the same artifact being verified and did not establish that the frozen question was actually sent.

Use one pure fail-closed policy for live first observations and normalized independently verified observations. Require the exact 42 unique identities/categories and one dispatch per profile, all declared three compatibility observations, literal boolean passes, five distinct named provenance checks, successful retirement/cancellation and restored baseline. Report format, functional and full quality checks separately. Missing, duplicate, failed or merely truthy evidence cannot grant quality PASS.

Reconstruct the complete request with the unchanged adapter payload builder: original profile/system template, frozen question/source text, frozen image bytes/hash, structural schema and every generation/stream parameter. Authenticate every historical request against the earlier delivery pinned to SHA256 `1f2b7d9197a56488b7e7ae9ce1543a43b6817f54a57b4a0aafcd4471046ce463`. This prior archive, created before this review fix, supplies an independent retained-byte anchor; recomputing an artifact's own hash does not change it.

For calibrated context, verify the neutral numbered document and single frozen needle, and bind the complete request bytes, including needle position, to that archive. This is historical integrity verification, **not a new pre-inference receipt or fresh tokenizer/position measurement**. No tokenizer/model calls are needed. A future corpus requires its own protocol and trusted binding; this historical report cannot certify arbitrary new campaigns.

Keep historical execution freezes unchanged. For the two reviewed benchmark files that now differ, verify their executed versions inside the pinned archive against the original freeze instead of changing the freeze. Verify all other frozen inputs and the unchanged 730-file application normally. Authenticate the old freeze/results/first report against the archive. Publish new review receipts separately; never overwrite old scores or measurements.

A later host reboot is distinct from historical cleanup: require the recorded before/after equality and empty native inventory, check current containers/native inventory, and disclose whether the current boot matches. Do not rerun models or alter services to recreate an old boot.

## Alternatives, impact and rollback

Separate acceptance expressions drifted and produced the reviewed false positives. Self-reported hashes alone cannot authenticate input provenance. Repeating failed questions would change the measured cohort; regenerating expected answers or weakening thresholds would invalidate acceptance. These alternatives are rejected.

Priority P1 before trusting quality promotion; dependency: retained archive, frozen inputs and corrected native parser. Effort: one bounded benchmark-policy/verifier fix and regression pass. Risks: confusing corrected replay with first scores, mistaking the historical archive for a pre-inference attestation, and treating scoped tests as a new full-suite run. Explicit receipts and immutable first evidence retain these distinctions. No production migration. Rollback restores the prior reviewed code while retaining all evidence; it never approves quality or changes models/data/defaults.
