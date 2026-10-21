# ADR-071: Neutral JSON encoding of web source delimiters

**Purpose:** Authorize the smallest necessary repair to accepted D47 prompt serialization after a frozen D52 failure, preserving original source evidence and agreed models.

**Date:** 2026-10-21 (Asia/Ho_Chi_Minh).

**Status:** Accepted necessary repair after original2157 related PASS/140.83s/0SKIP and exact first-cohort archive. Distinct same-oracle CORE cohort8/8 PASS/4.229s; first7/8 retained. Repaired2164 related plus fresh3534 full PASS/0SKIP/exit0 and clean readonly audit now complete; D52 PASS within defined local scope.

## Observed problem and rationale

The first eight one-attempt original CORE responses complete with fixed configuration; application boundary8/8 and marker adherence8/8, functional oracle7/8. Role-delimiter source text makes the model return the correct fictional fact as plain prose rather than the required JSON; original schema correctly rejects it. The first raw completion/source/prompt hash remains private and unchanged. No unauthorized tool or private HTTP action occurs. Literal protocol-looking delimiters in the source data are a plausible contributor; do not claim a proven tokenizer exploit or credential leak from this observation.

Current `search_messages` serializes complete untrusted query/title/URL/snippet fields as JSON, but leaves angle brackets literal. Encode `<` and `>` as JSON Unicode escapes in that data message before checking the existing24KiB prompt limit. Every decoded value remains exactly equal to its original source string; original source IDs/URLs/hashes, fixed system policy, CORE route/model/preset/temperature/token budget, response schema and all permission boundaries remain unchanged. The model sees JSON escape syntax instead of literal role delimiters. No stripping, replacement of source facts, truncation or instruction-based URL/model/tool selection.

This is a necessary accepted-source repair justified by actual D52 evidence, not a model replacement or retrospective edit of PASS results. Only `src/application/services/search_pipeline.py` changes among485 accepted source/config files. Add targeted complete-source roundtrip, angle-token absence, query/title/URL/snippet, aggregate expansion/limit/no-clipping/citation/log tests in a separate new test file; preserve existing passing tests/fixtures. Larger encoded inputs may now hit the same explicit byte budget earlier; reject them rather than silently narrowing evidence. Existing512-byte query/title/snippet/URL and24KiB prompt limits remain.

## Priority, dependencies, effort and risks

P1 blocker inside D52; do not advance D53 while the current acceptance fails. Estimate one serialization repair plus eight same-original-corpus actual measurements, affected regression and full application/native/model/data audit. Dependencies: completed original frozen related gate, original CORE/runtime and cached models already present. Risks: accidentally changing decoded source values, failing to account escaped expansion, old-source provenance falsely reported unchanged, changing corpus/oracles after failure and overstating eight same-agent examples as general security.

No model/image/package download, API enable, schema/Vault/provider/database service change or migration. Every prior source hash remains historical and must verify against its original accepted Git blob where this one current file differs. Current repaired-source freeze records both old/new digests; all other484 accepted bytes must remain unchanged. No historical evidence rewrite.

## Required acceptance and rollback

Archive original current source/tests/corpus/freeze/eight outcomes/related result before repair. Freeze a distinct repaired cohort with identical corpus/order/oracles and original model/preset/resources; one application-port completion per case, no hidden retry. All8 functional/application/raw-adherence gates must pass, including both benign controls. A new failure remains a failure, not a threshold relaxation. Run affected regression then a fresh full with actual observed exit/zero SKIP and boot/PID/source provenance; old D48 full3010 is historical only. Only after full and final readonly/runtime audit may D52 close.

Rollback restores the exact previous serializer from D51 commit176825b after stopping only owned test calls, retaining both cohort outcomes. Original stricter response schema continues to reject the known plain-prose failure; no model/data/config/reindex/container migration is needed. This narrow encoding does not prove general prompt-injection resistance or full-page-to-agent safety; future research composition still needs its own gates.


Pre-full controls100 PASS/7.00s include70 accepted search controls plus30 D52 controls,7 native. Source-quality5 Python/41 described functions/classes passes isolated Ruff; full3534 and new30 case collection are not execution results. Repaired490-source/1032-hash freeze b3205577f105990838e31b160a1d6f9b8466cbea766c8ef30d63650448f8e420 records one old/new source exception and unchanged original corpus/oracles/model; complete6-file evaluated archive0600/CRC/exact bytes.


Fresh full3534 PASS/1685.66s (0:28:05)/0SKIP/exit0, wrapper1686.53s; log d4339fcb080a051d74356b085a9d885d62483cd0acf8b5872438d9e3ceff16e0. Final490-source/1032-hash audit verifies this one old/new serializer against Git, all other484 accepted D51 bytes, original15 containers/CORE/model/config/Vault/data/ACLs unchanged and no owned browser resources left. Original7/8/2157 related and all first raw outcomes remain unchanged. Both original and repaired cohorts stay same-agent development examples, not held-out/general security evidence.
