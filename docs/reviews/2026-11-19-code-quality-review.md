# Đánh giá chất lượng thiết kế: harness và các thành phần "tạm bợ"

**Trạng thái:** đã kiểm tra xong cả 11 khu vực (harness, context, api, api_services, research, app_core, infra_storage, infra_exec, infra_workers, scripts, architecture). Đối tượng là nhánh `develop` tại `cabb1d7`, bỏ qua dòng dev_log chưa commit. Tổng cộng giữ lại **220 finding** sau vòng skeptic: 10 mức cao, 101 trung bình, 109 thấp. Không finding nào bị bác bỏ toàn bộ. Các khẳng định con bị sửa được liệt kê ở mục 6.2.

Những điểm quyết định chủ đề, tôi đã tự mở code kiểm lại:
- Bốn envelope `asyncio.timeout(120)` + `admission`: `apps/harness/routes.py:214`, `service.py:217`, `browser.py:413`, `generation.py:55`.
- Các lệnh gọi `gateway._timeout/_verify_model/_select_auto_preset/_count_input_tokens` trong `apps/harness/inference.py:66-76`, `llama_adapter.py:76-87`, `structured_excerpt_adapter.py:384-385`, `coding_reasoning.py:109` và `summarizer.py:28`.
- `apps/cli/client.py:156-160` bỏ body lỗi.
- `check_jobs.py` không có đường unlink/delete, với `MAX_JOBS=32` và `MAX_OWNER_JOBS=8`.
- `conversation_manager.py:12,23-31` import SQLAlchemy và các repo Postgres.
- `llama_gateway.py`, `presets.py` và `model_config.py` mỗi file chỉ có đúng một commit (`2576c65`).
- Cấu trúc `compose()` trong `apps/harness/main.py`.

Lưu ý về con số: cùng một vấn đề thường được nhiều khu vực phát hiện, chẳng hạn CORE client xuất hiện ở C1, Z2, H5, S6 và R2. Vì vậy 220 finding gom lại chỉ còn 10 chủ đề.

---

## 1. Kết luận ngắn

Cảm giác "tạm bợ" là có cơ sở, nhưng vấn đề nằm ở **tầng tích hợp và cấu trúc**, không nằm ở từng thành phần. Từng module được viết cẩn thận và phòng thủ tốt: fail-closed, sandbox, cancellation có shield-và-join, log không lộ nội dung, khoảng 2.950 test. Điểm yếu là hệ thống lớn lên bằng cách cộng thêm từng lát cắt opt-in và gần như chưa có lần hợp nhất nào.

Nguyên nhân gốc là một quy tắc được chọn có chủ đích. Nhiều ADR (ADR-175, ADR-137, ADR-063, ADR-028) yêu cầu file cũ giữ nguyên từng byte để bảo toàn evidence. Vì thế mỗi tính năng mới phải bọc ngoài, sao chép, monkeypatch hoặc gọi private method, chứ không được sửa lõi.

Hệ quả đo được:
- Không có một CORE client duy nhất: 12 `httpx.AsyncClient` gọi CORE nằm trong 9 module, với 3 dialect `response_format`.
- Phân lớp bị đảo ngược: lõi inference và config nằm trong `apps/api`, nên `src/` phải import ngược vào `apps/`.
- Ba app factory bọc lẫn nhau và không kết hợp được với nhau.
- Khoảng 20% số dòng product không được entrypoint nào gọi tới.
- 50 class exception tồn tại mà không có registry mã lỗi.

**Harness** có một composition root và một coordinator rõ ràng. Riêng phần tích hợp thì đúng là tạm bợ:
- Chính sách CORE (admission, deadline 120 s, ánh xạ lỗi) bị chép 4 lần, mỗi bản báo lỗi theo một kiểu.
- Vòng đời run chỉ là dict không kiểu.
- `ProductHarness` là một túi service-locator, route thò tay sửa field trực tiếp.
- Inference gọi private method của gateway và gọi CORE hai lần cho một lượt.

Có vài lỗi chạm người dùng thật, nên sửa sớm:
- Check job không bao giờ được giải phóng, nên mỗi owner có giới hạn trọn đời 8 job.
- UI streaming chấp nhận câu trả lời bị cắt cụt.
- CLI bỏ hết mã lỗi của server.
- Các route CORE gốc chạy cùng process đi vòng qua admission của harness.

Phần lớn việc cần làm là hợp nhất (cỡ S hoặc M), không phải viết lại. Có hai việc lớn (L): xây một CORE client duy nhất, và quyết định nối dây hay loại bỏ planner/MCP.

**Điều kiện tiên quyết** là một ADR đổi cách neo evidence, từ "byte nguồn" sang "hành vi cộng commit SHA". Thiếu ADR này thì mọi bước hợp nhất đều vi phạm quy tắc đang áp dụng.

---

## 2. Các chủ đề chính

### 2.1 Gốc rễ: evidence được neo vào byte nguồn nên không ai được hợp nhất

**Vấn đề.** Quy tắc AGENTS.md "Preserve passing components and historical benchmark results" đã được nhiều ADR diễn giải thành "file cũ phải giữ nguyên từng byte". Vì thế mọi thay đổi xuyên suốt đều phải gắn thêm từ bên ngoài.

**Bằng chứng mạnh nhất**
- `docs/ADR/175-optional-main-voice-composition-and-entrypoint-binding.md:9` viết: *"Editing the old main entry, gateway, recorder or numerical adapters would unnecessarily invalidate that retained evidence"*. `docs/ADR/137-host-selected-boolean-answer-contract.md:21` viết: *"Old application files remain byte-identical"*. Có 24 ADR chứa "byte-identical" và khoảng 159/181 ADR chứa "unchanged".
- `apps/api/services/llama_gateway.py`, `apps/api/runtime/presets.py` và `apps/api/core/model_config.py` mỗi file chỉ có commit `2576c65 init: 15-days process`. Trong khi đó `voice.py` (06/11), `grounded_extract.py` (09/11) và `harness/main.py` (11/11) đều bọc quanh chúng.
- `src/application/services/web_fetch_tasks.py:1` ghi *"without refactoring earlier accepted helpers"*, và module này có 34 importer. ADR-028:18 ghi "without refactoring its PASS modules". `docs/evidence/d60-4032-full-freeze.json` có khóa `all536_accepted_source_config_bytes_unchanged`. Test AST-parity ở `tests/test_main_voice_extraction.py:101-151` ghim bản sao voice giống hệt script nghiên cứu.
- Quy tắc này còn không đạt được mục tiêu của chính nó. ADR-177:255 ghi lại rằng việc thêm module extract làm snapshot nguồn của evidence voice tăng từ 307 lên 310 file và kích hoạt `unexpected_source_drift`, dù `main.py` vẫn giữ nguyên byte.

**Vì sao quan trọng.** Đây là nguyên nhân chung của các chủ đề 2.2 đến 2.5 và 2.9. Nó không giải thích hết 2.6 và 2.8, vì hai chủ đề đó có thể đã được làm khác mà không cần chạm file đóng băng. Mỗi mối quan tâm xuyên suốt đều phải cài lại ở N chỗ: seal ADR-195 ở 11 site kèm một AST registry, GPU admission ở 11 entry point bằng `setattr`.

**Có chủ đích:** có. Riêng ADR-195 (đã accepted, đang nằm trên nhánh) đã sửa `llama_gateway.py`, tức là quy tắc đang được nới lỏng theo từng trường hợp.

**Thiết kế đích.** Một ADR mới thay thế các điều khoản byte-identical:
- Evidence ghi commit SHA và tag git. Việc tái lập được thực hiện bằng cách checkout tag đó.
- "Preserve" được hiểu là các receipt hành vi vẫn xanh: test, capture byte request body gửi tới CORE, output canonical (golden) và kết quả benchmark.
- Refactor hợp nhất được phép nếu giữ được các receipt đó. Thay đổi nào làm request tới CORE khác đi thì phải benchmark lại theo AGENTS.md.

*Finding liên quan:* Z1, P-m3, T10, W9, C6, A2, nguyên nhân của S1/R1.

### 2.2 Không có một CORE client duy nhất và không có admission chung

**Vấn đề.** LlamaGateway là client CORE duy nhất trên danh nghĩa, nhưng nó bị đóng băng. Vì vậy mỗi năng lực mới (structured output, excerpt, vision, OCR, summary, streaming, coding) đều tự dựng transport, kiểm danh tính model, timeout, giới hạn kích thước, parser và ánh xạ lỗi riêng.

**Bằng chứng mạnh nhất**
- **12 client CORE trong 9 module:** `llama_gateway.py:295`, `llama_adapter.py:74`, `apps/harness/inference.py:63/159/222`, `structured_profile.py:301`, `structured_excerpt_adapter.py:377`, `core_vision_chat.py:66`, `coding_reasoning.py:103`, `vision_ocr.py:40`, `voice/core.py:104/125`. Timeout đọc lần lượt là 1200, 60, 45, 20 và 10 giây tùy đường.
- **Private method được dùng như API public**, đã kiểm lại: `apps/harness/inference.py:66-76` gọi `gateway._timeout()`, `_verify_model`, `_select_auto_preset`, `_count_input_tokens`. Sau đó `inference.py:200` gọi `gateway.complete()`, hàm này mở một client mới, verify lại (`llama_gateway.py:302`) và đếm token lại (`:343`). Kết quả là mỗi lượt text tốn hai lần `GET /v1/models` và một lần tokenize thừa.
- **Wire format phân kỳ:**
  - Có 3 dialect `response_format`: `structured_profile.py:258`, `harness/inference.py:154` và `core_vision_chat.py:105-110`. ADR-183:31 đã ghi nhận một lỗi âm thầm thật do dialect gây ra.
  - Reasoning budget có hai cách viết: `presets.py:288` và `reasoning_profile.py:71`.
  - `response.json()` không có giới hạn kích thước (`llama_gateway.py:366`). Ở `harness/inference.py:167` và `summarizer.py:48`, kích thước chỉ được kiểm sau khi đã đệm toàn bộ body.
  - Đường **stream không kiểm `finish_reason`** (`inference.py:207-249`), trong khi đường non-stream từ chối câu bị cắt (`llama_gateway.py:373-392`). Hệ quả là UI web hiển thị câu bị cắt như câu bình thường.
- **Admission:**
  - Cơ chế duy nhất cho cả process là `setattr` lên 11 target, trong đó có cả private method (`apps/api/voice_admission.py:9-41`, `:60`).
  - `grounded.py:202-207` đọc `gpu_admission._coordinator`. Nhánh này không chạy được trong bất kỳ composition nào được hỗ trợ (ADR-177:250).
  - Ngoài voice, `models.yaml` khai `parallel: 1`, nhưng code có khoảng 23 `asyncio.Lock()` riêng rẽ. Route chat gốc (`apps/api/routes/chat.py:90`) không có lock nào.
  - Harness chép route gốc vào cùng process (`harness/main.py:62-70`), nên các route này đi vòng `product.admission`, trong khi `/props` quảng cáo `total_slots=1`.
- **Một sự cố CORE ra ít nhất 6 mã lỗi:** `llama_gateway_unavailable/timeout`, `structured_<phase>` 503, `coding_reasoning_failed`, `image_chat_model_failed`, `vision_unavailable`, `gateway_error`.

**Vì sao quan trọng.** Mỗi thay đổi xuyên suốt (seal, admission, timeout, giới hạn) phải sửa khoảng 10 chỗ và phải dựa vào registry test để không bỏ sót. Hành vi khác nhau theo từng đường. Một `/runs` có thể hết hạn 120 s chỉ vì một completion của route gốc đang chiếm slot duy nhất.

**Thiết kế đích**
```
src/infrastructure/inference/core_client.py
  RequestSpec (frozen): messages, max_tokens, temperature, reasoning_budget (một tên),
                        response_schema (một builder dialect), stream
  CoreClient   – dựng một lần từ ModelProfile, inject vào mọi adapter;
                 sở hữu CoreAdmission (semaphore theo profile.parallel,
                 deadline chờ hàng đợi tách khỏi deadline chạy)
  CoreSession  – một httpx.AsyncClient cho mỗi request scope:
                 verify_model, count_tokens, select_preset,
                 complete / complete_fitted(spec, plan) / stream
                 + đọc có giới hạn, classify_completion cho CẢ stream,
                 seal ADR-195 tại đúng một điểm, CoreError
  CoreError(code ∈ {unavailable, timeout, model_mismatch, invalid_reply,
                    incomplete, refused, budget})
```
LlamaGateway trở thành shim. Adapter chỉ còn dựng `RequestSpec` và parse kết quả. Admission đi vào qua constructor, nên xóa được `TARGETS` và `_coordinator`.

*Finding liên quan:* C1, C3, C7, C8, C9, C11, C12, Z2, Z4, Z14, Z-m2, H1, H5, H-m2, S6, S8, A3, R2, T14, C-m2.

### 2.3 Phân lớp bị đảo ngược, lõi nằm sai chỗ

**Vấn đề.** Code được viết trong `apps/api` trước (ngày 17/10) và chưa bao giờ được chuyển vào trong. Các tầng sau import nó tại chỗ, trái với AGENTS.md ("Keep domain logic independent of HTTP, databases, and inference implementations").

**Bằng chứng mạnh nhất**
- **Import ngược tầng:** có 11 cạnh infrastructure→apps trong 7 file và 3 cạnh application→apps. Ví dụ: `src/application/services/conversation_context.py:6` có `from apps.api.runtime.presets import PresetError, calculate_budget`; `src/infrastructure/inference/llama_adapter.py:11-16` import `apps.api.services.llama_gateway`; `src/infrastructure/qwen_query.py:9` có `from apps.api.services.files import file_io`, kéo theo starlette và mọi document processor.
- **Application gắn cứng vào Postgres:** `src/application/services/conversation_manager.py:12,23-31` import `sqlalchemy.ext.asyncio` và ba repo Postgres, rồi dựng chúng ở 6 method. Port `src/application/ports/repositories.py` không có importer nào, không đổi từ init, và thiếu `owner_id` cùng các method lease.
- **`apps/api/services` mới là tầng application thật:** các service tự dựng adapter (`coding_workflows.py:57`, `grounded.py:33` gọi `LlamaInferenceAdapter()`; `ingestion.py:34` gọi `QwenEmbedding()`). Harness import `apps.api.services.harness_tools/skill_tools` (`harness/service.py:8-9`). Bảy module route import `sqlalchemy.exc` (`routes/memory.py:12`).
- **`scripts/` chứa worker product:**
  - `src/infrastructure/qwen_embedding.py:19` khai `WORKER = ROOT / "scripts/qwen_ingestion_encoder.py"`. Worker này import `scripts.qwen_embedding_evaluation.QwenCpu`, có docstring "for evaluation only".
  - `qwen_query.py:26` đọc `configs/embedding-qwen-evaluation.json` ("for authorized offline comparison only").
  - Ngược lại, `src/infrastructure/coding_sandbox.py` chỉ dùng cho đánh giá lại nằm trong `src/`.

**Hiệu chỉnh của skeptic.** `apps/__init__.py` rỗng, nên import một service application không kéo FastAPI theo. Chi phí thật gồm ba thứ: lõi nằm sai chỗ, chu trình giữa gói `apps` và `src`, và coupling ngẫu nhiên.

**Thiết kế đích** (chiều phụ thuộc domain ← application ← infrastructure ← apps)
- `presets.py` là code thuần ("no HTTP or Docker operations"), chuyển sang `src/domain/token_budget.py`.
- `ModelProfile` chuyển sang `src/infrastructure/config/`. Gateway và CoreClient chuyển sang `src/infrastructure/inference/`. `file_io`/`finish_task` chuyển vào kernel dùng chung.
- ConversationManager nhận một unit-of-work hoặc repository factory qua port đã cập nhật.
- Các orchestrator có trạng thái (workflows, checks, ingestion, retrieval, grounded, memory) chuyển dần sang `src/application/orchestration/`, viết theo port. `apps/api` chỉ còn route và composition.
- Worker product chuyển sang `src/infrastructure/workers/`; `QwenCpu` và `verify_artifacts` chuyển sang `src/infrastructure/embedding/`.
- Lỗi persistence được dịch thành lỗi application tại tầng repo hoặc service.
- CI có contract import-linter: `src` không import `apps`, `domain` không import gì, route không import `sqlalchemy`.

*Finding liên quan:* C2, A1, A10, S2, P1, P2, P-m1, I2, I4, I-m3, Z3, Z13, Z-m3, H-m3, W7, T1, T-m3, X9, X20, X-m3, R7.

### 2.4 Composition bằng wrapper factory và cờ env

**Vấn đề.** Mỗi tính năng được thêm theo kiểu "mặc định tắt, không chạm main". Kết quả là các tính năng trở thành entrypoint thay thế cho nhau và cờ env mới, chứ không phải module đăng ký trên một app.

**Bằng chứng mạnh nhất**
- `apps/api/voice.py:56-74`, `apps/api/grounded_extract.py:40-58` và `apps/harness/main.py:55-72` đều dựng lại FastAPI từ `base.router.routes` trừ `DOCS`. `DOCS` được định nghĩa ở `grounded_extract.py:10` và `harness/main.py:20`, và viết inline lần thứ ba ở `voice.py:69`. Cả ba đều copy `dependency_overrides`/`exception_handlers` và bọc `base.router.lifespan_context`.
- **Loại trừ nhau và bỏ qua âm thầm:**
  - `grounded_extract.py:74-75` từ chối chạy cùng voice.
  - `harness/main.py:115-124` chỉ kiểm tra `ASSISTANT_HARNESS_ENABLED` và `ASSISTANT_AUTH_FILE`. Đặt `ASSISTANT_VOICE_ENABLED=1` hay `ASSISTANT_GROUNDED_EXTRACT_ENABLED=1` dưới `aevra serve` sẽ bị bỏ qua mà không báo lỗi.
  - Server product thật chính là wrapper "opt-in" này: `apps/cli/main.py:391-410` ghi `os.environ` rồi gọi `uvicorn.run(..., factory=True)`.
- **Lifespan viết tay:** `apps/api/storage/lifecycle.py:33-162` gán 14 `app.state.X = None` bằng tay, truyền phụ thuộc theo vị trí, và shutdown tuần tự không có `try` cho từng bước. Một bước shutdown raise sẽ bỏ qua luôn `engine.dispose()`. Đoạn `:105-109` bọc mọi initializer trong `except Exception … raise RuntimeError(...) from None`, nên không biết được capability nào hỏng.
- **Cấu hình tản mạn:** có 30 tên `ASSISTANT_*` và 18 cờ `*_ENABLED`, không có object settings. `ASSISTANT_AUTH_FILE` được đọc ở ít nhất 4 chỗ, có chỗ đọc lại mỗi request. Khi thiếu `DATABASE_URL`, memory, files và ingestion bị bỏ qua chỉ với một warning (`lifecycle.py:80`), rồi trả 503 lúc chạy.

**Có chủ đích:** có (ADR-175, 177, 180, 181). Nhưng như ADR-177:255 cho thấy, việc giữ `main.py` nguyên byte đã không bảo toàn được evidence voice.

**Thiết kế đích**
```
Settings (pydantic-settings, frozen; validator cho phụ thuộc giữa các cờ, fail-closed)
create_app(settings):
    async with AsyncExitStack() as stack:      # shutdown tự động, ngược thứ tự, an toàn khi lỗi
        for feature in FEATURES:               # conversations, files, ingestion, memory, checks,
            if feature.enabled(settings):      # workspace, harness, voice, grounded_extract …
                feature.register(app, settings, container, stack)
Container (dataclass có kiểu) → dependency có kiểu thay cho getattr(app.state, "...")
StartupError(capability, code) → log không lộ nội dung; chỉ redact lỗi có thể chứa DSN
```
Bảo đảm "mặc định tắt" bằng snapshot OpenAPI và route-set theo từng tổ hợp cờ, thay vì so object app. Đổi tên `apps/api/storage` thành `apps/api/composition`.

*Finding liên quan:* A2, A8, A9, A-m1, A-m2, A-m4, Z6, H13, I11.

### 2.5 Primitive hạ tầng bị chép thay vì chia sẻ

**Vấn đề.** Không thể sửa helper chung, nên mỗi milestone chép lại helper đó. Helper nằm ở module tính năng nào cần nó đầu tiên.

**Bằng chứng mạnh nhất**
- **Vòng đời owned-operation:**
  - Cùng một vòng lặp `while True: try: return await asyncio.shield(task) …` xuất hiện ở `apps/api/services/files.py:41-48` (`finish_task`), `src/application/services/web_fetch_tasks.py:20-28` (`finish_owned`) và `src/infrastructure/qwen_embedding.py:71-78` (`join_task`).
  - Khối `if self.admission.locked(): raise …busy; await self.admission.acquire()` có ở khoảng 30 file. Có khoảng 17 `shutdown()` gần giống nhau, và đã phân kỳ (vô hại): `retrieval.py:188` không loại `current_task`, còn `checks.py:366` thì có.
- **Sandbox và worker:**
  - Có 6 đến 7 builder bwrap: `check_runner.py:99`, `coding_sandbox.py:21`, `checkpoint_git.py:96`, `mcp_stdio.py:54`, `voice/sandbox.py:11`, `file_verifier.py:41`.
  - Có 7 wrapper client phía host, ví dụ `pdf_extractor.py:55-98`, `page_ocr.py:26-82`, `docx_processor.py:32-101`. Bản DOCX và XLSX chỉ khác nhau ở tên.
  - `check_runner.py:306` và `coding_sandbox.py:165` dùng `killpg` rồi `wait`. Đây đúng là kiểu mà ADR-179 đã đo được là trả về trước khi namespace thật sự chết.
  - `audio_worker.py:15-27` mượn `ocr_worker.child_output` và biến mọi exit code khác 0, kể cả ENOMEM, thành `audio_invalid_content`. Việc này đã từng che một lỗi decoder thật.
- **Store riêng có ký:**
  - `plan_checkpoints.py:59-73` và `harness_history.py:153-167` bootstrap khóa giống hệt nhau, nhưng kiểm tra quyền khác nhau (`st_mode & 0o077` so với `S_IMODE != 0o700`).
  - `harness_history.py:305-310` unlink file temp mà không kiểm, còn `checkpoint_storage.py:255-265` kiểm inode trước.
  - `research_sessions.py:205-223` chép lại `create_file` chỉ vì giới hạn 32 KiB bị cứng trong code.
- **Chính sách HTTP và JSON:**
  - Có 4 subclass `APIRoute` và 8 vòng đọc body.
  - FastAPI gọi `await request.body()` trước `solve_dependencies`. Vì vậy conversations, memory, grounded và retrieval **đệm body không giới hạn trước khi kiểm loopback, Origin và bearer** (A4, mức cao). `MessageSend.content` không có `max_length` (`routes/conversations.py:158`).
  - Pairing và session trình duyệt có hai bản (`harness/browser.py:42-101` và `api/voice_identity.py:28-94`), đã lệch nhau về TTL và độ dài mã.
  - Có hai hàm `digest` với `ensure_ascii` khác nhau (`history_summary.py:235-241` và `source_output_contract.py:52-58`).
  - `canonical()` nằm trong `mcp_adapter.py:51-64`, ném `McpError` và mang theo giới hạn 16 KiB ẩn.

**Vì sao quan trọng.** Một bản vá bảo mật hay cancellation phải tìm và áp ở 3 đến 11 chỗ. Phần lớn phân kỳ hiện tại là vô hại, riêng A4 là một khoảng trống thật (nhỏ, vì chỉ chạy trên localhost). Mỗi service mới bắt đầu bằng việc chép khoảng 40 dòng concurrency tinh vi.

**Thiết kế đích (kernel dùng chung)**
- `owned_tasks.py`: `spawn_owned`, `finish_owned`, `join_thread`. `owned_admission.py`: `OwnedOperations` với `admit()` nonqueued, phân biệt mode đọc và ghi, có `shutdown()`.
- `strict_json.py`: `loads_strict(raw, limit, max_depth)`, `dumps_canonical`, `digest`, có golden test theo byte.
- `private_store.py`: `PrivateDir` (pin root, kiểm dir/file, đọc ổn định, `create_file(limit)`, `replace` kiểm inode) và `SignedRecordCodec`.
- Sandbox: `SandboxSpec` sinh argv, cùng một supervisor duy nhất trên `sandbox_process.Sandbox` (info-fd và pidfd cho mọi họ, kể cả voice và check runner). Thêm `run_json_job` và `worker_main` dùng chung, và `native_child.py` với `NativeChildError(kind)`.
- `apps/api/core/http_guard.py` (`GuardedRoute(max_bytes, auth_first)`, `PRIVATE_HEADERS`, `read_bounded_json`) và `apps/api/core/browser_session.py` (`PairingSessions` có tham số TTL).
- Gộp DOCX và XLSX thành OOXML. `PgJournal` helper gồm `bounded_transaction`, `page_check`, `db_now` và `Lease`.

*Finding liên quan:* S1, R1, P3, P4, X7, Z7, R8, X13, H14, H15, I1, I3, I6, I7, I-m4, X-m4, X1, X2, W1, W2, W3, W6, W11, W-m3, W-m4, T3, T4, T5, T6, X5, X6, R12, P5, C15, C16, T-m4, R9, R11, R13, A4, A5, A6, H7, H8, H16, H18, Z-m1, W17, W18, S5.

### 2.6 Mô hình lỗi không có registry

**Vấn đề.** Mỗi tính năng tự định nghĩa từ vựng lỗi hữu hạn của riêng nó, và khi cần thì mượn kiểu lỗi nào đang nằm gần.

**Bằng chứng mạnh nhất**
- Có 50 class exception không có base chung, với các hình dạng `code`, `code,status_code`, `code,status`, chỉ `status_code`, hoặc không có gì. Có khoảng 1.100 đến 1.170 mã literal khác nhau trên 2.957 lệnh `raise`, và khoảng 322 handler bắt rộng.
- **Lỗi sai nghĩa:** `StoragePolicyError` (`file_storage_policy.py:45-53`, log `file_policy_rejected` ngay trong `__init__`) được dùng cho timeout model của grounded (`apps/api/services/grounded.py:61`) và cho vision (`vision_ocr.py:23`). `WorkspaceAccessError` cũng log trong `__init__` và được dùng cho lỗi model output, nên một reply hỏng có thể sinh tới 3 cảnh báo `workspace_access_rejected` mang tên tính năng khác.
- **Remap âm thầm:**
  - Constructor tự đổi mã: HookError thành `failed` (`tool_hooks.py:21-37`), SkillError thành `invalid_manifest` (`skill_contract.py:27-44`), McpError thành `invalid_response` (`mcp_adapter.py:29-45`).
  - `harness/main.py:103-109` biến mọi SkillError thành `skill_operation_denied` 409.
  - `harness/routes.py:220-231` biến InferenceFailure 422 `context_overflow` thành 502 `inference_unavailable`.
- **Mất ở client:** `apps/cli/client.py:156-160` bỏ body lỗi và chỉ còn `http_<status>`. Năm mã 503 khác nhau trở thành cùng một `http_503`, với cùng exit code như khi server không chạy.
- **Envelope không thống nhất:** `{"detail":{"code","message"}}` (`routes/conversations.py:70-76`), `{"detail":{"code"}}`, `{"code"}` ở top-level (`voice.py:81-98`) và `{"error":{…}}` (`harness/main.py:75-89`). `memory.py:119-153` dùng thang if/elif kết thúc bằng `else: status = 422`. Có 12 chỗ bắt `(OSError, ValueError, TypeError, KeyError, RuntimeError)` rồi trả 503, khiến bug lập trình trông như sự cố hạ tầng.

**Thiết kế đích**
```
src/shared/errors.py:  class CodedError(Exception)   # __init__ không có side effect
                         code: ErrorCode   (StrEnum theo bounded context, gom vào một registry)
                         category: Category (not_found|conflict|busy|invalid_input|unavailable|timeout…)
apps/api/errors.py:    CATEGORY_STATUS + MỘT exception handler + MỘT envelope
```
- Mã lạ thì làm test fail, thay vì bị remap.
- Adapter bọc `CoreError` nhưng giữ nguyên mã.
- CLI đọc `detail.code` hoặc `error.code` (khớp một pattern allowlist) và chỉ dùng HTTP status làm fallback.
- Log ở biên kèm `type(exc).__name__`.
- Có test kiểm "mọi literal được raise đều đã đăng ký".

*Finding liên quan:* H10, H-m1, C9, C-m1, A7, S7, R6, R-m2, P9, P10, I8, X11, X12, W4, W5, Z8, Z-m3, T18.

### 2.7 Dữ liệu không kiểu, state machine nằm trong dict và JSONB

**Vấn đề.** Các khái niệm domain như vòng đời run, trạng thái workflow, preset và scope chưa bao giờ được mô hình hóa. Mỗi tầng tự khai lại từ vựng bằng chuỗi.

**Bằng chứng mạnh nhất**
- **Harness run:** định nghĩa chính thức duy nhất của vòng đời là validator trong store tùy chọn `src/infrastructure/harness_history.py:16-24` và `:88-92`. Store này đọc dict của tầng apps qua `str(row["owner"])` (`:109-127`). Ở memory mode, `event()` (`apps/harness/service.py:148-167`) không kiểm tra gì. Tập trạng thái kết thúc bị chép ở `service.py:18-19` và `apps/cli/main.py:583-588`.
- **Coding workflow:** `WorkflowRecord.value: dict` có 22 khóa (`apps/api/services/coding_workflows.py:41`, `:243-267`) và 15 chuỗi trạng thái, không có enum. Trạng thái uncertain được phát hiện bằng substring (`controlled_coding_workflows.py:82-86`). Tham số ẩn đi qua ContextVar (`:32-33`). `save()` kích hook dựa trên chuỗi trạng thái (`:66-74`).
- **Check job:**
  - `validate_core` dài khoảng 140 dòng `set(x) != {...}` (`src/infrastructure/check_job_records.py:112-253`), dùng chỉ số vị trí kiểu `native[3]`.
  - Kết quả trả qua một out-parameter `evidence` (`check_jobs.py:498-602`).
  - `check_runner.py:268` đặt `outcome="running"`, giá trị mà validator không chấp nhận. Khi gặp exception lạ, journal không ghi được và job kẹt ở trạng thái `starting`.
- **Định danh nằm trong JSONB:**
  - `_storage_namespace` (`file_journal.py:57-65`, SQL thô ở `apps/api/services/retrieval.py:66`), chọn có chủ đích theo ADR-024:19.
  - `owner_id` (`conversation_repository.py:211-218`): `_owner_filter(None)` trả `true()`, nên mặc định là **không scope**, tức fail-open.
  - Lease inference là float epoch trong JSONB (`inference_run_repository.py:241-268`), theo ADR-017.
- **Domain chỉ còn vỏ:** `src/domain` có 69 dòng, không đổi từ init. Từ vựng preset lặp ở khoảng 10 chỗ. `ProductInference.prepare` nhận 15 tham số, `compose_context` 14, và `reduce_history` dài 323 dòng.

**Thiết kế đích**
- `src/domain/` chứa `RunState`, `RunErrorCode`, `RunRecord` và `transition()` (luôn được kiểm, kể cả ở memory mode); `WorkflowState` kèm bảng chuyển trạng thái; `Preset`/`Profile` lấy từ `RuntimePreset` và dùng chung cho route, CLI, repo và DB CHECK.
- Record dạng frozen dataclass hoặc pydantic với `to_record`/`from_record`, validate tại đúng một chỗ. Journal trả về đối tượng có kiểu. `AttemptResult` thay cho out-parameter.
- `ContextRequest`, `ContextPolicy` (enum mode) và `ContextPorts` thay cho 11 đến 15 kwargs. `reduce_history` được tách theo strategy.
- Scope trở thành bắt buộc: `owner: UUID` cho đường người dùng, và `Scope.UNSCOPED` tường minh cho đường bảo trì.
- Migration cộng thêm, đưa `owner_id`, `storage_namespace` và lease lên cột có index (xem Pha 9).

*Finding liên quan:* H2, H3, H4, H11, H17, C4, C11, C14, A11, A-m4, S3, S4, S9, S13, R5, R10, R14, P2, P6, P7, P12, P13, P-m2, I6, I10, I-m2, X10, X16, X19, X-m5, W10, W13, W15, Z11, Z12.

### 2.8 Cấu hình bị nhân bản thành literal, kèm I/O chặn rải rác

**Bằng chứng mạnh nhất**
- **`configs/models.yaml` không phải nguồn duy nhất:**
  - File khai `context_size: 32768`, `port: 8080` và `parallel: 1`. Server lấy context size từ đó (`scripts/start-core.py:37`), nhưng app lại dùng `CONTEXT_SIZE = 32768` (`apps/api/runtime/presets.py:26`) và các literal ở `coding_reasoning.py:112`, `harness/browser.py:331`, `voice/native.py:152`. Hai bên có thể lệch nhau mà không ai phát hiện.
  - `get_model_profile` parse YAML ở mỗi lần gọi (`apps/api/core/model_config.py:14-20`), có 11 chỗ gọi và nhiều chỗ nằm trong handler async.
  - Hàm này chấp nhận host `localhost` hoặc `::1` nhưng luôn trả `http://127.0.0.1:{port}` (`:33`, `:42`).
- **Endpoint và model được pin bằng literal:**
  - `structured_profile.py:208` cho phép cả cổng benchmark 18080 trong adapter product; `structured_excerpt_adapter.py:372` và `core_vision_chat.py:63` cũng pin địa chỉ. Chuỗi `qwen3.5-9b-core` xuất hiện 10 lần trong 7 file.
  - `voice/core.py:66-79` đòi các cờ `--slots` và `--offline`, mà không launcher nào được commit truyền vào. Launcher cho làn voice chỉ tồn tại trong scratchpad của phiên nghiệm thu (`docs/progress/D74_B4_OWNER_ACCEPTANCE.md:34`).
- **Policy đã duyệt khác với thứ được thực thi:**
  - `check_policy.py:132-158` đưa các giới hạn vào bản review để owner duyệt, nhưng `check_runner.py:162-168` lại hard-code `--as=536870912 --cpu=2:3 …`.
  - `browser_runtime.py:35-63` đòi file config phải khớp đúng các hằng số trong code.
  - Cổng kiểm revision schema rải ở `apps/api/storage/memory.py:33` (đúng `'0006'`), `storage/files.py:15`, `services/ingestion.py:59` và `scripts/release_recovery_drill.py:225`. ADR-191 vì thế cần một release riêng chỉ để sửa các cổng này.
- **I/O chặn** (cùng gốc là thiếu object cấu hình và thiếu cache):
  - `history.save` đọc lại 64 record và gọi 2 lần fsync ngay trên event loop.
  - Asset UI hash lại 9 MB mỗi lần tải trang.
  - Guard voice quét `/proc` 40 lần mỗi giây (`voice/ipc.py:103-105`).
  - Mỗi truy vấn retrieval khởi động **2 worker uv lạnh và hash lại khoảng 1,2 GB trọng số** (`qwen_query.py:39-40`).

**Thiết kế đích**
- `ModelProfile` frozen (`model_id`, `base_url`, `context_size`, `parallel`, `digests`) được nạp một lần lúc khởi động và inject vào nơi cần. Presets lấy context từ đó. Adapter vẫn pin danh tính CORE, nhưng so với profile chứ không so với literal.
- Một hàm `core_command(profile, purpose)` duy nhất, dùng cho launcher, cho việc sinh và kiểm tra compose, và cho `BorrowedCore`.
- Thêm `HarnessSettings`, cho `ExecutionPolicy` sinh argv prlimit, dùng registry `VoiceRoleSpec` và registry `schema_compat`.
- `history.save` chạy qua `to_thread` và giữ index trong bộ nhớ. Asset được verify một lần lúc khởi động. Guard voice chạy ở 4 Hz trong thread. Encoder truy vấn chạy thường trú.

*Finding liên quan:* C10, Z9, A12, A13, S10, S14, S-m3, H9, H12, I5, I12, I14, I15, I16, X3, X4, X14, X18, X22, W12, W14, T8, T11, T15, T16, R15, R-m1, P8, P14.

### 2.9 Code lab và code chưa nối dây nằm lẫn với product

**Bằng chứng mạnh nhất**
- Khoảng 59 đến 66 module (≈11,5 đến 12,5 nghìn dòng, khoảng 20% trong 57 nghìn dòng product) không được entrypoint nào gọi tới.
- **Harness:**
  - `BoundedPlanRunner`, `McpAdapter`, `PinnedPythonStdio` và `PlanCheckpointStore` (khoảng 1.550 dòng) chỉ được test dùng. `ProductHarness.execute` là một vòng "tối đa 4 lần đọc rồi 1 completion" viết riêng (`service.py:214-269`).
  - Đang có ba mô hình trạng thái run mâu thuẫn: product, planner và `HARNESS_PRODUCT_DESIGN.md:37`. ADR-180, quyết định 1, định tái dùng planner, hook và approval; ADR-181 thì có chủ đích không nối.
  - `GenerationJobs` không có backend (`main.py:42`), nên 5 route cùng 2 nhóm lệnh CLI luôn trả `generation_capability_unavailable`.
- **Các stack khác chỉ có test dùng:**
  - Stack research: 4.493 dòng cộng 1.368 dòng (ADR-069, ADR-074 đến 078, ADR-084). Discovery recovery hard-code một archive D53 duy nhất (`discovery_recovery_policy.py:117-127`).
  - 3 biến thể coding workflow (ADR-129/138).
  - Vision và video, đang chờ VISION-PROD-001.
  - Browser động khoảng 1.335 dòng, cùng report export và Brave.
- **`scripts/`:**
  - Có 82 file, trong đó 79 file sửa lần cuối trong khoảng 17 đến 24/10. Khoảng 50 file là campaign nghiên cứu chạy một lần. 74 trên 375 file test import `scripts.*`.
  - 13 script gọi `core_snapshot` với PID 37256 hard-code (`scripts/asr_evaluation_runner.py:219`), chọn có chủ đích theo ADR-126/127. Hiện không script nào trong số đó chạy được.
  - Campaign đã retire được tắt bằng hằng số trong source.
- **Product bị benchmark định hình:**
  - `summary_debug` và `inspect_layers` đi xuyên 4 tầng product nhưng chỉ benchmark bật (`apps/harness/inference.py:57-58`).
  - `benchmarks/context_summary_v2.py:310-327` gán lại biến global của `history_summary` lúc chạy và đóng băng hash file của nó.
  - Còn hai file chết được track: `apps/api/main.py.bak` và `docker-compose.yaml.bak`.

**Có chủ đích:** có, theo từng tính năng ("No route/default activation"). Vấn đề không nằm ở việc tạm cất code, mà ở chỗ **không có ranh giới hay đánh dấu**. Hệ quả là mọi refactor ở các chủ đề 2.2 đến 2.5 đều phải giữ cho một bề mặt lớn không dùng tới vẫn biên dịch được và vẫn xanh.

**Thiết kế đích**
- Đưa code lab vào `src/labs/<feature>/`, mỗi thư mục có README ghi ADR, trạng thái và điều kiện kích hoạt.
- CI có báo cáo reachability.
- Chia lại `scripts/`: `src/infrastructure/workers/` cho product, `scripts/` cho công cụ vận hành (có README), và `research/<milestone>/` cho campaign, dùng pytest marker `research` chạy trong job riêng. Cách khác là xóa hẳn và dựa vào tag git cùng hash evidence.
- Thay các cờ debug bằng một recorder/observer được inject.

*Finding liên quan:* Z5, Z10, Z-m4, H6, C5, C6, C13, A14, A-m3, R3, R4, R16, S11, S12, P11, I13, I-m1, X8, X15, X17, W8, W16, T2, T7, T9, T12 (một phần), T13, T14, T17, T-m3.

### 2.10 Chốt fail-closed không có đường phục hồi và các lỗi chạm người dùng

**Vấn đề.** Nhiều cơ chế an toàn đúng về nguyên tắc nhưng không có đường ra, hoặc tính giới hạn theo vòng đời kho/process thay vì theo những gì đang thực sự sống. Đây là nơi sự "tạm bợ" gây hại thật nhất.

**Bằng chứng mạnh nhất**
- **Check job không bao giờ được giải phóng (mức cao):** `check_policy.py:16-17` khai `MAX_JOBS = 32` và `MAX_OWNER_JOBS = 8`. `check_jobs.py:321-327` đếm mọi job đang được giữ ở mọi trạng thái, và file này không có đường xóa (đã grep lại). Mỗi coding workflow đề xuất một check (`coding_workflows.py:390`). ADR-060 chọn "no retirement" cho v1, trong khi harness runs đã có `runs remove`.
- **Một capture dở chặn tất cả:** `check_jobs.py:334-341` gọi `os.mkdir` trước khi ghi dữ liệu. Nếu bị hủy hoặc timeout, nó để lại thư mục thiếu manifest. Từ đó capture, list và cả `CheckJobStore.__init__` đều trả `checks_storage_recovery_required` 503, nên khi bật `ASSISTANT_CHECKS_ENABLED=1` **API không khởi động được**. Checkpoint có cùng dạng lỗi: `checkpoints.py:277` gọi mkdir trước git, dẫn tới `checkpoint_recovery_required` cho mọi owner. `tests/test_checkpoints.py:204-205` khẳng định đúng hành vi này, và không có công cụ nào để sửa.
- **Coding workflow:** 16 record toàn cục và 4 record mỗi owner, không có eviction (`coding_workflows.py:231-236`, chủ đích theo ADR-062), trong khi PatchService có evict (`patches.py:112-119`). Một lock dùng chung cho cả đọc và ghi (`coding_workflows.py:83-97`, `:439-451`), nên GET trong 60 s generation nhận 429. Ngoài ra `patch_busy` của một sibling sẽ đốt mất lượt model one-shot (`:305-312`).
- **Voice:** câu trả lời có "github.com", "server-side" hay "API-key" bị chặn ở `reading_policy.py:61-68` và hiện ra dưới dạng `dependency_failed`. Worker TTS không có envelope lỗi theo request (`tts_runtime.py:218-256`), nên một lần từ chối nội dung sẽ giết cả nhóm model.

**Thiết kế đích**
- Thêm thao tác retention tường minh: xóa job hoặc record đã kết thúc và chỉ đếm những thứ đang sống.
- Publish capture theo kiểu stage rồi rename atomic.
- Thêm `recover_incomplete()` cho operator, cách ly bằng rename chứ không xóa.
- Lỗi của checks không được làm hỏng lifespan; service chỉ chuyển sang trạng thái unavailable.
- Tách quyền đọc trạng thái khỏi admission ghi.
- Worker thường trú trả envelope lỗi theo từng request.

Phần lớn các lựa chọn hiện tại có chủ đích (ADR-060, 062, 059, 182, 174, 175), nên mỗi thay đổi cần một ADR mới.

*Finding liên quan:* X-m1, X-m2, I9, S-m1, S-m2, P-m4, W-m1, W-m2, X21, T-m1, T-m2, C-m2.

---

## 3. Harness

### 3.1 Cấu trúc hiện tại

| File | Dòng | Trách nhiệm |
|---|---|---|
| `apps/harness/main.py` | 124 | `create_app` (đọc env) và `compose()`: chép route gốc, bọc lifespan gốc, tạo `ProductHarness` và `GenerationJobs` |
| `apps/harness/routes.py` | 412 | `HarnessRoute(ProtectedStatelessRoute)`, `RunInput`/`ChatInput`, `/status`, `/runs`, `/chat`, `/context/*`, `/skills/*`, `/generations/*` |
| `apps/harness/service.py` | 344 | `ProductHarness`: runs, tasks, admission, skills, review_bytes, context_archive, summary_cache, history, history_broken |
| `apps/harness/browser.py` | 492 | `BrowserSessions`, `bounded_json`, middleware, các route UI, SSE `/v1/chat/completions`, `/props`, asset |
| `apps/harness/inference.py` | 250 | `ProductInference.prepare/complete/stream`, dựng 3 httpx client |
| `apps/harness/summarizer.py`, `generation.py`, `assets.py` | 67, 133, 148 | `GatewaySummarizer`, `GenerationJobs` (không có backend), bundle UI được pin |
| Phụ thuộc mượn | | `apps/api/services/harness_tools.py`, `skill_tools.py`, `apps/api/routes/chat.py` (`ProtectedStatelessRoute`), `apps/api/voice_routes.local_browser`, `mcp_adapter.canonical`, `src/infrastructure/harness_history.py` |
| Client | | `apps/cli/main.py` (695 dòng; `execute()` là chuỗi if 290 dòng), `apps/cli/client.py` (166), `apps/desktop/*` |

**Luồng request hiện nay**

- **A. Khởi động (`aevra serve`).**
  1. `apps/cli/main.py:391-410` ghi `os.environ["ASSISTANT_HARNESS_ENABLED"]="1"` và `ASSISTANT_AUTH_FILE`, rồi gọi `uvicorn.run("apps.harness.main:create_app", factory=True)`.
  2. `create_app` (`main.py:115-124`) đọc lại env và lấy `apps.api.main.app` làm base.
  3. `compose()` chép mọi route gốc (trừ DOCS) sang app "Aevra", rồi include harness router và `register_browser`.
  4. Lifespan bọc lifespan gốc và tạo `ProductHarness(ProductInference(), getattr(app.state, "workspace_service", None), history)` cùng `GenerationJobs(product.admission)`.
- **B. CLI chat (`POST /api/v1/harness/chat`, `routes.py:190-233`).**
  1. `HarnessRoute` auth bearer lần 1, đòi Content-Type JSON kể cả với GET/DELETE, và đệm body.
  2. `owner_service` auth lần 2 và đọc lại file auth.
  3. Route tự dựng closure `archive/recall` trên `service.context_archive` và gắn summary cache.
  4. `asyncio.timeout(120)` bọc **cả thời gian chờ lock** lẫn `async with service.admission`, sau đó gọi `inference.complete()`.
  5. `prepare()` mở httpx client riêng, gọi `gateway._verify_model/_select_auto_preset/_count_input_tokens`, rồi `compose_context` hoặc `compose_reduced_context`, và đếm lại cho report.
  6. `gateway.complete()` mở client mới, verify lại và đếm lại.
  7. Lỗi được ánh xạ inline: `InferenceFailure`, `ValueError` và `Exception` đều thành 502 `inference_unavailable`, hoặc `ContextError` nếu có `history_policy`.
- **C. Run (`POST /runs`, `service.py:180-289`).**
  1. `start()` kiểm `closed`, `history_broken` và capacity 64/8.
  2. `installed()` duyệt `skills.installed` và dùng `authorize(..., permissions[0])` làm probe kiểm skill còn sống.
  3. Dựng row dạng dict và gọi `event("created")`. Lệnh này gọi `history.save()` đồng bộ: load 64 record, rồi 2 lần fsync trên event loop.
  4. `create_task(execute)`, rồi `timeout(120)` và `admission`.
  5. Dùng `SkillToolRun` (dẫn tới `WorkspaceToolRun`, **bỏ qua `GuardedToolRun`**) hoặc `HarnessToolRun` (dẫn tới `GuardedToolRun` rồi `WorkspaceToolRun`) để chạy tối đa 4 tool. Mỗi tool qua `canonical(tool.model_dump())` của MCP.
  6. Gọi `authorize`, rồi `inference.complete`, rồi `authorize` lần nữa, và cuối cùng `event("succeeded")`.
  7. Lỗi: `SkillError` thành `skill_revoked`, `TimeoutError` thành `run_timeout`, mọi lỗi khác thành `run_failed`.
- **D. UI web (`POST /v1/chat/completions`, `browser.py:369-432`).**
  1. Middleware `:169-224` xử lý cookie session (gọi `load_principals` mỗi request), rồi gọi `local_browser` mượn từ voice, trên một `Request` được dựng lại với query string rỗng. CSRF header `x-harness-ui` được viết inline.
  2. `bounded_json`: TimeoutError không được bắt nên lọt thành 500.
  3. Validate tay, giới hạn `max_tokens` trong khoảng 512 đến 4096.
  4. `StreamingResponse`, rồi `timeout(120)` và `admission`, rồi `inference.stream()`. Đây là client thứ ba, và **không kiểm `finish_reason`**.
  5. Mọi lỗi đều thành một chuỗi SSE cố định `inference_unavailable`.
- **E. Generation (`/generations`).** Luôn trả `generation_capability_unavailable`, vì `compose()` không cho inject backend.
- **F. Route gốc trong cùng process.** `/api/v1/chat/completions`, conversations, grounded và coding workflows gọi CORE mà không qua `product.admission`.
- **G. Asset.** `asset()` đọc lại `receipt.json`, đọc lại file và sha256 bundle 9 MB ở mỗi request, với header `no-store`.

### 3.2 Những gì tạm bợ

1. **Chính sách CORE không có chủ sở hữu (H1, H-m2, C-m1).**
   - Envelope 3 dòng được chép ở `routes.py:214`, `service.py:217`, `browser.py:413` và `generation.py:55`. Mỗi bản ánh xạ lỗi một kiểu.
   - Deadline tính cả thời gian xếp hàng, nên một `/runs` đứng sau một stream 100 s chỉ còn vài giây để chạy.
   - Input sai của client thành 502: `ChatInput.messages` là `list[dict[str,str]]`, nên role `tool` hoặc prompt quá dài thành `inference_unavailable` thay vì 422.
   - Route gốc đi vòng admission.
2. **Vòng đời run không có kiểu (H2).** Bảng trạng thái và mã lỗi chỉ tồn tại trong store tùy chọn, và store này đọc dict của tầng apps. Ở memory mode không có gì được kiểm. Tập trạng thái kết thúc bị chép 3 chỗ.
3. **`ProductHarness` là service-locator (H3).**
   - Route thò tay trực tiếp: `service.context_archive.put`, `service.admission`, `service.runs.items()` cùng với `row["owner"]`, `service.skills.uninstall`, `sessions.sessions.pop`.
   - Chỉ `start()` kiểm `closed` và capacity.
   - Một class gánh 4 mối quan tâm khác nhau.
4. **Hack kiểm skill còn sống (H4).** `authorize(permissions[0])` được dùng làm probe, nên GET `/skills/installations/{id}` ghi log audit `skill_tool_authorized`. `review_bytes` là một dict song song. Lỗi "tool không có trong manifest" bị đổi nhãn thành `skill_revoked`.
5. **Inference xuyên private method và gọi đôi (H5, C-m2).** Mỗi completion text gọi `/v1/models` hai lần. Stream không phân loại completion.
6. **Đường evidence chồng lớp (H6, H7).**
   - 4 vòng validate, 3 cap 8-attempt không bao giờ chạm tới (vì giới hạn tool là 4), và 3 timeout lồng nhau.
   - Run có skill bỏ qua `GuardedToolRun`, nên mất audit `tool_hook_event` và mất kiểm `closing`.
   - Planner, MCP và checkpoint, ba thứ mà ADR-180 định tái dùng, vẫn chưa được nối.
7. **Biên trình duyệt chép từ voice (H8, H18).**
   - Có 3 trình đọc body; từ chối ở biên bị log là `voice_browser_boundary_denied`.
   - Có hai envelope lỗi.
   - Route `ui-pairings` nằm ngoài router nên ngoài audit.
   - Một lệnh `curl` GET thuần nhận 415.
8. **Lỗi (H10, H-m1).** Mọi `SkillError` đều thành 409 `skill_operation_denied`, và CLI bỏ hết mã.
9. **Vấn đề nhỏ:**
   - I/O chặn: history, asset, auth hai lần mỗi request (H9).
   - 14 kwargs và literal lặp ở server, CLI và composer (H11).
   - 120 s, 32768, 4096 và nhãn `/status` chép tay (H12).
   - Cấu hình đi qua `os.environ` và `app.state` (H13).
   - Primitive store bị chép (H14). Helper nằm sai module (H15).
   - `GenerationJobs` chép coordinator (H16). CLI REPL giữ ngữ nghĩa history của server (H17).
   - Service context import `apps.api.runtime` (H-m3).

### 3.3 Những gì không tạm bợ (giữ nguyên hành vi)

- Mặc định tắt. `compose()` lồng lifespan gốc và join task product trước khi tài nguyên gốc đóng (`main.py:27-53`).
- Biên bảo mật cục bộ:
  - CLI chỉ chấp nhận URL loopback trực tiếp, tắt redirect và proxy.
  - Token mở bằng `O_NOFOLLOW` và kiểm quyền chỉ chủ sở hữu.
  - Mã pairing dùng một lần, đi qua fragment hoặc stdin, không bao giờ qua argv.
  - Cookie `HttpOnly SameSite=Strict`, CSP dùng hash.
- Bundle UI được pin chặt: checksum archive, receipt SHA-256 cho từng file, giải nén tar có hardening, không có fallback "latest" (`assets.py`).
- `harness_history` fail-closed: HMAC, kiểm schema và chuyển trạng thái, publish atomic có fsync, flock, và run đang chạy thành `interrupted` khi restart (ADR-182).
- Cancellation có kỷ luật: worker bị hủy và được await; client ngắt kết nối thì đóng stream upstream và nhả admission.
- `SkillRegistry`, `ApprovalStore`, `GuardedToolRun`, `WorkflowControl` và `McpAdapter` nhỏ, bất biến và có test riêng.

### 3.4 Kiến trúc đích

```
apps/harness/http/                         (mỏng: parse → gọi service → trả)
  api_routes.py      HarnessRoute riêng: auth đúng 1 lần (principal vào request.state),
                     JSON chỉ khi có body, audit mọi route (kể cả ui-pairings)
  browser_routes.py  dùng PairingSessions + read_bounded_json chung với voice
  errors.py          MỘT handler: CodedError → status theo registry, MỘT envelope
  settings.py        HarnessSettings (frozen) → compose(settings); không đọc env mỗi request

src/application/harness/
  chat_service.py      ChatService.complete/stream(owner, ChatRequest)
                       – ContextComposer(ContextRequest, ContextPolicy, ContextPorts)
                       – core.admit(queue_deadline) + execution_deadline
                       – map lỗi MỘT lần (422 cho lỗi context, 502/503/504 cho backend)
  run_coordinator.py   start/get/list/cancel/remove/close; OwnedJobTable dùng chung
                       với GenerationJobs; RunRecord.transition() luôn được kiểm
  evidence_reader.py   GuardedToolRun + WorkspaceToolRun, MỘT budget;
                       skill = authorize-callback (giữ hook audit cho run có skill)
  skill_catalog.py     SkillRegistry.find(owner, ws, id) / require_live(); review bytes
                       nằm trong SkillReview
  context_cache.py     ContextArchive + SummaryCache
  ports.py             CorePort, HistoryPort, WorkspacePort

src/domain/harness_run.py   RunState, RunErrorCode, RunRecord, transition()

src/infrastructure/
  inference/core_client.py  CoreClient + CoreAdmission (DÙNG CHUNG với route gốc)
  harness_history.py        serialize RunRecord; save qua to_thread + index in-memory
```

**Luồng đích**
- **`/chat`:** route gọi `ChatService.complete(owner, ChatRequest)` với messages có kiểu, nên input sai thành 422 ngay tại biên. Bên trong: composer, rồi `CoreSession.complete_fitted()` (không verify hay đếm lại), trả `ChatResult` hoặc `CodedError`.
- **`/runs`:** route gọi `RunCoordinator.start()`, tạo `RunRecord("created")`. Task gồm `EvidenceReader.read(tools, budget)`, rồi `ChatService.complete()`, rồi `RunRecord.transition("succeeded")`, rồi `HistoryPort.save()` chạy ngoài event loop.
- **UI:** route gọi `ChatService.stream()`, sang `CoreSession.stream()`. Khi `finish_reason != "stop"`, phát SSE với mã `incomplete_completion` từ registry.
- **Generation:** chỉ đăng ký route khi có backend.
- **Asset:** verify receipt một lần lúc khởi động; với đường `_app/immutable` có hash thì cho cache immutable.

**Các quyết định cần owner**
1. Planner, MCP và checkpoint: nối vào `RunCoordinator` (cho `execute` chạy `BoundedPlanRunner` với catalog PlanTool chỉ đọc, từ đó có checkpoint và resume), hay chuyển sang `src/labs/` và ngừng mở rộng. Đây là việc cỡ L.
2. Deadline: có tách thời gian chờ hàng đợi khỏi ngân sách chạy 120 s hay không. Ngân sách này do ADR-181 cố định.
3. Đưa route CORE gốc trong cùng process vào `CoreAdmission` chung. Việc này làm thay đổi hành vi đồng thời của route gốc.
4. Thống nhất envelope lỗi cho `/api/v1/harness` và cho đường tương thích OpenAI.

### 3.5 Thứ tự chuyển đổi trong harness

1. **Thuộc Pha 1.**
   - Gõ kiểu `ChatInput.messages` và trả 422 cho các lỗi context.
   - CLI đọc mã lỗi từ server.
   - `HarnessRoute` có guard riêng.
   - `bounded_json` chuyển TimeoutError thành một mã hữu hạn.
   - Stream kiểm `finish_reason`.
2. **Có thể làm sớm, không cần CoreClient.** Trích `CoreAdmission` và `map_inference_error()` dùng chung cho 4 đường, giữ nguyên hành vi.
3. **Thuộc Pha 7.**
   - Thêm `RunRecord` và `transition()`.
   - Chuyển `/chat` vào `ChatService`.
   - Tách `ProductHarness`.
   - Thêm `SkillRegistry.find/require_live`.
   - Thêm `EvidenceReader`.
4. **Thuộc Pha 4.** `PairingSessions` dùng chung với voice; `OwnedJobTable` dùng chung với `GenerationJobs`.
5. **Thuộc Pha 6.** `ProductInference` chuyển sang `CoreSession`, bỏ private method và bỏ round-trip đôi.

---

## 4. Lộ trình cải tổ

Nguyên tắc chung cho mọi pha:
- Chia thành PR nhỏ, dùng prefix `fix:`/`feat:`/`docs:`. Mỗi thay đổi có regression test cho các trường hợp lỗi, cancel và biên. Không đụng vào các chỉnh sửa không liên quan trong worktree.
- Kiểm tra tập trung bằng `uv run --no-sync python -m pytest <tệp> -q`, cùng `uv tool run --offline ruff check --isolated --select E4,E7,E9,F` và `ruff format --check`.
- Ở các mốc của pha: `uv run --no-sync python -m pytest tests benchmarks/tests -q --basetemp=<thư mục trên đĩa>`, vì `/tmp` là tmpfs nhỏ. Các mốc lớn chạy thêm `scripts/full_regression.py`. Ghi lại lệnh, số test, số skip, và tách rõ test phần mềm với phép đo chất lượng model.
- Không restart service dùng chung. Benchmark hay smoke có gọi CORE chỉ chạy khi owner mở cửa sổ host.

| Pha | Nội dung | Công sức | Rủi ro | ADR | Owner duyệt |
|---|---|---|---|---|---|
| 0 | Neo evidence vào hành vi; guardrail đo lường | S | thấp | có | **có** |
| 1 | Sửa nhanh các lỗi chạm người dùng | S (khoảng 10 mục) | thấp | phần lớn không | thông báo |
| 2 | Đường phục hồi cho các chốt fail-closed | M | trung bình | có | **có** |
| 3 | Tách code lab, phân loại `scripts/` | M | thấp | có | **có** (retire/xóa) |
| 4 | Kernel dùng chung | M | thấp–TB | có | thông báo |
| 5 | Đưa lõi vào đúng tầng, import-linter | M | trung bình | có | thông báo |
| 6 | CoreClient, CoreAdmission, CoreError | L | **cao** | có | **có**, cần cửa sổ CORE |
| 7 | Tái cấu trúc harness | M | trung bình | có | **có** |
| 8 | Một composition root và Settings | M/L | TB–cao | có | **có** |
| 9 | Registry lỗi, record có kiểu, cột DB | L | trung bình | có | **có** (migration, envelope) |

Lý do sắp xếp:
- Pha 0 đi trước vì mọi bước sau đều vi phạm quy tắc byte hiện hành.
- Pha 1 và 2 chạm người dùng nên làm sớm.
- Pha 3 đi trước 4 đến 6 vì nó thu nhỏ bề mặt mà các refactor phải mang theo.
- Pha 6 cần kernel (Pha 4) và lõi đã ở đúng tầng (Pha 5).
- Bước 1 đến 4 của harness (mục 3.5) chạy song song được với Pha 4 và 5.

**Pha 0 — Quản trị và guardrail**
- *Phạm vi:*
  - Một ADR mới thay các điều khoản byte-identical. Evidence ghi commit SHA và tag; "preserve" được hiểu là receipt hành vi còn xanh.
  - Hợp nhất phải giữ byte request gửi tới CORE (capture test) và giữ output canonical (golden). Thay đổi nào làm khác đi thì phải benchmark lại.
  - Guardrail ở chế độ chỉ báo cáo: contract import-linter, script reachability. `full_regression.py` mở rộng freeze sang `benchmarks/` và thêm wall timeout (T13).
- *Module:* `docs/ADR/`, `scripts/full_regression.py`, CI.
- *Rủi ro:* thấp.
- *ADR và owner:* có. Owner phải duyệt cách diễn giải dòng "Preserve passing components" trong AGENTS.md.
- *Kiểm chứng:* các manifest evidence cũ vẫn xác minh được tại tag; CI xanh.

**Pha 1 — Sửa nhanh**
- *Phạm vi:*
  - (a) CLI parse `detail.code`/`error.code` (H-m1).
  - (b) Harness: gõ kiểu messages, trả 422 cho `context_overflow` và `strict_context_would_trim`, bắt TimeoutError của `bounded_json` (H1, C-m1, H8).
  - (c) Stream kiểm `finish_reason` (C-m2).
  - (d) `HarnessRoute` có guard riêng và `ui-pairings` vào router (H18).
  - (e) Xóa `*.bak`, nhánh `preset=None`, nhánh publisher chết và `WorkingStateError` (A14, Z-m4, C13, X8, C9).
  - (f) Argv prlimit sinh từ `execution_policy` (X3).
  - (g) `lock_timeout` cho `file_journal`; memory gọi `_bounded()` trước advisory lock (I6, I-m4).
  - (h) Chặn `main()` mặc định của `postgres_recovery_acceptance`; đổi assert thành RuntimeError có mã (T12).
  - (i) Bỏ kwargs chết của `run_worker` (C16, T-m4).
  - (j) Validate cấu hình embedding một lần lúc start; lệch cấu hình trả 503 (P8).
- *Rủi ro:* thấp. Mục (b) và (c) đổi status code và hành vi UI, nên PR cần ghi rõ và kèm screenshot UI.
- *ADR:* chỉ (b) và (c) cần một ghi chú bổ sung cho ADR-181.
- *Kiểm chứng:* regression test cho từng mục và chạy toàn bộ suite.

**Pha 2 — Đường phục hồi**
- *Phạm vi:*
  - Thao tác xóa check job đã kết thúc, có đối ứng `checks remove` ở API và CLI; chỉ đếm job đang sống (X-m1).
  - Capture theo kiểu stage rồi rename atomic; initializer không làm hỏng lifespan (X-m2).
  - Thêm marker và `recover_incomplete()` cho checkpoint (I9).
  - Evict record terminal của workflow, và admission riêng cho đọc với ghi (S-m1, S-m2).
  - Envelope lỗi theo request cho worker voice (W-m2).
  - Thủ tục reset `history_broken` sau khi đã kiểm tra.
- *Module:* `check_jobs.py`, `apps/api/storage/checks.py`, `checkpoints.py`, `coding_workflows.py`, `voice/tts_runtime.py`, `apps/harness/service.py`.
- *Rủi ro:* trung bình, vì đụng vào các bảo đảm an toàn.
- *ADR và owner:* có, thay một phần ADR-060 ("no retirement"), ADR-062 ("no eviction"), ADR-059 và ADR-182.
- *Kiểm chứng:* tạo hơn 8 job, xóa, rồi tạo lại; hủy giữa lúc capture rồi khởi động lại API; test restart; test poll trạng thái trong lúc generation.

**Pha 3 — Tách code lab**
- *Phạm vi:*
  - Chuyển các module không có entrypoint sang `src/labs/` mà không đổi hành vi: planner, MCP, stdio, plan_checkpoints, stack research, biến thể coding, vision/video, browser động, report export, Brave, live publisher.
  - Chia `scripts/`: worker product sang `src/infrastructure/workers/`, `QwenCpu` sang `src/infrastructure/embedding/`, campaign sang `research/<milestone>/` với marker `research`, hoặc xóa. Viết README cho `scripts/`.
  - `GenerationJobs` chỉ đăng ký route khi có backend.
- *Rủi ro:* thấp, vì chỉ là đường import. Để shim re-export trong một release cho benchmark.
- *ADR và owner:* có. Owner quyết định planner (nối hay retire) và các campaign cần xóa.
- *Kiểm chứng:* báo cáo reachability cho thấy `src/` product gần như không còn module không gọi tới; suite xanh; thời gian CI giảm.

**Pha 4 — Kernel dùng chung**
- *Phạm vi:* như thiết kế đích ở mục 2.5. Mỗi primitive một PR: tên cũ trở thành alias trước, rồi mới đổi import.
- *Rủi ro:* thấp đến trung bình.
  - Encoder canonical phải ra **đúng từng byte**, vì digest của review và approval phụ thuộc vào nó. Phải có golden test trước khi chuyển.
  - Supervisor sandbox mới có thể đổi timing teardown; test ADR-179 phải phủ mọi họ sandbox.
- *ADR:* một ADR "shared kernel".
- *Kiểm chứng:* test hiện có xanh mà không sửa; golden bytes; test auth-before-body cho mọi router (A4).

**Pha 5 — Lõi về đúng tầng**
- *Phạm vi:*
  - `presets` sang `src/domain/token_budget.py`.
  - `ModelProfile` frozen, nạp một lần (dùng đúng host và context từ yaml).
  - Gateway sang `src/infrastructure/inference/`.
  - Để shim ở `apps/` trong một release.
  - ConversationManager nhận UoW qua port đã cập nhật.
  - Route bỏ `sqlalchemy`.
  - Import-linter chuyển sang chế độ enforce.
- *Rủi ro:* trung bình, vì nhiều đường import và benchmark import đường cũ.
- *Kiểm chứng:* import-linter, toàn suite, các test số học budget.

**Pha 6 — CoreClient**
- *Tiền đề:* merge ADR-195 (draft PR #90) sau khi tách phần reformat toàn file `llama_gateway.py` ra (C-m3). AST registry `SITES` của nó là lưới an toàn khi gom các site lại.
- *Phạm vi:*
  - Xây `CoreClient`, `CoreSession`, `RequestSpec`, `CoreAdmission` và `CoreError` như ở mục 2.2.
  - Chuyển từng builder: gateway (thành shim), `ProductInference`, summarizer, `llama_adapter`, `structured_excerpt`, `vision_ocr`/`core_vision_chat`, `coding_reasoning`, `structured_profile`.
  - Inject admission, rồi xóa `TARGETS` và `_coordinator`.
- *Rủi ro:* cao. Đây là đường model; khả năng so sánh benchmark có thể bị ảnh hưởng; route gốc sẽ bắt đầu phải xếp hàng.
- *ADR và owner:* có, thay phần wrapper của ADR-175 và phần coupling của ADR-017:32. Cần cửa sổ CORE.
- *Kiểm chứng:* capture golden byte body POST cho từng builder trước và sau. Nếu body đổi có chủ đích (thống nhất dialect `response_format` hay tên reasoning budget) thì chạy lại benchmark liên quan. Test admission khi route gốc và harness chạy đồng thời. Smoke live mỗi đường một lần.

**Pha 7 — Harness**
- *Phạm vi:* mục 3.4 và 3.5.
- *Rủi ro:* trung bình.
- *ADR và owner:* có, sửa ADR-180, 181 và 182; owner quyết định 4 câu hỏi ở mục 3.4.
- *Kiểm chứng:* test harness, CLI end-to-end, screenshot UI, và test chuyển trạng thái `RunRecord` ở cả memory mode lẫn history mode.

**Pha 8 — Composition root**
- *Phạm vi:*
  - `Settings` có kiểu, `create_app(settings)` với feature registry và `AsyncExitStack`.
  - Bỏ 3 wrapper factory, đổi tên `storage` thành `composition`, thêm `StartupError(capability, code)`, và bắt buộc scope (I-m2, A-m4).
- *Rủi ro:* trung bình đến cao, vì thay đổi entrypoint (`aevra serve`, đường đánh giá voice).
- *ADR và owner:* có, thay điều khoản "main byte-identical" của ADR-175 và ADR-177.
- *Kiểm chứng:* snapshot route-set và OpenAPI cho mọi tổ hợp cờ được hỗ trợ; test lỗi khởi động theo từng capability; test shutdown khi một service raise.

**Pha 9 — Lỗi, kiểu dữ liệu, DB**
- *Phạm vi:*
  - `CodedError` cùng registry, một handler và một envelope. Có lớp tương thích cho CLI, desktop và web UI.
  - Record có kiểu cho workflow, check job và journal.
  - Registry `schema_compat` thay 4 cổng revision (gộp với ADR-191).
  - Migration cộng thêm đưa `owner_id`, `storage_namespace` và lease lên cột có index, kèm backfill.
- *Rủi ro:* trung bình, vì đổi hợp đồng API và migration.
- *ADR và owner:* có. Migration cần phân tích migration và rollback; không commit dump DB.
- *Kiểm chứng:* test mọi literal được raise đều đã đăng ký; contract test cho envelope; migration up/down trên DB probe; chạy release recovery drill.

---

## 5. Những phần vững (nên giữ nguyên hành vi)

- **Sandbox và worker:**
  - `src/infrastructure/sandbox_process.Sandbox` (ADR-179) dùng bwrap `--info-fd` cộng pidfd, kiểm PID bị tái dùng, teardown có giới hạn và `retire()` idempotent.
  - `file_verifier.sandbox_command` cô lập mạnh: `--unshare-all`, `--clearenv`, `--cap-drop ALL`, payload qua `--ro-bind-data`.
  - Worker đặt `setrlimit` trước khi import parser.
  - `file_content_verifier.py` xử lý định dạng thù địch rất kỹ: preflight EOCD của ZIP và duyệt các tính năng chủ động của PDF.
  - Lỗi `MALLOC_ARENA_MAX=1` đã được truy đến gốc và có test hồi quy.
- **Lưu trữ:**
  - `local_blob_storage.py`: publish bằng `link()`, flock, fsync thư mục cha, giữ quota cho tới khi purge xong.
  - `file_journal`/`ingestion_journal`: dùng giờ của DB, thứ tự lock được ghi rõ, transaction ngắn.
  - `PrivateCheckpointRoot` đã được dùng chung bởi checkpoints, research_sessions và check_jobs, chứng tỏ hợp nhất là làm được.
  - `qdrant_ingestion` đọc lại để xác nhận mỗi lần ghi.
  - `harness_history` có HMAC và fail-closed.
- **Biên bảo mật:**
  - Kiểm loopback, Origin và proxy header (`routes/conversations.py:25-47`).
  - So sánh bearer bằng `hmac.compare_digest`.
  - `review_approval.py`: chỉ loopback, `trust_env=False`, token qua `getpass`, đồng ý bằng gõ `APPROVE`/`REJECT`.
  - Chống SSRF trong `web_fetch_policy.public_url/public_address`.
  - `public_https` pin địa chỉ đã kiểm và kiểm tra framing nghiêm ngặt.
  - Bundle UI và artifact Hugging Face đều được pin.
- **Logic thuần, dễ test:**
  - `presets.py` (`calculate_budget`, `classify_completion`).
  - `context_reduction`, `working_state` và `history_summary` nhận counter, archive và summarizer qua inject. Kiểm trích dẫn nguyên văn trong `history_summary` rất bảo thủ.
  - `memory_contract.py` là một value model mạnh. `StoragePolicy` tự kiểm bất biến.
  - Chunk ID và plan ID có tính tất định, được định địa chỉ theo nội dung.
- **Cancellation và fail-closed:** shield-và-join nhất quán; shutdown join theo thứ tự phụ thuộc; fence cuối trước khi giao dữ liệu; trạng thái `unknown` không bao giờ bị coi là thành công.
- **Kỷ luật chung:**
  - Log không chứa nội dung, đúng AGENTS.md.
  - Pydantic dùng `extra='forbid'`.
  - Gần như không có state global (chỉ một singleton có guard).
  - Domain không import ra ngoài.
  - ADR trung thực về nợ kỹ thuật: ADR-017:32, ADR-195:386/404, backlog ghi PARTIAL.
  - 375 file test (khoảng 2.950 test) cộng 165 file benchmark.
  - `full_regression.py` kế toán trung thực: từ chối nghiệm thu nếu có bất kỳ skip, fail hay error.

---

## 6. Phụ lục

### 6.1 Bảng mọi finding được giữ (220)

CĐ là chủ đề chính ở mục 2. Mức: cao, TB (trung bình), thấp. Đuôi `-m` là finding do skeptic bổ sung.

| ID | Khu vực | Mức | Tiêu đề | Vị trí chính | CĐ |
|---|---|---|---|---|---|
| H1 | harness | TB | Admission, deadline 120 s và ánh xạ lỗi chép ở 4 đường, mỗi đường báo lỗi khác | apps/harness/routes.py:190-233 | 2 |
| H2 | harness | TB | State machine run và mã lỗi chỉ có trong store tùy chọn; memory mode không kiểm | src/infrastructure/harness_history.py:16-24 | 7 |
| H3 | harness | TB | ProductHarness là túi service-locator, route thao tác field trực tiếp | apps/harness/service.py:34-43 | 7 |
| H4 | harness | TB | Kiểm skill còn sống bằng authorize(permissions[0]); review_bytes song song; đổi nhãn skill_revoked | apps/harness/service.py:71-83 | 7 |
| H5 | harness | TB | Inference gọi private method của gateway và lặp round-trip CORE | apps/harness/inference.py:61-79 | 2 |
| H6 | harness | TB | Planner/MCP/stdio/checkpoint/nửa ghi của router không có caller; 3 mô hình run | src/application/services/run_planner.py:157 | 9 |
| H7 | harness | thấp | Đường evidence 3 wrapper, 3 budget, 4 lần validate; run có skill bỏ qua guard | apps/harness/service.py:221-244 | 5 |
| H8 | harness | TB | Session trình duyệt, bounded JSON, CSRF chép từ voice; hack viết lại request scope | apps/harness/browser.py:42-101 | 5 |
| H9 | harness | thấp | I/O file và hash đồng bộ trên event loop (history, bundle 9 MB, auth) | apps/harness/browser.py:460-479 | 8 |
| H10 | harness | TB | Exception khác hình dạng; mã remap âm thầm; SkillError gộp ở biên | apps/harness/main.py:96-109 | 6 |
| H11 | harness | thấp | Option dạng dict, 14 kwargs; literal preset/strategy/contract lặp ở server, CLI, composer | apps/harness/inference.py:41-59 | 7 |
| H12 | harness | thấp | Giới hạn và nhãn capability chép tay thay vì lấy từ cấu hình | apps/harness/browser.py:326-346 | 8 |
| H13 | harness | thấp | Cấu hình và wiring qua os.environ và app.state | apps/cli/main.py:391-411 | 4 |
| H14 | harness | thấp | Store riêng có ký, kiểm file riêng, kiểm URL loopback bị chép | src/infrastructure/harness_history.py:133-188 | 5 |
| H15 | harness | thấp | Helper chung nằm ở module không liên quan, ném lỗi không liên quan | src/application/services/mcp_adapter.py:51-64 | 5 |
| H16 | harness | thấp | GenerationJobs chép pattern coordinator và không thể chạy trong product | apps/harness/generation.py:14-133 | 5 |
| H17 | harness | thấp | CLI execute() là chuỗi if 290 dòng giữ logic context-policy phía client | apps/cli/main.py:373-662 | 7 |
| H18 | harness | thấp | HarnessRoute kế thừa guard chat: GET/DELETE cũng đòi JSON; ui-pairings ngoài router | apps/harness/routes.py:33-72 | 5 |
| H-m1 | harness | TB | CLI bỏ mọi mã lỗi server, chỉ còn http_<status> | apps/cli/client.py:156-160 | 6 |
| H-m2 | harness | TB | "Single CORE admission" chỉ phủ route harness; route gốc cùng process đi vòng | apps/harness/main.py:62-70 | 2 |
| H-m3 | harness | thấp | Service context của application import apps.api runtime (lan sang CLI) | src/application/services/context_reduction.py:13 | 3 |
| C1 | context | cao | Không có CORE client duy nhất: 10 body, 12 httpx client, dialect khác nhau | apps/api/services/llama_gateway.py:295 | 2 |
| C2 | context | TB | Application và infrastructure import apps (presets, model_config, gateway) | src/application/services/conversation_context.py:6 | 3 |
| C3 | context | TB | Private helper của gateway dùng như API; prompt cuối bị đếm 2–3 lần | src/infrastructure/inference/llama_adapter.py:74 | 2 |
| C4 | context | TB | Hai đường compose context khác quy tắc dung lượng, schema báo cáo, ghép turn | src/application/services/context_reduction.py:177 | 7 |
| C5 | context | thấp | context_inspection tái dựng composer thay vì composer tự báo layer | src/application/services/context_inspection.py:29 | 9 |
| C6 | context | thấp | Benchmark sửa global của history_summary lúc chạy và đóng băng hash file product | benchmarks/context_summary_v2.py:310 | 9 |
| C7 | context | TB | Seal ADR-195 gắn ở 11 chỗ thay vì ở một biên client | nhánh adr195: src/infrastructure/inference/core_request_seal.py:42 | 2 |
| C8 | context | thấp | Binding special-literal là state process, có hook reset cho test, 18 guard đặt tay | nhánh adr195: src/application/services/special_literals.py:123 | 2 |
| C9 | context | TB | Lỗi đổi nhãn theo adapter; một sự cố CORE ra 6 mã | src/infrastructure/inference/structured_excerpt_adapter.py:462 | 6 |
| C10 | context | TB | Model id, cổng, context size hard-code dù đã có models.yaml | src/infrastructure/inference/structured_profile.py:205-208 | 8 |
| C11 | context | thấp | Chuỗi subclass adapter sửa budget đã validate; InferencePort nạp chồng mode | src/infrastructure/inference/reasoning_profile.py:46 | 7 |
| C12 | context | TB | GPU admission bằng monkeypatch danh sách chuỗi private method | apps/api/voice_admission.py:9-41 | 2 |
| C13 | context | thấp | Code chưa nối dây hoặc chỉ benchmark dùng trong đường inference product | src/application/services/inference_observability.py:15 | 9 |
| C14 | context | thấp | Tham số dài và cờ opt-in ràng buộc nhau ở entry point context | src/application/services/context_composer.py:41 | 7 |
| C15 | context | thấp | Validator/converter/JSON helper nhỏ chép; hai `digest` khác encoding | src/application/services/history_summary.py:235 | 5 |
| C16 | context | thấp | run_worker của qwen_token_preflight nuốt kwargs âm thầm | src/infrastructure/qwen_token_preflight.py:33 | 5 |
| C-m1 | context | TB | Harness gộp mọi lỗi inference thành một mã, kể cả 422 mà client sửa được | apps/harness/routes.py:220-231 | 6 |
| C-m2 | context | TB | Chat streaming (UI web) không kiểm finish_reason | apps/harness/inference.py:207-249 | 10 |
| C-m3 | context | thấp | Nhánh ADR-195 trộn reformat toàn file gateway vào commit bảo mật | nhánh adr195: apps/api/services/llama_gateway.py | 1 |
| A1 | api | TB | Tầng trong import entry layer API (presets, model config, gateway, file_io) | src/infrastructure/qwen_query.py:9 | 3 |
| A2 | api | cao | Composition bằng clone app gốc trong các wrapper factory loại trừ nhau | apps/api/voice.py:56-74 | 4 |
| A3 | api | TB | GPU admission cài bằng monkeypatch 11 thuộc tính class/module | apps/api/voice_admission.py:9 | 2 |
| A4 | api | cao | Chính sách HTTP viết lại theo router; 4 router đệm body không giới hạn trước auth | apps/api/routes/conversations.py:158 | 5 |
| A5 | api | thấp | Response sở hữu context chép 9 lần với __aenter__/__aexit__ tay | apps/api/routes/files.py:139 | 5 |
| A6 | api | TB | Router/initializer/getter service clone-and-rename | apps/api/routes/workspace_explanations.py:33 | 5 |
| A7 | api | TB | Thang status theo router, 3 envelope, catch rộng biến bug thành 503 | apps/api/routes/memory.py:119 | 6 |
| A8 | api | TB | Cấu hình tản mạn: 25+ khóa env, 17+ cờ, bỏ qua âm thầm, path cứng | apps/api/storage/lifecycle.py:80 | 4 |
| A9 | api | TB | Package 'storage' là composition root; lifespan 130 dòng teardown mong manh | apps/api/storage/lifecycle.py:113-161 | 4 |
| A10 | api | TB | Auth và owner rải trong route module; 4 cách lấy principal | apps/api/routes/conversations.py:25 | 3 |
| A11 | api | TB | Quy tắc nghiệp vụ và truy cập repo trong route; dispatch bằng chuỗi | apps/api/routes/memory.py:262 | 7 |
| A12 | api | TB | Cổng revision Alembic hard-code rải ở các initializer | apps/api/storage/memory.py:33 | 8 |
| A13 | api | thấp | Đọc file và YAML đồng bộ trên event loop mỗi request | apps/api/core/conversation_auth.py:61 | 8 |
| A14 | api | thấp | File backup chết được track; hằng định danh cũ trong health | apps/api/main.py.bak:1 | 9 |
| A-m1 | api | TB | Lỗi khởi động bị đổi nhãn, mất nguyên nhân capability | apps/api/storage/lifecycle.py:105 | 4 |
| A-m2 | api | TB | Entry point product bỏ qua âm thầm cờ voice/grounded-extract | apps/harness/main.py:115 | 4 |
| A-m3 | api | thấp | Nhánh gpu_busy không thể chạy, đọc global private | apps/api/routes/grounded_extract.py:268 | 9 |
| A-m4 | api | thấp | Service không scope trên app.state; scope dựa vào caller nhớ for_owner | apps/api/storage/lifecycle.py:83 | 7 |
| S1 | api_services | TB | Task-join, admission nonqueued, shutdown chép qua mọi service | apps/api/services/files.py:41 | 5 |
| S2 | api_services | cao | Tầng application thực nằm ở apps/api/services; infra và harness import ngược | apps/api/services/coding_workflows.py:57 | 3 |
| S3 | api_services | cao | Biến thể coding workflow chồng bằng kế thừa và ContextVar; 3 biến thể chỉ test dùng | apps/api/services/controlled_coding_workflows.py:32 | 7 |
| S4 | api_services | TB | State workflow là dict/chuỗi; phát hiện uncertain bằng substring | apps/api/services/coding_workflows.py:41 | 7 |
| S5 | api_services | TB | Thao tác tài liệu FileService dán 4 lần; chunks.py chạm counter private | apps/api/services/files.py:395 | 5 |
| S6 | api_services | TB | Lệnh gọi CORE viết lại theo service, preset/token/timeout cứng | apps/api/services/grounded.py:43 | 2 |
| S7 | api_services | TB | Chọn class lỗi theo nơi sinh; constructor log và đổi nhãn | apps/api/services/grounded.py:61 | 6 |
| S8 | api_services | TB | Grounded đọc global private để phân loại lỗi; GPU guard monkeypatch | apps/api/services/grounded.py:201 | 2 |
| S9 | api_services | TB | Service thò vào nội bộ service khác; precondition lặp | apps/api/services/ingestion.py:39 | 7 |
| S10 | api_services | TB | SQL thô và allowlist revision schema viết tay trong service | apps/api/services/ingestion.py:51 | 8 |
| S11 | api_services | thấp | Composition chỉ dùng đánh giá với catalogue cứng trong package product | apps/api/services/live_publisher_research.py:27 | 9 |
| S12 | api_services | thấp | Hook test và state quan sát trong service product | apps/api/services/web_search.py:17 | 9 |
| S13 | api_services | thấp | Dispatch bằng chuỗi cho mutation memory/conversation | apps/api/services/memory.py:50 | 7 |
| S14 | api_services | thấp | YAML model đọc lại đồng bộ mỗi lần trong đường async | apps/api/services/conversations.py:137 | 8 |
| S-m1 | api_services | TB | Giới hạn record theo vòng đời process, không eviction | apps/api/services/coding_workflows.py:231 | 10 |
| S-m2 | api_services | TB | Một lock cho đọc/ghi/gọi lồng: poll nhận 429, busy của sibling đốt one-shot | apps/api/services/coding_workflows.py:83 | 10 |
| S-m3 | api_services | thấp | Thao tác file lồng mở và hash lại cùng blob nhiều lần | apps/api/services/chunks.py:71 | 8 |
| R1 | research | cao | Vòng đời owned-operation chép vào từng service | src/application/services/research.py:240 | 5 |
| R2 | research | cao | Giao thức CORE JSON viết lại theo tính năng; escape và pin model không nhất quán | src/application/services/grounded_answer.py:146 | 2 |
| R3 | research | TB | ~4.500 dòng research/claims/report/export chỉ test chạm tới | src/application/services/research_sessions.py:22 | 9 |
| R4 | research | TB | Discovery recovery là fixture một archive nằm trong application | src/application/services/discovery_recovery_policy.py:117 | 9 |
| R5 | research | TB | Port là DTO, Protocol không dùng; collaborator duck-typed | src/application/services/research_sessions.py:326 | 7 |
| R6 | research | TB | 12 từ vựng lỗi, ánh xạ sai (lỗi clock thành rate-limit) | src/application/services/discovery_recovery.py:79 | 6 |
| R7 | research | thấp | Logic /proc, sandbox, HTTP nằm trong "policy" tầng application | src/application/services/report_export_policy.py:265 | 3 |
| R8 | research | TB | Kernel chung rải trong module tính năng; tên policy/contract trôi | src/application/services/web_fetch_tasks.py:1 | 5 |
| R9 | research | TB | 3 resolver trích dẫn lệch nhau và hack JSON giả | src/application/services/workspace_diagnosis.py:211 | 5 |
| R10 | research | thấp | Ngữ pháp locator dạng chuỗi dựng một nơi, parse nơi khác | src/application/services/chunk_sources.py:68 | 7 |
| R11 | research | thấp | Báo cáo render 2 lần; kiểm artifact export lặp 3 lần | src/application/services/research_report_policy.py:166 | 5 |
| R12 | research | thấp | Helper strict/bounded JSON chép 10+ lần | src/application/services/search_pipeline.py:134 | 5 |
| R13 | research | thấp | HMAC receipt tạm thời viết 2 lần với serializer khác | src/application/services/web_evidence.py:47 | 5 |
| R14 | research | thấp | validate_source 135 dòng, mở rộng bằng override class attribute | src/application/services/web_evidence.py:109 | 7 |
| R15 | research | thấp | Model id và budget vận hành cứng trong application | src/application/services/grounded_extract.py:29 | 8 |
| R16 | research | thấp | Alias create_task global làm seam test cho ~50 module | src/application/services/web_fetch_tasks.py:7 | 9 |
| R-m1 | research | thấp | Stage research-session ghi blob fsync đồng bộ trên event loop | src/application/services/research_sessions.py:272-307 | 8 |
| R-m2 | research | thấp | Parser JSON workspace mượn dùng sinh cảnh báo audit sai | src/application/services/workspace_policy.py:16-21 | 6 |
| P1 | app_core | TB | ConversationManager gắn cứng SQLAlchemy/Postgres; port repo chết và lệch | src/application/services/conversation_manager.py:12-31 | 3 |
| P2 | app_core | TB | Domain chỉ còn vỏ; quy tắc nằm ở repo infra, enum apps, literal lặp | src/domain/entities/inference_run.py:9-32 | 7 |
| P3 | app_core | TB | Vòng đời operation (lock, owned task, shutdown) chép qua service | src/application/services/vision_chat.py:42-108 | 5 |
| P4 | app_core | TB | Primitive chung nằm trong module web-search/web-fetch, dùng dưới tên sai | src/application/services/web_fetch_tasks.py:10-28 | 5 |
| P5 | app_core | TB | Validator viết lại theo module, ngữ nghĩa lệch (Cf/bidi trong code sinh ra) | src/application/services/coding_workflow.py:22-34 | 5 |
| P6 | app_core | thấp | Giá trị media có kiểu bị serialize lại thành dict để validate | src/application/services/video_description.py:54-72 | 7 |
| P7 | app_core | thấp | plan_ingestion nhận 3 dict thô với catch-all | src/application/services/ingestion_contract.py:54-251 | 7 |
| P8 | app_core | thấp | Contract embedding cứng; lệch cấu hình server báo thành 422 | src/application/services/ingestion_contract.py:123-161 | 8 |
| P9 | app_core | TB | Không có mô hình lỗi: class theo module, side effect trong constructor | src/application/services/file_storage_policy.py:45-53 | 6 |
| P10 | app_core | thấp | VoiceSession: mã 'closed' gánh 5 nghĩa; nuốt cancellation | src/application/services/voice_session.py:28-33 | 6 |
| P11 | app_core | thấp | Service chưa nối dây và harness đánh giá trong tầng application | src/application/services/vision_chat.py:25 | 9 |
| P12 | app_core | thấp | Preset tạm, owner_id hai nghĩa, kwargs không kiểu trong ConversationManager | src/application/services/conversation_manager.py:292-296 | 7 |
| P13 | app_core | thấp | Namespace giấu trong khóa JSONB '_storage_namespace' | src/application/services/ingestion_contract.py:74-77 | 7 |
| P14 | app_core | thấp | Version OCR/pypdf dùng làm định danh processor của frame video | src/application/services/video_contract.py:227 | 8 |
| P-m1 | app_core | TB | Gateway và chính sách preset/budget nằm trong apps/, src/ import vào | apps/api/services/llama_gateway.py:151 | 3 |
| P-m2 | app_core | TB | Authorization và lease trong JSONB; principal None fail-open | src/infrastructure/repositories/conversation_repository.py:212-218 | 7 |
| P-m3 | app_core | TB | Bồi đắp là chính sách: module PASS bị cấm refactor | docs/ADR/028-bounded-xlsx-roundtrip.md:18 | 1 |
| P-m4 | app_core | thấp | Quota vision lồng theo frame: dịch vụ clip lỗi 'internal' ở clip thứ hai | src/application/services/video_description.py:182 | 10 |
| I1 | infra_storage | TB | Primitive thư mục riêng/ghi bền/HMAC viết lại theo milestone, kiểm tra lệch | src/infrastructure/plan_checkpoints.py:52-76 | 5 |
| I2 | infra_storage | TB | Application dựng repo Postgres; port repo chết và cũ | src/application/ports/repositories.py:11-30 | 3 |
| I3 | infra_storage | thấp | research_sessions.append chép create_file vì giới hạn cứng | src/infrastructure/research_sessions.py:205-223 | 5 |
| I4 | infra_storage | thấp | qwen_query (infra) import apps.api | src/infrastructure/qwen_query.py:9 | 3 |
| I5 | infra_storage | thấp | Instruction query lấy từ config đánh giá, ingestion lấy từ config đã duyệt | src/infrastructure/qwen_query.py:25-30 | 8 |
| I6 | infra_storage | TB | 3 cách mã hóa lease và 3 chính sách timeout giữa các journal | src/infrastructure/repositories/file_journal.py:326-341 | 5 |
| I7 | infra_storage | TB | Memory journal mở rộng bằng subclass với SQL chép nguyên văn | src/infrastructure/repositories/message_memory_journal.py:174-179 | 5 |
| I8 | infra_storage | thấp | Lỗi file-policy có HTTP status làm catch-all cho vector/embedding | src/infrastructure/qdrant_ingestion.py:126 | 6 |
| I9 | infra_storage | TB | Một capture checkpoint hỏng khóa cả store cho mọi owner, không có đường sửa | src/infrastructure/checkpoints.py:277 | 10 |
| I10 | infra_storage | TB | Record dạng dict, khóa ma thuật JSONB, validator viết tay | src/infrastructure/repositories/file_journal.py:57-65 | 7 |
| I11 | infra_storage | thấp | Composition thò vào thuộc tính đối tượng khác | apps/api/services/ingestion.py:39-41 | 4 |
| I12 | infra_storage | thấp | Chiều vector, endpoint, tên collection cứng dù config đã có | src/infrastructure/qwen_embedding.py:43 | 8 |
| I13 | infra_storage | thấp | Hook probe nghiệm thu và đường writer không guard trong adapter product | src/infrastructure/qdrant_ingestion.py:79-83 | 9 |
| I14 | infra_storage | thấp | Giới hạn dùng chung lặp thành số ma thuật (8192, 20 s, 120 s) | src/infrastructure/checkpoints.py:235 | 8 |
| I15 | infra_storage | thấp | Đường embedding product chạy file PEP 723 trong scripts/ qua uv | src/infrastructure/qwen_embedding.py:18-19 | 8 |
| I16 | infra_storage | thấp | Blob reader bỏ qua policy; thuộc tính private writer bị vá sau khi tạo | src/infrastructure/local_blob_storage.py:720-721 | 8 |
| I-m1 | infra_storage | TB | plan_checkpoints và research_sessions không có entry point product | src/infrastructure/plan_checkpoints.py:43 | 9 |
| I-m2 | infra_storage | TB | Scope bảo mật tùy chọn, mặc định không scope | src/infrastructure/repositories/conversation_repository.py:211-218 | 7 |
| I-m3 | infra_storage | TB | Runtime embedding/preflight product nằm trong script đánh giá | scripts/qwen_embedding_evaluation.py:13-18 | 3 |
| I-m4 | infra_storage | thấp | grant/create_manual lấy advisory lock trước khi áp timeout | src/infrastructure/repositories/memory_journal.py:204-206 | 5 |
| X1 | infra_exec | TB | Launcher bwrap viết riêng theo tính năng; teardown ADR-179 chỉ phủ một họ | src/infrastructure/check_runner.py:303 | 5 |
| X2 | infra_exec | thấp | report_export dựng sandbox bằng phẫu thuật argv và assert | src/infrastructure/report_export.py:27-39 | 5 |
| X3 | infra_exec | TB | Policy check đã duyệt và cờ prlimit là hai nguồn sự thật | src/infrastructure/check_runner.py:162 | 8 |
| X4 | infra_exec | thấp | Config browser runtime chỉ để nghi thức; giới hạn thật là literal | src/infrastructure/browser_runtime.py:35 | 8 |
| X5 | infra_exec | thấp | Hai client HTTPS GET gần giống nhau; vòng redirect viết tay | src/infrastructure/browser_resources.py:40 | 5 |
| X6 | infra_exec | thấp | Canonical JSON/strict decode viết lại theo module | src/infrastructure/check_runtime_io.py:212 | 5 |
| X7 | infra_exec | TB | Wrapper admission chép và bị vô hiệu do tạo mới mỗi lần gọi | src/infrastructure/web_evidence_source.py:98-115 | 5 |
| X8 | infra_exec | thấp | Bản vá publisher để lại nhánh parent chết | src/infrastructure/publisher_links.py:211-221 | 9 |
| X9 | infra_exec | TB | CheckJobStore là god class tiêu thụ approval; checks không có port | src/infrastructure/check_jobs.py:51 | 3 |
| X10 | infra_exec | TB | Job/journal là dict với validator khổng lồ và out-parameter | src/infrastructure/check_job_records.py:112 | 7 |
| X11 | infra_exec | TB | Context manager viết lại exception của caller; catch rộng xóa kiểu lỗi | src/infrastructure/check_jobs.py:111-146 | 6 |
| X12 | infra_exec | thấp | 74+ mã checks_* là literal kèm HTTP status trong infra | src/infrastructure/check_jobs.py:71 | 6 |
| X13 | infra_exec | thấp | Seam test và helper chung đặt tên sai (web_fetch_tasks) | src/infrastructure/web_fetch.py:24 | 5 |
| X14 | infra_exec | thấp | Layout runtime, path repo, endpoint cứng thay vì cấu hình | src/infrastructure/searxng_search.py:19 | 8 |
| X15 | infra_exec | thấp | Subsystem lớn chưa nối dây; cờ 'reviewed' dư thừa | src/infrastructure/publisher_links.py:189 | 9 |
| X16 | infra_exec | thấp | Layout worker export dựa vào text nhãn | src/infrastructure/report_export_worker.py:66 | 7 |
| X17 | infra_exec | thấp | sleep cố định và polling để đoán trang đã ổn định | src/infrastructure/readonly_browser.py:318 | 9 |
| X18 | infra_exec | thấp | Quét lại kho và hash lại runtime 64 MiB mỗi request | src/infrastructure/check_jobs.py:321 | 8 |
| X19 | infra_exec | thấp | Spec giả, __enter__ tay, state định nghĩa bằng hasattr | src/infrastructure/check_runtime.py:129 | 7 |
| X20 | infra_exec | thấp | Logic truy vấn workspace nằm trong infrastructure | src/infrastructure/workspace_reader.py:213 | 3 |
| X21 | infra_exec | thấp | Cleanup Docker CLI không có giới hạn thời gian | src/infrastructure/browser_runtime.py:220 | 10 |
| X22 | infra_exec | thấp | Log INFO trong vòng lặp nóng theo entry | src/infrastructure/readonly_workspace.py:126 | 8 |
| X-m1 | infra_exec | cao | Check job không bao giờ được giải phóng: trọn đời 8/owner, 32 tổng | src/infrastructure/check_jobs.py:321 | 10 |
| X-m2 | infra_exec | TB | Capture dở chặn capture, list và cả khởi động API | src/infrastructure/check_jobs.py:334 | 10 |
| X-m3 | infra_exec | TB | Điều phối check bị chia và lặp giữa app service và store | apps/api/services/checks.py:256 | 3 |
| X-m4 | infra_exec | thấp | Store checkpoint dùng làm store chung cho checks, audit dưới tên checkpoint_* | src/infrastructure/check_jobs.py:64 | 5 |
| X-m5 | infra_exec | thấp | parent_binding là kênh trả về ngoài luồng có thể thay đổi | src/infrastructure/publisher_links.py:221 | 7 |
| W1 | infra_workers | TB | Một launcher nhưng 7 wrapper client phía host viết tay | src/infrastructure/file_verifier.py:111-178 | 5 |
| W2 | infra_workers | thấp | 7 main() worker dán lại, giới hạn và output không nhất quán | src/infrastructure/ocr_worker.py:214-263 | 5 |
| W3 | infra_workers | TB | DOCX và XLSX là bản sao chỉ khác tên | src/infrastructure/docx_processor.py:1-101 | 5 |
| W4 | infra_workers | TB | Audio/video mượn child runner OCR, đổi nhãn che lỗi decoder thật | src/infrastructure/audio_worker.py:15-27 | 6 |
| W5 | infra_workers | TB | Mã lỗi worker là chuỗi, bảng theo module, heuristic hậu tố, timeout thành 413 | src/infrastructure/page_ocr.py:16-23 | 6 |
| W6 | infra_workers | thấp | Builder sandbox nằm trong file_verifier, caller nối argv | src/infrastructure/docx_processor.py:47-55 | 5 |
| W7 | infra_workers | TB | Voice infra import apps và override private method gateway | src/infrastructure/voice/native.py:12 | 3 |
| W8 | infra_workers | TB | Hai làn voice song song; trial dựa trên script benchmark | apps/voice_trial/native.py:14-37 | 9 |
| W9 | infra_workers | TB | Parity AST giữ nhánh research chết trong module voice | src/infrastructure/voice/asr_decode.py:82-107 | 1 |
| W10 | infra_workers | thấp | Class ASR dựng qua __new__ với thuộc tính gán từ ngoài | src/infrastructure/voice/asr_runtime.py:55-67 | 7 |
| W11 | infra_workers | TB | Worker voice thường trú là pattern process thứ ba, 3 vòng serve dán lại | src/infrastructure/voice/ipc.py:212-247 | 5 |
| W12 | infra_workers | TB | Nhánh theo chuỗi role; model/context/path/budget cứng | src/infrastructure/voice/native.py:226-273 | 8 |
| W13 | infra_workers | thấp | TTS phụ thuộc monkeypatch nội bộ private của SDK | src/infrastructure/voice/terms.py:26-31 | 7 |
| W14 | infra_workers | thấp | Guard tài nguyên busy-poll đồng bộ mỗi 25 ms | src/infrastructure/voice/ipc.py:99-116 | 8 |
| W15 | infra_workers | TB | NativeRuntime/Ports trộn gating, giám sát, kế toán, composition | src/infrastructure/voice/native.py:191-417 | 7 |
| W16 | infra_workers | thấp | Năng lực worker đã xây nhưng không nối entry point | src/infrastructure/native_image_normalizer.py:18 | 9 |
| W17 | infra_workers | thấp | Guard loopback/CSRF/CSP và recorder chép qua 3 bề mặt voice | apps/api/voice_routes.py:55-95 | 5 |
| W18 | infra_workers | thấp | Text trang PDF trích ở 2 worker với giới hạn khác nhau | src/infrastructure/ocr_worker.py:155-167 | 5 |
| W-m1 | infra_workers | TB | Workaround render giọng đọc làm hỏng lượt voice với câu trả lời bình thường | src/infrastructure/voice/reading_policy.py:61-68 | 10 |
| W-m2 | infra_workers | thấp | Worker voice không có envelope lỗi theo request; một lần từ chối giết cả nhóm | src/infrastructure/voice/tts_runtime.py:218-256 | 10 |
| W-m3 | infra_workers | thấp | run_sandbox giấu kết quả teardown | src/infrastructure/sandbox_process.py:245-261 | 5 |
| W-m4 | infra_workers | thấp | 3 helper join-thread; media mượn parser JSON của vision-chat | src/infrastructure/voice/resources.py:121-131 | 5 |
| T1 | scripts | TB | Worker product nằm trong scripts/, import module chỉ dùng đánh giá | src/infrastructure/qwen_embedding.py:19 | 3 |
| T2 | scripts | TB | core_snapshot hard-code PID CORE lịch sử; 13 script không chạy được | scripts/asr_evaluation_runner.py:217 | 9 |
| T3 | scripts | thấp | Launcher worker uv chép 4 lần, tên biến QWEN_INGESTION_* | scripts/reranker_comparison.py:245 | 5 |
| T4 | scripts | thấp | 5 builder bwrap viết tay, mở rộng bằng phẫu thuật argv | scripts/tts_voxtral_preparation.py:173 | 5 |
| T5 | scripts | thấp | 10+ writer artifact riêng tư với cờ khác nhau | scripts/coding_baseline_trial.py:84 | 5 |
| T6 | scripts | thấp | Metric IR, Levenshtein, loader, downloader, pcm_wave chép qua campaign | scripts/retrieval_review_scoring.py:115 | 5 |
| T7 | scripts | thấp | Phê duyệt/retire là công tắc module-level sửa tay | scripts/tts_local_review.py:368 | 9 |
| T8 | scripts | TB | 4 launcher CORE lệch nhau; voice attestation đòi cờ không launcher nào truyền | src/infrastructure/voice/core.py:66 | 8 |
| T9 | scripts | TB | Công cụ một lần và cũ nằm lẫn công cụ product; reranker hoãn vẫn được ship | scripts/create-release-manifest.py:11 | 9 |
| T10 | scripts | thấp | Freeze tự hash và parity AST biến code research thành bất biến | scripts/qwen_reranker_trial_worker.py:31 | 1 |
| T11 | scripts | thấp | Path tương đối CWD và path milestone cố định lúc import | scripts/asr_evaluation_assets.py:15 | 8 |
| T12 | scripts | TB | Recovery acceptance dựa vào assert; đường mặc định làm điều ADR-123 cấm | scripts/postgres_recovery_acceptance.py:241 | 10 |
| T13 | scripts | thấp | full_regression bỏ benchmarks/ khỏi freeze, không có wall timeout | scripts/full_regression.py:52 | 9 |
| T14 | scripts | thấp | Script thò vào nội bộ private và sửa state app | scripts/streaming_timing_probe.py:168 | 9 |
| T15 | scripts | thấp | 6 lock uv script giống hệt nhau | scripts/qwen_ingestion_encoder.py:2 | 8 |
| T16 | scripts | thấp | Token ID, revision, giới hạn lặp giữa code và config | scripts/browser_readonly_worker.cjs:14 | 8 |
| T17 | scripts | thấp | Họ TTS local-review: hàm god nhiều mode, control lặp 3 lần | scripts/tts_local_review.py:279 | 9 |
| T18 | scripts | thấp | Exception log trong constructor; lỗi bị đổi nhãn hoặc nuốt | scripts/profile_excerpt_evaluation.py:303 | 6 |
| T-m1 | scripts | TB | Mỗi truy vấn retrieval khởi động 2 worker lạnh và hash ~1,2 GB | src/infrastructure/qwen_query.py:39-40 | 10 |
| T-m2 | scripts | TB | Làn voice đã nghiệm thu phụ thuộc công cụ chưa từng commit | docs/progress/D74_B4_OWNER_ACCEPTANCE.md:34 | 10 |
| T-m3 | scripts | thấp | Coding sandbox chỉ dùng đánh giá nằm trong infra product | src/infrastructure/coding_sandbox.py:19 | 9 |
| T-m4 | scripts | thấp | kwargs chết ở launcher preflight che hành vi timeout/capture thật | src/infrastructure/qwen_token_preflight.py:32 | 5 |
| Z1 | architecture | cao | Quy tắc evidence byte-identical ép workaround thay vì refactor | docs/ADR/175-optional-main-voice-composition-and-entrypoint-binding.md:9 | 1 |
| Z2 | architecture | cao | Không có CORE client duy nhất; 5 module gọi private method gateway | apps/harness/inference.py:63 | 2 |
| Z3 | architecture | TB | Phân lớp đảo: infra/application import apps/ | src/infrastructure/inference/llama_adapter.py:11 | 3 |
| Z4 | architecture | TB | GPU admission bằng monkeypatch 11 entry point và đọc global private | apps/api/voice_admission.py:55 | 2 |
| Z5 | architecture | TB | ~20% nguồn product không có entry point | src/application/services/run_planner.py:1 | 9 |
| Z6 | architecture | TB | 18 cờ env và 3 wrapper factory không kết hợp được | apps/api/grounded_extract.py:74 | 4 |
| Z7 | architecture | TB | Helper chép-không-refactor: task-join, strict JSON, canonical, store, bwrap | src/application/services/web_fetch_tasks.py:20 | 5 |
| Z8 | architecture | TB | 50 class exception, ~1.100+ mã, không registry, ánh xạ HTTP tay | src/application/services/file_storage_policy.py:45 | 6 |
| Z9 | architecture | TB | models.yaml bị kiểm lại bằng literal; YAML parse mỗi request | apps/api/runtime/presets.py:26 | 8 |
| Z10 | architecture | TB | Product mang hình benchmark: voice 3 bản, trial import benchmarks, cờ debug | apps/voice_trial/native.py:17 | 9 |
| Z11 | architecture | TB | 61 hàm >100 dòng, API 15 tham số, policy opt-in bồi đắp | src/application/services/context_reduction.py:348 | 7 |
| Z12 | architecture | thấp | Dữ liệu dạng dict đi xuyên tầng; domain chỉ phủ conversation | apps/api/core/model_config.py:39 | 7 |
| Z13 | architecture | thấp | Tên module không khớp trách nhiệm | src/application/services/memory_contract.py:253 | 3 |
| Z14 | architecture | thấp | Singleton global đọc xuyên module; registry in-memory theo process | src/application/services/gpu_admission.py:9 | 2 |
| Z-m1 | architecture | TB | Hai cài đặt pairing/session trình duyệt với vòng đời khác nhau | apps/api/voice_identity.py:28 | 5 |
| Z-m2 | architecture | TB | Ngoài voice không có admission CORE chung; 20+ lock trên CORE một slot | configs/models.yaml:16 | 2 |
| Z-m3 | architecture | thấp | Exception driver DB đi lên tới route HTTP | apps/api/routes/memory.py:162 | 6 |
| Z-m4 | architecture | thấp | File backup cũ được track từ commit init | docker-compose.yaml.bak | 9 |

Thống kê: cao 10 (C1, A2, A4, S2, S3, R1, R2, Z1, Z2, X-m1), TB 101, thấp 109.

### 6.2 Khẳng định bị bác hoặc sửa

Không finding nào bị bác bỏ toàn bộ: danh sách `refuted` của cả 11 khu vực đều rỗng. Dưới đây là các khẳng định con mà skeptic đã bác hoặc sửa, để không có gì bị bỏ âm thầm.

- **harness**
  - H1: hạ từ cao xuống TB. "Fail mà chưa chạy" chỉ xảy ra khi thời gian chờ ăn hết 120 s.
  - H2: "latent outage" chỉ là giả định, vì không có đường nào hiện nay sinh mã ngoài whitelist. "Whitelist gây việc gộp thành run_failed" không có căn cứ; việc gộp do catch-all gây ra.
  - H4: dẫn chiếu sai dòng (lỗi parse ở skill_tools.py:52-53; lỗi từ chối ở skill_contract.py:275-279).
  - H5: đổi private method sẽ vỡ ồn ào, không âm thầm. Đường structured có kiểm finish_reason.
  - H7: SkillError ra skill_revoked chứ không phải run_failed; hạ xuống thấp.
  - H9: "khoảng 70 request asset mỗi lần tải trang" là sai (70 là số file trong receipt, phần lớn là icon); mức trễ chỉ vài chục ms.
  - H10: CLI vốn chưa bao giờ thấy mã của server; mất mã xảy ra ở client chứ không phải do gộp skill_operation_denied.
  - H11: prepare có 14 kwargs, không phải 16; cờ benchmark là chủ đích theo ADR-192/193.
  - H14: phân kỳ làm một bản chặt hơn chứ không lỏng hơn.
- **context**
  - C1: một số số dòng sai (vision_ocr :40/:44/:48-58/:84-91; voice/core :104/:125). voice/core chỉ gửi GET danh tính. V2 dùng budget 1536.
  - C2: chu trình apps↔src không phải mới có từ nhánh ADR-195.
  - C3: gateway đếm lại là chủ đích (ADR-017:30); chỉ lần đếm lại để báo cáo ở context_composer.py:161 là lãng phí.
  - C4: khẳng định phân kỳ cách theo dõi trùng lặp là sai; hai đường tương đương nhau.
  - C7: body precheck của grounded có từ trước ADR-195; TARGETS khác SITES.
  - C8: rủi ro fail-open nhỏ hơn vì mọi process product đều ghi binding.
  - C10: "không ai đọc context_size" là sai (start-core/start-model có đọc). Điều này làm vấn đề lệch giá trị càng rõ.
  - C11: V2 dùng 1536. C14: compose_context có 14 tham số; HistoryPolicy có 10 trường.
- **api**
  - A1: import service application không kéo FastAPI.
  - A3: target bị đổi tên sẽ fail-closed lúc khởi động, và cơ chế chỉ áp cho composition voice.
  - A4: files/docx/xlsx/grounded_extract có auth trước body; WorkspaceRoute giới hạn 16 KiB; nhóm vệ sinh validation không chỉ có memory/web_search; khoảng 11 literal chứ không phải 14.
  - A5: việc context không phân biệt được giao hỏng không phải là lỗi.
  - A9: gọi create_session_factory ba lần chỉ là vấn đề thẩm mỹ.
  - A11: số dòng chunk_sources khác.
- **api_services**
  - S1: không có bug tiềm ẩn từ phân kỳ current_task.
  - S4: không có lần nhận diện sai đang xảy ra; con số "applied ×9" trộn khóa của receipt.
  - S5: slot chunk dùng chung là chủ đích theo ADR-037.
  - S7: khoảng 180 chứ không phải 200; 422 và 413 là hai tình huống khác nhau.
  - S9: workflow_cancellation sửa trong phạm vi admission và lock của PatchService (ADR-063:39); precondition lặp là để bảo vệ lượt one-shot.
  - S10: JOIN của retrieval là fence cuối theo ADR-037, không thừa.
- **research**
  - R1: ví dụ về drift khi charge là sai.
  - R2: có 19 site profile=core; sau khi merge ADR-195 thì hạ xuống TB.
  - R5: schema journal thuộc application, không phải định dạng private của infra; plan_checkpoint không thuộc research.
  - R7: header_map là hàm thuần và application cũng dùng; public_address là chính sách SSRF.
  - R8: 48 file chứ không phải hơn 60.
  - R10: endswith không thể bind nhầm cell; lỗi ở đây là fail-closed.
  - R14: hàm có tính gắn kết, coupling chỉ cục bộ.
  - R15: budget là chính sách cố định có chủ đích (ADR-069); MODEL_ID thuộc giao thức D81 đã đóng băng.
- **app_core**
  - P1: chỉ là vi phạm cô lập, module duy nhất như vậy.
  - P2: từ vựng được thực thi dư thừa (có cả DB CHECK), không phải âm thầm.
  - P3: khoảng 30 module chứ không phải 11.
  - P5: validator văn bản nên khác nhau theo lớp; quote của memory không được normalize.
  - P7: dict ở reply của worker, record lưu trữ và view HTTP là biên hợp lý.
  - P8: pin là phòng thủ chiều sâu có chủ đích.
  - P10: retire khi lỗi và budget theo process là chủ đích (ADR-174/175).
  - P12: preset tạm không có consumer nào đọc.
  - P13: là chủ đích theo ADR-024:19,29.
  - P14: định danh đúng cho image chat; chuyện nâng cấp pypdf làm vỡ không xảy ra trong một process.
- **infra_storage**
  - I1: plan_checkpoints chưa nối dây; ADR-182:19 tách có chủ đích; rủi ro hard-link nhỏ; encoder của harness có giới hạn 16 KiB khi save.
  - I5: không có suy giảm âm thầm; fingerprint phủ cả query prefix nên lỗi sẽ lộ ra.
  - I7, I10, I11: dẫn chiếu dòng hoặc file sai. Việc rebuild và tái dùng client là chủ đích (ADR-024/037).
  - I8: HistoryError không log; status nằm trong exception là quy ước chung của dự án.
  - I13: transactional_session là helper chung, không phải hook test.
- **infra_exec**
  - X1: cuộc đua cleanup chỉ kéo dài cỡ ms vì có --die-with-parent; hạ xuống TB.
  - X5: chỉ đoạn request/response bị lặp; có 2 vòng redirect, không phải 3.
  - X6: 5 fenced read phục vụ 5 contract khác nhau.
  - X7: khoảng 31 class chứ không phải 21.
  - X12: quy ước (code, status) là chung toàn dự án.
  - X15: instance_reviewed chỉ dư thừa, không phải control rỗng.
  - X18: vòng lặp thứ hai trong validate() cho bảo đảm ở mức cả tập.
- **infra_workers**
  - W1: hạ xuống TB; có 8 client.
  - W6: phần splice của voice_trial là một builder khác.
  - W7: infra import apps là vấn đề toàn hệ thống, không riêng voice.
  - W8: hạ xuống TB; trial tự sở hữu CORE ở cổng 18080.
  - W12: số đếm hơi cao.
  - W13: không có MRO skip; drift của SDK fail ồn ào.
  - W16: ADR-085/090 chấp nhận việc chưa nối dây và có VISION-PROD-001.
- **scripts**
  - T1: coding sandbox không phải runtime product; các đường liên quan mặc định tắt nên mức TB.
  - T2: pin PID là chủ đích theo ADR-126/127.
  - T3: join_task là public; các bản research đã đóng băng.
  - T4: phía product cũng chưa hợp nhất vào run_sandbox; run_sandbox không nhận PIPE.
  - T5: phần lớn khe symlink hay world-readable không tồn tại (nhờ O_EXCL và thư mục 0700).
  - T6: phần lớn khác biệt là chọn lựa theo giao thức.
  - T7: gate bằng hằng số là chủ đích theo ADR-108/110 và fail-closed.
  - T8: luồng của người dùng theo README không vỡ.
  - T9: 74/375 file test; reranker bị hoãn chứ không bị bác.
  - T10: freeze được monkeypatch trong test; quan hệ nhân quả với việc chép code chỉ là suy đoán.
- **architecture**
  - Z1: "gốc của Z2–Z9" quá tay với Z8 và Z9.
  - Z2: 5 module chứ không phải 6.
  - Z3: "không test được nếu thiếu FastAPI" là sai.
  - Z4: nhánh _coordinator không chạy trong composition nào được hỗ trợ; hạ xuống TB.
  - Z5: khoảng 59 module, 11,5 nghìn dòng (khoảng 20%).
  - Z6: 30 tên env, 18 cờ ENABLED; env không chỉ được đọc ở biên.
  - Z10: last_request chính là body được gửi đi; trial là sự đánh đổi đã chấp nhận.
  - Z11: 18 nhánh; HistoryPolicy có 5 quy tắc chéo cộng 1.
  - Z14: đọc lại file auth mỗi request là chủ đích (thu hồi có hiệu lực ngay), nên **không** áp dụng đề xuất cache theo mtime như đã nêu.
