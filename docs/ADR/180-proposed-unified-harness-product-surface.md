# ADR 180 — Proposed unified harness CLI and llama.cpp chat surface

**Purpose:** Define the proposed integration boundary for a usable harness product, context composition, specialist skills and optional media generation.

**Date:** 2026-11-10. **Status:** Accepted for staged implementation after the owner's “Vậy làm những thứ tôi đã bảo đi”. The original design-only stage remains historical. [ADR-181](181-checkout-cli-desktop-and-readonly-specialist-runs.md) records the implemented first slice; generation model adoption, migrations, production activation and release are not approved by this request alone.

## Context

The repository already has scoped workspace tools, guarded actions, skill contracts, hooks, plans/checkpoints and token-bounded conversation history. They are not a unified task-run product. Operator scripts are not a common CLI. Existing vision/video components interpret media rather than synthesize it. Skill instructions are parsed but no public task-level prompt-binding workflow has been established.

The owner requested a CLI, reuse of the llama.cpp chat interface, context strategies, managed specialist skills and an assessed plan for image/video generation. The checked-out runtime matches pin `5c8854fd88319125125dc4b836c98b1b215b0f23`. Its UI has its own browser conversation storage, streaming API, native tools, MCP and model-management surfaces. Directly exposing those surfaces would bypass application ownership and action controls.

## Proposed decision

1. Add one authenticated application task coordinator using existing bounded planner, hooks, dispatch and approvals. CLI and browser are clients, never additional executors or authority sources.
2. Design the `la` CLI around status, chat, runs, approvals, context inspection, skills and artifacts. Use existing `uv` workflow and Python argparse initially. No model installation, service restart or Vault mutation as an implicit CLI startup step.
3. Reuse pinned llama.cpp UI assets with a narrowly scoped same-origin compatibility gateway and minimal integration changes. Preserve the existing bearer/local-client API boundary. Define a separate browser session/CSRF boundary, real SSE and server-owned Conversation mapping; prohibit generic native reverse proxying and direct browser tool/MCP/model management.
4. Introduce context composition incrementally: deterministic source layers/budgets first, then evidence packing and structured working state. Keep current whole-turn/tokenizer fitting as baseline. Summarization/automatic memory binding require measured preservation and consent gates, not assumptions.
5. Bind only exact owner-reviewed installed skill instructions to a task. Preserve ADR-115's v1 read-only permission contract and process-local grants. Durable catalog metadata must not restore installation/approval authority after restart. Skill trust never grants a write action.
6. Plan image/video generation as optional ports, jobs and owned artifacts. Select no generation model in this ADR. Resource/quality/license evaluation and explicit model approval must precede model preparation or activation.

The complete command, endpoint, context and skill contracts are in [the product design](../HARNESS_PRODUCT_DESIGN.md). Dependencies, effort, risks and Acceptance Criteria are in [the assessed backlog](../progress/HARNESS_PRODUCT_BACKLOG.md).

## Alternatives and consequences

- Opening native llama-server UI directly is suitable only as a runtime/operator interface. It cannot represent authenticated product Conversation, skill or approval integration.
- Building a new chat UI would duplicate upstream work and contradict the requested interface choice. Retain upstream presentation and isolate compatibility changes instead.
- Executing the agent loop in each client would duplicate controls and break recovery/approval ownership. Keep one server coordinator.
- A universal auto-loading plugin/model agent would expand authority and resources beyond the current contracts. Defer package scripts, remote marketplace, free-form shell and automatic model switching.

Integration costs include UI protocol/version maintenance, conversation-cache reconciliation, new browser-auth tests, run persistence design and resource scheduling. The current API is not SSE-compatible merely because the native runtime is. Native router, tool and resumable-stream behavior must be explicitly supported or disabled.

## Acceptance, rollout and rollback

No existing day is advanced by this proposal. Complete HAR-001 through HAR-007 in dependency order after architecture review, then context and specialist evaluations. Model-generation preparation remains separately gated. Do not change original D60/D81/D89/D90 criteria or historic evidence.

Before activation, require CLI/API contracts, auth/ACL and CSRF tests, real stream/cancel/disconnect tests, no duplicate writes on recovery, context overflow/provenance tests, skill revocation tests and a frozen-source integration result. Media generation additionally requires approved measured resource/quality/license envelopes and artifact lifecycle tests.

Ship new entrypoints and adapters default-off. Rollback disables them and joins owned workers while retaining metadata, action receipts and artifacts. Existing routes, models, runtime pins, Qdrant collections, Vault, database contents and prior accepted workflows remain unchanged during this design task. Any implementation requiring persistent schema/config changes needs its own concrete migration/rollback review.
