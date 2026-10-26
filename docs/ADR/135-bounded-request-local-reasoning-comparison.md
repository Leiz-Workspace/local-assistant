# ADR-135 — Bounded request-local reasoning comparison

**Purpose:** Assess whether explicit bounded thinking improves fresh D14 factual answers without changing agreed models or default behavior.

Date: 2026-10-26. Status: Accepted for one isolated comparative diagnostic within the owner's request “Tìm cách đi sao lại fail ?”. No model replacement, production adoption or original-score update.

## Evidence and hypothesis

After the format/parser fixes, the original CORE wire has 11 incorrect answers and UNRESTRICTED has 12. CORE's failures include two reasoning, five Python and four exact-source/label cases; UNRESTRICTED includes arithmetic/Python, source-policy booleans and labels. These are not missing JSON wrappers. Both original requests explicitly disable thinking and often produce only 14–46 answer tokens. This is an observed configuration, **not proof that disabled thinking caused the errors**.

The pinned local runtime's `tools/server/server-common.cpp` accepts a boolean `chat_template_kwargs.enable_thinking` overriding the server default, `reasoning_format=deepseek`, and `reasoning_budget_tokens`. Its README documents request-local template parameters and separated reasoning. Existing defaults can stay unchanged while a separate research adapter compares conditions. Native nonempty reasoning must actually be observed before claiming the condition was exercised.

## Decision and assessment

D14-SEMANTIC-001 is P1 before quality promotion. Dependencies: the unchanged two original GGUFs/projectors/runtime/templates, strict structural adapter, complete retained failures and trusted arithmetic/Python references. Effort: one finite paired diagnostic, followed only by a separately frozen fresh full validation if justified. Risks: token-budget/latency cost, forced reasoning truncation, unnoticed unsupported condition, prompt clarity being confused with reasoning gains, selected-case bias, output/reference leakage and false generalization from twelve text cases.

Run exactly twelve newly authored text questions per profile in direct and thinking conditions: at most 48 first generations, two sequential original owned GPU workers, no retry. Both conditions receive identical questions/system/schema, temperature0, cache disabled and max1024 tokens. Direct has thinkingFalse/budget0; thinking has thinkingTrue/budget512. Parse native final content independently from reasoning; preserve all native bytes and first failures. The inference adapter never receives reference values or executes generated Python. Clarify atomic-label requirements identically in both conditions, without encoding answer labels in grammar.

Keep configured reasoningoff/context32K/GPU99/thread2/batch512/ubatch128 and original resource guards. Only these owned-port research requests override thinking; no YAML/default/API/shared-adapter changes. Request timeout90s/campaign2400s. Require actual condition evidence, exact paired identities/counts, five distinct provenance checks, retired exit0/no guard and restored baseline. Full thinking text correctness12/12 per profile is required even to consider a larger fresh validation; it does not close original D14 or approve production. Compare time/token cost and direct results before proposing use.

## Migration and rollback

No production migration or new model/download/dependency. Research code is under benchmarks and is unregistered. Rollback omits the trial adapter and retires only owned workers. Preserve all original results and trial attempts even when this hypothesis fails. Future changes require their own assessed protocol; do not tune against these observed answers or silently relax42/42 full criteria.
