# ADR 122 — Content-free observability and timing provenance

**Purpose:** Define D83 bounded aggregate inference traces and distinguish measurable streaming timings from unavailable nonstreaming metrics.

**Date:** 2026-10-23. **Status:** Accepted for optional instrumentation/probes, not a production rollout or performance SLO.

## Decision

Wrap an existing InferencePort without changing its request/model/ownership policy. Aggregate only two fixed host profiles and finite success/failure/cancellation/activity/latency/usage counters; generate opaque trace UUIDs. Retain no request/reply/exception text, raw model label, owner/query/URL, token, nonce or high-cardinality user labels. Return fresh operator-only snapshots, not public cross-owner metric endpoints. Keep active counters until actual dependency cleanup returns. Invalid/truncated completions count as failures; invalid/backward host clocks produce unavailable timing, never zero samples.

Nonstreaming replies cannot yield measured TTFT or client decode TPS; report null with explicit provenance. Add a separate bounded one-shot research stream probe against the already loaded verified CORE. Client TTFT starts immediately before the HTTP stream request and ends at first nonempty text delta, not the first role/empty SSE event. Bound30seconds/64KiB and require exact model/complete stop/usage/DONE. SSE chunks do not expose exact token boundaries, so client decode TPS stays null. Record end-to-end output tokens/wall time under its own name and optional native `predicted_per_second` only as server-reported decode TPS. No model load/switch, streaming product API or existing gateway change.

## Impact and rollback

Existing D83/P1, depends on D80/current inference port and verified original backend. Effort one instrumentation/protocol/test milestone; risks content leakage, misleading rates, cardinality growth and cancellation undercount. Fixed labels/content-free logs, complete-result checks and explicit timing-availability fields constrain them. Operator aggregate exposure still needs deployment authentication/retention review. Disable the optional wrapper/probe to roll back; retain original measurements. A single warm short probe is not a cold-load/context/concurrency benchmark, native GPU certification or SLO. Manual/model/license/release gates remain open.
