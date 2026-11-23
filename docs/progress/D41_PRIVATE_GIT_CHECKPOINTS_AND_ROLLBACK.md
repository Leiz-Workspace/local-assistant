# D41 private Git checkpoints and newly approved byte rollback

**Purpose:** Document durable bounded source history, truthful action journals and explicit fresh rollback consent without executing project Git hooks/configuration or resuming old approvals.

**Status:** PASS within the defined local fixture scope. **2269 full PASS/1554.97s,0SKIP,exit0**,912 related PASS/40.32s as a subset;97 new cases,24 evaluated Python files/161 described functions/classes,371 source/377 unique protected hashes. [Acceptance](../evidence/d41-checkpoint-acceptance.json), [full result](../evidence/d41-full-regression.json), [clean audit](../evidence/d41-final-post-audit.json), ADR-059/061. Earlier intentionally interrupted/failed checkpoints below remain historical evidence; no production action or general coding-agent release.

## Explicit local scope

Default-off `ASSISTANT_CHECKPOINT_ENABLED=1` requires live accepted workspace/approval/patch services and an explicit existing `ASSISTANT_CHECKPOINT_ROOT`. The root must be application-owned0700, nonsymlink and outside all registered workspace roots in either native ancestry direction. No implicit root creation or host project registration. Startup takes a private single-link0600 lock inode with nonblocking process lock; storage operations have nonqueued thread admission and refuse premature close. Join all owned operations before closing checkpoint storage, then invalidate approvals and close workspace dependencies.

Only this optional composition adds private source checkpoints; accepted standalone ephemeral D40 behavior stays available for its earlier local fixture contract and makes no durability claim. General coding-agent release must require durable composition before exposing project mutation. No database/Vault/Docker/migration/model/dependency change, model write tool or arbitrary public Git/checkpoint-creation command is introduced. All recorded approvals, edits and restores use disposable synthetic owners/files.

Each full D40 proposal captures original raw bytes/native source version and complete review SHA256. Before its pending approval is published, create a private Git repository containing fixed `source.bin` and canonical `metadata.json` objects, a tree and a commit. Metadata binds owner/workspace/proposal/path/root/parent/source identity, original/replacement hashes, eligible mode/group and exact review digest. Read back actual Git objects/tree/commit and independently check source/metadata SHA256 and object identities before fsynced record/journal publication. Never invoke Git in the user's existing repository, change its branch/index or execute its hooks/filters/configuration. A checkpoint covers one admitted file, not the entire repository.

Private Git uses the existing bubblewrap mechanism: new user/process/network namespaces, no capabilities, actual unprivileged application UID/GID, read-only trusted system runtime/empty template, only the pinned private repository writable through native descriptor-consuming mount options, no host home/workspace/Vault mounts, cleared env plus fixed safe Git options. Finite init/blob/tree/commit/read plumbing only; no transport, shell or model-selected executable/argument/path. Static Git system/global config, prompt, pager, hooks, attributes, signing, autocrlf and auto-GC policies apply inside the namespace. No unsandboxed fallback.

| Resource | Bound |
|---|---|
| Source | Existing D40<=8192 original/replacement raw bytes, UTF-8/no NUL |
| Metadata |8192 canonical UTF-8 bytes; private record/journal<=32768 bytes |
| Records |128 global count ceiling,32 per owner; incomplete reservations retained/accounted |
| Reservations |256KiB per checkpoint,16MiB global reservation ceiling; effective maximum64 under the byte cap |
| Native storage | Private files0600/directories0700, owner/single-link/device/hash checks; bounded64-entry/depth8 Git scan and256KiB allocated storage per checkpoint |
| Git resources |256MiB address space, CPU2s soft/3s hard,256KiB per file,32 FDs,16 processes, core0 |
| Parent supervision |5s per Git command/20s checkpoint stage, stdin<=16384/stdout<=65536/stderr<=4096 bytes, process-group kill and joined exit |

These are enforced policies, not measured memory/VRAM/throughput claims. Native storage deadlines remain cooperative around potentially blocked kernel I/O. No automatic history retirement, guessed orphan cleanup or Git GC. Capacity exhaustion prevents new proposals/source writes while keeping existing backups. Unsupported or unknown/incomplete private records fail closed for admission instead of disappearing from quota accounting.

## Journal and commit truth

The initial journal is ready and contains no grant/nonce/credential. Before a native workspace temporary file or approval consumption, verify the exact checkpoint/review again and durably publish applying intent. D40 still checks source/root/parent/prepared bytes and consumes the exact one-shot grant immediately before native rename. Rename remains the source commit point.

After joined native work and source-pin cleanup, attempt terminal journal publication with the actual NativePatch receipt, or failed when no commit was acknowledged. File/parent fsync and private atomic journal rename are real native operations. A pre-commit backup/intent failure keeps source bytes intact and cannot consume the grant through the native writer. If a journal syscall acknowledgement fails after source rename, retain `applied_checkpoint_uncertain` with applied=true rather than reporting an unapplied edit or retrying. Unknown native source outcomes remain unknown. Cleanup acknowledgement uncertainty from the native pin is included before terminal evidence is recorded. Cancellation attempts terminal persistence after joining and keeps storage alive until its worker finishes.

If private temporary-file identity was never acknowledged before an error/process loss, retain that entry; do not infer ownership from its `.journal-*` name. Owner history can show `unacknowledged_private_entry`. A later fresh source observation and fresh approval are separate from the old journal. There is no claim to recover every window between file creation, inode acknowledgement, rename and fsync, nor to prove hardware power-loss durability.

## Local HTTP review and rollback

All routes use the accepted local bearer/Origin policy, typed UUID scope, strict streamed16KiB JSON and private/no-store/nosniff responses. Historical source bytes are authorized before private Git content read. Unknown/foreign checkpoint responses are indistinguishable; listing filters foreign IDs. Default-off routes return unavailable without creating private roots/records.

| Method | Route suffix under `/api/v1/workspaces/{workspace}` | Behavior |
|---|---|---|
| GET | `/checkpoints` | Bounded own historical metadata/commit IDs, no recovered grants |
| GET | `/checkpoints/{checkpoint}` | Verified original source and historical journal; no current-source claim |
| GET | `/checkpoints/{checkpoint}/recovery` | Fresh bounded native current-hash observation only |
| POST | `/checkpoints/{checkpoint}/rollback` | Only expected_sha256 of current source; creates new full D40 proposal and pending approval |

Proposal path/restoration bytes come from the verified owner checkpoint; clients cannot supply replacement, root, mode, owner, command, old approval or action overrides. Require the same native workspace root as the historical checkpoint. The current source must still pass fresh D40 source-version/path/metadata checks. Rollback restores bytes while preserving current eligible metadata; it does not reset a branch, create/delete files, restore a whole repository or silently revert permissions.

The owner reviews the complete new diff using the existing CLI and explicitly types a second `APPROVE <new-request-uuid>`. Approval itself edits nothing. Apply uses the separate new proposal's exact one-shot grant. Old consumed/expired/restarted grants cannot authorize rollback. A changed current file/root/context needs a new proposal/review. Restoring does not delete its own pre-restore checkpoint, so the intermediate bytes also remain historical evidence.

Restart loses old in-memory proposals/approvals and never resumes an edit. Verified private history survives. Recovery returns observed_original, observed_replacement or observed_other against current stable bytes, root_changed or source_unavailable for missing/unsafe/unreadable/oversized targets. It always reports source_modified=false, action_taken=false, recovered_approval=false and causality_inferred=false. Matching bytes do not prove which process caused them; journal applying is not permission to finish an old edit. Observations describe the fresh read/final fence, not perpetual source immutability.

## Observed gate and remaining work

**Pre-FD-fix91 new PASS/9.44s**, including89 checkpoint cases and2 artifact-history cases; **712 related PASS/17.30s,0 SKIP,exit0**, including621 earlier cases.19 evaluated Python files/132 described functions/classes pass Ruff correctness/import/format.370 source files plus6 additional historical evidence targets are hash-frozen.The first2263 full was intentionally interrupted (419 confirmed pass markers, exit2), not accepted. Fixed-source new scope97 cases/full2269 and expanded worker regression remain pending.

Actual namespace resource/UID/env/host-file/network/write denial, fixed Git commit/raw readback, private root ancestry/lock/inode/hash/quota/restart, corrupt metadata/objects/journal and changed review gates pass. Controlled smaller quota, clocks/stage boundaries/faults are disclosed. Actual native journal file and post-rename directory-fsync errors preserve pre/post-source-commit truth. Cancellation joins constructor/capture/native/terminal-journal ownership before shutdown; native close uncertainty survives in durable receipts.

Actual Uvicorn/TCP performs checkpoint→full CLI review→explicit edit→new full rollback review→explicit restore with exact original bytes. Three real child SIGKILL cases cover acknowledged ready checkpoint, durable applying intent and committed source before terminal journal: locks release, old grants are absent after reopen, observations report original/replacement without causal inference or automatic mutation. This is controlled process termination at known boundaries, not machine power-loss or all uninterruptible syscall windows.

The first D38 public4/6 model score/failures and D40's additional private4/6 report remain unchanged. The D38 live test now stores each subsequent summary in its unique private trial directory and only updates `data/backups/d38-most-recent-trial.json`; it cannot overwrite an earlier summary or D40's legacy `d38-latest-core-observations.json` reference. Cases/model/scoring are unchanged; two artifact-only tests measure no model quality. Do not substitute a later measurement for the first score or treat model repair failures as all coding tasks passing.

Finish exact-source full regression and readonly data/Qdrant/security/model/config cleanup audit before marking D41 PASS or implementing D42. Disabling/draining the feature stops new work and retains checkpoints; restoration always requires a new explicit action. No production coding-agent release, real project rollback, cross-worker replication, arbitrary execution, hostile same-UID CAS or multi-file transaction is claimed.


## Required FD repair evidence

The independent parent-canary probe and related document-stdin probe are retained in [repair evidence](../evidence/d41-fd-authority-repair.json). Git setup uses consuming bind-fd/ro-bind-fd so original child directory descriptors cannot traverse outside namespace mounts. Shared document workers use one bounded readonly namespace input copy and trusted stdin bootstrap; actual proc/mount write/truncate/chmod attempts return EROFS. Existing private document algorithms and result contracts stay unchanged. Do not accept only namespace path/UID checks; validate FD-derived authority too. All corrected-source regression/full/data/config evidence must pass before D41 acceptance.

Final namespace scaffold is readonly after all mounts; only private Git repository remains writable. DOCX/XLSX metadata mounts are inserted before the final readonly remount. Two partial runs retained separately, neither a full PASS. Final corrected source freeze covers371 files/377 unique protected targets and24 evaluated Python files/161 described functions/classes. One related checkpoint911 PASS/1 FAIL/40.21s exposed the D33 test fixture mount-order dependency; its mount construction was corrected, unchanged NO_XDEV assertions now pass in the final912-case regression.

## Final acceptance

Corrected exact-source full completed2269 PASS/1554.97s,0SKIP,exit0 (wrapper1555.78s), log SHA256 `9c9934e0f85dd326ab1d766296300d9ecd9780e9c2be1d003d9bac25f0e4430e`. Final readonly audit exit0:V006, original owners/ACL/narrow grants/invoker triggers and agreed model/config/dependency/migration hashes intact; source/memory/quota/vector/probe/worker/advisory-lock residue zero. Original D38 score and D40 legacy trial unchanged; separate new CORE trial again4/6 with both failures retained. All preceding pending statements describe historical checkpoints; final D41 local acceptance is PASS. D42 NEXT.
