# HAR-008-Q3 — Finite semantic review and planned self-check

**Purpose:** Freeze richer semantic correctness criteria before native responses. [ADR-186](ADR/186-native-only-finite-semantic-review-prototype.md). Date2026-11-11.

## Cases and trusted reference

`benchmarks/semantic_review_cases.py` defines twelve opaque-ID cases, fixed four-probe inputs, exact registered snippets, caller contracts and predeclared admissible source locations. Five known defects concern None/falsey defaults, UTF-8 byte quotas, inclusive ranges, integer caller attributes and cancellation. Five corresponding finite-probe controls conform; two unit contracts are unknown/conflicting. Gold tables are computed locally before generation and never inserted into model inputs/schema. Sources/model text are never executed. Registered pure operations implement only this finite test domain; they are not an arbitrary Python interpreter or independent validator of real repositories.

Verdicts: defect, no_defect (within four declared probes), uncertain (caller contract unresolved). A defect must give a global claim code, probe ID, typed expected and observed values, source evidence and short title. Expected and observed must match the trusted table and differ. Source location must be predeclared acceptable; source-pair membership alone is insufficient. All source lines are grammar alternatives, not just acceptable locations. Claims include global unused distractors; probe IDs always p0–p3. Raised exceptions use class-name strings, returned values retain JSON types. Title prose is bounded but semantically ungraded.

## Shared candidates, not retries

Each case has one no-skill candidate plus exactly one self-check, and one unchanged-repo-review candidate plus exactly one self-check:48 native calls,24 initial draws,24 planned checks. Original candidate bytes are shared with the checked outcome and kept separately. Each check receives original task/probes/sources and raw candidate text marked untrusted, with no gold/grade feedback. Skill group order alternates by case; check-after-candidate order is inherently dependent. Same CORE/Q6_K/b11557/Fast512/strict for each call; two-stage total cap1024 output tokens versus512 single-stage. Report the extra latency/budget; do not call self-review independent proof or replace initial scores.

This is **native-only benchmark prototype**, not an activated product task API/schema/skill change. Actual workspace reads use the configured owner fixture, while skill use here is inert prompt binding, not a new installation/authority lifecycle. Preserve all L1/Q2 outputs, including their narrow exact-localization scores; no old answer gets alternative-location credit.

## Freeze, bounds and reporting

Before first completion save exact cases/gold/probe tables, actual read envelopes, source/skill/code/config hashes and options in a new owner-private directory. Save complete outbound native payloads and unmodified first results, each candidate/check hash link and deterministic score. One unrelated schema development response is retained separately and never scored. Fixed bounds:48calls,120s/call,1200s/campaign, no retries. Transport/software/drift stops; a complete but malformed/truncated candidate remains a first failure and can receive only its already planned check. No source execution, tools selected by model, model downloads/replacement or cap changes.

Observe native RSS/GPU allocation with the existing pinned-PID0.2second sampler, preserve units/lifetime-HWM/missing metrics limits. Call time includes preparation/request persistence and concurrent instrumentation; checked workflow cost sums both calls, excluding one-time source-freeze/model load. No TTFT/concurrency/cold-start/SLO acceptance. Report exact finite correctness, false positives, unsupported-contract overclaims, missed defect classifications and self-check gains/regressions. Measurement completion is distinct from semantic/adoption qualification; same-author controlled cases and ungraded titles remain major limits. Stop only owned trial processes and keep production/release/default/model choices unchanged.
