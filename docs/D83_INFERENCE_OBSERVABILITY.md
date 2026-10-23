# D83 — Inference observability and timing provenance

**Purpose:** Explain verified content-free aggregate counters and the limits of measured token timing.

**Status:** Local optional instrumentation/probe VERIFIED. [ADR122](ADR/122-content-free-observability-and-timing-provenance.md).

InferenceObservability wraps the existing port unchanged: fixed CORE/UNRESTRICTED aggregate started/completed/failed/cancelled/active/peak counters, measured wall latency and validated successful token usage. Opaque trace UUIDs and finite outcome labels omit request/reply/exception text, credentials, user/model URLs and high-cardinality fields. Invalid/truncated replies count as failures; invalid/backward clocks produce no latency sample. Actual awaited cleanup precedes active-counter retirement. Snapshots are fresh operator-only data; no public metrics endpoint is added.

Nonstreaming TTFT and client decode TPS are **null/unavailable**, never approximated as total latency or zero. A separate30second/64KiB one-shot SSE probe verifies exact already-loaded CORE/model, first nonempty text, explicit stop/usage/DONE and finite timing. Empty/role events do not define first-token arrival. Chunk timestamps lack exact token boundaries, so client decode TPS remains unavailable.

Actual neutral warm stream: **client TTFT169.451ms**, total248.696ms,24input/7output tokens,6content chunks; client end-to-end28.147output tokens/second. Backend separately reports decode73.671tokens/second, labeled **native/server-reported**, not inferred from chunks. Exact original CORE PID/start/command unchanged. One actual wrapped nonstreaming CORE request also reports complete usage/activity/latency with no body retained in telemetry. These short warm checks do not establish cold-load, long-context, concurrency or SLO performance.

**22new/66related PASS0.94s/0FAIL/0SKIP/Ruff PASS**: clock/failure/usage/cardinality/redaction/cancellation controls and SSE incomplete/mismatched/truncated/oversized/missing-usage/duplicate/backward-clock cases. [Native/source/log receipts](evidence/d83-observability-verification.json). No existing gateway/config/model/API deployment change; the D82 route remains the sole necessary old-source exception. D84 isolated backup/restore is next; existing manual/product/format gates stay open.
