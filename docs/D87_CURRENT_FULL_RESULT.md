# D87 — Full regression trên source hiện tại

**Mục đích:** Ghi kết quả full suite hiện hành ngày 2026-11-09 trên cây source của `production` `0b67d95`: lệnh, source, dịch vụ, số liệu, kiểm tra database sau test, so sánh với CI, phạm vi và ảnh hưởng tới D90. Kết quả hiện hành trước đó (ngày 2026-10-27) được giữ nguyên ở mục lịch sử cuối trang.

**Trạng thái: PASS — full software regression cho cây source của `production` `0b67d95` (2026-11-09).** [Receipt công khai](evidence/d87-20261109-full-acceptance.json). Đây là bằng chứng hồi quy phần mềm cho đúng cây source này, không phải đo chất lượng model, nghiệm thu thiết bị, D89 hay quyết định release.

| Phạm vi | Kết quả thực tế |
|---|---|
| Toàn bộ `pytest tests` | **6.200 PASS / 0 FAIL / 0 ERROR / 0 SKIP**, exit 0, status `complete`, `accepted_full_software_regression: true` |
| Thời gian pytest | **1.869,85 giây** (summary "6200 passed, 1 warning in 1869.85s (0:31:09)"); wrapper 1.871,66 giây |
| Source snapshot | **817 file** trong `src`, `apps`, `scripts`, `tests`, `configs`, `pyproject.toml`, `uv.lock`; `source_bytes_unchanged: true` |
| Commit và cây | `develop` `3812e5c`, cây `0ed89bcbfad4ffafb14cea32bd27f73c63467ada`, trùng cây của `production` `0b67d95` |
| Source freeze SHA-256 | `307a312938952bbb16edae149bf58959e98bfb78dfb4966335fb89bacf1391c6` |
| Log SHA-256 | `11fdb7102c8c08c6fdd73f2cf16ae159e8b9e7ca13c448571c9c44521fb359a2` |
| Cảnh báo | Summary ghi 1 warning; receipt công khai không ghi nội dung warning |
| So với full trước | 5.889 PASS trên 750 file ngày 2026-11-03 ([receipt](evidence/d60-fresh-20261103-final-acceptance.json)) nay là lịch sử |

Lượt chạy bắt đầu 10:31 (2026-11-09T03:31:46Z) và kết thúc 11:02 (2026-11-09T04:02:58Z) theo Asia/Ho_Chi_Minh. Thư mục kết quả `data/backups/d87-20261109-full` (`result.json`, log, source freeze) là private, bị git bỏ qua và không công bố; receipt chỉ ghi tên thư mục và các SHA-256 ở trên.

## Lệnh, source và dịch vụ (2026-11-09)

Ngày 2026-11-09 chủ dự án yêu cầu "Tiếp theo làm D81, D87 đi"; với câu hỏi về thứ tự D87, chủ dự án chọn "Sau D81 + promote (Recommended)": merge D81, promote `develop` → `staging` → `production` (không tag, không deploy), rồi chạy D87 trên commit đó. Assistant chạy D87 theo yêu cầu đó, theo [runbook](D87_FULL_REGRESSION_20261106_RUNBOOK.md):

1. Chạy từ `ai/` trên `develop` `3812e5c`; lệnh kiểm tra cây ở bước 1 của runbook in "develop trùng production". `uv sync --locked --dev` không thay đổi gì. Phạm vi source sạch: không có file sửa dở hay untracked trong `src/`, `apps/`, `scripts/`, `tests/`, `configs/`, `pyproject.toml`, `uv.lock`.
2. Vault đã bị seal lại (container chạy được khoảng 3 giờ). Assistant unseal Vault từ bootstrap file theo ủy quyền của chủ dự án ngày 2026-11-08: ba key share được nộp trong process, không in ra. Script đọc credential trong bộ nhớ qua `../infras/scripts/vault_static_secret.py` như thiết kế.
3. CORE khởi động bằng `docker compose --profile core up -d`: container `local-assistant-core-1`, image `local-assistant/llama-cuda:5c8854fd8`, model `qwen3.5-9b-core` ở `127.0.0.1:8080`, health 200. Sau lượt chạy, CORE được dừng bằng `docker compose --profile core stop`. PostgreSQL, Vault và Qdrant không bị restart.
4. Lệnh:

   ```bash
   uv run --no-sync python -m scripts.full_regression data/backups/d87-20261109-full
   ```

   Script chạy `pytest tests` (không gồm `benchmarks/tests`, không loại trừ gì) và tự đặt các biến môi trường, trong đó có `DATABASE_URL`, `LOCAL_ASSISTANT_LIVE_E2E=1`, `LOCAL_ASSISTANT_EMBEDDING_COMPARE_LIVE=1`.

Đợt merge và promote trước lượt chạy: PR #42 (D81) merge vào `develop` lúc 10:03 (2026-11-09T03:03:20Z) thành `3812e5c`; PR #43 (`develop` → `staging`) merge lúc 10:13 (2026-11-09T03:13:38Z) thành `2790b4e`; PR #44 (`staging` → `production`) merge lúc 10:30 (2026-11-09T03:30:56Z) thành `0b67d95`. Sau đợt promote, `origin/develop` (`3812e5c`) và `origin/production` (`0b67d95`) có cùng cây (kiểm bằng `git rev-parse <ref>^{tree}`). Không có tag, GitHub Release hay deploy lên Home Server; voice vẫn mặc định tắt.

## Kiểm tra database sau lượt chạy

Truy vấn read-only bằng runtime role trên database `local_assistant` sau lượt chạy: conversations 0, messages 0, inference_runs 0, files 0, memories 0, memory_consents 0, memory_settings 0, ingestion_jobs 0, ingestion_heads 0, file_owner_usage 1 (dòng giá trị 0 có từ trước), file_global_usage 1 (dòng bộ đếm bằng 0); Alembic revision `0006`, như trước lượt chạy. Đây là số dòng sau test và revision, không phải phép so sánh từng dòng trước/sau như audit ngày 2026-10-27; receipt này cũng không ghi inventory Qdrant.

## So sánh với CI

CI và D87 đo hai thứ khác nhau. Số 6.456 của CI đếm `tests` cùng `benchmarks/tests`, có 39 mục loại trừ và không có DB/CORE; số 6.200 của D87 chỉ là `pytest tests`, không loại trừ gì, với dịch vụ thật. Hai số này không so được với nhau.

Run push lên `production` (run 42556825440, commit `0b67d95`) thành công: job chính 6.456 passed, 368 skipped, 31 deselected; job cách ly thành công; `package` tạo artifact `local-assistant-production-0b67d95` (14.017.331 byte). Trong đợt promote, run push lên `staging` (run 42555210293, commit `2790b4e`) lỗi ở lần đầu: 1 failed, 6.455 passed, tại `tests/test_pdf_extractor.py::test_real_timeout_reaps_worker` (marker của worker bị treo vẫn thấy trong một `/proc/*/cmdline` ngay sau khi reap do timeout). Cùng commit đã pass ở PR run 42554274811, và lần chạy lại các job lỗi thành công. Lỗi này cùng dạng với test đã cách ly `tests/test_page_ocr.py::test_timeout_reaps_worker_and_descendant`; test PDF chưa có trong `.github/ci/hosted-runner-quarantine.txt` và chưa có gì được sửa. Việc tiếp theo có thể làm: thêm test này vào danh sách cách ly (PR cấu hình CI) hoặc làm chắc phần kiểm tra reap.

## Phạm vi và ảnh hưởng tới D90

Lượt này là bằng chứng hồi quy phần mềm cho cây source của `production` `0b67d95`, gồm code D81 mặc định tắt, bản sửa decoder của PR #33, code voice B1/B2, ADR176 và ADR178. Đây không phải đo chất lượng model, nghiệm thu thiết bị, D89 hay quyết định release.

D87 dùng cho D90 phải chạy trên đúng nội dung của commit sẽ tag ([hồ sơ D90](D90_RELEASE_DECISION_DOSSIER.md) mục 6, [runbook D87](D87_FULL_REGRESSION_20261106_RUNBOOK.md) bước 1). Tại ngày 2026-11-09, lượt này khớp `production` `0b67d95`. Mọi commit chỉ có tài liệu về sau (kể cả PR ghi lại lượt chạy này và phiếu D90 chủ dự án đã điền) làm đổi cây của commit, nhưng không đổi phạm vi source freeze của D87 (src, apps, scripts, tests, configs, pyproject.toml, uv.lock). Chấp nhận khác biệt chỉ có tài liệu đó cho tag, hay chạy lại D87 trên commit tag cuối cùng, là quyết định của chủ dự án khi điền phiếu D90 (phiếu có ô ngoại lệ có tên). Phiếu D90 chưa được điền ở đây.

Vẫn mở hoặc không đổi: D81 vẫn OPEN (code đã merge ở trạng thái mặc định tắt và đã promote; chưa có nghiệm thu full-flow và chưa chạy native v4). D89 và D90 mở; D60 hoãn; quyết định model/voice/default/sản phẩm cho voice còn mở; voice mặc định tắt; không tag, không release, không deploy. D88 chỉ cần nếu phân phối.

## Lịch sử: kết quả ngày 2026-10-27

Phần dưới đây là nội dung hiện hành của trang này trước ngày 2026-11-09, giữ nguyên làm lịch sử; các trạng thái "còn mở" trong đó là trạng thái lúc ấy. Sau lượt này còn các full 5.837 PASS trên 745 file (ngày 2026-11-02) và 5.889 PASS trên 750 file (ngày 2026-11-03, [receipt](evidence/d60-fresh-20261103-final-acceptance.json)), trước lượt 2026-11-09; cả hai cũng là lịch sử.

**Mục đích:** Ghi kết quả full suite ngày 2026-10-27, phạm vi source, kiểm tra bảo toàn sau test và các gate còn mở.

**Trạng thái: VERIFIED — full software regression.** [Terminal và audit receipt](evidence/d87-current-20261027-full-acceptance.json), [preflight trước lượt chạy](evidence/d87-current-20261027-preflight.json).

| Phạm vi | Kết quả thực tế |
|---|---|
| Toàn bộ `pytest tests` | **5.759 PASS / 0 FAIL / 0 ERROR / 0 SKIP**, exit 0 |
| Thời gian pytest | **1.870,65 giây**; wrapper 1.872,69 giây |
| Source/config/test snapshot | **732 file**, inventory và SHA giữ nguyên trước/sau |
| So với full cũ | Toàn bộ 728 file của full 5.674 vẫn khớp byte; bốn file adapter/test D14 bổ sung đã nằm trong full mới |
| Cảnh báo | Một warning cố ý từ fixture ZIP có entry trùng `piper/voice.py`; test từ chối archive này PASS |
| Benchmark controls riêng | 183 PASS / 2,26 giây; không cộng vào 5.759 |
| Operator controls riêng | Supervisor/runner/lifecycle 71 PASS; audit policy 46 PASS; delivery policy ban đầu32 PASS, cuối43 PASS; các scope có overlap, không cộng thành một full suite |

Lượt chạy bắt đầu 11:29:08 và kết thúc 12:00:21 theo Asia/Ho_Chi_Minh. Source ứng dụng không cần sửa. Không tải hoặc thay model, thay default/API/config, đổi provider, schema, ACL hay collection. Các live integration test dùng runtime và credential hiện có; kết quả software regression không ghi đè điểm benchmark đầu tiên.

### Điều kiện chạy và cleanup

Sau reboot, máy không có native worker và Vault đã initialized nhưng sealed. Operator unseal đúng Vault hiện có bằng bootstrap material đã lưu, chỉ đọc credential vào bộ nhớ; không init/rotate hoặc sửa policy. Vault được giữ unsealed và thay đổi trạng thái này được ghi trong audit.

Supervisor dùng đúng CORE/model/projector/context hiện có tại cổng 8080, fixture umask 0022, log/metadata riêng tư và một process group sở hữu riêng. CORE exit 0, đã reap, guard failure null; full runner cũng exit 0 và đã join. Sau cleanup, cùng boot, cùng 15 container identities/images/ports và native=0 như baseline đầu lượt chạy.

Peak RSS của toàn CORE worker là 8.081.632 KiB, khoảng **7,71 GiB RAM**; sampled peak VRAM **8.910 MiB**. Đây là hai phép đo khác nhau, không phải virtual address-space cap hoặc tổng bộ nhớ cả máy.

Lỗi gọi trực tiếp private script thiếu import `scripts` được giữ trong log. Lỗi xảy ra trước khi có worker hoặc thư mục full suite. Cách gọi được sửa bằng runpy từ `ai/`, không sửa application source hoặc chạy lại một full đã thất bại. [Protocol và lệnh thực thi](D87_FULL_REGRESSION_PROTOCOL.md#current-reboot-aware-run--2026-10-27).

### Kiểm tra dữ liệu sau suite

Đối chiếu read-only với snapshot chụp trước test: schema 0006, security/owners/ACL và 11 bảng khác giữ nguyên. Chỉ `assistant.file_global_usage.updated_at` thay đổi do upload/delete test; complete singleton row vẫn 0 byte, 0 file, 0 active upload. Vì vậy **strict all-row equality=False**, còn qualified preservation=True. Không restore timestamp, chạy restore probe hoặc chuẩn hóa để giấu thay đổi.

Authenticated Qdrant inventory sau test rỗng. Không có authenticated collection snapshot cùng boot trước suite, nên receipt chỉ khẳng định inventory sau test; không bịa một phép so sánh trước/sau. Restore probe count=0, không còn app connection/pending inference khi audit. 916/917 older protected files khớp byte; ngoại lệ duy nhất là thay đổi tài liệu MODEL_REGISTRY đã được duyệt từ trước. Toàn bộ 176 original inputs và worksheet D70 chưa nghe giữ nguyên.

### Phạm vi hoàn tất và việc tiếp theo

D87 current-source software refresh hoàn tất. D14 selected semantic path vẫn VERIFIED_LOCAL_OPT_IN trên fresh 42/42 mỗi profile; mọi điểm FAIL/composite cũ được giữ nguyên. Full software PASS không tự phê duyệt tích hợp API/default hoặc chất lượng coding/web rộng hơn.

D70 nghe thực tế vẫn **0/24 owner-deferred**; [hướng dẫn nghe](D70_MANUAL_LISTENING_TEST.md) đã sẵn sàng. D74 voice/model/license/no-speech, D81 product integration, D86/D89 product/device acceptance, các gate D88 liên quan model/license và D90 release vẫn mở theo [ledger](OUTSTANDING_WORK_STATUS.md). Không push, tag, deploy hoặc tuyên bố toàn dự án hoàn thành.

Root `AGENTS.md` untracked và dòng IDE riêng đầu devlog được giữ nguyên, ngoài commit và ZIP D87. Gói đầy đủ sau commit: `data/backups/local-assistant-d87-20261027-full-files.zip`, kèm receipt và manifest. Gói giữ các artifact lịch sử theo SHA, full phiên bản file Git và operator/test/log được chọn rõ; không chứa weights, SDK, secret, dump hay checkpoint.

Đóng gói phát hiện thêm sáu CE003 latest pointers do `tests/test_coding_feedback_oracles.py` cập nhật trong full suite. Đã đối chiếu từng target summary/SHA: frozen oracle PASS, hai native check, 0 model attempt; đây không phải thay đổi first model score. Builder đầu từ chối trước khi tạo ZIP và log được giữ. Policy cuối chỉ chấp nhận đúng12CE002+6CE003pointer, giữ byte archive cũ và ghi riêng SHA workspace; mọi immutable extra khác phải khớp.43delivery controls PASS/0SKIP/0,58 giây, gồm chặn pointer giả/unknown/archive hỏng/target có model call và active builder stdout.
