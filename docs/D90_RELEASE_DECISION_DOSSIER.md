# D90 — Hồ sơ quyết định phát hành

**Mục đích:** Chủ dự án dùng hồ sơ này để chọn một phạm vi hỗ trợ cụ thể, chấp nhận các giới hạn đã biết và ghi rõ những mục hoãn trước khi tạo tag. Hồ sơ không tự phê duyệt release. Nó không tạo tag, không deploy và không đổi model hay default.

**Ngày lập:** 2026-11-06, trạng thái tại khoảng 18:00 (Asia/Ho_Chi_Minh); cập nhật ngày 2026-11-07 với kết quả B3 theo [ADR178](ADR/178-graceful-sigterm-exit-in-b3-acceptance.md) và đợt promote lên `staging`/`production` (PR #30, #31). **Trạng thái D90:** NOT APPROVED / NOT TAGGED / NOT DEPLOYED ([ledger](OUTSTANDING_WORK_STATUS.md), [release status](RELEASE_CANDIDATE_STATUS.md), [các D còn mở](OPEN_DAYS_20261105.md)).

**Quy ước bằng chứng:**

- Mục có link là tài liệu hoặc receipt đã lưu trong repo.
- Mục ghi *(operator 2026-11-06)* là sự kiện operator cung cấp. Các sự kiện B3/ADR176 nay đã có [báo cáo kết quả B3](D74_MAIN_VOICE_B3_RESULT.md), [receipt](evidence/d74-main-voice-b3-adr176-result.json) và mục devlog 2026-11-06. Lượt B3 theo [ADR178](ADR/178-graceful-sigterm-exit-in-b3-acceptance.md) có [receipt công khai](evidence/d74-main-voice-b3-adr178-result.json) và mục devlog 2026-11-07; mục nào chưa có tài liệu thì cần ghi trước khi dùng làm bằng chứng nghiệm thu.
- Mục ghi *(owner 2026-11-06, operator record)* là quyết định của chủ dự án do operator ghi lại, chưa có bản ghi riêng trong repo.
- Receipt dưới `data/backups/` là private, bị Git bỏ qua, không có trong repo hay bundle.
- Câu "Ổn rồi" của chủ dự án là [nhận xét tích cực chung](evidence/d74-voice-browser-owner-feedback-20261105.json), không phải số đo PASS.
- Test phần mềm không phải chất lượng model hay nghiệm thu vật lý.

## 1. Release D90 có nghĩa gì với dự án cá nhân này

- Chủ dự án chốt **một phạm vi hỗ trợ đã review** tại một commit cụ thể trên `production`, kèm các giới hạn được chấp nhận và danh sách mục hoãn. Mốc này được đánh dấu bằng một tag `v*` trên repo private `DungeonLeiz/local-assistant`.
- Tag kích hoạt job `package` và `release` trong [CI](../.github/workflows/ci.yml). CI đóng gói source bằng `git archive` rồi tạo GitHub Release. Đầu file workflow ghi rõ không liên lạc hay deploy lên Home Server.
- Bundle gồm mọi file Git đang theo dõi. [.gitignore](../.gitignore) loại `/models/`, `*.gguf`, `*.safetensors`, `data/`, `.env`, `secrets/` và `.venv/`, nên bundle không chứa weights, dữ liệu runtime trong `data/` hay credential. Bundle vẫn gồm fixture test (audio, video, PDF, DOCX), evidence trong `docs/evidence/`, `dev_log/dev_log.md` và hai file `.bak` đang được theo dõi.
- Tag **không** có nghĩa là:
  - deploy hoặc restart dịch vụ dùng chung;
  - bật voice: `ASSISTANT_VOICE_ENABLED` mặc định `0` và khi đó trả về app gốc ([apps/api/voice.py](../apps/api/voice.py));
  - đổi model, provider hoặc default;
  - công nhận chất lượng model tổng quát;
  - đóng D74, D81 hoặc D60.
- Đây không phải v1.0. [Release status](RELEASE_CANDIDATE_STATUS.md) ghi rõ không tag một dự án chưa hoàn tất là v1.0. Hồ sơ này đề xuất dùng dải `v0.x`.
- Bề mặt hiện có là API HTTP cục bộ có xác thực, chạy trên 127.0.0.1 với một worker ([runbook](CONVERSATION_API_LOCAL_RUNBOOK.md), [D88 cài sạch](D88_CLEAN_INSTALL_REHEARSAL.md)). Repo chưa có giao diện web chat văn bản; HTML chỉ có ở các bề mặt voice. API chính cố ý từ chối request có Origin trình duyệt ([D74 integration review](D74_VOICE_INTEGRATION_REVIEW.md)).
- Các phần sau chưa được chứng nhận ([release status, mục Accepted local limits](RELEASE_CANDIDATE_STATUS.md)): OIDC, TLS, reverse proxy, multiworker/SLO, host OOM và khôi phục off-host.

**Trạng thái repo:**

- `ai/` là repo private `DungeonLeiz/local-assistant`, với các nhánh `production` (mặc định), `staging` và `develop`. Lịch sử được replay qua PR #7–#20; code lên staging qua PR #22 và lên production qua PR #24 *(operator 2026-11-06)*.
- Đối chiếu cục bộ với `origin/*` ngày 2026-11-07: `develop` ở `d97119c`, `staging` ở `0ec664d`, `production` ở `4dcf8db`. PR #25 (`1eb20a0`) thêm [LICENSE](../LICENSE) MIT; chủ dự án chọn MIT *(owner 2026-11-06, operator record)*. PR #26 (`eeabbe8`) thêm [ADR176](ADR/176-bounded-foreign-gpu-tolerance-and-b3-preflight.md) cùng code dung sai tiến trình GPU ngoài và preflight B3. PR #28 (merge `73cecdf`, commit nhánh `6e78f8d`) thêm [ADR178](ADR/178-graceful-sigterm-exit-in-b3-acceptance.md) cùng bản sửa runner B3 cho kiểm tra exit của web process và kiểm tra worker join sạch. Kết quả B3 theo ADR178 vào `develop` qua PR #29 (merge `d97119c`). Ngày 2026-11-07, `develop` được promote lên `staging` qua PR #30 (merge `0ec664d`, có deployment `staging`) và lên `production` qua PR #31 (merge `4dcf8db`). Khi đó ba nhánh có cùng cây nội dung, nên `production` đã có LICENSE, ADR176 và ADR178. Các PR `docs:` sau đó chỉ vào `develop` cho tới lượt promote kế tiếp.
- `git tag -l` trả về rỗng; chưa có GitHub Release *(operator 2026-11-06)*.
- Repo private trên gói GitHub Free: API branch protection/rulesets trả 403 "Upgrade to GitHub Pro or make this repository public" *(operator 2026-11-06)*.

## 2. Các phương án phạm vi hỗ trợ

Nhãn A/B/C ở đây không liên quan đến phương án A/B trong [ADR174](ADR/174-proposed-opt-in-authenticated-voice-integration.md) hay [rà soát quyền D74](D74_VOICE_RIGHTS_REVIEW.md).

A và B tag cùng một commit `production`. `production` đã có LICENSE, ADR176 và ADR178 từ PR #31 (`4dcf8db`); nếu `develop` có thêm thay đổi, kể cả tài liệu và phiếu ở mục 5, thì promote lại trước khi tag. C chưa tag lúc này và sẽ tag một commit muộn hơn. A và B chỉ khác nhau ở phạm vi **được tuyên bố hỗ trợ**, không khác nội dung bundle. Code voice vẫn nằm trong bundle, nhưng mặc định tắt.

### Phương án A — văn bản, tài liệu, RAG, coding, web đã kiểm chứng cục bộ; không gồm voice

| Năng lực trong phạm vi | Bằng chứng | Giới hạn đã biết |
|---|---|---|
| Chat CORE có xác thực; hội thoại và lịch sử tách theo owner | [Roadmap §1, P2a PASS](LOCAL_ASSISTANT_MASTER_ROADMAP.md). Đường semantic đã chọn đạt 42/42 ở mỗi profile ([D14](D14_SEMANTIC_REMEDIATION_RESULT.md)) | Điểm tổng hợp cục bộ: CORE 66,5, UNRESTRICTED 52 ([ledger](OUTSTANDING_WORK_STATUS.md)). Đường đã chọn là opt-in, không phải chất lượng tổng quát |
| Profile UNRESTRICTED tách biệt, không tự cấp tool | [D88 scorecard](D88_MODEL_PROVENANCE_SCORECARD.md): MQ002 đạt 20/30, so với CORE 23/30 | Chủ dự án chọn giữ hay bỏ. Rà soát quyền D74 chỉ phủ CORE và luồng voice, chưa phủ weights UNRESTRICTED |
| File: upload, đọc, thay, xóa theo owner/hash/quota; PDF/DOCX/XLSX; OCR một trang | [Roadmap §1, P2b](LOCAL_ASSISTANT_MASTER_ROADMAP.md), [ADR029](ADR/029-page-ocr-and-local-vision.md), [D62](D62_NATIVE_CORE_OCR_QUALITY.md) | Tesseract chỉ có `eng/osd`. Trên mẫu D62, OCR native cho tiếng Việt có CER 0,25 và WER 0,75. VLM luôn cần review |
| Ingestion, RAG có trích dẫn, xóa nguồn; memory có consent và thu hồi | [D32](D32_KNOWLEDGE_GATE.md), [D31](D31_PRIVACY_AND_DELETION.md), workflow 5 và 14 trong [D89](D89_MANUAL_ACCEPTANCE_CHECKLIST.md) | Embedding Qwen3 đang `selected_not_deployed`; rollback E5 giữ nguyên. Reranker mới chỉ thử nghiệm cô lập ([D88 scorecard](D88_MODEL_PROVENANCE_SCORECARD.md)) |
| Coding theo chuỗi: đọc workspace → đề xuất → phê duyệt rõ → patch → kiểm tra riêng | [D46](D46_CODING_AGENT_MVP_SCORECARD.md) đạt 7/10. [CODE-EVAL-002](CODE_EVAL_002_FIRST_SCORECARD.md) đạt 7/12 ở cả hai nhánh. CE005 đạt 12/12 trên cohort đã chọn ([D46/D60](D46_D60_REMEDIATION_RESULT.md)) | Chưa xác lập chất lượng coding tổng quát hay khả năng chạy không giám sát |
| Web research theo chuỗi: tìm nguồn → trang nhà xuất bản → báo cáo → DOCX/PDF → archive | [D60 fresh](D60_FRESH_DISCOVERY_RESULT.md), [D46/D60](D46_D60_REMEDIATION_RESULT.md) | Lượt Brave gần nhất chỉ có 3/8 hợp lệ ([D60 resumed](D60_BRAVE_RESUMED_RESULT.md)). Gate direct-result gốc vẫn FAIL |
| Ảnh, bảng, biểu đồ, ảnh chụp tài liệu, frame video | [D63](D63_IMAGE_GOLDENS.md), [D65](D65_FRAME_VIDEO_DESCRIPTIONS.md), [D67](D67_EXISTING_MULTIMODAL_BENCHMARK.md), workflow 8–9 trong D89 | Chưa có độ chính xác OCR/VLM tổng quát. Còn giới hạn frame thưa và transcript phải cung cấp sẵn |
| Vận hành cục bộ: localhost với bearer, restore, lỗi tài nguyên có giới hạn | [D82](D82_THREAT_MODEL_SECURITY_REVIEW.md), [D84](D84_ISOLATED_RESTORE_DRILL.md), [D85](D85_BOUNDED_FAILURE_LOAD_POLICY.md) | Chưa có khôi phục off-host, xử lý host OOM hay SLO |

**Các mục hoãn trong A:**

- toàn bộ voice: D68–D74, recorder D71, trang thử 8092 và voice chính B1/B2/B3;
- D81 dưới dạng tính năng sản phẩm;
- harness D75–D80 (các thành phần độc lập, chưa kích hoạt);
- coverage D60 đạt 8/8.

### Phương án B — A cộng các bề mặt voice nghiên cứu, mặc định tắt

Mọi bề mặt dưới đây đều mang nhãn bắt buộc: "nghiên cứu, mặc định tắt, không phải tính năng sản phẩm". Phương án này không bật voice và không chọn model, giọng hay default.

| Bề mặt thêm vào | Bằng chứng | Giới hạn |
|---|---|---|
| Voice trong app chính (B1/B2) | [ADR174](ADR/174-proposed-opt-in-authenticated-voice-integration.md), [ADR175](ADR/175-optional-main-voice-composition-and-entrypoint-binding.md), code tại [apps/api/voice.py](../apps/api/voice.py). Flag mặc định `0`. Chỉ bật được cho mục đích `integration_evaluation`, với auth file, manifest operator riêng và một worker; ADR175 chỉ cho phép manifest đánh giá của operator, chưa chấp nhận manifest production hay kích hoạt production | Hai lượt B3 đầu NOT_PASS; lượt theo ADR178 ngày 2026-11-07 PASS. Xem bên dưới bảng |
| Trang thử loopback 8092 ([ADR173](ADR/173-loopback-voice-trial-and-playback-instrumentation.md)) | [Kết quả](D74_VOICE_BROWSER_TRIAL_RESULT.md): HTTP native 6/6, client roundtrip 1,972–3,250 s; 766 Python PASS và 20 JS PASS | Prepare mất 43,843 s và tính riêng. Đây không phải PASS cho 4 giây khi khởi động lạnh |
| Pipeline buffered: Qwen ASR CUDA, CORE 32K, Trúc Ly CPU8 | [LOCAL_BUFFERED_COMPUTE_PASS](D74_RESIDENT_CUDA_LATENCY_RESULT.md): 4/4 câu nói hoàn tất trong 2,000–3,334 s | Có PCM hoàn chỉnh chưa có nghĩa là đã nghe thấy tiếng từ loa |
| Recorder D71 | [D71](D71_EXPLICIT_RECORDING.md); [smoke micro thật do chủ dự án báo PASS](D74_PHYSICAL_MIC_CHECK.md) | Preview, xóa, TTL và lifecycle còn lại chưa được báo cáo ([D89](D89_MANUAL_ACCEPTANCE_CHECKLIST.md)) |
| Quyền sử dụng | [Rà soát D74](D74_VOICE_RIGHTS_REVIEW.md): tích hợp cá nhân tại máy, chỉ source | Phân phối binary hoặc weights cần SBOM/notice riêng (mục D1 trong [ADR174](ADR/174-proposed-opt-in-authenticated-voice-integration.md)) |

**Ba lượt B3: hai lượt đầu NOT_PASS, lượt theo ADR178 PASS:**

- **Lượt đầu, 2026-11-05** ([ADR176, mục Context](ADR/176-bounded-foreign-gpu-tolerance-and-b3-preflight.md)): `main_voice_prepare_fault`, 6/6 dòng chưa thử, 0 retry. Guard thực sự kích hoạt không được log. Nguyên nhân khả dĩ có bằng chứng là quy tắc NVML của ADR175, từ chối mọi tiến trình GPU ngoài các worker voice sở hữu và CORE mượn: bản ghi NVML sau lỗi có `gnome-remote-desktop` (khoảng 223 MiB), ngày 2026-11-06 thấy ba tiến trình desktop. ADR176 để ngỏ câu hỏi RSS (đỉnh 7,71 GiB khi nạp model); preflight lượt thay thế đo RSS ổn định của CORE khoảng 0,96 GiB, nên cap RAM 8 GiB không phải nguyên nhân *(operator 2026-11-06)*.
- **ADR176** (ACCEPTED 2026-11-06; vào `develop` qua PR #26, lên `production` qua PR #31 ngày 2026-11-07): chấp nhận tiến trình GPU ngoài tổng tối đa 1 GiB, giữ cap free-VRAM và RAM, thêm preflight tự động và cho đúng một panel thay thế.
- **Lượt thay thế duy nhất theo ADR176, 2026-11-06 17:45** *(operator 2026-11-06; receipt private `data/backups/d74-main-integration-adr176/`)*: software gate 1070 test Python liên quan và 27 JS PASS; preflight RSS CORE 1.031.987.200 byte, 2 tiến trình GPU ngoài dùng 272.539.648 byte; Prepare 56,78 s; 4/4 câu nói `EXACT_COMPLETE_PCM`, server 2,247 / 2,736 / 3,241 / 3,178 s; 2/2 negative `CORRECT_NO_SPEECH` trong khoảng 0,017 s; số lượt đúng vad 6 / asr 4 / core 4 / tts 4, readiness 1, 3 worker joined; CORE sở hữu exit 0, đã reap, guard failure null; không còn native pid; source không đổi.
- **Kết quả lượt thay thế: NOT_PASS**, mã `main_voice_call_budget_or_cleanup`. Runner gửi SIGTERM cho web process rồi yêu cầu mã thoát 0 (kiểm tra `web.returncode != 0` trong [main_voice_integration.py](../benchmarks/scripts/main_voice_integration.py), có trên `develop` `eeabbe8` lúc đó; ADR178 đã thay kiểm tra này). uvicorn 0.54.0 (khóa trong `uv.lock`) lại gọi `signal.raise_signal` cho SIGTERM đã bắt sau khi shutdown graceful hoàn tất (`Server.capture_signals`), nên web thoát với -15; app log có đủ lifespan shutdown *(operator 2026-11-06)*. Vì vậy runner chưa đánh giá bước kiểm tra sau đó: CORE mượn còn sống sau khi app tắt. Theo ADR176 không chạy retry. Kết quả giữ NOT_PASS; khi đó mọi panel tiếp theo cần điều kiện tiên quyết ở C mục 2 và quyết định mới của chủ dự án. Cả hai nay đã có (xem ADR178 bên dưới).
- **ADR178** (ACCEPTED 2026-11-07; vào `develop` qua PR #28, merge `73cecdf`; lên `production` qua PR #31 ngày 2026-11-07): ngày 2026-11-06 chủ dự án trả lời "Duyệt B3 mới", tức sửa runner rồi chạy đúng một panel mới. Runner chỉ chấp nhận mã thoát 0 hoặc -15 của web process khi audit có đủ 5 sự kiện tắt lifespan voice, đúng thứ tự, mỗi sự kiện đúng một lần, và không có dòng quarantine, Traceback, ERROR hay CRITICAL. ADR178 cũng đòi cả 3 worker join sạch (exit 0, không bị ép dừng, vai trò khác nhau), release trả HTTP 200 với trạng thái sau release `idle` không lỗi, và che token cùng mã pairing trong bản log thô giữ lại ở nhánh lỗi. Review đối kháng trước merge xác nhận 5/8 phát hiện; mọi phát hiện về code đã được sửa trước merge.
- **Lượt duy nhất theo ADR178, 2026-11-07 10:31** ([receipt công khai](evidence/d74-main-voice-b3-adr178-result.json); receipt private `data/backups/d74-main-integration-adr178/`): software gate 1.122 test Python liên quan và 27 JS PASS trên `73cecdf`, ghim SHA-256 của 307 file nguồn; preflight RSS CORE 1.255.170.048 byte (khoảng 1,17 GiB), 2 tiến trình GPU ngoài dùng 235.839.488 byte (khoảng 225 MiB); Prepare 51,45 s; 4/4 câu nói `EXACT_COMPLETE_PCM`, server 3,412 / 2,608 / 3,747 / 3,182 s; 2/2 negative `CORRECT_NO_SPEECH` trong khoảng 0,017–0,024 s; cả 6 dòng có SHA-256 playback, PCM và WAV trùng lượt ADR176; số lượt đúng vad 6 / asr 4 / core 4 / tts 4, readiness 1, 3 worker join sạch; web exit -15 với tắt êm đã được chứng minh (`web_shutdown_graceful: true`); release HTTP 200, trạng thái sau release `idle` không lỗi; CORE mượn còn sống sau khi app tắt, lần đầu bước này được đánh giá trong một lượt B3; CORE sở hữu exit 0, đã reap, guard failure null; audit không có dòng ERROR/CRITICAL/Traceback hay credential; không còn native pid; source không đổi; 0 retry.
- **Kết quả lượt ADR178: PASS** cho bước B3 của [ADR174](ADR/174-proposed-opt-in-authenticated-voice-integration.md) trên đường `/voice` mặc định tắt. Thời gian server là xử lý cộng HTTP loopback, không phải lúc loa phát. Dải server 2,608–3,747 s so với 2,247–3,241 s ở lượt ADR176: dòng 0036 tăng từ 2,247 lên 3,412 s, chủ yếu do LLM (0,511 → 1,082 s), và dòng chậm nhất chỉ còn khoảng 0,25 s dưới trần 4 giây. PASS này không đổi nhãn NOT_PASS của hai lượt trước. Nó không bật voice (`ASSISTANT_VOICE_ENABLED` vẫn mặc định `0`, chỉ cho mục đích `integration_evaluation`), không xác lập first-audible vật lý ≤4 giây (B4), câu ngắn, giọng nhỏ hay tiếng ồn phòng, và không chọn model, giọng hay default.

**Giới hạn khác của B:**

- First-audible vật lý ≤4 giây vẫn UNVERIFIED.
- Chưa đo ASR với câu ngắn, giọng nhỏ hay tiếng ồn phòng.
- Phụ âm cuối tiếng Anh của Trúc Ly chưa rõ: "this" nghe thành "dít" ([Trúc Ly](D74_TRUC_LY_VALIDATION_RESULT.md)).
- Voice giữ GPU cho tới khi đóng phiên.
- Chưa chọn model, giọng hay default.

### Phương án C — chờ D74 vật lý và D60 rồi mới tag (B3 đã PASS ngày 2026-11-07)

Chưa tag lúc này. Các điều kiện cần có trước khi quay lại D90:

1. **Đã hoàn tất (2026-11-07):** promote `develop` (LICENSE, ADR176, ADR178) lên `staging` (PR #30, `0ec664d`) và `production` (PR #31, `4dcf8db`).
2. **Đã hoàn tất (2026-11-07):** điều kiện tiên quyết cho panel B3 mới là một thay đổi runner đã review cho kiểm tra exit của web process, kèm regression test và ghi chú ADR. [ADR178](ADR/178-graceful-sigterm-exit-in-b3-acceptance.md) (PR #28, merge `73cecdf`) đáp ứng điều kiện này: runner chỉ chấp nhận -15 khi audit chứng minh lifespan shutdown hoàn tất, có regression test và review trước merge. Thay đổi này không đổi nhãn kết quả ADR176: kết quả đó vẫn NOT_PASS. Chủ dự án đã duyệt việc sửa runner cùng đúng một panel mới ngày 2026-11-06, và panel đó cho kết quả PASS ngày 2026-11-07 ([receipt](evidence/d74-main-voice-b3-adr178-result.json)). B3 không còn là điều kiện chờ của C.
3. Chủ dự án đo first-audible vật lý ≤4 giây (B4), đo thêm ASR câu ngắn, giọng nhỏ và tiếng ồn. Phiếu đo là [checklist đo vật lý](D74_PHYSICAL_FIRST_AUDIBLE_CHECKLIST.md), chưa có kết quả; vì B3 đã PASS, checklist có thể lặp lại trên `/voice`. [Yêu cầu voice](VOICE_PRODUCT_REQUIREMENTS.md) ghi VOICE-LATENCY-AC-001 còn cần measurement plan.
4. Chủ dự án chốt model, giọng và default cho voice.
5. D60 đạt 8/8 trên panel coverage cố định. Hiện D60 đang được chủ dự án để pending, không có ngày ([các D còn mở](OPEN_DAYS_20261105.md)).
6. Chạy một D87 full regression mới trên đúng commit sẽ tag.

**Rủi ro của C:**

- Rủi ro panel B3 mới lặp lại NOT_PASS của lượt ADR176 đã được xử lý: runner được sửa theo ADR178 (mục 2) và panel duy nhất được duyệt đã PASS. Rủi ro còn lại của D74 nằm ở các phần chủ dự án phải làm (đo vật lý B4, câu ngắn/giọng nhỏ/ồn phòng, chốt model/giọng/default), chưa có lịch. Thời gian B3 chưa gồm độ trễ phát của trình duyệt và loa, trong khi dòng chậm nhất chỉ còn khoảng 0,25 s dưới trần 4 giây, nên biên cho B4 hẹp. Nếu sau này cần thêm panel B3, theo ADR176 preflight tự động trong `benchmarks/scripts/main_voice_integration.py` dừng run trước khi nạp model voice nếu RSS CORE ≥ 6 GiB hoặc GPU ngoài vượt 1 GiB. Kết quả `PREFLIGHT_STOPPED` (`panel_consumed: false`) không phải kết quả B3 và không tiêu panel; panel chỉ tính là đã dùng khi `/ui/voice/prepare` được gọi.
- D60 phụ thuộc upstream và chưa có lịch, nên C có thể chặn D90 vô thời hạn.

Biến thể C1 chỉ chờ D74 và tiếp tục hoãn D60.

## 3. Bảng gate

| Gate | Bằng chứng hiện có | Còn thiếu | Ai phải làm | Trạng thái | Cần cho A / B / C |
|---|---|---|---|---|---|
| D74 | [Rà soát quyền](D74_VOICE_RIGHTS_REVIEW.md); trang thử 6/6; buffered PASS; "Ổn rồi" (không phải số đo); B1/B2 mặc định tắt ([apps/api/voice.py](../apps/api/voice.py)); B3 lượt đầu NOT_PASS ([ADR176](ADR/176-bounded-foreign-gpu-tolerance-and-b3-preflight.md)); lượt thay thế NOT_PASS *(operator 2026-11-06)*; **B3 PASS ngày 2026-11-07** theo [ADR178](ADR/178-graceful-sigterm-exit-in-b3-acceptance.md) ([receipt](evidence/d74-main-voice-b3-adr178-result.json)): 4/4 câu nói đúng, server 2,608–3,747 s, 2/2 negative, ngân sách và dọn dẹp đạt, CORE mượn còn sống sau khi app tắt | Đo first-audible vật lý ≤4 giây (B4, theo [checklist](D74_PHYSICAL_FIRST_AUDIBLE_CHECKLIST.md)); ASR câu ngắn/giọng nhỏ/ồn phòng; quyết định bật dùng sản phẩm; chốt model, giọng, default | Chủ dự án: đo vật lý, quyết định sản phẩm, chốt lựa chọn | OPEN | A: hoãn. B: chỉ nhãn nghiên cứu. C: bắt buộc |
| D81 | Workflow gốc đạt 3/3 qua adapter tùy chọn ([D81](D81_CROSS_DOMAIN_ORCHESTRATION.md)); lượt FMT-002 1/6 FAIL vẫn giữ ([D81-FMT-002](D81_FROZEN_EXCERPT_PROTOCOL_EVALUATION.md)) | Tích hợp vào luồng sản phẩm chính và nghiệm thu toàn luồng cho phạm vi được chọn ([các D còn mở](OPEN_DAYS_20261105.md)) | Engineering soạn đề xuất tích hợp; chủ dự án duyệt | OPEN | Hoãn ở cả ba, trừ khi chủ dự án chọn khác |
| D86 | Recorder UI đã kiểm tra ([D86](D86_UI_RELEASE_CANDIDATE_REVIEW.md)); UI voice chính có test riêng ([client](../tests/test_main_voice_client.mjs), [smoke](../tests/main_voice_browser_smoke.mjs)) | Xác nhận không còn blocker nghiêm trọng trong phạm vi được chọn. A không có UI văn bản để nghiệm thu | Chủ dự án và engineering | OPEN | Cả ba đều cần xác nhận |
| D87 | Full 5.889 PASS / 0 FAIL / 0 ERROR / 0 SKIP trên 750 file, ngày 2026-11-03 ([receipt](evidence/d60-fresh-20261103-final-acceptance.json)). Đây là kết quả lịch sử, có trước B1/B2, ADR176, ADR178 và CI | Full regression với PostgreSQL, Vault và CORE thật trên commit sẽ tag, theo [protocol](D87_FULL_REGRESSION_PROTOCOL.md). [scripts/full_regression.py](../scripts/full_regression.py) chỉ chạy `pytest tests`; benchmark controls báo riêng; supervisor sở hữu CORE và audit bảo toàn của lượt 5.889 là script private | Chủ dự án chạy theo runbook `docs/D87_FULL_REGRESSION_20261106_RUNBOOK.md` (thêm trong cùng PR) *(owner 2026-11-06, operator record)*; engineering đối chiếu receipt | OPEN cho source hiện tại | Cả ba: docs yêu cầu D87 hiện hành cho D90 ([các D còn mở](OPEN_DAYS_20261105.md), [roadmap](LOCAL_ASSISTANT_MASTER_ROADMAP.md) Phase 7). Tag không có D87 là ngoại lệ phải ghi tên trong phiếu |
| D88 | Cài sạch Python 3.12 đã kiểm chứng ([D88](D88_CLEAN_INSTALL_REHEARSAL.md)); [scorecard](D88_MODEL_PROVENANCE_SCORECARD.md); rà soát quyền; LICENSE MIT vào `develop` qua PR #25, lên `production` qua PR #31 (2026-11-07) | SBOM/notice chỉ cần khi phân phối binary hoặc weights. Quyền của UNRESTRICTED và embedding chưa được rà soát ở mức tương đương | Chủ dự án duyệt; engineering chuẩn bị SBOM/notice nếu phân phối | OPEN | Cả ba đều cần LICENSE trên commit được tag (đã có trên `production` từ PR #31) |
| D89 | Đối chiếu 14 workflow; nghe 24/24; smoke micro thật | Ba ô chưa tick: lifecycle preview/xóa/TTL; review model và license; duyệt phạm vi và giới hạn | Chủ dự án | OPEN | A: phần lifecycle voice được hoãn. B và C: cần đủ |
| D90 | NOT APPROVED / NOT TAGGED / NOT DEPLOYED | Phiếu quyết định ở mục 5 | Chủ dự án | OPEN | — |

CI hosted chưa đáp ứng D87. CI chạy cả `tests` lẫn `benchmarks/tests`, loại trừ 39 mục, có test tự skip và không có PostgreSQL, Vault hay CORE ([ci.yml](../.github/workflows/ci.yml)). Vì vậy số liệu của CI không so được với 5.889 (chỉ `tests/`). Tiêu chí D87 là 0 FAIL/0 ERROR/0 SKIP cho `pytest tests` trên commit được freeze, với inventory source đầy đủ không đổi; benchmark controls báo riêng ([protocol](D87_FULL_REGRESSION_PROTOCOL.md)).

## 4. Các giới hạn sẽ được chấp nhận rõ ràng

Dòng 5 là precondition P2 còn mở, không phải giới hạn mặc nhiên được chấp nhận; phiếu ở mục 5 có ô riêng cho nó.

| # | Giới hạn | Bằng chứng | Áp dụng cho |
|---|---|---|---|
| 1 | **Coding:** D46 đạt 7/10 (2 candidate fail assertion native, 1 đề xuất bị contract từ chối). CODE-EVAL-002 đạt 7/12 ở cả nhánh baseline lẫn concise. CE005 12/12 chỉ đúng với cohort đã chọn | [D46](D46_CODING_AGENT_MVP_SCORECARD.md), [CE002](CODE_EVAL_002_FIRST_SCORECARD.md), [D46/D60](D46_D60_REMEDIATION_RESULT.md) | A, B |
| 2 | **D60 Brave:** lượt gần nhất có 3 hợp lệ, 1 rate-limit, 4 chưa chạy; tiêu chí là 8/8. Vẫn giữ Brave, chưa đổi provider | [D60 resumed](D60_BRAVE_RESUMED_RESULT.md), [các D còn mở](OPEN_DAYS_20261105.md) | A, B |
| 3 | **OCR chỉ hỗ trợ tiếng Anh;** điểm engine chưa hiệu chuẩn; VLM luôn cần review | [ADR029](ADR/029-page-ocr-and-local-vision.md), [D62](D62_NATIVE_CORE_OCR_QUALITY.md) | A, B |
| 4 | **Trúc Ly tiếng Anh:** chủ dự án chấp nhận mức hiện tại nhưng phụ âm cuối chưa rõ; đã dừng tinh chỉnh | [Trúc Ly](D74_TRUC_LY_VALIDATION_RESULT.md) | B |
| 5 | **Lỗi decoder P2 gián đoạn (precondition còn mở):** một lượt 236 case có 1 FAIL `audio_invalid_content`; các lượt sau PASS; chưa xác định nguyên nhân. Ledger yêu cầu điều tra P2 trước khi nghiệm thu sản phẩm. Tag khi chưa điều tra cần miễn trừ rõ của chủ dự án. Trên CI, 3 file test media và 1 test OCR phụ thuộc thời gian chạy trong job quarantine, không chặn release | [Ledger](OUTSTANDING_WORK_STATUS.md), [các D còn mở](OPEN_DAYS_20261105.md), [danh sách quarantine](../.github/ci/hosted-runner-quarantine.txt) | A, B (chỉ khi có miễn trừ) |
| 6 | **Nợ lint:** CI chỉ lint các file Python thay đổi khi vào `develop`. Promotion và tag bỏ qua lint vì nợ có sẵn trong các file lịch sử được bảo vệ bằng hash. Quy mô nợ chưa được đo trong docs | [ci.yml](../.github/workflows/ci.yml) (job `prepare`) | A, B |
| 7 | **Không có branch protection:** repo private trên GitHub Free; API branch protection/rulesets trả 403 *(operator 2026-11-06)*. GitHub không chặn merge hay push khi CI đỏ; chủ dự án tự giữ kỷ luật PR và `ci-gate` | — | A, B |
| 8 | **CI có loại trừ:** [danh sách](../.github/ci/hosted-runner-exclusions.txt) trong checkout này có 39 mục kèm lý do. Lý do gồm: cần dữ liệu private, cần CORE đang chạy, cần Brave/CDP, export LibreOffice, Tesseract 5.5.0, cần ≥14 GiB RAM trống cùng artifact model voice cục bộ, và cần `../infras/searxng-server` nằm ngoài repo này. CI hosted chỉ là kiểm tra phần mềm, không thay D87 và không đo chất lượng model | [hosted_exclusions.py](../.github/ci/hosted_exclusions.py) | A, B |
| 9 | **Ranh giới cục bộ:** localhost, một worker, chưa có web chat văn bản; chưa chứng nhận OIDC, TLS, multiworker hay off-host recovery | [Release status](RELEASE_CANDIDATE_STATUS.md) | A, B |
| 10 | **Chất lượng model:** chỉ có điểm D14 tổng hợp cục bộ, không có kết luận về năng lực tổng quát | [D14 scorecard](D14_COMPLETION_SCORECARD.md), [D88 scorecard](D88_MODEL_PROVENANCE_SCORECARD.md) | A, B |

## 5. Phiếu quyết định (chủ dự án điền)

Một câu trả lời chung như "Ổn rồi" không thay cho phiếu này. Nếu phiếu chưa được điền, D90 vẫn OPEN.

```text
Người quyết định: ______________________   Ngày quyết định: ____-__-__

Phạm vi chọn:        [ ] A    [ ] B    [ ] C (chưa tag)    [ ] C1 (chỉ chờ D74)
UNRESTRICTED nằm trong phạm vi hỗ trợ:   [ ] Có    [ ] Không
Commit production được tag (SHA đầy đủ): ________________________________
Tên tag:             ________   (đề xuất v0.1.0; không dùng v1.0)
LICENSE MIT trên production:             [ ] Có, promotion PR #31 (vào develop qua PR #25)
D87 hiện hành (docs yêu cầu cho D90):    receipt: ____________ (pytest tests 0 FAIL/0 ERROR/0 SKIP, cùng SHA)
                     [ ] Ngoại lệ có tên: tag không có D87 hiện hành, lý do: __________
P2 decoder (mục 4, dòng 5):  [ ] Đã điều tra trước tag   [ ] Miễn trừ cho tag này, lý do: ______

Giới hạn chấp nhận (mục 4):  [ ]1 [ ]2 [ ]3 [ ]4 [ ]6 [ ]7 [ ]8 [ ]9 [ ]10
Mục hoãn ghi rõ:     [ ] D74 vật lý (B4)/model-giọng-default   [ ] D81 tích hợp sản phẩm
                     [ ] D60 coverage 8/8   [ ] harness D75–D80   [ ] khác: __________
Điều kiện hoặc ghi chú thêm: ______________________________________________
Xác nhận:            ______________________
```

Lưu ý về tên tag: repo đã có [releases/v0.1/release-manifest.json](../releases/v0.1/release-manifest.json). Đây là baseline runtime nội bộ `shldd-personal-ai-v0.1` ngày 2026-10-13, không phải Git tag. Nếu chọn `v0.1.0`, ghi rõ trong phiếu rằng tag mới khác với manifest đó.

## 6. Sau khi phê duyệt

1. Ghi phiếu đã điền vào file này qua một PR `docs:` vào `develop`. Engineering không điền thay chủ dự án.
2. Promote `develop` → `staging` → `production` qua PR, giống PR #22/#24 và #30/#31, để commit được tag có cả phiếu đã ghi. LICENSE (PR #25), ADR176 (PR #26) và ADR178 (PR #28) đã lên `production` qua PR #31 ngày 2026-11-07.
3. Chủ dự án chạy D87 trên đúng commit sẽ tag, theo runbook `docs/D87_FULL_REGRESSION_20261106_RUNBOOK.md`. Engineering đối chiếu receipt theo [protocol](D87_FULL_REGRESSION_PROTOCOL.md): `pytest tests` đạt 0 FAIL, 0 ERROR, 0 SKIP và inventory source không đổi. Nếu không đạt thì dừng, không tag; kết quả lỗi được giữ nguyên. Chỉ bỏ bước này khi phiếu ghi ngoại lệ D87 có tên.
4. Chủ dự án tạo annotated tag trên đúng SHA ghi trong phiếu rồi push tag lên GitHub.
5. Khi nhận tag, CI chạy các bước sau ([ci.yml](../.github/workflows/ci.yml)):
   - Chạy `prepare`, `test-python`, `test-js` và `ci-gate`. Lint được bỏ qua với tag. Job quarantine vẫn chạy nhưng không chặn.
   - Job `package` tạo `local-assistant-<tag>-<sha7>.tar.gz` và `SHA256SUMS`, lưu làm artifact 30 ngày.
   - Job `release` chạy trong GitHub environment `production` và gọi `gh release create --generate-notes --verify-tag` để publish GitHub Release kèm bundle.
6. Không có bước deploy. Workflow chỉ gắn job `release` với environment `production`; quy tắc bảo vệ của environment đó (nếu có) chưa được kiểm tra. Home Server, dịch vụ dùng chung, model, config và `ASSISTANT_VOICE_ENABLED=0` giữ nguyên.
7. Nếu CI đỏ, tag vẫn tồn tại nhưng không có Release. Không tự xóa hay di chuyển tag; chủ dự án quyết định bước tiếp theo.
8. Sau khi có Release, engineering cập nhật [release status](RELEASE_CANDIDATE_STATUS.md), [ledger](OUTSTANDING_WORK_STATUS.md), [roadmap](LOCAL_ASSISTANT_MASTER_ROADMAP.md) và `dev_log/dev_log.md` với tag, SHA, Release và SHA256 thực tế. Release notes tự sinh chỉ liệt kê PR, nên cần thêm link tới hồ sơ này để nêu giới hạn. Các gate đã hoãn vẫn OPEN; tag không đóng D74, D81 hay D60.
