# D46 coding-agent evaluation: 7/10 functional repairs

**Purpose:** Publish the immutable first ten realistic bounded CORE repair outcomes, actual oracles/reviews/resources, failure review and current readiness limits.

**Status:** PASS for the defined local ten-case evidence gate:1344 related plus separately retained ten actual protocol cases PASS/0SKIP/exit0 and clean readonly audit. **Repair score:7/10**; two admitted candidates fail native assertions, one proposal is rejected by the response contract. Broad/unattended production coding quality is **not established**. [Acceptance](../evidence/d46-evaluation-acceptance.json), [first experiment](../evidence/d46-first-mvp-evaluation.json), [failure analysis](../evidence/d46-failure-analysis.json), [frozen protocol](D46_CODING_AGENT_MVP_EVALUATION_PLAN.md).

## First actual outcomes

| Frozen case | Repair outcome | Visible exit | Held-out exit | Model call (s) | Full candidate |
|---|---|---|---|---|---|
| timeout-units | FUNCTIONAL_PASS | 0 | 0 | 3.729 | [untrusted source](../../data/backups/d46-coding-case-timeout-units-7dfff62b084a4f59a4deaf320b718c9a/candidate.py) |
| token-masking | FUNCTIONAL_FAIL | 1 | 1 | 3.549 | [untrusted source](../../data/backups/d46-coding-case-token-masking-cb86c201c80849c69a129fa96d99d205/candidate.py) |
| api-path-join | FUNCTIONAL_PASS | 0 | 0 | 3.022 | [untrusted source](../../data/backups/d46-coding-case-api-path-join-9663b679d7df417ea5dcefba9767b495/candidate.py) |
| stable-id-order | FUNCTIONAL_PASS | 0 | 0 | 3.091 | [untrusted source](../../data/backups/d46-coding-case-stable-id-order-1f6cb3308ed1461b9dcc0f7440acd7b9/candidate.py) |
| partial-batch-tail | FUNCTIONAL_PASS | 0 | 0 | 3.071 | [untrusted source](../../data/backups/d46-coding-case-partial-batch-tail-060a74124f4549ceb4b534151bf4dc8b/candidate.py) |
| fractional-quota-percent | FUNCTIONAL_PASS | 0 | 0 | 3.152 | [untrusted source](../../data/backups/d46-coding-case-fractional-quota-percent-a57813049f854edcb7895369e06339e8/candidate.py) |
| header-redaction-case | FUNCTIONAL_PASS | 0 | 0 | 3.136 | [untrusted source](../../data/backups/d46-coding-case-header-redaction-case-3dd75e6432dd490aa395bb48d01aad36/candidate.py) |
| explicit-boolean-text | PROPOSAL_FAILED | Not run | Not run | 4.694 | Not admitted |
| capped-retry-arithmetic | FUNCTIONAL_FAIL | 0 | 1 | 3.099 | [untrusted source](../../data/backups/d46-coding-case-capped-retry-arithmetic-437098341ada4e549c8dddec4407c5ba/candidate.py) |
| owner-live-filter | FUNCTIONAL_PASS | 0 | 0 | 3.216 | [untrusted source](../../data/backups/d46-coding-case-owner-live-filter-c3e06c6f128b4e2ca69d6980b868c7a8/candidate.py) |

Every attempt is retained once. No plan trimming, schema relaxation, repeated generation or failed-score replacement. The second native suite was predeclared and separately approved against the same applied candidate; it is not a repair retry. Input/test bytes and external fixture canaries remain unchanged; only nine explicitly reviewed disposable target edits occur.27 typed fixture approvals and18 native checks are authorized test operations, with no production action.

## Failure review

- **Token masking:** loses masked padding for a visible suffix and retains token bytes when the whole token must be masked. Native visible and held-out suites fail; only synthetic fixture strings were involved.
- **Boolean parsing:** returns six plan entries while the existing schema permits one to five. Server rejects before patch/check publication;0 approvals/native runs. Its replacement function was not executed or scored correct.
- **Retry arithmetic:** passes the supplied nonnegative examples but misses the declared negative-attempt boundary:actual1.0 versus expected2. The held-out native suite catches this. This pure fixture enables no production retry feature.

[CODE-EVAL-002](CODING_AGENT_BACKLOG.md) assesses P1 follow-up before broader coding/quality promotion:format adherence, edge-case specification and explicit feedback budgets on fresh predeclared data. No model/routing/policy change is implemented by the scorecard; future agreed-model adoption still requires benchmark/performance/resources/migration/rollback and owner approval.

## Evidence, resources and scope

Ten actual one-attempt CORE cases complete in46.41s at the pytest protocol level. Model application-port wall duration:min3.021945s/median3.143810s/max4.694445s. Existing CORE/fast/temperature0/max_tokens2048/generation wall60s remains; native stdlib unittest capsules retain all D42 limits and separate approvals. These are descriptive timings on authored cases, not TTFT/TPS/SLO or statistical model superiority. Peak RSS/VRAM and actual token usage are unmeasured.

Ten reference/buggy oracle pairs were validated natively before inference:reference passes both complete suites and buggy fails. Model context includes only buggy target and visible tests; the held-out module/example records are not supplied. SHA-bound actual prompts match frozen expectations. The fixture review preserves the single API/logging header/audit call and permits only predeclared pure value operations; it is not universal source sanitization. Model candidates never execute on the host. Native generic quality_evaluated remains false; the host score here applies only to fixed functional oracles.

Six evaluated Python modules/22 described functions/classes pass isolated Ruff correctness/import/format.50 new cases;1344 related PASS/114.22s plus separate ten actual protocol cases,0SKIP/exit0; not one1354 invocation.427 sources/687 unique source-protected hashes match and readonly audit passes.2713 collected is not a fresh full. Production code remains byte-identical to the historical D44 full2622 baseline.

First experiment private artifact `data/backups/d46-evaluation-ddadfe69-7197-44fd-b637-1aa8b678e4d9/summary.json`, SHA256 `594ffde1b8a37630e21571d28a333e60fe1079f6c04df142fc3746609fd45d03`; original model attempts/raw/native outputs/full untrusted candidates/typed-review displays remain exclusive private artifacts. Pre-inference freeze `81afed398e21e0ac6e0714d45ec2dd29335995d14636e2ceac6601a137af360f`, corpus `63e0a05b2b6f1a9d3d85210b09931d74d015ce6f53dfeb27f66c2936b74849d4`; related freeze `a04877d88456ecdf908ff41d255f9ced06ca4f036f834aeb11ac38f2eabf88fe`, log `55a9f81a4d3d0e4e1587aff70c0a42ab65f276007429253b86b607ff579d0e5f`.

[Readonly audit](../evidence/d46-final-post-audit.json) confirms V006, zero source/memory/quota/vector/probe/worker/native/advisory-lock/app/pending inventories and original ACL/owner/narrow-grant/invoker-trigger properties. Agreed model/config/dependency/migration/data bytes, D44 full/both interrupted predecessors and original D45/D43/D38 first scores/failures remain unchanged. Existing CORE stays healthy/running; production flags/actions remain off/unapproved. Initial test-harness collection error was corrected before any model measurement and retained separately.

Complete evaluated seven-file archive `data/backups/d46-evaluated-full-files.zip`, SHA256 `f4eefa8a76b6c1791d60db728b3310bb0150bfe1543e4e3693ae124d688c9dbb`, CRC/exact bytes verified. Complete committed versions are retained privately as `data/backups/d46-complete-full-files.zip`. Existing process-local/single-target/fixed-runtime/trusted-readonly-OS/independent-component/TCP-disconnect/cooperating-writer/crash/source-freshness limitations remain. D46 evidence gate completes with the first7/10 score and assessed quality debt; D47 is next.
