# ADR-190: Opt-in source-bound working state across compactions

**Purpose:** Record HAR-009-C1, first slice. A deterministic structured working state, built only from user-marked lines, carries goals, constraints, decisions, open tasks and corrections across history reduction and across client-side window drops. It also flags and keeps newer pairs that may update a kept item. No LLM summary, model, default, context-size or storage change.

**Date:** 2026-11-11. **Status:** Implemented as an experimental opt-in and measured ([protocol](../HAR009_C1_WORKING_STATE_PROTOCOL.md), [result](../HAR009_C1_WORKING_STATE_RESULT.md)). Default adoption is not decided. Extends [ADR-187](187-opt-in-pinned-history-and-extractive-compaction.md) and [ADR-189](189-opt-in-token-budget-history-window.md); supersedes nothing.

## Context

- **What B2 left open.** The `token-budget` policy keeps marked rules under pressure. It also answered with the old value whenever a marked decision was later corrected without a marker ([B2 result](../HAR009_B2_TOKEN_BUDGET_RESULT.md)).
- **The request bound.** The API takes at most 256 messages per request. Before this change, the CLI with an explicit history policy therefore stopped at 128 pairs. Without a policy it keeps only the last 22 messages. Either way, anything the client dropped was gone.
- **The backlog item HAR-009-C1 asks for:**
  - a structured state (goals, constraints, decisions, work in progress, open items, uncertainty) with lineage and freshness;
  - automatic compaction with an output reserve;
  - carrying the state with recent context into the next window;
  - tests over several successive compactions;
  - a clear separation between model text and user facts;
  - no restoration of old approvals;
  - no LLM summary without its own measurement.

## Decision

1. **Opt-in policy fields.** `HistoryPolicy` gains:
   - `working_state: bool = false`;
   - `carried_state`: at most 64 items, returned by an earlier response;
   - `history_offset`: the number of earlier pairs the client has dropped, 0–1,000,000.

   `carried_state` and a non-zero offset require `working_state`. `working_state` is refused with `extractive-compact`, which already has its own capsule; combining the two is future work. Without `working_state`, every mode behaves exactly as before.
2. **Items come only from user lines.** A working-state item is a **line of a user message** that opens with a marker, optionally preceded by a `-` or `*` bullet and with an optional key in brackets: `Decision[db-region]: Warsaw` or `Decision [db-region]: Warsaw`. Matching runs on the case-folded NFC line. Matching ignores case and Unicode form (NFC/NFD); unusual capitals such as Turkish `İ` simply do not match. Kinds and markers:
   - `goal`: `goal`, `mục tiêu`
   - `constraint`: `rule`, `constraint`, `quy tắc`, `quy ước`, `ràng buộc`
   - `decision`: `decision`, `quyết định`
   - `todo`: `todo`, `việc cần làm`
   - `done`: `done`, `đã xong`
   - `note`: `important`, `remember`, `quan trọng`, `ghi nhớ`
   - `correction`: `correction`, `update`, `đính chính`, `cập nhật`

   Assistant text never becomes an item, so model statements are never recorded as user facts. The item text is kept verbatim (NFC) and never paraphrased or clipped. A marked line that cannot become an item is reported in `skipped_lines` with its pair number and a reason: `line_too_long` (over 500 characters), `invalid_key` (empty, or longer than 48 characters) or `malformed_marker_line` (for example `Rule:` with no text, or nested brackets).
3. **Lineage.** Every item records:
   - its kind and optional key;
   - its absolute pair number (`history_offset` + the local pair number);
   - the SHA-256 of its exact source pair;
   - its origin: `window` (re-derived from this request) or `carried` (from a pair the client has dropped).

   Carried items whose pair is still in the request are re-derived instead of trusted. Carried keys are case-folded and space-collapsed like parsed keys. Only parsed lines are NFC-normalised, so a client that rewrites keys in NFD would not supersede them; the CLI returns the server's own keys. A carried item that is already superseded, closed or dropped stays so. Carried items are client-supplied, untrusted data; their hashes cannot be re-verified once the pair is gone, and the receipt says so.
4. **Supersession by key (deterministic).** Items are applied in pair order:
   - A later item with the same key and a kind other than `done` or `todo` supersedes earlier `goal`, `constraint`, `decision`, `note` or `correction` items with that key.
   - A later `todo` supersedes an earlier `todo` with the same key.
   - A `done` with a key closes the open `todo` with that key.

   Unkeyed items are never superseded automatically; the prompt policy tells the model that newer items and newer dialogue override older ones.
5. **Freshness.** For each active item, newer pairs in the request whose text (user or assistant) shares at least 3 significant terms with the item are listed in `newer_mentions` (at most 3, newest first). Significant terms are lowercase words of at least 2 letters, excluding a fixed English and Vietnamese stopword list and the marker words. In `token-budget`, after the importance step, the newest mention of each active item is kept as a whole pair with reason `newer_related`. This is limited to 8 probes and to the soft target. A correction written without a marker can therefore survive next to the marked decision it corrects.
6. **Capsule.**
   - **Content:** active items and open todos, as `{"untrusted_working_state": …}` JSON in the current user message. A host policy line states that the state is user-authored history, not verified fact, and grants no approval, tool, write or memory authority.
   - **Budget:** the capsule is mandatory content. Reduction measures with it included, so it shares the soft target and the hard limit.
   - **Limits:** at most 64 active items and 32 KiB. When either limit is exceeded, active items are dropped, oldest `note` and `correction` items first, then the oldest of any kind, until both limits hold. Every dropped pair number is reported in `dropped_active` (the CLI prints it), and dropped items keep the status `dropped`. Unkeyed items cannot be superseded, so failing closed would leave a CLI session unusable forever.
   - **Evidence:** the evidence-first mandatory estimate includes the capsule.
7. **Carrying the state.**
   - **Receipt:** the full state, including superseded and closed items up to 64 (pruned oldest-inactive first), is returned in `history_policy.working_state` to the authenticated caller only. It is not logged; logs carry counts only. The receipt also reports the item counts, `newer_related` pairs, skipped lines, dropped items and carried items.
   - **Numbering:** selection, `retained_turns` and `evicted_turns` use the request's local pair numbers, while working-state items use absolute numbers. The CLI prints evicted pairs as absolute numbers.
   - **CLI:** `aevra chat --history-policy token-budget --working-state` sends the state back on every request. Without `--working-state` the CLI does not send the new fields, so an older server keeps accepting its requests. When the local history reaches the 256-message request bound, the CLI drops the oldest 32 pairs, raises `history_offset` and continues, instead of stopping. With pins configured, it keeps the previous behaviour and stops, because pin numbers would shift.

## Alternatives and consequences

- **Rejected alternatives:**
  - *LLM summary of evicted turns.* It can fabricate or omit facts, adds latency, and needs its own retention evaluation (HAR-009-C remainder).
  - *Server-side durable state.* It needs storage, ACL, retention and invalidation (HAR-009-D1).
  - *Semantic subject matching for supersession.* It cannot be inspected; explicit keys can.
  - *Failing closed above the limits.* This was the first implementation. The independent review showed that unkeyed items can never be retired, so one long pasted list would make every later request fail. Reported dropping replaced it.
- **Risks:**
  - Unmarked facts are still lost once their pairs leave the window.
  - The lexical freshness rule can keep an unrelated pair that shares terms, or miss a correction phrased with different words.
  - Carried state is client data: a client can edit it, which only affects its own context.
  - The capsule costs tokens on every request.

## Validation

- Software tests cover:
  - extraction (markers, keys, bullets, NFD, assistant lines ignored, long lines skipped);
  - supersession and todo closing;
  - freshness and `newer_related` selection;
  - carry, offset and dedupe across three successive window drops;
  - capsule limits and fail-closed errors;
  - the receipt and logs without text;
  - CLI carry and drop.
- The native measurement is the C1 protocol: the B2 stale cases with and without state, and multi-window conversations above the request bound.

## Rollback

Omit `working_state`. Nothing is stored server-side. Removing the feature is a code revert; no data, model, configuration or migration is involved.
