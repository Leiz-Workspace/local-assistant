# Harness product capability backlog

**Mục đích:** Theo dõi khoảng trống CLI/UI/context/skill/media generation, đánh giá dependency, effort và rủi ro trước khi triển khai.

**Cập nhật:** 2026-11-11. Owner đã yêu cầu triển khai; **v1 opt-in đã có code**, phạm vi/kiểm chứng theo [runbook](../HARNESS_CLI_DESKTOP_RUNBOOK.md), [ADR-181](../ADR/181-checkout-cli-desktop-and-readonly-specialist-runs.md). Không có mục nào được tự đóng toàn bộ AC chỉ vì v1 chạy được. [Thiết kế đầy đủ](../HARNESS_PRODUCT_DESIGN.md), [ADR-180](../ADR/180-proposed-unified-harness-product-surface.md).

## Trạng thái implementation hiện tại

| Mục | Trạng thái so với AC đầy đủ |
|---|---|
| HAR-001 | PARTIAL: typed contracts/state/events; optional signed metadata history đã kiểm, chưa durable execution/approval integration. |
| HAR-002 | PARTIAL: đúng pin, archive/file digests, actual browser UI/HTTP compatibility; full request inventory/advanced settings/PWA còn giới hạn. |
| HAR-003 | AEVRA CLI VERIFIED / full task PARTIAL: command chính `aevra`, alias `la`, shared dragon logo, auth/chat/run/context/skill/UI/native-desktop/job controls; chưa đầy đủ admin/approval commands. |
| HAR-004 | READONLY + METADATA ARCHIVE VERIFIED / PARTIAL: bốn host-specified reads + một CORE completion, cancel/join/ACL; metadata qua restart đã kiểm, active→interrupted không replay. Chưa model-selected loop/durable execution/write reconciliation. |
| HAR-005 | WEB + NATIVE LINUX SLICE VERIFIED / PARTIAL: shared Aevra identity, pinned chat UI, real SSE/cookie boundary, independent GTK/WebKit window and owned backend lifecycle. [Guide](../AEVRA_DESKTOP.md). Chưa PostgreSQL history sync/clean-machine native installer/full device acceptance. |
| HAR-006 | V1 + NATIVE PACKING VERIFIED / PARTIAL: ba priorities và actual tokenizer probe 24,131-token history + source collision; evidence-first giữ source/bỏ history, hai mode khác giữ history/bỏ source. [Result](../HAR006_NATIVE_CONTEXT_PACKING_RESULT.md). Chưa semantic quality/peak resources/full layered allocation. |
| HAR-007 | PROCESS-LOCAL SLICE VERIFIED / PARTIAL: review/install/show/remove, exact hash binding và revoke; chưa durable catalog hoặc executable/markdown skill packages. |
| HAR-008 | V1 MEASUREMENT COMPLETE / PROMOTION NOT QUALIFIED: 24/24 native attempts, strict baseline 5/12, skill 6/12; một paired win, một JSON regression và quote/null-contract failures giữ nguyên. [V1 result](../HAR008_PAIRED_EVALUATION_RESULT.md) giữ nguyên. HAR-008-R1 mechanics VERIFIED theo [fresh R3 result](../HAR008_OUTPUT_CONTRACT_RESULT.md): text 8/12 mỗi nhóm, constrained 12/12 mỗi nhóm; không có skill gain, full HAR-008 vẫn PARTIAL/NOT_QUALIFIED. [Q2 maintenance](../HAR008_Q2_MAINTENANCE_RESULT.md) đã đo 96 calls, constrained21/24→23/24, semantic/localization failures giữ nguyên; L1 bounded mechanics verified theo [result](../HAR008_L1_REVIEW_PAIR_RESULT.md), semantic adoption NOT_QUALIFIED. Q3 finite semantic measurement complete, all groups0/5 complete known-defect proofs; Q4 deferred theo ưu tiên context mới của owner. |
| HAR-009 | EXPERIMENTAL MECHANICS VERIFIED / PARTIAL: pin-aware window, verbatim history extracts, owner-private RAM archive/explicit recall/delete đã có CLI/API và tokenizer panel. [Guide](../CONTEXT_MANAGEMENT_STRATEGIES.md), [ADR-187](../ADR/187-opt-in-pinned-history-and-extractive-compaction.md). Chưa semantic/resource adoption, LLM summary, tool/task-state compaction, layered consented memory hoặc durable offload. |
| HAR-010 | SOFTWARE SLICE VERIFIED / PARTIAL: ports/jobs/ACL/cancel/digest/ephemeral artifacts qua synthetic adapter tests; chưa native media validation/durable storage/resource admission. |
| HAR-011 / HAR-013 | METADATA SCREENING ONLY, chưa chọn/tải/chạy model; [candidate notes](../GENERATION_CANDIDATE_SCREENING.md). |
| HAR-012 / HAR-014 | NOT IMPLEMENTED: production generation adapters absent; API/CLI báo unavailable, không sinh placeholder hoặc fallback. |
| HAR-015 | PARTIAL: Aevra editable packaging, independent Linux GTK/WebKit host, installed icon/launcher, software + actual native synthetic-stream smoke; chưa fully bundled/clean-machine installers, Windows/macOS, full regression/release acceptance. |
| HAR-016 | AEVRA BRAND + NATIVE HOST VERIFIED: supplied white dragon shared by CLI/web/desktop, original assets preserved, no browser fallback; [ADR-188](../ADR/188-aevra-brand-and-native-webkit-desktop.md). Broader packaging/UX gates remain open. |

Lượt software mới: 209 PASS trong 2.38 s; invocation riêng auth/stateless/presets 50 PASS trong 0.80 s; không gộp thành full suite. Model/provider/runtime config/DB/Vault/Qdrant cũ không đổi. D87 cũ chỉ còn là reference cho source scope cũ.

**Follow-up 2026-11-10:** [Metadata history](../HARNESS_METADATA_HISTORY.md), [ADR-182](../ADR/182-opt-in-signed-harness-metadata-history.md): final combined related **294 PASS, 3.80 s**, có actual process-loss recovery và actual separate-process metadata roundtrip của một CORE run. Default vẫn memory-only; raw results/skill grants không được lưu/phục hồi. Primary desktop 7090 không restart; probe 7092 đã dừng. Không cộng 294 với các invocation cũ hoặc gọi đây là full regression/model-quality PASS.

**Follow-up v1.2:** [ADR-183](../ADR/183-opt-in-source-bound-json-output-contract.md), opt-in `source-value-quote-v1`; 323 related PASS/3.89s, 48 fresh R3 native calls và 24 independent receipt/provenance checks. R1 dừng do envelope integration; R2 schema gửi sai wrapper nên không chứng minh schema enforcement, cả hai giữ nguyên. Không tự bật mặc định, không đổi model; primary desktop giữ process cũ. HAR-008-R1 đóng riêng remediation mechanics, HAR-008-Q2 tiếp theo.

**Follow-up v1.3:** [Q2 result](../HAR008_Q2_MAINTENANCE_RESULT.md): MEASUREMENT COMPLETE, 24 maintenance cases/96 first calls, text11/24 mỗi nhóm, constrained21/24 baseline/23/24 skill. All48 schema/catalog valid, nhưng bốn gold errors giữ nguyên. Sampled CORE RSS9.55GiB/GPU allocation7.83GiB; tám warm streaming timing replays, không phải task-API TTFT. 349 related PASS/4.07s. HAR-008-L1 là task tiếp theo; không đóng broad qualification hoặc đổi model.

**Follow-up v1.4 — 2026-11-11:** [L1 result](../HAR008_L1_REVIEW_PAIR_RESULT.md): explicit target/range/duplicate/const-pair enforcement, 72/72 bound replies mechanically valid across48+72first quality calls. First value-first baseline regressed versus generic; quote-first did not consistently improve the fresh six-arm cohort. All exact scores, false positives and first-source snapshot retained; no automatic adoption/default change.389 related PASS/4.63s. L1 implementation/measurement slice complete, semantic gate remains open; HAR-008-Q3 NEXT.

**Follow-up v1.5 — 2026-11-11:** [Q3 result](../HAR008_Q3_SEMANTIC_RESULT.md):48native-only prototype calls, trusted finite registered probes,24 shared-candidate checks. Overall single6/12→checked5/12 baseline,5/12→6/12 skill, nhưng **0/5 complete defect proofs ở mọi nhóm**. Tự kiểm tra không qualified để activate; source-valid/type/category/title không thay phản ví dụ đúng.407 related PASS/4.50s; không production/model/default change. Q4 evidence-assisted design NEXT; giữ all first results và semantic gate mở. *(Ghi chú 2026-11-11: Q4 sau đó được chuyển sang DEFERRED theo ưu tiên context của chủ dự án; xem dòng HAR-008-Q4.)*

## 1. Quy tắc xếp lịch

P0 = cần cho boundary/surface thống nhất; P1 = cần trước khi gọi là specialist harness sử dụng được; P2 = mở rộng sau baseline; P3 = nghiên cứu tốn tài nguyên. Effort là **ước lượng engineer-days**, không là ngày roadmap hoặc lịch cam kết; chưa gồm chờ owner, tải model hay benchmark dài.

Đề xuất phase “Product harness” sau/độc lập phần chuẩn bị của release hiện tại, không tái sử dụng D91/D92/D93 đã có trong roadmap. Mã HAR-* là định danh chính; chỉ gán development-day mới khi dependency/ADR được duyệt. Không tự nhảy milestone, đổi AC hoặc tuyên bố dự án đã release.

## 2. Backlog đã đánh giá

| ID / task | Ưu tiên / effort | Dependency | Rủi ro chính |
|---|---|---|---|
| HAR-001 — Control-plane contract, task state và authority | P0 / 2–3 ngày | ADR-180 review; ADR-115–119, auth/workspace hiện có | Client/model tự cấp quyền; duplicate writes; state drift |
| HAR-002 — Pinned llama-ui compatibility spike | P0 / 2–4 ngày | HAR-001; pin/license và API inventory | Native `/tools`/MCP/model download bypass; API drift; browser storage lệch server |
| HAR-003 — CLI v1 status/auth/chat/run inspection | P0 / 3–5 ngày | HAR-001; existing API và credentials provider | Token lộ argv/log; lệnh thiết kế bị tưởng là đã chạy được |
| HAR-004 — Bounded task coordinator, event/cancel/reconcile | P0 / 4–7 ngày | HAR-001, HAR-003; planner/hooks/checkpoints | Automatic retries, orphan workers, approval replay, persistence mơ hồ |
| HAR-005 — llama-ui product chat integration | P1 / 4–7 ngày | HAR-002, HAR-004; separate browser-auth boundary | CSRF/Origin, buffer giả SSE, partial message thành completed, duplicate history |
| HAR-006 — Deterministic context composer và inspector | P1 / 3–5 ngày | HAR-001, HAR-004; tokenizer/presets, RAG ACL | Bỏ constraint/citation, stale facts, prompt injection, vượt RAM/VRAM |
| HAR-007 — Skill lifecycle CLI và task instruction binder | P1 / 3–5 ngày | HAR-003, HAR-004, HAR-006; exact v1 manifest trust | Skill tự install/escalate; prompt/config drift; hồi sinh grant sau restart |
| HAR-008 — Specialist task benchmark và workflow packs | P1 / 2–4 ngày + đo | HAR-007; approved unchanged CORE; frozen held-out tasks | Overfit, tự chấm là independent, gọi pytest PASS là năng lực model |
| HAR-008-Q2 — Broader specialist semantic/resource evaluation | P1 / 2–4 ngày chuẩn bị + đo | HAR-008-R1 verified; cùng CORE/skill; protocol/oracles mới trước inference | Same-author bias, saturation/overfit, valid quote nhưng sai nghĩa, long-context omission, peak-resource drift |
| HAR-008-L1 — Bind review target/line/quote before generation | P1 / 1–2 ngày + đo | Q2 first outcomes frozen; explicit target read snapshot; new ADR/opt-in contract and fresh corpus | Wrong target authority, duplicate lines/multifile ambiguity, schema size, valid localization still wrong reasoning; preserve generic numeric answers |
| HAR-008-Q3 — Semantic review rubric and verification workflow | P1 / 2–4 ngày chuẩn bị + đo | L1 immutable first outcomes; fresh blinded cases; admissible-location/claim/counterexample protocol; ADR before multi-call/budget/schema changes | Exact-line bias, false positives, model self-review mistaken for independent proof, added latency/tokens, source-injection authority drift; unchanged approved CORE/skills by default |
| HAR-008-Q4 — Observation-assisted semantic reviewer | P1 / 2–4 ngày chuẩn bị + đo | Q3 immutable finite tables/errors; ADR and fixed source/type/probe receipt contract; fresh cohort with expected/verdict labels withheld | Tool evidence mistaken for gold/authority, registered templates generalized to arbitrary code, false proofs, source execution escalation, added latency/token cost; keep approved model |
| HAR-009 — Compaction, retrieval/tool packing, consented memory | P1 theo yêu cầu owner / 4–7 ngày + đo phần còn lại | HAR-006 baseline; source/artifact references, memory consent | Lossy summary, stale evidence, secret leak, compaction phục hồi approval |
| HAR-009-A — Pinned window/extractive history/ephemeral recall | P1 / MECHANICS VERIFIED 2026-11-11 | HAR-006, current auth/CLI/tokenizer; ADR-187 | Lexical omission, short-context overhead, RAM quotas/expiry; experimental opt-in only |
| HAR-009-B — Frozen paired retention/resource evaluation | P1 / MEASURED 2026-11-11 (B1 [kết quả](../HAR009_B1_RETENTION_RESULT.md), B2 [kết quả](../HAR009_B2_TOKEN_BUDGET_RESULT.md)) | A; frozen hidden facts/constraints/citations/contradictions; native telemetry | False factual confidence, benchmark leakage; need latency/TTFT/peak RAM/VRAM before adoption |
| HAR-009-C — LLM summary, RAG layers and consented memory | P2 / PENDING, 4–7 ngày + đo; **LLM summary: DESIGN PROPOSED 2026-11-11** ([ADR-192](../ADR/192-proposed-opt-in-llm-summary-of-evicted-history.md), [protocol nháp](../HAR009_C_SUMMARY_PROTOCOL_DRAFT.md): tóm tắt opt-in các cặp bị loại bằng CORE đã duyệt, mỗi mục phải trích nguyên văn và được bộ kiểm tra tất định xác minh; triển khai sau khi ADR được review) | B; existing memory consent/ACL/freshness; ADR before integration | Hallucinated summary, stale memory, secret/approval promotion; no new model implied |
| HAR-009-D — Durable offload, tool/task state and UI controls | P2 / PENDING, 3–5 ngày + đo | A/B, artifact ACL/retention/invalidation and UI compatibility | Recovery of stale approvals, disk privacy/quotas and context drift; separate adoption gate |
| HAR-010 — Common generation job/asset contracts | P2 / 3–5 ngày | HAR-004; artifact ACL/quotas, scheduler design | Disk/VRAM exhaustion, incomplete assets, unsafe output paths |
| HAR-011 — Image generation candidate evaluation | P2 / 2–3 ngày chuẩn bị + đo riêng | HAR-010; assessed candidates/rights/resource plan; model download approval | Model chưa duyệt, chất lượng không đạt, phá CORE residency |
| HAR-012 — Optional image generation integration | P2 / 4–7 ngày | HAR-011 benchmark + explicit adoption approval | Cancel/OOM cleanup, reproducibility, cold/warm latency, missing rollback |
| HAR-013 — Video generation feasibility/evaluation | P3 / 3–5 ngày chuẩn bị + đo riêng | HAR-010; image scheduling findings; separate model/resource approval | VRAM/disk/latency cao; video understanding bị nhầm là synthesis |
| HAR-014 — Optional video generation integration | P3 / 5–10 ngày | HAR-013 benchmark + explicit adoption approval | Long jobs/restart, partial files/audio drift, quotas và restore |
| HAR-015 — Packaging, end-to-end quality và operator guide | P1 / 3–5 ngày baseline | HAR-003–008; media chỉ khi được chọn vào release scope | Release sớm, CLI/UI protocol mismatch, thiếu install/rollback path |
| HAR-016 — Aevra brand and independent native Linux desktop | P1 / IMPLEMENTED AND VERIFIED 2026-11-11 | Owner request; current auth/pinned UI, installed GTK/WebKit; ADR-188 | Device-history privacy, unavailable OS dependencies, lifecycle ownership; no model changes |
| HAR-016-B — Native distribution/clean-machine and UX qualification | P2 / PENDING, 3–5 ngày + matrix testing; **DESIGN PROPOSED 2026-11-11** ([thiết kế](../AEVRA_LINUX_DISTRIBUTION_DESIGN.md): khuyến nghị venv uv + desktop entry, bảng kê phụ thuộc/giấy phép, kế hoạch máy sạch, 11 quyết định của chủ dự án; R1 đã sửa: giấy phép llama.cpp nằm trong package nên `ui prepare` chạy được trên checkout sạch) | HAR-016, OS dependency/license inventory, installers/update/rollback design | Checkout-relative resources, OS variations, accessibility, resource footprints and data migration; no unsupported cross-platform claim |

Thứ tự v1: HAR-001 → HAR-002/HAR-003 → HAR-004 → HAR-005/HAR-006 → HAR-007 → HAR-008/HAR-015. Context nâng cao và media là nhánh tiếp theo; không bắt release baseline phải có sinh video. Dấu `/` mô tả nhánh có thể độc lập sau dependency, không cấp quyền triển khai tất cả cùng lúc.

## 3. Acceptance Criteria

### HAR-001 — Contracts

- Versioned schemas cho run/event/skill/artifact/approval; owner/workspace bind bởi host, không nhận quyền từ model.
- State machine, event ordering, budget và uncertain-write reconciliation có ví dụ thành công/lỗi/cancel/restart. Chốt persistence scope và migration/rollback trước code storage.
- Compatibility matrix API/CLI/UI; giữ nguyên CORE-only harness, finite tools và action-specific one-shot approvals.

### HAR-002 và HAR-005 — Chat UI

- HAR-002 ghi build/source/license pin, actual browser request inventory và mapping toàn bộ API được UI dùng. Đo base-path/absolute-URL behavior thay vì giả định hỗ trợ proxy.
- HAR-005 chạy UI upstream qua app gateway; auth/CSRF/ACL/expiry/revoke, message persistence và real SSE được kiểm chứng từ browser.
- Unsupported native tools/MCP/model downloads/router/cors-proxy/sandbox bị chặn cả UI và direct requests; không có token trong URL/localStorage, request không thoát sang native/remote authority.
- Kiểm cancel/disconnect/reload, partial/final/error, exact model/preset mapping. Branch/import/export/resume chỉ enabled khi có server contract và tests; không có thì hiển thị unsupported.

### HAR-003 và HAR-004 — CLI và run loop

- CLI được đóng gói, `uv run la --help`, doctor/status/chat và JSON/exit contracts hoạt động; read-only startup không tạo side effect.
- Chạy một readonly task qua các khối có sẵn; owner/workspace isolation và denied action có test. Approve write chỉ qua action contract hiện có, không qua skill/model text.
- Event stream/cancel/deadline/attempt caps rõ; terminal state/receipts giữ được. Crash/resume không retry ambiguous write hoặc hồi sinh approvals; owned workers được join.
- Secret/prompt/source redaction và CLI SIGINT được kiểm tra; logs không phá machine-readable stdout.

### HAR-006 và HAR-009 — Context

- HAR-006 có report từng layer/token/source/omission; output/thinking/reserve theo preset, count bằng đúng tokenizer/template; whole-turn baseline không đổi.
- Các ca mandatory overflow/stale evidence/source injection/oversized tools/owner memory isolation đều fail rõ hoặc giữ đúng constraint, không silent truncation.
- HAR-009 chỉ bật compaction sau paired frozen benchmark: constraint/fact/citation retention, latency/TTFT/peak RAM/VRAM và failure cases; summary có lineage, invalidation, truy xuất nguồn và rollback.
- Memory injection cần consent và explicit inspection/disable. Không tự tăng context, đổi runtime precision/model hoặc ghi lại consent.

### HAR-007 và HAR-008 — Skill

- Review exact raw hash/version/permissions → explicit trust → install → bind task → authorize từng tool → revoke. Thay một byte/quyền/version phải review lại.
- Instructions thực sự vào prompt có budget; ghi digest và binder version, không log body. Catalog durable không phục hồi quyền process-local sau restart.
- Có end-to-end `source-reader` và `repo-review`, schema-negative/injection/revocation/expiry/cross-owner tests; v1 vẫn readonly, không shell/network/script/package install.
- HAR-008 so cùng model/preset/corpus giữa baseline và skill, oracle đóng băng trước chạy; báo first outcomes, uncertainty và resource/latency. Nếu không có gain thì giữ NOT QUALIFIED, không tự chọn model khác.

### HAR-008 follow-up gates

- HAR-008-R1: bounded JSON/quote/null remediation **VERIFIED**, default-off. R3 48/48 first outcomes, constrained 12/12 mỗi nhóm; đây là mechanics + controlled semantics panel, không đóng specialist qualification. R1/R2 và original 5/12–6/12 giữ nguyên; không tự đổi skill/model hoặc hạ AC.
- HAR-008-Q2: **BOUNDED MEASUREMENT COMPLETE / BROAD PROMOTION NOT_QUALIFIED**, [protocol/result](../HAR008_Q2_MAINTENANCE_RESULT.md). 96 first calls và 104 native calls tổng gồm tám unscored timing replays; 48 constrained provenance checks, 637+58 resource samples. Fixed author-controlled maintenance/caller/unsupported/long-source oracles, không human-independent hay actual user-repository findings. Source-valid JSON còn sai nghĩa/số dòng; resource samples không absolute peaks hoặc deployment SLO. Giữ toàn bộ first errors và model/defaults.
- HAR-008-L1: **IMPLEMENTED / BOUNDED MECHANICS VERIFIED / SEMANTIC ADOPTION NOT_QUALIFIED**, [result](../HAR008_L1_REVIEW_PAIR_RESULT.md), [ADR-185](../ADR/185-opt-in-target-bound-review-line-quote-contract.md). Target/range/snapshot validation and independent pair checks, both value-first and quote-first explicit research modes; defaults/generic answers unchanged. All72 bound pairs valid, but first48 and fresh72-call scores show semantic regressions/false positives and no consistent ordering advantage. Keep every first outcome, no post-output correction/retry or automatic adoption.
- HAR-008-Q3: **BOUNDED NATIVE PROTOTYPE MEASURED / SEMANTIC ADOPTION NOT_QUALIFIED**, [result](../HAR008_Q3_SEMANTIC_RESULT.md), [ADR-186](../ADR/186-native-only-finite-semantic-review-prototype.md). Registered trusted finite operations, exact source binding, predeclared alternative locations and typed counterexample grading; no snippet/model execution.48first calls/24shared checks, all groups0/5 complete known-defect proofs. Initial overall6/12 baseline/5/12 skill versus checked5/12/6/12, no consistent self-check benefit; ungraded titles and same-author references are explicit limits. Product remains single-completion/default unchanged.
- HAR-008-Q4: **DEFERRED / NOT IMPLEMENTED** under the owner’s current context priority; retained quality gate stays open. Design fixed approved source/type/probe observation receipts to ground the reviewer, preserving hidden expected/verdict gold and first draws. Registered-template support must reject outside its exact source domain, never execute arbitrary source/model code or expand tool authority. ADR/resource/latency/permission assessment and fresh paired evaluation before any tool/workflow activation; no model/preset/skill/default changes inferred from Q3.

### HAR-010 đến HAR-014 — Image/video generation

- HAR-010 chứng minh queued/running/completed/failed/cancelled/interrupted lifecycle bằng fake adapter; input/asset ACL, disk/size/time quotas, worker cleanup và digest provenance.
- HAR-011/HAR-013 lập candidate matrix, quality corpus, licenses, download sizes, cold/warm time, peak RAM/VRAM, CORE co-residency, migration/rollback. Không tải weights trước model-preparation approval; không ghi số đo chưa chạy.
- HAR-012/HAR-014 cần approval adoption cụ thể, actual quality/resource panel, cancel/OOM/restart/partial artifact tests và owner acceptance phù hợp. Không có adapter phải báo unavailable, không fallback provider hay unload CORE.
- Không dùng PASS của vision/OCR/video sampling hoặc fixture-rendering scripts làm bằng chứng sinh ảnh/video.

### HAR-015 — Baseline completion

- Cài từ clean supported environment bằng uv + pinned UI build, không cần private artifacts trong unit tests; có guide setup/auth/run/stop/upgrade/rollback.
- End-to-end CLI/UI → same API → bounded coordinator → tool/skill → verified result; test real streaming/cancel, unchanged prior PASS scope và no-credential logging.
- Ghi exact source scope/commands/counts/skips; software, live integration, model quality và owner UX signoff tách biệt. Chỉ đóng các mục đã có evidence đúng AC.

## 4. Liên hệ với backlog cũ và giới hạn

[Coding backlog](CODING_AGENT_BACKLOG.md), [memory backlog](MEMORY_BACKLOG.md), [vision backlog](VISION_BACKLOG.md), [web backlog](WEB_RESEARCH_BACKLOG.md), [voice integration](VOICE_INTEGRATION_BACKLOG.md), [model evaluations](MODEL_EVALUATION_BACKLOG.md) và [outstanding ledger](OUTSTANDING_WORK_STATUS.md) vẫn giữ nguyên. HAR-* bổ sung lớp product/integration, không thay hoặc đóng những đánh giá còn mở.

Không thêm marketplace/auto-update, executable skill bundles, multi-agent parallelism, cross-platform/mobile/cloud deployment hoặc model replacement vào v1. Các hướng này cần assessment riêng nếu có nhu cầu. ADR-180 đã được owner cho triển khai theo giai đoạn; bước tiếp theo là chốt các AC còn thiếu của HAR-001/004/005/006/007 và chạy HAR-008 trước khi gọi specialist harness qualified. Nhánh generation chờ candidate/manifest/SDK/resource proposal và owner approval cụ thể, không dùng quyền triển khai software để tự chọn model.

## Context follow-up — 2026-11-11

Owner ưu tiên xử lý context vượt ngân sách. [Guide](../CONTEXT_MANAGEMENT_STRATEGIES.md) đối chiếu cả bảy phương pháp; HAR-009-A đóng riêng mechanics thử nghiệm, không đóng AC adoption HAR-009 ở trên. 462 related PASS/0FAIL/0SKIP/4.75s,38files,55tests mới. Native frozen eight-case preparation-only panel giữ/bỏ đúng dữ kiện/cặp/pin, pressure còn20328tokens, strict/mandatory overflow từ chối đúng; zero completion calls, chưa semantic/TTFT/peak resource qualification. Default/browser/approved model/DB/provider giữ nguyên; chỉ owned CORE trial được chạy rồi dừng. Q4 research deferred, không bỏ kết quả cũ hoặc gọi toàn dự án PASS.


## TODO: tối ưu context cho tác vụ dài — 2026-11-11

**Yêu cầu owner:** ghi nhận hướng cải thiện sau khi đối chiếu với cơ chế công khai của OpenAI/Anthropic. Đây là việc cần làm, chưa phải kết quả benchmark hoặc quyết định bật mặc định. HAR-009 tổng vẫn PARTIAL; HAR-009-B là bước kế tiếp. *(Ghi chú 2026-11-11: B1, B2 và C1 slice 1 đã đo; theo thứ tự B1 → B2 → C1 → D1, bước kế tiếp là thiết kế D1 và phần còn lại của C.)*

Mục tiêu: kết hợp **ràng buộc được ghim + recent context theo ngân sách token + trạng thái công việc có cấu trúc + bản gốc có thể truy xuất lại**. Không dùng số lượng lượt hội thoại làm tiêu chí chính duy nhất và không xem excerpt có mặt trong prompt là bằng chứng model trả lời đúng.

| Task / trạng thái | Priority / effort dự kiến | Việc cần làm và điều kiện nghiệm thu | Dependency / rủi ro |
|---|---|---|---|
| HAR-009-B1 — Benchmark retention trước tối ưu / **MEASURED 2026-11-11** ([kết quả](../HAR009_B1_RETENTION_RESULT.md): `full` 11/12, `legacy` 3/12, `window3` 1/12, `window3_pin1` 3/12, `compact3` 12/12 (0 câu trả lời giá trị cũ; legacy và window3 mỗi nhánh 1). `full` và `compact3` giữ đủ 12/12 dữ kiện, chênh 12/11 chỉ do luật chấm chữ số; compact dùng ~2,1× token so với full trên hội thoại ngắn; corpus làm truy xuất từ khóa dễ (cận trên). Chưa đo output tokens và recall tường minh; không quyết định adoption) | P1 / thuộc 2–3 ngày chuẩn bị + đo của B | Freeze corpus/oracle/thresholds trước inference; so sánh legacy window, configurable window + pins và extractive compact/recall trên cùng model/preset/input. Chấm câu trả lời thực tế, facts, constraints, citations, mâu thuẫn cũ–mới và việc còn dang dở; đo input/output tokens, latency/TTFT, RAM/VRAM và chi phí compact. Giữ first outcomes, failures và không retry-until-pass. | HAR-009-A, native telemetry; rủi ro leakage, corpus dễ và nhầm software PASS/context presence với semantic quality. |
| HAR-009-B2 — Recent window theo token budget và mức quan trọng / **IMPLEMENTED opt-in + MEASURED 2026-11-11** ([ADR-189](../ADR/189-opt-in-token-budget-history-window.md), [kết quả](../HAR009_B2_TOKEN_BUDGET_RESULT.md), 2 lần chạy cho cùng kết quả chấm: `token-budget` 7/12, `legacy` 3/12, `extractive-compact` 11/12. Giữ đủ 40 lượt ngắn (4/4, legacy 0/4) và rule có marker dưới áp lực token (2/2, legacy 0/2), nhưng 2 regression: giữ quyết định cũ có marker, bỏ lời đính chính mới hơn không có marker và trả lời giá trị cũ. Không đổi default; trước adoption cần luật cho lời đính chính mới hơn thắng, có ADR riêng và chạy lại protocol. *Cập nhật 2026-11-11:* luật đó đã có trong ADR-190 (freshness `newer_related`) khi bật `working_state`; C1 phần A đo được lời đính chính được giữ ở cả 4 lượt. `token-budget` không kèm state giữ nguyên hành vi đã đo của B2) | P1 / 1–2 ngày triển khai + đo, ước lượng riêng sau B1 | Giữ current task và pin bắt buộc; chọn recent whole pairs trong token budget thay vì chỉ mốc 11 cặp. Quy tắc importance phải inspect được; tách token pressure khỏi giới hạn message/cache. Có receipt cho nội dung giữ/bỏ và lý do; kiểm thử long turns, short turns và mandatory overflow. Không tự tăng context size. | B1 baseline, ADR cho thay đổi thuật toán; rủi ro mất constraint cũ hoặc priority sai. Cần paired evaluation trước adoption/default change. |
| HAR-009-C1 — Structured working state và compaction / **SLICE 1 IMPLEMENTED opt-in + MEASURED 2026-11-11** ([ADR-190](../ADR/190-opt-in-source-bound-working-state.md), [kết quả](../HAR009_C1_WORKING_STATE_RESULT.md): working state tất định chỉ từ dòng user có marker, khóa `[key]` để thay thế/đóng việc, lineage theo cặp + SHA-256, freshness giữ cặp mới hơn có liên quan; CLI mang state qua các lần bỏ cửa sổ. 2 lần chạy (lần 2 trên code đã sửa sau review độc lập), cùng kế hoạch context. Phần A: `budget_state` 9/12 rồi 7/12; freshness giữ lời đính chính ở cả 4 lượt thuộc case cũ-mới, trả lời đúng 3/4, lượt còn lại nêu cả giá trị mới lẫn cũ nên bị tính là trả lời giá trị cũ; `budget` không state 0/4. Phần B (200 lượt, 3 lần bỏ cửa sổ): 5/5 case có marker ở cả 2 lần, legacy và không-state 0/5; control không marker hỏng ở mọi nhánh. Còn mở: LLM summary, compaction tool output, state bền phía server (D1)) | P1 / 2–3 ngày + đo, nằm trong scope C; không cộng thành cam kết lịch | Thiết kế schema gồm mục tiêu, ràng buộc, quyết định, nguồn/bằng chứng, công việc đang làm, lỗi chưa giải quyết, chi tiết triển khai, việc còn thiếu và uncertainty. Thiết kế tự kích hoạt compaction khi token thực tế vượt ngưỡng cấu hình, chừa output reserve và mang working state cùng recent context sang cửa sổ tiếp theo; kiểm thử nhiều lần compact liên tiếp, không chỉ một lần cắt lịch sử. Mỗi mục có lineage/freshness; phân biệt lời model với fact đã kiểm chứng. Nếu dùng LLM summary, đo giữ đúng thông tin và mâu thuẫn trước khi bật; chỉ dùng model đã duyệt. Giảm tool outputs dư thừa nhưng giữ tham chiếu để xem lại. | B1/B2, ADR trước implementation; rủi ro summary bịa/thiếu, stale state, mất chi tiết hoặc đưa approval/consent cũ thành quyền hiện tại. |
| HAR-009-D1 — Bản gốc, ghi chú bền vững và retrieval khi cần / **DESIGN PROPOSED 2026-11-11** ([ADR-191](../ADR/191-proposed-durable-context-originals-and-notes.md): thread bền do chủ dự án tạo, bảng mới trong migration 0007, không Qdrant, không khôi phục approval/consent; triển khai chờ 10 nhóm quyết định của chủ dự án, gồm duyệt migration, thời hạn lưu, quota, mã hóa dữ liệu lưu trữ và cửa sổ vận hành) | P2 / thuộc 3–5 ngày + đo của D; cần đánh giá lại sau thiết kế | Lưu bản gốc và structured notes/working state ngoài prompt có owner ACL/hash/retention/delete/invalidation; ghi chú được cập nhật theo tiến độ, có version/source references và xử lý mâu thuẫn. Inspect và nạp lại đúng ghi chú/nguồn sau khi đổi cửa sổ context hoặc restart, kiểm thử tiếp tục việc dang dở, expiry/deletion/cross-owner; không phục hồi approval/consent qua ghi chú. Nối RAG/memory vào chat chỉ qua consent và scope đã duyệt. Không coi RAM cache 30 phút hiện tại là long-term memory. | C1, artifact/storage design, existing consent/ACL; rủi ro secret leak, nguồn đã xóa vẫn bị recall, recovery quyền cũ và tăng RAM/disk. |

**Thứ tự:** B1 → B2 → C1 → D1. Sau mỗi thay đổi phải chạy lại paired retention/resource evaluation trên protocol đã chốt; chưa đạt thì không promote/default-enable. Các effort là ước lượng cần cập nhật khi có thiết kế, không phải ngày bắt buộc hoàn tất. B1/B2 ưu tiên trước việc thêm LLM summary hoặc nhiều tầng memory chỉ để tăng số tính năng.

**Gate giữ nguyên:** không đổi model/provider/runtime preset, không nâng cửa sổ context, không tự nối memory hoặc thay storage trong bước ghi backlog này. Mọi đề xuất thay model vẫn cần benchmark, tài nguyên, migration/rollback và owner approval. Không gắn chất lượng “ngang hệ thống lớn” nếu chưa có benchmark so sánh phù hợp.

Tham khảo thiết kế công khai: [OpenAI compaction](https://developers.openai.com/api/docs/guides/compaction), [Anthropic context engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents). Các nguồn mô tả cơ chế; không chứng minh implementation hiện tại có chất lượng tương đương.

## Aevra/native desktop follow-up — 2026-11-11

Owner yêu cầu tên/logo Aevra và desktop độc lập. HAR-016 Linux implementation verified theo [guide](../AEVRA_DESKTOP.md), [ADR-188](../ADR/188-aevra-brand-and-native-webkit-desktop.md), [receipt](../evidence/aevra-native-desktop-20261111.json). Native GTK/WebKit dùng lại chat UI, không gọi Brave/Chromium, không fallback browser. Owned missing-backend start/stop và reused-backend protection đã kiểm; UI/context/model/tool authority không tự mở rộng. Launcher Aevra đã có trong menu Linux; còn phụ thuộc checkout/uv/OS libraries, chưa là AppImage/Windows/macOS installer.

498 related PASS/0FAIL/0SKIP/5.14s,41files,36tests mới; actual native synthetic stream/exit0,0model calls;18Python files lint/format/descriptions và23packaged files byte-match. Original dragon SVG/PNG và70upstream UI files unchanged. Broader device/installer/full-regression/release gates pending. Context optimization B1 vẫn là NEXT sau yêu cầu branding/native hiện tại; không đóng các TODO B2/C1/D1 hoặc reset kết quả cũ. *(Ghi chú 2026-11-11: B1, B2 và C1 slice 1 đã đo sau đó; xem các dòng HAR-009-B1/B2/C1 bên dưới.)*

**Owner icon acceptance — 2026-11-11:** ngoài Desktop đã đúng; Show Apps được xác nhận hết ô đen sau khi dùng PNG trong suốt và thay đăng ký canonical `io.aevra.Aevra`, đồng bộ native ID. TEST đã dọn, entry cũ lưu riêng;75related PASS/1.11s. Chỉ đóng lỗi hiển thị logo này, không đóng installer/device/context/semantic/release gates khác.
