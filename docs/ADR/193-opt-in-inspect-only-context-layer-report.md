# ADR-193: Opt-in inspect-only context layer report (HAR-006 v2, product side)

**Purpose:** Let a caller of `ProductInference.prepare` ask for an exact, layered account of one default whole-turn packing (schema 1): which tokens each layer costs, why each message or source was left out, and how the output budget was set. Packing, routes, models, presets, defaults and context size do not change.

**Date:** 2026-11-12. **Status:** IMPLEMENTED as an opt-in software change and MEASURED in HAR-006 v2 on 2026-11-12.
- **Measured result.** Inspection completed on every default-path composition. The layers telescoped exactly to `input_tokens`, and C1–C6 held. The server count matched in 172 of 172 cells, so the label is ALLOCATION_VERIFIED ([result](../HAR006_V2_RESULT.md)).
- **Scope.** It is not exposed through routes, the CLI, the UI or `/status`. Exposing it, and adopting it, are the owner's decisions.
- **Supersedes:** nothing.

## Context

- The schema-1 report has only totals: `input_tokens`, `retained_messages`, `trimmed_messages` and the included and omitted evidence with reasons. It has no per-layer tokens, no split of `trimmed_messages` by cause and no budget arithmetic. The HAR-006 item "full layered allocation" therefore stays open.
- HAR-006 v2 measures the default composer exactly as shipped. Any edit to the packing code would change what is being measured.
- Drops by cause can be re-derived outside the composer from `(messages, fitted, report)` with the composer's own read-only helpers (`select_whole_turns`, `fit_token_budget`). No bookkeeping inside `compose_context` is needed.

## Decision

1. **New module** `src/application/services/context_inspection.py` with `inspect_context(messages, fitted, report, *, count_tokens, preset, max_tokens=None, skill=None, evidence=(), output_contract="text")`.
   - It reads only the packing inputs and outputs, never mutates them, and returns a dict with `status` COMPLETE, MISMATCH (with a closed reason code) or UNSUPPORTED.
   - **Reconstruction and conservation (C1–C6):**
     - C1: the evidence indices partition into included and omitted, with the composer's admissible reasons.
     - C2: the packed task is exactly the original task plus each included block, in index order.
     - C3: no head or tail fragment (256 escaped characters) of an omitted, non-duplicate item appears in the packed input.
     - C4: the retained pairs are byte-identical originals and form the newest suffix of `select_whole_turns`' pairs.
     - C5: the system message is POLICY, then the exact contract segment, then the exact skill block.
     - C6: the unpaired, `turn_window`, `token_budget` and `evidence_priority` message counts sum to `trimmed_messages`.
   - **Layers (`prefix-marginal-v1`):** the inspector counts a growing sequence of well-formed conversations with the same counter: the task alone, then policy, contract and skill, each client system message, each retained pair (oldest first) and each included evidence block. Each layer is the difference between consecutive counts, so the layers telescope exactly to `input_tokens`. Template framing is attributed to `current_task`.
   - **Omissions:**
     - Dropped pairs get a standalone marginal; `turn_window` and `unpaired` get null.
     - Evidence entries carry bytes, UTF-8 validity and literal control-token counts. `token_budget` and `history_priority` items get a marginal against the packed input. `duplicate_evidence` and `source_byte_limit` items get null and are never tokenized.
   - **Budget block:** computed from `calculate_budget` at the packed input. It gives the granted output, `unallocated`, the closed-form `input_ceiling` (32,768 − 256 − 512, minus the reasoning budget for finite thinking) and `identity_ok`.
   - **Count bound:** `count_calls ≤ (P_sel + 1) + 4 + C + P_ret + E_inc + P_drop + E_omit`, which is reported as `count_bound`.
   - **Errors:** counter errors and `CancelledError` propagate. A reconstruction failure returns MISMATCH and never raises.
   - **Logging:** one log line, `context_inspection_computed status=… calls=… layers=…`, with no text.
2. **Opt-in flag:** `ProductInference.prepare(…, inspect_layers=False)`. When the flag is True, `report["inspection"]` is computed after `compose_context` returns, inside the same HTTP client block and with the same `count` closure. When it is False, nothing else runs and the HTTP request sequence is unchanged.

## Scope

- **Default path only.** Schema-2 reports (the explicit `history_policy` path of HAR-009) return `UNSUPPORTED` / `history_policy_path` without any count.
- **Not exposed.** The report is not exposed through routes, the CLI, the UI or `/status`. Exposing it would be a separate item with its own ADR.
- **Byte-unchanged.** These files have an empty diff against base `f30a49f`:
  - `context_composer.py`, `conversation_context.py`, `context_reduction.py`;
  - `presets.py`, `llama_gateway.py`, `configs/models.yaml`;
  - `apps/harness/routes.py`, `apps/harness/service.py`.

  The `inference.py` diff is additive: one import, one keyword and one guarded block.

## Alternatives

- **Bookkeeping inside `compose_context`** (Designs 2 and 3). Rejected: it edits the measured code, which is not needed.
- **An unwired module used only by the benchmark** (Design 1). Rejected: the product would still have no inspector.
- **An empty-content template skeleton for the template layer.** Rejected: empty contents are not a well-formed conversation, and the skeleton can fail on the real template.
- **Swallowing counter failures as "unavailable".** Rejected: it hides cancellation and backend faults.

## Consequences

- Layer figures are order-dependent prefix marginals. The total is exact; the split between layers is not an intrinsic cost.
- With the flag on, inspection adds up to `count_bound` count calls (at most 48 for the HAR-006 v2 corpus), so the flag stays off by default.
- The inspector duplicates a few composer constants: the 24-message selection, the 65,536-byte limit and the skill header. A change to any of them makes `tests/test_context_baseline_golden.py` (selection window, skill header) or the byte-boundary test in `tests/test_context_inspection.py` (65,536 included, 65,537 `source_byte_limit`) fail. At run time, the inspector reports MISMATCH only for an item that the change affects.
- C3 is conservative. An omitted item whose leading or trailing 256 characters also appear in an included item or in the conversation is reported as MISMATCH.

## Rollback

Do not pass `inspect_layers`, or revert the commit. No data, model, configuration, route or migration is involved.

## Validation

- `tests/test_context_baseline_golden.py` pins the SHA-256 of `(fitted, report)` for 78 cells under two deterministic fake counters. One counter adds a per-message overhead; the other merges tokens across message boundaries. The 78 cells are:
  - 3 strategies × 6 evidence cases × 2 skill settings × 2 client-system settings = 72 cells;
  - 6 variants: source contract, review contract, 12 pairs, an unpaired message, mandatory overflow and balanced/512.

  The digests were recorded on `f30a49f` before the inspector existed.
- `tests/test_context_inspection.py` covers:
  - with the flag off, the HTTP request sequence equals the digest pinned on HEAD;
  - with the flag on, only the `inspection` key is added;
  - the telescoping sum over all composable cells under both counters;
  - tampering returns MISMATCH: evidence, blocks, pairs, report counts, partition, reasons, system segments and a non-deterministic counter;
  - the trim-reason split;
  - evidence reasons, and that oversized bytes are never counted;
  - the byte boundary for each strategy under both counters: a 65,536-byte source is included, a 65,537-byte source is omitted as `source_byte_limit`, and both inspect COMPLETE;
  - positive skill, contract and client-system layers;
  - the budget identity, and the ceiling against brute force for fast, balanced, deep and unlimited × {None, 512};
  - schema 2 returns UNSUPPORTED;
  - counter errors and cancellation propagate;
  - the count bound;
  - logs carry no text;
  - control-literal counts.
- The native check is the HAR-006 v2 Window 1 (D1 flag invariance, D2 layer sum, D3 budget). It is not run yet and needs the owner's CORE authorization.
