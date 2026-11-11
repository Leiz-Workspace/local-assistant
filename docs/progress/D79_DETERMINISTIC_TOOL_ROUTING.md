# D79 — Deterministic tool routing and existing approvals

**Purpose:** Describe verified owner-bound fixed routing and exact action approval composition.

**Status:** Independent local routing VERIFIED; product/manual gates remain open. [ADR119](../ADR/119-deterministic-routing-through-existing-action-approvals.md).

`HarnessToolRun` binds authenticated owner/workspace and explicit CORE outside model input. The fixed catalog includes the five original read-only workspace operations plus `patch.apply` and `checks.run`. Model envelopes cannot add scope, shell commands, budgets, callbacks, approval identifiers or review decisions. Strict action arguments contain only a canonical existing target UUID. Invalid envelopes count toward the8attempt limit too.

Existing services create complete proposals and explicit owner reviews. A separate trusted host method attaches an exact action/target approval reference; attachment does not approve pending, expired, rejected or wrong-scope records. Existing PatchService/CheckService verify and consume their original one-shot grants at execution. Local attachments are popped before attempting work and are never recovered from plan/checkpoint data. Router hooks retain argument hashes and decisions; existing service logs retain their original non-secret correlation identifiers. Raw bodies/review nonces are not added to logs.

D77 owns pre/post authorization, deadline, joined stop/cancellation, finite reply and sticky uncertain-write handling. Even an action denied by its underlying service is conservatively terminal/uncertain at this outer layer; original action receipts distinguish actual mutation. No retry or rollback inference. Close joins the route and read capability, then clears local references; the host separately closes shared action services.

**18new/221related PASS6.58s/0FAIL/0SKIP**, including actual fixture-approved atomic patch, follow-up native read, pending/rejected/foreign/wrong-target/wrong-action refusal, no implicit grants, no replay and actual existing pinned offline Ruff run with retained history. First test failure incorrectly demanded that existing approval correlation IDs disappear from all service logs; corrected to check the new router logs while retaining original audit behavior. No runtime guard weakened. Ruff PASS; original661source bytes unchanged.

No new HTTP route, production registration, deployment, permission or model choice. [Source/log receipts](../evidence/d79-deterministic-routing-verification.json). D80 profile/prompt version isolation is next.
