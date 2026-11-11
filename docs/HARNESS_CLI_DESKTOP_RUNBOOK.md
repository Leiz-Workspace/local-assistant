# Harness CLI và chat desktop — bản v1

**Mục đích:** Hướng dẫn sử dụng code đã triển khai cho CLI, chat UI llama.cpp, context và skill; ghi rõ giới hạn và kết quả kiểm thử.

**Cập nhật:** 2026-11-10. Entry point mới là **opt-in**, không thay `apps.api.main:app`. [ADR-181](ADR/181-checkout-cli-desktop-and-readonly-specialist-runs.md), [backlog còn lại](progress/HARNESS_PRODUCT_BACKLOG.md). Đây chưa là release hoặc native desktop installer.

**V1.1 follow-up:** đã có [signed metadata history opt-in](HARNESS_METADATA_HISTORY.md) bằng `la serve --state-dir PATH`; default vẫn memory-only, không lưu/phục hồi answer text, task execution hoặc skill grants. [Paired skill measurement](HAR008_PAIRED_EVALUATION_RESULT.md) đã chạy 24 first attempts: baseline 5/12, skill 6/12, promotion NOT_QUALIFIED. [Actual tokenizer packing](HAR006_NATIVE_CONTEXT_PACKING_RESULT.md) đã đo history 24,131 tokens; không phải semantic-quality/peak-memory benchmark. Lượt final combined related mới **294 PASS trong 3.80 s**, không thay các kết quả v1 lịch sử ở mục 6.

**CURRENT Aevra/native — 2026-11-11:** tên chính `aevra` (`la` alias), supplied white dragon và native GTK/WebKit desktop đã triển khai theo [guide](AEVRA_DESKTOP.md), [ADR-188](ADR/188-aevra-brand-and-native-webkit-desktop.md). Không còn Brave/Chromium app-mode trong command desktop.498related PASS/5.14s; actual synthetic native streaming/0model calls. Các kết quả v1 cũ bên dưới là lịch sử, không phải mô tả launcher mới.

## 1. Cài đặt và chạy

Chạy từ repository `ai/`. Console script `la` được cài bằng uv editable; dependency versions hiện có giữ nguyên, lock chỉ đổi project từ virtual sang editable.

```bash
uv sync --locked --dev
uv run --no-sync la --help
uv run --no-sync la doctor
```

Thiết lập **một principal local mới, tách biệt**, chỉ khi chưa có cấu hình cho harness này:

```bash
uv run --no-sync la init
```

Lệnh tạo token và digest-only principal file, quyền `0600`, tại `~/.local/state/local-assistant/`. Nó từ chối overwrite. Không dùng lệnh này để thay identity hay credential của hệ thống hiện có. Muốn dùng principal sẵn có, khởi động server với đúng auth file và dùng `la --token-file PATH auth login`; token nhập kín, không truyền qua argv. Không đọc/sửa Vault trong quá trình setup này.

Tải **UI assets, không phải model**:

```bash
uv run --no-sync la ui prepare
```

Nguồn cố định `ggml-org/llama-ui`, version `b11557`, tương ứng runtime pin `5c8854fd88319125125dc4b836c98b1b215b0f23`. Không fallback `latest`. Checksum archive và hash từng file được lưu trong `data/ui/b11557/receipt.json`; có license llama.cpp đi kèm. Lượt đã chạy: **70 file, 10,074,640 byte** giải nén; archive SHA-256 `840a7017ac2a774b109c32752d15b24ced86db373b556b0d85baa60e1b2e4ae2`. Những số này là UI assets, không phải RAM/VRAM hoặc weights.

CORE phải chạy theo cấu hình đã duyệt ở [phần inference](DOCUMENTATION.md). Nếu chưa có server trên cổng cấu hình và model đã có sẵn, launcher hiện tại là:

```bash
uv run --no-sync python scripts/start-core.py
```

Không khởi động thêm server nếu cổng đang có runtime. CLI không tự tải, thay hoặc unload model. Trên terminal khác, chạy backend harness:

```bash
uv run --no-sync la serve
```

Mặc định bind `127.0.0.1:7090`, không proxy headers/access log chứa URL bootstrap. Có thể dùng `serve --port PORT --auth-file /ABSOLUTE/PRIVATE_AUTH_FILE`. `DATABASE_URL` và các feature flag của base API vẫn theo lifecycle hiện có; không tự tìm secret, bật database hay đăng ký source roots.

## 2. Mở giao diện và desktop

Khi backend đã chạy:

```bash
uv run --no-sync la ui open
uv run --no-sync la desktop
```

`aevra ui open` mở trình duyệt mặc định. `aevra desktop` mở **ứng dụng GTK/WebKit native độc lập** dùng cùng UI local; không mở/fallback Brave/Chromium. Backend đang có được dùng lại và không bị dừng; nếu chưa có backend thì app có thể khởi động/dọn đúng backend của nó với identity sẵn có. Không tự nạp hoặc dừng CORE. Xem [native guide](AEVRA_DESKTOP.md) cho prerequisites, storage, session expiry và launcher. Chưa là AppImage hoặc bộ cài Windows/macOS.

Tạo shortcut tại đường dẫn do người dùng chọn, không tự cài vào hệ điều hành:

```bash
mkdir -p data/desktop
uv run --no-sync aevra desktop --write-launcher 'data/desktop/Aevra.desktop'
```

App bearer không đưa vào URL/JavaScript/browser storage. CLI mint một pairing nonce một lần, hết hạn sau 60 giây; nonce chỉ đi trong fragment, được xóa trước khi đổi sang cookie HttpOnly/SameSite. Session sống tối đa 30 phút và được kiểm lại với auth file khi nhận request. Khởi động lại backend làm mất session; chạy lại `ui open`/`desktop` để pair lại. `auth logout` chỉ xóa credential file của CLI, không tuyên bố đã revoke mọi server session.

Giao diện v1 chỉ chat text với CORE/Fast, output tối đa 4096 tokens theo budget còn lại. Không chuyển native tool calls, MCP, model load/download/unload, arbitrary proxy, sandbox hay multimodal sang runtime. Các controls Models/MCP/reasoning đã ẩn; native endpoints vẫn từ chối direct requests. UI advanced generation settings ngoài hợp đồng này chưa được nối. Service worker bị CSP chặn có thể tạo console warning; v1 không dùng PWA cache/offline installation.

**History v1:** upstream IndexedDB trên thiết bị, chưa đồng bộ với PostgreSQL Conversation. Backend chat stateless; không tuyên bố branch/import/export trong UI đã có server ACL/persistence semantics. Không có replay stream sau reload; lookup trả danh sách rỗng vì không có resumable server sessions. SSE lỗi có safe error event, không buffer câu trả lời hoàn chỉnh rồi giả streaming.

## 3. Chat, task và context

```bash
uv run --no-sync la --json status
uv run --no-sync la chat
uv run --no-sync la --json chat --message 'Reply with exactly: READY' --preset fast
```

Global options `--url`, `--token-file`, `--json` đặt **trước** subcommand. `--json chat` cần `--message`, tránh lẫn interactive prompts vào machine output. CLI chat giữ recent history trong tiến trình, chưa là durable conversation.

Task chuyên biệt có tối đa bốn evidence calls readonly do host/user chỉ định, sau đó một CORE completion. Không có tự chọn tool bằng model, free-form shell hoặc tự retry. Tổng deadline 120 giây, một task/stream/generation giữ admission tại một thời điểm. Deadline có tính thời gian chờ; preset Deep/Unlimited không được tự kéo dài thời hạn.

```bash
uv run --no-sync la run --workspace WORKSPACE_UUID \
  --task-file task.md --tools-file tools.json --skill source-reader \
  --preset fast --context-strategy evidence-first --wait
uv run --no-sync la runs list
uv run --no-sync la runs show RUN_UUID
uv run --no-sync la context inspect RUN_UUID
uv run --no-sync la runs cancel RUN_UUID
uv run --no-sync la runs remove RUN_UUID
```

`WORKSPACE_UUID`, `RUN_UUID` là placeholders. `tools.json` là list typed envelopes, ví dụ `[{"name":"workspace.read","arguments":{"path":"README.md"}}]`; không phải shell script. Workspace cần host catalog hiện có qua `ASSISTANT_WORKSPACE_ENABLED=1` và private `ASSISTANT_WORKSPACE_CONFIG_FILE`, theo [workspace documentation](DOCUMENTATION.md). `la init` không tự cho phép đọc toàn bộ repository hoặc ổ đĩa.

Ba context strategies đã có:

| Strategy | Hành vi |
|---|---|
| `evidence-first` | Thêm bounded evidence; có thể bỏ các cặp hội thoại cũ để vừa token budget. |
| `recent-turns` | Giữ recent turns đã fit; bỏ evidence nếu phải hy sinh thêm history, ghi `history_priority`. |
| `strict` | Từ chối nếu bước chọn/fit history phải loại message; optional evidence vẫn có thể bị bỏ với lý do rõ. |

Mọi strategy giữ host policy/current task/reviewed skill, dùng tokenizer/template thật và preset hiện có. Exact duplicate evidence được loại theo hash. Report có selected preset, total input tokens, trimming/omission và skill/source digests. Chưa có semantic summarization, automatic memory injection hoặc quality benchmark trên long-context corpus; source layering/global allocation và durable working state còn trong backlog.

Mặc định run/skill/result/artifact **process-local**; khi bật state-dir, chỉ run metadata/digests được archive qua restart, không raw results hoặc execution/grants. Có tối đa 8 retained runs mỗi owner, 64 toàn coordinator, gồm archives; dùng `runs remove` để giải phóng terminal capacity. Không có durable resume hoặc write actions; event sequence hiện lấy qua `runs show`, chưa có run-event SSE riêng.

## 4. Review, install, inspect và revoke skill

Hai manifest local: [source-reader](../configs/skills/source-reader.v1.json), [repo-review](../configs/skills/repo-review.v1.json). File không tự cài hoặc activate.

```bash
uv run --no-sync la skills review configs/skills/source-reader.v1.json --workspace WORKSPACE_UUID
uv run --no-sync la skills install --review REVIEW_UUID --sha256 EXACT_REVIEWED_SHA256 --workspace WORKSPACE_UUID
uv run --no-sync la skills list
uv run --no-sync la skills show INSTALLATION_UUID --workspace WORKSPACE_UUID
uv run --no-sync la skills remove INSTALLATION_UUID --workspace WORKSPACE_UUID
```

Đọc toàn bộ review trước khi install. Review 120 giây, một lần, bind exact raw bytes/hash/version/permissions/owner/workspace. CLI không có auto-trust/auto-update. Mỗi tool call và sau inference đều recheck installation; revoke giữa run chặn publication. Instructions thực sự bind vào context dưới host policy, không cấp thêm quyền. V1 chỉ các readonly workspace permissions; chưa import executable skill bundles, arbitrary `SKILL.md`, dependency scripts hoặc marketplace.

Skill giúp chuẩn hóa quy trình; chưa có bằng chứng năng lực ngang model lớn. Live smoke bên dưới không thay [paired measurement HAR-008](HAR008_PAIRED_EVALUATION_RESULT.md), hiện đã hoàn tất với promotion NOT_QUALIFIED.

## 5. Image/video generation

Đã có [request/port contract](../src/application/ports/media_generation.py), [job manager](../apps/harness/generation.py), typed API `/api/v1/harness/generations`, cancellation, scoped download và CLI:

```bash
uv run --no-sync la generate image --prompt-file prompt.md --width 512 --height 512
uv run --no-sync la generate video --prompt-file prompt.md --seconds 4 --fps 12
uv run --no-sync la jobs list
uv run --no-sync la jobs show JOB_UUID
uv run --no-sync la jobs cancel JOB_UUID
uv run --no-sync la jobs remove JOB_UUID
```

**Hiện không có backend/model generation được cấu hình:** hai lệnh generate báo HTTP 503 / CLI exit 6 trước khi tạo job hoặc giữ prompt. Không trả placeholder như ảnh/video thật, không tự tải weights/chọn provider/unload CORE. Khi adapter được duyệt ở giai đoạn sau, contract hiện có cho phép tối đa 120 giây, 8 MiB/artifact, 32 MiB retained bytes tổng, 4 retained jobs/owner và 16 toàn manager; đây là software bounds, chưa là resource envelope đã benchmark cho model nào.

Tests dùng synthetic bytes chỉ chứng minh lifecycle/ACL/hash/cancel, không chứng minh ảnh/video hợp lệ hoặc chất lượng. Native format validation, disk durability/retention/restart recovery, resource admission và actual media benchmarks còn pending. [Candidate screening](GENERATION_CANDIDATE_SCREENING.md) chỉ là metadata, chưa chọn/tải/chạy thêm model.

## 6. Kiểm chứng đã chạy và giới hạn

- **209 PASS / 0 FAIL / 0 SKIP, 2.38 s**: 7 file test mới cộng 11 file liên quan harness/skill/context/planner/MCP/observability/logging; không gọi model trong pytest.
- **50 PASS / 0 FAIL / 0 SKIP, 0.80 s**: invocation riêng cho auth, stateless security và runtime presets. Không cộng hai lượt thành một full regression.
- Ruff check/format trên toàn bộ source/tests mới PASS; browser scripts được thực thi bằng Node doubles trong pytest.
- Đã tải/checksum UI thật; actual browser đã hiển thị upstream UI, nhận `fixture` từ backend test và sau đó nhận **`READY` từ CORE thật** ở backend cuối. Các lần đầu sai `/tools` array shape và MODEL-mode request semantics đã được sửa và bổ sung regression; không coi các lần đó là PASS.
- CORE đã có sẵn được kiểm SHA-256 trước khi khởi động bằng launcher/config không đổi. CLI thật nhận `READY`. Live `source-reader` + native workspace read trên **synthetic** README trả đúng port 7443 và cite line 5: 805 input / 114 output tokens, 2.057 s cho run-plus-context-inspection theo script. Đây là một smoke, không là TTFT/SLO/general quality benchmark.
- Actual cookie-authenticated SSE với CORE trả `STREAM-READY`, 5 native choice chunks và `[DONE]`. Lượt validator đầu lỗi vì nối initial `content: null` như string đã được giữ NOT_PASS; lượt sau xử lý đúng protocol mới PASS. Không relabel lượt đầu hoặc gọi đây là model comparison.
- Linux desktop launch command đã tạo isolated Brave app-window process; UI rendering được kiểm ở in-app browser. Chưa có native-window/device acceptance hoặc native installer certification.

Bản source cuối có thêm route-template/request-ID/status audit và kiểm tra log không lộ token/query/prompt. Live strict-context smoke sau thay đổi cuối chạy thành công trong **1.560 s** theo CLI-command wall clock, xác nhận restart không khôi phục installation và phải review/install lại. [Public receipt và source hashes](evidence/harness-v1-20261110-receipt.json), [ảnh UI thực trả READY](evidence/harness-v1-real-core-ui.png). Native counters trong UI không phải phép đo physical first-token/SLO.

Private receipts ở `data/harness-local/cli-core-receipt.json`, `stream-core-first-validation-error.json`, `stream-core-receipt.json`; auth/session tokens không vào report. D87 6233 PASS cũ vẫn chỉ chứng minh source scope cũ. Chưa chạy full regression cho các source additions này; mọi D60/D81/D89/D90 và model/voice decisions cũ giữ nguyên.

## 7. Dừng và rollback

Ctrl+C terminal chạy `la serve` để join task/job trước khi đóng shared services của tiến trình đó. CORE chạy ở terminal riêng, dừng riêng nếu do mình khởi động; không kill shared runtime bằng PID đoán. Để quay về entrypoint cũ dùng `apps.api.main:app`, không set product flag. Giữ receipts/config/model/data cũ; không xóa history để gọi rollback thành công.

## 8. Source-backed JSON opt-in

[ADR-183](ADR/183-opt-in-source-bound-json-output-contract.md), [kết quả và giới hạn](HAR008_OUTPUT_CONTRACT_RESULT.md): dành cho câu hỏi đọc nguồn/review cần đúng hai trường `value` và `quote`. Default vẫn text; CLI không gửi trường mới khi dùng text, nên tương thích server v1 còn chạy. Browser streaming chưa hỗ trợ chế độ này. Primary desktop7090 chưa restart trong lượt triển khai; muốn dùng mode mới cần một process từ checkout mới, dùng cùng cấu hình workspace/auth được phép. Không tự bật/tải/đổi model.

Ví dụ `reads.json` chứa tool được host chỉ định, path tương đối trong workspace đã cấp quyền:

```json
[{"name":"workspace.read","arguments":{"path":"README.md","start_line":1,"end_line":30}}]
```

`task.md` mô tả câu hỏi, kiểu value mong muốn và yêu cầu quote nguyên dòng. Chạy với UUID workspace thực của bạn:

```bash
uv run --no-sync la run --workspace WORKSPACE_UUID \
  --task-file task.md --tools-file reads.json \
  --preset fast --max-tokens 512 --context-strategy strict \
  --output-contract source-value-quote-v1 --wait
```

Có thể thêm `--skill source-reader` hoặc `--skill repo-review` sau khi review/install đúng hash như mục 3. Skill không được vượt host policy, tự gọi thêm tool hoặc thay output contract. Không đưa đáp án benchmark vào task/schema. `--output-contract text` hoặc bỏ option để quay lại đường text; không fallback tự động khi contract lỗi.

Host chỉ nhận 1–4 workspace.read snapshots đã retained và đúng hash/envelope/trust metadata; không mixed search hoặc schema tự truyền. Catalog tối đa 128 quote khác nhau, 16 KiB canonical text, 256 origins; mỗi quote tối đa 1 KiB, schema tối đa 64 KiB. ASCII indentation/trailing spaces bị bỏ ở **nguồn trước inference**, không sửa output. Value là string 1–256 ký tự hoặc signed 32-bit integer, kèm quote nguyên canonical line; thiếu câu trả lời xác định thì phải null/null. Không hỗ trợ trích đoạn tùy ý/multiline. Dùng read ranges nhỏ nếu source vượt catalog limits.

`run.context.output_contract` chứa tên/status, schema/catalog/raw-content hashes, quote origins và `semantic_correctness=not_established`. Hợp lệ về nguồn chưa chứng minh đúng nghĩa. Catalog unavailable hoặc output invalid làm run failed; `diagnostic.code` giải thích cho owner, raw native result nếu đủ bounded được giữ ở `diagnostic.raw_result`, không phải result thành công. Không bóc fence/trim/cast/retry. History chỉ lưu digest/state, không phục hồi raw diagnostic sau restart; logs không chứa nội dung.

Kiểm chứng mới: 323 related PASS/3.89s; fresh R3 48 calls, text 8/12 mỗi nhóm, constrained 12/12 mỗi nhóm, không có skill gain bổ sung. R1/R2 errors và original 5/12–6/12 giữ nguyên. Đây chưa là broad specialist qualification, TTFT/resource acceptance, full regression hay release.

## 9. Maintenance và telemetry follow-up

[Q2 result](HAR008_Q2_MAINTENANCE_RESULT.md), [protocol](HAR008_Q2_MAINTENANCE_PROTOCOL.md): benchmark-only runner `benchmarks.har008_maintenance` đã đo24 controlled maintenance/caller/long-source cases qua API sản phẩm,96 first calls. Text11/24 mỗi nhóm, constrained21/24 baseline/23/24 skill. Contract-valid source vẫn có thể sai số dòng/ý nghĩa; quote đúng nhưng line5 thay vì4 được giữ failed theo oracle. HAR-008-L1 là task assessed tiếp theo; chưa triển khai contract mới hoặc thay skill/model.

Native PID được chọn rõ và pin start ticks; lấy mẫu RSS RAM/GPU allocation mỗi0.2s. Đã quan sát native RSS9.55GiB/GPU process allocation7.83GiB trong637 mẫu chất lượng. Tám benchmark-only streaming replays đo first nonempty text delta0.42–0.62s short/2.37–2.53s long,58 mẫu riêng; không biến task API thành streaming hay cấp thêm quyền tool. Không tự reset cache/restart/unload CORE. Chi tiết command scope/units/cache/missing metrics trong protocol; các case đã công khai không còn là fresh evaluation nếu chạy lại.

349 related software tests PASS/4.07s; không native calls trong pytest và chưa full D87 mới. Probe7092 đã dừng sau khi xóa đúng terminal runs/grants của campaign; desktop7090/CORE8080 vẫn chạy. Không thay default, config, DB/Vault/Docker/Qdrant hoặc release state.

Đoạn trên là checkpoint Q2 ngày2026-11-10. Trạng thái L1/ngày2026-11-11 và lifecycle trial mới được ghi ở mục10.

## 10. Target-bound review research modes

[ADR-185](ADR/185-opt-in-target-bound-review-line-quote-contract.md), [kết quả đầy đủ](HAR008_L1_REVIEW_PAIR_RESULT.md): hai mode opt-in ràng buộc **cặp dòng–quote từ đúng target**, chưa qualified để tự động dùng làm review mặc định. `review-line-quote-v1` sinh value trước quote; `review-quote-line-v1` sinh quote trước value. Đổi thứ tự không chứng minh review tốt hơn. Text và generic source-value-quote giữ nguyên; browser streaming chưa có hai mode này.

Tạo `reads.json` theo quyền workspace thực, ví dụ:

```json
[{"name":"workspace.read","arguments":{"path":"src/sample.py","start_line":1,"end_line":80}}]
```

`task.md` ghi rõ contract cần review và chỉ tiêu kết quả. Dùng UUID workspace đã cấu hình, server khởi động từ source mới và CORE cũ đã sẵn sàng:

```bash
uv run --no-sync la run --workspace WORKSPACE_UUID \
  --task-file task.md --tools-file reads.json --skill repo-review \
  --preset fast --max-tokens 512 --context-strategy strict \
  --output-contract review-line-quote-v1 --review-target src/sample.py --wait
```

Muốn thử quote-first thì thay đúng tên mode bằng `review-quote-line-v1`. Skill cần review/install đúng raw hash theo mục3; không tự cấp quyền từ target field. Có thể thêm explicit read của caller/policy để làm context. Target phải clean relative path và đã được explicit read, retained, đúng source hash; target không được dùng với text/generic. Range giữa file giữ original line numbers. Quote lặp có nhiều cặp hợp lệ, không tự chọn occurrence đầu; snapshot mâu thuẫn/target bị omit/không có dòng hợp lệ/schema trên64KiB làm run failed, không fallback.

Kết quả luôn gồm hai trường JSON value/quote (null/null nếu không có supported finding), với `context.output_contract` ghi tên mode, target, schema/catalog/content hashes, selected origins, `line_binding` và `semantic_correctness=not_established`. Đúng cặp không có nghĩa đúng lỗi. Wrong native pair không được sửa; failed diagnostics chỉ owner xem, history chỉ giữ digest/state. Bỏ option và target để rollback về text hoặc chọn generic không target; không tự thay model.

Đã đo48+72first calls trên hai bộ mới:72/72 bound pairs hợp lệ nhưng strict scores dao động và có false positives/regressions; quote-first không cải thiện nhất quán. Giữ toàn bộ first results, không gọi các bộ đã công khai là fresh nếu chạy lại.389 related PASS/4.63s, offline wheel/source bytes verified, chưa full D87/release. CORE ban đầu chưa chạy; đã kiểm checksum/pin, chạy đúng approved model cho trial rồi dừng cùng owned app7092 sau khi lưu bằng chứng. Không restart primary, tải model hay đổi DB/Vault/Docker/Qdrant. Q3 semantic rubric/workflow là bước assessed tiếp theo.

## 11. Finite semantic review prototype

[Q3 result](HAR008_Q3_SEMANTIC_RESULT.md), [protocol](HAR008_Q3_SEMANTIC_PROTOCOL.md), [ADR-186](ADR/186-native-only-finite-semantic-review-prototype.md): đây là native-only benchmark, chưa phải lệnh product review hoặc multi-call task mới. Kiểm tra các flag bằng lệnh không inference:

```bash
uv run --no-sync python -m benchmarks.semantic_review_run --help
```

Thực chạy cần workspace fixture được owner cấu hình, đúng native PID/start ticks, CORE cũ đã verified/ready và output directory mới. Không dùng source thật tùy ý: trusted helpers chỉ hỗ trợ các exact registered snippets/probes; source/gold/evidence phải khớp trước generation, ngoài domain bị chặn. Không execute snippets/model code hoặc cấp quyền từ candidate text. Bộ công khai này không còn là fresh evaluation nếu chạy lại.

Mỗi case có single candidate và đúng một planned self-check, cùng nguồn/probes, không gold/grade feedback. Giữ cả hai raw outputs và hash liên kết; không retry-until-pass hoặc ghi đè initial score. Typed counterexample/location/claim được chấm bằng trusted finite operations, title prose không được chấm semantic; self-check không là oracle độc lập. Checked workflow dùng thêm một call/cap512 tokens và phải cộng chi phí hai calls.

Kết quả48calls: single6/12→checked5/12 baseline,5/12→6/12 skill; **all groups0/5 complete known-defect proofs**. Không activate production self-check/skill/model/default từ số này.407 related PASS/4.50s là software verification, không model-quality PASS/full D87. Owned CORE trial đã dừng, không product/config/DB/Vault/Qdrant change. Q4 deterministic-observation assistance còn pending và cần ADR/assessment/fresh evidence trước triển khai.

## 12. Context policy thử nghiệm

Xem [guide đầy đủ](CONTEXT_MANAGEMENT_STRATEGIES.md) cho bảy methods, CLI/API examples, pin numbering, quotas/TTL, raw-history privacy và giới hạn. `la chat --history-policy sliding-window --history-window 8 --pin-turn 1` giữ cặp đầu tiên sau khi hoàn thành; `--history-policy extractive-compact` thêm nguyên văn đoạn liên quan và lưu bản gốc tạm trong RAM. `la context archives/recall/forget` liệt kê/đọc/xóa cache; không phục hồi sau restart hoặc xóa conversation gốc. Muốn dùng cần process từ checkout mới; không tự restart shared app.

462 related PASS/0FAIL/0SKIP/4.75s,38files; actual native eight-case preparation-only panel/0completions. Pin/compact/recall giữ đúng old fact, pressure còn20328tokens, mandatory overflow và strict trim bị từ chối. Đây chưa là semantic summary/resource/adoption acceptance. Browser UI defaults/approved model và signed metadata-only history giữ nguyên; LLM summary/tool-state/layered memory/durable offload/UI controls pending.

## 13. Aevra identity và native host

[Aevra desktop guide](AEVRA_DESKTOP.md) là mô tả hiện tại: shared owner-provided logo, primary CLI/desktop entries, response-only upstream branding, native GTK/WebKit, optional owned backend lifecycle và installed Linux shortcut.498 related PASS/0FAIL/0SKIP/5.14s; native UI thật nhận synthetic stream, không gọi model.70pinned UI files giữ nguyên; history trên thiết bị tách khỏi Brave, scoped theo endpoint/credential hash, không tự đồng bộ DB. Cross-platform/bundled installers, full UX/device/release acceptance và UI controls context/task/skills còn pending.
