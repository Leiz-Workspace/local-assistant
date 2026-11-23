# HAR-008-R1 — Four-arm source output contract evaluation

Purpose: measure the opt-in mechanics remediation from ADR-183 separately from skill quality, without changing HAR-008 v1 first outcomes or the approved model.

## Frozen scope

Initial cohort: `benchmarks/fixtures/har008-source-review-r1.json`. The campaign stopped on attempt 3 **before constrained generation** because the catalog parser rejected real tool metadata absent from its fixture. Two text responses, the failed run and INCOMPLETE summary remain retained. Corrected the parser to accept the actual full envelope, added a real native tool regression and passed a new full-path development pilot. Do not resume or regrade R1.

R2 cohort: `benchmarks/fixtures/har008-source-review-r2.json`, 48 first outcomes retained. Incorrect flat schema binding silently selected generic-object JSON, as shown by the actual pinned parser; nine constrained outputs failed host validation. Treat as invalid schema-enforcement evidence, not a successful schema benchmark. Do not resume or regrade R2.

Final replacement cohort, frozen before its native calls: `benchmarks/fixtures/har008-source-review-r3.json`, 12 same-author controlled cases: six source questions (one Vietnamese), six review cases; four null controls, one source-instruction control. No previous cohort ID/source/question is reused. These remain related controlled task families, not independently authored or broad qualification. Oracles are exact value types and complete source lines with ASCII indentation/trailing spaces removed, or null/null, defined before inference and never sent to the model. Two earlier positive development pilots and three new adversarial format controls are excluded: the latter requested an outside quote, null with text quote and preserved indentation; the corrected nested binding produced VALID outputs on all three.

Four arms per case: `text_baseline`, `text_skill`, `constrained_baseline`, `constrained_skill`. Rotate the four-arm sequence by case index; every arm occupies each position three times. Same approved CORE, Fast preset, 512 output-token cap, strict context strategy, one explicit native workspace.read and unchanged skill hashes. No tool selection, retries, output extraction, oracle-driven schema, model replacement, downloads or default activation.

The constrained schema admits **all** retained canonical source lines, including irrelevant/injection lines; it does not contain only the expected answer. Mandatory host instructions declare schema/null precedence. Thus the measured factor combines schema decoding and those host instructions; it does not isolate their separate effects. Source-valid JSON can still contain a wrong value or irrelevant quote.

## Execution and scoring

Freeze corpus/oracles, source/skill/code/config hashes and options before the first call. Run 48 first outcomes through an isolated authenticated product server on loopback, separate from the active desktop. Maximum campaign wall time 480 seconds, existing per-run deadline 120 seconds. Save each request, full first response and exact deterministic score in exclusive owner-private files. Stop on transport, context-binding, software or frozen-input drift; preserve partial receipts. A host-rejected native output is a first quality failure and remains counted without retry.

Report format, exact typed value, exact oracle quote, strict conjunction and independent output-contract failures by arm. A contract-invalid output cannot be a strict success. Compare paired gains/regressions within this cohort. Report wall time descriptively; no TTFT, peak RAM/VRAM or resource acceptance is inferred. Do not compare changed cohorts causally or overwrite the original baseline 5/12, skill 6/12.

Measurement completion does not promote a skill or model: `promotion=NOT_QUALIFIED`, even at saturation. Keep broader specialist, context-semantic, clean-install, full-regression and release gates open. Remove only this campaign's temporary skill grants and terminal runs after retaining receipts. Do not restart the primary desktop or CORE. Rollback is to omit `--output-contract`, retaining all results.
